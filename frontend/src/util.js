export const fmt = (n) => new Intl.NumberFormat('en-US').format(n ?? 0)

export const fmtFloat = (x, d = 2) =>
  x == null ? '—' : Number(x).toLocaleString('en-US', { maximumFractionDigits: d })

export const fmtPct = (x) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)

export const fmtDate = (ts) =>
  ts == null
    ? '—'
    : new Date(ts * 1000).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

export const fmtDateTime = (ts) =>
  ts == null
    ? '—'
    : new Date(ts * 1000).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

export const sha7 = (s) => (s ? s.slice(0, 7) : '')

export const PALETTE = [
  '#58a6ff', '#3fb950', '#d29922', '#f778ba', '#a371f7',
  '#f85149', '#39c5cf', '#ff9e64', '#7ee787', '#c9d1d9',
]
