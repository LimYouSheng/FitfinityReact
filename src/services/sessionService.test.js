import { beforeEach, describe, expect, it } from 'vitest'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'

describe('session service', () => {
  beforeEach(() => mockDb.reset())

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

  it('debits one package credit for a normal acknowledgement and never debits twice', async () => {
    await sessionService.acknowledge('s1', { method: 'signature', signerName: 'Amanda Lim' })
    await sessionService.acknowledge('s1', { method: 'late_no_show', note: 'Converted record' })

    const db = mockDb.read()
    const session = db.sessions.find(item => item.id === 's1')
    const client = db.clients.find(item => item.id === 'c1')
    const debits = db.packageCreditTransactions.filter(item => item.sessionId === 's1')

    expect(session.status).toBe('completed')
    expect(session.acknowledgement.method).toBe('late_no_show')
    expect(client.package.used).toBe(4)
    expect(debits).toHaveLength(1)
  })

  it('completes late/no-show without requiring a signature', async () => {
    const result = await sessionService.acknowledge('s2', { method: 'late_no_show' })

    expect(result.session.status).toBe('completed')
    expect(result.session.acknowledgement.signerName).toBe('')
    expect(result.transactions).toHaveLength(1)
  })

  it('persists session outcome, client summary and repeatable WhatsApp sends', async () => {
    await sessionService.saveOutcome('s1', { durationMinutes: 55, trainerComments: 'Technique remained consistent.' })
    await sessionService.saveClientSummary('s1', 'Custom client-ready summary.')
    await sessionService.markWhatsAppSent('s1')
    await sessionService.markWhatsAppSent('s1')

    const session = mockDb.read().sessions.find(item => item.id === 's1')
    expect(session.outcome).toEqual({ durationMinutes: 55, trainerComments: 'Technique remained consistent.' })
    expect(session.clientSummary).toBe('Custom client-ready summary.')
    expect(session.whatsappSentAt).toBeTruthy()
    expect(session.whatsappSendCount).toBe(2)
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
    const timeResult = await sessionService.requestTimeChange(
      's1',
      { role: 'trainer', trainerId: 't1' },
      { date: '2026-09-04', from: '17:00', to: '18:00' },
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
    mockDb.mutate(db => {
      db.sessions.find(item => item.id === 's2').trainerId = 't3'
    })

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
