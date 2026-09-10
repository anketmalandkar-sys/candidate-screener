/**
 * The shared fetch client every feature's API module is built on: error
 * normalisation, cookie credentials, and the 204 / empty-body handling.
 */

/** An API error carrying the status, so callers can branch on 401 vs the rest. */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/**
 * Notified whenever any request comes back 401. The auth context registers a
 * handler here so a session that dies mid-visit (cookie expiry, sign-out in
 * another tab) drops the app to the login screen instead of leaving stale
 * protected UI on screen with inline "Not authenticated" errors.
 */
let unauthorizedHandler: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

/** Pull a readable message out of FastAPI's several error shapes. */
function messageFrom(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // Pydantic validation errors: [{loc, msg, ...}, ...]
    const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined
    if (first?.msg) {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null
      return field ? `${String(field)}: ${first.msg}` : first.msg
    }
  }
  if (status === 0) return 'Could not reach the server.'
  return `Request failed (${status})`
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      // Always send the session cookie.
      credentials: 'same-origin',
      ...init,
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server.')
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const body = text ? JSON.parse(text) : null

  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.()
    throw new ApiError(response.status, messageFrom(response.status, body))
  }
  return body as T
}

export function json<T>(path: string, method: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
