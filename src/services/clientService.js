import { delay, mockDb } from './mockDb.js'
import { appendSavedEditMessage, savedFields } from './editMessage.js'

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

  async saveFixedWeeklySchedule(id, slots, actor) {
    await delay(180)

    let outcome = 'applied'

    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')

      const nextSlots = copySlots(slots)
      const previousSlots = copySlots(client.fixedWeeklySchedule)

      if (actor.role === 'owner') {
        client.fixedWeeklySchedule = nextSlots
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

      if (trainer.approvalNeeded?.fixedWeeklySchedule) {
        outcome = 'requested'

        db.messages.push({
          id: messageId('schedule-request-owner'),
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

      client.fixedWeeklySchedule = nextSlots

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
