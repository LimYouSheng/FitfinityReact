import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { clientService } from './clientService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { clientProfileDraft } from '../app/clientOnboarding.js'

const owner = () => mockDb.read().users.find(item => item.role === 'owner')
const request = () => {
  const db = mockDb.read(), client = db.clients.find(item => item.id === 'c1')
  const person = clientProfileDraft(client, db.settings).people[0]
  return { personIndex: 0, formId: 'balance', expectedPerson: { name: person.name, birthday: person.birthday },
    record: { date: '2000-01-01', assessor: 'Spoofed name', answers: { eyes_open_1: 0 } } }
}
const save = options => clientService.saveAssessment('c1', options ?? request(), owner())
beforeEach(() => { localStorage.clear(); mockDb.reset(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-21T04:00:00Z')) })
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('records one unfilled profile form with canonical metadata and preserves unrelated data across reload', async () => {
  const before = mockDb.read(), saved = await save()
  expect(saved).toMatchObject({ status: 'filled', date: '2026-09-21', assessor: owner().name, answers: { eyes_open_1: 0 } })
  const after = mockDb.reload()
  expect(after.clients.find(item => item.id === 'c1').people[0].assessments.balance).toEqual(saved)
  for (const key of ['sessions', 'messages', 'trainers', 'packageCreditTransactions']) expect(after[key]).toEqual(before[key])
  expect(await save()).toEqual(saved)
  await expect(save({ ...request(), record: { answers: { eyes_open_1: 9 } } })).rejects.toThrow('already been filled')
})

it('preserves the unsaved snapshot on persistence failure and rejects stale people and inactive clients', async () => {
  const before = mockDb.read()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
  await expect(save()).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  await expect(save({ ...request(), expectedPerson: { name: 'Someone else', birthday: '1990-01-01' } })).rejects.toThrow('Client details changed')
  mockDb.mutate(db => { db.clients.find(item => item.id === 'c1').status = 'inactive' })
  await expect(save()).rejects.toThrow(/inactive/i)
})

it('denies trainer actor spoofing at the adapter and keeps couple records independent', async () => {
  const db = mockDb.read(), trainer = db.users.find(item => item.role === 'trainer')
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: trainer.id, expiresAt: Date.now() + 3600000 }))
  await expect(mockPortalAdapter.invoke({ service: 'clientService', operation: 'saveAssessment', input: { id: 'c1', assessment: request() } })).rejects.toThrow('owner')
  mockDb.mutate(state => {
    const client = state.clients.find(item => item.id === 'c1')
    const first = clientProfileDraft(client, state.settings).people[0]
    client.type = 'Couple'; client.people = [first, { ...first, name: 'Second Person', assessments: {} }]
  })
  const original = mockDb.read().clients.find(item => item.id === 'c1').people[0]
  await save({ ...request(), personIndex: 1, expectedPerson: { name: 'Second Person', birthday: original.birthday } })
  const people = mockDb.reload().clients.find(item => item.id === 'c1').people
  expect(people[0]).toEqual(original)
  expect(people[1].assessments.balance.answers.eyes_open_1).toBe(0)
})
