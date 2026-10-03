import { test, expect, waitForPortal, selectDemoIdentity } from './fixtures.js'
import { createDemoSeed } from '../src/data/seed.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const instant = new Date('2026-10-03T01:00:00Z')
const read = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
const activate = (locator, isMobile) => isMobile ? locator.tap() : locator.click()
async function start(page, { twice = false, supervised = false, past = false, inactive = false, conflict = false } = {}) {
  const data = createDemoSeed('2026-10-03')
  const client = data.clients.find(item => item.id === 'c1')
  client.name = 'Postpone Client'; client.status = inactive ? 'inactive' : 'active'; client.trainerId = 't1'
  client.fixedWeeklySchedule = [{ id: 'mon', day: 'Monday', from: '10:00', to: '11:00' }, ...(twice ? [{ id: 'thu', day: 'Thursday', from: '10:00', to: '11:00' }] : [])]
  Object.assign(client.package, { used: 0, status: 'active', startDate: '2026-09-01', endDate: '2026-12-31', fixedWeeklySchedule: structuredClone(client.fixedWeeklySchedule) })
  const original = data.sessions.find(item => item.clientId === 'c1')
  data.sessions = (twice ? ['2026-10-05', '2026-10-08', '2026-10-12', '2026-10-15'] : ['2026-10-05', '2026-10-12', '2026-10-19']).map((date, index) => ({ ...original,
    id: `undo-s${index + 1}`, clientId: client.id, trainerId: 't1', packageId: client.package.id, date: past && !index ? '2026-10-03' : date,
    from: past && !index ? '08:00' : '10:00', to: past && !index ? '09:00' : '11:00', weeklySlotId: twice && index % 2 ? 'thu' : 'mon',
    sessionNumber: index + 1, status: 'planned', acknowledgement: null, acknowledgementHistory: [], clientSummary: '',
    exercisePlan: [], exerciseResults: undefined }))
  if (conflict) {
    Object.assign(data.sessions[0], { date: '2026-10-06', from: '12:00', to: '13:00' })
    const other = data.clients.find(item => item.id === 'c2')
    other.status = 'active'; other.package.status = 'active'
    data.sessions.push({ ...data.sessions[0], id: 'occupied-tail', clientId: other.id, packageId: other.package.id, date: '2026-10-26', from: '10:00', to: '11:00' })
  }
  for (const trainer of data.trainers) { trainer.status = 'active'; trainer.approvalNeeded.sessionTime = supervised }
  data.messages = []; data.packageCreditTransactions = []; data.remunerationApprovals = []
  await page.clock.setFixedTime(instant)
  await page.addInitScript(({ key, data }) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, { key: KEY, data })
  await page.goto('/#/sessions/undo-s1'); await waitForPortal(page)
  await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
}
async function postpone(page, isMobile) {
  await activate(page.getByRole('button', { name: 'Postpone', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Postpone this session?', exact: true })
  await expect(dialog).toBeVisible()
  await activate(dialog.getByRole('button', { name: 'Confirm Postponement', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
}
async function messages(page) { await page.goto('/#/messages'); await waitForPortal(page) }
async function reverse(page, isMobile, row) {
  const title = await row.getByRole('button', { name: /^Open / }).getAttribute('aria-label')
  const stableRow = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: title, exact: true }) })
  await activate(row.getByRole('button', { name: /^Undo / }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Undo session change?', exact: true }).getByRole('button', { name: 'Undo Change', exact: true }), isMobile)
  await expect(stableRow.getByRole('status')).toHaveText('Undone'); await waitForPortal(page)
}
const postponedRow = page => page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: 'Open Session postponed: Postpone Client', exact: true }) })

for (const twice of [false, true]) test(`session actions: ${twice ? 'twice' : 'once'} weekly preview, single move and persistent Undo`, async ({ page, isMobile }) => {
  await start(page, { twice }); const before = await read(page)
  await activate(page.getByRole('button', { name: 'Postpone', exact: true }), isMobile)
  const preview = page.getByRole('dialog', { name: 'Postpone this session?', exact: true })
  await expect(preview.locator('tbody tr')).toHaveCount(1)
  await expect(preview).toContainText('Credits stay the same')
  await activate(preview.getByRole('button', { name: 'Cancel', exact: true }), isMobile)
  expect((await read(page)).sessions).toEqual(before.sessions)
  await postpone(page, isMobile)
  expect((await read(page)).sessions.map(item => item.date)).toEqual(twice ? ['2026-10-22', '2026-10-08', '2026-10-12', '2026-10-15'] : ['2026-10-26', '2026-10-12', '2026-10-19'])
  expect((await read(page)).sessions.slice(1)).toEqual(before.sessions.slice(1))
  await messages(page)
  const row = postponedRow(page); await expect(row.getByRole('button', { name: /^Undo / })).toBeEnabled()
  await reverse(page, isMobile, row); await page.reload(); await waitForPortal(page)
  const after = await read(page)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.clients.find(item => item.id === 'c1').package.used).toBe(0)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  await expect(row.getByRole('status')).toHaveText('Undone')
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
})

