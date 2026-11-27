import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

function profile(value, userId) {
  if (!value || value.id !== userId || !Number.isSafeInteger(value.version) || value.version < 1 ||
    ['name', 'email', 'phone_country_code', 'phone_number', 'birthday', 'gender'].some(key => typeof value[key] !== 'string')) {
    throw new ApiError('API_RESPONSE', 'The Owner profile could not be verified.')
  }
  return value
}

export function ownerProfileCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Owner profile', roles: ['owner'], path: () => '/api/owner-profile', receiptPath: '/api/owner-profile/saves',
    bodyFor: ({ expectedVersion, details }) => ({ expectedVersion, details }),
    validate(value, input) {
      const result = profile(value, input.id)
      if (result.version !== input.expectedVersion + 1 || Object.entries(input.details).some(([key, expected]) => result[key] !== expected)) throw new ApiError('API_RESPONSE', 'Check the original Owner profile save before continuing.')
      return result
    },
  })
  return {
    async read(generation) {
      const { user, sessionGeneration } = await actionSession(generation)
      if (user.role !== 'owner') throw new ApiError('forbidden', 'Owner profile is unavailable.', 403)
      return profile(await http.get('/api/owner-profile', { expectedGeneration: sessionGeneration }), user.id)
    },
    save,
  }
}
