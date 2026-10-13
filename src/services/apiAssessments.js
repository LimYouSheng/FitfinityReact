import { assessmentForm, assessmentFields } from '../app/assessmentForms.js'
import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { assessmentHistoryPage, assessmentRecord, assessmentUuid, assessmentVersion, clientAssessmentRecords } from './apiAssessmentRecords.js'

const invalid = () => { throw new ApiError('INVALID_REQUEST', 'Review the client and assessment before saving.') }
function commandInput({ id, assessment: value }) {
  if (!assessmentUuid(id) || !value || !assessmentUuid(value.personId) || !assessmentVersion(value.expectedPersonVersion)
    || !assessmentForm(value.formId) || value.formVersion !== assessmentForm(value.formId).version
    || !value.record?.answers || typeof value.record.answers !== 'object' || Array.isArray(value.record.answers)
    || !['draft', 'completed', 'correction', 'voided'].includes(value.event)) invalid()
  const answers = structuredClone(value.record.answers)
  for (const field of assessmentFields(assessmentForm(value.formId))) {
    if (answers[field.id] === null || (typeof answers[field.id] === 'string' && !answers[field.id].trim())) delete answers[field.id]
    else if (field.type === 'number' && typeof answers[field.id] === 'string' && Number.isFinite(Number(answers[field.id]))) answers[field.id] = Number(answers[field.id])
    else if (typeof answers[field.id] === 'string') answers[field.id] = answers[field.id].trim()
  }
  const body = { expectedClientId: id, expectedPersonVersion: value.expectedPersonVersion, answers, event: value.event }
  if (value.assessmentId) {
    if (!assessmentUuid(value.assessmentId) || !assessmentVersion(value.expectedVersion) || value.previousAssessmentId || value.expectedPreviousVersion) invalid()
    Object.assign(body, { expectedVersion: value.expectedVersion, ...(value.reason === undefined ? {} : { reason: value.reason }) })
  } else {
    if (!['draft', 'completed'].includes(value.event) || value.reason !== undefined || value.expectedVersion !== undefined) invalid()
    Object.assign(body, { formId: value.formId, formVersion: value.formVersion })
    if (value.previousAssessmentId || value.expectedPreviousVersion) {
      if (!assessmentUuid(value.previousAssessmentId) || !assessmentVersion(value.expectedPreviousVersion)) invalid()
      Object.assign(body, { previousAssessmentId: value.previousAssessmentId, expectedPreviousVersion: value.expectedPreviousVersion })
    }
  }
  return { clientId: id, personId: value.personId, formId: value.formId, formVersion: value.formVersion, assessmentId: value.assessmentId ?? null, body }
}
function restoreInput(command) {
  if (!command) return null
  const { answers, ...fields } = command.body
  return { id: command.clientId, assessment: { ...fields, personId: command.personId, formId: command.formId, formVersion: command.formVersion,
    ...(command.assessmentId ? { assessmentId: command.assessmentId } : {}), record: { answers } } }
}

export function assessmentCommands(http, actionSession) {
  const authorize = async generation => {
    const session = await actionSession(generation)
    if (!['owner', 'admin'].includes(session.user.role)) throw new ApiError('forbidden', 'Assessment forms are available to the Owner or Admin.', 403)
    return session.sessionGeneration
  }
  const save = reconciledCommand(http, actionSession, {
    label: 'Assessment', receiptPath: '/api/assessment-saves',
    path: input => input.assessmentId ? `/api/assessments/${input.assessmentId}/revisions` : `/api/people/${input.personId}/assessments`,
    bodyFor: input => input.body,
    validate(value, input) {
      const record = assessmentRecord(value)
      const expectedRevision = input.assessmentId ? input.body.expectedVersion + 1 : input.body.event === 'draft' ? 1 : 2
      if (record.formId !== input.formId || record.version !== input.formVersion || record.revision !== expectedRevision
        || (input.assessmentId && record.assessmentId !== input.assessmentId) || record.event !== input.body.event
        || Object.keys(record.answers).length !== Object.keys(input.body.answers).length
        || Object.entries(input.body.answers).some(([key, answer]) => record.answers[key] !== answer)) throw new ApiError('API_RESPONSE', 'This assessment save could not be verified. Check the original save again.')
      return record
    },
  })
  return {
    save: (input, generation) => save(commandInput(input), generation),
    async read(client, generation) {
      const current = await authorize(generation)
      if (!assessmentUuid(client?.id)) invalid()
      if (save.pendingInput(current)?.clientId === client.id) await save.reconcile(current)
      const value = await http.get(`/api/clients/${client.id}/assessment-records`, { expectedGeneration: current })
      const data = clientAssessmentRecords(value, client)
      return { ...data, pending: restoreInput(save.pendingInput(current)) }
    },
    async history({ personId, formId, assessmentId, offset = 0 }, generation) {
      const current = await authorize(generation)
      if (!assessmentForm(formId) || !Number.isSafeInteger(offset) || offset < 0 || offset > 10000
        || (assessmentId ? !assessmentUuid(assessmentId) : !assessmentUuid(personId))) invalid()
      const path = assessmentId ? `/api/assessments/${assessmentId}/revisions?limit=25&offset=${offset}`
        : `/api/people/${personId}/assessments?formId=${encodeURIComponent(formId)}&limit=25&offset=${offset}`
      return assessmentHistoryPage(await http.get(path, { expectedGeneration: current }), { offset, formId, assessmentId })
    },
  }
}
