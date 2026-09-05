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
