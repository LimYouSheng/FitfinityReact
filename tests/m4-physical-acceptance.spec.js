import { test, expect, drawClientSignature, selectDemoIdentity } from './fixtures.js'
import { seed } from '../src/data/seed.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const back = page => page.getByRole('button', { name: 'Back', exact: true }).click()
async function tab(page, name) {
  const menu = page.locator('.profile-menu')
  const summary = menu.locator('summary')
  if (await summary.isVisible()) await summary.click()
  await menu.getByRole('button', { name, exact: true }).click()
}
async function fixture(page, customize = () => {}) {
  const data = structuredClone(seed)
  const source = data.sessions.find(item => item.id === 's0')
  data.sessions.push(...Array.from({ length: 22 }, (_, index) => ({ ...source, id: `physical-history-${index}`, date: '2026-08-01', clientId: 'c1', status: 'completed', sessionNumber: index + 1 })))
  data.contentEntries = [{ id: 'physical-content', title: 'Studio hours', key: 'studio-hours', body: 'Opening hours', status: 'ready', version: 1 }]
  customize(data)
  await page.clock.setFixedTime(new Date('2026-09-02T04:00:00Z'))
  // Seed the complete snapshot before the app loads. Hash navigation keeps its in-memory database.
  await page.addInitScript(({ key, data }) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data))
  }, { key: KEY, data })
  await page.goto('/#/dashboard')
  await expect(page.getByRole('heading', { name: 'Calendar', exact: true })).toBeVisible()
}

test('M4 Back restores the client history tab, page and scroll position and survives reload', async ({ page }) => {
  await fixture(page)
  await page.goto('/#/clients/c1')
  await tab(page, 'Session History')
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  const list = page.getByLabel('Session History', { exact: true })
  const first = await list.locator('article').first().textContent()
  const view = list.getByRole('button', { name: 'View', exact: true }).last()
  await view.scrollIntoViewIfNeeded()
  const scroll = await page.evaluate(() => window.scrollY)
  await view.click()
  await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
  await back(page)
  await expect(page.getByRole('heading', { name: 'Session History', exact: true })).toBeVisible()
  await expect(page.getByLabel('List pages')).toContainText('Page 2')
  await expect(list.locator('article').first()).toHaveText(first)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(Math.max(0, scroll - 50))
  await page.goForward()
  await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
  await page.goBack()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Session History', exact: true })).toBeVisible()
  await expect(page.getByLabel('List pages')).toContainText('Page 2')
})

