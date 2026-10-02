import { describe, expect, it, vi } from 'vitest'
import { apiBaseUrl, createApiClient } from './apiClient.js'
import { csrfToken, failure, jsonResponse, sessionInfo } from '../test/api.js'

const make = fetchImpl => createApiClient({ baseUrl: 'https://api.example.test/staff', fetchImpl })

describe('real API transport', () => {
  it('restricts credentials to the configured HTTPS base and allows local development', async () => {
    for (const url of ['http://api.example', 'https://user:secret@api.example', 'https://api.example?q=1', 'https://api.example#key', 'file:///tmp/api']) expect(() => apiBaseUrl(url)).toThrow()
    expect(apiBaseUrl('http://127.0.0.1:8080/')).toBe('http://127.0.0.1:8080')
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ businessDate: '2026-09-22' }))
    await make(fetch).get('/api/clock')
    expect(fetch).toHaveBeenCalledWith('https://api.example.test/staff/api/clock', expect.objectContaining({ credentials: 'include', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer' }))
  })
  it('rejects external, traversing and invalid-method requests before fetching', async () => {
    const fetch = vi.fn(), http = make(fetch)
    for (const path of ['//evil.test', 'https://evil.test', '/api/../private', '/api/%2e%2e/private', '/api/clock#secret', '/api/\\evil']) await expect(http.get(path)).rejects.toMatchObject({ code: 'API_PATH' })
    expect(fetch).not.toHaveBeenCalled()
  })
  it('sends CSRF and a caller-owned retry key without a bearer token', async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ saved: true })), http = make(fetch)
    await expect(http.post('/api/clients', {}, { csrf: true })).rejects.toMatchObject({ code: 'SESSION_EXPIRED' })
    http.remember({ csrfToken })
    await http.post('/api/clients', { name: 'One' }, { csrf: true, idempotencyKey: 'stable-key' })
    expect(fetch.mock.calls[0][1]).toMatchObject({ body: '{"name":"One"}', headers: { 'X-CSRF-Token': csrfToken, 'Idempotency-Key': 'stable-key', 'Content-Type': 'application/json' } })
    expect(fetch.mock.calls[0][1].headers).not.toHaveProperty('Authorization')
  })
  it('bootstraps CSRF after reload, refreshes once, then reads the verified principal', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(failure('TOKEN_EXPIRED')).mockResolvedValueOnce(jsonResponse({ csrfToken })).mockResolvedValueOnce(jsonResponse({ refreshed: true })).mockResolvedValueOnce(jsonResponse(sessionInfo()))
    expect((await make(fetch).session()).user.role).toBe('owner')
    expect(fetch.mock.calls.map(([url]) => url.split('/staff')[1])).toEqual(['/me', '/auth/session', '/auth/refresh', '/me'])
    expect(fetch.mock.calls[2][1].headers['X-CSRF-Token']).toBe(csrfToken)
  })
  it('coalesces concurrent token expiry into one refresh', async () => {
    let refreshed = false
    const fetch = vi.fn(async url => {
      if (url.endsWith('/auth/session')) return jsonResponse({ csrfToken })
      if (url.endsWith('/auth/refresh')) { refreshed = true; return jsonResponse({ refreshed: true }) }
      return refreshed ? jsonResponse(sessionInfo()) : failure('TOKEN_EXPIRED')
    })
    const http = make(fetch)
    await Promise.all([http.session(), http.session(), http.session()])
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/auth/refresh'))).toHaveLength(1)
  })
  it('never automatically resubmits a mutation after an expired token or network error', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(failure('TOKEN_EXPIRED')).mockRejectedValueOnce(new Error('sensitive raw detail')), http = make(fetch)
    http.remember({ csrfToken })
    await expect(http.post('/api/clients', {}, { csrf: true })).rejects.toMatchObject({ code: 'TOKEN_EXPIRED' })
    await expect(http.post('/api/clients', {}, { csrf: true })).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('does not consume a second refresh when an older expired response arrives late', async () => {
    let late, reads = 0, refreshed = false
    const fetch = vi.fn(async url => {
      if (url.endsWith('/auth/session')) return jsonResponse({ csrfToken })
      if (url.endsWith('/auth/refresh')) { refreshed = true; return jsonResponse({ refreshed: true }) }
      reads++
      if (reads === 1) return new Promise(resolve => { late = resolve })
      return refreshed ? jsonResponse(sessionInfo()) : failure('TOKEN_EXPIRED')
    })
    const http = make(fetch), older = http.session()
    await http.session()
    late(failure('TOKEN_EXPIRED'))
    expect((await older).user.role).toBe('owner')
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/auth/refresh'))).toHaveLength(1)
  })
  it('does not repeat an ambiguous consuming refresh and allows a later successful read to reconcile', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(failure('TOKEN_EXPIRED')).mockResolvedValueOnce(jsonResponse({ csrfToken })).mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce(failure('TOKEN_EXPIRED')).mockResolvedValueOnce(jsonResponse(sessionInfo()))
    const http = make(fetch)
    await expect(http.session()).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
    await expect(http.session()).rejects.toMatchObject({ code: 'SESSION_RECHECK' })
    expect((await http.session()).user.name).toBe('Owner')
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/auth/refresh'))).toHaveLength(1)
  })
  it('ignores late responses from before a session change', async () => {
    let finish
    const http = make(() => new Promise(resolve => { finish = resolve }))
    const result = http.session()
    http.clear()
    finish(jsonResponse(sessionInfo()))
    await expect(result).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
    await expect(http.post('/api/clients', {}, { csrf: true })).rejects.toMatchObject({ code: 'SESSION_EXPIRED' })
  })
  it('rejects malformed JSON, HTML proxy errors and malformed session responses', async () => {
    const fetch = vi.fn().mockResolvedValueOnce({ headers: new Headers({ 'Content-Type': 'text/html' }) }).mockResolvedValueOnce(jsonResponse({ csrfToken, user: { role: 'admin' } })).mockResolvedValueOnce(jsonResponse({ csrfToken: 'invalid' }))
    const http = make(fetch)
    await expect(http.get('/me')).rejects.toMatchObject({ code: 'API_RESPONSE' })
    await expect(http.session()).rejects.toMatchObject({ code: 'API_RESPONSE' })
    await expect(http.session()).rejects.toMatchObject({ code: 'API_RESPONSE' })
  })
  it('preserves safe support IDs and clears authority on terminal session expiry', async () => {
    const fetch = vi.fn().mockResolvedValue(failure('SESSION_EXPIRED')), http = make(fetch)
    http.remember({ csrfToken })
    await expect(http.session()).rejects.toMatchObject({ code: 'SESSION_EXPIRED', status: 401, requestId: 'request-one' })
    await expect(http.post('/api/clients', {}, { csrf: true })).rejects.toMatchObject({ code: 'SESSION_EXPIRED' })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})

