import { beforeEach, expect, it } from 'vitest'
import { ASSESSMENT_FORMS, assessmentFields, assessmentErrors, normaliseAssessments, saveAssessment } from './assessmentForms.js'
import paperLayouts from './assessmentPaperLayouts.json'
import { clientProfileDraft, clientStepErrors } from './clientOnboarding.js'
import { mockDb } from '../services/mockDb.js'
import { clientService } from '../services/clientService.js'

const draft = () => ({ date: '2026-09-17', assessor: ' Owner ', answers: { eyes_open_1: '0', eyes_closed_1: '' } })
const record = () => saveAssessment('balance', draft(), '2026-09-17T09:00:00Z')
beforeEach(() => mockDb.reset())

it('includes all eleven distinct forms with unique field identifiers and no prefilled reference results', () => {
  expect(ASSESSMENT_FORMS).toHaveLength(11)
  expect(new Set(ASSESSMENT_FORMS.map(form => form.id)).size).toBe(11)
  expect(ASSESSMENT_FORMS.find(form => form.id === 'single_leg').subtitle).toContain('Step-up')
  expect(ASSESSMENT_FORMS.find(form => form.id === 'hurdle_step').subtitle).toContain('hurdle')
  for (const form of ASSESSMENT_FORMS) {
    const fields = assessmentFields(form)
    expect(new Set(fields.map(field => field.id)).size).toBe(fields.length)
    expect(fields.every(field => !Object.hasOwn(field, 'value'))).toBe(true)
    expect(form.source).toMatch(/\.pdf$/)
    for (const page of paperLayouts[form.id]) {
      expect(page.asset).toMatch(/\.svg$/)
      expect(page.text.length).toBeGreaterThan(100)
      for (const placement of page.fields) {
        const [x, y, width, height] = placement.rect
        expect(x).toBeGreaterThanOrEqual(0); expect(y).toBeGreaterThanOrEqual(0)
        expect(width).toBeGreaterThan(0); expect(height).toBeGreaterThan(0)
        expect(x + width).toBeLessThanOrEqual(page.width)
        expect(y + height).toBeLessThanOrEqual(page.height)
        if (placement.id.startsWith('$')) continue
        const field = fields.find(item => item.id === placement.id)
        expect(field, placement.id).toBeDefined()
        if (field.type === 'select') expect(field.options).toContain(placement.value)
      }
    }
  }
  expect(Object.values(paperLayouts).flat()).toHaveLength(17)
  expect(paperLayouts.health_history).toHaveLength(4)
  const singleLeg = paperLayouts.single_leg[0].fields
  expect(singleLeg.find(field => field.id === 'torso_compensations').rect[2])
    .toBeGreaterThan(singleLeg.find(field => field.id === 'feet_overactive').rect[2] * 2)
  expect(singleLeg.some(field => field.id === 'torso_underactive')).toBe(false)
  const upper = paperLayouts.upper_flexibility.flatMap(page => page.fields)
  expect(upper.filter(field => field.kind === 'check')).toHaveLength(15)
  expect(upper.some(field => field.id.endsWith('_left'))).toBe(false)
})

it('keeps zero distinct from blank, strips whitespace and records version, date and assessor', () => {
  const saved = record()
  expect(saved).toMatchObject({ formId: 'balance', version: 1, status: 'filled', date: '2026-09-17', assessor: 'Owner', answers: { eyes_open_1: 0 } })
  expect(saved.answers).not.toHaveProperty('eyes_closed_1')
  expect(draft().answers.eyes_open_1).toBe('0')
  const medical = saveAssessment('health_history', { ...draft(), answers: { condition_5: 'Yes', condition_6: '', conditions: 'Previous narrative retained', plan_type: 'Previous plan and reason' } })
  expect(medical.answers).toEqual({ condition_5: 'Yes', conditions: 'Previous narrative retained', plan_type: 'Previous plan and reason' })
  expect(normaliseAssessments({ health_history: medical }).health_history).toEqual(medical)
  expect(normaliseAssessments({ balance: saved })).toEqual({ balance: saved })
  const reference = saveAssessment('upper_flexibility', { ...draft(), answers: { shoulder_flexion_reference_checked: 'Yes', shoulder_flexion_left: '121' } })
  expect(reference.answers).toEqual({ shoulder_flexion_reference_checked: 'Yes', shoulder_flexion_left: 121 })
  expect(reference.answers).not.toHaveProperty('shoulder_flexion_right')
  const family = saveAssessment('health_history', { ...draft(), answers: { family_0: 'Earlier combined answer', family_0_relation: 'Father', family_0_age: '52', family_0_selected: 'Yes' } })
  expect(normaliseAssessments({ health_history: family }).health_history.answers).toEqual(family.answers)
})

