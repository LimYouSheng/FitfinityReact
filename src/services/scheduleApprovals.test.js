import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { clientService } from './clientService.js'
import { trainerService } from './trainerService.js'
import { requestService } from './requestService.js'
let owner, trainer, nextSlots
const blocks = [{ id:'new', days:['Monday','Wednesday'], from:'09:00',to:'12:00' }]
const pending = type => mockDb.read().messages.findLast(message => message.request?.type === type)
beforeEach(() => {
  vi.useFakeTimers({toFake:['Date']}); vi.setSystemTime(new Date('2026-09-05T02:00:00Z'))
  mockDb.reset()
  mockDb.mutate(db => {
    owner = db.users.find(user => user.role === 'owner')
    trainer = db.users.find(user => user.trainerId === 't1')
    const client = db.clients.find(item => item.id === 'c1')
    nextSlots = client.fixedWeeklySchedule.map(slot => ({...slot,from:'19:00',to:'20:00'}))
    const source = db.sessions.find(session => session.clientId === 'c1')
    db.sessions = [
      {...source,id:'future',date:'2026-09-07',from:'18:00',to:'19:00',status:'planned',trainerId:'t1'},
      {...source,id:'past',date:'2026-08-31',from:'18:00',to:'19:00',status:'planned',trainerId:'t1'},
      {...source,id:'completed',date:'2026-09-14',from:'18:00',to:'19:00',status:'completed',trainerId:'t1'},
      {...source,id:'cancelled',date:'2026-09-21',from:'18:00',to:'19:00',status:'cancelled',trainerId:'t1'},
      {...source,id:'ad-hoc',date:'2026-09-28',from:'09:00',to:'10:00',status:'planned',trainerId:'t1'},
      {...source,id:'expired',date:'2026-11-16',from:'18:00',to:'19:00',status:'planned',trainerId:'t1'},
      {...source,id:'replacement',date:'2026-10-05',from:'18:00',to:'19:00',status:'planned',trainerId:'t2'},
    ]
  })
})
afterEach(() => vi.useRealTimers())
it('supervised availability preserves approved data and creates linked pending messages', async () => {
  const before = mockDb.read().trainers
  expect((await trainerService.saveAvailability('t1',blocks,trainer)).outcome).toBe('requested')
  expect(mockDb.read().trainers).toEqual(before)
  const request = pending('trainer_availability')
  expect(request.request.newAvailability.Monday).toEqual([['09:00','12:00']])
  expect(mockDb.read().messages.find(message => message.requestId === request.id)).toMatchObject({status:'pending',recipientTrainerId:'t1'})
})
it('autonomous availability changes immediately and emits a related message', async () => {
  mockDb.mutate(db => { db.trainers.find(item => item.id==='t1').approvalNeeded.availability=false })
  expect((await trainerService.saveAvailability('t1',blocks,trainer)).outcome).toBe('applied')
  expect(mockDb.read().trainers.find(item=>item.id==='t1').availability.Monday).toEqual([['09:00','12:00']])
  expect(pending('trainer_availability')).toBeUndefined()
  expect(mockDb.read().messages.findLast(message=>message.kind==='availability_update')).toMatchObject({read:false,trainerId:'t1'})
})
it('availability rejects owner editing, spoofed identities and another trainer', async () => {
  const before=mockDb.read()
  for (const actor of [owner,{...trainer,id:'unknown'},mockDb.read().users.find(user=>user.trainerId==='t2')]) await expect(trainerService.saveAvailability('t1',blocks,actor)).rejects.toThrow()
  expect(mockDb.read()).toEqual(before)
})
it('overlapping availability fails without any partial writes', async () => {
  const before=mockDb.read()
  await expect(trainerService.saveAvailability('t1',[...blocks,{days:['Monday'],from:'11:00',to:'13:00'}],trainer)).rejects.toThrow('overlaps')
  expect(mockDb.read()).toEqual(before)
})
it('availability approval applies every proposed day and settles the receipt', async () => {
  await trainerService.saveAvailability('t1',blocks,trainer);const request=pending('trainer_availability')
  await requestService.resolve(request.id,'approved',owner)
  const db=mockDb.read()
  expect(db.trainers.find(item=>item.id==='t1').availability).toEqual({Monday:[['09:00','12:00']],Tuesday:[],Wednesday:[['09:00','12:00']],Thursday:[],Friday:[],Saturday:[],Sunday:[]})
  expect(db.messages.filter(item=>item.requestId===request.id).every(item=>item.status==='approved')).toBe(true)
})
it('availability rejection preserves trainers and sessions', async () => {
  await trainerService.saveAvailability('t1',blocks,trainer);const before=mockDb.read()
  await requestService.resolve(pending('trainer_availability').id,'rejected',owner)
  expect(mockDb.read().trainers).toEqual(before.trainers);expect(mockDb.read().sessions).toEqual(before.sessions)
})
it('stale availability is not overwritten and the request remains rejectable', async () => {
  await trainerService.saveAvailability('t1',blocks,trainer);const request=pending('trainer_availability')
  mockDb.mutate(db=>{db.trainers.find(item=>item.id==='t1').availability.Monday=[['07:00','08:00']]})
  const before=mockDb.read()
  await expect(requestService.resolve(request.id,'approved',owner)).rejects.toThrow('changed')
  expect(mockDb.read()).toEqual(before)
  await requestService.resolve(request.id,'rejected',owner)
})
it('supervised weekly change leaves client and every session unchanged until approval', async () => {
  const before=mockDb.read()
  expect((await clientService.saveFixedWeeklySchedule('c1',nextSlots,trainer)).outcome).toBe('requested')
  expect(mockDb.read().clients).toEqual(before.clients);expect(mockDb.read().sessions).toEqual(before.sessions)
  const request=pending('fixed_weekly_schedule')
  expect(mockDb.read().messages.find(item=>item.requestId===request.id)).toMatchObject({status:'pending'})
})
it('weekly approval changes every upcoming booking including custom times and replacement trainers, keeping plans, IDs and credits', async () => {
  await clientService.saveFixedWeeklySchedule('c1',nextSlots,trainer);const before=mockDb.read()
  await requestService.resolve(pending('fixed_weekly_schedule').id,'approved',owner)
  const db=mockDb.read()
  expect(db.sessions).toEqual(before.sessions.map(session=>['future','ad-hoc','expired','replacement'].includes(session.id)?{...session,from:'19:00',to:'20:00',outcome:{...session.outcome,durationMinutes:60}}:session))
  expect(db.clients.find(item=>item.id==='c1').fixedWeeklySchedule).toEqual(nextSlots)
  expect(db.packageCreditTransactions).toEqual(before.packageCreditTransactions)
})
it('a conflict introduced while weekly request is pending rolls back the whole approval', async () => {
  await clientService.saveFixedWeeklySchedule('c1',nextSlots,trainer);const request=pending('fixed_weekly_schedule')
  mockDb.mutate(db=>{db.sessions.push({...db.sessions[0],id:'conflict',clientId:'c2',from:'19:30',to:'20:30'})})
  const before=mockDb.read()
  await expect(requestService.resolve(request.id,'approved',owner)).rejects.toThrow('conflicts')
  expect(mockDb.read()).toEqual(before)
})
it('stale weekly requests cannot overwrite a later schedule', async () => {
  await clientService.saveFixedWeeklySchedule('c1',nextSlots,trainer);const request=pending('fixed_weekly_schedule')
  mockDb.mutate(db=>{db.clients.find(item=>item.id==='c1').fixedWeeklySchedule[0].from='18:30'})
  const before=mockDb.read()
  await expect(requestService.resolve(request.id,'approved',owner)).rejects.toThrow('changed')
  expect(mockDb.read()).toEqual(before)
})
it('owner direct changes use the same future-session update path', async () => {
  expect((await clientService.saveFixedWeeklySchedule('c1',nextSlots,owner)).outcome).toBe('applied')
  expect(mockDb.read().sessions[0].from).toBe('19:00')
  expect(pending('fixed_weekly_schedule')).toBeUndefined()
})
it('autonomous weekly changes use the same future-session update path', async () => {
  mockDb.mutate(db=>{db.trainers.find(item=>item.id==='t1').approvalNeeded.fixedWeeklySchedule=false})
  expect((await clientService.saveFixedWeeklySchedule('c1',nextSlots,trainer)).outcome).toBe('applied')
  expect(mockDb.read().sessions[0].from).toBe('19:00')
})
it('invalid weekly ranges are rejected without writes', async () => {
  const before=mockDb.read()
  await expect(clientService.saveFixedWeeklySchedule('c1',[{...nextSlots[0],to:'18:00'}],owner)).rejects.toThrow('earlier')
  expect(mockDb.read()).toEqual(before)
})
it('weekly changes cannot be submitted by an unassigned trainer', async () => {
  const before=mockDb.read()
  await expect(clientService.saveFixedWeeklySchedule('c1',nextSlots,dbTrainer('t3'))).rejects.toThrow('assigned')
  expect(mockDb.read()).toEqual(before)
})
function dbTrainer(id) {return mockDb.read().users.find(user=>user.trainerId===id)}
it('setting availability to unavailable does not move or cancel booked sessions', async () => {
  await trainerService.saveAvailability('t1',[],trainer);const before=mockDb.read()
  await requestService.resolve(pending('trainer_availability').id,'approved',owner)
  expect(Object.values(mockDb.read().trainers.find(item=>item.id==='t1').availability).flat()).toEqual([])
  expect(mockDb.read().sessions).toEqual(before.sessions)
})

