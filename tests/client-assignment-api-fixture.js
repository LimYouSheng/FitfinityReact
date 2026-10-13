import { assignmentReview } from '../src/test/clientAssignment.js'
import { directoryId } from '../src/test/directory.js'

export function clientAssignmentApiFixture({ state, path, request, body, json, error }) {
  const target = /^\/api\/clients\/([^/]+)\/trainer-assignment(-review)?$/.exec(path)
  const receipt = /^\/api\/client-trainer-assignments\/([^/]+)$/.exec(path)
  if (!target && !receipt) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.clientAssignmentReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.clientAssignmentReceipts.get(key)
  if (receipt) { if (saved) json(saved); else error('not_found', 404); return true }
  const client = state.directory.clients.find(c => c.id === target[1])
  if (!client || client.status !== 'active') { error('not_found', 404); return true }
  const current = state.directory.trainers.find(t => t.id === client.trainer_id)
  const review = { ...assignmentReview(), id: client.id, name: client.name, version: client.version, expected: client.version.toString(16).padStart(64, '0'),
    current: { id: current.id, name: current.name },
    purchases: client.purchases.filter(p => p.status === 'active' && p.stage !== 'archived').map(p => ({ id: p.id, version: p.version, name: p.name, trainerId: p.trainer_id })),
    choices: state.directory.trainers.filter(t => t.id !== current.id && t.status === 'active').map(t => ({ id: t.id, name: t.name, version: t.version, error: state.clientAssignmentConflict ? 'The selected trainer has another booking during an eligible session.' : null })),
    history: state.clientAssignmentHistory ?? [] }
  review.sessions = review.sessions.map(s => ({ ...s, trainerId: current.id, purchaseId: review.purchases[0].id }))
  if (request.method === 'GET') { json(review); return true }
  state.clientAssignmentAttempts ??= []
  state.clientAssignmentAttempts.push({ key, body: structuredClone(body) })
  if (saved) { json(saved); return true }
  const replacement = review.choices.find(t => t.id === body.trainerId)
  if (review.expected !== body.expected || !replacement || replacement.error) { error('state_conflict', 409); return true }
  if (state.clientAssignmentAbsent) { state.clientAssignmentAbsent = false; error('service_unavailable', 503); return true }
  client.trainer_id = replacement.id; client.version++
  for (const purchase of client.purchases.filter(p => review.purchases.some(r => r.id === p.id))) {
    purchase.trainer_id = replacement.id; purchase.trainer_name = replacement.name; purchase.version++
  }
  const result = { id: client.id, version: client.version, trainerId: replacement.id, eventId: directoryId(32) }
  state.clientAssignmentHistory = [...review.history, { id: result.eventId, at: '2026-10-13T20:00:00Z', actor: { id: state.user.id, name: state.user.name }, previous: review.current, replacement: { id: replacement.id, name: replacement.name } }]
  state.clientAssignmentReceipts.set(key, result)
  if (state.clientAssignmentUnknown) { state.clientAssignmentUnknown = false; error('service_unavailable', 503); return true }
  if (state.clientAssignmentRefreshFailure) state.unavailable = true
  json(result); return true
}
