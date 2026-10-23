import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validSessionDate } from '../app/sessionRules.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const version = v => Number.isSafeInteger(v) && v > 0
const keys = (v, fields) => v && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k))
const time = v => typeof v === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(v)
const fail = () => { throw new ApiError('API_RESPONSE', 'The session booking could not be verified. Check the original save again.') }
const validPosition = v => keys(v, ['id', 'version', 'sessionNumber', 'scheduleState', 'date', 'startsAt', 'endsAt', 'trainerId', 'slotId']) && uuid(v.id) && version(v.version) && uuid(v.trainerId) && (v.slotId === null || uuid(v.slotId))
  && (v.scheduleState === 'open' ? v.sessionNumber === null && v.date === null && v.startsAt === null && v.endsAt === null && v.slotId === null : v.scheduleState === 'booked' && version(v.sessionNumber) && validSessionDate(v.date) && time(v.startsAt) && time(v.endsAt) && v.startsAt < v.endsAt)
export const bookingDraft = reviewed => ({ date: reviewed.session.date ?? '', from: reviewed.session.startsAt ?? '', to: reviewed.session.endsAt ?? '', trainerId: reviewed.session.trainerId })
export const validBookingReview = v => keys(v, ['id', 'version', 'clientId', 'clientVersion', 'purchaseId', 'purchaseVersion', 'expected', 'session', 'trainers']) && uuid(v.id) && version(v.version) && uuid(v.clientId) && version(v.clientVersion) && uuid(v.purchaseId) && version(v.purchaseVersion) && /^[0-9a-f]{64}$/.test(v.expected)
  && validPosition(v.session) && v.session.id === v.id && v.session.version === v.version && Array.isArray(v.trainers) && v.trainers.length <= 2000 && new Set(v.trainers.map(t => t?.id)).size === v.trainers.length
  && v.trainers.every(t => keys(t, ['id', 'version', 'name']) && uuid(t.id) && version(t.version) && typeof t.name === 'string' && t.name.trim())
const validDraft = v => keys(v, ['date', 'from', 'to', 'trainerId']) && validSessionDate(v.date) && time(v.from) && time(v.to) && v.from < v.to && uuid(v.trainerId)

// Preserve one original intent across response loss; recovery reads its actor-private receipt.
export function sessionBookingCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Session booking', path: input => `/api/sessions/${input.sessionId}/booking`, receiptPath: '/api/session-booking-saves',
    bodyFor: ({ reviewed, patch }) => ({ expected: reviewed.expected, date: patch.date, startsAt: patch.from, endsAt: patch.to, trainerId: patch.trainerId }),
    validate(value, input) {
      const { reviewed, patch } = input
      if (!keys(value, ['session', 'client', 'purchase', 'positions', 'messageId']) || !validPosition(value.session) || value.session.id !== input.sessionId || value.session.version < reviewed.version
        || value.session.date !== patch.date || value.session.startsAt !== patch.from || value.session.endsAt !== patch.to || value.session.trainerId !== patch.trainerId
        || !keys(value.client, ['id', 'version']) || value.client.id !== reviewed.clientId || !version(value.client.version) || value.client.version < reviewed.clientVersion
        || !keys(value.purchase, ['id', 'version']) || value.purchase.id !== reviewed.purchaseId || !version(value.purchase.version) || value.purchase.version < reviewed.purchaseVersion
        || (value.messageId !== null && !uuid(value.messageId)) || !Array.isArray(value.positions) || !value.positions.length || value.positions.length > 365 || !value.positions.every(validPosition)
        || new Set(value.positions.map(p => p.id)).size !== value.positions.length || !value.positions.some(p => JSON.stringify(p) === JSON.stringify(value.session))) fail()
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload this session before editing.')
      const { user, sessionGeneration } = await actionSession(generation)
      if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Session booking is unavailable for this account.', 403)
      const pending = save.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous session booking first.')
        return { reviewed: pending.reviewed, draft: pending.patch, uncertain: true }
      }
      const reviewed = await http.get(`/api/sessions/${id}/booking-review`, { expectedGeneration: sessionGeneration })
      if (!validBookingReview(reviewed) || reviewed.id !== id) fail()
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This session changed. Reload before editing.', 409)
      return { reviewed, draft: bookingDraft(reviewed), uncertain: false }
    },
    async save(input, generation) {
      if (!validBookingReview(input?.reviewed) || input.sessionId !== input.reviewed.id || !validDraft(input.patch)) throw new ApiError('INVALID_REQUEST', 'Review this session and choose valid booking details.')
      return save(input, generation)
    },
    reconcile: save.reconcile,
  }
}
