import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import CandidateList from './pages/CandidateList'
import CandidateDetail from './pages/CandidateDetail'
import MetricsPage from './pages/MetricsPage'

function App() {
  return (
    <div className="h-full flex bg-page text-t-primary">
      {/* Sidebar */}
      <aside className="w-60 h-full bg-sidebar border-r border-b-color flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-b-color">
          <span className="text-lg font-semibold text-t-primary tracking-tight">
            Agent Evolver
          </span>
          <p className="text-[11px] text-t-tertiary mt-0.5">技能进化仪表盘</p>
        </div>
        <nav className="flex-1 overflow-auto py-2">
          <Navbar />
        </nav>
        <div className="px-4 py-3 border-t border-b-color">
          <p className="text-[10px] text-t-tertiary">v0.1.0</p>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<CandidateList />} />
            <Route path="/candidate/:id" element={<CandidateDetail />} />
            <Route path="/metrics" element={<MetricsPage />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

export default App