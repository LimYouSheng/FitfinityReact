// The application boundary accepts one named input object per operation.
// Nested drafts remain the responsibility of the domain validators. Actor identity
// is never part of an input; adapters obtain it from their authenticated session.
const contract = (fields, access, result, api = false) => Object.freeze({ fields: Object.freeze(fields), access, result, api })

export const PORTAL_CONTRACTS = Object.freeze({
  staffService: Object.freeze({
    createAdmin: contract({ 'body': 'object', 'requestKey': 'string' }, 'owner', 'AdminInvitation', true),
  }),
  contentService: Object.freeze({
    save: contract({ 'id?': 'string', 'expectedVersion?': 'number', 'draft': 'object' }, 'operations', 'ContentEntry'),
  }),
  clientService: Object.freeze({
    getAll: contract({}, 'authenticated', 'Client[]', true),
    getById: contract({ 'id': 'string' }, 'authenticated', 'Client | null', true),
    create: contract({ 'draft': 'object' }, 'operations', 'Client'),
    renewPackage: contract({ 'id': 'string', 'draft': 'object' }, 'operations', 'Client'),
    deactivatePackage: contract({ 'id': 'string', 'options': 'object' }, 'operations', 'Client'),
    deletePackageSessions: contract({ 'id': 'string', 'options': 'object' }, 'operations', 'Client'),
    update: contract({ 'id': 'string', 'patch': 'object' }, 'clientEdit', 'Client'),
    saveAssessment: contract({ 'id': 'string', 'assessment': 'object' }, 'operations', 'AssessmentRecord'),
    saveFixedWeeklySchedule: contract({ 'id': 'string', 'slots': 'array' }, 'assignedClient', 'ScheduleResult<Client>'),
    reassignTrainer: contract({ 'id': 'string', 'draft': 'object' }, 'operations', 'Client'),
    recordProgressReportAction: contract({ 'id': 'string', 'action': 'object' }, 'reportClient', 'ProgressReportEvent'),
    progressReportHistory: contract({ 'id': 'string', 'packageId?': 'string' }, 'operations', 'ProgressReportEvent[]'),
    deactivate: contract({ 'id': 'string' }, 'operations', 'Client'),
    reactivate: contract({ 'id': 'string', 'dates?': 'object', 'expected?': 'object' }, 'operations', 'Client'),
  }),
  trainerService: Object.freeze({
    create: contract({ 'draft': 'object' }, 'trainerCreate', 'Trainer'),
    saveAvailability: contract({ 'id': 'string', 'blocks': 'array' }, 'assignedTrainer', 'ScheduleResult<Trainer>'),
    getAll: contract({}, 'authenticated', 'Trainer[]', true),
    getActive: contract({}, 'authenticated', 'Trainer[]', true),
    getById: contract({ 'id': 'string' }, 'authenticated', 'Trainer | null', true),
    isSelectableForAvailability: contract({ 'trainer': 'object' }, 'authenticated', 'boolean'),
    update: contract({ 'id': 'string', 'patch': 'object' }, 'trainerEdit', 'Trainer'),
    updateAutonomy: contract({ 'id': 'string', 'approvalNeeded': 'object' }, 'operations', 'Trainer'),
    deactivate: contract({ 'id': 'string', 'replacements?': 'object' }, 'operations', 'Trainer'),
    reactivate: contract({ 'id': 'string' }, 'operations', 'Trainer'),
  }),
  sessionService: Object.freeze({
    previewPostponement: contract({ 'sessionId': 'string', 'lastSlot?': 'object' }, 'session', 'PostponementPreview'),
    postpone: contract({ 'sessionId': 'string', 'expected': 'string', 'requestKey': 'string', 'lastSlot?': 'object' }, 'session', 'ScheduleResult<Session>'),
    loadVideo: contract({ 'sessionId': 'string', 'exerciseId': 'string' }, 'session', 'Blob | null'),
    saveVideo: contract({ 'sessionId': 'string', 'exerciseId': 'string', 'file': 'blob', 'metadata': 'object' }, 'session', 'MediaReference'),
    removeVideo: contract({ 'sessionId': 'string', 'exerciseId': 'string' }, 'session', 'void'),
    updateDetails: contract({ 'sessionId': 'string', 'patch': 'object' }, 'operationsSession', 'Session'),
    requestTimeChange: contract({ 'sessionId': 'string', 'patch': 'object' }, 'session', 'ScheduleResult<Session>'),
    requestTrainerChange: contract({ 'sessionId': 'string', 'replacementTrainerId': 'string' }, 'session', 'ScheduleResult<Session>'),
    saveExercisePlan: contract({ 'sessionId': 'string', 'items': 'array' }, 'session', 'Session'),
    previousPlanFor: contract({ 'sessionId': 'string' }, 'session', 'ExercisePlanItem[]'),
    copyPreviousPlan: contract({ 'sessionId': 'string' }, 'session', 'Session'),
    saveOutcome: contract({ 'sessionId': 'string', 'outcome': 'object' }, 'session', 'Session'),
    saveClientSummary: contract({ 'sessionId': 'string', 'summary': 'string' }, 'session', 'Session'),
    markWhatsAppOpened: contract({ 'sessionId': 'string' }, 'session', 'Session'),
    acknowledge: contract({ 'sessionId': 'string', 'acknowledgement': 'object' }, 'session', 'AcknowledgementResult'),
  }),
  packageService: Object.freeze({
    save: contract({ 'id?': 'string', 'expectedVersion?': 'number', 'draft': 'object' }, 'operations', 'PackageDefinition'),
  }),
  exerciseLibraryService: Object.freeze({
    loadMedia: contract({ 'id': 'string' }, 'authenticated', 'Blob | null'),
    getAll: contract({}, 'authenticated', 'LibraryExercise[]'),
    save: contract({ 'id?': 'string', 'expectedVersion?': 'number', 'draft': 'object', 'mediaFile?': 'blob', 'removeMedia?': 'boolean' }, 'operations', 'LibraryExercise'),
  }),
  messageService: Object.freeze({
    dismissRenewal: contract({ 'id': 'string' }, 'message', 'PersonalMessage'),
    undo: contract({ 'id': 'string' }, 'message', 'SessionUndoResult'),
    markRead: contract({ 'id': 'string' }, 'message', 'PersonalMessage'),
    markUnread: contract({ 'id': 'string' }, 'message', 'PersonalMessage'),
  }),
  requestService: Object.freeze({
    resolve: contract({ 'id': 'string', 'decision': 'string' }, 'operations', 'Message'),
    cancel: contract({ 'id': 'string' }, 'authenticated', 'Message'),
  }),
  remunerationService: Object.freeze({
    list: contract({}, 'remuneration', 'RemunerationCycle[]'),
    detail: contract({ 'cycle': 'string', 'trainerId': 'string' }, 'remuneration', 'RemunerationRecord'),
    approve: contract({ 'cycle': 'string', 'trainerId': 'string', 'revision': 'string' }, 'approveRemuneration', 'RemunerationApproval'),
  }),
})

