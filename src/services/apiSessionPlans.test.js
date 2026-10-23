import { expect, it, vi } from 'vitest'
import { sessionPlanCommands } from './apiSessionPlans.js'
import { ApiError } from './apiClient.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'

const item = () => ({ id: 'draft-one', name: 'Squat', weight: '12 kg', reps: '8', rounds: '3', rest: '60s', customDetails: [{ id: 'detail-a', value: 'Slow descent' }] })
const review = () => ({ sessionId: id(1), version: 2, expected: 'a'.repeat(64), items: [] })
const input = () => ({ sessionId: id(1), reviewed: review(), items: [item()] })
const result = () => ({ sessionId: id(1), version: 3, items: [{ ...item(), id: id(2), version: 1, notes: '', videoAttached: false }], savedAt: '2026-10-23T07:00:00Z' })
const actor = async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 })

it.each(['owner', 'admin', 'trainer'])('configured %s plan writes preserve ordered details and server-assigned identity', async role => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role, ...(role === 'trainer' ? { trainerId: id(9) } : {}) } } : options.method === 'GET' ? review() : result()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect((await services.reviewSessionPlan({ id: id(1), expectedVersion: 2 })).reviewed).toEqual(review())
  expect(await services.sessionService.saveExercisePlan(input())).toEqual(result())
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ expected: review().expected, items: [item()] })
  expect(options.headers['Idempotency-Key']).toEqual(expect.any(String))
})

it('freezes original details after a lost response and reconciles without a second write', async () => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'Lost') }), get: vi.fn(async () => result()) }
  const service = sessionPlanCommands(http, actor)
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await service.review({ id: id(1), expectedVersion: 3 }, 0)).toEqual({ reviewed: review(), draft: [item()], uncertain: true })
  await expect(service.save({ ...input(), items: [{ ...item(), name: 'Different' }] }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await service.save(input(), 0)).toEqual(result())
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(service.pendingInput(0)).toBeNull()
})

it('rejects stale reviews, foreign response identities and lost details rather than claiming success', async () => {
  let saved = { ...result(), sessionId: id(8) }
  const service = sessionPlanCommands({ get: async () => review(), post: async () => saved }, actor)
  await expect(service.review({ id: id(1), expectedVersion: 1 }, 0)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(service.pendingInput(0)).toEqual(input())
  const next = sessionPlanCommands({ get: async () => review(), post: async () => saved }, actor)
  saved = result(); saved.items[0].customDetails = []
  await expect(next.save(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('retains existing item identities and rejects unexpected private fields', async () => {
  const data = input(); data.items[0].id = id(3)
  const service = sessionPlanCommands({ get: async () => ({ ...review(), healthNotes: 'private' }), post: async () => result() }, actor)
  await expect(service.review({ id: id(1), expectedVersion: 2 }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(service.save(data, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
