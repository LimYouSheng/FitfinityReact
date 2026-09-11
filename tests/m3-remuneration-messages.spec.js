import { waitForPortal, expect, test, selectDemoIdentity, drawClientSignature } from './fixtures.js'
import { seed } from '../src/data/seed.js'
import { signatureFixture } from '../src/test/fixtures/signature.js'
const KEY = 'fitfinity-m2-demo-db-v4'
async function start(page, route = 'messages', extraSessions = []) {
  const db = structuredClone(seed)
  const completed = db.sessions.find(session => session.status === 'completed')
  const base = { ...completed, acknowledgement: { method: 'signature', signerName: 'Amanda Lim', signature: structuredClone(signatureFixture), recordedAt: '2020-08-21T12:00:00+08:00' }, outcome: null, whatsappOpenedAt: null }
  db.sessions = [
    { ...base, id:'pay-peak', clientId:'c1', trainerId:'t1', date:'2020-08-20', from:'18:00', to:'19:00' },
    { ...base, id:'pay-off', clientId:'c1', trainerId:'t1', date:'2020-08-21', from:'10:00', to:'11:00' },
    { ...base, id:'pay-other', clientId:'c2', trainerId:'t2', date:'2020-08-21', from:'18:00', to:'19:00' },
  ]
  db.sessions.push(...extraSessions.map(session => ({ ...db.sessions[0], ...session })))
  for (const session of db.sessions) session.packageId = `client-package-${session.clientId}`
  db.clients.push({ ...db.clients[0], id:'created-test', name:'Test' })
  db.messages = [
    { id:'general', recipientRole:'owner', title:'General update', body:'The latest announcement is available.', createdAt:'2026-09-05T10:00:00Z', read:false },
    { id:'linked', recipientRole:'owner', title:'Linked session update', body:'The latest session update is available.', sessionId:'pay-peak', createdAt:'2026-09-05T09:00:00Z', read:false, kind:'request_decision', status:'approved' },
  ]
  delete db.remunerationEntries; delete db.remunerationApprovals
  await page.addInitScript(({key,data})=>{if(!localStorage.getItem(key)) localStorage.setItem(key,JSON.stringify(data))},{key:KEY,data:db})
  await page.goto(`/#/${route}`)
  await waitForPortal(page)
}
const readDb = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
async function openMessage(page, title) {
  await page.getByRole('button',{name:`Open ${title}`,exact:true}).click()
  return page.getByRole('dialog',{name:title,exact:true})
}
async function showBreakdown(page) {
  await start(page,'remuneration/2020-09/t1')
  await page.getByRole('button',{name:'Show remuneration amounts',exact:true}).click()
}

