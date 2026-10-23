import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { personalMessage } from './apiMessages.js'
import { directoryData, directoryId } from '../test/directory.js'
import { messageRequest, personalNotice } from '../test/messageApi.js'
import { authPolicy, failure, jsonResponse, sessionInfo, staff } from '../test/api.js'

function transport(handler) {
  return vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), personalMessages: true })
    return handler(url, options)
  })
}
const input = { id: directoryId(90), expectedVersion: 1 }
const savedRead = { ...input, version: 2, read: true, readAt: '2026-10-13T11:00:00Z' }
delete savedRead.expectedVersion

it('loads personal messages into the scoped API snapshot and enables its existing route', async () => {
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: transport(() => jsonResponse([personalNotice()])) }))
  const snapshot = await services.load()
  expect(snapshot.capabilities.personalMessages).toBe(true)
  expect(snapshot.data.messages).toEqual([personalNotice()])
  expect(snapshot.messageReadPending).toBeNull()
})

it('uses a reviewed personal version for read and unread commands', async () => {
  const fetch = transport((_url, options) => {
    const body = JSON.parse(options.body)
    return jsonResponse({ id: input.id, version: body.expectedVersion + 1, read: body.read, readAt: body.read ? savedRead.readAt : null })
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  expect(await services.messageService.markRead(input)).toEqual(savedRead)
  expect(await services.messageService.markUnread({ ...input, expectedVersion: 2 })).toEqual({ id: input.id, version: 3, read: false, readAt: null })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => JSON.parse(options.body))).toEqual([{ expectedVersion: 1, read: true }, { expectedVersion: 2, read: false }])
})

it('a snapshot read reconciles a committed unknown command without repeating it', async () => {
  let writes = 0
  const fetch = transport((url, options) => {
    if (options.method === 'POST') { writes++; throw new Error('offline') }
    return jsonResponse(url.includes('/message-read-saves/') ? savedRead : [personalNotice(savedRead)])
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.messageService.markRead(input)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const snapshot = await services.load()
  expect(snapshot.messageReadPending).toBeNull()
  expect(snapshot.data.messages[0].read).toBe(true)
  expect(writes).toBe(1)
})

it('missing receipts retain the original intent across snapshot recovery and prevent replacement commands', async () => {
  let writes = 0
  const fetch = transport((url, options) => {
    if (options.method === 'POST') { if (++writes === 1) throw new Error('offline'); return jsonResponse(savedRead) }
    return url.includes('/message-read-saves/') ? failure('not_found', 404) : jsonResponse([personalNotice()])
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.messageService.markRead(input)).rejects.toThrow()
  const snapshot = await services.load()
  expect(snapshot.messageReadPending).toEqual({ ...input, read: true })
  await expect(services.messageService.markUnread(input)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await services.messageService.markRead({ id: snapshot.messageReadPending.id, expectedVersion: snapshot.messageReadPending.expectedVersion })
  const posts = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(posts).toHaveLength(2)
  expect(posts[1].body).toBe(posts[0].body)
  expect(posts[1].headers['Idempotency-Key']).toBe(posts[0].headers['Idempotency-Key'])
})

it.each([
  { recipientUserId: directoryId(99) }, { readBy: { other: true } }, { read: true }, { version: -1 },
  { requestId: directoryId(91) }, { createdAt: 'invalid' },
])('rejects malformed or wrongly scoped message projections: %j', patch => {
  expect(() => personalMessage(personalNotice(patch), staff)).toThrow()
})

it.each(['trainer_rates', 'remuneration_pending'])('rejects Admin financial message leakage: %s', kind => {
  expect(() => personalMessage(personalNotice({ kind }), { ...staff, role: 'admin' })).toThrow()
})

it.each(['trainer_availability', 'fixed_weekly_schedule', 'session_time', 'session_trainer'])('maps the exact %s proposal into the approved read-only comparison', kind => {
  const fields = kind === 'trainer_availability' ? {} : { client_id: directoryId(7), purchase_id: directoryId(8) }
  if (kind.startsWith('session_')) Object.assign(fields, { session_id: directoryId(9), slots: [] })
  if (kind === 'session_time') Object.assign(fields, { old_date: '2026-10-13', new_date: '2026-10-14', old_start: '10:00:00', old_end: '11:00:00', new_start: '11:00:00', new_end: '12:00:00' })
  if (kind === 'session_trainer') fields.replacement_trainer_id = directoryId(2)
  const request = messageRequest({ kind, ...fields })
  const result = personalMessage(personalNotice({ requestId: request.id, request }), staff)
  expect(result.status).toBe('pending')
  expect(result.request.type).toBe(kind)
  if (kind === 'trainer_availability') expect(result.request.newAvailability.Monday).toEqual([['11:00', '12:00']])
  if (kind === 'fixed_weekly_schedule') expect(result.request.newSlots[0]).toMatchObject({ day: 'Monday', from: '11:00', to: '12:00' })
  if (kind === 'session_time') expect(result.request.next).toEqual({ date: '2026-10-14', from: '11:00', to: '12:00' })
  if (kind === 'session_trainer') expect(result.request.replacementTrainerId).toBe(directoryId(2))
})

it('rejects missing reviewed versions and stale rendered login commands', async () => {
  const fetch = transport(() => jsonResponse(savedRead))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.messageService.markRead({ id: input.id })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(services.forSession(999).messageService.markRead(input)).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch).not.toHaveBeenCalled()
})

it('a later Messages preflight detects account changes before requesting private notices', async () => {
  let identities = 0
  const fetch = vi.fn(async url => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse(++identities === 1 ? sessionInfo() : { ...sessionInfo(), user: { ...staff, id: directoryId(99), role: 'admin' } })
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), personalMessages: true })
    throw new Error('Must not request messages with old authority')
  })
  await expect(createApiPortalAdapter({ fetchImpl: fetch }).load()).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/api/messages'))).toBe(false)
})

