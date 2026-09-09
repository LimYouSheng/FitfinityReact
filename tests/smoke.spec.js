import { test, expect, drawClientSignature, selectDemoIdentity, expandSidebarSections } from './fixtures.js'

async function navIsOnScreen(sidebar) {
  return sidebar.evaluate(element => {
    const rect = element.getBoundingClientRect()
    const style = getComputedStyle(element)

    return (
      element.classList.contains('mobile-open') &&
      style.visibility !== 'hidden' &&
      style.display !== 'none' &&
      rect.right > 0 &&
      rect.left < window.innerWidth &&
      rect.width > 0
    )
  })
}

async function openNavIfNeeded(page) {
  await expandSidebarSections(page, { keepOpen: true })
  await expect(page.locator('.portal-shell')).toHaveAttribute('aria-busy', 'false')
  const menu = page.getByRole('button', { name: 'Open navigation' })
  if (!(await menu.isVisible())) return

  const sidebar = page.locator('.sidebar')
  await page.waitForTimeout(300)

  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (await navIsOnScreen(sidebar)) return
    await menu.click()
    await page.waitForTimeout(300)
    if (await navIsOnScreen(sidebar)) return
  }

  throw new Error('Mobile navigation drawer did not remain on screen after reopening')
}

async function clickNav(page, name) {
  await openNavIfNeeded(page)

  const item = page.locator('.sidebar nav').getByRole('button', {
    name,
    exact: true,
  })

  await expect(item).toBeVisible()
  await item.scrollIntoViewIfNeeded()

  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) {
    const itemIsOnScreen = async () => {
      const box = await item.boundingBox()
      const width = await page.evaluate(() => window.innerWidth)
      return Boolean(box && box.x < width && box.x + box.width > 0)
    }

    if (!(await itemIsOnScreen())) {
      await openNavIfNeeded(page)
      await item.scrollIntoViewIfNeeded()
    }
    await expect.poll(itemIsOnScreen, { timeout: 5000 }).toBe(true)
  }

  await item.click()
}

async function clickMessages(page) {
  await clickNav(page, 'Messages')
}

async function expectSameRow(locators) {
  const boxes = await Promise.all(locators.map(locator => locator.boundingBox()))
  const ys = boxes.map(box => Math.round(box?.y ?? -999))
  expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(3)
}

async function expectSameHeight(locators) {
  const boxes = await Promise.all(locators.map(locator => locator.boundingBox()))
  const heights = boxes.map(box => Math.round(box?.height ?? -999))
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1)
}

async function expectStandardSectionHeadings(page) {
  const styles = await page.locator('.panel h2').evaluateAll(elements =>
    elements.map(element => {
      const style = getComputedStyle(element)
      return { color: style.color, fontSize: style.fontSize }
    })
  )

  expect([...new Set(styles.map(style => style.fontSize))]).toEqual(['16px'])
  expect([...new Set(styles.map(style => style.color))]).toEqual(['rgb(207, 213, 255)'])
}

async function confirmAction(page, title, confirmLabel) {
  const dialog = page.getByRole('dialog', { name: title })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: confirmLabel }).click()
}

async function openSession(page, {
  client = 'Amanda Lim',
  status = '',
} = {}) {
  await page.getByLabel('Search sessions').fill(client)
  await page.getByLabel('Filter sessions by status').selectOption(status)
  const firstMatch = page.getByLabel('Session list').locator('.session-list-row').first()
  await expect(firstMatch).toBeVisible()
  await firstMatch.getByRole('button', { name: /View session/ }).click()
}

async function clickProfileTab(page, name) {
  const menu = page.locator('.profile-menu')
  await expect(menu).toBeVisible()
  if (await menu.locator('summary').isVisible()) await menu.locator('summary').click()
  const tab = menu.getByRole('button', { name, exact: true })
  await expect(tab).toBeVisible()
  await tab.click()
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-02T04:00:00Z'))
  await page.goto('/#/dashboard')
})

test('dashboard places renewal Messages above the calendar without statistics', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Calendar' })).toBeVisible()
  await expect(page.locator('.stats-grid')).toHaveCount(0)
  await expect(page.getByLabel('Renewal messages')).toBeVisible()
  const renewalBox = await page.locator('.dashboard-renewals').boundingBox()
  const calendarBox = await page.getByRole('heading', { name: 'Calendar', exact: true }).boundingBox()
  expect(renewalBox.y + renewalBox.height).toBeLessThan(calendarBox.y)
  await expect(page.getByText('Fitfinity Staff', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Owner portal', { exact: true })).toHaveCount(0)

  if (page.viewportSize().width > 780) {
    const sidebar = page.locator('.sidebar')
    await expect(sidebar).toHaveCSS('position', 'fixed')
    await page.evaluate(() => {
      document.body.style.minHeight = '200vh'
      window.scrollTo(0, document.documentElement.scrollHeight)
    })
    await expect.poll(async () => Math.round((await sidebar.boundingBox()).y)).toBe(0)
  }
})

test('client filters are one compact row', async ({ page }) => {
  await clickNav(page, 'Clients')
  await expect(page.locator('.page-head .eyebrow')).toHaveText('Operations')

  await expectSameHeight([
    page.getByLabel('Search client'),
    page.getByLabel('Filter clients by status'),
    page.getByLabel('Filter clients by type'),
    page.getByLabel('Filter clients by trainer'),
  ])

  await expectSameRow([
    page.getByLabel('Filter clients by status'),
    page.getByLabel('Filter clients by type'),
    page.getByLabel('Filter clients by trainer'),
  ])
})

test('trainer filters are one compact row', async ({ page }) => {
  await clickNav(page, 'Trainers')
  await expect(page.locator('.page-head .eyebrow')).toHaveText('Operations')

  await expectSameHeight([
    page.getByLabel('Search trainer'),
    page.getByLabel('Filter trainers by status'),
    page.getByLabel('Filter trainers by type'),
    page.getByLabel('Filter trainers by gender'),
  ])

  await expectSameRow([
    page.getByLabel('Filter trainers by status'),
    page.getByLabel('Filter trainers by type'),
    page.getByLabel('Filter trainers by gender'),
  ])
})

test('trainer client filters keep same layout', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await clickNav(page, 'All Clients')

  const status = page.getByLabel('Filter clients by status')
  const type = page.getByLabel('Filter clients by type')
  const trainer = page.getByLabel('Filter clients by trainer')

  await expect(status).toBeDisabled()
  await expect(trainer).toHaveCount(0)
  await expectSameRow([status, type])
})

test('owner can edit trainer rates', async ({ page }) => {
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()
  await expect(page.locator('.page-head .eyebrow')).toHaveText('Trainer')

  const ratesPanel = page.locator('.panel').filter({
    has: page.getByRole('heading', { name: 'Training & Rates' }),
  })

  await ratesPanel.getByRole('button', { name: 'Edit' }).click()
  await ratesPanel.getByLabel('Peak rate', { exact: true }).fill('85')
  await ratesPanel.getByLabel('Off-peak rate', { exact: true }).fill('60')
  await ratesPanel.getByRole('button', { name: 'Save' }).click()
  await confirmAction(page, 'Save trainer rates?', 'Save Rates')

  await expect(ratesPanel.getByText('$85 / session')).toBeVisible()
  await expect(ratesPanel.getByText('$60 / session')).toBeVisible()
})

