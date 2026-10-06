import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .db import REPO_DIR, get_db

ALLOWED_URL_SCHEMES = ("http://", "https://", "git://", "ssh://", "git@")


class IngestError(Exception):
    pass


def _git(*args, cwd=None, timeout=1800):
    return subprocess.run(
        ["git", *args], cwd=cwd, timeout=timeout,
        capture_output=True, text=True,
    )


def _unique_name(base: str) -> str:
    name, i = base, 2
    db = get_db()
    while db.execute("SELECT 1 FROM repos WHERE name=?", (name,)).fetchone():
        name = f"{base}-{i}"
        i += 1
    return name


def _valid_repo_dir(path: Path) -> bool:
    if not ((path / ".git").is_dir() or (path / ".git").is_file()):
        return False
    r = _git("-C", str(path), "rev-parse", "--verify", "HEAD")
    return r.returncode == 0


def _find_repo_root(extract_root: Path) -> Path:
    if _valid_repo_dir(extract_root):
        return extract_root
    children = [p for p in extract_root.iterdir() if p.is_dir()]
    for child in children:
        if _valid_repo_dir(child):
            return child
    raise IngestError("No git repository found in the zip (a .git file or directory is required).")


def _safe_extract(zf: zipfile.ZipFile, dest: Path):
    for member in zf.infolist():
        name = member.filename
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            raise IngestError(f"Unsafe path in zip archive: {name!r}")
    zf.extractall(dest)


def ingest_zip(filename: str, data: bytes) -> int:
    if not data:
        raise IngestError("Empty file uploaded.")
    base = re.sub(r"\.zip$", "", Path(filename).name, flags=re.I) or "uploaded-repo"
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-") or "repo"
    with tempfile.TemporaryDirectory(dir=REPO_DIR) as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                _safe_extract(zf, tmp_path)
        except zipfile.BadZipFile:
            raise IngestError("The uploaded file is not a valid zip archive.")
        src = _find_repo_root(tmp_path)
        name = _unique_name(base)
        dest = REPO_DIR / name
        shutil.move(str(src), str(dest))
    if not _valid_repo_dir(dest):
        shutil.rmtree(dest, ignore_errors=True)
        raise IngestError("Extracted directory is not a usable git repository.")
    return _register_repo(name, "zip", dest)


def ingest_url(url: str) -> int:
    url = url.strip()
    if not url.startswith(ALLOWED_URL_SCHEMES):
        raise IngestError("URL must start with http://, https://, git://, ssh:// or git@")
    base = url.rstrip("/").rsplit("/", 1)[-1]
    base = re.sub(r"\.git$", "", base) or "cloned-repo"
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-") or "repo"
    name = _unique_name(base)
    dest = REPO_DIR / name
    r = _git("clone", "--no-single-branch", url, str(dest), timeout=3600)
    if r.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise IngestError(f"git clone failed: {r.stderr.strip()[:500]}")
    if not _valid_repo_dir(dest):
        shutil.rmtree(dest, ignore_errors=True)
        raise IngestError("Cloned repository has no commits.")
    return _register_repo(name, "url", dest)


def _register_repo(name: str, source: str, path: Path) -> int:
    head = _git("-C", str(path), "rev-parse", "HEAD").stdout.strip()
    db = get_db()
    cur = db.execute(
        "INSERT INTO repos(name, source, path, head_sha, status) VALUES (?,?,?,?,'pending')",
        (name, source, str(path), head),
    )
    db.commit()
    return cur.lastrowid
