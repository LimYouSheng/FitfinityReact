import { ApiError } from './apiClient.js'
import { validSessionDate } from '../app/sessionRules.js'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const fail = () => { throw new ApiError('API_RESPONSE', 'The staff directory could not be verified. Please reload.') }
const list = value => Array.isArray(value) ? value : fail()
const text = value => typeof value === 'string' ? value : fail()
const number = value => Number.isSafeInteger(value) && value >= 0 ? value : fail()
const flag = value => typeof value === 'boolean' ? value : fail()
const choice = (value, options) => options.includes(value) ? value : fail()
const identity = value => /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(text(value)) ? value : fail()
const date = value => validSessionDate(value) ? value : fail()
const base = value => ({ id: identity(value.id), version: number(value.version) || fail(), name: text(value.name), status: choice(value.status, ['active', 'inactive']) })
const phone = person => ({ countryCode: text(person.phone_country_code), number: text(person.phone_number) })
const slot = row => ({ id: identity(row.id), day: days[choice(row.weekday, [0, 1, 2, 3, 4, 5, 6])], from: clockTime(row.starts_at), to: clockTime(row.ends_at) })
function clockTime(value) { if (!/^([01]\d|2[0-3]):[0-5]\d(:00)?$/.test(text(value))) fail(); return value.slice(0, 5) }
function unique(rows) { if (new Set(rows.map(row => row.id)).size !== rows.length) fail(); return rows }
function person(row) {
  return { id: identity(row.id), version: number(row.version) || fail(), name: text(row.name), email: text(row.email), birthday: row.birthday === null ? '' : date(row.birthday), gender: text(row.gender), phone: phone(row),
    emergencyContact: { name: text(row.emergency_name), relationship: text(row.emergency_relationship), countryCode: text(row.emergency_country_code), number: text(row.emergency_number) } }
}
function purchase(row) {
  const total = number(row.total_sessions), used = number(row.used)
  if (!total || used > total || !number(row.validity_days) || !number(row.sessions_per_week)) fail()
  return { ...base(row), total, used, validityDays: row.validity_days, sessionsPerWeek: row.sessions_per_week, freeGym: flag(row.free_gym),
    templateId: identity(row.template_id), templateVersion: number(row.template_revision), startDate: date(row.start_date), endDate: date(row.end_date),
    purchasedTrainerId: identity(row.purchased_trainer_id), trainerId: identity(row.trainer_id), trainerName: text(row.trainer_name),
    stage: choice(row.stage, ['queued', 'current', 'archived']), fixedWeeklySchedule: unique(list(row.schedule).map(slot)) }
}
function client(row) {
  const people = unique(list(row.people).map(person)), purchases = unique(list(row.purchases).map(purchase))
  const type = choice(row.kind, ['individual', 'couple']) === 'couple' ? 'Couple' : 'Individual'
  if (people.length !== (type === 'Couple' ? 2 : 1) || purchases.filter(p => p.stage === 'current').length > 1) fail()
  const current = purchases.find(p => p.stage === 'current') ?? null
  return { ...people[0], ...base(row), type, people, trainerId: identity(row.trainer_id), remarks: text(row.remarks),
    genderPreference: ({ any: 'No gender preference', female: 'Female trainer preferred', male: 'Male trainer preferred' })[choice(row.gender_preference, ['any', 'female', 'male'])],
    package: current, additionalPackages: purchases.filter(p => p.stage === 'queued'), packageHistory: purchases.filter(p => p.stage === 'archived'),
    startDate: current?.startDate ?? null, fixedWeeklySchedule: current?.fixedWeeklySchedule ?? [] }
}
function trainer(row, user) {
  if (user.role === 'admin' && ['peak_rate_cents', 'off_peak_rate_cents', 'rates'].some(key => Object.hasOwn(row, key))) fail()
  const availability = Object.fromEntries(days.map(day => [day, []]))
  for (const block of list(row.availability).map(slot)) availability[block.day].push([block.from, block.to])
  return { ...base(row), email: text(row.email), phone: `${text(row.phone_country_code)} ${text(row.phone_number)}`, birthday: row.birthday === null ? '' : date(row.birthday), gender: text(row.gender),
    trainerType: text(row.trainer_type), qualifications: text(row.qualifications), publicProfile: flag(row.public_profile) ? 'Visible' : 'Hidden', availability,
    ...(user.role === 'admin' ? {} : { rates: { peak: number(row.peak_rate_cents) / 100, offPeak: number(row.off_peak_rate_cents) / 100 } }),
    approvalNeeded: { availability: flag(row.approve_availability), sessionTime: flag(row.approve_session_time), trainerReassignment: flag(row.approve_session_trainer), fixedWeeklySchedule: flag(row.approve_weekly_schedule) } }
}

export function directoryPackage(row) {
  return { ...base(row), revision: number(row.revision) || fail(), total: number(row.total_sessions) || fail(), validityDays: number(row.validity_days) || fail() }
}

