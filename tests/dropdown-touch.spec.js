import { test, expect, waitForPortal, mockPhysicalOrientation, fillClientRequiredFields } from './fixtures.js'
import { seed } from '../src/data/seed.js'
import { DEFAULT_EXERCISES } from '../src/data/mockExercises.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const activate = (control, hasTouch) => hasTouch ? control.tap() : control.click()

async function start(page, route) {
  await page.goto(`/#/${route}`)
  await waitForPortal(page)
}

async function cancelledPress(control, closed) {
  await control.scrollIntoViewIfNeeded()
  const box = await control.boundingBox()
  const point = { pointerId: 77, pointerType: 'touch', isPrimary: true, button: 0,
    clientX: box.x + box.width / 2, clientY: box.y + box.height / 2 }
  await control.dispatchEvent('pointerdown', point)
  await closed()
  await control.dispatchEvent('pointermove', { ...point, clientY: point.clientY - 100 })
  await control.dispatchEvent('pointercancel', point)
  await closed()
}

async function selectValue(page, control, hasTouch, requested, beforeReopen = async () => {}) {
  await expect(control).toBeEnabled()
  const options = await control.locator('option').evaluateAll(items => items.filter(item => !item.disabled && !item.hidden)
    .map(item => ({ value: item.value, text: item.text })))
  const current = await control.inputValue()
  const target = requested === undefined ? options.find(option => option.value !== current) ?? options[0]
    : options.find(option => option.value === requested)
  expect(target, 'A real selectable option must exist').toBeTruthy()
  await cancelledPress(control, () => expect(control).toHaveAttribute('aria-expanded', 'false'))
  await activate(control, hasTouch)
  await expect(control).toHaveAttribute('aria-expanded', 'true')
  const id = await control.getAttribute('aria-controls')
  const menu = page.locator(`[id="${id}"]`)
  await expect(menu).toBeVisible()
  await activate(menu.getByRole('option', { name: target.text, exact: true }), hasTouch)
  await expect(control).toHaveValue(target.value)
  await expect(control).toHaveAttribute('aria-expanded', 'false')
  await beforeReopen()
  await activate(control, hasTouch)
  await expect(page.locator(`[id="${await control.getAttribute('aria-controls')}"]`)).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(control).toHaveAttribute('aria-expanded', 'false')
}

async function dateValue(page, label, hasTouch) {
  const input = page.getByLabel(label, { exact: true })
  await input.fill('1990-01-02')
  await cancelledPress(input, () => expect(input).toHaveAttribute('aria-expanded', 'false'))
  await activate(input, hasTouch)
  const calendar = page.getByRole('dialog', { name: `${label} calendar`, exact: true })
  await expect(calendar).toBeVisible()
  await selectValue(page, calendar.getByRole('combobox', { name: 'Calendar picker year', exact: true }), hasTouch, '1991')
  await expect(calendar).toBeVisible()
  await selectValue(page, calendar.getByRole('combobox', { name: 'Calendar picker month', exact: true }), hasTouch, '3')
  await activate(calendar.locator('.date-calendar-grid button').filter({ hasText: /^3$/ }), hasTouch)
  await expect(input).toHaveValue('1991-03-03')
  await expect(calendar).toHaveCount(0)
  await activate(input, hasTouch)
  await expect(calendar).toBeVisible()
  await activate(calendar.getByRole('button', { name: 'Close', exact: true }), hasTouch)
  await expect(calendar).toHaveCount(0)
}

test.beforeEach(async ({ page }) => {
  await mockPhysicalOrientation(page)
  // Observe, never cancel or synthesize, the real event sequence used by tap().
  await page.addInitScript(() => {
    window.__dropdownEvents = []
    for (const type of ['pointerdown', 'pointerup', 'pointercancel', 'mousedown', 'click']) {
      document.addEventListener(type, event => {
        const target = event.target
        if (!(target instanceof Element) || !target.closest('.select-field,.suggestion-field,.date-field,.field-popover,.search-suggestions,.exercise-name-picker')) return
        queueMicrotask(() => window.__dropdownEvents.push({ type, tag: target.tagName,
          label: target.getAttribute('aria-label') ?? target.textContent?.slice(0, 80),
          pointerType: event.pointerType, trusted: event.isTrusted, prevented: event.defaultPrevented }))
      }, true)
    }
  })
})

test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status === testInfo.expectedStatus || page.isClosed()) return
  await testInfo.attach('dropdown-event-sequence', {
    body: JSON.stringify(await page.evaluate(() => window.__dropdownEvents ?? []), null, 2), contentType: 'application/json',
  })
})

