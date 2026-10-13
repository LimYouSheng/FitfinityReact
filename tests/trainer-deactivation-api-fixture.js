import { trainerDeactivationReview } from '../src/test/trainerDeactivation.js'

export function trainerDeactivationApiFixture({ state, path, request, body, json, error }) {
  const target = /^\/api\/trainers\/([^/]+)\/deactivation(-review)?$/.exec(path)
  const receipt = /^\/api\/trainer-deactivations\/([^/]+)$/.exec(path)
  if (!target && !receipt) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.trainerDeactivationReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.trainerDeactivationReceipts.get(key)
  if (receipt) { if (saved) json(saved); else error('not_found', 404); return true }
  const trainer = state.directory.trainers.find(t => t.id === target[1])
  if (!trainer || trainer.status !== 'active') { error('state_conflict', 409); return true }
  const viewed = { ...trainerDeactivationReview(), id: trainer.id, version: trainer.version, name: trainer.name, expected: trainer.version.toString(16).padStart(64, '0') }
  if (state.trainerDeactivationEmpty) viewed.sessions = []
  if (state.trainerDeactivationOpen) viewed.sessions = viewed.sessions.map(s => ({ ...s, scheduleState: 'open', date: null, startsAt: null, endsAt: null }))
  if (state.trainerDeactivationConflict) viewed.sessions = viewed.sessions.map(s => ({ ...s, choices: s.choices.map(t => ({ ...t, error: 'Already booked' })) }))
  if (request.method === 'GET') { json(viewed); return true }
  if (viewed.expected !== body.expected) { error('state_conflict', 409); return true }
  if (target[2]) { json(viewed); return true }
  state.trainerDeactivationAttempts ??= []
  state.trainerDeactivationAttempts.push({ key, body: structuredClone(body) })
  if (saved) { json(saved); return true }
  if (Object.keys(body.replacements).length !== viewed.sessions.length || viewed.sessions.some(s => !s.choices.some(t => t.id === body.replacements[s.id] && !t.error))) { error('state_conflict', 409); return true }
  if (state.trainerDeactivationAbsent) { state.trainerDeactivationAbsent = false; error('service_unavailable', 503); return true }
  trainer.status = 'inactive'; trainer.version++
  state.trainerDeactivationSavedSessions = viewed.sessions.map(s => ({ ...s, trainerId: body.replacements[s.id] }))
  const result = { id: trainer.id, version: trainer.version, status: 'inactive' }
  state.trainerDeactivationReceipts.set(key, result)
  if (state.trainerDeactivationUnknown) { state.trainerDeactivationUnknown = false; error('service_unavailable', 503); return true }
  if (state.trainerDeactivationRefreshFailure) state.unavailable = true
  json(result); return true
}
