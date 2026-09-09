import { PROGRESS_REPORT_ACTIONS } from '../app/progress.js'
import { appendRenewalMessage } from '../app/renewals.js'
import { selectedPackage } from '../app/packages.js'
import { applyWeeklySchedule, requireActiveActor, sameSlots, weeklyScheduleChanges } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'
import { appendSavedEditMessage, savedFields } from './editMessage.js'
import {
  buildClientRecord,
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

  async update(id, patch) {
    await delay(180)

    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')
      Object.assign(client, patch)
      appendSavedEditMessage(db, {
        clientId: client.id,
        trainerId: client.trainerId,
        title: `Client details saved: ${client.name}`,
        body: `Updated ${savedFields(patch) || 'client details'}.`,
      })
    })

    return state.clients.find(client => client.id === id)
  },

  async recordProgressReportAction(id, { id: actionId, kind }, actor) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const staff = requireActiveActor(db, actor)
      const client = db.clients.find(item => item.id === id)
      if (!client || (staff.role !== 'owner' && (client.status === 'inactive' || staff.trainerId !== client.trainerId))) throw new Error('This client is unavailable for your account.')
      if (typeof actionId !== 'string' || !/^[a-zA-Z0-9_-]{1,120}$/.test(actionId) || !Object.hasOwn(PROGRESS_REPORT_ACTIONS, kind)) throw new Error('A valid progress report action is required.')
      db.progressReportEvents ??= []
      const existing = db.progressReportEvents.find(event => event.id === actionId)
      if (existing) {
        if (existing.clientId !== id || existing.kind !== kind || existing.by.id !== staff.id) throw new Error('This report action ID has already been used.')
        return
      }
      const at = new Date().toISOString()
      db.progressReportEvents.push({ id: actionId, clientId: id, kind, at, by: { id: staff.id, name: staff.name } })
      appendSavedEditMessage(db, {
        clientId: id, trainerId: client.trainerId,
        title: `Progress report: ${client.name}`,
        body: `${PROGRESS_REPORT_ACTIONS[kind]} · ${staff.name}`,
      })
    })
    return state.progressReportEvents.find(event => event.id === actionId)
  },

  async progressReportHistory(id, actor) {
    await delay()
    const db = mockDb.read()
    const staff = requireActiveActor(db, actor)
    if (staff.role !== 'owner') throw new Error('Report history is available to the owner.')
    if (!db.clients.some(client => client.id === id)) throw new Error('Client not found')
    return (db.progressReportEvents ?? []).filter(event => event.clientId === id)
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

  async deactivate(id) {
    await delay(180)

    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')
      if (client.status === 'inactive') return

      client.status = 'inactive'
      client.deactivatedAt = new Date().toISOString()

      db.sessions
        .filter(session =>
          session.clientId === id &&
          !['completed', 'cancelled'].includes(session.status)
        )
        .forEach(session => {
          session.status = 'cancelled'
        })

      db.messages.push({
        id: messageId('client-off'),
        createdAt: new Date().toISOString(),
        recipientTrainerId: client.trainerId,
        clientId: client.id,
        trainerId: client.trainerId,
        title: `${client.name} deactivated`,
        body: `${client.name} has been deactivated by the owner and removed from your active client list.`,
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
        body: 'The inactive client remains retrievable at the bottom of All Clients and through the Status filter.',
        kind: 'client_status',
        read: false,
      })
    })

    return state.clients.find(client => client.id === id)
  },

  async reactivate(id) {
    await delay(180)

    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')

      client.status = 'active'
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
