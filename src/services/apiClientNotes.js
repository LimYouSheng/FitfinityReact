import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const fail = () => { throw new ApiError('API_RESPONSE', 'Client notes could not be verified. Reload and review again.') }
export function withClientNotes(client, value) {
  if (!value || value.id !== client.id || value.version !== client.version || typeof value.healthNotes !== 'string' || typeof value.remarks !== 'string' || !Array.isArray(value.people) || value.people.length !== client.people.length || Object.keys(value).some(key => !['id', 'version', 'healthNotes', 'remarks', 'people'].includes(key))) fail()
  const people = client.people.map((person, index) => {
    const note = value.people[index]
    if (!note || note.id !== person.id || note.version !== person.version || typeof note.healthNotes !== 'string' || Object.keys(note).some(key => !['id', 'version', 'healthNotes'].includes(key))) fail()
    return { ...person, healthNotes: note.healthNotes }
  })
  return { ...client, people, healthNotes: value.healthNotes, remarks: value.remarks, notesAvailable: true }
}

export function clientNoteCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Client notes', roles: ['owner', 'admin', 'trainer'],
    path: input => `/api/clients/${input.id}/notes`, receiptPath: '/api/client-note-saves',
    bodyFor: ({ id: _id, ...body }) => body,
    validate(value, input) {
      if (value?.id !== input.id || value.version !== input.expectedVersion + 1 || Object.keys(value).some(key => !['id', 'version'].includes(key))) fail()
      return value
    },
  })
  const command = ({ id, patch, reviewed }, generation) => {
    if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id) || !Number.isSafeInteger(reviewed?.expectedVersion) || reviewed.expectedVersion < 1 || !patch || !Object.keys(patch).length || Object.entries(patch).some(([key, value]) => !['remarks', 'healthNotes'].includes(key) || typeof value !== 'string' || value.length > 10000)) throw new ApiError('INVALID_REQUEST', 'Reload and review the client notes before saving.')
    return save({ id, expectedVersion: reviewed.expectedVersion, patch }, generation)
  }
  command.recovery = save
  return command
}
