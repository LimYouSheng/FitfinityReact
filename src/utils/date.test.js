import { describe, expect, it } from 'vitest'
import { formatDate, packageDayProgress, weekday } from './date.js'

describe('package progress', () => {
  it('never returns a negative day count', () => {
    expect(packageDayProgress('2026-09-10', 90, '2026-08-31')).toBe(0)
  })
  it('caps progress at validity days', () => {
    expect(packageDayProgress('2026-01-01', 90, '2026-08-31')).toBe(90)
  })
})

describe('optional profile dates', () => {
  it('renders missing birthdays without throwing', () => {
    for (const value of ['', null, undefined]) {
      expect(formatDate(value)).toBe('—')
      expect(weekday(value)).toBe('—')
    }
  })

  it('renders malformed or incomplete dates without crashing the profile', () => {
    for (const value of ['not-a-date', '2026', '2026-09']) {
      expect(formatDate(value)).toBe('—')
      expect(weekday(value)).toBe('—')
    }
  })

  it('preserves valid date formatting and full weekday names', () => {
    const expected = new Intl.DateTimeFormat('en-SG', {
      day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC',
    }).format(new Date(Date.UTC(2026, 8, 7)))
    expect(formatDate('2026-09-07')).toBe(expected)
    expect(weekday('2026-09-07')).toBe('Monday')
    expect(weekday('2026-02-28')).toBe('Saturday')
  })
})
