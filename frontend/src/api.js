async function req(path, opts = {}) {
  const res = await fetch(path, opts)
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body.detail) msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* keep status text */ }
    throw new Error(msg)
  }
  return res.json()
}

function toQuery(params) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === '') continue
    q.set(k, Array.isArray(v) ? v.join(',') : String(v))
  }
  return q.toString()
}

export const api = {
  listRepos: () => req('/api/repos'),
  getRepo: (id) => req(`/api/repos/${id}`),
  addByUrl: (url) => req('/api/repos/url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) }),
  addByZip: async (file) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/repos/zip', { method: 'POST', body: fd })
    if (!res.ok) {
      let msg = `${res.status} ${res.statusText}`
      try {
        const body = await res.json()
        if (body.detail) msg = body.detail
      } catch { /* keep status text */ }
      throw new Error(msg)
    }
    return res.json()
  },
  deleteRepo: (id) => req(`/api/repos/${id}`, { method: 'DELETE' }),
  reanalyze: (id) => req(`/api/repos/${id}/reanalyze`, { method: 'POST' }),
  getAuthors: (id) => req(`/api/repos/${id}/authors`),
  mergeAuthors: (id, payload) => req(`/api/repos/${id}/authors/merge`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  splitIdentity: (id, authorIds) => req(`/api/repos/${id}/authors/split`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ author_ids: authorIds }) }),
  getMetrics: (id, q) => req(`/api/repos/${id}/metrics`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(q) }),
  getTree: (id, params) => req(`/api/repos/${id}/tree?${toQuery(params)}`),
  getCommits: (id, params) => req(`/api/repos/${id}/commits?${toQuery(params)}`),
  getSeries: (id, params) => req(`/api/repos/${id}/series?${toQuery(params)}`),
}
