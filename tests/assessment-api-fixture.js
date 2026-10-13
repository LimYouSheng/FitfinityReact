import { assessmentRevision } from '../src/test/assessmentApi.js'
import { directoryId } from '../src/test/directory.js'

export function assessmentApiFixture({ state, path, request, body, json, error }) {
  const profile = /^\/api\/clients\/([^/]+)\/assessment-records$/.exec(path)
  const personPath = /^\/api\/people\/([^/]+)\/assessments$/.exec(path)
  const revisions = /^\/api\/assessments\/([^/]+)\/revisions$/.exec(path)
  const receiptPath = /^\/api\/assessment-saves\/([^/]+)$/.exec(path)
  if (!profile && !personPath && !revisions && !receiptPath) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  const store = state.assessmentStore ??= { people: new Map(), histories: new Map(), receipts: new Map(), sequence: 300 }
  const identity = () => directoryId(++store.sequence)
  if (request.method === 'GET') {
    state.assessmentReads = (state.assessmentReads ?? 0) + 1
    if (state.assessmentReadFailure) { error('service_unavailable', 503); return true }
    if (receiptPath) {
      const receipt = store.receipts.get(receiptPath[1])
      if (receipt) json(receipt); else error('not_found', 404)
      return true
    }
    if (profile) {
      const client = state.directory.clients.find(c => c.id === profile[1])
      if (!client) { error('not_found', 404); return true }
      json({ id: client.id, version: client.version, businessDate: '2026-10-13', people: client.people.map(person => {
        const records = new Map()
        for (const record of store.people.get(person.id) ?? []) records.set(record.form_id, record)
        return { id: person.id, version: person.version, records: [...records.values()] }
      }) }); return true
    }
    const query = new URL(request.url, 'http://fixture').searchParams
    const offset = Number(query.get('offset') ?? 0)
    const records = revisions ? store.histories.get(revisions[1]) ?? []
      : [...store.people.get(personPath[1]) ?? []].reverse().filter(row => !query.get('formId') || row.form_id === query.get('formId'))
    json({ items: records.slice(offset, offset + 25), limit: 25, offset, hasMore: records.length > offset + 25 }); return true
  }
  const key = request.headers['idempotency-key']
  if (store.receipts.has(key)) { json(store.receipts.get(key)); return true }
  const current = revisions ? store.histories.get(revisions[1])?.[0] : null
  const personId = personPath?.[1] ?? [...store.people.entries()].find(([, records]) => records.some(row => row.assessment_id === revisions?.[1]))?.[0]
  const client = state.directory.clients.find(c => c.people.some(person => person.id === personId))
  const person = client?.people.find(person => person.id === personId)
  if (!key || !person || client.id !== body.expectedClientId || client.status !== 'active' || person.version !== body.expectedPersonVersion) { error('state_conflict', 409); return true }
  let result
  if (personPath) {
    const previous = (store.people.get(personId) ?? []).filter(row => row.form_id === body.formId).at(-1)
    if (previous && (previous.status === 'draft' || previous.assessment_id !== body.previousAssessmentId || previous.revision !== body.expectedPreviousVersion)) { error('state_conflict', 409); return true }
    const draft = assessmentRevision({ id: identity(), assessment_id: identity(), revision: 1, previous_revision: null, status: 'draft', event: 'draft',
      form_id: body.formId, form_version: body.formVersion, answers: structuredClone(body.answers),
      client_name: person.name, client_birthday: person.birthday, assessor_id: state.user.id, assessor_name: state.user.name, actor_id: state.user.id, actor_name: state.user.name })
    result = body.event === 'draft' ? draft : { ...draft, id: identity(), revision: 2, previous_revision: 1, status: 'completed', event: 'completed' }
    store.histories.set(draft.assessment_id, result === draft ? [draft] : [result, draft])
    store.people.set(personId, [...store.people.get(personId) ?? [], result])
  } else {
    if (!current || current.status !== 'draft' || current.revision !== body.expectedVersion) { error('state_conflict', 409); return true }
    result = { ...current, id: identity(), revision: current.revision + 1, previous_revision: current.revision,
      status: body.event, event: body.event, answers: structuredClone(body.answers),
      client_name: person.name, client_birthday: person.birthday, assessor_id: state.user.id, assessor_name: state.user.name, actor_id: state.user.id, actor_name: state.user.name }
    store.histories.set(current.assessment_id, [result, ...store.histories.get(current.assessment_id)])
    store.people.set(personId, store.people.get(personId).map(row => row.assessment_id === current.assessment_id ? result : row))
  }
  store.receipts.set(key, result)
  state.mutations.at(-1).body = body
  if (state.assessmentUnknown) { state.assessmentUnknown = false; error('service_unavailable', 503); return true }
  if (state.assessmentRefreshFailure) { state.assessmentRefreshFailure = false; state.assessmentReadFailure = true }
  json(result); return true
}