const trainer = { ...staff, role: 'trainer', trainerId: directoryId(1) }
const cancellationInput = { id: directoryId(91), expectedVersion: 1 }
const cancellation = { id: directoryId(91), version: 2, status: 'cancelled', at: '2026-10-13T16:00:00Z', by: { id: trainer.id, name: trainer.name } }
function cancellationTransport(handler) {
  return vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse({ ...sessionInfo(), user: trainer })
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), packages: [], personalMessages: true, requestCancellationWrites: true })
    if (url.endsWith('/api/messages')) return jsonResponse([])
    return handler(url, options)
  })
}
it('cancellation retains its version and historical actor in personal messages', () => {
  const request = messageRequest({ status: 'cancelled', version: 2, resolved_at: cancellation.at, resolved_by: cancellation.by })
  expect(personalMessage(personalNotice({ requestId: request.id, request }), trainer)).toMatchObject({ requestVersion: 2, status: 'cancelled', cancelledAt: cancellation.at, cancelledBy: cancellation.by })
  expect(() => personalMessage(personalNotice({ requestId: request.id, request: { ...request, resolved_by: { ...cancellation.by, email: 'private@example.test' } } }), trainer)).toThrow()
})
it('an interrupted committed cancellation reconciles before any retry and never cancels twice', async () => {
  const fetch = cancellationTransport((_url, options) => {
    if (options.method === 'POST') throw new Error('offline')
    return jsonResponse(cancellation)
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.requestService.cancel(cancellationInput)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await services.requestService.cancel(cancellationInput)).toEqual(cancellation)
  const posts = fetch.mock.calls.filter(([, options]) => options.method === 'POST')
  expect(posts).toHaveLength(1)
  expect(JSON.parse(posts[0][1].body)).toEqual({ expectedVersion: 1 })
})
it('an absent cancellation receipt preserves original input and key until explicit retry', async () => {
  let writes = 0
  const fetch = cancellationTransport((_url, options) => {
    if (options.method === 'POST') { if (++writes === 1) throw new Error('offline'); return jsonResponse(cancellation) }
    return failure('not_found', 404)
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.requestService.cancel(cancellationInput)).rejects.toThrow()
  const snapshot = await services.load()
  expect(snapshot.requestCancellationPending).toEqual(cancellationInput)
  expect(snapshot.capabilities.requestCancellationWrites).toBe(true)
  await expect(services.requestService.cancel({ ...cancellationInput, expectedVersion: 2 })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await services.requestService.cancel(cancellationInput)
  const posts = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(posts).toHaveLength(2)
  expect(posts[0].body).toBe(posts[1].body)
  expect(posts[0].headers['Idempotency-Key']).toBe(posts[1].headers['Idempotency-Key'])
})
it('owners and invalid versions cannot issue cancellation commands', async () => {
  const fetch = transport(() => { throw new Error('No command allowed') })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.requestService.cancel(cancellationInput)).rejects.toMatchObject({ code: 'forbidden' })
  await expect(services.requestService.cancel({ ...cancellationInput, expectedVersion: 0 })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch.mock.calls.some(([, options]) => options.method === 'POST')).toBe(false)
})

it('retains a single postponed-session comparison without inventing a replacement booking', () => {
  const request = messageRequest({ kind: 'session_postpone', client_id: directoryId(7), purchase_id: directoryId(4), session_id: directoryId(5), old_date: '2026-10-14', old_start: '10:00:00', old_end: '11:00:00', slots: [] })
  const row = personalMessage(personalNotice({ requestId: request.id, request }), staff)
  expect(row.request.changes).toEqual([{ sessionId: directoryId(5), before: { scheduleState: 'scheduled', date: '2026-10-14', from: '10:00', to: '11:00' }, next: { scheduleState: 'open', date: '', from: '', to: '' } }])
  for (const patch of [{ new_date: '2026-10-20' }, { old_date: null }, { old_end: '09:00:00' }]) expect(() => personalMessage(personalNotice({ requestId: request.id, request: { ...request, ...patch } }), staff)).toThrow()
})

it('retains Open as the original state when a pending request proposes booking it', () => {
  const request = messageRequest({ kind: 'session_time', client_id: directoryId(7), purchase_id: directoryId(4), session_id: directoryId(5), new_date: '2026-10-14', new_start: '10:00:00', new_end: '11:00:00', slots: [] })
  const row = personalMessage(personalNotice({ requestId: request.id, request }), staff)
  expect(row.request.previous).toEqual({ scheduleState: 'open', date: '', from: '', to: '' })
  expect(row.request.next).toEqual({ date: '2026-10-14', from: '10:00', to: '11:00' })
  expect(() => personalMessage(personalNotice({ requestId: request.id, request: { ...request, old_start: '09:00:00' } }), staff)).toThrow()
})

it('a background snapshot does not replace the inbox while its read command is still in flight', async () => {
  let finish, started
  const active = new Promise(resolve => { started = resolve })
  const fetch = transport((url, options) => {
    if (options.method === 'POST') { started(); return new Promise(resolve => { finish = () => resolve(jsonResponse(savedRead)) }) }
    return url.includes('/message-read-saves/') ? failure('not_found', 404) : jsonResponse([personalNotice()])
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  const saving = services.messageService.markRead(input)
  await active
  try {
    const snapshot = await services.load()
    expect(snapshot.messageReadPending).toBeNull()
    expect(fetch.mock.calls.some(([url]) => url.includes('/message-read-saves/'))).toBe(false)
  } finally { finish(); await saving }
  expect((await services.load()).messageReadPending).toBeNull()
})
