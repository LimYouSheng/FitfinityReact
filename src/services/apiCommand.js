import { ApiError } from './apiClient.js'


// One uncertain command per rendered login. Reconciliation is a read;
// it never resubmits a command automatically after a transport failure.
export function reconciledCommand(http, actionSession, { path, receiptPath, validate, bodyFor = input => input, label }) {
  let pending = null
  return async (input, expectedGeneration) => {
    const { user, sessionGeneration } = await actionSession(expectedGeneration)
    if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', `${label} requires operational access.`, 403)
    if (pending?.generation !== sessionGeneration) pending = null
    const body = structuredClone(input)
    const fingerprint = JSON.stringify(body)
    if (pending && pending.fingerprint !== fingerprint) throw new ApiError('SAVE_UNCERTAIN', `Check the previous ${label.toLowerCase()} save with its original values before making another change.`)
    const attempt = pending ?? { fingerprint, body, key: crypto.randomUUID(), generation: sessionGeneration }
    const accept = value => {
      const saved = validate(value, attempt.body)
      if (pending === attempt) pending = null
      return saved
    }
    if (pending) {
      try { return accept(await http.get(`${receiptPath}/${attempt.key}`, { expectedGeneration: sessionGeneration })) }
      catch (error) { if (error.code !== 'not_found') throw error }
      // A serialized read proved no committed receipt. An explicit retry may now
      // send the same immutable command/key; a late arrival remains idempotent.
    }
    pending = attempt
    try { return accept(await http.post(path(attempt.body), bodyFor(attempt.body), { csrf: true, idempotencyKey: attempt.key, expectedGeneration: sessionGeneration })) }
    catch (error) {
      // A definitive rejection cannot have committed. Unknown outcomes retain the command.
      if (error.status >= 400 && error.status < 500 && pending === attempt) pending = null
      throw error
    }
  }
}
