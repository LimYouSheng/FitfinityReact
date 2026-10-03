import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as database from './mockDb.js'
import * as media from './exerciseVideoStore.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { signatureFixture } from '../test/fixtures/signature.js'
import { hasSessionDebit } from '../app/sessionRules.js'
import { flushExerciseVideoDeletions } from './exerciseVideoRetention.js'

const { mockDb } = database
const api = createPortalServices(mockPortalAdapter)
const baseTime = Date.parse('2026-10-03T01:00:00Z')
const day = 86400000
const signed = { method: 'signature', signerName: 'Amanda', signature: signatureFixture }
const login = (id = 'u-owner') => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: id, expiresAt: Date.now() + 30 * day }))
const session = (id = 's1') => mockDb.read().sessions.find(item => item.id === id)
const client = () => mockDb.read().clients.find(item => item.id === 'c1')
const latestMessage = () => mockDb.read().messages.findLast(item => item.mutationId)
const undo = message => api.messageService.undo({ id: (message ?? latestMessage()).id })
const defer = () => { let release; const promise = new Promise(resolve => { release = resolve }); return { promise, release } }

function schedule(twice = false) {
  mockDb.mutate(db => {
    const person = db.clients.find(item => item.id === 'c1')
    person.fixedWeeklySchedule = [{ id: 'mon', day: 'Monday', from: '10:00', to: '11:00' }, ...(twice ? [{ id: 'thu', day: 'Thursday', from: '10:00', to: '11:00' }] : [])]
    person.package.fixedWeeklySchedule = structuredClone(person.fixedWeeklySchedule)
    const original = db.sessions[0]
    db.sessions = (twice ? ['2026-10-05', '2026-10-08', '2026-10-12', '2026-10-15'] : ['2026-10-05', '2026-10-12', '2026-10-19']).map((date, index) => ({ ...original,
      id: `s${index + 1}`, date, from: '10:00', to: '11:00', weeklySlotId: twice && index % 2 ? 'thu' : 'mon', sessionNumber: index + 1 }))
  })
}
async function postpone(sessionId = 's1', requestKey = 'postpone-test') {
  const preview = await api.sessionService.previewPostponement({ sessionId })
  return api.sessionService.postpone({ sessionId, expected: preview.expected, requestKey })
}
beforeEach(() => {
  localStorage.clear(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(baseTime)
  mockDb.reset('2026-10-03'); vi.spyOn(database, 'delay').mockResolvedValue()
  vi.spyOn(media, 'loadExerciseVideoBlob').mockResolvedValue(new Blob(['original'], { type: 'video/webm' }))
  vi.spyOn(media, 'removeExerciseVideoBlob').mockResolvedValue()
  vi.spyOn(media, 'pruneExerciseVideoBlobs').mockResolvedValue()
  mockDb.mutate(db => {
    db.users.push({ id: 'undo-admin', role: 'admin', status: 'active', name: 'Admin' })
    for (const trainer of db.trainers) { trainer.status = 'active'; trainer.approvalNeeded.sessionTime = false; trainer.approvalNeeded.trainerReassignment = false }
    const person = db.clients.find(item => item.id === 'c1')
    person.status = 'active'; person.trainerId = 't1'
    Object.assign(person.package, { used: 0, status: 'active', startDate: '2026-09-01', endDate: '2026-12-31' })
    db.sessions = [{ ...db.sessions[0], id: 's1', clientId: 'c1', trainerId: 't1', packageId: person.package.id, date: '2026-10-05', from: '10:00', to: '11:00',
      status: 'planned', exercisePlan: [{ id: 'row', name: 'Row', weight: '20 kg', reps: '10', rounds: '3', rest: '30' }], acknowledgement: null, acknowledgementHistory: [], exerciseResults: undefined }]
    db.messages = []; db.packageCreditTransactions = []; db.remunerationApprovals = []
  })
  schedule(); login()
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); localStorage.clear() })

