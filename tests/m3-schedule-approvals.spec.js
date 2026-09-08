import { expect, test, selectDemoIdentity } from './fixtures.js'
import { addDays } from '../src/app/clientOnboarding.js'
import { seed } from '../src/data/seed.js'
const KEY = 'fitfinity-m2-demo-db-v4'
async function start(page, route = 'messages') {
  const db = structuredClone(seed)
  const trainer = db.trainers.find(item => item.id === 't1')
  const client = db.clients.find(item => item.id === 'c1')
  client.package.startDate = '2099-01-01'
  client.package.endDate = addDays(client.package.startDate, client.package.validityDays - 1)
  const session = { ...db.sessions.find(item=>item.clientId==='c1'), id:'weekly-future', clientId:'c1',trainerId:'t1',date:'2099-01-05',from:'18:00',to:'19:00',status:'planned' }
  db.sessions=[session]
  db.messages = [
    {id:'availability-review',recipientRole:'owner',trainerId:'t1',createdAt:'2099-01-01T10:00:00Z',kind:'availability_request',status:'pending',read:false,title:'Availability review',body:'Review the current and proposed availability.',request:{type:'trainer_availability',trainerId:'t1',oldAvailability:trainer.availability,newAvailability:{...trainer.availability,Monday:[['09:00','12:00'],['18:00','21:00']]}}},
    {id:'weekly-review',recipientRole:'owner',clientId:'c1',trainerId:'t1',createdAt:'2099-01-01T09:00:00Z',kind:'schedule_request',status:'pending',read:false,title:'Weekly schedule review',body:'Review weekly training times.',request:{type:'fixed_weekly_schedule',clientId:'c1',trainerId:'t1',oldSlots:client.fixedWeeklySchedule,newSlots:client.fixedWeeklySchedule.map(slot=>({...slot,from:'19:00',to:'20:00'}))}},
    {id:'approved',recipientRole:'owner',createdAt:'2099-01-01T08:00:00Z',kind:'request_decision',status:'approved',read:false,title:'Approved example',body:'Approved request.'},
    {id:'rejected',recipientRole:'owner',createdAt:'2099-01-01T07:00:00Z',kind:'request_decision',status:'rejected',read:false,title:'Rejected example',body:'Rejected request.'},
  ]
  await page.addInitScript(({key,data})=>{if(!localStorage.getItem(key))localStorage.setItem(key,JSON.stringify(data))},{key:KEY,data:db})
  await page.goto(`/#/${route}`)
}
async function open(page,title) {
  await page.getByRole('button',{name:`Open ${title}`,exact:true}).click()
  return page.getByRole('dialog',{name:title,exact:true})
}
async function decide(page,dialog,name) {
  await dialog.getByRole('button',{name,exact:true}).click()
  await page.locator('.modal-actions').getByRole('button',{name,exact:true}).click()
}
async function availabilityTab(page) {
  const menu=page.locator('.profile-menu')
  await expect(menu).toBeVisible()
  if(await menu.locator('summary').isVisible())await menu.locator('summary').click()
  await menu.getByRole('button',{name:'Availability',exact:true}).click()
}
async function data(page){return page.evaluate(key=>JSON.parse(localStorage.getItem(key)),KEY)}

