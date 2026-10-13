export function clientDeactivationApiFixture({ state, path, request, body, json, error }) {
  const endpoint = /^\/api\/clients\/([^/]+)\/deactivation$/.exec(path)
  const receipt = /^\/api\/client-deactivations\/([^/]+)$/.exec(path)
  if (!endpoint && !receipt) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.clientDeactivationReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.clientDeactivationReceipts.get(key)
  const client = state.directory.clients.find(row => row.id === endpoint?.[1])
  if (receipt) { if (saved) json(saved); else error('not_found', 404); return true }
  if (!client) { error('not_found', 404); return true }
  if (request.method === 'GET') {
    if (client.status !== 'active') { error('state_conflict', 409); return true }
    json({ id: client.id, version: client.version, name: client.name, trainerId: client.trainer_id,
      purchases: client.purchases.map(({ id, version, status, name }) => ({ id, version, status, name })) }); return true
  }
  state.clientDeactivationAttempts ??= []
  state.clientDeactivationAttempts.push({ path, body: structuredClone(body), key })
  if (saved) { json(saved); return true }
  const reviewed = body.purchases
  if (client.status !== 'active' || body.expectedVersion !== client.version || body.expectedTrainerId !== client.trainer_id
    || reviewed.length !== client.purchases.length || client.purchases.some(p => !reviewed.some(r => r.id === p.id && r.version === p.version && r.status === p.status))) { error('state_conflict', 409); return true }
  if (state.deactivationAbsentUnknown) { state.deactivationAbsentUnknown = false; error('service_unavailable', 503); return true }
  client.status = 'inactive'; client.version++
  for (const purchase of client.purchases) if (purchase.status === 'active') { purchase.status = 'inactive'; purchase.version++ }
  const result = { id: client.id, version: client.version, status: 'inactive' }
  state.clientDeactivationReceipts.set(key, result)
  if (state.deactivationUnknown) { state.deactivationUnknown = false; error('service_unavailable', 503); return true }
  if (state.deactivationRefreshFailure) { state.deactivationRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
