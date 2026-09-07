import { describe, expect, it } from 'vitest'
import { availabilityBlockError, availabilityByDay } from './availability.js'

const block = { days: ['Monday'], from: '18:00', to: '19:00' }
describe('shared availability rules', () => {
  it('rejects absent days, malformed times and duplicate blocks', () => {
    expect(availabilityBlockError({ ...block, days: [] })).toBeTruthy()
    expect(availabilityBlockError({ ...block, from: '25:00' })).toBeTruthy()
    expect(availabilityBlockError(block, [block])).toContain('already')
  })
  it('allows adjacent windows but rejects overlapping trainer windows only', () => {
    const overlapping = { ...block, from: '18:30', to: '19:30' }
    expect(availabilityBlockError(overlapping, [block], true)).toContain('overlaps')
    expect(availabilityBlockError(overlapping, [block], false)).toBe('')
    expect(availabilityBlockError({ ...block, from: '19:00', to: '20:00' }, [block], true)).toBe('')
  })
  it('copies and sorts multi-day blocks without sharing stored arrays', () => {
    const value = { ...block, days: ['Monday', 'Wednesday'] }
    const result = availabilityByDay([value, { ...block, from: '08:00', to: '09:00' }])
    expect(result.Monday).toEqual([['08:00', '09:00'], ['18:00', '19:00']])
    expect(result.Wednesday).toEqual([['18:00', '19:00']])
    result.Monday[1][0] = '17:00'
    expect(result.Wednesday[0][0]).toBe('18:00')
    expect(value.from).toBe('18:00')
    expect(Object.keys(result)).toHaveLength(7)
  })
})
