import { expect, test } from '@playwright/test'

async function selectSection(page, label) {
  const menu = page.locator('.profile-menu')
  const summary = menu.locator('summary')
  const collapsedLayout = await summary.isVisible()
  if (collapsedLayout) await summary.click()
  await menu.getByRole('button', { name: label, exact: true }).click()
  await expect(summary).toHaveText(label)
  await expect(menu.locator('button[aria-current="true"]')).toHaveText(label)
  if (collapsedLayout) {
    await expect(menu).not.toHaveAttribute('open')
    const bounds = await summary.boundingBox()
    expect(bounds.x).toBeGreaterThanOrEqual(0)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize().width)
  }
}

test('M3 client profile menu names the active section and respects cancelled edits', async ({ page }) => {
  await page.goto('/#/clients/c1')
  await expect(page.locator('.profile-menu summary')).toHaveText('Overview')
  for (const label of ['Package', 'Session History', 'Upcoming Sessions', 'Progress', 'Overview']) {
    await selectSection(page, label)
  }
  const information = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information', exact: true }) })
  await information.getByRole('button', { name: 'Edit', exact: true }).click()
  const summary = page.locator('.profile-menu summary')
  await page.getByRole('button', { name: 'Back', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Leave this edit?', exact: true })
  await expect(dialog).toBeVisible()
  await expect(summary).toHaveText('Overview')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(information.getByRole('button', { name: 'Save', exact: true })).toBeVisible()
  await expect(summary).toHaveText('Overview')
  await information.getByRole('button', { name: 'Cancel', exact: true }).click()
  await selectSection(page, 'Package')
})

test('M3 owner trainer menu reflects each selection and retains Assigned Clients', async ({ page }) => {
  await page.goto('/#/trainers/t1')
  for (const label of ['Availability', 'Assigned Clients', 'Monthly Activity', 'Overview']) {
    await selectSection(page, label)
    if (label === 'Assigned Clients') await expect(page.getByLabel('Assigned client list')).toContainText('Amanda Lim')
  }
})

test('M3 trainer uses All Clients and the profile menu reflects the remaining sections', async ({ page }) => {
  await page.goto('/#/dashboard')
  await page.locator('.role-switcher select').selectOption('u-marcus')
  await expect(page.getByRole('heading', { name: 'Trainer Dashboard', exact: true })).toBeVisible()
  await page.evaluate(() => { location.hash = '#/my-profile' })
  await expect(page.getByRole('heading', { name: 'Marcus Tan', exact: true })).toBeVisible()
  await expect(page.locator('.profile-menu button').filter({ hasText: 'Assigned Clients' })).toHaveCount(0)
  for (const label of ['Availability', 'Monthly Activity', 'Overview']) await selectSection(page, label)
  await page.evaluate(() => { location.hash = '#/clients' })
  await expect(page.getByRole('heading', { name: 'All Clients', exact: true })).toBeVisible()
  await page.getByLabel('Search client', { exact: true }).fill('Amanda Lim')
  await expect(page.getByLabel('Client list').getByText('Amanda Lim', { exact: true })).toBeVisible()
  await page.getByLabel('Filter clients by type').selectOption('Individual')
  await expect(page.getByLabel('Filter clients by type').locator('option:checked')).toHaveText('Individual')
  await expect(page.getByLabel('Client list').getByText('Amanda Lim', { exact: true })).toBeVisible()
})
