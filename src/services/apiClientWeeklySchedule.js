import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { DAYS } from '../app/constants.js'
import { validSessionDate } from '../app/sessionRules.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const version = v => Number.isSafeInteger(v) && v > 0
const keys = (v, allowed) => v && Object.keys(v).every(k => allowed.includes(k))
const time = v => typeof v === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(v)
const rows = v => Array.isArray(v) && v.length <= 2000 && new Set(v.map(s => s?.id)).size === v.length
const fail = () => { throw new ApiError('API_RESPONSE', 'The weekly schedule could not be verified. Check the original request again.') }
export const weeklySlots = reviewed => reviewed.slots.map(s => ({ id: s.id, day: DAYS[s.weekday], from: s.startsAt, to: s.endsAt }))
export function validWeeklyReview(v) {
  return keys(v, ['id', 'version', 'name', 'purchaseId', 'purchaseVersion', 'trainerId', 'trainerVersion', 'outcome', 'expected', 'slots', 'sessions'])
    && uuid(v.id) && version(v.version) && typeof v.name === 'string' && uuid(v.purchaseId) && version(v.purchaseVersion) && uuid(v.trainerId) && version(v.trainerVersion)
    && ['applied', 'requested'].includes(v.outcome) && /^[0-9a-f]{64}$/.test(v.expected)
    && rows(v.slots) && v.slots.length > 0 && v.slots.length <= 7 && new Set(v.slots.map(s => s.weekday)).size === v.slots.length
    && v.slots.every(s => keys(s, ['id', 'weekday', 'startsAt', 'endsAt']) && uuid(s.id) && Number.isInteger(s.weekday) && s.weekday >= 0 && s.weekday < 7 && time(s.startsAt) && time(s.endsAt) && s.startsAt < s.endsAt)
    && rows(v.sessions) && v.sessions.every(s => keys(s, ['id', 'version', 'trainerId', 'date', 'startsAt', 'endsAt', 'slotId']) && uuid(s.id) && version(s.version) && uuid(s.trainerId) && validSessionDate(s.date) && time(s.startsAt) && time(s.endsAt) && s.startsAt < s.endsAt && (s.slotId === null || uuid(s.slotId)))
}
const validInput = input => validWeeklyReview(input?.reviewed) && input.id === input.reviewed.id && rows(input.slots)
  && input.slots.length === input.reviewed.slots.length && input.slots.every(s => keys(s, ['id', 'day', 'from', 'to']) && input.reviewed.slots.some(old => old.id === s.id && DAYS[old.weekday] === s.day) && time(s.from) && time(s.to) && s.from < s.to)
const bodyFor = ({ reviewed, slots }) => ({ expected: reviewed.expected, slots: slots.map(s => ({ id: s.id, weekday: DAYS.indexOf(s.day), startsAt: s.from, endsAt: s.to })) })
export function clientWeeklyScheduleCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Weekly schedule', roles: ['owner', 'admin', 'trainer'], path: input => `/api/clients/${input.id}/weekly-schedule`, receiptPath: '/api/client-weekly-schedules', bodyFor,
    validate(value, input) {
      if (!keys(value, ['outcome', 'client', 'requestId', 'updatedSessions']) || !keys(value.client, ['id', 'version']) || value.client.id !== input.id
        || value.outcome !== input.reviewed.outcome || value.client.version !== input.reviewed.version + (value.outcome === 'applied' ? 1 : 0)
        || !Number.isSafeInteger(value.updatedSessions) || value.updatedSessions < 0 || value.updatedSessions > input.reviewed.sessions.length
        || (value.outcome === 'requested' ? !uuid(value.requestId) || value.updatedSessions !== 0 : value.requestId !== null)) fail()
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload the client before changing weekly times.')
      const { sessionGeneration } = await actionSession(generation), pending = save.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.id !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous weekly schedule first.')
        return { reviewed: pending.reviewed, slots: pending.slots, uncertain: true }
      }
      const reviewed = await http.get(`/api/clients/${id}/weekly-schedule-review`, { expectedGeneration: sessionGeneration })
      if (!validWeeklyReview(reviewed) || reviewed.id !== id) fail()
      if (reviewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This client changed. Reload before editing weekly times.', 409)
      return { reviewed, slots: weeklySlots(reviewed), uncertain: false }
    },
    async preview(input, generation) {
      if (!validInput(input)) throw new ApiError('INVALID_REQUEST', 'Keep the reviewed weekly days and valid times.')
      const { sessionGeneration } = await actionSession(generation)
      if (save.pendingInput(sessionGeneration)) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous weekly schedule first.')
      const value = await http.post(`/api/clients/${input.id}/weekly-schedule-review`, bodyFor(input), { csrf: true, idempotencyKey: crypto.randomUUID(), expectedGeneration: sessionGeneration })
      if (!keys(value, ['expected', 'outcome', 'updatedSessions']) || value.expected !== input.reviewed.expected || value.outcome !== input.reviewed.outcome || !Number.isSafeInteger(value.updatedSessions) || value.updatedSessions < 0 || value.updatedSessions > input.reviewed.sessions.length) fail()
      return value
    },
    async save(input, generation) {
      if (!validInput(input)) throw new ApiError('INVALID_REQUEST', 'Review the original weekly times before saving.')
      return save(input, generation)
    },
    async reconcile(generation) {
      if (!save.pendingInput(generation)) return null
      await save.reconcile(generation)
      return save.pendingInput(generation)
    },
  }
}
