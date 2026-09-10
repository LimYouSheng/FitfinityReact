import { sessionIsInactive } from '../app/clientPackages.js'
import { requireActiveActor, sameAvailability, validateAvailability } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'
import { activeTrainers, trainerSelectableForAvailability } from '../app/status.js'
import { appendSavedEditMessage, savedFields } from './editMessage.js'
import { buildTrainerRecord, nextTrainerId, normalizeTrainerEmail, trainerProfileDraft, trainerStepErrors, validateTrainerDraft } from '../app/trainerOnboarding.js'

function messageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export const trainerService = {
  async create(draft, actor) {
    await delay(180)
    const errors = validateTrainerDraft(draft)
    if (errors.length) throw new Error(errors[0])
    let createdId

    const state = mockDb.mutate(db => {
      const owner = db.users.find(user => user.id === actor?.id)
      if (actor?.role !== 'owner' || owner?.role !== 'owner' || (owner.status ?? 'active') !== 'active') {
        throw new Error('Only an active owner can create a trainer.')
      }
      const email = normalizeTrainerEmail(draft.email)
      if ([...db.trainers, ...db.users].some(record => normalizeTrainerEmail(record.email) === email)) {
        throw new Error('This email already belongs to a trainer or staff account. Use a different email or reactivate the existing trainer.')
      }
      createdId = nextTrainerId(db.trainers, db.users)
      const trainer = buildTrainerRecord(draft, createdId)
      db.trainers.push(trainer)
      // Development identity only, so owner/trainer flows can be exercised before auth.
      db.users.push({ id: `u-${trainer.id}`, role: 'trainer', status: 'active', trainerId: trainer.id, name: trainer.name, email: trainer.email, profile: 'Trainer' })
      db.messages ??= []
      const createdAt = new Date().toISOString()
      db.messages.push({
        id: messageId('trainer-created-owner'), createdAt, recipientRole: 'owner', trainerId: trainer.id,
        title: `New trainer created: ${trainer.name}`,
        body: 'Trainer profile, session rates, approved availability and approval controls were saved.',
        kind: 'trainer_created', read: false,
      }, {
        id: messageId('trainer-created-self'), createdAt, recipientTrainerId: trainer.id, trainerId: trainer.id,
        title: `Trainer profile created: ${trainer.name}`,
        body: 'Your profile and approved availability are ready for client assignment.',
        kind: 'trainer_created', read: false,
      })
    })
    return state.trainers.find(trainer => trainer.id === createdId)
  },

  async saveAvailability(id, blocks, actor) {
    await delay(180)
    const nextAvailability = validateAvailability(blocks)
    let outcome = 'applied'
    const state = mockDb.mutate(db => {
      const stored = requireActiveActor(db, actor)
      const trainer = db.trainers.find(item => item.id === id)
      if (stored.role !== 'trainer' || stored.trainerId !== id || trainer?.status !== 'active') {
        throw new Error('Only the active trainer can change their own availability.')
      }
      if (sameAvailability(trainer.availability, nextAvailability)) throw new Error('Change your availability before saving.')
      const request = { type: 'trainer_availability', trainerId: id, oldAvailability: trainer.availability, newAvailability: nextAvailability }
      const createdAt = new Date().toISOString()
      if (trainer.approvalNeeded?.availability !== false) {
        outcome = 'requested'
        const requestId = messageId('availability-request')
        db.messages.push({ id: requestId, recipientRole: 'owner', trainerId: id,
          title: `Availability change: ${trainer.name}`, body: 'Review all current and proposed availability blocks.',
          kind: 'availability_request', status: 'pending', read: false, createdAt, request },
        { id: messageId('availability-receipt'), recipientTrainerId: id, trainerId: id, requestId,
          title: `Availability change request sent: ${trainer.name}`, body: 'Your approved availability remains unchanged until the owner approves.',
          kind: 'availability_request', status: 'pending', read: false, createdAt })
      } else {
        trainer.availability = nextAvailability
        appendSavedEditMessage(db, { trainerId: id, title: `Availability updated: ${trainer.name}`,
          body: 'Approved availability was updated. Existing booked sessions retain their scheduled times.', kind: 'availability_update' })
      }
    })
    return { outcome, trainer: state.trainers.find(item => item.id === id) }
  },

  async getAll() {
    await delay()
    return mockDb.read().trainers
  },

  async getActive() {
    await delay()
    return activeTrainers(mockDb.read().trainers)
  },

  async getById(id) {
    await delay()
    return mockDb.read().trainers.find(trainer => trainer.id === id) ?? null
  },

  isSelectableForAvailability(trainer) {
    return trainerSelectableForAvailability(trainer)
  },

  async update(id, patch) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')
      const changes = { ...patch }
      const generalKeys = ['name', 'phone', 'email', 'birthday', 'gender', 'trainerType', 'qualifications', 'publicProfile']
      if (generalKeys.some(key => Object.hasOwn(changes, key))) {
        const errors = trainerStepErrors(trainerProfileDraft({ ...trainer, ...changes }, db.settings), 'general')
        if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
        if (Object.hasOwn(changes, 'email')) {
          changes.email = normalizeTrainerEmail(changes.email)
          if (db.trainers.some(item => item.id !== id && normalizeTrainerEmail(item.email) === changes.email) || db.users.some(item => item.trainerId !== id && normalizeTrainerEmail(item.email) === changes.email)) throw new Error('This email already belongs to a trainer or staff account.')
          for (const user of db.users.filter(item => item.trainerId === id)) user.email = changes.email
        }
      }
      if (Object.hasOwn(changes, 'rates')) {
        const errors = trainerStepErrors(changes, 'rates')
        if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
      }
      if (Object.hasOwn(changes, 'name')) {
        if (typeof changes.name !== 'string' || !changes.name.trim()) throw new Error('Enter a trainer name.')
        changes.name = changes.name.trim()
        for (const user of db.users.filter(item => item.trainerId === id)) user.name = changes.name
      }
      Object.assign(trainer, changes)
      appendSavedEditMessage(db, {
        trainerId: trainer.id,
        title: `Trainer details saved: ${trainer.name}`,
        body: `Updated ${savedFields(patch) || 'trainer details'}.`,
      })
    })
    return state.trainers.find(trainer => trainer.id === id)
  },

  async updateAutonomy(id, approvalNeeded) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')
      trainer.approvalNeeded = { ...approvalNeeded }
      appendSavedEditMessage(db, {
        trainerId: trainer.id,
        title: `Autonomy and approvals saved: ${trainer.name}`,
        body: 'The trainer approval settings were updated.',
      })
    })
    return state.trainers.find(trainer => trainer.id === id)
  },

  async deactivate(id, replacements = {}) {
    await delay(220)

    const state = mockDb.mutate(db => {
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')

      const remaining = db.sessions.filter(session =>
        session.trainerId === id &&
        !sessionIsInactive(db.clients.find(client => client.id === session.clientId), session) &&
        !['completed', 'cancelled'].includes(session.status)
      )

      for (const session of remaining) {
        const replacementId = replacements[session.id]
        const replacement = db.trainers.find(item => item.id === replacementId)

        if (!replacement || replacement.id === id || replacement.status !== 'active') {
          throw new Error('Every remaining session must be reassigned to an active trainer before deactivation.')
        }

        session.trainerId = replacement.id

        const client = db.clients.find(item => item.id === session.clientId)
        db.messages.push({
          id: messageId('reassign'),
          createdAt: new Date().toISOString(),
          recipientTrainerId: replacement.id,
          sessionId: session.id,
          clientId: session.clientId,
          trainerId: replacement.id,
          title: 'Session reassigned to you',
          body: `${client?.name ?? 'Client'} • ${session.date} • ${session.from}–${session.to}`,
          kind: 'assignment',
          read: false,
        })
      }

      trainer.status = 'inactive'
      trainer.deactivatedAt = new Date().toISOString()

      db.users
        .filter(user => user.trainerId === id)
        .forEach(user => { user.status = 'inactive' })

      db.messages.push({
        id: messageId('trainer-off'),
        createdAt: new Date().toISOString(),
        recipientRole: 'owner',
        trainerId: trainer.id,
        title: `${trainer.name} deactivated`,
        body: `${remaining.length} remaining session${remaining.length === 1 ? '' : 's'} reassigned before account deactivation.`,
        kind: 'trainer_status',
        read: false,
      })
    })

    return state.trainers.find(trainer => trainer.id === id)
  },

  async reactivate(id) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')

      trainer.status = 'active'
      delete trainer.deactivatedAt

      db.users
        .filter(user => user.trainerId === id)
        .forEach(user => { user.status = 'active' })

      db.messages.push({
        id: messageId('trainer-on'),
        createdAt: new Date().toISOString(),
        recipientRole: 'owner',
        trainerId: trainer.id,
        title: `${trainer.name} reactivated`,
        body: 'The trainer is eligible for active scheduling and availability matching again.',
        kind: 'trainer_status',
        read: false,
      })
    })

    return state.trainers.find(trainer => trainer.id === id)
  },
}
