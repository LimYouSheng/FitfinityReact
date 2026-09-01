import { delay, mockDb } from './mockDb.js'

export const trainerService = {
  async getAll() { await delay(); return mockDb.read().trainers },
  async getById(id) { await delay(); return mockDb.read().trainers.find(trainer => trainer.id === id) ?? null },
  async updateAutonomy(id, approvalNeeded) {
    await delay(180)
    const state = mockDb.mutate(db => {
      const trainer = db.trainers.find(item => item.id === id)
      if (!trainer) throw new Error('Trainer not found')
      trainer.approvalNeeded = { ...approvalNeeded }
    })
    return state.trainers.find(trainer => trainer.id === id)
  },
}
