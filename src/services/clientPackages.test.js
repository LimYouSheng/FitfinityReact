import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { clientService } from './clientService.js'
import { sessionService } from './sessionService.js'
import { trainerService } from './trainerService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { progressForPackage } from '../app/clientPackages.js'
import { updateClientProgress } from '../app/progress.js'
import { remunerationDraft } from '../app/remuneration.js'
import { signatureFixture } from '../test/fixtures/signature.js'
import { pastClientPackages } from '../app/clientPackages.js'
import { packageDraftForClient } from '../app/packageRenewal.js'
import { requestService } from './requestService.js'

const owner = () => mockDb.read().users.find(item => item.role === 'owner')
const client = () => mockDb.read().clients.find(item => item.id === 'c1')
const draft = (patch = {}) => ({ ...packageDraftForClient(client(), mockDb.read().sessions, mockDb.read().packages, '2027-01-04'), requestId: 'renew-test', expectedPackageId: client().package.id,
  expectedTrainerId: client().trainerId, expectedSchedule: client().fixedWeeklySchedule,
  packageId: 'package-12', packageVersion: 1, startDate: '2027-01-04', sessionsPerWeek: 1,
  genderPreference: 'No gender preference', ...patch })
const renew = request => clientService.renewPackage('c1', request ?? draft(), owner())
beforeEach(() => { localStorage.clear(); mockDb.reset(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2027-05-01T04:00:00Z')) })
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('renews atomically without creating a client, overwriting a package or colliding session IDs', async () => {
  const before = mockDb.read(), original = client()
  const result = await renew()
  const after = mockDb.reload()
  expect(after.clients).toHaveLength(before.clients.length)
  expect(result.package).toMatchObject({ total: 12, used: 0, startDate: '2027-01-04', validityDays: 90 })
  expect(result.packageHistory[0]).toEqual(original.package)
  expect(result.phone).toEqual(original.phone)
  expect(result.startDate).toBe(original.startDate)
  expect(result.trainerId).toBe(original.trainerId)
  expect(result.fixedWeeklySchedule).toEqual(original.fixedWeeklySchedule)
  expect(result.strengthProgress).toEqual(original.strengthProgress)
  expect(after.sessions.filter(item => item.packageId === result.package.id)).toHaveLength(12)
  expect(new Set(after.sessions.map(item => item.id)).size).toBe(after.sessions.length)
  expect(after.sessions.filter(item => before.sessions.some(old => old.id === item.id))).toEqual(before.sessions)
})

it('handles concurrent duplicate renewals once and rejects changed or stale requests', async () => {
  const request = draft(), before = mockDb.read()
  const [first, second] = await Promise.all([renew(request), renew(request)])
  expect(second).toEqual(first)
  const saved = mockDb.read()
  expect(saved.sessions.length).toBe(before.sessions.length + 12)
  await expect(renew({ ...request, startDate: '2027-02-01' })).rejects.toThrow('already been used')
  await expect(renew({ ...request, requestId: 'another' })).rejects.toThrow('changed')
  expect(mockDb.read()).toEqual(saved)
})

it('preserves all data if renewal persistence fails and permits a safe retry', async () => {
  const request = draft(), before = mockDb.read()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
  await expect(renew(request)).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  await renew(request)
  expect(client().packageHistory).toHaveLength(before.clients[0].packageHistory.length + 1)
})

it('validates package version, calendar date, cadence, trainer preference and schedule conflicts before writing', async () => {
  const before = mockDb.read()
  for (const change of [{ packageVersion: 0 }, { startDate: '2027-02-30' }, { sessionsPerWeek: 2.5 },
    { sessionsPerWeek: 2 }, { genderPreference: 'Female trainer preferred' }, { startDate: '2026-08-01' },
    { expectedTrainerId: 't2' }, { expectedSchedule: [] }]) {
    await expect(renew(draft(change))).rejects.toThrow()
    expect(mockDb.read()).toEqual(before)
  }
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'conflict', status: 'planned', date: '2027-01-04', from: '18:00', to: '19:00' }) })
  const conflict = mockDb.read()
  await expect(renew()).rejects.toThrow('conflicts')
  expect(mockDb.read()).toEqual(conflict)
})

