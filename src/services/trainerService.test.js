import { mockPolicy } from '../data/mockPolicy.js'
import { beforeEach, describe, expect, it } from 'vitest'
import { trainerService } from './trainerService.js'
import { mockDb } from './mockDb.js'
import { createTrainerDraft } from '../app/trainerOnboarding.js'
import { matchTrainers } from '../app/clientOnboarding.js'

const draft = (email = 'm3-new-trainer@example.com') => ({ ...createTrainerDraft(mockPolicy), name: 'M3 Trainer', email,
  gender: 'Female', trainerType: 'Personal', phone: { countryCode: '+65', number: '91234567' }, birthday: '1990-01-02',
  availabilityBlocks: [{ id: 'one', days: ['Sunday'], from: '10:00', to: '12:00' }] })
const owner = () => mockDb.read().users.find(user => user.role === 'owner')

beforeEach(() => mockDb.reset())

describe('trainer creation service', () => {
  it('applies creation validation to profile edits, synchronizes staff identity and preserves sessions and decimal rates on reload', async () => {
    const before = mockDb.read(), trainer = before.trainers[0]
    for (const patch of [{ gender: 'invalid' }, { phone: '+65 abc' }, { rates: { peak: '', offPeak: 55 } }, { rates: { peak: 80.251, offPeak: 55 } }, { email: before.trainers[1].email }]) {
      await expect(trainerService.update(trainer.id, patch)).rejects.toThrow()
      expect(mockDb.read()).toEqual(before)
    }
    await trainerService.update(trainer.id, { name: 'Marcus Lee', email: ' MARCUS.UPDATED@EXAMPLE.COM ', phone: '+60 123456789', gender: 'Male', qualifications: 'Updated certification\nFirst aid', rates: { peak: 80.25, offPeak: 55.50 } })
    const after = mockDb.reload(), updated = after.trainers.find(item => item.id === trainer.id)
    expect(updated).toMatchObject({ name: 'Marcus Lee', email: 'marcus.updated@example.com', phone: '+60 123456789', rates: { peak: 80.25, offPeak: 55.50 } })
    expect(after.users.find(item => item.trainerId === trainer.id)).toMatchObject({ name: updated.name, email: updated.email })
    expect(updated.availability).toEqual(trainer.availability)
    expect(after.clients).toEqual(before.clients)
    expect(after.sessions).toEqual(before.sessions)
  })
  it('atomically creates the profile, demo identity and independently unread routed messages', async () => {
    const result = await trainerService.create(draft(), owner())
    const state = mockDb.read()
    expect(state.trainers.find(item => item.id === result.id)).toEqual(result)
    expect(state.users.find(user => user.trainerId === result.id)).toMatchObject({ role: 'trainer', status: 'active', email: draft().email })
    const messages = state.messages.filter(message => message.trainerId === result.id)
    expect(messages).toHaveLength(2)
    expect(messages.every(message => message.read === false && message.kind === 'trainer_created')).toBe(true)
    expect(messages.some(message => message.recipientRole === 'owner')).toBe(true)
    expect(messages.some(message => message.recipientTrainerId === result.id && !message.recipientRole)).toBe(true)
  })
  it('rolls back completely on invalid fields or overlapping availability', async () => {
    const before = mockDb.read()
    await expect(trainerService.create({ ...draft(), rates: { peak: '-1', offPeak: 55 } }, owner())).rejects.toThrow()
    const duplicate = draft()
    duplicate.availabilityBlocks.push({ days: ['Sunday'], from: '11:00', to: '13:00' })
    await expect(trainerService.create(duplicate, owner())).rejects.toThrow('overlaps')
    expect(mockDb.read()).toEqual(before)
  })
  it('requires an active stored owner, not just a client-provided role', async () => {
    const before = mockDb.read()
    for (const actor of [undefined, { id: 'not-a-user', role: 'owner' }, mockDb.read().users.find(user => user.role === 'trainer')]) {
      await expect(trainerService.create(draft(), actor)).rejects.toThrow('active owner')
    }
    expect(mockDb.read()).toEqual(before)
    const disabled = owner()
    mockDb.mutate(state => { state.users.find(user => user.id === disabled.id).status = 'inactive' })
    const disabledState = mockDb.read()
    await expect(trainerService.create(draft(), disabled)).rejects.toThrow('active owner')
    expect(mockDb.read()).toEqual(disabledState)
  })
  it('rejects duplicate email regardless of case or inactive status', async () => {
    const result = await trainerService.create(draft(), owner())
    await trainerService.deactivate(result.id)
    const before = mockDb.read()
    await expect(trainerService.create(draft(' M3-NEW-TRAINER@EXAMPLE.COM '), owner())).rejects.toThrow('already belongs')
    expect(mockDb.read()).toEqual(before)
  })
  it('does not mutate existing trainers, clients, sessions or messages on success', async () => {
    const before = mockDb.read()
    await trainerService.create(draft(), owner())
    const after = mockDb.read()
    expect(after.clients).toEqual(before.clients)
    expect(after.sessions).toEqual(before.sessions)
    expect(after.trainers.slice(0, before.trainers.length)).toEqual(before.trainers)
    expect(after.messages.slice(0, before.messages.length)).toEqual(before.messages)
  })
  it('prevents double-submission from creating duplicate accounts or messages', async () => {
    const before = mockDb.read()
    const outcomes = await Promise.allSettled([trainerService.create(draft(), owner()), trainerService.create(draft(), owner())])
    expect(outcomes.filter(result => result.status === 'fulfilled')).toHaveLength(1)
    expect(mockDb.read().trainers).toHaveLength(before.trainers.length + 1)
    expect(mockDb.read().messages).toHaveLength(before.messages.length + 2)
  })
  it('makes the new active trainer immediately matchable and excludes them after deactivation', async () => {
    const result = await trainerService.create(draft(), owner())
    const preferences = [{ days: ['Sunday'], from: '10:00', to: '11:00' }]
    expect(matchTrainers(mockDb.read().trainers, preferences).some(item => item.trainer.id === result.id)).toBe(true)
    await trainerService.deactivate(result.id)
    expect(matchTrainers(mockDb.read().trainers, preferences).some(item => item.trainer.id === result.id)).toBe(false)
  })
})
