import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { assessmentRecord, clientAssessmentRecords } from './apiAssessmentRecords.js'
import { directoryData, directoryId } from '../test/directory.js'
import { assessmentRevision, assessmentSnapshot } from '../test/assessmentApi.js'
import { failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directorySnapshot } from './apiDirectory.js'

const client = directorySnapshot(directoryData(), sessionInfo().user).data.clients[0]
const assessment = { personId: client.people[0].id, expectedPersonVersion: client.people[0].version,
  formId: 'balance', formVersion: 1, event: 'completed', record: { answers: { eyes_open_1: '0', eyes_closed_1: '  ' }, assessor: 'Forged', date: '1900-01-01' } }
const input = { id: client.id, assessment }

it('sends reviewed person/form and typed answers without preview identity or dates', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : assessmentRevision()))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  const saved = await services.clientService.saveAssessment(input)
  expect(saved.assessor).toBe('API Owner')
  const [url, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(url).toMatch(new RegExp(`/people/${assessment.personId}/assessments$`))
  expect(JSON.parse(options.body)).toEqual({ expectedClientId: client.id, expectedPersonVersion: 1, answers: { eyes_open_1: 0 }, event: 'completed', formId: 'balance', formVersion: 1 })
})

it('profile reload reconciles an unknown committed save without writing again', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { writes++; if (writes === 1) throw new Error('offline'); return jsonResponse(assessmentRevision({ id: directoryId(23), revision: 3, previous_revision: 2, event: 'correction', reason: 'Correction' })) }
    if (url.includes('/assessment-saves/')) return jsonResponse(assessmentRevision())
    return jsonResponse(assessmentSnapshot(client, [assessmentRevision()]))
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.clientService.saveAssessment(input)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const result = await services.readClientAssessments(client)
  expect(result.pending).toBeNull()
  expect(result.people[0].assessments.balance.answers).toEqual({ eyes_open_1: 0 })
  expect(writes).toBe(1)
  await services.clientService.saveAssessment({ ...input, assessment: { ...assessment, assessmentId: directoryId(20), expectedVersion: 2, event: 'correction', reason: 'Correction' } })
  expect(writes).toBe(2)
})

it('missing receipt retains the original pending form without automatically resubmitting', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { writes++; if (writes === 1) throw new Error('offline'); return jsonResponse(assessmentRevision()) }
    if (url.includes('/assessment-saves/')) return failure('not_found', 404)
    return jsonResponse(assessmentSnapshot(client))
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.clientService.saveAssessment(input)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const { pending } = await services.readClientAssessments(client)
  expect(pending.assessment.record.answers).toEqual({ eyes_open_1: 0 })
  expect(writes).toBe(1)
  await services.clientService.saveAssessment(pending)
  const requests = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(requests[1].headers['Idempotency-Key']).toBe(requests[0].headers['Idempotency-Key'])
  expect(requests[1].body).toBe(requests[0].body)
})

it('drafts preserve blanks and histories retain the submitted person snapshot', () => {
  const draft = assessmentRevision({ revision: 1, previous_revision: null, status: 'draft', event: 'draft', answers: {} })
  expect(clientAssessmentRecords(assessmentSnapshot(client, [draft]), client).people[0].assessments.balance.status).toBe('draft')
  expect(assessmentRecord(assessmentRevision({ client_name: 'Original name' })).clientName).toBe('Original name')
})

it.each([
  { answers: { eyes_open_1: '0' } }, { answers: { eyes_open_1: false } }, { answers: { unknown: 1 } },
  { previous_revision: 0 }, { status: 'draft' }, { form_version: 2 }, { actor_id: 'spoof' },
])('rejects malformed or unsupported saved assessment data: %j', patch => {
  expect(() => assessmentRecord(assessmentRevision(patch))).toThrow()
})

it('rejects swapped people, stale versions and duplicate form rows', () => {
  const snapshot = assessmentSnapshot(client, [assessmentRevision()])
  expect(() => clientAssessmentRecords({ ...snapshot, version: 99 }, client)).toThrow()
  expect(() => clientAssessmentRecords({ ...snapshot, people: [{ ...snapshot.people[0], id: directoryId(99) }] }, client)).toThrow()
  expect(() => clientAssessmentRecords(assessmentSnapshot(client, [assessmentRevision(), assessmentRevision()]), client)).toThrow()
})

it('uses explicit paginated occasion and revision history with verified form identities', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { items: [assessmentRevision()], offset: 0, limit: 25, hasMore: false }))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  const history = await services.readAssessmentHistory({ personId: assessment.personId, formId: 'balance' })
  expect(history.items[0].assessmentId).toBe(directoryId(20))
  await services.readAssessmentHistory({ assessmentId: directoryId(20), formId: 'balance' })
  expect(fetch.mock.calls.some(([url]) => url.includes('formId=balance&limit=25&offset=0'))).toBe(true)
  expect(fetch.mock.calls.some(([url]) => url.endsWith(`/assessments/${directoryId(20)}/revisions?limit=25&offset=0`))).toBe(true)
})

it('denies Trainer reads, histories and writes before any assessment request', async () => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer', trainerId: directoryId(1) } }))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.readClientAssessments(client)).rejects.toMatchObject({ code: 'forbidden' })
  await expect(services.readAssessmentHistory({ personId: assessment.personId, formId: 'balance' })).rejects.toMatchObject({ code: 'forbidden' })
  await expect(services.clientService.saveAssessment(input)).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.every(([url]) => url.endsWith('/me'))).toBe(true)
})
