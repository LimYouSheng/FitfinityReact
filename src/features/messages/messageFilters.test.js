import { describe, expect, it } from 'vitest'
import { filterMessages } from './messageFilters.js'

const messages = [
  { id: 'm1', title: 'Schedule update', body: 'Evening session moved.', createdAt: '2026-09-01T12:00:00+08:00' },
  { id: 'm2', title: 'Package review', body: 'Review Amanda Lim before renewal.', createdAt: '2026-09-02T09:00:00+08:00' },
  { id: 'm3', title: 'Approval', body: 'Trainer change requested.', createdAt: '2026-09-03T18:00:00+08:00' },
]

describe('filterMessages', () => {
  it('searches title and body and applies an inclusive date range', () => {
    expect(filterMessages(messages, { query: 'amanda' }).map(message => message.id)).toEqual(['m2'])
    expect(filterMessages(messages, { query: 'SCHEDULE' }).map(message => message.id)).toEqual(['m1'])
    expect(filterMessages(messages, { from: '2026-09-02', to: '2026-09-03' }).map(message => message.id)).toEqual(['m2', 'm3'])
  })
})
