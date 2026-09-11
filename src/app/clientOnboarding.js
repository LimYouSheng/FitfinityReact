import { freeGymEligible } from './packages.js'
import { DAYS } from './availability.js'
import { GENDERS, COUNTRY_CODES, RELATIONSHIPS, phoneDraft, validPhoneNumber } from './contact.js'
export { DAYS } from './availability.js'
export { COUNTRY_CODES, RELATIONSHIPS, GENDER_PREFERENCES } from './contact.js'

const DAY_INDEX = {
  Sunday: 0, Monday: 1, Tuesday: 2, Wednesday: 3,
  Thursday: 4, Friday: 5, Saturday: 6,
}

const clone = value => JSON.parse(JSON.stringify(value))

function parseIsoDate(value) {
  const [year, month, day] = String(value || '').split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(Date.UTC(year, month - 1, day))
}

function isoDate(date) {
  return date.toISOString().slice(0, 10)
}

export function addDays(dateString, days) {
  const date = parseIsoDate(dateString)
  if (!date) return ''
  date.setUTCDate(date.getUTCDate() + days)
  return isoDate(date)
}

export function trainerCoversBlock(trainer, day, from, to) {
  return (trainer?.availability?.[day] ?? []).some(([availableFrom, availableTo]) =>
    availableFrom <= from && availableTo >= to
  )
}

function genderMatches(trainer, preference) {
  if (preference === 'Female trainer preferred') return trainer.gender === 'Female'
  if (preference === 'Male trainer preferred') return trainer.gender === 'Male'
  return true
}

export function matchTrainers(trainers, blocks, genderPreference = 'No gender preference') {
  const preferences = blocks ?? []

  return (trainers ?? [])
    .filter(trainer => (trainer.status ?? 'active') === 'active')
    .filter(trainer => genderMatches(trainer, genderPreference))
    .map(trainer => {
      const matches = preferences.reduce((count, block) => {
        const covered = (block.days ?? []).some(day =>
          trainerCoversBlock(trainer, day, block.from, block.to)
        )
        return count + (covered ? 1 : 0)
      }, 0)

      return { trainer, matches, total: preferences.length }
    })
    .filter(result => result.matches > 0)
    .sort((a, b) => b.matches - a.matches || a.trainer.name.localeCompare(b.trainer.name))
}

export function matchingScheduleOptions(trainer, blocks) {
  const options = []
  const seenDays = new Set()

  for (const day of DAYS) {
    for (const block of blocks ?? []) {
      if (
        (block.days ?? []).includes(day) &&
        !seenDays.has(day) &&
        trainerCoversBlock(trainer, day, block.from, block.to)
      ) {
        options.push({ day, from: block.from, to: block.to })
        seenDays.add(day)
        break
      }
    }
  }

  return options
}

export function buildFixedWeeklySchedule(trainer, blocks, sessionsPerWeek) {
  const needed = Number.isInteger(Number(sessionsPerWeek)) && Number(sessionsPerWeek) >= 1 && Number(sessionsPerWeek) <= DAYS.length ? Number(sessionsPerWeek) : 1
  return matchingScheduleOptions(trainer, blocks)
    .slice(0, needed)
    .map((slot, index) => ({ id: `new-slot-${index + 1}`, ...slot }))
}

/** Keep a valid choice; otherwise prefer a trainer covering the complete cadence. */
export function defaultMatchingTrainer(matches, blocks, sessionsPerWeek, previousId = '') {
  if (matches.some(result => result.trainer.id === previousId)) return previousId
  const eligible = matches.find(result =>
    buildFixedWeeklySchedule(result.trainer, blocks, sessionsPerWeek).length === Number(sessionsPerWeek))
  return eligible?.trainer.id ?? matches[0]?.trainer.id ?? ''
}

export function packageFor(startDate, sessionsPerWeek, definition, minimumFrequency) {
  const frequency = Number(sessionsPerWeek)
  return {
    durationWeeks: Math.ceil(definition.total / frequency),
    sessionsPerWeek: frequency,
    total: definition.total,
    freeGym: freeGymEligible(frequency, minimumFrequency),
    used: 0,
    startDate,
    validityDays: definition.validityDays,
    endDate: addDays(startDate, definition.validityDays - 1),
  }
}

export function nextClientId(clients) {
  const highest = (clients ?? []).reduce((max, client) => {
    const numeric = Number(String(client.id ?? '').match(/^c(\d+)$/)?.[1] ?? 0)
    return Math.max(max, numeric)
  }, 0)
  return `c${highest + 1}`
}