it('keeps old-session progress and credit on the old package after renewal and reload', async () => {
  const previousId = client().package.id, previousUsed = client().package.used
  await sessionService.saveExercisePlan('s1', [{ id: 'row', name: 'Package Row', weight: '30 kg', reps: '8', rounds: '3' }])
  const result = await renew()
  await sessionService.acknowledge('s1', { method: 'signature', signerName: 'Amanda', signature: signatureFixture }, owner())
  mockDb.reload()
  expect(client().package.used).toBe(0)
  expect(client().packageHistory.find(item => item.id === previousId).used).toBe(previousUsed + 1)
  expect(progressForPackage(client(), result.package.id)).toEqual([])
  expect(progressForPackage(client(), previousId).find(item => item.name === 'Package Row').points).toMatchObject([{ sessionId: 's1', load: 30, packageId: previousId }])
  const nextSession = mockDb.read().sessions.find(item => item.packageId === result.package.id)
  await sessionService.saveExercisePlan(nextSession.id, [{ id: 'row', name: 'Package Row', weight: '40 kg', reps: '8', rounds: '3' }])
  await sessionService.acknowledge(nextSession.id, { method: 'signature', signerName: 'Amanda', signature: signatureFixture }, owner())
  expect(client().package.used).toBe(1)
  expect(progressForPackage(client(), result.package.id).find(item => item.name === 'Package Row').points).toMatchObject([{ sessionId: nextSession.id, load: 40 }])
  expect(mockDb.read().packageCreditTransactions.filter(item => ['s1', nextSession.id].includes(item.sessionId)).map(item => item.packageId)).toEqual([previousId, result.package.id])
})

it('preserves unresolved legacy measurements outside reports across renewal and repeated loads', async () => {
  const point = { id: 'legacy-unmatched', date: '2024-01-01', load: 17, packageId: null }
  mockDb.mutate(db => {
    const target = db.clients[0]
    target.strengthProgress.push({ id: 'old-row', name: 'Old Row', points: [point] })
    target.progressBaseline = structuredClone(target.strengthProgress)
  })
  const archived = mockDb.read().progressMigrationArchive
  expect(archived).toEqual([{ clientId: 'c1', exerciseId: 'old-row', exerciseName: 'Old Row', point }])
  expect(progressForPackage(client(), null)).toEqual([])
  await renew()
  mockDb.mutate(db => updateClientProgress(db, 'c1'))
  mockDb.reload()
  expect(mockDb.read().progressMigrationArchive).toEqual(archived)
  expect(progressForPackage(client(), null)).toEqual([])
  expect(progressForPackage(client(), client().package.id)).toEqual([])
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-owner', expiresAt: Date.now() + 3600000 }))
  expect((await mockPortalAdapter.load()).data).not.toHaveProperty('progressMigrationArchive')
})

it('repairs known seed sessions to their original purchase after renewal and resolves only reliable progress links', async () => {
  const originalId = client().package.id
  await renew()
  const db = mockDb.read(), target = db.clients[0], original = target.packageHistory.find(item => item.id === originalId)
  const session = db.sessions.find(item => item.id === 'history-c1-1')
  session.packageId = null
  session.exerciseResults = [{ id: 'legacy-result', name: 'Legacy Row', loadKg: 15, reps: 8, sets: 3 }]
  const credit = db.packageCreditTransactions.find(item => item.sessionId === session.id)
  delete credit.packageId
  target.additionalPackages = [{ id: 'overlap', startDate: '2026-08-01', endDate: '2026-10-01', status: 'inactive' }]
  const points = [
    { id: 'by-session', sessionId: session.id, packageId: null, date: session.date, load: 15 },
    { id: 'by-date', packageId: null, date: '2026-03-15', load: 20 },
    { id: 'overlap', packageId: null, date: '2026-09-01', load: 25 },
    { id: 'foreign', packageId: 'other-client-package', date: '2026-03-15', load: 30 },
    { id: 'missing-session', sessionId: 'deleted-session', packageId: original.id, date: '2026-03-15', load: 35 },
  ]
  target.strengthProgress = [{ id: 'legacy-row', name: 'Legacy Row', points }]
  delete target.progressBaseline
  localStorage.setItem('fitfinity-m2-demo-db-v4', JSON.stringify(db))
  const migrated = mockDb.reload(), repaired = migrated.clients[0]
  expect(migrated.sessions.find(item => item.id === session.id)).toEqual({ ...session, packageId: original.id })
  expect(migrated.packageCreditTransactions.find(item => item.id === credit.id)).toEqual({ ...credit, packageId: original.id })
  expect(repaired.strengthProgress.find(item => item.name === 'Legacy Row').points).toEqual([
    { id: `result-${session.id}-legacy-result`, sessionId: session.id, packageId: original.id, date: session.date, load: 15, reps: 8, sets: 3 },
  ])
  expect(migrated.progressMigrationArchive.map(entry => entry.point.id)).toEqual(['by-date', 'overlap', 'foreign', 'missing-session'])
  expect(migrated.progressMigrationArchive.find(entry => entry.point.id === 'foreign').point).toEqual(points[3])
  expect(migrated.progressMigrationArchive.find(entry => entry.point.id === 'missing-session').point).toEqual(points[4])
  expect(repaired.package).toEqual(target.package)
  expect(repaired.packageHistory).toEqual(target.packageHistory)
  expect(mockDb.reload()).toEqual(migrated)
})

