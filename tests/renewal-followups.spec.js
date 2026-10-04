import { test, expect, waitForPortal, selectDemoIdentity } from './fixtures.js'
import { seed } from '../src/data/seed.js'
import { appendRenewalMessage } from '../src/app/renewals.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const title = 'Renewal follow-up: Amanda Lim'
const read = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
const activate = (locator, isMobile) => isMobile ? locator.tap() : locator.click()
async function start(page, renewed = false) {
  const data = structuredClone(seed), client = data.clients.find(item => item.id === 'c1')
  client.package.used = 10; client.status = 'active'; client.package.status = 'active'
  data.messages = []; data.renewalMessageVersion = 1
  appendRenewalMessage(data, client, '2026-09-09T04:00:00Z')
  if (renewed) client.additionalPackages = [{ ...client.package, id: 'previously-bought', startDate: '2027-01-04', endDate: '2027-04-03', used: 0 }]
  await page.clock.setFixedTime(new Date('2026-09-09T04:00:00Z'))
  await page.addInitScript(({ key, data }) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, { key: KEY, data })
  await page.goto('/#/dashboard'); await waitForPortal(page)
}
async function packageTab(page, isMobile) {
  const menu = page.locator('.profile-menu'), summary = menu.locator('summary')
  if (await summary.isVisible()) await activate(summary, isMobile)
  await activate(menu.getByRole('button', { name: 'Package', exact: true }), isMobile)
}

test('renewal follow-ups: Add Package clears the list only after confirmation and persists after reload', async ({ page, isMobile }) => {
  await start(page)
  await expect(page.locator('.renewal-count')).toHaveText('1')
  await page.goto('/#/clients/c1'); await waitForPortal(page); await packageTab(page, isMobile)
  const before = await read(page)
  await activate(page.getByRole('button', { name: 'Add Package', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Add Package', exact: true })
  await dialog.getByLabel('Start date', { exact: true }).fill('2027-01-04')
  for (const name of ['Continue to Client Availability', 'Continue to Trainer Matching', 'Continue to Review & Confirm']) {
    await activate(dialog.getByRole('button', { name, exact: true }), isMobile)
  }
  await activate(dialog.getByRole('button', { name: 'Add Package', exact: true }), isMobile)
  const confirmation = page.getByRole('dialog', { name: 'Add package for Amanda Lim?', exact: true })
  await activate(confirmation.getByRole('button', { name: 'Cancel', exact: true }), isMobile)
  expect((await read(page)).clients).toEqual(before.clients)
  expect((await read(page)).messages).toEqual(before.messages)
  await activate(dialog.getByRole('button', { name: 'Add Package', exact: true }), isMobile)
  await activate(confirmation.getByRole('button', { name: 'Add Package', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  await page.goto('/#/dashboard'); await waitForPortal(page)
  await expect(page.locator('.renewal-count')).toHaveText('0')
  await expect(page.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(0)
  await page.reload(); await waitForPortal(page)
  await expect(page.locator('.renewal-count')).toHaveText('0')
  const after = await read(page)
  expect(after.clients.find(item => item.id === 'c1').additionalPackages).toHaveLength(1)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  expect(after.messages.find(item => item.kind === 'renewal')).toEqual(before.messages[0])
  await page.goto('/#/messages'); await waitForPortal(page)
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${title}`, exact: true }) })
  await expect(row).toContainText('Renewed')
})

for (const role of ['owner', 'trainer']) test(`renewal follow-ups: ${role} removes from the popup without deleting the client`, async ({ page, isMobile }) => {
  await start(page)
  if (role === 'trainer') { await selectDemoIdentity(page, 'u-marcus'); await waitForPortal(page) }
  const before = await read(page)
  await activate(page.getByRole('button', { name: `Open ${title}`, exact: true }), isMobile)
  const popup = page.getByRole('dialog', { name: title, exact: true })
  const remove = popup.getByRole('button', { name: `Remove ${title} from renewals`, exact: true })
  await activate(remove, isMobile)
  const confirm = page.getByRole('dialog', { name: 'Remove renewal follow-up?', exact: true })
  await activate(confirm.getByRole('button', { name: 'Cancel', exact: true }), isMobile)
  await expect(popup).toBeVisible(); await expect(page.locator('.renewal-count')).toHaveText('1')
  expect((await read(page)).messages[0].renewalDismissal).toBeUndefined()
  await activate(remove, isMobile)
  await activate(confirm.getByRole('button', { name: 'Remove', exact: true }), isMobile)
  await expect(popup).toHaveCount(0)
  await expect(page.locator('.renewal-count')).toHaveText('0')
  await expect(page).toHaveURL(/#\/dashboard$/)
  await page.reload(); await waitForPortal(page)
  await expect(page.locator('.renewal-count')).toHaveText('0')
  const after = await read(page)
  expect(after.clients).toEqual(before.clients)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  expect(after.messages[0].renewalDismissal.by.id).toBe(role === 'owner' ? 'u-owner' : 'u-marcus')
  if (role === 'trainer') { await selectDemoIdentity(page, 'u-owner'); await waitForPortal(page); await expect(page.locator('.renewal-count')).toHaveText('0') }
  await activate(page.getByRole('button', { name: 'View All Renewals', exact: true }), isMobile)
  await expect(page.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
})

test('renewal follow-ups: previously purchased packages clear reminders until Deactivate Package', async ({ page, isMobile }) => {
  await start(page, true)
  await expect(page.locator('.renewal-count')).toHaveText('0')
  await page.goto('/#/messages/renewals'); await waitForPortal(page)
  await expect(page.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(0)
  const data = await read(page)
  expect(data.messages.filter(item => item.kind === 'renewal')).toHaveLength(1)
  expect(data.clients.find(item => item.id === 'c1').additionalPackages[0].id).toBe('previously-bought')
  await page.goto('/#/clients/c1'); await waitForPortal(page); await packageTab(page, isMobile)
  await activate(page.getByLabel('Additional packages', { exact: true }).getByRole('button', { name: 'Deactivate Package', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Deactivate Package?', exact: true })
  await expect(dialog.getByRole('checkbox')).not.toBeChecked()
  await activate(dialog.getByRole('button', { name: 'Deactivate Package', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  await page.goto('/#/dashboard'); await waitForPortal(page)
  await expect(page.locator('.renewal-count')).toHaveText('1')
  await page.reload(); await waitForPortal(page)
  await expect(page.locator('.renewal-count')).toHaveText('1')
  expect((await read(page)).messages.filter(item => item.kind === 'renewal')).toHaveLength(1)
})
