import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/#/dashboard')
})

test('owner can open client profile with v0.57 overview order', async ({ page }) => {
  await page.getByRole('button', { name: 'Clients', exact: true }).click()
  await page.getByRole('button', { name: 'View' }).first().click()
  const headings = await page.locator('main.content h2').allTextContents()
  expect(headings.slice(0, 4)).toEqual(['General Information', 'Fixed Weekly Schedule', 'Health / Limitation Notes', 'Remarks'])
})

test('approval-needed checkbox is checked when supervised', async ({ page }) => {
  await page.getByRole('button', { name: 'Trainers', exact: true }).click()
  await page.getByRole('button', { name: 'View' }).first().click()
  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(page.getByLabel('Session time changes')).toBeChecked()
})

test('trainer role only sees assigned clients', async ({ page }) => {
  await page.locator('.role-switcher select').selectOption('u-marcus')
  await page.getByRole('button', { name: 'Clients', exact: true }).click()
  await expect(page.getByText('Amanda Lim')).toBeVisible()
  await expect(page.getByText('Daniel & Mei Wong')).toHaveCount(0)
})
