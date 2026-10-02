import { webcrypto } from 'node:crypto'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { authService, MOCK_SESSION_KEY } from './authService.js'
import { mockDb } from './mockDb.js'
import { mockAccountPassword } from '../data/mockPolicy.js'
import { createPortalServices } from './portalService.js'
import { PORTAL_CONTRACTS, AUTH_CONTRACTS } from './portalContracts.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { contentService } from './contentService.js'
import { sessionService } from './sessionService.js'
import { signatureFixture } from '../test/fixtures/signature.js'
import { clientService } from './clientService.js'
import { clientProfileDraft } from '../app/clientOnboarding.js'

const owner = () => mockDb.read().users.find(item => item.role === 'owner')
const content = {title:'About the studio',key:'about',body:'Our studio details',status:'draft'}
beforeEach(() => { localStorage.clear(); mockDb.reset(); vi.stubGlobal('crypto', webcrypto) })
afterEach(() => vi.unstubAllGlobals())
describe('M4 account and service contract', () => {
  it('requires sign-in, rejects invalid credentials and does not select a default owner', async () => {
    expect((await mockPortalAdapter.load()).user).toBeNull()
    await expect(authService.signIn({identifier:owner().id,password:'wrong'})).rejects.toThrow('incorrect')
    await authService.signIn({identifier:owner().id,password:mockAccountPassword})
    expect(authService.current().id).toBe(owner().id)
    await authService.signOut(); expect(authService.current()).toBeNull()
    await expect(mockPortalAdapter.invoke({ service: 'contentService', operation: 'save', input: {draft:content} })).rejects.toMatchObject({code:'SESSION_EXPIRED'})
  })
  it('changes passwords with current-password verification and never persists plaintext', async () => {
    const id=owner().id
    await authService.signIn({identifier:id,password:mockAccountPassword})
    const values={currentPassword:'wrong',newPassword:'ChangedDemoPassword42!',confirmation:'ChangedDemoPassword42!'}
    await expect(authService.changePassword(values)).rejects.toThrow('current password')
    await authService.changePassword({...values,currentPassword:mockAccountPassword})
    expect(localStorage.getItem('fitfinity-demo-credentials-v1')).not.toContain(values.newPassword)
    await authService.signOut()
    await expect(authService.signIn({identifier:id,password:mockAccountPassword})).rejects.toThrow('incorrect')
    await authService.signIn({identifier:id,password:values.newPassword})
    expect(authService.current().id).toBe(id)
  })
  it('expires sessions, rejects malformed records and notices deactivation', async () => {
    localStorage.setItem(MOCK_SESSION_KEY,'invalid'); expect(authService.current()).toBeNull()
    localStorage.setItem(MOCK_SESSION_KEY,JSON.stringify({userId:owner().id,expiresAt:Date.now()-1})); expect(authService.current()).toBeNull()
    await authService.signIn({identifier:owner().id,password:mockAccountPassword})
    mockDb.mutate(db => { db.users.find(item=>item.role==='owner').status='inactive' })
    expect(authService.current()).toBeNull()
  })
  it('delegates through a replaceable asynchronous adapter and propagates errors', async () => {
    const adapter={load:vi.fn().mockResolvedValue({user:null}),reset:vi.fn(),session:vi.fn(),invoke:vi.fn().mockRejectedValue(new Error('Offline'))}
    const api=createPortalServices(adapter)
    expect(await api.load()).toEqual({user:null})
    await expect(api.contentService.save({draft:content})).rejects.toThrow('Offline')
    expect(adapter.invoke).toHaveBeenCalledWith({ service: 'contentService', operation: 'save', input: { draft: content } })
    await api.auth.signOut(); expect(adapter.session).toHaveBeenCalledWith({ operation: 'signOut', input: {} })

    const input = { reference: 'opaque input for the fake adapter' }
    for (const [domain, methods] of Object.entries(PORTAL_CONTRACTS)) {
      expect(Object.keys(api[domain])).toEqual(Object.keys(methods))
      for (const method of Object.keys(methods)) {
        const saved = { id: 'canonical-record', domain, method }
        adapter.invoke.mockResolvedValueOnce(saved)
        const result = api[domain][method](input)
        expect(result).toBeInstanceOf(Promise)
        await expect(result).resolves.toBe(saved)
        expect(adapter.invoke).toHaveBeenLastCalledWith({ service: domain, operation: method, input })
        const error = new Error(`${domain}.${method} unavailable`)
        adapter.invoke.mockRejectedValueOnce(error)
        await expect(api[domain][method](input)).rejects.toBe(error)
      }
    }
    for (const method of Object.keys(AUTH_CONTRACTS)) {
      const saved = { method }
      adapter.session.mockResolvedValueOnce(saved)
      const result = api.auth[method](input)
      expect(result).toBeInstanceOf(Promise)
      await expect(result).resolves.toBe(saved)
      expect(adapter.session).toHaveBeenLastCalledWith({ operation: method, input })
      const error = Object.assign(new Error('Account unavailable'), { code: 'SESSION_EXPIRED' })
      adapter.session.mockRejectedValueOnce(error)
      await expect(api.auth[method](input)).rejects.toBe(error)
    }
    for (const method of ['load', 'reset']) {
      const saved = { user: null }
      adapter[method].mockResolvedValueOnce(saved)
      const result = api[method]()
      expect(result).toBeInstanceOf(Promise)
      await expect(result).resolves.toBe(saved)
      expect(adapter[method]).toHaveBeenLastCalledWith()
      const error = new Error('Snapshot unavailable')
      adapter[method].mockRejectedValueOnce(error)
      await expect(api[method]()).rejects.toBe(error)
    }
  })
  it('rejects trainer calls to owner actions and other trainers sessions', async () => {
    const trainer=mockDb.read().users.find(item=>item.role==='trainer')
    await authService.signIn({identifier:trainer.id,password:mockAccountPassword})
    await expect(mockPortalAdapter.invoke({ service: 'contentService', operation: 'save', input: {draft:content} })).rejects.toThrow('owner')
    await expect(mockPortalAdapter.invoke({ service: 'trainerService', operation: 'updateAutonomy', input: { id: 't1', approvalNeeded: {} } })).rejects.toThrow('owner')
    const other=mockDb.read().sessions.find(item=>item.trainerId!==trainer.trainerId)
    await expect(mockPortalAdapter.invoke({ service: 'sessionService', operation: 'saveOutcome', input: { sessionId: other.id, outcome: {durationMinutes:55} } })).rejects.toThrow('unavailable')
    await expect(mockPortalAdapter.invoke({ service: 'sessionService', operation: 'acknowledge', input: { sessionId: other.id, acknowledgement: {method:'late_no_show'} } })).rejects.toThrow('unavailable')
    const result = await mockPortalAdapter.invoke({ service: 'sessionService', operation: 'acknowledge', input: { sessionId: 's1', acknowledgement: { method: 'late_no_show' } } })
    expect(result.session.acknowledgement.recordedBy).toEqual({ id: trainer.id, name: trainer.name, role: trainer.role })
  })
})
describe('M4 persisted frontend records', () => {
  it('saves individual profile contacts through the adapter with synchronized person fields and unchanged session evidence', async () => {
    await authService.signIn({ identifier: owner().id, password: mockAccountPassword })
    const before = mockDb.read(), original = before.clients[0]
    const person = clientProfileDraft(original, before.settings).people[0]
    const people = [{ ...person, name: 'Amanda Lee', gender: 'Prefer not to say', phone: { countryCode: '+60', number: '123456789' } }]
    await mockPortalAdapter.invoke({ service: 'clientService', operation: 'update', input: { id: original.id, patch: { people } } })
    const after = mockDb.reload(), client = after.clients[0]
    expect(client).toMatchObject({ name: 'Amanda Lee', gender: 'Prefer not to say', phone: people[0].phone, people })
    expect(client.package).toEqual(original.package)
    expect(client.packageHistory).toEqual(original.packageHistory)
    expect(client.strengthProgress).toEqual(original.strengthProgress)
    expect(after.sessions).toEqual(before.sessions)
    expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
    await clientService.update(client.id, { healthNotes: 'Updated coaching notes' }, mockDb.read().users.find(user => user.role === 'owner'))
    expect(mockDb.reload().clients[0].people[0].healthNotes).toBe('Updated coaching notes')
    const trainer = mockDb.read().users.find(item => item.trainerId === client.trainerId)
    await authService.switchDemoIdentity(trainer.id)
    const saved = mockDb.read()
    await expect(mockPortalAdapter.invoke({ service: 'clientService', operation: 'update', input: { id: client.id, patch: { people } } })).rejects.toThrow('owner')
    expect(mockDb.read()).toEqual(saved)
  })
  it('keeps couple people distinct, preserves independent coaching notes and rejects invalid or incomplete profile changes atomically', async () => {
    const before = mockDb.read(), client = before.clients.find(item => item.type === 'Couple')
    const legacy = clientProfileDraft(client, before.settings)
    expect(legacy.people.map(person => person.name)).toEqual([client.name, ''])
    await expect(clientService.update(client.id, { people: legacy.people }, mockDb.read().users.find(user => user.role === 'owner'))).rejects.toThrow()
    await expect(clientService.update(client.id, { people: [] }, mockDb.read().users.find(user => user.role === 'owner'))).rejects.toThrow('Review each')
    expect(mockDb.read()).toEqual(before)
    const people = legacy.people.map((person, index) => ({ ...person, name: index ? 'Mei Wong' : 'Daniel Wong', gender: index ? 'Female' : 'Male', healthNotes: index ? 'Shoulder mobility' : 'Knee mobility' }))
    await clientService.update(client.id, { people }, mockDb.read().users.find(user => user.role === 'owner'))
    await clientService.update(client.id, { healthNotes: 'Updated shared coaching notes' }, mockDb.read().users.find(user => user.role === 'owner'))
    const saved = mockDb.read()
    await expect(clientService.update(client.id, { people: people.map(person => ({ ...person, gender: 'invalid' })) }, mockDb.read().users.find(user => user.role === 'owner'))).rejects.toThrow('gender')
    expect(mockDb.read()).toEqual(saved)
    people[1].email = 'mei.updated@example.com'
    await clientService.update(client.id, { people }, mockDb.read().users.find(user => user.role === 'owner'))
    const after = mockDb.reload(), result = after.clients.find(item => item.id === client.id)
    expect(result).toMatchObject({ name: 'Daniel Wong & Mei Wong', gender: 'Couple', email: people[0].email, people, healthNotes: 'Updated shared coaching notes' })
    expect(result.package).toEqual(client.package)
    expect(after.sessions).toEqual(before.sessions)
    expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  })
  it('creates, reloads, edits and archives content with version and duplicate-key protection', async () => {
    const created=await contentService.save({draft:content},owner())
    expect(mockDb.reload().contentEntries[0]).toEqual(created)
    const updated=await contentService.save({id:created.id,expectedVersion:1,draft:{...content,status:'archived'}},owner())
    expect(updated).toMatchObject({id:created.id,status:'archived',version:2})
    await expect(contentService.save({id:created.id,expectedVersion:1,draft:content},owner())).rejects.toThrow('changed')
    await expect(contentService.save({draft:content},owner())).rejects.toThrow('already')
    expect(mockDb.read().messages.some(message=>message.contentId===created.id)).toBe(true)
  })
  it('keeps data unchanged on failed content persistence and permits a retry', async () => {
    const original=mockDb.read()
    const storage=vi.spyOn(Storage.prototype,'setItem').mockImplementationOnce(()=>{throw new Error('Quota exceeded')})
    await expect(contentService.save({draft:content},owner())).rejects.toThrow('Quota')
    expect(mockDb.read()).toEqual(original); storage.mockRestore()
    await contentService.save({draft:content},owner()); expect(mockDb.read().contentEntries).toHaveLength(1)
  })
  it('requires drawn evidence, saves measured progress and debits only once across retries', async () => {
    await expect(sessionService.acknowledge('s1',{method:'signature',signerName:'Client',signature:[]}, owner())).rejects.toThrow('Draw')
    await sessionService.saveOutcome('s1',{durationMinutes:55,exerciseResults:[{id:'result',name:'Measured row',loadKg:20,reps:8,sets:3}]}, mockDb.read().users.find(user => user.role === 'owner'))
    const ack={method:'signature',signerName:'Client',signature:signatureFixture}
    await sessionService.acknowledge('s1',ack, owner()); await sessionService.acknowledge('s1',ack, owner())
    const db=mockDb.reload()
    expect(db.sessions.find(item=>item.id==='s1').acknowledgement.signature).toEqual(signatureFixture)
    expect(db.clients.find(item=>item.id==='c1').strengthProgress.find(item=>item.name==='Measured row').points).toHaveLength(1)
    expect(db.packageCreditTransactions.filter(item=>item.sessionId==='s1')).toHaveLength(1)
  })
})

