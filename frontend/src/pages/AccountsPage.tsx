import { useState, useEffect } from 'react'
import { api } from '../lib/api'

interface ScoreEntry {
  account_id: string
  company_name: string
  priority_score: number
  icp_fit: number
  pain_fit: number
  timing: number
  confidence: number
  recommended_action: string
  disqualified: boolean
}

interface BriefData {
  account_id: string
  company_name: string
  snapshot: string
  why_this_account: string
  why_now: string
  scoring: {
    priority_score: number
    icp_fit: number
    pain_fit: number
    timing: number
    confidence: number
  }
  risks: string[]
  unknowns: string[]
  recommended_action: string
}

function scoreColor(val: number) {
  if (val >= 70) return 'var(--success)'
  if (val >= 40) return 'var(--warning)'
  return 'var(--error)'
}

function scoreBadgeClass(val: number) {
  if (val >= 70) return 'badge badge-success'
  if (val >= 40) return 'badge badge-warning'
  return 'badge badge-error'
}

function actionBadgeClass(action: string) {
  switch (action.toLowerCase()) {
    case 'pursue now':
    case 'pursue_now':
      return 'badge badge-success'
    case 'nurture':
      return 'badge badge-warning'
    case 'disqualify':
      return 'badge badge-error'
    default:
      return 'badge badge-neutral'
  }
}

type FilterType = 'all' | 'pursue_now' | 'nurture' | 'disqualify'
type SortType = 'priority_score' | 'icp_fit' | 'timing'