test('browser back returns client detail to list', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()
  await expect(page.locator('.page-head .eyebrow')).toHaveText('Client')
  await expect(page).toHaveURL(/#\/clients\/c1$/)

  await page.goBack()
  await expect(page).toHaveURL(/#\/clients$/)
})

test('client deactivation still removes client from trainer view', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()
  await expect(page.locator('.profile-menu')).toBeVisible()
  if (await page.locator('.profile-menu summary').isVisible()) {
    await page.locator('.profile-menu summary').click()
  }
  await page.getByRole('button', { name: 'Deactivate Client' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate Client' }).click()

  await selectDemoIdentity(page, 'u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await page.waitForTimeout(350)
  await clickNav(page, 'All Clients')

  await expect(page.getByText('Amanda Lim')).toHaveCount(0)
})

test('trainer profile keeps status in the name card and account status leaves rates panel', async ({ page }) => {
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()

  await expect(page.getByLabel('Trainer status')).toContainText('Active')

  const ratesPanel = page.locator('.panel').filter({
    has: page.getByRole('heading', { name: 'Training & Rates' }),
  })
  await expect(ratesPanel.getByText('Account status')).toHaveCount(0)
  await expect(ratesPanel.getByText('Assigned clients', { exact: true })).toHaveCount(0)

  const generalPanel = page.locator('.panel').filter({
    has: page.getByRole('heading', { name: 'General Information' }),
  })
  const approvalPanel = page.locator('.panel').filter({
    has: page.getByRole('heading', { name: 'Owner Approval Needed' }),
  })
  await expect(approvalPanel).toBeVisible()
  await expect(page.locator('.profile-tabs').getByRole('button', { name: 'Autonomy & Approvals' })).toHaveCount(0)
  await expect(page.getByText(/Uncheck and save/)).toHaveCount(0)

  const [generalBox, ratesBox, approvalBox] = await Promise.all([
    generalPanel.boundingBox(),
    ratesPanel.boundingBox(),
    approvalPanel.boundingBox(),
  ])
  expect(ratesBox.y).toBeGreaterThanOrEqual(generalBox.y + generalBox.height - 2)
  expect(approvalBox.y).toBeGreaterThanOrEqual(ratesBox.y + ratesBox.height - 2)

  if (page.viewportSize().width >= 700) {
    const rowTops = await generalPanel.locator('.profile-info-grid .info-row').evaluateAll(elements =>
      elements.slice(0, 2).map(element => element.getBoundingClientRect().top)
    )
    expect(Math.abs(rowTops[0] - rowTops[1])).toBeLessThanOrEqual(2)
  }

  const menu = page.locator('.profile-menu')
  await expect(menu).toBeVisible()
  if (await menu.locator('summary').isVisible()) await menu.locator('summary').click()
  await expect(menu.locator('.profile-tabs button').last()).toHaveText('Deactivate Trainer')
  await menu.getByRole('button', { name: 'Availability', exact: true }).click()
  await expect(page.getByText(/Owner view is read-only by design/)).toHaveCount(0)

  await clickProfileTab(page, 'Monthly Activity')
  const month = page.locator('.trainer-activity-month')
  const stats = page.locator('.trainer-monthly-activity .stats-grid')
  await expect(month).toContainText('September 2026')
  const [monthBox, statsBox] = await Promise.all([month.boundingBox(), stats.boundingBox()])
  expect(monthBox.y + monthBox.height).toBeLessThanOrEqual(statsBox.y)
})

test('trainer sidebar exposes Messages and Profile under System', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await page.waitForTimeout(350)
  await openNavIfNeeded(page)

  const sidebar = page.locator('.sidebar')
  const system = sidebar.locator('.nav-group').filter({ hasText: 'System' })
  await expect(system.getByRole('button', { name: 'Messages', exact: true })).toBeVisible()
  await expect(system.getByRole('button', { name: 'Profile', exact: true })).toBeVisible()
})

test('System follows Remuneration while topbar controls remain available', async ({ page }) => {
  await openNavIfNeeded(page)
  const sidebar = page.locator('.sidebar')
  const groupLabels = await sidebar.locator('.nav-group-label').allTextContents()

  expect(groupLabels.indexOf('System')).toBe(groupLabels.indexOf('Remuneration') + 1)
  await expect(sidebar.getByRole('button', { name: 'Messages', exact: true })).toBeVisible()
  await expect(sidebar.getByRole('button', { name: 'Profile', exact: true })).toBeVisible()
  const topbarMessages = page.getByRole('banner').getByRole('button', { name: 'Messages' })
  const profile = page.getByRole('button', { name: 'Open profile menu' })
  await expect(topbarMessages).toBeVisible()
  await expect(topbarMessages.locator('.message-icon')).toBeVisible()
  await expect(profile).toBeVisible()
  await expect(profile.locator('.user-avatar')).toBeVisible()
})

test('client status is visible at the card edge and lifecycle action is last', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  await expect(page.getByLabel('Client status')).toContainText('Active')

  const menu = page.locator('.profile-menu')
  await expect(menu).toBeVisible()
  if (await menu.locator('summary').isVisible()) await menu.locator('summary').click()
  await expect(menu.locator('.profile-tabs button').last()).toHaveText('Deactivate Client')
})

test('assigned supervised trainer can edit fixed weekly schedule and submits request', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await page.waitForTimeout(350)

  await clickNav(page, 'All Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const schedule = page.locator('.schedule-panel')
  await schedule.getByRole('button', { name: 'Edit' }).click()

  const fromBox = await schedule.getByLabel('Monday from').boundingBox()
  const toBox = await schedule.getByLabel('Monday to').boundingBox()
  expect(fromBox).not.toBeNull()
  expect(toBox).not.toBeNull()
  expect(
    fromBox.x + fromBox.width <= toBox.x ||
    fromBox.y + fromBox.height <= toBox.y
  ).toBe(true)
  if (page.viewportSize().width <= 1100) {
    expect(fromBox.y + fromBox.height).toBeLessThanOrEqual(toBox.y)
  }

  await schedule.getByLabel('Monday from').fill('18:30')
  await schedule.getByRole('button', { name: 'Save' }).click()
  await confirmAction(page, 'Save fixed weekly schedule?', 'Save Schedule')
  await expect(schedule.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()

  await selectDemoIdentity(page, 'u-owner')
  await expect(page.getByRole('heading', { name: 'Owner Dashboard' })).toBeVisible()

  await clickMessages(page)
  await expect(page.getByText('Fixed weekly schedule change: Amanda Lim')).toBeVisible()
})

test('message becomes read and loses blue border after opening', async ({ page }) => {
  // Keep the read action later than every seeded message, on the same business day.
  await page.clock.setFixedTime(new Date('2026-09-02T15:00:00Z'))
  await clickMessages(page)

  const messageFilters = page.getByLabel('Message filters')
  const messageDateControls = messageFilters.locator('.date-filter-control')
  const messageRows = page.getByLabel('Message list').locator('.message-title-row')
  await expect(messageRows).toHaveCount(10)
  await expect(messageRows.locator('.message-title-time')).toHaveCount(10)
  await expect(messageRows.locator('.message-title-time').first()).toHaveAttribute('datetime', /\d{4}-\d{2}-\d{2}T/)
  if (page.viewportSize().width > 620) {
    await expect(page.locator('.message-title-head')).toContainText('Date & time')
  }
  await expect(messageFilters.getByText('Select start date', { exact: true })).toBeVisible()
  await expect(messageFilters.getByText('Select end date', { exact: true })).toBeVisible()

  await expectSameHeight([
    page.getByLabel('Search messages'),
    messageDateControls.nth(0),
    messageDateControls.nth(1),
  ])

  if (page.viewportSize().width <= 850) {
    const searchBox = await page.getByLabel('Search messages').boundingBox()
    const fromBox = await messageDateControls.nth(0).boundingBox()
    const toBox = await messageDateControls.nth(1).boundingBox()

    expect(searchBox.y + searchBox.height).toBeLessThanOrEqual(fromBox.y)
    expect(Math.abs(fromBox.y - toBox.y)).toBeLessThanOrEqual(1)
    expect(fromBox.x + fromBox.width).toBeLessThanOrEqual(toBox.x)
    expect(Math.abs(fromBox.width - toBox.width)).toBeLessThanOrEqual(1)
  }

  const row = page.getByLabel('Message list').locator('.message-title-row').filter({
    hasText: 'Renewal follow-up: Nadia Koh',
  })

  await expect(
    page.getByRole('button', { name: 'Unread Renewal follow-up: Nadia Koh' })
  ).toBeVisible()

  const beforeBorder = await row.evaluate(element => getComputedStyle(element).borderTopColor)
  expect(beforeBorder).not.toBe('rgba(0, 0, 0, 0)')

  await page.getByRole('button', { name: 'Unread Renewal follow-up: Nadia Koh' }).click()
  await expect(page.getByRole('dialog', { name: 'Open and mark as read?' })).toHaveCount(0)

  const dialog = page.getByRole('dialog', { name: 'Renewal follow-up: Nadia Koh' })
  await expect(dialog).toBeVisible()

  await page.goBack()
  await expect(dialog).toHaveCount(0)

  await expect(
    page.getByRole('button', { name: 'Read Renewal follow-up: Nadia Koh' })
  ).toBeVisible()
  await expect(
    page.getByLabel('Message list').locator('.message-title-row.read').first()
  ).toContainText('Renewal follow-up: Nadia Koh')

  await expect.poll(async () =>
    row.evaluate(element => getComputedStyle(element).borderTopColor)
  ).toBe('rgba(0, 0, 0, 0)')

  const search = page.getByLabel('Search messages')
  await search.fill('approaching package renewal')
  await expect(page.getByLabel('Message list').locator('.message-title-row')).toHaveCount(1)
  await expect(page.getByText('Renewal follow-up: Nadia Koh', { exact: true })).toBeVisible()

  await search.fill('')
  await page.getByLabel('Messages from date').fill('2026-09-02')
  await page.getByLabel('Messages to date').fill('2026-09-02')
  await expect(messageFilters.getByText('Select start date', { exact: true })).toHaveCount(0)
  await expect(messageFilters.getByText('Select end date', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Renewal follow-up: Nadia Koh', { exact: true })).toBeVisible()
  await expect(page.getByText('Messages foundation ready', { exact: true })).toHaveCount(0)

  await page.getByLabel('Messages from date').fill('')
  await page.getByLabel('Messages to date').fill('')
  await page.getByRole('button', { name: 'Read Renewal follow-up: Nadia Koh' }).click()
  const reopenedDialog = page.getByRole('dialog', { name: 'Renewal follow-up: Nadia Koh' })
  await reopenedDialog.getByRole('button', { name: 'View Client · Nadia Koh' }).click()
  await expect(page.getByRole('heading', { name: 'Nadia Koh' })).toBeVisible()
  await expect(page.locator('.page-head .eyebrow')).toHaveText('Client')
})

test('swipe back visibly moves the whole page before navigating', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const portal = page.locator('.portal-main')
  const backBox = await page.getByRole('button', { name: 'Back' }).boundingBox()
  expect(backBox).not.toBeNull()
  const startX = Math.round(backBox.x + backBox.width / 2)

  await page.evaluate(({ startX }) => {
    window.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true,
      pointerId: 7,
      pointerType: 'touch',
      clientX: startX,
      clientY: 260,
      isPrimary: true,
    }))

    window.dispatchEvent(new PointerEvent('pointermove', {
      bubbles: true,
      pointerId: 7,
      pointerType: 'touch',
      clientX: startX + 90,
      clientY: 266,
      isPrimary: true,
    }))
  }, { startX })

  await expect.poll(async () =>
    portal.evaluate(element => {
      const transform = getComputedStyle(element).transform
      return transform !== 'none' && transform !== 'matrix(1, 0, 0, 1, 0, 0)'
    })
  ).toBe(true)

  await page.evaluate(({ startX }) => {
    window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true,
      pointerId: 7,
      pointerType: 'touch',
      clientX: startX + 140,
      clientY: 270,
      isPrimary: true,
    }))
  }, { startX })

  await expect(page).toHaveURL(/#\/clients$/)
})

