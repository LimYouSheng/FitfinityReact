import { mockPolicy } from '../data/mockPolicy.js'
import { describe, expect, it } from 'vitest'
import { APPROVAL_FIELDS } from './constants.js'
import { buildTrainerRecord, createTrainerDraft, nextTrainerId, trainerStepErrors, TRAINER_ONBOARDING_STEPS, validateTrainerDraft } from './trainerOnboarding.js'

function validDraft() {
  return { ...createTrainerDraft(mockPolicy), name: ' New Trainer ', email: ' NEW@Example.com ',
    gender: 'Female', trainerType: 'Personal', phone: { countryCode: '+65', number: '91234567' }, birthday: '1990-01-02',
    availabilityBlocks: [{ id: 'a1', days: ['Monday', 'Wednesday'], from: '18:00', to: '19:00' }] }
}

describe('trainer onboarding', () => {
  it('starts with +65, 80/55 rates and four independent supervised controls', () => {
    const a = createTrainerDraft(mockPolicy), b = createTrainerDraft(mockPolicy)
    expect(a.phone.countryCode).toBe('+65')
    expect(a.rates).toEqual({ peak: '80', offPeak: '55' })
    expect(Object.keys(a.approvalNeeded)).toEqual(APPROVAL_FIELDS.map(([key]) => key))
    expect(Object.values(a.approvalNeeded)).toEqual([true, true, true, true])
    a.approvalNeeded.availability = false
    expect(b.approvalNeeded.availability).toBe(true)
  })
  it('requires complete general information while qualifications remain optional', () => {
    expect(trainerStepErrors(validDraft(), 'general')).toEqual({})
    expect(Object.keys(trainerStepErrors(createTrainerDraft(mockPolicy), 'general'))).toEqual(['name', 'email', 'gender', 'trainerType', 'phoneNumber', 'birthday'])
    expect(trainerStepErrors(createTrainerDraft(mockPolicy), 'rates')).toEqual({})
  })
  it('rejects invalid email, phone, gender and impossible birthday', () => {
    expect(trainerStepErrors({ ...validDraft(), email: 'broken' }, 'general').email).toBeTruthy()
    expect(trainerStepErrors({ ...validDraft(), birthday: '2026-02-30' }, 'general').birthday).toBeTruthy()
    expect(trainerStepErrors({ ...validDraft(), phone: { countryCode: '+65', number: 'xx' } }, 'general').phoneNumber).toBeTruthy()
    expect(trainerStepErrors({ ...validDraft(), gender: '' }, 'general').gender).toBeTruthy()
  })
  it('blocks empty, negative, non-numeric and over-precision rates but accepts zero', () => {
    for (const value of ['', '-1', 'NaN', 'Infinity', '1.001']) {
      expect(trainerStepErrors({ ...validDraft(), rates: { peak: value, offPeak: 55 } }, 'rates').peak).toBeTruthy()
    }
    expect(trainerStepErrors({ ...validDraft(), rates: { peak: '0', offPeak: '55.50' } }, 'rates')).toEqual({})
  })
  it('requires non-overlapping availability and allows adjacent blocks', () => {
    const draft = validDraft()
    expect(trainerStepErrors({ ...draft, availabilityBlocks: [] }, 'availability').availability).toBeTruthy()
    draft.availabilityBlocks.push({ days: ['Monday'], from: '18:30', to: '19:30' })
    expect(trainerStepErrors(draft, 'availability').availability).toContain('overlaps')
    draft.availabilityBlocks[1] = { days: ['Monday'], from: '19:00', to: '20:00' }
    expect(trainerStepErrors(draft, 'availability')).toEqual({})
  })
  it('requires boolean controls and preserves checked versus unchecked semantics', () => {
    const draft = validDraft()
    draft.approvalNeeded.sessionTime = false
    expect(trainerStepErrors(draft, 'autonomy')).toEqual({})
    expect(buildTrainerRecord(draft, 't99').approvalNeeded.sessionTime).toBe(false)
    delete draft.approvalNeeded.availability
    expect(trainerStepErrors(draft, 'autonomy').approvalNeeded).toBeTruthy()
  })
  it('normalises the existing profile contract without invented activity or shared state', () => {
    const draft = validDraft()
    draft.phone = { countryCode: '+60', number: '123456789' }
    const record = buildTrainerRecord(draft, 't99')
    expect(record).toMatchObject({ id: 't99', status: 'active', name: 'New Trainer', email: 'new@example.com', phone: '+60 123456789', birthday: '1990-01-02', rates: { peak: 80, offPeak: 55 }, monthlyActivity: { sessions: 0, hours: 0, peak: 0, offPeak: 0 } })
    expect(record.availability.Wednesday).toEqual([['18:00', '19:00']])
    draft.availabilityBlocks[0].from = '17:00'
    expect(record.availability.Monday).toEqual([['18:00', '19:00']])
  })
  it('allocates IDs without colliding with trainers or mock identities', () => {
    expect(nextTrainerId([{ id: 't2' }, { id: 't10' }], [{ id: 'u-t11' }])).toBe('t12')
  })
  it('revalidates every named step before creating any record', () => {
    expect(TRAINER_ONBOARDING_STEPS.map(item => item.title)).toEqual(['General Information', 'Training & Rates', 'Trainer Availability', 'Owner Approval Needed'])
    expect(validateTrainerDraft(validDraft())).toEqual([])
    expect(validateTrainerDraft({ ...validDraft(), email: '', availabilityBlocks: [] })).toEqual(['Email is required.', 'Add at least one availability block.'])
  })
})
