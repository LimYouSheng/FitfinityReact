import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'
import { packageService } from './packageService.js'
import { clientService } from './clientService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { signatureFixture } from '../test/fixtures/signature.js'

const signature = { method: 'signature', signerName: 'Amanda Lim', signature: signatureFixture }
const client = () => mockDb.read().clients.find(item => item.id === 'c1')
const points = () => client().strengthProgress.flatMap(item => item.points).filter(point => point.sessionId === 's1')
beforeEach(() => {
  localStorage.clear(); mockDb.reset()
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-01T15:59:59Z'))
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('rejects future signature, no-show and WhatsApp calls without changing sessions, credits or messages', async () => {
  const before = mockDb.read()
  await expect(sessionService.acknowledge('s1', signature)).rejects.toThrow('training date')
  await expect(sessionService.acknowledge('s1', { method: 'late_no_show' })).rejects.toThrow('training date')
  await expect(sessionService.markWhatsAppOpened('s1')).rejects.toThrow('training date')
  expect(mockDb.read()).toEqual(before)
})

it('unlocks on the gym calendar date, using its timezone independently of the session start time', async () => {
  vi.setSystemTime(new Date('2026-09-01T16:00:00Z'))
  mockDb.mutate(db => { db.settings.timeZone = 'UTC' })
  await expect(sessionService.markWhatsAppOpened('s1')).rejects.toThrow('training date')
  mockDb.mutate(db => { db.settings.timeZone = 'Asia/Singapore' })
  await sessionService.markWhatsAppOpened('s1')
  await sessionService.acknowledge('s1', signature)
  expect(mockDb.read().sessions.find(item => item.id === 's1')).toMatchObject({ status: 'completed', whatsappOpenCount: 1 })
})

it('updates progress from a signed numeric plan, remains idempotent and corrects measured loads', async () => {
  vi.setSystemTime(new Date('2026-09-02T02:00:00Z'))
  await sessionService.saveExercisePlan('s1', [
    { id: 'squat', name: 'Test Squat', weight: '27.5 kg', reps: '8', rounds: '3' },
    { id: 'unknown', name: 'Test Carry', weight: 'light', reps: '8', rounds: '3' },
  ])
  await sessionService.acknowledge('s1', signature)
  await sessionService.acknowledge('s1', signature)
  mockDb.reload()
  expect(points()).toHaveLength(1)
  expect(points()[0]).toMatchObject({ load: 27.5, reps: 8, sets: 3 })
  await sessionService.saveOutcome('s1', { durationMinutes: 55, exerciseResults: [{ id: 'squat', name: 'Test Squat', loadKg: 30, reps: 6, sets: 2 }] })
  expect(points()).toHaveLength(1)
  expect(points()[0]).toMatchObject({ load: 30, reps: 6, sets: 2 })
  expect(mockDb.read().packageCreditTransactions.filter(item => item.sessionId === 's1')).toHaveLength(1)
})

it('uses recorded results before planned loads and removes no-show progress without another debit', async () => {
  vi.setSystemTime(new Date('2026-09-02T02:00:00Z'))
  await sessionService.saveExercisePlan('s1', [{ id: 'row', name: 'Test Row', weight: '50 kg', reps: '8', rounds: '3' }])
  await sessionService.saveOutcome('s1', { durationMinutes: 55, exerciseResults: [{ id: 'row', name: 'Test Row', loadKg: 35, reps: 8, sets: 2 }] })
  await sessionService.acknowledge('s1', signature)
  expect(points()[0].load).toBe(35)
  await sessionService.acknowledge('s1', { method: 'late_no_show' })
  expect(points()).toEqual([])
  await sessionService.acknowledge('s1', signature)
  expect(points()).toHaveLength(1)
  expect(points()[0].load).toBe(35)
  expect(mockDb.read().packageCreditTransactions.filter(item => item.sessionId === 's1')).toHaveLength(1)
})

it('rebuilds older signed sessions in the snapshot without duplicating previously derived points', async () => {
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-owner', expiresAt: Date.now() + 3600000 }))
  mockDb.mutate(db => {
    const session = db.sessions.find(item => item.id === 's1')
    Object.assign(session, { status: 'completed', acknowledgement: signature, exercisePlan: [{ id: 'legacy', name: 'Legacy Row', weight: '40 kg', reps: '8', rounds: '3' }] })
    const person = db.clients.find(item => item.id === 'c1')
    delete person.progressBaseline
    person.strengthProgress = [{ id: 'legacy-row', name: 'Legacy Row', points: [{ id: 'old', sessionId: 's1', date: session.date, load: 40 }] }]
  })
  const before = mockDb.read()
  for (let i = 0; i < 2; i++) {
    const snapshot = await mockPortalAdapter.load()
    expect(snapshot.data.clients.find(item => item.id === 'c1').strengthProgress[0].points).toHaveLength(1)
  }
  expect(mockDb.read()).toEqual(before)
})

it('accepts arbitrary whole session counts and keeps each created client package and schedule consistent', async () => {
  const owner = mockDb.read().users.find(user => user.role === 'owner')
  for (const total of [1, 18, 365]) {
    const definition = await packageService.save({ draft: { name: `Custom ${total}`, total: String(total) } }, owner)
    expect(definition).toMatchObject({ total, validityDays: Math.ceil(total * 90 / 12) })
    const created = await clientService.create({
      type: 'Individual', people: [{ name: `Custom ${total} client` }], startDate: '2026-09-07', trainerId: 't1',
      sessionsPerWeek: 1, packageId: definition.id, packageVersion: definition.version,
      clientPreferences: [{ days: ['Monday'], from: '18:00', to: '19:00' }],
      fixedWeeklySchedule: [{ day: 'Monday', from: '18:00', to: '19:00' }],
    })
    const sessions = mockDb.read().sessions.filter(item => item.clientId === created.id)
    expect(sessions).toHaveLength(total)
    expect(sessions.every(item => item.date <= created.package.endDate)).toBe(true)
  }
})

it('rejects blank, fractional, signed, exponential and out-of-range package counts atomically', async () => {
  const owner = mockDb.read().users.find(user => user.role === 'owner'), before = mockDb.read()
  for (const total of ['', ' ', 0, -1, 366, 1.5, '12.0', '1e2', '+12', 'abc', null, true]) {
    await expect(packageService.save({ draft: { name: 'Invalid count', total } }, owner)).rejects.toThrow('whole number')
  }
  expect(mockDb.read()).toEqual(before)
})


it('records report actions with the authenticated staff and service timestamp, scoped to the client', async () => {
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-marcus', expiresAt: Date.now() + 3600000 }))
  const owner = mockDb.read().users.find(user => user.role === 'owner')
  const event = await mockPortalAdapter.invoke('clientService', 'recordProgressReportAction', ['c1', { id: 'report-one', kind: 'csv_export', at: '2000-01-01', by: owner }, owner])
  expect(event).toEqual({ id: 'report-one', clientId: 'c1', kind: 'csv_export', at: '2026-09-01T15:59:59.000Z', by: { id: 'u-marcus', name: 'Marcus Tan' } })
  vi.setSystemTime(new Date('2026-09-03T04:00:00Z'))
  await clientService.recordProgressReportAction('c1', { id: 'report-two', kind: 'whatsapp_opened' }, owner)
  await clientService.recordProgressReportAction('c2', { id: 'report-other', kind: 'csv_export' }, owner)
  mockDb.reload()
  const rows = await clientService.progressReportHistory('c1', owner)
  expect(rows.map(row => row.id)).toEqual(['report-two', 'report-one'])
  expect(rows[1]).toEqual(event)
})

it('retries the same action without duplicate history or messages and rejects ID reuse', async () => {
  const owner = mockDb.read().users.find(user => user.role === 'owner')
  const action = { id: 'report-repeat', kind: 'csv_export' }
  await clientService.recordProgressReportAction('c1', action, owner)
  const before = mockDb.read()
  vi.setSystemTime(new Date('2026-09-03T04:00:00Z'))
  await clientService.recordProgressReportAction('c1', action, owner)
  expect(mockDb.read()).toEqual(before)
  await expect(clientService.recordProgressReportAction('c1', { ...action, kind: 'whatsapp_opened' }, owner)).rejects.toThrow('already been used')
  expect(mockDb.read()).toEqual(before)
})

it('blocks report recording for another trainer or an unavailable client and validates action types', async () => {
  const db = mockDb.read(), owner = db.users.find(user => user.role === 'owner')
  const other = db.users.find(user => user.role === 'trainer' && user.trainerId !== 't1')
  await expect(clientService.recordProgressReportAction('c1', { id: 'report-unauthorized', kind: 'csv_export' }, other)).rejects.toThrow('unavailable')
  await expect(clientService.recordProgressReportAction('missing', { id: 'report-missing', kind: 'csv_export' }, owner)).rejects.toThrow('unavailable')
  for (const kind of ['sent', 'renewed', '__proto__']) {
    await expect(clientService.recordProgressReportAction('c1', { id: 'report-invalid', kind }, owner)).rejects.toThrow('valid progress report action')
  }
  expect(mockDb.read()).toEqual(db)
})

it('keeps report history and messages unchanged if storage fails and permits one successful retry', async () => {
  const owner = mockDb.read().users.find(user => user.role === 'owner'), before = mockDb.read()
  const action = { id: 'report-storage', kind: 'csv_export' }
  const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
  await expect(clientService.recordProgressReportAction('c1', action, owner)).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  storage.mockRestore()
  await clientService.recordProgressReportAction('c1', action, owner)
  expect((await clientService.progressReportHistory('c1', owner))).toHaveLength(1)
  expect(mockDb.read().messages.length).toBe(before.messages.length + 1)
})

it('exposes report history only through the owner operation and ignores a forged owner argument', async () => {
  const owner = mockDb.read().users.find(user => user.role === 'owner')
  await clientService.recordProgressReportAction('c1', { id: 'report-private', kind: 'csv_export' }, owner)
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-marcus', expiresAt: Date.now() + 3600000 }))
  await expect(mockPortalAdapter.invoke('clientService', 'progressReportHistory', ['c1', owner])).rejects.toThrow('owner')
  expect((await mockPortalAdapter.load()).data).not.toHaveProperty('progressReportEvents')
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-owner', expiresAt: Date.now() + 3600000 }))
  expect(await mockPortalAdapter.invoke('clientService', 'progressReportHistory', ['c1'])).toHaveLength(1)
})

it('does not invent report activity from legacy renewal records or expose another client history', async () => {
  const owner = mockDb.read().users.find(user => user.role === 'owner')
  mockDb.mutate(db => { db.clients.find(item => item.id === 'c1').renewalTracking = { status: 'progress_report_sent', history: [{ at: '2026-09-01T04:00:00Z' }] } })
  expect(await clientService.progressReportHistory('c1', owner)).toEqual([])
  await clientService.recordProgressReportAction('c2', { id: 'report-other-client', kind: 'csv_export' }, owner)
  expect(await clientService.progressReportHistory('c1', owner)).toEqual([])
  expect(mockDb.read().clients.find(item => item.id === 'c1').renewalTracking.status).toBe('progress_report_sent')
})
