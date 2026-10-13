import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openClient(page, staffApi, role = 'owner') {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.directory = { ...directoryData(), clientReactivationWrites: true }
  if (role !== 'owner') state.user = { ...state.user, role, id: directoryId(role === 'admin' ? 901 : 902), ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  if (role === 'admin') { delete state.directory.trainers[0].peak_rate_cents; delete state.directory.trainers[0].off_peak_rate_cents }
  if (role === 'trainer') state.directory.packages = []
  state.directory.viewerId = state.user.id
  state.directory.clients[0].status = 'inactive'
  for (const purchase of state.directory.clients[0].purchases) purchase.status = 'inactive'
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
const confirm = page => page.getByRole('dialog', { name: 'Reactivate API Client?', exact: true }).getByRole('button', { name: 'Reactivate Client', exact: true }).click()
async function retainedClient(page, staffApi) {
  await page.goto(`${staffApi.origin}/#/clients/${directoryId(7)}`)
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
  await expect(page.getByText('Active', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reactivate Client', exact: true })).toHaveCount(0)
  expect(staffApi.state.directory.clients[0].purchases[0].total_sessions).toBe(12)
  expect(staffApi.state.directory.clients[0].purchases[0].used).toBe(3)
}

test('API Owner client reactivation resolves retained conflicts and reconciles an interrupted save', async ({ page, staffApi }) => {
  await openClient(page, staffApi)
  staffApi.state.reactivationConflict = true
  await clientAction(page, 'Reactivate Client')
  const dialog = page.getByRole('dialog', { name: 'Reactivate API Client?', exact: true })
  const save = dialog.getByRole('button', { name: 'Reactivate Client', exact: true })
  await expect(save).toBeDisabled()
  await dialog.getByRole('textbox', { name: /Session 1/ }).fill('2026-09-08')
  await expect(save).toBeEnabled()
  await expect(dialog).toContainText('All retained sessions are conflict-free.')
  staffApi.state.reactivationUnknown = true
  await save.click()
  await dialog.getByRole('button', { name: 'Check Reactivation', exact: true }).click()
  await expect(page).toHaveURL(/#\/clients$/)
  expect(staffApi.state.clientReactivationAttempts).toHaveLength(1)
  expect(Object.values(staffApi.state.clientReactivationAttempts[0].body.dates)).toEqual(['2026-09-08'])
  await page.reload()
  await retainedClient(page, staffApi)
})

test('API Admin client reactivation stays committed through a failed follow-up read', async ({ page, staffApi }) => {
  await openClient(page, staffApi, 'admin')
  await clientAction(page, 'Reactivate Client')
  staffApi.state.reactivationRefreshFailure = true
  await confirm(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Clients', exact: true })).toBeVisible()
  await retainedClient(page, staffApi)
  expect(staffApi.state.clientReactivationAttempts).toHaveLength(1)
})

test('API Trainer cannot reactivate an assigned inactive client', async ({ page, staffApi }) => {
  await openClient(page, staffApi, 'trainer')
  await expect(page.getByRole('button', { name: 'Reactivate Client', exact: true })).toHaveCount(0)
  expect(staffApi.state.clientReactivationAttempts ?? []).toHaveLength(0)
  expect(staffApi.state.directory.clients[0].status).toBe('inactive')
})

test('API client reactivation retains a missing receipt across refresh before an identical retry', async ({ page, staffApi }) => {
  await openClient(page, staffApi)
  staffApi.state.reactivationAbsentUnknown = true
  await clientAction(page, 'Reactivate Client')
  await confirm(page)
  const dialog = page.getByRole('dialog', { name: 'Reactivate API Client?', exact: true })
  await expect(dialog.getByRole('alert')).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Check Client Reactivation', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Check Reactivation', exact: true }).click()
  await expect(page.getByText('Active', { exact: true }).first()).toBeVisible()
  await retainedClient(page, staffApi)
  const [first, second] = staffApi.state.clientReactivationAttempts
  expect(second).toEqual(first)
  expect(staffApi.state.clientReactivationAttempts).toHaveLength(2)
})

test('API client reactivation rejects a stale reviewed client without changing purchases', async ({ page, staffApi }) => {
  await openClient(page, staffApi)
  await clientAction(page, 'Reactivate Client')
  const dialog = page.getByRole('dialog', { name: 'Reactivate API Client?', exact: true })
  await expect(dialog).toBeVisible()
  staffApi.state.directory.clients[0].version++
  await confirm(page)
  await expect(dialog.getByRole('alert')).toBeVisible()
  expect(staffApi.state.directory.clients[0].status).toBe('inactive')
  expect(staffApi.state.directory.clients[0].purchases[0].status).toBe('inactive')
  expect(staffApi.state.clientReactivationReceipts.size).toBe(0)
})

test('API client reactivation retains open sessions without assigning calendar slots', async ({ page, staffApi }) => {
  await openClient(page, staffApi)
  staffApi.state.reactivationOpen = true
  await clientAction(page, 'Reactivate Client')
  const dialog = page.getByRole('dialog', { name: 'Reactivate API Client?', exact: true })
  await expect(dialog).toContainText('1 open session will remain unscheduled.')
  await expect(dialog.getByRole('textbox')).toHaveCount(0)
  await confirm(page)
  await expect(page).toHaveURL(/#\/clients$/)
  expect(staffApi.state.clientReactivationAttempts).toHaveLength(1)
  expect(staffApi.state.clientReactivationAttempts[0].body.dates).toEqual({})
  expect(staffApi.state.reactivationOpen).toBe(true)
  await retainedClient(page, staffApi)
})
