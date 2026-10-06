import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { useRepo } from './RepoLayout.jsx'
import BackButton from '../components/BackButton.jsx'
import { fmt, fmtDateTime, fmtFloat, fmtPct, sha7 } from '../util.js'

const PAGE = 100

export default function Explorer() {
  const { id } = useParams()
  const [searchParams] = useSearchParams()
  const path = searchParams.get('path') || ''
  const kind = searchParams.get('kind') || 'directory'

  const parent = path ? path.split('/').slice(0, -1).join('/') : ''
  const fallback = `/repo/${id}/explorer${parent ? `?path=${encodeURIComponent(parent)}` : ''}`

  return (
    <>
      <div className="breadcrumb">
        {path && <BackButton fallback={fallback} />}
        <Breadcrumb repoId={id} path={path} isFile={kind === 'file'} />
      </div>
      {kind === 'file' ? <FileDetail path={path} /> : <DirListing path={path} />}
    </>
  )
}

function Breadcrumb({ repoId, path, isFile }) {
  const crumbs = path ? path.split('/') : []
  const visible = isFile ? crumbs.slice(0, -1) : crumbs
  const leaf = isFile ? crumbs[crumbs.length - 1] : null
  let acc = ''
  return (
    <>
      <Link to={`/repo/${repoId}/explorer`}>root</Link>
      {visible.map((seg) => {
        acc = acc ? `${acc}/${seg}` : seg
        const target = acc
        return (
          <span key={target}>
            <span className="muted">/</span>{' '}
            <Link to={`/repo/${repoId}/explorer?path=${encodeURIComponent(target)}`}>{seg}</Link>
          </span>
        )
      })}
      {leaf && (
        <span>
          <span className="muted">/</span> <span className="mono">{leaf}</span>
        </span>
      )}
    </>
  )
}

function DirListing({ path }) {
  const { repo, params } = useRepo()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const pkey = JSON.stringify(params)

  useEffect(() => {
    let alive = true
    setRows(null); setErr('')
    api.getTree(repo.id, { path, ...params })
      .then((r) => { if (alive) setRows(r) })
      .catch((e) => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [repo.id, path, pkey])

  if (err) return <div className="error-box">{err}</div>
  if (!rows) return <div className="empty">Loading…</div>
  if (rows.length === 0) return <div className="empty">No files match this commit set.</div>

  return (
    <div className="panel">
      <table className="data">
        <thead>
          <tr>
            <th>Name</th><th className="right">Churn λ</th><th className="right">Growth δ</th>
            <th className="right">Modifications</th><th className="right">Frequency n/|H|</th>
            <th className="right">Churn rate λ/|H|</th><th>Top author</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.path}>
              <td>
                {r.is_dir ? (
                  <Link to={`/repo/${repo.id}/explorer?path=${encodeURIComponent(r.path)}`}>
                    <strong>{r.name}/</strong>
                  </Link>
                ) : (
                  <Link to={`/repo/${repo.id}/explorer?path=${encodeURIComponent(r.path)}&kind=file`}>
                    {r.name}
                  </Link>
                )}
              </td>
              <td className="right">{fmt(r.churn)}</td>
              <td className={`right ${r.growth >= 0 ? 'pos' : 'neg'}`}>{fmt(r.growth)}</td>
              <td className="right">{fmt(r.modifications)}</td>
              <td className="right">{fmtFloat(r.modification_frequency, 4)}</td>
              <td className="right">{fmtFloat(r.churn_rate)}</td>
              <td>
                {r.top_author ? (
                  <>
                    {r.top_author.name}{' '}
                    <span className="muted">{fmtPct(r.churn ? r.top_author.churn / r.churn : null)}</span>
                  </>
                ) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FileDetail({ path }) {
  const { repo, params } = useRepo()
  const [m, setM] = useState(null)
  const [page, setPage] = useState(0)
  const [rows, setRows] = useState([])
  const [hasNext, setHasNext] = useState(false)
  const [err, setErr] = useState('')
  const pkey = JSON.stringify(params)

  useEffect(() => { setPage(0) }, [path, pkey])

  useEffect(() => {
    let alive = true
    setM(null); setErr('')
    api.getMetrics(repo.id, { path, object_type: 'file', ...params })
      .then((r) => { if (alive) setM(r) })
      .catch((e) => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [repo.id, path, pkey])

  useEffect(() => {
    let alive = true
    api.getCommits(repo.id, { path, object_type: 'file', ...params, limit: PAGE + 1, offset: page * PAGE })
      .then((r) => {
        if (!alive) return
        setHasNext(r.length > PAGE)
        setRows(r.slice(0, PAGE))
      })
      .catch(() => {})
    return () => { alive = false }
  }, [repo.id, path, pkey, page])

  if (err) return <div className="error-box">{err}</div>
  if (!m) return <div className="empty">Loading…</div>

  const kpis = [
    { label: 'Commits |H|', value: fmt(m.commit_count) },
    { label: 'Added l⁺', value: fmt(m.added) },
    { label: 'Removed l⁻', value: fmt(m.removed) },
    { label: 'Growth δ', value: fmt(m.growth), cls: m.growth >= 0 ? 'pos' : 'neg' },
    { label: 'Churn λ', value: fmt(m.churn) },
    { label: 'Modifications n', value: fmt(m.modifications) },
    { label: 'Frequency n/|H|', value: fmtFloat(m.modification_frequency, 4) },
    { label: 'Churn rate λ/|H|', value: fmtFloat(m.churn_rate) },
  ]

  return (
    <>
      <div className="kpis">
        {kpis.map((k) => (
          <div className="kpi" key={k.label}>
            <div className="label">{k.label}</div>
            <div className={`value ${k.cls || ''}`}>{k.value}</div>
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>Authors touching this file</h2>
          <table className="data">
            <thead>
              <tr><th>Author</th><th className="right">l⁺</th><th className="right">l⁻</th><th className="right">δ</th><th className="right">λ</th><th className="right">Ownership ω</th></tr>
            </thead>
            <tbody>
              {(m.by_author || []).map((a) => (
                <tr key={a.identity_id}>
                  <td>{a.name}<div className="muted mono">{a.email}</div></td>
                  <td className="right">{fmt(a.added)}</td>
                  <td className="right">{fmt(a.removed)}</td>
                  <td className={`right ${a.growth >= 0 ? 'pos' : 'neg'}`}>{fmt(a.growth)}</td>
                  <td className="right">{fmt(a.churn)}</td>
                  <td className="right">{fmtPct(a.ownership)}</td>
                </tr>
              ))}
              {(m.by_author || []).length === 0 && (
                <tr><td colSpan="6" className="muted">No authors for this commit set.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h2>Commits touching this file</h2>
          <table className="data">
            <thead>
              <tr><th>Commit</th><th>Date</th><th>Author</th><th className="right">l⁺</th><th className="right">l⁻</th></tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.sha}>
                  <td className="mono" title={c.sha}>{sha7(c.sha)}</td>
                  <td>{fmtDateTime(c.committer_date)}</td>
                  <td>{c.name}</td>
                  <td className="right">{fmt(c.added)}</td>
                  <td className="right">{fmt(c.removed)}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan="5" className="muted">No commits for this commit set.</td></tr>}
            </tbody>
          </table>
          <div className="pager">
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</button>
            <span className="muted">page {page + 1}</span>
            <button disabled={!hasNext} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </div>
      </div>
    </>
  )
}
