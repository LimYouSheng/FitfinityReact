import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validSignature } from '../app/signature.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const keys = (v, fields) => v && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k))
const integer = v => Number.isSafeInteger(v) && v >= 0
const validReview = v => keys(v, ['sessionId', 'version', 'expected', 'previousMethod', 'used', 'total']) && uuid(v.sessionId) && integer(v.version) && v.version > 0 && /^[0-9a-f]{64}$/.test(v.expected) && [null, 'late_no_show'].includes(v.previousMethod) && integer(v.used) && integer(v.total) && v.used <= v.total
const invalid = () => { throw new ApiError('INVALID_REQUEST', 'Review the session and its acknowledgement before completing it.') }
const fail = () => { throw new ApiError('API_RESPONSE', 'Completion could not be verified. Check the original acknowledgement.') }

/** Retain the exact completion intent until its original actor-private receipt resolves. */
export function sessionAcknowledgementCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Session acknowledgement', roles: ['owner', 'admin', 'trainer'],
    path: v => `/api/sessions/${v.sessionId}/acknowledgement`, receiptPath: '/api/session-acknowledgements',
    bodyFor: v => ({ expected: v.reviewed.expected, ...v.acknowledgement }),
    validate(value, input) {
      if (!keys(value, ['sessionId', 'version', 'acknowledgementId', 'method', 'sequence', 'used', 'savedAt']) || value.sessionId !== input.sessionId || !integer(value.version) || value.version <= input.reviewed.version || !uuid(value.acknowledgementId) || value.method !== input.acknowledgement.method || value.sequence !== (input.reviewed.previousMethod ? 2 : 1) || value.used !== input.reviewed.used + (input.reviewed.previousMethod ? 0 : 1) || typeof value.savedAt !== 'string' || !Number.isFinite(Date.parse(value.savedAt))) fail()
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      if (!uuid(id) || !integer(expectedVersion) || expectedVersion < 1) invalid()
      const { sessionGeneration } = await actionSession(generation)
      const pending = command.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the original acknowledgement before completing another session.')
        return { reviewed: pending.reviewed, draft: pending.acknowledgement, uncertain: true }
      }
      const viewed = await http.get(`/api/sessions/${id}/acknowledgement-review`, { expectedGeneration: sessionGeneration })
      if (!validReview(viewed) || viewed.sessionId !== id) fail()
      if (viewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This session changed. Reload before completing it.', 409)
      return { reviewed: viewed, uncertain: false }
    },
    async save(input, generation) {
      const a = input?.acknowledgement
      if (!validReview(input?.reviewed) || input.sessionId !== input.reviewed.sessionId || !a || !['signature', 'late_no_show'].includes(a.method) || typeof a.note !== 'string' || a.note.length > 10000 || (input.reviewed.previousMethod && a.method !== 'signature')) invalid()
      if (a.method === 'signature' && (typeof a.signerName !== 'string' || !a.signerName.trim() || a.signerName.length > 200 || !validSignature(a.signature))) invalid()
      const acknowledgement = { method: a.method, note: a.note.trim(), ...(a.method === 'signature' ? { signerName: a.signerName.trim(), signature: a.signature } : {}) }
      return command({ sessionId: input.sessionId, reviewed: input.reviewed, acknowledgement }, generation)
    },
    pendingInput: command.pendingInput,
  }
}
