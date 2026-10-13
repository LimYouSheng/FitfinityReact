import { reactivationReview } from '../src/test/clientLifecycleApi.js'

export function clientReactivationApiFixture({ state, path, request, body, json, error }) {
  const endpoint = /^\/api\/clients\/([^/]+)\/(reactivation|reactivation-review)$/.exec(path)
  const receipt = /^\/api\/client-reactivations\/([^/]+)$/.exec(path)
  if (!endpoint && !receipt) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.clientReactivationReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.clientReactivationReceipts.get(key)
  if (receipt) { if (saved) json(saved); else error('not_found', 404); return true }
  const client = state.directory.clients.find(row => row.id === endpoint[1])
  if (!client) { error('not_found', 404); return true }
  const reviewed = reactivationReview({ id: client.id, name: client.name, version: client.version,
    expected: (client.version + client.purchases.reduce((n, p) => n + p.version, 0)).toString(16).padStart(64, '0') })
  reviewed.rows = reviewed.rows.map(r => ({ ...r, error: state.reactivationConflict ? 'Conflicts with another booking for this trainer or client. Choose a free date.' : null }))
  if (request.method === 'GET') {
    if (client.status !== 'inactive') { error('state_conflict', 409); return true }
    json(reviewed); return true
  }
  if (endpoint[2] === 'reactivation') {
    state.clientReactivationAttempts ??= []
    state.clientReactivationAttempts.push({ path, body: structuredClone(body), key })
    if (saved) { json(saved); return true }
  }
  if (client.status !== 'inactive' || body.expected !== reviewed.expected) { error('state_conflict', 409); return true }
  for (const row of reviewed.rows) {
    row.date = body.dates[row.id] ?? row.originalDate
    if (row.date !== row.originalDate) row.error = null
  }
  if (endpoint[2] === 'reactivation-review') { json(reviewed); return true }
  if (reviewed.rows.some(r => r.error)) { error('state_conflict', 409); return true }
  if (state.reactivationAbsentUnknown) { state.reactivationAbsentUnknown = false; error('service_unavailable', 503); return true }
  client.status = 'active'; client.version++
  for (const purchase of client.purchases) if (purchase.status === 'inactive') { purchase.status = 'active'; purchase.version++ }
  const result = { id: client.id, version: client.version, status: 'active' }
  state.clientReactivationReceipts.set(key, result)
  if (state.reactivationUnknown) { state.reactivationUnknown = false; error('service_unavailable', 503); return true }
  if (state.reactivationRefreshFailure) { state.reactivationRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
