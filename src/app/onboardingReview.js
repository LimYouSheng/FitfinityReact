import { weeklyFrequencyLabel } from './packages.js'
import { APPROVAL_FIELDS } from './constants.js'
import { packageFor } from './clientOnboarding.js'
import { formatDate } from '../utils/date.js'

export const ONBOARDING_REVIEW_STEP = { key: 'review', title: 'Review & Confirm' }

export function reviewValue(value) {
  if (value === null || value === undefined || String(value).trim() === '') return '—'
  return String(value).trim()
}

export function reviewPhone(phone) {
  if (!phone?.number?.trim()) return '—'
  return `${phone.countryCode ?? ''} ${phone.number}`.trim()
}

const row = (label, value) => ({ label, value: reviewValue(value) })
const group = rows => ({ rows })
const blockRows = blocks => (blocks ?? []).map((block, index) =>
  row(`Block ${index + 1}`, `${block.days.join(', ')} · ${block.from}–${block.to}`))

/** A review is derived from the live draft, never a second saved record. */
export function clientReviewSections(draft, trainer) {
  const people = draft.people.slice(0, draft.type === 'Couple' ? 2 : 1)
  const pack = packageFor(draft.startDate, draft.sessionsPerWeek, draft.packageDefinition)
  return [
    { key: 'general', title: 'General Information', groups: [
      group([row('Client type', draft.type === 'Couple' ? 'Couple' : 'Single'), row('Remarks', draft.remarks)]),
      ...people.map((person, index) => ({
        title: draft.type === 'Couple' ? `Client ${index + 1}` : 'Client',
        rows: [
          row('Name', person.name), row('Phone', reviewPhone(person.phone)),
          row('Email', person.email), row('Birthday', formatDate(person.birthday)), row('Gender', person.gender),
          row('Emergency contact name', person.emergencyContact?.name),
          row('Emergency contact relationship', person.emergencyContact?.relationship),
          row('Emergency contact phone', reviewPhone(person.emergencyContact)),
          row('Health / Limitation Notes', person.healthNotes),
        ],
      })),
    ] },
    { key: 'package', title: 'Package & Preferences', groups: [group([
      row('PT Package', `${pack.total} sessions`), row('Validity', `${pack.validityDays} days`),
      row('Free gym package', pack.freeGym ? 'Included' : 'Not included'),
      ...(draft.packageName ? [row('Package name', draft.packageName)] : []),
      row('Start date', formatDate(draft.startDate)), row('Expiry date', formatDate(pack.endDate)),
      row('Weekly frequency', weeklyFrequencyLabel(draft.sessionsPerWeek)),
      row('Total sessions', pack.total), row('Trainer preference', draft.genderPreference),
    ])] },
    { key: 'availability', title: 'Client Availability', groups: [group(blockRows(draft.clientPreferences))] },
    { key: 'matching', title: 'Trainer Matching', groups: [group([
      row('Assigned trainer', trainer?.name),
      row('Fixed Weekly Schedule', (draft.fixedWeeklySchedule ?? [])
        .map(slot => `${slot.day} · ${slot.from}–${slot.to}`).join('\n')),
    ])] },
  ]
}

export function trainerReviewSections(draft) {
  const money = value => value === '' || value === null || value === undefined || !Number.isFinite(Number(value))
    ? '—' : `S$${Number(value).toFixed(2)} / session`
  return [
    { key: 'general', title: 'General Information', groups: [group([
      row('Trainer name', draft.name), row('Email', draft.email.trim().toLowerCase()),
      row('Phone', reviewPhone(draft.phone)), row('Birthday', formatDate(draft.birthday)), row('Gender', draft.gender),
      row('Trainer type', draft.trainerType), row('Public profile', draft.publicProfile), row('Qualifications', draft.qualifications),
    ])] },
    { key: 'rates', title: 'Training & Rates', groups: [group([
      row('Peak session rate', money(draft.rates.peak)), row('Off-peak session rate', money(draft.rates.offPeak)),
    ])] },
    { key: 'availability', title: 'Trainer Availability', groups: [group(blockRows(draft.availabilityBlocks))] },
    { key: 'autonomy', title: 'Owner Approval Needed', groups: [group(APPROVAL_FIELDS.map(([field, label]) =>
      row(label, draft.approvalNeeded[field] === true ? 'Owner approval needed'
        : draft.approvalNeeded[field] === false ? 'Direct action allowed' : 'Not selected')))] },
  ]
}

/** Revalidate dependencies when returning from a quick edit and before creation. */
export function firstIncompleteSection(draft, steps, validateStep, pendingAvailability = false) {
  for (let index = 0; index < steps.length; index += 1) {
    const errors = { ...validateStep(draft, steps[index].key) }
    if (steps[index].key === 'availability' && pendingAvailability) {
      errors.availability = 'Select Add Time to include these days before continuing.'
    }
    if (Object.keys(errors).length) return { index, errors }
  }
  return null
}
