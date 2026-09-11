import { mockPolicy } from '../data/mockPolicy.js'

import { DEFAULT_PACKAGES } from '../data/mockPackages.js'
import { describe, expect, it } from 'vitest'
import { CLIENT_ONBOARDING_STEPS, clientStepErrors } from './clientOnboarding.js'
import { TRAINER_ONBOARDING_STEPS, createTrainerDraft, trainerStepErrors } from './trainerOnboarding.js'
import { clientReviewSections, trainerReviewSections, firstIncompleteSection, reviewValue, reviewPhone } from './onboardingReview.js'

const person = (name = 'Amanda') => ({ name, phone: { countryCode: '+65', number: '9123 4567' },
  email: 'amanda@example.com', birthday: '1990-01-02', gender: 'Female', healthNotes: 'Knee notes',
  emergencyContact: { name: 'Jason', relationship: 'Spouse', countryCode: '+60', number: '123456789' } })
const client = () => ({ type: 'Individual', packageDefinition: DEFAULT_PACKAGES[0], people: [person(), person('Hidden draft')],
  startDate: '2026-09-07', sessionsPerWeek: 1, genderPreference: 'Female trainer preferred', remarks: 'Shared remark',
  clientPreferences: [{ days: ['Monday'], from: '18:00', to: '19:00' }], trainerId: 't2',
  fixedWeeklySchedule: [{ day: 'Monday', from: '18:00', to: '19:00' }] })
const trainer = () => ({ ...createTrainerDraft(mockPolicy), phone: { countryCode: '+65', number: '91234567' }, birthday: '1990-01-02', name: '  Review Trainer  ', email: ' REVIEW@EXAMPLE.COM ',
  gender: 'Female', trainerType: 'Personal', qualifications: 'ACE',
  availabilityBlocks: [{ days: ['Monday', 'Wednesday'], from: '18:00', to: '20:00' }] })
const rows = section => Object.fromEntries(section.groups.flatMap(group => group.rows).map(row => [row.label, row.value]))

