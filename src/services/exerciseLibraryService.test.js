import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { exerciseLibraryService as service } from './exerciseLibraryService.js'
import { exerciseLibraryMedia as media } from './exerciseLibraryMedia.js'

import { DEFAULT_EXERCISES } from '../data/mockExercises.js'
vi.mock('./exerciseLibraryMedia.js', () => ({ exerciseLibraryMedia: { save: vi.fn(), remove: vi.fn(), load: vi.fn() } }))
const draft = { name: 'Band Row', category: 'Upper Body', description: 'Keep elbows close.', status: 'active' }
const photo = () => new File(['photo'], 'row.png', { type: 'image/png' })
let owner, trainer
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
beforeEach(() => {
  mockDb.reset(); vi.resetAllMocks()
  media.save.mockResolvedValue(undefined); media.remove.mockResolvedValue(undefined)
  owner = mockDb.read().users.find(user => user.role === 'owner')
  trainer = mockDb.read().users.find(user => user.role === 'trainer')
})
describe('exercise library service boundary', () => {
  it('creates and edits exercises with replacement attachments when randomUUID is unavailable', async () => {
    const browserCrypto = globalThis.crypto
    vi.stubGlobal('crypto', { getRandomValues: browserCrypto.getRandomValues.bind(browserCrypto) })
    const before = mockDb.read()
    const created = await service.save({ draft }, owner)
    const attached = await service.save({ id: created.id, expectedVersion: 1, draft: created, mediaFile: photo() }, owner)
    const replaced = await service.save({ id: created.id, expectedVersion: 2, draft: attached, mediaFile: photo() }, owner)
    const another = await service.save({ draft: { ...draft, name: 'Another movement' } }, owner)
    expect(created.id).toMatch(/^library-/)
    expect(another.id).not.toBe(created.id)
    expect(attached.id).toBe(created.id)
    expect(replaced.id).toBe(created.id)
    expect(replaced.media.id).not.toBe(attached.media.id)
    expect(media.save).toHaveBeenCalledWith(replaced.media.id, expect.any(File))
    expect(media.remove).toHaveBeenCalledWith(attached.media.id)
    expect(mockDb.read().messages.filter(message => message.exerciseId === created.id)).toHaveLength(3)
    expect(mockDb.read().sessions).toEqual(before.sessions)
  })
  it('creates one entry and an owner-only unread message without altering sessions', async () => {
    const before = mockDb.read()
    const saved = await service.save({ draft, mediaFile: photo() }, owner)
    const after = mockDb.read()
    expect(after.exerciseLibrary).toHaveLength(50)
    expect(after.exerciseLibrary.slice(1)).toEqual(DEFAULT_EXERCISES)
    expect(saved.media).toMatchObject({ type: 'image/png', name: 'row.png', size: 5 })
    expect(media.save).toHaveBeenCalledOnce()
    expect(after.sessions).toEqual(before.sessions)
    expect(after.messages).toHaveLength(before.messages.length + 1)
    expect(after.messages.at(-1)).toMatchObject({ exerciseId: saved.id, recipientRole: 'owner', read: false })
    expect(after.messages.at(-1)).not.toHaveProperty('clientId')
    expect(after.messages.at(-1)).not.toHaveProperty('recipientTrainerId')
    expect(service.getAll(trainer).some(item => item.id === saved.id)).toBe(true)
  })
  it('rejects trainer, forged and inactive identities before storing attachments', async () => {
    for (const actor of [trainer, { ...trainer, role: 'owner' }, { id: 'unknown', role: 'owner' }]) await expect(service.save({ draft, mediaFile: photo() }, actor)).rejects.toThrow()
    mockDb.mutate(db => { db.users.find(user => user.id === owner.id).status = 'inactive' })
    const before = mockDb.read()
    await expect(service.save({ draft, mediaFile: photo() }, owner)).rejects.toThrow(/active staff/)
    expect(media.save).not.toHaveBeenCalled(); expect(mockDb.read()).toEqual(before)
  })
  it('renames, deactivates and reactivates by stable ID while preserving all saved plans', async () => {
    const before = mockDb.read()
    const original = service.getAll(owner)[0]
    const updated = await service.save({ id: original.id, expectedVersion: 1, draft: { ...original, name: 'Renamed movement' } }, owner)
    const inactive = await service.save({ id: updated.id, expectedVersion: 2, draft: { ...updated, status: 'inactive' } }, owner)
    expect(service.getAll(owner)).toHaveLength(49)
    expect(service.getAll(trainer).some(item => item.id === updated.id)).toBe(false)
    const active = await service.save({ id: inactive.id, expectedVersion: 3, draft: { ...inactive, status: 'active' } }, owner)
    expect(active).toMatchObject({ id: original.id, name: 'Renamed movement', version: 4 })
    expect(service.getAll(trainer).some(item => item.id === active.id)).toBe(true)
    expect(mockDb.read().sessions).toEqual(before.sessions)
  })
  it('rejects duplicate names and stale versions atomically', async () => {
    const saved = await service.save({ draft }, owner), before = mockDb.read()
    await expect(service.save({ draft: { ...draft, name: ' BAND   ROW ' } }, owner)).rejects.toThrow(/already/)
    await expect(service.save({ id: saved.id, expectedVersion: 0, draft: { ...saved, description: 'stale' } }, owner)).rejects.toThrow(/changed/)
    expect(mockDb.read()).toEqual(before)
  })
  it('rolls back a newly uploaded attachment when a concurrent edit wins', async () => {
    const original = service.getAll(owner)[0]
    const winner = { ...original, version: 2, description: 'Concurrent change' }
    media.save.mockImplementation(async () => mockDb.mutate(db => { db.exerciseLibrary = [winner, ...DEFAULT_EXERCISES.slice(1)] }))
    await expect(service.save({ id: original.id, expectedVersion: 1, draft: original, mediaFile: photo() }, owner)).rejects.toThrow(/changed/)
    expect(media.remove).toHaveBeenCalledWith(media.save.mock.calls[0][0])
    expect(service.getAll(owner)[0]).toEqual(winner)
    expect(mockDb.read().messages.filter(message => message.exerciseId)).toHaveLength(0)
  })
  it('leaves the database untouched when attachment storage fails', async () => {
    const before = mockDb.read(); media.save.mockRejectedValue(new Error('Storage full'))
    await expect(service.save({ draft, mediaFile: photo() }, owner)).rejects.toThrow('Storage full')
    expect(mockDb.read()).toEqual(before)
  })
  it('rolls back a replacement attachment when database persistence fails, then retries without duplicate messages', async () => {
    const first = await service.save({ draft, mediaFile: photo() }, owner)
    const before = mockDb.read(), stored = localStorage.getItem('fitfinity-m2-demo-db-v4')
    const failure = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage full. Try again.') })
    const options = { id: first.id, expectedVersion: 1, draft: { ...first, description: 'Updated' }, mediaFile: photo() }
    await expect(service.save(options, owner)).rejects.toThrow('Storage full.')
    expect(mockDb.read()).toEqual(before)
    expect(localStorage.getItem('fitfinity-m2-demo-db-v4')).toBe(stored)
    expect(media.remove).toHaveBeenCalledWith(media.save.mock.calls.at(-1)[0])
    expect(media.remove).not.toHaveBeenCalledWith(first.media.id)
    failure.mockRestore()
    const saved = await service.save(options, owner)
    expect(saved.version).toBe(2)
    expect(saved.media.id).not.toBe(first.media.id)
    expect(media.remove).toHaveBeenCalledWith(first.media.id)
    expect(mockDb.read().messages.filter(message => message.exerciseId === first.id)).toHaveLength(2)
  })
  it('keeps existing media on text edits, then removes replaced or explicitly removed media', async () => {
    const first = await service.save({ draft, mediaFile: photo() }, owner)
    const text = await service.save({ id: first.id, expectedVersion: 1, draft: { ...first, description: 'Changed' } }, owner)
    expect(text.media).toEqual(first.media); expect(media.remove).not.toHaveBeenCalled()
    const second = await service.save({ id: first.id, expectedVersion: 2, draft: text, mediaFile: photo() }, owner)
    expect(second.media.id).not.toBe(first.media.id); expect(media.remove).toHaveBeenCalledWith(first.media.id)
    const removed = await service.save({ id: first.id, expectedVersion: 3, draft: second, removeMedia: true }, owner)
    expect(removed.media).toBeNull(); expect(media.remove).toHaveBeenCalledWith(second.media.id)
  })
  it('rejects invalid files without writing and ignores unrelated draft fields', async () => {
    const before = mockDb.read()
    await expect(service.save({ draft, mediaFile: new File(['<html>'], 'x.html', { type: 'text/html' }) }, owner)).rejects.toThrow(/Choose/)
    expect(mockDb.read()).toEqual(before); expect(media.save).not.toHaveBeenCalled()
    const saved = await service.save({ draft: { ...draft, id: 'injected', version: 99, media: { id: 'injected' }, clientId: 'c1' } }, owner)
    expect(saved.id).not.toBe('injected'); expect(saved.version).toBe(1); expect(saved.media).toBeNull(); expect(saved.clientId).toBeUndefined()
  })
})
