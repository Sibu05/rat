import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Outlet, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { fmtDate, sha7 } from '../util.js'

const RepoCtx = createContext(null)
export const useRepo = () => useContext(RepoCtx)

// Filter state -> API params. GET endpoints take shas as a comma list;
// the POST /metrics endpoint takes shas as an array, which toQuery preserves.
export function filterParams(filter) {
  const p = {}
  if (filter.mode === 'range') {
    if (filter.from) p.from_ts = Math.floor(new Date(`${filter.from}T00:00:00`).getTime() / 1000)
    if (filter.to) p.to_ts = Math.floor(new Date(`${filter.to}T00:00:00`).getTime() / 1000) + 86400
  }
  if (filter.mode === 'custom' && filter.shas.length) p.shas = filter.shas
  if (filter.authorId) p.author_id = Number(filter.authorId)
  return p
}

const DEFAULT_FILTER = { mode: 'all', from: '', to: '', shas: [], authorId: '' }

export default function RepoLayout() {
  const { id } = useParams()
  const [repo, setRepo] = useState(null)
  const [authors, setAuthors] = useState([])
  const [filter, setFilter] = useState(DEFAULT_FILTER)
  const [err, setErr] = useState('')
  const ready = repo?.status === 'ready'

  useEffect(() => {
    setRepo(null); setAuthors([]); setFilter(DEFAULT_FILTER); setErr('')
    let alive = true
    api.getRepo(id)
      .then((r) => { if (alive) setRepo(r) })
      .catch((e) => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [id])

  useEffect(() => {
    if (!repo || repo.status === 'ready' || repo.status === 'error') return
    const t = setInterval(async () => {
      try {
        const r = await api.getRepo(id)
        setRepo(r)
      } catch { /* keep polling */ }
    }, 2000)
    return () => clearInterval(t)
  }, [repo, id])

  useEffect(() => {
    if (!ready) return
    let alive = true
    api.getAuthors(id)
      .then((a) => { if (alive) setAuthors(a) })
      .catch(() => {})
    return () => { alive = false }
  }, [ready, id])

  const params = useMemo(() => filterParams(filter), [filter])

  const ctx = useMemo(
    () => ({ repo, authors, filter, setFilter, params }),
    [repo, authors, filter, params],
  )

  return (
    <>
      <div className="topbar">
        <div className="brand"><Link to="/">RAT</Link> <span>/ {repo?.name ?? '…'}</span></div>
        <div className="spacer" />
        {repo && (
          <span className="muted mono">
            {sha7(repo.head_sha)} · {fmtDate(repo.first_commit_date)} → {fmtDate(repo.last_commit_date)}
          </span>
        )}
      </div>
      <div className="page">
        {err && <div className="error-box">{err}</div>}
        {!repo && !err && <div className="empty">Loading…</div>}
        {repo && repo.status !== 'ready' && (
          <div className="panel">
            <h2>Status</h2>
            <p><span className={`badge ${repo.status}`}>{repo.status}</span></p>
            {repo.error && <div className="error-box">{repo.error}</div>}
            {repo.status !== 'error' && <p className="muted">Analysis is running — this page updates automatically.</p>}
          </div>
        )}
        {ready && (
          <RepoCtx.Provider value={ctx}>
            <FilterBar />
            <div className="tabs">
              <NavLink end to={`/repo/${id}`}>Overview</NavLink>
              <NavLink to={`/repo/${id}/explorer`}>Explorer</NavLink>
              <NavLink to={`/repo/${id}/authors`}>Authors</NavLink>
              <NavLink to={`/repo/${id}/commits`}>Commits</NavLink>
            </div>
            <Outlet />
          </RepoCtx.Provider>
        )}
      </div>
    </>
  )
}

function FilterBar() {
  const { authors, filter, setFilter } = useRepo()
  const patch = (p) => setFilter((f) => ({ ...f, ...p }))

  return (
    <div className="filterbar">
      <label>Commit set</label>
      <select
        value={filter.mode}
        onChange={(e) => patch({ mode: e.target.value })}
      >
        <option value="all">All commits</option>
        <option value="range">Date range</option>
        <option value="custom" disabled={filter.shas.length === 0}>
          Custom selection ({filter.shas.length})
        </option>
      </select>

      {filter.mode === 'range' && (
        <>
          <input type="date" value={filter.from} onChange={(e) => patch({ from: e.target.value })} />
          <span className="muted">to</span>
          <input type="date" value={filter.to} onChange={(e) => patch({ to: e.target.value })} />
        </>
      )}

      {filter.mode === 'custom' && (
        <>
          <span className="badge info">{filter.shas.length} commits</span>
          <button
            className="small"
            onClick={() => patch({ mode: 'all', shas: [] })}
          >
            Clear selection
          </button>
          <span className="muted" style={{ fontSize: 12 }}>
            Tick commits in the Commits tab, then pick “Custom selection” here.
          </span>
        </>
      )}

      <div className="sep" />
      <label>Author</label>
      <select
        value={filter.authorId}
        onChange={(e) => patch({ authorId: e.target.value })}
      >
        <option value="">All authors</option>
        {authors.map((a) => (
          <option key={a.identity_id} value={a.identity_id}>
            {a.name} &lt;{a.email}&gt;
          </option>
        ))}
      </select>
    </div>
  )
}
