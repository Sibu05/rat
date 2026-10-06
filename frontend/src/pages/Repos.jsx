import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { fmt, fmtDate, sha7 } from '../util.js'

export default function Repos() {
  const [repos, setRepos] = useState(null)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fileRef = useRef(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const list = await api.listRepos()
        if (alive) setRepos(list)
      } catch (e) {
        if (alive) setErr(e.message)
      }
    }
    load()
    const t = setInterval(load, 2000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const addUrl = async (e) => {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true); setErr('')
    try {
      await api.addByUrl(url.trim())
      setUrl('')
      setRepos(await api.listRepos())
    } catch (e2) {
      setErr(e2.message)
    } finally {
      setBusy(false)
    }
  }

  const addZip = async (file) => {
    if (!file) return
    setBusy(true); setErr('')
    try {
      await api.addByZip(file)
      setRepos(await api.listRepos())
    } catch (e2) {
      setErr(e2.message)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const remove = async (r) => {
    if (!window.confirm(`Delete repository "${r.name}" and all its data?`)) return
    await api.deleteRepo(r.id)
    setRepos(await api.listRepos())
  }

  const reanalyze = async (r) => {
    await api.reanalyze(r.id)
    setRepos(await api.listRepos())
  }

  return (
    <>
      <div className="topbar">
        <div className="brand">RAT <span>· Repo Analysis Tool</span></div>
        <div className="spacer" />
        <Link to="/">Repositories</Link>
      </div>
      <div className="page">
        <div className="panel">
          <h2>Add repository</h2>
          <form className="add-forms" onSubmit={addUrl}>
            <input
              type="url" placeholder="https://github.com/user/repo.git — clone URL"
              value={url} onChange={(e) => setUrl(e.target.value)} disabled={busy}
            />
            <button className="primary" disabled={busy || !url.trim()}>Clone &amp; analyze</button>
            <span className="muted">or</span>
            <input
              ref={fileRef} type="file" accept=".zip,application/zip"
              onChange={(e) => addZip(e.target.files[0])} disabled={busy}
            />
          </form>
        </div>

        {err && <div className="error-box">{err}</div>}

        <div className="panel">
          <h2>Repositories {repos != null && <span className="muted">({repos.length})</span>}</h2>
          {repos == null ? (
            <div className="empty">Loading…</div>
          ) : repos.length === 0 ? (
            <div className="empty">No repositories yet — add one above.</div>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Name</th><th>Status</th><th>Commits</th><th>Changes</th>
                  <th>First commit</th><th>Last commit</th><th>Analyzed</th><th></th>
                </tr>
              </thead>
              <tbody>
                {repos.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {r.status === 'ready' ? (
                        <Link to={`/repo/${r.id}`}><strong>{r.name}</strong></Link>
                      ) : (
                        <strong>{r.name}</strong>
                      )}
                      <div className="muted mono">{sha7(r.head_sha)} {r.source}</div>
                    </td>
                    <td>
                      <span className={`badge ${r.status}`}>{r.status}</span>
                      {r.status === 'error' && r.error && <div className="muted" style={{ fontSize: 11 }}>{r.error}</div>}
                    </td>
                    <td>{fmt(r.analyzed_commits || r.commit_count)}</td>
                    <td>{fmt(r.file_change_count)}</td>
                    <td>{fmtDate(r.first_commit_date)}</td>
                    <td>{fmtDate(r.last_commit_date)}</td>
                    <td>{r.analyzed_at ? r.analyzed_at.replace('T', ' ').slice(0, 16) : '—'}</td>
                    <td className="right">
                      {r.status === 'error' && (
                        <button className="small" onClick={() => reanalyze(r)}>Retry</button>
                      )}{' '}
                      <button className="small danger" onClick={() => remove(r)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
