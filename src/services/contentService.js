import { contentErrors } from '../app/content.js'
import { delay, mockDb } from './mockDb.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { appendSavedEditMessage } from './editMessage.js'

export const contentService = {
  async save({ id, expectedVersion, draft }, actor) {
    await delay()
    const errors = contentErrors(draft)
    if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
    let saved
    mockDb.mutate(db => {
      if (requireActiveActor(db, actor).role !== 'owner') throw new Error('Only the owner can manage content.')
      const entries = db.contentEntries ?? []
      const current = entries.find(item => item.id === id)
      if (id && !current) throw new Error('Content entry not found.')
      if (current && current.version !== expectedVersion) throw new Error('This content changed. Refresh and review before saving.')
      if (entries.some(item => item.id !== id && item.key === draft.key)) throw new Error('This content key is already in use.')
      const stamp = new Date().toISOString()
      saved = { id: id ?? `content-${Array.from(crypto.getRandomValues(new Uint8Array(12)), n => n.toString(16).padStart(2, '0')).join('')}`, key: draft.key, title: draft.title.trim(), body: draft.body.trim(), status: draft.status, version: (current?.version ?? 0) + 1, createdAt: current?.createdAt ?? stamp, updatedAt: stamp }
      db.contentEntries = current ? entries.map(item => item.id === id ? saved : item) : [saved, ...entries]
      appendSavedEditMessage(db, { title: `Content saved: ${saved.title}`, body: `${saved.key} · ${saved.status}.`, kind: 'content_update', contentId: saved.id })
    })
    return saved
  },
}
