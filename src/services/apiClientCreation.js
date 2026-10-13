import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { normaliseAssessments } from '../app/assessmentForms.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const interval = s => s && days.includes(s.day) && /^([01]\d|2[0-3]):[0-5]\d$/.test(s.from) && /^([01]\d|2[0-3]):[0-5]\d$/.test(s.to) && s.from < s.to

export function clientMatchBody(draft) {
  return { packageId: draft.packageId, packageVersion: draft.packageVersion, startDate: draft.startDate,
    sessionsPerWeek: Number(draft.sessionsPerWeek), genderPreference: draft.genderPreference,
    clientPreferences: draft.clientPreferences.map(({ days, from, to }) => ({ days, from, to })) }
}

export function clientCreationCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Client creation', path: () => '/api/clients', receiptPath: '/api/client-creations',
    validate(value) {
      if (!uuid(value?.id) || !uuid(value.purchaseId) || value.version !== 2 || Object.keys(value).some(key => !['id', 'version', 'purchaseId'].includes(key))) throw new ApiError('API_RESPONSE', 'Client creation could not be verified. Check the same creation again.')
      return value
    },
  })
  return {
    async preview(draft, generation) {
      const { user, sessionGeneration } = await actionSession(generation)
      if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Only the owner or Admin can match clients.', 403)
      const value = await http.post('/api/client-onboarding/matches', clientMatchBody(draft), { csrf: true, idempotencyKey: crypto.randomUUID(), expectedGeneration: sessionGeneration })
      if (!value || Object.keys(value).some(key => key !== 'matches') || !Array.isArray(value.matches) || new Set(value.matches.map(m => m.trainerId)).size !== value.matches.length || value.matches.some(m => !uuid(m.trainerId) || !Number.isSafeInteger(m.trainerVersion) || m.trainerVersion < 1 || !Number.isSafeInteger(m.matches) || m.matches < 1 || m.total !== draft.clientPreferences.length || m.matches > m.total || !Array.isArray(m.schedule) || m.schedule.length !== Number(draft.sessionsPerWeek) || new Set(m.schedule.map(s => s.day)).size !== m.schedule.length || m.schedule.some(s => !interval(s)) || Object.keys(m).some(key => !['trainerId', 'trainerVersion', 'matches', 'total', 'schedule'].includes(key)))) throw new ApiError('API_RESPONSE', 'Trainer matching could not be verified. Try again.')
      return value.matches
    },
    create({ draft }, generation) {
      if (!draft || !Array.isArray(draft.people) || !Array.isArray(draft.clientPreferences) || !Array.isArray(draft.fixedWeeklySchedule)) throw new ApiError('INVALID_REQUEST', 'Review the complete client creation form.')
      const people = draft.people.slice(0, draft.type === 'Couple' ? 2 : 1).map(person => {
        const { name, email, birthday, gender, phone, emergencyContact, healthNotes } = person
        return { name, email, birthday, gender, phone, emergencyContact, healthNotes,
          assessments: Object.values(normaliseAssessments(person.assessments)).map(record => ({ formId: record.formId, formVersion: record.version, assessmentDate: record.date, answers: record.answers })) }
      })
      return save({ ...clientMatchBody(draft), type: draft.type, people, trainerId: draft.trainerId,
        trainerVersion: draft.trainerVersion, fixedWeeklySchedule: draft.fixedWeeklySchedule.map(({ day, from, to }) => ({ day, from, to })), remarks: draft.remarks }, generation)
    },
  }
}
