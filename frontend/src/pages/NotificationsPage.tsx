import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

interface Notification {
  id: string
  notification_type: string
  title: string
  message: string
  priority: string
  is_read: boolean
  created_at: string
}

const typeIcons: Record<string, string> = {
  automation_paused: '\u23F8\uFE0F',
  automation_resumed: '\u25B6\uFE0F',
  brief_ready: '\uD83D\uDCCB',
  high_error_rate: '\u26A0\uFE0F',
  send_cap_reached: '\uD83D\uDEAB',
  kill_switch_triggered: '\uD83D\uDED1',
  evaluation_complete: '\u2705',
  qualification_complete: '\u2705',
}

const priorityBadge: Record<string, { className: string; style: React.CSSProperties }> = {
  critical: { className: 'badge', style: { background: 'rgba(239, 68, 68, 0.15)', color: 'var(--error)' } },
  high: { className: 'badge', style: { background: 'rgba(249, 115, 22, 0.15)', color: '#f97316' } },
  medium: { className: 'badge', style: { background: 'rgba(59, 130, 246, 0.15)', color: 'var(--info)' } },
  low: { className: 'badge', style: { background: 'rgba(148, 163, 184, 0.15)', color: 'var(--text-secondary)' } },
}

function timeAgo(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago'
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago'
  return new Date(iso).toLocaleDateString()
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const [loading, setLoading] = useState(true)

  const fetchNotifications = useCallback(async () => {
    try {
      const params = filter === 'unread' ? '?unread_only=true' : '?limit=50'
      const [notifRes, countRes] = await Promise.all([
        api<{ notifications: Notification[] }>(`/api/v1/notifications${params}`),
        api<{ count: number }>('/api/v1/notifications/unread-count'),
      ])
      setNotifications(notifRes.notifications)
      setUnreadCount(countRes.count)
    } catch {
      // silently handle errors on fetch
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    setLoading(true)
    fetchNotifications()
  }, [fetchNotifications])

  const markAsRead = async (id: string) => {
    try {
      await api(`/api/v1/notifications/${id}/read`, { method: 'POST' })
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      )
      setUnreadCount((prev) => Math.max(0, prev - 1))
    } catch {
      // silently handle
    }
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        Loading notifications...
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>
          Notifications
          {unreadCount > 0 && (
            <span
              className="badge"
              style={{
                background: 'rgba(239, 68, 68, 0.15)',
                color: 'var(--error)',
                marginLeft: '10px',
                fontSize: '12px',
                verticalAlign: 'middle',
              }}
            >
              {unreadCount} unread
            </span>
          )}
        </h1>
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '16px' }}>
        <button
          className={`btn ${filter === 'all' ? 'btn-secondary' : 'btn-ghost'}`}
          onClick={() => setFilter('all')}
        >
          All
        </button>
        <button
          className={`btn ${filter === 'unread' ? 'btn-secondary' : 'btn-ghost'}`}
          onClick={() => setFilter('unread')}
        >
          Unread
        </button>
      </div>

      {/* Notification list */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {notifications.length === 0 ? (
          <div className="empty-state">
            <h3>No notifications</h3>
            <p>{filter === 'unread' ? 'All caught up!' : 'Nothing here yet.'}</p>
          </div>
        ) : (
          notifications.map((notif) => (
            <div
              key={notif.id}
              onClick={() => !notif.is_read && markAsRead(notif.id)}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                padding: '14px 20px',
                borderBottom: '1px solid var(--border)',
                cursor: notif.is_read ? 'default' : 'pointer',
                background: notif.is_read ? 'transparent' : 'rgba(129, 140, 248, 0.03)',
                transition: 'background var(--transition)',
              }}
              onMouseEnter={(e) => {
                if (!notif.is_read) e.currentTarget.style.background = 'var(--bg-hover)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = notif.is_read ? 'transparent' : 'rgba(129, 140, 248, 0.03)'
              }}
            >
              {/* Type icon */}
              <div style={{ fontSize: '20px', flexShrink: 0, marginTop: '2px' }}>
                {typeIcons[notif.notification_type] || '\uD83D\uDD14'}
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{
                    fontSize: '14px',
                    fontWeight: notif.is_read ? 400 : 600,
                    color: 'var(--text-primary)',
                  }}>
                    {notif.title}
                  </span>
                  {!notif.is_read && (
                    <div style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: 'var(--accent)',
                      flexShrink: 0,
                    }} />
                  )}
                  <span
                    className={priorityBadge[notif.priority]?.className || 'badge badge-neutral'}
                    style={priorityBadge[notif.priority]?.style || priorityBadge.low.style}
                  >
                    {notif.priority}
                  </span>
                </div>
                <p style={{
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                  marginTop: '4px',
                  lineHeight: 1.4,
                }}>
                  {notif.message}
                </p>
              </div>

              {/* Timestamp */}
              <div style={{
                fontSize: '12px',
                color: 'var(--text-muted)',
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}>
                {timeAgo(notif.created_at)}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
