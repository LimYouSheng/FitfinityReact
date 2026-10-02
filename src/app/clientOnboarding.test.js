import { mockPolicy } from '../data/mockPolicy.js'

import { DEFAULT_PACKAGES } from '../data/mockPackages.js'
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
    expect(packageFor('2026-09-07', 1, DEFAULT_PACKAGES[0], mockPolicy.freeGymMinimumFrequency)).toEqual({
      durationWeeks: 12,
      sessionsPerWeek: 1,
      total: 12,
      freeGym: false,
      used: 0,
      startDate: '2026-09-07',
      validityDays: 90,
      endDate: '2026-12-05',
    })
    expect(packageFor('2026-09-07', 2, DEFAULT_PACKAGES[0], mockPolicy.freeGymMinimumFrequency).total).toBe(12)
    expect(packageFor('2026-09-07', 2, DEFAULT_PACKAGES[1], mockPolicy.freeGymMinimumFrequency)).toMatchObject({ total: 24, validityDays: 180, durationWeeks: 12, freeGym: true })
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
    }, 'c99', DEFAULT_PACKAGES[1], mockPolicy)

    const sessions = buildClientSessions(client)
    expect(sessions).toHaveLength(24)
    expect(sessions[0]).toMatchObject({ sessionNumber: 1, packageTotal: 24 })
    expect(sessions.at(-1).sessionNumber).toBe(24)
    expect(sessions.every(session => session.date <= client.package.endDate)).toBe(true)
  })
})


