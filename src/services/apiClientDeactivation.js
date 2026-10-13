import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const version = value => Number.isSafeInteger(value) && value > 0
const keys = (value, allowed) => value && Object.keys(value).every(key => allowed.includes(key))
export function validDeactivationReview(value) {
  return keys(value, ['id', 'version', 'name', 'trainerId', 'purchases']) && uuid(value.id) && version(value.version) && uuid(value.trainerId)
    && typeof value.name === 'string' && value.name.trim() && Array.isArray(value.purchases) && value.purchases.length <= 2000
    && value.purchases.every(p => keys(p, ['id', 'version', 'status', 'name']) && uuid(p.id) && version(p.version) && ['active', 'inactive'].includes(p.status) && typeof p.name === 'string' && p.name.trim())
    && new Set(value.purchases.map(p => p.id)).size === value.purchases.length
}
export function clientDeactivationCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Client deactivation', path: input => `/api/clients/${input.id}/deactivation`, receiptPath: '/api/client-deactivations',
    bodyFor: ({ reviewed }) => ({ expectedVersion: reviewed.version, expectedTrainerId: reviewed.trainerId, purchases: reviewed.purchases.map(({ id, version, status }) => ({ id, version, status })) }),
    validate(value, input) {
      if (!keys(value, ['id', 'version', 'status']) || value.id !== input.id || value.version !== input.reviewed.version + 1 || value.status !== 'inactive') throw new ApiError('API_RESPONSE', 'The deactivation could not be verified. Check the original request again.')
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      const { user, sessionGeneration } = await actionSession(generation)
      if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Client deactivation is unavailable for this account.', 403)
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload the client before deactivating.')
      const pending = save.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.id !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous client deactivation before starting another.')
        return { reviewed: pending.reviewed, uncertain: true }
      }
      const reviewed = await http.get(`/api/clients/${id}/deactivation`, { expectedGeneration: sessionGeneration })
      if (!validDeactivationReview(reviewed) || reviewed.id !== id) throw new ApiError('API_RESPONSE', 'The client and purchased packages could not be verified.')
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This client changed. Reload and review before deactivating.', 409)
      return { reviewed, uncertain: false }
    },
    save(input, generation) {
      if (!validDeactivationReview(input.reviewed) || input.reviewed.id !== input.id) throw new ApiError('INVALID_REQUEST', 'Review the client and packages before deactivating.')
      return save(input, generation)
    },
    async recover(generation) {
      if (save.pendingInput(generation)) await save.reconcile(generation)
      return save.pendingInput(generation)
    },
  }
}
