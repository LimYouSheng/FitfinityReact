import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const fields = ['availability', 'sessionTime', 'trainerReassignment', 'fixedWeeklySchedule']
export function trainerApprovalCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Approval settings', path: input => `/api/trainers/${input.id}/approvals`, receiptPath: '/api/trainer-approval-saves',
    bodyFor: ({ expectedVersion, approvalNeeded }) => ({ expectedVersion, approvalNeeded }),
    validate(value, input) {
      if (value?.id !== input.id || value.version !== input.expectedVersion + 1 || Object.keys(value).some(key => !['id', 'version', 'approvalNeeded'].includes(key)) || Object.keys(value.approvalNeeded ?? {}).length !== fields.length || fields.some(field => typeof value.approvalNeeded[field] !== 'boolean' || value.approvalNeeded[field] !== input.approvalNeeded[field])) throw new ApiError('API_RESPONSE', 'The approval settings save could not be verified. Check the same save again.')
      return value
    },
  })
  const command = (input, generation) => {
    if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(input.id) || !Number.isSafeInteger(input.expectedVersion) || input.expectedVersion < 1 || Object.keys(input.approvalNeeded ?? {}).length !== fields.length || fields.some(field => typeof input.approvalNeeded[field] !== 'boolean')) throw new ApiError('INVALID_REQUEST', 'Review all four approval settings and reload the trainer before saving.')
    return save(input, generation)
  }
  command.recovery = save
  return command
}
