const DATABASE = 'fitfinity-m2-exercise-videos'
const STORE = 'videos'
const legacyKey = (sessionId, exerciseId) => `${sessionId}:${exerciseId}`

function openDatabase() {
  if (!globalThis.indexedDB) return Promise.reject(new Error('This browser cannot store session videos. Use a supported browser and try again.'))
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function run(mode, operation) {
  const database = await openDatabase()
  return new Promise((resolve, reject) => {
    let transaction
    try {
      transaction = database.transaction(STORE, mode)
      const request = operation(transaction.objectStore(STORE))
      transaction.oncomplete = () => { database.close(); resolve(request.result) }
      transaction.onerror = transaction.onabort = () => { database.close(); reject(transaction.error || request.error || new Error('Session video storage failed.')) }
    } catch (error) {
      try { transaction?.abort() } catch { /* Already inactive. */ }
      database.close(); reject(error)
    }
  })
}

function bytesFor(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(new Uint8Array(reader.result))
    reader.onerror = () => reject(reader.error || new Error('Could not read the video.'))
    reader.onabort = () => reject(new Error('Reading the video was cancelled.'))
    reader.readAsArrayBuffer(blob)
  })
}

export async function saveExerciseVideoBlob(sessionId, exerciseId, blob) {
  const id = `${legacyKey(sessionId, exerciseId)}:${Array.from(crypto.getRandomValues(new Uint8Array(12)), byte => byte.toString(16).padStart(2, '0')).join('')}`
  const bytes = await bytesFor(blob)
  await run('readwrite', store => store.put({ format: 'bytes-v1', type: blob.type, bytes }, id))
  return id
}

export async function loadExerciseVideoBlob(sessionId, exerciseId, id) {
  const record = await run('readonly', store => store.get(id ?? legacyKey(sessionId, exerciseId)))
  if (!record) return null
  if (record instanceof Blob) return record
  if (record.format === 'bytes-v1' && ArrayBuffer.isView(record.bytes)) return new Blob([record.bytes], { type: record.type })
  throw new Error('The stored video could not be read. Attach it again.')
}

export function removeExerciseVideoBlob(sessionId, exerciseId, id) {
  return run('readwrite', store => store.delete(id ?? legacyKey(sessionId, exerciseId)))
}