export default function AccountsPage() {
  const [scores, setScores] = useState<ScoreEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<FilterType>('all')
  const [sort, setSort] = useState<SortType>('priority_score')

  const [briefOpen, setBriefOpen] = useState(false)
  const [brief, setBrief] = useState<BriefData | null>(null)
  const [briefLoading, setBriefLoading] = useState(false)

  useEffect(() => {
    loadScores()
  }, [])

  async function loadScores() {
    setLoading(true)
    setError('')
    try {
      const data = await api<ScoreEntry[]>('/api/v1/export/scores?format=json&limit=50')
      setScores(Array.isArray(data) ? data : [])
    } catch (err: any) {
      setError(err.message || 'Failed to load scores')
    } finally {
      setLoading(false)
    }
  }

  async function openBrief(accountId: string) {
    setBriefOpen(true)
    setBriefLoading(true)
    setBrief(null)
    try {
      const data = await api<BriefData>(`/embed/${accountId}/json`)
      setBrief(data)
    } catch (err: any) {
      setBrief(null)
      setError(err.message || 'Failed to load brief')
      setBriefOpen(false)
    } finally {
      setBriefLoading(false)
    }
  }

  function closeBrief() {
    setBriefOpen(false)
    setBrief(null)
  }

  const filtered = scores.filter((s) => {
    if (filter === 'all') return true
    const action = s.recommended_action?.toLowerCase().replace(/\s+/g, '_')
    return action === filter
  })

  const sorted = [...filtered].sort((a, b) => {
    return (b[sort] ?? 0) - (a[sort] ?? 0)
  })

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        Loading account scores...
      </div>
    )
  }

  if (error && scores.length === 0) {
    return (
      <div className="empty-state">
        <h3>Error</h3>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={loadScores} style={{ marginTop: '12px' }}>
          Retry
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Account Scoring</h1>
      </div>

      {/* Filter + Sort bar */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '4px' }}>
          {([
            ['all', 'All'],
            ['pursue_now', 'Pursue Now'],
            ['nurture', 'Nurture'],
            ['disqualify', 'Disqualify'],
          ] as [FilterType, string][]).map(([value, label]) => (
            <button
              key={value}
              className={filter === value ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
              onClick={() => setFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Sort by:</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortType)}
            style={{ width: 'auto', minWidth: '150px' }}
          >
            <option value="priority_score">Priority Score</option>
            <option value="icp_fit">ICP Fit</option>
            <option value="timing">Timing</option>
          </select>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="empty-state">
          <h3>No accounts found</h3>
          <p>No accounts match the current filter.</p>
        </div>
      ) : (
        <div className="grid-3">
          {sorted.map((account) => (
            <div className="card" key={account.account_id}>
              {/* Header: name + disqualified badge */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {account.company_name}
                </div>
                {account.disqualified && (
                  <span className="badge badge-error">Disqualified</span>
                )}
              </div>

              {/* Priority score large */}
              <div style={{ textAlign: 'center', margin: '16px 0' }}>
                <div style={{
                  fontSize: '42px',
                  fontWeight: 700,
                  color: scoreColor(account.priority_score),
                  lineHeight: 1,
                }}>
                  {account.priority_score}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Priority Score
                </div>
              </div>

              {/* Score bars */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
                {([
                  ['ICP Fit', account.icp_fit],
                  ['Pain Fit', account.pain_fit],
                  ['Timing', account.timing],
                ] as [string, number][]).map(([label, value]) => (
                  <div key={label}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '3px' }}>
                      <span>{label}</span>
                      <span>{value}</span>
                    </div>
                    <div className="score-bar">
                      <div
                        className="score-bar-fill"
                        style={{ width: `${value}%`, background: scoreColor(value) }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Confidence + action */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Confidence: {account.confidence}%
                </span>
                <span className={actionBadgeClass(account.recommended_action)}>
                  {account.recommended_action}
                </span>
              </div>

              {/* View brief button */}
              <button
                className="btn btn-secondary btn-sm"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => openBrief(account.account_id)}
              >
                View Brief
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Brief modal */}
      {briefOpen && (
        <div className="modal-overlay" onClick={closeBrief}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            {briefLoading ? (
              <div className="loading">
                <div className="spinner" />
                Loading brief...
              </div>
            ) : brief ? (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                  <div>
                    <h2 style={{ marginBottom: '4px' }}>{brief.company_name}</h2>
                    <span className={actionBadgeClass(brief.recommended_action)}>
                      {brief.recommended_action}
                    </span>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={closeBrief}>
                    Close
                  </button>
                </div>

                {/* Snapshot */}
                <div className="section">
                  <div className="section-title">Account Snapshot</div>
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{brief.snapshot}</p>
                </div>

                {/* Why this account / Why now */}
                <div className="grid-2" style={{ marginBottom: '20px' }}>
                  <div className="card">
                    <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                      Why This Account
                    </div>
                    <p style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{brief.why_this_account}</p>
                  </div>
                  <div className="card">
                    <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                      Why Now
                    </div>
                    <p style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{brief.why_now}</p>
                  </div>
                </div>

                {/* Scoring breakdown */}
                <div className="section">
                  <div className="section-title">Scoring Breakdown</div>
                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    {([
                      ['Priority', brief.scoring.priority_score],
                      ['ICP Fit', brief.scoring.icp_fit],
                      ['Pain Fit', brief.scoring.pain_fit],
                      ['Timing', brief.scoring.timing],
                      ['Confidence', brief.scoring.confidence],
                    ] as [string, number][]).map(([label, value]) => (
                      <div key={label} className="stat-card" style={{ flex: '1 1 100px', textAlign: 'center' }}>
                        <div className="stat-card-value" style={{ color: scoreColor(value), fontSize: '24px' }}>
                          {value}
                        </div>
                        <div className="stat-card-label">{label}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Risks */}
                {brief.risks && brief.risks.length > 0 && (
                  <div className="section">
                    <div className="section-title">Risks</div>
                    <ul style={{ paddingLeft: '18px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {brief.risks.map((risk, i) => (
                        <li key={i} style={{ marginBottom: '4px' }}>{risk}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Unknowns */}
                {brief.unknowns && brief.unknowns.length > 0 && (
                  <div className="section">
                    <div className="section-title">Unknowns</div>
                    <ul style={{ paddingLeft: '18px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {brief.unknowns.map((unknown, i) => (
                        <li key={i} style={{ marginBottom: '4px' }}>{unknown}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <div className="empty-state">
                <h3>Brief not available</h3>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
