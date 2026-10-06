import shutil
import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ingest, metrics
from .analyze import analyze_repo
from .db import get_db

app = FastAPI(title="RAT - Repo Analysis Tool")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

_jobs: set[int] = set()
_jobs_lock = threading.Lock()


def start_analysis(repo_id: int, ref: str | None = None):
    with _jobs_lock:
        if repo_id in _jobs:
            return
        _jobs.add(repo_id)

    def run():
        try:
            analyze_repo(repo_id, ref)
        finally:
            with _jobs_lock:
                _jobs.discard(repo_id)

    threading.Thread(target=run, daemon=True).start()


class UrlIn(BaseModel):
    url: str


class MergeIn(BaseModel):
    source_ids: list[int]
    target_id: int
    name: str | None = None
    email: str | None = None


class SplitIn(BaseModel):
    author_ids: list[int]


class MetricsQuery(BaseModel):
    path: str | None = None
    object_type: str = "repository"
    author_id: int | None = None
    from_ts: int | None = None
    to_ts: int | None = None
    shas: list[str] | None = None


def repo_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


def get_repo_row(repo_id: int):
    row = get_db().execute("SELECT * FROM repos WHERE id=?", (repo_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Repository not found")
    return row


def _require_ready(repo):
    if repo["status"] != "ready":
        raise HTTPException(409, f"Repository is not analyzed yet (status: {repo['status']})")


@app.on_event("startup")
def startup():
    db = get_db()
    db.execute(
        "UPDATE repos SET status='error', error='Interrupted by server restart' "
        "WHERE status IN ('pending','analyzing')"
    )
    db.commit()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/repos")
def list_repos():
    rows = get_db().execute("SELECT * FROM repos ORDER BY created_at DESC").fetchall()
    return [repo_dict(r) for r in rows]


@app.post("/api/repos/url", status_code=201)
def add_repo_url(body: UrlIn):
    try:
        repo_id = ingest.ingest_url(body.url)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    start_analysis(repo_id)
    return repo_dict(get_repo_row(repo_id))


@app.post("/api/repos/zip", status_code=201)
async def add_repo_zip(file: UploadFile = File(...)):
    data = await file.read()
    try:
        repo_id = ingest.ingest_zip(file.filename or "upload.zip", data)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    start_analysis(repo_id)
    return repo_dict(get_repo_row(repo_id))


@app.get("/api/repos/{repo_id}")
def get_repo(repo_id: int):
    return repo_dict(get_repo_row(repo_id))


@app.post("/api/repos/{repo_id}/reanalyze")
def reanalyze(repo_id: int, ref: str | None = None):
    get_repo_row(repo_id)
    start_analysis(repo_id, ref)
    return repo_dict(get_repo_row(repo_id))


@app.delete("/api/repos/{repo_id}")
def delete_repo(repo_id: int):
    row = get_repo_row(repo_id)
    db = get_db()
    db.execute("DELETE FROM repos WHERE id=?", (repo_id,))
    db.commit()
    shutil.rmtree(row["path"], ignore_errors=True)
    return {"ok": True}


# ------------------------- authors (identities) -------------------------

def _check_identity(repo_id: int, identity_id: int):
    row = get_db().execute(
        "SELECT id FROM identities WHERE id=? AND repo_id=?", (identity_id, repo_id)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Identity {identity_id} not found in this repository")


@app.get("/api/repos/{repo_id}/authors")
def authors(repo_id: int):
    get_repo_row(repo_id)
    return metrics.list_identities(repo_id)


@app.post("/api/repos/{repo_id}/authors/merge")
def merge_authors(repo_id: int, body: MergeIn):
    get_repo_row(repo_id)
    _check_identity(repo_id, body.target_id)
    for sid in body.source_ids:
        _check_identity(repo_id, sid)
    db = get_db()
    if body.name or body.email:
        cur = db.execute("SELECT name, email FROM identities WHERE id=?", (body.target_id,))
        row = cur.fetchone()
        db.execute(
            "UPDATE identities SET name=?, email=? WHERE id=?",
            (body.name or row["name"], body.email or row["email"], body.target_id),
        )
    marks = ",".join("?" * len(body.source_ids))
    db.execute(
        f"UPDATE authors SET canonical_id=? WHERE repo_id=? AND canonical_id IN ({marks})",
        [body.target_id, repo_id, *body.source_ids],
    )
    db.commit()
    return metrics.list_identities(repo_id)


@app.post("/api/repos/{repo_id}/authors/split")
def split_authors(repo_id: int, body: SplitIn):
    get_repo_row(repo_id)
    db = get_db()
    for aid in body.author_ids:
        row = db.execute(
            "SELECT id, name, email FROM authors WHERE id=? AND repo_id=?", (aid, repo_id)
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"Raw author {aid} not found in this repository")
        cur = db.execute(
            "INSERT INTO identities(repo_id, name, email) VALUES (?,?,?)",
            (repo_id, row["name"], row["email"]),
        )
        db.execute("UPDATE authors SET canonical_id=? WHERE id=?", (cur.lastrowid, aid))
    db.commit()
    return metrics.list_identities(repo_id)


# ------------------------- metrics -------------------------

@app.post("/api/repos/{repo_id}/metrics")
def query_metrics(repo_id: int, q: MetricsQuery):
    repo = get_repo_row(repo_id)
    _require_ready(repo)
    shas = metrics.expand_shas(repo_id, q.shas) if q.shas else None
    return metrics.compute_metrics(
        repo_id, q.path, q.object_type, q.author_id, q.from_ts, q.to_ts, shas
    )


@app.get("/api/repos/{repo_id}/metrics")
def query_metrics_get(repo_id: int, path: str | None = None,
                      object_type: str = "repository", author_id: int | None = None,
                      from_ts: int | None = None, to_ts: int | None = None):
    repo = get_repo_row(repo_id)
    _require_ready(repo)
    return metrics.compute_metrics(
        repo_id, path, object_type, author_id, from_ts, to_ts, None
    )


def _parse_shas(repo_id: int, shas: str | None):
    if not shas:
        return None
    return metrics.expand_shas(repo_id, [s.strip() for s in shas.split(",") if s.strip()])


@app.get("/api/repos/{repo_id}/tree")
def tree(repo_id: int, path: str = "", author_id: int | None = None,
         from_ts: int | None = None, to_ts: int | None = None,
         shas: str | None = None):
    repo = get_repo_row(repo_id)
    _require_ready(repo)
    return metrics.tree(repo_id, path, author_id, from_ts, to_ts, _parse_shas(repo_id, shas))


@app.get("/api/repos/{repo_id}/commits")
def commits(repo_id: int, path: str | None = None, object_type: str | None = None,
            author_id: int | None = None, from_ts: int | None = None,
            to_ts: int | None = None, limit: int = 200, offset: int = 0,
            shas: str | None = None):
    repo = get_repo_row(repo_id)
    _require_ready(repo)
    limit = min(max(limit, 1), 1000)
    return metrics.commit_history(
        repo_id, path, object_type, author_id, from_ts, to_ts, limit, offset,
        _parse_shas(repo_id, shas),
    )


@app.get("/api/repos/{repo_id}/series")
def series(repo_id: int, path: str | None = None, object_type: str | None = None,
           bucket: str = "month", author_id: int | None = None,
           from_ts: int | None = None, to_ts: int | None = None,
           shas: str | None = None):
    repo = get_repo_row(repo_id)
    _require_ready(repo)
    return metrics.series(
        repo_id, path, object_type, bucket, author_id, from_ts, to_ts,
        _parse_shas(repo_id, shas),
    )


# ------------------------- static frontend -------------------------

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