test('M3 request status is coloured in the list and remains the same after opening',async({page})=>{
  await start(page)
  const colours=[]
  for(const [title,label] of [['Availability review','Pending'],['Approved example','Approved'],['Rejected example','Rejected']]){
    const row=page.locator('.message-title-row').filter({has:page.getByRole('button',{name:`Open ${title}`,exact:true})})
    await expect(row.getByText(label,{exact:true})).toBeVisible()
    const timeBox=await row.locator('.message-title-time').boundingBox()
    const statusBox=await row.locator('.request-status').boundingBox()
    const readBox=await row.locator('.message-state-button').boundingBox()
    expect(timeBox).not.toBeNull();expect(statusBox).not.toBeNull();expect(readBox).not.toBeNull()
    expect(statusBox.x).toBeGreaterThanOrEqual(timeBox.x+timeBox.width)
    expect(readBox.x).toBeGreaterThanOrEqual(statusBox.x+statusBox.width)
    expect(Math.abs((statusBox.y+statusBox.height/2)-(readBox.y+readBox.height/2))).toBeLessThanOrEqual(2)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(0)
    const colour=await row.locator('.request-status').evaluate(el=>getComputedStyle(el).color);colours.push(colour)
    const dialog=await open(page,title)
    await expect(dialog.locator('.request-status')).toHaveText(label)
    expect(await dialog.locator('.request-status').evaluate(el=>getComputedStyle(el).color)).toBe(colour)
    await dialog.getByRole('button',{name:'Close message'}).click()
    await expect(dialog).toHaveCount(0)
    await expect(row.getByRole('button',{name:`Read ${title}`,exact:true})).toBeVisible()
  }
  expect(new Set(colours).size).toBe(3)
})
test('M3 availability review shows all days and blocks and approval updates both surfaces',async({page})=>{
  await start(page)
  const dialog=await open(page,'Availability review')
  await expect(dialog.getByRole('region',{name:'Current at request',exact:true}).locator('dt')).toHaveCount(7)
  await expect(dialog.getByRole('region',{name:'Requested',exact:true}).locator('dt')).toHaveCount(7)
  await expect(dialog.getByRole('region',{name:'Requested',exact:true}).getByText('09:00–12:00, 18:00–21:00',{exact:true})).toBeVisible()
  expect(await dialog.evaluate(el=>el.scrollWidth-el.clientWidth)).toBeLessThanOrEqual(1)
  await decide(page,dialog,'Approve Request')
  await expect(dialog.locator('.request-status')).toHaveText('Approved')
  expect((await data(page)).trainers.find(t=>t.id==='t1').availability.Monday).toEqual([['09:00','12:00'],['18:00','21:00']])
  await dialog.getByRole('button',{name:'Close message'}).click()
  await expect(page.locator('.message-title-row').filter({has:page.getByRole('button',{name:'Open Availability review',exact:true})}).locator('.request-status')).toHaveText('Approved')
})
test('M3 trainer availability request preserves approved blocks and owner rejection preserves bookings',async({page})=>{
  await start(page,'dashboard')
  await selectDemoIdentity(page, 'u-marcus')
  await page.goto('/#/my-profile')
  await availabilityTab(page)
  await page.getByRole('button',{name:'Request Change',exact:true}).click()
  await page.getByRole('button',{name:'Sunday',exact:true}).click()
  await page.getByRole('button',{name:'Add Time',exact:true}).click()
  await page.getByRole('button',{name:'Send Request',exact:true}).click()
  await page.locator('.modal-actions').getByRole('button',{name:'Send Request',exact:true}).click()
  await expect(page.locator('.notification-info').getByRole('status')).toHaveText('Availability request sent for owner approval.')
  expect((await data(page)).trainers.find(t=>t.id==='t1').availability.Sunday).toEqual([])
  await selectDemoIdentity(page, 'u-owner')
  await page.goto('/#/messages')
  const dialog=await open(page,'Availability change: Marcus Tan')
  await decide(page,dialog,'Reject Request')
  await expect(dialog.locator('.request-status')).toHaveText('Rejected')
  expect((await data(page)).sessions[0].from).toBe('18:00')
})
test('M3 weekly approval updates matching future sessions and keeps credits unchanged',async({page})=>{
  await start(page)
  const before=await data(page)
  const dialog=await open(page,'Weekly schedule review')
  await expect(dialog.getByRole('region',{name:'Current at request',exact:true}).getByText('18:00–19:00',{exact:true})).toBeVisible()
  await expect(dialog.getByRole('region',{name:'Requested',exact:true}).getByText('19:00–20:00',{exact:true})).toBeVisible()
  await decide(page,dialog,'Approve Request')
  await expect(dialog.locator('.request-status')).toHaveText('Approved')
  const after=await data(page)
  expect(after.sessions[0].from).toBe('19:00')
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
})
test('M3 owner availability stays read-only while autonomous trainer can save directly',async({page})=>{
  await start(page,'trainers/t3')
  await availabilityTab(page)
  await expect(page.getByRole('button',{name:'Request Change',exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Edit',exact:true})).toHaveCount(0)
  await selectDemoIdentity(page, 'u-daniel')
  await page.goto('/#/my-profile');await availabilityTab(page)
  await page.getByRole('button',{name:'Edit',exact:true}).click()
  await page.getByRole('button',{name:'Sunday',exact:true}).click()
  await page.getByRole('button',{name:'Add Time',exact:true}).click()
  await page.getByRole('button',{name:'Save',exact:true}).click()
  await page.locator('.modal-actions').getByRole('button',{name:'Save Availability',exact:true}).click()
  await expect(page.locator('.notification-success').getByRole('status')).toHaveText('Availability saved.')
  expect((await data(page)).trainers.find(t=>t.id==='t3').availability.Sunday).toEqual([['18:00','19:00']])
})


test('M3 the entire message row opens once from time, status, gaps and the read button',async({page})=>{
  await start(page)
  const row=page.locator('.message-title-row').filter({has:page.getByRole('button',{name:'Open Availability review',exact:true})})
  for(const target of ['time','status','gap','read']) {
    const before=await page.evaluate(()=>history.state?.fitfinityDepth??0)
    if(target==='time')await row.locator('.message-title-time').click()
    if(target==='status')await row.locator('.request-status').click()
    if(target==='read')await row.locator('.message-state-button').click()
    if(target==='gap'){
      const geometry=await row.evaluate(el=>{
        const rowBox=el.getBoundingClientRect(), time=el.querySelector('time').getBoundingClientRect(),status=el.querySelector('.message-approval-status').getBoundingClientRect()
        return {x:(time.right+status.left)/2-rowBox.left,y:(time.top+time.bottom)/2-rowBox.top}
      })
      await row.click({position:geometry})
    }
    const dialog=page.getByRole('dialog',{name:'Availability review',exact:true})
    await expect(dialog).toBeVisible()
    expect(await page.evaluate(()=>history.state?.fitfinityDepth??0)).toBe(before+1)
    await dialog.getByRole('button',{name:'Close message'}).click()
    await expect(dialog).toHaveCount(0)
    await expect.poll(()=>page.evaluate(()=>history.state?.fitfinityDepth??0)).toBe(before)
  }
})
