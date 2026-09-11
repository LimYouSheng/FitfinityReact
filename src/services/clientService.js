import { applyTrainerReassignment } from '../app/trainerReassignment.js'
import { clientAssignedToTrainer, clientPackages, deletablePackageSessions, ensureClientPackageReferences, requireActiveClient } from '../app/clientPackages.js'
import { deactivatePurchase, restoreClientPurchases } from '../app/packageLifecycle.js'
import { businessClock } from '../app/clock.js'
import { flushExerciseVideoDeletions, queueExerciseVideoDeletion } from './exerciseVideoRetention.js'
import { buildPackageRenewal } from '../app/packageRenewal.js'
import { PROGRESS_REPORT_ACTIONS } from '../app/progress.js'
import { appendRenewalMessage } from '../app/renewals.js'
import { selectedPackage } from '../app/packages.js'
import { applyWeeklySchedule, requireActiveActor, sameSlots, weeklyScheduleChanges } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'
import { appendSavedEditMessage, savedFields } from './editMessage.js'
import {
  buildClientRecord,
  clientPersonalDetails,
  clientProfileDraft,
  clientStepErrors,
  buildClientSessions,
  nextClientId,
  validateClientDraft,
} from '../app/clientOnboarding.js'

function messageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function copySlots(slots) {
  return (slots ?? []).map(slot => ({ ...slot }))
}

function describeSlots(slots) {
  return (slots ?? [])
    .map(slot => `${slot.day} ${slot.from}–${slot.to}`)
    .join(', ') || 'None'
}

function deleteUpcomingForPackage(db, client, purchased, staff) {
  const removed = deletablePackageSessions(client, purchased.id, db.sessions, db.packageCreditTransactions ?? [], businessClock(new Date(), db.settings.timeZone))
  if (!removed.length) return 0
  const ids = new Set(removed.map(session => session.id))
  const at = new Date().toISOString()
  for (const session of removed) for (const exercise of session.exercisePlan ?? []) {
    if (exercise.videoAttached) queueExerciseVideoDeletion(db, session.id, exercise.id, exercise.video?.id)
  }
  db.sessions = db.sessions.filter(session => !ids.has(session.id))
  purchased.deletedUpcomingSessions = [...(purchased.deletedUpcomingSessions ?? []), ...ids]
  purchased.sessionDeletionHistory = [...(purchased.sessionDeletionHistory ?? []), { at, by: { id: staff.id, name: staff.name }, sessionIds: [...ids] }]
  const requests = new Set(db.messages.filter(message => ids.has(message.request?.sessionId) && message.status === 'pending').map(message => message.id))
  for (const message of db.messages) if (requests.has(message.id) || requests.has(message.requestId)) {
    Object.assign(message, { status: 'rejected', decidedAt: at, decidedBy: staff.id, decisionReason: 'Session deleted from inactive package.' })
  }
  return removed.length
}

