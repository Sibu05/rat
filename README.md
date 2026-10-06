# RAT — Repo Analysis Tool

A web-app dashboard for analysing how git repositories evolve: who changed what,
where the churn is, and which parts of a project are most volatile. Built for the
COMS3011A test brief.

## What it does

- **Repository ingestion, two ways**
  - Upload a **zip file** containing a repo with its `.git` file or directory
  - Paste a **remote repository URL**, which is deeply cloned
  - Multiple repositories are supported side by side
- **Author identity merging** — authors with different names/emails are merged
  using the repo's `.mailmap` when present, and can be merged manually in the UI
- **Metrics at every level**, filterable by repository, author, file/directory,
  and commit set (all commits, a time period, or a hand-picked list of commits):
  - **File metrics** — added lines `l⁺`, removed lines `l⁻`, growth `δ`, churn `λ` per commit
  - **Directory metrics** — the same, aggregated recursively over immediate children
  - **Repository metrics** — directory metrics applied at the root
  - **Commit-set metrics** — totals over any set `H` of non-merge commits, plus
    modifications `n`, modification frequency `n/|H|`, churn rate `λ/|H|`
  - **Author metrics** — per-author modifications, churn, and ownership `ω`
    (fraction of an object's churn attributable to that author)
- **Git semantics honoured** — merge commits excluded; binary files not measured;
  rename detection at the 50 % threshold (a pure rename does not change an
  object's metrics; changes are attributed to the new path); deletions are
  recorded as removed lines on the deleted path

## Architecture

```
git repo ──(git log --numstat --no-merges -M50%, one pass)──► SQLite ──► FastAPI ──► React dashboard
```

History is parsed **once** per repository into an indexed SQLite store
(`data/rat.db`). Every metric query is then a SQL aggregation over the selected
commit set, which keeps the dashboard responsive even on repositories with
~100 000 commits (git itself does the line counting and rename detection, so the
numbers match `git log` exactly).

## Running it

```bash
./run.sh                  # full app on http://127.0.0.1:8000 (UI + API)
PORT=9000 ./run.sh        # custom port
```

`run.sh` installs Python dependencies, builds the React frontend if needed,
and serves everything from FastAPI. Requirements: Python 3.10+, git, and
(for building the UI) Node 18+.

Frontend development server (hot reload, proxies `/api`):

```bash
cd frontend && npm install && npm run dev   # dashboard on http://localhost:5173
```

Interactive API documentation (Swagger UI) is served at `/docs` while the server
runs — handy for trying every endpoint without the frontend.

## Validating against the reference data

```bash
cd backend && python3 compare_reference.py cjson redis git
```

Compares computed metrics row-by-row against the reference CSVs
(`~/Downloads/repo-references/`) for every object and author in each
repository. All rows match exactly for cJSON (983), Redis (18 301) and
git (62 601) at their reference commits.

## Layout

```
backend/app/
  main.py     FastAPI routes (repos, analysis jobs)
  ingest.py   zip upload + URL clone, validation
  analyze.py  git log parsing into SQLite
  metrics.py  metric computations over commit sets
  db.py       SQLite schema and connections
frontend/     React dashboard (Vite)
data/         cloned/uploaded repos and rat.db
run.sh        one-command launcher
```
