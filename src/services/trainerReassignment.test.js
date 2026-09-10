import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { clientService } from './clientService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { businessClock } from '../app/clock.js'
import { trainerReassignmentSnapshot } from '../app/trainerReassignment.js'
import { visibleClientsForUser } from '../app/status.js'
import { DAYS } from '../app/availability.js'

const owner = () => mockDb.read().users.find(item => item.role === 'owner')
const target = () => mockDb.read().clients.find(item => item.id === 'c1')
const request = patch => {
  const db = mockDb.read()
  return { requestId: 'permanent-reassign', trainerId: 't2',
    expected: trainerReassignmentSnapshot(target(), db.sessions, db.packageCreditTransactions, businessClock(new Date(), db.settings.timeZone)), ...patch }
}
const reassign = draft => clientService.reassignTrainer('c1', draft ?? request(), owner())
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  localStorage.clear(); mockDb.reset()
  mockDb.mutate(db => {
    db.sessions = db.sessions.filter(item => item.clientId === 'c1')
    const client = db.clients[0], sample = db.sessions.find(item => item.status === 'planned') ?? db.sessions[0]
    db.trainers.find(item => item.id === 't2').availability = Object.fromEntries(DAYS.map(day => [day, [['06:00', '23:00']]]))
    client.additionalPackages = [{ ...client.package, id: 'queued', startDate: '2027-01-04', endDate: '2027-04-03', used: 0, trainerId: 't1', fixedWeeklySchedule: structuredClone(client.fixedWeeklySchedule) }]
    db.sessions.push({ ...sample, id: 'queued-session', date: '2027-01-04', packageId: 'queued', acknowledgement: null, acknowledgementHistory: [], status: 'planned' })
    client.packageHistory[0].status = 'inactive'
    db.sessions.push({ ...sample, id: 'frozen-session', date: '2026-12-01', packageId: client.packageHistory[0].id, status: 'planned' })
  })
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('permanently changes active assignments and eligible sessions while preserving completed, started, signed, credited and inactive records', async () => {
  mockDb.mutate(db => {
    const sample = db.sessions.find(item => item.id === 'queued-session')
    db.sessions.push({ ...sample, id: 'already-started', date: '2026-09-09', from: '11:00', to: '12:00' },
      { ...sample, id: 'signed-future', acknowledgement: { method: 'signature', signature: 'retained-evidence' } },
      { ...sample, id: 'credited-future' })
    db.packageCreditTransactions.push({ id: 'kept-credit', sessionId: 'credited-future', packageId: 'queued', amount: -1 })
  })
  const draft = request(), before = mockDb.read(), original = target()
  expect(draft.expected.sessions.length).toBeGreaterThan(1)
  const result = await reassign(draft), after = mockDb.reload()
  expect(result.trainerId).toBe('t2')
  expect(result.package).toEqual({ ...original.package, trainerId: 't2' })
  expect(result.additionalPackages[0]).toEqual({ ...original.additionalPackages[0], trainerId: 't2' })
  expect(result.packageHistory).toEqual(original.packageHistory)
  expect(result.fixedWeeklySchedule).toEqual(original.fixedWeeklySchedule)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  const changed = new Set(draft.expected.sessions.map(item => item.id))
  for (const session of before.sessions) expect(after.sessions.find(item => item.id === session.id)).toEqual(changed.has(session.id)
    ? { ...session, trainerId: 't2', detailsUpdatedAt: new Date().toISOString() } : session)
  expect(result.trainerAssignmentHistory[0]).toMatchObject({ from: { id: 't1' }, to: { id: 't2' }, at: new Date().toISOString(), by: { id: owner().id } })
})

it('requires the authenticated owner and rejects inactive clients, inactive trainers, unchanged trainers and missing request IDs without writes', async () => {
  const before = mockDb.read(), trainer = before.users.find(item => item.role === 'trainer')
  await expect(clientService.reassignTrainer('c1', request(), trainer)).rejects.toThrow('owner')
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: trainer.id, expiresAt: Date.now() + 3600000 }))
  await expect(mockPortalAdapter.invoke('clientService', 'reassignTrainer', ['c1', request(), owner()])).rejects.toThrow('owner')
  for (const patch of [{ trainerId: 't1' }, { trainerId: 'missing' }, { requestId: '' }]) await expect(reassign(request(patch))).rejects.toThrow()
  expect(mockDb.read()).toEqual(before)
  mockDb.mutate(db => { db.trainers.find(item => item.id === 't2').status = 'inactive' })
  await expect(reassign()).rejects.toThrow('active trainer')
  mockDb.mutate(db => { db.clients[0].status = 'inactive' })
  await expect(reassign()).rejects.toThrow('Client inactive')
})

