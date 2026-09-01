import { delay, mockDb } from './mockDb.js'

export const clientService = {
  async getAll() { await delay(); return mockDb.read().clients },
  async getById(id) { await delay(); return mockDb.read().clients.find(client => client.id === id) ?? null },
  async update(id, patch) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const client = db.clients.find(item => item.id === id)
      if (!client) throw new Error('Client not found')
      Object.assign(client, patch)
    })
    return state.clients.find(client => client.id === id)
  },
}
