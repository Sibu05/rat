"""Validate computed metrics against the reference CSVs from the brief.

Usage (from backend/):
    python3 compare_reference.py cJSON [redis|git]
"""
import csv
import sys
from pathlib import Path

from app import metrics
from app.db import get_db

REFS = {
    "cJSON": "/home/vmuser/Downloads/repo-references/cJSON_6d9f2443ab07.csv",
    "redis": "/home/vmuser/Downloads/repo-references/redis_b540ca49cba8.csv",
    "git": "/home/vmuser/Downloads/repo-references/git_5a7d1e8045ce.csv",
}

NUM_FIELDS = ("added", "removed", "growth", "churn", "modifications",
              "modification_frequency", "churn_rate", "ownership")


def approx(a, b):
    if a is None and (b is None or b == ""):
        return True
    if b is None or b == "":
        b = 0.0
    if a is None:
        a = 0.0
    return abs(float(a) - float(b)) <= max(1e-9, abs(float(b)) * 1e-9)


def main():
    names = sys.argv[1:] or ["cJSON"]
    overall_bad = 0
    for name in names:
        ref = REFS[name]
        db = get_db()
        repo = db.execute("SELECT * FROM repos WHERE name=?", (name,)).fetchone()
        if repo is None:
            print(f"[{name}] repo not ingested yet — skipping")
            overall_bad += 1
            continue
        if repo["status"] != "ready":
            print(f"[{name}] status={repo['status']} — not ready")
            overall_bad += 1
            continue
        with open(ref) as f:
            rows = list(csv.DictReader(f))
        ref_sha = rows[0]["ref_sha"]
        if repo["analyzed_ref"] != ref_sha:
            print(f"[{name}] analyzed_ref={repo['analyzed_ref']} != csv ref {ref_sha} — re-analyze first")
            overall_bad += 1
            continue

        # compute once per (object_type, path)
        objects = {}
        for r in rows:
            objects.setdefault((r["object_type"], r["path"]), None)
        computed = {}
        t0 = __import__("time").time()
        for ot, p in objects:
            path = None if ot == "repository" else p
            computed[(ot, p)] = metrics.compute_metrics(
                repo["id"], path, ot if ot != "repository" else "repository"
            )
        dt = __import__("time").time() - t0

        n_ok = n_bad = 0
        problems = []
        csv_churn_order = {}
        for r in rows:
            ot, p, author = r["object_type"], r["path"], r["author"]
            m = computed[(ot, p)]
            if author != "ALL":
                csv_churn_order.setdefault((ot, p), []).append(float(r["churn"] or 0))
            if author == "ALL":
                got = m
            else:
                if "<" in author:
                    aname, aemail = author.rsplit("<", 1)
                    aname, aemail = aname.strip(), aemail.rstrip(">").strip()
                else:
                    aname, aemail = author, ""
                got = next(
                    (a for a in m["by_author"] if a["email"] == aemail and a["name"] == aname),
                    None,
                )
                if got is None:
                    n_bad += 1
                    problems.append(f"MISSING AUTHOR {author} for {ot}:{p}")
                    continue
            for f in NUM_FIELDS:
                csv_val = r[f]
                got_val = got.get(f)
                if csv_val == "" and got_val is None:
                    continue
                if not approx(got_val if got_val is not None else 0.0, csv_val or 0.0):
                    n_bad += 1
                    problems.append(
                        f"{ot}:{p} {author or 'ALL'} field {f}: csv={csv_val} got={got_val}"
                    )
                    break
            else:
                n_ok += 1

        # author rows must appear in non-increasing churn order (ties allowed)
        for key, seq in csv_churn_order.items():
            if any(seq[i] < seq[i + 1] for i in range(len(seq) - 1)):
                n_bad += 1
                problems.append(f"{key[0]}:{key[1]} CSV author rows not in churn-descending order")
            ours = [a["churn"] for a in computed[key]["by_author"]]
            if any(ours[i] < ours[i + 1] for i in range(len(ours) - 1)):
                n_bad += 1
                problems.append(f"{key[0]}:{key[1]} by_author not in churn-descending order")

        print(f"[{name}] {n_ok}/{len(rows)} rows match ({dt:.1f}s for {len(objects)} objects); mismatches: {n_bad}")
        for p in problems[:20]:
            print("   ", p)
        overall_bad += n_bad
    sys.exit(1 if overall_bad else 0)


if __name__ == "__main__":
    main()
