import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validSessionDate } from '../app/sessionRules.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const keys = (v, fields) => v && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k))
const integer = (v, min, max) => Number.isSafeInteger(v) && v >= min && v <= max
const load = v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 2000
const rows = v => Array.isArray(v) && v.length <= 2000 && new Set(v.map(r => r?.id)).size === v.length
const measured = r => load(r.loadKg) && integer(r.reps, 1, 1000) && integer(r.sets, 1, 100)
const validRow = r => keys(r, ['id', 'resultId', 'planItemId', 'name', 'loadKg', 'reps', 'sets']) && uuid(r.id) && (r.resultId === null || uuid(r.resultId)) && (r.planItemId === null || uuid(r.planItemId)) && r.id === (r.planItemId ?? r.resultId) && typeof r.name === 'string' && r.name.trim() && (r.loadKg === null ? r.reps === null && r.sets === null : measured(r))
const validBase = v => uuid(v?.sessionId) && integer(v.version, 1, Number.MAX_SAFE_INTEGER) && integer(v.durationMinutes, 0, 1440) && typeof v.trainerComments === 'string' && rows(v.rows) && v.rows.every(r => validRow(r) && (r.loadKg === null || uuid(r.resultId)))
const validReview = v => keys(v, ['sessionId', 'version', 'expected', 'durationMinutes', 'trainerComments', 'rows', 'draftRows']) && validBase(v) && rows(v.draftRows) && v.draftRows.length === v.rows.length && v.draftRows.every((r, i) => validRow(r) && r.id === v.rows[i].id && r.name === v.rows[i].name && r.resultId === v.rows[i].resultId) && /^[0-9a-f]{64}$/.test(v.expected)
const fail = () => { throw new ApiError('API_RESPONSE', 'The session outcome could not be verified. Check the original save.') }
const invalid = () => { throw new ApiError('INVALID_REQUEST', 'Review the session outcome and enter valid measured loads, reps and sets.') }
const draft = v => ({ durationMinutes: v.durationMinutes, trainerComments: v.trainerComments, exerciseResults: v.draftRows.map(r => ({ id: r.id, name: r.name, loadKg: r.loadKg ?? '', reps: r.reps ?? '', sets: r.sets ?? '' })) })

/** Freeze original measured values until a committed or interrupted outcome is reconciled. */
export function sessionOutcomeCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Session outcome', roles: ['owner', 'admin', 'trainer'], path: v => `/api/sessions/${v.sessionId}/outcome`, receiptPath: '/api/session-outcomes',
    bodyFor: v => ({ expected: v.reviewed.expected, trainerComments: v.outcome.trainerComments, measurements: v.outcome.exerciseResults.map(({ id, loadKg, reps, sets }) => ({ id, loadKg, reps, sets })) }),
    validate(value, input) {
      if (!keys(value, ['sessionId', 'version', 'durationMinutes', 'trainerComments', 'rows', 'savedAt']) || !validBase(value) || value.sessionId !== input.sessionId || value.version <= input.reviewed.version || value.durationMinutes !== input.reviewed.durationMinutes || value.trainerComments !== input.outcome.trainerComments || typeof value.savedAt !== 'string' || !Number.isFinite(Date.parse(value.savedAt))) fail()
      const offered = new Map(input.reviewed.rows.map(r => [r.id, r]))
      if (value.rows.some(r => !offered.has(r.id) || r.name !== offered.get(r.id).name || (offered.get(r.id).resultId && r.resultId !== offered.get(r.id).resultId))) fail()
      const recorded = value.rows.filter(r => r.loadKg !== null)
      if (recorded.length !== input.outcome.exerciseResults.length || input.outcome.exerciseResults.some(r => !recorded.some(s => s.id === r.id && s.loadKg === r.loadKg && s.reps === r.reps && s.sets === r.sets))) fail()
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      if (!uuid(id) || !integer(expectedVersion, 1, Number.MAX_SAFE_INTEGER)) invalid()
      const { sessionGeneration } = await actionSession(generation)
      const pending = command.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the original outcome before editing another.')
        return { reviewed: pending.reviewed, draft: pending.outcome, uncertain: true }
      }
      const viewed = await http.get(`/api/sessions/${id}/outcome-review`, { expectedGeneration: sessionGeneration })
      if (!validReview(viewed) || viewed.sessionId !== id) fail()
      if (viewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This session changed. Reload before editing its outcome.', 409)
      return { reviewed: viewed, draft: draft(viewed), uncertain: false }
    },
    async save(input, generation) {
      if (!validReview(input?.reviewed) || input.sessionId !== input.reviewed.sessionId || typeof input.outcome?.trainerComments !== 'string' || !Array.isArray(input.outcome.exerciseResults)) invalid()
      const exerciseResults = input.outcome.exerciseResults.filter(r => r.loadKg !== '' && r.loadKg != null).map(r => ({ id: r.id, name: r.name, loadKg: Number(r.loadKg), reps: Number(r.reps), sets: Number(r.sets) }))
      if (!rows(exerciseResults) || exerciseResults.some(r => !uuid(r.id) || !measured(r) || !input.reviewed.rows.some(s => s.id === r.id))) invalid()
      return command({ sessionId: input.sessionId, reviewed: input.reviewed, outcome: { trainerComments: input.outcome.trainerComments.trim(), exerciseResults } }, generation)
    },
    pendingInput: command.pendingInput,
  }
}

/** A profile-only projection; report export/history remain separate operations. */
export async function readClientProgress(http, actionSession, { id }, generation) {
  if (!uuid(id)) invalid()
  const { sessionGeneration } = await actionSession(generation)
  const value = await http.get(`/api/clients/${id}/progress`, { expectedGeneration: sessionGeneration })
  if (!keys(value, ['clientId', 'exercises']) || value.clientId !== id || !rows(value.exercises)) fail()
  const seen = new Set()
  for (const exercise of value.exercises) {
    if (!keys(exercise, ['id', 'name', 'points']) || !uuid(exercise.id) || typeof exercise.name !== 'string' || !rows(exercise.points) || !exercise.points.length) fail()
    for (const p of exercise.points) {
      if (!keys(p, ['id', 'sessionId', 'packageId', 'date', 'load', 'reps', 'sets']) || !uuid(p.id) || !uuid(p.sessionId) || !uuid(p.packageId) || !validSessionDate(p.date) || !load(p.load) || !integer(p.reps, 1, 1000) || !integer(p.sets, 1, 100) || seen.has(p.id)) fail()
      seen.add(p.id)
    }
  }
  if (seen.size > 2000) fail()
  return value.exercises
}
