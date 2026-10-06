import re
import subprocess

from .db import get_db, reset_repo_data

# %aN/%aE respect .mailmap. Unit separator \x1f between header fields.
LOG_FORMAT = "@@@%H%x1f%aN%x1f%aE%x1f%ct%x1f%s"
NUMSTAT_RE = re.compile(r"^(-|\d+)\t(-|\d+)\t(.*)$")
RENAME_RE = re.compile(r"^(.*?)\{(.*?) => (.*?)\}(.*)$")

BATCH = 20000


def resolve_rename(raw: str) -> str:
    """Map git's 'old => new' / '{old => new}' numstat path forms to the new path."""
    m = RENAME_RE.match(raw)
    if m:
        pre, _old, new, post = m.groups()
        # an empty replacement ('{dir => }/x') leaves a double slash at the junction
        return (pre + new + post).replace("//", "/")
    if " => " in raw:
        return raw.split(" => ", 1)[1]
    return raw


_QUICK_ESCAPES = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11}


def unquote_path(raw: str) -> str:
    """Decode git's C-style quoting of paths with non-ASCII/special bytes."""
    if len(raw) < 2 or not (raw.startswith('"') and raw.endswith('"')):
        return raw
    body, out, i = raw[1:-1], bytearray(), 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in _QUICK_ESCAPES:
                out.append(_QUICK_ESCAPES[nxt])
                i += 2
            elif nxt in ('"', "\\"):
                out.append(ord(nxt))
                i += 2
            elif i + 3 < len(body) and all(c in "01234567" for c in body[i + 1:i + 4]):
                out.append(int(body[i + 1:i + 4], 8))
                i += 4
            else:
                out.extend(ch.encode())
                i += 1
        else:
            out.extend(ch.encode())
            i += 1
    return out.decode("utf-8", errors="surrogateescape")


def analyze_repo(repo_id: int, ref: str | None = None):
    db = get_db()
    repo = db.execute("SELECT * FROM repos WHERE id=?", (repo_id,)).fetchone()
    if repo is None:
        return
    if not ref:
        ref = repo["head_sha"] or "HEAD"
    if ref.startswith("-"):
        raise ValueError(f"Invalid ref: {ref!r}")
    db.execute("UPDATE repos SET status='analyzing', error=NULL WHERE id=?", (repo_id,))
    db.commit()
    try:
        reset_repo_data(repo_id)
        resolved = _analyze(db, repo_id, repo["path"], ref)
        db.execute(
            "UPDATE repos SET status='ready', analyzed_ref=?, analyzed_at=datetime('now'), error=NULL WHERE id=?",
            (resolved, repo_id),
        )
        db.commit()
    except Exception as e:
        db.execute(
            "UPDATE repos SET status='error', error=? WHERE id=?",
            (str(e)[:1000], repo_id),
        )
        db.commit()


