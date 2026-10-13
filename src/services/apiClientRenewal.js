import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { clientMatchBody, decodeClientMatches } from './apiClientCreation.js'
import { validSessionDate } from '../app/sessionRules.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const version = v => Number.isSafeInteger(v) && v > 0
const digest = v => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v)
const keys = (v, allowed) => v && Object.keys(v).every(k => allowed.includes(k))
const date = v => typeof v === 'string' && validSessionDate(v)
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const interval = s => s && typeof s.from === 'string' && typeof s.to === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(s.from) && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(s.to) && s.from < s.to
const slots = draft => draft.fixedWeeklySchedule?.map(({ day, from, to }) => ({ day, from, to }))

export function validRenewalReview(v) {
  const p = v?.package
  return keys(v, ['id', 'version', 'name', 'trainerId', 'genderPreference', 'expected', 'minimumStartDate', 'package', 'fixedWeeklySchedule', 'clientPreferences'])
    && uuid(v.id) && version(v.version) && typeof v.name === 'string' && v.name.trim() && uuid(v.trainerId) && digest(v.expected) && date(v.minimumStartDate)
    && ['No gender preference', 'Female trainer preferred', 'Male trainer preferred'].includes(v.genderPreference)
    && keys(p, ['id', 'version', 'templateId', 'total', 'validityDays', 'sessionsPerWeek', 'startDate', 'endDate']) && uuid(p.id) && uuid(p.templateId) && version(p.version)
    && version(p.total) && p.total <= 365 && version(p.validityDays) && version(p.sessionsPerWeek) && p.sessionsPerWeek <= 7 && date(p.startDate) && date(p.endDate) && p.startDate <= p.endDate
    && Array.isArray(v.fixedWeeklySchedule) && v.fixedWeeklySchedule.length === p.sessionsPerWeek && new Set(v.fixedWeeklySchedule.map(s => s?.id)).size === p.sessionsPerWeek && new Set(v.fixedWeeklySchedule.map(s => s?.day)).size === p.sessionsPerWeek
    && v.fixedWeeklySchedule.every(s => keys(s, ['id', 'day', 'from', 'to']) && uuid(s.id) && days.includes(s.day) && interval(s))
    && Array.isArray(v.clientPreferences) && v.clientPreferences.length <= 2000 && v.clientPreferences.every(b => keys(b, ['days', 'from', 'to']) && interval(b) && Array.isArray(b.days) && b.days.length > 0 && b.days.every(d => days.includes(d)) && new Set(b.days).size === b.days.length)
}

export function renewalMatchBody(draft) {
  return { ...clientMatchBody(draft), expected: draft.expected ?? draft.renewalExpected,
    trainerId: draft.trainerId || null, fixedWeeklySchedule: slots(draft) ?? null }
}

export function clientRenewalCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Package addition', path: input => `/api/clients/${input.id}/packages`, receiptPath: '/api/client-renewals',
    keyFor: input => input.draft.requestId,
    bodyFor: ({ draft }) => ({ ...clientMatchBody(draft), expected: draft.renewalExpected, trainerId: draft.trainerId,
      trainerVersion: draft.trainerVersion, fixedWeeklySchedule: slots(draft) }),
    validate(value, input) {
      if (!keys(value, ['id', 'version', 'purchaseId']) || value.id !== input.id || !uuid(value.purchaseId) || value.version !== input.draft.expectedVersion + 1) throw new ApiError('API_RESPONSE', 'Package addition could not be verified. Check the original save again.')
      return value
    },
  })
  const sessionFor = async generation => {
    const current = await actionSession(generation)
    if (!['owner', 'admin'].includes(current.user.role)) throw new ApiError('forbidden', 'Only the owner or Admin can add packages.', 403)
    return current.sessionGeneration
  }
  return {
    async review({ id, expectedVersion }, generation) {
      const current = await sessionFor(generation)
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload the client before adding a package.')
      if (save.pendingInput(current)) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous package addition before opening another.')
      const value = await http.get(`/api/clients/${id}/renewal-review`, { expectedGeneration: current })
      if (!validRenewalReview(value) || value.id !== id) throw new ApiError('API_RESPONSE', 'Package renewal details could not be verified.')
      if (value.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This client changed. Reload before adding a package.', 409)
      return value
    },
    async preview({ id, draft }, generation) {
      const current = await sessionFor(generation)
      if (!uuid(id) || !digest(draft?.expected ?? draft?.renewalExpected)) throw new ApiError('INVALID_REQUEST', 'Review the client before matching trainers.')
      if (save.pendingInput(current)) throw new ApiError('SAVE_UNCERTAIN', 'Check the original package addition before changing its schedule.')
      return decodeClientMatches(await http.post(`/api/clients/${id}/renewal-matches`, renewalMatchBody(draft), { csrf: true, idempotencyKey: crypto.randomUUID(), expectedGeneration: current }), draft)
    },
    save(input, generation) {
      const d = input?.draft
      if (!uuid(input?.id) || !uuid(d?.requestId) || !version(d.expectedVersion) || !digest(d.renewalExpected) || !Array.isArray(d.clientPreferences) || !Array.isArray(d.fixedWeeklySchedule)) throw new ApiError('INVALID_REQUEST', 'Review the package and saved client details.')
      return save(input, generation)
    },
    async recover(generation) {
      const recovered = save.pendingInput(generation) ? await save.reconcile(generation) : null
      return { pending: save.pendingInput(generation), recovered }
    },
  }
}
