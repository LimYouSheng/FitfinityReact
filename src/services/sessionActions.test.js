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

const acknowledgementMessage = () => mockDb.read().messages.findLast(item => item.title.startsWith('Session acknowledgement saved'))
// Reproduce the stored journal shape from releases that allowed acknowledgement Undo.
function legacyAcknowledgement(before, actorId = 'u-owner') {
  const message = acknowledgementMessage()
  mockDb.mutate(db => {
    db.sessionMutations ??= []
    db.sessionMutations.push({ id: 'legacy-acknowledgement', operation: 'session.acknowledge',
      actor: structuredClone(db.users.find(item => item.id === actorId)), status: 'available',
      committedAt: new Date(baseTime).toISOString(), expiresAt: new Date(baseTime + day).toISOString(),
      sessions: [{ id: 's1', position: 0, before: before.sessions.find(item => item.id === 's1'), after: structuredClone(db.sessions.find(item => item.id === 's1')) }],
      patches: [], proposals: [], requests: [], dependencies: [], messageIds: [message.id],
      debits: db.packageCreditTransactions.filter(item => !before.packageCreditTransactions.some(prior => prior.id === item.id)) })
    db.messages.find(item => item.id === message.id).mutationId = 'legacy-acknowledgement'
  })
  return mockDb.read().messages.find(item => item.id === message.id)
}

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