it('does not publish Progress cleanup when its storage write fails and retries without duplicate archives', () => {
  const before = mockDb.read(), legacy = structuredClone(before)
  legacy.clients[0].strengthProgress.push({ id: 'unknown', name: 'Unknown Row', points: [{ id: 'unknown-point', date: '2024-01-01', load: 11 }] })
  const raw = JSON.stringify(legacy)
  localStorage.setItem('fitfinity-m2-demo-db-v4', raw)
  const save = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Migration storage unavailable') })
  expect(() => mockDb.reload()).toThrow('Migration storage unavailable')
  expect(mockDb.read()).toEqual(before)
  expect(localStorage.getItem('fitfinity-m2-demo-db-v4')).toBe(raw)
  save.mockRestore()
  const repaired = mockDb.reload()
  expect(repaired.progressMigrationArchive).toHaveLength(1)
  expect(progressForPackage(repaired.clients[0], null)).toEqual([])
  expect(mockDb.reload()).toEqual(repaired)
})

it('records report actions per purchase and preserves package-scoped idempotency and owner-only history', async () => {
  const previousId = client().package.id
  await renew()
  const action = { id: 'old-export', kind: 'pdf_export', packageId: previousId }
  await clientService.recordProgressReportAction('c1', action, owner())
  await clientService.recordProgressReportAction('c1', { id: 'new-export', kind: 'pdf_export', packageId: client().package.id }, owner())
  expect((await clientService.progressReportHistory('c1', owner(), previousId)).map(item => item.id)).toEqual(['old-export'])
  await expect(clientService.recordProgressReportAction('c1', { ...action, packageId: client().package.id }, owner())).rejects.toThrow('already been used')
  await expect(clientService.recordProgressReportAction('c1', { ...action, id: 'foreign', packageId: 'client-package-c2' }, owner())).rejects.toThrow('package not found')
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-marcus', expiresAt: Date.now() + 3600000 }))
  await expect(mockPortalAdapter.invoke('clientService', 'progressReportHistory', ['c1', owner(), previousId])).rejects.toThrow('owner')
  await expect(mockPortalAdapter.invoke('clientService', 'renewPackage', ['c1', draft(), owner()])).rejects.toThrow('owner')
  for (const method of ['deactivate', 'deactivatePackage', 'deletePackageSessions']) await expect(mockPortalAdapter.invoke('clientService', method, ['c1', { packageId: client().package.id }, owner()])).rejects.toThrow('owner')
  await expect(mockPortalAdapter.invoke('clientService', 'update', ['c1', { status: 'inactive' }])).rejects.toThrow('owner')
})

it('keeps inactive sessions unchanged and rejects every session mutation through the authenticated adapter', async () => {
  const beforeSessions = mockDb.read().sessions
  await clientService.deactivate('c1', owner())
  expect(mockDb.read().sessions).toEqual(beforeSessions)
  const inactive = mockDb.read()
  const plan = [{ id: 'row', name: 'Row', weight: '10 kg', reps: '8', rounds: '3' }]
  for (const userId of ['u-owner', 'u-marcus']) {
    localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId, expiresAt: Date.now() + 3600000 }))
    for (const [method, args] of [
      ['saveExercisePlan', [plan]], ['copyPreviousPlan', []], ['saveOutcome', [{ durationMinutes: 50 }]],
      ['saveClientSummary', ['Changed']], ['markWhatsAppOpened', []], ['acknowledge', [{ method: 'late_no_show' }]],
      ['saveVideo', ['exercise-s1-1', new Blob(), {}]], ['removeVideo', ['exercise-s1-1']],
      ['updateDetails', [{ date: '2027-06-01', from: '10:00', to: '11:00', trainerId: 't1' }]],
      ['requestTimeChange', [owner(), { date: '2027-06-01', from: '10:00', to: '11:00' }]],
      ['requestTrainerChange', [owner(), 't2']],
    ]) await expect(mockPortalAdapter.invoke('sessionService', method, ['s1', ...args])).rejects.toThrow()
    await expect(mockPortalAdapter.invoke('clientService', 'update', ['c1', { remarks: 'Changed' }])).rejects.toThrow('inactive')
    await expect(mockPortalAdapter.invoke('clientService', 'saveFixedWeeklySchedule', ['c1', client().fixedWeeklySchedule])).rejects.toThrow('active')
    expect(mockDb.read()).toEqual(inactive)
    await expect(mockPortalAdapter.invoke('sessionService', 'previousPlanFor', ['s1'])).resolves.toBeInstanceOf(Array)
  }
  await expect(renew()).rejects.toThrow('inactive')
  await clientService.reactivate('c1', owner())
  await sessionService.saveClientSummary('s1', 'Changed')
  expect(client().package.status).toBe('active')
})

