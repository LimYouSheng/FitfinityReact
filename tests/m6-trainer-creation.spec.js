import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function open(page, staffApi, role = 'owner') {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.user = { ...state.user, role, ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  state.directory = { ...directoryData(), viewerId: state.user.id, trainerCreation: true, personalMessages: true,
    trainerProfilePolicy: { defaultCountryCode: '+65', trainerTypes: ['Strength & Conditioning', 'Personal Trainer'] },
    trainerOnboardingPolicy: { availability: { from: '18:00', to: '19:00' }, approvalDefaults: { availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true }, ...(role === 'owner' ? { trainerRates: { peak: 80, offPeak: 55 } } : {}) } }
  state.messageRecords = []
  if (role === 'admin') { delete state.directory.trainers[0].peak_rate_cents; delete state.directory.trainers[0].off_peak_rate_cents }
  if (role === 'trainer') state.directory.packages = []
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/trainers/new`)
}
async function review(page, role = 'owner') {
  await page.getByLabel('Trainer name', { exact: true }).fill('API New Trainer')
  await page.getByLabel('Trainer email', { exact: true }).fill('new-trainer@example.test')
  await page.getByLabel('Trainer phone number', { exact: true }).fill('91234567')
  await page.getByLabel('Trainer birthday', { exact: true }).fill('1990-01-02')
  await page.getByLabel('Trainer gender', { exact: true }).selectOption('Female')
  await page.getByLabel('Trainer type', { exact: true }).fill('Personal Trainer')
  if (role === 'owner') {
    await page.getByRole('button', { name: 'Continue to Training & Rates', exact: true }).click()
    await expect(page.getByLabel('Peak session rate', { exact: true })).toHaveValue('80')
  }
  await page.getByRole('button', { name: 'Continue to Trainer Availability', exact: true }).click()
  await page.getByRole('button', { name: 'Monday', exact: true }).click()
  await page.getByRole('button', { name: 'Add Time', exact: true }).click()
  await page.getByRole('button', { name: 'Continue to Owner Approval Needed', exact: true }).click()
  await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
  if (role === 'admin') await expect(page.getByText(/S\$|Training & Rates/)).toHaveCount(0)
  await page.getByRole('button', { name: 'Create Trainer', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Create API New Trainer?', exact: true })
  await expect(dialog).toContainText('request a login invitation')
  await dialog.getByRole('button', { name: 'Create Trainer', exact: true }).click()
}
const saved = page => expect(page.getByRole('heading', { name: 'API New Trainer', exact: true })).toBeVisible()
for (const role of ['owner', 'admin']) test(`API ${role} creates a complete Trainer and reloads the durable profile`, async ({ page, staffApi }) => {
  await open(page, staffApi, role)
  await review(page, role)
  await saved(page)
  const body = staffApi.state.trainerCreationAttempts[0].body
  if (role === 'admin') expect(body).not.toHaveProperty('rates')
  else expect(body.rates).toEqual({ peak: 8000, offPeak: 5500 })
  expect(body.slots).toEqual([{ weekday: 0, startsAt: '18:00', endsAt: '19:00' }])
  await page.reload()
  await saved(page)
  expect(staffApi.state.trainerCreationAttempts).toHaveLength(1)
})
test('API creation reconciles a committed response without another invitation request', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerCreationUnknown = true
  await review(page)
  await page.getByRole('button', { name: 'Check Trainer Creation', exact: true }).click()
  await saved(page)
  expect(staffApi.state.trainerCreationAttempts).toHaveLength(1)
})
test('API pending invitation resumes the identical request after a directory outage', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerCreationPending = true
  await review(page)
  await expect(page.getByRole('button', { name: 'Check Trainer Creation', exact: true })).toBeVisible()
  staffApi.state.unavailable = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByText('Your trainer creation progress is retained in this tab. Retry loading to verify your account and resume.')).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await page.getByRole('button', { name: 'Check Trainer Creation', exact: true }).click()
  await saved(page)
  expect(staffApi.state.trainerCreationAttempts).toHaveLength(2)
  expect(staffApi.state.trainerCreationAttempts[0]).toEqual(staffApi.state.trainerCreationAttempts[1])
})
test('API unconfirmed invitation is truthful and never automatically resent', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerInvitationUnknown = true
  await review(page)
  await saved(page)
  await expect(page.getByText(/Invitation delivery is unconfirmed/)).toBeVisible()
  await page.reload()
  await saved(page)
  expect(staffApi.state.trainerCreationAttempts).toHaveLength(1)
})
test('API confirmed creation survives failed refresh without inviting another save', async ({ page, staffApi }) => {
  await open(page, staffApi)
  staffApi.state.trainerCreationRefreshFailure = true
  await review(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await saved(page)
  expect(staffApi.state.trainerCreationAttempts).toHaveLength(1)
})
test('API Trainer cannot open staff creation', async ({ page, staffApi }) => {
  await open(page, staffApi, 'trainer')
  await expect(page.getByText('This workflow is not available yet.', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Add New Trainer', exact: true })).toHaveCount(0)
  expect(staffApi.state.trainerCreationAttempts ?? []).toHaveLength(0)
})
