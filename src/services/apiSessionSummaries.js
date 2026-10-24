import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const keys = (v, fields) => v && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k))
const base = v => uuid(v?.sessionId) && Number.isSafeInteger(v.version) && v.version > 0 && typeof v.summary === 'string' && v.summary.length <= 20000
const validReview = v => keys(v, ['sessionId', 'version', 'expected', 'summary']) && base(v) && /^[0-9a-f]{64}$/.test(v.expected)
const invalid = () => { throw new ApiError('INVALID_REQUEST', 'Review the session and enter a client-facing summary.') }
const fail = () => { throw new ApiError('API_RESPONSE', 'The summary save could not be verified. Check the original save.') }

/** Keep reviewed summary intent frozen until its original command is resolved. */
export function sessionSummaryCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Client summary', roles: ['owner', 'admin', 'trainer'],
    path: v => `/api/sessions/${v.sessionId}/summary`, receiptPath: '/api/session-summaries',
    bodyFor: v => ({ expected: v.reviewed.expected, summary: v.summary }),
    validate(value, input) {
      if (!keys(value, ['sessionId', 'version', 'summary', 'savedAt']) || !base(value) || value.sessionId !== input.sessionId || value.version <= input.reviewed.version || value.summary !== input.summary || typeof value.savedAt !== 'string' || !Number.isFinite(Date.parse(value.savedAt))) fail()
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      if (!uuid(id) || !Number.isSafeInteger(expectedVersion) || expectedVersion < 1) invalid()
      const { sessionGeneration } = await actionSession(generation)
      const pending = command.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the original summary before editing another.')
        return { reviewed: pending.reviewed, draft: pending.summary, uncertain: true }
      }
      const viewed = await http.get(`/api/sessions/${id}/summary-review`, { expectedGeneration: sessionGeneration })
      if (!validReview(viewed) || viewed.sessionId !== id) fail()
      if (viewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This session changed. Reload before editing its summary.', 409)
      return { reviewed: viewed, draft: viewed.summary, uncertain: false }
    },
    async save(input, generation) {
      if (!validReview(input?.reviewed) || input.sessionId !== input.reviewed.sessionId || typeof input.summary !== 'string' || !input.summary.trim() || input.summary.length > 20000) invalid()
      return command({ sessionId: input.sessionId, reviewed: input.reviewed, summary: input.summary.trim() }, generation)
    },
    pendingInput: command.pendingInput,
  }
}
