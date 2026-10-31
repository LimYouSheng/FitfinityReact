import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { ADMIN_APPROVAL_FIELDS } from '../app/adminApprovals.js'

export function adminDetails(value) {
  if (!value || !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value.id) || value.role !== 'admin' ||
      !Number.isSafeInteger(value.version) || value.version < 1 || !['active', 'inactive'].includes(value.status) ||
      !value.details || ['name', 'email', 'phone_country_code', 'phone_number', 'birthday', 'gender'].some(key => typeof value.details[key] !== 'string') ||
      !value.approvalNeeded || Object.keys(value.approvalNeeded).length !== ADMIN_APPROVAL_FIELDS.length ||
      ADMIN_APPROVAL_FIELDS.some(([key]) => typeof value.approvalNeeded[key] !== 'boolean')) {
    throw new ApiError('API_RESPONSE', 'Admin details could not be verified. Reload before continuing.')
  }
  return value
}

export function adminManagementCommands(http, actionSession) {
  const update = reconciledCommand(http, actionSession, {
    label: 'Admin account', roles: ['owner'], path: input => `/api/staff/admins/${input.id}`,
    receiptPath: '/api/staff/admins/changes', bodyFor: input => input.body,
    validate(value, input) {
      const result = adminDetails(value)
      if (result.id !== input.id || result.version !== input.body.expectedVersion + 1) throw new ApiError('API_RESPONSE', 'Check the original Admin save before continuing.')
      return result
    },
  })
  const read = async (id, generation) => {
    const { user } = await actionSession(generation)
    if (user.role !== 'owner') throw new ApiError('forbidden', 'Admin management is available to the Owner.', 403)
    const result = await http.get(`/api/staff/admins${id ? `/${id}` : ''}`, { expectedGeneration: generation })
    if (id) {
      const value = adminDetails(result)
      if (value.id !== id) throw new ApiError('API_RESPONSE', 'The requested Admin could not be verified.')
      return value
    }
    if (!Array.isArray(result) || new Set(result.map(row => row.id)).size !== result.length) throw new ApiError('API_RESPONSE', 'The Admin list could not be verified.')
    return result.map(adminDetails)
  }
  return { read, update }
}
