import { test, expect, expandSidebarSections, selectDemoIdentity } from './fixtures.js'
import { seed } from '../src/data/seed.js'
import { OWNER_NAV, TRAINER_NAV } from '../src/app/constants.js'
import { withNavigationHistory } from '../src/test/fixtures/navigation.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const back = page => page.getByRole('button', { name: 'Back', exact: true })
const at = (page, route) => expect.poll(() => page.evaluate(() => location.hash)).toBe(`#/${route}`)
async function start(page, route = 'dashboard', historyFixture = false) {
  if (historyFixture) await page.addInitScript(({ key, db }) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(db))
  }, { key: KEY, db: withNavigationHistory(structuredClone(seed)) })
  await page.goto(`/#/${route}`)
  await expect(page.locator('.portal-shell')).toHaveAttribute('aria-busy', 'false')
}
async function nav(page, label) {
  await expandSidebarSections(page, { keepOpen: true })
  await page.getByRole('navigation', { name: 'Portal navigation' }).getByRole('button', { name: label, exact: true }).click()
  await expect(page.locator('.sidebar')).not.toHaveClass(/mobile-open/)
}
async function tab(page, name) {
  const menu = page.locator('details.profile-menu')
  if (await menu.locator('summary').isVisible() && !(await menu.getAttribute('open'))) await menu.locator('summary').click()
  await menu.getByRole('button', { name, exact: true }).click()
}
// Exercise the DOM's touch path, including real event targets and a refresh
// between start/end. OS-reserved Safari edge gestures still need a device check.
async function touch(page, selector, type, delta) {
  await page.locator(selector).evaluate((element, { type, delta }) => {
    const rect = element.getBoundingClientRect()
    const point = { identifier: 7, clientX: rect.left + 12 + delta, clientY: rect.top + 90, target: element }
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { touches: type === 'touchend' ? [] : [point], changedTouches: [point] })
    element.dispatchEvent(event)
  }, { type, delta })
}
async function swipe(page, selector = '.portal-main', during) {
  await page.evaluate(() => scrollTo(0, 0))
  await touch(page, selector, 'touchstart', 0)
  if (during) await during()
  await touch(page, selector, 'touchmove', 155)
  await touch(page, selector, 'touchend', 180)
}

