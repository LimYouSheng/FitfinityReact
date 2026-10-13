import { directoryData, directoryId, onboardingPolicy } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openAvailability(page, staffApi, supervised = true) {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.user = { ...state.user, role: 'trainer', id: directoryId(902), trainerId: directoryId(1), name: 'API Trainer' }
  state.directory = { ...directoryData(), viewerId: state.user.id, packages: [], clientOnboardingPolicy: onboardingPolicy, trainerAvailabilityWrites: true, personalMessages: true, requestCancellationWrites: true }
  state.directory.trainers[0].approve_availability = supervised
  state.messageRecords = []
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/my-profile`)
  const menu = page.locator('details.profile-menu')
  if (await menu.locator('summary').isVisible() && await menu.getAttribute('open') === null) await menu.locator('summary').click()
  await menu.getByRole('button', { name: 'Availability', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Approved Availability', exact: true })).toBeVisible()
  await page.getByRole('button', { name: supervised ? 'Request Change' : 'Edit', exact: true }).click()
  await page.getByRole('button', { name: 'Reset Availability', exact: true }).click()
}
async function submit(page, supervised = true) {
  await page.getByRole('button', { name: supervised ? 'Send Request' : 'Save', exact: true }).click()
  await page.getByRole('dialog', { name: supervised ? 'Request availability change?' : 'Save availability?', exact: true }).getByRole('button', { name: supervised ? 'Send Request' : 'Save Availability', exact: true }).click()
}

test('API supervised availability keeps approved hours, persists its proposal and can be cancelled', async ({ page, staffApi }) => {
  await openAvailability(page, staffApi)
  await submit(page)
  await expect(page.getByRole('heading', { name: 'Approved Availability', exact: true })).toBeVisible()
  await expect(page.getByText('10:00am–11:00am', { exact: true })).toBeVisible()
  expect(staffApi.state.directory.trainers[0].availability).toHaveLength(1)
  await page.goto(`${staffApi.origin}/#/messages`)
  await page.getByRole('button', { name: 'Open Availability change request', exact: true }).click()
  await expect(page.getByLabel('Current at request')).toContainText('10:00–11:00')
  await expect(page.getByLabel('Requested', { exact: true })).not.toContainText('10:00–11:00')
  await page.getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await page.getByRole('dialog', { name: 'Cancel this request?', exact: true }).getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await expect(page.getByText(/Cancelled by/)).toBeVisible()
  expect(staffApi.state.directory.trainers[0].availability).toHaveLength(1)
  expect(staffApi.state.availabilityAttempts).toHaveLength(1)
})
test('API direct availability save survives a failed directory refresh without resubmission', async ({ page, staffApi }) => {
  await openAvailability(page, staffApi, false)
  staffApi.state.availabilityRefreshFailure = true
  await submit(page, false)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Approved Availability', exact: true })).toBeVisible()
  await expect(page.getByText('10:00am–11:00am', { exact: true })).toHaveCount(0)
  expect(staffApi.state.directory.trainers[0].availability).toEqual([])
  expect(staffApi.state.availabilityAttempts).toHaveLength(1)
})
test('API availability keeps an uncommitted intent until its explicit original retry', async ({ page, staffApi }) => {
  await openAvailability(page, staffApi)
  staffApi.state.availabilityAbsentUnknown = true
  await submit(page)
  await page.getByRole('button', { name: 'Check Availability Save', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Approved Availability', exact: true })).toBeVisible()
  const attempts = staffApi.state.availabilityAttempts
  expect(attempts).toHaveLength(2)
  expect(attempts[1]).toEqual(attempts[0])
  expect(staffApi.state.messageRecords).toHaveLength(1)
})
test('API committed interrupted availability reconciles on refresh without a duplicate proposal', async ({ page, staffApi }) => {
  await openAvailability(page, staffApi)
  staffApi.state.availabilityUnknown = true
  await submit(page)
  await expect(page.getByRole('heading', { name: 'Approved Availability', exact: true })).toBeVisible()
  expect(staffApi.state.availabilityAttempts).toHaveLength(1)
  expect(staffApi.state.messageRecords).toHaveLength(1)
})
