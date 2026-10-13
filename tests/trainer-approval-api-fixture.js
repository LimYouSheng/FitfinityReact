// Controlled browser boundary. Real transactions/authority are tested against PostgreSQL.
export function trainerApprovalApiFixture({ state, path, request, body, json, error }) {
  if (!path.startsWith('/api/trainer-approval-saves/') && !/^\/api\/trainers\/[^/]+\/approvals$/.test(path)) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.approvalSaves ??= new Map()
  if (request.method === 'GET') {
    const result = state.approvalSaves.get(path.split('/').at(-1))
    if (result) json(result); else error('not_found', 404)
    return true
  }
  const key = request.headers['idempotency-key']
  if (state.approvalSaves.has(key)) { json(state.approvalSaves.get(key)); return true }
  const trainer = state.directory.trainers.find(t => t.id === path.split('/')[3])
  if (!key || !trainer || trainer.version !== body.expectedVersion) { error('state_conflict', 409); return true }
  trainer.version += 1
  const columns = { availability: 'approve_availability', sessionTime: 'approve_session_time', trainerReassignment: 'approve_session_trainer', fixedWeeklySchedule: 'approve_weekly_schedule' }
  for (const [field, column] of Object.entries(columns)) trainer[column] = body.approvalNeeded[field]
  const result = { id: trainer.id, version: trainer.version, approvalNeeded: body.approvalNeeded }
  state.approvalSaves.set(key, result)
  if (state.approvalUnknown) { state.approvalUnknown = false; error('service_unavailable', 503); return true }
  if (state.approvalRefreshFailure) { state.approvalRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