it('keeps inactive sessions immutable during trainer deactivation and retains completed pay', async () => {
  await clientService.deactivate('c1', owner())
  const before = mockDb.read(), inactiveSessions = before.sessions.filter(item => item.clientId === 'c1')
  const replacements = Object.fromEntries(before.sessions.filter(item => item.trainerId === 't1' && item.clientId !== 'c1' && !['completed', 'cancelled'].includes(item.status)).map(item => [item.id, 't2']))
  await trainerService.deactivate('t1', replacements)
  const after = mockDb.read()
  expect(after.sessions.filter(item => item.clientId === 'c1')).toEqual(inactiveSessions)
  const pay = remunerationDraft(after, '2026-09', 't1')
  expect(pay.rows.filter(item => item.clientId === 'c1').every(item => item.status === 'completed')).toBe(true)
  expect(pay.rows.some(item => item.clientId === 'c1' && item.billable)).toBe(true)
})

it('deactivates a package once with owner evidence, retains sessions by default and freezes only its own sessions', async () => {
  const oldId = client().package.id
  await renew()
  const newId = client().package.id, before = mockDb.read()
  await clientService.deactivatePackage('c1', { packageId: newId }, owner())
  const inactive = client().package, after = mockDb.read()
  expect(after.sessions).toEqual(before.sessions)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  expect(inactive).toMatchObject({ status: 'inactive', deactivatedAt: '2027-05-01T04:00:00.000Z', deactivatedBy: { id: owner().id, name: owner().name } })
  expect(pastClientPackages(client())[0]).toEqual(inactive)
  await clientService.deactivatePackage('c1', { packageId: newId }, owner())
  expect(mockDb.read()).toEqual(after)
  const frozen = before.sessions.find(item => item.packageId === newId)
  await expect(sessionService.saveClientSummary(frozen.id, 'Changed')).rejects.toThrow('Package inactive')
  await expect(sessionService.acknowledge(frozen.id, { method: 'late_no_show' }, owner())).rejects.toThrow('Package inactive')
  await sessionService.saveClientSummary('s1', 'Older active package remains editable')
  expect(client().packageHistory.find(item => item.id === oldId).status).not.toBe('inactive')
  await renew(draft({ requestId: 'corrected-renewal', startDate: '2026-11-16' }))
  expect(client().packageHistory[0]).toEqual(inactive)
})

it('hard-deletes only eligible future package sessions and preserves past, acknowledged, completed and credited evidence', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  const packageId = client().package.id
  mockDb.mutate(db => {
    const source = db.sessions.find(item => item.id === 's1')
    for (const [id, extra] of [
      ['future-completed', { status: 'completed' }],
      ['future-signed', { acknowledgement: { method: 'signature', signature: signatureFixture } }],
      ['future-log', { acknowledgementHistory: [{ method: 'late_no_show', recordedAt: '2026-09-01T00:00:00Z' }] }],
      ['future-credited', {}],
    ]) db.sessions.push({ ...source, id, date: '2026-09-30', ...extra })
    db.packageCreditTransactions.push({ id: 'protected-credit', sessionId: 'future-credited', type: 'session_debit', amount: -1 })
  })
  const before = mockDb.read()
  await clientService.deactivatePackage('c1', { packageId, deleteUpcomingSessions: true }, owner())
  const after = mockDb.reload(), deleted = client().package.deletedUpcomingSessions
  expect(deleted).toHaveLength(8)
  expect(after.sessions.some(item => deleted.includes(item.id))).toBe(false)
  expect(after.sessions).toEqual(before.sessions.filter(item => !deleted.includes(item.id)))
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  expect(client().package.used).toBe(before.clients[0].package.used)
  expect(after.sessions.filter(item => item.id.startsWith('future-'))).toHaveLength(4)
})

