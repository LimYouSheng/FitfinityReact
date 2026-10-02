import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { MOCK_SESSION_KEY } from './authService.js'

const paths = [
  { name: 'Owner edit', kind: 'details', role: 'owner' },
  { name: 'Admin edit', kind: 'details', role: 'admin' },
  { name: 'autonomous time change', kind: 'time', role: 'trainer' },
  { name: 'autonomous trainer change', kind: 'trainer', role: 'trainer' },
  { name: 'time request submission', kind: 'time', role: 'trainer', supervised: true },
  { name: 'trainer request submission', kind: 'trainer', role: 'trainer', supervised: true },
  { name: 'Owner time approval', kind: 'time', role: 'owner', supervised: true, approval: true },
  { name: 'Admin trainer approval', kind: 'trainer', role: 'admin', supervised: true, approval: true },
]
let original
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-26T00:00:00Z'))
  mockDb.reset('2026-09-26')
  mockDb.mutate(db => {
    if (!db.users.some(user => user.role === 'admin')) db.users.push({ id: 'audit-admin', role: 'admin', name: 'Admin', status: 'active' })
    for (const id of ['c1', 'c2']) {
      const client = db.clients.find(item => item.id === id)
      client.status = 'active'
      Object.assign(client.package, { status: 'active', startDate: '2026-09-01', endDate: '2026-12-31' })
    }
    for (const trainer of db.trainers) trainer.status = 'active'
    original = {
      ...db.sessions.find(session => session.id === 's1'),
      date: '2026-09-27', from: '10:00', to: '11:00', trainerId: 't1',
      packageId: db.clients.find(client => client.id === 'c1').package.id,
      status: 'planned', acknowledgement: null, acknowledgementHistory: [],
      outcome: { durationMinutes: 60, trainerComments: 'Retain coaching notes' },
    }
    db.sessions = [structuredClone(original)]
    db.messages = []
  })
})
afterEach(() => { vi.useRealTimers(); localStorage.removeItem(MOCK_SESSION_KEY) })

function signIn(role) {
  const user = mockDb.read().users.find(item => role === 'trainer' ? item.trainerId === 't1' : item.role === role)
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: user.id, expiresAt: Date.now() + 3600000 }))
}

function proposal(path) {
  const current = mockDb.read().sessions.find(session => session.id === original.id)
  return path.kind === 'trainer'
    ? { date: current.date, from: current.from, to: current.to, trainerId: 't2' }
    : { date: current.date, from: '12:15', to: '13:00', trainerId: path.kind === 'details' ? 't2' : 't1' }
}

function anotherBooking(slot, subject = 'trainer', changes = {}) {
  const clientId = subject === 'client' ? original.clientId : 'c2'
  const purchased = mockDb.read().clients.find(client => client.id === clientId).package
  return { ...original, ...slot, id: `other-${subject}`, clientId, packageId: purchased.id,
    trainerId: subject === 'client' ? 't3' : slot.trainerId, status: 'not_planned', ...changes }
}

async function prepare(path) {
  mockDb.mutate(db => { db.trainers.find(trainer => trainer.id === 't1').approvalNeeded = {
    ...db.trainers.find(trainer => trainer.id === 't1').approvalNeeded,
    sessionTime: Boolean(path.supervised), trainerReassignment: Boolean(path.supervised),
  } })
  const slot = proposal(path)
  const submit = async () => {
    signIn(path.kind === 'details' ? path.role : 'trainer')
    if (path.kind === 'details') return mockPortalAdapter.invoke({ service: 'sessionService', operation: 'updateDetails', input: { sessionId: original.id, patch: slot } })
    const method = path.kind === 'time' ? 'requestTimeChange' : 'requestTrainerChange'
    return mockPortalAdapter.invoke({ service: 'sessionService', operation: method, input: { sessionId: original.id, ...(path.kind === 'time' ? { patch: slot } : { replacementTrainerId: slot.trainerId }) } })
  }
  if (!path.approval) return submit
  await submit()
  const request = mockDb.read().messages.find(message => message.request?.sessionId === original.id)
  return async () => {
    signIn(path.role)
    return mockPortalAdapter.invoke({ service: 'requestService', operation: 'resolve', input: { id: request.id, decision: 'approved' } })
  }
}

