import { getProtectedMedia } from './apiLibraryMedia.js'
import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { ADMIN_APPROVAL_FIELDS } from '../app/adminApprovals.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
function verified(value) {
  if (!value || !uuid(value.id) || !uuid(value.actorId) || !Number.isSafeInteger(value.version) || value.version < 1 ||
      typeof value.actorName !== 'string' || !value.actorName.trim() || typeof value.operation !== 'string' ||
      !ADMIN_APPROVAL_FIELDS.some(([area]) => area === value.area) || !value.body || typeof value.body !== 'object' || Array.isArray(value.body) ||
      !['pending', 'approved', 'rejected', 'cancelled'].includes(value.status) || !Number.isFinite(Date.parse(value.createdAt)) ||
      (value.status === 'pending' ? value.resolvedAt !== null || value.resolvedBy !== null : !Number.isFinite(Date.parse(value.resolvedAt)) || !uuid(value.resolvedBy))) {
    throw new ApiError('API_RESPONSE', 'The approval request could not be verified.')
  }
  return value
}

export function adminRequestCommands(http, actionSession, fetchImpl = globalThis.fetch) {
  const decide = reconciledCommand(http, actionSession, {
    label: 'Admin approval', path: input => `/api/admin-requests/${input.id}/decision`,
    receiptPath: '/api/admin-requests/decisions', bodyFor: input => ({ expectedVersion: input.expectedVersion, decision: input.decision }),
    validate(value, input) {
      const result = verified(value)
      if (result.id !== input.id || result.version !== input.expectedVersion + 1 || result.status !== input.decision) {
        throw new ApiError('API_RESPONSE', 'Check the original approval decision before continuing.')
      }
      return result
    },
  })
  return {
    async read(generation) {
      const { user } = await actionSession(generation)
      if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Admin requests are unavailable.', 403)
      await decide.reconcile(generation)
      const rows = await http.get('/api/admin-requests', { expectedGeneration: generation })
      if (!Array.isArray(rows) || rows.length > 2000 || new Set(rows.map(row => row?.id)).size !== rows.length) throw new ApiError('API_RESPONSE', 'Admin requests could not be verified.')
      const items = rows.map(verified)
      if (user.role === 'admin' && items.some(item => item.actorId !== user.id)) throw new ApiError('API_RESPONSE', 'Admin request ownership could not be verified.')
      return { items, pending: decide.pendingInput(generation) }
    },
    async decide(input, generation) {
      if (!uuid(input?.id) || !Number.isSafeInteger(input.expectedVersion) || input.expectedVersion < 1 || !['approved', 'rejected', 'cancelled'].includes(input.decision)) throw new ApiError('INVALID_REQUEST', 'Review the original request before deciding.', 422)
      const { user } = await actionSession(generation)
      if (input.decision !== 'cancelled' && user.role !== 'owner') throw new ApiError('forbidden', 'Only the Owner can approve or reject Admin requests.', 403)
      return decide(input, generation)
    },
    async attachment({ id }, generation) {
      if (!uuid(id)) throw new ApiError('INVALID_REQUEST', 'Review the original proposal.', 422)
      await actionSession(generation)
      return getProtectedMedia(http, fetchImpl, `/api/admin-requests/${id}/attachment`, generation, () => {
        if (http.generation() !== generation) throw new ApiError('SESSION_CHANGED', 'Your sign-in changed.')
      })
    },
    recover: generation => decide.reconcile(generation),
  }
}
