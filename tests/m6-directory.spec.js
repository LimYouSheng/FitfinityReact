import { directoryData } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function profileTab(page, name) {
  const menu = page.locator('details.profile-menu')
  const button = menu.getByRole('button', { name, exact: true })
  if (!(await button.isVisible())) await menu.locator('summary').click()
  await button.click()
}
async function openDirectory(page, staffApi) {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  staffApi.state.directory = directoryData()
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
}

test('API directory searches clients and opens purchased terms with working Back', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Clients', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add New Client' })).toHaveCount(0)
  await page.getByLabel('Search client', { exact: true }).fill('API Client')
  await page.getByRole('button', { name: 'View API Client', exact: true }).click()
  await expect(page.getByText('client@fixture.test', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Health & Assessments' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0)
  await profileTab(page, 'Package')
  await expect(page.getByText('Purchased Twelve', { exact: true })).toBeVisible()
  await expect(page.getByLabel('25% package used')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add Package' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Back', exact: true }).click()
  await expect(page.getByLabel('Search client', { exact: true })).toHaveValue('API Client')
})

test('API trainer and package pages show stored data with mutation controls unavailable', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  await page.getByRole('button', { name: 'View Trainers', exact: true }).click()
  await page.getByRole('button', { name: 'View API Trainer', exact: true }).click()
  await expect(page.getByText('$80 / session', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0)
  await profileTab(page, 'Availability')
  await expect(page.getByText('10:00am–11:00am', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Home', exact: true }).click()
  await page.getByRole('button', { name: 'View Packages', exact: true }).click()
  await page.getByRole('button', { name: 'View package Current Template', exact: true }).click()
  await expect(page.getByText('180 days', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit Package', exact: true })).toHaveCount(0)
})

test('API empty purchase and interrupted refresh never become fabricated or cached records', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.clients[0].purchases = []
  await page.reload()
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await page.getByRole('button', { name: 'View API Client', exact: true }).click()
  await profileTab(page, 'Package')
  await expect(page.getByText('No active current package.', { exact: true })).toBeVisible()
  staffApi.state.unavailable = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'API Client' })).toHaveCount(0)
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'API Client' })).toBeVisible()
  const saved = await page.evaluate(() => JSON.stringify({ local: localStorage, session: sessionStorage }))
  expect(saved).not.toContain('client@fixture.test')
  expect(saved).not.toContain('91234568')
  await page.getByRole('button', { name: 'Home', exact: true }).click()
  await page.getByRole('button', { name: 'Sign Out', exact: true }).click()
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
})
