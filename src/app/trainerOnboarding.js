import { APPROVAL_FIELDS } from './constants.js'
import { COUNTRY_CODES, GENDERS } from './contact.js'
import { availabilityBlockError, availabilityByDay } from './availability.js'

export const TRAINER_ONBOARDING_STEPS = [
  { key: 'general', title: 'General Information' },
  { key: 'rates', title: 'Training & Rates' },
  { key: 'availability', title: 'Trainer Availability' },
  { key: 'autonomy', title: 'Owner Approval Needed' },
]

export function createTrainerDraft() {
  return {
    name: '', email: '', phone: { countryCode: '+65', number: '' },
    birthday: '', gender: '', trainerType: '', qualifications: '', publicProfile: 'Visible',
    rates: { peak: '80', offPeak: '55' },
    availabilityBlocks: [],
    approvalNeeded: Object.fromEntries(APPROVAL_FIELDS.map(([field]) => [field, true])),
  }
}

const text = value => typeof value === 'string' ? value.trim() : ''
export const normalizeTrainerEmail = value => text(value).toLowerCase()

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
}

function validRate(value) {
  const input = String(value ?? '').trim()
  return /^\d+(?:\.\d{1,2})?$/.test(input) && Number.isFinite(Number(input))
}

/** Continue and the service write enforce the same fields, without writing mid-flow. */
export function trainerStepErrors(draft, step) {
  const errors = {}
  if (step === 'general') {
    if (!text(draft.name)) errors.name = 'Trainer name is required.'
    const email = normalizeTrainerEmail(draft.email)
    if (!email) errors.email = 'Email is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter a valid email address.'
    if (!GENDERS.includes(draft.gender)) errors.gender = 'Choose a gender.'
    if (!text(draft.trainerType)) errors.trainerType = 'Trainer type is required.'
    if (!COUNTRY_CODES.includes(draft.phone?.countryCode)) errors.phoneCountryCode = 'Choose a phone country code.'
    const number = text(draft.phone?.number)
    if (number && (!/^[\d\s()-]+$/.test(number) || number.replace(/\D/g, '').length < 6 ||
      (draft.phone.countryCode.replace(/\D/g, '') + number.replace(/\D/g, '')).length > 15)) {
      errors.phoneNumber = 'Enter a valid phone number, or leave it blank.'
    }
    if (draft.birthday && !validDate(draft.birthday)) errors.birthday = 'Choose a valid birthday.'
    if (!['Visible', 'Hidden'].includes(draft.publicProfile)) errors.publicProfile = 'Choose the public profile visibility.'
  }
  if (step === 'rates') {
    if (!validRate(draft.rates?.peak)) errors.peak = 'Enter a non-negative peak rate with at most two decimal places.'
    if (!validRate(draft.rates?.offPeak)) errors.offPeak = 'Enter a non-negative off-peak rate with at most two decimal places.'
  }
  if (step === 'availability') {
    const blocks = draft.availabilityBlocks
    if (!Array.isArray(blocks) || !blocks.length) errors.availability = 'Add at least one availability block.'
    else {
      for (let index = 0; index < blocks.length; index += 1) {
        const error = availabilityBlockError(blocks[index], blocks.slice(0, index), true)
        if (error) { errors.availability = error; break }
      }
    }
  }
  if (step === 'autonomy' && APPROVAL_FIELDS.some(([field]) => typeof draft.approvalNeeded?.[field] !== 'boolean')) {
    errors.approvalNeeded = 'Set all four owner approval controls.'
  }
  return errors
}

export function validateTrainerDraft(draft) {
  return TRAINER_ONBOARDING_STEPS.flatMap(step => Object.values(trainerStepErrors(draft, step.key)))
}

export function nextTrainerId(trainers, users = []) {
  let next = trainers.reduce((max, trainer) => Math.max(max,
    Number(String(trainer.id).match(/^t(\d+)$/)?.[1] ?? 0)), 0) + 1
  while (users.some(user => user.id === `u-t${next}`)) next += 1
  return `t${next}`
}

export function buildTrainerRecord(draft, id) {
  // Existing trainer profiles use a display phone string. Keep that contract;
  // capture country code and number separately in the form without a second source of truth.
  const number = text(draft.phone.number)
  return {
    id, status: 'active', name: text(draft.name), email: normalizeTrainerEmail(draft.email),
    phone: number ? `${draft.phone.countryCode} ${number}` : '',
    birthday: draft.birthday || '', gender: draft.gender, trainerType: text(draft.trainerType),
    qualifications: text(draft.qualifications), publicProfile: draft.publicProfile,
    rates: { peak: Number(draft.rates.peak), offPeak: Number(draft.rates.offPeak) },
    availability: availabilityByDay(draft.availabilityBlocks),
    approvalNeeded: Object.fromEntries(APPROVAL_FIELDS.map(([field]) => [field, draft.approvalNeeded[field]])),
    monthlyActivity: { sessions: 0, hours: 0, peak: 0, offPeak: 0 },
  }
}
