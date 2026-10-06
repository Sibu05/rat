import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area, AreaChart, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api.js'
import { useRepo } from './RepoLayout.jsx'
import { fmt, fmtFloat, fmtPct, PALETTE } from '../util.js'

export default function Overview() {
  const { repo, params } = useRepo()
  const [m, setM] = useState(null)
  const [topDirs, setTopDirs] = useState([])
  const [series, setSeries] = useState([])
  const [bucket, setBucket] = useState('month')
  const [err, setErr] = useState('')
  const pkey = JSON.stringify(params)

  useEffect(() => {
    let alive = true
    setErr('')
    api.getMetrics(repo.id, { object_type: 'repository', ...params })
      .then((r) => { if (alive) setM(r) })
      .catch((e) => { if (alive) setErr(e.message) })
    api.getTree(repo.id, { path: '', ...params })
      .then((rows) => { if (alive) setTopDirs(rows.filter((r) => r.is_dir).slice(0, 10)) })
      .catch(() => {})
    return () => { alive = false }
  }, [repo.id, pkey])

  useEffect(() => {
    let alive = true
    api.getSeries(repo.id, { bucket, object_type: 'repository', ...params })
      .then((rows) => {
        if (!alive) return
        setSeries(rows.map((s) => ({
          ...s,
          label: new Date(s.t * 1000).toLocaleDateString(undefined, bucket === 'year' ? { year: 'numeric' } : { year: 'numeric', month: 'short' }),
        })))
      })
      .catch(() => {})
    return () => { alive = false }
  }, [repo.id, pkey, bucket])

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

  const authors = (m.by_author || []).slice(0, 10)
  let donut = (m.by_author || []).slice(0, 8).map((a) => ({ name: a.name, value: a.churn }))
  const rest = (m.by_author || []).slice(8).reduce((s, a) => s + a.churn, 0)
  if (rest > 0) donut.push({ name: 'Other', value: rest })
  if (donut.length === 1 && donut[0].value === 0) donut = []

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
          <h2>
            Lines over time{' '}
            <select value={bucket} onChange={(e) => setBucket(e.target.value)} style={{ float: 'right' }}>
              {['day', 'week', 'month', 'year'].map((b) => <option key={b} value={b}>per {b}</option>)}
            </select>
          </h2>
          <div className="chart-box">
            <ResponsiveContainer>
              <AreaChart data={series} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gAdd" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3fb950" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#3fb950" stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="gDel" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f85149" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#f85149" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="label" tick={{ fill: '#8b949e', fontSize: 11 }} minTickGap={40} />
                <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} width={60} />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8 }}
                  labelStyle={{ color: '#8b949e' }}
                />
                <Legend />
                <Area type="monotone" dataKey="added" name="added" stroke="#3fb950" fill="url(#gAdd)" strokeWidth={2} />
                <Area type="monotone" dataKey="removed" name="removed" stroke="#f85149" fill="url(#gDel)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <h2>Ownership by author (churn share)</h2>
          {donut.length === 0 ? (
            <div className="empty">No data for this commit set.</div>
          ) : (
            <div className="chart-box">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={donut} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2}>
                    {donut.map((entry, i) => (
                      <Cell key={entry.name} fill={PALETTE[i % PALETTE.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8 }}
                    formatter={(v, name) => [fmt(v), name]}
                  />
                  <Legend layout="vertical" align="right" verticalAlign="middle" wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>Top authors</h2>
          <table className="data">
            <thead>
              <tr><th>Author</th><th className="right">Churn</th><th className="right">Ownership</th><th></th></tr>
            </thead>
            <tbody>
              {authors.map((a) => (
                <tr key={a.identity_id}>
                  <td>{a.name}<div className="muted mono">{a.email}</div></td>
                  <td className="right">{fmt(a.churn)}</td>
                  <td className="right">{fmtPct(a.ownership)}</td>
                  <td>
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${Math.round(a.ownership * 100)}%` }} />
                    </span>
                  </td>
                </tr>
              ))}
              {authors.length === 0 && <tr><td colSpan="4" className="muted">No data for this commit set.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h2>Top directories</h2>
          <table className="data">
            <thead>
              <tr><th>Directory</th><th className="right">Churn</th><th className="right">Growth</th><th>Top author</th></tr>
            </thead>
            <tbody>
              {topDirs.map((d) => (
                <tr key={d.path}>
                  <td><Link to={`/repo/${repo.id}/explorer?path=${encodeURIComponent(d.path)}`}>{d.name}/</Link></td>
                  <td className="right">{fmt(d.churn)}</td>
                  <td className={`right ${d.growth >= 0 ? 'pos' : 'neg'}`}>{fmt(d.growth)}</td>
                  <td>
                    {d.top_author ? (
                      <>
                        {d.top_author.name}{' '}
                        <span className="muted">{fmtPct(d.churn ? d.top_author.churn / d.churn : null)}</span>
                      </>
                    ) : '—'}
                  </td>
                </tr>
              ))}
              {topDirs.length === 0 && <tr><td colSpan="4" className="muted">No directories for this commit set.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
