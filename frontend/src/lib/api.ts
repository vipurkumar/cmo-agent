/**
 * API client for CMO Agent.
 * Handles authentication, error responses, and JSON parsing.
 */

const API_BASE = ''  // Proxied by Vite in dev, same-origin in prod

export class ApiError extends Error {
  constructor(
    public status: number,
    public errorCode: string,
    message: string,
    public requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function getApiKey(): string | null {
  return localStorage.getItem('cmo_api_key')
}

export function setApiKey(key: string): void {
  localStorage.setItem('cmo_api_key', key)
}

export function clearApiKey(): void {
  localStorage.removeItem('cmo_api_key')
}

export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const apiKey = getApiKey()

  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  }

  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`
  }

  // Only set Content-Type for JSON bodies (not FormData)
  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    clearApiKey()
    window.location.href = '/app/login'
    throw new ApiError(401, 'AUTH_REQUIRED', 'Authentication required')
  }

  if (!response.ok) {
    let body: any = {}
    try {
      body = await response.json()
    } catch {}
    throw new ApiError(
      response.status,
      body.error_code || 'ERROR',
      body.message || `Request failed with status ${response.status}`,
      body.request_id,
    )
  }

  // Handle empty responses
  const text = await response.text()
  if (!text) return {} as T

  try {
    return JSON.parse(text)
  } catch {
    return text as unknown as T
  }
}
