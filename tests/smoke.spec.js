import { test, expect } from '@playwright/test'

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

  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) {
    await expect.poll(
      async () => {
        const box = await item.boundingBox()
        const width = await page.evaluate(() => window.innerWidth)
        return Boolean(box && box.x < width && box.x + box.width > 0)
      },
      { timeout: 5000 }
    ).toBe(true)
  }

  await item.click()
}

async function expectSameRow(locators) {
  const boxes = await Promise.all(locators.map(locator => locator.boundingBox()))
  const ys = boxes.map(box => Math.round(box?.y ?? -999))
  expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(3)
}

test.beforeEach(async ({ page }) => {
  await page.goto('/#/dashboard')
})

test('dashboard remains calendar only', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Calendar' })).toBeVisible()
  await expect(page.locator('.stats-grid')).toHaveCount(0)
})

test('client filters are one compact row', async ({ page }) => {
  await clickNav(page, 'Clients')

  await expectSameRow([
    page.getByLabel('Filter clients by status'),
    page.getByLabel('Filter clients by type'),
    page.getByLabel('Filter clients by trainer'),
  ])
})

test('trainer filters are one compact row', async ({ page }) => {
  await clickNav(page, 'Trainers')

  await expectSameRow([
    page.getByLabel('Filter trainers by status'),
    page.getByLabel('Filter trainers by type'),
    page.getByLabel('Filter trainers by gender'),
  ])
})

