import { ApiError } from './apiClient.js'
import { validSessionDate } from '../app/sessionRules.js'
import { validSignature } from '../app/signature.js'
const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const integer = (v, min = 0) => Number.isSafeInteger(v) && v >= min
const text = v => typeof v === 'string'
const keys = (v, allowed) => v && Object.keys(v).every(k => allowed.includes(k))
const rows = (v, max = 2000) => Array.isArray(v) && v.length <= max && new Set(v.map(r => r?.id)).size === v.length
const time = v => text(v) && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(v)
const timestamp = v => text(v) && Number.isFinite(Date.parse(v))
const status = v => ['active', 'inactive'].includes(v)
const fail = () => { throw new ApiError('API_RESPONSE', 'Session records could not be verified. Reload before continuing.') }
const client = c => keys(c, ['id', 'name', 'kind', 'status']) && uuid(c.id) && text(c.name) && ['individual', 'couple'].includes(c.kind) && status(c.status)
const trainer = t => keys(t, ['id', 'name', 'status']) && uuid(t.id) && text(t.name) && status(t.status)
const purchase = p => keys(p, ['id', 'clientId', 'trainerId', 'name', 'status', 'stage', 'total', 'used', 'validityDays', 'startDate', 'endDate']) && uuid(p.id) && uuid(p.clientId) && uuid(p.trainerId) && text(p.name) && status(p.status) && ['current', 'queued', 'archived'].includes(p.stage) && integer(p.total, 1) && integer(p.used) && p.used <= p.total && integer(p.validityDays, 1) && validSessionDate(p.startDate) && validSessionDate(p.endDate) && p.startDate <= p.endDate
function sessionRow(s) {
  return keys(s, ['readAccess', 'id', 'version', 'clientId', 'purchaseId', 'trainerId', 'scheduleState', 'sessionNumber', 'date', 'startsAt', 'endsAt', 'status']) && ['operations', 'assigned', 'historical'].includes(s.readAccess) && uuid(s.id) && integer(s.version, 1) && uuid(s.clientId) && uuid(s.purchaseId) && uuid(s.trainerId) && ['scheduled', 'planned', 'completed', 'cancelled'].includes(s.status)
    && (s.scheduleState === 'open' ? s.date === null && s.startsAt === null && s.endsAt === null && s.sessionNumber === null && s.status !== 'completed' : s.scheduleState === 'booked' && validSessionDate(s.date) && time(s.startsAt) && time(s.endsAt) && s.startsAt < s.endsAt && integer(s.sessionNumber, 1))
}
const authorized = (s, user) => user.role === 'trainer' ? (s.readAccess === (s.trainerId === user.trainerId ? 'assigned' : 'historical')) : s.readAccess === 'operations'
const mapped = (s, user) => ({ ...(user.role === 'trainer' ? { readableByTrainerId: user.trainerId } : {}), id: s.id, version: s.version, clientId: s.clientId, packageId: s.purchaseId, trainerId: s.trainerId, scheduleState: s.scheduleState === 'booked' ? 'scheduled' : 'open', sessionNumber: s.sessionNumber, date: s.date, from: s.startsAt, to: s.endsAt, status: s.status === 'scheduled' ? 'not_planned' : s.status })
const context = (c, purchases) => ({ ...c, package: purchases.find(p => p.clientId === c.id && p.stage === 'current') ?? null, additionalPackages: purchases.filter(p => p.clientId === c.id && p.stage === 'queued'), packageHistory: purchases.filter(p => p.clientId === c.id && p.stage === 'archived') })
export function sessionCalendar(value, user) {
  if (!keys(value, ['viewerId', 'sessions', 'clients', 'trainers', 'purchases']) || value.viewerId !== user.id || !rows(value.sessions, 730000) || !rows(value.clients) || !rows(value.trainers) || !rows(value.purchases, 730000) || !value.clients.every(client) || !value.trainers.every(trainer) || !value.purchases.every(purchase)) fail()
  const clients = new Map(value.clients.map(c => [c.id, c])), trainers = new Map(value.trainers.map(t => [t.id, t])), purchases = new Map(value.purchases.map(p => [p.id, p]))
  const referencedClients = new Set(), referencedTrainers = new Set(), referencedPurchases = new Set(), byClient = new Map()
  for (const s of value.sessions) {
    if (!sessionRow(s) || !clients.has(s.clientId) || !trainers.has(s.trainerId) || purchases.get(s.purchaseId)?.clientId !== s.clientId || !authorized(s, user)) fail()
    referencedClients.add(s.clientId); referencedTrainers.add(s.trainerId); referencedPurchases.add(s.purchaseId)
  }
  if (value.clients.some(c => !referencedClients.has(c.id)) || value.trainers.some(t => !referencedTrainers.has(t.id)) || value.purchases.some(p => !referencedPurchases.has(p.id))) fail()
  for (const p of value.purchases) { if (!byClient.has(p.clientId)) byClient.set(p.clientId, []); byClient.get(p.clientId).push(p) }
  if ([...byClient.values()].some(group => group.filter(p => p.stage === 'current').length > 1)) fail()
  return { sessions: value.sessions.map(s => ({ ...mapped(s, user), packageTotal: purchases.get(s.purchaseId).total })), sessionClients: value.clients.map(c => context(c, byClient.get(c.id) ?? [])), sessionTrainers: value.trainers }
}
function acknowledgement(a) {
  return keys(a, ['id', 'sequence', 'method', 'signerName', 'signature', 'note', 'recordedAt', 'recordedBy']) && uuid(a.id) && [1, 2].includes(a.sequence) && text(a.note) && timestamp(a.recordedAt) && keys(a.recordedBy, ['id', 'name']) && uuid(a.recordedBy.id) && text(a.recordedBy.name)
    && (a.method === 'signature' ? text(a.signerName) && a.signerName.trim() && validSignature(a.signature) : a.method === 'late_no_show' && a.signerName === null && a.signature === null)
}
export const validPlanItem = p => keys(p, ['id', 'version', 'name', 'weight', 'reps', 'rounds', 'rest', 'notes', 'customDetails', 'videoAttached']) && uuid(p.id) && integer(p.version, 1) && ['name', 'weight', 'reps', 'rounds', 'rest', 'notes'].every(k => text(p[k])) && typeof p.videoAttached === 'boolean' && rows(p.customDetails, 100) && p.customDetails.every(d => keys(d, ['id', 'value']) && text(d.id) && d.id.length > 0 && text(d.value))
export function sessionDetail(value, id, user) {
  if (!keys(value, ['session', 'client', 'trainer', 'purchase', 'exercisePlan', 'retiredPlanItemIds', 'exerciseResults', 'acknowledgementHistory', 'trainerComments', 'clientSummary', 'whatsappOpenedAt', 'whatsappOpenCount']) || !sessionRow(value.session) || value.session.id !== id || !client(value.client) || !trainer(value.trainer) || !purchase(value.purchase) || value.session.clientId !== value.client.id || value.session.trainerId !== value.trainer.id || value.session.purchaseId !== value.purchase.id || value.purchase.clientId !== value.client.id || !authorized(value.session, user)) fail()
  if (!rows(value.exercisePlan) || !rows(value.exerciseResults) || !rows(value.acknowledgementHistory, 2) || !text(value.trainerComments) || !text(value.clientSummary) || !integer(value.whatsappOpenCount) || (value.whatsappOpenedAt !== null && !timestamp(value.whatsappOpenedAt))) fail()
  if (!value.exercisePlan.every(validPlanItem) || !Array.isArray(value.retiredPlanItemIds) || value.retiredPlanItemIds.length > 2000 || !value.retiredPlanItemIds.every(uuid) || new Set(value.retiredPlanItemIds).size !== value.retiredPlanItemIds.length || value.retiredPlanItemIds.some(id => value.exercisePlan.some(p => p.id === id))) fail()
  if (!value.exerciseResults.every(r => keys(r, ['id', 'planItemId', 'name', 'loadKg', 'reps', 'sets']) && uuid(r.id) && (r.planItemId === null || value.exercisePlan.some(p => p.id === r.planItemId) || value.retiredPlanItemIds.includes(r.planItemId)) && text(r.name) && Number.isFinite(r.loadKg) && r.loadKg >= 0 && r.loadKg <= 2000 && integer(r.reps, 1) && r.reps <= 1000 && integer(r.sets, 1) && r.sets <= 100)) fail()
  if (!value.acknowledgementHistory.every((a, i) => acknowledgement(a) && a.sequence === i + 1)) fail()
  const history = value.acknowledgementHistory.map(a => ({ ...a, signerName: a.signerName ?? '' }))
  return { client: context(value.client, [value.purchase]), trainer: value.trainer, session: { ...mapped(value.session, user), packageTotal: value.purchase.total, exercisePlan: value.exercisePlan, exerciseResults: value.exerciseResults.map(r => ({ id: r.planItemId ?? r.id, name: r.name, loadKg: r.loadKg, reps: r.reps, sets: r.sets })), outcome: { trainerComments: value.trainerComments }, clientSummary: value.clientSummary, whatsappOpenedAt: value.whatsappOpenedAt, whatsappOpenCount: value.whatsappOpenCount, acknowledgementHistory: history, acknowledgement: history.at(-1) ?? null } }
}
export async function readSessionDetail(http, actionSession, input, generation) {
  if (!uuid(input?.id)) throw new ApiError('INVALID_REQUEST', 'Choose a session before opening its details.')
  const { user, sessionGeneration } = await actionSession(generation)
  return sessionDetail(await http.get(`/api/sessions/${input.id}/details`, { expectedGeneration: sessionGeneration }), input.id, user)
}
export async function readLimitedSessionClient(http, actionSession, input, generation) {
  if (!uuid(input?.id) || !uuid(input?.clientId)) throw new ApiError('INVALID_REQUEST', 'Choose a session before opening its client.')
  const { sessionGeneration } = await actionSession(generation)
  const value = await http.get(`/api/sessions/${input.id}/client`, { expectedGeneration: sessionGeneration })
  if (!keys(value, ['session_id', 'client_id', 'name', 'kind', 'person_names']) || value.session_id !== input.id || value.client_id !== input.clientId || !uuid(value.client_id) || !text(value.name) || !['individual', 'couple'].includes(value.kind) || !Array.isArray(value.person_names) || value.person_names.length !== (value.kind === 'couple' ? 2 : 1) || !value.person_names.every(text)) fail()
  return value
}