test('M4 nested trainer to client navigation restores Assigned Clients and its filters', async ({ page }) => {
  await fixture(page)
  await page.goto('/#/trainers/t1')
  await tab(page, 'Assigned Clients')
  await page.getByLabel('Search assigned clients').fill('Amanda')
  await page.getByLabel('Assigned client list').getByRole('button', { name: 'View', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Amanda Lim', exact: true })).toBeVisible()
  await tab(page, 'Session History')
  await page.getByLabel('Session History', { exact: true }).getByRole('button', { name: 'View', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
  await back(page)
  await expect(page.getByRole('heading', { name: 'Session History', exact: true })).toBeVisible()
  await back(page)
  await expect(page.getByRole('heading', { name: 'Assigned Clients', exact: true })).toBeVisible()
  await expect(page.getByLabel('Search assigned clients')).toHaveValue('Amanda')
})

for (const [route, search, query, open, ready] of [
  ['clients', 'Search client', 'Amanda', 'View Amanda Lim', 'Amanda Lim'],
  ['trainers', 'Search trainer', 'Marcus', 'View Marcus Tan', 'Marcus Tan'],
  ['sessions', 'Search sessions', 'Amanda', /View session/, 'Session Overview'],
  ['exercises', 'Search exercises', 'Squat', /View exercise/, 'Exercise details'],
  ['content', 'Search content', 'Studio', 'Edit Studio hours', 'Edit Content'],
]) {
  test(`M4 ${route} retains its search after detail Back`, async ({ page }) => {
    await fixture(page)
    await page.goto(`/#/${route}`)
    await page.getByLabel(search, { exact: true }).fill(query)
    await page.getByRole('button', { name: open, exact: typeof open === 'string' }).first().click()
    if (route === 'exercises') await expect(page.locator('.library-summary')).toBeVisible()
    else if (route === 'content') {
      await expect(page.getByLabel('Content title')).toHaveValue('Studio hours')
      await page.getByLabel('Content body').fill('Unsaved opening hours')
    }
    else await expect(page.getByRole('heading', { name: ready, exact: true })).toBeVisible()
    await back(page)
    if (route === 'content') await page.getByRole('dialog', { name: 'Leave this edit?' }).getByRole('button', { name: 'Leave Without Saving', exact: true }).click()
    await expect(page.getByLabel(search, { exact: true })).toHaveValue(query)
  })
}

test('M4 signature and WhatsApp stay blocked before the gym date and unlock on that date for both roles', async ({ page }) => {
  await fixture(page)
  for (const user of ['u-owner', 'u-marcus']) {
    await page.goto('/#/dashboard')
    await selectDemoIdentity(page, user)
    await page.clock.setFixedTime(new Date('2026-09-01T15:59:00Z'))
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await page.goto('/#/sessions/s1')
    await expect(page.getByRole('button', { name: 'Client Signature', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Export Summary', exact: true })).toBeDisabled()
    await page.clock.setFixedTime(new Date('2026-09-01T16:00:00Z'))
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(page.getByRole('button', { name: 'Client Signature', exact: true })).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Export Summary', exact: true })).toBeEnabled()
  }
})

test('M4 signed completion updates the progress chart from saved plan loads and survives refresh', async ({ page }) => {
  await fixture(page, data => {
    const session = data.sessions.find(item => item.id === 's1')
    session.exercisePlan = [{ id: 'physical-row', name: 'Physical Test Row', weight: '27.5 kg', reps: '8', rounds: '3' }]
    delete session.exerciseResults
  })
  await page.goto('/#/sessions/s1')
  await page.getByRole('button', { name: 'Client Signature', exact: true }).click()
  await drawClientSignature(page)
  await page.getByRole('button', { name: 'Review Completion', exact: true }).click()
  await page.getByRole('dialog', { name: 'Complete this session?' }).getByRole('button', { name: 'Complete Session', exact: true }).click()
  await expect(page.getByLabel('Session status summary')).toContainText('Completed')
  await page.getByRole('button', { name: 'View Client', exact: true }).click()
  await tab(page, 'Progress')
  await page.getByLabel('Strength progress exercise').selectOption({ label: 'Physical Test Row' })
  await expect(page.locator('.strength-chart-summary')).toContainText('27.5')
  await page.reload()
  await expect(page.getByLabel('Strength progress exercise')).toHaveValue('progress-physical-row')
  await expect(page.locator('.strength-chart-summary')).toContainText('27.5')
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).packageCreditTransactions.filter(item => item.sessionId === 's1').length, KEY)).toBe(1)
})

test('M4 package setup accepts a custom integer and blocks fractional and out-of-range input', async ({ page }) => {
  await fixture(page)
  await page.goto('/#/packages/new')
  await page.getByLabel('Package name').fill('Physical custom package')
  const count = page.getByLabel('Package session count')
  for (const invalid of ['0', '366', '1.5']) {
    await count.fill(invalid)
    await page.getByRole('button', { name: 'Create Package', exact: true }).click()
    await expect(count).toHaveValue(invalid)
    await expect(page.getByText('Enter a whole number from 1 to 365.')).toBeVisible()
  }
  await count.fill('18')
  await page.getByRole('button', { name: 'Create Package', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Create Package?' })
  await expect(dialog).toContainText('18 sessions · 135 days')
  await dialog.getByRole('button', { name: 'Create Package', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Package details' })).toBeVisible()
  await page.reload()
  await expect(page.locator('.package-details')).toContainText('18')
  await expect(page.locator('.package-details')).toContainText('135 days')
})


test('M4 owner sees timestamped export and WhatsApp history in Progress after reload', async ({ page, context }) => {
  await fixture(page)
  await page.goto('/#/clients/c1')
  await expect(page.getByText('Renewal status', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Renewal History', { exact: true })).toHaveCount(0)
  await tab(page, 'Progress')
  await page.getByRole('button', { name: 'View Export/WhatsApp History', exact: true }).click()
  const history = page.getByLabel('Export/WhatsApp history', { exact: true })
  await expect(history).toContainText('No export or WhatsApp history yet.')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export Progress Report', exact: true }).click()
  expect((await download).suggestedFilename()).toBe('amanda-lim-progress-report.csv')
  await expect(history.locator('article')).toHaveCount(1)
  await expect(history.locator('time')).toHaveAttribute('datetime', '2026-09-02T04:00:00.000Z')
  await expect(history).toContainText('12:00')
  await context.route('https://wa.me/**', route => route.fulfill({ contentType: 'text/html', body: '<p>WhatsApp test handoff</p>' }))
  await expect(page.getByRole('link', { name: 'Share Progress Report via WhatsApp' })).toHaveAttribute('aria-disabled', 'false')
  const opened = page.waitForEvent('popup')
  await page.getByRole('link', { name: 'Share Progress Report via WhatsApp' }).click()
  const popup = await opened
  await popup.waitForURL(/^https:\/\/wa\.me\/6591234567\?text=/)
  await popup.close()
  await expect(history.locator('article')).toHaveCount(2)
  await expect(history).toContainText('CSV export')
  await expect(history).toContainText('WhatsApp opened')
  await expect(history).toContainText('Chau')
  await page.reload()
  await expect(history.locator('article')).toHaveCount(2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('M4 trainer report activity is logged for the owner without exposing history to trainers', async ({ page }) => {
  await fixture(page)
  await selectDemoIdentity(page, 'u-marcus')
  await page.goto('/#/clients/c1')
  await tab(page, 'Progress')
  await expect(page.getByRole('button', { name: 'View Export/WhatsApp History', exact: true })).toHaveCount(0)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export Progress Report', exact: true }).click()
  await download
  await expect(page.getByRole('button', { name: 'Export Progress Report', exact: true })).toBeEnabled()
  await selectDemoIdentity(page, 'u-owner')
  await page.goto('/#/clients/c1')
  await tab(page, 'Progress')
  await page.getByRole('button', { name: 'View Export/WhatsApp History', exact: true }).click()
  await expect(page.getByLabel('Export/WhatsApp history', { exact: true })).toContainText('Marcus Tan')
  await page.goto('/#/clients/c2')
  await tab(page, 'Progress')
  await page.getByRole('button', { name: 'View Export/WhatsApp History', exact: true }).click()
  await expect(page.getByLabel('Export/WhatsApp history', { exact: true })).toContainText('No export or WhatsApp history yet.')
})

test('M4 blocked WhatsApp is not logged and retrying failed export history does not download again', async ({ page }) => {
  await fixture(page)
  await page.goto('/#/clients/c1')
  await tab(page, 'Progress')
  await page.evaluate(() => { window.open = () => null })
  await page.getByRole('link', { name: 'Share Progress Report via WhatsApp' }).click()
  await expect(page.getByRole('alert')).toContainText('WhatsApp could not be opened.')
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).progressReportEvents ?? [], KEY)).toEqual([])
  await page.evaluate(key => {
    const save = Storage.prototype.setItem
    Storage.prototype.setItem = function (name, value) {
      if (name === key && JSON.parse(value).progressReportEvents?.length) {
        Storage.prototype.setItem = save
        throw new Error('Simulated history write failure')
      }
      return save.call(this, name, value)
    }
  }, KEY)
  let downloads = 0
  page.on('download', () => { downloads += 1 })
  await page.getByRole('button', { name: 'Export Progress Report', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('CSV export started, but its history could not be saved.')
  await page.getByRole('button', { name: 'Retry History Save', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button', { name: 'View Export/WhatsApp History', exact: true }).click()
  await expect(page.getByLabel('Export/WhatsApp history').locator('article')).toHaveCount(1)
  expect(downloads).toBe(1)
})
