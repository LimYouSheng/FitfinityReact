import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function packageTab(page) {
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
  const menu = page.locator('details.profile-menu')
  if (await menu.locator('summary').isVisible() && await menu.getAttribute('open') === null) await menu.locator('summary').click()
  await menu.getByRole('button', { name: 'Package', exact: true }).click()
}
async function openPackage(page, staffApi, role = 'owner') {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.user = { ...state.user, role, ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  state.directory = { ...directoryData(), viewerId: state.user.id, packageReactivationWrites: true, personalMessages: true }
  state.messageRecords = []
  if (role === 'admin') { delete state.directory.trainers[0].peak_rate_cents; delete state.directory.trainers[0].off_peak_rate_cents }
  if (role === 'trainer') state.directory.packages = []
  state.directory.clients[0].purchases[0].status = 'inactive'
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/clients/${directoryId(7)}`)
  await packageTab(page)
}
const dialogFor = page => page.getByRole('dialog', { name: 'Reactivate Package?', exact: true })
const confirm = page => dialogFor(page).getByRole('button', { name: 'Reactivate Package', exact: true }).click()
async function restored(page) {
  await expect(page.getByRole('heading', { name: 'Current Package', exact: true }).locator('..')).toContainText('Purchased Twelve')
  await expect(page.getByRole('button', { name: 'Reactivate Package', exact: true })).toHaveCount(0)
}
for (const role of ['owner', 'admin']) test(`API ${role} restores a single package and persists the original terms after reload`, async ({ page, staffApi }) => {
  await openPackage(page, staffApi, role)
  staffApi.state.packageReactivationConflict = true
  const before = structuredClone(staffApi.state.directory.clients[0])
  await page.getByRole('button', { name: 'Reactivate Package', exact: true }).click()
  const dialog = dialogFor(page)
  await expect(dialog.getByRole('button', { name: 'Reactivate Package', exact: true })).toBeDisabled()
  await dialog.getByRole('textbox', { name: /Session 1/ }).fill('2026-09-08')
  await expect(dialog.getByRole('button', { name: 'Reactivate Package', exact: true })).toBeEnabled()
  await confirm(page)
  await restored(page)
  const client = staffApi.state.directory.clients[0]
  expect(client.status).toBe(before.status)
  expect(client.trainer_id).toBe(before.trainer_id)
  expect(client.people).toEqual(before.people)
  expect(client.purchases[0]).toEqual({ ...before.purchases[0], status: 'active', version: before.purchases[0].version + 1 })
  await page.reload()
  await packageTab(page)
  await restored(page)
  expect(staffApi.state.packageReactivationAttempts).toHaveLength(1)
})
test('API package restoration reconciles a committed interrupted response without a second POST', async ({ page, staffApi }) => {
  await openPackage(page, staffApi)
  staffApi.state.packageReactivationUnknown = true
  await page.getByRole('button', { name: 'Reactivate Package', exact: true }).click()
  await confirm(page)
  await dialogFor(page).getByRole('button', { name: 'Check Reactivation', exact: true }).click()
  await restored(page)
  expect(staffApi.state.packageReactivationAttempts).toHaveLength(1)
})
test('API package restoration retains an absent receipt through refresh for explicit identical retry', async ({ page, staffApi }) => {
  await openPackage(page, staffApi)
  staffApi.state.packageReactivationAbsentUnknown = true
  await page.getByRole('button', { name: 'Reactivate Package', exact: true }).click()
  await confirm(page)
  await expect(dialogFor(page).getByRole('alert')).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Check Package Reactivation', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Check Reactivation', exact: true }).click()
  await packageTab(page)
  await restored(page)
  const attempts = staffApi.state.packageReactivationAttempts
  expect(attempts).toHaveLength(2)
  expect(attempts[0]).toEqual(attempts[1])
})
test('API confirmed package restoration survives a failed follow-up refresh', async ({ page, staffApi }) => {
  await openPackage(page, staffApi)
  staffApi.state.packageReactivationRefreshFailure = true
  await page.getByRole('button', { name: 'Reactivate Package', exact: true }).click()
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await packageTab(page)
  await restored(page)
  expect(staffApi.state.packageReactivationAttempts).toHaveLength(1)
})
test('API assigned Trainer cannot restore a package', async ({ page, staffApi }) => {
  await openPackage(page, staffApi, 'trainer')
  await expect(page.getByRole('button', { name: 'Reactivate Package', exact: true })).toHaveCount(0)
  expect(staffApi.state.packageReactivationAttempts ?? []).toHaveLength(0)
})