it('rolls back package deactivation and optional deletion if storage fails and rejects trainer or forged owner calls', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  const options = { packageId: client().package.id, deleteUpcomingSessions: true }, before = mockDb.read()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
  await expect(clientService.deactivatePackage('c1', options, owner())).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-marcus', expiresAt: Date.now() + 3600000 }))
  await expect(mockPortalAdapter.invoke('clientService', 'deactivatePackage', ['c1', options, owner()])).rejects.toThrow('owner')
  await expect(clientService.deactivatePackage('c1', options, { ...owner(), id: 'u-marcus' })).rejects.toThrow('active staff')
  expect(mockDb.read()).toEqual(before)
})

it('blocks approval of a pending change after its package is deactivated', async () => {
  vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
  const trainer = mockDb.read().users.find(item => item.trainerId === 't1')
  await sessionService.requestTimeChange('s1', trainer, { date: '2026-09-03', from: '19:00', to: '20:00' })
  const request = mockDb.read().messages.findLast(item => item.request?.sessionId === 's1')
  await clientService.deactivatePackage('c1', { packageId: client().package.id }, owner())
  const before = mockDb.read()
  await expect(requestService.resolve(request.id, 'approved', owner())).rejects.toThrow('eligible')
  expect(mockDb.read()).toEqual(before)
  await requestService.resolve(request.id, 'rejected', owner())
})

it('automatically freezes every package with the client and allows owner-only timestamped cleanup later', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  const before = mockDb.read()
  await clientService.deactivate('c1', owner())
  expect(mockDb.read().sessions).toEqual(before.sessions)
  expect(pastClientPackages(client()).every(item => item.status === 'inactive')).toBe(true)
  const inactive = mockDb.read(), packageId = client().package.id
  const trainer = inactive.users.find(item => item.role === 'trainer')
  await expect(clientService.deletePackageSessions('c1', { packageId }, trainer)).rejects.toThrow('owner')
  await expect(clientService.deactivate('c2', trainer)).rejects.toThrow('owner')
  expect(mockDb.read()).toEqual(inactive)
  const result = await clientService.deletePackageSessions('c1', { packageId }, owner())
  const audit = result.package.sessionDeletionHistory[0]
  expect(audit).toMatchObject({ at: new Date().toISOString(), by: { id: owner().id, name: owner().name } })
  expect(audit.sessionIds.length).toBeGreaterThan(0)
  expect(result.status).toBe('inactive')
  expect(mockDb.read().sessions.filter(item => item.clientId !== 'c1' || item.status === 'completed' || item.date < '2026-09-09'))
    .toEqual(before.sessions.filter(item => item.clientId !== 'c1' || item.status === 'completed' || item.date < '2026-09-09'))
  await clientService.deletePackageSessions('c1', { packageId }, owner())
  expect(client().package.sessionDeletionHistory).toEqual([audit])
  await clientService.reactivate('c1', owner())
  expect(client().package.status).toBe('active')
  expect(client().package.sessionDeletionHistory).toEqual([audit])
  expect(mockDb.read().sessions.some(session => audit.sessionIds.includes(session.id))).toBe(false)
})

it('prefills current settings and applies a reviewed new trainer and schedule only to the added purchase', async () => {
  const initial = draft(), before = mockDb.read()
  expect(initial).toMatchObject({ trainerId: client().trainerId, fixedWeeklySchedule: client().fixedWeeklySchedule,
    sessionsPerWeek: client().package.sessionsPerWeek, genderPreference: client().genderPreference })
  const trainer = before.trainers.find(item => item.id !== client().trainerId && item.status === 'active' && item.availability.Monday?.length)
  const [from, to] = trainer.availability.Monday[0]
  const schedule = [{ id: 'replacement-slot', day: 'Monday', from, to }]
  const preferences = [{ id: 'replacement-preference', days: ['Monday'], from, to }]
  const result = await renew({ ...initial, trainerId: trainer.id, fixedWeeklySchedule: schedule, clientPreferences: preferences })
  expect(result).toMatchObject({ trainerId: trainer.id, fixedWeeklySchedule: schedule, clientPreferences: preferences })
  expect(result.phone).toEqual(client().phone)
  expect(result.package).toMatchObject({ trainerId: trainer.id, fixedWeeklySchedule: schedule })
  expect(mockDb.read().sessions.filter(item => item.packageId === result.package.id)).toHaveLength(12)
  expect(mockDb.read().sessions.filter(item => item.packageId === result.package.id).every(item => item.trainerId === trainer.id && item.from === from && item.to === to)).toBe(true)
  expect(mockDb.read().sessions.filter(item => before.sessions.some(old => old.id === item.id))).toEqual(before.sessions)
})