test('session actions: Undo expires while confirmation is open', async ({ page, isMobile }) => {
  await start(page); await postpone(page, isMobile); await messages(page)
  const row = postponedRow(page)
  await activate(row.getByRole('button', { name: /^Undo / }), isMobile)
  const before = await read(page), expiry = before.sessionMutations.at(-1).expiresAt
  await page.clock.setFixedTime(new Date(expiry))
  await activate(page.getByRole('dialog', { name: 'Undo session change?', exact: true }).getByRole('button', { name: 'Undo Change', exact: true }), isMobile)
  await expect(row.getByRole('alert')).toContainText('Undo expired')
  expect((await read(page)).sessions).toEqual(before.sessions)
  await page.reload(); await waitForPortal(page)
  await expect(row.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  await expect(row).toContainText('Undo expired')
})

test('session actions: supervised postponement is approved then reversed without reopening', async ({ page, isMobile }) => {
  await start(page, { supervised: true }); const before = await read(page)
  await selectDemoIdentity(page, 'u-marcus'); await page.goto('/#/sessions/undo-s1'); await waitForPortal(page)
  await postpone(page, isMobile)
  expect((await read(page)).sessions).toEqual(before.sessions)
  await selectDemoIdentity(page, 'u-owner'); await messages(page)
  const title = 'Postponement requested: Postpone Client'
  await activate(page.getByRole('button', { name: `Open ${title}`, exact: true }), isMobile)
  await expect(page.getByRole('region', { name: 'Requested change' })).toContainText('26 Oct 2026')
  await activate(page.getByRole('button', { name: 'Approve Request', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Approve request?', exact: true }).getByRole('button', { name: 'Approve Request', exact: true }), isMobile)
  await expect.poll(async () => (await read(page)).sessions[0].date).toBe('2026-10-26')
  await activate(page.getByRole('button', { name: 'Close message', exact: true }), isMobile)
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${title}`, exact: true }) })
  await reverse(page, isMobile, row)
  const after = await read(page)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.messages.find(item => item.request?.type === 'session_postpone').status).toBe('reversed')
})

test('session actions: completion Undo restores credit and retains acknowledgement history', async ({ page, isMobile }) => {
  await start(page, { past: true })
  await activate(page.getByRole('button', { name: 'Client Signature', exact: true }), isMobile)
  await activate(page.getByRole('button', { name: 'Record late / no-show instead', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Trainer late / no-show', exact: true }).getByRole('button', { name: 'Review Completion', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Complete this session?', exact: true }).getByRole('button', { name: 'Complete Session', exact: true }), isMobile)
  await expect.poll(async () => (await read(page)).sessions[0].status).toBe('completed')
  const completed = await read(page)
  expect(completed.clients.find(item => item.id === 'c1').package.used).toBe(1)
  await messages(page)
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: /^Undo / }) })
  await expect(row).toHaveCount(1); await reverse(page, isMobile, row)
  await page.reload(); await waitForPortal(page)
  const after = await read(page)
  expect(after.sessions[0].status).toBe('planned')
  expect(after.sessions[0].acknowledgement).toBeNull()
  expect(after.sessions[0].acknowledgementHistory).toEqual(completed.sessions[0].acknowledgementHistory)
  expect(after.clients.find(item => item.id === 'c1').package.used).toBe(0)
  expect(after.packageCreditTransactions.map(item => item.type)).toEqual(['session_debit', 'session_reversal'])
})

test('session actions: summary edit Undo preserves message overlay Back navigation', async ({ page, isMobile }) => {
  await start(page)
  const original = (await read(page)).sessions[0].clientSummary
  const panel = page.locator('.client-summary-panel')
  await activate(panel.getByRole('button', { name: 'Edit', exact: true }), isMobile)
  await panel.locator('textarea').fill('A newly edited client summary.')
  await activate(panel.getByRole('button', { name: 'Save', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Save client-facing summary?', exact: true }).getByRole('button', { name: 'Save Summary', exact: true }), isMobile)
  await expect(panel.locator('.client-summary-copy')).toHaveText('A newly edited client summary.')
  await messages(page)
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: /^Undo / }) })
  await expect(row).toHaveCount(1)
  await activate(row.getByRole('button', { name: /^Open / }), isMobile)
  await expect(page.getByRole('button', { name: 'Close message', exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Close message', exact: true })).toHaveCount(0)
  await expect(page).toHaveURL(/#\/messages$/)
  await reverse(page, isMobile, row)
  expect((await read(page)).sessions[0].clientSummary).toBe(original)
})

test('session actions: a new booking blocks Undo without partial restoration', async ({ page, isMobile }) => {
  await start(page); await postpone(page, isMobile)
  await page.evaluate(key => {
    const data = JSON.parse(localStorage.getItem(key))
    const other = data.clients.find(item => item.id === 'c2')
    data.sessions.push({ ...data.sessions[0], id: 'conflicting-booking', clientId: other.id, packageId: other.package.id, date: '2026-10-05' })
    localStorage.setItem(key, JSON.stringify(data))
  }, KEY)
  // A hash route change keeps mockDb's current snapshot. Reload injected storage first.
  await page.reload(); await waitForPortal(page)
  await messages(page); const before = await read(page), row = postponedRow(page)
  expect(before.sessions.some(item => item.id === 'conflicting-booking')).toBe(true)
  await activate(row.getByRole('button', { name: /^Undo / }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Undo session change?', exact: true }).getByRole('button', { name: 'Undo Change', exact: true }), isMobile)
  await expect(row.getByRole('alert')).toContainText('conflicts')
  expect((await read(page)).sessions).toEqual(before.sessions)
  expect((await read(page)).sessionMutations.at(-1).status).toBe('available')
})

test('session actions: started and inactive sessions cannot be postponed', async ({ page }) => {
  await start(page, { past: true })
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  await page.evaluate(key => { const data = JSON.parse(localStorage.getItem(key)); data.clients.find(item => item.id === 'c1').status = 'inactive'; localStorage.setItem(key, JSON.stringify(data)) }, KEY)
  await page.goto('/#/sessions/undo-s2')
  // Load the injected inactive client into the app, not only browser storage.
  await page.reload(); await waitForPortal(page)
  await expect(page.getByText('Client inactive', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  expect((await read(page)).sessionMutations ?? []).toHaveLength(0)
})


test('session actions: conflict offers another date and time without changing other bookings', async ({ page, isMobile }) => {
  await start(page, { conflict: true }); const before = await read(page)
  await activate(page.getByRole('button', { name: 'Postpone', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Postpone this session?', exact: true })
  await expect(dialog.getByRole('alert')).toContainText('conflicts with another session for this trainer')
  await expect(dialog.getByRole('button', { name: 'Check Availability', exact: true })).toBeDisabled()
  expect((await read(page)).sessions).toEqual(before.sessions)
  await activate(dialog.getByLabel('Postponed session date', { exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Postponed session date calendar', exact: true }).getByRole('button', { name: '27 Oct 2026', exact: true }), isMobile)
  await dialog.getByLabel('Postponed session start time', { exact: true }).fill('13:00')
  await dialog.getByLabel('Postponed session end time', { exact: true }).fill('14:00')
  await activate(dialog.getByRole('button', { name: 'Check Availability', exact: true }), isMobile)
  await expect(dialog.getByRole('button', { name: 'Confirm Postponement', exact: true })).toBeEnabled()
  await expect(dialog.getByRole('table')).toContainText('27 Oct 2026')
  expect((await read(page)).sessions).toEqual(before.sessions)
  await activate(dialog.getByRole('button', { name: 'Confirm Postponement', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  const after = await read(page)
  expect(after.sessions[0]).toMatchObject({ date: '2026-10-27', from: '13:00', to: '14:00' })
  expect(after.sessions.slice(1)).toEqual(before.sessions.slice(1))
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  await page.reload(); await waitForPortal(page); await messages(page)
  await reverse(page, isMobile, postponedRow(page))
  expect((await read(page)).sessions).toEqual(before.sessions)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
})
