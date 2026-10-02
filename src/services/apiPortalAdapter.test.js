import { emptyDirectory } from '../test/directory.js'
import { afterEach, expect, it, vi } from 'vitest'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { createPortalServices } from './portalService.js'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { authPolicy, challenge, csrfToken, failure, jsonResponse, sessionInfo } from '../test/api.js'

afterEach(() => vi.restoreAllMocks())
const make = fetchImpl => createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })

it('uses verified live identity without reading or writing demo storage', async () => {
  const read = vi.spyOn(Storage.prototype, 'getItem'), write = vi.spyOn(Storage.prototype, 'setItem')
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? emptyDirectory() : sessionInfo()))
  const services = createConfiguredPortalServices({ mode: 'api', baseUrl: 'https://api.example', fetchImpl: fetch })
  const snapshot = await services.load()
  expect(snapshot.user.email).toBe('owner@example.test')
  expect(snapshot).toMatchObject({ data: { clients: [], trainers: [], packages: [] }, capabilities: { demoControls: false, staffWorkflows: true, directoryReadOnly: true } })
  expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled()
})
it('shows sign-in only for terminal expiry and does not hide backend failures', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(authPolicy)).mockResolvedValueOnce(failure('SESSION_EXPIRED')).mockResolvedValueOnce(failure('service_unavailable', 503))
  const adapter = make(fetch)
  expect((await adapter.load()).user).toBe(null)
  await expect(adapter.load()).rejects.toMatchObject({ code: 'service_unavailable' })
})
it('fails closed on unknown mode and invalid API policy', async () => {
  await expect(createConfiguredPortalServices({ mode: 'production-typo' }).load()).rejects.toThrow('Unknown staff portal mode')
  await expect(make(vi.fn().mockResolvedValue(jsonResponse({ password: {} }))).load()).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
it('uses the backend challenge, recovery and password contracts without caller authority', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(challenge('NEW_PASSWORD_REQUIRED'))).mockResolvedValueOnce(jsonResponse(challenge('MFA_SETUP'))).mockResolvedValueOnce(jsonResponse(sessionInfo())).mockResolvedValueOnce(jsonResponse({ message: 'If eligible, check your email.' })).mockResolvedValueOnce(jsonResponse({ passwordReset: true, signedOut: true }))
  const adapter = make(fetch)
  await adapter.session({ operation: 'signIn', input: { identifier: ' owner@example.test ', password: 'unchanged password' } })
  await adapter.session({ operation: 'challenge', input: { newPassword: 'long-separator-passphrase' } })
  await adapter.session({ operation: 'challenge', input: { code: '123456' } })
  await adapter.session({ operation: 'forgotPassword', input: { identifier: 'owner@example.test' } })
  await adapter.session({ operation: 'resetPassword', input: { code: '123456', newPassword: 'new-separator-passphrase', confirmation: 'ignored' } })
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ email: 'owner@example.test', password: 'unchanged password' })
  expect(JSON.parse(fetch.mock.calls[4][1].body)).toEqual({ code: '123456', newPassword: 'new-separator-passphrase' })
  expect(fetch.mock.calls.every(([, options]) => options.credentials === 'include')).toBe(true)
})
it('changes a password with CSRF and clears the session after the server signs out', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(sessionInfo())).mockResolvedValueOnce(jsonResponse({ passwordChanged: true, signedOut: true })), adapter = make(fetch)
  const result = await adapter.session({ operation: 'changePassword', input: { currentPassword: 'old', newPassword: 'new-separator-password', confirmation: 'not-sent' } })
  expect(result.signedOut).toBe(true)
  expect(fetch.mock.calls[1][1].headers['X-CSRF-Token']).toBe(csrfToken)
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ currentPassword: 'old', newPassword: 'new-separator-password' })
})
it('signs out after access expiry without consuming a refresh', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(jsonResponse({ csrfToken })).mockResolvedValueOnce(jsonResponse({ signedOut: true })), adapter = make(fetch)
  await adapter.session({ operation: 'signOut', input: {} })
  expect(fetch.mock.calls.map(([url]) => new URL(url).pathname)).toEqual(['/auth/session', '/auth/sign-out'])
  expect(fetch.mock.calls[1][1].headers['X-CSRF-Token']).toBe(csrfToken)
})
it('does not claim successful logout when the request failed', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(jsonResponse({ csrfToken })).mockRejectedValueOnce(new Error('offline')), adapter = make(fetch)
  await expect(adapter.session({ operation: 'signOut', input: {} })).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
})
it('denies mock reset, identity switching and unimplemented domains without any request', async () => {
  const fetch = vi.fn(), adapter = make(fetch)
  await expect(adapter.reset()).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  await expect(adapter.session({ operation: 'switchDemoIdentity', input: { userId: 'owner' } })).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  await expect(adapter.invoke({ service: 'clientService', operation: 'create', input: { draft: {} } })).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  expect(fetch).not.toHaveBeenCalled()
})
it('coalesces initial loads and recovers from a failed policy request', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(jsonResponse(authPolicy)).mockResolvedValueOnce(jsonResponse(sessionInfo())).mockResolvedValueOnce(jsonResponse(emptyDirectory()))
  const adapter = make(fetch)
  await expect(adapter.load()).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const [one, two] = await Promise.all([adapter.load(), adapter.load()])
  expect(one).toEqual(two); expect(fetch).toHaveBeenCalledTimes(4)
})
it('rejects unsupported MFA and missing enrollment secrets', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(challenge('SMS_MFA'))).mockResolvedValueOnce(jsonResponse({ ...challenge('MFA_SETUP'), secretCode: null }))
  const adapter = make(fetch)
  for (let index = 0; index < 2; index++) await expect(adapter.session({ operation: 'signIn', input: { identifier: 'owner@example.test', password: 'password' } })).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it.each(['createAdmin', 'changePassword', 'signOut'])('binds %s to its rendered session across preflight and permits a fresh action', async operation => {
  let token = csrfToken
  const fetch = vi.fn(async (url, options) => {
    if (options.method === 'POST') return jsonResponse(operation === 'createAdmin'
      ? { id: 'created', name: 'New Admin', email: 'new@example.test', role: 'admin', invitation: 'sent' }
      : { signedOut: true })
    return jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? emptyDirectory() : { ...sessionInfo(), csrfToken: token })
  })
  const services = createPortalServices(make(fetch))
  const before = await services.load(), old = services.forSession(before.sessionGeneration)
  const action = scoped => operation === 'createAdmin' ? scoped.staffService.createAdmin({ body: { name: 'New Admin' }, requestKey: 'stable-key' })
    : operation === 'changePassword' ? scoped.auth.changePassword({ currentPassword: 'old', newPassword: 'replacement-passphrase' }) : scoped.auth.signOut()
  token = 'b'.repeat(64)
  await expect(action(old)).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(0)
  const current = await services.load()
  // A stale callback remains stale even after the adapter has loaded the replacement.
  const calls = fetch.mock.calls.length
  await expect(action(old)).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch).toHaveBeenCalledTimes(calls)
  await action(services.forSession(current.sessionGeneration))
  const posts = fetch.mock.calls.filter(([, options]) => options.method === 'POST')
  expect(posts).toHaveLength(1)
  expect(posts[0][1].headers['X-CSRF-Token']).toBe(token)
  expect(JSON.parse(posts[0][1].body)).not.toHaveProperty('expectedGeneration')
})

