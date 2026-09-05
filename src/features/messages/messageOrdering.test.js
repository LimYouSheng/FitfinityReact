import { describe, expect, it } from 'vitest'
import { orderMessages } from './messageOrdering.js'

describe('message ordering', () => {
  it('shows unread newest first, then read messages by latest read activity', () => {
    const messages = [
      {
        id: 'read-old', read: true,
        createdAt: '2026-09-02T14:00:00+08:00',
        readAt: '2026-09-02T14:05:00+08:00',
      },
      { id: 'unread-old', read: false, createdAt: '2026-09-01T10:00:00+08:00' },
      {
        id: 'read-new', read: true,
        createdAt: '2026-09-01T09:00:00+08:00',
        readAt: '2026-09-02T15:05:00+08:00',
      },
      { id: 'unread-new', read: false, createdAt: '2026-09-02T13:00:00+08:00' },
    ]

    expect(orderMessages(messages).map(message => message.id)).toEqual([
      'unread-new',
      'unread-old',
      'read-new',
      'read-old',
    ])
    expect(messages.map(message => message.id)).toEqual(['read-old', 'unread-old', 'read-new', 'unread-new'])
  })
})
