from .db import get_db

MAX_SHAS = 5000
BUCKETS = {"day": 86400, "week": 604800, "month": 2629746, "year": 31556952}


def object_condition(object_type: str | None, path: str | None):
    """SQL fragment + params matching file_changes rows for the object."""
    if not object_type or object_type == "repository" or path in (None, "", "/"):
        return "1=1", []
    if object_type == "directory":
        pre = path.rstrip("/") + "/"
        return "fc.path >= ? AND fc.path < ?", [pre, pre + "\x7f"]
    return "fc.path = ?", [path]


def commit_set_condition(from_ts=None, to_ts=None, shas=None, alias="c"):
    conds, params = [], []
    if shas:
        shas = shas[:MAX_SHAS]
        conds.append(f"{alias}.sha IN ({','.join('?' * len(shas))})")
        params.extend(shas)
    else:
        if from_ts is not None:
            conds.append(f"{alias}.committer_date >= ?")
            params.append(int(from_ts))
        if to_ts is not None:
            conds.append(f"{alias}.committer_date < ?")
            params.append(int(to_ts))
    return (" AND ".join(conds) or "1=1"), params


def _author_filter(author_id):
    return "c.author_id IN (SELECT id FROM authors WHERE canonical_id=?)", [author_id]


def expand_shas(repo_id, shas: list[str]) -> list[str]:
    """Expand possibly-abbreviated sha prefixes to full shas; drop unknown ones."""
    db = get_db()
    out = []
    for s in shas:
        s = s.strip()
        if not s:
            continue
        row = db.execute(
            "SELECT sha FROM commits WHERE repo_id=? AND sha=?", (repo_id, s)
        ).fetchone()
        if row:
            out.append(row["sha"])
            continue
        matches = db.execute(
            "SELECT sha FROM commits WHERE repo_id=? AND sha LIKE ? LIMIT 2",
            (repo_id, s + "%"),
        ).fetchall()
        if len(matches) == 1:
            out.append(matches[0]["sha"])
    return out


def commit_count(repo_id, author_id=None, from_ts=None, to_ts=None, shas=None) -> int:
    db = get_db()
    set_sql, set_params = commit_set_condition(from_ts, to_ts, shas)
    conds = [f"c.repo_id=?", set_sql]
    params = [repo_id, *set_params]
    if author_id:
        a_sql, a_params = _author_filter(author_id)
        conds.append(a_sql)
        params.extend(a_params)
    return db.execute(
        f"SELECT COUNT(*) n FROM commits c WHERE {' AND '.join(conds)}", params
    ).fetchone()["n"]


def compute_metrics(repo_id, path=None, object_type="repository",
                    author_id=None, from_ts=None, to_ts=None, shas=None) -> dict:
    """All commit-set + author metrics for one object (file, directory, or repository)."""
    db = get_db()
    H = commit_count(repo_id, author_id, from_ts, to_ts, shas)
    set_sql, set_params = commit_set_condition(from_ts, to_ts, shas)
    obj_sql, obj_params = object_condition(object_type, path)
    conds = ["fc.repo_id=?", "c.repo_id=?", set_sql, obj_sql]
    params = [repo_id, repo_id, *set_params, *obj_params]
    if author_id:
        a_sql, a_params = _author_filter(author_id)
        conds.append(a_sql)
        params.extend(a_params)
    row = db.execute(
        f"""
        SELECT COALESCE(SUM(fc.added), 0) AS added, COALESCE(SUM(fc.removed), 0) AS removed,
               COUNT(DISTINCT CASE WHEN fc.added + fc.removed > 0 THEN fc.sha END) AS modifications
        FROM file_changes fc
        JOIN commits c ON c.repo_id = fc.repo_id AND c.sha = fc.sha
        WHERE {' AND '.join(conds)}
        """,
        params,
    ).fetchone()
    added, removed, n = row["added"], row["removed"], row["modifications"]
    churn = added + removed
    out = {
        "path": path or "/",
        "object_type": object_type or "repository",
        "commit_count": H,
        "added": added,
        "removed": removed,
        "growth": added - removed,
        "churn": churn,
        "modifications": n,
        "modification_frequency": n / H if H else 0.0,
        "churn_rate": churn / H if H else 0.0,
    }
    if author_id is None:
        out["by_author"] = author_breakdown(repo_id, path, object_type, from_ts, to_ts, shas)
    return out