export function directorySnapshot(value, user) {
  try {
    if (value.schemaVersion !== 1 || value.viewerId !== user.id || value.timeZone !== 'Asia/Singapore' || !Number.isFinite(Date.parse(value.serverAt))) fail()
    const clients = unique(list(value.clients).map(client)), trainers = unique(list(value.trainers).map(row => trainer(row, user)))
    const packages = unique(list(value.packages).map(directoryPackage))
    if (clients.some(row => !trainers.some(t => t.id === row.trainerId))) fail()
    if (user.role === 'trainer' && (clients.some(row => row.trainerId !== user.trainerId) || trainers.some(row => row.id !== user.trainerId) || packages.length)) fail()
    let packagePolicy
    if (value.packagePolicy !== undefined) {
      const p = value.packagePolicy
      if (p?.minimum !== 1 || p.maximum !== 365 || p.sessions !== 12 || p.days !== 90) fail()
      packagePolicy = { packageSessionCount: { minimum: p.minimum, maximum: p.maximum }, packageValidityRule: { sessions: p.sessions, days: p.days } }
    }
    let clientOnboardingPolicy
    if (value.clientOnboardingPolicy !== undefined) {
      const p = value.clientOnboardingPolicy
      if (p?.defaultCountryCode !== '+65' || p.defaultRelationship !== 'Spouse' || JSON.stringify(p.weeklyFrequencies) !== '[1,2,3,4,5,6,7]' || p.freeGymMinimumFrequency !== 2 || p.availability?.from !== '18:00' || p.availability?.to !== '19:00') fail()
      clientOnboardingPolicy = structuredClone(p)
    }
    if (value.clientReactivationWrites !== undefined && typeof value.clientReactivationWrites !== 'boolean') fail()
    if (value.clientDeactivationWrites !== undefined && typeof value.clientDeactivationWrites !== 'boolean') fail()
    if (value.requestCancellationWrites !== undefined && typeof value.requestCancellationWrites !== 'boolean') fail()
    if (value.renewalDismissalWrites !== undefined && typeof value.renewalDismissalWrites !== 'boolean') fail()
    if (value.personalMessages !== undefined && typeof value.personalMessages !== 'boolean') fail()
    if (value.contentWorkflows !== undefined && typeof value.contentWorkflows !== 'boolean') fail()
    if (value.clientAssessmentWorkflows !== undefined && typeof value.clientAssessmentWorkflows !== 'boolean') fail()
    if (value.clientCreation !== undefined && typeof value.clientCreation !== 'boolean') fail()
    if (value.clientCreation && !clientOnboardingPolicy) fail()
    let trainerProfilePolicy
    if (value.trainerProfilePolicy !== undefined) {
      const p = value.trainerProfilePolicy
      if (p?.defaultCountryCode !== '+65' || !Array.isArray(p.trainerTypes) || p.trainerTypes.length !== 2 || p.trainerTypes[0] !== 'Strength & Conditioning' || p.trainerTypes[1] !== 'Personal Trainer') fail()
      trainerProfilePolicy = { defaultCountryCode: p.defaultCountryCode, trainerTypes: [...p.trainerTypes] }
    }
    if (value.trainerReactivationWrites !== undefined && typeof value.trainerReactivationWrites !== 'boolean') fail()
    if (value.trainerPersonalWrites !== undefined && typeof value.trainerPersonalWrites !== 'boolean') fail()
    if (value.trainerPersonalWrites && !trainerProfilePolicy) fail()
    if (value.trainerEmailWrites !== undefined && typeof value.trainerEmailWrites !== 'boolean') fail()
    if (value.trainerRateWrites !== undefined && typeof value.trainerRateWrites !== 'boolean') fail()
    if (value.trainerApprovalWrites !== undefined && typeof value.trainerApprovalWrites !== 'boolean') fail()
    if (value.clientNoteWrites !== undefined && typeof value.clientNoteWrites !== 'boolean') fail()
    if (value.clientPersonalWrites !== undefined && typeof value.clientPersonalWrites !== 'boolean') fail()
    return { requestCancellationWrites: value.requestCancellationWrites === true, clientReactivationWrites: value.clientReactivationWrites === true, clientDeactivationWrites: value.clientDeactivationWrites === true, renewalDismissalWrites: value.renewalDismissalWrites === true, personalMessages: value.personalMessages === true, contentWorkflows: value.contentWorkflows === true, clientAssessmentWorkflows: value.clientAssessmentWorkflows === true, trainerReactivationWrites: value.trainerReactivationWrites === true, clientOnboardingPolicy, clientCreation: value.clientCreation === true, trainerProfilePolicy, trainerPersonalWrites: value.trainerPersonalWrites === true, trainerEmailWrites: value.trainerEmailWrites === true, trainerRateWrites: value.trainerRateWrites === true, clientNoteWrites: value.clientNoteWrites === true, clientPersonalWrites: value.clientPersonalWrites === true, trainerApprovalWrites: value.trainerApprovalWrites === true, packagePolicy, data: { clients, trainers, packages }, serverAt: value.serverAt, businessDate: date(value.businessDate) }
  } catch (error) { if (error instanceof ApiError) throw error; fail() }
}