for (const [role, id, items] of [['owner', 'u-owner', OWNER_NAV], ['trainer', 'u-marcus', TRAINER_NAV]]) {
  for (const item of items.filter(item => item.key !== 'dashboard')) {
  test(`M4 ${role} ${item.key} supports chevron, swipe and native Forward`, async ({ page }) => {
    await start(page)
    if (id !== 'u-owner') await selectDemoIdentity(page, id)
    await expect(back(page)).toHaveCount(0)
      await nav(page, item.label); await at(page, item.key)
      await expect(back(page)).toBeVisible()
      const depth = await page.evaluate(() => history.state.fitfinityDepth)
      await nav(page, item.label)
      expect(await page.evaluate(() => history.state.fitfinityDepth)).toBe(depth)
      await back(page).click(); await at(page, 'dashboard')
      await page.goForward(); await at(page, item.key)
      await swipe(page); await at(page, 'dashboard')
      await expect(back(page)).toHaveCount(0)
    await nav(page, 'Messages')
    await page.getByRole('button', { name: 'Home', exact: true }).click()
    await expect(back(page)).toBeVisible()
    await swipe(page); await at(page, 'messages')
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
  })
  }

  test(`M4 ${role} previous-cycle trainer and session history survive reload and both Back controls`, async ({ page }) => {
    await start(page, 'dashboard', true)
    if (id !== 'u-owner') await selectDemoIdentity(page, id)
    await nav(page, 'Remuneration')
    await page.getByRole('button', { name: 'View pay cycle 2020-09', exact: true }).click()
    await page.getByRole('button', { name: 'Show remuneration amounts', exact: true }).click()
    if (role === 'owner') {
      await page.getByRole('button', { name: 'Next', exact: true }).click()
      await page.getByRole('button', { name: 'View remuneration for Marcus Tan', exact: true }).click()
    } else await expect(page.getByRole('table', { name: 'Trainer remuneration' })).toHaveCount(0)
    const breakdownRoute = role === 'owner' ? 'remuneration/2020-09/t1' : 'remuneration/2020-09'
    const parentRoute = role === 'owner' ? 'remuneration/2020-09' : 'remuneration'
    await expect(page.getByRole('button', { name: 'Back to Pay Cycle', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    const first = await page.locator('.remuneration-session').first().getAttribute('data-session-id')
    await page.locator('.remuneration-session').first().getByRole('button').click()
    await at(page, `sessions/${first}`)
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Session Overview' })).toBeVisible()
    await page.goBack(); await at(page, breakdownRoute)
    await expect(page.getByLabel('List pages')).toContainText('Page 2 of 3')
    await expect(page.locator('.remuneration-session').first()).toHaveAttribute('data-session-id', first)
    await expect(page.getByRole('button', { name: 'Hide remuneration amounts', exact: true })).toBeVisible()
    await back(page).click(); await at(page, parentRoute)
    if (role === 'owner') await expect(page.locator('.remuneration-cycle-caption')).toContainText('16 Aug 2020')
    else await expect(page.getByLabel('Pay cycles', { exact: true })).toBeVisible()
    if (role === 'owner') await expect(page.getByLabel('List pages')).toContainText('Page 2 of 2')
    await page.goForward(); await at(page, breakdownRoute)
    await expect(page.getByLabel('List pages')).toContainText('Page 2 of 3')
    await swipe(page); await at(page, parentRoute)
  })
}

test('M4 client history swipe survives a service refresh and restores the list filter', async ({ page }) => {
  await start(page, 'dashboard', true)
  await nav(page, 'Clients')
  await page.getByLabel('Search client', { exact: true }).fill('Amanda')
  await page.getByRole('button', { name: 'View Amanda Lim', exact: true }).click()
  await tab(page, 'Session History')
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await page.getByLabel('Session History', { exact: true }).getByRole('button', { name: 'View', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Session Overview' })).toBeVisible()
  await swipe(page, '.portal-main', async () => {
    await page.evaluate(key => {
      const db = JSON.parse(localStorage.getItem(key)); db.clients.find(item => item.id === 'c1').name = 'Amanda Refreshed'
      localStorage.setItem(key, JSON.stringify(db)); window.dispatchEvent(new Event('focus'))
    }, KEY)
    await expect(page.locator('.portal-main')).toContainText('Amanda Refreshed')
  })
  await at(page, 'clients/c1')
  await expect(page.getByLabel('List pages')).toContainText('Page 2 of 3')
  await swipe(page); await at(page, 'clients')
  await expect(page.getByLabel('Search client', { exact: true })).toHaveValue('Amanda')
})

test('M4 trainer nested client navigation restores the trainer tab and search after a swipe', async ({ page }) => {
  await start(page)
  await nav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan', exact: true }).click()
  await tab(page, 'Assigned Clients')
  await page.getByLabel('Search assigned clients').fill('Amanda')
  await page.getByLabel('Assigned client list').getByRole('button', { name: 'View Amanda Lim', exact: true }).click()
  await at(page, 'clients/c1')
  await swipe(page); await at(page, 'trainers/t1')
  await expect(page.getByLabel('Search assigned clients')).toHaveValue('Amanda')
  await swipe(page); await at(page, 'trainers')
})

test('M4 dashboard renewal popup swipe closes only the popup then returns to the saved calendar', async ({ page }) => {
  await start(page)
  await page.getByRole('button', { name: 'Monthly', exact: true }).click()
  await page.getByRole('button', { name: 'Next calendar period', exact: true }).click()
  const period = await page.locator('.calendar-range option:checked').textContent()
  await page.getByRole('button', { name: 'View All Renewals', exact: true }).click()
  await at(page, 'messages/renewals')
  await page.locator('.message-title-button').first().click()
  await expect(page.locator('.message-detail-modal')).toBeVisible()
  await swipe(page, '.message-detail-modal')
  await expect(page.locator('.message-detail-modal')).toHaveCount(0)
  await at(page, 'messages/renewals')
  await swipe(page); await at(page, 'dashboard')
  await expect(page.locator('.calendar-range option:checked')).toHaveText(period)
  await expect(page.getByRole('button', { name: 'Monthly', exact: true })).toHaveAttribute('aria-pressed', 'true')
})

test('M4 unsaved content swipe keeps the draft on Cancel and traverses only once after confirmation', async ({ page }) => {
  await start(page)
  await nav(page, 'Content Management')
  await page.getByRole('button', { name: 'Add Content', exact: true }).click()
  await page.getByLabel('Content title').fill('Keep my draft')
  await swipe(page)
  const dialog = page.getByRole('dialog', { name: 'Leave this edit?' })
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await at(page, 'content/new')
  await expect(page.getByLabel('Content title')).toHaveValue('Keep my draft')
  await swipe(page)
  await dialog.getByRole('button', { name: 'Leave Without Saving', exact: true }).click()
  await at(page, 'content')
  await back(page).click(); await at(page, 'dashboard')
})

for (const [route, label, add] of [
  ['content', 'Content Management', 'Add Content'], ['packages', 'Packages', 'Add Package'], ['exercises', 'Exercise Library', 'Add Exercise'],
]) {
  test(`M4 ${route} creation Cancel restores its list without a history loop`, async ({ page }) => {
    await start(page)
    await nav(page, label)
    await page.getByRole('button', { name: add, exact: true }).click()
    await at(page, `${route}/new`)
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    if (route === 'packages') await page.getByRole('dialog', { name: 'Leave this edit?' }).getByRole('button', { name: 'Leave Without Saving', exact: true }).click()
    await at(page, route)
    expect(await page.evaluate(() => history.state.fitfinityDepth)).toBe(1)
    await swipe(page); await at(page, 'dashboard')
  })
}

test('M4 password screen returns to the profile through a swipe', async ({ page }) => {
  await start(page)
  await nav(page, 'Profile')
  await page.getByRole('button', { name: 'Open profile menu', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Change Password', exact: true }).click()
  await at(page, 'change-password')
  await swipe(page); await at(page, 'owner-profile')
  await back(page).click(); await at(page, 'dashboard')
})

test('M4 calendar popup swipe closes the day and session Back restores the calendar', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-02T04:00:00Z'))
  await start(page)
  const day = page.getByRole('button', { name: 'Show sessions for 2026-09-02', exact: true })
  await day.click()
  await expect(page.getByRole('dialog', { name: 'Calendar sessions' })).toBeVisible()
  await swipe(page, '.calendar-day-dialog'); await at(page, 'dashboard')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await day.click()
  await page.getByRole('dialog', { name: 'Calendar sessions' }).locator('.calendar-event').first().click()
  await expect(page.getByRole('heading', { name: 'Session Overview' })).toBeVisible()
  await swipe(page); await at(page, 'dashboard')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(day).toBeVisible()
})
