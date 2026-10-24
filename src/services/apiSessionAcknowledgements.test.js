import { expect, it, vi } from 'vitest'
import { sessionAcknowledgementCommands } from './apiSessionAcknowledgements.js'
import { ApiError } from './apiClient.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'

const reviewed = () => ({ sessionId: id(1), version: 2, expected: 'a'.repeat(64), previousMethod: null, used: 0, total: 12 })
const input = () => ({ sessionId: id(1), reviewed: reviewed(), acknowledgement: { method: 'late_no_show', note: 'Absent' } })
const saved = () => ({ sessionId: id(1), version: 3, acknowledgementId: id(8), method: 'late_no_show', sequence: 1, used: 1, savedAt: '2026-10-24T08:00:00Z' })
const actor = async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 })

it.each(['owner', 'admin', 'trainer'])('configured %s reviews and completes a session through the API', async role => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role, ...(role === 'trainer' ? { trainerId: id(9) } : {}) } } : options.method === 'GET' ? reviewed() : saved()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect((await services.reviewSessionAcknowledgement({ id: id(1), expectedVersion: 2 })).reviewed).toEqual(reviewed())
  expect(await services.sessionService.acknowledge(input())).toEqual(saved())
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ expected: 'a'.repeat(64), method: 'late_no_show', note: 'Absent' })
})

it('recovers an interrupted completion without a second write or changed signature', async () => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'Lost') }), get: vi.fn(async () => saved()) }
  const service = sessionAcknowledgementCommands(http, actor)
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(service.save({ ...input(), acknowledgement: { method: 'late_no_show', note: 'Changed' } }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect((await service.review({ id: id(1), expectedVersion: 3 }, 0)).draft.note).toBe('Absent')
  expect(await service.save(service.pendingInput(0), 0)).toEqual(saved())
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(service.pendingInput(0)).toBeNull()
})

it('rejects stale reviews, invalid signatures and incorrect credit effects', async () => {
  const service = sessionAcknowledgementCommands({ get: async () => reviewed(), post: async () => ({ ...saved(), used: 2 }) }, actor)
  await expect(service.review({ id: id(1), expectedVersion: 1 }, 0)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  await expect(service.save({ ...input(), acknowledgement: { method: 'signature', signerName: 'Client', signature: [], note: '' } }, 0)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
