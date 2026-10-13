import { directoryId } from '../src/test/directory.js'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const addDays = (day, amount) => { const date = new Date(`${day}T00:00:00Z`); date.setUTCDate(date.getUTCDate() + amount); return date.toISOString().slice(0, 10) }
const expected = client => client.version.toString(16).padStart(64, '0')

// HTTP/recovery fixture only. PostgreSQL tests own real occupancy, atomicity and activation.
export function clientRenewalApiFixture({ state, path, request, body, json, error }) {
  const route = /^\/api\/clients\/([^/]+)\/(renewal-review|renewal-matches|packages)$/.exec(path)
  const receipt = /^\/api\/client-renewals\/([^/]+)$/.exec(path)
  if (!route && !receipt) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.packageRenewalReceipts ??= new Map()
  if (receipt) {
    const stored = state.packageRenewalReceipts.get(`${state.user.id}/${receipt[1]}`)
    if (stored) json(stored.result); else error('not_found', 404)
    return true
  }
  const client = state.directory.clients.find(c => c.id === route[1] && c.status === 'active')
  if (!client) { error('not_found', 404); return true }
  const current = client.purchases.find(p => p.stage === 'current')
  if (route[2] === 'renewal-review') {
    if (state.packageRenewalReviewFailure) { state.packageRenewalReviewFailure = false; error('service_unavailable', 503); return true }
    const last = client.purchases.filter(p => p.status === 'active').map(p => p.end_date).sort().at(-1)
    json({ id: client.id, version: client.version, name: client.name, trainerId: client.trainer_id, genderPreference: 'No gender preference', expected: expected(client),
      minimumStartDate: [state.directory.businessDate, ...(last ? [addDays(last, 1)] : [])].sort().at(-1),
      package: { id: current.id, version: current.version, templateId: current.template_id, total: current.total_sessions, validityDays: current.validity_days, sessionsPerWeek: current.sessions_per_week, startDate: current.start_date, endDate: current.end_date },
      fixedWeeklySchedule: current.schedule.map(s => ({ id: s.id, day: days[s.weekday], from: s.starts_at.slice(0, 5), to: s.ends_at.slice(0, 5) })),
      clientPreferences: [{ days: ['Monday'], from: '09:00', to: '12:00' }] })
    return true
  }
  if (route[2] === 'renewal-matches') {
    state.packageRenewalMatches ??= []
    state.packageRenewalMatches.push(structuredClone(body))
    if (body.expected !== expected(client)) { error('state_conflict', 409); return true }
    const trainer = state.directory.trainers[0], first = body.clientPreferences[0]
    json({ matches: state.packageRenewalNoMatches ? [] : [{ trainerId: trainer.id, trainerVersion: trainer.version, matches: body.clientPreferences.length, total: body.clientPreferences.length,
      schedule: body.fixedWeeklySchedule ?? [{ day: first.days[0], from: first.from, to: first.to }] }] })
    return true
  }
  const key = `${state.user.id}/${request.headers['idempotency-key']}`
  state.packageRenewalAttempts ??= []
  state.packageRenewalAttempts.push({ path, body: structuredClone(body), key })
  const stored = state.packageRenewalReceipts.get(key)
  if (stored) { if (JSON.stringify(stored.body) !== JSON.stringify(body)) error('idempotency_conflict', 409); else json(stored.result); return true }
  if (body.expected !== expected(client) || state.packageRenewalConflict) { error('state_conflict', 409); return true }
  if (state.packageRenewalAbsentUnknown) { state.packageRenewalAbsentUnknown = false; error('service_unavailable', 503); return true }
  const template = state.directory.packages.find(p => p.id === body.packageId)
  const trainer = state.directory.trainers.find(t => t.id === body.trainerId)
  const purchaseId = directoryId(800 + state.packageRenewalReceipts.size)
  client.purchases.push({ ...structuredClone(current), id: purchaseId, version: 1, name: template.name, template_id: template.id, template_revision: template.revision,
    total_sessions: template.total_sessions, validity_days: template.validity_days, sessions_per_week: body.sessionsPerWeek, free_gym: body.sessionsPerWeek >= 2,
    start_date: body.startDate, end_date: addDays(body.startDate, template.validity_days - 1), status: 'active', stage: 'queued', used: 0,
    purchased_trainer_id: trainer.id, trainer_id: trainer.id, trainer_name: trainer.name,
    schedule: body.fixedWeeklySchedule.map((s, i) => ({ id: directoryId(820 + i), weekday: days.indexOf(s.day), starts_at: `${s.from}:00`, ends_at: `${s.to}:00` })) })
  client.version++
  const result = { id: client.id, version: client.version, purchaseId }
  state.packageRenewalReceipts.set(key, { result, body: structuredClone(body) })
  if (state.packageRenewalUnknown) { state.packageRenewalUnknown = false; error('service_unavailable', 503); return true }
  if (state.packageRenewalRefreshFailure) { state.packageRenewalRefreshFailure = false; state.unavailable = true }
  json(result); return true
}