test('topbar chevron navigates back without previous-page text', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const back = page.getByRole('button', { name: 'Back' })
  await expect(back).toHaveText('‹')
  await back.click()

  await expect(page).toHaveURL(/#\/clients$/)
  await expect(page.getByRole('button', { name: 'Back' })).toHaveCount(0)
})

test('clicking transparent profile-menu scrim closes dropdown', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const menu = page.locator('.profile-menu')
  await expect(menu).toBeVisible()
  if (!(await menu.locator('summary').isVisible())) return
  await menu.locator('summary').click()
  await expect(menu).toHaveAttribute('open', '')

  const viewport = page.viewportSize()
  await page.mouse.click(viewport.width - 8, viewport.height - 8)

  await expect(menu).not.toHaveAttribute('open', '')
})


test('detail screen exposes topbar Back without profile-local back control', async ({ page }) => {
  await clickNav(page, 'Clients')
  await expect(page.getByRole('button', { name: 'Back' })).toHaveCount(0)

  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const back = page.getByRole('button', { name: 'Back' })
  await expect(back).toBeVisible()
  await expect(back).toHaveText('‹')

  await expect(page.locator('.profile-identity-card .back-link')).toHaveCount(0)
  await expect(page.locator('.profile-back-row')).toHaveCount(0)
})

test('when hamburger is visible Back sits to its left', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const back = page.getByRole('button', { name: 'Back' })
  const menu = page.getByRole('button', { name: 'Open navigation' })

  await expect(back).toBeVisible()

  if (await menu.isVisible()) {
    const backBox = await back.boundingBox()
    const menuBox = await menu.boundingBox()

    expect(backBox).not.toBeNull()
    expect(menuBox).not.toBeNull()
    expect(backBox.x).toBeLessThan(menuBox.x)
  }
})

test('Home is square and matches visible hamburger footprint', async ({ page }) => {
  const home = page.getByRole('button', { name: 'Home' })
  const menu = page.getByRole('button', { name: 'Open navigation' })

  await expect(home).toBeVisible()

  const homeBox = await home.boundingBox()
  expect(homeBox).not.toBeNull()
  expect(Math.abs(homeBox.width - homeBox.height)).toBeLessThanOrEqual(1)

  if (await menu.isVisible()) {
    const menuBox = await menu.boundingBox()

    expect(menuBox).not.toBeNull()
    expect(Math.abs(homeBox.width - menuBox.width)).toBeLessThanOrEqual(1)
    expect(Math.abs(homeBox.height - menuBox.height)).toBeLessThanOrEqual(1)
  }
})

test('detail screen exposes Back without profile-local back controls', async ({ page }) => {
  await clickNav(page, 'Clients')
  await expect(page.getByRole('button', { name: 'Back' })).toHaveCount(0)

  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  await expect(page.getByRole('button', { name: 'Back' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back' })).toHaveText('‹')
  await expect(page.locator('.profile-identity-card .back-link')).toHaveCount(0)
  await expect(page.locator('.profile-back-row')).toHaveCount(0)
})

test('when hamburger is visible Back remains to its left', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const back = page.getByRole('button', { name: 'Back' })
  const menu = page.getByRole('button', { name: 'Open navigation' })

  await expect(back).toBeVisible()

  if (await menu.isVisible()) {
    const backBox = await back.boundingBox()
    const menuBox = await menu.boundingBox()

    expect(backBox).not.toBeNull()
    expect(menuBox).not.toBeNull()
    expect(backBox.x).toBeLessThan(menuBox.x)
  }
})

test('Home icon is visible in a square button matching visible hamburger', async ({ page }) => {
  const home = page.getByRole('button', { name: 'Home' })
  const icon = home.locator('.home-icon')
  const menu = page.getByRole('button', { name: 'Open navigation' })

  await expect(home).toBeVisible()
  await expect(icon).toBeVisible()

  const homeBox = await home.boundingBox()
  expect(homeBox).not.toBeNull()
  expect(Math.abs(homeBox.width - homeBox.height)).toBeLessThanOrEqual(1)

  if (await menu.isVisible()) {
    const menuBox = await menu.boundingBox()
    expect(menuBox).not.toBeNull()
    expect(Math.abs(homeBox.width - menuBox.width)).toBeLessThanOrEqual(1)
    expect(Math.abs(homeBox.height - menuBox.height)).toBeLessThanOrEqual(1)
  }
})

test('viewport and CSS suppress zoom and pull refresh gestures', async ({ page }) => {
  const viewport = page.locator('meta[name="viewport"]')

  await expect(viewport).toHaveAttribute('content', /maximum-scale=1/)
  await expect(viewport).toHaveAttribute('content', /user-scalable=no/)

  const guards = await page.evaluate(() => ({
    touchAction: getComputedStyle(document.documentElement).touchAction,
    overscrollY: getComputedStyle(document.documentElement).overscrollBehaviorY,
  }))

  expect(guards.touchAction).toBe('pan-y')
  expect(guards.overscrollY).toBe('none')
})

test('sidebar unread badge content is centred in a compact bubble', async ({ page }) => {
  await openNavIfNeeded(page)
  const badge = page.locator('.nav-count').first()

  if (await badge.isVisible()) {
    const box = await badge.boundingBox()
    const styles = await badge.evaluate(element => {
      const style = getComputedStyle(element)
      return {
        alignItems: style.alignItems,
        justifyContent: style.justifyContent,
      }
    })

    expect(box).not.toBeNull()
    expect(Math.abs(box.width - box.height)).toBeLessThanOrEqual(1)
    expect(styles.alignItems).toBe('center')
    expect(styles.justifyContent).toBe('center')
  }
})

test('sidebar Messages carries the unread count and opens the message list', async ({ page }) => {
  await openNavIfNeeded(page)
  const button = page.locator('.sidebar nav').getByRole('button', { name: 'Messages', exact: true })
  await expect(button.locator('.nav-count')).toBeVisible()
  await button.click()
  await expect(page.getByRole('heading', { name: 'Messages' })).toBeVisible()
})

test('sidebar Messages remains available when every message is read', async ({ page }) => {
  await clickMessages(page)
  const unreadRows = page.getByLabel('Message list').locator('.message-title-row.unread')

  while (true) {
    if (await unreadRows.count()) {
      await unreadRows.first().locator('.message-state-button').click()
      await expect(page.getByRole('dialog', { name: 'Open and mark as read?' })).toHaveCount(0)
      await page.getByRole('button', { name: 'Close message' }).click()
      continue
    }

    const next = page.getByRole('button', { name: 'Next', exact: true })
    if (!(await next.isEnabled())) break
    await next.click()
  }

  await openNavIfNeeded(page)
  const messagesButton = page.locator('.sidebar nav').getByRole('button', { name: 'Messages', exact: true })
  await expect(messagesButton).toBeVisible()
  await expect(messagesButton.locator('.nav-count')).toHaveCount(0)
})

test('dark area anywhere outside message card closes message detail', async ({ page }) => {
  await clickMessages(page)

  const first = page.getByLabel('Message list').locator('.message-title-row').first()
  const stateButton = first.locator('.message-state-button')

  if (await stateButton.isVisible()) {
    await stateButton.click()
  } else {
    await first.locator('.message-title-button').click()
  }
  const backdrop = page.locator('.modal-backdrop')
  const dialog = page.locator('.message-detail-modal')

  await expect(backdrop).toBeVisible()
  await expect(dialog).toBeVisible()
  await expect.poll(() => page.evaluate(() => ({
    bodyPosition: document.body.style.position,
    rootOverflow: document.documentElement.style.overflow,
  }))).toEqual({ bodyPosition: 'fixed', rootOverflow: 'hidden' })

  const viewport = page.viewportSize()
  await page.mouse.click(viewport.width - 6, viewport.height - 6)

  await expect(dialog).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    bodyPosition: document.body.style.position,
    rootOverflow: document.documentElement.style.overflow,
  }))).toEqual({ bodyPosition: '', rootOverflow: '' })
})

