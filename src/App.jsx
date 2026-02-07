import { Routes, Route, NavLink } from 'react-router-dom'
import { Upload, Settings, Zap } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import SettingsPage from './pages/Settings'

function App() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header className="glass" style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        padding: '16px 24px'
      }}>
        <div style={{
          maxWidth: '1200px',
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '44px',
              height: '44px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #6366f1, #a855f7, #ec4899)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 16px rgba(99, 102, 241, 0.3)'
            }}>
              <Zap style={{ width: '22px', height: '22px', color: 'white' }} />
            </div>
            <h1 className="gradient-text" style={{ fontSize: '1.4rem', fontWeight: 700 }}>
              VideoUploader
            </h1>
          </div>

          <nav style={{ display: 'flex', gap: '8px' }}>
            <NavLink
              to="/"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <Upload style={{ width: '18px', height: '18px' }} />
              <span>Dashboard</span>
            </NavLink>
            <NavLink
              to="/settings"
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <Settings style={{ width: '18px', height: '18px' }} />
              <span>API Settings</span>
            </NavLink>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main style={{ flex: 1, padding: '32px 24px' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </div>
      </main>

      {/* Footer */}
      <footer className="glass" style={{
        padding: '16px 24px',
        textAlign: 'center',
        color: '#6b7280',
        fontSize: '0.875rem'
      }}>
        <p>© 2026 VideoUploader • YouTube Shorts & Instagram Reels</p>
      </footer>
    </div>
  )
}

export default App
