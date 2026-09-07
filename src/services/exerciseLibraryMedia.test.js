import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { exerciseLibraryMedia as media } from './exerciseLibraryMedia.js'

let records, writeFailure, closed
beforeEach(() => {
  records = new Map()
  writeFailure = null
  closed = vi.fn()
  // This storage boundary rejects raw blobs, as in the reported WebKit failure.
  vi.stubGlobal('indexedDB', {
    open: () => {
      const open = {}
      const db = {
        close: closed,
        transaction: () => {
          const tx = { abort: vi.fn() }
          const operation = (result, commit, writing = false) => {
            const request = { result }
            queueMicrotask(() => {
              if (writing && writeFailure) {
                tx.error = writeFailure
                tx.onabort?.()
              } else {
                commit?.()
                tx.oncomplete?.()
              }
            })
            return request
          }
          tx.objectStore = () => ({
            put: (value, id) => {
              if (value instanceof Blob) throw new Error('Error preparing Blob/File data to be stored in object store')
              const stored = structuredClone(value)
              return operation(id, () => records.set(id, stored), true)
            },
            get: id => operation(records.get(id)),
            delete: id => operation(undefined, () => records.delete(id), true),
          })
          return tx
        },
      }
      queueMicrotask(() => { open.result = db; open.onsuccess?.() })
      return open
    },
  })
})
afterEach(() => vi.unstubAllGlobals())

const bytesOf = blob => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(Array.from(new Uint8Array(reader.result)))
  reader.onerror = () => reject(reader.error)
  reader.readAsArrayBuffer(blob)
})

it('round-trips image and video bytes when storage refuses File/Blob values', async () => {
  const content = [0, 255, 128, 1, 42, 192, 7]
  for (const type of ['image/png', 'video/mp4']) {
    const file = new File([new Uint8Array(content)], 'reference', { type })
    await media.save(type, file)
    const loaded = await media.load(type)
    expect(loaded).toBeInstanceOf(Blob)
    expect(loaded.type).toBe(type)
    expect(await bytesOf(loaded)).toEqual(content)
    await media.remove(type)
    expect(await media.load(type)).toBeNull()
  }
})

it('reads previously saved blobs without rewriting them and reports missing or invalid records', async () => {
  const legacy = new Blob(['previous attachment'], { type: 'video/webm' })
  records.set('legacy', legacy)
  expect(await media.load('legacy')).toBe(legacy)
  expect(records.get('legacy')).toBe(legacy)
  expect(await media.load('missing')).toBeNull()
  records.set('invalid', { format: 'unknown' })
  await expect(media.load('invalid')).rejects.toThrow('could not be read')
})

it('rejects an aborted write and closes the connection without reporting a saved attachment', async () => {
  writeFailure = new Error('Storage full')
  await expect(media.save('failed', new Blob(['data'], { type: 'image/png' }))).rejects.toThrow('Storage full')
  expect(records.has('failed')).toBe(false)
  expect(closed).toHaveBeenCalledOnce()
})