export const clientService = {
  async getAll() {
    await delay()
    return mockDb.read().clients
  },

  async getById(id) {
    await delay()
    return mockDb.read().clients.find(client => client.id === id) ?? null
  },

  async create(draft) {
    await delay(180)

    const validationErrors = validateClientDraft(draft)
    if (validationErrors.length) throw new Error(validationErrors[0])

    let createdId = null
    const state = mockDb.mutate(db => {
      const trainer = db.trainers.find(item =>
        item.id === draft.trainerId && (item.status ?? 'active') === 'active'
      )
      if (!trainer) throw new Error('Selected trainer is not active.')

      createdId = nextClientId(db.clients)
      const client = buildClientRecord(draft, createdId, selectedPackage(db, draft), db.settings)
      db.clients.push(client)
      db.sessions ??= []
      const sessions = buildClientSessions(client)
      if (sessions.length !== client.package.total) throw new Error('The schedule must fit every session within package validity. Review the weekly schedule.')
      db.sessions.push(...sessions)
      db.messages ??= []
      appendRenewalMessage(db, client)

      db.messages.push({
        id: messageId('client-created-owner'),
        createdAt: new Date().toISOString(),
        recipientRole: 'owner',
        clientId: client.id,
        trainerId: trainer.id,
        title: `New client created: ${client.name}`,
        body: `${trainer.name} is assigned to ${client.name}. ${client.package.total} sessions were created with ${client.package.validityDays}-day validity.`,
        kind: 'client_created',
        read: false,
      })

      db.messages.push({
        id: messageId('client-assigned-trainer'),
        createdAt: new Date().toISOString(),
        recipientTrainerId: trainer.id,
        clientId: client.id,
        trainerId: trainer.id,
        title: `New client assigned: ${client.name}`,
        body: `${client.name} has been added to your active client list.`,
        kind: 'client_assignment',
        read: false,
      })
    })

    return state.clients.find(client => client.id === createdId)
  },

  async renewPackage(id, draft, actor) {
    await delay(180)
    const state = mockDb.mutate(db => {
      if (requireActiveActor(db, actor).role !== 'owner') throw new Error('Only the owner can add packages.')
      const client = requireActiveClient(db.clients.find(item => item.id === id))
      if (!/^[a-zA-Z0-9_-]{1,120}$/.test(draft.requestId ?? '')) throw new Error('A renewal request ID is required.')
      const packageId = `client-package-${id}-${draft.requestId}`
      const existing = clientPackages(client).find(item => item.id === packageId)
      const request = JSON.stringify(draft)
      if (existing) {
        if (existing.renewalRequest !== request) throw new Error('This renewal request ID has already been used.')
        return
      }
      if (client.package.id !== draft.expectedPackageId || client.trainerId !== draft.expectedTrainerId || !sameSlots(client.fixedWeeklySchedule, draft.expectedSchedule)) throw new Error('The client package, trainer or schedule changed. Reopen Add Package to review it.')
      const { purchasedPackage, sessions } = buildPackageRenewal(db, client, draft, packageId)
      ensureClientPackageReferences(db, client)
      client.additionalPackages = [...(client.additionalPackages ?? []), { ...purchasedPackage, renewalRequest: request, createdAt: new Date().toISOString() }]
        .sort((a, b) => a.startDate.localeCompare(b.startDate))
      db.sessions.push(...sessions)
      appendSavedEditMessage(db, { clientId: id, trainerId: client.trainerId,
        title: `Package added: ${client.name}`, body: `${purchasedPackage.name} · ${purchasedPackage.total} sessions · ${purchasedPackage.startDate}–${purchasedPackage.endDate}` })
      appendRenewalMessage(db, client)
    })
    return state.clients.find(client => client.id === id)
  },

  async deactivatePackage(id, { packageId, deleteUpcomingSessions = false }, actor) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const staff = requireActiveActor(db, actor)
      if (staff.role !== 'owner') throw new Error('Only the owner can deactivate packages.')
      const client = requireActiveClient(db.clients.find(item => item.id === id))
      const purchased = clientPackages(client).find(item => item.id === packageId)
      if (!purchased) throw new Error('Package not found.')
      if (purchased.status === 'inactive') return
      if (typeof deleteUpcomingSessions !== 'boolean') throw new Error('Choose whether to delete upcoming sessions.')
      deactivatePurchase(purchased, staff, new Date().toISOString(), 'package')
      const removed = deleteUpcomingSessions ? deleteUpcomingForPackage(db, client, purchased, staff) : 0
      appendSavedEditMessage(db, { clientId: id, trainerId: client.trainerId,
        title: `Package deactivated: ${client.name}`, body: `${purchased.name ?? `${purchased.total} Sessions`} · ${staff.name}${deleteUpcomingSessions ? ` · ${removed} upcoming sessions permanently deleted` : ''}` })
    })
    await flushExerciseVideoDeletions()
    return state.clients.find(client => client.id === id)
  },

  async deletePackageSessions(id, { packageId }, actor) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const staff = requireActiveActor(db, actor)
      if (staff.role !== 'owner') throw new Error('Only the owner can delete package sessions.')
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found.')
      const purchased = clientPackages(client).find(item => item.id === packageId)
      if (!purchased || purchased.status !== 'inactive') throw new Error('Deactivate the package before deleting its upcoming sessions.')
      const count = deleteUpcomingForPackage(db, client, purchased, staff)
      if (count) appendSavedEditMessage(db, { clientId: id, trainerId: client.trainerId,
        title: `Package sessions deleted: ${client.name}`, body: `${count} upcoming sessions permanently deleted · ${staff.name}` })
    })
    await flushExerciseVideoDeletions()
    return state.clients.find(client => client.id === id)
  },

  async reassignTrainer(id, draft, actor) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const staff = requireActiveActor(db, actor)
      if (staff.role !== 'owner') throw new Error('Only the owner can permanently reassign trainers.')
      const client = requireActiveClient(db.clients.find(item => item.id === id))
      applyTrainerReassignment(db, client, draft, staff)
    })
    return state.clients.find(item => item.id === id)
  },

  async update(id, patch) {
    await delay(180)

    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')
      requireActiveClient(client)
      const fields = ['name', 'phone', 'email', 'birthday', 'gender', 'emergencyContact', 'genderPreference', 'healthNotes', 'remarks', 'notes', 'people']
      if (!patch || Object.keys(patch).some(key => !fields.includes(key))) throw new Error('Use the dedicated package, schedule or client status action for these changes.')
      let changes = { ...patch }
      if (Object.hasOwn(changes, 'people')) {
        const draft = { ...client, ...changes, type: client.type }
        if (!Array.isArray(draft.people) || draft.people.length !== (client.type === 'Couple' ? 2 : 1)) throw new Error('Review each client’s personal details.')
        const errors = clientStepErrors(draft, 'general', { requireComplete: false })
        if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
        changes = { ...changes, ...clientPersonalDetails(draft, db.settings) }
        // Coaching notes can be updated independently. A contact-only edit must
        // not replace them with an older per-person summary on couple records.
        const previousPeople = clientProfileDraft(client, db.settings).people
        if (client.type === 'Couple' && changes.people.every((person, index) => person.healthNotes === previousPeople[index].healthNotes)) changes.healthNotes = client.healthNotes
      } else if (client.type === 'Individual' && ['name', 'phone', 'email', 'birthday', 'gender', 'emergencyContact', 'healthNotes'].some(key => Object.hasOwn(changes, key))) {
        const draft = clientProfileDraft({ ...client, ...changes }, db.settings)
        const errors = clientStepErrors(draft, 'general', { requireComplete: false })
        if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
        changes = { ...changes, ...clientPersonalDetails(draft, db.settings) }
      }
      if (Object.hasOwn(changes, 'name')) {
        if (typeof changes.name !== 'string' || !changes.name.trim()) throw new Error('Enter a client name.')
        changes.name = changes.name.trim()
        if (client.type === 'Individual' && client.people?.length === 1) client.people[0].name = changes.name
      }
      Object.assign(client, changes)
      appendSavedEditMessage(db, {
        clientId: client.id,
        trainerId: client.trainerId,
        title: `Client details saved: ${client.name}`,
        body: `Updated ${savedFields(patch) || 'client details'}.`,
      })
    })

    return state.clients.find(client => client.id === id)
  },

  async recordProgressReportAction(id, { id: actionId, kind, packageId }, actor) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const staff = requireActiveActor(db, actor)
      const client = db.clients.find(item => item.id === id)
      if (!client || (staff.role !== 'owner' && !clientAssignedToTrainer(client, staff.trainerId, db.sessions))) throw new Error('This client is unavailable for your account.')
      if (typeof actionId !== 'string' || !/^[a-zA-Z0-9_-]{1,120}$/.test(actionId) || !Object.hasOwn(PROGRESS_REPORT_ACTIONS, kind)) throw new Error('A valid progress report action is required.')
      db.progressReportEvents ??= []
      const existing = db.progressReportEvents.find(event => event.id === actionId)
      const reportPackageId = packageId === undefined ? (existing ? existing.packageId ?? null : client.package.id) : packageId
      if (reportPackageId !== null && !clientPackages(client).some(item => item.id === reportPackageId)) throw new Error('Report package not found.')
      if (existing) {
        if (existing.clientId !== id || existing.kind !== kind || (existing.packageId ?? null) !== (reportPackageId ?? null) || existing.by.id !== staff.id) throw new Error('This report action ID has already been used.')
        return
      }
      if (kind === 'csv_export') throw new Error('New progress reports must be exported as PDF.')
      const at = new Date().toISOString()
      db.progressReportEvents.push({ id: actionId, clientId: id, packageId: reportPackageId, kind, at, by: { id: staff.id, name: staff.name } })
      appendSavedEditMessage(db, {
        clientId: id, trainerId: client.trainerId,
        title: `Progress report: ${client.name}`,
        body: `${PROGRESS_REPORT_ACTIONS[kind]} · ${staff.name}`,
      })
    })
    return state.progressReportEvents.find(event => event.id === actionId)
  },

  async progressReportHistory(id, actor, packageId) {
    await delay()
    const db = mockDb.read()
    const staff = requireActiveActor(db, actor)
    if (staff.role !== 'owner') throw new Error('Report history is available to the owner.')
    if (!db.clients.some(client => client.id === id)) throw new Error('Client not found')
    return (db.progressReportEvents ?? []).filter(event => event.clientId === id && (packageId === undefined || (event.packageId ?? null) === packageId))
      .sort((a, b) => b.at.localeCompare(a.at) || b.id.localeCompare(a.id))
  },

  async saveFixedWeeklySchedule(id, slots, actor) {
    await delay(180)

    let outcome = 'applied'

    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')

      requireActiveActor(db, actor)
      const nextSlots = copySlots(slots)
      const previousSlots = copySlots(client.fixedWeeklySchedule)
      weeklyScheduleChanges(db, client, nextSlots)
      if (sameSlots(previousSlots, nextSlots)) throw new Error('Change a weekly time before saving.')

      if (actor.role === 'owner') {
        applyWeeklySchedule(db, client, nextSlots)
        appendSavedEditMessage(db, {
          clientId: client.id,
          trainerId: client.trainerId,
          title: `Fixed weekly schedule saved: ${client.name}`,
          body: `Old: ${describeSlots(previousSlots)}\nNew: ${describeSlots(nextSlots)}`,
          kind: 'schedule_update',
        })
        return
      }

      if (actor.role !== 'trainer' || actor.trainerId !== client.trainerId) {
        throw new Error('Only the assigned trainer can edit this client schedule.')
      }

      const trainer = db.trainers.find(item => item.id === actor.trainerId)
      if (!trainer || trainer.status !== 'active') {
        throw new Error('Assigned trainer is not active.')
      }

      if (trainer.approvalNeeded?.fixedWeeklySchedule !== false) {
        outcome = 'requested'

        const requestId = messageId('schedule-request-owner')
        db.messages.push({
          id: requestId,
          createdAt: new Date().toISOString(),
          recipientRole: 'owner',
          clientId: client.id,
          trainerId: trainer.id,
          title: `Fixed weekly schedule change: ${client.name}`,
          body:
            `${trainer.name} requested a fixed weekly schedule change.\n` +
            `Old: ${describeSlots(previousSlots)}\n` +
            `New: ${describeSlots(nextSlots)}`,
          kind: 'schedule_request',
          status: 'pending',
          read: false,
          request: {
            type: 'fixed_weekly_schedule',
            clientId: client.id,
            trainerId: trainer.id,
            oldSlots: previousSlots,
            newSlots: nextSlots,
          },
        })

        db.messages.push({
          id: messageId('schedule-request-trainer'),
          requestId,
          createdAt: new Date().toISOString(),
          recipientTrainerId: trainer.id,
          clientId: client.id,
          trainerId: trainer.id,
          title: `Schedule change request sent: ${client.name}`,
          body: 'Owner approval is required before the fixed weekly schedule changes.',
          kind: 'schedule_request',
          status: 'pending',
          read: false,
        })

        return
      }

      applyWeeklySchedule(db, client, nextSlots)

      appendSavedEditMessage(db, {
        clientId: client.id,
        trainerId: trainer.id,
        title: `Fixed weekly schedule updated: ${client.name}`,
        body:
          `${trainer.name} updated the fixed weekly schedule directly.\n` +
          `Old: ${describeSlots(previousSlots)}\n` +
          `New: ${describeSlots(nextSlots)}`,
        kind: 'schedule_update',
      })
    })

    return {
      outcome,
      client: state.clients.find(client => client.id === id),
    }
  },

  async deactivate(id, actor) {
    await delay(180)

    const state = mockDb.mutate(db => {
      const staff = requireActiveActor(db, actor)
      if (staff.role !== 'owner') throw new Error('Only the owner can deactivate clients.')
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')
      if (client.status === 'inactive') return

      client.status = 'inactive'
      client.deactivatedAt = new Date().toISOString()
      client.deactivatedBy = { id: staff.id, name: staff.name }
      for (const purchased of clientPackages(client)) deactivatePurchase(purchased, staff, client.deactivatedAt, 'client')

      db.messages.push({
        id: messageId('client-off'),
        createdAt: client.deactivatedAt,
        recipientTrainerId: client.trainerId,
        clientId: client.id,
        trainerId: client.trainerId,
        title: `${client.name} deactivated`,
        body: `${client.name} has been deactivated by the owner and is available in your client list for viewing only.`,
        kind: 'client_status',
        read: false,
      })

      db.messages.push({
        id: messageId('client-owner'),
        createdAt: new Date().toISOString(),
        recipientRole: 'owner',
        clientId: client.id,
        trainerId: client.trainerId,
        title: `${client.name} deactivated`,
        body: 'The client and their packages are inactive and remain viewable in Clients. Open the client’s Package tab to review Past Packages and, if needed, permanently delete unacknowledged upcoming sessions. Reactivating the client restores packages disabled with this client and their retained sessions. Packages deactivated separately stay inactive; deleted sessions cannot be restored.',
        kind: 'client_status',
        read: false,
      })
    })

    return state.clients.find(client => client.id === id)
  },

  async reactivate(id, actor) {
    await delay(180)

    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')

      const staff = requireActiveActor(db, actor)
      if (staff.role !== 'owner') throw new Error('Only the owner can reactivate clients.')
      if (client.status !== 'inactive') return
      client.status = 'active'
      client.reactivatedAt = new Date().toISOString()
      client.reactivatedBy = { id: staff.id, name: staff.name }
      restoreClientPurchases(client, client.reactivatedAt, client.reactivatedBy)
      delete client.deactivatedAt

      db.messages.push({
        id: messageId('client-on'),
        createdAt: new Date().toISOString(),
        recipientTrainerId: client.trainerId,
        clientId: client.id,
        trainerId: client.trainerId,
        title: `${client.name} reactivated`,
        body: `${client.name} is active again and has returned to your assigned client list.`,
        kind: 'client_status',
        read: false,
      })
    })

    return state.clients.find(client => client.id === id)
  },
}
