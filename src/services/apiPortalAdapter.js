import { ApiError, createApiClient } from './apiClient.js'
import { directorySnapshot } from './apiDirectory.js'
import { portalRequest, authRequest } from './portalContracts.js'

export function createApiPortalAdapter(options = {}) {
  const http = createApiClient(options)
  let policyPromise
  let loading
  let loadingGeneration
  const policy = () => {
    if (!policyPromise) policyPromise = http.get('/auth/policy', { authenticated: false }).then(value => {
      if (value?.password?.minimumLength !== 15 || value.password.maximumLength !== 128 || value.password.spacesAllowed !== false || value?.mfa?.required !== true || value.mfa.method !== 'totp') throw new ApiError('API_RESPONSE', 'The staff sign-in policy could not be verified.')
      return value
    }).catch(error => { policyPromise = null; throw error })
    return policyPromise
  }
  const assertSession = expected => {
    if (expected !== http.generation()) throw new ApiError('SESSION_CHANGED', 'Your sign-in changed. Reload your account before continuing.')
  }
  const actionSession = async (expected, bootstrap = false) => {
    assertSession(expected)
    const session = bootstrap
      ? await http.get('/auth/session', { authenticated: false, expectedGeneration: expected, accept: result => ({ ...http.remember(result), sessionGeneration: http.generation() }) })
      : await http.session()
    // A preflight may discover a different cookie. It cannot adopt that login for an old action.
    assertSession(expected)
    return session
  }
  const clearSession = result => { http.clear(); return result }
  const methods = {
    async signIn({ identifier, password }) {
      http.clear()
      return validateChallenge(await http.post('/auth/sign-in', { email: identifier.trim(), password }))
    },
    async challenge(answer) {
      return http.post('/auth/challenge', answer, { accept: result => result.user ? http.remember(result) : validateChallenge(result) })
    },
    async forgotPassword({ identifier }) {
      http.clear()
      return http.post('/auth/forgot-password', { email: identifier.trim() })
    },
    async resetPassword({ code, newPassword }) {
      return http.post('/auth/reset-password', { code, newPassword }, { accept: clearSession })
    },
    async changePassword({ currentPassword, newPassword }, expected) {
      const session = await actionSession(expected)
      return http.post('/auth/change-password', { currentPassword, newPassword }, { csrf: true, expectedGeneration: session.sessionGeneration, accept: clearSession })
    },
    async signOut(_input, expected) {
      try {
        // Bootstrap works even after access expiry; logout never needs a refresh.
        const session = await actionSession(expected, true)
        return await http.post('/auth/sign-out', { allSessions: false }, { csrf: true, expectedGeneration: session.sessionGeneration, accept: clearSession })
      } catch (error) {
        if (error.code !== 'SESSION_EXPIRED') throw error
        return { signedOut: true }
      }
    },
  }
  return {
    async load() {
      if (loading && loadingGeneration === http.generation()) return loading
      loadingGeneration = http.generation()
      const operation = (async () => {
        const authPolicy = await policy()
        const snapshot = { user: null, data: null, accounts: [], policy: { ...authPolicy, timeZone: 'Asia/Singapore' }, capabilities: { demoControls: false, staffWorkflows: false, realAuthentication: true } }
        let verifiedIdentity
        try {
          const { user, sessionGeneration } = await http.session()
          verifiedIdentity = { id: user.id, role: user.role, sessionGeneration }
          const directory = directorySnapshot(await http.get('/api/directory', { expectedGeneration: sessionGeneration }), user)
          return { ...snapshot, ...directory, user, sessionGeneration, capabilities: { ...snapshot.capabilities, staffWorkflows: true, directoryReadOnly: true } }
        }
        catch (error) {
          if (error.code === 'SESSION_EXPIRED') return snapshot
          if (error.code === 'SESSION_RECHECK') return { ...snapshot, authNotice: error.message }
          // A failed directory read must not conceal a verified account/role change.
          // This metadata may retire recovery state, never authorize private UI.
          if (verifiedIdentity && error.code !== 'SESSION_CHANGED') error.verifiedIdentity = verifiedIdentity
          throw error
        }
      })()
      loading = operation
      try { return await operation }
      finally { if (loading === operation) loading = null }
    },
    async session(request, { expectedGeneration = http.generation() } = {}) {
      const { operation, input } = authRequest(request, 'api')
      return methods[operation](input, expectedGeneration)
    },
    async invoke(request, { expectedGeneration = http.generation() } = {}) {
      const { service, operation, input } = portalRequest(request, 'api')
      if (service === 'staffService' && operation === 'createAdmin') {
        const { user, sessionGeneration } = await actionSession(expectedGeneration)
        if (user.role !== 'owner') throw new ApiError('forbidden', 'Only the owner can create an Admin.', 403)
        const result = await http.post('/api/staff/admins', input.body, { csrf: true, idempotencyKey: input.requestKey, expectedGeneration: sessionGeneration })
        if (result?.role !== 'admin' || !['pending', 'sending', 'sent', 'unknown'].includes(result.invitation) || !['id', 'name', 'email'].every(key => typeof result[key] === 'string' && result[key]) || Object.keys(result).some(key => !['id', 'name', 'email', 'role', 'invitation'].includes(key))) throw new ApiError('API_RESPONSE', 'Account setup could not be verified. Check the same request again.')
        return result
      }
      const { user, sessionGeneration } = await http.session()
      const { data } = directorySnapshot(await http.get('/api/directory', { expectedGeneration: sessionGeneration }), user)
      const rows = data[service === 'clientService' ? 'clients' : 'trainers']
      if (operation === 'getById') return rows.find(row => row.id === input.id) ?? null
      return operation === 'getActive' ? rows.filter(row => row.status === 'active') : rows
    },
    async reset() { throw new ApiError('OPERATION_UNAVAILABLE', 'Demo controls are unavailable for this account.') },
  }
}

function validateChallenge(result) {
  if (!['NEW_PASSWORD_REQUIRED', 'MFA_SETUP', 'SOFTWARE_TOKEN_MFA'].includes(result?.challenge) || !Number.isFinite(Date.parse(result.expiresAt)) || (result.challenge === 'MFA_SETUP' && !/^[A-Z2-7]+$/.test(result.secretCode ?? ''))) throw new ApiError('API_RESPONSE', 'The sign-in response could not be verified. Start again.')
  return result
}
