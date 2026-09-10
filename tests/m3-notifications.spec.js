import { waitForPortal, expect, test } from './fixtures.js'
import { seed } from '../src/data/seed.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const button = (page, name) => page.getByRole('button', { name, exact: true })
const banner = page => page.locator('.notification-banner')
const data = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
async function start(page, route, initial = seed) {
  await page.addInitScript(({ key, initial }) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(initial))
  }, { key: KEY, initial })
  await page.goto(`/#/${route}`)
  await waitForPortal(page)
}
async function confirm(page, action) {
  await button(page, action).click()
  const dialog = page.getByRole('dialog', { name: `${action}?`, exact: true })
  await button(dialog, action).click()
  await expect(dialog).toHaveCount(0)
}
async function notice(page, tone, message) {
  await expect(banner(page)).toHaveCount(1)
  await expect(banner(page)).toHaveAttribute('data-tone', tone)
  await expect(banner(page).getByRole(tone === 'error' ? 'alert' : 'status')).toHaveText(message)
}

test('M3 top save banner survives the created profile, stays below navigation and has no inline copy', async ({ page }) => {
  await start(page, 'exercises/new')
  await button(page, 'Create Exercise').click()
  await expect(banner(page)).toHaveCount(0)
  await page.getByRole('textbox', { name: 'Exercise name', exact: true }).fill('M3 Banner Exercise')
  await button(page, 'Create Exercise').click()
  await button(page.getByRole('dialog', { name: 'Create Exercise?' }), 'Cancel').click()
  await expect(banner(page)).toHaveCount(0)
  await confirm(page, 'Create Exercise')
  await expect(page.getByRole('heading', { name: 'M3 Banner Exercise', exact: true })).toBeVisible()
  await notice(page, 'success', 'Exercise created.')
  await expect(page.locator('main [role="status"]')).toHaveCount(0)
  const geometry = await banner(page).evaluate(el => {
    const rect = el.getBoundingClientRect(), header = document.querySelector('.topbar').getBoundingClientRect()
    const main = document.querySelector('.portal-main').getBoundingClientRect()
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, headerBottom: header.bottom,
      mainLeft: main.left, mainRight: main.right, bannerHeight: rect.height,
      width: innerWidth, height: innerHeight, overflow: document.documentElement.scrollWidth - innerWidth,
      background: getComputedStyle(el).backgroundColor }
  })
  expect(geometry.left).toBeGreaterThanOrEqual(0)
  expect(geometry.right).toBeLessThanOrEqual(geometry.width)
  expect(Math.abs(geometry.left - geometry.mainLeft)).toBeLessThanOrEqual(1)
  expect(Math.abs(geometry.right - geometry.mainRight)).toBeLessThanOrEqual(1)
  expect(geometry.bannerHeight).toBeLessThanOrEqual(38)
  expect(geometry.top).toBeGreaterThanOrEqual(geometry.headerBottom)
  expect(geometry.top).toBeLessThan(130)
  expect(geometry.bottom).toBeLessThan(geometry.height)
  expect(geometry.overflow).toBeLessThanOrEqual(1)
  expect(geometry.background).toBe('rgb(18, 60, 44)')
  await button(page, 'Dismiss notification').click()
  await button(page, 'Edit Exercise').click()
  await page.getByLabel('Description', { exact: true }).fill('Banner save check')
  await confirm(page, 'Save Exercise')
  await notice(page, 'success', 'Exercise saved.')
  await expect(page.locator('main [role="status"]')).toHaveCount(0)
  await page.reload()
  await expect(banner(page)).toHaveCount(0)
  await expect(page.locator('.library-summary')).toContainText('Banner save check')
})

test('M3 approvals and rejections show distinct banners above the message popup without closing it', async ({ page }) => {
  const initial = structuredClone(seed), trainer = initial.trainers.find(item => item.id === 't1')
  initial.messages = ['approve', 'reject'].map((id, index) => ({ id, title: `Banner ${id}`, recipientRole: 'owner',
    read: false, status: 'pending', createdAt: `2099-01-01T0${index}:00:00Z`, trainerId: trainer.id,
    kind: 'availability_request', body: 'Review availability.', request: { type: 'trainer_availability',
      trainerId: trainer.id, oldAvailability: trainer.availability,
      newAvailability: { ...trainer.availability, Sunday: [['10:00', '11:00']] } } }))
  await start(page, 'messages', initial)
  const colours = []
  for (const [id, action, tone, text] of [['approve', 'Approve Request', 'success', 'Request approved.'], ['reject', 'Reject Request', 'warning', 'Request rejected.']]) {
    await button(page, `Open Banner ${id}`).click()
    const dialog = page.getByRole('dialog', { name: `Banner ${id}`, exact: true })
    await expect(banner(page)).toHaveCount(0)
    await button(dialog, action).click()
    await page.locator('.modal-actions').getByRole('button', { name: action, exact: true }).click()
    await notice(page, tone, text)
    colours.push(await banner(page).evaluate(el => getComputedStyle(el).backgroundColor))
    await button(page, 'Dismiss notification').click()
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('.request-status')).toHaveText(id === 'approve' ? 'Approved' : 'Rejected')
    await button(dialog, 'Close message').click()
    await expect(dialog).toHaveCount(0)
  }
  expect(new Set(colours).size).toBe(2)
})

