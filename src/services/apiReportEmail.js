import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const invalid = () => { throw new ApiError('API_RESPONSE', 'The email request could not be verified. Check the original request.') }

/** Preserve one original email intent; server content deduplication also survives a fresh login. */
export function reportEmailCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Report email', roles: ['owner', 'admin', 'trainer'],
    path: () => '/api/report-email', receiptPath: '/api/report-email',
    validate(value) {
      if (!value || Object.keys(value).length !== 2 || !uuid(value.requestId) || !Number.isInteger(value.queued) || value.queued < 1 || value.queued > 2) invalid()
      return value
    },
  })
  const original = (selection, generation) => {
    const input = command.pendingInput(generation)
    if (!input) throw new ApiError('INVALID_REQUEST', 'There is no original email to check.')
    if (['kind', 'targetId', 'purchaseId', 'includeSummary'].some(key => input[key] !== selection[key]) || JSON.stringify(input.videoIds) !== JSON.stringify(selection.videoIds)) {
      throw new ApiError('SAVE_PENDING', 'Return to the original report to check its email request.')
    }
    return input
  }
  return {
    async review(selection, generation) {
      const { sessionGeneration } = await actionSession(generation)
      if (command.pendingInput(sessionGeneration)) throw new ApiError('SAVE_UNCERTAIN', 'Check the original email before preparing another.')
      const result = await http.post('/api/report-email/review', selection, { csrf: true, idempotencyKey: crypto.randomUUID(), expectedGeneration: sessionGeneration })
      if (!result || Object.keys(result).length !== 2 || !/^[0-9a-f]{64}$/.test(result.expected) || !Array.isArray(result.recipients) || result.recipients.length < 1 || result.recipients.length > 2 || result.recipients.some(row => typeof row.name !== 'string' || !row.name || typeof row.email !== 'string' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(row.email))) invalid()
      return result
    },
    send: command,
    async recover(selection, generation) {
      original(selection, generation)
      const result = await command.reconcile(generation)
      if (!result) throw new ApiError('SAVE_UNCERTAIN', 'The original email is not confirmed. Retry the original request.')
      return result.result
    },
    async retry(selection, generation) {
      const input = original(selection, generation)
      return command(input, generation)
    },
  }
}
