import { expect, it, vi } from 'vitest'
import { sessionChangeCommands } from './apiSessionChanges.js'
import { ApiError } from './apiClient.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'

const position = () => ({ id: id(1), version: 2, sessionNumber: 1, scheduleState: 'booked', date: '2026-10-24', startsAt: '10:00', endsAt: '11:00', trainerId: id(2), slotId: id(3) })
const review = (kind, outcome = 'requested') => ({ kind, outcome, id: id(1), version: 2, clientId: id(4), clientVersion: 1, purchaseId: id(5), purchaseVersion: 1, expected: 'a'.repeat(64), session: position(), trainers: [{ id: id(2), version: 1, name: 'Trainer' }, { id: id(8), version: 1, name: 'Replacement' }] })
const input = (kind, outcome) => ({ sessionId: id(1), kind, reviewed: review(kind, outcome), patch: kind === 'time' ? { date: '2026-10-24', from: '12:00', to: '13:00' } : { replacementTrainerId: id(8) } })
const result = (kind, outcome = 'requested') => ({ kind, outcome, session: outcome === 'requested' ? position() : { ...position(), version: 3, ...(kind === 'time' ? { startsAt: '12:00', endsAt: '13:00' } : { trainerId: id(8) }) }, requestId: outcome === 'requested' ? id(6) : null, messageId: id(7) })
const trainer = async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 })

it.each(['time', 'trainer'])('configured services preserve the reviewed %s proposal and server outcome', async kind => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer', trainerId: id(2) } } : options.method === 'GET' ? review(kind) : result(kind)))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect((await services.reviewSessionChange({ id: id(1), kind, expectedVersion: 2 })).reviewed).toEqual(review(kind))
  const data = input(kind)
  expect(await services.sessionService[kind === 'time' ? 'requestTimeChange' : 'requestTrainerChange']({ sessionId: data.sessionId, reviewed: data.reviewed, ...(kind === 'time' ? { patch: data.patch } : data.patch) })).toEqual(result(kind))
  const [url, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(url).toContain(`/${kind}-change`)
  expect(JSON.parse(options.body)).toEqual(kind === 'time' ? { expected: 'a'.repeat(64), date: '2026-10-24', startsAt: '12:00', endsAt: '13:00' } : { expected: 'a'.repeat(64), trainerId: id(8) })
  expect(options.headers['Idempotency-Key']).toEqual(expect.any(String))
})

it.each(['time', 'trainer'])('lost %s response retains original intent and recovers without another write', async kind => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'response lost') }), get: vi.fn(async () => result(kind, 'applied')) }
  const command = sessionChangeCommands(http, trainer), data = input(kind, 'applied')
  await expect(command.save(data, 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await command.review({ id: id(1), kind, expectedVersion: 2 }, 0)).toEqual({ reviewed: data.reviewed, draft: data.patch, uncertain: true })
  await expect(command.review({ id: id(1), kind: kind === 'time' ? 'trainer' : 'time', expectedVersion: 2 }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await command.save(data, 0)).toEqual(result(kind, 'applied'))
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(command.pendingInput(0)).toBeNull()
})

it('does not project a command in flight as recovery and drops it across login generations', async () => {
  let reject, generation = 0
  const command = sessionChangeCommands({ post: () => new Promise((_, fail) => { reject = fail }), get: async () => review('time') }, async () => ({ user: { role: 'trainer' }, sessionGeneration: generation }))
  const saving = command.save(input('time'), 0)
  await vi.waitFor(() => expect(reject).toEqual(expect.any(Function)))
  expect(command.pendingInput(0)).toBeNull()
  reject(new ApiError('NETWORK_ERROR', 'lost'))
  await expect(saving).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  generation = 1
  expect((await command.review({ id: id(1), kind: 'time', expectedVersion: 2 }, 1)).uncertain).toBe(false)
})

it('rejects malformed or leaked review fields and unexpected state transitions', async () => {
  let viewed = { ...review('time'), healthNotes: 'private' }
  const command = sessionChangeCommands({ get: async () => viewed, post: async () => result('time', 'applied') }, trainer)
  await expect(command.review({ id: id(1), kind: 'time', expectedVersion: 2 }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  viewed = review('time')
  await expect(command.review({ id: id(1), kind: 'time', expectedVersion: 1 }, 0)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  await expect(command.save(input('time'), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(command.pendingInput(0)).toEqual(input('time'))
})

it.each(['owner', 'admin'])('blocks %s impersonation before sending domain requests', async role => {
  const http = { get: vi.fn(), post: vi.fn() }
  const command = sessionChangeCommands(http, async () => ({ user: { role }, sessionGeneration: 0 }))
  await expect(command.review({ id: id(1), kind: 'time', expectedVersion: 2 }, 0)).rejects.toMatchObject({ status: 403 })
  await expect(command.save(input('time'), 0)).rejects.toMatchObject({ status: 403 })
  expect(http.get).not.toHaveBeenCalled(); expect(http.post).not.toHaveBeenCalled()
})
