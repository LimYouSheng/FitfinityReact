import { test, expect, waitForPortal, selectDemoIdentity } from './fixtures.js'
import { seed } from '../src/data/seed.js'
import { appendRenewalMessage } from '../src/app/renewals.js'
import { addDays } from '../src/app/clientOnboarding.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const title = 'Renewal follow-up: Amanda Lim'
const read = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
const activate = (locator, isMobile, options) => isMobile ? locator.tap(options) : locator.click(options)
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

async function startPackageReactivation(page, isMobile, { deleted = false, conflict = false } = {}) {
  const data = structuredClone(seed), client = data.clients[0], other = data.clients[1]
  data.messages = []; data.packageCreditTransactions = []; client.package.used = 0
  data.sessions = [{ id: 'retained-package-session', clientId: client.id, packageId: client.package.id, trainerId: 't1',
    date: '2026-09-10', from: '10:00', to: '11:00', status: 'not_planned', sessionNumber: 1, packageTotal: 12, exercisePlan: [] }]
  await page.clock.setFixedTime(new Date('2026-09-09T04:00:00Z'))
  await page.addInitScript(({ key, data }) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, { key: KEY, data })
  await page.goto('/#/clients/c1'); await waitForPortal(page); await packageTab(page, isMobile)
  await activate(page.getByRole('button', { name: 'Deactivate Package', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Deactivate Package?', exact: true })
  await expect(dialog).not.toContainText('cannot be undone')
  if (deleted) await activate(dialog.getByRole('checkbox'), isMobile)
  await activate(dialog.getByRole('button', { name: 'Deactivate Package', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  if (conflict) {
    await page.evaluate(({ key, other }) => {
      const db = JSON.parse(localStorage.getItem(key))
      db.sessions.push({ ...db.sessions[0], id: 'new-package-conflict', clientId: other.id, packageId: other.package.id })
      localStorage.setItem(key, JSON.stringify(db))
    }, { key: KEY, other })
    await page.reload(); await waitForPortal(page); await packageTab(page, isMobile)
  }
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
  const addedTitle = 'Package added: Amanda Lim'
  const added = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${addedTitle}`, exact: true }) })
  await expect(added).toBeVisible()
  await expect(added.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  await activate(added.getByRole('button', { name: `Open ${addedTitle}`, exact: true }), isMobile)
  const details = page.getByRole('dialog', { name: addedTitle, exact: true })
  await expect(details).toBeVisible()
  await expect(details.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  expect((await read(page)).sessionMutations?.some(item => item.operation === 'client.renewPackage') ?? false).toBe(false)
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
  await expect(dialog).not.toContainText('cannot be undone')
  await activate(dialog.getByRole('button', { name: 'Deactivate Package', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  await page.goto('/#/dashboard'); await waitForPortal(page)
  await expect(page.locator('.renewal-count')).toHaveText('1')
  await page.reload(); await waitForPortal(page)
  await expect(page.locator('.renewal-count')).toHaveText('1')
  expect((await read(page)).messages.filter(item => item.kind === 'renewal')).toHaveLength(1)
  await page.goto('/#/messages'); await waitForPortal(page)
  const deactivatedTitle = 'Package deactivated: Amanda Lim'
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${deactivatedTitle}`, exact: true }) })
  await expect(row).toBeVisible()
  await expect(row.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  await activate(row.getByRole('button', { name: `Open ${deactivatedTitle}`, exact: true }), isMobile)
  const details = page.getByRole('dialog', { name: deactivatedTitle, exact: true })
  await expect(details).toBeVisible()
  await expect(details.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  expect((await read(page)).sessionMutations?.some(item => item.operation === 'client.deactivatePackage') ?? false).toBe(false)
})

test('message rows: renewal Remove section whitespace opens its message without removing the follow-up', async ({ page, isMobile }) => {
  await start(page)
  await page.goto('/#/messages/renewals'); await waitForPortal(page)
  const before = await read(page)
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${title}`, exact: true }) })
  const action = row.locator('.renewal-remove-action')
  await action.scrollIntoViewIfNeeded()
  const point = await action.evaluate(element => {
    const rect = element.getBoundingClientRect(), x = rect.width - 3, y = rect.height / 2
    return { x, y, hitsSpace: document.elementFromPoint(rect.left + x, rect.top + y) === element }
  })
  expect(point.hitsSpace).toBe(true)
  await activate(action, isMobile, { position: { x: point.x, y: point.y } })
  const dialog = page.getByRole('dialog', { name: title, exact: true })
  await expect(dialog).toBeVisible()
  await expect(page.getByRole('dialog', { name: 'Remove renewal follow-up?', exact: true })).toHaveCount(0)
  const after = await read(page)
  expect(after.clients).toEqual(before.clients)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.messages[0].renewalDismissal).toBeUndefined()
  expect(after.messages[0].readBy['u-owner']).toBeTruthy()
  await activate(dialog.getByRole('button', { name: 'Close message', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0)
  await activate(row.getByRole('button', { name: `Remove ${title} from renewals`, exact: true }), isMobile)
  const confirm = page.getByRole('dialog', { name: 'Remove renewal follow-up?', exact: true })
  await expect(confirm).toBeVisible(); await expect(dialog).toHaveCount(0)
  await activate(confirm.getByRole('button', { name: 'Cancel', exact: true }), isMobile)
  expect((await read(page)).messages[0].renewalDismissal).toBeUndefined()
})

for (const deleted of [false, true]) test(`package reactivation: ${deleted ? 'deleted sessions stay deleted' : 'retained sessions return'} with credits and expiry preserved`, async ({ page, isMobile }) => {
  await startPackageReactivation(page, isMobile, { deleted })
  const before = await read(page)
  const button = page.getByRole('button', { name: 'Reactivate Package', exact: true })
  await activate(button, isMobile)
  const dialog = page.getByRole('dialog', { name: 'Reactivate Package?', exact: true })
  await expect(dialog).toContainText('Used credits and the expiry date stay the same')
  await activate(dialog.getByRole('button', { name: 'Cancel', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); expect((await read(page)).clients).toEqual(before.clients)
  await activate(button, isMobile)
  await activate(dialog.getByRole('button', { name: 'Reactivate Package', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  await page.reload(); await waitForPortal(page); await packageTab(page, isMobile)
  const after = await read(page), previous = before.clients[0].package, purchased = after.clients[0].package
  expect(purchased).toMatchObject({ status: 'active', used: previous.used, validityDays: previous.validityDays, startDate: previous.startDate, endDate: previous.endDate })
  expect(after.sessions).toEqual(before.sessions)
  expect(after.sessions).toHaveLength(deleted ? 0 : 1)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  expect(purchased.sessionDeletionHistory).toEqual(previous.sessionDeletionHistory)
  await expect(page.getByRole('button', { name: 'Reactivate Package', exact: true })).toHaveCount(0)
  await page.goto('/#/messages'); await waitForPortal(page)
  const title = 'Package reactivated: Amanda Lim'
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${title}`, exact: true }) })
  await expect(row.locator('.message-undo-action')).toHaveCount(0)
  await activate(row.getByRole('button', { name: `Open ${title}`, exact: true }), isMobile)
  await expect(page.getByRole('dialog', { name: title, exact: true }).locator('.message-undo-action')).toHaveCount(0)
})

