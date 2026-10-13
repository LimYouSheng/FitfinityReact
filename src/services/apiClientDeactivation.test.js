import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { directoryData, directoryId } from '../test/directory.js'
import { deactivationReview } from '../test/clientLifecycleApi.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from '../test/api.js'

const reviewed = deactivationReview(), input = { id: reviewed.id, reviewed }
const result = { id: reviewed.id, version: reviewed.version + 1, status: 'inactive' }
function transport(handler, role = 'owner') {
  return vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) { const session = sessionInfo(); session.user.role = role; return jsonResponse(session) }
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), clientDeactivationWrites: true })
    return handler(url, options)
  })
}
const servicesFor = fetch => createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))

it('previews the exact purchased records and exposes the configured helper', async () => {
  const services = servicesFor(transport(() => jsonResponse(reviewed)))
  expect(await services.previewClientDeactivation({ id: reviewed.id, expectedVersion: reviewed.version })).toEqual({ reviewed, uncertain: false })
})

it('posts only the client, assignment and purchase review fields', async () => {
  const fetch = transport(() => jsonResponse(result))
  expect(await servicesFor(fetch).clientService.deactivate(input)).toEqual(result)
  const [url, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(new URL(url).pathname).toBe(`/api/clients/${reviewed.id}/deactivation`)
  expect(JSON.parse(options.body)).toEqual({ expectedVersion: reviewed.version, expectedTrainerId: reviewed.trainerId,
    purchases: reviewed.purchases.map(({ id, version, status }) => ({ id, version, status })) })
})

it('snapshot reconciliation resolves a committed unknown save without another POST', async () => {
  let writes = 0
  const services = servicesFor(transport((_url, options) => { if (options.method === 'POST') { writes++; throw new Error('offline') } return jsonResponse(result) }))
  await expect(services.clientService.deactivate(input)).rejects.toThrow()
  const snapshot = await services.load()
  expect(snapshot.clientDeactivationPending).toBeNull()
  expect(snapshot.capabilities.clientDeactivationWrites).toBe(true)
  expect(writes).toBe(1)
})

it('retains the original unresolved review and key through snapshot recovery', async () => {
  let writes = 0
  const fetch = transport((_url, options) => { if (options.method === 'POST') { if (++writes === 1) throw new Error('offline'); return jsonResponse(result) } return failure('not_found', 404) })
  const services = servicesFor(fetch)
  await expect(services.clientService.deactivate(input)).rejects.toThrow()
  expect((await services.load()).clientDeactivationPending).toEqual(input)
  expect(await services.previewClientDeactivation({ id: reviewed.id, expectedVersion: 100 })).toEqual({ reviewed, uncertain: true })
  await expect(services.previewClientDeactivation({ id: directoryId(99), expectedVersion: 1 })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await services.clientService.deactivate(input)).toEqual(result)
  const attempts = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(attempts[0].body).toBe(attempts[1].body)
  expect(attempts[0].headers['Idempotency-Key']).toBe(attempts[1].headers['Idempotency-Key'])
})

it('rejects a changed client preview before confirmation or posting', async () => {
  const fetch = transport(() => jsonResponse({ ...reviewed, version: 3 }))
  await expect(servicesFor(fetch).previewClientDeactivation({ id: reviewed.id, expectedVersion: 2 })).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(0)
})

it.each(['duplicate', 'private', 'identity'])('rejects %s fields in the server review', async change => {
  const value = structuredClone(reviewed)
  if (change === 'duplicate') value.purchases.push(value.purchases[0])
  if (change === 'private') value.healthNotes = 'private notes'
  if (change === 'identity') value.id = directoryId(99)
  const services = servicesFor(transport(() => jsonResponse(value)))
  await expect(services.previewClientDeactivation({ id: reviewed.id, expectedVersion: 2 })).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('keeps malformed write results uncertain until the original receipt is confirmed', async () => {
  let writes = 0
  const services = servicesFor(transport((_url, options) => { if (options.method === 'POST') { writes++; return jsonResponse({ ...result, status: 'active' }) } return jsonResponse(result) }))
  await expect(services.clientService.deactivate(input)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(await services.clientService.deactivate(input)).toEqual(result)
  expect(writes).toBe(1)
})

it('a definitive conflict permits a fresh reviewed command and key', async () => {
  let writes = 0
  const fetch = transport(() => ++writes === 1 ? failure('state_conflict', 409) : jsonResponse({ ...result, version: 4 }))
  const services = servicesFor(fetch)
  await expect(services.clientService.deactivate(input)).rejects.toMatchObject({ code: 'state_conflict' })
  await services.clientService.deactivate({ ...input, reviewed: { ...reviewed, version: 3 } })
  const attempts = fetch.mock.calls.filter(([, options]) => options.method === 'POST')
  expect(attempts[0][1].headers['Idempotency-Key']).not.toBe(attempts[1][1].headers['Idempotency-Key'])
})

it('Trainer authority cannot preview or post client deactivation', async () => {
  const fetch = transport(() => jsonResponse(result), 'trainer')
  const services = servicesFor(fetch)
  await expect(services.previewClientDeactivation({ id: reviewed.id, expectedVersion: 2 })).rejects.toMatchObject({ code: 'forbidden' })
  await expect(services.clientService.deactivate(input)).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(0)
})
