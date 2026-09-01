import { describe, expect, it } from 'vitest'
import { packageDayProgress } from './date.js'

describe('package progress', () => {
  it('never returns a negative day count', () => {
    expect(packageDayProgress('2026-09-10', 90, '2026-08-31')).toBe(0)
  })
  it('caps progress at validity days', () => {
    expect(packageDayProgress('2026-01-01', 90, '2026-08-31')).toBe(90)
  })
})
