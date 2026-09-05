const DATABASE = 'fitfinity-m2-exercise-videos'
const STORE = 'videos'
const memoryStore = new Map()

const keyFor = (sessionId, exerciseId) => `${sessionId}:${exerciseId}`

function openDatabase() {
  if (!globalThis.indexedDB) return Promise.resolve(null)

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function run(mode, operation) {
  const database = await openDatabase()
  if (!database) return operation(null)

  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE, mode)
    const request = operation(transaction.objectStore(STORE))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => database.close()
    transaction.onabort = () => database.close()
  })
}

export async function saveExerciseVideoBlob(sessionId, exerciseId, blob) {
  const key = keyFor(sessionId, exerciseId)
  memoryStore.set(key, blob)
  try {
    await run('readwrite', store => store ? store.put(blob, key) : undefined)
  } catch {
    // The in-memory copy keeps the prototype usable when private browsing blocks IndexedDB.
  }
}

export async function loadExerciseVideoBlob(sessionId, exerciseId) {
  const key = keyFor(sessionId, exerciseId)
  try {
    const stored = await run('readonly', store => store ? store.get(key) : memoryStore.get(key))
    return stored ?? memoryStore.get(key) ?? null
  } catch {
    return memoryStore.get(key) ?? null
  }
}

export async function removeExerciseVideoBlob(sessionId, exerciseId) {
  const key = keyFor(sessionId, exerciseId)
  memoryStore.delete(key)
  try {
    await run('readwrite', store => store ? store.delete(key) : undefined)
  } catch {
    // The persisted prototype metadata can still be removed if IndexedDB is unavailable.
  }
}