def author_breakdown(repo_id, path=None, object_type=None, from_ts=None, to_ts=None, shas=None) -> list[dict]:
    db = get_db()
    set_sql, set_params = commit_set_condition(from_ts, to_ts, shas)
    obj_sql, obj_params = object_condition(object_type, path)
    conds = ["fc.repo_id=?", "c.repo_id=?", set_sql, obj_sql]
    params = [repo_id, repo_id, *set_params, *obj_params]
    rows = db.execute(
        f"""
        SELECT i.id, i.name, i.email,
               SUM(fc.added) AS added, SUM(fc.removed) AS removed,
               COUNT(DISTINCT CASE WHEN fc.added + fc.removed > 0 THEN fc.sha END) AS modifications
        FROM file_changes fc
        JOIN commits c ON c.repo_id = fc.repo_id AND c.sha = fc.sha
        JOIN authors a ON a.id = c.author_id
        JOIN identities i ON i.id = a.canonical_id
        WHERE {' AND '.join(conds)}
        GROUP BY i.id
        ORDER BY SUM(fc.added) + SUM(fc.removed) DESC
        """,
        params,
    ).fetchall()
    total_churn = sum(r["added"] + r["removed"] for r in rows) or 0
    out = []
    for r in rows:
        churn = r["added"] + r["removed"]
        out.append({
            "identity_id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "added": r["added"],
            "removed": r["removed"],
            "growth": r["added"] - r["removed"],
            "churn": churn,
            "modifications": r["modifications"],
            "modification_frequency": None,
            "churn_rate": None,
            "ownership": churn / total_churn if total_churn else 0.0,
        })
    return out


def tree(repo_id, path="", author_id=None, from_ts=None, to_ts=None, shas=None,
         with_owners=True) -> list[dict]:
    """Immediate children of a directory with their commit-set metrics."""
    db = get_db()
    pre = (path.rstrip("/") + "/") if path else ""
    set_sql, set_params = commit_set_condition(from_ts, to_ts, shas)
    obj_sql, obj_params = object_condition("directory", path)
    conds = ["fc.repo_id=?", "c.repo_id=?", set_sql, obj_sql]
    params = [repo_id, repo_id, *set_params, *obj_params]
    if author_id:
        a_sql, a_params = _author_filter(author_id)
        conds.append(a_sql)
        params.extend(a_params)
    rest = f"substr(fc.path, {len(pre) + 1})"
    nested = f"instr({rest}, '/') > 0"
    name_expr = f"CASE WHEN {nested} THEN substr({rest}, 1, instr({rest}, '/') - 1) ELSE {rest} END"
    rows = db.execute(
        f"""
        SELECT {name_expr} AS name,
               MAX(CASE WHEN {nested} THEN 1 ELSE 0 END) AS is_dir,
               SUM(fc.added) AS added, SUM(fc.removed) AS removed,
               COUNT(DISTINCT CASE WHEN fc.added + fc.removed > 0 THEN fc.sha END) AS modifications
        FROM file_changes fc
        JOIN commits c ON c.repo_id = fc.repo_id AND c.sha = fc.sha
        WHERE {' AND '.join(conds)}
        GROUP BY name
        """,
        params,
    ).fetchall()
    H = commit_count(repo_id, author_id, from_ts, to_ts, shas)
    by_name = {r["name"]: r for r in rows}
    children = db.execute(
        "SELECT path, is_dir FROM paths WHERE repo_id=? AND path > ? AND path < ? "
        "AND instr(substr(path, ?), '/') = 0",
        (repo_id, pre, pre + "\x7f", len(pre) + 1),
    ).fetchall()
    out = []
    for ch in children:
        name = ch["path"][len(pre):]
        agg = by_name.get(name)
        added = agg["added"] if agg else 0
        removed = agg["removed"] if agg else 0
        n = agg["modifications"] if agg else 0
        churn = added + removed
        item = {
            "name": name,
            "path": ch["path"],
            "is_dir": bool(ch["is_dir"]),
            "added": added,
            "removed": removed,
            "growth": added - removed,
            "churn": churn,
            "modifications": n,
            "modification_frequency": n / H if H else 0.0,
            "churn_rate": churn / H if H else 0.0,
        }
        if with_owners:
            item["top_author"] = top_owner(
                repo_id, ch["path"], "directory" if ch["is_dir"] else "file",
                from_ts, to_ts, shas,
            )
        out.append(item)
    out.sort(key=lambda x: (-x["is_dir"], -x["churn"]))
    return out


def top_owner(repo_id, path, object_type, from_ts=None, to_ts=None, shas=None):
    db = get_db()
    set_sql, set_params = commit_set_condition(from_ts, to_ts, shas)
    obj_sql, obj_params = object_condition(object_type, path)
    row = db.execute(
        f"""
        SELECT i.name, i.email, SUM(fc.added + fc.removed) AS churn
        FROM file_changes fc
        JOIN commits c ON c.repo_id = fc.repo_id AND c.sha = fc.sha
        JOIN authors a ON a.id = c.author_id
        JOIN identities i ON i.id = a.canonical_id
        WHERE fc.repo_id=? AND c.repo_id=? AND {set_sql} AND {obj_sql}
        GROUP BY i.id ORDER BY churn DESC LIMIT 1
        """,
        [repo_id, repo_id, *set_params, *obj_params],
    ).fetchone()
    if not row:
        return None
    return {"name": row["name"], "email": row["email"], "churn": row["churn"]}


