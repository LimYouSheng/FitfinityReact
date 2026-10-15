import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { directoryData, directoryId, onboardingPolicy } from '../test/directory.js'
import { authPolicy, failure, jsonResponse, sessionInfo, staff } from '../test/api.js'

const trainer = { ...staff, role: 'trainer', trainerId: directoryId(1) }
const input = { id: directoryId(1), expectedVersion: 1, blocks: [{ id: 'draft', days: ['Tuesday'], from: '09:00', to: '10:00' }] }
const applied = { outcome: 'applied', trainer: { id: input.id, version: 2 }, requestId: null }
const requested = { outcome: 'requested', trainer: { id: input.id, version: 1 }, requestId: directoryId(91) }
function setup(handler, user = trainer) {
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse({ ...sessionInfo(), user })
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), packages: [], personalMessages: true, clientOnboardingPolicy: onboardingPolicy, trainerAvailabilityWrites: true })
    if (url.endsWith('/api/messages')) return jsonResponse([])
    return handler(url, options)
  })
  return { fetch, services: createPortalServices(createApiPortalAdapter({ fetchImpl: fetch })) }
}
it.each([applied, requested])('maps availability blocks to strict server windows and validates %j', async result => {
  const { services, fetch } = setup(() => jsonResponse(result))
  expect(await services.trainerService.saveAvailability(input)).toEqual(result)
  const post = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(post[0]).toContain(`/api/trainers/${input.id}/availability`)
  expect(JSON.parse(post[1].body)).toEqual({ expectedVersion: 1, slots: [{ weekday: 1, startsAt: '09:00', endsAt: '10:00' }] })
  expect(post[1].headers['X-CSRF-Token']).toBe(sessionInfo().csrfToken)
  expect(post[1].headers['Idempotency-Key']).toMatch(/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i)
})
it('reconciles a committed unknown submission on reload without duplicating the proposal', async () => {
  const { services, fetch } = setup((_url, options) => {
    if (options.method === 'POST') throw new Error('offline')
    return jsonResponse(requested)
  })
  await expect(services.trainerService.saveAvailability(input)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const snapshot = await services.load()
  expect(snapshot.trainerAvailabilityPending).toBeNull()
  expect(snapshot.trainerAvailabilityRecovered).toEqual(requested)
  expect(snapshot.capabilities.trainerAvailabilityWrites).toBe(true)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('retains missing-receipt input through reload and reuses its original key only on explicit retry', async () => {
  let count = 0
  const { services, fetch } = setup((_url, options) => {
    if (options.method === 'POST') { if (++count === 1) throw new Error('offline'); return jsonResponse(requested) }
    return failure('not_found', 404)
  })
  await expect(services.trainerService.saveAvailability(input)).rejects.toThrow()
  const snapshot = await services.load()
  expect(snapshot.trainerAvailabilityPending).toEqual(input)
  await expect(services.trainerService.saveAvailability({ ...input, blocks: [] })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await services.trainerService.saveAvailability(snapshot.trainerAvailabilityPending)
  const posts = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(posts).toHaveLength(2)
  expect(posts[1].body).toBe(posts[0].body)
  expect(posts[1].headers['Idempotency-Key']).toBe(posts[0].headers['Idempotency-Key'])
})
it('rejects a malformed result and reconciles the original write before accepting it', async () => {
  const { services, fetch } = setup((_url, options) => jsonResponse(options.method === 'POST' ? { ...requested, requestId: null } : requested))
  await expect(services.trainerService.saveAvailability(input)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(await services.trainerService.saveAvailability(input)).toEqual(requested)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('operations accounts cannot issue self-only availability writes', async () => {
  const { services, fetch } = setup(() => { throw new Error('No mutation allowed') }, staff)
  await expect(services.trainerService.saveAvailability(input)).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.some(([, options]) => options.method === 'POST')).toBe(false)
})
it('invalid windows or absent reviewed version fail before HTTP', async () => {
  const { services, fetch } = setup(() => { throw new Error('No request allowed') })
  await expect(services.trainerService.saveAvailability({ ...input, expectedVersion: 0 })).rejects.toThrow()
  await expect(services.trainerService.saveAvailability({ ...input, blocks: [{ days: ['Tuesday'], from: '12:00', to: '10:00' }] })).rejects.toThrow()
  expect(fetch).not.toHaveBeenCalled()
})
