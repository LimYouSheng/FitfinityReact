import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validBookingPosition } from './apiSessionBooking.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const keys = (v, fields) => v && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k))
const fail = () => { throw new ApiError('API_RESPONSE', 'The postponement could not be verified. Check the original request again.') }
const validReview = v => keys(v, ['id', 'version', 'expected', 'outcome', 'session']) && uuid(v.id) && Number.isSafeInteger(v.version) && v.version > 0 && /^[0-9a-f]{64}$/.test(v.expected)
  && ['applied', 'requested'].includes(v.outcome) && validBookingPosition(v.session) && v.session.id === v.id && v.session.version === v.version && v.session.scheduleState === 'booked'
const preview = reviewed => ({ reviewed, expected: reviewed.expected, outcome: reviewed.outcome,
  changes: [{ sessionId: reviewed.id, before: { date: reviewed.session.date, from: reviewed.session.startsAt, to: reviewed.session.endsAt, trainerId: reviewed.session.trainerId, weeklySlotId: reviewed.session.slotId }, next: { scheduleState: 'open', date: null, from: null, to: null, weeklySlotId: null } }] })

/** Keep a supervised proposal distinguishable from an applied Open booking. */
export function sessionPostponementCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Session postponement', roles: ['owner', 'admin', 'trainer'], path: v => `/api/sessions/${v.sessionId}/postponement`, receiptPath: '/api/session-postponements',
    keyFor: v => v.requestKey, bodyFor: v => ({ expected: v.expected }),
    validate(value, input) {
      if (!keys(value, ['outcome', 'session', 'requestId', 'messageId', 'changedPositions']) || value.outcome !== input.reviewed.outcome || !validBookingPosition(value.session) || value.session.id !== input.sessionId || value.session.trainerId !== input.reviewed.session.trainerId || !uuid(value.messageId)
        || !Number.isSafeInteger(value.changedPositions) || value.changedPositions < 0 || value.changedPositions > 365) fail()
      if (value.outcome === 'requested') {
        if (!uuid(value.requestId) || value.changedPositions !== 0 || Object.keys(input.reviewed.session).some(k => value.session[k] !== input.reviewed.session[k])) fail()
      } else if (value.requestId !== null || value.session.scheduleState !== 'open' || value.session.version <= input.reviewed.version) fail()
      return value
    },
  })
  return {
    async review({ sessionId }, generation) {
      if (!uuid(sessionId)) throw new ApiError('INVALID_REQUEST', 'Choose a session before postponing.')
      const { sessionGeneration } = await actionSession(generation), pending = save.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== sessionId) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous postponement first.')
        return { ...preview(pending.reviewed), requestKey: pending.requestKey, uncertain: true }
      }
      const reviewed = await http.get(`/api/sessions/${sessionId}/postponement-review`, { expectedGeneration: sessionGeneration })
      if (!validReview(reviewed) || reviewed.id !== sessionId) fail()
      return { ...preview(reviewed), uncertain: false }
    },
    async save(input, generation) {
      if (!validReview(input?.reviewed) || input.sessionId !== input.reviewed.id || input.expected !== input.reviewed.expected || !uuid(input.requestKey)) throw new ApiError('INVALID_REQUEST', 'Review the original postponement before saving.')
      return save(input, generation)
    },
  }
}
