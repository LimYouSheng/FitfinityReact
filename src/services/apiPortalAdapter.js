import { clientReactivationCommands } from './apiClientReactivation.js'
import { clientDeactivationCommands } from './apiClientDeactivation.js'
import { messageCommands } from './apiMessages.js'
import { contentCommands } from './apiContent.js'
import { assessmentCommands } from './apiAssessments.js'
import { trainerSelectableForAvailability } from '../app/status.js'
import { clientCreationCommands } from './apiClientCreation.js'
import { emailCommands } from './apiEmailChanges.js'
import { trainerReactivationCommands } from './apiTrainerReactivation.js'
import { trainerDetailCommands } from './apiTrainerDetails.js'
import { trainerRateCommands } from './apiTrainerRates.js'
import { clientNoteCommands, withClientNotes } from './apiClientNotes.js'
import { clientDetailCommands } from './apiClientDetails.js'
import { trainerApprovalCommands } from './apiTrainerApprovals.js'
import { packageCommands } from './apiPackages.js'
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
  const saveTrainerRates = trainerRateCommands(http, actionSession)
  const trainerReactivation = trainerReactivationCommands(http, actionSession)
  const saveTrainerDetails = trainerDetailCommands(http, actionSession)
  const { request: requestEmailChange, ...emailMethods } = emailCommands(http, actionSession)
  const saveTrainerApprovals = trainerApprovalCommands(http, actionSession)
  const saveClientNotes = clientNoteCommands(http, actionSession)
  const saveClientDetails = clientDetailCommands(http, actionSession)
  const clientReactivation = clientReactivationCommands(http, actionSession)
  const clientDeactivation = clientDeactivationCommands(http, actionSession)
  const personalMessages = messageCommands(http, actionSession)
  const content = contentCommands(http, actionSession)
  const savePackage = packageCommands(http, actionSession)
  const clientAssessments = assessmentCommands(http, actionSession)
  const clientCreation = clientCreationCommands(http, actionSession)
  const clearSession = result => { http.clear(); return result }
  const methods = {
    ...emailMethods,
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
    async readContent(_input, { expectedGeneration = http.generation() } = {}) { return content.read(expectedGeneration) },
    async readClientAssessments(client, { expectedGeneration = http.generation() } = {}) {
      return clientAssessments.read(client, expectedGeneration)
    },
    async readAssessmentHistory(input, { expectedGeneration = http.generation() } = {}) {
      return clientAssessments.history(input, expectedGeneration)
    },
    async previewClientReactivation(input, { expectedGeneration = http.generation() } = {}) { return clientReactivation.review(input, expectedGeneration) },
    async previewClientReactivationDates(input, { expectedGeneration = http.generation() } = {}) { return clientReactivation.preview(input, expectedGeneration) },
    async previewClientDeactivation(input, { expectedGeneration = http.generation() } = {}) {
      return clientDeactivation.review(input, expectedGeneration)
    },
    async previewTrainerReactivation(input, { expectedGeneration = http.generation() } = {}) {
      return trainerReactivation.review(input, expectedGeneration)
    },
    async previewClientMatches(draft, { expectedGeneration = http.generation() } = {}) {
      return clientCreation.preview(draft, expectedGeneration)
    },
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
          const clientReactivationPending = await clientReactivation.recover(sessionGeneration)
          const clientDeactivationPending = await clientDeactivation.recover(sessionGeneration)
          const inbox = directory.personalMessages ? await personalMessages.read(sessionGeneration) : null
          return { ...snapshot, ...directory, clientDeactivationPending, clientReactivationPending, ...(inbox ? { data: { ...directory.data, messages: inbox.messages }, messageReadPending: inbox.pending, renewalDismissalPending: inbox.dismissalPending, requestCancellationPending: inbox.cancellationPending } : {}), user, sessionGeneration, policy: { ...snapshot.policy, ...directory.packagePolicy, ...directory.trainerProfilePolicy, ...directory.clientOnboardingPolicy }, capabilities: { ...snapshot.capabilities, staffWorkflows: true, directoryReadOnly: true, clientReactivationWrites: directory.clientReactivationWrites && ['owner', 'admin'].includes(user.role), clientDeactivationWrites: directory.clientDeactivationWrites && ['owner', 'admin'].includes(user.role), personalMessages: directory.personalMessages, requestCancellationWrites: directory.personalMessages && directory.requestCancellationWrites && user.role === 'trainer', renewalDismissalWrites: directory.personalMessages && directory.renewalDismissalWrites, contentWorkflows: directory.contentWorkflows && ['owner', 'admin'].includes(user.role), clientAssessmentWorkflows: directory.clientAssessmentWorkflows && ['owner', 'admin'].includes(user.role), clientCreation: directory.clientCreation && ['owner', 'admin'].includes(user.role), trainerReactivationWrites: directory.trainerReactivationWrites && ['owner', 'admin'].includes(user.role), trainerPersonalWrites: directory.trainerPersonalWrites && ['owner', 'admin'].includes(user.role), trainerEmailWrites: directory.trainerEmailWrites, trainerRateWrites: directory.trainerRateWrites && user.role === 'owner', clientNoteWrites: directory.clientNoteWrites, clientPersonalWrites: directory.clientPersonalWrites && ['owner', 'admin'].includes(user.role), trainerApprovalWrites: directory.trainerApprovalWrites && ['owner', 'admin'].includes(user.role), packageWrites: Boolean(directory.packagePolicy) && ['owner', 'admin'].includes(user.role) } }
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
      if (service === 'clientService' && operation === 'saveAssessment') return clientAssessments.save(input, expectedGeneration)
      if (service === 'clientService' && operation === 'reactivate') return clientReactivation.save(input, expectedGeneration)
      if (service === 'clientService' && operation === 'deactivate') return clientDeactivation.save(input, expectedGeneration)
      if (service === 'clientService' && operation === 'create') return clientCreation.create(input, expectedGeneration)
      if (service === 'trainerService' && operation === 'isSelectableForAvailability') {
        await actionSession(expectedGeneration)
        return trainerSelectableForAvailability(input.trainer)
      }
      if (service === 'trainerService' && operation === 'reactivate') return trainerReactivation.save(input, expectedGeneration)
      if (service === 'trainerService' && operation === 'update') {
        if (input.patch && Object.keys(input.patch).length === 1 && Object.hasOwn(input.patch, 'email')) return requestEmailChange(input, expectedGeneration)
        if (input.patch && Object.hasOwn(input.patch, 'rates')) return saveTrainerRates(input, expectedGeneration)
        return saveTrainerDetails(input, expectedGeneration)
      }
      if (service === 'trainerService' && operation === 'updateAutonomy') return saveTrainerApprovals(input, expectedGeneration)
      if (service === 'clientService' && operation === 'update') {
        if (input.patch && Object.keys(input.patch).length && Object.keys(input.patch).every(key => ['remarks', 'healthNotes'].includes(key))) return saveClientNotes(input, expectedGeneration)
        return saveClientDetails(input, expectedGeneration)
      }
      if (service === 'requestService' && operation === 'cancel') return personalMessages.cancel(input, expectedGeneration)
      if (service === 'messageService' && operation === 'dismissRenewal') return personalMessages.dismiss(input, expectedGeneration)
      if (service === 'messageService' && ['markRead', 'markUnread'].includes(operation)) return personalMessages.save(input, operation === 'markRead', expectedGeneration)
      if (service === 'contentService') return content.save(input, expectedGeneration)
      if (service === 'packageService') return savePackage(input, expectedGeneration)
      if (service === 'staffService' && operation === 'createAdmin') {
        const { user, sessionGeneration } = await actionSession(expectedGeneration)
        if (user.role !== 'owner') throw new ApiError('forbidden', 'Only the owner can create an Admin.', 403)
        const result = await http.post('/api/staff/admins', input.body, { csrf: true, idempotencyKey: input.requestKey, expectedGeneration: sessionGeneration })
        if (result?.role !== 'admin' || !['pending', 'sending', 'sent', 'unknown'].includes(result.invitation) || !['id', 'name', 'email'].every(key => typeof result[key] === 'string' && result[key]) || Object.keys(result).some(key => !['id', 'name', 'email', 'role', 'invitation'].includes(key))) throw new ApiError('API_RESPONSE', 'Account setup could not be verified. Check the same request again.')
        return result
      }
      const { user, sessionGeneration } = await http.session()
      const { data, clientNoteWrites } = directorySnapshot(await http.get('/api/directory', { expectedGeneration: sessionGeneration }), user)
      const rows = data[service === 'clientService' ? 'clients' : 'trainers']
      if (operation === 'getById') {
        const row = rows.find(row => row.id === input.id) ?? null
        if (row && service === 'clientService' && clientNoteWrites) return withClientNotes(row, await http.get(`/api/clients/${input.id}/notes`, { expectedGeneration: sessionGeneration }))
        return row
      }
      return operation === 'getActive' ? rows.filter(row => row.status === 'active') : rows
    },
    async reset() { throw new ApiError('OPERATION_UNAVAILABLE', 'Demo controls are unavailable for this account.') },
  }
}

function validateChallenge(result) {
  if (!['NEW_PASSWORD_REQUIRED', 'MFA_SETUP', 'SOFTWARE_TOKEN_MFA'].includes(result?.challenge) || !Number.isFinite(Date.parse(result.expiresAt)) || (result.challenge === 'MFA_SETUP' && !/^[A-Z2-7]+$/.test(result.secretCode ?? ''))) throw new ApiError('API_RESPONSE', 'The sign-in response could not be verified. Start again.')
  return result
}
