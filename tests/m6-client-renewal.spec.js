import { directoryData, directoryId, onboardingPolicy } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function packageTab(page) {
  const menu = page.locator('details.profile-menu')
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
  if (await menu.locator('summary').isVisible() && await menu.getAttribute('open') === null) await menu.locator('summary').click()
  await page.getByRole('button', { name: 'Package', exact: true }).click()
}
async function openRenewal(page, staffApi, role = 'owner', reviewFailure = false) {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.user = { ...state.user, role }
  state.directory = { ...directoryData(), viewerId: state.user.id, clientOnboardingPolicy: onboardingPolicy, personalMessages: true, clientRenewalWrites: true }
  state.directory.clients[0].start_date = '2026-09-01'
  state.messageRecords = []
  if (role === 'admin') { delete state.directory.trainers[0].peak_rate_cents; delete state.directory.trainers[0].off_peak_rate_cents }
  state.packageRenewalReviewFailure = reviewFailure
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/clients/${directoryId(7)}`)
  await packageTab(page)
  await page.getByRole('button', { name: 'Add Package', exact: true }).click()
  if (reviewFailure) {
    await expect(page.getByRole('dialog', { name: 'Add Package', exact: true }).getByRole('alert')).toBeVisible()
    await expect(page.getByLabel('Start date', { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Retry package review', exact: true }).click()
  }
  await expect(page.getByLabel('Start date', { exact: true })).toHaveValue('2026-11-30')
  await page.getByRole('button', { name: 'Continue to Client Availability', exact: true }).click()
  await expect(page.getByLabel('Client availability blocks')).toContainText('09:00–12:00')
  await page.getByRole('button', { name: 'Continue to Trainer Matching', exact: true }).click()
}
async function submit(page) {
  await expect(page.getByLabel('Matched trainer', { exact: true })).toHaveValue(directoryId(1))
  await expect(page.getByLabel('Fixed Weekly Schedule')).toContainText('10:00–11:00')
  await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
  await page.getByRole('dialog', { name: 'Add Package', exact: true }).getByRole('button', { name: 'Add Package', exact: true }).click()
  await page.getByRole('dialog', { name: 'Add package for API Client?', exact: true }).getByRole('button', { name: 'Add Package', exact: true }).click()
}
async function added(page) {
  await expect(page.getByRole('dialog', { name: 'Add Package', exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Additional Packages', exact: true })).toBeVisible()
  await expect(page.getByLabel('Additional packages')).toContainText('Current Template')
  await expect(page.getByRole('heading', { name: 'Current Package', exact: true }).locator('..')).toContainText('Purchased Twelve')
}
for (const role of ['owner', 'admin']) test(`API ${role} adds a future package with the saved cadence and preserves it across reload`, async ({ page, staffApi }) => {
  await openRenewal(page, staffApi, role, role === 'admin')
  const previous = structuredClone(staffApi.state.directory.clients[0])
  await submit(page)
  await added(page)
  expect(staffApi.state.packageRenewalAttempts).toHaveLength(1)
  expect(staffApi.state.packageRenewalAttempts[0].body.fixedWeeklySchedule).toEqual([{ day: 'Monday', from: '10:00', to: '11:00' }])
  expect(staffApi.state.directory.clients[0].purchases[0]).toEqual(previous.purchases[0])
  expect(staffApi.state.directory.clients[0].people).toEqual(previous.people)
  expect(staffApi.state.directory.clients[0].trainer_id).toBe(previous.trainer_id)
  await page.reload()
  await packageTab(page)
  await added(page)
})
test('API committed interrupted renewal reconciles without a duplicate purchase', async ({ page, staffApi }) => {
  await openRenewal(page, staffApi)
  staffApi.state.packageRenewalUnknown = true
  await submit(page)
  await added(page)
  expect(staffApi.state.packageRenewalAttempts).toHaveLength(1)
  expect(staffApi.state.directory.clients[0].purchases).toHaveLength(2)
})
test('API absent renewal receipt requires explicit retry with the exact original request', async ({ page, staffApi }) => {
  await openRenewal(page, staffApi)
  staffApi.state.packageRenewalAbsentUnknown = true
  await submit(page)
  await page.getByRole('button', { name: 'Check Package Addition', exact: true }).click()
  await added(page)
  const attempts = staffApi.state.packageRenewalAttempts
  expect(attempts).toHaveLength(2)
  expect(attempts[1]).toEqual(attempts[0])
  expect(staffApi.state.directory.clients[0].purchases).toHaveLength(2)
})
test('API confirmed renewal survives a failed refresh without resubmitting', async ({ page, staffApi }) => {
  await openRenewal(page, staffApi)
  staffApi.state.packageRenewalRefreshFailure = true
  await submit(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await packageTab(page)
  await added(page)
  expect(staffApi.state.packageRenewalAttempts).toHaveLength(1)
})
test('API renewal trusts an empty server match result and a rejected save keeps its reviewed draft', async ({ page, staffApi }) => {
  staffApi.state.packageRenewalNoMatches = true
  await openRenewal(page, staffApi)
  await expect(page.getByLabel('Matched trainer', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Add Package', exact: true }).getByRole('alert')).toContainText('Choose a matched trainer.')
  expect(staffApi.state.packageRenewalAttempts ?? []).toHaveLength(0)
  staffApi.state.packageRenewalNoMatches = false
  await page.getByRole('button', { name: 'Back to Client Availability', exact: true }).click()
  await page.getByRole('button', { name: 'Continue to Trainer Matching', exact: true }).click()
  staffApi.state.packageRenewalConflict = true
  await submit(page)
  await expect(page.getByRole('dialog', { name: 'Add Package', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog', { name: 'Add Package', exact: true }).getByRole('alert')).toBeVisible()
  expect(staffApi.state.directory.clients[0].purchases).toHaveLength(1)
})
