import { describe, expect, it } from 'vitest'
import { relatedMessageLinks } from './messageLinks.js'

describe('message links', () => {
  it('resolves permitted session, client and trainer records', () => {
    const links = relatedMessageLinks(
      { sessionId: 's1', clientId: 'c1', trainerId: 't1' },
      {
        user: { role: 'owner' },
        clients: [{ id: 'c1', name: 'Amanda Lim', trainerId: 't1' }],
        trainers: [{ id: 't1', name: 'Marcus Tan' }],
        sessions: [{ id: 's1', clientId: 'c1', trainerId: 't1', date: '2026-09-02', from: '18:00' }],
      },
    )

    expect(links.map(link => `${link.type}:${link.id}`)).toEqual([
      'session:s1',
      'client:c1',
      'trainer:t1',
    ])
  })
})

it('never infers related records from short names inside words or message text', () => {
  const data = { user: { role: 'owner' }, clients: [{ id: 'test', name: 'Test' }], trainers: [{ id: 'ann', name: 'Ann' }], sessions: [] }
  expect(relatedMessageLinks({ title: 'Latest announcement', body: 'Test 2026-09-05 18:00' }, data)).toEqual([])
  expect(relatedMessageLinks({ title: 'Latest announcement', clientId: 'missing' }, data)).toEqual([])
})
it('uses stored IDs despite ambiguous names and keeps trainer links within scope', () => {
  const data = { user: { role: 'trainer', trainerId: 't1' }, clients: [{ id: 'c1', name: 'Test', trainerId: 't1' }, { id: 'c2', name: 'Test', trainerId: 't2' }], trainers: [], sessions: [] }
  expect(relatedMessageLinks({ clientId: 'c2', body: 'Test' }, data)).toEqual([])
  expect(relatedMessageLinks({ clientId: 'c1', body: 'Test' }, data).map(link => link.id)).toEqual(['c1'])
})
it('routes remuneration notifications by cycle and trainer IDs with access scope', () => {
  const message = { remunerationCycle: '2026-09', trainerId: 't1' }
  expect(relatedMessageLinks(message, { user: { role: 'owner' } })[0]).toMatchObject({ type: 'remuneration', id: '2026-09/t1' })
  expect(relatedMessageLinks(message, { user: { role: 'trainer', trainerId: 't2' } })).toEqual([])
})
it('links library messages only by stored exercise ID and only for the owner', () => {
  const exercises = [{ id: 'exercise-a', name: 'Renamed exercise' }]
  expect(relatedMessageLinks({ exerciseId: 'exercise-a' }, { user: { role: 'owner' }, exercises })).toEqual([{ type: 'exercise', id: 'exercise-a', label: 'Exercise · Renamed exercise' }])
  expect(relatedMessageLinks({ exerciseId: 'exercise-a' }, { user: { role: 'trainer' }, exercises })).toEqual([])
  expect(relatedMessageLinks({ exerciseId: 'missing', title: 'Renamed exercise' }, { user: { role: 'owner' }, exercises })).toEqual([])
})