test('message dialog is centred against the full viewport', async ({ page }) => {
  await clickMessages(page)
  await page.getByLabel('Message list').locator('.message-title-row').first()
    .locator('.message-state-button').click()
  const dialog = page.locator('.message-detail-modal')
  const box = await dialog.boundingBox()
  const viewport = page.viewportSize()

  expect(box).not.toBeNull()
  expect(Math.abs((box.x + box.width / 2) - viewport.width / 2)).toBeLessThanOrEqual(2)
})

test('owner opens session details with client trainer weekday and status', async ({ page }) => {
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '02 Sept 2026', status: 'planned' })

  await expect(page).toHaveURL(/#\/sessions\/s1$/)
  await expect(page.getByText(/Wednesday,/).first()).toBeVisible()
  await expect(page.getByText('Amanda Lim', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Marcus Tan', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Session · Planned', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'View Client' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'View Trainer' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Client Signature' })).toBeVisible()
})

test('client trainer and trainer type columns share the shifted-left compact layout', async ({ page }) => {
  await clickNav(page, 'Clients')
  const clientColumns = await page.locator('.client-compact-grid').first().evaluate(element =>
    getComputedStyle(element).gridTemplateColumns.split(' ').map(parseFloat)
  )
  expect(clientColumns[0]).toBeLessThan(clientColumns[1])

  await clickNav(page, 'Trainers')
  const trainerColumns = await page.locator('.trainer-compact-grid').first().evaluate(element =>
    getComputedStyle(element).gridTemplateColumns.split(' ').map(parseFloat)
  )
  expect(trainerColumns[0]).toBeLessThan(trainerColumns[1])
})

test('trainer session list includes only that trainer sessions', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')

  const list = page.getByLabel('Session list')
  await expect(list.getByText('Amanda Lim', { exact: true }).first()).toBeVisible()
  await expect(list.getByText('Daniel & Mei Wong', { exact: true })).toHaveCount(0)
  await expect(list.getByText('Farah Noor', { exact: true })).toHaveCount(0)
})

test('blank exercise blocks save and cancelling it releases Add Exercise', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '07 Sept 2026', status: 'not_planned' })
  const emptyPlan = page.getByRole('button', { name: 'Start Plan' })
  await expect(emptyPlan).toContainText('Start Plan')
  await expect(page.locator('.exercise-plan-head').getByRole('button')).toHaveCount(0)
  await emptyPlan.click()

  const editor = page.locator('.exercise-editor')
  const plan = page.locator('.exercise-plan-panel')
  const addExercise = plan.getByRole('button', { name: 'Add Exercise' })
  const save = plan.getByRole('button', { name: 'Save', exact: true })
  await expect(addExercise).toBeDisabled()
  await expect(save).toBeDisabled()
  await expect(editor.getByLabel('Exercise 1 name')).toHaveClass(/pending-empty/)
  await expect(editor.getByLabel('Exercise 1 details 1')).toHaveCount(0)
  await editor.getByRole('button', { name: 'Add details for exercise 1' }).click()
  await editor.getByRole('button', { name: 'Add details for exercise 1' }).click()
  await expect(editor.getByLabel('Exercise 1 details 1', { exact: true })).toBeVisible()
  await expect(editor.getByLabel('Exercise 1 details 2', { exact: true })).toBeVisible()

  const weightBox = await editor.getByLabel('Exercise 1 weight').boundingBox()
  const detailBox = await editor.getByLabel('Exercise 1 details 1', { exact: true }).boundingBox()
  expect(Math.abs(weightBox.height - detailBox.height)).toBeLessThanOrEqual(1)
  await expect(editor).not.toContainText('Editing 1 exercise')

  await editor.locator('.exercise-editor-row').getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(addExercise).toBeEnabled()
  await expect(save).toBeDisabled()
})

test('exercise plan saves to display rows and overall Edit returns to editor', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '07 Sept 2026', status: 'not_planned' })
  await page.getByRole('button', { name: 'Start Plan' }).click()
  await page.getByLabel('Exercise 1 name').click()
  await page.getByRole('button', { name: 'Custom Exercise', exact: true }).click()
  await page.getByLabel('Exercise 1 custom name').fill('Romanian Deadlift')
  await page.getByRole('button', { name: 'Use Custom Exercise' }).click()
  await page.getByLabel('Exercise 1 reps').fill('8')
  await page.getByLabel('Exercise 1 rounds').fill('3')
  await page.locator('.exercise-plan-panel').getByRole('button', { name: 'Save', exact: true }).click()
  await confirmAction(page, 'Save exercise plan?', 'Save Plan')

  await expect(page.getByLabel('Exercise plan', { exact: true }).getByText('Romanian Deadlift')).toBeVisible()
  await expect(page.locator('.exercise-plan-head')).toHaveCSS('border-bottom-style', 'none')
  await expect(page.getByLabel('Exercise plan', { exact: true })).toHaveCSS('border-top-style', 'solid')
  await page.locator('.exercise-plan-panel').getByRole('button', { name: 'Edit exercise plan', exact: true }).click()
  await expect(page.getByLabel('Exercise 1 name')).toContainText('Romanian Deadlift')
})

test('exercise dropdown starts with Custom Exercise, keeps Oracle categories and supports search', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '02 Sept 2026', status: 'planned' })

  const plan = page.locator('.exercise-plan-panel')
  await plan.getByRole('button', { name: 'Edit exercise plan', exact: true }).click()
  const selector = plan.getByLabel('Exercise 1 name')
  await selector.click()
  const menu = plan.getByLabel('Exercise 1 choices')
  await expect(menu.getByRole('button', { name: 'Custom Exercise', exact: true })).toBeVisible()
  await expect(menu.locator('.exercise-picker-group')).toHaveCount(6)
  await expect(menu.locator('.exercise-picker-group').first().locator('strong')).toHaveText('Full Body')
  await expect(menu.locator('.exercise-picker-group button')).toHaveCount(49)
  await plan.getByLabel('Search exercise 1').fill('smith')
  await expect(menu.getByRole('button', { name: 'Smith chest press', exact: true })).toBeVisible()
  await expect(menu.getByRole('button', { name: 'Wall Ball', exact: true })).toHaveCount(0)
})

