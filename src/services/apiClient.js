// Cookie credentials and CSRF stay in memory. A failed mutation is never replayed.
export class ApiError extends Error {
  constructor(code, message, status = 0, requestId = '') {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.requestId = requestId
  }
}

export function apiBaseUrl(value = '', origin = globalThis.location?.origin) {
  let url
  try { url = new URL(value || origin, origin) } catch { throw new ApiError('API_CONFIGURATION', 'The staff API address is not configured correctly.') }
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if ((url.protocol !== 'https:' && !(loopback && url.protocol === 'http:')) || url.username || url.password || url.search || url.hash) {
    throw new ApiError('API_CONFIGURATION', 'Use an HTTPS staff API address, or localhost for development.')
  }
  return url.href.replace(/\/$/, '')
}

export function createApiClient({ baseUrl = '', origin, fetchImpl = globalThis.fetch } = {}) {
  const base = apiBaseUrl(baseUrl, origin)
  let csrfToken = null
  let principal = null
  let generation = 0
  let sessionCleared = false
  let refreshPending = null
  let refreshBlocked = false
  let refreshVersion = 0
  const clear = () => { csrfToken = null; principal = null; generation++; sessionCleared = true; refreshPending = null; refreshBlocked = false }
  const remember = body => {
    if (!/^[0-9a-f]{64}$/.test(body?.csrfToken ?? '')) throw new ApiError('API_RESPONSE', 'The server returned an invalid session. Sign in again.')
    const nextPrincipal = body.user ? `${body.user.id}/${body.user.role}` : principal
    // Establishing authority after sign-in, recovery or expiry is a new boundary,
    // even when the previous credentials have already been removed from memory.
    if (sessionCleared || (csrfToken && csrfToken !== body.csrfToken) || (principal && nextPrincipal !== principal)) clear()
    csrfToken = body.csrfToken
    principal = nextPrincipal
    sessionCleared = false
    return body
  }
  const assertGeneration = expected => {
    if (expected !== generation) throw new ApiError('SESSION_CHANGED', 'The account changed while this request was running. Please retry.')
  }
  const send = async (path, { method = 'GET', body, csrf = false, idempotencyKey, signal, expectedGeneration = generation, accept = value => value } = {}) => {
    assertGeneration(expectedGeneration)
    if (!/^\/(?:auth\/|api\/|me$)/.test(path) || /[\\#]/.test(path) || /(?:^|\/)(?:\.|%2e){1,2}(?:\/|$)/i.test(path) || path.includes('://')) {
      throw new ApiError('API_PATH', 'Invalid staff API request.')
    }
    if (!['GET', 'POST'].includes(method) || (method === 'GET' && body !== undefined)) throw new ApiError('API_METHOD', 'Invalid staff API method.')
    const headers = { Accept: 'application/json' }
    if (method === 'POST') {
      headers['Content-Type'] = 'application/json'
      if (csrf) {
        if (!csrfToken) throw new ApiError('SESSION_EXPIRED', 'Your session has ended. Sign in again.')
        headers['X-CSRF-Token'] = csrfToken
      }
      if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
    }
    const at = generation
    let response, result
    try {
      response = await fetchImpl(`${base}${path}`, {
        method, headers, credentials: 'include', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer', signal,
        ...(method === 'POST' ? { body: JSON.stringify(body ?? {}) } : {}),
      })
      if (!response.headers.get('content-type')?.toLowerCase().includes('application/json')) throw new ApiError('API_RESPONSE', 'The staff service returned an unreadable response.')
      result = await response.json()
    } catch (error) {
      assertGeneration(at)
      if (error instanceof ApiError) throw error
      if (error.name === 'AbortError') throw error
      throw new ApiError('NETWORK_ERROR', method === 'POST' ? 'The response was interrupted. Check the current state before trying again.' : 'Unable to reach the staff service. Check your connection and retry.')
    }
    assertGeneration(at)
    if (!response.ok) {
      const detail = result?.error
      const code = /^[A-Za-z_]{1,64}$/.test(detail?.code ?? '') ? detail.code : 'API_ERROR'
      const requestId = /^[A-Za-z0-9_-]{1,100}$/.test(detail?.requestId ?? '') ? detail.requestId : ''
      const message = typeof detail?.message === 'string' && detail.message.length <= 500 ? detail.message : 'The staff request could not be completed.'
      if (code === 'SESSION_EXPIRED') clear()
      throw new ApiError(code, message, response.status, requestId)
    }
    // Validation and session changes run in the same turn as the generation check.
    return accept(result)
  }
  const refresh = async () => {
    if (refreshPending) return refreshPending
    if (refreshBlocked) throw new ApiError('SESSION_RECHECK', 'The session could not be renewed safely. Sign in again.')
    const at = generation
    const operation = (async () => {
      if (!csrfToken) await send('/auth/session', { accept: remember })
      assertGeneration(at)
      // Set before the consuming request. An ambiguous result cannot trigger another refresh.
      refreshBlocked = true
      await send('/auth/refresh', { method: 'POST', body: {}, csrf: true })
      if (at === generation) { refreshBlocked = false; refreshVersion++ }
    })()
    refreshPending = operation
    try { await operation }
    finally { if (refreshPending === operation) refreshPending = null }
  }
  const get = async (path, { authenticated = true, signal, expectedGeneration = generation, accept } = {}) => {
    const beforeRefresh = refreshVersion
    try { return await send(path, { signal, expectedGeneration, accept }) }
    catch (error) {
      if (!authenticated || error.code !== 'TOKEN_EXPIRED') throw error
      assertGeneration(expectedGeneration)
      if (beforeRefresh === refreshVersion) await refresh()
      return send(path, { signal, expectedGeneration, accept })
    }
  }
  const session = () => get('/me', { accept: result => {
    if (!result.user || !['owner', 'admin', 'trainer'].includes(result.user.role) || !['id', 'name', 'email'].every(key => typeof result.user[key] === 'string' && result.user[key]) || !Number.isFinite(Date.parse(result.expiresAt)) || !Number.isFinite(Date.parse(result.accessExpiresAt))) {
      clear()
      throw new ApiError('API_RESPONSE', 'The server returned an invalid account response.')
    }
    remember(result)
    refreshBlocked = false
    return { ...result, sessionGeneration: generation }
  } })
  return {
    clear, remember, get, session, generation: () => generation,
    post: (path, body, options = {}) => send(path, { ...options, method: 'POST', body }),
  }
}
