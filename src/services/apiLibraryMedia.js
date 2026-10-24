import { ApiError } from './apiClient.js'

const fail = () => { throw new ApiError('MEDIA_RESPONSE', 'The protected attachment could not be verified.') }
const sha = bytes => crypto.subtle.digest('SHA-256', bytes).then(result => [...new Uint8Array(result)].map(v => v.toString(16).padStart(2, '0')).join(''))
export const fileDigest = async file => sha(await file.arrayBuffer())

function signedUrl(value) {
  let url
  try { url = new URL(value) } catch { fail() }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(globalThis.location?.hostname)
  if (url.username || url.password || url.hash || (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) || !/^[0-9a-f]{64}$/.test(url.searchParams.get('X-Amz-Signature') ?? '')) fail()
  return url.href
}

/** Storage receives no portal cookies, CSRF tokens or referrer, and cannot redirect credentials. */
export async function putLibraryMedia(fetchImpl, lease, file, expectedHash, assertCurrent) {
  const headers = lease?.headers
  if (!headers || Object.keys(headers).length !== 3 || headers['Content-Type'] !== file.type || headers['If-None-Match'] !== '*' || headers['x-amz-checksum-sha256'] !== btoa(String.fromCharCode(...expectedHash.match(/../g).map(v => parseInt(v, 16))))) fail()
  assertCurrent()
  const result = await fetchImpl(signedUrl(lease.url), { method: 'PUT', body: file, headers, credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer', cache: 'no-store' })
  assertCurrent()
  if (!result.ok && result.status !== 412) throw new ApiError('UPLOAD_UNCERTAIN', 'Check the original exercise save before uploading again.')
}

/** Bound streaming reads, verify exact bytes, then recheck current server scope before playback. */
export async function getLibraryMedia(http, fetchImpl, identity, generation, assertCurrent) {
  const lease = await http.get(`/api/exercise-library/media/${identity}`, { expectedGeneration: generation })
  if (!lease || Object.keys(lease).length !== 5 || !Number.isSafeInteger(lease.size) || lease.size < 1 || lease.size > 50 * 1024 * 1024 || !/^[0-9a-f]{64}$/.test(lease.sha256) || !Number.isSafeInteger(lease.version) || lease.version < 1) fail()
  assertCurrent()
  const response = await fetchImpl(signedUrl(lease.url), { credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer', cache: 'no-store' })
  assertCurrent()
  if (!response.ok || response.headers.get('content-type') !== lease.type || Number(response.headers.get('content-length')) !== lease.size || !response.body) fail()
  const reader = response.body.getReader(), chunks = []
  let size = 0
  try {
    for (;;) {
      const { done, value } = await reader.read()
      assertCurrent()
      if (done) break
      size += value.byteLength
      if (size > lease.size) fail()
      chunks.push(value)
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error }
  finally { reader.releaseLock() }
  const blob = new Blob(chunks, { type: lease.type })
  if (size !== lease.size || await fileDigest(blob) !== lease.sha256) fail()
  const checked = await http.get(`/api/exercise-library/media/${identity}/check?version=${lease.version}`, { expectedGeneration: generation })
  assertCurrent()
  if (checked?.valid !== true || Object.keys(checked).length !== 1) fail()
  return blob
}
