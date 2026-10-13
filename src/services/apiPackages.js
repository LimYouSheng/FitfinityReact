import { ApiError } from './apiClient.js'
import { directoryPackage } from './apiDirectory.js'
import { reconciledCommand } from './apiCommand.js'

export function packageCommands(http, actionSession) {
  return reconciledCommand(http, actionSession, {
    label: 'Package setup', path: () => '/api/packages', receiptPath: '/api/packages/saves',
    validate(value, input) {
      const saved = directoryPackage(value)
      if (saved.version !== (input.id ? input.expectedVersion + 1 : 1) || (input.id && saved.id !== input.id) || saved.name !== input.draft.name.trim() || saved.total !== input.draft.total || saved.status !== input.draft.status) throw new ApiError('API_RESPONSE', 'The package save could not be verified. Check the same save again.')
      return saved
    },
  })
}
