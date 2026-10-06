import { Navigate, Route, Routes } from 'react-router-dom'
import Repos from './pages/Repos.jsx'
import RepoLayout from './pages/RepoLayout.jsx'
import Overview from './pages/Overview.jsx'
import Explorer from './pages/Explorer.jsx'
import Authors from './pages/Authors.jsx'
import Commits from './pages/Commits.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Repos />} />
      <Route path="/repo/:id" element={<RepoLayout />}>
        <Route index element={<Overview />} />
        <Route path="explorer" element={<Explorer />} />
        <Route path="authors" element={<Authors />} />
        <Route path="commits" element={<Commits />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
