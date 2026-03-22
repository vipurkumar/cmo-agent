import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api, clearApiKey } from '../lib/api'
import './Layout.css'

const navItems = [
  { path: '/app', label: 'Dashboard', icon: '◼', end: true },
  { path: '/app/campaigns', label: 'Campaigns', icon: '▶' },
  { path: '/app/accounts', label: 'Accounts & Briefs', icon: '★' },
  { path: '/app/kb', label: 'Knowledge Base', icon: '📚' },
  { path: '/app/settings', label: 'Settings', icon: '⚙' },
  { path: '/app/notifications', label: 'Notifications', icon: '🔔' },
]

export default function Layout() {
  const navigate = useNavigate()
  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    const poll = async () => {
      try {
        const data = await api('/api/v1/notifications/unread-count')
        setUnreadCount(data.unread_count || 0)
      } catch {}
    }
    poll()
    const interval = setInterval(poll, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleLogout = () => {
    clearApiKey()
    navigate('/app/login')
  }

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="sidebar-logo">
          <span className="logo-icon">🎯</span>
          <span className="logo-text">CMO Agent</span>
        </div>

        <div className="nav-links">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'active' : ''}`
              }
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
              {item.label === 'Notifications' && unreadCount > 0 && (
                <span className="nav-badge">{unreadCount}</span>
              )}
            </NavLink>
          ))}
        </div>

        <div className="sidebar-footer">
          <button className="btn btn-ghost btn-sm" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </nav>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
