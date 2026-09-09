import { describe, expect, it } from 'vitest'
import { isSessionHistory, sessionStatus, sortSessions, validateExercisePlan, visibleSessionsForUser } from './sessionRules.js'

const sessions = [
  { id: 'future', trainerId: 't1', date: '2026-09-07', from: '18:00', status: 'not_planned' },
  { id: 'today', trainerId: 't1', date: '2026-09-02', from: '18:00', status: 'planned' },
  { id: 'past', trainerId: 't2', date: '2026-08-29', from: '18:00', status: 'completed' },
]

describe('session rules', () => {
  it('filters trainer sessions without restricting the owner', () => {
    expect(visibleSessionsForUser({ role: 'owner' }, sessions)).toHaveLength(3)
    expect(visibleSessionsForUser({ role: 'trainer', trainerId: 't1' }, sessions).map(item => item.id)).toEqual(['future', 'today'])
  })

  it('orders upcoming nearest first and All by descending date and time with stable ties', () => {
    expect(sortSessions(sessions, '2026-09-02').map(item => item.id)).toEqual(['today', 'future', 'past'])
    const mixed = [
      ...sessions,
      { ...sessions[0], id: 'earlier-time', from: '08:00' },
      { ...sessions[0], id: 'future-z' },
      { ...sessions[0], id: 'future-a' },
      { ...sessions[2], id: 'future-completed', date: '2026-10-01' },
      { ...sessions[0], id: 'older-unplanned', date: '2026-08-20' },
    ]
    const original = mixed.map(item => item.id)
    const expected = ['future-completed', 'future', 'future-a', 'future-z', 'earlier-time', 'today', 'past', 'older-unplanned']
    expect(sortSessions(mixed, '2026-09-02', 'all').map(item => item.id)).toEqual(expected)
    expect(sortSessions([...mixed].reverse(), '2026-09-02', 'all').map(item => item.id)).toEqual(expected)
    expect(mixed.map(item => item.id)).toEqual(original)
    expect(isSessionHistory(sessions[2])).toBe(true)
  })

  it('uses the approved three-state status labels', () => {
    expect(sessionStatus('not_planned').label).toBe('Not Planned')
    expect(sessionStatus('planned').label).toBe('Planned')
    expect(sessionStatus('completed').label).toBe('Completed')
  })

  it('blocks empty plans and blank exercise names', () => {
    expect(validateExercisePlan([])).toMatch(/at least one/i)
    expect(validateExercisePlan([{ name: '   ' }])).toMatch(/needs a name/i)
    expect(validateExercisePlan([{ name: 'Goblet Squat' }])).toBeNull()
  })
})