describe('M3 sequential client validation', () => {
  const person = (name = 'New Client') => ({ name, phone: { countryCode: '+65', number: '91234567' },
    email: 'client@example.com', birthday: '1990-01-02', gender: 'Female', healthNotes: '',
    emergencyContact: { name: 'Emergency Contact', relationship: 'Spouse', countryCode: '+65', number: '98765432' } })
  const draft = () => ({
    type: 'Individual', people: [person(), person('')],
    startDate: '2026-09-07', sessionsPerWeek: 1,
    clientPreferences: preferences, trainerId: 't1',
    fixedWeeklySchedule: buildFixedWeeklySchedule(trainers[0], preferences, 1),
  })

  it('uses the five named sections in the correct order', () => {
    expect(CLIENT_ONBOARDING_STEPS.map(step => step.title)).toEqual([
      'General Information', 'Health & Assessments', 'Package & Preferences', 'Client Availability', 'Trainer Matching',
    ])
  })

  it('requires every personal field while health notes and remarks remain optional', () => {
    expect(clientStepErrors({ ...draft(), remarks: '' }, 'general')).toEqual({})
    expect(clientStepErrors({ ...draft(), people: [person('  ')] }, 'general')).toEqual({ 'people.0.name': 'Client name is required.' })
    for (const [field, blank, error] of [
      ['phone', { countryCode: '+65', number: '' }, 'phoneNumber'],
      ['phone', { countryCode: '', number: '91234567' }, 'phoneCountryCode'],
      ['email', ' ', 'email'], ['birthday', '', 'birthday'], ['gender', '', 'gender'],
    ]) expect(clientStepErrors({ ...draft(), people: [{ ...person(), [field]: blank }] }, 'general')[`people.0.${error}`]).toBeTruthy()
    for (const [field, error] of [['name', 'emergencyName'], ['relationship', 'emergencyRelationship'], ['countryCode', 'emergencyCountryCode'], ['number', 'emergencyNumber']]) {
      const value = person(); value.emergencyContact[field] = ''
      expect(clientStepErrors({ ...draft(), people: [value] }, 'general')[`people.0.${error}`]).toBeTruthy()
    }
    for (const [field, value] of [['email', 'invalid'], ['birthday', '2026-02-30']]) {
      expect(clientStepErrors({ ...draft(), people: [{ ...person(), [field]: value }] }, 'general')[`people.0.${field}`]).toBeTruthy()
    }
    expect(clientStepErrors({ type: 'Individual', people: [{ name: 'Existing Client' }] }, 'general', { requireComplete: false })).toEqual({})
  })

  it('requires complete information for both couple members without requiring health notes', () => {
    const value = { ...draft(), type: 'Couple' }
    expect(clientStepErrors(value, 'general')).toEqual({ 'people.1.name': 'Client 2 name is required.' })
    value.people[1].name = 'Second Client'
    expect(clientStepErrors(value, 'general')).toEqual({})
    value.people[1].phone.number = ''
    expect(clientStepErrors(value, 'general')).toEqual({ 'people.1.phoneNumber': 'Phone number is required.' })
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

describe('dated booking-aware trainer matching', () => {
  const calendar = overrides => ({ startDate: '2027-06-07', sessionsPerWeek: 1,
    definition: { total: 2, validityDays: 90 }, clients: [], sessions: [], ...overrides })
  const booking = overrides => ({ id: 'booked', clientId: 'other', trainerId: 't1', date: '2027-06-07', from: '18:00', to: '19:00', status: 'planned', ...overrides })
  const matches = (blocks, value) => matchTrainers(trainers, blocks, 'No gender preference', calendar(value))

  it('excludes a trainer occupied on any generated date without changing declared hours', () => {
    const before = structuredClone(trainers)
    expect(matches([{ ...preferences[0], days: ['Monday'] }], { sessions: [booking({ date: '2027-06-14' })] }).map(result => result.trainer.id)).toEqual(['t2'])
    expect(trainers).toEqual(before)
  })
  it('uses another offered day when the first weekly option is occupied', () => {
    expect(matches(preferences, { sessions: [booking()] }).find(result => result.trainer.id === 't1').schedule).toEqual([
      { id: 'new-slot-1', day: 'Wednesday', from: '18:00', to: '19:00' },
    ])
  })
  it('uses another offered time on the same day and allows touching endpoints', () => {
    const blocks = [{ days: ['Monday'], from: '18:00', to: '19:00' }, { days: ['Monday'], from: '19:00', to: '20:00' }]
    expect(matches(blocks, { sessions: [booking()] }).find(result => result.trainer.id === 't1').schedule[0]).toMatchObject({ day: 'Monday', from: '19:00', to: '20:00' })
  })
  it('does not block a date after the purchased session count has been scheduled', () => {
    expect(matches([{ ...preferences[0], days: ['Monday'] }], { sessions: [booking({ date: '2027-06-21' })] }).map(result => result.trainer.id)).toEqual(['t1', 't2'])
  })
  it('keeps a saved renewal cadence unchanged and excludes it when occupied', () => {
    const fixedWeeklySchedule = [{ id: 'saved', day: 'Monday', from: '18:00', to: '19:00' }]
    expect(matches(preferences, { trainerId: 't1', fixedWeeklySchedule, sessions: [booking()] }).map(result => result.trainer.id)).toEqual(['t2'])
    expect(matches(preferences, { trainerId: 't1', fixedWeeklySchedule })[0].schedule).toEqual(fixedWeeklySchedule)
  })
  it('counts completed history in an inactive package while allowing cancelled and inactive unfinished bookings', () => {
    const clients = [{ id: 'other', status: 'inactive', package: { id: 'past', status: 'inactive' } }]
    const blocks = [{ ...preferences[0], days: ['Monday'] }]
    expect(matches(blocks, { clients, sessions: [booking({ status: 'completed', packageId: 'past' })] }).map(result => result.trainer.id)).toEqual(['t2'])
    for (const status of ['planned', 'cancelled']) expect(matches(blocks, { clients, sessions: [booking({ status, packageId: 'past' })] })).toHaveLength(2)
  })
  it('checks renewal client conflicts even when another trainer owns the occupied session', () => {
    expect(matches([{ ...preferences[0], days: ['Monday'] }], { clientId: 'other', sessions: [booking({ trainerId: 't9' })] })).toEqual([])
  })
  it('requires the full cadence and session count to fit the package', () => {
    expect(matches(preferences, { sessionsPerWeek: 2, sessions: [booking()] }).map(result => result.trainer.id)).toEqual(['t2'])
    expect(matches(preferences, { definition: { total: 12, validityDays: 7 } })).toEqual([])
  })
})

it.each(['Individual', 'Couple'])('keeps blank legacy %s details optional while validating every supplied contact value', type => {
  const people = Array.from({ length: type === 'Couple' ? 2 : 1 }, (_, index) => ({ name: `Person ${index}`, phone: { countryCode: '+65', number: '' }, emergencyContact: { countryCode: '+65' } }))
  const draft = { type, people }
  expect(clientStepErrors(draft, 'general', { requireComplete: false })).toEqual({})
  expect(Object.keys(clientStepErrors(draft, 'general')).length).toBeGreaterThan(0)
  for (const [patch, key] of [
    [{ email: 'not-an-email' }, 'email'],
    [{ phone: { countryCode: '+65', number: 'letters-only' } }, 'phoneNumber'],
    [{ phone: { countryCode: '+999', number: '91234567' } }, 'phoneCountryCode'],
    [{ birthday: '2026-02-31' }, 'birthday'],
    [{ emergencyContact: { number: 'letters-only', countryCode: '+65' } }, 'emergencyNumber'],
    [{ emergencyContact: { number: '91234567', countryCode: '+999' } }, 'emergencyCountryCode'],
    [{ emergencyContact: { relationship: 'invalid' } }, 'emergencyRelationship'],
  ]) {
    const index = people.length - 1
    const changed = people.map((person, position) => position === index ? { ...person, ...patch } : person)
    expect(clientStepErrors({ ...draft, people: changed }, 'general', { requireComplete: false })).toHaveProperty(`people.${index}.${key}`)
  }
  const valid = people.map(person => ({ ...person, email: 'valid@example.test', birthday: '2000-02-29', phone: { countryCode: '+65', number: '91234567' }, emergencyContact: { name: 'Contact', relationship: 'Friend', countryCode: '+65', number: '87654321' } }))
  expect(clientStepErrors({ ...draft, people: valid }, 'general', { requireComplete: false })).toEqual({})
})
