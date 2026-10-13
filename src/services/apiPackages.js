import { ApiError } from './apiClient.js'
import { directoryPackage } from './apiDirectory.js'

// One uncertain catalogue command per rendered login. Reconciliation is a read;
// it never resubmits a command automatically after a transport failure.
export function packageCommands(http, actionSession) {
  let pending = null
  return async (input, expectedGeneration) => {
    const { user, sessionGeneration } = await actionSession(expectedGeneration)
    if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Package setup requires operational access.', 403)
    if (pending?.generation !== sessionGeneration) pending = null
    const body = structuredClone(input)
    const fingerprint = JSON.stringify(body)
    if (pending && pending.fingerprint !== fingerprint) throw new ApiError('SAVE_UNCERTAIN', 'Check the previous package save with its original values before making another change.')
    const attempt = pending ?? { fingerprint, body, key: crypto.randomUUID(), generation: sessionGeneration }
    const accept = value => {
      const saved = directoryPackage(value)
      if (saved.version !== (input.id ? input.expectedVersion + 1 : 1) || (input.id && saved.id !== input.id) || saved.name !== input.draft.name.trim() || saved.total !== input.draft.total || saved.status !== input.draft.status) throw new ApiError('API_RESPONSE', 'The package save could not be verified. Check the same save again.')
      if (pending === attempt) pending = null
      return saved
    }
    if (pending) {
      try { return accept(await http.get(`/api/packages/saves/${attempt.key}`, { expectedGeneration: sessionGeneration })) }
      catch (error) { if (error.code !== 'not_found') throw error }
      // A serialized read proved no committed receipt. An explicit retry may now
      // send the same immutable command/key; a late arrival remains idempotent.
    }
    pending = attempt
    try { return accept(await http.post('/api/packages', attempt.body, { csrf: true, idempotencyKey: attempt.key, expectedGeneration: sessionGeneration })) }
    catch (error) {
      // A definitive rejection cannot have committed. Unknown outcomes retain the command.
      if (error.status >= 400 && error.status < 500 && pending === attempt) pending = null
      throw error
    }
  }
}
