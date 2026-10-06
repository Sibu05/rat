import { useNavigate } from 'react-router-dom'

// Browser-style back through in-app history when possible; otherwise the
// caller-supplied fallback route (e.g. the parent directory).
export default function BackButton({ fallback, label = '← Back' }) {
  const navigate = useNavigate()
  const go = () => {
    const idx = window.history.state?.idx
    if (typeof idx === 'number' && idx > 0) navigate(-1)
    else navigate(fallback)
  }
  return <button className="back-btn" onClick={go}>{label}</button>
}
