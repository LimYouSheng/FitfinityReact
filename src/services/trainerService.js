import { mutateSessionRecords } from './sessionMutation.js'
import { managesOperations, canEditTrainerRates } from '../app/permissions.js'
import { adminProjection } from '../app/adminProjection.js'
import { sessionIsInactive } from '../app/clientPackages.js'
import { requireActiveActor, sameAvailability, validateAvailability } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'
import { activeTrainers, trainerSelectableForAvailability } from '../app/status.js'
import { appendSavedEditMessage, savedFields } from './editMessage.js'
import { buildTrainerRecord, nextTrainerId, normalizeTrainerEmail, trainerProfileDraft, trainerStepErrors, validateTrainerDraft } from '../app/trainerOnboarding.js'
import { requireSessionSlotAvailable } from '../app/bookingAvailability.js'
import { APPROVAL_FIELDS } from '../app/constants.js'

const profileFields = ['name', 'phone', 'email', 'birthday', 'gender', 'trainerType', 'qualifications', 'publicProfile']

function messageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export const trainerService = {
  async create(draft, actor) {
    await delay(180)
    let createdId

    const state = mutateSessionRecords(actor, 'trainer.create', db => {
      const owner = db.users.find(user => user.id === actor?.id)
      if (!managesOperations(actor) || !managesOperations(owner) || owner.role !== actor.role || (owner.status ?? 'active') !== 'active') {
        throw new Error('Only an active owner can create a trainer.')
      }
      if (owner.role === 'admin' && Object.hasOwn(draft, 'rates')) throw new Error('Trainer pay rates are restricted.')
      const source = owner.role === 'admin' ? { ...draft, rates: { ...db.settings.trainerRates } } : draft
      const errors = validateTrainerDraft(source)
      if (errors.length) throw new Error(errors[0])
      const email = normalizeTrainerEmail(source.email)
      if ([...db.trainers, ...db.users].some(record => normalizeTrainerEmail(record.email) === email)) {
        throw new Error('This email already belongs to a trainer or staff account. Use a different email or reactivate the existing trainer.')
      }
      createdId = nextTrainerId(db.trainers, db.users)
      const trainer = buildTrainerRecord(source, createdId)
      db.trainers.push(trainer)
      // Development identity only, so owner/trainer flows can be exercised before auth.
      db.users.push({ id: `u-${trainer.id}`, role: 'trainer', status: 'active', trainerId: trainer.id, name: trainer.name, email: trainer.email, profile: 'Trainer' })
      db.messages ??= []
      const createdAt = new Date().toISOString()
      db.messages.push({
        id: messageId('trainer-created-owner'), createdAt, recipientRole: 'owner', trainerId: trainer.id,
        title: `New trainer created: ${trainer.name}`,
        body: 'Trainer profile, session rates, approved availability and approval controls were saved.',
        kind: 'trainer_created', readBy: {},
      }, {
        id: messageId('trainer-created-self'), createdAt, recipientTrainerId: trainer.id, trainerId: trainer.id,
        title: `Trainer profile created: ${trainer.name}`,
        body: 'Your profile and approved availability are ready for client assignment.',
        kind: 'trainer_created', readBy: {},
      })
    })
    const created = state.trainers.find(trainer => trainer.id === createdId)
    return actor.role === 'admin' ? adminProjection(created) : created
  },

  async saveAvailability(id, blocks, actor) {
    await delay(180)
    const nextAvailability = validateAvailability(blocks)
    let outcome = 'applied'
    const state = mutateSessionRecords(actor, 'trainer.saveAvailability', db => {
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
          kind: 'availability_request', status: 'pending', readBy: {}, createdAt, request },
        { id: messageId('availability-receipt'), recipientTrainerId: id, trainerId: id, requestId,
          title: `Availability change request sent: ${trainer.name}`, body: 'Your approved availability remains unchanged until the owner approves.',
          kind: 'availability_request', status: 'pending', readBy: {}, createdAt })
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

  async update(id, patch, actor) {
    await delay(180)
    const state = mutateSessionRecords(actor, 'trainer.update', db => {
      const staff = requireActiveActor(db, actor)
      if (Object.keys(patch).some(key => ![...profileFields, 'rates'].includes(key))) {
        throw new Error('Unsupported trainer profile field. Use the dedicated action for approvals, availability or status.')
      }
      if (Object.hasOwn(patch, 'rates') && !canEditTrainerRates(staff)) {
        throw new Error('Trainer pay rates are restricted.')
      }
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')
      if (!managesOperations(staff) && (staff.trainerId !== id || trainer.status !== 'active' || Object.hasOwn(patch, 'name'))) {
        throw new Error('Only the active assigned trainer can edit their profile; name changes require the owner or Admin.')
      }
      const changes = { ...patch }
      if (profileFields.some(key => Object.hasOwn(changes, key))) {
        const errors = trainerStepErrors(trainerProfileDraft({ ...trainer, ...changes }, db.settings), 'general', { requireComplete: false })
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
        kind: Object.hasOwn(patch, 'rates') ? 'trainer_rates' : 'saved_edit',
      })
    })
    const updated = state.trainers.find(trainer => trainer.id === id)
    return actor?.role === 'admin' ? adminProjection(updated) : updated
  },

  async updateAutonomy(id, approvalNeeded, actor) {
    await delay(180)
    const state = mutateSessionRecords(actor, 'trainer.updateAutonomy', db => {
      if (!managesOperations(requireActiveActor(db, actor))) throw new Error('Only the owner or Admin can change approval settings.')
      if (!approvalNeeded || Object.keys(approvalNeeded).length !== APPROVAL_FIELDS.length ||
          APPROVAL_FIELDS.some(([field]) => typeof approvalNeeded[field] !== 'boolean')) throw new Error('Set all four owner approval controls.')
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

  async deactivate(id, replacements = {}, actor) {
    await delay(220)

    const state = mutateSessionRecords(actor, 'trainer.deactivate', db => {
      if (!managesOperations(requireActiveActor(db, actor))) throw new Error('Only the owner or Admin can deactivate a trainer.')
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')

      const remaining = db.sessions.filter(session =>
        session.trainerId === id &&
        !sessionIsInactive(db.clients.find(client => client.id === session.clientId), session) &&
        !['completed', 'cancelled'].includes(session.status)
      )

      const changes = remaining.map(session => {
        const replacementId = replacements[session.id]
        const replacement = db.trainers.find(item => item.id === replacementId)

        if (!replacement || replacement.id === id || replacement.status !== 'active') {
          throw new Error('Every remaining session must be reassigned to an active trainer before deactivation.')
        }
        return { ...session, trainerId: replacement.id }
      })
      const changedById = new Map(changes.map(session => [session.id, session]))
      const calendar = { ...db, sessions: db.sessions.map(session => changedById.get(session.id) ?? session) }
      for (const session of changes) requireSessionSlotAvailable(calendar, session)

      for (const session of remaining) {
        const replacementId = changedById.get(session.id).trainerId
        session.trainerId = replacementId

        const client = db.clients.find(item => item.id === session.clientId)
        db.messages.push({
          id: messageId('reassign'),
          createdAt: new Date().toISOString(),
          recipientTrainerId: replacementId,
          sessionId: session.id,
          clientId: session.clientId,
          trainerId: replacementId,
          title: 'Session reassigned to you',
          body: `${client?.name ?? 'Client'} • ${session.date} • ${session.from}–${session.to}`,
          kind: 'assignment',
          readBy: {},
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
        readBy: {},
      })
    })

    return state.trainers.find(trainer => trainer.id === id)
  },

  async reactivate(id, actor) {
    await delay(180)
    const state = mutateSessionRecords(actor, 'trainer.reactivate', db => {
      if (!managesOperations(requireActiveActor(db, actor))) throw new Error('Only the owner or Admin can reactivate trainers.')
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
        readBy: {},
      })
    })

    return state.trainers.find(trainer => trainer.id === id)
  },
}
