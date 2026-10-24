import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
const version = value => Number.isSafeInteger(value) && value > 0
const failure = () => { throw new ApiError('API_RESPONSE', 'The package action could not be verified. Check the original request.') }
const path = input => `/api/clients/${input.id}/purchases/${input.packageId}`

// Keep the reviewed target, checkbox and original command together through uncertain responses.
export function packageActionCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Package action', path: input => `${path(input)}/actions`, receiptPath: '/api/package-actions',
    bodyFor: input => ({ operation: input.operation, expected: input.reviewed.expected, deleteUpcomingSessions: input.deleteUpcomingSessions }),
    validate(value, input) {
      if (!uuid(value?.id) || value.clientId !== input.id || value.purchaseId !== input.packageId || !version(value.purchaseVersion)
        || value.status !== 'inactive' || !Array.isArray(value.deletedSessionIds) || !value.deletedSessionIds.every(uuid)
        || value.deletedSessionIds.some(id => !input.reviewed.eligible.some(row => row.id === id))
        || value.messageId !== null && !uuid(value.messageId) || value.undoUntil !== null && !Number.isFinite(Date.parse(value.undoUntil))) failure()
      const expected = input.operation === 'delete_sessions' || input.deleteUpcomingSessions && input.reviewed.status === 'active' ? input.reviewed.eligible.map(row => row.id).sort() : []
      if (JSON.stringify([...value.deletedSessionIds].sort()) !== JSON.stringify(expected)) failure()
      return value
    },
  })
  return {
    async review(input, generation) {
      const current = await actionSession(generation)
      if (!['owner', 'admin'].includes(current.user.role)) throw new ApiError('forbidden', 'Package actions require Owner or Admin.', 403)
      if (!uuid(input.id) || !uuid(input.packageId) || !['deactivate', 'delete_sessions'].includes(input.operation)) throw new ApiError('INVALID_REQUEST', 'Choose a package action.')
      const pending = save.pendingInput(generation)
      if (pending) {
        if (pending.id !== input.id || pending.packageId !== input.packageId || pending.operation !== input.operation) throw new ApiError('SAVE_UNCERTAIN', 'Check the original package action first.')
        return { ...pending, uncertain: true }
      }
      const reviewed = await http.get(`${path(input)}/action-review?operation=${input.operation}`, { expectedGeneration: generation })
      if (reviewed?.clientId !== input.id || reviewed.purchaseId !== input.packageId || reviewed.operation !== input.operation || !digest(reviewed.expected)
        || !version(reviewed.clientVersion) || !version(reviewed.purchaseVersion) || !['active', 'inactive'].includes(reviewed.status)
        || !Array.isArray(reviewed.eligible) || reviewed.eligible.length > 365 || !reviewed.eligible.every(row => uuid(row.id) && version(row.version))
        || new Set(reviewed.eligible.map(row => row.id)).size !== reviewed.eligible.length) failure()
      return { ...input, reviewed, deleteUpcomingSessions: false, uncertain: false }
    },
    save(input, generation) {
      if (!input.reviewed || !digest(input.reviewed.expected) || input.reviewed.clientId !== input.id || input.reviewed.purchaseId !== input.packageId
        || input.reviewed.operation !== input.operation || typeof input.deleteUpcomingSessions !== 'boolean') throw new ApiError('INVALID_REQUEST', 'Review the package action first.')
      return save(input, generation)
    },
    reconcile: generation => save.reconcile(generation),
    pendingInput: generation => save.pendingInput(generation),
  }
}


export function packageUndoCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Package deletion Undo', path: input => `/api/package-actions/${input.actionId}/undo`, receiptPath: '/api/package-undos',
    bodyFor: input => ({ expected: input.expected }),
    validate(value) { if (!uuid(value?.id) || value.status !== 'undone' || !Number.isFinite(Date.parse(value.undoneAt))) failure(); return value },
  })
  return async (input, generation) => {
    const current = await actionSession(generation)
    if (!['owner', 'admin'].includes(current.user.role) || !uuid(input.id)) throw new ApiError('forbidden', 'Package deletion Undo is unavailable.', 403)
    const pending = save.pendingInput(generation)
    if (pending) {
      if (pending.id !== input.id) throw new ApiError('SAVE_UNCERTAIN', 'Check the original Undo first.')
      const recovered = await save.reconcile(generation)
      if (!recovered) throw new ApiError('SAVE_UNCERTAIN', 'The original Undo is not confirmed yet. Check again.')
      return recovered.result
    }
    const messages = await http.get('/api/messages', { expectedGeneration: generation })
    if (!Array.isArray(messages)) failure()
    const message = messages.find(row => row.id === input.id)
    if (message?.undo?.kind !== 'package_deletion') throw new ApiError('OPERATION_UNAVAILABLE', 'Undo is unavailable for this message.')
    const review = await http.get(`/api/package-actions/${message.undo.id}/undo-review`, { expectedGeneration: generation })
    if (review.id !== message.undo.id || review.messageId !== input.id || !digest(review.expected)) failure()
    return save({ id: input.id, actionId: review.id, expected: review.expected }, generation)
  }
}
