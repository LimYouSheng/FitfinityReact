import { expect, test } from '@playwright/test'
import { seed } from '../src/data/seed.js'

const KEY = 'fitfinity-m2-demo-db-v4'
async function start(page, route = 'packages', data = seed) {
  await page.addInitScript(({ key, data }) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data))
  }, { key: KEY, data })
  await page.goto(`/#/${route}`)
}
const database = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
const routeTo = (page, route) => page.evaluate(route => { location.hash = `#/${route}` }, route)
async function confirm(page, title, action) {
  const dialog = page.getByRole('dialog', { name: title, exact: true })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: action, exact: true }).click()
}
async function openMenu(page) {
  const toggle = page.getByRole('button', { name: 'Open navigation', exact: true })
  if (await toggle.isVisible()) await toggle.click()
}

async function expectPackageActionSpacing(page) {
  const form = page.locator('.package-setup form')
  const gaps = await form.evaluate(element => {
    const fieldsBottom = element.querySelector('fieldset').getBoundingClientRect().bottom
    return [...element.querySelectorAll('.inline-actions button')].map(button => button.getBoundingClientRect().top - fieldsBottom)
  })
  expect(gaps).toHaveLength(2)
  for (const gap of gaps) expect(gap).toBeGreaterThanOrEqual(16)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
}