test('M3 failed exercise save has a red banner, retains the draft and succeeds on retry', async ({ page }) => {
  await start(page, 'exercises/new')
  await page.getByRole('textbox', { name: 'Exercise name', exact: true }).fill('M3 Retry Banner')
  const before = await data(page)
  // Fail only the real database write, after loading. Restore it for the retry.
  await page.evaluate(key => {
    window.restoreNotificationStorage = Storage.prototype.setItem
    Storage.prototype.setItem = function (name, value) {
      if (name === key) throw new Error('Storage full. Try again.')
      return window.restoreNotificationStorage.call(this, name, value)
    }
  }, KEY)
  await confirm(page, 'Create Exercise')
  await notice(page, 'error', 'Storage full. Try again.')
  await expect(page.getByRole('textbox', { name: 'Exercise name', exact: true })).toHaveValue('M3 Retry Banner')
  expect(await data(page)).toEqual(before)
  await button(page, 'Dismiss notification').click()
  await page.evaluate(() => {
    Storage.prototype.setItem = window.restoreNotificationStorage
    delete window.restoreNotificationStorage
  })
  await confirm(page, 'Create Exercise')
  await notice(page, 'success', 'Exercise created.')
  expect((await data(page)).exerciseLibrary.filter(item => item.name === 'M3 Retry Banner')).toHaveLength(1)
})

test('M3 client edit uses the global banner and keeps the top navigation clickable', async ({ page }) => {
  await start(page, 'clients/c1')
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information', exact: true }) })
  await button(panel, 'Edit').click()
  const email = panel.getByLabel('Client email', { exact: true })
  await email.fill('banner@example.com')
  await page.evaluate(key => {
    const originalGetItem = Storage.prototype.getItem
    window.__profileRefreshReads = 0
    window.__restoreProfileRefreshGetItem = originalGetItem
    Storage.prototype.getItem = function (name) {
      if (name === key) window.__profileRefreshReads += 1
      return originalGetItem.call(this, name)
    }
    window.dispatchEvent(new Event('storage'))
  }, KEY)
  await expect.poll(() => page.evaluate(() => window.__profileRefreshReads)).toBeGreaterThan(0)
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  await expect(email).toHaveValue('banner@example.com')
  await expect(button(panel, 'Save')).toBeVisible()
  await page.evaluate(() => {
    Storage.prototype.getItem = window.__restoreProfileRefreshGetItem
    delete window.__restoreProfileRefreshGetItem
    delete window.__profileRefreshReads
  })
  await button(panel, 'Save').click()
  await button(page.getByRole('dialog', { name: 'Save client information?', exact: true }), 'Save Changes').click()
  await notice(page, 'success', 'Client details saved.')
  expect((await data(page)).clients.find(item => item.id === 'c1').email).toBe('banner@example.com')
  await button(page.locator('.topbar'), 'Messages').click()
  await expect(page.getByRole('heading', { name: 'Messages', exact: true })).toBeVisible()
  await notice(page, 'success', 'Client details saved.')
  await button(page, 'Dismiss notification').click()
  await expect(banner(page)).toHaveCount(0)
})

test('M3 hidden remuneration amounts prompt a blue review banner before any approval confirmation', async ({ page }) => {
  const initial = structuredClone(seed)
  const completed = initial.sessions.find(item => item.status === 'completed')
  initial.sessions = [{ ...completed, id: 'banner-pay', clientId: 'c1', trainerId: 't1',
    date: '2020-08-20', from: '18:00', to: '19:00', outcome: { durationMinutes: 60 } }]
  delete initial.remunerationEntries
  delete initial.remunerationApprovals
  await start(page, 'remuneration/2020-09/t1', initial)
  const before = await data(page)
  await button(page, 'Approve Remuneration').click()
  await notice(page, 'info', 'Show amounts to review the total before approving.')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(await data(page)).toEqual(before)
  await expect(page.locator('.remuneration-page')).not.toContainText('Show amounts to review the total before approving.')
  await button(page, 'Show remuneration amounts').click()
  await button(page, 'Approve Remuneration').click()
  const confirmation = page.getByRole('dialog', { name: 'Approve trainer remuneration?', exact: true })
  await expect(confirmation).toContainText('80.00')
  expect(await data(page)).toEqual(before)
  await button(confirmation, 'Approve Remuneration').click()
  await notice(page, 'success', 'Remuneration approved.')
})
