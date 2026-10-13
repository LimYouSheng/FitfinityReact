export function renewalDismissalApiFixture({ state, path, request, body, json, error }) {
  const write = /^\/api\/messages\/([^/]+)\/dismiss-renewal$/.exec(path)
  const receipt = /^\/api\/renewal-dismissal-saves\/([^/]+)$/.exec(path)
  if (!write && !receipt) return false
  state.renewalDismissalReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.renewalDismissalReceipts.get(key)
  if (request.method === 'GET') { if (saved) json(saved); else error('not_found', 404); return true }
  state.renewalDismissalAttempts ??= []
  state.renewalDismissalAttempts.push({ body: structuredClone(body), key, path })
  if (saved) { json(saved); return true }
  const row = state.messageRecords?.find(row => row.value.id === write[1] && row.value.kind === 'renewal')
  const client = state.directory.clients.find(client => client.id === row?.value.clientId)
  if (!row || !client || (state.user.role === 'trainer' && client.trainerId !== state.user.trainerId && client.trainer_id !== state.user.trainerId)) { error('not_found', 404); return true }
  if (client.version !== body.expectedClientVersion) { error('state_conflict', 409); return true }
  if (state.dismissalAbsentUnknown) { state.dismissalAbsentUnknown = false; error('service_unavailable', 503); return true }
  const result = row.value.renewalStatus === 'renewed' ? { id: row.value.id, renewalStatus: 'renewed', renewalDismissal: null }
    : { id: row.value.id, renewalStatus: 'removed', renewalDismissal: row.value.renewalDismissal ?? { at: '2026-10-13T12:00:00Z', by: { id: state.user.id, name: state.user.name } } }
  Object.assign(row.value, result)
  state.renewalDismissalReceipts.set(key, result)
  if (state.dismissalUnknown) { state.dismissalUnknown = false; error('service_unavailable', 503); return true }
  if (state.dismissalRefreshFailure) { state.dismissalRefreshFailure = false; state.messageReadFailure = true }
  json(result); return true
}