it.each([false, true].flatMap(twice => ['u-owner', 'undo-admin', 'u-marcus'].map(actor => ({ twice, actor }))))('postpones and restores only the selected session ($actor / twice=$twice)', async ({ twice, actor }) => {
  schedule(twice); login(actor)
  const before = mockDb.read()
  expect((await postpone()).outcome).toBe('applied')
  expect(mockDb.read().sessions.map(item => item.date)).toEqual(twice ? [null, '2026-10-08', '2026-10-12', '2026-10-15'] : [null, '2026-10-12', '2026-10-19'])
  expect(mockDb.read().sessions.map(item => item.id)).toEqual(before.sessions.map(item => item.id))
  expect(mockDb.read().sessions.slice(1).map(({ sessionNumber, ...rest }) => rest)).toEqual(before.sessions.slice(1).map(({ sessionNumber, ...rest }) => rest))
  expect(mockDb.read().clients).toEqual(before.clients)
  expect(mockDb.read().packageCreditTransactions).toEqual(before.packageCreditTransactions)
  await undo()
  expect(mockDb.reload().sessions).toEqual(before.sessions)
  expect(client().package.used).toBe(0)
})
it('preserves other bookings and isolates chronological numbering to the current package', async () => {
  mockDb.mutate(db => {
    const person = db.clients.find(item => item.id === 'c1')
    person.additionalPackages = [{ ...person.package, id: 'additional' }]
    db.sessions.push({ ...db.sessions[0], id: 'another-package', packageId: 'additional', date: '2026-11-02' })
  })
  const before = session(), other = session('another-package')
  await postpone('s2')
  expect(session()).toEqual(before); expect(session('another-package')).toEqual(other)
  expect(session('s2')).toMatchObject({ date: null, scheduleState: 'open', sessionNumber: null })
})
it.each(['trainer', 'client'])('rejects scheduling an open session into another %s booking atomically', async subject => {
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'conflict', clientId: subject === 'client' ? 'c1' : 'c2', trainerId: subject === 'client' ? 't2' : 't1', packageId: subject === 'client' ? 'outside' : db.clients.find(item => item.id === 'c2').package.id, date: '2026-10-26' }) })
  const before = mockDb.read()
  await postpone()
  const open = mockDb.read()
  await expect(api.sessionService.updateDetails({ sessionId: 's1', patch: { date: '2026-10-26', from: '10:00', to: '11:00', trainerId: 't1' } })).rejects.toThrow('conflicts')
  expect(mockDb.read()).toEqual(open)
  await undo()
  expect(mockDb.read().sessions).toEqual(before.sessions)
})
it.each(['completed', 'cancelled', 'started', 'acknowledged', 'inactive client', 'inactive package', 'inactive trainer', 'invalid interval'])('rejects ineligible postponement: %s', async kind => {
  mockDb.mutate(db => {
    const first = db.sessions[0], person = db.clients.find(item => item.id === 'c1')
    if (['completed', 'cancelled'].includes(kind)) first.status = kind
    if (kind === 'started') first.date = '2026-10-03'
    if (kind === 'started') first.from = '08:00'
    if (kind === 'acknowledged') first.acknowledgement = { method: 'late_no_show' }
    if (kind === 'inactive client') person.status = 'inactive'
    if (kind === 'inactive package') person.package.status = 'inactive'
    if (kind === 'inactive trainer') db.trainers.find(item => item.id === 't1').status = 'inactive'
    if (kind === 'invalid interval') first.from = '11:15'
  })
  const before = mockDb.read(); await expect(postpone()).rejects.toThrow(); expect(mockDb.read()).toEqual(before)
})
it('postponement preserves individually rescheduled sessions', async () => {
  mockDb.mutate(db => { Object.assign(db.sessions[1], { date: '2026-10-13', from: '13:00', to: '14:00' }) })
  const before = mockDb.read().sessions
  await postpone()
  expect(mockDb.read().sessions.map(({ date, from, to }) => ({ date, from, to }))).toEqual([
    { date: null, from: null, to: null },
    { date: '2026-10-13', from: '13:00', to: '14:00' },
    { date: '2026-10-19', from: '10:00', to: '11:00' },
  ])
  await undo(); expect(mockDb.read().sessions).toEqual(before)
})
it('postponement previews an explicit undated state without writing or needing a free replacement slot', async () => {
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'conflict', clientId: 'c2', packageId: db.clients[1].package.id, date: '2026-10-26' }) })
  const before = mockDb.read()
  const preview = await api.sessionService.previewPostponement({ sessionId: 's1' })
  expect(preview.changes[0].next).toEqual({ scheduleState: 'open', date: null, from: null, to: null, weeklySlotId: null })
  expect(JSON.parse(preview.expected).version).toBe(4)
  expect(mockDb.read()).toEqual(before)
})
it('rejects a stale preview without moving any of the remaining sessions', async () => {
  const preview = await api.sessionService.previewPostponement({ sessionId: 's1' })
  mockDb.mutate(db => { db.sessions[2].date = '2026-10-20' })
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
  expect(session()).toMatchObject({ date: null, scheduleState: 'open' })
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
it('rechecks changed calendar when a postponement is approved', async () => {
  mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus'); await postpone()
  const request = latestMessage(); login()
  mockDb.mutate(db => { db.sessions[1].date = '2026-10-13' })
  const before = mockDb.read()
  await expect(api.requestService.resolve({ id: request.id, decision: 'approved' })).rejects.toThrow('changed')
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
it.each(['signature', 'late_no_show'])('acknowledgement finality keeps %s completion and its credit permanent for new and old Messages', async method => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' })
  const before = mockDb.read()
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: method === 'signature' ? signed : { method } })
  const message = acknowledgementMessage(), completed = mockDb.read()
  expect(session().status).toBe('completed'); expect(client().package.used).toBe(1)
  expect(completed.sessionMutations?.some(item => item.operation === 'session.acknowledge') ?? false).toBe(false)
  expect((await api.load()).data.messages.find(item => item.id === message.id).undo).toBeUndefined()
  await expect(undo(message)).rejects.toThrow('no recoverable session change')
  expect(mockDb.read()).toEqual(completed)
  const legacy = legacyAcknowledgement(before), stored = mockDb.read()
  expect((await api.load()).data.messages.find(item => item.id === legacy.id).undo).toBeNull()
  await expect(undo(legacy)).rejects.toThrow('Acknowledgements cannot be undone')
  expect(mockDb.read()).toEqual(stored)
  expect(hasSessionDebit(stored.packageCreditTransactions, 's1')).toBe(true)
})
it('acknowledgement finality permits no-show-to-signature correction without another credit or a reversible correction', async () => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: { method: 'late_no_show' } })
  const before = mockDb.read()
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })
  const message = acknowledgementMessage()
  expect((await api.load()).data.messages.find(item => item.id === message.id).undo).toBeUndefined()
  expect(session().acknowledgement.method).toBe('signature'); expect(session().acknowledgementHistory).toHaveLength(2)
  expect(session().acknowledgementHistory[0]).toEqual(before.sessions[0].acknowledgement)
  expect(client().package.used).toBe(1); expect(mockDb.read().packageCreditTransactions).toHaveLength(1)
  const legacy = legacyAcknowledgement(before), stored = mockDb.read()
  expect((await api.load()).data.messages.find(item => item.id === legacy.id).undo).toBeNull()
  await expect(undo(legacy)).rejects.toThrow('Acknowledgements cannot be undone')
  await expect(api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: { method: 'late_no_show' } })).rejects.toThrow('permanent')
  expect(mockDb.read()).toEqual(stored)
})
it.each(['u-owner', 'undo-admin', 'u-marcus'])('acknowledgement finality refuses legacy Undo by %s after reload', async actor => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' }); login('u-marcus')
  const before = mockDb.read()
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })
  const legacy = legacyAcknowledgement(before, 'u-marcus')
  login(actor); mockDb.reload()
  const stored = mockDb.read()
  expect((await api.load()).data.messages.find(item => item.id === legacy.id).undo).toBeNull()
  await expect(undo(legacy)).rejects.toThrow('Acknowledgements cannot be undone')
  expect(mockDb.read()).toEqual(stored)
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
it('blocks restoring a now occupied slot without partial changes', async () => {
  await postpone(); const message = latestMessage()
  mockDb.mutate(db => { db.sessions.push({ ...db.sessions[0], id: 'occupied', date: '2026-10-05', from: '10:00', to: '11:00', scheduleState: 'scheduled', clientId: 'c2', packageId: db.clients[1].package.id }) })
  const before = mockDb.read(); await expect(undo(message)).rejects.toThrow('conflicts'); expect(mockDb.read()).toEqual(before)
})
it('blocks a reversal affecting an approved pay cycle without altering pay or credits', async () => {
  await api.sessionService.updateDetails({ sessionId: 's1', patch: { date: '2026-10-06', from: '11:00', to: '12:00', trainerId: 't1' } })
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
it('acknowledgement finality preserves already-reopened legacy history and requires fresh completion', async () => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03' })
  const before = mockDb.read()
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })
  const legacy = legacyAcknowledgement(before)
  mockDb.mutate(db => {
    const completed = db.sessions[0], debit = db.packageCreditTransactions[0]
    completed.acknowledgementReversals = [{ operationId: legacy.mutationId, at: new Date(baseTime).toISOString(), by: 'u-owner', acknowledgement: structuredClone(completed.acknowledgement) }]
    completed.acknowledgement = null; completed.status = 'planned'
    db.clients.find(item => item.id === 'c1').package.used = 0
    db.packageCreditTransactions.push({ id: 'legacy-credit-reversal', type: 'session_reversal', debitId: debit.id, sessionId: 's1', clientId: 'c1', packageId: debit.packageId, amount: 1, createdAt: new Date(baseTime).toISOString() })
    db.sessionMutations.find(item => item.id === legacy.mutationId).status = 'undone'
  })
  mockDb.reload(); const reopened = mockDb.read()
  await expect(undo(legacy)).rejects.toThrow('Acknowledgements cannot be undone')
  await expect(api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })).rejects.toThrow('reopened')
  expect(mockDb.read()).toEqual(reopened)
  const acknowledgement = { ...signed, reversalId: legacy.mutationId }
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement })
  expect(client().package.used).toBe(1)
  expect(mockDb.read().packageCreditTransactions.map(item => item.amount)).toEqual([-1, 1, -1])
  expect(new Set(mockDb.read().packageCreditTransactions.map(item => item.id)).size).toBe(3)
  expect(session().acknowledgementHistory).toHaveLength(2)
  expect((await api.load()).data.messages.find(item => item.id === acknowledgementMessage().id).undo).toBeUndefined()
})
it('acknowledgement finality preserves credits consumed by both sessions when Undo is attempted', async () => {
  mockDb.mutate(db => { db.sessions[0].date = '2026-10-03'; db.sessions[1].date = '2026-10-02' })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed }); const first = acknowledgementMessage()
  await api.sessionService.acknowledge({ sessionId: 's2', acknowledgement: { method: 'late_no_show' } })
  const completed = mockDb.read()
  await expect(undo(first)).rejects.toThrow('no recoverable session change')
  expect(mockDb.read()).toEqual(completed)
  expect(client().package.used).toBe(2); expect(session('s2').status).toBe('completed')
  expect(hasSessionDebit(completed.packageCreditTransactions, 's1')).toBe(true)
  expect(hasSessionDebit(completed.packageCreditTransactions, 's2')).toBe(true)
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
it.each(['additionalPackages', 'packageHistory'])('acknowledgement finality preserves the debit in %s when Undo is attempted', async field => {
  mockDb.mutate(db => {
    const person = db.clients.find(item => item.id === 'c1')
    person[field] = [{ ...person.package, id: 'separate-purchase', used: 2 }]
    Object.assign(db.sessions[0], { packageId: 'separate-purchase', date: '2026-10-03' })
  })
  await api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })
  expect(client()[field][0].used).toBe(3)
  const completed = mockDb.read()
  await expect(undo(acknowledgementMessage())).rejects.toThrow('no recoverable session change')
  expect(mockDb.read()).toEqual(completed)
  expect(client()[field][0].used).toBe(3); expect(client().package.used).toBe(0)
})
it.each([false, true])('package finality keeps deactivation and its history without Undo (delete sessions=%s)', async deleteUpcomingSessions => {
  const original = mockDb.read()
  await api.clientService.deactivatePackage({ id: 'c1', options: { packageId: client().package.id, deleteUpcomingSessions } })
  const message = mockDb.read().messages.findLast(item => item.title.startsWith('Package deactivated:'))
  expect(message.mutationId).toBeUndefined()
  expect(message.body).not.toContain('Undo')
  expect((await api.load()).data.messages.find(item => item.id === message.id).undo).toBeUndefined()
  mockDb.reload(); const saved = mockDb.read()
  await expect(undo(message)).rejects.toThrow('no recoverable session change')
  expect(mockDb.read()).toEqual(saved)
  expect(client().package.status).toBe('inactive')
  expect(client().package.statusHistory.map(item => item.status)).toEqual(['inactive'])
  expect(saved.sessions).toEqual(deleteUpcomingSessions ? [] : original.sessions)
  expect(saved.packageCreditTransactions).toEqual(original.packageCreditTransactions)
})
it('does not replay an undone reactivation from retained Messages on reload', async () => {
  await api.clientService.deactivate({ id: 'c1' })
  const frozen = client().package.status
  await api.clientService.reactivate({ id: 'c1' }); await undo()
  mockDb.reload(); expect(client().status).toBe('inactive'); expect(client().package.status).toBe(frozen)
  const notice = mockDb.read().messages.find(item => item.id.startsWith('client-on-'))
  expect(notice.reversedAt).toBeTruthy()
})