describe('onboarding review', () => {
  it('displays blank optional values without inventing content and preserves zero', () => {
    expect(reviewValue('  ')).toBe('—')
    expect(reviewValue(null)).toBe('—')
    expect(reviewValue(0)).toBe('0')
    expect(reviewValue('  Line one\nLine two ')).toBe('Line one\nLine two')
    expect(reviewPhone({ countryCode: '+65', number: '' })).toBe('—')
    expect(reviewPhone({ countryCode: '+60', number: '1234567' })).toBe('+60 1234567')
  })
  it('maps every single-client person field while excluding an unused second draft', () => {
    const draft = client(); const snapshot = JSON.stringify(draft)
    const sections = clientReviewSections(draft, { name: 'Rachel' }, mockPolicy)
    expect(sections.map(section => section.key)).toEqual(CLIENT_ONBOARDING_STEPS.map(step => step.key))
    expect(rows(sections[0])).toMatchObject({ 'Client type': 'Single', Name: 'Amanda', Phone: '+65 9123 4567',
      Email: 'amanda@example.com', Birthday: '02 Jan 1990', Gender: 'Female', 'Emergency contact name': 'Jason',
      'Emergency contact relationship': 'Spouse', 'Emergency contact phone': '+60 123456789', 'Health / Limitation Notes': 'Knee notes' })
    expect(JSON.stringify(sections)).not.toContain('Hidden draft')
    expect(JSON.stringify(draft)).toBe(snapshot)
  })
  it('keeps both Couple people and their health and emergency information separate', () => {
    const draft = client(); draft.type = 'Couple'
    draft.people[1] = { ...person('Mei'), healthNotes: 'Shoulder notes', phone: { countryCode: '+44', number: '1234567' } }
    const general = clientReviewSections(draft, { name: 'Rachel' }, mockPolicy)[0]
    expect(general.groups.slice(1).map(group => group.title)).toEqual(['Client 1', 'Client 2'])
    expect(general.groups[1].rows).toContainEqual({ label: 'Health / Limitation Notes', value: 'Knee notes' })
    expect(general.groups[2].rows).toContainEqual({ label: 'Health / Limitation Notes', value: 'Shoulder notes' })
    expect(general.groups[2].rows).toContainEqual({ label: 'Phone', value: '+44 1234567' })
  })
  it('derives package totals, all availability blocks and the selected fixed schedule from current inputs', () => {
    const draft = client(); draft.sessionsPerWeek = 2; draft.packageDefinition = DEFAULT_PACKAGES[1]
    draft.clientPreferences.push({ days: ['Wednesday'], from: '19:00', to: '20:00' })
    draft.fixedWeeklySchedule.push({ day: 'Wednesday', from: '19:00', to: '20:00' })
    const sections = clientReviewSections(draft, { name: 'Chosen Trainer' }, mockPolicy)
    expect(rows(sections[1])).toMatchObject({ 'PT Package': '24 sessions', Validity: '180 days', 'Free gym package': 'Included',
      'Total sessions': '24', 'Weekly frequency': 'Twice per week' })
    expect(rows(sections[0]).Remarks).toBe('Shared remark')
    expect(rows(sections[1])).not.toHaveProperty('Remarks')
    expect(rows(sections[1])['Expiry date']).toContain('Mar')
    expect(sections[2].groups[0].rows).toHaveLength(2)
    expect(rows(sections[3])['Assigned trainer']).toBe('Chosen Trainer')
    expect(rows(sections[3])['Fixed Weekly Schedule']).toBe('Monday · 18:00–19:00\nWednesday · 19:00–20:00')
  })
  it('shows trainer rates including zero, all profile fields and the meaning of every approval control', () => {
    const draft = trainer(); draft.rates = { peak: '85.50', offPeak: '0' }; draft.approvalNeeded.sessionTime = false
    const sections = trainerReviewSections(draft)
    expect(sections.map(section => section.key)).toEqual(TRAINER_ONBOARDING_STEPS.map(step => step.key))
    expect(rows(sections[0])).toMatchObject({ 'Trainer name': 'Review Trainer', Email: 'review@example.com',
      Phone: '+65 91234567', Birthday: '02 Jan 1990', Gender: 'Female', 'Trainer type': 'Personal', Qualifications: 'ACE', 'Public profile': 'Visible' })
    expect(rows(sections[1])).toEqual({ 'Peak session rate': 'S$85.50 / session', 'Off-peak session rate': 'S$0.00 / session' })
    expect(rows(sections[3])['Session time changes']).toBe('Direct action allowed')
    expect(rows(sections[3])['Availability changes']).toBe('Owner approval needed')
    expect(Object.keys(rows(sections[3]))).toHaveLength(4)
  })
  it('returns the specific earliest incomplete section after a quick edit without mutating the draft', () => {
    const draft = client(); draft.people[0].name = ''; draft.startDate = ''
    const snapshot = JSON.stringify(draft)
    expect(firstIncompleteSection(draft, CLIENT_ONBOARDING_STEPS, clientStepErrors)).toMatchObject({ index: 0, errors: { 'people.0.name': 'Client name is required.' } })
    expect(JSON.stringify(draft)).toBe(snapshot)
    draft.people[0].name = 'Ready'
    expect(firstIncompleteSection(draft, CLIENT_ONBOARDING_STEPS, clientStepErrors).index).toBe(1)
  })
  it('does not let unadded availability bypass review validation for either form', () => {
    expect(firstIncompleteSection(client(), CLIENT_ONBOARDING_STEPS, clientStepErrors, true)).toMatchObject({ index: 2 })
    expect(firstIncompleteSection(trainer(), TRAINER_ONBOARDING_STEPS, trainerStepErrors, true)).toMatchObject({ index: 2 })
    expect(firstIncompleteSection(client(), CLIENT_ONBOARDING_STEPS, clientStepErrors)).toBeNull()
    expect(firstIncompleteSection(trainer(), TRAINER_ONBOARDING_STEPS, trainerStepErrors)).toBeNull()
  })
  it('requires matching again after dependent client edits and blocks invalid trainer rates', () => {
    const draft = client(); draft.trainerId = ''; draft.fixedWeeklySchedule = []
    expect(firstIncompleteSection(draft, CLIENT_ONBOARDING_STEPS, clientStepErrors).index).toBe(3)
    const changedTrainer = trainer(); changedTrainer.rates.peak = '-1'
    expect(firstIncompleteSection(changedTrainer, TRAINER_ONBOARDING_STEPS, trainerStepErrors).index).toBe(1)
  })
})
