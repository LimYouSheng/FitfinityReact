import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function open(page, staffApi, role = 'owner') {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.user = { ...state.user, role, ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  state.directory = { ...directoryData(), viewerId: state.user.id, clientAssignmentWrites: true, personalMessages: true }
  state.directory.trainers.push({ ...state.directory.trainers[0], id: directoryId(31), name: 'Replacement Trainer', email: 'replacement@example.test' })
  state.messageRecords = []
  if (role === 'admin') for (const trainer of state.directory.trainers) { delete trainer.peak_rate_cents; delete trainer.off_peak_rate_cents }
  if (role === 'trainer') { state.directory.trainers = state.directory.trainers.slice(0, 1); state.directory.packages = [] }
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/clients/${directoryId(7)}`)
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
  const menu = page.locator('details.profile-menu')
  if (await menu.locator('summary').isVisible() && await menu.getAttribute('open') === null) await menu.locator('summary').click()
  await menu.getByRole('button', { name: 'Package', exact: true }).click()
}
const dialog = page => page.getByRole('dialog', { name: 'Permanently Reassign Trainer', exact: true })
async function review(page) {
  await page.getByRole('button', { name: 'Reassign Trainer', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  await page.getByLabel('New trainer', { exact: true }).selectOption(directoryId(31))
}
async function confirm(page) {
  await dialog(page).getByRole('button', { name: 'Review Reassignment', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: 'Reassign trainer for API Client?', exact: true })
  await expect(confirmation).toContainText('1 eligible upcoming sessions')
  await confirmation.getByRole('button', { name: 'Reassign Trainer', exact: true }).click()
}
const assigned = page => expect(page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Current Package', exact: true }) }).getByText('Replacement Trainer', { exact: true })).toBeVisible()
for (const role of ['owner', 'admin']) test(`API ${role} permanently reassigns the reviewed client and preserves purchased terms across reload`, async ({ page, staffApi }) => {
  await open(page, staffApi, role)
  const before = structuredClone(staffApi.state.directory.clients[0].purchases[0])
  await review(page); await confirm(page); await assigned(page)
  const purchase = staffApi.state.directory.clients[0].purchases[0]
  expect(purchase).toEqual({ ...before, trainer_id: directoryId(31), trainer_name: 'Replacement Trainer', version: before.version + 1 })
  await page.getByRole('button', { name: 'Reassign Trainer', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Trainer assignment history' })).toContainText('Replacement Trainer')
  await page.reload(); await assigned(page)
  expect(staffApi.state.clientAssignmentAttempts).toHaveLength(1)
})
test('API blocks a replacement with a real server-reviewed conflict', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.clientAssignmentConflict = true
  await page.getByRole('button', { name: 'Reassign Trainer', exact: true }).click()
  await expect(dialog(page)).toContainText('another booking during an eligible session')
  await expect(dialog(page).getByRole('button', { name: 'Review Reassignment' })).toBeDisabled()
  expect(staffApi.state.clientAssignmentAttempts ?? []).toHaveLength(0)
})
test('API recovers a committed interrupted assignment without a second write', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.clientAssignmentUnknown = true
  await review(page); await confirm(page)
  await dialog(page).getByRole('button', { name: 'Check Reassignment', exact: true }).click()
  await assigned(page)
  expect(staffApi.state.clientAssignmentAttempts).toHaveLength(1)
})
test('API retains an absent receipt through directory refresh and explicitly retries identical input', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.clientAssignmentAbsent = true
  await review(page); await confirm(page)
  await expect(dialog(page).getByRole('button', { name: 'Check Reassignment', exact: true })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Check Trainer Reassignment' })).toBeVisible()
  await page.getByRole('button', { name: 'Check Reassignment', exact: true }).click()
  await assigned(page)
  expect(staffApi.state.clientAssignmentAttempts).toHaveLength(2)
  expect(staffApi.state.clientAssignmentAttempts[0]).toEqual(staffApi.state.clientAssignmentAttempts[1])
})
test('API successful reassignment remains successful after a failed directory refresh', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.clientAssignmentRefreshFailure = true
  await review(page); await confirm(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await assigned(page)
  expect(staffApi.state.clientAssignmentAttempts).toHaveLength(1)
})
test('API retains the original open review after background version change and rejects its stale save', async ({ page, staffApi }) => {
  await open(page, staffApi)
  await review(page)
  staffApi.state.directory.clients[0].version++
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(dialog(page)).toBeVisible()
  await confirm(page)
  await expect(dialog(page).getByRole('alert')).toBeVisible()
  expect(staffApi.state.directory.clients[0].trainer_id).toBe(directoryId(1))
})
test('API assigned Trainer cannot permanently reassign the client', async ({ page, staffApi }) => {
  await open(page, staffApi, 'trainer')
  await expect(page.getByRole('button', { name: 'Reassign Trainer', exact: true })).toHaveCount(0)
  expect(staffApi.state.clientAssignmentAttempts ?? []).toHaveLength(0)
})
