import { ApiError } from './apiClient.js'
import { exerciseMediaError } from '../app/exerciseCatalog.js'
import { fileDigest, getLibraryMedia, putLibraryMedia } from './apiLibraryMedia.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const stamp = value => typeof value === 'string' && Number.isFinite(Date.parse(value))
const fail = () => { throw new ApiError('API_RESPONSE', 'The exercise save could not be verified. Check the original save.') }
const base = '/api/exercise-library'
const normalized = value => String(value ?? '').trim().replace(/\s+/g, ' ')

export function libraryExercise(value) {
  if (!value || Object.keys(value).length !== 9 || !uuid(value.id) || !Number.isSafeInteger(value.version) || value.version < 1 || typeof value.name !== 'string' || !value.name || typeof value.category !== 'string' || typeof value.description !== 'string' || !['active', 'inactive'].includes(value.status) || !stamp(value.createdAt) || !stamp(value.updatedAt)) fail()
  const media = value.media
  if (media !== null && (!media || Object.keys(media).length !== 4 || !uuid(media.id) || typeof media.name !== 'string' || typeof media.type !== 'string' || !Number.isSafeInteger(media.size) || media.size < 1 || media.size > 50 * 1024 * 1024)) fail()
  return structuredClone(value)
}

/** One original file/command per login; recovery reads never repeat an upload or commit. */
export function exerciseLibraryCommands(http, actionSession, fetchImpl = globalThis.fetch) {
  let pending = null, starting = false
  const assertCurrent = generation => { if (http.generation() !== generation) throw new ApiError('SESSION_CHANGED', 'Your sign-in changed. Reload before continuing.') }
  const sessionFor = async generation => {
    const session = await actionSession(generation)
    if (pending?.generation !== session.sessionGeneration) pending = null
    return session
  }
  const accept = (attempt, value) => {
    const saved = libraryExercise(value), body = attempt.body
    if ((body.id && saved.id !== body.id) || saved.version !== (body.expectedVersion ?? 0) + 1 || saved.name !== body.name || saved.category !== body.category || saved.description !== body.description || saved.status !== body.status || (body.removeMedia && saved.media !== null) || (body.upload && (!saved.media || saved.media.name !== body.upload.name || saved.media.type !== body.upload.type || saved.media.size !== body.upload.size))) fail()
    if (pending === attempt) pending = null
    return saved
  }
  const inspect = async attempt => {
    try {
      const viewed = await http.get(`${base}/save-intents/${attempt.key}`, { expectedGeneration: attempt.generation })
      if (!viewed || Object.keys(viewed).length !== 4 || viewed.key !== attempt.key || !['pending', 'completed', 'expired'].includes(viewed.state) || !stamp(viewed.uploadUntil) || (viewed.state === 'completed') !== (viewed.result !== null)) fail()
      if (viewed.state === 'expired') { if (pending === attempt) pending = null; throw new ApiError('SAVE_EXPIRED', 'The original upload expired. Review a new exercise save.', 409) }
      return viewed.state === 'completed' ? accept(attempt, viewed.result) : null
    } catch (error) {
      if (['APPROVAL_PENDING', 'approval_closed'].includes(error.code) && pending === attempt) pending = null
      if (error.code === 'not_found') return null
      throw error
    }
  }
  const optionsFor = attempt => ({ csrf: true, expectedGeneration: attempt.generation, idempotencyKey: attempt.key })
  const commands = {
    async catalogue(generation) {
      await sessionFor(generation)
      const value = await http.get(base, { expectedGeneration: generation })
      if (!Array.isArray(value?.items) || !Array.isArray(value.categories) || value.categories.some(v => typeof v !== 'string')) fail()
      const items = value.items.map(libraryExercise)
      if (new Set(items.map(v => v.id)).size !== items.length) fail()
      return { items, categories: value.categories }
    },
    async save(input, generation) {
      if (starting || pending?.inFlight) throw new ApiError('SAVE_PENDING', 'The exercise save is still running.')
      starting = true
      let attempt
      try {
        const { user, sessionGeneration } = await sessionFor(generation)
        if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Operational access is required.', 403)
        const file = input.mediaFile ?? null
        if (file && (!(file instanceof Blob) || exerciseMediaError(file))) throw new ApiError('INVALID_REQUEST', 'Choose a supported non-empty attachment up to 50 MB.')
        const body = { id: input.id ?? null, expectedVersion: input.expectedVersion ?? null,
          name: normalized(input.draft?.name), category: input.draft?.category, description: String(input.draft?.description ?? '').trim(), status: input.draft?.status,
          removeMedia: input.removeMedia === true, upload: file ? { name: file.name || 'Exercise media', type: file.type, size: file.size, sha256: await fileDigest(file) } : null }
        assertCurrent(sessionGeneration)
        const fingerprint = JSON.stringify(body)
        if (pending && pending.fingerprint !== fingerprint) throw new ApiError('SAVE_UNCERTAIN', 'Check the original exercise save before changing its values.')
        attempt = pending ?? { key: crypto.randomUUID(), body, file, input: structuredClone(input), fingerprint, generation: sessionGeneration }
        const resumed = Boolean(pending)
        pending = attempt; attempt.inFlight = true
        if (resumed) {
          const saved = await inspect(attempt)
          if (saved) return saved
        }
        await http.post(`${base}/save-intents`, attempt.body, optionsFor(attempt))
        if (resumed) {
          try { return accept(attempt, await http.post(`${base}/save-intents/${attempt.key}/commit`, {}, optionsFor(attempt))) }
          catch (error) { if (error.code !== 'MEDIA_MISSING') throw error }
        }
        if (attempt.file) {
          const lease = await http.post(`${base}/save-intents/${attempt.key}/upload`, {}, optionsFor(attempt))
          await putLibraryMedia(fetchImpl, lease, attempt.file, attempt.body.upload.sha256, () => assertCurrent(sessionGeneration))
        }
        return accept(attempt, await http.post(`${base}/save-intents/${attempt.key}/commit`, {}, optionsFor(attempt)))
      } catch (error) {
        if (error.status >= 400 && error.status < 500 && error.code !== 'MEDIA_MISSING' && pending === attempt) pending = null
        throw error
      } finally { starting = false; if (attempt) attempt.inFlight = false }
    },
    async recover(generation) {
      await sessionFor(generation)
      return pending && !pending.inFlight ? inspect(pending) : null
    },
    pendingInput(generation) { return pending?.generation === generation && !pending.inFlight ? structuredClone(pending.input) : null },
    async loadMedia({ id }, generation) {
      if (!uuid(id)) fail()
      await sessionFor(generation)
      return getLibraryMedia(http, fetchImpl, id, generation, () => assertCurrent(generation))
    },
  }
  return commands
}
