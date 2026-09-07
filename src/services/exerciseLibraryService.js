import { delay, mockDb } from './mockDb.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { exerciseCatalog, exerciseDraftErrors, exerciseMediaError } from '../app/exerciseCatalog.js'
import { appendSavedEditMessage } from './editMessage.js'
import { exerciseLibraryMedia } from './exerciseLibraryMedia.js'

// Local record IDs also need to work during HTTP device previews.
function libraryId(prefix) {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return `${prefix}-${Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')}`
}

function validateSave(db, options, actor) {
  const owner = requireActiveActor(db, actor)
  if (owner.role !== 'owner') throw new Error('Only the owner can manage the exercise library.')
  const catalog = exerciseCatalog(db)
  const current = options.id ? catalog.find(item => item.id === options.id) : null
  if (options.id && !current) throw new Error('Exercise not found.')
  if (current && current.version !== options.expectedVersion) throw new Error('This exercise changed. Refresh the page before editing again.')
  const errors = exerciseDraftErrors(options.draft, catalog, options.id)
  if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
  if (options.mediaFile) {
    if (!(options.mediaFile instanceof Blob)) throw new Error('Choose a valid media file.')
    const error = exerciseMediaError(options.mediaFile)
    if (error) throw new Error(error)
  }
  return { current, catalog }
}

export const exerciseLibraryService = {
  getAll(actor) {
    const db = mockDb.read(), user = requireActiveActor(db, actor)
    return structuredClone(exerciseCatalog(db).filter(item => user.role === 'owner' || item.status === 'active'))
  },
  async save(options, actor) {
    await delay(100)
    validateSave(mockDb.read(), options, actor)
    const id = options.id || libraryId('library')
    let newMediaId = null, previousMediaId = null, saved
    try {
      if (options.mediaFile) {
        newMediaId = libraryId('library-media')
        await exerciseLibraryMedia.save(newMediaId, options.mediaFile)
      }
      mockDb.mutate(db => {
        const { current, catalog } = validateSave(db, options, actor)
        previousMediaId = current?.media?.id ?? null
        const stamp = new Date().toISOString()
        const { name, category, description, status } = options.draft
        saved = { id, name: name.trim().replace(/\s+/g, ' '), category, description: (description ?? '').trim(), status,
          createdAt: current?.createdAt ?? stamp, updatedAt: stamp, version: (current?.version ?? 0) + 1,
          media: options.mediaFile ? { id: newMediaId, name: options.mediaFile.name || 'Exercise media', type: options.mediaFile.type, size: options.mediaFile.size }
            : options.removeMedia ? null : current?.media ?? null }
        db.exerciseLibrary = current ? catalog.map(item => item.id === id ? saved : item) : [saved, ...catalog]
        const action = !current ? 'created' : current.status !== status ? status === 'active' ? 'reactivated' : 'deactivated' : 'updated'
        appendSavedEditMessage(db, { exerciseId: id, title: `Exercise ${action}: ${saved.name}`,
          body: `${saved.category}. ${saved.status === 'active' ? 'Available in the session exercise picker.' : 'Unavailable for new selections.'} Existing saved session plans are preserved.`, kind: 'exercise_library_update' })
      })
    } catch (error) {
      if (newMediaId) await exerciseLibraryMedia.remove(newMediaId).catch(() => {})
      throw error
    }
    if (previousMediaId && previousMediaId !== saved.media?.id) await exerciseLibraryMedia.remove(previousMediaId).catch(() => {})
    return structuredClone(saved)
  },
}
