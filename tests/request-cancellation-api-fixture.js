export function requestCancellationApiFixture({ state, path, request, body, json, error }) {
  const write = /^\/api\/requests\/([^/]+)\/cancel$/.exec(path)
  const receipt = /^\/api\/request-cancellations\/([^/]+)$/.exec(path)
  if (!write && !receipt) return false
  if (state.user.role !== 'trainer') { error('forbidden', 403); return true }
  state.cancellationReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.cancellationReceipts.get(key)
  if (request.method === 'GET') { if (saved) json(saved); else error('not_found', 404); return true }
  state.cancellationAttempts ??= []
  state.cancellationAttempts.push({ body: structuredClone(body), key, path })
  if (saved) { json(saved); return true }
  const proposal = state.messageRecords?.find(row => row.value.requestId === write[1])?.value.request
  if (!proposal || proposal.trainer_id !== state.user.trainerId) { error('not_found', 404); return true }
  if (proposal.status !== 'pending' || proposal.version !== body.expectedVersion) { error('state_conflict', 409); return true }
  if (state.cancellationAbsentUnknown) { state.cancellationAbsentUnknown = false; error('service_unavailable', 503); return true }
  const result = { id: proposal.id, version: proposal.version + 1, status: 'cancelled', at: '2026-10-13T16:00:00Z', by: { id: state.user.id, name: state.user.name } }
  for (const row of state.messageRecords.filter(row => row.value.requestId === proposal.id)) Object.assign(row.value.request, { status: result.status, version: result.version, resolved_at: result.at, resolved_by: result.by })
  state.cancellationReceipts.set(key, result)
  if (state.cancellationUnknown) { state.cancellationUnknown = false; error('service_unavailable', 503); return true }
  if (state.cancellationRefreshFailure) { state.cancellationRefreshFailure = false; state.messageReadFailure = true }
  json(result); return true
}
