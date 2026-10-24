import { expect, it, vi } from 'vitest'
import { sessionOutcomeCommands, readClientProgress } from './apiSessionOutcomes.js'
import { ApiError } from './apiClient.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'

const row = () => ({ id: id(2), resultId: null, planItemId: id(2), name: 'Squat', loadKg: null, reps: null, sets: null })
const reviewed = () => ({ sessionId: id(1), version: 2, expected: 'a'.repeat(64), durationMinutes: 60, trainerComments: '', rows: [row()], draftRows: [{ ...row(), loadKg: 12, reps: 8, sets: 3 }] })
const input = () => ({ sessionId: id(1), reviewed: reviewed(), outcome: { durationMinutes: 999, trainerComments: ' Measured ', exerciseResults: [{ id: id(2), name: 'Squat', loadKg: '25', reps: '8', sets: '3' }] } })
const saved = () => ({ sessionId: id(1), version: 3, durationMinutes: 60, trainerComments: 'Measured', rows: [{ ...row(), resultId: id(3), loadKg: 25, reps: 8, sets: 3 }], savedAt: '2026-10-23T08:00:00Z' })
const actor = async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 })

it.each(['owner', 'admin', 'trainer'])('configured %s reviews defaults and saves measured values without trusting duration or actor fields', async role => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role, ...(role === 'trainer' ? { trainerId: id(9) } : {}) } } : options.method === 'GET' ? reviewed() : saved()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  const viewed = await services.reviewSessionOutcome({ id: id(1), expectedVersion: 2 })
  expect(viewed.draft.exerciseResults[0]).toMatchObject({ loadKg: 12, reps: 8, sets: 3 })
  expect(await services.sessionService.saveOutcome(input())).toEqual(saved())
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ expected: 'a'.repeat(64), trainerComments: 'Measured', measurements: [{ id: id(2), loadKg: 25, reps: 8, sets: 3 }] })
})

it('freezes an unknown outcome and reconciles the original measured values without another write', async () => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'Lost') }), get: vi.fn(async () => saved()) }
  const service = sessionOutcomeCommands(http, actor)
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const pending = service.pendingInput(0)
  expect(pending.outcome.exerciseResults[0].loadKg).toBe(25)
  await expect(service.save({ ...input(), outcome: { ...input().outcome, trainerComments: 'Different' } }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect((await service.review({ id: id(1), expectedVersion: 3 }, 0)).uncertain).toBe(true)
  expect(await service.save(pending, 0)).toEqual(saved())
  expect(http.post).toHaveBeenCalledTimes(1)
})

it('blank load removes a measurement while zero remains a real measured value', async () => {
  let result = { ...saved(), rows: [{ ...row(), resultId: id(3) }] }
  const http = { post: vi.fn(async () => result) }, service = sessionOutcomeCommands(http, actor)
  const value = input(); value.outcome.exerciseResults[0].loadKg = ''
  await service.save(value, 0)
  expect(http.post.mock.calls[0][1].measurements).toEqual([])
  value.outcome.exerciseResults[0].loadKg = '0'
  result = { ...saved(), rows: [{ ...saved().rows[0], loadKg: 0 }] }
  await service.save(value, 0)
  expect(http.post.mock.calls[1][1].measurements[0].loadKg).toBe(0)
})

it('rejects stale review, foreign rows and unverified result identities', async () => {
  const service = sessionOutcomeCommands({ get: async () => reviewed(), post: async () => ({ ...saved(), rows: [{ ...saved().rows[0], resultId: null }] }) }, actor)
  await expect(service.review({ id: id(1), expectedVersion: 1 }, 0)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  const bad = input(); bad.outcome.exerciseResults[0].id = id(9)
  await expect(service.save(bad, 0)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('client progress uses the configured profile read and rejects repeated or private response data', async () => {
  const exercise = { id: id(2), name: 'Squat', points: [{ id: id(2), sessionId: id(1), packageId: id(4), date: '2026-10-01', load: 25, reps: 8, sets: 3 }] }
  let value = { clientId: id(5), exercises: [exercise] }
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : value))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect(await services.readClientProgress({ id: id(5) })).toEqual([exercise])
  value = { ...value, healthNotes: 'private' }
  await expect(readClientProgress({ get: async () => value }, actor, { id: id(5) }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  value = { clientId: id(5), exercises: [exercise, { ...exercise, id: id(8) }] }
  await expect(readClientProgress({ get: async () => value }, actor, { id: id(5) }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
