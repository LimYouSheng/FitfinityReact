import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validSessionDate } from '../app/sessionRules.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const version = v => Number.isSafeInteger(v) && v > 0
const keys = (v, allowed) => v && Object.keys(v).every(k => allowed.includes(k))
const rows = v => Array.isArray(v) && v.length <= 2000 && new Set(v.map(r => r?.id)).size === v.length
const time = v => typeof v === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(v)
const fail = () => { throw new ApiError('API_RESPONSE', 'The Trainer deactivation could not be verified. Check the original request again.') }
export function validTrainerDeactivation(v) {
  return keys(v, ['id', 'version', 'name', 'accountId', 'accountVersion', 'expected', 'sessions']) && uuid(v.id) && version(v.version)
    && typeof v.name === 'string' && v.name.trim() && /^[0-9a-f]{64}$/.test(v.expected)
    && (v.accountId === null ? v.accountVersion === null : uuid(v.accountId) && version(v.accountVersion))
    && rows(v.sessions) && v.sessions.every(s => keys(s, ['id', 'version', 'clientId', 'clientName', 'purchaseId', 'trainerId', 'scheduleState', 'date', 'startsAt', 'endsAt', 'choices'])
      && uuid(s.id) && version(s.version) && uuid(s.clientId) && uuid(s.purchaseId) && s.trainerId === v.id && typeof s.clientName === 'string'
      && (s.scheduleState === 'open' ? [s.date, s.startsAt, s.endsAt].every(x => x === null) : s.scheduleState === 'booked' && validSessionDate(s.date) && time(s.startsAt) && time(s.endsAt) && s.startsAt < s.endsAt)
      && rows(s.choices) && s.choices.every(t => keys(t, ['id', 'name', 'version', 'error']) && uuid(t.id) && t.id !== v.id && version(t.version) && typeof t.name === 'string' && (t.error === null || typeof t.error === 'string' && t.error.trim())))
}
const validSelection = (reviewed, replacements) => replacements && typeof replacements === 'object' && !Array.isArray(replacements)
  && Object.entries(replacements).every(([id, trainer]) => reviewed.sessions.some(s => s.id === id && s.choices.some(t => t.id === trainer)))
export function trainerDeactivationCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Trainer deactivation', path: input => `/api/trainers/${input.id}/deactivation`, receiptPath: '/api/trainer-deactivations',
    bodyFor: ({ reviewed, replacements }) => ({ expected: reviewed.expected, replacements }),
    validate(value, input) {
      if (!keys(value, ['id', 'version', 'status']) || value.id !== input.id || value.version !== input.reviewed.version + 1 || value.status !== 'inactive') fail()
      return value
    },
  })
  const sessionFor = async generation => {
    const current = await actionSession(generation)
    if (!['owner', 'admin'].includes(current.user.role)) throw new ApiError('forbidden', 'Trainer deactivation is unavailable for this account.', 403)
    return current.sessionGeneration
  }
  return {
    async review({ id, expectedVersion }, generation) {
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload the Trainer before deactivating.')
      const current = await sessionFor(generation), pending = save.pendingInput(current)
      if (pending) {
        if (pending.id !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous deactivation first.')
        return { reviewed: pending.reviewed, replacements: pending.replacements, uncertain: true }
      }
      const reviewed = await http.get(`/api/trainers/${id}/deactivation-review`, { expectedGeneration: current })
      if (!validTrainerDeactivation(reviewed) || reviewed.id !== id) fail()
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This Trainer changed. Reload before deactivating.', 409)
      return { reviewed, replacements: {}, uncertain: false }
    },
    async preview({ id, reviewed, replacements }, generation) {
      if (!validTrainerDeactivation(reviewed) || reviewed.id !== id || !validSelection(reviewed, replacements)) throw new ApiError('INVALID_REQUEST', 'Review the replacement batch before continuing.')
      const current = await sessionFor(generation)
      if (save.pendingInput(current)) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous deactivation first.')
      const result = await http.post(`/api/trainers/${id}/deactivation-review`, { expected: reviewed.expected, replacements }, { csrf: true, idempotencyKey: crypto.randomUUID(), expectedGeneration: current })
      if (!validTrainerDeactivation(result) || result.id !== id || result.expected !== reviewed.expected) fail()
      return result
    },
    async save(input, generation) {
      if (!validTrainerDeactivation(input?.reviewed) || input.id !== input.reviewed.id || !validSelection(input.reviewed, input.replacements)
        || input.reviewed.sessions.some(s => !s.choices.some(t => t.id === input.replacements[s.id] && t.error === null))) throw new ApiError('INVALID_REQUEST', 'Review an available replacement for every remaining session.')
      return save(input, generation)
    },
    async reconcile(generation) {
      if (!save.pendingInput(generation)) return null
      await save.reconcile(generation)
      return save.pendingInput(generation)
    },
  }
}
