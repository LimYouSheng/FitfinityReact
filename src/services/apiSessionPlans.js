import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'
import { validPlanItem } from './apiSessionReads.js'
import { normalizeExercisePlan } from '../app/sessionRules.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const fail = () => { throw new ApiError('API_RESPONSE', 'The exercise plan could not be verified. Check the original save.') }
const itemsValid = v => Array.isArray(v) && v.length <= 2000 && v.every(validPlanItem) && new Set(v.map(p => p.id)).size === v.length
const validReview = v => v && Object.keys(v).length === 4 && uuid(v.sessionId) && Number.isSafeInteger(v.version) && v.version > 0 && /^[0-9a-f]{64}$/.test(v.expected) && itemsValid(v.items)
const writable = items => normalizeExercisePlan(items).map(({ id, name, weight, reps, rounds, rest, customDetails }) => ({ id, name, weight, reps, rounds, rest, customDetails }))

/** Keep the exact reviewed plan frozen until a lost-response save is reconciled. */
export function sessionPlanCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Exercise plan', roles: ['owner', 'admin', 'trainer'], path: v => `/api/sessions/${v.sessionId}/plan`, receiptPath: '/api/session-plans',
    bodyFor: v => ({ expected: v.reviewed.expected, items: v.items }),
    validate(value, input) {
      if (!value || Object.keys(value).length !== 4 || value.sessionId !== input.sessionId || !Number.isSafeInteger(value.version) || value.version <= input.reviewed.version || !itemsValid(value.items) || value.items.length !== input.items.length || typeof value.savedAt !== 'string' || !Number.isFinite(Date.parse(value.savedAt))) fail()
      for (const [index, saved] of value.items.entries()) {
        const requested = input.items[index]
        if (uuid(requested.id) && saved.id !== requested.id) fail()
        if (['name', 'weight', 'reps', 'rounds', 'rest'].some(k => saved[k] !== requested[k]) || JSON.stringify(saved.customDetails) !== JSON.stringify(requested.customDetails)) fail()
      }
      return value
    },
  })
  return {
    async review({ id, expectedVersion }, generation) {
      if (!uuid(id) || !Number.isSafeInteger(expectedVersion) || expectedVersion < 1) throw new ApiError('INVALID_REQUEST', 'Reload this session before editing its plan.')
      const { sessionGeneration } = await actionSession(generation)
      const pending = command.pendingInput(sessionGeneration)
      if (pending) {
        if (pending.sessionId !== id) throw new ApiError('SAVE_UNCERTAIN', 'Check the original plan before editing another.')
        return { reviewed: pending.reviewed, draft: pending.items, uncertain: true }
      }
      const viewed = await http.get(`/api/sessions/${id}/plan-review`, { expectedGeneration: sessionGeneration })
      if (!validReview(viewed) || viewed.sessionId !== id) fail()
      if (viewed.version !== expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This session changed. Reload before editing its plan.', 409)
      return { reviewed: viewed, draft: viewed.items, uncertain: false }
    },
    async save(input, generation) {
      if (!validReview(input?.reviewed) || input.sessionId !== input.reviewed.sessionId || !Array.isArray(input.items)) throw new ApiError('INVALID_REQUEST', 'Review the exercise plan before saving.')
      return command({ ...input, items: writable(input.items) }, generation)
    },
    pendingInput: command.pendingInput,
  }
}
