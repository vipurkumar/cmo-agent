import { useState, useEffect } from 'react'
import { api } from '../lib/api'

interface Campaign {
  id: string
  name: string
  status: string
  icp_criteria?: {
    industries?: string[]
    employee_range?: { min: number; max: number }
  }
  created_at: string
}

interface CampaignListResponse {
  items: Campaign[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface Toast {
  message: string
  type: 'success' | 'error'
}

const PAGE_SIZE = 10

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [formName, setFormName] = useState('')
  const [formIndustries, setFormIndustries] = useState('')
  const [formEmployeeMin, setFormEmployeeMin] = useState('')
  const [formEmployeeMax, setFormEmployeeMax] = useState('')
  const [creating, setCreating] = useState(false)

  // Qualification state
  const [qualifyingId, setQualifyingId] = useState<string | null>(null)

  // Account upload modal state
  const [showAccountModal, setShowAccountModal] = useState(false)
  const [accountModalCampaignId, setAccountModalCampaignId] = useState<string | null>(null)
  const [accountsText, setAccountsText] = useState('')
  const [uploadingAccounts, setUploadingAccounts] = useState(false)

  // Toast state
  const [toast, setToast] = useState<Toast | null>(null)

  useEffect(() => {
    loadCampaigns()
  }, [page])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  function showToast(message: string, type: 'success' | 'error') {
    setToast({ message, type })
  }

  async function loadCampaigns() {
    setLoading(true)
    setError(null)
    try {
      const data = await api<CampaignListResponse>(
        `/campaigns?page=${page}&page_size=${PAGE_SIZE}`,
      )
      setCampaigns(data.items ?? [])
      setTotalPages(data.total_pages ?? 1)
      setTotal(data.total ?? 0)
    } catch (err: any) {
      setError(err.message || 'Failed to load campaigns.')
      setCampaigns([])
    } finally {
      setLoading(false)
    }
  }

  async function createCampaign(e: React.FormEvent) {
    e.preventDefault()
    if (!formName.trim()) return

    setCreating(true)
    try {
      const industries = formIndustries
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)

      const body: any = {
        name: formName.trim(),
        icp_criteria: {},
        sequence_config: {},
      }

      if (industries.length > 0) {
        body.icp_criteria.industries = industries
      }

      const min = parseInt(formEmployeeMin, 10)
      const max = parseInt(formEmployeeMax, 10)
      if (!isNaN(min) && !isNaN(max) && min > 0 && max >= min) {
        body.icp_criteria.employee_range = { min, max }
      }

      await api('/campaigns', {
        method: 'POST',
        body: JSON.stringify(body),
      })

      showToast(`Campaign "${formName.trim()}" created successfully.`, 'success')
      closeModal()
      setPage(1)
      await loadCampaigns()
    } catch (err: any) {
      showToast(err.message || 'Failed to create campaign.', 'error')
    } finally {
      setCreating(false)
    }
  }

  async function triggerQualification(campaignId: string) {
    setQualifyingId(campaignId)
    try {
      await api(`/api/v1/campaigns/${campaignId}/qualify`, {
        method: 'POST',
        body: JSON.stringify({ max_accounts: 20 }),
      })
      showToast('Qualification triggered successfully.', 'success')
      await loadCampaigns()
    } catch (err: any) {
      showToast(err.message || 'Failed to trigger qualification.', 'error')
    } finally {
      setQualifyingId(null)
    }
  }

  function closeModal() {
    setShowModal(false)
    setFormName('')
    setFormIndustries('')
    setFormEmployeeMin('')
    setFormEmployeeMax('')
  }

  function openAccountUpload(campaignId: string) {
    setAccountModalCampaignId(campaignId)
    setAccountsText('')
    setShowAccountModal(true)
  }

  function closeAccountModal() {
    setShowAccountModal(false)
    setAccountModalCampaignId(null)
    setAccountsText('')
  }