const filters = [
  ['clients', ['Filter clients by status', 'Filter clients by type', 'Filter clients by trainer']],
  ['trainers', ['Filter trainers by status', 'Filter trainers by type', 'Filter trainers by gender']],
  ['sessions', ['Filter sessions by period', 'Filter sessions by status']],
  ['content', ['Filter content status']],
  ['exercises', ['Exercise category', 'Exercise status']],
]
for (const [route, labels] of filters) {
  test(`dropdown touch: ${route} filters select and reopen after a cancelled press`, async ({ page, hasTouch }) => {
    await start(page, route)
    for (const label of labels) await selectValue(page, page.getByRole('combobox', { name: label, exact: true }), hasTouch)
    if (route === 'sessions') {
      await dateValue(page, 'Sessions from date', hasTouch)
      await dateValue(page, 'Sessions to date', hasTouch)
    }
    if (route === 'content') {
      await activate(page.getByRole('button', { name: 'Add Content', exact: true }), hasTouch)
      await selectValue(page, page.getByRole('combobox', { name: 'Content status', exact: true }), hasTouch)
    }
    if (route === 'exercises') {
      await activate(page.getByRole('button', { name: 'Add Exercise', exact: true }), hasTouch)
      await selectValue(page, page.getByRole('combobox', { name: 'Category', exact: true }), hasTouch)
    }
  })
}

test('dropdown touch: client personal and nested date menus', async ({ page, hasTouch }) => {
  await start(page, 'clients/new')
  await selectValue(page, page.getByRole('combobox', { name: 'Client type', exact: true }), hasTouch, 'Couple')
  await expect(page.getByLabel('Client 1 gender', { exact: true })).toBeVisible()
  await selectValue(page, page.getByRole('combobox', { name: 'Client type', exact: true }), hasTouch, 'Individual')
  await page.getByLabel('Client name', { exact: true }).fill('Local Dropdown Client')
  for (const [label, value] of [['Client phone country code', '+65'], ['Client gender', 'Female'],
    ['Client emergency contact relationship', undefined], ['Client emergency contact country code', '+65']]) {
    await selectValue(page, page.getByRole('combobox', { name: label, exact: true }), hasTouch, value)
  }
  await dateValue(page, 'Client birthday', hasTouch)
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).clients.some(client => client.name === 'Local Dropdown Client'), KEY)).toBe(false)
})

test('dropdown touch: client package and preference menus', async ({ page, hasTouch }) => {
  await start(page, 'clients/new')
  await page.getByLabel('Client name', { exact: true }).fill('Local Dropdown Client')
  await fillClientRequiredFields(page)
  await activate(page.getByRole('button', { name: 'Continue to Health & Assessments', exact: true }), hasTouch)
  await expect(page.getByRole('heading', { name: 'Health & Assessments', exact: true })).toBeVisible()
  await activate(page.getByRole('button', { name: 'Continue to Package & Preferences', exact: true }), hasTouch)
  await expect(page.getByRole('heading', { name: 'Package & Preferences', exact: true })).toBeVisible()
  for (const label of ['PT Package', 'Weekly frequency', 'Trainer preference']) {
    await selectValue(page, page.getByRole('combobox', { name: label, exact: true }), hasTouch)
  }
  const date = page.getByLabel('Start date', { exact: true })
  await activate(date, hasTouch)
  const calendar = page.getByRole('dialog', { name: 'Start date calendar', exact: true })
  await activate(calendar.locator('.date-calendar-grid button:not(:disabled)').first(), hasTouch)
  await expect(date).toHaveValue(/^\d{4}-\d{2}-\d{2}$/)
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).clients.some(client => client.name === 'Local Dropdown Client'), KEY)).toBe(false)
})

test('dropdown touch: trainer fields and editable suggestions select on release', async ({ page, hasTouch }) => {
  await start(page, 'trainers/new')
  for (const label of ['Trainer phone country code', 'Trainer gender', 'Trainer public profile']) {
    await selectValue(page, page.getByRole('combobox', { name: label, exact: true }), hasTouch)
  }
  await dateValue(page, 'Trainer birthday', hasTouch)
  const input = page.getByLabel('Trainer type', { exact: true })
  await cancelledPress(input, () => expect(input).toHaveAttribute('aria-expanded', 'false'))
  await activate(input, hasTouch)
  const menu = page.getByRole('listbox', { name: 'Trainer type suggestions', exact: true })
  const option = menu.getByRole('option').first()
  const value = await option.innerText()
  await activate(option, hasTouch)
  await expect(input).toHaveValue(value)
  await expect(menu).toHaveCount(0)
  await activate(input, hasTouch)
  await expect(menu).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(menu).toHaveCount(0)
})

for (const [route, kind, query, title] of [['clients', 'client', 'Amanda', 'Client'], ['trainers', 'trainer', 'Marcus', 'Trainer']]) {
  test(`dropdown touch: ${kind} search suggestions select and reopen`, async ({ page, hasTouch }) => {
    await start(page, route)
    const input = page.getByLabel(`Search ${kind}`, { exact: true })
    const menu = page.getByRole('listbox', { name: `${title} search suggestions`, exact: true })
    await cancelledPress(input, () => expect(menu).toHaveCount(0))
    await input.fill(query)
    const option = menu.getByRole('option').first()
    const name = await option.locator('strong').innerText()
    await activate(option, hasTouch)
    await expect(input).toHaveValue(name)
    await expect(menu).toHaveCount(0)
    await activate(input, hasTouch)
    await expect(menu).toBeVisible()
    await activate(option, hasTouch)
    await expect(menu).toHaveCount(0)
  })
}

