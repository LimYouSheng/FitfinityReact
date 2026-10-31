import { MAX_EXERCISE_VIDEO_BYTES } from '../app/video.js'
import { ApiError } from './apiClient.js'
import { fileDigest, getProtectedMedia, putLibraryMedia } from './apiLibraryMedia.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const stamp = value => typeof value === 'string' && Number.isFinite(Date.parse(value))
const positive = value => Number.isSafeInteger(value) && value > 0
const hash = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
const fail = () => { throw new ApiError('API_RESPONSE', 'The recording could not be verified. Check the original save.') }
const base = '/api/session-media'
const path = input => `/api/sessions/${input.sessionId}/exercises/${input.exerciseId}/video`
const validTarget = input => uuid(input?.sessionId) && uuid(input.exerciseId)
const mediaValid = value => value === null || value && uuid(value.id) && typeof value.name === 'string' && ['video/mp4', 'video/webm', 'video/quicktime'].includes(value.type) && positive(value.size) && value.size <= MAX_EXERCISE_VIDEO_BYTES && stamp(value.attachedAt) && stamp(value.expiresAt) && Date.parse(value.expiresAt) > Date.parse(value.attachedAt)
const reviewValid = value => validTarget(value) && positive(value.version) && hash(value.expected) && mediaValid(value.media)

