import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const version = value => Number.isSafeInteger(value) && value > 0
const keys = (value, allowed) => value && Object.keys(value).every(key => allowed.includes(key))
const date = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
const time = value => typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)
const optionalError = value => value === null || typeof value === 'string' && value.trim().length > 0
export function validReactivationReview(value) {
  return keys(value, ['id', 'version', 'name', 'expected', 'purchaseIds', 'rows', 'packageError']) && uuid(value.id) && version(value.version)
    && typeof value.name === 'string' && value.name.trim() && typeof value.expected === 'string' && /^[0-9a-f]{64}$/.test(value.expected) && optionalError(value.packageError)
    && Array.isArray(value.purchaseIds) && value.purchaseIds.length <= 2000 && value.purchaseIds.every(uuid) && new Set(value.purchaseIds).size === value.purchaseIds.length
    && Array.isArray(value.rows) && value.rows.length <= 2000 && new Set(value.rows.map(r => r?.id)).size === value.rows.length
    && value.rows.every(r => keys(r, ['id', 'version', 'purchaseId', 'trainerId', 'trainerName', 'originalDate', 'date', 'startsAt', 'endsAt', 'locked', 'error'])
      && uuid(r.id) && version(r.version) && uuid(r.purchaseId) && uuid(r.trainerId) && typeof r.trainerName === 'string' && r.trainerName.trim()
      && date(r.originalDate) && date(r.date) && time(r.startsAt) && time(r.endsAt) && r.startsAt < r.endsAt && typeof r.locked === 'boolean' && optionalError(r.error))
}
export function clientReactivationCommands(http, actionSession) {
  const validate = (value, input) => {
    if (!validReactivationReview(value) || value.id !== input.id || value.version !== input.reviewed.version || value.expected !== input.reviewed.expected
      || value.rows.length !== input.reviewed.rows.length || value.rows.some(row => {
        const before = input.reviewed.rows.find(r => r.id === row.id)
        return !before || row.date !== (input.dates[row.id] ?? before.originalDate) || ['version', 'purchaseId', 'trainerId', 'trainerName', 'originalDate', 'startsAt', 'endsAt', 'locked'].some(key => row[key] !== before[key])
      }) || JSON.stringify(value.purchaseIds) !== JSON.stringify(input.reviewed.purchaseIds)) throw new ApiError('API_RESPONSE', 'The retained calendar could not be verified.')
    return value
  }
  const save = reconciledCommand(http, actionSession, {
    label: 'Client reactivation', path: input => `/api/clients/${input.id}/reactivation`, receiptPath: '/api/client-reactivations',
    bodyFor: ({ reviewed, dates }) => ({ expected: reviewed.expected, dates }),
    validate(value, input) {
      if (!keys(value, ['id', 'version', 'status']) || value.id !== input.id || value.version !== input.reviewed.version + 1 || value.status !== 'active') throw new ApiError('API_RESPONSE', 'The reactivation could not be verified. Check the original request again.')
      return value
    },
  })
  const sessionFor = async generation => {
    const session = await actionSession(generation)
    if (!['owner', 'admin'].includes(session.user.role)) throw new ApiError('forbidden', 'Client reactivation is unavailable for this account.', 403)
    return session.sessionGeneration
  }
  const inputFor = input => {
    if (!validReactivationReview(input.reviewed) || input.reviewed.id !== input.id || !input.dates || Array.isArray(input.dates) || typeof input.dates !== 'object'
      || Object.entries(input.dates).some(([id, day]) => !input.reviewed.rows.some(r => r.id === id) || !date(day))) throw new ApiError('INVALID_REQUEST', 'Review the client and retained calendar before reactivating.')
    return input
  }
  return {
    async review({ id, expectedVersion }, generation) {
      const current = await sessionFor(generation)
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload the client before reactivating.')
      const pending = save.pendingInput(current)
      if (pending) {
        if (pending.id !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous client reactivation before starting another.')
        return { reviewed: pending.reviewed, dates: pending.dates, uncertain: true }
      }
      const reviewed = await http.get(`/api/clients/${id}/reactivation-review`, { expectedGeneration: current })
      if (!validReactivationReview(reviewed) || reviewed.id !== id) throw new ApiError('API_RESPONSE', 'The retained calendar could not be verified.')
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This client changed. Reload before reactivating.', 409)
      return { reviewed, dates: {}, uncertain: false }
    },
    async preview(input, generation) {
      inputFor(input)
      const current = await sessionFor(generation)
      if (save.pendingInput(current)) throw new ApiError('SAVE_UNCERTAIN', 'Check the original reactivation before editing dates.')
      return validate(await http.post(`/api/clients/${input.id}/reactivation-review`, { expected: input.reviewed.expected, dates: input.dates }, { csrf: true, idempotencyKey: crypto.randomUUID(), expectedGeneration: current }), input)
    },
    save: (input, generation) => save(inputFor(input), generation),
    async recover(generation) {
      if (save.pendingInput(generation)) await save.reconcile(generation)
      return save.pendingInput(generation)
    },
  }
}