test('dropdown touch: calendar periods and demo identity', async ({ page, hasTouch }) => {
  await start(page, 'dashboard')
  await selectValue(page, page.getByRole('combobox', { name: 'Calendar week', exact: true }), hasTouch)
  await activate(page.getByRole('button', { name: 'Monthly', exact: true }), hasTouch)
  await selectValue(page, page.getByRole('combobox', { name: 'Calendar month', exact: true }), hasTouch)
  const openSidebar = async () => {
    await waitForPortal(page)
    const drawer = page.getByRole('button', { name: 'Open navigation', exact: true })
    if (await drawer.isVisible() && await drawer.getAttribute('aria-expanded') === 'false') await activate(drawer, hasTouch)
  }
  await openSidebar()
  await selectValue(page, page.getByRole('combobox', { name: 'Demo identity', exact: true }), hasTouch, 'u-marcus', openSidebar)
  await expect(page.locator('.portal-shell')).toHaveAttribute('data-user-id', 'u-marcus')
})

test('dropdown touch: exercise library and custom exercise choices', async ({ page, hasTouch }) => {
  const data = structuredClone(seed)
  const movement = DEFAULT_EXERCISES[0]
  data.sessions = [{ ...data.sessions[0], id: 'touch-session', clientId: 'c1', trainerId: 't1', status: 'planned', date: '2099-09-06',
    from: '10:00', to: '11:00', exercisePlan: [{ id: 'touch-exercise', name: movement.name, weight: '10 kg', reps: '8', rounds: '2', rest: '60 sec', customDetails: [] }] }]
  await page.addInitScript(({ key, data }) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, { key: KEY, data })
  await start(page, 'sessions/touch-session')
  await activate(page.getByRole('button', { name: 'Edit exercise plan', exact: true }), hasTouch)
  const input = page.getByRole('combobox', { name: 'Exercise 1 name', exact: true })
  await cancelledPress(input, () => expect(input).toHaveAttribute('aria-expanded', 'false'))
  await activate(input, hasTouch)
  const choice = page.locator('.exercise-picker-results button').first()
  const name = await choice.innerText()
  await activate(choice, hasTouch)
  await expect(input).toContainText(name)
  await expect(input).toHaveAttribute('aria-expanded', 'false')
  await activate(input, hasTouch)
  await activate(page.getByRole('button', { name: 'Custom Exercise', exact: true }), hasTouch)
  await page.getByLabel('Exercise 1 custom name', { exact: true }).fill('Local Touch Custom')
  await activate(page.getByRole('button', { name: 'Use Custom Exercise', exact: true }), hasTouch)
  await expect(input).toContainText('Local Touch Custom')
  await expect(input).toHaveAttribute('aria-expanded', 'false')
  await activate(page.locator('.exercise-edit-actions').getByRole('button', { name: 'Cancel', exact: true }), hasTouch)
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).sessions[0].exercisePlan[0].name, KEY)).toBe(movement.name)
})

test('dropdown touch: profile action menu and responsive profile navigation', async ({ page, hasTouch }) => {
  await start(page, 'trainers/t1')
  const menu = page.locator('.profile-menu')
  const summary = menu.locator('summary')
  if (await summary.isVisible()) {
    await activate(summary, hasTouch)
    await expect(menu).toHaveAttribute('open', '')
  }
  await activate(menu.getByRole('button', { name: 'Assigned Clients', exact: true }), hasTouch)
  const assigned = page.getByRole('combobox', { name: 'Filter assigned clients by type', exact: true })
  await expect(assigned).toBeVisible()
  await selectValue(page, assigned, hasTouch)
  await selectValue(page, page.getByRole('combobox', { name: 'Filter assigned clients by frequency', exact: true }), hasTouch)
  const trigger = page.getByRole('button', { name: 'Open profile menu', exact: true })
  await cancelledPress(trigger, () => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  await activate(trigger, hasTouch)
  await activate(page.getByRole('menuitem', { name: 'My Profile', exact: true }), hasTouch)
  await expect(page).toHaveURL(/#\/owner-profile$/)
  await expect(page.getByRole('menu', { name: 'Profile menu' })).toHaveCount(0)
})

test.describe('signed-out dropdown', () => {
  test.use({ demoSignedIn: false })
  test('dropdown touch: signed-out account choices', async ({ page, hasTouch }) => {
    await page.goto('/')
    const control = page.getByRole('combobox', { name: 'Account', exact: true })
    await selectValue(page, control, hasTouch, 'u-owner')
    await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('fitfinity-demo-session-v1'))).toBeNull()
  })
})
