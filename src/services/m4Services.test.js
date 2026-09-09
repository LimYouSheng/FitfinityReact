import { webcrypto } from 'node:crypto'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { authService, MOCK_SESSION_KEY } from './authService.js'
import { mockDb } from './mockDb.js'
import { mockAccountPassword } from '../data/mockPolicy.js'
import { createPortalServices, PORTAL_OPERATIONS } from './portalService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { contentService } from './contentService.js'
import { sessionService } from './sessionService.js'
import { signatureFixture } from '../test/fixtures/signature.js'

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
    await expect(mockPortalAdapter.invoke('contentService','save',[{draft:content},owner()])).rejects.toMatchObject({code:'SESSION_EXPIRED'})
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
    expect(adapter.invoke).toHaveBeenCalledWith('contentService','save',[{draft:content}])
    await api.auth.signOut(); expect(adapter.session).toHaveBeenCalledWith('signOut',[])

    const args = ['external-record', { expectedVersion: 7 }]
    for (const [domain, methods] of Object.entries(PORTAL_OPERATIONS)) {
      expect(Object.keys(api[domain])).toEqual(methods)
      for (const method of methods) {
        const saved = { id: 'canonical-record', domain, method }
        adapter.invoke.mockResolvedValueOnce(saved)
        const result = api[domain][method](...args)
        expect(result).toBeInstanceOf(Promise)
        await expect(result).resolves.toBe(saved)
        expect(adapter.invoke).toHaveBeenLastCalledWith(domain, method, args)
        const error = new Error(`${domain}.${method} unavailable`)
        adapter.invoke.mockRejectedValueOnce(error)
        await expect(api[domain][method](...args)).rejects.toBe(error)
      }
    }
    for (const method of ['signIn', 'signOut', 'changePassword', 'switchDemoIdentity']) {
      const saved = { method }
      adapter.session.mockResolvedValueOnce(saved)
      const result = api.auth[method](...args)
      expect(result).toBeInstanceOf(Promise)
      await expect(result).resolves.toBe(saved)
      expect(adapter.session).toHaveBeenLastCalledWith(method, args)
      const error = Object.assign(new Error('Account unavailable'), { code: 'SESSION_EXPIRED' })
      adapter.session.mockRejectedValueOnce(error)
      await expect(api.auth[method](...args)).rejects.toBe(error)
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
    await expect(mockPortalAdapter.invoke('contentService','save',[{draft:content},owner()])).rejects.toThrow('owner')
    await expect(mockPortalAdapter.invoke('trainerService','updateAutonomy',['t1',{}])).rejects.toThrow('owner')
    const other=mockDb.read().sessions.find(item=>item.trainerId!==trainer.trainerId)
    await expect(mockPortalAdapter.invoke('sessionService','saveOutcome',[other.id,{durationMinutes:55}])).rejects.toThrow('unavailable')
  })
})
describe('M4 persisted frontend records', () => {
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
    await expect(sessionService.acknowledge('s1',{method:'signature',signerName:'Client',signature:[]})).rejects.toThrow('Draw')
    await sessionService.saveOutcome('s1',{durationMinutes:55,exerciseResults:[{id:'result',name:'Measured row',loadKg:20,reps:8,sets:3}]})
    const ack={method:'signature',signerName:'Client',signature:signatureFixture}
    await sessionService.acknowledge('s1',ack); await sessionService.acknowledge('s1',ack)
    const db=mockDb.reload()
    expect(db.sessions.find(item=>item.id==='s1').acknowledgement.signature).toEqual(signatureFixture)
    expect(db.clients.find(item=>item.id==='c1').strengthProgress.find(item=>item.name==='Measured row').points).toHaveLength(1)
    expect(db.packageCreditTransactions.filter(item=>item.sessionId==='s1')).toHaveLength(1)
  })
})
