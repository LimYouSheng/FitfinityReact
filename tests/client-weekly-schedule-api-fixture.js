import { weeklyReview } from '../src/test/clientWeeklySchedule.js'
import { directoryId } from '../src/test/directory.js'
export function clientWeeklyScheduleApiFixture({ state, path, request, body, json, error }) {
  const target = /^\/api\/clients\/([^/]+)\/weekly-schedule(-review)?$/.exec(path)
  const receipt = /^\/api\/client-weekly-schedules\/([^/]+)$/.exec(path)
  if (!target && !receipt) return false
  state.weeklyReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.weeklyReceipts.get(key)
  if (receipt) { if (saved) json(saved); else error('not_found', 404); return true }
  const client = state.directory.clients.find(c => c.id === target[1])
  if (!client || client.status !== 'active' || (state.user.role === 'trainer' && client.trainer_id !== state.user.trainerId)) { error('not_found', 404); return true }
  const trainer = state.directory.trainers.find(t => t.id === client.trainer_id), purchase = client.purchases.find(p => p.stage === 'current')
  const outcome = state.user.role === 'trainer' && trainer.approve_weekly_schedule ? 'requested' : 'applied'
  const review = { ...weeklyReview(outcome), id: client.id, name: client.name, version: client.version, expected: client.version.toString(16).padStart(64, '0'), purchaseId: purchase.id, purchaseVersion: purchase.version, trainerId: trainer.id, trainerVersion: trainer.version,
    slots: purchase.schedule.map(s => ({ id: s.id, weekday: s.weekday, startsAt: s.starts_at.slice(0, 5), endsAt: s.ends_at.slice(0, 5) })) }
  if (request.method === 'GET') { json(review); return true }
  if (target[2]) {
    if (review.expected !== body.expected || state.weeklyConflict) error('state_conflict', 409)
    else json({ expected: review.expected, outcome, updatedSessions: 1 })
    return true
  }
  state.weeklyAttempts ??= []; state.weeklyAttempts.push({ key, body: structuredClone(body) })
  if (saved) { json(saved); return true }
  if (review.expected !== body.expected) { error('state_conflict', 409); return true }
  if (state.weeklyAbsent) { state.weeklyAbsent = false; error('service_unavailable', 503); return true }
  if (outcome === 'applied') {
    for (const slot of purchase.schedule) { const changed = body.slots.find(s => s.id === slot.id); slot.starts_at = `${changed.startsAt}:00`; slot.ends_at = `${changed.endsAt}:00` }
    client.version++; purchase.version++
  } else state.weeklyProposal = structuredClone(body)
  const result = { outcome, client: { id: client.id, version: client.version }, requestId: outcome === 'requested' ? directoryId(40) : null, updatedSessions: outcome === 'applied' ? 1 : 0 }
  state.weeklyReceipts.set(key, result)
  if (state.weeklyUnknown) { state.weeklyUnknown = false; error('service_unavailable', 503); return true }
  if (state.weeklyRefreshFailure) state.unavailable = true
  json(result); return true
}
