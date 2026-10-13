import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId } from '../test/directory.js'

const reviewed = { id: directoryId(2), version: 2, accountId: directoryId(3), accountVersion: 4 }
const request = { service: 'trainerService', operation: 'reactivate', input: { id: reviewed.id, reviewed } }
const state = { id: reviewed.id, version: 3, status: 'active' }

it('reviews the linked account and submits only its reviewed versions', async () => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? sessionInfo() : options.method === 'POST' ? state : reviewed))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  expect(await services.previewTrainerReactivation({ id: reviewed.id, expectedVersion: 2 })).toEqual({ reviewed, uncertain: false })
  expect(await services.trainerService.reactivate(request.input)).toEqual(state)
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ expectedVersion: 2, expectedAccountId: reviewed.accountId, expectedAccountVersion: 4 })
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
})

it('retains the original review after an unknown save and reads its receipt without resending', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { writes++; throw new Error('offline') }
    return jsonResponse(state)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const recovery = await adapter.previewTrainerReactivation({ id: reviewed.id, expectedVersion: 3 })
  expect(recovery).toEqual({ reviewed, uncertain: true })
  expect(fetch.mock.calls.filter(([url, options]) => url.endsWith('/reactivation') && options.method === 'GET')).toHaveLength(0)
  await expect(adapter.previewTrainerReactivation({ id: directoryId(4), expectedVersion: 2 })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request)).toEqual(state)
  expect(writes).toBe(1)
})

it('rejects a newer review before a write and rejects malformed account linkage', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : reviewed))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.previewTrainerReactivation({ id: reviewed.id, expectedVersion: 1 })).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  await expect(adapter.invoke({ ...request, input: { ...request.input, reviewed: { ...reviewed, accountId: null } } })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch.mock.calls.every(([, options]) => options.method === 'GET')).toBe(true)
})

it('allows explicit identical retry only after no receipt is found', async () => {
  const writes = []
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (url.includes('/trainer-reactivations/')) return failure('not_found', 404)
    if (options.method === 'POST') {
      writes.push(options)
      if (writes.length === 1) throw new Error('offline')
      return jsonResponse(state)
    }
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.invoke(request)).toEqual(state)
  expect(writes[1].body).toBe(writes[0].body)
  expect(writes[1].headers['Idempotency-Key']).toBe(writes[0].headers['Idempotency-Key'])
})

it('clears a definitive conflict so the next attempt can review fresh values', async () => {
  const fetch = vi.fn(async (url, options) => url.endsWith('/me') ? jsonResponse(sessionInfo()) : options.method === 'POST' ? failure('conflict', 409) : jsonResponse(reviewed))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request)).rejects.toMatchObject({ status: 409 })
  expect(await adapter.previewTrainerReactivation({ id: reviewed.id, expectedVersion: 2 })).toEqual({ reviewed, uncertain: false })
})

it('denies Trainer review and write without domain HTTP calls', async () => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer', trainerId: reviewed.id } }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.previewTrainerReactivation({ id: reviewed.id, expectedVersion: 2 })).rejects.toMatchObject({ code: 'forbidden' })
  await expect(adapter.invoke(request)).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.every(([url]) => url.endsWith('/me'))).toBe(true)
})

it('rejects unverified receipts and preserves the uncertain review', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...state, version: 9 }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect((await adapter.previewTrainerReactivation({ id: reviewed.id, expectedVersion: 2 })).uncertain).toBe(true)
})
