import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'

const KEY = 'fitfinity-m2-demo-db-v4'
beforeEach(() => mockDb.reset())
afterEach(() => vi.restoreAllMocks())

it('rejects failed mutations, writes and resets without changing memory or stored data, then retries once', () => {
  for (const operation of ['mutate', 'write', 'reset']) {
    mockDb.mutate(db => { db.testRevision = 1 })
    const before = mockDb.read(), stored = localStorage.getItem(KEY)
    const save = () => operation === 'mutate' ? mockDb.mutate(db => { db.testRevision += 1 })
      : operation === 'write' ? mockDb.write({ ...before, testRevision: 2 }) : mockDb.reset()
    const error = new Error('Storage full. Try again.')
    const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw error })
    expect(save).toThrow(error)
    expect(mockDb.read()).toEqual(before)
    expect(localStorage.getItem(KEY)).toBe(stored)
    fail.mockRestore()
    const saved = save()
    expect(mockDb.read()).toEqual(saved)
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(saved)
    if (operation !== 'reset') expect(saved.testRevision).toBe(2)
    else expect(saved.testRevision).toBeUndefined()
  }
})

it('leaves the current state untouched when a mutation or serialization fails', () => {
  const before = mockDb.read(), stored = localStorage.getItem(KEY)
  expect(() => mockDb.mutate(db => { db.clients.length = 0; throw new Error('Invalid change') })).toThrow('Invalid change')
  expect(() => mockDb.mutate(db => { db.circular = db })).toThrow()
  expect(mockDb.read()).toEqual(before)
  expect(localStorage.getItem(KEY)).toBe(stored)
})