export const CLIENT_ONBOARDING_STEPS = [
  { key: 'general', title: 'General Information' },
  { key: 'package', title: 'Package & Preferences' },
  { key: 'availability', title: 'Client Availability' },
  { key: 'matching', title: 'Trainer Matching' },
]

/** Step and final validation share the same rules; Continue never writes records. */
export function clientStepErrors(draft, step, { requireComplete = true } = {}) {
  const errors = {}
  const people = draft.people ?? []
  const requiredSlots = Number(draft.sessionsPerWeek)

  if (step === 'general') {
    if (!['Individual', 'Couple'].includes(draft.type)) errors.type = 'Choose a client type.'
    const count = draft.type === 'Couple' ? 2 : 1
    for (let index = 0; index < count; index += 1) {
      if (!people[index]?.name?.trim()) {
        errors[`people.${index}.name`] = `${count === 2 ? `Client ${index + 1}` : 'Client'} name is required.`
      }
      if ((requireComplete || people[index]?.gender) && !GENDERS.includes(people[index]?.gender)) errors[`people.${index}.gender`] = 'Choose a gender.'
      if (requireComplete) {
        const person = people[index] ?? {}
        const key = field => `people.${index}.${field}`
        if (!COUNTRY_CODES.includes(person.phone?.countryCode)) errors[key('phoneCountryCode')] = 'Choose a phone country code.'
        if (!person.phone?.number?.trim()) errors[key('phoneNumber')] = 'Phone number is required.'
        else if (!validPhoneNumber(person.phone)) errors[key('phoneNumber')] = 'Enter a valid phone number.'
        if (!person.email?.trim()) errors[key('email')] = 'Email is required.'
        else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(person.email.trim())) errors[key('email')] = 'Enter a valid email address.'
        const birthday = parseIsoDate(person.birthday)
        if (!person.birthday) errors[key('birthday')] = 'Birthday is required.'
        else if (!/^\d{4}-\d{2}-\d{2}$/.test(person.birthday) || !birthday || !Number.isFinite(birthday.getTime()) || isoDate(birthday) !== person.birthday) errors[key('birthday')] = 'Choose a valid birthday.'
        const emergency = person.emergencyContact ?? {}
        if (!emergency.name?.trim()) errors[key('emergencyName')] = 'Emergency contact name is required.'
        if (!RELATIONSHIPS.includes(emergency.relationship)) errors[key('emergencyRelationship')] = 'Choose an emergency contact relationship.'
        if (!COUNTRY_CODES.includes(emergency.countryCode)) errors[key('emergencyCountryCode')] = 'Choose an emergency contact country code.'
        if (!emergency.number?.trim()) errors[key('emergencyNumber')] = 'Emergency contact phone number is required.'
        else if (!validPhoneNumber(emergency)) errors[key('emergencyNumber')] = 'Enter a valid emergency contact phone number.'
      }
    }
  }

  if (step === 'package') {
    const date = parseIsoDate(draft.startDate)
    if (!draft.startDate) errors.startDate = 'Start date is required.'
    else if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.startDate) || !date || !Number.isFinite(date.getTime()) || isoDate(date) !== draft.startDate) {
      errors.startDate = 'Choose a valid start date.'
    } else if (draft.minimumStartDate && draft.startDate < draft.minimumStartDate) {
      errors.startDate = `Choose ${draft.minimumStartDate} or later, after the existing packages end.`
    }
    if (!Number.isInteger(requiredSlots) || requiredSlots < 1 || requiredSlots > DAYS.length) errors.sessionsPerWeek = 'Choose between one and seven sessions per week.'
  }

  if (step === 'availability') {
    const blocks = draft.clientPreferences ?? []
    const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/
    if (!blocks.length) errors.availability = 'Add at least one availability block.'
    else if (blocks.some(block => !block.days?.length || block.days.some(day => !DAYS.includes(day)) || !timePattern.test(block.from) || !timePattern.test(block.to) || block.from >= block.to)) {
      errors.availability = 'Each block needs a valid day and a From time earlier than To.'
    } else if (new Set(blocks.flatMap(block => block.days)).size < requiredSlots) {
      errors.availability = requiredSlots === 2 ? 'Twice-weekly training needs at least two possible days.' : `Add at least ${requiredSlots} possible training days.`
    }
  }

  if (step === 'matching') {
    if (!draft.trainerId) errors.trainerId = 'Choose a matched trainer.'
    if ((draft.fixedWeeklySchedule ?? []).length < requiredSlots) {
      errors.fixedWeeklySchedule = `The selected trainer needs ${requiredSlots} matching fixed weekly ${requiredSlots === 1 ? 'day' : 'days'}.`
    }
  }
  return errors
}