def _analyze(db, repo_id: int, workdir: str, ref: str):
    resolved = subprocess.run(
        ["git", "-C", workdir, "rev-parse", "--verify", f"{ref}^{{commit}}"] ,
        capture_output=True, text=True,
    )
    if resolved.returncode != 0:
        raise RuntimeError(f"Cannot resolve ref {ref!r} to a commit")
    resolved_sha = resolved.stdout.strip()
    proc = subprocess.Popen(
        [
            "git", "-C", workdir, "log", resolved_sha,
            "--numstat", "--no-merges", "-M50%",
            "--date=unix", f"--pretty=format:{LOG_FORMAT}",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        bufsize=1024 * 1024,
    )

    identity_cache: dict[tuple[str, str], int] = {}
    author_cache: dict[tuple[str, str], int] = {}

    def identity_id(name: str, email: str) -> int:
        key = (name, email)
        if key not in identity_cache:
            row = db.execute(
                "SELECT id FROM identities WHERE repo_id=? AND name=? AND email=?",
                (repo_id, name, email),
            ).fetchone()
            if row is None:
                cur = db.execute(
                    "INSERT INTO identities(repo_id, name, email) VALUES (?,?,?)",
                    (repo_id, name, email),
                )
                ident_id = cur.lastrowid
            else:
                ident_id = row["id"]
            identity_cache[key] = ident_id
        return identity_cache[key]

    def author_id(name: str, email: str) -> int:
        key = (name, email)
        if key not in author_cache:
            ident_id = identity_id(name, email)
            db.execute(
                "INSERT OR IGNORE INTO authors(repo_id, name, email, canonical_id) VALUES (?,?,?,?)",
                (repo_id, name, email, ident_id),
            )
            author_cache[key] = db.execute(
                "SELECT id FROM authors WHERE repo_id=? AND name=? AND email=?",
                (repo_id, name, email),
            ).fetchone()["id"]
        return author_cache[key]

    commit_rows = []
    change_rows = []
    path_rows = set()
    n_commits = 0
    n_changes = 0
    cur_sha = cur_author = cur_date = cur_subject = None
    idx = 0

    def flush():
        nonlocal n_commits, n_changes
        if commit_rows:
            db.executemany(
                "INSERT INTO commits(repo_id, sha, author_id, committer_date, subject, idx) "
                "VALUES (?,?,?,?,?,?)",
                commit_rows,
            )
            n_commits += len(commit_rows)
            commit_rows.clear()
        if change_rows:
            db.executemany(
                "INSERT INTO file_changes(repo_id, sha, path, added, removed) VALUES (?,?,?,?,?)",
                change_rows,
            )
            n_changes += len(change_rows)
            change_rows.clear()
        if path_rows:
            db.executemany(
                "INSERT OR IGNORE INTO paths(repo_id, path, is_dir) VALUES (?,?,?)",
                [(repo_id, p, d) for p, d in sorted(path_rows)],
            )
            path_rows.clear()
        db.execute(
            "UPDATE repos SET analyzed_commits=?, file_change_count=? WHERE id=?",
            (n_commits, n_changes, repo_id),
        )
        db.commit()

    def record_path(path: str):
        path_rows.add(("", 1))  # repository root
        parts = path.split("/")
        for i in range(1, len(parts)):
            path_rows.add(("/".join(parts[:i]), 1))
        path_rows.add((path, 0))

    for line in proc.stdout:
        line = line.rstrip("\n")
        if not line:
            continue
        if line.startswith("@@@"):
            if cur_sha is not None:
                commit_rows.append((repo_id, cur_sha, cur_author, cur_date, cur_subject, idx))
                idx += 1
                if len(commit_rows) >= BATCH:
                    flush()
            fields = line[3:].split("\x1f")
            if len(fields) != 5:
                raise ValueError(f"Malformed git log header: {line[:120]!r}")
            sha, name, email, cdate, subject = fields
            cur_sha, cur_date, cur_subject = sha, int(cdate), subject
            cur_author = author_id(name, email)
        else:
            m = NUMSTAT_RE.match(line)
            if not m or cur_sha is None:
                continue
            added_s, removed_s, raw_path = m.groups()
            if added_s == "-" or removed_s == "-":
                continue  # binary files are not measured
            path = resolve_rename(unquote_path(raw_path))
            if not path:
                continue
            record_path(path)
            change_rows.append((repo_id, cur_sha, path, int(added_s), int(removed_s)))

    if cur_sha is not None:
        commit_rows.append((repo_id, cur_sha, cur_author, cur_date, cur_subject, idx))
    flush()

    _, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed: {stderr.strip()[:500]}")

    stats = db.execute(
        "SELECT COUNT(*) n, MIN(committer_date) lo, MAX(committer_date) hi FROM commits WHERE repo_id=?",
        (repo_id,),
    ).fetchone()
    db.execute(
        "UPDATE repos SET commit_count=?, first_commit_date=?, last_commit_date=? WHERE id=?",
        (stats["n"], stats["lo"], stats["hi"], repo_id),
    )
    db.commit()
    return resolved_sha
