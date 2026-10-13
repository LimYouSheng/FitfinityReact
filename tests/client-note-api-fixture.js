export function clientNoteApiFixture({ state, path, request, body, json, error }) {
  if (!path.startsWith('/api/client-note-saves/') && !/^\/api\/clients\/[^/]+\/notes$/.test(path)) return false
  state.clientNoteSaves ??= new Map()
  if (path.startsWith('/api/client-note-saves/')) {
    const saved = state.clientNoteSaves.get(path.split('/').at(-1))
    if (saved) json(saved); else error('not_found', 404)
    return true
  }
  const row = state.directory.clients.find(client => client.id === path.split('/')[3])
  if (!row || (state.user.role === 'trainer' && state.user.trainerId !== row.trainer_id)) { error('not_found', 404); return true }
  if (request.method === 'GET') {
    json({ id: row.id, version: row.version, healthNotes: row.health_notes ?? '', remarks: row.remarks,
      people: row.people.map(person => ({ id: person.id, version: person.version, healthNotes: person.health_notes ?? '' })) })
    return true
  }
  const key = request.headers['idempotency-key']
  if (state.clientNoteSaves.has(key)) { json(state.clientNoteSaves.get(key)); return true }
  if (body.expectedVersion !== row.version) { error('state_conflict', 409); return true }
  if (Object.hasOwn(body.patch, 'healthNotes')) {
    row.health_notes = body.patch.healthNotes
    if (row.kind === 'individual') { row.people[0].health_notes = row.health_notes; row.people[0].version++ }
  }
  if (Object.hasOwn(body.patch, 'remarks')) row.remarks = body.patch.remarks
  const result = { id: row.id, version: ++row.version }
  state.clientNoteSaves.set(key, result)
  if (state.clientNoteUnknown) { state.clientNoteUnknown = false; error('service_unavailable', 503); return true }
  if (state.clientNoteRefreshFailure) { state.clientNoteRefreshFailure = false; state.unavailable = true }
  json(result)
  return true
}