it('checks saved preferences, weekly availability and actual rescheduled session times', async () => {
  mockDb.mutate(db => { db.clients[0].genderPreference = 'Male trainer preferred'; db.trainers.find(item => item.id === 't2').gender = 'Female' })
  await expect(reassign()).rejects.toThrow('preference')
  mockDb.mutate(db => { db.clients[0].genderPreference = 'No gender preference'; db.trainers.find(item => item.id === 't2').availability.Monday = [] })
  await expect(reassign()).rejects.toThrow('weekly schedule')
  mockDb.mutate(db => { db.trainers.find(item => item.id === 't2').availability.Monday = [['06:00', '23:00']]; db.sessions.find(item => item.id === 'queued-session').from = '05:00' })
  const before = mockDb.read()
  await expect(reassign()).rejects.toThrow('unavailable on 2027-01-04')
  expect(mockDb.read()).toEqual(before)
})

it('rejects stale reviews when a booking or package changes or a session starts before confirmation', async () => {
  let draft = request()
  mockDb.mutate(db => { db.sessions.find(item => item.id === 'queued-session').to = '20:00' })
  await expect(reassign(draft)).rejects.toThrow('changed')
  draft = request()
  mockDb.mutate(db => { db.clients[0].additionalPackages[0].trainerId = 't3' })
  await expect(reassign(draft)).rejects.toThrow('changed')
  mockDb.mutate(db => { Object.assign(db.sessions.find(item => item.id === 'queued-session'), { date: '2026-09-09', from: '12:01', to: '13:00' }) })
  draft = request()
  vi.setSystemTime(new Date('2026-09-09T04:02:00Z'))
  const before = mockDb.read()
  await expect(reassign(draft)).rejects.toThrow('changed')
  expect(mockDb.read()).toEqual(before)
})

it('rejects conflicts atomically and leaves assignments, messages and audit untouched', async () => {
  mockDb.mutate(db => {
    const sample = db.sessions.find(item => item.id === 'queued-session')
    db.sessions.push({ ...sample, id: 'other-client-booking', clientId: 'c2', trainerId: 't2' })
  })
  const before = mockDb.read()
  await expect(reassign()).rejects.toThrow('booking conflict')
  expect(mockDb.read()).toEqual(before)
})

it('retries idempotently, records both trainers and the owner once, and rolls back a storage failure', async () => {
  const draft = request(), before = mockDb.read()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
  await expect(reassign(draft)).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  const [first, second] = await Promise.all([reassign(draft), reassign(draft)])
  expect(second).toEqual(first)
  expect(second.trainerAssignmentHistory).toHaveLength(1)
  const messages = mockDb.read().messages.filter(item => item.id.startsWith('reassignment-'))
  expect(messages).toHaveLength(3)
  expect(messages.map(item => item.recipientRole ?? item.recipientTrainerId).sort()).toEqual(['owner', 't1', 't2'])
  await expect(reassign({ ...draft, trainerId: 't3' })).rejects.toThrow('already been used')
})

it('supersedes only affected pending requests and receipts with the owner and timestamp', async () => {
  mockDb.mutate(db => {
    db.messages.push({ id: 'pending-session', status: 'pending', request: { type: 'session_time', sessionId: 'queued-session' } },
      { id: 'pending-receipt', status: 'pending', requestId: 'pending-session' },
      { id: 'pending-schedule', status: 'pending', request: { type: 'fixed_weekly_schedule', clientId: 'c1' } },
      { id: 'unrelated', status: 'pending', request: { type: 'trainer_availability', trainerId: 't1' } },
      { id: 'approved', status: 'approved', request: { type: 'session_time', sessionId: 'queued-session' } })
  })
  await reassign()
  const messages = mockDb.read().messages
  for (const id of ['pending-session', 'pending-receipt', 'pending-schedule']) expect(messages.find(item => item.id === id)).toMatchObject({ status: 'rejected', decidedBy: owner().id, decidedAt: new Date().toISOString(), decisionReason: 'Superseded by permanent trainer reassignment.' })
  expect(messages.find(item => item.id === 'unrelated').status).toBe('pending')
  expect(messages.find(item => item.id === 'approved').status).toBe('approved')
})

it('keeps the new assignment when a queued package activates and retains historical trainer visibility without edit rights', async () => {
  await reassign()
  vi.setSystemTime(new Date('2027-01-04T04:00:00Z'))
  const db = mockDb.reload()
  expect(target().package.id).toBe('queued')
  expect(target().trainerId).toBe('t2')
  expect(target().package.trainerId).toBe('t2')
  for (const trainerId of ['t1', 't2']) expect(visibleClientsForUser({ role: 'trainer', trainerId }, db.clients, db.sessions).some(item => item.id === 'c1')).toBe(true)
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-marcus', expiresAt: Date.now() + 3600000 }))
  await expect(mockPortalAdapter.invoke('clientService', 'update', ['c1', { notes: 'Former trainer edit' }])).rejects.toThrow('unavailable')
})