export function validateClientDraft(draft) {
  return CLIENT_ONBOARDING_STEPS.flatMap(step => Object.values(clientStepErrors(draft, step.key)))
}

function normalisePerson(person, policy) {
  return {
    name: person?.name?.trim() ?? '',
    phone: {
      countryCode: person?.phone?.countryCode ?? policy.defaultCountryCode,
      number: person?.phone?.number?.trim() ?? '',
    },
    email: person?.email?.trim() ?? '',
    birthday: person?.birthday ?? '',
    gender: person?.gender ?? '',
    emergencyContact: {
      name: person?.emergencyContact?.name?.trim() ?? '',
      relationship: person?.emergencyContact?.relationship ?? policy.defaultRelationship,
      countryCode: person?.emergencyContact?.countryCode ?? policy.defaultCountryCode,
      number: person?.emergencyContact?.number?.trim() ?? '',
    },
    healthNotes: person?.healthNotes?.trim() ?? '',
  }
}

export function clientPersonalDetails(draft, policy) {
  const isCouple = draft.type === 'Couple'
  const people = (isCouple ? draft.people.slice(0, 2) : draft.people.slice(0, 1)).map(person => normalisePerson(person, policy))
  const primary = people[0]
  const displayName = isCouple
    ? people.map(person => person.name).filter(Boolean).join(' & ')
    : primary.name
  const healthNotes = isCouple
    ? people.map(person => `${person.name}: ${person.healthNotes}`).join('\n')
    : primary.healthNotes
  return { name: displayName, phone: clone(primary.phone), email: primary.email, birthday: primary.birthday,
    gender: isCouple ? 'Couple' : primary.gender, emergencyContact: clone(primary.emergencyContact), people, healthNotes }
}

export function clientProfileDraft(client, policy) {
  const primary = normalisePerson({ ...client, phone: phoneDraft(client.phone, policy.defaultCountryCode),
    gender: client.type === 'Couple' ? '' : client.gender }, policy)
  const people = client.type === 'Couple'
    ? (client.people?.length === 2 ? client.people.map(person => normalisePerson(person, policy)) : [primary, normalisePerson({}, policy)])
    : [primary]
  return { ...client, people }
}

export function buildClientRecord(draft, id, definition, policy) {
  const isCouple = draft.type === 'Couple'
  const packageRecord = packageFor(draft.startDate, draft.sessionsPerWeek, definition, policy.freeGymMinimumFrequency)

  return {
    id,
    status: 'active',
    type: isCouple ? 'Couple' : 'Individual',
    ...clientPersonalDetails(draft, policy),
    startDate: draft.startDate,
    trainerId: draft.trainerId,
    genderPreference: draft.genderPreference || 'No gender preference',
    remarks: draft.remarks?.trim() ?? '',
    clientPreferences: clone(draft.clientPreferences ?? []),
    fixedWeeklySchedule: (draft.fixedWeeklySchedule ?? []).map((slot, index) => ({
      id: `${id}-slot-${index + 1}`,
      day: slot.day,
      from: slot.from,
      to: slot.to,
    })),
    package: { id: `client-package-${id}`, ...packageRecord, ...(definition ? { templateId: definition.id, name: definition.name, templateVersion: definition.version } : {}) },
    packageHistory: [],
    strengthProgress: [],
    lastTrained: null,
  }
}

export function buildClientSessions(client) {
  const schedule = client.fixedWeeklySchedule ?? []
  const target = client.package?.total ?? 0
  const start = parseIsoDate(client.package?.startDate)
  const validityDays = client.package?.validityDays ?? 0
  if (!start || !schedule.length || !target) return []

  const candidates = []
  for (let offset = 0; offset < validityDays; offset += 1) {
    const date = new Date(start)
    date.setUTCDate(start.getUTCDate() + offset)
    schedule.forEach(slot => {
      if (date.getUTCDay() === DAY_INDEX[slot.day]) {
        candidates.push({ date: isoDate(date), from: slot.from, to: slot.to, weeklySlotId: slot.id })
      }
    })
  }

  return candidates
    .sort((a, b) => `${a.date}T${a.from}`.localeCompare(`${b.date}T${b.from}`))
    .slice(0, target)
    .map((slot, index) => ({
      id: `${client.package.id}-session-${index + 1}`,
      packageId: client.package.id,
      weeklySlotId: slot.weeklySlotId,
      clientId: client.id,
      trainerId: client.trainerId,
      date: slot.date,
      from: slot.from,
      to: slot.to,
      sessionNumber: index + 1,
      packageTotal: target,
      status: 'not_planned',
      exercisePlan: [],
    }))
}
