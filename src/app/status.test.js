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

  it('retains assigned inactive clients below active clients and excludes other trainers clients', () => {
    const user = { role: 'trainer', trainerId: 't1' }
    const clients = [
      { id: 'c1', name: 'A', trainerId: 't1', status: 'active' },
      { id: 'c2', name: 'B', trainerId: 't1', status: 'inactive' },
      { id: 'c3', name: 'C', trainerId: 't2', status: 'active' },
    ]

    expect(visibleClientsForUser(user, clients).map(item => item.id)).toEqual(['c1', 'c2'])
  })

  it('flushes inactive records to the bottom', () => {
    const records = [
      { id: 'i1', name: 'Aaron', status: 'inactive' },
      { id: 'a1', name: 'Zara', status: 'active' },
      { id: 'a2', name: 'Bella', status: 'active' },
    ]

    expect(sortActiveFirst(records).map(item => item.id)).toEqual(['a2', 'a1', 'i1'])
    expect(records.map(item => item.id)).toEqual(['i1', 'a1', 'a2'])
  })

  it('owner client list includes inactive records', () => {
    const user = { role: 'owner' }
    const clients = [
      { id: 'c1', name: 'Active', status: 'active' },
      { id: 'c2', name: 'Inactive', status: 'inactive' },
    ]

    expect(visibleClientsForUser(user, clients).map(item => item.id)).toEqual(['c1', 'c2'])
    const dated = [
      { id: 'old', name: 'Aaron', startDate: '2026-01-01', status: 'active' },
      { id: 'inactive', name: 'A', startDate: '2026-12-01', status: 'inactive' },
      { id: 'new-z', name: 'Zara', startDate: '2026-02-01' },
      { id: 'new-a', name: 'Bella', startDate: '2026-02-01', status: 'active' },
    ]
    for (const role of ['owner', 'admin']) {
      expect(visibleClientsForUser({ role }, dated).map(item => item.id)).toEqual(['new-a', 'new-z', 'old', 'inactive'])
    }
    expect(dated.map(item => item.id)).toEqual(['old', 'inactive', 'new-z', 'new-a'])
    expect(visibleClientsForUser(user, [{ id: 'z', name: 'Zara' }, { id: 'a', name: 'Aaron', startDate: '2026-02-01' }]).map(item => item.id)).toEqual(['a', 'z'])
  })
})
