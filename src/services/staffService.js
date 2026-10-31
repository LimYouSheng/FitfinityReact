import { ADMIN_APPROVAL_FIELDS, defaultAdminApprovals } from '../app/adminApprovals.js'
import { adminErrors } from '../app/adminOnboarding.js'
import { businessClock } from '../app/clock.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'
import { createUuid } from '../utils/uuid.js'

const adminRecord = user => ({ id: user.id, version: user.version ?? 1, role: 'admin', status: user.status ?? 'active',
  details: { name: user.name, email: user.email ?? '', phone_country_code: user.phone?.countryCode ?? '+65', phone_number: user.phone?.number ?? '', birthday: user.birthday ?? '', gender: user.gender ?? '' },
  approvalNeeded: Object.fromEntries(ADMIN_APPROVAL_FIELDS.map(([key]) => [key, user.approvalNeeded?.[key] ?? false])),
})

function ownerOnly(db, actor) {
  if (requireActiveActor(db, actor).role !== 'owner') throw new Error('Admin management is available to the Owner.')
}

export const staffService = {
  async getAll(actor) {
    const db = mockDb.read(); ownerOnly(db, actor)
    return db.users.filter(user => user.role === 'admin').map(adminRecord)
  },
  async getById(id, actor) {
    const db = mockDb.read(); ownerOnly(db, actor)
    const user = db.users.find(item => item.id === id && item.role === 'admin')
    if (!user) throw new Error('Admin account is unavailable.')
    return adminRecord(user)
  },
  async update(id, body, actor) {
    let result
    mockDb.mutate(db => {
      ownerOnly(db, actor)
      const user = db.users.find(item => item.id === id && item.role === 'admin')
      if (!user || (user.version ?? 1) !== body.expectedVersion) throw new Error('Admin details changed. Reload and review.')
      const before = adminRecord(user)
      if (body.operation === 'details') {
        if (user.status === 'inactive' || body.details.email !== user.email) throw new Error('This account or login email cannot be changed here.')
        const draft = { ...body.details, phone: { countryCode: body.details.phone_country_code, number: body.details.phone_number } }
        const errors = adminErrors(draft, businessClock(new Date(), db.settings.timeZone).date)
        if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
        Object.assign(user, { name: draft.name.trim(), phone: draft.phone, birthday: draft.birthday, gender: draft.gender })
      } else if (body.operation === 'approvals') {
        if (user.status === 'inactive' || !body.approvalNeeded || Object.keys(body.approvalNeeded).length !== ADMIN_APPROVAL_FIELDS.length || ADMIN_APPROVAL_FIELDS.some(([key]) => typeof body.approvalNeeded[key] !== 'boolean')) throw new Error('Review the complete approval requirements.')
        user.approvalNeeded = structuredClone(body.approvalNeeded)
      } else if (['deactivate', 'reactivate'].includes(body.operation)) {
        const expected = body.operation === 'deactivate' ? 'active' : 'inactive'
        if ((user.status ?? 'active') !== expected) throw new Error('Admin status changed. Reload and review.')
        user.status = body.operation === 'deactivate' ? 'inactive' : 'active'
      } else throw new Error('Choose an Admin action.')
      user.version = before.version + 1
      result = adminRecord(user)
      db.adminChanges ??= []
      db.adminChanges.push({ id: createUuid(), actorId: actor.id, at: new Date().toISOString(), operation: body.operation, before, result })
    })
    return structuredClone(result)
  },
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
      const user = { id: createUuid(), name: body.name.trim(), email, role: 'admin', status: 'active', approvalNeeded: defaultAdminApprovals(), profile: 'Admin', phone: draft.phone, birthday: body.birthday, gender: body.gender }
      db.users.push(user)
      result = { id: user.id, name: user.name, email, role: 'admin', invitation: 'demo' }
      db.staffInvitations.push({ requestKey, actorId: owner.id, body: digest, result })
    })
    return structuredClone(result)
  },
}
