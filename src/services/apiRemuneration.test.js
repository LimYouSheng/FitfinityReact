import { expect, it, vi } from 'vitest'
import { remunerationCommands } from './apiRemuneration.js'
import { ApiError } from './apiClient.js'
import { directoryId as id } from '../test/directory.js'

const cycle = { key: '2026-09', start: '2026-08-16', end: '2026-09-15', payout: '2026-09-16' }
const record = () => ({ cycle, trainerId: id(1), trainerName: 'Trainer One', rows: [], sessions: 0, totalSessions: 0, minutes: 0, amountCents: 0, reviewCount: 0, closed: true, status: 'No sessions', revision: 'a'.repeat(64), approvedAt: null, approvedBy: null, changed: false, current: null })
const actor = role => async () => ({ user: { role, trainerId: id(1) }, sessionGeneration: 0 })
const input = () => ({ cycle: cycle.key, trainerId: id(1), revision: 'a'.repeat(64) })
const result = () => ({ id: id(2), trainerId: id(1), cycle: cycle.key, revision: 'a'.repeat(64), approvedAt: '2026-10-24T09:00:00Z' })

it.each(['owner', 'trainer'])('reads verified %s remuneration without financial recomputation', async role => {
  const views = [{ key: cycle.key, cycle, isCurrent: false, trainers: [record()] }]
  const http = { get: vi.fn(async path => path === '/api/remuneration' ? views : record()) }
  const commands = remunerationCommands(http, actor(role))
  expect(await commands.list(0)).toEqual(views)
  expect(await commands.detail(input(), 0)).toEqual(record())
})
it('rejects financial inconsistencies, foreign scope and Admin access', async () => {
  let value = record()
  const http = { get: vi.fn(async () => value) }
  const commands = remunerationCommands(http, actor('trainer'))
  value = { ...record(), amountCents: 5500 }
  await expect(commands.detail(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  value = { ...record(), trainerId: id(3) }
  await expect(commands.detail(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(commands.detail({ ...input(), trainerId: id(3) }, 0)).rejects.toMatchObject({ status: 404 })
  const admin = remunerationCommands(http, actor('admin'))
  await expect(admin.list(0)).rejects.toMatchObject({ status: 403 })
  await expect(admin.approve(input(), 0)).rejects.toMatchObject({ status: 403 })
})
it('recovers original approval without repeating the write or accepting a changed review', async () => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'Lost response') }), get: vi.fn(async () => result()) }
  const commands = remunerationCommands(http, actor('owner'))
  await expect(commands.approve(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(commands.pendingInput(0)).toEqual(input())
  await expect(commands.approve({ ...input(), revision: 'b'.repeat(64) }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await commands.approve(input(), 0)).toEqual(result())
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(commands.pendingInput(0)).toBeNull()
})
it('rejects wrong approval receipts and malformed review identities', async () => {
  let response = { ...result(), trainerId: id(3) }
  const commands = remunerationCommands({ post: async () => response, get: async () => response }, actor('owner'))
  await expect(commands.approve(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  response = { ...result(), approvedAt: 2026 }
  await expect(commands.approve(input(), 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(commands.detail({ ...input(), cycle: '../other' }, 0)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
})
