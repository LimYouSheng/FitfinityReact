import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { bookingDraft, validBookingPosition, validBookingReview } from './apiSessionBooking.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const fail = () => { throw new ApiError('API_RESPONSE', 'The session change could not be verified. Check the original request.') }
const same = (a, b) => Object.keys(a).every(k => a[k] === b[k])
const validReview = v => {
  if (!v || !['time', 'trainer'].includes(v.kind) || !['applied', 'requested'].includes(v.outcome)) return false
  const { kind: _kind, outcome: _outcome, ...booking } = v
  return validBookingReview(booking)
}
const draftFor = review => review.kind === 'time' ? (({ date, from, to }) => ({ date, from, to }))(bookingDraft(review)) : { replacementTrainerId: '' }

/** One original command across both request kinds, including loss after reassignment. */
export function sessionChangeCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Trainer session change', roles: ['trainer'], path: v => `/api/sessions/${v.sessionId}/${v.kind}-change`, receiptPath: '/api/session-changes',
    bodyFor: v => v.kind === 'time' ? { expected: v.reviewed.expected, date: v.patch.date, startsAt: v.patch.from, endsAt: v.patch.to } : { expected: v.reviewed.expected, trainerId: v.patch.replacementTrainerId },
    validate(value, input) {
      const { reviewed, patch, kind } = input
      if (!value || Object.keys(value).length !== 5 || value.kind !== kind || !['applied', 'requested'].includes(value.outcome) || !validBookingPosition(value.session) || value.session.id !== input.sessionId || value.session.version < reviewed.version
        || (value.messageId !== null && !uuid(value.messageId))) fail()
      if (value.outcome === 'requested') {
        if (reviewed.outcome !== 'requested' || !uuid(value.requestId) || !uuid(value.messageId) || !same(reviewed.session, value.session)) fail()
      } else {
        if (value.requestId !== null || (reviewed.outcome === 'requested' && !same(reviewed.session, value.session))) fail()
        if (kind === 'time' ? value.session.date !== patch.date || value.session.startsAt !== patch.from || value.session.endsAt !== patch.to || value.session.trainerId !== reviewed.session.trainerId
          : value.session.trainerId !== patch.replacementTrainerId || ['date', 'startsAt', 'endsAt', 'scheduleState'].some(k => value.session[k] !== reviewed.session[k])) fail()
        if (!same(reviewed.session, value.session) && (value.session.version <= reviewed.version || !uuid(value.messageId))) fail()
      }
      return value
    },
  })
  return {
    async review({ id, kind, expectedVersion }, generation) {
      if (!uuid(id) || !['time', 'trainer'].includes(kind) || !Number.isSafeInteger(expectedVersion) || expectedVersion < 1) throw new ApiError('INVALID_REQUEST', 'Reload this session before requesting a change.')
      const { user, sessionGeneration } = await actionSession(generation)
      if (user.role !== 'trainer') throw new ApiError('forbidden', 'Only the assigned Trainer can request this change.', 403)
      const pending = command.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== id || pending.kind !== kind) throw new ApiError('SAVE_UNCERTAIN', 'Check the original session change before starting another.')
        return { reviewed: pending.reviewed, draft: pending.patch, uncertain: true }
      }
      const reviewed = await http.get(`/api/sessions/${id}/change-review?kind=${kind}`, { expectedGeneration: sessionGeneration })
      if (!validReview(reviewed) || reviewed.id !== id || reviewed.kind !== kind) fail()
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This session changed. Reload before requesting a change.', 409)
      return { reviewed, draft: draftFor(reviewed), uncertain: false }
    },
    async save(input, generation) {
      if (!validReview(input?.reviewed) || input.sessionId !== input.reviewed.id || input.kind !== input.reviewed.kind || !input.patch) throw new ApiError('INVALID_REQUEST', 'Review the original session change before saving.')
      return command(input, generation)
    },
    pendingInput: command.pendingInput,
    reconcile: command.reconcile,
  }
}
