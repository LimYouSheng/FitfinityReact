import { describe, expect, it } from 'vitest'
import {
  activeTrainers,
  sortActiveFirst,
  trainerSelectableForAvailability,
  visibleClientsForUser,
} from './status.js'

describe('active/inactive foundation', () => {
  it('never exposes an inactive trainer to availability selection', () => {
    const trainers = [
      { id: 't1', name: 'Active', status: 'active' },
      { id: 't2', name: 'Inactive', status: 'inactive' },
    ]

    expect(activeTrainers(trainers).map(item => item.id)).toEqual(['t1'])
    expect(trainerSelectableForAvailability(trainers[1])).toBe(false)
  })

  it('removes inactive clients from trainer active-client view', () => {
    const user = { role: 'trainer', trainerId: 't1' }
    const clients = [
      { id: 'c1', name: 'A', trainerId: 't1', status: 'active' },
      { id: 'c2', name: 'B', trainerId: 't1', status: 'inactive' },
      { id: 'c3', name: 'C', trainerId: 't2', status: 'active' },
    ]

    expect(visibleClientsForUser(user, clients).map(item => item.id)).toEqual(['c1'])
  })

  it('flushes inactive records to the bottom', () => {
    const records = [
      { id: 'i1', name: 'Aaron', status: 'inactive' },
      { id: 'a1', name: 'Zara', status: 'active' },
      { id: 'a2', name: 'Bella', status: 'active' },
    ]

    expect(sortActiveFirst(records).map(item => item.id)).toEqual(['a2', 'a1', 'i1'])
  })

  it('owner client list includes inactive records', () => {
    const user = { role: 'owner' }
    const clients = [
      { id: 'c1', name: 'Active', status: 'active' },
      { id: 'c2', name: 'Inactive', status: 'inactive' },
    ]

    expect(visibleClientsForUser(user, clients).map(item => item.id)).toEqual(['c1', 'c2'])
  })
})
