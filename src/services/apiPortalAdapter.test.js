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
  expect(snapshot).toMatchObject({ data: { clients: [], trainers: [], packages: [] }, capabilities: { demoControls: false, staffWorkflows: true, apiBackedWorkflows: true } })
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
  await expect(adapter.invoke({ service: 'clientService', operation: 'deactivatePackage', input: { id: 'unavailable', options: {} } })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(adapter.invoke({ service: 'clientService', operation: 'reactivatePackage', input: { id: 'unavailable', options: {} } })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(adapter.invoke({ service: 'clientService', operation: 'deactivate', input: { id: 'unavailable' } })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
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

const packageDraft = { name: 'Custom', total: 18, status: 'active' }
const packageRecord = { id: '10000000-0000-4000-8000-000000000099', version: 1, revision: 1, name: 'Custom', total_sessions: 18, validity_days: 135, status: 'active' }
const savePackageRequest = draft => ({ service: 'packageService', operation: 'save', input: { draft: draft ?? packageDraft } })

it.each(['owner', 'admin'])('saves a package for %s with CSRF and a stable server receipt key', async role => {
  const fetch = vi.fn(async (url, options) => jsonResponse(options.method === 'POST' ? packageRecord : { ...sessionInfo(), user: { ...sessionInfo().user, role } }))
  const result = await make(fetch).invoke(savePackageRequest())
  expect(result).toMatchObject({ id: packageRecord.id, total: 18, validityDays: 135 })
  const [, post] = fetch.mock.calls.at(-1)
  expect(post.headers['X-CSRF-Token']).toBe(csrfToken)
  expect(post.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
  expect(JSON.parse(post.body)).toEqual({ draft: packageDraft })
})
it('denies trainer package writes before a mutation', async () => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer' } }))
  await expect(make(fetch).invoke(savePackageRequest())).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch).toHaveBeenCalledTimes(1)
})
it('binds package writes to the rendered login even when the cookie changes during preflight', async () => {
  let token = csrfToken
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? emptyDirectory() : { ...sessionInfo(), csrfToken: token }))
  const adapter = make(fetch), snapshot = await adapter.load()
  token = 'b'.repeat(64)
  await expect(adapter.invoke(savePackageRequest(), { expectedGeneration: snapshot.sessionGeneration })).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch.mock.calls.some(([, options]) => options.method === 'POST')).toBe(false)
})
it('reconciles a lost package response without issuing a second mutation', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (options.method === 'POST') throw new Error('Response lost after commit')
    return jsonResponse(url.includes('/packages/saves/') ? packageRecord : sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(savePackageRequest())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.invoke(savePackageRequest())).toMatchObject({ id: packageRecord.id })
  const posts = fetch.mock.calls.filter(([, options]) => options.method === 'POST')
  expect(posts).toHaveLength(1)
  expect(fetch.mock.calls.at(-1)[0]).toContain(posts[0][1].headers['Idempotency-Key'])
})
it('retries the identical package key only after a receipt read proves no committed save', async () => {
  let posts = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.includes('/packages/saves/')) return failure('not_found', 404)
    if (options.method === 'POST') { if (++posts === 1) throw new Error('Not received'); return jsonResponse(packageRecord) }
    return jsonResponse(sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(savePackageRequest())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await adapter.invoke(savePackageRequest())
  const keys = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options.headers['Idempotency-Key'])
  expect(keys).toHaveLength(2); expect(new Set(keys).size).toBe(1)
  expect(fetch.mock.calls.at(-2)[0]).toContain('/packages/saves/')
})
it('blocks changed values while the previous package command is uncertain', async () => {
  const fetch = vi.fn(async (url, options) => { if (options.method === 'POST') throw new Error('offline'); return jsonResponse(sessionInfo()) })
  const adapter = make(fetch)
  await expect(adapter.invoke(savePackageRequest())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(savePackageRequest({ ...packageDraft, name: 'Another' }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('does not accept malformed package evidence or resend an uncertain command', async () => {
  const fetch = vi.fn(async (url, options) => jsonResponse(options.method === 'POST' ? { ...packageRecord, total_sessions: 0 } : url.includes('/packages/saves/') ? packageRecord : sessionInfo()))
  const adapter = make(fetch)
  await expect(adapter.invoke(savePackageRequest())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(await adapter.invoke(savePackageRequest())).toMatchObject({ total: 18 })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})

it.each([false, true])('post-write refresh cannot reuse a snapshot begun before the write (lost response: %s)', async lost => {
  let releaseOld, signalStarted, directoryReads = 0, writes = 0
  const started = new Promise(resolve => { signalStarted = resolve })
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (url.endsWith('/api/directory')) {
      if (++directoryReads === 1) return new Promise(resolve => { releaseOld = () => resolve(jsonResponse(emptyDirectory())); signalStarted() })
      return jsonResponse({ ...emptyDirectory(), packages: [packageRecord] })
    }
    if (options.method === 'POST' && url.endsWith('/api/packages')) {
      writes++
      if (lost) throw new Error('Lost committed response')
      return jsonResponse(packageRecord)
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  const services = createPortalServices(make(fetch))
  const beforeWrite = services.load()
  await started
  const save = services.packageService.save({ draft: packageDraft })
  if (lost) await expect(save).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  else await expect(save).resolves.toMatchObject({ id: packageRecord.id })
  const afterWrite = services.load()
  releaseOld()
  const [old, fresh] = await Promise.all([beforeWrite, afterWrite])
  expect(old.data.packages).toEqual([])
  expect(fresh.data.packages).toEqual([expect.objectContaining({ id: packageRecord.id, name: packageRecord.name })])
  expect(directoryReads).toBe(2)
  expect(writes).toBe(1)
})

it('reads authorized notes without a directory reload and rejects mismatched reviewed versions', async () => {
  const client = { id: '00000000-0000-4000-8000-000000000111', version: 2, people: [] }
  let version = 2
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { id: client.id, version, people: [], healthNotes: 'Private note', remarks: '' }))
  const services = createPortalServices(make(fetch))
  expect(await services.readClientNotes(client)).toMatchObject({ healthNotes: 'Private note', notesAvailable: true })
  expect(fetch.mock.calls.map(([url]) => new URL(url).pathname)).toEqual(['/me', `/api/clients/${client.id}/notes`])
  version = 3
  await expect(services.readClientNotes(client)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(services.readClientNotes({ ...client, id: '../other' })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
})
