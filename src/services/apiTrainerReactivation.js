import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const version = value => Number.isSafeInteger(value) && value > 0
const validReview = value => value && uuid(value.id) && version(value.version)
  && (value.accountId === null ? value.accountVersion === null : uuid(value.accountId) && version(value.accountVersion))
  && Object.keys(value).every(key => ['id', 'version', 'accountId', 'accountVersion'].includes(key))

export function trainerReactivationCommands(http, actionSession) {
  let uncertain = null
  const save = reconciledCommand(http, actionSession, {
    label: 'Trainer reactivation',
    path: input => `/api/trainers/${input.id}/reactivation`, receiptPath: '/api/trainer-reactivations',
    bodyFor: ({ reviewed }) => ({ expectedVersion: reviewed.version, expectedAccountId: reviewed.accountId, expectedAccountVersion: reviewed.accountVersion }),
    validate(value, input) {
      if (value?.id !== input.id || value.version !== input.reviewed.version + 1 || value.status !== 'active' || Object.keys(value).some(key => !['id', 'version', 'status'].includes(key))) throw new ApiError('API_RESPONSE', 'The reactivation could not be verified. Check the same reactivation again.')
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      const { user, sessionGeneration } = await actionSession(generation)
      if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Trainer reactivation is unavailable for this account.', 403)
      if (uncertain?.generation !== sessionGeneration) uncertain = null
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload and review the trainer before continuing.')
      if (uncertain) {
        if (uncertain.input.id !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous trainer reactivation before starting another.')
        return { reviewed: structuredClone(uncertain.input.reviewed), uncertain: true }
      }
      const reviewed = await http.get(`/api/trainers/${id}/reactivation`, { expectedGeneration: sessionGeneration })
      if (!validReview(reviewed) || reviewed.id !== id) throw new ApiError('API_RESPONSE', 'The trainer account could not be verified. Reload before continuing.')
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This trainer changed. Reload and review the current record before reactivating.', 409)
      return { reviewed, uncertain: false }
    },
    async save(input, generation) {
      if (!validReview(input.reviewed) || input.reviewed.id !== input.id) throw new ApiError('INVALID_REQUEST', 'Review the trainer account before reactivating.')
      const { sessionGeneration } = await actionSession(generation)
      if (uncertain?.generation !== sessionGeneration) uncertain = null
      try {
        const result = await save(input, generation)
        uncertain = null
        return result
      } catch (error) {
        if (!(error.status >= 400 && error.status < 500) && !['SESSION_CHANGED', 'SESSION_EXPIRED', 'forbidden'].includes(error.code)) uncertain ??= { input: structuredClone(input), generation: sessionGeneration }
        else if (error.code !== 'SAVE_UNCERTAIN') uncertain = null
        throw error
      }
    },
  }
}
