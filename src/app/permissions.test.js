import { describe, expect, it } from 'vitest'
import { canEditClientCoachingNotes, directChangeAllowed, routeTrainerChange } from './permissions.js'

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

it('grants coaching notes for a started concurrent purchase without general or future assignment powers', () => {
  const trainer = { role: 'trainer', trainerId: 'parallel-trainer' }
  const purchase = { trainerId: trainer.trainerId, status: 'active', startDate: '2020-01-01', endDate: '2099-12-31' }
  const client = { trainerId: 'default-trainer', status: 'active', additionalPackages: [purchase] }
  expect(canEditClientCoachingNotes(trainer, client)).toBe(true)
  for (const patch of [{ status: 'inactive' }, { startDate: '2099-01-01' }, { endDate: '2020-12-31' }, { trainerId: 'foreign' }]) {
    expect(canEditClientCoachingNotes(trainer, { ...client, additionalPackages: [{ ...purchase, ...patch }] })).toBe(false)
  }
  expect(canEditClientCoachingNotes(trainer, { ...client, status: 'inactive' })).toBe(false)
  expect(canEditClientCoachingNotes({ role: 'unknown', trainerId: trainer.trainerId }, client)).toBe(false)
})