it.each(['signOut', 'changePassword', 'resetPassword', 'challenge', 'signIn', 'forgotPassword'])('rejects delayed %s completion after a newer verified login', async operation => {
  let token = csrfToken, finish, started
  const entered = new Promise(resolve => { started = resolve })
  const paths = { signOut: '/auth/sign-out', changePassword: '/auth/change-password', resetPassword: '/auth/reset-password', challenge: '/auth/challenge', signIn: '/auth/sign-in', forgotPassword: '/auth/forgot-password' }
  const inputs = {
    signOut: {}, changePassword: { currentPassword: 'old', newPassword: 'replacement-passphrase' },
    resetPassword: { code: '123456', newPassword: 'replacement-passphrase' }, challenge: { code: '123456' },
    signIn: { identifier: 'owner@example.test', password: 'old-password' }, forgotPassword: { identifier: 'owner@example.test' },
  }
  const fetch = vi.fn(async url => {
    if (new URL(url).pathname === paths[operation]) { started(); return new Promise(resolve => { finish = resolve }) }
    if (url.endsWith('/api/staff/admins')) return jsonResponse({ id: 'new', name: 'Current', email: 'current@example.test', role: 'admin', invitation: 'sent' })
    return jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? emptyDirectory() : { ...sessionInfo(), csrfToken: token })
  })
  const services = createPortalServices(make(fetch)), before = await services.load()
  const old = services.forSession(before.sessionGeneration).auth[operation](inputs[operation])
  const rejected = expect(old).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  await entered
  token = 'b'.repeat(64)
  const current = await services.load()
  const result = operation === 'challenge' ? sessionInfo() : operation === 'signIn' ? challenge() : operation === 'forgotPassword' ? { message: 'Check your email.' } : { signedOut: true }
  finish(jsonResponse(result)); await rejected
  await services.forSession(current.sessionGeneration).staffService.createAdmin({ body: { name: 'Current' }, requestKey: 'current-key' })
  expect(fetch.mock.calls.at(-1)[1].headers['X-CSRF-Token']).toBe(token)
  expect(fetch.mock.calls.filter(([url]) => new URL(url).pathname === paths[operation])).toHaveLength(1)
})

it('does not let a pending anonymous account read erase completed MFA', async () => {
  let release, entered, signedIn = false
  const waiting = new Promise(resolve => { entered = resolve })
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/auth/sign-in')) return jsonResponse(challenge())
    if (url.endsWith('/auth/challenge')) { signedIn = true; return jsonResponse(sessionInfo()) }
    if (url.endsWith('/api/directory')) return jsonResponse(emptyDirectory())
    if (url.endsWith('/me') && !signedIn) { entered(); return new Promise(resolve => { release = resolve }) }
    if (options.method === 'POST') return jsonResponse({ id: 'new', name: 'Current', email: 'current@example.test', role: 'admin', invitation: 'sent' })
    return jsonResponse(sessionInfo())
  })
  const adapter = make(fetch)
  await adapter.session({ operation: 'signIn', input: { identifier: 'owner@example.test', password: 'old-password' } })
  const anonymous = adapter.load(), rejected = expect(anonymous).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  await waiting
  await adapter.session({ operation: 'challenge', input: { code: '123456' } })
  // Account loading for the completed login cannot join the held anonymous read.
  const current = await adapter.load()
  release(failure('SESSION_EXPIRED')); await rejected
  expect(current.user.role).toBe('owner')
  await createPortalServices(adapter).forSession(current.sessionGeneration).staffService.createAdmin({ body: { name: 'Current' }, requestKey: 'current-key' })
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/auth/challenge'))).toHaveLength(1)
})