it.each([false, true].flatMap(twice => ['u-owner', 'undo-admin', 'u-marcus'].map(actor => ({ twice, actor }))))('postpones and restores the entire weekly cascade ($actor / twice=$twice)', async ({ twice, actor }) => {
  schedule(twice); login(actor)
  const before = mockDb.read()
  expect((await postpone()).outcome).toBe('applied')
  expect(mockDb.read().sessions.map(item => item.date)).toEqual(twice ? ['2026-10-12', '2026-10-15', '2026-10-19', '2026-10-22'] : ['2026-10-12', '2026-10-19', '2026-10-26'])
  expect(mockDb.read().sessions.map(item => item.id)).toEqual(before.sessions.map(item => item.id))
  expect(mockDb.read().clients).toEqual(before.clients)
  expect(mockDb.read().packageCreditTransactions).toEqual(before.packageCreditTransactions)
  await undo()
  expect(mockDb.reload().sessions).toEqual(before.sessions)
  expect(client().package.used).toBe(0)
})
it('keeps earlier sessions and a second purchased package outside the cascade', async () => {
  mockDb.mutate(db => {
    const person = db.clients.find(item => item.id === 'c1')
    person.additionalPackages = [{ ...person.package, id: 'additional' }]
    db.sessions.push({ ...db.sessions[0], id: 'another-package', packageId: 'additional', date: '2026-11-02' })
  })
  const before = session(), other = session('another-package')
  await postpone('s2')
  expect(session()).toEqual(before); expect(session('another-package')).toEqual(other)
  expect(session('s2').date).toBe('2026-10-19')
})
it.each(['trainer', 'client'])('rejects a cascade conflicting with another %s booking atomically', async subject => {
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'conflict', clientId: subject === 'client' ? 'c1' : 'c2', trainerId: subject === 'client' ? 't2' : 't1', packageId: subject === 'client' ? 'outside' : db.clients.find(item => item.id === 'c2').package.id, date: '2026-10-26' }) })
  const before = mockDb.read()
  await expect(postpone()).rejects.toThrow('conflicts')
  expect(mockDb.read()).toEqual(before)
})
it.each(['completed', 'cancelled', 'started', 'acknowledged', 'inactive client', 'inactive package', 'inactive trainer', 'individual time'])('rejects ineligible postponement: %s', async kind => {
  mockDb.mutate(db => {
    const first = db.sessions[0], person = db.clients.find(item => item.id === 'c1')
    if (['completed', 'cancelled'].includes(kind)) first.status = kind
    if (kind === 'started') first.date = '2026-10-03'
    if (kind === 'started') first.from = '08:00'
    if (kind === 'acknowledged') first.acknowledgement = { method: 'late_no_show' }
    if (kind === 'inactive client') person.status = 'inactive'
    if (kind === 'inactive package') person.package.status = 'inactive'
    if (kind === 'inactive trainer') db.trainers.find(item => item.id === 't1').status = 'inactive'
    if (kind === 'individual time') first.from = '10:15'
  })
  const before = mockDb.read(); await expect(postpone()).rejects.toThrow(); expect(mockDb.read()).toEqual(before)
})
it('rejects a stale preview without moving any of the remaining sessions', async () => {
  const preview = await api.sessionService.previewPostponement({ sessionId: 's1' })
  mockDb.mutate(db => { db.sessions[1].trainerId = 't2' })
  const before = mockDb.read()
  await expect(api.sessionService.postpone({ sessionId: 's1', expected: preview.expected, requestKey: 'stale' })).rejects.toThrow('changed')
  expect(mockDb.read()).toEqual(before)
})
it('deduplicates postponement retries and rejects reusing a key for different content', async () => {
  const preview = await api.sessionService.previewPostponement({ sessionId: 's1' })
  const input = { sessionId: 's1', expected: preview.expected, requestKey: 'repeat' }
  await api.sessionService.postpone(input)
  const after = mockDb.read()
  await api.sessionService.postpone(input)
  expect(mockDb.read()).toEqual(after)
  await expect(api.sessionService.postpone({ ...input, expected: 'other' })).rejects.toThrow('already been used')
})
it('routes a supervised postponement through approval and reverses it without reviving the request', async () => {
  mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true })
  const before = mockDb.read().sessions; login('u-marcus')
  expect((await postpone()).outcome).toBe('requested')
  expect(mockDb.read().sessions).toEqual(before)
  const request = latestMessage()
  await expect(postpone('s1', 'duplicate')).rejects.toThrow('pending')
  login(); await api.requestService.resolve({ id: request.id, decision: 'approved' })
  expect(session().date).toBe('2026-10-12')
  await undo(mockDb.read().messages.find(item => item.id === request.id))
  expect(mockDb.read().sessions).toEqual(before)
  expect(mockDb.read().messages.find(item => item.id === request.id).status).toBe('reversed')
})
it('Undo of a pending postponement cancels only the proposal', async () => {
  mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus')
  const before = mockDb.read().sessions
  await postpone(); await undo()
  expect(mockDb.read().sessions).toEqual(before)
  expect(mockDb.read().messages.find(item => item.request?.type === 'session_postpone').status).toBe('cancelled')
})
it('rechecks booking conflicts when a postponement is approved', async () => {
  mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus'); await postpone()
  const request = latestMessage(); login()
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'new-booking', clientId: 'c2', packageId: db.clients[1].package.id, date: '2026-10-26' }) })
  const before = mockDb.read()
  await expect(api.requestService.resolve({ id: request.id, decision: 'approved' })).rejects.toThrow('conflicts')
  expect(mockDb.read()).toEqual(before)
})
it.each([
  ['saveClientSummary', { summary: 'Changed summary' }],
  ['saveOutcome', { outcome: { trainerComments: 'Changed comments', exerciseResults: [{ id: 'row', name: 'Row', loadKg: 30, reps: 10, sets: 3 }] } }],
  ['saveExercisePlan', { items: [{ id: 'new', name: 'Squat', weight: '25 kg' }] }],
  ['updateDetails', { patch: { date: '2026-10-06', from: '11:00', to: '12:00', trainerId: 't2' } }],
  ['requestTimeChange', { patch: { date: '2026-10-06', from: '11:00', to: '12:00' } }],
])('reverses %s through its Message', async (operation, input) => {
  if (operation.startsWith('request')) login('u-marcus')
  const before = session()
  await api.sessionService[operation]({ sessionId: 's1', ...input })
  await undo()
  expect(session()).toEqual(before)
})
it.each(['signature', 'late_no_show'])('reverses %s completion with one compensating credit and retained evidence', async method => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: method === 'signature' ? signed : { method } })
  const original = session().acknowledgement
  expect(client().package.used).toBe(1)
  const message = latestMessage(); await undo(message); await undo(message)
  expect(session().status).toBe('planned'); expect(session().acknowledgement).toBeNull()
  expect(session().acknowledgementHistory).toContainEqual(original)
  expect(client().package.used).toBe(0); expect(client().strengthProgress).toEqual([])
  expect(mockDb.read().packageCreditTransactions.map(item => item.amount)).toEqual([-1, 1])
  expect(hasSessionDebit(mockDb.read().packageCreditTransactions, 's1')).toBe(false)
})
it('reverses a no-show-to-signature correction without issuing a credit', async () => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: { method: 'late_no_show' } })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })
  await undo()
  expect(session().acknowledgement.method).toBe('late_no_show'); expect(session().acknowledgementHistory).toHaveLength(2)
  expect(client().package.used).toBe(1); expect(mockDb.read().packageCreditTransactions).toHaveLength(1)
})
it.each([-1, 0, 1])('enforces the exact 24-hour boundary (%s ms)', async offset => {
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'Changed' })
  const message = latestMessage(); vi.setSystemTime(baseTime + day + offset)
  if (offset < 0) { await undo(message); expect(session().clientSummary).not.toBe('Changed') }
  else { const before = mockDb.read(); await expect(undo(message)).rejects.toThrow('expired'); expect(mockDb.read()).toEqual(before) }
})
it('returns an already committed reversal after expiry without a second write', async () => {
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'Changed' })
  const message = latestMessage(), result = await undo(message)
  const before = mockDb.read(); vi.setSystemTime(baseTime + 2 * day)
  expect(await undo(message)).toEqual(result); expect(mockDb.read()).toEqual(before)
})
it('does not reset the expiry when read, reloaded or refreshed across midnight', async () => {
  vi.setSystemTime(Date.parse('2026-10-03T15:59:00Z'))
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'Changed' })
  const message = latestMessage(), expiresAt = mockDb.read().sessionMutations.at(-1).expiresAt
  vi.setSystemTime(Date.parse('2026-10-03T16:01:00Z'))
  await api.messageService.markRead({ id: message.id }); mockDb.reload()
  const loaded = await api.load()
  expect(loaded.data.messages.find(item => item.id === message.id).undo.expiresAt).toBe(expiresAt)
  expect(expiresAt).toBe('2026-10-04T15:59:00.000Z')
  expect(loaded.data).not.toHaveProperty('sessionMutations')
})
it('refuses an older Undo after a later edit, then permits reversing in order', async () => {
  const original = session()
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'First' }); const first = latestMessage()
  await api.sessionService.saveOutcome({ sessionId: 's1', outcome: { trainerComments: 'Second' } }); const second = latestMessage()
  const before = mockDb.read(); await expect(undo(first)).rejects.toThrow('changed again'); expect(mockDb.read()).toEqual(before)
  await undo(second); await undo(first); expect(session()).toEqual(original)
})
it('preserves unrelated session edits and per-user Message read receipts', async () => {
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'First' }); const first = latestMessage()
  await api.messageService.markRead({ id: first.id })
  await api.sessionService.saveClientSummary({ sessionId: 's2', summary: 'Other session' })
  await undo(first)
  expect(session('s2').clientSummary).toBe('Other session')
  expect(mockDb.read().messages.find(item => item.id === first.id).readBy['u-owner']).toBeTruthy()
})
it('blocks restoring a now occupied slot without a partial cascade', async () => {
  await postpone(); const message = latestMessage()
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'occupied', date: '2026-10-05', clientId: 'c2', packageId: db.clients[1].package.id }) })
  const before = mockDb.read(); await expect(undo(message)).rejects.toThrow('conflicts'); expect(mockDb.read()).toEqual(before)
})
it('blocks a reversal affecting an approved pay cycle without altering pay or credits', async () => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })
  const message = latestMessage()
  mockDb.mutate(db => { db.remunerationApprovals = [{ trainerId: 't1', cycle: { key: '2026-10' }, amountCents: 9000 }] })
  const before = mockDb.read(); await expect(undo(message)).rejects.toThrow('approved remuneration'); expect(mockDb.read()).toEqual(before)
})
it.each(['disabled', 'reassigned', 'replacement login'])('rejects a pending Undo after %s', async reason => {
  login('u-marcus'); await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'Changed' }); const message = latestMessage()
  const waiting = defer(); database.delay.mockImplementationOnce(() => waiting.promise)
  const pending = undo(message)
  await Promise.resolve()
  if (reason === 'disabled') mockDb.mutate(db => { db.users.find(item => item.id === 'u-marcus').status = 'inactive' })
  if (reason === 'reassigned') mockDb.mutate(db => { db.sessions[0].trainerId = 't2' })
  if (reason === 'replacement login') localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: 'u-marcus', generation: 'replacement', expiresAt: Date.now() + day }))
  const before = mockDb.read(); waiting.release()
  await expect(pending).rejects.toThrow(/active|assigned|session changed/); expect(mockDb.read()).toEqual(before)
})
it('rejects another trainer and does not expose a private inverse payload', async () => {
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'Changed' }); const message = latestMessage()
  login('u-daniel'); await expect(undo(message)).rejects.toThrow(/unavailable|original trainer/)
  login('undo-admin'); const loaded = await api.load()
  expect(loaded.data).not.toHaveProperty('sessionMutations')
  expect(JSON.stringify(loaded.data.messages.find(item => item.id === message.id).undo)).not.toContain('before')
})
it('does not publish a partial Undo when storage fails and allows an explicit retry', async () => {
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'Changed' }); const message = latestMessage(), before = mockDb.read()
  const failure = vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Quota') })
  await expect(undo(message)).rejects.toThrow('Quota'); expect(mockDb.read()).toEqual(before)
  failure.mockRestore(); await undo(message); expect(session().clientSummary).not.toBe('Changed')
})
it('retains removed video bytes for Undo, restores the video and respects the original expiry', async () => {
  mockDb.mutate(db => { db.sessions[0].exercisePlan[0] = { id: 'row', name: 'Row', videoAttached: true, video: { id: 'old-video', attachedAt: new Date(baseTime).toISOString(), expiresAt: new Date(baseTime + 7 * day).toISOString() } } })
  await api.sessionService.removeVideo({ sessionId: 's1', exerciseId: 'row' }); const message = latestMessage()
  expect(media.removeExerciseVideoBlob).not.toHaveBeenCalled()
  await undo(message)
  expect(session().exercisePlan[0].video.id).toBe('old-video')
  await flushExerciseVideoDeletions(); expect(media.removeExerciseVideoBlob).not.toHaveBeenCalled()
})
it.each(['missing', 'expired'])('cannot restore %s media and leaves all other state unchanged', async kind => {
  mockDb.mutate(db => { db.sessions[0].exercisePlan[0] = { id: 'row', name: 'Row', videoAttached: true, video: { id: 'old-video', attachedAt: new Date(baseTime - 6.5 * day).toISOString(), expiresAt: new Date(baseTime + day / 2).toISOString() } } })
  await api.sessionService.removeVideo({ sessionId: 's1', exerciseId: 'row' }); const message = latestMessage()
  if (kind === 'missing') media.loadExerciseVideoBlob.mockResolvedValue(null)
  else vi.setSystemTime(baseTime + day / 2)
  const before = mockDb.read(); await expect(undo(message)).rejects.toThrow(/no longer available|expired/); expect(mockDb.read()).toEqual(before)
})
it('releases removed media once the one-day Undo window ends', async () => {
  mockDb.mutate(db => { db.sessions[0].exercisePlan[0] = { id: 'row', name: 'Row', videoAttached: true, video: { id: 'old-video', attachedAt: new Date(baseTime).toISOString(), expiresAt: new Date(baseTime + 7 * day).toISOString() } } })
  await api.sessionService.removeVideo({ sessionId: 's1', exerciseId: 'row' }); expect(media.removeExerciseVideoBlob).not.toHaveBeenCalled()
  vi.setSystemTime(baseTime + day); await flushExerciseVideoDeletions()
  expect(media.removeExerciseVideoBlob).toHaveBeenCalledExactlyOnceWith('s1', 'row', 'old-video')
})
it('reverses weekly schedule edits and client deactivation as complete operations', async () => {
  const before = mockDb.read()
  await api.clientService.saveFixedWeeklySchedule({ id: 'c1', slots: [{ id: 'mon', day: 'Monday', from: '12:00', to: '13:00' }] }); await undo()
  expect(mockDb.read().sessions).toEqual(before.sessions); expect(client().fixedWeeklySchedule).toEqual(before.clients.find(item => item.id === 'c1').fixedWeeklySchedule)
  await api.clientService.deactivate({ id: 'c1' }); await undo()
  expect(client().status).toBe('active'); expect(client().package.status).toBe('active')
})
it('requires a fresh acknowledgement after Undo and consumes exactly one credit on re-completion', async () => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed }); await undo()
  const before = mockDb.read()
  await expect(api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })).rejects.toThrow('reopened')
  expect(mockDb.read()).toEqual(before)
  const acknowledgement = { ...signed, reversalId: session().acknowledgementReversals.at(-1).operationId }
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement })
  expect(client().package.used).toBe(1)
  expect(mockDb.read().packageCreditTransactions.map(item => item.amount)).toEqual([-1, 1, -1])
  expect(new Set(mockDb.read().packageCreditTransactions.map(item => item.id)).size).toBe(3)
  expect(client().strengthProgress[0].points).toHaveLength(1)
})
it('completion Undo preserves credits consumed by another session in the same package', async () => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03'; db.sessions[1].date = '2026-10-02' })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed }); const first = latestMessage()
  await api.sessionService.acknowledge({ sessionId: 's2', acknowledgement: { method: 'late_no_show' } })
  await undo(first)
  expect(client().package.used).toBe(1); expect(session('s2').status).toBe('completed')
  expect(hasSessionDebit(mockDb.read().packageCreditTransactions, 's2')).toBe(true)
})
it('rechecks expiry after asynchronous media recovery and commits nothing late', async () => {
  mockDb.mutate(db => { db.sessions[0].exercisePlan[0] = { id: 'row', name: 'Row', videoAttached: true, video: { id: 'old-video', attachedAt: new Date(baseTime).toISOString(), expiresAt: new Date(baseTime + 7 * day).toISOString() } } })
  await api.sessionService.removeVideo({ sessionId: 's1', exerciseId: 'row' })
  const waiting = defer(), entered = defer(); media.loadExerciseVideoBlob.mockImplementation(() => { entered.release(); return waiting.promise })
  const pending = undo(); await entered.promise
  vi.setSystemTime(baseTime + day); const before = mockDb.read(); waiting.release(new Blob(['original']))
  await expect(pending).rejects.toThrow('expired'); expect(mockDb.read()).toEqual(before)
})
it('reverses copied plans and trainer changes, with current-assignment authority', async () => {
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'prior', date: '2026-09-28', exercisePlan: [{ id: 'prior-row', name: 'Prior exercise' }] }) })
  const original = session()
  await api.sessionService.copyPreviousPlan({ sessionId: 's1' }); await undo(); expect(session()).toEqual(original)
  login('u-marcus'); await api.sessionService.requestTrainerChange({ sessionId: 's1', replacementTrainerId: 't2' }); const message = latestMessage()
  await expect(undo(message)).rejects.toThrow('assigned')
  login(); await undo(message); expect(session()).toEqual(original)
})
it('reverses deletion of an inactive package’s sessions without restoring media placeholders', async () => {
  mockDb.mutate(db => { db.clients.find(item => item.id === 'c1').package.status = 'inactive' })
  const before = mockDb.read().sessions
  await api.clientService.deletePackageSessions({ id: 'c1', options: { packageId: client().package.id } })
  expect(mockDb.read().sessions).toHaveLength(0)
  await undo(); expect(mockDb.read().sessions).toEqual(before)
  expect(client().package.status).toBe('inactive')
})
it('reverses trainer deactivation and all its cover assignments atomically', async () => {
  const before = mockDb.read()
  await api.trainerService.deactivate({ id: 't1', replacements: { s1: 't2', s2: 't2', s3: 't2' } }); await undo()
  expect(mockDb.read().sessions).toEqual(before.sessions)
  expect(mockDb.read().trainers.find(item => item.id === 't1').status).toBe('active')
  expect(mockDb.read().users.find(item => item.id === 'u-marcus').status).toBe('active')
})
it('starts the applied postponement window when approved, not when requested', async () => {
  mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus'); await postpone(); const request = latestMessage()
  vi.setSystemTime(baseTime + day); login(); await api.requestService.resolve({ id: request.id, decision: 'approved' })
  expect(mockDb.read().sessionMutations.at(-1).expiresAt).toBe(new Date(baseTime + 2 * day).toISOString())
  await undo(mockDb.read().messages.find(item => item.id === request.id)); expect(session().date).toBe('2026-10-05')
})
it('does not reverse a session underneath a newly pending change request', async () => {
  await api.sessionService.saveClientSummary({ sessionId: 's1', summary: 'Changed' }); const message = latestMessage()
  mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus')
  await api.sessionService.requestTimeChange({ sessionId: 's1', patch: { date: '2026-10-06', from: '10:00', to: '11:00' } }); login()
  const before = mockDb.read(); await expect(undo(message)).rejects.toThrow('pending request'); expect(mockDb.read()).toEqual(before)
})
it.each(['additionalPackages', 'packageHistory'])('completion Undo restores the correct purchase inside %s', async field => {
  mockDb.mutate(db => {
    const person = db.clients.find(item => item.id === 'c1')
    person[field] = [{ ...person.package, id: 'separate-purchase', used: 2 }]
    Object.assign(db.sessions[0], { packageId: 'separate-purchase', date: '2026-10-03' })
  })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })
  expect(client()[field][0].used).toBe(3); await undo()
  expect(client()[field][0].used).toBe(2); expect(client().package.used).toBe(0)
})
it('preserves the deactivation history when a package is restored by Undo', async () => {
  await api.clientService.deactivatePackage({ id: 'c1', options: { packageId: client().package.id } }); await undo()
  expect(client().package.status).toBe('active')
  expect(client().package.statusHistory.map(item => item.status)).toEqual(['inactive', 'active'])
  expect(client().package.statusHistory.at(-1).reason).toBe('undo')
})
it('does not replay an undone reactivation from retained Messages on reload', async () => {
  await api.clientService.deactivate({ id: 'c1' })
  const frozen = client().package.status
  await api.clientService.reactivate({ id: 'c1' }); await undo()
  mockDb.reload(); expect(client().status).toBe('inactive'); expect(client().package.status).toBe(frozen)
  const notice = mockDb.read().messages.find(item => item.id.startsWith('client-on-'))
  expect(notice.reversedAt).toBeTruthy()
})

