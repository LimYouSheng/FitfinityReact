import { DEFAULT_PACKAGES } from './packages.js'
import { describe, expect, it } from 'vitest'
import {
  CLIENT_ONBOARDING_STEPS,
  clientStepErrors,
  validateClientDraft,
  buildClientRecord,
  buildClientSessions,
  buildFixedWeeklySchedule,
  matchTrainers,
  packageFor,
} from './clientOnboarding.js'

const trainers = [
  {
    id: 't1', status: 'active', name: 'Marcus Tan', gender: 'Male',
    availability: {
      Monday: [['18:00', '21:00']],
      Wednesday: [['18:00', '21:00']],
    },
  },
  {
    id: 't2', status: 'active', name: 'Rachel Ong', gender: 'Female',
    availability: {
      Monday: [['18:00', '21:00']],
      Wednesday: [['18:00', '21:00']],
    },
  },
  {
    id: 't3', status: 'inactive', name: 'Inactive Trainer', gender: 'Female',
    availability: {
      Monday: [['00:00', '23:59']],
      Wednesday: [['00:00', '23:59']],
    },
  },
]

const preferences = [
  { id: 'p1', days: ['Monday', 'Wednesday'], from: '18:00', to: '19:00' },
]

describe('M3 client onboarding domain', () => {
  it('uses session-count packages with independent weekly frequency and matching validity', () => {
    expect(packageFor('2026-09-07', 1)).toEqual({
      durationWeeks: 12,
      sessionsPerWeek: 1,
      total: 12,
      freeGym: false,
      used: 0,
      startDate: '2026-09-07',
      validityDays: 90,
      endDate: '2026-12-05',
    })
    expect(packageFor('2026-09-07', 2).total).toBe(12)
    expect(packageFor('2026-09-07', 2, DEFAULT_PACKAGES[1])).toMatchObject({ total: 24, validityDays: 180, durationWeeks: 12, freeGym: true })
  })

  it('matches active trainers only and respects trainer gender preference', () => {
    expect(matchTrainers(trainers, preferences).map(result => result.trainer.id)).toEqual(['t1', 't2'])
    expect(
      matchTrainers(trainers, preferences, 'Female trainer preferred').map(result => result.trainer.id)
    ).toEqual(['t2'])
  })

  it('builds fixed weekly slots only where the trainer covers the full range', () => {
    expect(buildFixedWeeklySchedule(trainers[0], preferences, 2)).toEqual([
      { id: 'new-slot-1', day: 'Monday', from: '18:00', to: '19:00' },
      { id: 'new-slot-2', day: 'Wednesday', from: '18:00', to: '19:00' },
    ])
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    const dailyTrainer = { ...trainers[0], availability: Object.fromEntries(days.map(day => [day, [['18:00', '21:00']]])) }
    const blocks = [{ days, from: '18:00', to: '19:00' }]
    for (let frequency = 1; frequency <= 7; frequency += 1) {
      expect(buildFixedWeeklySchedule(dailyTrainer, blocks, frequency)).toHaveLength(frequency)
      expect(clientStepErrors({ sessionsPerWeek: frequency, startDate: '2026-09-07' }, 'package')).toEqual({})
    }
  })

  it('creates all 24 twice-weekly session records inside the 180-day validity', () => {
    const client = buildClientRecord({
      type: 'Individual',
      people: [{
        name: 'M3 Client',
        phone: { countryCode: '+65', number: '' },
        emergencyContact: { name: '', relationship: 'Spouse', countryCode: '+65', number: '' },
      }],
      startDate: '2026-09-07',
      trainerId: 't1',
      genderPreference: 'No gender preference',
      sessionsPerWeek: 2,
      clientPreferences: preferences,
      fixedWeeklySchedule: buildFixedWeeklySchedule(trainers[0], preferences, 2),
      remarks: '',
    }, 'c99', DEFAULT_PACKAGES[1])

    const sessions = buildClientSessions(client)
    expect(sessions).toHaveLength(24)
    expect(sessions[0]).toMatchObject({ sessionNumber: 1, packageTotal: 24 })
    expect(sessions.at(-1).sessionNumber).toBe(24)
    expect(sessions.every(session => session.date <= client.package.endDate)).toBe(true)
  })
})


