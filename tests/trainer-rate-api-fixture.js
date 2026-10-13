// Controlled browser boundary. Real transactions/authority are tested against PostgreSQL.
export function trainerRateApiFixture({ state, path, request, body, json, error }) {
  if (!path.startsWith('/api/trainer-rate-saves/') && !/^\/api\/trainers\/[^/]+\/rates$/.test(path)) return false
  if (state.user.role !== 'owner') { error('forbidden', 403); return true }
  state.rateSaves ??= new Map()
  if (request.method === 'GET') {
    const result = state.rateSaves.get(path.split('/').at(-1))
    if (result) json(result); else error('not_found', 404)
    return true
  }
  const key = request.headers['idempotency-key']
  if (state.rateSaves.has(key)) { json(state.rateSaves.get(key)); return true }
  const trainer = state.directory.trainers.find(t => t.id === path.split('/')[3])
  if (!key || !trainer || trainer.version !== body.expectedVersion) { error('state_conflict', 409); return true }
  trainer.version += 1
  trainer.peak_rate_cents = body.rates.peak
  trainer.off_peak_rate_cents = body.rates.offPeak
  const result = { id: trainer.id, version: trainer.version }
  state.rateSaves.set(key, result)
  if (state.rateUnknown) { state.rateUnknown = false; error('service_unavailable', 503); return true }
  if (state.rateRefreshFailure) { state.rateRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