it.each(paths.flatMap(path => ['trainer', 'client'].map(subject => ({ ...path, subject }))))(
  '$name blocks an overlapping $subject booking without any partial mutation', async path => {
    const change = await prepare(path)
    // For approvals, the booking appeared after submission; approval must recheck.
    const slot = proposal(path)
    mockDb.mutate(db => { db.sessions.push(anotherBooking({ ...slot, from: path.kind === 'trainer' ? '10:30' : '12:30', to: '13:30' }, path.subject)) })
    const before = mockDb.read()
    const action = path.subject === 'trainer' ? 'Choose another time or trainer.' : 'Choose another time.'
    await expect(change()).rejects.toThrow(`The change conflicts with another session for this ${path.subject}. ${action}`)
    expect(mockDb.read()).toEqual(before)
    expect(mockDb.reload()).toEqual(before)
  },
)

it.each(paths)('$name permits agreed exceptions and adjacent bookings while preserving purchase and credits', async path => {
  mockDb.mutate(db => {
    const session = db.sessions[0]
    session.date = '2027-01-05'
    session.to = '10:45'
    session.outcome.durationMinutes = 45
    for (const trainer of db.trainers) trainer.availability = {}
  })
  const slot = proposal(path)
  mockDb.mutate(db => { db.sessions.push(
    anotherBooking({ ...slot, from: '09:00', to: slot.from }, 'trainer', { id: 'adjacent-before' }),
    anotherBooking({ ...slot, from: slot.to, to: '14:00' }, 'client', { id: 'adjacent-after' }),
  ) })
  const before = mockDb.read()
  const change = await prepare(path)
  await change()
  if (path.supervised && !path.approval) {
    expect(mockDb.read().sessions).toEqual(before.sessions)
    const request = mockDb.read().messages.find(message => message.request?.sessionId === original.id)
    signIn('owner')
    await mockPortalAdapter.invoke({ service: 'requestService', operation: 'resolve', input: { id: request.id, decision: 'approved' } })
  }
  const after = mockDb.reload()
  expect(after.sessions.find(session => session.id === original.id)).toMatchObject({
    ...slot, packageId: original.packageId, outcome: { durationMinutes: 45, trainerComments: 'Retain coaching notes' },
  })
  expect(after.clients).toEqual(before.clients)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
})

it.each(['owner', 'admin'])('%s can correct a past unfinished session but cannot overlap completed history', async role => {
  const path = { kind: 'details', role }
  mockDb.mutate(db => {
    db.sessions[0].date = '2026-09-20'
    db.clients.find(client => client.id === 'c2').package.status = 'inactive'
  })
  const slot = proposal(path)
  const change = await prepare(path)
  const clear = mockDb.read()
  for (const subject of ['trainer', 'client']) {
    mockDb.mutate(db => { db.sessions.push(anotherBooking(slot, subject, { status: 'completed' })) })
    const before = mockDb.read()
    await expect(change()).rejects.toThrow('conflicts')
    expect(mockDb.read()).toEqual(before)
    mockDb.write(clear)
  }
  await change()
  expect(mockDb.read().sessions[0]).toMatchObject(slot)
})

it('does not reserve cancelled sessions or unfinished sessions in inactive packages', async () => {
  const path = paths[0]
  const slot = proposal(path)
  mockDb.mutate(db => {
    db.sessions.push(anotherBooking(slot, 'client', { status: 'cancelled' }), anotherBooking(slot))
    db.clients.find(client => client.id === 'c2').package.status = 'inactive'
  })
  const change = await prepare(path)
  await change()
  expect(mockDb.read().sessions[0]).toMatchObject(slot)
})

it('keeps completed and cancelled subjects locked for direct edits and trainer replacement', async () => {
  for (const status of ['completed', 'cancelled']) {
    mockDb.mutate(db => { db.sessions[0].status = status })
    for (const path of [paths[0], paths[1], paths[3]]) {
      const change = await prepare(path)
      const before = mockDb.read()
      await expect(change()).rejects.toThrow('locked')
      expect(mockDb.read()).toEqual(before)
    }
  }
})
