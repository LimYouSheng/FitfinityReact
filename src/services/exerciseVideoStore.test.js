import { afterEach, expect, it, vi } from 'vitest'
import { loadExerciseVideoBlob, pruneExerciseVideoBlobs, saveExerciseVideoBlob } from './exerciseVideoStore.js'
afterEach(()=>vi.unstubAllGlobals())
it('M4 fails explicitly when persistent video storage is unavailable instead of pretending a memory save succeeded',async()=>{
  vi.stubGlobal('indexedDB',undefined)
  await expect(saveExerciseVideoBlob('session','exercise',new Blob(['clip'],{type:'video/webm'}))).rejects.toThrow('cannot store session videos')
  await expect(loadExerciseVideoBlob('session','exercise')).rejects.toThrow('cannot store session videos')
  await expect(pruneExerciseVideoBlobs(new Date(), {})).rejects.toThrow('cannot store session videos')
})

it('timestamps stored bytes and retries expiration cleanup without deleting unexpired or referenced legacy clips', async () => {
  const records = new Map([
    ['expired-orphan', { format: 'bytes-v1', bytes: new Uint8Array([1]), expiresAt: '2026-09-02T10:00:00Z' }],
    ['legacy-kept', new Blob(['old retained'])],
    ['undated-orphan', new Blob(['unknown age'])],
  ])
  let failSweep = true
  const database = {
    close: vi.fn(),
    transaction() {
      const transaction = {}
      transaction.objectStore = () => ({
        put(value, key) {
          const request = { result: key }
          queueMicrotask(() => { records.set(key, value); transaction.oncomplete() })
          return request
        },
        openCursor() {
          const request = {}
          const keys = [...records.keys()]
          const deletions = []
          let offset = 0
          const next = () => {
            if (offset === keys.length) {
              request.result = null
              request.onsuccess()
              if (failSweep) {
                transaction.error = new Error('Temporary storage failure')
                transaction.onabort()
              } else {
                for (const key of deletions) records.delete(key)
                transaction.oncomplete()
              }
              return
            }
            const key = keys[offset++]
            request.result = {
              key, value: records.get(key),
              delete() { deletions.push(key) },
              continue() { queueMicrotask(next) },
            }
            request.onsuccess()
          }
          queueMicrotask(next)
          return request
        },
      })
      return transaction
    },
  }
  vi.stubGlobal('indexedDB', { open() {
    const request = { result: database }
    queueMicrotask(() => request.onsuccess())
    return request
  } })
  const expiresAt = '2026-09-16T10:00:00.000Z'
  const id = await saveExerciseVideoBlob('session', 'exercise', new Blob(['retained clip'], { type: 'video/webm' }), { expiresAt })
  expect(records.get(id)).toMatchObject({ format: 'bytes-v1', type: 'video/webm', expiresAt })
  const retained = { 'legacy-kept': expiresAt }
  await expect(pruneExerciseVideoBlobs(new Date('2026-09-09T10:00:00Z'), retained)).rejects.toThrow('Temporary storage failure')
  expect(records.has('expired-orphan')).toBe(true)
  failSweep = false
  await pruneExerciseVideoBlobs(new Date('2026-09-09T10:00:00Z'), retained)
  expect([...records.keys()]).toEqual(['legacy-kept', id])
  await pruneExerciseVideoBlobs(new Date(expiresAt), retained)
  expect(records.size).toBe(0)
})