it.each([false, true])('reverses renewal after normalized purchase selection (activated=%s)', async activated => {
  const { packageDraftForClient } = await import('../app/packageRenewal.js')
  if (activated) { vi.setSystemTime('2027-05-01T04:00:00Z'); login() }
  mockDb.mutate(db => {
    db.trainers.find(item => item.id === 't1').availability.Monday = [['06:00', '23:00']]
    db.clients.find(item => item.id === 'c1').clientPreferences = [{ id: 'mon', days: ['Monday'], from: '10:00', to: '11:00' }]
  })
  const original = mockDb.read(), person = client()
  const draft = { ...packageDraftForClient(person, original.sessions, original.packages, '2027-01-04'), requestId: 'undo-renewal',
    expectedPackageId: person.package.id, expectedTrainerId: person.trainerId, expectedSchedule: person.fixedWeeklySchedule,
    packageId: 'package-12', packageVersion: 1, startDate: '2027-01-04', sessionsPerWeek: 1, genderPreference: 'No gender preference' }
  await api.clientService.renewPackage({ id: 'c1', draft })
  expect(mockDb.read().sessions.length).toBeGreaterThan(original.sessions.length)
  const message = latestMessage()
  expect(message.mutationId).toBeTruthy()
  await undo(message)
  expect(mockDb.reload().sessions).toEqual(original.sessions)
  expect(client().package.id).toBe(person.package.id)
  expect(client().additionalPackages ?? []).toEqual(person.additionalPackages ?? [])
  expect(client().packageHistory).toEqual(person.packageHistory)
})
it('reverses permanent trainer reassignment while retaining assignment history', async () => {
  const { trainerReassignmentSnapshot } = await import('../app/trainerReassignment.js')
  const { businessClock } = await import('../app/clock.js')
  mockDb.mutate(db => {
    db.trainers.find(item => item.id === 't2').availability = Object.fromEntries(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => [day, [['06:00', '23:00']]]))
  })
  const before = mockDb.read()
  const draft = { requestId: 'undo-reassign', trainerId: 't2', expected: trainerReassignmentSnapshot(client(), before.sessions, before.packageCreditTransactions, businessClock(new Date(), before.settings.timeZone)) }
  await api.clientService.reassignTrainer({ id: 'c1', draft })
  expect(client().trainerId).toBe('t2')
  await undo(mockDb.read().messages.findLast(item => item.mutationId && item.recipientRole === 'owner'))
  expect(mockDb.reload().sessions).toEqual(before.sessions)
  expect(client().trainerId).toBe('t1')
  expect(client().trainerAssignmentHistory).toHaveLength((before.clients[0].trainerAssignmentHistory?.length ?? 0) + 2)
  expect(client().trainerAssignmentHistory.at(-1).reversalOf).toBeTruthy()
})
