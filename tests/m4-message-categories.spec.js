import { test, expect, selectDemoIdentity } from './fixtures.js'
import { seed } from '../src/data/seed.js'

const database = 'fitfinity-m2-demo-db-v4'
async function start(page, route = 'messages') {
  const data = structuredClone(seed)
  const common = { createdAt: '2026-09-02T10:00:00Z', read: false, recipientRole: 'owner' }
  data.messages = [
    ...Array.from({ length: 12 }, (_, index) => ({ ...common, id: `renewal-${index}`, kind: 'renewal', clientId: 'c3', title: `Renewal ${index}`, body: 'Package follow-up.' })),
    { ...common, id: 'session-example', kind: 'session', title: 'Morning session', body: 'Routine session update.' },
    { ...common, id: 'private-renewal', recipientRole: undefined, recipientTrainerId: 't2', kind: 'renewal', title: 'Another trainer renewal' },
    { ...common, id: 'trainer-renewal', recipientRole: undefined, recipientTrainerId: 't1', kind: 'renewal', title: 'Assigned trainer renewal' },
  ]
  await page.addInitScript(({ key, data }) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, { key: database, data })
  await page.goto(`/#/${route}`)
}

async function selectCategory(page, label) {
  const categories = page.getByRole('group', { name: 'Message categories' })
  const menu = categories.locator('.profile-menu'), summary = menu.locator('summary')
  await expect(menu).toBeVisible()
  const dropdown = await summary.isVisible()
  if (dropdown && await menu.getAttribute('open') === null) await summary.click()
  await menu.getByRole('button', { name: label, exact: true }).click()
  await expect(menu.locator('button[aria-current="true"]')).toHaveText(label)
  if (dropdown) {
    await expect(summary).toHaveText(label)
    await expect(menu).not.toHaveAttribute('open')
  }
}

test('M4 shared profile navigation filters Messages by category with dates, search and pagination reset', async ({ page }) => {
  await start(page)
  const categories = page.getByRole('group', { name: 'Message categories' })
  await selectCategory(page, 'Renewals')
  await expect(categories.locator('.profile-tabs button')).toHaveCount(7)
  if (page.viewportSize().width >= 700) {
    await expect(categories.locator('summary')).toBeHidden()
    const rows = await categories.locator('.profile-tabs button').evaluateAll(buttons => buttons.map(button => ({ top: button.getBoundingClientRect().top, radius: getComputedStyle(button).borderRadius })))
    expect(new Set(rows.map(row => Math.round(row.top))).size).toBe(1)
    expect(rows.every(row => row.radius === '7px')).toBe(true)
  }
  await expect(page.getByLabel('Message list').locator('article')).toHaveCount(10)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByLabel('Message list').locator('article')).toHaveCount(2)
  await selectCategory(page, 'Sessions')
  await expect(page.getByRole('button', { name: 'Open Morning session' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Previous', exact: true })).toHaveCount(0)
  await page.getByLabel('Search messages').fill('Package')
  await expect(page.getByText('No messages match these filters.')).toBeVisible()
  await selectCategory(page, 'Renewals')
  await page.getByLabel('Messages from date').fill('2026-09-03')
  await expect(page.getByText('No messages match these filters.')).toBeVisible()
  await page.getByLabel('Messages from date').fill('2026-09-02')
  await page.getByLabel('Messages to date').fill('2026-09-02')
  await expect(page.getByLabel('Message list').locator('article')).toHaveCount(10)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
  const records = await page.evaluate(key => JSON.parse(localStorage.getItem(key)).messages, database)
  expect(records.every(message => !message.read)).toBe(true)
})

test('M4 dashboard renewal preview opens shared details and keeps read state in the linked category after reload', async ({ page }) => {
  await start(page, 'dashboard')
  const preview = page.getByLabel('Renewal messages')
  await expect(preview.locator('article')).toHaveCount(3)
  const total = page.getByRole('status', { name: 'Total renewal follow-ups' }).locator('.renewal-count')
  await expect(total).toHaveText('12')
  expect(await total.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(32)
  await expect(preview.getByText('Morning session')).toHaveCount(0)
  await preview.getByRole('button', { name: 'Open Renewal 0', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Renewal 0', exact: true })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'View Client · Nadia Koh', exact: true }).click()
  await expect(page).toHaveURL(/#\/clients\/c3$/)
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Calendar', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(total).toHaveText('12')
  await page.getByRole('button', { name: 'View All Renewals' }).click()
  await expect(page).toHaveURL(/#\/messages\/renewals$/)
  await page.reload()
  await expect(page.getByRole('group', { name: 'Message categories' }).locator('button[aria-current="true"]')).toHaveText('Renewals')
  await page.getByLabel('Search messages').fill('Renewal 0')
  await expect(page.getByRole('button', { name: 'Read Renewal 0', exact: true })).toBeVisible()
})

test('M4 trainer dashboard renewals respect recipients and show a real empty state', async ({ page }) => {
  await start(page, 'dashboard')
  await selectDemoIdentity(page, 'u-marcus')
  const preview = page.getByLabel('Renewal messages')
  await expect(preview.locator('article')).toHaveCount(1)
  await expect(page.locator('.renewal-count')).toHaveText('1')
  await expect(preview.getByRole('button', { name: 'Open Assigned trainer renewal' })).toBeVisible()
  await expect(page.getByText('Another trainer renewal')).toHaveCount(0)
  await page.evaluate(key => { const data = JSON.parse(localStorage.getItem(key)); data.messages = []; localStorage.setItem(key, JSON.stringify(data)) }, database)
  await page.reload()
  await expect(preview.getByText('No renewal messages.')).toBeVisible()
  await expect(page.locator('.renewal-count')).toHaveText('0')
  await expect(page.getByRole('heading', { name: 'Calendar', exact: true })).toBeVisible()
})

test('M4 Message category navigation matches client and trainer navigation through the same responsive boundary', async ({ page }) => {
  const styles = []
  for (const route of ['messages', 'clients/c3', 'trainers/t1']) {
    await page.goto(`/#/${route}`)
    const menu = page.locator('.profile-menu'), summary = menu.locator('summary')
    await expect(menu).toBeVisible()
    if (page.viewportSize().width < 700) await summary.click()
    styles.push(await menu.locator('.profile-tabs button').first().evaluate(button => {
      const style = getComputedStyle(button)
      return [style.minHeight, style.borderRadius, style.padding, style.fontSize, style.fontWeight]
    }))
  }
  expect(styles[1]).toEqual(styles[0]); expect(styles[2]).toEqual(styles[0])
  await page.setViewportSize({ width: 699, height: 1024 })
  await page.goto('/#/messages')
  await selectCategory(page, 'Renewals')
  const menu = page.getByRole('group', { name: 'Message categories' }).locator('.profile-menu')
  await page.setViewportSize({ width: 700, height: 1024 })
  await expect(menu.locator('summary')).toBeHidden()
  await expect(menu.getByRole('button', { name: 'Renewals', exact: true })).toHaveAttribute('aria-current', 'true')
  await page.setViewportSize({ width: 699, height: 1024 })
  await expect(menu.locator('summary')).toHaveText('Renewals')
  await expect(menu).not.toHaveAttribute('open')
  await menu.locator('summary').click()
  await page.mouse.click(690, 1000)
  await expect(menu).not.toHaveAttribute('open')
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
})
