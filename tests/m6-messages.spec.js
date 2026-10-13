import { directoryData, directoryId } from '../src/test/directory.js'
import { messageRequest, personalNotice } from '../src/test/messageApi.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openMessages(page, staffApi, role = 'owner') {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  staffApi.state.directory = { ...directoryData(), personalMessages: true }
  if (role === 'admin') {
    staffApi.state.user = { ...staffApi.state.user, id: directoryId(901), role, name: 'API Admin' }
    delete staffApi.state.directory.trainers[0].peak_rate_cents
    delete staffApi.state.directory.trainers[0].off_peak_rate_cents
  }
  if (role === 'trainer') {
    staffApi.state.user = { ...staffApi.state.user, id: directoryId(902), role, trainerId: directoryId(1) }
    staffApi.state.directory.packages = []
  }
  staffApi.state.directory.viewerId = staffApi.state.user.id
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/messages`)
  await expect(page.getByRole('heading', { name: 'Messages', exact: true })).toBeVisible()
}
const writes = staffApi => staffApi.state.messageWriteRequests ?? []
const noticeButton = page => page.getByRole('button', { name: 'Open Saved staff notice', exact: true })

test('API Owner Messages recovers an interrupted read and persists personal unread state across reload', async ({ page, staffApi }) => {
  await openMessages(page, staffApi)
  staffApi.state.messageUnknown = true
  await noticeButton(page).click()
  await expect(page.getByRole('dialog', { name: 'Saved staff notice', exact: true })).toHaveCount(0)
  await expect(page.getByRole('alert').first()).toBeVisible()
  await noticeButton(page).click()
  const dialog = page.getByRole('dialog', { name: 'Saved staff notice', exact: true })
  await expect(dialog).toBeVisible()
  expect(writes(staffApi)).toHaveLength(1)
  await dialog.getByRole('button', { name: 'Mark as Unread', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Unread Saved staff notice', exact: true })).toBeVisible()
  expect(writes(staffApi)).toHaveLength(2)
})

test('API Admin Messages excludes financial notices and preserves request comparisons without enabling decisions', async ({ page, staffApi }) => {
  const request = messageRequest()
  staffApi.state.messageRecords = [
    { value: personalNotice({ requestId: request.id, request }), recipients: ['owner'] },
    { value: personalNotice({ id: directoryId(93), kind: 'trainer_rates', title: 'Private rate notice' }), recipients: ['owner', 'admin'] },
  ]
  await openMessages(page, staffApi, 'admin')
  await expect(page.getByText('Private rate notice')).toHaveCount(0)
  await noticeButton(page).click()
  const dialog = page.getByRole('dialog', { name: 'Saved staff notice', exact: true })
  await expect(dialog.getByRole('heading', { name: 'Availability change', exact: true })).toBeVisible()
  await expect(dialog.getByLabel('Requested', { exact: true }).getByText('11:00–12:00')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Approve Request', exact: true })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: 'Cancel Request', exact: true })).toHaveCount(0)
  expect(writes(staffApi)[0].body.expectedVersion).toBe(0)
})

test('API Trainer read stays committed through a follow-up outage and Owner-only notices remain absent', async ({ page, staffApi }) => {
  staffApi.state.messageRecords = [
    { value: personalNotice(), recipients: ['trainer'] },
    { value: personalNotice({ id: directoryId(93), title: 'Owner-only notice' }), recipients: ['owner'] },
  ]
  await openMessages(page, staffApi, 'trainer')
  await expect(page.getByText('Owner-only notice')).toHaveCount(0)
  staffApi.state.messageRefreshFailure = true
  await noticeButton(page).click()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.messageReadFailure = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Read Saved staff notice', exact: true })).toBeVisible()
  const recovered = page.getByRole('dialog', { name: 'Saved staff notice', exact: true })
  if (!(await recovered.isVisible())) await noticeButton(page).click()
  await expect(recovered).toBeVisible()
  expect(writes(staffApi)).toHaveLength(1)
})

test('API Messages retains a missing-receipt intent through a portal outage before explicit identical retry', async ({ page, staffApi }) => {
  await openMessages(page, staffApi)
  staffApi.state.messageAbsentUnknown = true
  await noticeButton(page).click()
  await expect(page.getByRole('alert').first()).toBeVisible()
  staffApi.state.unavailable = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await page.getByRole('button', { name: 'Check Message Read State', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Read Saved staff notice', exact: true })).toBeVisible()
  expect(writes(staffApi)).toHaveLength(2)
  expect(writes(staffApi)[1].body).toEqual(writes(staffApi)[0].body)
  expect(writes(staffApi)[1].key).toBe(writes(staffApi)[0].key)
})
