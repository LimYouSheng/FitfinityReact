import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId, directoryData } from '../test/directory.js'
import { trainerDeactivationReview } from '../test/trainerDeactivation.js'

const input = () => ({ id: directoryId(1), reviewed: trainerDeactivationReview(), replacements: { [directoryId(30)]: directoryId(31) } })
const request = (value = input()) => ({ service: 'trainerService', operation: 'deactivate', input: value })
const saved = { id: directoryId(1), version: 2, status: 'inactive' }
it('connects configured review, batch preview and minimal save with CSRF', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : url.endsWith('/deactivation') ? saved : trainerDeactivationReview()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect(await services.reviewTrainerDeactivation({ id: saved.id, expectedVersion: 1 })).toEqual({ reviewed: trainerDeactivationReview(), replacements: {}, uncertain: false })
  expect(await services.previewTrainerDeactivation(input())).toEqual(trainerDeactivationReview())
  expect(await services.trainerService.deactivate(input())).toEqual(saved)
  const posts = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(posts).toHaveLength(2)
  for (const [, options] of posts) {
    expect(JSON.parse(options.body)).toEqual({ expected: 'a'.repeat(64), replacements: input().replacements })
    expect(options.headers['X-CSRF-Token']).toBeTruthy()
  }
})
it('reconciles committed interrupted deactivation without repeating a write', async () => {
  const fetch = vi.fn(async (url, o) => url.endsWith('/me') ? jsonResponse(sessionInfo()) : o.method === 'POST' ? failure('service_unavailable', 503) : jsonResponse(saved))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ status: 503 })
  expect((await adapter.reviewTrainerDeactivation({ id: saved.id, expectedVersion: 1 })).uncertain).toBe(true)
  await expect(adapter.previewTrainerDeactivation(input())).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual(saved)
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
})
it('retries absent receipts only with the identical original command and key', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, o) => url.endsWith('/me') ? jsonResponse(sessionInfo()) : o.method === 'GET' ? failure('not_found', 404) : ++writes === 1 ? failure('service_unavailable', 503) : jsonResponse(saved))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ status: 503 })
  const changed = input(); changed.reviewed.expected = 'b'.repeat(64)
  await expect(adapter.invoke(request(changed))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual(saved)
  const posts = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(posts).toHaveLength(2)
  expect(posts[0][1].body).toBe(posts[1][1].body)
  expect(posts[0][1].headers['Idempotency-Key']).toBe(posts[1][1].headers['Idempotency-Key'])
})
it('rejects malformed, financial, stale and foreign reviews', async () => {
  let viewed = trainerDeactivationReview()
  const adapter = createApiPortalAdapter({ fetchImpl: async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : viewed) })
  await expect(adapter.reviewTrainerDeactivation({ id: saved.id, expectedVersion: 2 })).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  for (const mutate of [r => { r.id = directoryId(90) }, r => { r.sessions[0].trainerId = directoryId(90) }, r => { r.sessions[0].choices[0].rates = {} }, r => { r.sessions[0].scheduleState = 'open' }]) {
    viewed = trainerDeactivationReview(); mutate(viewed)
    await expect(adapter.reviewTrainerDeactivation({ id: saved.id, expectedVersion: 1 })).rejects.toMatchObject({ code: 'API_RESPONSE' })
  }
})
it('rejects incomplete or unavailable replacement batches before writing', async () => {
  const fetch = vi.fn(), adapter = createApiPortalAdapter({ fetchImpl: fetch })
  const bad = input(); bad.reviewed.sessions[0].choices[0].error = 'Already booked'
  await expect(adapter.invoke(request(bad))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(adapter.invoke(request({ ...input(), replacements: {} }))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})
it('rejects a mismatched saved state and retains uncertain original intent', async () => {
  const adapter = createApiPortalAdapter({ fetchImpl: async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...saved, status: 'active' }) })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect((await adapter.reviewTrainerDeactivation({ id: saved.id, expectedVersion: 1 })).uncertain).toBe(true)
})
it('preserves ordinary Trainer directory loads while denying deactivation', async () => {
  const session = sessionInfo(); session.user = { ...session.user, role: 'trainer', trainerId: saved.id }
  const directory = directoryData(); directory.viewerId = session.user.id; directory.packages = []
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? session : url.endsWith('/policy') ? authPolicy : directory))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  expect((await adapter.load()).user.role).toBe('trainer')
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(0)
})