test('M3 a newly created Test client never attaches itself to unrelated messages', async ({page}) => {
  await start(page)
  let dialog = await openMessage(page,'General update')
  await expect(dialog.getByRole('navigation',{name:'Related records'})).toHaveCount(0)
  await dialog.getByRole('button',{name:'Close message'}).click()
  dialog = await openMessage(page,'Linked session update')
  await expect(dialog.getByRole('button',{name:'View Client · Amanda Lim',exact:true})).toBeVisible()
  await expect(dialog.getByRole('button',{name:'View Client · Test',exact:true})).toHaveCount(0)
})
test('M3 popup Mark as Unread closes, persists across refresh and preserves the approval badge', async ({page}) => {
  await start(page)
  const dialog = await openMessage(page,'Linked session update')
  await expect(dialog.locator('.request-status')).toHaveText('Approved')
  await dialog.getByRole('button',{name:'Mark as Unread',exact:true}).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.locator('.notification-info').getByRole('status')).toHaveText('Message marked as unread.')
  await expect(page.getByRole('button',{name:'Unread Linked session update',exact:true})).toBeVisible()
  const message = (await readDb(page)).messages.find(item => item.id === 'linked')
  expect(message.read).toBe(false)
  expect(message.readAt).toBeUndefined()
  expect(message.status).toBe('approved')
  await page.reload()
  await expect(page.getByRole('button',{name:'Unread Linked session update',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Unread Linked session update',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'Linked session update',exact:true})).toBeVisible()
})
test('M3 remuneration cycle list has compact ordered columns and a money toggle without page overflow', async ({page}) => {
  await start(page,'remuneration/2020-09')
  await expect(page.getByRole('heading',{name:'Remuneration',exact:true})).toBeVisible()
  const table = page.getByRole('table',{name:'Trainer remuneration'})
  expect(await table.locator('[role="columnheader"]').allTextContents()).toEqual(['Name','Sessions','Remuneration','Status','View'])
  await expect(page.getByRole('button',{name:'Show remuneration amounts'})).toBeVisible()
  await page.getByRole('button',{name:'Show remuneration amounts'}).click()
  await expect(page.getByRole('button',{name:'Hide remuneration amounts'})).toBeVisible()
  const trainerCells = await table.locator('.remuneration-trainer-row').first().evaluate(el => [...el.children].map(cell => {
    const rect = cell.getBoundingClientRect()
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }
  }))
  for (let index = 1; index < trainerCells.length; index++) expect(trainerCells[index - 1].right).toBeLessThanOrEqual(trainerCells[index].left)
  expect(Math.max(...trainerCells.map(cell => cell.top))).toBeLessThan(Math.min(...trainerCells.map(cell => cell.bottom)))
  await page.getByRole('button',{name:'View remuneration for Marcus Tan',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Marcus Tan',exact:true})).toBeVisible()
  await expect(page.locator('.remuneration-session')).toHaveCount(2)
  await expect(page.getByRole('combobox',{name:'Pay cycle',exact:true})).toHaveCount(0)
  await expect(page.locator('.remuneration-cycle-caption')).toHaveText(/16 Aug 2020 – 15 Sept? 2020/)
  const row = page.locator('.remuneration-session').first()
  await expect(row.locator('dl, select')).toHaveCount(0)
  await expect(row).not.toContainText('Acknowledgement')
  await expect(row).not.toContainText('18:00')
  const dimensions = await row.evaluate(el => [...el.children].map(cell => {
    const rect = cell.getBoundingClientRect()
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }
  }))
  for (let index = 1; index < dimensions.length; index++) expect(dimensions[index - 1].right).toBeLessThanOrEqual(dimensions[index].left)
  expect(Math.max(...dimensions.map(cell => cell.top))).toBeLessThan(Math.min(...dimensions.map(cell => cell.bottom)))
  expect((await row.boundingBox()).height).toBeLessThanOrEqual(80)
  expect(await row.locator('.remuneration-session-rate').evaluate(el => Number(getComputedStyle(el).fontWeight))).toBeGreaterThanOrEqual(700)
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1)
  await page.getByRole('button',{name:'Back',exact:true}).click()
  await expect(page.getByRole('table',{name:'Trainer remuneration'})).toBeVisible()
  await expect(page.locator('.remuneration-cycle-caption')).toContainText('16 Aug 2020')
})

test('M4 owner and trainer open the current remuneration cycle and every total links to its sessions', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2020-09-01T04:00:00Z'))
  await start(page, 'remuneration', [{ id: 'future-pay', date: '2020-10-20', status: 'planned', acknowledgement: null }])
  for (const id of ['u-owner', 'u-marcus']) {
    if (id !== 'u-owner') {
      await selectDemoIdentity(page, id)
      await page.goto('/#/remuneration')
    }
    const cycles = page.getByLabel('Pay cycles', { exact: true })
    await expect(cycles.locator('article').first()).toHaveAttribute('data-cycle-key', '2020-09')
    await expect(cycles.locator('article').first()).toContainText('Current')
    await expect(cycles.locator('[data-cycle-key="2020-11"]')).toHaveCount(0)
    await page.getByRole('button', { name: 'Show remuneration amounts', exact: true }).click()
    await page.getByRole('button', { name: 'View pay cycle 2020-09', exact: true }).click()
    if (id === 'u-owner') {
      const row = page.locator('.remuneration-trainer-row').filter({ hasText: 'Marcus Tan' })
      await expect(row.locator('[data-label="Sessions"]')).toHaveText('2')
      await expect(row.locator('[data-label="Remuneration"]')).toContainText('135.00')
      await row.getByRole('button', { name: 'View remuneration for Marcus Tan', exact: true }).click()
    } else await expect(page.getByRole('table', { name: 'Trainer remuneration' })).toHaveCount(0)
    await expect(page.locator('.remuneration-session')).toHaveCount(2)
    await expect(page.locator('[data-session-id="pay-peak"] .remuneration-session-rate')).toContainText('80.00')
    await expect(page.locator('[data-session-id="pay-off"] .remuneration-session-rate')).toContainText('55.00')
    await page.locator('[data-session-id="pay-peak"]').getByRole('button', { name: /View Session/ }).click()
    await expect(page.getByLabel('Session status summary')).toContainText('Completed')
    await page.goBack()
    await expect(page.locator('.remuneration-totals')).toContainText('135.00')
    const alignment = await page.locator('.remuneration-totals').evaluate(node => [...node.children].map(card => {
      const label = card.querySelector('span').getBoundingClientRect(), value = card.querySelector('strong').getBoundingClientRect()
      return { labelY: label.y, valueY: value.y, inset: Math.abs(label.x - value.x) }
    }))
    expect(Math.max(...alignment.map(row => row.labelY)) - Math.min(...alignment.map(row => row.labelY))).toBeLessThanOrEqual(1)
    expect(Math.max(...alignment.map(row => row.valueY)) - Math.min(...alignment.map(row => row.valueY))).toBeLessThanOrEqual(1)
    for (const row of alignment) expect(row.inset).toBeLessThanOrEqual(1)
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    if (id === 'u-owner') await page.getByRole('button', { name: 'Back', exact: true }).click()
    await expect(cycles).toBeVisible()
    await page.reload()
    await expect(cycles.locator('article').first()).toHaveAttribute('data-cycle-key', '2020-09')
    await expect(cycles.locator('[data-cycle-key="2020-11"]')).toHaveCount(0)
    // The future booking remains intact even though its cycle is not open.
    expect((await readDb(page)).sessions.find(session => session.id === 'future-pay')).toMatchObject({ date: '2020-10-20', status: 'planned' })
  }
})