test('video attaches after planning and remains available for read-only playback after completion', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '02 Sept 2026', status: 'planned' })

  const plan = page.locator('.exercise-plan-panel')
  await plan.getByRole('button', { name: 'Edit exercise plan', exact: true }).click()
  await expect(plan.getByRole('button', { name: /video/i })).toHaveCount(0)
  await plan.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(plan.getByRole('button', { name: /video for/i }).first()).toBeVisible()
  await expect(plan.locator('.exercise-display-camera.attached')).toHaveCount(0)
  await plan.getByRole('button', { name: /Manage video for/i }).first().click()
  const videoDialog = page.getByRole('dialog', { name: /Video ·/ })
  const recordInput = videoDialog.getByLabel(/Record new video for/)
  const attachInput = videoDialog.getByLabel(/Attach video for/)
  await expect(recordInput).toHaveAttribute('capture', 'environment')
  await expect(attachInput).toBeAttached()
  await expect(videoDialog).toContainText('Maximum 1 minute')
  await attachInput.setInputFiles('tests/fixtures/silent-one-second.webm')
  await expect(videoDialog.getByRole('button', { name: 'Save Video' })).toBeEnabled({ timeout: 15000 })
  await expect(videoDialog.locator('.exercise-video-preview')).toBeVisible()
  await videoDialog.getByRole('button', { name: 'Save Video' }).click()
  await expect(videoDialog).toHaveCount(0)
  await expect(plan.locator('.exercise-display-camera.attached').first()).toBeVisible()
  const cameraColours = await plan.locator('.exercise-display-camera svg').evaluateAll(elements =>
    elements.map(element => ({ attached: element.closest('.exercise-display-camera').classList.contains('attached'),
      icon: getComputedStyle(element).color, control: getComputedStyle(element.closest('.exercise-display-camera')).color }))
  )
  expect(cameraColours.some(item => item.attached)).toBe(true)
  expect(cameraColours.some(item => !item.attached)).toBe(true)
  for (const item of cameraColours) {
    expect(item.icon).toBe(item.attached ? 'rgb(200, 206, 255)' : 'rgb(143, 152, 168)')
    expect(item.icon).toBe(item.control)
  }
  await page.getByRole('button', { name: 'Client Signature' }).click()
  await drawClientSignature(page)
  await page.getByRole('dialog', { name: 'Client signature' }).getByRole('button', { name: 'Review Completion' }).click()
  await confirmAction(page, 'Complete this session?', 'Complete Session')
  await expect(page.getByText('Session · Completed', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.locator('.portal-shell')).toHaveAttribute('aria-busy', 'false')
  await plan.getByRole('button', { name: /View video for/i }).first().click()
  await expect(videoDialog.locator('video')).toHaveAttribute('src', /^blob:/)
  await expect(videoDialog.locator('video')).toHaveAttribute('controls', '')
  await expect(videoDialog.getByLabel(/Record new video|Attach video/)).toHaveCount(0)
  await expect(videoDialog.getByRole('button', { name: /Save Video|Remove saved video/ })).toHaveCount(0)
  await expect(videoDialog).toContainText('Available until')
  const savedVideo = await page.evaluate(() => JSON.parse(localStorage.getItem('fitfinity-m2-demo-db-v4')).sessions.find(item => item.id === 's1').exercisePlan.find(item => item.videoAttached).video)
  expect(Date.parse(savedVideo.expiresAt) - Date.parse(savedVideo.attachedAt)).toBe(7 * 24 * 60 * 60 * 1000)
  await expect(videoDialog.locator('time')).toHaveAttribute('datetime', savedVideo.expiresAt)
  await videoDialog.getByRole('button', { name: 'Close dialog' }).click()
  await page.getByRole('button', { name: 'Export Summary', exact: true }).click()
  const exportDialog = page.getByRole('dialog', { name: 'Export Summary' })
  const videos = exportDialog.getByRole('group', { name: 'Selected Videos' })
  await expect(videos.getByRole('checkbox')).toHaveCount(1)
  await expect(videos.getByRole('checkbox')).toBeChecked()
  await expect(exportDialog.getByRole('checkbox', { name: 'Include Client-Facing Summary' })).toBeChecked()
  const attachedName = await plan.locator('.exercise-display-camera.attached').getAttribute('aria-label')
  await expect(exportDialog).toContainText(attachedName.replace('View video for ', ''))
  await videos.getByRole('checkbox').uncheck()
  await expect(videos.getByRole('checkbox')).not.toBeChecked()
  await exportDialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await clickNav(page, 'Messages')
  await expect(page.getByText('Exercise video saved: Amanda Lim').first()).toBeVisible()
})

test('only one section edits at a time and navigation warns before discarding it', async ({ page }) => {
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()

  const ratesPanel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Training & Rates' }) })
  const generalPanel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information' }) })
  await ratesPanel.getByRole('button', { name: 'Edit' }).click()

  await expect(ratesPanel).toHaveClass(/editing-section/)
  await expect(page.locator('.content')).toHaveClass(/edit-active/)
  await expect.poll(() => page.locator('.content').evaluate(element =>
    getComputedStyle(element, '::before').backgroundColor
  )).toBe('rgba(3, 4, 7, 0.62)')
  await expect(generalPanel.getByRole('button', { name: 'Edit' })).toBeDisabled()

  await clickNav(page, 'Clients')
  await confirmAction(page, 'Leave this edit?', 'Cancel')
  await expect(ratesPanel.getByLabel('Peak rate', { exact: true })).toBeVisible()

  await page.locator('.sidebar nav button').evaluateAll(buttons => {
    buttons.find(button => button.textContent.trim() === 'Clients').click()
    buttons.find(button => button.textContent.trim() === 'Sessions').click()
  })
  await expect(page.getByRole('dialog', { name: 'Leave this edit?' })).toHaveCount(1)
  await confirmAction(page, 'Leave this edit?', 'Leave Without Saving')
  await expect(page.getByRole('heading', { name: 'All Clients' })).toBeVisible()
  await expect(page.locator('.sidebar nav button.active')).toHaveCount(1)
  await expect(page.locator('.content')).not.toHaveClass(/edit-active/)
})

test('owner can edit session details and add a locked blank exercise at the top', async ({ page }) => {
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '02 Sept 2026', status: 'planned' })

  const overview = page.locator('.session-overview-panel')
  const overviewEdit = overview.getByRole('button', { name: 'Edit', exact: true })
  const plan = page.locator('.exercise-plan-panel')
  const planEdit = plan.getByRole('button', { name: 'Edit exercise plan', exact: true })
  const outcomePanel = page.locator('.session-outcome-panel')
  const summaryPanel = page.locator('.client-summary-panel')
  const outcomeEdit = outcomePanel.getByRole('button', { name: 'Edit', exact: true })
  const summaryEdit = summaryPanel.getByRole('button', { name: 'Edit', exact: true })
  const editButtons = [overviewEdit, planEdit, outcomeEdit, summaryEdit]
  const editPanels = [overview, plan, outcomePanel, summaryPanel]
  const editBoxes = await Promise.all(editButtons.map(button => button.boundingBox()))
  const panelBoxes = await Promise.all(editPanels.map(panel => panel.boundingBox()))
  const editHeights = editBoxes.map(box => box.height)
  const rightInsets = editBoxes.map((box, index) =>
    panelBoxes[index].x + panelBoxes[index].width - box.x - box.width
  )

  expect(Math.max(...editHeights) - Math.min(...editHeights)).toBeLessThanOrEqual(1)
  expect(Math.max(...rightInsets) - Math.min(...rightInsets)).toBeLessThanOrEqual(1)

  if (page.viewportSize().width <= 780) {
    const headingBox = await overview.getByRole('heading', { name: 'Session Overview' }).boundingBox()
    const statusesBox = await overview.getByLabel('Session status summary').boundingBox()
    expect(statusesBox.y).toBeGreaterThanOrEqual(headingBox.y + headingBox.height)
  }

  await overviewEdit.click()
  await expect(overview).toHaveClass(/editing-section/)
  await expect(page.locator('.content')).toHaveClass(/edit-active/)
  await expect(page.getByRole('button', { name: 'Export Summary' })).toBeDisabled()
  await expect(overview.getByRole('button', { name: 'Save', exact: true })).toHaveCSS('pointer-events', 'auto')
  await expect(overview.getByRole('button', { name: 'View Client' })).toHaveCount(0)
  await expect(overview.getByRole('button', { name: 'View Trainer' })).toHaveCount(0)
  await expect(overview.getByRole('button', { name: 'Save', exact: true })).toBeVisible()
  await expect(overview.getByRole('button', { name: 'Cancel', exact: true })).toBeVisible()
  await page.getByLabel('Session date').fill('2026-09-03')
  await overview.getByRole('button', { name: 'Save', exact: true }).click()
  await confirmAction(page, 'Save session details?', 'Save Changes')
  await expect(page.getByText(/Thursday,/).first()).toBeVisible()

  await plan.getByRole('button', { name: 'Edit exercise plan', exact: true }).click()
  await plan.getByRole('button', { name: 'Add Exercise' }).click()

  const rows = plan.locator('.exercise-editor-row')
  await expect(rows.first()).toHaveClass(/pending/)
  await expect(rows.first().getByLabel('Exercise 1 name')).toContainText('Select exercise')
  await expect(rows.first().getByLabel('Exercise 1 reps')).toHaveValue('8')
  await expect(rows.first().getByLabel('Exercise 1 rounds')).toHaveValue('2')
  await expect(rows.first().getByLabel('Exercise 1 rest')).toHaveValue('60 sec')
  await expect(plan.getByRole('button', { name: 'Add Exercise' })).toBeDisabled()
  await expect(plan.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()

  await rows.first().getByLabel('Exercise 1 name').click()
  await rows.first().getByRole('button', { name: 'Walking lunges', exact: true }).click()
  await expect(plan.getByRole('button', { name: 'Add Exercise' })).toBeEnabled()
  await expect(plan.getByRole('button', { name: 'Save', exact: true })).toBeEnabled()
})

