import { delay, mockDb } from './mockDb.js'
import { activeTrainers, trainerSelectableForAvailability } from '../app/status.js'

function messageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export const trainerService = {
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
      Object.assign(trainer, patch)
    })
    return state.trainers.find(trainer => trainer.id === id)
  },

  async updateAutonomy(id, approvalNeeded) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')
      trainer.approvalNeeded = { ...approvalNeeded }
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
        title: `${trainer.name} reactivated`,
        body: 'The trainer is eligible for active scheduling and availability matching again.',
        kind: 'trainer_status',
        read: false,
      })
    })

    return state.trainers.find(trainer => trainer.id === id)
  },
}