test('M3 Setup upgrades old data, preloads packages and confirms create, edit and deactivation with routed Messages', async ({ page }) => {
  const old = structuredClone(seed); delete old.packages; old.clients[0].name = 'Preserved client'
  await start(page, 'packages', old)
  for (const text of ['12 sessions · 90 days', '24 sessions · 180 days', '36 sessions · 270 days']) {
    await expect(page.getByLabel('Package list').getByText(text, { exact: true })).toBeVisible()
  }
  await page.getByRole('button', { name: 'Add Package', exact: true }).click()
  await page.getByLabel('Package name', { exact: true }).fill('Strength programme')
  await page.getByLabel('Package session count', { exact: true }).selectOption('36')
  await expect(page.locator('.package-setup form p')).toHaveCount(0)
  await expectPackageActionSpacing(page)
  await page.getByRole('button', { name: 'Create Package', exact: true }).click()
  expect((await database(page)).packages).toBeUndefined()
  await confirm(page, 'Create Package?', 'Create Package')
  await expect(page.getByRole('heading', { name: 'Package details', exact: true })).toBeVisible()
  await expect(page.locator('.notification-success')).toContainText('Package created.')
  const created = (await database(page)).packages.find(item => item.name === 'Strength programme')
  expect(created).toMatchObject({ total: 36, validityDays: 270 })
  await page.getByRole('button', { name: 'Edit Package' }).click()
  await page.getByLabel('Package name', { exact: true }).fill('Strength programme revised')
  await expectPackageActionSpacing(page)
  await page.getByRole('button', { name: 'Save Package', exact: true }).click()
  await confirm(page, 'Save Package?', 'Save Package')
  await expect(page.getByRole('heading', { name: 'Strength programme revised', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Deactivate Package', exact: true }).click()
  await confirm(page, 'Deactivate Package?', 'Deactivate Package')
  await expect(page.locator('.package-setup .status-badge')).toHaveText('Inactive')
  await expect(page.locator('.notification-warning')).toContainText('Package deactivated.')
  const after = await database(page)
  expect(after.clients).toEqual(old.clients)
  expect(after.sessions).toEqual(old.sessions)
  await routeTo(page, 'messages')
  await page.getByRole('button', { name: 'Open Package updated: Strength programme revised', exact: true }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Package updated: Strength programme revised', exact: true })
  await dialog.getByRole('button', { name: 'View Package · Strength programme revised', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`#/packages/${created.id}$`))
  await expect(page.getByRole('button', { name: 'Reactivate Package' })).toBeVisible()
})

for (const [total, validity, frequency] of [[12, 90, 2], [24, 180, 1], [36, 270, 3]]) {
  test(`M3 ${total}-session package remains independent of ${frequency} weekly sessions and has correct validity and gym entitlement`, async ({ page }) => {
    const name = `Package ${total} client`
    await start(page, 'clients/new')
    await page.getByLabel('Client name', { exact: true }).fill(name)
    await page.getByRole('button', { name: 'Continue to Package & Preferences', exact: true }).click()
    await page.getByLabel('PT Package', { exact: true }).selectOption(`package-${total}`)
    await page.getByLabel('Start date', { exact: true }).fill('2026-09-07')
    const membership = page.getByLabel('Gym membership', { exact: true })
    await expect(membership).toHaveAttribute('readonly', '')
    await expect(membership).not.toBeEditable()
    for (const cadence of [1, 2, 7, frequency]) {
      await page.getByLabel('Weekly frequency', { exact: true }).selectOption(String(cadence))
      await expect(membership).toHaveValue(cadence >= 2 ? 'Included' : 'Not included')
      await expect(page.getByLabel('PT Package', { exact: true })).toHaveValue(`package-${total}`)
    }
    await expect(page.getByLabel('Remarks', { exact: true })).toHaveCount(0)
    await expect(page.locator('.onboarding-package-fields > .onboarding-field')).toHaveCount(4)
    await expect(page.locator('.onboarding-step-body .onboarding-hint')).toHaveCount(0)
    const gymBox = await membership.boundingBox(), frequencyBox = await page.getByLabel('Weekly frequency', { exact: true }).boundingBox()
    if (page.viewportSize().width > 430) {
      expect(gymBox.x).toBeGreaterThanOrEqual(frequencyBox.x + frequencyBox.width)
      expect(Math.abs(gymBox.y - frequencyBox.y)).toBeLessThanOrEqual(1)
    } else expect(gymBox.y).toBeGreaterThanOrEqual(frequencyBox.y + frequencyBox.height)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
    await page.getByRole('button', { name: 'Continue to Client Availability', exact: true }).click()
    for (const day of ['Monday', 'Wednesday', 'Friday'].slice(0, frequency)) await page.getByRole('button', { name: day, exact: true }).click()
    await page.getByLabel('Availability from', { exact: true }).fill('18:00')
    await page.getByLabel('Availability to', { exact: true }).fill('19:00')
    await page.getByRole('button', { name: 'Add Time', exact: true }).click()
    await page.getByRole('button', { name: 'Continue to Trainer Matching', exact: true }).click()
    await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
    const summary = page.getByLabel('Form summary')
    await expect(summary).toContainText(`${validity} days`)
    // Assert the exact summary row, without matching unrelated Included/Not included text.
    await expect(summary.locator('dt').filter({ hasText: /^Free gym package$/ }).locator('..')).toContainText(frequency >= 2 ? 'Included' : 'Not included')
    await page.getByRole('button', { name: 'Create Client', exact: true }).click()
    await confirm(page, `Create ${name}?`, 'Create Client')
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
    const db = await database(page), client = db.clients.find(item => item.name === name)
    expect(client.package).toMatchObject({ total, validityDays: validity, sessionsPerWeek: frequency, freeGym: frequency >= 2 })
    const sessions = db.sessions.filter(item => item.clientId === client.id)
    expect(sessions).toHaveLength(total)
    expect(sessions.every(item => item.date <= client.package.endDate)).toBe(true)
    const menu = page.locator('.profile-menu')
    if (await menu.locator('summary').isVisible()) await menu.locator('summary').click()
    await menu.getByRole('button', { name: 'Package', exact: true }).click()
    await expect(page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Current Package', exact: true }) })).toContainText(`Free gym package: ${frequency >= 2 ? 'Included' : 'Not included'}`)
  })
}

test('M3 owner Setup is reachable from the menu and both roles have a prominent remuneration eye without header copy', async ({ page }) => {
  await start(page, 'dashboard')
  await openMenu(page)
  const nav = page.getByRole('navigation', { name: 'Portal navigation' })
  await expect(nav.locator('.nav-group').filter({ hasText: 'Setup' }).getByRole('button', { name: 'Packages', exact: true })).toBeVisible()
  await nav.getByRole('button', { name: 'Packages', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Packages', exact: true })).toBeVisible()
  const actionStyles = []
  for (const [route, names] of [['dashboard', ['Add Client', 'Add Trainer']], ['clients', ['Add New Client']], ['trainers', ['Add New Trainer']]]) {
    await routeTo(page, route)
    for (const name of names) {
      const button = page.getByRole('button', { name, exact: true })
      await expect(button).toBeVisible()
      actionStyles.push(await button.evaluate(element => {
        const style = getComputedStyle(element)
        return [element.getBoundingClientRect().height, style.padding, style.fontSize, style.fontWeight, style.backgroundColor, style.borderRadius]
      }))
    }
  }
  for (const style of actionStyles) expect(style).toEqual(actionStyles[0])
  for (const trainer of [false, true]) {
    if (trainer) await page.locator('.role-switcher select').selectOption('u-marcus')
    await routeTo(page, 'remuneration')
    await expect(page.locator('.remuneration-page .page-head p')).toHaveCount(0)
    const eye = page.getByRole('button', { name: 'Show remuneration amounts', exact: true })
    await expect(eye).toBeVisible()
    const size = await eye.boundingBox()
    expect(size.height).toBeGreaterThanOrEqual(44)
    if (page.viewportSize().width <= 720) {
      const header = await page.locator('.remuneration-page .page-head').boundingBox()
      expect(Math.abs(size.y - header.y)).toBeLessThanOrEqual(1)
      expect(Math.abs(size.x + size.width - header.x - header.width)).toBeLessThanOrEqual(1)
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
    }
    expect(await eye.evaluate(element => getComputedStyle(element).borderTopWidth)).toBe('2px')
    await eye.click()
    await expect(page.getByRole('button', { name: 'Hide remuneration amounts', exact: true })).toBeVisible()
    if (trainer) {
      await expect(nav.getByRole('button', { name: 'Packages', exact: true })).toHaveCount(0)
      await routeTo(page, 'packages')
      await expect(page.getByText('Package setup is available to the owner.', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Add Package', exact: true })).toHaveCount(0)
    }
  }
})

test('M3 native Back preserves edits until confirmed, and confirmation focus cannot reach the background', async ({ page }) => {
  await start(page, 'packages')
  await page.getByRole('button', { name: 'Add Package', exact: true }).click()
  const field = page.getByLabel('Package name', { exact: true })
  await field.fill('Keep this draft')
  await page.goBack()
  const dialog = page.getByRole('dialog', { name: 'Leave this edit?', exact: true })
  await expect(dialog).toBeVisible()
  await expect(page).toHaveURL(/#\/packages\/new$/)
  expect(await field.evaluate(element => Boolean(element.closest('[inert]')))).toBe(true)
  await expect.poll(() => dialog.evaluate(element => element.contains(document.activeElement))).toBe(true)
  for (let index = 0; index < 5; index += 1) {
    await page.keyboard.press(index % 2 ? 'Shift+Tab' : 'Tab')
    await expect.poll(() => dialog.evaluate(element => element.contains(document.activeElement))).toBe(true)
  }
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(field).toHaveValue('Keep this draft')
  await expect(field).toBeFocused()
  await page.goBack()
  await confirm(page, 'Leave this edit?', 'Leave Without Saving')
  await expect(page).toHaveURL(/#\/packages$/)
  await page.goForward()
  await expect(page.getByLabel('Package name', { exact: true })).toHaveValue('')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('M3 client and trainer filters stay inside their panels across the former tablet overflow interval', async ({ page }) => {
  await start(page, 'clients')
  for (const route of ['clients', 'trainers']) {
    await routeTo(page, route)
    for (const width of [780, 781, 810, 834, 884, 885, 900, 901]) {
      await page.setViewportSize({ width, height: 1024 })
      const controls = page.locator('.list-controls')
      await expect(controls).toBeVisible()
      const bounds = await controls.evaluate(element => {
        const panel = element.closest('.panel').getBoundingClientRect()
        return [...element.querySelectorAll('input,select,button')].filter(child => child.getBoundingClientRect().width)
          .map(child => { const box = child.getBoundingClientRect(); return { left: box.left - panel.left, right: panel.right - box.right } })
      })
      for (const box of bounds) { expect(box.left).toBeGreaterThanOrEqual(0); expect(box.right).toBeGreaterThanOrEqual(0) }
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
    }
  }
})

for (const role of ['owner', 'trainer']) {
  test(`M3 ${role} session shows both pending changes below statuses on phone and beside them on tablet and desktop`, async ({ page }) => {
    const data = structuredClone(seed), session = data.sessions.find(item => item.id === 's1')
    data.messages = ['session_time', 'session_trainer'].map((type, index) => ({
      id: `pending-${index}`, recipientRole: 'owner', read: false, status: 'pending', title: `Pending ${type}`, body: 'Review session change.',
      createdAt: `2026-09-06T10:0${index}:00Z`, sessionId: session.id,
      request: { type, sessionId: session.id, trainerId: session.trainerId,
        previous: { date: session.date, from: session.from, to: session.to }, next: { date: '2026-12-01', from: '10:00', to: '11:00' },
        previousTrainerId: session.trainerId, replacementTrainerId: 't2' },
    }))
    await start(page, 'dashboard', data)
    if (role === 'trainer') await page.locator('.role-switcher select').selectOption('u-marcus')
    await routeTo(page, 'sessions/s1')
    await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
    const pending = page.getByLabel('Pending session approvals')
    await expect(pending.locator('.status-badge.amber')).toHaveCount(2)
    await expect(pending).toContainText('Time change pending')
    await expect(pending).toContainText('Trainer change pending')
    const statusBox = await page.getByLabel('Session status summary').boundingBox(), pendingBox = await pending.boundingBox()
    if (page.viewportSize().width <= 620) expect(pendingBox.y).toBeGreaterThanOrEqual(statusBox.y + statusBox.height)
    else expect(pendingBox.x).toBeGreaterThanOrEqual(statusBox.x + statusBox.width)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
    if (role === 'owner') {
      await routeTo(page, 'messages')
      await page.getByRole('button', { name: 'Open Pending session_trainer', exact: true }).click()
      const review = page.getByRole('dialog', { name: 'Pending session_trainer', exact: true })
      await review.getByRole('button', { name: 'Reject Request', exact: true }).click()
      await page.locator('.modal-actions').getByRole('button', { name: 'Cancel', exact: true }).click()
      await expect.poll(() => review.evaluate(element => element.contains(document.activeElement))).toBe(true)
      await review.getByRole('button', { name: 'Reject Request', exact: true }).click()
      await page.locator('.modal-actions').getByRole('button', { name: 'Reject Request', exact: true }).click()
      await expect(review).toContainText('Rejected')
      await review.getByRole('button', { name: 'Close message', exact: true }).click()
      await expect(review).toHaveCount(0)
      await routeTo(page, 'sessions/s1')
      await expect(pending.locator('.status-badge')).toHaveCount(1)
      await expect(pending).toHaveText('Time change pending')
    }
  })
}