test('trainer session details use two request actions instead of owner Edit', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '02 Sept 2026', status: 'planned' })

  const overview = page.locator('.session-overview-panel')
  await expect(overview.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0)
  await expect(overview.getByRole('button', { name: 'Request Time Change' })).toBeVisible()
  await expect(overview.getByRole('button', { name: 'Request Trainer Change' })).toBeVisible()

  await overview.getByRole('button', { name: 'Request Time Change' }).click()
  const dialog = page.getByRole('dialog', { name: 'Request Time Change' })
  await expect(dialog.getByLabel('Requested session date')).toHaveAttribute('min', '2026-09-02')
  await dialog.getByLabel('Requested session date').fill('2026-09-01')
  await expect(dialog.getByRole('button', { name: 'Review Request' })).toBeDisabled()
  await expect(dialog.getByRole('alert')).toContainText('in the future')
  await dialog.getByLabel('Requested session date').fill('2026-09-02')
  await dialog.getByLabel('Requested start time').fill('12:00')
  await expect(dialog.getByRole('button', { name: 'Review Request' })).toBeDisabled()
  await dialog.getByLabel('Requested start time').fill('18:00')
  await dialog.getByLabel('Requested session date').fill('2026-09-04')
  await dialog.getByRole('button', { name: 'Review Request' }).click()
  await confirmAction(page, 'Submit time-change request?', 'Submit Request')
  await expect(page.getByRole('status')).toContainText('owner approval')
  await expect(page.getByText(/Wednesday,/).first()).toBeVisible()
  await overview.getByRole('button', { name: 'Request Time Change' }).click()
  await dialog.getByLabel('Requested session date').fill('2026-09-05')
  await dialog.getByRole('button', { name: 'Review Request' }).click()
  await page.clock.setFixedTime(new Date('2026-09-02T10:00:00Z'))
  await confirmAction(page, 'Submit time-change request?', 'Submit Request')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('alert')).toContainText('before the session starts')
  await expect(dialog.getByRole('button', { name: 'Review Request' })).toBeDisabled()
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(overview.getByRole('button', { name: 'Request Time Change' })).toBeDisabled()
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('fitfinity-m2-demo-db-v4')).messages.filter(message => message.request?.type === 'session_time' && message.request.sessionId === 's1').length)).toBe(1)
})

test('normal acknowledgement completes session and records one debit state', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')

  await openSession(page, { date: '02 Sept 2026', status: 'planned' })
  await page.getByRole('button', { name: 'Client Signature' }).click()
  let acknowledgement = page.getByRole('dialog', { name: 'Client signature' })
  await acknowledgement.getByRole('button', { name: 'Close dialog' }).click()
  await expect(acknowledgement).toHaveCount(0)
  await page.getByRole('button', { name: 'Client Signature' }).click()
  acknowledgement = page.getByRole('dialog', { name: 'Client signature' })
  await acknowledgement.getByLabel('Acknowledgement note').fill('Session completed as planned.')
  await drawClientSignature(page)
  await acknowledgement.getByRole('button', { name: 'Review Completion' }).click()
  await confirmAction(page, 'Complete this session?', 'Complete Session')

  await expect(page.getByText('Session · Completed', { exact: true })).toBeVisible()
  await expect(page.getByText('WhatsApp · Not opened', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Update Completion' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Client Signature', exact: true })).toHaveCount(0)
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('fitfinity-m2-demo-db-v4')))
  const session = saved.sessions.find(item => item.id === 's1')
  expect(session.whatsappOpenedAt).toBeFalsy()
  expect(session.acknowledgementHistory).toEqual([session.acknowledgement])
  await expect(page.getByLabel('Acknowledgement history').locator('time')).toHaveAttribute('datetime', session.acknowledgement.recordedAt)
  expect(saved.packageCreditTransactions.filter(item => item.sessionId === 's1')).toHaveLength(1)
})

