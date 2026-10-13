export function trainerReactivationApiFixture({ state, path, request, body, json, error }) {
  if (!path.startsWith('/api/trainer-reactivations/') && !/^\/api\/trainers\/[^/]+\/reactivation$/.test(path)) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.trainerReactivations ??= new Map()
  if (path.startsWith('/api/trainer-reactivations/')) {
    const receipt = state.trainerReactivations.get(path.split('/').at(-1))
    if (receipt) json(receipt); else error('not_found', 404)
    return true
  }
  const trainer = state.directory.trainers.find(t => t.id === path.split('/')[3])
  if (!trainer) { error('not_found', 404); return true }
  if (request.method === 'GET') {
    if (trainer.status !== 'inactive') error('state_conflict', 409)
    else json({ id: trainer.id, version: trainer.version, accountId: null, accountVersion: null })
    return true
  }
  const key = request.headers['idempotency-key']
  if (state.trainerReactivations.has(key)) { json(state.trainerReactivations.get(key)); return true }
  if (!key || trainer.status !== 'inactive' || body.expectedVersion !== trainer.version || body.expectedAccountId !== null || body.expectedAccountVersion !== null) { error('state_conflict', 409); return true }
  trainer.status = 'active'; trainer.version++
  const result = { id: trainer.id, version: trainer.version, status: 'active' }
  state.trainerReactivations.set(key, result)
  if (state.trainerReactivationUnknown) { state.trainerReactivationUnknown = false; error('service_unavailable', 503); return true }
  if (state.trainerReactivationRefreshFailure) { state.trainerReactivationRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
