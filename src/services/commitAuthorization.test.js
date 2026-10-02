import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as database from './mockDb.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { MOCK_SESSION_KEY } from './authService.js'
import * as videoStore from './exerciseVideoStore.js'
import { exerciseLibraryMedia } from './exerciseLibraryMedia.js'

const { mockDb } = database
const api = createPortalServices(mockPortalAdapter)
const login = userId => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId, expiresAt: Date.now() + 3600000 }))
const unchanged = before => { expect(mockDb.read()).toEqual(before); expect(mockDb.reload()).toEqual(before) }
const deferred = () => { let release; const promise = new Promise(resolve => { release = resolve }); return { promise, release } }
beforeEach(() => {
  localStorage.clear(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
  mockDb.reset(); vi.spyOn(database, 'delay').mockResolvedValue(); login('u-marcus')
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); localStorage.clear() })
const writes = [
  ['saveOutcome', { outcome: { trainerComments: 'Must not persist' } }],
  ['saveClientSummary', { summary: 'Must not persist' }],
  ['saveExercisePlan', { items: [{ name: 'New exercise' }] }],
  ['copyPreviousPlan', {}],
  ['markWhatsAppOpened', {}],
  ['requestTimeChange', { patch: { date: '2026-09-10', from: '10:00', to: '11:00' } }],
  ['requestTrainerChange', { replacementTrainerId: 't2' }],
]
it.each(writes.flatMap(([operation, input]) => ['account disabled', 'session reassigned', 'trainer disabled'].map(reason => [operation, input, reason])))('%s rejects a pending save when %s / %s', async (operation, input, reason) => {
  const wait = deferred(), entered = deferred()
  database.delay.mockImplementationOnce(() => { entered.release(); return wait.promise })
  const pending = api.sessionService[operation]({ sessionId: 's1', ...input })
  await entered.promise
  mockDb.mutate(db => {
    if (reason === 'account disabled') db.users.find(u => u.id === 'u-marcus').status = 'inactive'
    if (reason === 'session reassigned') db.sessions.find(s => s.id === 's1').trainerId = 't2'
    if (reason === 'trainer disabled') db.trainers.find(t => t.id === 't1').status = 'inactive'
  })
  const before = mockDb.read(); wait.release()
  await expect(pending).rejects.toThrow(/active|unavailable/); unchanged(before)
})
it('rechecks client assignment before committing coaching notes', async () => {
  const wait = deferred(), entered = deferred()
  database.delay.mockImplementationOnce(() => { entered.release(); return wait.promise })
  const pending = api.clientService.update({ id: 'c1', patch: { remarks: 'Must not persist' } })
  await entered.promise
  mockDb.mutate(db => { db.clients.find(c => c.id === 'c1').trainerId = 't2' })
  const before = mockDb.read(); wait.release()
  await expect(pending).rejects.toThrow('unavailable'); unchanged(before)
})
it.each([
  ['sessionService', 'updateDetails', { sessionId: 's1', patch: { date: '2026-09-10', from: '10:00', to: '11:00', trainerId: 't1' } }],
  ['trainerService', 'reactivate', { id: 't2' }],
])('rechecks operations access for %s.%s after the request starts', async (service, operation, input) => {
  login('u-owner')
  const wait = deferred(), entered = deferred()
  database.delay.mockImplementationOnce(() => { entered.release(); return wait.promise })
  const pending = api[service][operation](input); await entered.promise
  mockDb.mutate(db => { db.users.find(u => u.id === 'u-owner').status = 'inactive' })
  const before = mockDb.read(); wait.release()
  await expect(pending).rejects.toThrow('active staff'); unchanged(before)
})
function attachVideo() {
  mockDb.mutate(db => { db.sessions.find(s => s.id === 's1').exercisePlan = [{ id: 'video', name: 'Row', videoAttached: true,
    video: { id: 'old-blob', attachedAt: '2026-09-02T03:00:00Z', expiresAt: '2026-09-09T03:00:00Z' } }] })
}
it('rolls back a newly stored video if access was removed during upload, preserving old media', async () => {
  attachVideo(); const wait = deferred(), entered = deferred()
  vi.spyOn(videoStore, 'saveExerciseVideoBlob').mockImplementation(() => { entered.release(); return wait.promise })
  const remove = vi.spyOn(videoStore, 'removeExerciseVideoBlob').mockResolvedValue()
  const pending = api.sessionService.saveVideo({ sessionId: 's1', exerciseId: 'video', file: new Blob(['new'], { type: 'video/webm' }), metadata: { duration: 10, audioIncluded: false } })
  await entered.promise
  mockDb.mutate(db => { db.sessions.find(s => s.id === 's1').trainerId = 't2' })
  const before = mockDb.read(); wait.release('new-blob')
  await expect(pending).rejects.toThrow('unavailable'); unchanged(before)
  expect(remove).toHaveBeenCalledExactlyOnceWith('s1', 'video', 'new-blob')
})
it('does not return private session media if the trainer loses access while loading it', async () => {
  attachVideo(); const wait = deferred(), entered = deferred()
  vi.spyOn(videoStore, 'loadExerciseVideoBlob').mockImplementation(() => { entered.release(); return wait.promise })
  const pending = api.sessionService.loadVideo({ sessionId: 's1', exerciseId: 'video' }); await entered.promise
  mockDb.mutate(db => { db.sessions.find(s => s.id === 's1').trainerId = 't2' })
  wait.release(new Blob(['video']))
  await expect(pending).rejects.toThrow('unavailable')
})
it('returns playable Blobs to Admin for both media services while keeping trainer pay fields hidden', async () => {
  attachVideo()
  const blob = new Blob(['video'], { type: 'video/webm' })
  vi.spyOn(videoStore, 'loadExerciseVideoBlob').mockResolvedValue(blob)
  vi.spyOn(exerciseLibraryMedia, 'load').mockResolvedValue(blob)
  mockDb.mutate(db => { db.users.push({ id: 'test-admin', role: 'admin', name: 'Admin', status: 'active' }) })
  login('test-admin')
  expect(await api.sessionService.loadVideo({ sessionId: 's1', exerciseId: 'video' })).toBe(blob)
  expect(await api.exerciseLibraryService.loadMedia({ id: 'library-media' })).toBe(blob)
  const trainer = await api.trainerService.getById({ id: 't1' })
  expect(trainer.name).toBeTruthy(); expect(trainer).not.toHaveProperty('rates')
  await expect(api.trainerService.update({ id: 't1', patch: { rates: { peak: 99, offPeak: 88 } } })).rejects.toThrow('restricted')
})
it.each([
  { date: '2026-02-31' }, { date: '2026-02-29' }, { date: '2026-13-01' }, { date: 'bad' },
  { from: '25:00', to: '26:00' }, { from: '09:60' }, { from: '9:00' }, { from: '11:00', to: '10:00' }, { from: '10:00', to: '10:00' },
])('rejects an invalid operations schedule %j without changing records', async invalid => {
  login('u-owner'); const before = mockDb.read()
  await expect(api.sessionService.updateDetails({ sessionId: 's1', patch: { date: '2026-09-10', from: '10:00', to: '11:00', trainerId: 't1', ...invalid } })).rejects.toThrow('valid date')
  unchanged(before)
})
it('accepts a real leap day and arbitrary positive session duration', async () => {
  login('u-owner')
  const result = await api.sessionService.updateDetails({ sessionId: 's1', patch: { date: '2028-02-29', from: '10:05', to: '11:40', trainerId: 't1' } })
  expect(result).toMatchObject({ date: '2028-02-29', from: '10:05', to: '11:40' })
})
