import { expect, test } from './fixtures.js'
import { seed } from '../src/data/seed.js'
const KEY = 'fitfinity-m2-demo-db-v4'
async function request(page, type = 'session_time') {
  await page.addInitScript(({key, data}) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, {key:KEY, data:seed})
  await page.goto('/#/dashboard')
  await expect(page.getByRole('heading', { name:'Owner Dashboard' })).toBeVisible()
  await page.evaluate(({key,type}) => {
    const db = JSON.parse(localStorage.getItem(key))
    const session = db.sessions.find(item => item.id === 's1')
    const replacement = db.trainers.find(item => item.status === 'active' && item.id !== session.trainerId)
    db.messages.push({ id:'approval-test', recipientRole:'owner', title:'Review test request', body:'Please review this change.', createdAt:new Date().toISOString(), read:false, status:'pending', sessionId:session.id, clientId:session.clientId,
      request:{type, sessionId:session.id, trainerId:session.trainerId, previous:{date:session.date,from:session.from,to:session.to}, next:{date:'2026-12-01',from:'10:00',to:'11:00'}, previousTrainerId:session.trainerId,replacementTrainerId:replacement.id} })
    localStorage.setItem(key,JSON.stringify(db))
  },{key:KEY,type})
  await page.goto('/#/messages'); await page.reload()
  await page.getByRole('button',{name:'Open Review test request',exact:true}).click()
  return page.getByRole('dialog',{name:'Review test request',exact:true})
}
test('M3 dashboard Add Trainer opens the canonical form and browser Back returns home',async ({page}) => {
  await page.goto('/#/dashboard')
  await page.getByRole('button',{name:'Add Trainer',exact:true}).click()
  await expect(page.getByLabel('Trainer name',{exact:true})).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('heading',{name:'Owner Dashboard'})).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(0)
})
test('M3 owner reviews time, cancels confirmation, then approves once', async ({page}) => {
  const dialog = await request(page)
  await expect(dialog.getByText(/Tuesday, .*2026 · 10:00–11:00/)).toBeVisible()
  await dialog.getByRole('button',{name:'Approve Request',exact:true}).click()
  await page.locator('.modal-actions').getByRole('button',{name:'Cancel',exact:true}).click()
  await expect(dialog.getByRole('button',{name:'Approve Request'})).toBeEnabled()
  await dialog.getByRole('button',{name:'Approve Request'}).click()
  await page.locator('.modal-actions').getByRole('button',{name:'Approve Request',exact:true}).click()
  await expect(dialog.getByText('Approved',{exact:true})).toBeVisible()
  expect(await page.evaluate(key=>JSON.parse(localStorage.getItem(key)).sessions.find(s=>s.id==='s1').date,KEY)).toBe('2026-12-01')
  await expect(dialog.getByRole('button',{name:'Approve Request'})).toHaveCount(0)
})
test('M3 owner rejects trainer request without changing the assignment', async ({page}) => {
  const dialog = await request(page,'session_trainer')
  const before = await page.evaluate(key=>JSON.parse(localStorage.getItem(key)).sessions.find(s=>s.id==='s1').trainerId,KEY)
  await dialog.getByRole('button',{name:'Reject Request'}).click()
  await page.locator('.modal-actions').getByRole('button',{name:'Reject Request',exact:true}).click()
  await expect(dialog.getByText('Rejected',{exact:true})).toBeVisible()
  expect(await page.evaluate(key=>JSON.parse(localStorage.getItem(key)).sessions.find(s=>s.id==='s1').trainerId,KEY)).toBe(before)
})
