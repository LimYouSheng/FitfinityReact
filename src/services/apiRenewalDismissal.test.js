import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { renewalState } from './apiMessages.js'
import { directoryData, directoryId } from '../test/directory.js'
import { personalNotice } from '../test/messageApi.js'
import { authPolicy, failure, jsonResponse, sessionInfo, staff } from '../test/api.js'

const input = { id: directoryId(90), expectedClientVersion: 2 }
const result = { id: input.id, renewalStatus: 'removed', renewalDismissal: { at: '2026-10-13T12:00:00Z', by: { id: staff.id, name: staff.name } } }
function transport(handler) {
  return vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), personalMessages: true, renewalDismissalWrites: true })
    return handler(url, options)
  })
}
const servicesFor = fetch => createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))

it('submits only the reviewed client version and decodes shared dismissal evidence', async () => {
  const fetch = transport(() => jsonResponse(result))
  expect(await servicesFor(fetch).messageService.dismissRenewal(input)).toEqual(result)
  const [url, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(new URL(url).pathname).toBe(`/api/messages/${input.id}/dismiss-renewal`)
  expect(JSON.parse(options.body)).toEqual({ expectedClientVersion: 2 })
  expect(options.headers['Idempotency-Key']).toBeTruthy()
})

it('reconciles a committed removal on snapshot reload without repeating the write', async () => {
  let writes = 0
  const services = servicesFor(transport((url, options) => {
    if (options.method === 'POST') { writes++; throw new Error('offline') }
    return jsonResponse(url.includes('/renewal-dismissal-saves/') ? result : [personalNotice({ kind: 'renewal', ...result })])
  }))
  await expect(services.messageService.dismissRenewal(input)).rejects.toThrow()
  const snapshot = await services.load()
  expect(snapshot.renewalDismissalPending).toBeNull()
  expect(snapshot.capabilities.renewalDismissalWrites).toBe(true)
  expect(snapshot.data.messages[0].renewalDismissal).toEqual(result.renewalDismissal)
  expect(writes).toBe(1)
})

it('retains the original unresolved body through reload and requires identical explicit retry', async () => {
  let writes = 0
  const fetch = transport((url, options) => {
    if (options.method === 'POST') { if (++writes === 1) throw new Error('offline'); return jsonResponse(result) }
    return url.includes('/renewal-dismissal-saves/') ? failure('not_found', 404) : jsonResponse([])
  })
  const services = servicesFor(fetch)
  await expect(services.messageService.dismissRenewal(input)).rejects.toThrow()
  expect((await services.load()).renewalDismissalPending).toEqual(input)
  await expect(services.messageService.dismissRenewal({ ...input, expectedClientVersion: 3 })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await services.messageService.dismissRenewal(input)).toEqual(result)
  const attempts = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(attempts[0].body).toBe(attempts[1].body)
  expect(attempts[0].headers['Idempotency-Key']).toBe(attempts[1].headers['Idempotency-Key'])
})

it('accepts an already-renewed result without inventing dismissal evidence', async () => {
  const saved = { id: input.id, renewalStatus: 'renewed', renewalDismissal: null }
  expect(await servicesFor(transport(() => jsonResponse(saved))).messageService.dismissRenewal(input)).toEqual(saved)
})

it('rejects missing review versions before posting', async () => {
  const fetch = transport(() => jsonResponse(result))
  await expect(servicesFor(fetch).messageService.dismissRenewal({ id: input.id })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(0)
})

it('rejects invalid or excessive dismissal evidence and mismatched result identity', async () => {
  for (const value of [{ ...result, renewalDismissal: null }, { ...result, renewalStatus: 'active' }, { ...result, readBy: {} }, { ...result, renewalDismissal: { ...result.renewalDismissal, by: { ...result.renewalDismissal.by, email: 'private@example.test' } } }]) expect(() => renewalState(value)).toThrow()
  await expect(servicesFor(transport(() => jsonResponse({ ...result, id: directoryId(91) }))).messageService.dismissRenewal(input)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('keeps a forbidden dismissal rejection definitive and permits a new reviewed attempt', async () => {
  let writes = 0
  const fetch = transport(() => ++writes === 1 ? failure('not_found', 404) : jsonResponse(result))
  const services = servicesFor(fetch)
  await expect(services.messageService.dismissRenewal(input)).rejects.toMatchObject({ code: 'not_found' })
  expect(await services.messageService.dismissRenewal({ ...input, expectedClientVersion: 3 })).toEqual(result)
  const attempts = fetch.mock.calls.filter(([, options]) => options.method === 'POST')
  expect(attempts[0][1].headers['Idempotency-Key']).not.toBe(attempts[1][1].headers['Idempotency-Key'])
})
