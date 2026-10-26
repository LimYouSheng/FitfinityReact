import { phoneDraft } from '../app/contact.js'
import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const fields = ['name', 'phone', 'birthday', 'gender', 'trainerType', 'qualifications', 'publicProfile']
export function trainerDetailCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Trainer information', roles: ['owner', 'admin', 'trainer'],
    path: input => `/api/trainers/${input.id}/personal-details`, receiptPath: '/api/trainer-detail-saves',
    bodyFor: ({ id: _id, ...body }) => body,
    validate(value, input) {
      if (value?.id !== input.id || value.version !== input.expectedVersion + 1 || Object.keys(value).some(key => !['id', 'version'].includes(key))) throw new ApiError('API_RESPONSE', 'The trainer profile save could not be verified. Check the same save again.')
      return value
    },
  })
  const command = ({ id, patch, expectedVersion }, generation) => {
    if (!patch || !Object.keys(patch).length || Object.keys(patch).some(key => !fields.includes(key))) throw new ApiError('OPERATION_UNAVAILABLE', 'Use the dedicated workflow for these trainer fields.')
    if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id) || !Number.isSafeInteger(expectedVersion) || expectedVersion < 1) throw new ApiError('INVALID_REQUEST', 'Reload and review the trainer before saving.')
    const body = { ...patch }
    if (Object.hasOwn(body, 'phone')) body.phone = phoneDraft(body.phone, '+65')
    if (body.birthday === '') body.birthday = null
    return save({ id, expectedVersion, patch: body }, generation)
  }
  command.recovery = save
  return command
}
