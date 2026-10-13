import { directoryData, directoryId } from '../src/test/directory.js'
import { personalNotice } from '../src/test/messageApi.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openRenewals(page, staffApi, role = 'owner') {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.directory = { ...directoryData(), personalMessages: true, renewalDismissalWrites: true }
  if (role !== 'owner') state.user = { ...state.user, role, id: directoryId(role === 'admin' ? 901 : 902), ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  if (role === 'admin') { delete state.directory.trainers[0].peak_rate_cents; delete state.directory.trainers[0].off_peak_rate_cents }
  if (role === 'trainer') state.directory.packages = []
  state.directory.viewerId = state.user.id
  state.messageRecords = [{ value: personalNotice({ kind: 'renewal', title: 'Renewal follow-up', clientId: directoryId(7), purchaseId: directoryId(4), renewalStatus: 'active' }), recipients: ['owner', 'trainer'] }]
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/messages/renewals`)
  await expect(page.getByRole('heading', { name: 'Messages', exact: true })).toBeVisible()
}
const remove = page => page.getByRole('button', { name: 'Remove Renewal follow-up from renewals', exact: true })
async function confirmRemoval(page) {
  await remove(page).click()
  await page.getByRole('dialog', { name: 'Remove renewal follow-up?', exact: true }).getByRole('button', { name: 'Remove', exact: true }).click()
}
async function retainedNotice(page, origin) {
  await page.goto(`${origin}/#/messages`)
  await expect(page.getByRole('button', { name: 'Open Renewal follow-up', exact: true })).toBeVisible()
  await expect(page.getByText('Removed from renewals', { exact: true })).toBeVisible()
  await expect(remove(page)).toHaveCount(0)
}

test('API Owner renewal dismissal recovers a committed interrupted response and keeps the notice after reload', async ({ page, staffApi }) => {
  await openRenewals(page, staffApi)
  staffApi.state.dismissalUnknown = true
  await confirmRemoval(page)
  await expect(page.getByRole('alert').first()).toBeVisible()
  await confirmRemoval(page)
  await expect(remove(page)).toHaveCount(0)
  expect(staffApi.state.renewalDismissalAttempts).toHaveLength(1)
  await page.reload()
  await retainedNotice(page, staffApi.origin)
})

test('API Admin confirmed renewal removal survives a failed follow-up read', async ({ page, staffApi }) => {
  await openRenewals(page, staffApi, 'admin')
  staffApi.state.dismissalRefreshFailure = true
  await confirmRemoval(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.messageReadFailure = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Messages', exact: true })).toBeVisible()
  await retainedNotice(page, staffApi.origin)
  expect(staffApi.state.renewalDismissalAttempts).toHaveLength(1)
})

test('API Trainer renewal removal rechecks current assignment after confirmation', async ({ page, staffApi }) => {
  await openRenewals(page, staffApi, 'trainer')
  await remove(page).click()
  staffApi.state.directory.clients[0].trainer_id = directoryId(888)
  await page.getByRole('dialog', { name: 'Remove renewal follow-up?', exact: true }).getByRole('button', { name: 'Remove', exact: true }).click()
  await expect(page.getByRole('alert').first()).toBeVisible()
  expect(staffApi.state.renewalDismissalReceipts.size).toBe(0)
  staffApi.state.directory.clients[0].trainer_id = directoryId(1)
  await confirmRemoval(page)
  await retainedNotice(page, staffApi.origin)
  expect(staffApi.state.renewalDismissalAttempts).toHaveLength(2)
})

test('API renewal dismissal retains an uncommitted intent through reload before explicit identical retry', async ({ page, staffApi }) => {
  await openRenewals(page, staffApi)
  staffApi.state.dismissalAbsentUnknown = true
  await confirmRemoval(page)
  await expect(page.getByRole('alert').first()).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check Renewal Removal', exact: true }).click()
  await retainedNotice(page, staffApi.origin)
  const [first, second] = staffApi.state.renewalDismissalAttempts
  expect(second).toEqual(first)
  expect(staffApi.state.renewalDismissalAttempts).toHaveLength(2)
})
