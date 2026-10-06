import sqlite3
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DATA_DIR / "rat.db"
REPO_DIR = DATA_DIR / "repos"

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    head_sha TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    analyzed_ref TEXT,
    commit_count INTEGER NOT NULL DEFAULT 0,
    analyzed_commits INTEGER NOT NULL DEFAULT 0,
    file_change_count INTEGER NOT NULL DEFAULT 0,
    first_commit_date INTEGER,
    last_commit_date INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    analyzed_at TEXT
);

CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_identities_repo ON identities(repo_id);

CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    canonical_id INTEGER NOT NULL REFERENCES identities(id),
    UNIQUE (repo_id, name, email)
);
CREATE INDEX IF NOT EXISTS idx_authors_canonical ON authors(canonical_id);

CREATE TABLE IF NOT EXISTS commits (
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    sha TEXT NOT NULL,
    author_id INTEGER NOT NULL REFERENCES authors(id),
    committer_date INTEGER NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    idx INTEGER NOT NULL,
    PRIMARY KEY (repo_id, sha)
);
CREATE INDEX IF NOT EXISTS idx_commits_repo_date ON commits(repo_id, committer_date);
CREATE INDEX IF NOT EXISTS idx_commits_repo_author ON commits(repo_id, author_id);

CREATE TABLE IF NOT EXISTS file_changes (
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    sha TEXT NOT NULL,
    path TEXT NOT NULL,
    added INTEGER NOT NULL,
    removed INTEGER NOT NULL,
    PRIMARY KEY (repo_id, sha, path)
);
CREATE INDEX IF NOT EXISTS idx_fc_path ON file_changes(repo_id, path);
CREATE INDEX IF NOT EXISTS idx_fc_sha ON file_changes(repo_id, sha);

CREATE TABLE IF NOT EXISTS paths (
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    is_dir INTEGER NOT NULL,
    PRIMARY KEY (repo_id, path)
);
"""


def get_db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        REPO_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        _migrate(conn)
        _local.conn = conn
    return conn


def _migrate(conn: sqlite3.Connection):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(repos)")}
    if "analyzed_ref" not in cols:
        conn.execute("ALTER TABLE repos ADD COLUMN analyzed_ref TEXT")
        conn.commit()
    idx = [r[1] for r in conn.execute("PRAGMA index_list(identities)")]
    if any("autoindex" in name for name in idx):
        # drop the old UNIQUE(repo_id,name,email): manual author splits may need
        # an identity that collides with an existing name/email pair
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            """
            BEGIN;
            CREATE TABLE identities_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                email TEXT NOT NULL
            );
            INSERT INTO identities_new SELECT id, repo_id, name, email FROM identities;
            DROP TABLE identities;
            ALTER TABLE identities_new RENAME TO identities;
            CREATE INDEX idx_identities_repo ON identities(repo_id);
            COMMIT;
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")


def reset_repo_data(repo_id: int):
    db = get_db()
    db.execute("DELETE FROM file_changes WHERE repo_id=?", (repo_id,))
    db.execute("DELETE FROM commits WHERE repo_id=?", (repo_id,))
    db.execute("DELETE FROM authors WHERE repo_id=?", (repo_id,))
    db.execute("DELETE FROM identities WHERE repo_id=?", (repo_id,))
    db.execute("DELETE FROM paths WHERE repo_id=?", (repo_id,))
    db.commit()
