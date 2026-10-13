import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const pendingCodes = ['INVITATION_BUSY', 'STAFF_IDENTITY_CONFLICT', 'STAFF_INACTIVE']
const rate = value => {
  const text = String(value ?? '').trim()
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) throw new ApiError('INVALID_REQUEST', 'Review the trainer rates.')
  const [whole, decimal = ''] = text.split('.')
  const cents = Number(whole) * 100 + Number(decimal.padEnd(2, '0'))
  if (!Number.isSafeInteger(cents)) throw new ApiError('INVALID_REQUEST', 'Review the trainer rates.')
  return cents
}
export function trainerCreationBody({ draft }) {
  if (Object.hasOwn(draft, 'rates') && (!draft.rates || typeof draft.rates !== 'object')) throw new ApiError('INVALID_REQUEST', 'Review the trainer rates.')
  return { name: draft.name, email: draft.email, phone_country_code: draft.phone.countryCode, phone_number: draft.phone.number,
    birthday: draft.birthday, gender: draft.gender, trainerType: draft.trainerType, qualifications: draft.qualifications, publicProfile: draft.publicProfile,
    ...(Object.hasOwn(draft, 'rates') ? { rates: { peak: rate(draft.rates.peak), offPeak: rate(draft.rates.offPeak) } } : {}),
    slots: draft.availabilityBlocks.flatMap(block => block.days.map(day => ({ weekday: days.indexOf(day), startsAt: block.from, endsAt: block.to }))),
    approvalNeeded: draft.approvalNeeded }
}
export function trainerCreationCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Trainer creation', path: () => '/api/staff/trainers', receiptPath: '/api/staff/trainer-creations',
    keyFor: input => input.draft.requestId, bodyFor: trainerCreationBody,
    complete: value => ['sent', 'unknown'].includes(value.invitation),
    definitiveRejection: error => error.status >= 400 && error.status < 500 && !pendingCodes.includes(error.code),
    validate(value) {
      if (!uuid(value?.id) || !['pending', 'sending', 'sent', 'unknown'].includes(value.invitation) || Object.keys(value).some(key => !['id', 'invitation'].includes(key))) throw new ApiError('API_RESPONSE', 'Trainer creation could not be verified. Check the original request again.')
      return value
    },
  })
  return {
    async create(input, generation) {
      const draft = input?.draft
      if (!uuid(draft?.requestId) || !draft.phone || !Array.isArray(draft.availabilityBlocks) || draft.availabilityBlocks.some(b => !Array.isArray(b?.days)) || !draft.approvalNeeded) throw new ApiError('INVALID_REQUEST', 'Review the complete trainer creation form.')
      // Validate local rate conversion before storing an uncertain write intent.
      trainerCreationBody(input)
      try { return await save(input, generation) }
      catch (error) {
        if (pendingCodes.includes(error.code) && save.pendingInput(generation)) throw new ApiError('SAVE_UNCERTAIN', error.message)
        throw error
      }
    },
  }
}
