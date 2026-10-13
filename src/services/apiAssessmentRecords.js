import { assessmentErrors, assessmentFields, assessmentForm } from '../app/assessmentForms.js'
import { validSessionDate } from '../app/sessionRules.js'
import { ApiError } from './apiClient.js'

export const assessmentUuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
export const assessmentVersion = value => Number.isSafeInteger(value) && value > 0
const fail = () => { throw new ApiError('API_RESPONSE', 'The assessment record could not be verified. Reload before continuing.') }
const text = value => typeof value === 'string' && value.trim().length > 0
const revisionFields = ['id', 'assessment_id', 'revision', 'previous_revision', 'form_id', 'form_version', 'status', 'event', 'assessment_date', 'assessor_id', 'assessor_name', 'client_name', 'client_birthday', 'answers', 'actor_id', 'actor_name', 'reason', 'created_at']

export function assessmentRecord(value) {
  const definition = assessmentForm(value?.form_id)
  if (!value || Object.keys(value).some(key => !revisionFields.includes(key)) || !definition || value.form_version !== definition.version
    || ![value.id, value.assessment_id, value.assessor_id, value.actor_id].every(assessmentUuid)
    || !assessmentVersion(value.revision) || value.previous_revision !== (value.revision === 1 ? null : value.revision - 1)
    || ![value.client_name, value.assessor_name, value.actor_name].every(text)
    || !validSessionDate(value.assessment_date) || !validSessionDate(value.client_birthday)
    || typeof value.created_at !== 'string' || !Number.isFinite(Date.parse(value.created_at))
    || !['draft', 'completed', 'voided'].includes(value.status)
    || ({ draft: 'draft', completed: 'completed', correction: 'completed', voided: 'voided' })[value.event] !== value.status
    || (['correction', 'voided'].includes(value.event) ? !text(value.reason) : value.reason !== null)) fail()
  if (Object.keys(assessmentErrors(value.form_id, { date: value.assessment_date, assessor: value.assessor_name, answers: value.answers }, { completed: value.status === 'completed' })).length) fail()
  for (const field of assessmentFields(definition)) {
    const answer = value.answers[field.id]
    if (answer !== undefined && (field.type === 'number' ? typeof answer !== 'number' : typeof answer !== 'string')) fail()
  }
  return { formId: value.form_id, version: value.form_version, status: value.status === 'completed' ? 'filled' : value.status,
    date: value.assessment_date, assessor: value.assessor_name, savedAt: value.created_at, answers: structuredClone(value.answers),
    clientName: value.client_name, clientBirthday: value.client_birthday, assessmentId: value.assessment_id,
    revision: value.revision, revisionId: value.id, event: value.event, actorName: value.actor_name, reason: value.reason }
}

export function clientAssessmentRecords(value, client) {
  if (!value || value.id !== client.id || value.version !== client.version || !validSessionDate(value.businessDate)
    || Object.keys(value).some(key => !['id', 'version', 'businessDate', 'people'].includes(key))
    || !Array.isArray(value.people) || value.people.length !== client.people.length) fail()
  const people = client.people.map((person, index) => {
    const row = value.people[index]
    if (!row || row.id !== person.id || row.version !== person.version || !Array.isArray(row.records)
      || Object.keys(row).some(key => !['id', 'version', 'records'].includes(key))) fail()
    const records = row.records.map(assessmentRecord)
    if (new Set(records.map(record => record.formId)).size !== records.length) fail()
    return { ...person, assessments: Object.fromEntries(records.map(record => [record.formId, record])) }
  })
  return { id: value.id, version: value.version, businessDate: value.businessDate, people }
}

export function assessmentHistoryPage(value, { offset, formId, assessmentId }) {
  if (!value || !Array.isArray(value.items) || value.limit !== 25 || value.offset !== offset || typeof value.hasMore !== 'boolean'
    || value.items.length > 25 || (value.hasMore && value.items.length !== 25)
    || Object.keys(value).some(key => !['items', 'limit', 'offset', 'hasMore'].includes(key))) fail()
  const items = value.items.map(assessmentRecord)
  if (new Set(items.map(row => row.revisionId)).size !== items.length
    || items.some(row => row.formId !== formId || (assessmentId && row.assessmentId !== assessmentId))) fail()
  return { items, offset, hasMore: value.hasMore }
}
