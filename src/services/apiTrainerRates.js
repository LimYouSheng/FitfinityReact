import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

function cents(value) {
  const text = String(value ?? '').trim()
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) throw new ApiError('INVALID_REQUEST', 'Enter non-negative rates with at most two decimal places.')
  const [whole, fraction = ''] = text.split('.')
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  if (!Number.isSafeInteger(result)) throw new ApiError('INVALID_REQUEST', 'The rate is too large to save accurately.')
  return result
}

export function trainerRateCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Trainer rates', roles: ['owner'],
    path: input => `/api/trainers/${input.id}/rates`, receiptPath: '/api/trainer-rate-saves',
    bodyFor: ({ id: _id, ...body }) => body,
    validate(value, input) {
      if (value?.id !== input.id || value.version !== input.expectedVersion + 1 || Object.keys(value).some(key => !['id', 'version'].includes(key))) throw new ApiError('API_RESPONSE', 'The trainer rate save could not be verified. Check the same save again.')
      return value
    },
  })
  const command = ({ id, patch, expectedVersion }, generation) => {
    if (!patch || Object.keys(patch).length !== 1 || !Object.hasOwn(patch, 'rates')) throw new ApiError('OPERATION_UNAVAILABLE', 'Use the dedicated workflow for these trainer fields.')
    if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id) || !Number.isSafeInteger(expectedVersion) || expectedVersion < 1 || !patch.rates || Object.keys(patch.rates).length !== 2 || !['peak', 'offPeak'].every(key => Object.hasOwn(patch.rates, key))) throw new ApiError('INVALID_REQUEST', 'Review both rates and reload the trainer before saving.')
    return save({ id, expectedVersion, rates: { peak: cents(patch.rates.peak), offPeak: cents(patch.rates.offPeak) } }, generation)
  }
  command.recovery = save
  return command
}
