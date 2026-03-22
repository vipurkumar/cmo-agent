import { useState, useEffect } from 'react'
import { api } from '../lib/api'

interface StatData {
  totalCampaigns: number
  totalBriefs: number
  totalScores: number
  unreadNotifications: number
}

interface AutomationStatus {
  paused: boolean
  last_run?: string
}

interface ActivityItem {
  id: string
  action: string
  resource: string
  resource_id?: string
  timestamp: string
  details?: string
}

export default function DashboardPage() {
  const [stats, setStats] = useState<StatData>({
    totalCampaigns: 0,
    totalBriefs: 0,
    totalScores: 0,
    unreadNotifications: 0,
  })
  const [automation, setAutomation] = useState<AutomationStatus | null>(null)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [togglingAutomation, setTogglingAutomation] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    setError(null)

    const [campaignsRes, auditRes, autoRes, notifsRes, activityRes] =
      await Promise.allSettled([
        api<{ total: number }>('/campaigns?page=1&page_size=1'),
        api<{ total_briefs: number; total_scores: number }>('/api/v1/audit/summary'),
        api<AutomationStatus>('/api/v1/automation/status'),
        api<{ count: number }>('/api/v1/notifications/unread-count'),
        api<ActivityItem[]>('/api/v1/audit/activity?limit=10'),
      ])

    const newStats: StatData = {
      totalCampaigns: 0,
      totalBriefs: 0,
      totalScores: 0,
      unreadNotifications: 0,
    }

    if (campaignsRes.status === 'fulfilled') {
      newStats.totalCampaigns = campaignsRes.value.total ?? 0
    }
    if (auditRes.status === 'fulfilled') {
      newStats.totalBriefs = auditRes.value.total_briefs ?? 0
      newStats.totalScores = auditRes.value.total_scores ?? 0
    }
    if (notifsRes.status === 'fulfilled') {
      newStats.unreadNotifications = notifsRes.value.count ?? 0
    }

    setStats(newStats)

    if (autoRes.status === 'fulfilled') {
      setAutomation(autoRes.value)
    }

    if (activityRes.status === 'fulfilled') {
      setActivity(Array.isArray(activityRes.value) ? activityRes.value : [])
    }

    const allFailed = [campaignsRes, auditRes, autoRes, notifsRes, activityRes].every(
      (r) => r.status === 'rejected',
    )
    if (allFailed) {
      setError('Failed to load dashboard data. Please check your connection and try again.')
    }

    setLoading(false)
  }

  async function toggleAutomation() {
    if (!automation) return
    setTogglingAutomation(true)
    try {
      const endpoint = automation.paused
        ? '/api/v1/automation/resume'
        : '/api/v1/automation/pause'
      const result = await api<AutomationStatus>(endpoint, { method: 'POST' })
      setAutomation(result)
    } catch (err: any) {
      setError(err.message || 'Failed to toggle automation status.')
    } finally {
      setTogglingAutomation(false)
    }
  }

  function formatTimestamp(ts: string): string {
    try {
      const date = new Date(ts)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffMins = Math.floor(diffMs / 60000)

      if (diffMins < 1) return 'Just now'
      if (diffMins < 60) return `${diffMins}m ago`
      const diffHours = Math.floor(diffMins / 60)
      if (diffHours < 24) return `${diffHours}h ago`
      const diffDays = Math.floor(diffHours / 24)
      if (diffDays < 7) return `${diffDays}d ago`
      return date.toLocaleDateString()
    } catch {
      return ts
    }
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        Loading dashboard...
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <button className="btn btn-secondary" onClick={loadData}>
          Refresh
        </button>
      </div>

      {error && (
        <div
          style={{
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px 16px',
            color: 'var(--error)',
            fontSize: '13px',
            marginBottom: '20px',
          }}
        >
          {error}
        </div>
      )}

      {/* Stat Cards */}
      <div className="section">
        <div className="grid-4">
          <div className="stat-card">
            <div className="stat-card-value">{stats.totalCampaigns}</div>
            <div className="stat-card-label">Total Campaigns</div>
          </div>
          <div className="stat-card">
            <div className="stat-card-value">{stats.totalBriefs}</div>
            <div className="stat-card-label">Total Briefs</div>
          </div>
          <div className="stat-card">
            <div className="stat-card-value">{stats.totalScores}</div>
            <div className="stat-card-label">Total Scores</div>
          </div>
          <div className="stat-card">
            <div className="stat-card-value">{stats.unreadNotifications}</div>
            <div className="stat-card-label">Unread Notifications</div>
          </div>
        </div>
      </div>

      {/* Automation Status */}
      <div className="section">
        <div className="section-title">Automation Status</div>
        <div className="card">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: automation?.paused ? 'var(--warning)' : 'var(--success)',
                }}
              />
              <div>
                <div style={{ fontWeight: 600, fontSize: '14px' }}>
                  {automation?.paused ? 'Paused' : 'Active'}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {automation?.paused
                    ? 'Automation is currently paused. No campaigns are being processed.'
                    : 'Automation is running. Campaigns are being processed normally.'}
                </div>
                {automation?.last_run && (
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Last run: {formatTimestamp(automation.last_run)}
                  </div>
                )}
              </div>
            </div>
            <button
              className={`btn ${automation?.paused ? 'btn-primary' : 'btn-secondary'}`}
              onClick={toggleAutomation}
              disabled={togglingAutomation || !automation}
            >
              {togglingAutomation
                ? 'Updating...'
                : automation?.paused
                  ? 'Resume'
                  : 'Pause'}
            </button>
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="section">
        <div className="section-title">Recent Activity</div>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {activity.length === 0 ? (
            <div className="empty-state">
              <h3>No recent activity</h3>
              <p>Activity from campaigns and automations will appear here.</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Resource</th>
                  <th>Details</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {activity.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <span className="badge badge-info">{item.action}</span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)' }}>{item.resource}</td>
                    <td style={{ color: 'var(--text-secondary)', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.details || '--'}
                    </td>
                    <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {formatTimestamp(item.timestamp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
