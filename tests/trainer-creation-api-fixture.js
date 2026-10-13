import { directoryId } from '../src/test/directory.js'

export function trainerCreationApiFixture({ state, path, request, body, json, error }) {
  const receipt = /^\/api\/staff\/trainer-creations\/([^/]+)$/.exec(path)
  if (path !== '/api/staff/trainers' && !receipt) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.trainerCreationReceipts ??= new Map()
  const key = `${state.user.id}/${receipt?.[1] ?? request.headers['idempotency-key']}`
  const saved = state.trainerCreationReceipts.get(key)
  if (receipt) { if (saved) json(saved); else error('not_found', 404); return true }
  state.trainerCreationAttempts ??= []
  state.trainerCreationAttempts.push({ key, body: structuredClone(body) })
  if (saved && ['sent', 'unknown'].includes(saved.invitation)) { json(saved); return true }
  if (state.trainerCreationPending) {
    state.trainerCreationPending = false
    state.trainerCreationReceipts.set(key, { id: directoryId(41), invitation: 'pending' })
    error('INVITATION_RETRY', 503); return true
  }
  const result = { id: directoryId(41), invitation: state.trainerInvitationUnknown ? 'unknown' : 'sent' }
  const trainer = { ...state.directory.trainers[0], id: result.id, version: 1, status: 'active', name: body.name, email: body.email, phone_country_code: body.phone_country_code, phone_number: body.phone_number, birthday: body.birthday, gender: body.gender, trainer_type: body.trainerType, qualifications: body.qualifications, public_profile: body.publicProfile === 'Visible', availability: body.slots.map((slot, index) => ({ id: directoryId(50 + index), weekday: slot.weekday, starts_at: slot.startsAt, ends_at: slot.endsAt })), approve_availability: body.approvalNeeded.availability, approve_session_time: body.approvalNeeded.sessionTime, approve_session_trainer: body.approvalNeeded.trainerReassignment, approve_weekly_schedule: body.approvalNeeded.fixedWeeklySchedule }
  if (state.user.role === 'owner') { trainer.peak_rate_cents = body.rates.peak; trainer.off_peak_rate_cents = body.rates.offPeak }
  state.directory.trainers.push(trainer)
  state.trainerCreationReceipts.set(key, result)
  if (state.trainerCreationUnknown) { state.trainerCreationUnknown = false; error('service_unavailable', 503); return true }
  if (state.trainerCreationRefreshFailure) state.unavailable = true
  json(result); return true
}
