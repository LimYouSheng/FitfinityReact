import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as database from './mockDb.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { clientReactivationReview, clientReactivationSnapshot } from '../app/clientReactivation.js'
import { sessionBookingConflict } from '../app/bookingAvailability.js'

const { mockDb } = database
const api = createPortalServices(mockPortalAdapter)
const client = () => mockDb.read().clients.find(item => item.id === 'c1')
const expected = () => clientReactivationSnapshot(client(), mockDb.read().sessions, mockDb.read().packageCreditTransactions)
const signIn = userId => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId, expiresAt: Date.now() + 3600000 }))
const unchanged = before => { expect(mockDb.read()).toEqual(before); expect(mockDb.reload()).toEqual(before) }
const review = dates => clientReactivationReview(mockDb.read(), client(), dates)
beforeEach(() => {
  localStorage.clear()
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
  mockDb.reset(); vi.spyOn(database, 'delay').mockResolvedValue()
  signIn('u-owner')
  mockDb.mutate(db => {
    db.users.push({ id: 'test-admin', role: 'admin', status: 'active', name: 'Admin' })
    db.sessions = [
      { id: 'restore-a', clientId: 'c1', trainerId: 't1', packageId: db.clients.find(c => c.id === 'c1').package.id,
        date: '2026-09-10', from: '10:00', to: '11:00', status: 'not_planned', sessionNumber: 1 },
      { id: 'restore-b', clientId: 'c1', trainerId: 't1', packageId: db.clients.find(c => c.id === 'c1').package.id,
        date: '2026-09-11', from: '10:00', to: '11:00', status: 'planned', sessionNumber: 2 },
      { id: 'occupied', clientId: 'c2', trainerId: 't2', packageId: db.clients.find(c => c.id === 'c2').package.id,
        date: '2026-09-10', from: '12:00', to: '13:00', status: 'planned', sessionNumber: 1 },
    ]
    db.packageCreditTransactions = []
  })
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); localStorage.clear() })
async function conflict() {
  await api.clientService.deactivate({ id: 'c1' })
  await api.sessionService.updateDetails({ sessionId: 'occupied', patch: { date: '2026-09-10', from: '10:00', to: '11:00', trainerId: 't1' } })
}
it('blocks reactivation atomically when another client took the inactive slot', async () => {
  await conflict()
  const before = mockDb.read()
  expect(review().conflicts.map(row => row.session.id)).toEqual(['restore-a'])
  await expect(api.clientService.reactivate({ id: 'c1' })).rejects.toThrow('Resolve all')
  unchanged(before)
})
it.each(['u-owner', 'test-admin'])('%s can reschedule conflicts without changing trainer, time or original purchase', async userId => {
  await conflict(); signIn(userId)
  const before = mockDb.read(), original = before.sessions[0]
  await api.clientService.reactivate({ id: 'c1', dates: { 'restore-a': '2027-01-01' }, expected: expected() })
  const db = mockDb.reload(), moved = db.sessions[0]
  expect(client().status).toBe('active'); expect(client().package.status).toBe('active')
  expect(moved).toMatchObject({ trainerId: original.trainerId, packageId: original.packageId, from: original.from, to: original.to, date: '2027-01-01' })
  expect(moved.reactivationDateHistory[0]).toMatchObject({ fromDate: original.date, toDate: '2027-01-01', by: { id: userId } })
  expect(db.sessions.slice(1)).toEqual(before.sessions.slice(1))
  expect(sessionBookingConflict(db, moved)).toBeUndefined()
})
it('checks proposed dates against each other as one batch and rejects client overlap across trainers', async () => {
  await conflict()
  mockDb.mutate(db => { db.sessions.find(s => s.id === 'restore-b').trainerId = 't2' })
  const before = mockDb.read(), dates = { 'restore-a': '2026-09-12', 'restore-b': '2026-09-12' }
  expect(review(dates).conflicts.map(row => row.session.id)).toEqual(['restore-a', 'restore-b'])
  await expect(api.clientService.reactivate({ id: 'c1', dates, expected: expected() })).rejects.toThrow('client')
  unchanged(before)
})
it('reviews retained past unfinished sessions and completed no-shows still occupy their full intervals', async () => {
  await conflict()
  mockDb.mutate(db => {
    db.sessions[0].date = '2026-09-01'
    Object.assign(db.sessions[2], { date: '2026-09-01', status: 'completed', acknowledgement: { method: 'late_no_show' } })
    db.clients.find(c => c.id === 'c2').status = 'inactive'
  })
  const before = mockDb.read()
  await expect(api.clientService.reactivate({ id: 'c1' })).rejects.toThrow('conflict')
  unchanged(before)
})
it('restores conflict-free sessions unchanged while manual inactive purchases and cancelled sessions remain untouched', async () => {
  mockDb.mutate(db => {
    const c = db.clients.find(item => item.id === 'c1')
    c.packageHistory = [{ ...c.package, id: 'manual-purchase', status: 'inactive', deactivationReason: 'package', deactivatedAt: '2026-09-01T00:00:00Z' }]
    db.sessions.push({ ...db.sessions[0], id: 'manual-session', packageId: 'manual-purchase' },
      { ...db.sessions[0], id: 'cancelled', status: 'cancelled' })
  })
  await api.clientService.deactivate({ id: 'c1' })
  const before = mockDb.read()
  await api.clientService.reactivate({ id: 'c1' })
  expect(mockDb.reload().sessions).toEqual(before.sessions)
  expect(client().packageHistory.find(p => p.id === 'manual-purchase').status).toBe('inactive')
})
it.each(['2026-02-31', '2026-13-01', '2026-09-00', 'bad', '', null])('rejects invalid replacement date %s with complete rollback', async date => {
  await conflict(); const before = mockDb.read()
  await expect(api.clientService.reactivate({ id: 'c1', dates: { 'restore-a': date }, expected: expected() })).rejects.toThrow('valid date')
  unchanged(before)
})
it.each(['unknown', 'occupied'])('rejects a replacement date for an ineligible session %s', async id => {
  await conflict(); const before = mockDb.read()
  await expect(api.clientService.reactivate({ id: 'c1', dates: { [id]: '2026-09-12' }, expected: expected() })).rejects.toThrow('eligible')
  unchanged(before)
})
it('requires reviewed scheduling evidence for date moves and refuses stale review data', async () => {
  await conflict(); const old = expected()
  mockDb.mutate(db => { db.sessions[0].from = '09:30' })
  const before = mockDb.read()
  for (const snapshot of [undefined, old]) {
    await expect(api.clientService.reactivate({ id: 'c1', dates: { 'restore-a': '2026-09-12' }, expected: snapshot })).rejects.toThrow('changed')
    unchanged(before)
  }
})
it('rechecks competing bookings at commit even when the reviewed client sessions have not changed', async () => {
  await conflict(); const snapshot = expected()
  let release, entered
  const waiting = new Promise(resolve => { entered = resolve })
  database.delay.mockImplementationOnce(() => new Promise(resolve => { release = resolve; entered() }))
  const pending = api.clientService.reactivate({ id: 'c1', dates: { 'restore-a': '2026-09-12' }, expected: snapshot })
  await waiting
  mockDb.mutate(db => { db.sessions[2].date = '2026-09-12' })
  const before = mockDb.read(); release()
  await expect(pending).rejects.toThrow('conflict'); unchanged(before)
})
it('blocks restoration with an inactive trainer and locks acknowledged records against date changes', async () => {
  await conflict()
  mockDb.mutate(db => { db.trainers.find(t => t.id === 't1').status = 'inactive' })
  const before = mockDb.read()
  await expect(api.clientService.reactivate({ id: 'c1' })).rejects.toThrow('assigned trainer'); unchanged(before)
  mockDb.mutate(db => { db.trainers.find(t => t.id === 't1').status = 'active'; db.sessions[0].acknowledgement = { method: 'late_no_show' } })
  const acknowledged = mockDb.read()
  await expect(api.clientService.reactivate({ id: 'c1', dates: { 'restore-a': '2026-09-12' }, expected: expected() })).rejects.toThrow('Acknowledged')
  unchanged(acknowledged)
})
