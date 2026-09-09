import { describe, expect, it } from 'vitest'
import { filterMessages, messageCategory } from './messageFilters.js'

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
    const boundaries = [
      { id: 'before', createdAt: '2026-09-08T15:59:59Z' },
      { id: 'midnight', createdAt: '2026-09-08T16:00:00Z' },
      { id: 'last-second', createdAt: '2026-09-09T15:59:59Z' },
      { id: 'next-day', createdAt: '2026-09-09T16:00:00Z' },
      { id: 'date-only', createdAt: '2026-09-09' },
    ]
    const day = { from: '2026-09-09', to: '2026-09-09' }
    expect(filterMessages(boundaries, { ...day, timeZone: 'Asia/Singapore' }).map(message => message.id)).toEqual(['midnight', 'last-second', 'date-only'])
    expect(filterMessages(boundaries, { ...day, timeZone: 'UTC' }).map(message => message.id)).toEqual(['last-second', 'next-day', 'date-only'])
  })
})

it('classifies typed records and adapter categories without guessing from the title', () => {
  const cases = [
    [{ kind: 'renewal' }, 'renewals'],
    [{ kind: 'request_decision' }, 'approvals'],
    [{ kind: 'availability_request' }, 'approvals'],
    [{ request: { type: 'session_time' }, sessionId: 's1' }, 'approvals'],
    [{ kind: 'remuneration_approval', trainerId: 't1' }, 'remuneration'],
    [{ kind: 'session_time_update' }, 'sessions'],
    [{ kind: 'saved_edit', sessionId: 's1' }, 'sessions'],
    [{ kind: 'client_assignment' }, 'people'],
    [{ kind: 'trainer_created' }, 'people'],
    [{ kind: 'content_update' }, 'updates'],
    [{ title: 'Renewal request for session payment', kind: 'system' }, 'updates'],
    [{ category: 'renewals', kind: 'vendor_event' }, 'renewals'],
    [{ category: 'unknown', kind: 'vendor_event' }, 'updates'],
  ]
  for (const [record, expected] of cases) expect(messageCategory(record)).toBe(expected)
})

it('combines category, text and inclusive dates and retains unrecognised events in All', () => {
  const records = messages.map((message, index) => ({ ...message, kind: index === 2 ? 'vendor_event' : 'renewal' }))
  expect(filterMessages(records, { category: 'renewals', query: 'amanda', from: '2026-09-02', to: '2026-09-02' }).map(item => item.id)).toEqual(['m2'])
  expect(filterMessages(records, { category: 'sessions' })).toEqual([])
  expect(filterMessages(records, { category: 'all' })).toEqual(records)
  expect(filterMessages(records, { category: 'updates' }).map(item => item.id)).toEqual(['m3'])
})
