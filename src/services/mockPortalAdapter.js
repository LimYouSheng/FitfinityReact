import { managesOperations } from '../app/permissions.js'
import { adminProjection } from '../app/adminProjection.js'
import { renewalStatus } from '../app/renewals.js'
import { businessClock } from '../app/clock.js'
import { payCycle } from '../app/remuneration.js'
import { authService, MOCK_SESSION_KEY } from './authService.js'
import { bindSessionMutationActor, mutationForMessage } from './sessionMutation.js'
import { mockDb, delay } from './mockDb.js'
import { mockPolicy, mockAccountPassword } from '../data/mockPolicy.js'
import { exerciseLibraryService } from './exerciseLibraryService.js'
import { remunerationService } from './remunerationService.js'
import { pruneExpiredExerciseVideos } from './exerciseVideoRetention.js'

import { mockPortalOperations } from './mockPortalOperations.js'
import { portalRequest, authRequest } from './portalContracts.js'
import { authorizePortalRequest } from './portalAuthorization.js'
import { messageForUser, messageVisibleTo } from '../app/messageInbox.js'

const accountOperations = {
  signIn: input => authService.signIn(input),
  signOut: () => authService.signOut(),
  switchDemoIdentity: ({ userId }) => authService.switchDemoIdentity(userId),
  changePassword: input => authService.changePassword(input),
}

// This adapter owns mock persistence. An API adapter implements load/session/invoke.
export const mockPortalAdapter = {
  async load() {
    await delay(20)
    mockDb.reload()
    await pruneExpiredExerciseVideos(new Date(), { background: true })
    const db = mockDb.read()
    const user = authService.current()
    const policy = structuredClone(db.settings ?? mockPolicy)
    if (user?.role === 'admin') { delete policy.trainerRates; delete policy.remuneration }
    const accounts = db.users.filter(item => (item.status ?? 'active') === 'active').map(({ id, name }) => ({ id, name }))
    if (!user) return { user: null, capabilities: { demoControls: true }, policy, accounts, demoPassword: mockAccountPassword, data: null }
    // Report audit entries are fetched through the owner-only history operation.
    delete db.progressReportEvents
    delete db.progressMigrationArchive
    delete db.staffInvitations
    // Give a requester their original proposal without making the UI fetch owner-only messages.
    // Existing receipts acquire this read projection without rewriting stored history.
    const requests = new Map(db.messages.filter(message => message.recipientRole === 'owner' && message.request).map(message => [message.id, message]))
    db.messages = db.messages.map(message => {
      const original = requests.get(message.requestId)
      if (user.role !== 'trainer' || message.recipientTrainerId !== user.trainerId || original?.request.trainerId !== user.trainerId) return message
      return { ...message, request: structuredClone(original.request), status: original.status,
        ...(original.cancelledAt ? { cancelledAt: original.cancelledAt, cancelledBy: structuredClone(original.cancelledBy) } : {}) }
    }).map(message => ({ ...messageForUser(message, user), ...(message.kind === 'renewal' ? { renewalStatus: renewalStatus(message, db.clients.find(client => client.id === message.clientId)) } : {}), ...(messageVisibleTo(user, message) && message.mutationId ? { undo: mutationForMessage(db, message, user) } : {}) }))
    delete db.sessionMutations
    const data = { ...db, ...(user.role === 'admin' ? {} : { remunerationViews: remunerationService.list(user).map(view => ({ ...view, cycle: payCycle(view.key, policy.remuneration) })) }), contentEntries: managesOperations(user) ? db.contentEntries ?? [] : [], exerciseLibrary: exerciseLibraryService.getAll(user) }
    return { user, capabilities: { demoControls: true }, policy, accounts, demoPassword: mockAccountPassword, data: user.role === 'admin' ? adminProjection(data) : data }
  },
  async session(request) {
    const { operation, input } = authRequest(request, 'mock')
    return accountOperations[operation](input)
  },
  async invoke(request) {
    const actor = authService.requireCurrent()
    const scope = localStorage.getItem(MOCK_SESSION_KEY)
    bindSessionMutationActor(actor, () => {
      if (localStorage.getItem(MOCK_SESSION_KEY) !== scope || authService.requireCurrent().id !== actor.id) throw Object.assign(new Error('Your session changed. Refresh before trying again.'), { code: 'SESSION_CHANGED' })
    })
    const resolved = portalRequest(request, 'mock')
    authorizePortalRequest(resolved, actor, mockDb.read())
    const { service, operation, input } = resolved
    let result = await mockPortalOperations[service][operation](input, { actor })
    if (service === 'requestService') result = messageForUser(result, actor)
    return actor.role === 'admin' ? adminProjection(result) : result
  },
  async reset() {
    authService.requireCurrent()
    const { settings } = mockDb.read()
    mockDb.reset(businessClock(new Date(), settings.timeZone).date)
    return this.load()
  },
}
