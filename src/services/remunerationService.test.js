import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { remunerationService } from './remunerationService.js'
import { remunerationDraft } from '../app/remuneration.js'
import { payFixture } from '../test/fixtures/remuneration.js'
const owner = { id: 'owner', role: 'owner' }, trainer = { id: 'trainer', role: 'trainer', trainerId: 't1' }
const revision = () => remunerationDraft(mockDb.read(), '2026-09', 't1').revision
const finish = async promise => { await vi.runAllTimersAsync(); return promise }
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-09-16T01:00:00Z')); mockDb.write(payFixture()) })
afterEach(() => { vi.useRealTimers(); mockDb.reset() })
it('requires stored active owners to approve and scopes trainer detail and list reads', async () => {
  const previous = mockDb.read()
  for (const actor of [trainer, { id: 'trainer', role: 'owner' }, { id: 'unknown', role: 'owner' }]) {
    const result = remunerationService.approve('2026-09', 't1', revision(), actor).catch(error => error)
    expect(await finish(result)).toBeInstanceOf(Error)
  }
  expect(() => remunerationService.detail('2026-09', 't2', trainer)).toThrow('another trainer')
  expect(remunerationService.list(trainer).flatMap(cycle => cycle.trainers).every(record => record.trainerId === 't1')).toBe(true)
  expect(mockDb.read()).toEqual(previous)
})
it('calculates automatic rates without mutating sessions, credits or creating manual rate records', async () => {
  const before = mockDb.read()
  const detail = remunerationService.detail('2026-09', 't1', owner)
  expect(detail).toMatchObject({ amountCents: 8000, reviewCount: 0 })
  expect(mockDb.read()).toEqual(before)
  await finish(remunerationService.approve('2026-09', 't1', detail.revision, owner))
  const after = mockDb.read()
  expect(after.remunerationEntries).toBeUndefined()
  expect(after.sessions).toEqual(before.sessions)
  expect(after.clients).toEqual(before.clients)
})
it('rejects stale preset rates and invalid current rates atomically', async () => {
  const stale = revision()
  mockDb.mutate(db => { db.trainers[0].rates.peak = 95 })
  let before = mockDb.read()
  expect(await finish(remunerationService.approve('2026-09', 't1', stale, owner).catch(error => error))).toBeInstanceOf(Error)
  expect(mockDb.read()).toEqual(before)
  mockDb.mutate(db => { delete db.trainers[0].rates.peak })
  before = mockDb.read()
  expect(await finish(remunerationService.approve('2026-09', 't1', revision(), owner).catch(error => error))).toBeInstanceOf(Error)
  expect(mockDb.read()).toEqual(before)
})
it('blocks approval until the cycle closes and required session evidence is complete', async () => {
  mockDb.mutate(db => { delete db.sessions[0].acknowledgement })
  expect(await finish(remunerationService.approve('2026-09', 't1', revision(), owner).catch(error => error))).toBeInstanceOf(Error)
  mockDb.write(payFixture())
  vi.setSystemTime(new Date('2026-09-15T15:59:00Z'))
  expect(await finish(remunerationService.approve('2026-09', 't1', revision(), owner).catch(error => error))).toBeInstanceOf(Error)
  expect(mockDb.read().remunerationApprovals).toBeUndefined()
})
it('approves once, stores the reviewed breakdown and sends separate owner and trainer notifications', async () => {
  mockDb.write(payFixture())
  const expected = revision()
  await finish(remunerationService.approve('2026-09', 't1', expected, owner))
  const db = mockDb.read()
  expect(db.remunerationApprovals).toHaveLength(1)
  expect(db.remunerationApprovals[0]).toMatchObject({ amountCents: 8000, sessions: 1, approvedBy: 'owner' })
  expect(db.messages).toHaveLength(2)
  expect(db.messages.map(message => message.status)).toEqual(['approved', 'approved'])
  expect(db.messages[1]).toMatchObject({ trainerId: 't1', recipientTrainerId: 't1', remunerationCycle: '2026-09', read: false })
  expect(await finish(remunerationService.approve('2026-09', 't1', expected, owner).catch(error => error))).toBeInstanceOf(Error)
  expect(mockDb.read()).toEqual(db)
})
it('rejects changed evidence between opening and approving and leaves no approval or receipt', async () => {
  mockDb.write(payFixture())
  const expected = revision()
  mockDb.mutate(db => { db.sessions[0].acknowledgement.signerName = 'Another signer' })
  const before = mockDb.read()
  expect(await finish(remunerationService.approve('2026-09', 't1', expected, owner).catch(error => error))).toBeInstanceOf(Error)
  expect(mockDb.read()).toEqual(before)
})
