import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

interface AutomationStatus {
  workspace_id: string
  is_paused: boolean
  daily_send_cap: number
  sends_today: number
  hourly_send_cap: number
  sends_this_hour: number
}

interface User {
  id: string
  email: string
  name: string
  role: string
}

interface Webhook {
  id: string
  url: string
  events: string[]
  is_active: boolean
}

const roleBadgeClass: Record<string, string> = {
  admin: 'badge-purple',
  operator: 'badge-info',
  viewer: 'badge-neutral',
}

const roleBadgeStyle: Record<string, React.CSSProperties> = {
  admin: { background: 'rgba(168, 85, 247, 0.15)', color: '#a855f7' },
  operator: { background: 'rgba(59, 130, 246, 0.15)', color: 'var(--info)' },
  viewer: { background: 'rgba(148, 163, 184, 0.15)', color: 'var(--text-secondary)' },
}

export default function SettingsPage() {
  // API Keys state
  const [workspaceId, setWorkspaceId] = useState('')
  const [maskedKey, setMaskedKey] = useState('cmo_****...****')
  const [newKeyLabel, setNewKeyLabel] = useState('')
  const [generatedKey, setGeneratedKey] = useState('')
  const [keyCopied, setKeyCopied] = useState(false)

  // Team Members state
  const [users, setUsers] = useState<User[]>([])
  const [newUserEmail, setNewUserEmail] = useState('')
  const [newUserName, setNewUserName] = useState('')
  const [newUserRole, setNewUserRole] = useState('viewer')

  // Webhooks state
  const [webhooks, setWebhooks] = useState<Webhook[]>([])
  const [newWebhookUrl, setNewWebhookUrl] = useState('')
  const [testingWebhook, setTestingWebhook] = useState<string | null>(null)

  // Automation state
  const [automation, setAutomation] = useState<AutomationStatus | null>(null)
  const [pauseReason, setPauseReason] = useState('')

  // General
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const showToast = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }, [])

  // Load all data
  useEffect(() => {
    async function load() {
      try {
        const [statusRes, usersRes, webhooksRes] = await Promise.all([
          api<AutomationStatus>('/api/v1/automation/status'),
          api<{ users: User[] }>('/api/v1/users'),
          api<{ webhooks: Webhook[] }>('/api/v1/webhooks'),
        ])
        setAutomation(statusRes)
        setWorkspaceId(statusRes.workspace_id)
        setUsers(usersRes.users)
        setWebhooks(webhooksRes.webhooks)
      } catch (err: any) {
        showToast(err.message || 'Failed to load settings', 'error')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [showToast])

  // API Key actions
  const createApiKey = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api<{ api_key: string }>(`/api/v1/workspaces/${workspaceId}/api-keys`, {
        method: 'POST',
        body: JSON.stringify({ label: newKeyLabel || 'New Key' }),
      })
      setGeneratedKey(res.api_key)
      setMaskedKey(res.api_key.slice(0, 4) + '****...' + res.api_key.slice(-4))
      setNewKeyLabel('')
      showToast('API key created successfully')
    } catch (err: any) {
      showToast(err.message || 'Failed to create API key', 'error')
    }
  }

  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(generatedKey)
      setKeyCopied(true)
      setTimeout(() => setKeyCopied(false), 2000)
    } catch {
      showToast('Failed to copy to clipboard', 'error')
    }
  }

  // Team actions
  const addUser = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api<User>('/api/v1/users', {
        method: 'POST',
        body: JSON.stringify({ email: newUserEmail, name: newUserName, role: newUserRole }),
      })
      setUsers((prev) => [...prev, res])
      setNewUserEmail('')
      setNewUserName('')
      setNewUserRole('viewer')
      showToast('User added successfully')
    } catch (err: any) {
      showToast(err.message || 'Failed to add user', 'error')
    }
  }

  // Webhook actions
  const createWebhook = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api<Webhook>('/api/v1/webhooks', {
        method: 'POST',
        body: JSON.stringify({ url: newWebhookUrl, events: ['brief_ready', 'automation_paused'] }),
      })
      setWebhooks((prev) => [...prev, res])
      setNewWebhookUrl('')
      showToast('Webhook created successfully')
    } catch (err: any) {
      showToast(err.message || 'Failed to create webhook', 'error')
    }
  }

  const testWebhook = async (id: string) => {
    setTestingWebhook(id)
    try {
      await api(`/api/v1/webhooks/${id}/test`, { method: 'POST' })
      showToast('Test payload sent')
    } catch (err: any) {
      showToast(err.message || 'Webhook test failed', 'error')
    } finally {
      setTestingWebhook(null)
    }
  }

  const deleteWebhook = async (id: string) => {
    try {
      await api(`/api/v1/webhooks/${id}`, { method: 'DELETE' })
      setWebhooks((prev) => prev.filter((w) => w.id !== id))
      showToast('Webhook deleted')
    } catch (err: any) {
      showToast(err.message || 'Failed to delete webhook', 'error')
    }
  }

  // Automation actions
  const pauseAutomation = async () => {
    try {
      await api('/api/v1/automation/pause', {
        method: 'POST',
        body: JSON.stringify({ reason: pauseReason || 'Paused from settings' }),
      })
      setAutomation((prev) => (prev ? { ...prev, is_paused: true } : prev))
      setPauseReason('')
      showToast('Automation paused')
    } catch (err: any) {
      showToast(err.message || 'Failed to pause automation', 'error')
    }
  }

  const resumeAutomation = async () => {
    try {
      await api('/api/v1/automation/resume', { method: 'POST' })
      setAutomation((prev) => (prev ? { ...prev, is_paused: false } : prev))
      showToast('Automation resumed')
    } catch (err: any) {
      showToast(err.message || 'Failed to resume automation', 'error')
    }
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        Loading settings...
      </div>
    )
  }

  const dailyCapPct = automation ? Math.min((automation.sends_today / automation.daily_send_cap) * 100, 100) : 0
  const hourlyCapPct = automation ? Math.min((automation.sends_this_hour / automation.hourly_send_cap) * 100, 100) : 0

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      {/* API Keys */}
      <div className="section">
        <div className="section-title">API Keys</div>
        <div className="card">
          <div style={{ marginBottom: '16px' }}>
            <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
              Current Key
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <code style={{
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '8px 12px',
                fontSize: '13px',
                fontFamily: 'monospace',
                flex: 1,
              }}>
                {maskedKey}
              </code>
              {generatedKey && (
                <button className="btn btn-secondary btn-sm" onClick={copyKey}>
                  {keyCopied ? 'Copied!' : 'Copy'}
                </button>
              )}
            </div>
            {generatedKey && (
              <p style={{ fontSize: '12px', color: 'var(--warning)', marginTop: '6px' }}>
                Save this key now -- it will not be shown again.
              </p>
            )}
          </div>
          <form onSubmit={createApiKey} style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label>Key Label</label>
              <input
                type="text"
                value={newKeyLabel}
                onChange={(e) => setNewKeyLabel(e.target.value)}
                placeholder="e.g. Production, CI/CD"
              />
            </div>
            <button type="submit" className="btn btn-primary">
              Create New Key
            </button>
          </form>
        </div>
      </div>

      {/* Team Members */}
      <div className="section">
        <div className="section-title">Team Members</div>
        <div className="card">
          <div style={{ overflowX: 'auto', marginBottom: '16px' }}>
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Role</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>
                      No team members yet
                    </td>
                  </tr>
                ) : (
                  users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.email}</td>
                      <td>{user.name}</td>
                      <td>
                        <span className="badge" style={roleBadgeStyle[user.role] || roleBadgeStyle.viewer}>
                          {user.role}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <form onSubmit={addUser} style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div className="form-group" style={{ flex: 1, minWidth: '160px', marginBottom: 0 }}>
              <label>Email</label>
              <input
                type="email"
                value={newUserEmail}
                onChange={(e) => setNewUserEmail(e.target.value)}
                placeholder="user@company.com"
                required
              />
            </div>
            <div className="form-group" style={{ flex: 1, minWidth: '140px', marginBottom: 0 }}>
              <label>Name</label>
              <input
                type="text"
                value={newUserName}
                onChange={(e) => setNewUserName(e.target.value)}
                placeholder="Full name"
                required
              />
            </div>
            <div className="form-group" style={{ width: '120px', marginBottom: 0 }}>
              <label>Role</label>
              <select value={newUserRole} onChange={(e) => setNewUserRole(e.target.value)}>
                <option value="admin">Admin</option>
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
            <button type="submit" className="btn btn-primary" disabled={!newUserEmail || !newUserName}>
              Add User
            </button>
          </form>
        </div>
      </div>

      {/* Webhooks */}
      <div className="section">
        <div className="section-title">Webhooks</div>
        <div className="card">
          <div style={{ marginBottom: '16px' }}>
            {webhooks.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>
                No webhooks configured
              </div>
            ) : (
              webhooks.map((wh) => (
                <div
                  key={wh.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 0',
                    borderBottom: '1px solid var(--border)',
                    gap: '12px',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '13px', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {wh.url}
                    </div>
                    <div style={{ display: 'flex', gap: '4px', marginTop: '4px', flexWrap: 'wrap' }}>
                      {wh.events.map((ev) => (
                        <span key={ev} className="badge badge-neutral" style={{ fontSize: '10px' }}>
                          {ev}
                        </span>
                      ))}
                      <span
                        className="badge"
                        style={wh.is_active
                          ? { background: 'rgba(34, 197, 94, 0.15)', color: 'var(--success)' }
                          : { background: 'rgba(239, 68, 68, 0.15)', color: 'var(--error)' }
                        }
                      >
                        {wh.is_active ? 'active' : 'inactive'}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => testWebhook(wh.id)}
                      disabled={testingWebhook === wh.id}
                    >
                      {testingWebhook === wh.id ? 'Sending...' : 'Test'}
                    </button>
                    <button className="btn btn-danger btn-sm" onClick={() => deleteWebhook(wh.id)}>
                      Delete
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
          <form onSubmit={createWebhook} style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label>Webhook URL</label>
              <input
                type="url"
                value={newWebhookUrl}
                onChange={(e) => setNewWebhookUrl(e.target.value)}
                placeholder="https://your-service.com/webhook"
                required
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={!newWebhookUrl}>
              Add Webhook
            </button>
          </form>
        </div>
      </div>

      {/* Automation Control */}
      <div className="section">
        <div className="section-title">Automation Control</div>
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
            <div
              style={{
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                background: automation?.is_paused ? 'var(--error)' : 'var(--success)',
                boxShadow: automation?.is_paused
                  ? '0 0 8px rgba(239, 68, 68, 0.4)'
                  : '0 0 8px rgba(34, 197, 94, 0.4)',
              }}
            />
            <span style={{ fontSize: '15px', fontWeight: 600 }}>
              {automation?.is_paused ? 'Automation Paused' : 'Automation Running'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', marginBottom: '20px' }}>
            {automation?.is_paused ? (
              <button className="btn btn-primary" onClick={resumeAutomation}>
                Resume Automation
              </button>
            ) : (
              <>
                <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                  <label>Pause Reason (optional)</label>
                  <input
                    type="text"
                    value={pauseReason}
                    onChange={(e) => setPauseReason(e.target.value)}
                    placeholder="e.g. Reviewing campaign settings"
                  />
                </div>
                <button className="btn btn-danger" onClick={pauseAutomation}>
                  Pause Automation
                </button>
              </>
            )}
          </div>

          {/* Send cap bars */}
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Daily Send Cap</span>
                <span style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
                  {automation?.sends_today ?? 0} / {automation?.daily_send_cap ?? 0}
                </span>
              </div>
              <div className="score-bar">
                <div
                  className="score-bar-fill"
                  style={{
                    width: `${dailyCapPct}%`,
                    background: dailyCapPct > 90 ? 'var(--error)' : dailyCapPct > 70 ? 'var(--warning)' : 'var(--accent)',
                  }}
                />
              </div>
            </div>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Hourly Send Cap</span>
                <span style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
                  {automation?.sends_this_hour ?? 0} / {automation?.hourly_send_cap ?? 0}
                </span>
              </div>
              <div className="score-bar">
                <div
                  className="score-bar-fill"
                  style={{
                    width: `${hourlyCapPct}%`,
                    background: hourlyCapPct > 90 ? 'var(--error)' : hourlyCapPct > 70 ? 'var(--warning)' : 'var(--accent)',
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`toast ${toast.type === 'success' ? 'toast-success' : 'toast-error'}`}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
