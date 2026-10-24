import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const keys = (value, fields) => value && Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key))
const stamp = value => typeof value === 'string' && Number.isFinite(Date.parse(value))
const base = value => uuid(value?.sessionId) && Number.isSafeInteger(value.version) && value.version > 0 && Number.isSafeInteger(value.whatsappOpenCount) && value.whatsappOpenCount >= 0
const fail = () => { throw new ApiError('API_RESPONSE', 'The original opening action could not be verified.') }

/** Compatibility only: a caller reports an opening; this never opens a device app or claims delivery. */
export function sessionHandoffCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Session opening', roles: ['owner', 'admin', 'trainer'],
    path: input => `/api/sessions/${input.sessionId}/handoff`, receiptPath: '/api/session-handoffs',
    bodyFor: input => ({ expected: input.reviewed.expected }),
    validate(value, input) {
      if (!keys(value, ['sessionId', 'version', 'whatsappOpenedAt', 'whatsappOpenCount']) || !base(value) || !stamp(value.whatsappOpenedAt) || value.sessionId !== input.sessionId || value.version !== input.reviewed.version + 1 || value.whatsappOpenCount !== input.reviewed.whatsappOpenCount + 1) fail()
      return value
    },
  })
  return {
    async mark({ sessionId }, generation) {
      if (!uuid(sessionId)) throw new ApiError('INVALID_REQUEST', 'Choose a persisted session.')
      const { sessionGeneration } = await actionSession(generation)
      const pending = command.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== sessionId) throw new ApiError('SAVE_UNCERTAIN', 'Check the original opening action before recording another.')
        return command(pending, sessionGeneration)
      }
      const reviewed = await http.get(`/api/sessions/${sessionId}/handoff-review`, { expectedGeneration: sessionGeneration })
      if (!keys(reviewed, ['sessionId', 'version', 'expected', 'whatsappOpenedAt', 'whatsappOpenCount']) || !base(reviewed) || reviewed.sessionId !== sessionId || typeof reviewed.expected !== 'string' || !/^[0-9a-f]{64}$/.test(reviewed.expected) || (reviewed.whatsappOpenedAt !== null && !stamp(reviewed.whatsappOpenedAt))) fail()
      return command({ sessionId, reviewed }, sessionGeneration)
    },
  }
}
