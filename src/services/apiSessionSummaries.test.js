import { expect, it, vi } from 'vitest'
import { sessionSummaryCommands } from './apiSessionSummaries.js'
import { ApiError } from './apiClient.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'

const reviewed = () => ({ sessionId: id(1), version: 2, expected: 'a'.repeat(64), summary: 'Before' })
const input = () => ({ sessionId: id(1), reviewed: reviewed(), summary: ' Reviewed summary ' })
const saved = () => ({ sessionId: id(1), version: 3, summary: 'Reviewed summary', savedAt: '2026-10-24T08:00:00Z' })
const actor = async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 })

it.each(['owner', 'admin', 'trainer'])('configured %s reviews and saves summary text through the API', async role => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role, ...(role === 'trainer' ? { trainerId: id(9) } : {}) } } : options.method === 'GET' ? reviewed() : saved()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect((await services.reviewSessionSummary({ id: id(1), expectedVersion: 2 })).draft).toBe('Before')
  expect(await services.sessionService.saveClientSummary(input())).toEqual(saved())
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ expected: 'a'.repeat(64), summary: 'Reviewed summary' })
})

it('retains an interrupted summary and recovers the original receipt without a second write', async () => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'Lost') }), get: vi.fn(async () => saved()) }
  const service = sessionSummaryCommands(http, actor)
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(service.save({ ...input(), summary: 'Replacement' }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect((await service.review({ id: id(1), expectedVersion: 3 }, 0)).draft).toBe('Reviewed summary')
  expect(await service.save(service.pendingInput(0), 0)).toEqual(saved())
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(service.pendingInput(0)).toBeNull()
})

it('rejects stale reviews, blank text and changed response identity or text', async () => {
  let result = { ...saved(), sessionId: id(9) }
  const service = sessionSummaryCommands({ get: async () => reviewed(), post: async () => result }, actor)
  await expect(service.review({ id: id(1), expectedVersion: 1 }, 0)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  await expect(service.save({ ...input(), summary: '  ' }, 0)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(service.save(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  result = { ...saved(), summary: 'Unexpected' }
  const other = sessionSummaryCommands({ post: async () => result }, actor)
  await expect(other.save(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
