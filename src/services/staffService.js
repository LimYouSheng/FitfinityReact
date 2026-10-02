import { adminErrors } from '../app/adminOnboarding.js'
import { businessClock } from '../app/clock.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'
import { createUuid } from '../utils/uuid.js'

export const staffService = {
  async createAdmin(body, requestKey, actor) {
    await delay(120)
    const draft = { name: body.name, email: body.email, phone: { countryCode: body.phone_country_code, number: body.phone_number }, birthday: body.birthday, gender: body.gender }
    const expected = ['name', 'email', 'phone_country_code', 'phone_number', 'birthday', 'gender']
    if (Object.keys(body).some(key => !expected.includes(key)) || !/^[0-9a-f-]{36}$/i.test(requestKey)) throw new Error('Invalid staff account details.')
    let result
    mockDb.mutate(db => {
      const owner = requireActiveActor(db, actor)
      if (owner.role !== 'owner') throw new Error('Only the owner can create an Admin.')
      const errors = adminErrors(draft, businessClock(new Date(), db.settings.timeZone).date)
      if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
      db.staffInvitations ??= []
      const receipt = db.staffInvitations.find(item => item.requestKey === requestKey)
      const digest = JSON.stringify(body)
      if (receipt) {
        if (receipt.actorId !== owner.id || receipt.body !== digest) throw new Error('The original account details are required for this request.')
        result = receipt.result
        return
      }
      const email = body.email.trim().toLowerCase()
      if ([...db.users, ...db.trainers].some(record => record.email?.trim().toLowerCase() === email)) throw Object.assign(new Error('This email already belongs to a staff account or trainer.'), { code: 'STAFF_EMAIL_EXISTS' })
      const user = { id: createUuid(), name: body.name.trim(), email, role: 'admin', status: 'active', profile: 'Admin', phone: draft.phone, birthday: body.birthday, gender: body.gender }
      db.users.push(user)
      result = { id: user.id, name: user.name, email, role: 'admin', invitation: 'demo' }
      db.staffInvitations.push({ requestKey, actorId: owner.id, body: digest, result })
    })
    return structuredClone(result)
  },
}