it.each([false, true])('package finality preserves Add Package after normalized purchase selection (activated=%s)', async activated => {
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
  const message = mockDb.read().messages.findLast(item => item.title.startsWith('Package added:'))
  expect(message.mutationId).toBeUndefined()
  expect((await api.load()).data.messages.find(item => item.id === message.id).undo).toBeUndefined()
  mockDb.reload(); const saved = mockDb.read()
  await expect(undo(message)).rejects.toThrow('no recoverable session change')
  expect(mockDb.read()).toEqual(saved)
  await api.clientService.renewPackage({ id: 'c1', draft })
  expect(mockDb.read()).toEqual(saved)
  expect(saved.packageCreditTransactions).toEqual(original.packageCreditTransactions)
})
it.each(['client.renewPackage', 'client.deactivatePackage', 'client.reactivatePackage'].flatMap(operation => ['u-owner', 'undo-admin', 'u-marcus'].map(actor => ({ operation, actor }))))('package finality refuses legacy $operation Undo by $actor without rewriting history', async ({ operation, actor }) => {
  const message = { id: 'legacy-package-message', title: 'Package history', kind: 'client_update', recipientRole: 'owner', recipientTrainerId: 't1',
    clientId: 'c1', mutationId: 'legacy-package-operation', readBy: {}, createdAt: new Date(baseTime).toISOString() }
  mockDb.mutate(db => {
    db.messages.push(message)
    db.sessionMutations ??= []
    db.sessionMutations.push({ id: message.mutationId, operation, actor: structuredClone(db.users.find(item => item.id === 'u-owner')),
      committedAt: new Date(baseTime).toISOString(), expiresAt: new Date(baseTime + day).toISOString(), status: 'available',
      sessions: [], patches: [], proposals: [], requests: [], dependencies: [], messageIds: [message.id] })
  })
  login(actor)
  for (const status of ['available', 'undone']) {
    mockDb.mutate(db => { db.sessionMutations.find(item => item.id === message.mutationId).status = status })
    mockDb.reload(); const saved = mockDb.read()
    expect((await api.load()).data.messages.find(item => item.id === message.id).undo).toBeNull()
    await expect(undo(message)).rejects.toThrow(/Package actions cannot be undone|original trainer/)
    expect(mockDb.read()).toEqual(saved)
  }
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

it('postponement removes only the selected booking despite individually changed dates and a cancelled tail', async () => {
  mockDb.mutate(db => {
    Object.assign(db.sessions[0], { date: '2026-10-06', from: '12:00', to: '13:00' })
    Object.assign(db.sessions[2], { date: '2026-10-20', from: '14:00', to: '15:30' })
    db.sessions.push({ ...db.sessions[2], id: 'cancelled-tail', date: '2026-11-30', status: 'cancelled' })
  })
  const before = mockDb.read()
  await postpone()
  expect(session()).toMatchObject({ date: null, from: null, to: null, scheduleState: 'open', weeklySlotId: null, sessionNumber: null })
  expect(mockDb.read().sessions.slice(1).map(({ sessionNumber, ...rest }) => rest)).toEqual(before.sessions.slice(1).map(({ sessionNumber, ...rest }) => rest))
  expect(mockDb.read().clients).toEqual(before.clients)
  await undo(); expect(mockDb.read().sessions).toEqual(before.sessions)
})
it.each(['s3', 'only'])('postponement permits the last or only current-package session: %s', async id => {
  if (id === 'only') mockDb.mutate(db => { db.sessions = [db.sessions[0]] })
  await postpone(id === 'only' ? 's1' : id)
  expect(session(id === 'only' ? 's1' : id)).toMatchObject({ scheduleState: 'open', date: null })
})
it('postponement rejects an additional purchase even when it is active', async () => {
  mockDb.mutate(db => {
    const person = db.clients.find(item => item.id === 'c1')
    person.additionalPackages = [{ ...person.package, id: 'additional' }]
    db.sessions[0].packageId = 'additional'
  })
  const before = mockDb.read()
  await expect(postpone()).rejects.toThrow('current package')
  expect(mockDb.read()).toEqual(before)
})
it('schedules an open session and undoes scheduling before undoing postponement', async () => {
  const before = mockDb.read(); await postpone(); const open = mockDb.read()
  await api.sessionService.updateDetails({ sessionId: 's1', patch: { date: '2026-10-13', from: '13:00', to: '14:00', trainerId: 't1' } })
  expect(session()).toMatchObject({ scheduleState: 'scheduled', date: '2026-10-13', sessionNumber: 2 })
  expect(session('s2').sessionNumber).toBe(1)
  expect(session('s3').sessionNumber).toBe(3)
  await undo(); expect(mockDb.read().sessions).toEqual(open.sessions)
  await undo(open.messages.findLast(item => item.mutationId)); expect(mockDb.read().sessions).toEqual(before.sessions)
})
it.each([
  { date: '2026-10-18', from: '10:00', to: '11:00' },
  { date: '2026-10-19', from: '10:30', to: '11:30' },
  { date: '2026-10-27', from: '14:00', to: '13:00' },
])('postponement rejects removed replacement-slot input regardless of its interval: $date $from', async lastSlot => {
  const before = mockDb.read()
  await expect(api.sessionService.previewPostponement({ sessionId: 's1', lastSlot })).rejects.toThrow()
  const preview = await api.sessionService.previewPostponement({ sessionId: 's1' })
  await expect(api.sessionService.postpone({ sessionId: 's1', expected: preview.expected, requestKey: 'obsolete-input', lastSlot })).rejects.toThrow()
  expect(mockDb.read()).toEqual(before)
})
it('rejects old version-3 postponed-slot tokens without a partial write', async () => {
  const before = mockDb.read()
  await expect(api.sessionService.postpone({ sessionId: 's1', expected: JSON.stringify({ version: 3 }), requestKey: 'legacy' })).rejects.toThrow('changed')
  expect(mockDb.read()).toEqual(before)
  mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus')
  await postpone()
  const request = mockDb.read().messages.find(item => item.request?.type === 'session_postpone')
  mockDb.mutate(db => { const stored = db.messages.find(item => item.id === request.id); stored.request.expected = JSON.stringify({ version: 3 }); stored.request.lastSlot = { date: '2026-10-26', from: '10:00', to: '11:00' } })
  login(); const legacyPending = mockDb.read()
  await expect(api.requestService.resolve({ id: request.id, decision: 'approved' })).rejects.toThrow('obsolete')
  expect(mockDb.read()).toEqual(legacyPending)
})
it('repeated postponement cannot duplicate an open session or its credit', async () => {
  await postpone(); const before = mockDb.read()
  await expect(postpone('s1', 'new-key')).rejects.toThrow('upcoming')
  expect(mockDb.read()).toEqual(before)
})
it.each([false, true])('scheduling an open session revalidates approval (new conflict=%s)', async conflict => {
  await postpone(); mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus')
  const next = { date: '2026-10-13', from: '13:00', to: '14:00' }
  await api.sessionService.requestTimeChange({ sessionId: 's1', patch: next })
  const request = mockDb.read().messages.find(item => item.request?.type === 'session_time'); login()
  if (conflict) mockDb.mutate(db => { db.sessions.push({ ...db.sessions[1], ...next, id: 'occupied', clientId: 'c2', packageId: db.clients[1].package.id }) })
  const before = mockDb.read()
  expect(session().scheduleState).toBe('open')
  if (conflict) {
    await expect(api.requestService.resolve({ id: request.id, decision: 'approved' })).rejects.toThrow('conflicts')
    expect(mockDb.read()).toEqual(before)
  } else {
    await api.requestService.resolve({ id: request.id, decision: 'approved' })
    expect(session()).toMatchObject({ ...next, scheduleState: 'scheduled', sessionNumber: 2 })
  }
})

it.each(['postpone-and-schedule', 'bring-last-forward'])('keeps 12/2/10 credits and chronological identity in the agreed example: %s', async scenario => {
  mockDb.mutate(db => {
    const original = db.sessions[0], person = db.clients.find(item => item.id === 'c1')
    Object.assign(person.package, { total: 12, used: 2 })
    db.sessions = Array.from({ length: 12 }, (_, index) => ({ ...original, id: `example-${index + 1}`, sessionNumber: index + 1,
      date: `2026-10-${String(index < 2 ? index + 1 : index + 2).padStart(2, '0')}`, status: index < 2 ? 'completed' : 'planned',
      acknowledgement: index < 2 ? { method: 'late_no_show' } : null, exercisePlan: [{ id: `plan-${index + 1}`, name: `Plan ${index + 1}` }] }))
    db.sessions[2].date = '2026-10-04'; db.sessions[3].date = '2026-10-05'
    db.sessions[4].date = '2026-10-06'; db.sessions[5].date = '2026-10-07'
    db.packageCreditTransactions = db.sessions.slice(0, 2).map(item => ({ id: `debit-${item.id}`, type: 'session_debit', sessionId: item.id, clientId: 'c1', packageId: person.package.id, amount: -1 }))
  })
  const before = mockDb.read(), selected = scenario === 'bring-last-forward' ? 'example-12' : 'example-3'
  let postponementMessage
  if (scenario === 'postpone-and-schedule') {
    await postpone(selected); postponementMessage = latestMessage()
    expect(session(selected)).toMatchObject({ scheduleState: 'open', date: null, sessionNumber: null })
    expect(mockDb.read().sessions.slice(3).map(item => item.sessionNumber)).toEqual([3, 4, 5, 6, 7, 8, 9, 10, 11])
  }
  const beforeScheduling = mockDb.read()
  // After postponement, current positions 5 and 6 are original IDs 6 and 7.
  const targetDate = scenario === 'bring-last-forward' ? '2026-10-06' : '2026-10-07'
  await api.sessionService.updateDetails({ sessionId: selected, patch: { date: targetDate, from: '13:00', to: '14:00', trainerId: 't1' } })
  expect(session(selected).sessionNumber).toBe(6)
  const after = mockDb.reload()
  expect(after.sessions).toHaveLength(12)
  expect(after.clients.find(item => item.id === 'c1').package).toEqual(before.clients.find(item => item.id === 'c1').package)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  for (const item of after.sessions) {
    const original = before.sessions.find(old => old.id === item.id)
    expect(item.exercisePlan).toEqual(original.exercisePlan)
    if (item.id !== selected) expect([item.date, item.from, item.to]).toEqual([original.date, original.from, original.to])
  }
  if (scenario === 'bring-last-forward') expect(after.sessions.slice(5, 11).map(item => item.sessionNumber)).toEqual([7, 8, 9, 10, 11, 12])
  if (postponementMessage) await expect(undo(postponementMessage)).rejects.toThrow('changed')
  await undo(); expect(mockDb.read().sessions).toEqual(beforeScheduling.sessions)
  if (postponementMessage) { await undo(postponementMessage); expect(mockDb.read().sessions).toEqual(before.sessions) }
})

it('retains multiple open sessions after reload without making them completable', async () => {
  await postpone('s1', 'first'); await postpone('s2', 'second')
  const before = mockDb.reload()
  expect(before.sessions.slice(0, 2).map(item => [item.scheduleState, item.date, item.sessionNumber])).toEqual([['open', null, null], ['open', null, null]])
  await expect(api.sessionService.acknowledge({ sessionId: 's1', acknowledgement: signed })).rejects.toThrow('Schedule this open session')
  expect(mockDb.read()).toEqual(before)
})

it('deduplicates pending and applied open-session scheduling submissions', async () => {
  await postpone(); mockDb.mutate(db => { db.trainers[0].approvalNeeded.sessionTime = true }); login('u-marcus')
  const input = { sessionId: 's1', patch: { date: '2026-10-13', from: '13:00', to: '14:00' } }
  await api.sessionService.requestTimeChange(input); const pending = mockDb.read()
  await api.sessionService.requestTimeChange(input); expect(mockDb.read()).toEqual(pending)
  login(); await api.requestService.resolve({ id: pending.messages.find(item => item.request?.type === 'session_time').id, decision: 'approved' })
  const applied = mockDb.read(); login('u-marcus')
  await api.sessionService.requestTimeChange(input); expect(mockDb.read()).toEqual(applied)
})

it('keeps numbering-only effects on another trainer session reversible by the original trainer', async () => {
  mockDb.mutate(db => { db.sessions[1].trainerId = 't2' }); login('u-marcus')
  const before = mockDb.read(); await postpone(); await undo()
  expect(mockDb.read().sessions).toEqual(before.sessions)
})


it('retains undated sessions through client deactivation and reactivation without inventing bookings', async () => {
  await postpone()
  const open = session(), credits = mockDb.read().packageCreditTransactions
  await api.clientService.deactivate({ id: 'c1' })
  await expect(api.sessionService.updateDetails({ sessionId: 's1', patch: { date: '2026-10-13', from: '13:00', to: '14:00', trainerId: 't1' } })).rejects.toThrow()
  await api.clientService.reactivate({ id: 'c1' })
  expect(session()).toEqual(open)
  expect(mockDb.reload().packageCreditTransactions).toEqual(credits)
})

it('permanently reassigns open sessions without dates and reverses the assignment atomically', async () => {
  const { trainerReassignmentSnapshot } = await import('../app/trainerReassignment.js')
  const { businessClock } = await import('../app/clock.js')
  await postpone()
  mockDb.mutate(db => { db.trainers.find(item => item.id === 't2').availability = Object.fromEntries(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => [day, [['06:00', '23:00']]])) })
  const before = mockDb.read()
  await api.clientService.reassignTrainer({ id: 'c1', draft: { requestId: 'open-reassign', trainerId: 't2', expected: trainerReassignmentSnapshot(client(), before.sessions, before.packageCreditTransactions, businessClock(new Date(), before.settings.timeZone)) } })
  expect(session()).toMatchObject({ scheduleState: 'open', trainerId: 't2', date: null, from: null, to: null, sessionNumber: null })
  await undo(mockDb.read().messages.findLast(item => item.mutationId && item.recipientRole === 'owner'))
  expect(mockDb.reload().sessions).toEqual(before.sessions)
  expect(mockDb.read().packageCreditTransactions).toEqual(before.packageCreditTransactions)
})