export const AUTH_CONTRACTS = Object.freeze({
  signIn: Object.freeze({ fields: Object.freeze({ 'identifier': 'string', 'password': 'string' }), result: 'User | AuthChallenge', adapter: 'both' }),
  challenge: Object.freeze({ fields: Object.freeze({ 'code?': 'string', 'newPassword?': 'string' }), result: 'AuthChallenge | AuthSession', adapter: 'api' }),
  forgotPassword: Object.freeze({ fields: Object.freeze({ 'identifier': 'string' }), result: 'PasswordRecovery', adapter: 'api' }),
  resetPassword: Object.freeze({ fields: Object.freeze({ 'code': 'string', 'newPassword': 'string', 'confirmation?': 'string' }), result: 'PasswordReset', adapter: 'api' }),
  signOut: Object.freeze({ fields: Object.freeze({}), result: 'void | SignedOut', adapter: 'both' }),
  switchDemoIdentity: Object.freeze({ fields: Object.freeze({ 'userId': 'string' }), result: 'User', adapter: 'mock' }),
  changePassword: Object.freeze({ fields: Object.freeze({ 'currentPassword': 'string', 'newPassword': 'string', 'confirmation?': 'string' }), result: 'PasswordChange', adapter: 'both' }),
})

export class PortalContractError extends Error {
  constructor(code, message) { super(message); this.name = 'PortalContractError'; this.code = code }
}

const record = value => value !== null && typeof value === 'object' && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value))
const invalid = message => { throw new PortalContractError('INVALID_REQUEST', message) }
const unavailable = () => { throw new PortalContractError('OPERATION_UNAVAILABLE', 'This action is not enabled in this environment yet.') }

function envelope(request, keys) {
  if (!record(request) || Object.keys(request).some(key => !keys.includes(key))) invalid('Use a named service request without actor or context fields.')
}

export function validateInput(input, fields) {
  if (!record(input)) invalid('Service input must be a named object.')
  const allowed = new Set(Object.keys(fields).map(key => key.replace(/\?$/, '')))
  if (Object.keys(input).some(key => !allowed.has(key))) invalid('Service input contains an unsupported field. Identity comes from the authenticated session.')
  for (const [field, type] of Object.entries(fields)) {
    const optional = field.endsWith('?'), key = optional ? field.slice(0, -1) : field
    const value = Object.hasOwn(input, key) ? input[key] : undefined
    if (optional && value == null) continue
    const valid = type === 'array' ? Array.isArray(value) : type === 'object' ? record(value)
      : type === 'blob' ? value instanceof Blob : typeof value === type && (type !== 'number' || Number.isFinite(value))
    if (!valid) invalid(`Service input ${key} must be ${type}.`)
  }
  return input
}

export function portalRequest(request, adapter) {
  envelope(request, ['service', 'operation', 'input'])
  const { service, operation } = request
  if (typeof service !== 'string' || typeof operation !== 'string' || !Object.hasOwn(PORTAL_CONTRACTS, service) || !Object.hasOwn(PORTAL_CONTRACTS[service], operation)) unavailable()
  const definition = PORTAL_CONTRACTS[service][operation]
  if (adapter === 'api' && !definition.api) unavailable()
  return { service, operation, input: validateInput(request.input, definition.fields), definition }
}

export function authRequest(request, adapter) {
  envelope(request, ['operation', 'input'])
  const { operation } = request
  if (typeof operation !== 'string' || !Object.hasOwn(AUTH_CONTRACTS, operation)) unavailable()
  const definition = AUTH_CONTRACTS[operation]
  if (definition.adapter !== 'both' && definition.adapter !== adapter) unavailable()
  const input = validateInput(request.input, definition.fields)
  if (operation === 'challenge' && [input.code, input.newPassword].filter(value => value !== undefined).length !== 1) invalid('Provide one challenge answer.')
  return { operation, input }
}
