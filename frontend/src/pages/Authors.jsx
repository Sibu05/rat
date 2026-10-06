import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { useRepo } from './RepoLayout.jsx'
import { fmt } from '../util.js'

export default function Authors() {
  const { repo } = useRepo()
  const [idents, setIdents] = useState(null)
  const [selected, setSelected] = useState(() => new Set())
  const [target, setTarget] = useState('')
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const reload = useCallback(() => {
    api.getAuthors(repo.id)
      .then((a) => setIdents(a))
      .catch((e) => setErr(e.message))
  }, [repo.id])

  useEffect(reload, [reload])

  const toggle = (id) => {
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id); else n.add(id)
      return n
    })
  }

  const doMerge = async () => {
    setErr(''); setMsg('')
    const sources = [...selected].filter((x) => x !== Number(target))
    if (!target || sources.length === 0) {
      setErr('Pick a merge target and at least one source identity (different from the target).')
      return
    }
    try {
      const list = await api.mergeAuthors(repo.id, {
        source_ids: sources,
        target_id: Number(target),
        name: newName.trim() || undefined,
        email: newEmail.trim() || undefined,
      })
      setIdents(list)
      setSelected(new Set()); setTarget(''); setNewName(''); setNewEmail('')
      setMsg(`Merged ${sources.length} identity(ies) into the target.`)
    } catch (e) {
      setErr(e.message)
    }
  }

  const doSplit = async (authorId, label) => {
    if (!window.confirm(`Split "${label}" back into its own identity?`)) return
    setErr(''); setMsg('')
    try {
      const list = await api.splitIdentity(repo.id, [authorId])
      setIdents(list)
      setMsg(`Split "${label}" into a separate identity.`)
    } catch (e) {
      setErr(e.message)
    }
  }

  if (!idents) return <div className="empty">Loading…</div>

  return (
    <>
      {err && <div className="error-box">{err}</div>}
      {msg && <div className="selection-banner">{msg}</div>}

      {selected.size > 0 && (
        <div className="merge-panel">
          <strong>Merge {selected.size} identity(ies)</strong>
          <span className="muted">into:</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">choose target…</option>
            {[...selected].map((id) => {
              const a = idents.find((x) => x.identity_id === id)
              return <option key={id} value={id}>{a?.name} &lt;{a?.email}&gt;</option>
            })}
          </select>
          <input
            type="text" placeholder="new name (optional)" value={newName}
            onChange={(e) => setNewName(e.target.value)} style={{ width: 160 }}
          />
          <input
            type="text" placeholder="new email (optional)" value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)} style={{ width: 200 }}
          />
          <button className="primary" onClick={doMerge}>Merge</button>
          <button onClick={() => setSelected(new Set())}>Cancel</button>
        </div>
      )}

      <div className="panel">
        <h2>Author identities {idents.length > 0 && <span className="muted">({idents.length})</span>}</h2>
        <table className="data">
          <thead>
            <tr><th></th><th>Identity</th><th>Aliases</th><th className="right">Commits</th><th className="right">Churn λ</th><th className="right">Modifications</th></tr>
          </thead>
          <tbody>
            {idents.map((a) => (
              <tr key={a.identity_id}>
                <td><input type="checkbox" checked={selected.has(a.identity_id)} onChange={() => toggle(a.identity_id)} /></td>
                <td>
                  <strong>{a.name}</strong> <span className="muted mono">&lt;{a.email}&gt;</span>{' '}
                  {a.merged && <span className="badge merged">merged</span>}
                </td>
                <td className="wrap">
                  {a.aliases.length <= 1 ? (
                    <span className="muted">—</span>
                  ) : (
                    a.aliases.map((al) => (
                      <span className="alias-chip" key={al.author_id}>
                        {al.name} &lt;{al.email}&gt;
                        <button
                          className="small" title="Split this alias into its own identity"
                          onClick={() => doSplit(al.author_id, `${al.name} <${al.email}>`)}
                        >
                          split
                        </button>
                      </span>
                    ))
                  )}
                </td>
                <td className="right">{fmt(a.commits)}</td>
                <td className="right">{fmt(a.churn)}</td>
                <td className="right">{fmt(a.modifications)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted" style={{ marginBottom: 0 }}>
          Tick identities above to merge them (e.g. the same person committing under several emails).
          .mailmap mappings are applied automatically during analysis.
        </p>
      </div>
    </>
  )
}
