import { profileRecoveryCommands } from './apiProfileRecovery.js'
import { sessionMediaCommands } from './apiSessionMedia.js'
import { packageActionCommands } from './apiPackageActions.js'
import { messageUndoCommands } from './apiMessageUndo.js'
import { exerciseLibraryCommands } from './apiExerciseLibrary.js'
import { sessionHandoffCommands } from './apiSessionHandoffs.js'
import { remunerationCommands } from './apiRemuneration.js'
import { progressReportCommands } from './apiProgressReports.js'
import { sessionAcknowledgementCommands } from './apiSessionAcknowledgements.js'
import { sessionSummaryCommands } from './apiSessionSummaries.js'
import { sessionOutcomeCommands, readClientProgress } from './apiSessionOutcomes.js'
import { sessionPlanCommands } from './apiSessionPlans.js'
import { sessionChangeCommands } from './apiSessionChanges.js'
import { sessionPostponementCommands } from './apiSessionPostponement.js'
import { sessionBookingCommands } from './apiSessionBooking.js'
import { sessionCalendar, readSessionDetail, readLimitedSessionClient } from './apiSessionReads.js'
import { clientWeeklyScheduleCommands } from './apiClientWeeklySchedule.js'
import { trainerDeactivationCommands } from './apiTrainerDeactivation.js'
import { clientAssignmentCommands } from './apiClientAssignment.js'
import { trainerAvailabilityCommands } from './apiTrainerAvailability.js'
import { clientReactivationCommands, packageReactivationCommands } from './apiClientReactivation.js'
import { clientDeactivationCommands } from './apiClientDeactivation.js'
import { messageCommands } from './apiMessages.js'
import { contentCommands } from './apiContent.js'
import { assessmentCommands } from './apiAssessments.js'
import { trainerSelectableForAvailability } from '../app/status.js'
import { clientCreationCommands } from './apiClientCreation.js'
import { trainerCreationCommands } from './apiTrainerCreation.js'
import { clientRenewalCommands } from './apiClientRenewal.js'
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
  const transport = createApiClient(options)
  let writeRevision = 0
  const http = { ...transport, async post(...args) {
    try { return await transport.post(...args) }
    // Even an interrupted response may have committed. A later refresh must not
    // reuse a snapshot that began before this command settled.
    finally { writeRevision++ }
  } }
  let policyPromise
  let loading
  let loadingGeneration
  let loadingRevision
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
  const sessionPostponement = sessionPostponementCommands(http, actionSession)
  const sessionPlans = sessionPlanCommands(http, actionSession)
  const sessionMedia = sessionMediaCommands(http, actionSession, options.fetchImpl)
  const sessionHandoffs = sessionHandoffCommands(http, actionSession)
  const exerciseLibrary = exerciseLibraryCommands(http, actionSession, options.fetchImpl)
  const remuneration = remunerationCommands(http, actionSession)
  const progressReports = progressReportCommands(http, actionSession)
  const sessionAcknowledgements = sessionAcknowledgementCommands(http, actionSession)
  const sessionSummaries = sessionSummaryCommands(http, actionSession)
  const sessionOutcomes = sessionOutcomeCommands(http, actionSession)
  const sessionChanges = sessionChangeCommands(http, actionSession)
  const sessionBooking = sessionBookingCommands(http, actionSession)
  const clientWeeklySchedule = clientWeeklyScheduleCommands(http, actionSession)
  const trainerDeactivation = trainerDeactivationCommands(http, actionSession)
  const trainerReactivation = trainerReactivationCommands(http, actionSession)
  const saveTrainerDetails = trainerDetailCommands(http, actionSession)
  const { request: requestEmailChange, ...emailMethods } = emailCommands(http, actionSession)
  const saveTrainerApprovals = trainerApprovalCommands(http, actionSession)
  const saveClientNotes = clientNoteCommands(http, actionSession)
  const saveClientDetails = clientDetailCommands(http, actionSession)
  const clientReactivation = clientReactivationCommands(http, actionSession)
  const clientDeactivation = clientDeactivationCommands(http, actionSession)
  const trainerAvailability = trainerAvailabilityCommands(http, actionSession)
  const personalMessages = messageCommands(http, actionSession)
  const content = contentCommands(http, actionSession)
  const savePackage = packageCommands(http, actionSession)
  const clientAssessments = assessmentCommands(http, actionSession)
  const clientCreation = clientCreationCommands(http, actionSession)
  const clientAssignment = clientAssignmentCommands(http, actionSession)
  const trainerCreation = trainerCreationCommands(http, actionSession)
  const clientRenewal = clientRenewalCommands(http, actionSession)
  const messageUndo = messageUndoCommands(http, actionSession)
  const packageActions = packageActionCommands(http, actionSession)
  const packageReactivation = packageReactivationCommands(http, actionSession)
  const profileRecovery = profileRecoveryCommands({
    notes: { label: 'Notes', command: saveClientNotes.recovery },
    clientDetails: { label: 'Client Information', command: saveClientDetails.recovery },
    trainerDetails: { label: 'Trainer Information', command: saveTrainerDetails.recovery },
    trainerRates: { label: 'Trainer Rates', command: saveTrainerRates.recovery },
    trainerApprovals: { label: 'Approval Settings', command: saveTrainerApprovals.recovery },
    packages: { label: 'Package Setup', command: savePackage },
  })
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
    async recoverProfileSaves({ kind } = {}, { expectedGeneration = http.generation() } = {}) { return profileRecovery.read(expectedGeneration, kind) },
    async resumeProfileSave({ kind }, { expectedGeneration = http.generation() } = {}) { return profileRecovery.resume(kind, expectedGeneration) },
    async readContent(_input, { expectedGeneration = http.generation() } = {}) { return content.read(expectedGeneration) },
    async readClientNotes(client, { expectedGeneration = http.generation() } = {}) {
      if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(client?.id) || !Number.isSafeInteger(client.version) || client.version < 1 || !Array.isArray(client.people)) throw new ApiError('INVALID_REQUEST', 'Reload the client before reading notes.')
      const { sessionGeneration } = await actionSession(expectedGeneration)
      // The scoped endpoint enforces current authority; the version check rejects stale directory rows.
      return withClientNotes(client, await http.get(`/api/clients/${client.id}/notes`, { expectedGeneration: sessionGeneration }))
    },
    async readClientAssessments(client, { expectedGeneration = http.generation() } = {}) {
      return clientAssessments.read(client, expectedGeneration)
    },
    async readAssessmentHistory(input, { expectedGeneration = http.generation() } = {}) {
      return clientAssessments.history(input, expectedGeneration)
    },
    async reviewPackageAction(input, { expectedGeneration = http.generation() } = {}) { return packageActions.review(input, expectedGeneration) },
    async reconcilePackageAction(input, { expectedGeneration = http.generation() } = {}) { return packageActions.reconcile(expectedGeneration) },
    async previewPackageReactivation(input, { expectedGeneration = http.generation() } = {}) { return packageReactivation.review(input, expectedGeneration) },
    async previewPackageReactivationDates(input, { expectedGeneration = http.generation() } = {}) { return packageReactivation.preview(input, expectedGeneration) },
    async previewClientReactivation(input, { expectedGeneration = http.generation() } = {}) { return clientReactivation.review(input, expectedGeneration) },
    async previewClientReactivationDates(input, { expectedGeneration = http.generation() } = {}) { return clientReactivation.preview(input, expectedGeneration) },
    async previewClientDeactivation(input, { expectedGeneration = http.generation() } = {}) {
      return clientDeactivation.review(input, expectedGeneration)
    },
    async previewTrainerReactivation(input, { expectedGeneration = http.generation() } = {}) {
      return trainerReactivation.review(input, expectedGeneration)
    },
    async reviewClientRenewal(input, { expectedGeneration = http.generation() } = {}) { return clientRenewal.review(input, expectedGeneration) },
    async previewClientRenewalMatches(input, { expectedGeneration = http.generation() } = {}) { return clientRenewal.preview(input, expectedGeneration) },
    async reviewSessionAcknowledgement(input, { expectedGeneration = http.generation() } = {}) { return sessionAcknowledgements.review(input, expectedGeneration) },
    async reviewSessionSummary(input, { expectedGeneration = http.generation() } = {}) { return sessionSummaries.review(input, expectedGeneration) },
    async reviewSessionOutcome(input, { expectedGeneration = http.generation() } = {}) { return sessionOutcomes.review(input, expectedGeneration) },
    async readClientProgress(input, { expectedGeneration = http.generation() } = {}) { return readClientProgress(http, actionSession, input, expectedGeneration) },
    async reviewSessionMedia(input, { expectedGeneration = http.generation() } = {}) { return sessionMedia.review(input, expectedGeneration) },
    async reconcileSessionMedia(input, { expectedGeneration = http.generation() } = {}) { return sessionMedia.recover(input, expectedGeneration) },
    async resumeSessionMedia(input, { expectedGeneration = http.generation() } = {}) { return sessionMedia.resume(input, expectedGeneration) },
    async reviewSessionPlan(input, { expectedGeneration = http.generation() } = {}) { return sessionPlans.review(input, expectedGeneration) },
    async reviewSessionChange(input, { expectedGeneration = http.generation() } = {}) { return sessionChanges.review(input, expectedGeneration) },
    async reviewSessionBooking(input, { expectedGeneration = http.generation() } = {}) { return sessionBooking.review(input, expectedGeneration) },
    async readSessionClient(input, { expectedGeneration = http.generation() } = {}) { return readLimitedSessionClient(http, actionSession, input, expectedGeneration) },
    async readSessionDetails(input, { expectedGeneration = http.generation() } = {}) { return readSessionDetail(http, actionSession, input, expectedGeneration) },
    async reviewClientWeeklySchedule(input, { expectedGeneration = http.generation() } = {}) { return clientWeeklySchedule.review(input, expectedGeneration) },
    async previewClientWeeklySchedule(input, { expectedGeneration = http.generation() } = {}) { return clientWeeklySchedule.preview(input, expectedGeneration) },
    async reviewTrainerDeactivation(input, { expectedGeneration = http.generation() } = {}) { return trainerDeactivation.review(input, expectedGeneration) },
    async previewTrainerDeactivation(input, { expectedGeneration = http.generation() } = {}) { return trainerDeactivation.preview(input, expectedGeneration) },
    async previewClientAssignment(input, { expectedGeneration = http.generation() } = {}) { return clientAssignment.review(input, expectedGeneration) },
    async previewClientMatches(draft, { expectedGeneration = http.generation() } = {}) {
      return clientCreation.preview(draft, expectedGeneration)
    },
    async load() {
      if (loading && loadingGeneration === http.generation() && loadingRevision === writeRevision) return loading
      loadingGeneration = http.generation()
      loadingRevision = writeRevision
      const operation = (async () => {
        const authPolicy = await policy()
        const snapshot = { user: null, data: null, accounts: [], policy: { ...authPolicy, timeZone: 'Asia/Singapore' }, capabilities: { demoControls: false, staffWorkflows: false, realAuthentication: true } }
        let verifiedIdentity
        try {
          const { user, sessionGeneration } = await http.session()
          verifiedIdentity = { id: user.id, role: user.role, sessionGeneration }
          const clientWeeklySchedulePending = await clientWeeklySchedule.reconcile(sessionGeneration)
          const trainerDeactivationPending = await trainerDeactivation.reconcile(sessionGeneration)
          const clientAssignmentPending = await clientAssignment.reconcile(sessionGeneration)
          const packageReactivationPending = await packageReactivation.recover(sessionGeneration)
          const renewalRecovery = await clientRenewal.recover(sessionGeneration)
          const sessionChangePending = user.role === 'trainer' ? sessionChanges.pendingInput(sessionGeneration) : null
          const directory = directorySnapshot(await http.get('/api/directory', { expectedGeneration: sessionGeneration }), user)
          const availabilityRecovery = await trainerAvailability.recover(sessionGeneration)
          const clientReactivationPending = await clientReactivation.recover(sessionGeneration)
          const clientDeactivationPending = await clientDeactivation.recover(sessionGeneration)
          // Recovery that can change domain state stays ordered above. These independent reads
          // share a verified generation and publish only as a complete, validated snapshot.
          const [calendar, library, inbox] = await Promise.all([
            directory.sessionReads ? http.get('/api/session-calendar', { expectedGeneration: sessionGeneration }).then(value => sessionCalendar(value, user)) : {},
            directory.exerciseLibraryWorkflows ? exerciseLibrary.catalogue(sessionGeneration) : null,
            directory.personalMessages ? personalMessages.read(sessionGeneration) : null,
          ])
          const data = { ...directory.data, ...calendar, ...(library ? { exerciseLibrary: library.items } : {}), ...(inbox ? { messages: inbox.messages } : {}) }
          return { ...snapshot, ...directory, exerciseLibraryPending: exerciseLibrary.pendingInput(sessionGeneration), remunerationPending: remuneration.pendingInput(sessionGeneration), progressReportPending: progressReports.pendingInput(sessionGeneration), sessionAcknowledgementPending: sessionAcknowledgements.pendingInput(sessionGeneration), sessionSummaryPending: sessionSummaries.pendingInput(sessionGeneration), sessionOutcomePending: sessionOutcomes.pendingInput(sessionGeneration), sessionPlanPending: sessionPlans.pendingInput(sessionGeneration), sessionChangePending, data, clientWeeklySchedulePending, trainerDeactivationPending, clientAssignmentPending, packageReactivationPending, clientRenewalPending: renewalRecovery.pending, clientRenewalRecovered: renewalRecovery.recovered, clientDeactivationPending, clientReactivationPending, trainerAvailabilityPending: availabilityRecovery.pending, trainerAvailabilityRecovered: availabilityRecovery.recovered, ...(inbox ? { messageReadPending: inbox.pending, renewalDismissalPending: inbox.dismissalPending, requestCancellationPending: inbox.cancellationPending, requestResolutionPending: inbox.resolutionPending } : {}), user, sessionGeneration, policy: { ...snapshot.policy, ...(library ? { exerciseCategories: library.categories } : {}), ...directory.packagePolicy, ...directory.trainerProfilePolicy, ...directory.clientOnboardingPolicy, ...directory.trainerOnboardingPolicy }, capabilities: { ...snapshot.capabilities, sessionUndoWrites: directory.sessionUndoWrites, sessionMediaWorkflows: directory.sessionMediaWorkflows, packageActionWrites: directory.packageActionWrites && ['owner', 'admin'].includes(user.role), staffWorkflows: true, directoryReadOnly: true, exerciseLibraryWorkflows: directory.exerciseLibraryWorkflows, remunerationWorkflows: directory.remunerationWorkflows && user.role !== 'admin', sessionPlanWrites: directory.sessionPlanWrites, sessionOutcomeWrites: directory.sessionOutcomeWrites, progressReportWrites: directory.progressReportWrites, sessionAcknowledgementWrites: directory.sessionAcknowledgementWrites, sessionSummaryWrites: directory.sessionSummaryWrites, sessionChangeWrites: directory.sessionChangeWrites && user.role === 'trainer', sessionPostponementWrites: directory.sessionPostponementWrites, sessionBookingWrites: directory.sessionBookingWrites && ['owner', 'admin'].includes(user.role), sessionReads: directory.sessionReads, clientWeeklyScheduleWrites: directory.clientWeeklyScheduleWrites, trainerDeactivationWrites: directory.trainerDeactivationWrites && ['owner', 'admin'].includes(user.role), clientAssignmentWrites: directory.clientAssignmentWrites && ['owner', 'admin'].includes(user.role), trainerCreation: directory.trainerCreation && ['owner', 'admin'].includes(user.role), packageReactivationWrites: directory.packageReactivationWrites && ['owner', 'admin'].includes(user.role), clientRenewalWrites: directory.clientRenewalWrites && ['owner', 'admin'].includes(user.role), clientReactivationWrites: directory.clientReactivationWrites && ['owner', 'admin'].includes(user.role), clientDeactivationWrites: directory.clientDeactivationWrites && ['owner', 'admin'].includes(user.role), personalMessages: directory.personalMessages, trainerAvailabilityWrites: directory.trainerAvailabilityWrites && user.role === 'trainer', requestResolutionWrites: directory.personalMessages && directory.requestResolutionWrites && ['owner', 'admin'].includes(user.role), requestCancellationWrites: directory.personalMessages && directory.requestCancellationWrites && user.role === 'trainer', renewalDismissalWrites: directory.personalMessages && directory.renewalDismissalWrites, contentWorkflows: directory.contentWorkflows && ['owner', 'admin'].includes(user.role), clientAssessmentWorkflows: directory.clientAssessmentWorkflows && ['owner', 'admin'].includes(user.role), clientCreation: directory.clientCreation && ['owner', 'admin'].includes(user.role), trainerReactivationWrites: directory.trainerReactivationWrites && ['owner', 'admin'].includes(user.role), trainerPersonalWrites: directory.trainerPersonalWrites && ['owner', 'admin'].includes(user.role), trainerEmailWrites: directory.trainerEmailWrites, trainerEmailCorrections: directory.trainerEmailCorrections, trainerRateWrites: directory.trainerRateWrites && user.role === 'owner', clientNoteWrites: directory.clientNoteWrites, clientPersonalWrites: directory.clientPersonalWrites && ['owner', 'admin'].includes(user.role), trainerApprovalWrites: directory.trainerApprovalWrites && ['owner', 'admin'].includes(user.role), packageWrites: Boolean(directory.packagePolicy) && ['owner', 'admin'].includes(user.role) } }
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
      if (service === 'exerciseLibraryService' && operation === 'save') return exerciseLibrary.save(input, expectedGeneration)
      if (service === 'exerciseLibraryService' && operation === 'getAll') return (await exerciseLibrary.catalogue(expectedGeneration)).items
      if (service === 'exerciseLibraryService' && operation === 'loadMedia') return exerciseLibrary.loadMedia(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'previewPostponement') return sessionPostponement.review(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'postpone') return sessionPostponement.save(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'previousPlanFor') return sessionPlans.previous(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'copyPreviousPlan') return sessionPlans.copy(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'markWhatsAppOpened') return sessionHandoffs.mark(input, expectedGeneration)
      if (service === 'remunerationService' && operation === 'list') return remuneration.list(expectedGeneration)
      if (service === 'remunerationService' && operation === 'detail') return remuneration.detail(input, expectedGeneration)
      if (service === 'remunerationService' && operation === 'approve') return remuneration.approve(input, expectedGeneration)
      if (service === 'clientService' && operation === 'recordProgressReportAction') return progressReports.record(input, expectedGeneration)
      if (service === 'clientService' && operation === 'progressReportHistory') return progressReports.history(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'acknowledge') return sessionAcknowledgements.save(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'saveClientSummary') return sessionSummaries.save(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'saveOutcome') return sessionOutcomes.save(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'loadVideo') return sessionMedia.load(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'saveVideo') return sessionMedia.save(input, expectedGeneration)
      if (service === 'sessionService' && operation === 'removeVideo') return sessionMedia.save(input, expectedGeneration, true)
      if (service === 'sessionService' && operation === 'saveExercisePlan') return sessionPlans.save(input, expectedGeneration)
      if (service === 'sessionService' && ['requestTimeChange', 'requestTrainerChange'].includes(operation)) return sessionChanges.save({ sessionId: input.sessionId, reviewed: input.reviewed, kind: operation === 'requestTimeChange' ? 'time' : 'trainer', patch: operation === 'requestTimeChange' ? input.patch : { replacementTrainerId: input.replacementTrainerId } }, expectedGeneration)
      if (service === 'sessionService' && operation === 'updateDetails') return sessionBooking.save(input, expectedGeneration)
      if (service === 'clientService' && operation === 'saveFixedWeeklySchedule') return clientWeeklySchedule.save(input, expectedGeneration)
      if (service === 'clientService' && operation === 'reassignTrainer') return clientAssignment.save({ id: input.id, reviewed: input.draft.reviewed, trainerId: input.draft.trainerId }, expectedGeneration)
      if (service === 'clientService' && operation === 'saveAssessment') return clientAssessments.save(input, expectedGeneration)
      if (service === 'clientService' && operation === 'reactivate') return clientReactivation.save(input, expectedGeneration)
      if (service === 'clientService' && operation === 'deactivate') return clientDeactivation.save(input, expectedGeneration)
      if (service === 'messageService' && operation === 'undo') return messageUndo(input, expectedGeneration)
      if (service === 'clientService' && ['deactivatePackage', 'deletePackageSessions'].includes(operation)) return packageActions.save({ id: input.id, ...input.options, operation: operation === 'deactivatePackage' ? 'deactivate' : 'delete_sessions' }, expectedGeneration)
      if (service === 'clientService' && operation === 'reactivatePackage') return packageReactivation.save({ id: input.id, ...input.options }, expectedGeneration)
      if (service === 'clientService' && operation === 'renewPackage') return clientRenewal.save(input, expectedGeneration)
      if (service === 'trainerService' && operation === 'create') return trainerCreation.create(input, expectedGeneration)
      if (service === 'clientService' && operation === 'create') return clientCreation.create(input, expectedGeneration)
      if (service === 'trainerService' && operation === 'isSelectableForAvailability') {
        await actionSession(expectedGeneration)
        return trainerSelectableForAvailability(input.trainer)
      }
      if (service === 'trainerService' && operation === 'deactivate') return trainerDeactivation.save(input, expectedGeneration)
      if (service === 'trainerService' && operation === 'reactivate') return trainerReactivation.save(input, expectedGeneration)
      if (service === 'trainerService' && operation === 'update') {
        if (input.patch && Object.hasOwn(input.patch, 'email') && Object.keys(input.patch).every(key => ['email', 'supersedes'].includes(key))) return requestEmailChange(input, expectedGeneration)
        if (input.patch && Object.hasOwn(input.patch, 'rates')) return saveTrainerRates(input, expectedGeneration)
        return saveTrainerDetails(input, expectedGeneration)
      }
      if (service === 'trainerService' && operation === 'updateAutonomy') return saveTrainerApprovals(input, expectedGeneration)
      if (service === 'clientService' && operation === 'update') {
        if (input.patch && Object.keys(input.patch).length && Object.keys(input.patch).every(key => ['remarks', 'healthNotes'].includes(key))) return saveClientNotes(input, expectedGeneration)
        return saveClientDetails(input, expectedGeneration)
      }
      if (service === 'trainerService' && operation === 'saveAvailability') return trainerAvailability.save(input, expectedGeneration)
      if (service === 'requestService' && operation === 'resolve') return personalMessages.resolve(input, expectedGeneration)
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
