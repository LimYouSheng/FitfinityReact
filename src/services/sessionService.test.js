import { signatureFixture } from '../test/fixtures/signature.js'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'

const acknowledgementActor = () => mockDb.read().users.find(user => user.role === 'owner')

describe('session service', () => {
  beforeEach(() => {
    mockDb.reset()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-09T04:00:00Z'))
  })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('saves a valid plan and changes Not Planned to Planned', async () => {
    await sessionService.saveExercisePlan('s2', [{
      id: 'draft-1', name: 'Romanian Deadlift', weight: '24 kg', customDetails: [], reps: '8', rounds: '3', rest: '75 sec',
      videoAttached: true,
      video: { name: 'deadlift.webm', type: 'video/webm', size: 2048, duration: 18, source: 'recorded', audioIncluded: false },
    }])

    const session = mockDb.read().sessions.find(item => item.id === 's2')
    expect(session.status).toBe('planned')
    expect(session.exercisePlan[0].name).toBe('Romanian Deadlift')
    expect(session.exercisePlan[0].video).toMatchObject({ name: 'deadlift.webm', duration: 18, audioIncluded: false })
  })

  it('copies the most recent previous plan into a new owned plan', async () => {
    await sessionService.copyPreviousPlan('s1')
    const session = mockDb.read().sessions.find(item => item.id === 's1')

    expect(session.exercisePlan.map(item => item.name)).toEqual(['Goblet Squat', 'Seated Cable Row'])
    expect(session.copiedFromSessionId).toBe('s0')
    expect(session.exercisePlan[0].id).not.toBe('exercise-s0-1')
  })

  it('preserves a client signature and timestamp permanently, with a write-free retry and one debit', async () => {
    const input = { method: 'signature', signerName: 'Amanda Lim', signature: signatureFixture }
    const actor = acknowledgementActor()
    const original = await sessionService.acknowledge('s1', input, actor)
    const saved = mockDb.read()
    const persist = vi.spyOn(Storage.prototype, 'setItem')
    vi.setSystemTime(new Date('2026-09-10T04:00:00Z'))
    expect(await sessionService.acknowledge('s1', input, actor)).toEqual(original)
    for (const replacement of [
      { method: 'late_no_show', note: 'Pressed incorrectly' },
      { ...input, signerName: 'Someone else' },
      { ...input, note: 'Replacement note' },
      { ...input, signature: signatureFixture.map(stroke => stroke.map(point => ({ ...point, x: point.x + 1 }))) },
    ]) await expect(sessionService.acknowledge('s1', replacement, actor)).rejects.toThrow(/preserv|permanent|already|replac|chang|irreversible/i)
    expect(persist).not.toHaveBeenCalled()
    expect(mockDb.reload()).toEqual(saved)

    const db = mockDb.read()
    const session = db.sessions.find(item => item.id === 's1')
    const client = db.clients.find(item => item.id === 'c1')
    const debits = db.packageCreditTransactions.filter(item => item.sessionId === 's1')

    expect(session.status).toBe('completed')
    expect(session.acknowledgement).toMatchObject({
      ...input, recordedAt: '2026-09-09T04:00:00.000Z',
      recordedBy: { id: actor.id, name: actor.name, role: actor.role },
    })
    expect(session.acknowledgementHistory).toEqual([session.acknowledgement])
    expect(client.package.used).toBe(4)
    expect(debits).toHaveLength(1)
  })

  it('completes a no-show and permits only correction to a signature with immutable timestamped evidence', async () => {
    const actor = mockDb.read().users.find(user => user.id === 'u-marcus')
    const input = { method: 'late_no_show', note: 'Client did not arrive' }
    const result = await sessionService.acknowledge('s2', input, actor)

    expect(result.session.status).toBe('completed')
    expect(result.session.acknowledgement.signerName).toBe('')
    expect(result.transactions).toHaveLength(1)
    const original = structuredClone(result.session.acknowledgement)
    expect(original).toMatchObject({
      recordedAt: '2026-09-09T04:00:00.000Z',
      recordedBy: { id: 'u-marcus', name: 'Marcus Tan', role: 'trainer' },
    })
    const saved = mockDb.read()
    const persist = vi.spyOn(Storage.prototype, 'setItem')
    vi.setSystemTime(new Date('2026-09-09T04:10:00Z'))
    expect(await sessionService.acknowledge('s2', input, actor)).toEqual(result)
    await expect(sessionService.acknowledge('s2', { ...input, note: 'Erase prior note' }, actor)).rejects.toThrow()
    expect(persist).not.toHaveBeenCalled()
    expect(mockDb.read()).toEqual(saved)
    const correction = { method: 'signature', signerName: 'Amanda Lim', signature: signatureFixture, note: 'Recorded no-show by mistake' }
    persist.mockImplementationOnce(() => { throw new Error('Storage full') })
    await expect(sessionService.acknowledge('s2', correction, actor)).rejects.toThrow('Storage full')
    expect(mockDb.reload()).toEqual(saved)
    const corrected = await sessionService.acknowledge('s2', correction, actor)
    expect(corrected.session.acknowledgementHistory).toEqual([original, corrected.session.acknowledgement])
    expect(corrected.session.acknowledgement).toMatchObject({
      method: 'signature', recordedAt: '2026-09-09T04:10:00.000Z', recordedBy: original.recordedBy,
    })
    expect(corrected.transactions).toEqual(result.transactions)
    expect(mockDb.read().clients.find(client => client.id === 'c1').package.used).toBe(4)
    expect(mockDb.read().messages.length).toBe(saved.messages.length + 1)
  })

  it('requires an active stored owner or assigned trainer and rejects forged acknowledgement identities atomically', async () => {
    const input = { method: 'late_no_show' }
    const before = mockDb.read()
    const trainer = before.users.find(user => user.id === 'u-marcus')
    const other = before.users.find(user => user.id === 'u-aisha')
    for (const actor of [undefined, { role: 'owner' }, { ...trainer, role: 'owner' }, { ...trainer, trainerId: other.trainerId }, other]) {
      await expect(sessionService.acknowledge('s1', input, actor)).rejects.toThrow()
      expect(mockDb.read()).toEqual(before)
    }
    mockDb.mutate(db => { db.users.find(user => user.id === trainer.id).status = 'inactive' })
    const inactive = mockDb.read()
    await expect(sessionService.acknowledge('s1', input, trainer)).rejects.toThrow('active')
    expect(mockDb.read()).toEqual(inactive)
  })

  it('persists session outcome, client summary and repeatable WhatsApp sends', async () => {
    await sessionService.saveOutcome('s1', { durationMinutes: 55, trainerComments: 'Technique remained consistent.' })
    await sessionService.saveClientSummary('s1', 'Custom client-ready summary.')
    await sessionService.markWhatsAppOpened('s1')
    await sessionService.markWhatsAppOpened('s1')

    const session = mockDb.read().sessions.find(item => item.id === 's1')
    expect(session.outcome).toEqual({ durationMinutes: 55, trainerComments: 'Technique remained consistent.' })
    expect(session.clientSummary).toBe('Custom client-ready summary.')
    expect(session.whatsappOpenedAt).toBeTruthy()
    expect(session.whatsappOpenCount).toBe(2)
  })

  it('lets the owner update schedule and trainer details directly', async () => {
    await sessionService.updateDetails('s1', {
      date: '2026-09-03',
      from: '19:00',
      to: '20:00',
      trainerId: 't2',
    })

    const session = mockDb.read().sessions.find(item => item.id === 's1')
    expect(session).toMatchObject({ date: '2026-09-03', from: '19:00', to: '20:00', trainerId: 't2' })
  })

  it('keeps supervised trainer requests pending without changing the session', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-02T09:59:00Z'))
    const actor = { role: 'trainer', trainerId: 't1' }
    const future = { date: '2026-09-04', from: '17:00', to: '18:00' }
    const before = mockDb.read()
    for (const past of [
      { date: '2026-09-01', from: '18:00', to: '19:00' },
      { date: '2026-09-02', from: '17:00', to: '18:00' },
      { date: '2026-09-02', from: '17:59', to: '19:00' },
    ]) {
      await expect(sessionService.requestTimeChange('s1', actor, past)).rejects.toThrow('in the future')
      expect(mockDb.read()).toEqual(before)
    }
    for (const status of ['completed', 'cancelled']) {
      mockDb.mutate(db => { db.sessions.find(item => item.id === 's1').status = status })
      const locked = mockDb.read()
      await expect(sessionService.requestTimeChange('s1', actor, future)).rejects.toThrow(/locked|cannot request/)
      expect(mockDb.read()).toEqual(locked)
    }
    mockDb.write(before)
    vi.setSystemTime(new Date('2026-09-02T10:00:00Z'))
    await expect(sessionService.requestTimeChange('s1', actor, future)).rejects.toThrow('before the session starts')
    expect(mockDb.read()).toEqual(before)
    // The same instant is still before this session in the configured UTC gym.
    mockDb.mutate(db => { db.settings.timeZone = 'UTC' })
    const timeResult = await sessionService.requestTimeChange(
      's1',
      actor,
      future,
    )
    const trainerResult = await sessionService.requestTrainerChange(
      's1',
      { role: 'trainer', trainerId: 't1' },
      't2',
    )

    const db = mockDb.read()
    const session = db.sessions.find(item => item.id === 's1')
    expect(timeResult.outcome).toBe('requested')
    expect(trainerResult.outcome).toBe('requested')
    expect(session).toMatchObject({ date: '2026-09-02', from: '18:00', to: '19:00', trainerId: 't1' })
    expect(db.messages.some(message => message.request?.type === 'session_time')).toBe(true)
    expect(db.messages.some(message => message.request?.type === 'session_trainer')).toBe(true)
  })

  it('applies autonomous trainer changes directly', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-06T16:00:00Z'))
    mockDb.mutate(db => {
      db.sessions.find(item => item.id === 's2').trainerId = 't3'
    })
    const before = mockDb.read()
    for (const past of [
      { date: '2026-09-06', from: '23:00', to: '23:30' },
      { date: '2026-09-07', from: '00:00', to: '01:00' },
    ]) {
      await expect(sessionService.requestTimeChange('s2', { role: 'trainer', trainerId: 't3' }, past)).rejects.toThrow('in the future')
      expect(mockDb.read()).toEqual(before)
    }

    const timeResult = await sessionService.requestTimeChange(
      's2',
      { role: 'trainer', trainerId: 't3' },
      { date: '2026-09-08', from: '17:00', to: '18:00' },
    )
    const trainerResult = await sessionService.requestTrainerChange(
      's2',
      { role: 'trainer', trainerId: 't3' },
      't4',
    )

    const session = mockDb.read().sessions.find(item => item.id === 's2')
    expect(timeResult.outcome).toBe('applied')
    expect(trainerResult.outcome).toBe('applied')
    expect(session).toMatchObject({ date: '2026-09-08', from: '17:00', to: '18:00', trainerId: 't4' })
  })
})
