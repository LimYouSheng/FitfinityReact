import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryData, directoryId } from '../test/directory.js'
import { weeklyInput, weeklyResult, weeklyReview } from '../test/clientWeeklySchedule.js'
const request = (input = weeklyInput()) => ({ service: 'clientService', operation: 'saveFixedWeeklySchedule', input })
it('forwards configured review/preview/save with scoped digest, CSRF and stable write identity', async () => {
  const fetch = vi.fn(async (url, o) => jsonResponse(url.endsWith('/me') ? sessionInfo() : o.method === 'GET' ? weeklyReview() : url.endsWith('-review') ? { expected: 'a'.repeat(64), outcome: 'applied', updatedSessions: 1 } : weeklyResult()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect((await services.reviewClientWeeklySchedule({ id: directoryId(7), expectedVersion: 2 })).reviewed).toEqual(weeklyReview())
  expect((await services.previewClientWeeklySchedule(weeklyInput())).updatedSessions).toBe(1)
  expect(await services.clientService.saveFixedWeeklySchedule(weeklyInput())).toEqual(weeklyResult())
  const posts = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(posts).toHaveLength(2)
  for (const [, o] of posts) {
    expect(JSON.parse(o.body)).toEqual({ expected: 'a'.repeat(64), slots: [{ id: directoryId(6), weekday: 0, startsAt: '12:00', endsAt: '13:00' }] })
    expect(o.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
    expect(o.headers['X-CSRF-Token']).toBe(sessionInfo().csrfToken)
  }
})
it('reconciles an interrupted committed save without replaying the write', async () => {
  const fetch = vi.fn(async (url, o) => { if (url.endsWith('/me')) return jsonResponse(sessionInfo()); if (o.method === 'POST') throw new Error('offline'); return jsonResponse(weeklyResult()) })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.reviewClientWeeklySchedule({ id: directoryId(7), expectedVersion: 2 })).toEqual({ reviewed: weeklyReview(), slots: weeklyInput().slots, uncertain: true })
  expect(await adapter.invoke(request())).toEqual(weeklyResult())
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
})
it('retries an absent receipt only with the original input and key', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, o) => url.endsWith('/me') ? jsonResponse(sessionInfo()) : o.method === 'GET' ? failure('not_found', 404) : ++writes === 1 ? failure('service_unavailable', 503) : jsonResponse(weeklyResult()))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ status: 503 })
  const changed = weeklyInput(); changed.slots[0].from = '12:15'
  await expect(adapter.invoke(request(changed))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await expect(adapter.reviewClientWeeklySchedule({ id: directoryId(90), expectedVersion: 2 })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual(weeklyResult())
  const posts = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(posts[0][1].body).toBe(posts[1][1].body)
  expect(posts[0][1].headers['Idempotency-Key']).toBe(posts[1][1].headers['Idempotency-Key'])
})
it('rejects stale, foreign, private and malformed review data', async () => {
  let reviewed = weeklyReview()
  const adapter = createApiPortalAdapter({ fetchImpl: async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : reviewed) })
  await expect(adapter.reviewClientWeeklySchedule({ id: directoryId(7), expectedVersion: 1 })).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  for (const change of [r => { r.id = directoryId(90) }, r => { r.rates = {} }, r => { r.slots[0].weekday = 7 }, r => { r.sessions[0].date = null }]) {
    reviewed = weeklyReview(); change(reviewed)
    await expect(adapter.reviewClientWeeklySchedule({ id: directoryId(7), expectedVersion: 2 })).rejects.toMatchObject({ code: 'API_RESPONSE' })
  }
})
it('rejects changed weekly days or slot identities before issuing a request', async () => {
  const fetch = vi.fn(), adapter = createApiPortalAdapter({ fetchImpl: fetch })
  for (const change of [r => { r.slots[0].day = 'Tuesday' }, r => { r.slots[0].id = directoryId(90) }, r => { r.slots[0].to = '11:00' }]) {
    const input = weeklyInput(); change(input)
    await expect(adapter.invoke(request(input))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  }
  expect(fetch).not.toHaveBeenCalled()
})
it('preserves uncertainty after an inconsistent saved response', async () => {
  const adapter = createApiPortalAdapter({ fetchImpl: async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...weeklyResult(), updatedSessions: 90 }) })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect((await adapter.reviewClientWeeklySchedule({ id: directoryId(7), expectedVersion: 2 })).uncertain).toBe(true)
})
it('loads an assigned Trainer and accepts its supervised proposal without claiming approved changes', async () => {
  const session = sessionInfo(); session.user = { ...session.user, role: 'trainer', trainerId: directoryId(1) }
  const directory = directoryData(); directory.viewerId = session.user.id; directory.packages = []
  const adapter = createApiPortalAdapter({ fetchImpl: async (url, o) => jsonResponse(url.endsWith('/me') ? session : url.endsWith('/policy') ? authPolicy : o.method === 'POST' ? weeklyResult('requested') : directory) })
  expect((await adapter.load()).user.role).toBe('trainer')
  expect(await adapter.invoke(request(weeklyInput('requested')))).toEqual(weeklyResult('requested'))
})
