import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId, directoryData } from '../test/directory.js'
import { assignmentReview } from '../test/clientAssignment.js'

const input = () => ({ id: directoryId(7), draft: { reviewed: assignmentReview(), trainerId: directoryId(31) } })
const request = value => ({ service: 'clientService', operation: 'reassignTrainer', input: value ?? input() })
const saved = { id: directoryId(7), version: 3, trainerId: directoryId(31), eventId: directoryId(32) }

it('reviews and saves only the server digest and selected Trainer through a scoped helper', async () => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? sessionInfo() : options.method === 'GET' ? assignmentReview() : saved))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect(await services.previewClientAssignment({ id: saved.id, expectedVersion: 2 })).toEqual({ reviewed: assignmentReview(), trainerId: '', uncertain: false })
  expect(await services.clientService.reassignTrainer(input())).toEqual(saved)
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ expected: 'a'.repeat(64), trainerId: directoryId(31), purchaseId: directoryId(9) })
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
})
it('retains original selection and reconciles a committed interrupted response without replay', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') throw new Error('offline')
    return jsonResponse(saved)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.previewClientAssignment({ id: saved.id, expectedVersion: 2 })).toEqual({ reviewed: assignmentReview(), trainerId: saved.trainerId, uncertain: true })
  expect(await adapter.invoke(request())).toEqual(saved)
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
})
it('requires identical input when an absent receipt permits explicit retry', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'GET') return failure('not_found', 404)
    return ++writes === 1 ? failure('service_unavailable', 503) : jsonResponse(saved)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ status: 503 })
  const changed = input(); changed.draft.reviewed.expected = 'b'.repeat(64)
  await expect(adapter.invoke(request(changed))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual(saved)
  const posts = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(posts).toHaveLength(2)
  expect(posts[0][1].body).toBe(posts[1][1].body)
  expect(posts[0][1].headers['Idempotency-Key']).toBe(posts[1][1].headers['Idempotency-Key'])
})
it('refuses stale, foreign, incomplete and financially contaminated server reviews', async () => {
  let reviewed = assignmentReview()
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : reviewed))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.previewClientAssignment({ id: saved.id, expectedVersion: 1 })).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  for (const mutate of [r => { r.id = directoryId(90) }, r => { r.sessions[0].purchaseId = directoryId(90) }, r => { r.choices[0].rates = {} }, r => { r.sessions[0].scheduleState = 'open' }]) {
    reviewed = assignmentReview(); mutate(reviewed)
    await expect(adapter.previewClientAssignment({ id: saved.id, expectedVersion: 2 })).rejects.toMatchObject({ code: 'API_RESPONSE' })
  }
})
it('rejects unavailable selections locally and never sends a caller-supplied actor', async () => {
  const fetch = vi.fn(), adapter = createApiPortalAdapter({ fetchImpl: fetch })
  const invalid = input(); invalid.draft.reviewed.choices[0].error = 'Already booked'
  await expect(adapter.invoke(request(invalid))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})
it('rejects a mismatched saved Trainer and retains the original uncertain operation', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...saved, trainerId: directoryId(90) }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect((await adapter.previewClientAssignment({ id: saved.id, expectedVersion: 2 })).uncertain).toBe(true)
})
it('does not break ordinary Trainer directory loads and refuses assignment before any domain write', async () => {
  const session = sessionInfo(); session.user = { ...session.user, role: 'trainer', trainerId: directoryId(1) }
  const directory = directoryData(); directory.viewerId = session.user.id; directory.packages = []
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? session : url.endsWith('/policy') ? authPolicy : directory))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  expect((await adapter.load()).user.role).toBe('trainer')
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(0)
})