/** Retain one original reviewed recording command and file across ambiguous responses. */
export function sessionMediaCommands(http, actionSession, fetchImpl = globalThis.fetch) {
  let pending = null, starting = false
  const assertCurrent = generation => { if (http.generation() !== generation) throw new ApiError('SESSION_CHANGED', 'Your sign-in changed. Reload before continuing.') }
  const current = async generation => {
    const session = await actionSession(generation)
    if (pending?.generation !== session.sessionGeneration) pending = null
    return session
  }
  const options = attempt => ({ csrf: true, expectedGeneration: attempt.generation, idempotencyKey: attempt.key })
  const accept = (attempt, value) => {
    if (!value || value.sessionId !== attempt.body.sessionId || value.exerciseId !== attempt.body.exerciseId || !positive(value.version) || value.version <= attempt.input.reviewed.version || !stamp(value.savedAt) || !mediaValid(value.media)) fail()
    if (attempt.body.remove ? value.media !== null : !value.media || value.media.name !== attempt.body.upload.name || value.media.type !== attempt.body.upload.type || value.media.size !== attempt.body.upload.size) fail()
    if (pending === attempt) pending = null
    return value
  }
  const inspect = async attempt => {
    try {
      const value = await http.get(`${base}/intents/${attempt.key}`, { expectedGeneration: attempt.generation })
      if (!value || value.key !== attempt.key || !['pending', 'completed', 'expired'].includes(value.state) || !stamp(value.uploadUntil) || (value.state === 'completed') !== (value.result !== null)) fail()
      if (value.state === 'expired') { pending = null; throw new ApiError('SAVE_EXPIRED', 'The original recording save expired. Review a new save.', 409) }
      return value.state === 'completed' ? accept(attempt, value.result) : null
    } catch (error) { if (error.code === 'not_found') return null; throw error }
  }
  const commands = {
    async review(input, generation) {
      if (!validTarget(input) || !positive(input.expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload this session before managing its recording.', 422)
      await current(generation)
      if (pending) {
        if (pending.body.sessionId !== input.sessionId || pending.body.exerciseId !== input.exerciseId) throw new ApiError('SAVE_UNCERTAIN', 'Check the original recording before editing another.')
        return { reviewed: pending.input.reviewed, uncertain: true, remove: pending.body.remove }
      }
      const viewed = await http.get(`${path(input)}/review`, { expectedGeneration: generation })
      if (!reviewValid(viewed) || viewed.sessionId !== input.sessionId || viewed.exerciseId !== input.exerciseId) fail()
      if (viewed.version !== input.expectedVersion) throw new ApiError('VERSION_CONFLICT', 'This session changed. Reload before managing its recording.', 409)
      return { reviewed: viewed, uncertain: false, remove: false }
    },
    async save(input, generation, remove = false) {
      if (starting || pending?.inFlight) throw new ApiError('SAVE_PENDING', 'The original recording save is still running.')
      if (!validTarget(input) || !reviewValid(input.reviewed) || input.reviewed.sessionId !== input.sessionId || input.reviewed.exerciseId !== input.exerciseId) throw new ApiError('INVALID_REQUEST', 'Review this recording before saving.', 422)
      starting = true
      let attempt
      try {
        await current(generation)
        if (pending) {
          if (pending.body.sessionId !== input.sessionId || pending.body.exerciseId !== input.exerciseId) throw new ApiError('SAVE_UNCERTAIN', 'Check the original recording first.')
          throw new ApiError('SAVE_UNCERTAIN', 'Check the original recording before submitting another save.')
        }
        const supplied = remove ? null : input.file
        // MediaRecorder may add codec parameters; sign the canonical container MIME type
        // while preserving the exact bytes for independent server verification.
        const type = supplied instanceof Blob ? supplied.type.split(';', 1)[0].trim() : ''
        const file = supplied instanceof Blob ? supplied.slice(0, supplied.size, type) : supplied
        if (!remove && (!(file instanceof Blob) || !file.size || file.size > MAX_EXERCISE_VIDEO_BYTES || !['video/mp4', 'video/webm', 'video/quicktime'].includes(file.type))) throw new ApiError('INVALID_REQUEST', 'Choose a supported non-empty video up to 10 MB.', 422)
        const metadata = input.metadata ?? {}
        const body = { sessionId: input.sessionId, exerciseId: input.exerciseId, expected: input.reviewed.expected, remove,
          upload: file ? { name: metadata.name || supplied.name || 'Training video', type: file.type, size: file.size, sha256: await fileDigest(file) } : null,
          duration: metadata.duration ?? null, source: metadata.source ?? 'attached', caption: metadata.caption ?? '',
          processingStatus: metadata.processingStatus ?? 'deferred', audioIncluded: metadata.audioIncluded ?? null }
        assertCurrent(generation)
        attempt = { key: crypto.randomUUID(), body, file, input: { sessionId: input.sessionId, exerciseId: input.exerciseId, reviewed: structuredClone(input.reviewed) }, generation, inFlight: true }
        pending = attempt
        await http.post(`${base}/intents`, body, options(attempt))
        if (file) {
          const lease = await http.post(`${base}/intents/${attempt.key}/upload`, {}, options(attempt))
          await putLibraryMedia(fetchImpl, lease, file, body.upload.sha256, () => assertCurrent(generation))
        }
        return accept(attempt, await http.post(`${base}/intents/${attempt.key}/commit`, {}, options(attempt)))
      } catch (error) {
        if (attempt && error.status >= 400 && error.status < 500 && error.code !== 'MEDIA_MISSING' && pending === attempt) pending = null
        throw error
      } finally { starting = false; if (attempt) attempt.inFlight = false }
    },
    async recover(input, generation) {
      await current(generation)
      if (!pending || pending.body.sessionId !== input.sessionId || pending.body.exerciseId !== input.exerciseId) return null
      if (pending.inFlight) throw new ApiError('SAVE_PENDING', 'The original recording save is still running.')
      return inspect(pending)
    },
    async resume(input, generation) {
      await current(generation)
      const attempt = pending
      if (!attempt || attempt.inFlight || attempt.body.sessionId !== input.sessionId || attempt.body.exerciseId !== input.exerciseId) throw new ApiError('SAVE_PENDING', 'Check the original recording save.')
      attempt.inFlight = true
      try {
        const saved = await inspect(attempt)
        if (saved) return saved
        await http.post(`${base}/intents`, attempt.body, options(attempt))
        try { return accept(attempt, await http.post(`${base}/intents/${attempt.key}/commit`, {}, options(attempt))) }
        catch (error) { if (error.code !== 'MEDIA_MISSING' || !attempt.file) throw error }
        const lease = await http.post(`${base}/intents/${attempt.key}/upload`, {}, options(attempt))
        await putLibraryMedia(fetchImpl, lease, attempt.file, attempt.body.upload.sha256, () => assertCurrent(generation))
        return accept(attempt, await http.post(`${base}/intents/${attempt.key}/commit`, {}, options(attempt)))
      } catch (error) {
        if (error.status >= 400 && error.status < 500 && error.code !== 'MEDIA_MISSING' && pending === attempt) pending = null
        throw error
      } finally { attempt.inFlight = false }
    },
    async load(input, generation) {
      if (!validTarget(input)) throw new ApiError('INVALID_REQUEST', 'Choose a session recording.', 422)
      await current(generation)
      return getProtectedMedia(http, fetchImpl, path(input), generation, () => assertCurrent(generation), MAX_EXERCISE_VIDEO_BYTES, true)
    },
  }
  return commands
}
