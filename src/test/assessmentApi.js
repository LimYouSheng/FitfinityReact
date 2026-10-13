import { directoryId } from './directory.js'
import { staff } from './api.js'

export function assessmentRevision(patch = {}) {
  return { id: directoryId(21), assessment_id: directoryId(20), revision: 2, previous_revision: 1,
    form_id: 'balance', form_version: 1, status: 'completed', event: 'completed',
    assessment_date: '2026-10-13', assessor_id: staff.id, assessor_name: 'API Owner',
    client_name: 'API Client', client_birthday: '1990-01-01', answers: { eyes_open_1: 0 },
    actor_id: staff.id, actor_name: 'API Owner', reason: null, created_at: '2026-10-13T12:00:00Z', ...patch }
}
export function assessmentSnapshot(client, records = []) {
  return { id: client.id, version: client.version, businessDate: '2026-10-13',
    people: client.people.map((person, index) => ({ id: person.id, version: person.version, records: index === 0 ? records : [] })) }
}
