import { reactivationReview } from '../src/test/clientLifecycleApi.js'

export function packageReactivationApiFixture({ state, path, request, body, json, error }) {
  const endpoint = /^\/api\/clients\/([^/]+)\/packages\/([^/]+)\/(reactivation|reactivation-review)$/.exec(path)
  const receipt = /^\/api\/package-reactivations\/([^/]+)$/.exec(path)
  if (!endpoint && !receipt) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.packageReactivationReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.packageReactivationReceipts.get(key)
  if (receipt) { if (saved) json(saved); else error('not_found', 404); return true }
  const client = state.directory.clients.find(row => row.id === endpoint[1])
  if (!client) { error('not_found', 404); return true }
  const purchase = client.purchases.find(p => p.id === endpoint[2])
  if (!purchase) { error('not_found', 404); return true }
  const reviewed = reactivationReview({ id: client.id, name: client.name, version: client.version,
    packageId: purchase.id, purchaseIds: [purchase.id], expected: (client.version + client.purchases.reduce((n, p) => n + p.version, 0)).toString(16).padStart(64, '0') })
  reviewed.rows = reviewed.rows.map(r => ({ ...r, purchaseId: purchase.id, error: state.packageReactivationConflict ? 'Conflicts with another booking for this trainer or client. Choose a free date.' : null }))
  if (state.packageReactivationOpen) reviewed.rows.push({ ...reviewed.rows[0], id: '10000000-0000-4000-8000-000000000021', scheduleState: 'open', date: null, originalDate: null, startsAt: null, endsAt: null, error: null })
  if (request.method === 'GET') {
    if (client.status !== 'active' || purchase.status !== 'inactive') { error('state_conflict', 409); return true }
    json(reviewed); return true
  }
  if (endpoint[3] === 'reactivation') {
    state.packageReactivationAttempts ??= []
    state.packageReactivationAttempts.push({ path, body: structuredClone(body), key })
    if (saved) { json(saved); return true }
  }
  if (client.status !== 'active' || purchase.status !== 'inactive' || body.expected !== reviewed.expected) { error('state_conflict', 409); return true }
  for (const row of reviewed.rows) {
    row.date = body.dates[row.id] ?? row.originalDate
    if (row.date !== row.originalDate) row.error = null
  }
  if (endpoint[3] === 'reactivation-review') { json(reviewed); return true }
  if (reviewed.rows.some(r => r.error)) { error('state_conflict', 409); return true }
  if (state.packageReactivationAbsentUnknown) { state.packageReactivationAbsentUnknown = false; error('service_unavailable', 503); return true }
  client.version++; purchase.status = 'active'; purchase.version++
  const result = { id: client.id, version: client.version, packageId: purchase.id, status: 'active' }
  state.packageReactivationReceipts.set(key, result)
  if (state.packageReactivationUnknown) { state.packageReactivationUnknown = false; error('service_unavailable', 503); return true }
  if (state.packageReactivationRefreshFailure) { state.packageReactivationRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