it('rejects tampered or unavailable trainer schedules atomically before adding a purchase', async () => {
  const before = mockDb.read()
  for (const patch of [{ status: 'inactive' }, { package: { status: 'inactive' } }, { trainerId: 't2' }, { fixedWeeklySchedule: [] }]) {
    await expect(clientService.update('c1', patch)).rejects.toThrow('dedicated')
    expect(mockDb.read()).toEqual(before)
  }
  for (const patch of [{ trainerId: 'missing' }, { clientPreferences: [] },
    { fixedWeeklySchedule: [{ id: 'invalid', day: 'Monday', from: '23:00', to: '23:30' }] },
    { fixedWeeklySchedule: [{ id: 'invalid', day: 'Monday', from: '20:00', to: '19:00' }] }]) {
    await expect(renew(draft(patch))).rejects.toThrow()
    expect(mockDb.read()).toEqual(before)
  }
})

it('prefills legacy package terms without silently selecting an unrelated or ambiguous template', () => {
  const db = mockDb.read(), source = db.clients.find(item => item.package.total === 24)
  const make = (client = source, packages = db.packages) => packageDraftForClient(client, db.sessions, packages, '2026-09-09')
  const matching = db.packages.find(item => item.total === source.package.total)
  expect(make()).toMatchObject({ packageId: matching.id, sessionsPerWeek: source.package.sessionsPerWeek,
    trainerId: source.trainerId, fixedWeeklySchedule: source.fixedWeeklySchedule })
  expect(make(source, db.packages.filter(item => item.id !== matching.id)).packageId).toBe('')
  expect(make(source, [...db.packages, { ...matching, id: 'ambiguous' }]).packageId).toBe('')
  expect(make(source, [...db.packages, { ...matching, id: 'exact-terms', validityDays: source.package.validityDays }]).packageId).toBe('exact-terms')
  expect(make({ ...source, package: { ...source.package, templateId: 'retired-template' } }).packageId).toBe('')
  expect(make({ ...source, package: { ...source.package, templateId: matching.id } }, [...db.packages, { ...matching, id: 'ambiguous' }]).packageId).toBe(matching.id)
  expect(make(source, db.packages.map(item => item.id === matching.id ? { ...item, status: 'inactive' } : item)).packageId).toBe('')
  vi.stubGlobal('crypto', {})
  try {
    const first = make(), second = make()
    expect(first.requestId).toMatch(/^[a-zA-Z0-9_-]{1,120}$/)
    expect(second.requestId).not.toBe(first.requestId)
  } finally { vi.unstubAllGlobals() }
})

it('queues future purchases without replacing current terms, progress, trainer or preferences', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  const before = mockDb.read(), original = client()
  const result = await renew()
  expect(result.package).toEqual(original.package)
  expect(result.packageHistory).toEqual(original.packageHistory)
  for (const key of ['trainerId', 'fixedWeeklySchedule', 'clientPreferences', 'genderPreference', 'strengthProgress']) expect(result[key]).toEqual(original[key])
  expect(result.additionalPackages).toHaveLength(1)
  expect(result.additionalPackages[0]).toMatchObject({ startDate: '2027-01-04', used: 0, trainerId: original.trainerId })
  const newSessions = mockDb.read().sessions.filter(session => session.packageId === result.additionalPackages[0].id)
  expect(newSessions).toHaveLength(12)
  expect(mockDb.read().sessions.filter(session => before.sessions.some(old => old.id === session.id))).toEqual(before.sessions)
  expect(mockDb.reload().clients.find(item => item.id === 'c1')).toEqual(result)
})

it('rejects inclusive package overlap even without session conflicts and queues multiple distinct purchases', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  const initial = client(), before = mockDb.read()
  await expect(renew(draft({ startDate: initial.package.endDate, minimumStartDate: undefined }))).rejects.toThrow('last day')
  expect(mockDb.read()).toEqual(before)
  const first = await renew(), existing = first.additionalPackages[0]
  const saved = mockDb.read()
  await expect(renew(draft({ requestId: 'overlap', startDate: existing.endDate }))).rejects.toThrow('last day')
  expect(mockDb.read()).toEqual(saved)
  const nextDraft = packageDraftForClient(client(), saved.sessions, saved.packages, '2026-09-09')
  expect(nextDraft.startDate > existing.endDate).toBe(true)
  const result = await renew({ ...nextDraft, requestId: 'second-purchase', packageVersion: 1 })
  expect(result.package).toEqual(initial.package)
  expect(result.additionalPackages).toHaveLength(2)
  expect(result.additionalPackages[1].startDate > existing.endDate).toBe(true)
  expect(new Set(mockDb.read().sessions.map(item => item.id)).size).toBe(mockDb.read().sessions.length)
})

