import { mockDb } from './mockDb.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { adminErrors } from '../app/adminOnboarding.js'
import { businessClock } from '../app/clock.js'

const profile = user => ({ id: user.id, version: user.version ?? 1, name: user.name, email: user.email ?? '',
  phone_country_code: user.phone?.countryCode ?? '+65', phone_number: user.phone?.number ?? '', birthday: user.birthday ?? '', gender: user.gender ?? '' })
function owner(db, actor) {
  const user = requireActiveActor(db, actor)
  if (user.role !== 'owner') throw new Error('Owner profile is unavailable.')
  return user
}
export const ownerService = {
  async getProfile(actor) { return profile(owner(mockDb.read(), actor)) },
  async saveProfile(input, actor) {
    let result
    mockDb.mutate(db => {
      const user = owner(db, actor)
      if (input.id !== user.id || input.expectedVersion !== (user.version ?? 1) || input.details.email !== user.email) throw new Error('Owner details changed. Reload and review.')
      const draft = { ...input.details, phone: { countryCode: input.details.phone_country_code, number: input.details.phone_number } }
      const errors = adminErrors(draft, businessClock(new Date(), db.settings.timeZone).date)
      if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
      Object.assign(user, { name: draft.name.trim(), phone: draft.phone, birthday: draft.birthday, gender: draft.gender, version: (user.version ?? 1) + 1 })
      result = profile(user)
    })
    return result
  },
}
