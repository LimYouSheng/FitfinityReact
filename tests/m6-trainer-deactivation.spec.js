import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function open(page, staffApi, role = 'owner') {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.user = { ...state.user, role, ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  state.directory = { ...directoryData(), viewerId: state.user.id, trainerDeactivationWrites: true, personalMessages: true }
  state.directory.trainers.push({ ...state.directory.trainers[0], id: directoryId(31), name: 'Replacement Trainer', email: 'replacement@example.test' })
  state.messageRecords = []
  if (role === 'admin') for (const trainer of state.directory.trainers) { delete trainer.peak_rate_cents; delete trainer.off_peak_rate_cents }
  if (role === 'trainer') { state.directory.trainers = state.directory.trainers.slice(0, 1); state.directory.packages = [] }
  await page.goto(staffApi.origin)
  await passwordSignIn(page); await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/${role === 'trainer' ? 'my-profile' : `trainers/${directoryId(1)}`}`)
  await expect(page.getByRole('heading', { name: 'API Trainer', exact: true })).toBeVisible()
  const menu = page.locator('details.profile-menu > summary')
  if (await menu.isVisible()) await menu.click()
}
const dialog = page => page.getByRole('dialog', { name: 'Deactivate API Trainer?', exact: true })
async function review(page) {
  await page.getByRole('button', { name: 'Deactivate Trainer', exact: true }).click()
  await expect(dialog(page)).toBeVisible()
  await expect(dialog(page).getByRole('button', { name: 'Deactivate Trainer' })).toBeDisabled()
  await page.getByLabel('Reassign API Client', { exact: true }).selectOption(directoryId(31))
  await expect(dialog(page).getByRole('button', { name: 'Deactivate Trainer' })).toBeEnabled()
}
async function inactive(page, staffApi) {
  await expect(page.getByRole('heading', { name: 'Trainers', exact: true })).toBeVisible()
  await page.goto(`${staffApi.origin}/#/trainers/${directoryId(1)}`)
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Inactive')
}
for (const role of ['owner', 'admin']) test(`API ${role} deactivates a Trainer and preserves permanent client and purchase assignments`, async ({ page, staffApi }) => {
  await open(page, staffApi, role)
  const before = structuredClone(staffApi.state.directory.clients)
  await review(page)
  await dialog(page).getByRole('button', { name: 'Deactivate Trainer', exact: true }).click()
  await inactive(page, staffApi)
  await page.reload()
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Inactive')
  expect(staffApi.state.directory.clients).toEqual(before)
  expect(staffApi.state.trainerDeactivationSavedSessions[0].trainerId).toBe(directoryId(31))
  expect(staffApi.state.trainerDeactivationAttempts).toHaveLength(1)
})
test('API Trainer deactivation retains Open sessions without inventing a schedule', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerDeactivationOpen = true
  await review(page)
  await expect(dialog(page)).toContainText('Open session')
  await dialog(page).getByRole('button', { name: 'Deactivate Trainer' }).click()
  await inactive(page, staffApi)
  expect(staffApi.state.trainerDeactivationSavedSessions[0]).toMatchObject({ scheduleState: 'open', date: null, startsAt: null, endsAt: null })
})
test('API Trainer deactivation cannot submit an unavailable replacement batch', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerDeactivationConflict = true
  await page.getByRole('button', { name: 'Deactivate Trainer', exact: true }).click()
  await expect(dialog(page)).toContainText('No active trainer is free for this session')
  await expect(dialog(page).getByRole('button', { name: 'Deactivate Trainer' })).toBeDisabled()
  expect(staffApi.state.trainerDeactivationAttempts ?? []).toHaveLength(0)
})
test('API interrupted committed Trainer deactivation reconciles without another write', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerDeactivationUnknown = true
  await review(page)
  await dialog(page).getByRole('button', { name: 'Deactivate Trainer' }).click()
  await dialog(page).getByRole('button', { name: 'Check Deactivation' }).click()
  await inactive(page, staffApi)
  expect(staffApi.state.trainerDeactivationAttempts).toHaveLength(1)
})
test('API absent deactivation receipt survives focus refresh until explicit identical retry', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerDeactivationAbsent = true
  await review(page)
  await dialog(page).getByRole('button', { name: 'Deactivate Trainer' }).click()
  await expect(dialog(page).getByRole('button', { name: 'Check Deactivation' })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Check Trainer Deactivation' })).toBeVisible()
  await page.getByRole('button', { name: 'Check Deactivation', exact: true }).click()
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Inactive')
  expect(staffApi.state.trainerDeactivationAttempts).toHaveLength(2)
  expect(staffApi.state.trainerDeactivationAttempts[0]).toEqual(staffApi.state.trainerDeactivationAttempts[1])
})
test('API Trainer deactivation stays successful when directory refresh fails', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerDeactivationRefreshFailure = true
  await review(page)
  await dialog(page).getByRole('button', { name: 'Deactivate Trainer' }).click()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Inactive')
  expect(staffApi.state.trainerDeactivationAttempts).toHaveLength(1)
})
test('API Trainer cannot deactivate their own account', async ({ page, staffApi }) => {
  await open(page, staffApi, 'trainer')
  await expect(page.getByRole('button', { name: 'Deactivate Trainer', exact: true })).toHaveCount(0)
})
