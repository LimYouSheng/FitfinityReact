import { delay, mockDb } from './mockDb.js'

export const messageService = {
  async markRead(id) {
    await delay(80)

    const state = mockDb.mutate(db => {
      const message = db.messages.find(item => item.id === id)
      if (!message) return
      message.read = true
      message.readAt = message.readAt ?? new Date().toISOString()
    })

    return state.messages.find(message => message.id === id) ?? null
  },

  async markUnread(id) {
    await delay(80)

    const state = mockDb.mutate(db => {
      const message = db.messages.find(item => item.id === id)
      if (!message) return
      message.read = false
      delete message.readAt
    })

    return state.messages.find(message => message.id === id) ?? null
  },
}