it('promotes a due additional package once and preserves both trainers historical access', async () => {
  const { visibleClientsForUser } = await import('../app/status.js')
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  const original = client(), trainer = mockDb.read().trainers.find(item => item.id !== original.trainerId && item.status === 'active' && item.availability.Monday?.length)
  const [from, to] = trainer.availability.Monday[0]
  await renew(draft({ trainerId: trainer.id, clientPreferences: [{ id: 'next', days: ['Monday'], from, to }], fixedWeeklySchedule: [{ id: 'next', day: 'Monday', from, to }] }))
  const queued = client().additionalPackages[0]
  vi.setSystemTime(new Date('2027-01-03T15:59:00Z'))
  mockDb.reload()
  expect(client().package).toEqual(original.package)
  vi.setSystemTime(new Date('2027-01-03T16:00:00Z'))
  const db = mockDb.reload()
  expect(client().package.id).toBe(queued.id)
  expect(client().packageHistory[0]).toEqual(original.package)
  expect(client().trainerId).toBe(trainer.id)
  expect(client().fixedWeeklySchedule).toEqual(queued.fixedWeeklySchedule)
  expect(client().additionalPackages).toEqual([])
  for (const trainerId of [original.trainerId, trainer.id]) expect(visibleClientsForUser({ role: 'trainer', trainerId }, db.clients, db.sessions).some(item => item.id === 'c1')).toBe(true)
  expect(mockDb.reload()).toEqual(db)
})

it('reactivation restores automatically frozen sessions while preserving separate deactivation and deletion evidence', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  await renew()
  const futureId = client().additionalPackages[0].id
  await clientService.deactivatePackage('c1', { packageId: futureId, deleteUpcomingSessions: true }, owner())
  const future = structuredClone(client().additionalPackages[0])
  await clientService.deactivate('c1', owner())
  const sessions = mockDb.read().sessions
  await clientService.reactivate('c1', owner())
  expect(client().package.status).toBe('active')
  expect(client().additionalPackages[0]).toEqual(future)
  expect(client().package.statusHistory.map(item => item.reason)).toEqual(['client', 'client_reactivated'])
  expect(mockDb.read().sessions).toEqual(sessions)
  const { sessionIsInactive } = await import('../app/clientPackages.js')
  expect(sessions.filter(item => item.clientId === 'c1' && item.packageId === client().package.id).every(item => !sessionIsInactive(client(), item))).toBe(true)
  vi.setSystemTime(new Date('2027-01-05T04:00:00Z'))
  mockDb.reload()
  expect(client().package.id).not.toBe(futureId)
})

it('repairs identifiable legacy reactivations without enabling separately deactivated packages', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  const db = mockDb.read(), target = db.clients[0], at = '2026-09-08T04:00:00.000Z'
  Object.assign(target.package, { status: 'inactive', deactivatedAt: at, deactivatedBy: owner() })
  Object.assign(target.packageHistory[0], { status: 'inactive', deactivatedAt: '2026-09-01T04:00:00.000Z' })
  db.messages.push({ id: 'client-off-legacy', clientId: target.id, kind: 'client_status', createdAt: at },
    { id: 'client-on-legacy', clientId: target.id, kind: 'client_status', createdAt: '2026-09-08T05:00:00.000Z' })
  localStorage.setItem('fitfinity-m2-demo-db-v4', JSON.stringify(db))
  mockDb.reload()
  expect(client().package.status).toBe('active')
  expect(client().package.statusHistory.at(-1)).toMatchObject({ reason: 'client_reactivated', at: '2026-09-08T05:00:00.000Z' })
  expect(client().packageHistory[0].status).toBe('inactive')
  expect(mockDb.reload().clients[0]).toEqual(client())
})

it('migrates the earlier future-package replacement by saved purchase and trainer identities', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  await renew()
  const db = mockDb.read(), target = db.clients[0], original = structuredClone(target.package)
  target.packageHistory.unshift(target.package)
  target.package = target.additionalPackages[0]
  target.additionalPackages = []
  target.trainerId = 't2'
  delete target.packageHistory[0].trainerId
  delete target.packageHistory[0].fixedWeeklySchedule
  localStorage.setItem('fitfinity-m2-demo-db-v4', JSON.stringify(db))
  mockDb.reload()
  expect(client().package.id).toBe(original.id)
  expect(client().trainerId).toBe(original.trainerId)
  expect(client().additionalPackages[0].id).toBe(target.package.id)
  expect(mockDb.read().sessions).toEqual(db.sessions)
})

