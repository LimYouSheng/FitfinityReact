import { directoryId } from '../src/test/directory.js'
import { messageRequest, personalNotice } from '../src/test/messageApi.js'

export function trainerAvailabilityApiFixture({ state, path, request, body, json, error }) {
  const write = /^\/api\/trainers\/([^/]+)\/availability$/.exec(path)
  const receipt = /^\/api\/trainer-availability-saves\/([^/]+)$/.exec(path)
  if (!write && !receipt) return false
  if (state.user.role !== 'trainer') { error('forbidden', 403); return true }
  state.availabilityReceipts ??= new Map()
  const key = `${state.user.id}/${request.headers['idempotency-key'] ?? receipt?.[1]}`
  const saved = state.availabilityReceipts.get(key)
  if (request.method === 'GET') { if (saved) json(saved); else error('not_found', 404); return true }
  state.availabilityAttempts ??= []
  state.availabilityAttempts.push({ path, body: structuredClone(body), key })
  if (saved) { json(saved); return true }
  const trainer = state.directory.trainers.find(row => row.id === write[1] && row.id === state.user.trainerId)
  if (!trainer || trainer.status !== 'active') { error('not_found', 404); return true }
  if (trainer.version !== body.expectedVersion) { error('state_conflict', 409); return true }
  if (state.availabilityAbsentUnknown) { state.availabilityAbsentUnknown = false; error('service_unavailable', 503); return true }
  let requestId = null
  if (trainer.approve_availability) {
    requestId = directoryId(300)
    const proposal = messageRequest({ id: requestId, trainer_id: trainer.id, expected_version: trainer.version, slots: [
      ...trainer.availability.map((slot, index) => ({ side: 'old', slot_identity: directoryId(310 + index), weekday: slot.weekday, starts_at: slot.starts_at, ends_at: slot.ends_at })),
      ...body.slots.map((slot, index) => ({ side: 'new', slot_identity: directoryId(330 + index), weekday: slot.weekday, starts_at: `${slot.startsAt}:00`, ends_at: `${slot.endsAt}:00` })),
    ] })
    state.messageRecords ??= []
    state.messageRecords.push({ value: personalNotice({ id: directoryId(301), title: 'Availability change request', kind: 'availability_request', requestId, trainerId: trainer.id, request: proposal, actorId: state.user.id, actorName: state.user.name }), recipients: ['trainer', 'owner'] })
  } else {
    trainer.availability = body.slots.map((slot, index) => ({ id: directoryId(350 + index), weekday: slot.weekday, starts_at: `${slot.startsAt}:00`, ends_at: `${slot.endsAt}:00` }))
    trainer.version++
  }
  const result = { outcome: requestId ? 'requested' : 'applied', trainer: { id: trainer.id, version: trainer.version }, requestId }
  state.availabilityReceipts.set(key, result)
  if (state.availabilityUnknown) { state.availabilityUnknown = false; error('service_unavailable', 503); return true }
  if (state.availabilityRefreshFailure) { state.availabilityRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
