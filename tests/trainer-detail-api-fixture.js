export function trainerDetailApiFixture({ state, path, request, body, json, error }) {
  if (!path.startsWith('/api/trainer-detail-saves/') && !/^\/api\/trainers\/[^/]+\/personal-details$/.test(path)) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.trainerDetails ??= new Map()
  if (request.method === 'GET') {
    const receipt = state.trainerDetails.get(path.split('/').at(-1))
    if (receipt) json(receipt); else error('not_found', 404)
    return true
  }
  const key = request.headers['idempotency-key']
  if (state.trainerDetails.has(key)) { json(state.trainerDetails.get(key)); return true }
  const trainer = state.directory.trainers.find(t => t.id === path.split('/')[3])
  if (!key || !trainer || trainer.version !== body.expectedVersion || Object.hasOwn(body.patch, 'email')) { error('state_conflict', 409); return true }
  for (const [field, value] of Object.entries(body.patch)) {
    if (field === 'phone') { trainer.phone_country_code = value.countryCode; trainer.phone_number = value.number }
    else if (field === 'trainerType') trainer.trainer_type = value
    else if (field === 'publicProfile') trainer.public_profile = value === 'Visible'
    else trainer[field] = value
  }
  trainer.version++
  for (const client of state.directory.clients) for (const purchase of client.purchases) if (purchase.trainer_id === trainer.id) purchase.trainer_name = trainer.name
  const result = { id: trainer.id, version: trainer.version }
  state.trainerDetails.set(key, result)
  if (state.trainerDetailUnknown) { state.trainerDetailUnknown = false; error('service_unavailable', 503); return true }
  if (state.trainerDetailRefreshFailure) { state.trainerDetailRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
