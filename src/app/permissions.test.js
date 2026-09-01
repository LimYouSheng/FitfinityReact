import { describe, expect, it } from 'vitest'
import { directChangeAllowed, routeTrainerChange } from './permissions.js'

describe('trainer autonomy checkbox semantics', () => {
  it('checked approval-needed means direct change is not allowed', () => {
    expect(directChangeAllowed(true)).toBe(false)
  })

  it('unchecked approval-needed means direct change is allowed', () => {
    expect(directChangeAllowed(false)).toBe(true)
  })

  it('routes a supervised change into a request', () => {
    expect(routeTrainerChange({ sessionTime: true }, 'sessionTime')).toBe('request')
  })
})