it('keeps client visibility from saved session assignment even when current assignment changes and client is inactive', async () => {
  const { visibleClientsForUser } = await import('../app/status.js')
  const db = mockDb.read(), target = db.clients[0]
  target.trainerId = 't2'; target.package.trainerId = 't2'; target.status = 'inactive'
  target.packageHistory = []
  expect(visibleClientsForUser({ role: 'trainer', trainerId: 't1' }, [target], db.sessions)).toEqual([target])
  expect(visibleClientsForUser({ role: 'trainer', trainerId: 'unassigned' }, [target], db.sessions)).toEqual([])
})

it('renames clients and trainer accounts without changing IDs, bookings or historical signatures and enforces ownership', async () => {
  const before = mockDb.read()
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-owner', expiresAt: Date.now() + 3600000 }))
  await mockPortalAdapter.invoke('clientService', 'update', ['c1', { name: ' Amanda Updated ' }])
  await mockPortalAdapter.invoke('trainerService', 'update', ['t1', { name: ' Marcus Updated ' }])
  expect(client().name).toBe('Amanda Updated')
  expect(mockDb.read().trainers.find(item => item.id === 't1').name).toBe('Marcus Updated')
  expect(mockDb.read().users.find(item => item.id === 'u-marcus').name).toBe('Marcus Updated')
  expect(mockDb.read().sessions).toEqual(before.sessions)
  for (const [domain, id] of [['clientService', 'c1'], ['trainerService', 't1']]) await expect(mockPortalAdapter.invoke(domain, 'update', [id, { name: ' ' }])).rejects.toThrow('name')
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-marcus', expiresAt: Date.now() + 3600000 }))
  await expect(mockPortalAdapter.invoke('clientService', 'update', ['c1', { name: 'Changed' }])).rejects.toThrow('owner')
  await expect(mockPortalAdapter.invoke('trainerService', 'update', ['t1', { name: 'Changed' }])).rejects.toThrow('owner')
  expect((await mockPortalAdapter.load()).user.name).toBe('Marcus Updated')
})

it('keeps reactivation atomic when storage fails and includes actionable package handling in deactivation Messages', async () => {
  await clientService.deactivate('c1', owner())
  const before = mockDb.read()
  const message = before.messages.findLast(item => item.clientId === 'c1' && item.recipientRole === 'owner')
  expect(message.body).toContain('Package tab')
  expect(message.body).toContain('deleted sessions cannot be restored')
  vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
  await expect(clientService.reactivate('c1', owner())).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  await clientService.reactivate('c1', owner())
  expect(client().package.status).toBe('active')
  await expect(clientService.reactivate('c1', before.users.find(item => item.role === 'trainer'))).rejects.toThrow('owner')
})

it('changes current weekly times without altering a separately scheduled additional package', async () => {
  vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  mockDb.mutate(db => { db.sessions = db.sessions.filter(item => item.clientId === 'c1') })
  await renew()
  const before = mockDb.read(), futureId = client().additionalPackages[0].id
  const slots = client().fixedWeeklySchedule.map(item => ({ ...item, from: '19:00', to: '20:15' }))
  await clientService.saveFixedWeeklySchedule('c1', slots, owner())
  expect(mockDb.read().sessions.filter(item => item.packageId === futureId)).toEqual(before.sessions.filter(item => item.packageId === futureId))
  expect(client().additionalPackages).toEqual(before.clients[0].additionalPackages)
  expect(mockDb.read().sessions.filter(item => item.packageId === client().package.id && item.date > '2026-09-09' && item.status !== 'completed').every(item => item.from === '19:00' && item.to === '20:15')).toBe(true)
})

it('defaults Add Package to the first saved weekly slot after all active purchases and today', () => {
  const db = mockDb.read(), source = client()
  const make = (input, today = '2026-09-09') => packageDraftForClient(input, db.sessions, db.packages, today)
  expect(make(source)).toMatchObject({ minimumStartDate: '2026-11-15', startDate: '2026-11-16' })
  const twice = { ...source, fixedWeeklySchedule: [{ id: 'wed', day: 'Wednesday', from: '18:00', to: '19:00' }, { id: 'sat', day: 'Saturday', from: '10:00', to: '11:00' }] }
  expect(make(twice).startDate).toBe('2026-11-18')
  expect(make(twice, '2027-01-02').startDate).toBe('2027-01-02')
  const queued = { ...source, additionalPackages: [{ ...source.package, id: 'next', endDate: '2027-02-01' }] }
  expect(make(queued)).toMatchObject({ minimumStartDate: '2027-02-02', startDate: '2027-02-08' })
  expect(make({ ...queued, additionalPackages: [{ ...queued.additionalPackages[0], status: 'inactive' }] }).startDate).toBe('2026-11-16')
})