it('updates off-weekday legacy bookings and explicit slot bookings across packages, and derives their duration', async () => {
  mockDb.mutate(db => {
    const client = db.clients.find(item => item.id === 'c1')
    const future = db.sessions.find(item => item.id === 'future')
    future.date = '2026-09-10'; future.outcome = { durationMinutes: 999, trainerComments: 'Keep notes' }
    db.sessions.find(item => item.id === 'ad-hoc').packageId = client.packageHistory[0].id
    db.sessions.find(item => item.id === 'replacement').weeklySlotId = client.fixedWeeklySchedule[0].id
  })
  const before = mockDb.read()
  await clientService.saveFixedWeeklySchedule('c1', nextSlots.map(slot => ({ ...slot, to: '19:45' })), owner)
  const after = mockDb.reload()
  for (const id of ['future', 'ad-hoc', 'expired', 'replacement']) {
    const updated = after.sessions.find(item => item.id === id), original = before.sessions.find(item => item.id === id)
    expect(updated).toEqual({ ...original, from: '19:00', to: '19:45', outcome: { ...original.outcome, durationMinutes: 45 } })
  }
})

it('keeps past and started sessions and inactive-package sessions unchanged and rejects a new time that has passed today', async () => {
  mockDb.mutate(db => {
    const source = db.sessions[0], client = db.clients.find(item => item.id === 'c1')
    client.packageHistory[0].status = 'inactive'
    db.sessions.push({ ...source, id: 'inactive-package', packageId: client.packageHistory[0].id })
    db.sessions.push({ ...source, id: 'started', date: '2026-09-05', from: '09:00', to: '10:00' })
    db.sessions.push({ ...source, id: 'later-today', date: '2026-09-05', from: '11:00', to: '12:00' })
  })
  const before = mockDb.read()
  await expect(clientService.saveFixedWeeklySchedule('c1', nextSlots.map(slot => ({ ...slot, from: '08:00', to: '09:00' })), owner)).rejects.toThrow('passed today')
  expect(mockDb.read()).toEqual(before)
  await clientService.saveFixedWeeklySchedule('c1', nextSlots, owner)
  for (const id of ['inactive-package', 'started', 'past', 'completed']) expect(mockDb.read().sessions.find(item => item.id === id)).toEqual(before.sessions.find(item => item.id === id))
})
