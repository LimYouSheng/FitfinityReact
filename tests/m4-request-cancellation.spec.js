import { expect, test, selectDemoIdentity, waitForPortal } from './fixtures.js'
import { seed } from '../src/data/seed.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const current = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)

async function start(page, type = 'session_time') {
  await page.clock.setFixedTime(new Date('2026-09-09T04:00:00Z'))
  await page.addInitScript(({ key, data }) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data))
  }, { key: KEY, data: seed })
  await page.goto('/#/dashboard')
  await waitForPortal(page)
  const identities = await page.evaluate(({ key, type }) => {
    const db = JSON.parse(localStorage.getItem(key))
    const client = db.clients.find(item => item.id === 'c1')
    const trainer = db.trainers.find(item => item.id === client.trainerId)
    const session = db.sessions.find(item => item.clientId === client.id && item.date > '2026-09-09' && item.status !== 'completed')
    const requester = db.users.find(item => item.role === 'trainer' && item.status === 'active' && item.trainerId === trainer.id)
    // A trainer record alone does not guarantee a selectable demo login.
    const other = db.users.find(item => item.role === 'trainer' && item.status === 'active' && item.trainerId !== trainer.id
      && db.trainers.some(candidate => candidate.id === item.trainerId && candidate.status === 'active'))
    if (!requester || !other) throw new Error('Cancellation fixture requires two active trainer accounts.')
    const replacement = db.trainers.find(item => item.id === other.trainerId)
    const request = { type, trainerId: trainer.id, clientId: client.id, sessionId: session.id,
      previous: { date: session.date, from: session.from, to: session.to },
      next: { date: '2026-12-15', from: '10:00', to: '11:00' },
      previousTrainerId: trainer.id, replacementTrainerId: replacement.id,
      oldAvailability: trainer.availability, newAvailability: { Monday: [['09:00', '12:00']] },
      oldSlots: client.fixedWeeklySchedule, newSlots: client.fixedWeeklySchedule.map(slot => ({ ...slot, from: '19:00', to: '20:00' })) }
    for (const number of [1, 2]) {
      const common = { sessionId: session.id, clientId: client.id, trainerId: trainer.id, createdAt: new Date().toISOString(), read: false, status: 'pending', kind: 'schedule_request' }
      db.messages.push(
        { ...common, id: `cancel-${number}`, title: `Review cancellation test ${number}`, body: 'Review the proposed change.', recipientRole: 'owner', request },
        { ...common, id: `cancel-receipt-${number}`, requestId: `cancel-${number}`, title: `Cancellation test ${number}`, body: 'Your request is awaiting owner approval.', recipientTrainerId: trainer.id },
      )
    }
    localStorage.setItem(key, JSON.stringify(db))
    return { trainer: requester.id, other: other.id }
  }, { key: KEY, type })
  await page.reload()
  await selectDemoIdentity(page, identities.trainer)
  await page.goto('/#/messages/approvals')
  await waitForPortal(page)
  await page.getByLabel('Search messages', { exact: true }).fill('Cancellation test')
  await page.getByRole('button', { name: 'Open Cancellation test 1', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Cancellation test 1', exact: true })
  // Opening an unread message awaits its save; fault injection must target cancellation afterwards.
  await expect(dialog).toBeVisible()
  return { identities, dialog }
}

async function confirmCancellation(page, dialog) {
  await dialog.getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await page.getByRole('dialog', { name: 'Cancel this request?', exact: true }).getByRole('button', { name: 'Cancel Request', exact: true }).click()
}

for (const type of ['session_time', 'session_trainer', 'fixed_weekly_schedule', 'trainer_availability']) {
  test(`M4.1 trainer cancels only the selected ${type} request with retained history, owner notice and Back state`, async ({ page }) => {
    const { identities, dialog } = await start(page, type)
    await expect(dialog.getByLabel('Current at request', { exact: true })).toBeVisible()
    await expect(dialog.getByLabel('Requested', { exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Approve Request' })).toHaveCount(0)
    const before = await current(page)
    await dialog.getByRole('button', { name: 'Cancel Request', exact: true }).click()
    await page.getByRole('dialog', { name: 'Cancel this request?', exact: true }).getByRole('button', { name: 'Cancel', exact: true }).click()
    expect(await current(page)).toEqual(before)
    await confirmCancellation(page, dialog)
    await expect(dialog.getByText('Cancelled', { exact: true })).toBeVisible()
    await expect(dialog.getByText(/Cancelled by Marcus Tan/)).toBeVisible()
    await expect(dialog.locator('time[datetime="2026-09-09T04:00:00.000Z"]')).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Cancel Request', exact: true })).toHaveCount(0)
    const after = await current(page)
    expect({ ...after, messages: before.messages }).toEqual(before)
    expect(after.messages.find(item => item.id === 'cancel-2').status).toBe('pending')
    expect(after.messages.find(item => item.id === 'cancel-receipt-2').status).toBe('pending')
    expect(after.messages.find(item => item.id === 'cancellation-cancel-1-owner')).toMatchObject({ read: false, recipientRole: 'owner', status: 'cancelled' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
    await page.goBack()
    await expect(dialog).toHaveCount(0)
    await expect(page.getByLabel('Search messages', { exact: true })).toHaveValue('Cancellation test')
    await page.goForward()
    await expect(dialog.getByText('Cancelled', { exact: true })).toBeVisible()
    await page.reload()
    await expect(dialog.getByText('Cancelled', { exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: 'Close message', exact: true }).click()
    await selectDemoIdentity(page, identities.other)
    await page.goto('/#/messages/approvals')
    await expect(page.getByRole('button', { name: 'Open Cancellation test 1', exact: true })).toHaveCount(0)
    await selectDemoIdentity(page, 'u-owner')
    await page.goto('/#/messages/approvals')
    await page.getByLabel('Search messages', { exact: true }).fill('Review cancellation test 1')
    await page.getByRole('button', { name: 'Open Review cancellation test 1', exact: true }).click()
    const ownerDialog = page.getByRole('dialog', { name: 'Review cancellation test 1', exact: true })
    await expect(ownerDialog.getByText('Cancelled', { exact: true })).toBeVisible()
    await expect(ownerDialog.getByRole('button', { name: /Approve Request|Reject Request|Cancel Request/ })).toHaveCount(0)
  })
}

test('M4.1 an owner decision received during cancellation confirmation remains authoritative', async ({ page }) => {
  const { dialog } = await start(page)
  await dialog.getByRole('button', { name: 'Cancel Request', exact: true }).click()
  // Simulate the refreshed server decision while the trainer is reviewing confirmation.
  await page.evaluate(key => {
    const db = JSON.parse(localStorage.getItem(key))
    for (const message of db.messages.filter(item => item.id === 'cancel-1' || item.requestId === 'cancel-1')) {
      Object.assign(message, { status: 'rejected', decidedBy: 'u-owner', decidedAt: new Date().toISOString() })
    }
    localStorage.setItem(key, JSON.stringify(db))
    window.dispatchEvent(new StorageEvent('storage', { key }))
  }, KEY)
  // The message layer is intentionally inert beneath confirmation; inspect its retained DOM.
  const background = page.locator('.message-detail-modal[aria-label="Cancellation test 1"]')
  await expect(background.getByText('Rejected', { exact: true })).toBeAttached()
  expect(await background.evaluate(element => Boolean(element.closest('[inert]')))).toBe(true)
  const decided = await current(page)
  await page.getByRole('dialog', { name: 'Cancel this request?', exact: true }).getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await expect(dialog.locator('.request-review [role="alert"]')).toContainText('no longer pending')
  expect(await current(page)).toEqual(decided)
  await expect(dialog.getByRole('button', { name: 'Cancel Request', exact: true })).toHaveCount(0)
})

test('M4.1 cancellation save failure retains pending requests and a retry records one cancellation', async ({ page }) => {
  const { dialog } = await start(page)
  const before = await current(page)
  await page.evaluate(key => {
    const setItem = Storage.prototype.setItem
    Storage.prototype.setItem = function (name, value) {
      if (name === key) { Storage.prototype.setItem = setItem; throw new Error('Cancellation storage unavailable') }
      return setItem.call(this, name, value)
    }
  }, KEY)
  await confirmCancellation(page, dialog)
  await expect(dialog.locator('.request-review [role="alert"]')).toContainText('Cancellation storage unavailable')
  expect(await current(page)).toEqual(before)
  await expect(dialog.getByRole('button', { name: 'Cancel Request', exact: true })).toBeEnabled()
  await confirmCancellation(page, dialog)
  await expect(dialog.getByText('Cancelled', { exact: true })).toBeVisible()
  expect((await current(page)).messages.filter(item => item.id.startsWith('cancellation-cancel-1-'))).toHaveLength(2)
})
