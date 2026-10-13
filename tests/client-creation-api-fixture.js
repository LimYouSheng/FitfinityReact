import { directoryId } from '../src/test/directory.js'

// Deterministic transport/recovery fixture; real matching and atomicity use PostgreSQL tests.
export function clientCreationApiFixture({ state, path, request, body, json, error }) {
  if (!['/api/client-onboarding/matches', '/api/clients'].includes(path) && !path.startsWith('/api/client-creations/')) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  if (request.method === 'GET') {
    const saved = state.clientCreationReceipts?.get(path.split('/').at(-1))
    if (saved) json(saved); else error('not_found', 404)
    return true
  }
  if (path.endsWith('/matches')) {
    if (state.clientMatchFailure) { state.clientMatchFailure = false; error('service_unavailable', 503); return true }
    const trainer = state.directory.trainers[0], block = body.clientPreferences[0]
    json({ matches: state.clientNoMatches ? [] : [{ trainerId: trainer.id, trainerVersion: trainer.version, matches: body.clientPreferences.length, total: body.clientPreferences.length,
      schedule: [{ day: block.days[0], from: block.from, to: block.to }] }] })
    return true
  }
  const key = request.headers['idempotency-key']
  state.clientCreationReceipts ??= new Map()
  if (!state.clientCreationReceipts.has(key)) {
    const source = state.directory.clients[0], template = state.directory.packages[0]
    const client = { ...structuredClone(source), id: directoryId(100), name: body.people.map(p => p.name).join(' & '), kind: body.type === 'Couple' ? 'couple' : 'individual', remarks: body.remarks,
      people: body.people.map((p, i) => ({ id: directoryId(101 + i), version: 1, position: i + 1, name: p.name, email: p.email, birthday: p.birthday, gender: p.gender,
        phone_country_code: p.phone.countryCode, phone_number: p.phone.number, emergency_name: p.emergencyContact.name, emergency_relationship: p.emergencyContact.relationship,
        emergency_country_code: p.emergencyContact.countryCode, emergency_number: p.emergencyContact.number })),
      purchases: [{ ...structuredClone(source.purchases[0]), id: directoryId(103), used: 0, name: template.name, total_sessions: template.total_sessions, validity_days: template.validity_days,
        start_date: body.startDate, end_date: '2027-12-03', schedule: [{ id: directoryId(104), weekday: 0, starts_at: '18:00:00', ends_at: '19:00:00' }] }] }
    state.clientCreationBody = body
    state.directory.clients.push(client)
    state.clientCreationReceipts.set(key, { id: client.id, version: 2, purchaseId: directoryId(103) })
  }
  if (state.clientCreateUnknown) { state.clientCreateUnknown = false; error('service_unavailable', 503); return true }
  json(state.clientCreationReceipts.get(key))
  if (state.clientCreateRefreshFailure) state.unavailable = true
  return true
}