test('package reactivation: resolve a newly occupied booking before restoring the selected purchase', async ({ page, isMobile }) => {
  await startPackageReactivation(page, isMobile, { conflict: true })
  const before = await read(page)
  await activate(page.getByRole('button', { name: 'Reactivate Package', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Reactivate Package?', exact: true })
  const confirm = dialog.getByRole('button', { name: 'Reactivate Package', exact: true })
  await expect(confirm).toBeDisabled()
  await expect(dialog).toContainText('Conflicts with another session')
  const date = dialog.getByRole('textbox', { name: /Session 1/ })
  await activate(date, isMobile)
  const calendar = page.getByRole('dialog', { name: /Session 1.*calendar/ })
  await expect(calendar).toBeVisible()
  // Locale data differs across engines (Sep/Sept); resolve the exact label in this browser.
  const replacementDate = '2026-09-11'
  const label = await page.evaluate(value => new Intl.DateTimeFormat('en-SG', {
    day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`)), replacementDate)
  await activate(calendar.getByRole('button', { name: label, exact: true }), isMobile)
  await expect(calendar).toHaveCount(0)
  await expect(date).toHaveValue(replacementDate)
  await expect(confirm).toBeEnabled()
  expect((await read(page)).sessions).toEqual(before.sessions)
  await activate(confirm, isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  await page.reload(); await waitForPortal(page)
  const after = await read(page)
  expect(after.clients[0].package.status).toBe('active')
  expect(after.sessions.find(item => item.id === 'retained-package-session')).toMatchObject({ date: '2026-09-11', from: '10:00', to: '11:00', trainerId: 't1', packageId: before.clients[0].package.id })
  expect(after.sessions.find(item => item.id === 'new-package-conflict')).toEqual(before.sessions.find(item => item.id === 'new-package-conflict'))
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
})

for (const [total, days] of [[12, 90], [24, 180], [36, 270]]) test(`package validity: ${total} sessions have ${days} days after Add Package and reload`, async ({ page, isMobile }) => {
  await start(page)
  await page.goto('/#/clients/c1'); await waitForPortal(page); await packageTab(page, isMobile)
  await activate(page.getByRole('button', { name: 'Add Package', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Add Package', exact: true })
  const select = dialog.getByLabel('PT Package', { exact: true })
  await expect(select.locator(`option[value="package-${total}"]`)).toContainText(`${days} days`)
  await select.selectOption(`package-${total}`)
  await dialog.getByLabel('Start date', { exact: true }).fill('2027-01-04')
  for (const name of ['Continue to Client Availability', 'Continue to Trainer Matching', 'Continue to Review & Confirm']) {
    await activate(dialog.getByRole('button', { name, exact: true }), isMobile)
  }
  await activate(dialog.getByRole('button', { name: 'Add Package', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Add package for Amanda Lim?', exact: true }).getByRole('button', { name: 'Add Package', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
  await page.reload(); await waitForPortal(page)
  const stored = await read(page), purchased = stored.clients[0].additionalPackages[0]
  expect(purchased).toMatchObject({ total, validityDays: days, startDate: '2027-01-04', endDate: addDays('2027-01-04', days - 1) })
  expect(stored.sessions.filter(item => item.packageId === purchased.id)).toHaveLength(total)
})
