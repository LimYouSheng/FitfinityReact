import { test, expect, drawClientSignature, selectDemoIdentity } from './fixtures.js'
import { seed } from '../src/data/seed.js'

const database = 'fitfinity-m2-demo-db-v4'
async function start(page, route = 'messages', firstRenewalTitle = 'Renewal 0') {
  const data = structuredClone(seed)
  const common = { createdAt: '2026-09-02T10:00:00Z', read: false, recipientRole: 'owner' }
  data.messages = [
    ...Array.from({ length: 12 }, (_, index) => ({ ...common, id: `renewal-${index}`, kind: 'renewal', clientId: 'c3', title: index === 0 ? firstRenewalTitle : `Renewal ${index}`, body: 'Package follow-up.' })),
    { ...common, id: 'session-example', kind: 'session', title: 'Morning session', body: 'Routine session update.' },
    { ...common, id: 'private-renewal', recipientRole: undefined, recipientTrainerId: 't2', kind: 'renewal', title: 'Another trainer renewal' },
    { ...common, id: 'trainer-renewal', recipientRole: undefined, recipientTrainerId: 't1', kind: 'renewal', title: 'Assigned trainer renewal' },
  ]
  await page.addInitScript(({ key, data }) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, { key: database, data })
  await page.goto(`/#/${route}`)
}

async function selectCategory(page, label) {
  const filter = page.getByLabel('Message category', { exact: true })
  await filter.click()
  await page.getByRole('listbox', { name: 'Message category' }).getByRole('option', { name: label, exact: true }).click()
  await expect(filter.locator('option:checked')).toHaveText(label)
  await expect(page.getByRole('listbox', { name: 'Message category' })).toHaveCount(0)
}

test('M4 shared profile navigation filters Messages by category with dates, search and pagination reset', async ({ page }) => {
  await start(page)
  const title = page.getByRole('heading', { name: 'Messages', exact: true })
  const badge = title.locator('..').locator('.status-badge')
  await expect(badge).toHaveText('13 new')
  const [a, b] = await Promise.all([title.boundingBox(), badge.boundingBox()])
  expect(a.x + a.width).toBeLessThanOrEqual(b.x)
  expect(Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y)).toBeGreaterThan(0)
  const categories = page.getByRole('group', { name: 'Message categories' })
  await selectCategory(page, 'Renewals')
  await expect(categories.getByLabel('Message category').locator('option')).toHaveCount(7)
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
  expect(records.every(message => Object.keys(message.readBy).length === 0)).toBe(true)
})