it.each(['expired', 'forbidden', 'success', 'network', 'malformed'])('rejects a late %s mutation after a verified session replacement without losing current CSRF', async outcome => {
  let finish, reject
  const fetch = vi.fn().mockImplementationOnce(() => new Promise((resolve, fail) => { finish = resolve; reject = fail }))
    .mockResolvedValueOnce(jsonResponse({ ...sessionInfo(), csrfToken: 'b'.repeat(64) })).mockResolvedValue(jsonResponse({ saved: true }))
  const http = make(fetch)
  http.remember(sessionInfo())
  const old = http.post('/api/staff/admins', {}, { csrf: true })
  const rejected = expect(old).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  await http.session()
  if (outcome === 'network') reject(new Error('offline'))
  else finish(outcome === 'expired' ? failure('SESSION_EXPIRED') : outcome === 'forbidden' ? failure('forbidden', 403) : outcome === 'malformed' ? { headers: new Headers({ 'Content-Type': 'text/html' }) } : jsonResponse({ saved: true }))
  await rejected
  await http.post('/api/staff/admins', {}, { csrf: true })
  expect(fetch.mock.calls).toHaveLength(3)
  expect(fetch.mock.calls[2][1].headers['X-CSRF-Token']).toBe('b'.repeat(64))
})
it('rejects an old session response instead of reverting the replacement session token', async () => {
  let finish
  const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    .mockResolvedValueOnce(jsonResponse({ ...sessionInfo(), csrfToken: 'b'.repeat(64) })).mockResolvedValue(jsonResponse({ saved: true }))
  const http = make(fetch); http.remember(sessionInfo())
  const old = http.session(), rejected = expect(old).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  await http.session(); finish(jsonResponse(sessionInfo())); await rejected
  await http.post('/api/staff/admins', {}, { csrf: true })
  expect(fetch.mock.calls.at(-1)[1].headers['X-CSRF-Token']).toBe('b'.repeat(64))
})
it('does not advance the session for a same-session focus read or reject its pending mutation', async () => {
  let finish
  const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue(jsonResponse(sessionInfo()))
  const http = make(fetch); http.remember(sessionInfo())
  const old = http.post('/api/staff/admins', {}, { csrf: true }), before = http.generation()
  await http.session(); finish(jsonResponse({ saved: true }))
  await expect(old).resolves.toEqual({ saved: true })
  expect(http.generation()).toBe(before)
})
it('rejects a role change even if a response reuses the same CSRF value', async () => {
  let finish
  const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue(jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'admin' } }))
  const http = make(fetch); http.remember(sessionInfo())
  const old = http.post('/api/staff/admins', {}, { csrf: true }), rejected = expect(old).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  await http.session(); finish(failure('SESSION_EXPIRED')); await rejected
})
it('does not start a follow-up request authorized under a superseded session', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(sessionInfo())).mockResolvedValueOnce(jsonResponse({ ...sessionInfo(), csrfToken: 'b'.repeat(64) }))
  const http = make(fetch), old = await http.session()
  await http.session()
  await expect(http.post('/api/staff/admins', {}, { csrf: true, expectedGeneration: old.sessionGeneration })).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch).toHaveBeenCalledTimes(2)
})
it('rejects an old consuming refresh without blocking or refreshing the replacement session', async () => {
  let finish, started
  const waiting = new Promise(resolve => { started = resolve })
  const fetch = vi.fn().mockResolvedValueOnce(failure('TOKEN_EXPIRED'))
    .mockImplementationOnce(() => { started(); return new Promise(resolve => { finish = resolve }) })
    .mockResolvedValueOnce(jsonResponse({ ...sessionInfo(), csrfToken: 'b'.repeat(64) })).mockResolvedValue(jsonResponse({ saved: true }))
  const http = make(fetch); http.remember(sessionInfo())
  const old = http.session(), rejected = expect(old).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  await waiting; await http.session(); finish(failure('SESSION_EXPIRED')); await rejected
  await http.post('/api/staff/admins', {}, { csrf: true })
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/auth/refresh'))).toHaveLength(1)
  expect(fetch.mock.calls.at(-1)[1].headers['X-CSRF-Token']).toBe('b'.repeat(64))
})
