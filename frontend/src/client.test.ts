import { ApiError, request, setUnauthorizedHandler } from './client'

function mockResponse(status: number, body: unknown = null): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => (body === null ? '' : JSON.stringify(body)),
  } as Response
}

afterEach(() => {
  setUnauthorizedHandler(null)
  vi.unstubAllGlobals()
})

test('a 401 notifies the unauthorized handler and still throws', async () => {
  const onUnauthorized = vi.fn()
  setUnauthorizedHandler(onUnauthorized)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse(401, { detail: 'Not authenticated' })))

  await expect(request('/api/candidates')).rejects.toBeInstanceOf(ApiError)
  expect(onUnauthorized).toHaveBeenCalledTimes(1)
})

test('non-401 failures do not notify the handler', async () => {
  const onUnauthorized = vi.fn()
  setUnauthorizedHandler(onUnauthorized)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse(403, { detail: 'Forbidden' })))

  await expect(request('/api/roles')).rejects.toBeInstanceOf(ApiError)
  expect(onUnauthorized).not.toHaveBeenCalled()
})

test('successful requests do not notify the handler', async () => {
  const onUnauthorized = vi.fn()
  setUnauthorizedHandler(onUnauthorized)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse(200, { id: 1 })))

  await expect(request('/api/auth/me')).resolves.toEqual({ id: 1 })
  expect(onUnauthorized).not.toHaveBeenCalled()
})
