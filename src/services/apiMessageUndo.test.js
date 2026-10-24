import { expect, it, vi } from 'vitest'
import { messageUndoCommands } from './apiMessageUndo.js'

const id = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const auth = async generation => ({ sessionGeneration: generation, user: { role: 'owner' } })

it('Undo reconciles the original result after transport loss rather than rebuilding a review', async () => {
  const saved = { id: id(8), status: 'undone', undoneAt: '2026-10-24T00:00:00Z' }
  const http = { get: vi.fn(async path => path === '/api/messages' ? [{ id: id(5), undo: { id: id(4), kind: 'package_deletion' } }] : path.endsWith('undo-review') ? { id: id(4), messageId: id(5), expected: 'b'.repeat(64) } : saved), post: vi.fn().mockRejectedValue(new Error('lost')) }
  const undo = messageUndoCommands(http, auth)
  await expect(undo({ id: id(5) }, 1)).rejects.toThrow('lost')
  expect(await undo({ id: id(5) }, 1)).toEqual(saved)
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.get.mock.calls.filter(([path]) => path.endsWith('undo-review'))).toHaveLength(1)
})

it('allows a Trainer to submit a reviewed session change while preserving package authority', async () => {
  const saved = { id: id(8), actionId: id(4), status: 'undone', undoneAt: '2026-10-24T00:00:00Z' }
  const http = { get: vi.fn(async path => path === '/api/messages'
    ? [{ id: id(5), undo: { id: id(4), kind: 'session_change' } }]
    : { id: id(4), messageId: id(5), expected: 'b'.repeat(64) }), post: vi.fn().mockResolvedValue(saved) }
  const trainer = async generation => ({ sessionGeneration: generation, user: { role: 'trainer' } })
  expect(await messageUndoCommands(http, trainer)({ id: id(5) }, 1)).toEqual(saved)
  expect(http.post.mock.calls[0][0]).toBe(`/api/session-changes/${id(4)}/undo`)
  expect(http.post.mock.calls[0][1]).toEqual({ expected: 'b'.repeat(64) })
  http.get.mockResolvedValue([{ id: id(5), undo: { id: id(4), kind: 'package_deletion' } }])
  await expect(messageUndoCommands(http, trainer)({ id: id(5) }, 1)).rejects.toMatchObject({ code: 'forbidden' })
  expect(http.post).toHaveBeenCalledTimes(1)
})

it('keeps an uncertain session Undo from being replaced by a package Undo', async () => {
  const http = { get: vi.fn(async path => path === '/api/messages'
    ? [{ id: id(5), undo: { id: id(4), kind: 'session_change' } }]
    : { id: id(4), messageId: id(5), expected: 'b'.repeat(64) }), post: vi.fn().mockRejectedValue(new Error('lost')) }
  const undo = messageUndoCommands(http, auth)
  await expect(undo({ id: id(5) }, 1)).rejects.toThrow('lost')
  await expect(undo({ id: id(6) }, 1)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.get).toHaveBeenCalledTimes(2)
})

it('refuses a receipt for another change and blocks simultaneous Undo submissions', async () => {
  let finish
  const http = { get: vi.fn(async path => path === '/api/messages'
    ? [{ id: id(5), undo: { id: id(4), kind: 'session_change' } }]
    : { id: id(4), messageId: id(5), expected: 'b'.repeat(64) }), post: vi.fn(() => new Promise(resolve => { finish = resolve })) }
  const undo = messageUndoCommands(http, auth), first = undo({ id: id(5) }, 1)
  await vi.waitFor(() => expect(http.post).toHaveBeenCalledTimes(1))
  await expect(undo({ id: id(6) }, 1)).rejects.toMatchObject({ code: 'SAVE_PENDING' })
  finish({ id: id(8), actionId: id(9), status: 'undone', undoneAt: '2026-10-24T00:00:00Z' })
  await expect(first).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
