import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validSessionDate } from '../app/sessionRules.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const version = value => Number.isSafeInteger(value) && value > 0
const keys = (value, allowed) => value && Object.keys(value).every(key => allowed.includes(key))
const named = value => keys(value, ['id', 'name']) && uuid(value.id) && typeof value.name === 'string' && value.name.trim()
const time = value => typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)
const unique = rows => Array.isArray(rows) && rows.length <= 2000 && new Set(rows.map(r => r?.id)).size === rows.length
const fail = () => { throw new ApiError('API_RESPONSE', 'The Trainer assignment could not be verified. Check the original request again.') }
export function validAssignmentReview(value) {
  return keys(value, ['id', 'version', 'name', 'expected', 'current', 'purchases', 'sessions', 'choices', 'history']) && uuid(value.id) && version(value.version)
    && typeof value.name === 'string' && value.name.trim() && /^[0-9a-f]{64}$/.test(value.expected) && named(value.current)
    && unique(value.purchases) && value.purchases.every(p => keys(p, ['id', 'version', 'trainerId', 'name']) && uuid(p.id) && version(p.version) && uuid(p.trainerId) && typeof p.name === 'string')
    && unique(value.sessions) && value.sessions.every(s => keys(s, ['id', 'version', 'trainerId', 'purchaseId', 'scheduleState', 'date', 'startsAt', 'endsAt']) && uuid(s.id) && version(s.version) && uuid(s.trainerId) && value.purchases.some(p => p.id === s.purchaseId)
      && (s.scheduleState === 'open' ? [s.date, s.startsAt, s.endsAt].every(v => v === null) : s.scheduleState === 'booked' && validSessionDate(s.date) && time(s.startsAt) && time(s.endsAt) && s.startsAt < s.endsAt))
    && unique(value.choices) && value.choices.every(t => keys(t, ['id', 'version', 'name', 'error']) && uuid(t.id) && t.id !== value.current.id && version(t.version) && typeof t.name === 'string' && (t.error === null || typeof t.error === 'string' && t.error.trim()))
    && unique(value.history) && value.history.every(h => keys(h, ['id', 'at', 'actor', 'previous', 'replacement']) && uuid(h.id) && Number.isFinite(Date.parse(h.at)) && named(h.actor) && named(h.previous) && named(h.replacement))
}
export function clientAssignmentCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Trainer reassignment', path: input => `/api/clients/${input.id}/trainer-assignment`, receiptPath: '/api/client-trainer-assignments',
    bodyFor: ({ reviewed, trainerId }) => ({ expected: reviewed.expected, trainerId, purchaseId: reviewed.purchases[0]?.id }),
    validate(value, input) {
      if (!keys(value, ['id', 'version', 'trainerId', 'eventId']) || value.id !== input.id || value.version !== input.reviewed.version + 1 || value.trainerId !== input.trainerId || !uuid(value.eventId)) fail()
      return value
    },
  })
  const sessionFor = async generation => {
    const current = await actionSession(generation)
    if (!['owner', 'admin'].includes(current.user.role)) throw new ApiError('forbidden', 'Trainer reassignment is unavailable for this account.', 403)
    return current.sessionGeneration
  }
  return {
    async review({ id, expectedVersion, packageId }, generation) {
      if (!uuid(id) || !version(expectedVersion) || (packageId !== undefined && !uuid(packageId))) throw new ApiError('INVALID_REQUEST', 'Reload the client before reassigning.')
      const current = await sessionFor(generation), pending = save.pendingInput(current)
      if (pending) {
        if (pending.id !== id || (packageId && pending.reviewed.purchases[0]?.id !== packageId)) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous reassignment first.')
        return { reviewed: pending.reviewed, trainerId: pending.trainerId, uncertain: true }
      }
      const reviewed = await http.get(`/api/clients/${id}/trainer-assignment-review${packageId ? `?purchaseId=${packageId}` : ''}`, { expectedGeneration: current })
      if (!validAssignmentReview(reviewed) || reviewed.id !== id || (packageId && (reviewed.purchases.length !== 1 || reviewed.purchases[0].id !== packageId))) fail()
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This client changed. Reload before reassigning.', 409)
      return { reviewed, trainerId: '', uncertain: false }
    },
    async save(input, generation) {
      if (!validAssignmentReview(input?.reviewed) || input.id !== input.reviewed.id || !input.reviewed.choices.some(t => t.id === input.trainerId && t.error === null)) throw new ApiError('INVALID_REQUEST', 'Review an available replacement Trainer before saving.')
      return save(input, generation)
    },
    async reconcile(generation) {
      if (!save.pendingInput(generation)) return null
      await save.reconcile(generation)
      return save.pendingInput(generation)
    },
  }
}
