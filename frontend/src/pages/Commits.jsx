import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useRepo } from './RepoLayout.jsx'
import { fmt, fmtDateTime, sha7 } from '../util.js'

const PAGE = 100

export default function Commits() {
  const { repo, params, filter, setFilter } = useRepo()
  const [page, setPage] = useState(0)
  const [rows, setRows] = useState(null)
  const [hasNext, setHasNext] = useState(false)
  const [err, setErr] = useState('')
  const pkey = JSON.stringify(params)

  useEffect(() => { setPage(0) }, [pkey])

  useEffect(() => {
    let alive = true
    setRows(null); setErr('')
    api.getCommits(repo.id, { ...params, limit: PAGE + 1, offset: page * PAGE })
      .then((r) => {
        if (!alive) return
        setHasNext(r.length > PAGE)
        setRows(r.slice(0, PAGE))
      })
      .catch((e) => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [repo.id, pkey, page])

  const selectedShas = new Set(filter.shas)
  const toggleSha = (sha) => {
    setFilter((f) => {
      const n = new Set(f.shas)
      if (n.has(sha)) n.delete(sha); else n.add(sha)
      return { ...f, shas: [...n] }
    })
  }

  const clearSelection = () => setFilter((f) => ({ ...f, shas: [], mode: f.mode === 'custom' ? 'all' : f.mode }))

  return (
    <>
      {filter.shas.length > 0 && (
        <div className="selection-banner">
          <strong>{filter.shas.length} commit(s) selected</strong>
          <button
            className="small primary"
            onClick={() => setFilter((f) => ({ ...f, mode: 'custom' }))}
          >
            Apply as commit set
          </button>
          <button className="small" onClick={clearSelection}>Clear</button>
          {filter.mode === 'custom' && <span className="badge info">active</span>}
        </div>
      )}

      {err && <div className="error-box">{err}</div>}

      <div className="panel">
        <h2>Commits in set</h2>
        {rows == null ? (
          <div className="empty">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="empty">No commits match the current filters.</div>
        ) : (
          <table className="data">
            <thead>
              <tr><th></th><th>SHA</th><th>Date</th><th>Author</th><th>Message</th><th className="right">l⁺</th><th className="right">l⁻</th></tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.sha}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedShas.has(c.sha)}
                      onChange={() => toggleSha(c.sha)}
                      title="Select for custom commit set"
                    />
                  </td>
                  <td className="mono" title={c.sha}>{sha7(c.sha)}</td>
                  <td>{fmtDateTime(c.committer_date)}</td>
                  <td>{c.name}</td>
                  <td className="wrap" style={{ maxWidth: 420 }}>{c.subject}</td>
                  <td className="right">{fmt(c.added)}</td>
                  <td className="right">{fmt(c.removed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="pager">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</button>
          <span className="muted">page {page + 1}</span>
          <button disabled={!hasNext} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
    </>
  )
}
