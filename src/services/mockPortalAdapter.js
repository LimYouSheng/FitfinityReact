import { payCycle } from '../app/remuneration.js'
import { contentService } from './contentService.js'
import { authService } from './authService.js'
import { mockDb, delay } from './mockDb.js'
import { mockPolicy, mockAccountPassword } from '../data/mockPolicy.js'
import { clientService } from './clientService.js'
import { trainerService } from './trainerService.js'
import { sessionService } from './sessionService.js'
import { packageService } from './packageService.js'
import { exerciseLibraryService } from './exerciseLibraryService.js'
import { messageService } from './messageService.js'
import { requestService } from './requestService.js'
import { remunerationService } from './remunerationService.js'

const domains = { contentService, clientService, trainerService, sessionService, packageService, exerciseLibraryService, messageService, requestService, remunerationService }

// This adapter owns mock persistence. An API adapter implements load/session/invoke.
export const mockPortalAdapter = {
  async load() {
    await delay(20)
    const db = mockDb.reload()
    const user = authService.current()
    const policy = structuredClone(db.settings ?? mockPolicy)
    const accounts = db.users.filter(item => (item.status ?? 'active') === 'active').map(({ id, name }) => ({ id, name }))
    if (!user) return { user: null, capabilities: { demoControls: true }, policy, accounts, demoPassword: mockAccountPassword, data: null }
    return { user, capabilities: { demoControls: true }, policy, accounts, demoPassword: mockAccountPassword, data: { ...db, remunerationViews: remunerationService.list(user).map(view => ({ ...view, cycle: payCycle(view.key, policy.remuneration) })), contentEntries: user.role === 'owner' ? db.contentEntries ?? [] : [], exerciseLibrary: exerciseLibraryService.getAll(user) } }
  },
  async session(method, args) { return authService[method](...args) },
  async invoke(domain, method, args) {
    const user = authService.requireCurrent()
    if (['contentService', 'packageService', 'exerciseLibraryService', 'requestService'].includes(domain) && !['getAll', 'loadMedia'].includes(method) && user.role !== 'owner') throw new Error('This action is available to the owner.')
    if (domain === 'clientService' && ['create', 'deactivate', 'reactivate'].includes(method) && user.role !== 'owner') throw new Error('This action is available to the owner.')
    const owner = () => { if (user.role !== 'owner') throw new Error('This action is available to the owner.') }
    if (domain === 'trainerService' && ['create', 'updateAutonomy', 'deactivate', 'reactivate'].includes(method)) owner()
    if (domain === 'trainerService' && ['update', 'saveAvailability'].includes(method) && user.role !== 'owner' && args[0] !== user.trainerId) throw new Error('This trainer is unavailable for your account.')
    if (domain === 'clientService' && ['update', 'saveFixedWeeklySchedule'].includes(method) && user.role !== 'owner' && !mockDb.read().clients.some(item => item.id === args[0] && item.trainerId === user.trainerId)) throw new Error('This client is unavailable for your account.')
    if (domain === 'sessionService' && method === 'updateDetails') owner()
    if (domain === 'remunerationService' && method === 'approve') owner()
    const actorIndex = { contentService: { save: 1 }, packageService: { save: 1 }, exerciseLibraryService: { getAll: 0, save: 1 }, clientService: { saveFixedWeeklySchedule: 2 }, trainerService: { create: 1, saveAvailability: 2 }, sessionService: { requestTimeChange: 1, requestTrainerChange: 1 }, requestService: { resolve: 2 }, remunerationService: { list: 0, detail: 2, approve: 3 } }[domain]?.[method]
    if (actorIndex !== undefined) { args = [...args]; args[actorIndex] = user }
    if (domain === 'sessionService') {
      const session = mockDb.read().sessions.find(item => item.id === args[0])
      if (!session || (user.role !== 'owner' && session.trainerId !== user.trainerId)) throw new Error('This session is unavailable for your account.')
    }
    return domains[domain][method](...args)
  },
  async reset() { authService.requireCurrent(); mockDb.reset(); return this.load() },
}
