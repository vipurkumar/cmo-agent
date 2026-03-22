import { useState } from 'react'
import { api } from '../lib/api'

interface SearchResult {
  id: string
  title: string
  type: string
  content: string
  score?: number
}

interface ReloadResult {
  count: number
  message?: string
}

const KB_TYPES = [
  { value: 'battlecard', label: 'Battlecard' },
  { value: 'case_study', label: 'Case Study' },
  { value: 'messaging', label: 'Messaging' },
  { value: 'objection_handling', label: 'Objection Handling' },
]

export default function KnowledgeBasePage() {
  // Upload state
  const [title, setTitle] = useState('')
  const [type, setType] = useState('battlecard')
  const [content, setContent] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState<{ text: string; isError: boolean } | null>(null)

  // Search state
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<SearchResult[]>([])
  const [searchError, setSearchError] = useState('')

  // Reload state
  const [reloading, setReloading] = useState(false)
  const [reloadMessage, setReloadMessage] = useState('')

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim() || !content.trim()) return

    setUploading(true)
    setUploadMessage(null)
    try {
      const formData = new FormData()
      formData.append('title', title.trim())
      formData.append('type', type)
      formData.append('content', content.trim())

      await api('/api/v1/kb/upload', {
        method: 'POST',
        body: formData,
      })

      setUploadMessage({ text: 'Content uploaded successfully.', isError: false })
      setTitle('')
      setContent('')
      setType('battlecard')
    } catch (err: any) {
      setUploadMessage({ text: err.message || 'Upload failed.', isError: true })
    } finally {
      setUploading(false)
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return

    setSearching(true)
    setSearchError('')
    setResults([])
    try {
      const data = await api<SearchResult[]>(
        `/api/v1/kb/search?query=${encodeURIComponent(query.trim())}&limit=5`,
      )
      setResults(Array.isArray(data) ? data : [])
    } catch (err: any) {
      setSearchError(err.message || 'Search failed.')
    } finally {
      setSearching(false)
    }
  }

  async function handleReload() {
    setReloading(true)
    setReloadMessage('')
    try {
      const data = await api<ReloadResult>('/api/v1/kb/reload', { method: 'POST' })
      setReloadMessage(`Reloaded ${data.count ?? 0} KB files.`)
    } catch (err: any) {
      setReloadMessage(err.message || 'Reload failed.')
    } finally {
      setReloading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Knowledge Base</h1>
        <button
          className="btn btn-secondary"
          onClick={handleReload}
          disabled={reloading}
        >
          {reloading ? 'Reloading...' : 'Reload KB Files'}
        </button>
      </div>

      {reloadMessage && (
        <div style={{
          background: 'var(--accent-bg)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          padding: '10px 14px',
          fontSize: '13px',
          color: 'var(--accent)',
          marginBottom: '20px',
        }}>
          {reloadMessage}
        </div>
      )}

      <div className="grid-2">
        {/* Upload section */}
        <div className="card">
          <div className="section-title">Upload Content</div>
          <form onSubmit={handleUpload}>
            <div className="form-group">
              <label>Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Competitor X Battlecard"
              />
            </div>

            <div className="form-group">
              <label>Type</label>
              <select value={type} onChange={(e) => setType(e.target.value)}>
                {KB_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Content</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Paste your content here..."
                rows={8}
              />
            </div>

            {uploadMessage && (
              <div style={{
                background: uploadMessage.isError
                  ? 'rgba(239, 68, 68, 0.1)'
                  : 'rgba(34, 197, 94, 0.1)',
                border: `1px solid ${uploadMessage.isError
                  ? 'rgba(239, 68, 68, 0.2)'
                  : 'rgba(34, 197, 94, 0.2)'}`,
                borderRadius: 'var(--radius-sm)',
                padding: '10px 14px',
                color: uploadMessage.isError ? 'var(--error)' : 'var(--success)',
                fontSize: '13px',
                marginBottom: '14px',
              }}>
                {uploadMessage.text}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={uploading || !title.trim() || !content.trim()}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
          </form>
        </div>

        {/* Search section */}
        <div className="card">
          <div className="section-title">Search Knowledge Base</div>
          <form onSubmit={handleSearch} style={{ marginBottom: '16px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search KB entries..."
                style={{ flex: 1 }}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={searching || !query.trim()}
                style={{ whiteSpace: 'nowrap' }}
              >
                {searching ? 'Searching...' : 'Search'}
              </button>
            </div>
          </form>

          {searchError && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.2)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 14px',
              color: 'var(--error)',
              fontSize: '13px',
              marginBottom: '14px',
            }}>
              {searchError}
            </div>
          )}

          {searching && (
            <div className="loading">
              <div className="spinner" />
              Searching...
            </div>
          )}

          {!searching && results.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {results.map((result) => (
                <div
                  key={result.id}
                  style={{
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '14px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {result.title}
                    </span>
                    <span className="badge badge-info">{result.type}</span>
                  </div>
                  <p style={{
                    fontSize: '13px',
                    color: 'var(--text-secondary)',
                    display: '-webkit-box',
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                    lineHeight: '1.5',
                  }}>
                    {result.content}
                  </p>
                  {result.score !== undefined && (
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '6px' }}>
                      Relevance: {(result.score * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {!searching && !searchError && results.length === 0 && query && (
            <div className="empty-state" style={{ padding: '30px 20px' }}>
              <h3>No results</h3>
              <p>Try a different search query.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
