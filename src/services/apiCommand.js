import { ApiError } from './apiClient.js'


// One uncertain command per rendered login. Reconciliation is a read;
// it never resubmits a command automatically after a transport failure.
export function reconciledCommand(http, actionSession, { path, receiptPath, validate, bodyFor = input => input, label, roles = ['owner', 'admin'], keyFor = () => crypto.randomUUID(), complete = () => true, definitiveRejection = error => error.status >= 400 && error.status < 500 }) {
  let pending = null
  const sessionFor = async expectedGeneration => {
    const { user, sessionGeneration } = await actionSession(expectedGeneration)
    if (!roles.includes(user.role)) throw new ApiError('forbidden', `${label} is unavailable for this account.`, 403)
    if (pending?.generation !== sessionGeneration) pending = null
    return sessionGeneration
  }
  const accept = (attempt, saved) => {
    if (!complete(saved)) throw new ApiError('SAVE_PENDING', `${label} is still being checked. Check the original request again.`)
    if (pending === attempt) pending = null
    return saved
  }
  const readReceipt = async (attempt, generation) => {
    try {
      const value = validate(await http.get(`${receiptPath}/${attempt.key}`, { expectedGeneration: generation }), attempt.body)
      return complete(value) ? { found: true, result: accept(attempt, value) } : { found: false }
    }
    catch (error) { if (error.code !== 'not_found') throw error; return { found: false } }
  }
  const command = async (input, expectedGeneration) => {
    const sessionGeneration = await sessionFor(expectedGeneration)
    const body = structuredClone(input)
    const fingerprint = JSON.stringify(body)
    if (pending && pending.fingerprint !== fingerprint) throw new ApiError('SAVE_UNCERTAIN', `Check the previous ${label.toLowerCase()} save with its original values before making another change.`)
    const attempt = pending ?? { fingerprint, body, key: keyFor(body), generation: sessionGeneration }
    if (pending) {
      const receipt = await readReceipt(attempt, sessionGeneration)
      if (receipt.found) return receipt.result
      // A serialized read found no final receipt. An explicit retry may resume
      // the same immutable command/key; a late arrival remains idempotent.
    }
    pending = attempt
    try { return accept(attempt, validate(await http.post(path(attempt.body), bodyFor(attempt.body), { csrf: true, idempotencyKey: attempt.key, expectedGeneration: sessionGeneration }), attempt.body)) }
    catch (error) {
      // A definitive rejection cannot have committed. Unknown outcomes retain the command.
      if (definitiveRejection(error) && pending === attempt) pending = null
      throw error
    }
  }
  // A profile reload can resolve a committed save without initiating another write.
  command.reconcile = async expectedGeneration => {
    const generation = await sessionFor(expectedGeneration)
    const attempt = pending
    if (!attempt) return null
    const receipt = await readReceipt(attempt, generation)
    return receipt.found ? { input: structuredClone(attempt.body), result: receipt.result } : null
  }
  command.pendingInput = generation => pending?.generation === generation ? structuredClone(pending.body) : null
  return command
}