def commit_history(repo_id, path=None, object_type=None, author_id=None,
                   from_ts=None, to_ts=None, limit=200, offset=0, shas=None) -> list[dict]:
    """Commits in the set, most recent first, with per-commit line stats for the object."""
    db = get_db()
    set_sql, set_params = commit_set_condition(from_ts, to_ts, shas)
    conds = ["c.repo_id=?", set_sql]
    params = [repo_id, *set_params]
    if author_id:
        a_sql, a_params = _author_filter(author_id)
        conds.append(a_sql)
        params.extend(a_params)
    obj_sql, obj_params = object_condition(object_type, path)
    if object_type and not (object_type == "repository" or path in (None, "", "/")):
        conds.append(
            f"EXISTS (SELECT 1 FROM file_changes fx WHERE fx.repo_id=c.repo_id "
            f"AND fx.sha=c.sha AND {obj_sql})"
        )
        params.extend(obj_params)
    rows = db.execute(
        f"""
        SELECT c.sha, c.committer_date, c.subject,
               i.id AS identity_id, i.name, i.email,
               COALESCE(SUM(fc.added), 0) AS added, COALESCE(SUM(fc.removed), 0) AS removed
        FROM commits c
        JOIN authors a ON a.id = c.author_id
        JOIN identities i ON i.id = a.canonical_id
        LEFT JOIN file_changes fc ON fc.repo_id = c.repo_id AND fc.sha = c.sha AND {obj_sql}
        WHERE {' AND '.join(conds)}
        GROUP BY c.sha
        ORDER BY c.committer_date DESC, c.idx ASC
        LIMIT ? OFFSET ?
        """,
        [*obj_params, *params, limit, offset],
    ).fetchall()
    return [
        {
            "sha": r["sha"], "committer_date": r["committer_date"], "subject": r["subject"],
            "identity_id": r["identity_id"], "name": r["name"], "email": r["email"],
            "added": r["added"], "removed": r["removed"],
            "growth": r["added"] - r["removed"], "churn": r["added"] + r["removed"],
        }
        for r in rows
    ]


def series(repo_id, path=None, object_type=None, bucket="month",
           author_id=None, from_ts=None, to_ts=None, shas=None) -> list[dict]:
    """Added/removed lines per time bucket for charts."""
    db = get_db()
    secs = BUCKETS.get(bucket, BUCKETS["month"])
    set_sql, set_params = commit_set_condition(from_ts, to_ts, shas)
    obj_sql, obj_params = object_condition(object_type, path)
    conds = ["fc.repo_id=?", "c.repo_id=?", set_sql, obj_sql]
    params = [repo_id, repo_id, *set_params, *obj_params]
    if author_id:
        a_sql, a_params = _author_filter(author_id)
        conds.append(a_sql)
        params.extend(a_params)
    rows = db.execute(
        f"""
        SELECT (c.committer_date / ?) * ? AS t,
               SUM(fc.added) AS added, SUM(fc.removed) AS removed,
               COUNT(DISTINCT c.sha) AS commits
        FROM file_changes fc
        JOIN commits c ON c.repo_id = fc.repo_id AND c.sha = fc.sha
        WHERE {' AND '.join(conds)}
        GROUP BY t ORDER BY t
        """,
        [secs, secs, *params],
    ).fetchall()
    return [
        {"t": r["t"], "added": r["added"], "removed": r["removed"], "commits": r["commits"]}
        for r in rows
    ]


def list_identities(repo_id) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """
        SELECT i.id, i.name, i.email,
               COUNT(DISTINCT c.sha) AS commits,
               COALESCE(SUM(fc.added), 0) AS added, COALESCE(SUM(fc.removed), 0) AS removed,
               COUNT(DISTINCT CASE WHEN fc.added + fc.removed > 0 THEN fc.sha END) AS modifications
        FROM identities i
        JOIN authors a ON a.canonical_id = i.id
        JOIN commits c ON c.author_id = a.id
        LEFT JOIN file_changes fc ON fc.repo_id = c.repo_id AND fc.sha = c.sha
        WHERE i.repo_id = ?
        GROUP BY i.id
        ORDER BY COALESCE(SUM(fc.added), 0) + COALESCE(SUM(fc.removed), 0) DESC
        """,
        (repo_id,),
    ).fetchall()
    aliases = db.execute(
        "SELECT id, name, email, canonical_id FROM authors WHERE repo_id=?", (repo_id,)
    ).fetchall()
    by_ident: dict[int, list] = {}
    for al in aliases:
        by_ident.setdefault(al["canonical_id"], []).append(
            {"author_id": al["id"], "name": al["name"], "email": al["email"]}
        )
    out = []
    for r in rows:
        churn = r["added"] + r["removed"]
        out.append({
            "identity_id": r["id"], "name": r["name"], "email": r["email"],
            "commits": r["commits"], "added": r["added"], "removed": r["removed"],
            "churn": churn, "modifications": r["modifications"],
            "aliases": by_ident.get(r["id"], []),
            "merged": len(by_ident.get(r["id"], [])) > 1,
        })
    return out