  function parseAccountsText(text: string): { company_name: string; domain?: string }[] {
    return text
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(',').map((s) => s.trim())
        const result: { company_name: string; domain?: string } = {
          company_name: parts[0],
        }
        if (parts[1]) {
          result.domain = parts[1]
        }
        return result
      })
  }

  async function uploadAccounts(e: React.FormEvent) {
    e.preventDefault()
    if (!accountModalCampaignId || !accountsText.trim()) return

    const accounts = parseAccountsText(accountsText)
    if (accounts.length === 0) {
      showToast('No valid accounts found. Enter one per line: company_name, domain', 'error')
      return
    }

    setUploadingAccounts(true)
    try {
      await api(`/api/v1/campaigns/${accountModalCampaignId}/accounts`, {
        method: 'POST',
        body: JSON.stringify({
          accounts,
          trigger_qualification: true,
        }),
      })
      showToast(
        `${accounts.length} account${accounts.length !== 1 ? 's' : ''} uploaded and qualification triggered.`,
        'success',
      )
      closeAccountModal()
      await loadCampaigns()
    } catch (err: any) {
      showToast(err.message || 'Failed to upload accounts.', 'error')
    } finally {
      setUploadingAccounts(false)
    }
  }

  function handleCsvUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      const csv = event.target?.result as string
      if (csv) {
        // Skip header row if it looks like a header
        const lines = csv.split('\n')
        const firstLine = lines[0]?.toLowerCase() || ''
        const hasHeader = firstLine.includes('company') || firstLine.includes('name')
        const dataLines = hasHeader ? lines.slice(1) : lines
        setAccountsText(dataLines.join('\n'))
      }
    }
    reader.readAsText(file)
  }

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    } catch {
      return dateStr
    }
  }

  function getStatusBadgeClass(status: string): string {
    switch (status.toLowerCase()) {
      case 'active':
      case 'running':
        return 'badge-success'
      case 'paused':
        return 'badge-warning'
      case 'completed':
      case 'done':
        return 'badge-info'
      case 'failed':
      case 'error':
        return 'badge-error'
      default:
        return 'badge-neutral'
    }
  }

  function formatIcp(campaign: Campaign): string {
    const parts: string[] = []
    if (campaign.icp_criteria?.industries?.length) {
      parts.push(campaign.icp_criteria.industries.join(', '))
    }
    if (campaign.icp_criteria?.employee_range) {
      const { min, max } = campaign.icp_criteria.employee_range
      parts.push(`${min}-${max} employees`)
    }
    return parts.length > 0 ? parts.join(' | ') : '--'
  }

  if (loading && campaigns.length === 0) {
    return (
      <div className="loading">
        <div className="spinner" />
        Loading campaigns...
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Campaigns</h1>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          + New Campaign
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

      {/* Campaign Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {campaigns.length === 0 ? (
          <div className="empty-state">
            <h3>No campaigns yet</h3>
            <p>Create your first campaign to get started with outbound automation.</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>ICP</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((campaign) => (
                <tr key={campaign.id}>
                  <td style={{ fontWeight: 500 }}>{campaign.name}</td>
                  <td>
                    <span className={`badge ${getStatusBadgeClass(campaign.status)}`}>
                      {campaign.status}
                    </span>
                  </td>
                  <td
                    style={{
                      color: 'var(--text-secondary)',
                      maxWidth: '250px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {formatIcp(campaign)}
                  </td>
                  <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                    {formatDate(campaign.created_at)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => openAccountUpload(campaign.id)}
                      >
                        Add Accounts
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => triggerQualification(campaign.id)}
                        disabled={qualifyingId === campaign.id}
                      >
                        {qualifyingId === campaign.id ? 'Qualifying...' : 'Qualify'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: '16px',
          }}
        >
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {total} campaign{total !== 1 ? 's' : ''} total
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              Previous
            </button>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Page {page} of {totalPages}
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Create Campaign Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Create New Campaign</h2>
            <form onSubmit={createCampaign}>
              <div className="form-group">
                <label>Campaign Name *</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Q1 Enterprise Outbound"
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label>ICP Industries (comma-separated)</label>
                <input
                  type="text"
                  value={formIndustries}
                  onChange={(e) => setFormIndustries(e.target.value)}
                  placeholder="e.g. SaaS, FinTech, HealthTech"
                />
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label>Min Employees</label>
                  <input
                    type="number"
                    value={formEmployeeMin}
                    onChange={(e) => setFormEmployeeMin(e.target.value)}
                    placeholder="e.g. 50"
                    min="1"
                  />
                </div>
                <div className="form-group">
                  <label>Max Employees</label>
                  <input
                    type="number"
                    value={formEmployeeMax}
                    onChange={(e) => setFormEmployeeMax(e.target.value)}
                    placeholder="e.g. 500"
                    min="1"
                  />
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '8px',
                  marginTop: '20px',
                }}
              >
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={closeModal}
                  disabled={creating}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!formName.trim() || creating}
                >
                  {creating ? 'Creating...' : 'Create Campaign'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Account Upload Modal */}
      {showAccountModal && (
        <div className="modal-overlay" onClick={closeAccountModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add Target Accounts</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
              Paste accounts (one per line): <strong>company_name, domain</strong>
              <br />
              Domain is optional but recommended for enrichment.
            </p>
            <form onSubmit={uploadAccounts}>
              <div className="form-group">
                <label>Accounts</label>
                <textarea
                  value={accountsText}
                  onChange={(e) => setAccountsText(e.target.value)}
                  placeholder={`Acme Corp, acme.com\nBigCo Industries, bigco.io\nNovaPay, novapay.io`}
                  rows={8}
                  style={{ fontFamily: 'monospace', fontSize: '13px' }}
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label>Or upload CSV</label>
                <input
                  type="file"
                  accept=".csv,.txt"
                  onChange={handleCsvUpload}
                  style={{ fontSize: '13px' }}
                />
              </div>

              {accountsText.trim() && (
                <div
                  style={{
                    background: 'var(--bg-secondary)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    marginBottom: '12px',
                  }}
                >
                  {parseAccountsText(accountsText).length} account
                  {parseAccountsText(accountsText).length !== 1 ? 's' : ''} detected
                </div>
              )}

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '8px',
                  marginTop: '20px',
                }}
              >
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={closeAccountModal}
                  disabled={uploadingAccounts}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!accountsText.trim() || uploadingAccounts}
                >
                  {uploadingAccounts ? 'Uploading & Qualifying...' : 'Upload & Qualify'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className={`toast ${toast.type === 'success' ? 'toast-success' : 'toast-error'}`}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