it('rejects an empty form, metadata-only form and impossible dates', () => {
  expect(assessmentErrors('balance', { ...draft(), answers: { side: 'Left' } }).answers).toBeTruthy()
  expect(assessmentErrors('balance', { ...draft(), date: '2026-02-30', assessor: '' })).toMatchObject({ date: expect.any(String), assessor: expect.any(String) })
  expect(() => saveAssessment('unknown', draft())).toThrow()
  const unchecked = saveAssessment('hurdle_step', { ...draft(), answers: {} })
  expect(unchecked.answers).toEqual({})
  expect(normaliseAssessments({ hurdle_step: unchecked }).hurdle_step).toEqual(unchecked)
  expect(assessmentErrors('hurdle_step', { ...draft(), assessor: '', answers: {} })).toHaveProperty('assessor')
})

it('rejects negative, nonfinite, out-of-range, forged and unknown values', () => {
  for (const value of ['-1', 'abc', Infinity, {}]) expect(assessmentErrors('balance', { ...draft(), answers: { eyes_open_1: value } }).eyes_open_1).toBeTruthy()
  expect(assessmentErrors('health_history', { ...draft(), answers: { stress: 11 } }).stress).toBeTruthy()
  expect(assessmentErrors('health_history', { ...draft(), answers: { health: 'Fine' } }).health).toBeTruthy()
  expect(assessmentErrors('health_history', { ...draft(), answers: { condition_5: false } }).condition_5).toBeTruthy()
  expect(assessmentErrors('health_history', { ...draft(), answers: { condition_5: 'No' } }).condition_5).toBeTruthy()
  expect(assessmentErrors('balance', { ...draft(), answers: { diagnosis: 'invented' } }).answers).toBeTruthy()
  expect(() => normaliseAssessments({ balance: { ...record(), version: 99 } })).toThrow()
})

it('allows unfilled forms without weakening validation of a saved form', () => {
  expect(clientStepErrors({ type: 'Couple', people: [{}, {}] }, 'assessments')).toEqual({})
  expect(clientStepErrors({ type: 'Individual', people: [{ assessments: { balance: { ...record(), date: '' } } }] }, 'assessments'))
    .toHaveProperty('people.0.assessments')
})

it('persists separate couple assessments and preserves them through contact-only edits', async () => {
  const db = mockDb.read()
  const person = (name, assessments) => ({ name, phone: { countryCode: '+65', number: '91234567' }, email: 'client@example.com',
    birthday: '1990-01-02', gender: 'Female', emergencyContact: { name: 'Contact', relationship: 'Spouse', countryCode: '+65', number: '98765432' }, assessments })
  const created = await clientService.create({ type: 'Couple', people: [person('First', { balance: record() }), person('Second', {})],
    startDate: '2027-06-07', trainerId: 't1', sessionsPerWeek: 1, packageId: db.packages[0].id, packageVersion: db.packages[0].version,
    clientPreferences: [{ days: ['Monday'], from: '18:00', to: '19:00' }], fixedWeeklySchedule: [{ day: 'Monday', from: '18:00', to: '19:00' }] }, mockDb.read().users.find(user => user.role === 'owner'))
  const read = await clientService.getById(created.id)
  expect(read.people.map(person => person.assessments)).toEqual([{ balance: record() }, {}])
  const profile = clientProfileDraft(read, db.settings)
  profile.people[0].name = 'First Updated'
  delete profile.people[0].assessments
  const updated = await clientService.update(created.id, { people: profile.people }, mockDb.read().users.find(user => user.role === 'owner'))
  expect(updated.people[0].assessments).toEqual({ balance: record() })
  const before = mockDb.read()
  await expect(clientService.update(created.id, { people: updated.people.map(person => ({ ...person, assessments: {} })) }, mockDb.read().users.find(user => user.role === 'owner'))).rejects.toThrow('contact edit')
  expect(mockDb.read()).toEqual(before)
})

it('retains individual assessments and historical notes when top-level contact fields change', async () => {
  mockDb.mutate(db => { db.clients[0].people = [{ ...clientProfileDraft(db.clients[0], db.settings).people[0], assessments: { balance: record() } }] })
  const before = mockDb.read().clients[0]
  const updated = await clientService.update(before.id, { name: 'Updated name' }, mockDb.read().users.find(user => user.role === 'owner'))
  expect(updated.people[0].assessments).toEqual({ balance: record() })
  expect(updated.healthNotes).toBe(before.healthNotes)
})