describe('M3 sequential client validation', () => {
  const draft = () => ({
    type: 'Individual', people: [{ name: 'New Client' }, { name: '' }],
    startDate: '2026-09-07', sessionsPerWeek: 1,
    clientPreferences: preferences, trainerId: 't1',
    fixedWeeklySchedule: buildFixedWeeklySchedule(trainers[0], preferences, 1),
  })

  it('uses the existing four named sections in the correct order', () => {
    expect(CLIENT_ONBOARDING_STEPS.map(step => step.title)).toEqual([
      'General Information', 'Package & Preferences', 'Client Availability', 'Trainer Matching',
    ])
  })

  it('validates only the current section and leaves optional contacts and birthday optional', () => {
    expect(clientStepErrors({ type: 'Individual', people: [{ name: 'Client' }] }, 'general')).toEqual({})
    expect(clientStepErrors({ type: 'Individual', people: [{ name: '  ' }] }, 'general')).toEqual({ 'people.0.name': 'Client name is required.' })
  })

  it('requires both couple names without creating another account or demanding optional fields', () => {
    const value = { ...draft(), type: 'Couple' }
    expect(clientStepErrors(value, 'general')).toEqual({ 'people.1.name': 'Client 2 name is required.' })
    value.people[1].name = 'Second Client'
    expect(clientStepErrors(value, 'general')).toEqual({})
  })

  it('blocks missing or impossible start dates and unsupported weekly frequency', () => {
    expect(clientStepErrors({ ...draft(), startDate: '' }, 'package')).toEqual({ startDate: 'Start date is required.' })
    expect(clientStepErrors({ ...draft(), startDate: '2026-02-30' }, 'package').startDate).toBeTruthy()
    expect(clientStepErrors({ ...draft(), sessionsPerWeek: 8 }, 'package').sessionsPerWeek).toBeTruthy()
  })

  it('requires added availability with valid days and times', () => {
    expect(clientStepErrors({ ...draft(), clientPreferences: [] }, 'availability').availability).toBeTruthy()
    expect(clientStepErrors({ ...draft(), clientPreferences: [{ days: ['Monday'], from: '19:00', to: '18:00' }] }, 'availability').availability).toBeTruthy()
    expect(clientStepErrors(draft(), 'availability')).toEqual({})
  })

  it('requires two distinct possible days for twice-weekly training', () => {
    expect(clientStepErrors({ ...draft(), sessionsPerWeek: 2, clientPreferences: [{ days: ['Monday'], from: '18:00', to: '19:00' }] }, 'availability').availability).toBeTruthy()
    expect(clientStepErrors({ ...draft(), sessionsPerWeek: 2 }, 'availability')).toEqual({})
  })

  it('blocks creation without a trainer or without enough matched weekly slots', () => {
    expect(clientStepErrors({ ...draft(), trainerId: '' }, 'matching').trainerId).toBeTruthy()
    expect(clientStepErrors({ ...draft(), sessionsPerWeek: 2 }, 'matching').fixedWeeklySchedule).toBeTruthy()
  })

  it('reuses every section rule during final service validation', () => {
    expect(validateClientDraft(draft())).toEqual([])
    const invalid = { ...draft(), startDate: '', trainerId: '' }
    expect(validateClientDraft(invalid)).toEqual(['Start date is required.', 'Choose a matched trainer.'])
  })
})

describe('M3 automatic trainer selection', () => {
  it('prefers a full cadence match when entering the matching section', async () => {
    const { defaultMatchingTrainer } = await import('./clientOnboarding.js')
    const partial = { ...trainers[0], availability: { Monday: [['18:00', '21:00']] } }
    const ranked = matchTrainers([partial, trainers[1]], preferences)
    expect(defaultMatchingTrainer(ranked, preferences, 2)).toBe('t2')
  })

  it('keeps a valid choice and leaves no-results unselected', async () => {
    const { defaultMatchingTrainer } = await import('./clientOnboarding.js')
    const ranked = matchTrainers(trainers, preferences)
    expect(defaultMatchingTrainer(ranked, preferences, 1, 't2')).toBe('t2')
    expect(defaultMatchingTrainer([], preferences, 1, 't3')).toBe('')
  })
})
