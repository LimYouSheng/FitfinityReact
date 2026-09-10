import { describe, expect, it } from 'vitest'
import { createDemoSeed, seed } from './seed.js'
import { buildClientSessions, trainerCoversBlock } from '../app/clientOnboarding.js'
import { packageForRecord } from '../app/clientPackages.js'
import { clientProgressExercises, progressSessionSummary } from '../app/progress.js'

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

  it('keeps session chronology, package usage, debit evidence and every plotted measurement coherent', () => {
    for (const demo of [seed, createDemoSeed('2026-09-10'), createDemoSeed('2027-01-04')]) {
      for (const client of demo.clients) {
        const sessions = demo.sessions.filter(item => item.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
        const scheduled = buildClientSessions(client)
        const completed = sessions.filter(item => item.status === 'completed')
        const exerciseNames = ['Goblet Squat', 'Seated Cable Row', 'DB Chest Press', 'Romanian Deadlift', 'Lat Pulldown', 'Walking Lunge']
        expect(completed).toHaveLength(client.package.used)
        expect(sessions.filter(session => session.status === 'completed' || session.date < demo.demoReferenceDate)).toEqual(completed)
        expect(progressSessionSummary(client, demo.sessions, client.package.id)).toEqual({ completed: completed.length, recorded: completed.length })
        for (const purchased of client.packageHistory) expect(progressSessionSummary(client, demo.sessions, purchased.id)).toEqual({ completed: 0, recorded: 0 })
        expect(completed.at(-1).date).toBe(client.lastTrained)
        for (const [index, session] of sessions.entries()) {
          expect(session.exercisePlan.map(row => row.name)).toEqual(exerciseNames)
          expect(session.status).toBe(index < client.package.used ? 'completed' : 'planned')
          expect(session.sessionNumber).toBe(index + 1)
          expect(session).toMatchObject({ date: scheduled[index].date, from: scheduled[index].from, to: scheduled[index].to, weeklySlotId: scheduled[index].weeklySlotId })
          const slot = client.fixedWeeklySchedule.find(item => item.id === session.weeklySlotId)
          expect(trainerCoversBlock(demo.trainers.find(item => item.id === client.trainerId), slot.day, slot.from, slot.to)).toBe(true)
          expect(session.status === 'completed' ? session.date < demo.demoReferenceDate : session.date >= demo.demoReferenceDate).toBe(true)
          expect(demo.sessions.some(other => other.id !== session.id && other.trainerId === session.trainerId && other.date === session.date && other.from < session.to && session.from < other.to)).toBe(false)
          expect(session.packageId).toBe(client.package.id)
          expect(session.date >= client.package.startDate && session.date <= client.package.endDate).toBe(true)
          if (index) expect(session.date >= sessions[index - 1].date).toBe(true)
          const credits = demo.packageCreditTransactions.filter(item => item.sessionId === session.id)
          expect(credits).toHaveLength(session.status === 'completed' ? 1 : 0)
          if (credits.length) {
            expect(credits[0].packageId).toBe(session.packageId)
            expect(credits[0].createdAt).toBe(session.acknowledgement.recordedAt)
          }
          if (session.status === 'completed') for (const row of session.exercisePlan) {
            const exercise = client.strengthProgress.find(item => item.name === row.name)
            expect(exercise, `${client.name}: ${row.name} from ${session.id}`).toBeDefined()
            const points = exercise.points.filter(point => point.sessionId === session.id)
            expect(points).toHaveLength(1)
            expect(points[0]).toMatchObject({ date: session.date, packageId: session.packageId, load: parseFloat(row.weight), reps: Number(row.reps), sets: Number(row.rounds) })
            expect(points[0].reps).toBeGreaterThan(0)
            if (row.name === 'Walking Lunge') {
              expect(points[0].reps).toBe(20)
              expect(row.customDetails.map(detail => detail.value)).toEqual(['10 repetitions per side (20 total)'])
            }
          }
        }
        expect(client.strengthProgress.map(exercise => exercise.name)).toEqual(exerciseNames)
        const stale = { ...client, strengthProgress: client.strengthProgress.map(exercise => ({ ...exercise, points: exercise.points.slice(-1) })) }
        expect(clientProgressExercises(stale, demo.sessions)).toEqual(client.strengthProgress)
        for (const exercise of client.strengthProgress) {
          expect(exercise.points.map(point => point.sessionId)).toEqual(completed.map(session => session.id))
          for (const [index, point] of exercise.points.entries()) {
            const session = completed.find(item => item.id === point.sessionId)
            expect(session).toBeDefined()
            expect(point.packageId).toBe(packageForRecord(client, session).id)
            expect(point.date).toBe(session.date)
            const row = session.exercisePlan.find(item => item.name === exercise.name)
            expect(point).toMatchObject({ load: parseFloat(row.weight), reps: Number(row.reps), sets: Number(row.rounds) })
            if (index) expect(point.date >= exercise.points[index - 1].date).toBe(true)
          }
        }
      }
    }
    expect(seed.clients[0].strengthProgress.map(item => item.points.length)).toEqual([3, 3, 3, 3, 3, 3])
    expect(seed.clients[0].strengthProgress.map(item => item.points.map(point => point.load))).toEqual([[14, 15, 16], [22, 23, 24], [8, 9, 10], [28, 29, 30], [26, 27, 28], [6, 7, 8]])
  })
})
