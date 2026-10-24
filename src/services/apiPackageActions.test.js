import { expect, it, vi } from 'vitest'
import { packageActionCommands, packageUndoCommands } from './apiPackageActions.js'

const id = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const input = { id: id(1), packageId: id(2), operation: 'deactivate' }
const reviewed = { clientId: input.id, purchaseId: input.packageId, operation: input.operation, clientVersion: 2, purchaseVersion: 1, expected: 'a'.repeat(64), status: 'active', name: 'Package', eligible: [{ id: id(3), version: 1 }] }
const draft = { ...input, reviewed, deleteUpcomingSessions: true }
const result = { id: id(4), clientId: id(1), purchaseId: id(2), status: 'inactive', purchaseVersion: 2, deletedSessionIds: [id(3)], messageId: id(5), undoUntil: null }
const auth = async generation => ({ sessionGeneration: generation, user: { role: 'owner' } })

it('binds one reviewed package and exact deletion selection to its save', async () => {
  const http = { get: vi.fn().mockResolvedValue(reviewed), post: vi.fn().mockResolvedValue(result) }
  const api = packageActionCommands(http, auth)
  expect((await api.review(input, 1)).reviewed).toEqual(reviewed)
  expect(await api.save(draft, 1)).toEqual(result)
  expect(http.post.mock.calls[0][1]).toEqual({ operation: 'deactivate', expected: reviewed.expected, deleteUpcomingSessions: true })
})

it('recovers a lost response without a second write and preserves the original checkbox', async () => {
  const http = { get: vi.fn().mockResolvedValue(result), post: vi.fn().mockRejectedValue(new Error('lost')) }
  const api = packageActionCommands(http, auth)
  await expect(api.save(draft, 1)).rejects.toThrow('lost')
  expect(await api.review(input, 1)).toMatchObject({ uncertain: true, deleteUpcomingSessions: true, reviewed })
  await expect(api.review({ ...input, packageId: id(20) }, 1)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect((await api.reconcile(1)).result).toEqual(result)
  expect(http.post).toHaveBeenCalledTimes(1)
})

it.each(['foreign-target', 'foreign-deletion', 'missing-deletion'])('rejects misleading receipts: %s', async mode => {
  const saved = structuredClone(result)
  if (mode === 'foreign-target') saved.purchaseId = id(20)
  if (mode === 'foreign-deletion') saved.deletedSessionIds = [id(20)]
  if (mode === 'missing-deletion') saved.deletedSessionIds = []
  const api = packageActionCommands({ post: vi.fn().mockResolvedValue(saved) }, auth)
  await expect(api.save(draft, 1)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('denies Trainer reviews before reading a purchase', async () => {
  const http = { get: vi.fn() }
  const api = packageActionCommands(http, async () => ({ user: { role: 'trainer' } }))
  await expect(api.review(input, 1)).rejects.toMatchObject({ code: 'forbidden' })
  expect(http.get).not.toHaveBeenCalled()
})

it('Undo reconciles the original result after transport loss rather than rebuilding a review', async () => {
  const saved = { id: id(8), status: 'undone', undoneAt: '2026-10-24T00:00:00Z' }
  const http = { get: vi.fn(async path => path === '/api/messages' ? [{ id: id(5), undo: { id: id(4), kind: 'package_deletion' } }] : path.endsWith('undo-review') ? { id: id(4), messageId: id(5), expected: 'b'.repeat(64) } : saved), post: vi.fn().mockRejectedValue(new Error('lost')) }
  const undo = packageUndoCommands(http, auth)
  await expect(undo({ id: id(5) }, 1)).rejects.toThrow('lost')
  expect(await undo({ id: id(5) }, 1)).toEqual(saved)
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.get.mock.calls.filter(([path]) => path.endsWith('undo-review'))).toHaveLength(1)
})
