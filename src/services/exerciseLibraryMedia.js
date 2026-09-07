// Reference media has its own store; session filming keeps its existing contract.
const DATABASE = 'fitfinity-exercise-library-media'
function openDatabase() {
  if (!globalThis.indexedDB) return Promise.reject(new Error('This browser cannot store exercise media. Try another browser or save without an attachment.'))
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => request.result.createObjectStore('media')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}
async function transaction(mode, operation) {
  const db = await openDatabase()
  return new Promise((resolve, reject) => {
    let tx
    try {
      tx = db.transaction('media', mode)
      const request = operation(tx.objectStore('media'))
      tx.oncomplete = () => { db.close(); resolve(request.result) }
      tx.onerror = tx.onabort = () => { db.close(); reject(tx.error || request.error || new Error('Could not store exercise media.')) }
    } catch (error) {
      try { tx?.abort() } catch { /* The transaction may already be inactive. */ }
      db.close()
      reject(error)
    }
  })
}

function readBytes(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error || new Error('Could not read this attachment.'))
    reader.onabort = () => reject(new Error('Reading this attachment was cancelled.'))
    reader.readAsArrayBuffer(blob)
  })
}

export const exerciseLibraryMedia = {
  async save(id, blob) {
    // WebKit can reject File/Blob persistence; ordinary byte records avoid that path.
    const bytes = new Uint8Array(await readBytes(blob))
    return transaction('readwrite', store => store.put({ format: 'bytes-v1', bytes, type: blob.type }, id))
  },
  async load(id) {
    const stored = await transaction('readonly', store => store.get(id))
    if (!stored) return null
    if (stored instanceof Blob) return stored
    if (stored.format === 'bytes-v1' && ArrayBuffer.isView(stored.bytes)) return new Blob([stored.bytes], { type: stored.type })
    throw new Error('This stored attachment could not be read. Attach the file again.')
  },
  remove(id) { return transaction('readwrite', store => store.delete(id)) },
}