test('M3 owner approves automatic session totals once with routed unread notifications', async ({page}) => {
  await showBreakdown(page)
  const before = await readDb(page)
  await expect(page.getByRole('combobox',{name:'Pay cycle',exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Approve Remuneration',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Approve Remuneration',exact:true}).click()
  const confirmation = page.getByRole('dialog',{name:'Approve trainer remuneration?',exact:true})
  await expect(confirmation).toContainText('135.00')
  await confirmation.getByRole('button',{name:'Approve Remuneration',exact:true}).click()
  await expect(page.locator('.notification-success').getByRole('status')).toHaveText('Remuneration approved.')
  await expect(page.locator('.remuneration-page [role="status"]')).toHaveCount(0)
  const after = await readDb(page)
  expect(after.remunerationApprovals).toHaveLength(1)
  expect(after.remunerationApprovals[0]).toMatchObject({amountCents:13500,sessions:2})
  expect(after.sessions).toEqual(before.sessions)
  expect(after.clients).toEqual(before.clients)
  expect(after.messages.filter(message=>message.kind==='remuneration_approval')).toHaveLength(2)
  await expect(page.getByRole('button',{name:'Approve Remuneration',exact:true})).toHaveCount(0)
  await page.goto('/#/messages')
  const dialog = await openMessage(page,'Remuneration approved · Marcus Tan · 2020-09')
  await expect(dialog.locator('.request-status')).toHaveText('Approved')
  await dialog.getByRole('button',{name:'View Remuneration · 2020-09',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Marcus Tan',exact:true})).toBeVisible()
  await expect(page.locator('.remuneration-section-head .status-badge')).toHaveText('Approved')
})
test('M3 trainer remuneration is read-only and an arbitrary other-trainer URL reveals no breakdown', async ({page}) => {
  await start(page,'dashboard')
  await selectDemoIdentity(page, 'u-marcus')
  await page.evaluate(()=>{location.hash='#/remuneration/2020-09'})
  await expect(page.getByLabel('Cycle session breakdown', { exact: true })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Trainer remuneration' })).toHaveCount(0)
  await expect(page.getByRole('button',{name:'View remuneration for Rachel Ong',exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Approve Remuneration',exact:true})).toHaveCount(0)
  await expect(page.locator('.remuneration-toolbar select, .remuneration-session select')).toHaveCount(0)
  await page.evaluate(()=>{location.hash='#/remuneration/2020-09/t2'})
  await expect(page.getByText('This remuneration record is unavailable for your account.')).toBeVisible()
  await expect(page.locator('.remuneration-session')).toHaveCount(0)
})
test('M3 cancelling approval writes nothing and View Session returns to the same fixed cycle', async ({page}) => {
  await showBreakdown(page)
  const before = await readDb(page)
  await page.getByRole('button',{name:'Approve Remuneration',exact:true}).click()
  const confirmation = page.getByRole('dialog',{name:'Approve trainer remuneration?',exact:true})
  await confirmation.getByRole('button',{name:'Cancel',exact:true}).click()
  expect(await readDb(page)).toEqual(before)
  await expect(page.getByRole('button',{name:'Approve Remuneration',exact:true})).toBeEnabled()
  await page.locator('[data-session-id="pay-peak"]').getByRole('button',{name:/View Session/}).click()
  await expect(page).toHaveURL(/#\/sessions\/pay-peak$/)
  await page.goBack()
  await expect(page).toHaveURL(/#\/remuneration\/2020-09\/t1$/)
  await expect(page.locator('.remuneration-session')).toHaveCount(2)
  await expect(page.locator('.remuneration-toolbar select, .remuneration-session select')).toHaveCount(0)
})
test('M3 automatic peak rates respect weekday boundaries and both weekend days', async ({page}) => {
  const cases = [
    ['early','2020-08-17','06:29','55.00'], ['morning','2020-08-17','06:30','80.00'],
    ['morning-end','2020-08-17','08:30','55.00'], ['evening','2020-08-17','18:00','80.00'],
    ['evening-end','2020-08-17','20:30','55.00'], ['saturday','2020-08-22','12:00','80.00'],
    ['sunday','2020-08-23','00:00','80.00'],
  ]
  await start(page,'remuneration/2020-09/t1',cases.map(([id,date,from])=>({id,date,from})))
  await page.getByRole('button',{name:'Show remuneration amounts',exact:true}).click()
  for (const [id,,,amount] of cases) await expect(page.locator(`[data-session-id="${id}"] .remuneration-session-rate`)).toContainText(amount)
  await expect(page.locator('.remuneration-toolbar select, .remuneration-session select')).toHaveCount(0)
  await page.getByRole('button',{name:'Hide remuneration amounts',exact:true}).click()
  for (const [id] of cases) await expect(page.locator(`[data-session-id="${id}"] .remuneration-session-rate`)).toHaveText('••••')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1)
})
test('M4 remuneration moves from In progress to Pending review and becomes approvable with acknowledgement alone', async ({page}) => {
  await page.clock.install({ time: new Date('2020-09-15T15:59:30Z') })
  await start(page, 'remuneration/2020-09/t1', [{ id: 'pay-missing', status: 'planned', acknowledgement: null }])
  await expect(page.locator('.remuneration-section-head .status-badge')).toHaveText('In progress')
  await expect(page.getByText(/Approval opens after/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Approve Remuneration', exact: true })).toBeDisabled()
  await expect(page.locator('.remuneration-session')).toHaveCount(3)
  await page.clock.fastForward(31000)
  await page.reload()
  await expect(page.locator('.remuneration-section-head .status-badge')).toHaveText('Pending review')
  await expect(page.getByRole('button', { name: 'Approve Remuneration', exact: true })).toBeDisabled()
  await selectDemoIdentity(page, 'u-marcus')
  await page.evaluate(() => { location.hash = '#/remuneration/2020-09/t1' })
  await expect(page.locator('.remuneration-section-head .status-badge')).toHaveText('Pending review')
  await expect(page.getByRole('button', { name: 'Approve Remuneration', exact: true })).toHaveCount(0)
  await page.locator('[data-session-id="pay-missing"]').getByRole('button', { name: /View Session/ }).click()
  await page.getByRole('button', { name: 'Client Signature', exact: true }).click()
  await drawClientSignature(page)
  await page.getByRole('button', { name: 'Review Completion' }).click()
  await page.getByRole('dialog', { name: 'Complete this session?' }).getByRole('button', { name: 'Complete Session', exact: true }).click()
  await expect(page.getByRole('button', { name: 'View Client Signature' })).toBeVisible()
  const completed = (await readDb(page)).sessions.find(session => session.id === 'pay-missing')
  expect(completed).toMatchObject({ status: 'completed', outcome: null, whatsappOpenedAt: null })
  expect(completed.acknowledgement.signature.length).toBeGreaterThan(0)
  await page.goBack()
  await expect(page.locator('.remuneration-section-head .status-badge')).toHaveText('Pending approval')
  await selectDemoIdentity(page, 'u-owner')
  await page.evaluate(() => { location.hash = '#/remuneration/2020-09/t1' })
  await expect(page.locator('.remuneration-section-head .status-badge')).toHaveText('Pending approval')
  await page.getByRole('button', { name: 'Show remuneration amounts', exact: true }).click()
  await page.getByRole('button', { name: 'Approve Remuneration', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: 'Approve trainer remuneration?', exact: true })
  await expect(confirmation).toContainText('215.00')
  await confirmation.getByRole('button', { name: 'Approve Remuneration', exact: true }).click()
  await expect(page.locator('.remuneration-section-head .status-badge')).toHaveText('Approved')
  expect((await readDb(page)).remunerationApprovals[0]).toMatchObject({ sessions: 3, amountCents: 21500 })
})