test('trainer no-show completes without signature and correction preserves its timestamped history and single debit', async ({ page }) => {
  await selectDemoIdentity(page, 'u-marcus')
  await clickNav(page, 'Sessions')

  await openSession(page, { date: '02 Sept 2026', status: 'planned' })
  await page.getByRole('button', { name: 'Client Signature' }).click()
  await page.getByRole('dialog', { name: 'Client signature' })
    .getByRole('button', { name: 'Record late / no-show instead' }).click()

  const conversion = page.getByRole('dialog', { name: 'Trainer late / no-show' })
  await expect(conversion.getByLabel('Client name')).toHaveCount(0)
  await conversion.getByLabel('Acknowledgement note').fill('No-show selected by mistake')
  await conversion.getByRole('button', { name: 'Review Completion' }).click()
  await confirmAction(page, 'Complete this session?', 'Complete Session')

  await expect(page.getByText('Session · Completed', { exact: true })).toBeVisible()
  await expect(page.getByText('WhatsApp · Not opened', { exact: true })).toBeVisible()
  const noShow = await page.evaluate(() => JSON.parse(localStorage.getItem('fitfinity-m2-demo-db-v4')).sessions.find(item => item.id === 's1').acknowledgement)
  await page.clock.setFixedTime(new Date('2026-09-02T04:10:00Z'))
  await page.reload()
  await page.getByRole('button', { name: 'Correct to Client Signature' }).click()
  const signing = page.getByRole('dialog', { name: 'Client signature' })
  await expect(signing.getByRole('button', { name: 'Review Completion' })).toBeDisabled()
  await expect(signing.getByRole('button', { name: 'Record late / no-show instead' })).toHaveCount(0)
  await expect(signing.getByLabel('Acknowledgement note')).toHaveValue('')
  await drawClientSignature(page)
  await signing.getByRole('button', { name: 'Review Completion' }).click()
  await confirmAction(page, 'Complete this session?', 'Complete Session')
  // No-show is already Completed. Wait for the saved correction before reload.
  await expect(page.getByRole('button', { name: 'View Client Signature', exact: true })).toBeVisible()
  await expect(page.getByLabel('Acknowledgement history').getByRole('listitem')).toHaveCount(2)
  await expect(page.getByLabel('Acknowledgement history').locator('time').nth(1)).toHaveAttribute('datetime', '2026-09-02T04:10:00.000Z')
  await expect(page.getByText('Session · Completed', { exact: true })).toBeVisible()
  await expect(page.getByText('WhatsApp · Not opened', { exact: true })).toBeVisible()
  await page.reload()
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('fitfinity-m2-demo-db-v4')))
  const session = saved.sessions.find(item => item.id === 's1')
  expect(session.acknowledgementHistory).toEqual([noShow, session.acknowledgement])
  expect(session.acknowledgement.recordedAt).toBe('2026-09-02T04:10:00.000Z')
  expect(session.acknowledgement.recordedBy).toEqual({ id: 'u-marcus', name: 'Marcus Tan', role: 'trainer' })
  const history = page.getByLabel('Acknowledgement history')
  await expect(history.getByRole('listitem')).toHaveCount(2)
  await expect(history).toContainText('No-show selected by mistake')
  await expect(history).toContainText('Corrected to client signature')
  await expect(history.locator('time').nth(0)).toHaveAttribute('datetime', noShow.recordedAt)
  await expect(history.locator('time').nth(1)).toHaveAttribute('datetime', session.acknowledgement.recordedAt)
  await expect(page.getByRole('button', { name: 'Update Completion' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Correct to Client Signature' })).toHaveCount(0)
  expect(saved.packageCreditTransactions.filter(item => item.sessionId === 's1')).toHaveLength(1)
})

test('Sessions defaults to Upcoming and All stays newest-first after detail Back for both roles', async ({ page }) => {
  for (const user of ['u-owner', 'u-marcus']) {
    if (user === 'u-marcus') await selectDemoIdentity(page, user)
    await clickNav(page, 'Sessions')
    const period = page.getByLabel('Filter sessions by period')
    const search = page.getByLabel('Search sessions')
    const rows = page.getByLabel('Session list').locator('.session-list-row')
    await expect(period).toHaveValue('upcoming')
    await expect(search).toHaveValue('')
    await search.fill('Amanda')
    await expect(rows).toHaveCount(9)
    await expect(rows.locator('.session-date-cell .compact-primary')).toHaveText([
      /02 Sep(?:t)? 2026/, /07 Sep(?:t)? 2026/, /17 Sep(?:t)? 2026/,
      /24 Sep(?:t)? 2026/, '01 Oct 2026', '08 Oct 2026', '15 Oct 2026', '22 Oct 2026', '29 Oct 2026',
    ])
    await period.selectOption('all')
    await expect(rows).toHaveCount(10)
    await expect(rows.locator('.session-date-cell .compact-primary')).toHaveText([
      '29 Oct 2026', '22 Oct 2026', '15 Oct 2026', '08 Oct 2026', '01 Oct 2026',
      /24 Sep(?:t)? 2026/, /17 Sep(?:t)? 2026/, /07 Sep(?:t)? 2026/, /02 Sep(?:t)? 2026/, '29 Aug 2026',
    ])
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(rows.locator('.session-date-cell .compact-primary')).toHaveText(['04 Aug 2026', '02 Aug 2026'])
    await rows.first().getByRole('button', { name: /View session/ }).click()
    await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await expect(page).toHaveURL(/#\/sessions$/)
    await expect(period).toHaveValue('all')
    await expect(search).toHaveValue('Amanda')
    await expect(page.getByLabel('List pages')).toContainText('Page 2')
    await expect(rows.locator('.session-date-cell .compact-primary')).toHaveText(['04 Aug 2026', '02 Aug 2026'])
  }
})

test('client and trainer profiles use the shared pink initials avatar', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()
  await expect(page.locator('.profile-avatar')).toHaveText('AL')
  await expectStandardSectionHeadings(page)
  const clientName = await page.getByRole('heading', { name: 'Amanda Lim' }).boundingBox()
  const clientStatus = await page.getByLabel('Client status').boundingBox()
  expect(clientStatus.x).toBeGreaterThan(clientName.x + clientName.width)

  await page.getByRole('button', { name: 'Back' }).click()
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()
  await expect(page.locator('.profile-avatar')).toHaveText('MT')
  await expectStandardSectionHeadings(page)
})

test('tablet and desktop profile name cards and navigation stay in single rows', async ({ page }) => {
  const viewport = page.viewportSize()
  if (viewport.width < 700) return

  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const avatarBox = await page.locator('.profile-avatar').boundingBox()
  const nameBox = await page.getByRole('heading', { name: 'Amanda Lim' }).boundingBox()
  expect(avatarBox).not.toBeNull()
  expect(nameBox).not.toBeNull()
  expect(Math.abs((avatarBox.y + avatarBox.height / 2) - (nameBox.y + nameBox.height / 2))).toBeLessThanOrEqual(16)

  await expect(page.locator('.profile-menu>summary')).toBeHidden()
  const tabs = page.locator('.profile-menu .profile-tabs button')
  const tabBoxes = await tabs.evaluateAll(elements => elements.map(element => element.getBoundingClientRect().top))
  expect(Math.max(...tabBoxes) - Math.min(...tabBoxes)).toBeLessThanOrEqual(2)

  await page.getByRole('button', { name: 'Back' }).click()
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()
  await expect(page.locator('.profile-menu>summary')).toBeHidden()
  const trainerTabBoxes = await page.locator('.profile-menu .profile-tabs button')
    .evaluateAll(elements => elements.map(element => element.getBoundingClientRect().top))
  expect(Math.max(...trainerTabBoxes) - Math.min(...trainerTabBoxes)).toBeLessThanOrEqual(2)
})

test('client profile navigation tabs contain package session and progress data', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  await clickProfileTab(page, 'Package')
  await expect(page.getByRole('heading', { name: 'Current Package' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Past Packages' })).toBeVisible()
  await expect(page.locator('.client-record-row')).toHaveCount(2)
  await expect(page.getByText('19 / 90 days')).toBeVisible()
  await expect(page.getByText('Once weekly')).toBeVisible()

  await clickProfileTab(page, 'Session History')
  await expect(page.getByLabel('Session History').locator('.client-record-row')).toHaveCount(3)

  await clickProfileTab(page, 'Upcoming Sessions')
  await expect(page.getByLabel('Upcoming Sessions').locator('.client-record-row')).toHaveCount(9)
  await expect(page.getByLabel('Upcoming Sessions')).toContainText('Session 12 / 12')

  await clickProfileTab(page, 'Progress')
  await expect(page.getByRole('heading', { name: 'Strength Progress' })).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export Progress Report' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('amanda-lim-progress-report.pdf')
  const reportStream = await download.createReadStream()
  const reportChunks = []
  for await (const chunk of reportStream) reportChunks.push(chunk)
  const reportPdf = Buffer.concat(reportChunks).toString('latin1')
  expect(reportPdf).toMatch(/^%PDF-1\.4\n/)
  expect(reportPdf).toContain('/Count 9 /Kids')
  expect(reportPdf.match(/\/Subtype \/Image/g)).toHaveLength(9)
  expect(reportPdf).toMatch(/%%EOF\n$/)
  await expect(page.getByRole('button', { name: 'Share Progress Report via WhatsApp' })).toBeEnabled()
  // Six imported baseline exercises plus the three exercises in Amanda's signed session.
  await expect(page.getByLabel('Strength progress exercise').locator('option')).toHaveText([
    'Smith back squat', 'Leg press', 'Smith chest press', 'Seated row',
    'DB shoulder press (incline bench and flat bench)', 'Smith deadlift',
    'Goblet Squat', 'Seated Cable Row', 'DB Chest Press',
  ])
  await expect(page.locator('.strength-progress-cards button')).toHaveCount(9)
  await expect(page.getByRole('img', { name: 'Smith back squat load progress chart' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Completed Sessions' })).toHaveCount(0)

  if (page.viewportSize().width <= 620) {
    const exportBox = await page.getByRole('button', { name: 'Export Progress Report' }).boundingBox()
    const titleBox = await page.getByRole('heading', { name: 'Strength Progress' }).boundingBox()
    expect(Math.abs(exportBox.width - exportBox.height)).toBeLessThanOrEqual(1)
    expect(exportBox.x).toBeGreaterThan(titleBox.x)
  }

  if (page.viewportSize().width > 900) {
    const progressHead = await page.locator('.strength-progress-head').boundingBox()
    const exerciseFilter = await page.getByLabel('Strength progress exercise').boundingBox()
    const headCentre = progressHead.x + progressHead.width / 2
    const filterCentre = exerciseFilter.x + exerciseFilter.width / 2
    expect(Math.abs(headCentre - filterCentre)).toBeLessThanOrEqual(2)
  }
})

test('client contact editing uses structured phone and emergency fields', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  await expect(page.getByText('Package validity', { exact: true })).toHaveCount(0)
  const general = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information' }) })
  const schedule = page.locator('.schedule-panel')
  const [generalBox, scheduleBox] = await Promise.all([general.boundingBox(), schedule.boundingBox()])
  expect(scheduleBox.y).toBeGreaterThanOrEqual(generalBox.y + generalBox.height - 2)

  if (page.viewportSize().width >= 700) {
    const rowTops = await general.locator('.profile-info-grid .info-row').evaluateAll(elements =>
      elements.map(element => Math.round(element.getBoundingClientRect().top))
    )
    expect(rowTops).toHaveLength(8)
    for (let index = 0; index < rowTops.length; index += 2) {
      expect(Math.abs(rowTops[index] - rowTops[index + 1])).toBeLessThanOrEqual(2)
    }
    expect(rowTops[2]).toBeGreaterThan(rowTops[0])
    expect(rowTops[4]).toBeGreaterThan(rowTops[2])
    expect(rowTops[6]).toBeGreaterThan(rowTops[4])

    const gridBox = await general.locator('.profile-info-grid').boundingBox()
    const emergencyBox = await general.locator('.emergency-contact-row').boundingBox()
    expect(emergencyBox.width).toBeLessThan(gridBox.width * 0.75)
  }
  await general.getByRole('button', { name: 'Edit', exact: true }).click()

  const phoneCode = general.getByLabel('Phone country extension')
  const phoneNumber = general.getByLabel('Phone number', { exact: true })
  await expectSameRow([phoneCode, phoneNumber])
  await expect(general.getByLabel('Emergency contact relationship')).toBeVisible()
  await expectSameRow([
    general.getByLabel('Emergency contact country extension'),
    general.getByLabel('Emergency contact phone number'),
  ])
  const genderPreference = general.getByLabel('Gender preference')
  await expect(genderPreference).toBeVisible()
  await genderPreference.selectOption('Female trainer preferred')
  await general.getByRole('button', { name: 'Save', exact: true }).click()
  await confirmAction(page, 'Save client information?', 'Save Changes')
  await expect(general.getByText('Female trainer preferred', { exact: true })).toBeVisible()
})

test('trainer assigned clients provide search and package filters', async ({ page }) => {
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()
  await clickProfileTab(page, 'Assigned Clients')

  const search = page.getByLabel('Search assigned clients')
  await expect(search).toBeVisible()
  await expect(page.getByLabel('Filter assigned clients by type')).toBeVisible()
  await expect(page.getByLabel('Filter assigned clients by frequency')).toBeVisible()
  await expectSameHeight([
    search,
    page.getByLabel('Filter assigned clients by type'),
    page.getByLabel('Filter assigned clients by frequency'),
  ])
  expect(await page.getByLabel('Assigned client list').locator('.quick-row').count()).toBeLessThanOrEqual(10)
  await search.fill('Amanda')
  await expect(page.getByText('Amanda Lim', { exact: true })).toBeVisible()
})

test('substantial demo lists enforce ten items per page', async ({ page }) => {
  await clickNav(page, 'Clients')
  await expect(page.getByLabel('Client list').locator('.compact-list-row')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Next' })).toBeEnabled()

  await clickNav(page, 'Trainers')
  await expect(page.getByLabel('Trainer list').locator('.compact-list-row')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Next' })).toBeEnabled()

  await clickNav(page, 'Sessions')
  await expect(page.getByLabel('Session list').locator('.session-list-row')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Next' })).toBeEnabled()

  await clickMessages(page)
  await expect(page.getByLabel('Message list').locator('.message-title-row')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Next' })).toBeEnabled()
})

test('Sessions reuses the compact Client-list structure', async ({ page }) => {
  await clickNav(page, 'Sessions')
  const sessionFilters = page.locator('.session-controls')
  await expect(page.locator('.session-compact-list.compact-list')).toBeVisible()
  await expect(page.getByLabel('Session list').locator('.compact-list-row').first()).toBeVisible()
  await expect(page.getByLabel('Search sessions')).toBeVisible()
  await expect(sessionFilters.getByText('Select start date', { exact: true })).toBeVisible()
  await expect(sessionFilters.getByText('Select end date', { exact: true })).toBeVisible()
  await expectSameHeight([
    page.getByLabel('Search sessions'),
    page.getByLabel('Filter sessions by period'),
    page.getByLabel('Filter sessions by status'),
    sessionFilters.locator('.date-filter-control').nth(0),
    sessionFilters.locator('.date-filter-control').nth(1),
  ])

  const searchBox = await page.getByLabel('Search sessions').boundingBox()
  const periodBox = await page.getByLabel('Filter sessions by period').boundingBox()
  const statusBox = await page.getByLabel('Filter sessions by status').boundingBox()
  const fromBox = await sessionFilters.locator('.date-filter-control').nth(0).boundingBox()
  const toBox = await sessionFilters.locator('.date-filter-control').nth(1).boundingBox()
  expect(searchBox.y + searchBox.height).toBeLessThanOrEqual(periodBox.y)

  if (page.viewportSize().width > 900) {
    expect(Math.max(periodBox.y, statusBox.y, fromBox.y, toBox.y) - Math.min(periodBox.y, statusBox.y, fromBox.y, toBox.y)).toBeLessThanOrEqual(1)
    expect(Math.max(periodBox.width, statusBox.width, fromBox.width, toBox.width) - Math.min(periodBox.width, statusBox.width, fromBox.width, toBox.width)).toBeLessThanOrEqual(1)
    const filterBoxes = [periodBox, statusBox, fromBox, toBox]
    for (let index = 0; index < filterBoxes.length - 1; index += 1) {
      expect(filterBoxes[index].x + filterBoxes[index].width).toBeLessThanOrEqual(filterBoxes[index + 1].x)
    }
  } else {
    expect(Math.abs(periodBox.y - statusBox.y)).toBeLessThanOrEqual(1)
    expect(Math.abs(fromBox.y - toBox.y)).toBeLessThanOrEqual(1)
    expect(fromBox.y).toBeGreaterThanOrEqual(periodBox.y + periodBox.height)
    expect(periodBox.x + periodBox.width).toBeLessThanOrEqual(statusBox.x)
    expect(fromBox.x + fromBox.width).toBeLessThanOrEqual(toBox.x)
  }

  await page.getByLabel('Sessions from date').fill('2026-09-02')
  await page.getByLabel('Sessions to date').fill('2026-09-02')
  await expect(sessionFilters.getByText('Select start date', { exact: true })).toHaveCount(0)
  await expect(sessionFilters.getByText('Select end date', { exact: true })).toHaveCount(0)
  const rows = page.getByLabel('Session list').locator('.session-list-row')
  await expect(rows).toHaveCount(1)
  await expect(rows).toContainText(/02 Sep(?:t)? 2026/)
})

test('Sessions removes row status and keeps one compact View column', async ({ page }) => {
  await clickNav(page, 'Sessions')
  const action = page.getByLabel('Session list').locator('.session-action-cell').first()
  const view = action.getByRole('button', { name: /View session/ })
  await expect(action.locator('.status-badge')).toHaveCount(0)
  await expect(view).toBeVisible()
  await expect(page.getByLabel('Session list').getByText('Status / View', { exact: true })).toHaveCount(0)
  const columns = await action.locator('..').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length)
  expect(columns).toBe(3)
})

test('Session Details follows the approved internal section order', async ({ page }) => {
  await clickNav(page, 'Sessions')
  await openSession(page, { date: '02 Sept 2026', status: 'planned' })

  await expect(page.getByRole('heading', { name: 'Session Details' })).toHaveCount(0)
  await expect(page.locator('.page-head .eyebrow')).toHaveCount(0)
  await expect(page.getByLabel('Session status summary')).toBeVisible()
  await expect(page.locator('.session-status-card')).toHaveCount(0)
  await expect(page.locator('.session-identity-card')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'View Client' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'View Trainer' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Exercise Plan' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Session Outcome' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Client-Facing Summary' })).toBeVisible()
  await expect(page.locator('.panel h2')).toHaveText(['Session Overview', 'Exercise Plan', 'Session Outcome', 'Client-Facing Summary', 'Acknowledgement'])
  const exportSummary = page.getByRole('button', { name: 'Export Summary' })
  await expect(exportSummary).toBeVisible()
  await exportSummary.click()
  const exportDialog = page.getByRole('dialog', { name: 'Export Summary' })
  await expect(exportDialog.getByRole('button', { name: 'Continue to WhatsApp' })).toBeVisible()
  await expect(exportDialog.locator('legend')).toHaveText(['Selected Videos', 'Select Client Facing Summary'])
  await expect(exportDialog.getByRole('group', { name: 'Selected Videos' }).getByRole('checkbox')).toHaveCount(0)
  await expect(exportDialog.getByRole('checkbox', { name: 'Include Client-Facing Summary' })).toBeChecked()
  await expect(exportDialog).toContainText('No videos')
  await expect(exportDialog.locator('.helper, .notice')).toHaveCount(0)
  await exportDialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('heading', { name: 'Session Overview' })).toBeVisible()
  await expect(page.locator('.session-overview-item')).toHaveCount(4)
  await expectStandardSectionHeadings(page)

  const factLabels = await page.locator('.session-fact-label').allTextContents()
  expect(factLabels).toEqual(['Client', 'Trainer', 'Date & time', 'Package details'])

  const clientName = await page.getByText('Amanda Lim', { exact: true }).first().boundingBox()
  const viewClient = await page.getByRole('button', { name: 'View Client' }).boundingBox()
  expect(Math.abs((clientName.y + clientName.height / 2) - (viewClient.y + viewClient.height / 2))).toBeLessThanOrEqual(4)

  const title = await page.getByRole('heading', { name: 'Session Overview' }).boundingBox()
  const statuses = await page.getByLabel('Session status summary').boundingBox()
  if (page.viewportSize().width <= 780) {
    expect(statuses.y).toBeGreaterThanOrEqual(title.y + title.height)
  } else {
    expect(statuses.x).toBeGreaterThan(title.x)
  }
})
