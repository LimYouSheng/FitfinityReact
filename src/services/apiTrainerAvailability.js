import { DAYS } from '../app/constants.js'
import { validateAvailability } from '../app/scheduleChanges.js'
import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
export function trainerAvailabilityCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Trainer availability', roles: ['trainer'],
    path: input => `/api/trainers/${input.id}/availability`, receiptPath: '/api/trainer-availability-saves',
    bodyFor: ({ expectedVersion, blocks }) => {
      const availability = validateAvailability(blocks)
      return { expectedVersion, slots: DAYS.flatMap((day, weekday) => availability[day].map(([startsAt, endsAt]) => ({ weekday, startsAt, endsAt }))) }
    },
    validate(value, input) {
      if (!value || Object.keys(value).some(key => !['outcome', 'trainer', 'requestId'].includes(key)) || !['applied', 'requested'].includes(value.outcome)
        || value.trainer?.id !== input.id || Object.keys(value.trainer).some(key => !['id', 'version'].includes(key))
        || value.trainer.version !== input.expectedVersion + (value.outcome === 'applied' ? 1 : 0)
        || (value.outcome === 'requested' ? !uuid(value.requestId) : value.requestId !== null)) throw new ApiError('API_RESPONSE', 'The availability save could not be verified. Check the original save again.')
      return value
    },
  })
  return {
    save(input, generation) {
      if (!uuid(input.id) || !Number.isSafeInteger(input.expectedVersion) || input.expectedVersion < 1) throw new ApiError('INVALID_REQUEST', 'Reload the Trainer before editing availability.')
      validateAvailability(input.blocks)
      return save(input, generation)
    },
    async recover(generation) {
      const recovered = save.pendingInput(generation) ? await save.reconcile(generation) : null
      return { pending: save.pendingInput(generation), recovered: recovered?.result ?? null }
    },
  }
}
