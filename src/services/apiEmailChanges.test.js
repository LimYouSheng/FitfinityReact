import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { authPolicy, failure, jsonResponse, sessionInfo, csrfToken } from '../test/api.js'
import { directoryData, directoryId } from '../test/directory.js'

const change = { id: directoryId(90), email: 'new@example.test', state: 'pending', signedOut: false }
const input = { id: directoryId(1), expectedVersion: 1, patch: { email: ' New@example.test ' } }
const update = { service: 'trainerService', operation: 'update', input }
const make = fetchImpl => createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })

it('reserves the normalized address without sending a verification code', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...change, state: 'requested' }))
  await make(fetch).invoke(update)
  const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/email-change'))
  expect(JSON.parse(options.body)).toEqual({ email: 'new@example.test', expectedVersion: 1 })
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
  expect(options.headers['X-CSRF-Token']).toBe(csrfToken)
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/send'))).toBe(false)
})

it('reconciles an uncertain manager request before any explicit identical retry', async () => {
  let posted = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { posted++; throw new Error('response lost') }
    return jsonResponse({ ...change, state: 'requested' })
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(update)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke({ ...update, input: { ...input, patch: { email: 'other@example.test' } } })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect((await adapter.invoke(update)).email).toBe('new@example.test')
  expect(posted).toBe(1)
  expect(fetch.mock.calls.some(([url]) => url.includes('/api/trainer-email-requests/'))).toBe(true)
})

it('binds verification to the rendered login and rejects a changed cookie before sending the code', async () => {
  let token = csrfToken
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? directoryData() : { ...sessionInfo(), csrfToken: token }))
  const services = createPortalServices(make(fetch))
  const snapshot = await services.load()
  token = 'b'.repeat(64)
  await expect(services.forSession(snapshot.sessionGeneration).auth.verifyEmailChange({ id: change.id, code: '123456' })).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(0)
})

it('does not automatically repeat a lost send or verification request', async () => {
  const fetch = vi.fn(async (url, options) => options.method === 'POST' ? failure('AUTH_UNAVAILABLE', 503) : jsonResponse(sessionInfo()))
  const adapter = make(fetch)
  for (const operation of ['sendEmailCode', 'verifyEmailChange']) {
    await expect(adapter.session({ operation, input: { id: change.id, ...(operation === 'verifyEmailChange' ? { code: '123456' } : {}) } })).rejects.toMatchObject({ code: 'AUTH_UNAVAILABLE' })
  }
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(2)
})

it('validates the verification response before clearing the login', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...change, signedOut: true }))
  const adapter = make(fetch)
  await expect(adapter.session({ operation: 'verifyEmailChange', input: { id: change.id, code: '123456' } })).rejects.toMatchObject({ code: 'API_RESPONSE' })
  fetch.mockImplementation(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...change, state: 'completed', signedOut: true }))
  expect((await adapter.session({ operation: 'reconcileEmailChange', input: { id: change.id } })).signedOut).toBe(true)
})

it('rejects malformed pending state and codes without fabricating an empty pending change', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : {}))
  const adapter = make(fetch)
  await expect(adapter.session({ operation: 'pendingEmailChange', input: {} })).rejects.toMatchObject({ code: 'API_RESPONSE' })
  const count = fetch.mock.calls.length
  await expect(adapter.session({ operation: 'verifyEmailChange', input: { id: change.id, code: 'abcdef' } })).rejects.toMatchObject({ code: 'INVALID_CODE' })
  expect(fetch).toHaveBeenCalledTimes(count)
})


it('binds a correction to the reviewed request and retains it through lost-response recovery', async () => {
  let posted = 0
  const corrected = { ...change, id: directoryId(91), state: 'requested' }
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { posted++; throw new Error('response lost') }
    return jsonResponse(corrected)
  })
  const adapter = make(fetch)
  const correction = { ...update, input: { ...input, patch: { ...input.patch, supersedes: change.id } } }
  await expect(adapter.invoke(correction)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(JSON.parse(fetch.mock.calls.find(([, options]) => options.method === 'POST')[1].body)).toEqual({ email: 'new@example.test', expectedVersion: 1, supersedes: change.id })
  await expect(adapter.invoke({ ...correction, input: { ...correction.input, patch: { ...input.patch, supersedes: directoryId(92) } } })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(correction)).toEqual(corrected)
  expect(posted).toBe(1)
})
