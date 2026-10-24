import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validSessionDate } from '../app/sessionRules.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const month = value => typeof value === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(value)
const hash = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
const integer = value => Number.isSafeInteger(value) && value >= 0
const fail = () => { throw new ApiError('API_RESPONSE', 'Remuneration could not be verified.') }
const invalid = () => { throw new ApiError('INVALID_REQUEST', 'Choose a trainer and reviewed pay cycle.') }
const timestamp = value => typeof value === 'string' && Number.isFinite(Date.parse(value))
const text = value => typeof value === 'string' && Boolean(value.trim())
const time = value => typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(value)
function period(value) {
  if (!value || !month(value.key) || ![value.start, value.end, value.payout].every(validSessionDate) || value.start >= value.end || value.end >= value.payout || value.end !== `${value.key}-15` || value.payout !== `${value.key}-16`) fail()
}
function record(value, user, current = false) {
  if (!value || !uuid(value.trainerId) || !text(value.trainerName) || !hash(value.revision) || !Array.isArray(value.rows) || value.rows.length > 2000 || ![value.sessions, value.totalSessions, value.minutes, value.amountCents, value.reviewCount].every(integer) || typeof value.closed !== 'boolean' || typeof value.changed !== 'boolean' || !['In progress', 'No sessions', 'Pending review', 'Pending approval', 'Approved'].includes(value.status)) fail()
  period(value.cycle)
  if (user.role === 'trainer' && value.trainerId !== user.trainerId) fail()
  if (new Set(value.rows.map(row => row.sessionId)).size !== value.rows.length) fail()
  for (const row of value.rows) {
    if (!uuid(row.sessionId) || !uuid(row.clientId) || !text(row.clientName) || !['Individual', 'Couple'].includes(row.clientType) || !hash(row.source) || !validSessionDate(row.date) || row.date < value.cycle.start || row.date > value.cycle.end || !time(row.from) || !time(row.to) || row.from >= row.to || !integer(row.durationMinutes) || typeof row.billable !== 'boolean' || !['scheduled', 'planned', 'completed'].includes(row.status) || !['peak', 'offPeak'].includes(row.band) || !(row.amountCents === null || integer(row.amountCents)) || !Array.isArray(row.issues) || !row.issues.every(text)) fail()
  }
  if (value.totalSessions !== value.rows.length || value.sessions !== value.rows.filter(row => row.billable).length || value.minutes !== value.rows.reduce((sum, row) => sum + row.durationMinutes, 0) || value.amountCents !== value.rows.reduce((sum, row) => sum + (row.amountCents ?? 0), 0) || value.reviewCount !== value.rows.filter(row => row.issues.length).length) fail()
  if (value.status === 'Approved') {
    if (current || !value.closed || !uuid(value.approvedBy) || !timestamp(value.approvedAt) || !value.current) fail()
    record(value.current, user, true)
    if (value.current.trainerId !== value.trainerId || value.current.cycle.key !== value.cycle.key) fail()
  } else if (value.current !== null || value.approvedBy !== null || value.approvedAt !== null || value.changed) fail()
  return value
}

/** Verify financial totals and actor scope before rendering; uncertain approval retains its original intent. */
export function remunerationCommands(http, actionSession) {
  const actor = async generation => {
    const session = await actionSession(generation)
    if (!['owner', 'trainer'].includes(session.user.role)) throw new ApiError('forbidden', 'Remuneration access is restricted.', 403)
    return session
  }
  const approve = reconciledCommand(http, actionSession, {
    label: 'Remuneration approval', roles: ['owner'], path: input => `/api/remuneration/${input.cycle}/${input.trainerId}/approval`, receiptPath: '/api/remuneration-approvals',
    bodyFor: input => ({ revision: input.revision }),
    validate(value, input) {
      if (!uuid(value?.id) || value.trainerId !== input.trainerId || value.cycle !== input.cycle || value.revision !== input.revision || !timestamp(value.approvedAt)) fail()
      return value
    },
  })
  return {
    async list(generation) {
      const { user, sessionGeneration } = await actor(generation)
      const views = await http.get('/api/remuneration', { expectedGeneration: sessionGeneration })
      if (!Array.isArray(views) || views.length > 2000 || new Set(views.map(view => view.key)).size !== views.length) fail()
      for (const view of views) {
        period(view.cycle)
        if (view.key !== view.cycle.key || typeof view.isCurrent !== 'boolean' || !Array.isArray(view.trainers) || new Set(view.trainers.map(row => row.trainerId)).size !== view.trainers.length) fail()
        for (const row of view.trainers) { record(row, user); if (row.cycle.key !== view.key) fail() }
      }
      return views
    },
    async detail(input, generation) {
      if (!month(input?.cycle) || !uuid(input.trainerId)) invalid()
      const { user, sessionGeneration } = await actor(generation)
      if (user.role === 'trainer' && user.trainerId !== input.trainerId) throw new ApiError('not_found', 'This remuneration is unavailable.', 404)
      const result = record(await http.get(`/api/remuneration/${input.cycle}/${input.trainerId}`, { expectedGeneration: sessionGeneration }), user)
      if (result.trainerId !== input.trainerId || result.cycle.key !== input.cycle) fail()
      return result
    },
    async approve(input, generation) {
      if (!month(input?.cycle) || !uuid(input.trainerId) || !hash(input.revision)) invalid()
      return approve({ cycle: input.cycle, trainerId: input.trainerId, revision: input.revision }, generation)
    },
    pendingInput: approve.pendingInput,
  }
}
