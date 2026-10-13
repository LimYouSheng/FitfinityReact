import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openClient(page, staffApi, role = 'owner') {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.directory = { ...directoryData(), clientDeactivationWrites: true }
  if (role !== 'owner') state.user = { ...state.user, role, id: directoryId(role === 'admin' ? 901 : 902), ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  if (role === 'admin') { delete state.directory.trainers[0].peak_rate_cents; delete state.directory.trainers[0].off_peak_rate_cents }
  if (role === 'trainer') state.directory.packages = []
  state.directory.viewerId = state.user.id
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/clients/${directoryId(7)}`)
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
}
async function clientAction(page, name) {
  const menu = page.locator('details.profile-menu')
  const summary = menu.locator('summary')
  if (await summary.isVisible() && await menu.getAttribute('open') === null) await summary.click()
  await menu.getByRole('button', { name, exact: true }).click()
}
const confirm = page => page.getByRole('dialog', { name: 'Deactivate API Client?', exact: true }).getByRole('button', { name: 'Deactivate Client', exact: true }).click()
async function retainedClient(page, staffApi) {
  await page.goto(`${staffApi.origin}/#/clients/${directoryId(7)}`)
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
  await expect(page.getByText('Inactive', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Deactivate Client', exact: true })).toHaveCount(0)
  expect(staffApi.state.directory.clients[0].purchases[0].total_sessions).toBe(12)
  expect(staffApi.state.directory.clients[0].purchases[0].used).toBe(3)
}

test('API Owner client deactivation rejects stale purchases and recovers a committed interrupted save', async ({ page, staffApi }) => {
  await openClient(page, staffApi)
  await clientAction(page, 'Deactivate Client')
  await expect(page.getByRole('dialog', { name: 'Deactivate API Client?', exact: true })).toBeVisible()
  staffApi.state.directory.clients[0].purchases[0].version++
  await confirm(page)
  await expect(page.getByRole('alert').first()).toBeVisible()
  expect(staffApi.state.clientDeactivationReceipts.size).toBe(0)
  await clientAction(page, 'Deactivate Client')
  staffApi.state.deactivationUnknown = true
  await confirm(page)
  await clientAction(page, 'Check Deactivation')
  await expect(page).toHaveURL(/#\/clients$/)
  expect(staffApi.state.clientDeactivationAttempts).toHaveLength(2)
  await page.reload()
  await retainedClient(page, staffApi)
})

test('API Admin client deactivation stays committed through a failed follow-up read', async ({ page, staffApi }) => {
  await openClient(page, staffApi, 'admin')
  await clientAction(page, 'Deactivate Client')
  staffApi.state.deactivationRefreshFailure = true
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Clients', exact: true })).toBeVisible()
  await retainedClient(page, staffApi)
  expect(staffApi.state.clientDeactivationAttempts).toHaveLength(1)
})

test('API Trainer cannot deactivate an assigned client', async ({ page, staffApi }) => {
  await openClient(page, staffApi, 'trainer')
  await expect(page.getByRole('button', { name: 'Deactivate Client', exact: true })).toHaveCount(0)
  expect(staffApi.state.clientDeactivationAttempts ?? []).toHaveLength(0)
  expect(staffApi.state.directory.clients[0].status).toBe('active')
})

test('API client deactivation retains a missing-receipt review across refresh before an identical retry', async ({ page, staffApi }) => {
  await openClient(page, staffApi)
  staffApi.state.deactivationAbsentUnknown = true
  await clientAction(page, 'Deactivate Client')
  await confirm(page)
  await expect(page.getByRole('alert').first()).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Check Client Deactivation', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Check Deactivation', exact: true }).click()
  await expect(page.getByText('Inactive', { exact: true }).first()).toBeVisible()
  await retainedClient(page, staffApi)
  const [first, second] = staffApi.state.clientDeactivationAttempts
  expect(second).toEqual(first)
  expect(staffApi.state.clientDeactivationAttempts).toHaveLength(2)
})
