import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const identity = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const version = value => Number.isSafeInteger(value) && value >= 1
export function clientDetailCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Client information', path: input => `/api/clients/${input.id}/personal-details`, receiptPath: '/api/client-detail-saves',
    bodyFor: ({ id: _id, ...body }) => body,
    validate(value, input) {
      if (value?.id !== input.id || value.version !== input.expectedVersion + 1 || Object.keys(value).some(key => !['id', 'version', 'people'].includes(key)) || !Array.isArray(value.people) || value.people.length !== input.people.length || value.people.some((person, index) => person.id !== input.people[index].id || person.version !== input.people[index].expectedVersion + 1 || Object.keys(person).some(key => !['id', 'version'].includes(key)))) throw new ApiError('API_RESPONSE', 'The client save could not be verified. Check the same save again.')
      return value
    },
  })
  const command = (input, generation) => {
    const { id, patch, reviewed } = input
    if (!patch || Object.keys(patch).some(key => !['people', 'remarks', 'genderPreference'].includes(key))) throw new ApiError('OPERATION_UNAVAILABLE', 'Use the dedicated workflow for these client fields.')
    if (!identity(id) || !version(reviewed?.expectedVersion) || !Array.isArray(patch.people) || !Array.isArray(reviewed.people) || patch.people.length !== reviewed.people.length || ![1, 2].includes(patch.people.length) || reviewed.people.some(p => !identity(p.id) || !version(p.expectedVersion))) throw new ApiError('INVALID_REQUEST', 'Reload and review each client’s details before saving.')
    if (!reviewed.notesEnabled && patch.people.some(person => person.healthNotes)) throw new ApiError('OPERATION_UNAVAILABLE', 'Health and coaching edits require their separate workflow.')
    const people = patch.people.map((person, index) => ({
      ...reviewed.people[index], name: person.name, email: person.email, birthday: person.birthday, gender: person.gender,
      phone: person.phone, emergencyContact: person.emergencyContact,
      ...(reviewed.notesEnabled ? { healthNotes: person.healthNotes ?? '' } : {}),
    }))
    return save({ id, expectedVersion: reviewed.expectedVersion, people, remarks: patch.remarks, genderPreference: patch.genderPreference }, generation)
  }
  command.recovery = save
  return command
}
