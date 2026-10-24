import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
const failure = () => { throw new ApiError('API_RESPONSE', 'The Undo could not be verified. Check the original request.') }

/** Route typed message actions and retain one original Undo across transport loss. */
export function messageUndoCommands(http, actionSession) {
  let busy = false
  const commands = Object.fromEntries([
    ['package_deletion', '/api/package-actions', '/api/package-undos', ['owner', 'admin']],
    ['session_change', '/api/session-changes', '/api/session-undos', ['owner', 'admin', 'trainer']],
  ].map(([kind, base, receipts, roles]) => [kind, {
    base,
    save: reconciledCommand(http, actionSession, {
      label: 'Session change Undo', roles,
      path: input => `${base}/${input.actionId}/undo`, receiptPath: receipts,
      bodyFor: input => ({ expected: input.expected }),
      validate(value, input) {
        if (!uuid(value?.id) || value.status !== 'undone' || !Number.isFinite(Date.parse(value.undoneAt))
          || kind === 'session_change' && value.actionId !== input.actionId) failure()
        return value
      },
    }),
  }]))
  return async (input, generation) => {
    if (busy) throw new ApiError('SAVE_PENDING', 'The original Undo is still running.')
    busy = true
    try {
      const current = await actionSession(generation)
      if (!uuid(input?.id)) throw new ApiError('INVALID_REQUEST', 'Choose a message to undo.', 422)
      for (const { save } of Object.values(commands)) {
        const pending = save.pendingInput(current.sessionGeneration)
        if (!pending) continue
        if (pending.id !== input.id) throw new ApiError('SAVE_UNCERTAIN', 'Check the original Undo first.')
        const recovered = await save.reconcile(generation)
        if (!recovered) throw new ApiError('SAVE_UNCERTAIN', 'The original Undo is not confirmed yet. Check again.')
        return recovered.result
      }
      const messages = await http.get('/api/messages', { expectedGeneration: generation })
      if (!Array.isArray(messages)) failure()
      const message = messages.find(row => row.id === input.id)
      const command = commands[message?.undo?.kind]
      if (!command || !uuid(message.undo.id)) throw new ApiError('OPERATION_UNAVAILABLE', 'Undo is unavailable for this message.')
      if (message.undo.kind === 'package_deletion' && !['owner', 'admin'].includes(current.user.role)) throw new ApiError('forbidden', 'Package deletion Undo is unavailable.', 403)
      const review = await http.get(`${command.base}/${message.undo.id}/undo-review`, { expectedGeneration: generation })
      if (review.id !== message.undo.id || review.messageId !== input.id || !digest(review.expected)) failure()
      return await command.save({ id: input.id, actionId: review.id, expected: review.expected }, generation)
    } finally { busy = false }
  }
}
