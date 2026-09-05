import { describe, expect, it } from 'vitest'
import { seed } from './seed.js'

describe('production-shaped demo data', () => {
  it('uses only twelve-week packages with fixed ninety-day validity', () => {
    for (const client of seed.clients) {
      expect(client.package.durationWeeks).toBe(12)
      expect([1, 2]).toContain(client.package.sessionsPerWeek)
      expect(client.package.total).toBe(client.package.sessionsPerWeek * 12)
      expect(client.package.validityDays).toBe(90)
    }
  })

  it('schedules every active client through the final package session', () => {
    for (const client of seed.clients.filter(item => item.status === 'active')) {
      const upcoming = seed.sessions
        .filter(session => session.clientId === client.id && session.status !== 'completed')
        .sort((a, b) => a.sessionNumber - b.sessionNumber)

      expect(upcoming).toHaveLength(client.package.total - client.package.used)
      expect(upcoming[0]?.sessionNumber).toBe(client.package.used + 1)
      expect(upcoming.at(-1)?.sessionNumber).toBe(client.package.total)
    }
  })

  it('fills every client progress tab with the six Oracle strength series', () => {
    for (const client of seed.clients) {
      expect(client.strengthProgress).toHaveLength(6)
      expect(client.strengthProgress[0].name).toBe('Smith back squat')
      expect(client.strengthProgress[0].points.at(-1).load).toBe(25)
    }
  })
})