test('trainer client filters keep same layout', async ({ page }) => {
  await page.locator('.role-switcher select').selectOption('u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await page.waitForTimeout(350)
  await clickNav(page, 'All Clients')

  const status = page.getByLabel('Filter clients by status')
  const type = page.getByLabel('Filter clients by type')
  const trainer = page.getByLabel('Filter clients by trainer')

  await expect(status).toBeDisabled()
  await expect(trainer).toBeDisabled()
  await expectSameRow([status, type, trainer])
})

test('owner can edit trainer rates', async ({ page }) => {
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()

  const ratesPanel = page.locator('.panel').filter({
    has: page.getByRole('heading', { name: 'Training & Rates' }),
  })

  await ratesPanel.getByRole('button', { name: 'Edit' }).click()
  await ratesPanel.getByLabel('Peak rate', { exact: true }).fill('85')
  await ratesPanel.getByLabel('Off-peak rate', { exact: true }).fill('60')
  await ratesPanel.getByRole('button', { name: 'Save' }).click()

  await expect(ratesPanel.getByText('$85 / session')).toBeVisible()
  await expect(ratesPanel.getByText('$60 / session')).toBeVisible()
})

test('browser back returns client detail to list', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()
  await expect(page).toHaveURL(/#\/clients\/c1$/)

  await page.goBack()
  await expect(page).toHaveURL(/#\/clients$/)
})

test('client deactivation still removes client from trainer view', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()
  await page.locator('.profile-menu summary').click()
  await page.getByRole('button', { name: 'Deactivate Client' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate Client' }).click()

  await page.locator('.role-switcher select').selectOption('u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await page.waitForTimeout(350)
  await clickNav(page, 'All Clients')

  await expect(page.getByText('Amanda Lim')).toHaveCount(0)
})

test('trainer profile uses dropdown and account status leaves rates panel', async ({ page }) => {
  await clickNav(page, 'Trainers')
  await page.getByRole('button', { name: 'View Marcus Tan' }).click()

  const headingBlock = page.getByRole('heading', { name: 'Marcus Tan' }).locator('..')
  await expect(headingBlock.getByText('Active', { exact: true })).toBeVisible()

  const ratesPanel = page.locator('.panel').filter({
    has: page.getByRole('heading', { name: 'Training & Rates' }),
  })
  await expect(ratesPanel.getByText('Account status')).toHaveCount(0)

  const menu = page.locator('.profile-menu')
  await menu.locator('summary').click()
  await expect(menu.locator('.profile-tabs button').last()).toHaveText('Deactivate Trainer')
})

test('trainer hamburger omits My Profile', async ({ page }) => {
  await page.locator('.role-switcher select').selectOption('u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await page.waitForTimeout(350)
  await openNavIfNeeded(page)

  await expect(
    page.locator('.sidebar nav').getByRole('button', { name: 'My Profile', exact: true })
  ).toHaveCount(0)
})

test('messages and remuneration appear as separate main-menu groups', async ({ page }) => {
  await openNavIfNeeded(page)
  const sidebar = page.locator('.sidebar')

  await expect(sidebar.getByText('Messages', { exact: true }).first()).toBeVisible()
  await expect(sidebar.getByText('Remuneration', { exact: true }).first()).toBeVisible()
})

test('client status is visible below name and lifecycle action is last', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const headingBlock = page.getByRole('heading', { name: 'Amanda Lim' }).locator('..')
  await expect(headingBlock.getByLabel('Client status')).toContainText('Active')

  const menu = page.locator('.profile-menu')
  await menu.locator('summary').click()
  await expect(menu.locator('.profile-tabs button').last()).toHaveText('Deactivate Client')
})

test('assigned supervised trainer can edit fixed weekly schedule and submits request', async ({ page }) => {
  await page.locator('.role-switcher select').selectOption('u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard' })).toBeVisible()
  await page.waitForTimeout(350)

  await clickNav(page, 'All Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const schedule = page.locator('.schedule-panel')
  await schedule.getByRole('button', { name: 'Edit' }).click()

  await schedule.getByLabel('Monday from').fill('18:30')
  await schedule.getByRole('button', { name: 'Save' }).click()

  await page.locator('.role-switcher select').selectOption('u-owner')
  await expect(page.getByRole('heading', { name: 'Owner Dashboard' })).toBeVisible()

  await clickNav(page, 'Messages')
  await expect(page.getByText('Fixed weekly schedule change: Amanda Lim')).toBeVisible()
})

test('message becomes read and loses blue border after opening', async ({ page }) => {
  await clickNav(page, 'Messages')

  const row = page.getByLabel('Message list').locator('.message-title-row').filter({
    hasText: 'Renewal follow-up: Nadia Koh',
  })

  await expect(
    page.getByRole('button', { name: 'Unread Renewal follow-up: Nadia Koh' })
  ).toBeVisible()

  const beforeBorder = await row.evaluate(element => getComputedStyle(element).borderTopColor)
  expect(beforeBorder).not.toBe('rgba(0, 0, 0, 0)')

  await page.getByRole('button', { name: 'Unread Renewal follow-up: Nadia Koh' }).click()

  const dialog = page.getByRole('dialog', { name: 'Renewal follow-up: Nadia Koh' })
  await expect(dialog).toBeVisible()

  await page.goBack()
  await expect(dialog).toHaveCount(0)

  await expect(
    page.getByRole('button', { name: 'Read Renewal follow-up: Nadia Koh' })
  ).toBeVisible()

  await expect.poll(async () =>
    row.evaluate(element => getComputedStyle(element).borderTopColor)
  ).toBe('rgba(0, 0, 0, 0)')
})

test('swipe back visibly moves the whole page before navigating', async ({ page }) => {
  await clickNav(page, 'Clients')
  await page.getByRole('button', { name: 'View Amanda Lim' }).click()

  const portal = page.locator('.portal-main')

  await page.evaluate(() => {
    window.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true,
      pointerId: 7,
      pointerType: 'touch',
      clientX: 5,
      clientY: 260,
      isPrimary: true,
    }))

    window.dispatchEvent(new PointerEvent('pointermove', {
      bubbles: true,
      pointerId: 7,
      pointerType: 'touch',
      clientX: 95,
      clientY: 266,
      isPrimary: true,
    }))
  })

  await expect.poll(async () =>
    portal.evaluate(element => {
      const transform = getComputedStyle(element).transform
      return transform !== 'none' && transform !== 'matrix(1, 0, 0, 1, 0, 0)'
    })
  ).toBe(true)

  await page.evaluate(() => {
    window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true,
      pointerId: 7,
      pointerType: 'touch',
      clientX: 145,
      clientY: 270,
      isPrimary: true,
    }))
  })

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

test('notification badge content is centred in a square bubble', async ({ page }) => {
  const badge = page.locator('.message-button > span').first()

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

test('dark area anywhere outside message card closes message detail', async ({ page }) => {
  await clickNav(page, 'Messages')

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

  const viewport = page.viewportSize()
  await page.mouse.click(viewport.width - 6, viewport.height - 6)

  await expect(dialog).toHaveCount(0)
})
