import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { expect, it, vi } from 'vitest'
import { ApiError } from './apiClient.js'
import { sessionBookingCommands } from './apiSessionBooking.js'
import { directoryId as id } from '../test/directory.js'

const position = () => ({ id: id(1), version: 2, sessionNumber: 1, scheduleState: 'booked', date: '2026-10-24', startsAt: '10:00', endsAt: '11:00', trainerId: id(2), slotId: id(3) })
const review = () => ({ id: id(1), version: 2, clientId: id(4), clientVersion: 1, purchaseId: id(5), purchaseVersion: 1, expected: 'a'.repeat(64), session: position(), trainers: [{ id: id(2), version: 1, name: 'Trainer' }] })
const input = () => ({ sessionId: id(1), reviewed: review(), patch: { date: '2026-10-24', from: '12:00', to: '13:00', trainerId: id(2) } })
const result = () => { const session = { ...position(), version: 3, startsAt: '12:00', endsAt: '13:00' }; return { session, client: { id: id(4), version: 2 }, purchase: { id: id(5), version: 2 }, positions: [session], messageId: id(6) } }
const sessionFor = async () => ({ user: { role: 'owner' }, sessionGeneration: 0 })

it('sends only reviewed booking values with an idempotency key and session generation', async () => {
  const http = { get: vi.fn(async () => review()), post: vi.fn(async () => result()) }
  const command = sessionBookingCommands(http, sessionFor)
  expect((await command.review({ id: id(1), expectedVersion: 2 }, 0)).reviewed).toEqual(review())
  expect(await command.save(input(), 0)).toEqual(result())
  expect(http.post).toHaveBeenCalledWith(`/api/sessions/${id(1)}/booking`, { expected: 'a'.repeat(64), date: '2026-10-24', startsAt: '12:00', endsAt: '13:00', trainerId: id(2) }, { csrf: true, idempotencyKey: expect.any(String), expectedGeneration: 0 })
})

it('reads the original receipt after response loss without another write', async () => {
  const http = { get: vi.fn(async () => result()), post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'offline') }) }
  const command = sessionBookingCommands(http, sessionFor)
  await expect(command.save(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await command.review({ id: id(1), expectedVersion: 2 }, 0)).toEqual({ reviewed: review(), draft: input().patch, uncertain: true })
  await expect(command.save({ ...input(), patch: { ...input().patch, from: '12:15' } }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await command.save(input(), 0)).toEqual(result())
  expect(http.post).toHaveBeenCalledTimes(1)
})

it('reuses the original key only after an absent receipt and explicit retry', async () => {
  const http = { get: vi.fn(async () => { throw new ApiError('not_found', 'missing', 404) }), post: vi.fn().mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 'offline')).mockResolvedValue(result()) }
  const command = sessionBookingCommands(http, sessionFor)
  await expect(command.save(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await command.save(input(), 0)).toEqual(result())
  expect(http.post.mock.calls[0]).toEqual(http.post.mock.calls[1])
})

it('rejects foreign, private and malformed reviews and stale versions', async () => {
  let value = review()
  const command = sessionBookingCommands({ get: async () => value }, sessionFor)
  await expect(command.review({ id: id(1), expectedVersion: 1 }, 0)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  for (const change of [v => { v.id = id(90) }, v => { v.healthNotes = 'private' }, v => { v.session.date = '2026-02-30' }]) {
    value = review(); change(value)
    await expect(command.review({ id: id(1), expectedVersion: 2 }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  }
})

it('blocks Trainer writes and reviews before domain requests', async () => {
  const http = { get: vi.fn(), post: vi.fn() }
  const command = sessionBookingCommands(http, async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 }))
  await expect(command.review({ id: id(1), expectedVersion: 2 }, 0)).rejects.toMatchObject({ status: 403 })
  await expect(command.save(input(), 0)).rejects.toMatchObject({ status: 403 })
  expect(http.get).not.toHaveBeenCalled(); expect(http.post).not.toHaveBeenCalled()
})

it('keeps a malformed successful response uncertain until its receipt can be checked', async () => {
  const http = { post: async () => ({ ...result(), session: { ...result().session, trainerId: id(90) } }) }
  const command = sessionBookingCommands(http, sessionFor)
  await expect(command.save(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect((await command.review({ id: id(1), expectedVersion: 2 }, 0)).uncertain).toBe(true)
})

it('configured services expose the reviewed booking command through the application boundary', async () => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? sessionInfo() : options.method === 'GET' ? review() : result()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect((await services.reviewSessionBooking({ id: id(1), expectedVersion: 2 })).reviewed).toEqual(review())
  expect(await services.sessionService.updateDetails(input())).toEqual(result())
  const post = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(post[1].headers['X-CSRF-Token']).toBe(sessionInfo().csrfToken)
})