test('M4 dashboard renewal preview opens shared details and keeps read state in the linked category after reload', async ({ page }) => {
  const title = 'Renewal 0 · Nadia Koh · Annual personal training package renewal with remaining sessions, scheduling preferences, continued strength coaching goals and an updated progress review before the next training cycle'
  await start(page, 'dashboard', title)
  const preview = page.getByLabel('Renewal messages')
  await expect(preview.locator('article')).toHaveCount(3)
  for (const row of await preview.locator('article').all()) {
    await expect(row.getByRole('button')).toHaveCount(2)
    await expect(row.getByRole('button', { name: /^Remove / })).toHaveCount(0)
  }
  await expect(preview.locator('time, .message-approval-status, .message-title-head')).toHaveCount(0)
  const originalViewport = page.viewportSize()
  for (const width of [320, originalViewport.width]) {
    await page.setViewportSize({ width, height: originalViewport.height })
    const rows = await preview.locator('article').evaluateAll(elements => elements.map(element => {
      const row = element.getBoundingClientRect()
      const title = element.querySelector('.message-title-button').getBoundingClientRect()
      const state = element.querySelector('.message-state-button').getBoundingClientRect()
      const strong = element.querySelector('strong'), style = getComputedStyle(strong)
      return {
        height: row.height,
        centerDifference: Math.abs(title.y + title.height / 2 - state.y - state.height / 2),
        withinRow: title.left >= row.left && title.right <= state.left && state.right <= row.right,
        titleHeight: strong.getBoundingClientRect().height,
        lineHeight: parseFloat(style.lineHeight),
        whiteSpace: style.whiteSpace,
        ellipsis: style.textOverflow,
      }
    }))
    for (const row of rows) {
      expect(row.height).toBeCloseTo(44, 0)
      expect(row.centerDifference).toBeLessThanOrEqual(1)
      expect(row.withinRow).toBe(true)
      expect(row.titleHeight).toBeLessThanOrEqual(row.lineHeight + 1)
      expect(row.whiteSpace).toBe('nowrap')
      expect(row.ellipsis).toBe('ellipsis')
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
  }
  const total = page.getByRole('status', { name: 'Total renewal follow-ups' }).locator('.renewal-count')
  await expect(total).toHaveText('12')
  expect(await total.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeCloseTo(36 * 0.65 + 2, 1)
  await expect(preview.getByText('Morning session')).toHaveCount(0)
  const openRenewal = preview.getByRole('button', { name: `Open ${title}`, exact: true })
  await expect(openRenewal).toHaveAttribute('title', title)
  await expect(openRenewal).toHaveText(title)
  await openRenewal.click()
  const dialog = page.getByRole('dialog', { name: title, exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading', { name: title, exact: true })).toBeVisible()
  await expect(dialog.getByText('Package follow-up.', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: `Remove ${title} from renewals`, exact: true })).toBeVisible()
  await expect(dialog.locator('.message-detail-meta')).toContainText('2026')
  await dialog.getByRole('button', { name: 'View Client · Nadia Koh', exact: true }).click()
  await expect(page).toHaveURL(/#\/clients\/c3$/)
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Calendar', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(total).toHaveText('12')
  await page.getByRole('button', { name: 'View All Renewals' }).click()
  await expect(page).toHaveURL(/#\/messages\/renewals$/)
  await page.reload()
  await expect(page.getByLabel('Message category').locator('option:checked')).toHaveText('Renewals')
  await page.getByLabel('Search messages').fill('Renewal 0')
  await expect(page.getByRole('button', { name: `Read ${title}`, exact: true })).toBeVisible()
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).messages.find(message => message.id === 'renewal-0').title, database)).toBe(title)
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

test('M4 Message category uses the shared dropdown across responsive widths', async ({ page }) => {
  await start(page)
  await selectCategory(page, 'Renewals')
  const filter = page.getByLabel('Message category')
  for (const width of [699, 700, 390]) {
    await page.setViewportSize({ width, height: 1024 })
    await expect(filter).toBeVisible()
    await expect(filter.locator('option:checked')).toHaveText('Renewals')
    await filter.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('listbox', { name: 'Message category' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('listbox', { name: 'Message category' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
  }
})


test('M4 completing the tenth session creates one renewal reminder with independent recipient read state and trainer scope', async ({ page }) => {
  const data = structuredClone(seed)
  data.clients.find(client => client.id === 'c1').package.used = 9
  data.sessions.find(session => session.id === 's1').date = '2026-09-01'
  await page.clock.setFixedTime(new Date('2026-09-08T04:00:00Z'))
  await page.addInitScript(({ key, data }) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data))
  }, { key: database, data })
  const title = 'Renewal follow-up: Amanda Lim'
  const preview = page.getByLabel('Renewal messages')
  const reminders = () => page.evaluate(key => JSON.parse(localStorage.getItem(key)).messages.filter(message => message.kind === 'renewal' && message.clientId === 'c1'), database)
  await page.goto('/#/dashboard')
  await expect(preview.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(0)
  await page.goto('/#/sessions/s1')
  await page.getByRole('button', { name: 'Client Signature', exact: true }).click()
  await drawClientSignature(page)
  await page.getByRole('button', { name: 'Review Completion', exact: true }).click()
  await page.getByRole('dialog', { name: 'Complete this session?' }).getByRole('button', { name: 'Complete Session', exact: true }).click()
  await expect(page.getByLabel('Session status summary')).toContainText('Completed')
  await page.goto('/#/dashboard')
  await expect(preview.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(1)
  expect(await reminders()).toHaveLength(1)
  await preview.getByRole('button', { name: `Open ${title}`, exact: true }).click()
  const dialog = page.getByRole('dialog', { name: title, exact: true })
  await expect(dialog).toContainText('10/12 sessions used · 2 sessions remaining.')
  await dialog.getByRole('button', { name: 'Close message', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  const [readReminder] = await reminders()
  expect(readReminder).toMatchObject({ readBy: { 'u-owner': { readAt: expect.any(String) } }, renewal: { type: 'last_sessions', used: 10, total: 12, remaining: 2 } })
  expect(readReminder.readBy['u-owner'].readAt).toBeTruthy()
  await page.reload()
  await expect(preview.getByRole('button', { name: `Read ${title}`, exact: true })).toBeVisible()
  expect(await reminders()).toEqual([readReminder])
  await selectDemoIdentity(page, 'u-marcus')
  await expect(preview.locator('article')).toHaveCount(1)
  await expect(preview.getByRole('button', { name: `Unread ${title}`, exact: true })).toBeVisible()
  await expect(preview.getByRole('button', { name: 'Open Renewal follow-up: Nadia Koh', exact: true })).toHaveCount(0)
  await page.reload()
  await expect(preview.getByRole('button', { name: `Unread ${title}`, exact: true })).toBeVisible()
  await preview.getByRole('button', { name: `Open ${title}`, exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Mark as Unread', exact: true })).toBeVisible()
  await expect.poll(async () => (await reminders())[0].readBy).toEqual({
    'u-owner': readReminder.readBy['u-owner'], 'u-marcus': { readAt: expect.any(String) },
  })
  await dialog.getByRole('button', { name: 'Mark as Unread', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(preview.getByRole('button', { name: `Unread ${title}`, exact: true })).toBeVisible()
  expect(await reminders()).toEqual([readReminder])
  await selectDemoIdentity(page, 'u-aisha')
  await expect(preview.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(0)
  await selectDemoIdentity(page, 'u-owner')
  await expect(preview.getByRole('button', { name: `Read ${title}`, exact: true })).toBeVisible()
  expect(await reminders()).toEqual([readReminder])
  const saved = await page.evaluate(key => JSON.parse(localStorage.getItem(key)), database)
  expect(saved.clients.find(client => client.id === 'c1').package.used).toBe(10)
  expect(saved.packageCreditTransactions.filter(transaction => transaction.sessionId === 's1')).toHaveLength(1)
})