it.each(['individual people', 'individual scalar', 'couple people', 'couple scalar'])('rejects malformed contact edits atomically through %s', async path => {
  const before = mockDb.read()
  const client = before.clients.find(row => row.type === (path.startsWith('couple') ? 'Couple' : 'Individual'))
  const draft = clientProfileDraft(client, before.settings)
  if (path.startsWith('couple')) draft.people = draft.people.map((person, index) => ({ ...person, name: `Person ${index}` }))
  for (const bad of [{ email: 'not-an-email' }, { phone: { countryCode: '+65', number: 'letters-only' } }, { birthday: '2026-02-31' }, { emergencyContact: { name: 'Contact', relationship: 'Friend', countryCode: '+65', number: 'letters-only' } }]) {
    const patch = path.endsWith('scalar') ? bad : { people: draft.people.map((person, index) => index === draft.people.length - 1 ? { ...person, ...bad } : person) }
    await expect(clientService.update(client.id, patch, owner())).rejects.toThrow()
    expect(mockDb.reload()).toEqual(before)
  }
})
it('accepts valid optional scalar contact values and real leap birthdays without requiring absent legacy fields', async () => {
  const client = mockDb.read().clients.find(row => row.type === 'Individual')
  const saved = await clientService.update(client.id, { email: 'updated@example.test', birthday: '2000-02-29', phone: { countryCode: '+65', number: '91234567' } }, owner())
  expect(saved).toMatchObject({ email: 'updated@example.test', birthday: '2000-02-29', phone: { countryCode: '+65', number: '91234567' } })
  expect(saved.people[0].birthday).toBe('2000-02-29')
})
