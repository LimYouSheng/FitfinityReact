import { signatureFixture } from '../test/fixtures/signature.js'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clientService } from './clientService.js'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'
import { trainerService } from './trainerService.js'

const acknowledgementActor = () => mockDb.read().users.find(user => user.role === 'owner')

describe('saved edit messages', () => {
  beforeEach(() => {
    // Keep the schedule-change fixture before its seeded future sessions.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-05T02:00:00Z'))
    mockDb.reset()
  })
  afterEach(() => vi.useRealTimers())

  it('adds related messages for saved client details and schedules', async () => {
    await clientService.update('c1', { notes: 'Prefers morning sessions.' })
    await clientService.saveFixedWeeklySchedule('c1', [{ day: 'Monday', from: '08:00', to: '09:00' }], mockDb.read().users.find(user => user.role === 'owner'))

    const messages = mockDb.read().messages.filter(message => message.clientId === 'c1' && message.kind === 'saved_edit' || message.title.startsWith('Fixed weekly schedule saved'))
    expect(messages.some(message => message.title === 'Client details saved: Amanda Lim')).toBe(true)
    expect(messages.some(message => message.title === 'Fixed weekly schedule saved: Amanda Lim')).toBe(true)
    expect(messages.every(message => message.read === false)).toBe(true)
  })

  it('adds messages for saved trainer profile and autonomy edits', async () => {
    await trainerService.update('t1', { specialty: 'Strength and conditioning' })
    await trainerService.updateAutonomy('t1', {
      fixedWeeklySchedule: false,
      sessionTime: true,
      trainerReassignment: true,
    })

    const messages = mockDb.read().messages.filter(message => message.recipientTrainerId === 't1')
    expect(messages.some(message => message.title === 'Trainer details saved: Marcus Tan')).toBe(true)
    expect(messages.some(message => message.title === 'Autonomy and approvals saved: Marcus Tan')).toBe(true)
  })

  it('adds a routed message for each saved session section', async () => {
    await sessionService.updateDetails('s1', { date: '2026-09-03', from: '18:00', to: '19:00', trainerId: 't1' })
    await sessionService.saveExercisePlan('s1', [{ id: 'e1', name: 'Goblet Squat', weight: '8 kg', reps: '8', rounds: '2', rest: '60 sec', customDetails: [] }])
    await sessionService.saveOutcome('s1', { durationMinutes: 60, trainerComments: 'Good control.' })
    await sessionService.saveClientSummary('s1', 'Strong session.')
    await sessionService.acknowledge('s1', { method: 'signature', signerName: 'Amanda Lim', signature: signatureFixture }, acknowledgementActor())

    const messages = mockDb.read().messages.filter(message => message.sessionId === 's1' && message.kind === 'saved_edit')
    expect(messages.map(message => message.title)).toEqual(expect.arrayContaining([
      'Session details saved: Amanda Lim',
      'Exercise plan saved: Amanda Lim',
      'Session outcome saved: Amanda Lim',
      'Client-facing summary saved: Amanda Lim',
      'Session acknowledgement saved: Amanda Lim',
    ]))
    expect(messages.every(message => message.clientId === 'c1' && message.recipientTrainerId === 't1')).toBe(true)
  })
})
