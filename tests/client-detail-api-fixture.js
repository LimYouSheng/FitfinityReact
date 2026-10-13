// Controlled HTTP behavior only; PostgreSQL tests own persistence and security evidence.
export function clientDetailApiFixture({ state, path, request, body, json, error }) {
  if (!path.startsWith('/api/client-detail-saves/') && !/^\/api\/clients\/[^/]+\/personal-details$/.test(path)) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.clientDetailSaves ??= new Map()
  if (request.method === 'GET') {
    const saved = state.clientDetailSaves.get(path.split('/').at(-1))
    if (saved) json(saved); else error('not_found', 404)
    return true
  }
  const key = request.headers['idempotency-key']
  if (state.clientDetailSaves.has(key)) { json(state.clientDetailSaves.get(key)); return true }
  const client = state.directory.clients.find(c => c.id === path.split('/')[3])
  if (!key || !client || client.version !== body.expectedVersion || body.people.some((p, i) => client.people[i]?.id !== p.id || client.people[i]?.version !== p.expectedVersion)) { error('state_conflict', 409); return true }
  for (const [i, person] of body.people.entries()) {
    Object.assign(client.people[i], {
      name: person.name, email: person.email, birthday: person.birthday || null, gender: person.gender,
      phone_country_code: person.phone.countryCode, phone_number: person.phone.number,
      emergency_name: person.emergencyContact.name, emergency_relationship: person.emergencyContact.relationship,
      emergency_country_code: person.emergencyContact.countryCode, emergency_number: person.emergencyContact.number,
      version: person.expectedVersion + 1,
    })
  }
  client.name = body.people.map(p => p.name).join(' & ')
  client.remarks = body.remarks
  client.gender_preference = ({ 'No gender preference': 'any', 'Female trainer preferred': 'female', 'Male trainer preferred': 'male' })[body.genderPreference]
  client.version += 1
  const result = { id: client.id, version: client.version, people: client.people.map(p => ({ id: p.id, version: p.version })) }
  state.clientDetailSaves.set(key, result)
  if (state.clientDetailUnknown) { state.clientDetailUnknown = false; error('service_unavailable', 503); return true }
  if (state.clientDetailRefreshFailure) { state.clientDetailRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
