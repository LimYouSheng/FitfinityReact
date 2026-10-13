import { directoryData, directoryId } from '../src/test/directory.js'
import { messageRequest, personalNotice } from '../src/test/messageApi.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openRequest(page, staffApi, proposal = {}) {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'
  state.user = { ...state.user, role: 'trainer', id: directoryId(902), trainerId: directoryId(1) }
  state.directory = { ...directoryData(), viewerId: state.user.id, packages: [], personalMessages: true, requestCancellationWrites: true }
  const request = messageRequest(proposal)
  const title = request.kind === 'session_postpone' ? 'Postponement request' : request.kind === 'session_time' ? 'Session time request' : 'Availability request'
  state.messageRecords = [{ value: personalNotice({ kind: 'request_receipt', title, requestId: request.id, trainerId: state.user.trainerId, request }), recipients: ['trainer'] }]
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/messages`)
  await page.getByRole('button', { name: `Open ${title}`, exact: true }).click()
  await expect(page.getByRole('dialog', { name: title, exact: true })).toBeVisible()
}
async function cancel(page) {
  await page.getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await page.getByRole('dialog', { name: 'Cancel this request?', exact: true }).getByRole('button', { name: 'Cancel Request', exact: true }).click()
}
async function verifyCancelled(page) {
  await expect(page.getByText(/Cancelled by/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel Request', exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Current at request')).toContainText('10:00–11:00')
  await expect(page.getByLabel('Requested', { exact: true })).toContainText('11:00–12:00')
}

test('API requesting Trainer checks an interrupted committed cancellation and preserves both proposal sides', async ({ page, staffApi }) => {
  await openRequest(page, staffApi)
  staffApi.state.cancellationUnknown = true
  await cancel(page)
  await page.getByRole('button', { name: 'Check Cancellation', exact: true }).click()
  await verifyCancelled(page)
  expect(staffApi.state.cancellationAttempts).toHaveLength(1)
  await page.reload()
  await expect(page.getByRole('dialog', { name: 'Availability request', exact: true })).toBeVisible()
  await verifyCancelled(page)
})
test('API cancellation absent receipt retains its intent across focus reload until explicit identical retry', async ({ page, staffApi }) => {
  await openRequest(page, staffApi)
  staffApi.state.cancellationAbsentUnknown = true
  await cancel(page)
  await expect(page.getByRole('button', { name: 'Check Cancellation', exact: true })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check Request Cancellation', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Availability request', exact: true })).toBeVisible()
  await verifyCancelled(page)
  const attempts = staffApi.state.cancellationAttempts
  expect(attempts).toHaveLength(2)
  expect(attempts[1]).toEqual(attempts[0])
})
test('API cancellation preserves a confirmed result through a failed message refresh', async ({ page, staffApi }) => {
  await openRequest(page, staffApi)
  staffApi.state.cancellationRefreshFailure = true
  await cancel(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.messageReadFailure = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Availability request', exact: true })).toBeVisible()
  await verifyCancelled(page)
  expect(staffApi.state.cancellationAttempts).toHaveLength(1)
})
test('API cancellation refuses a decision made after the confirmation opened', async ({ page, staffApi }) => {
  await openRequest(page, staffApi)
  await page.getByRole('button', { name: 'Cancel Request', exact: true }).click()
  Object.assign(staffApi.state.messageRecords[0].value.request, { status: 'rejected', version: 2, resolved_at: '2026-10-13T16:00:00Z' })
  await page.getByRole('dialog', { name: 'Cancel this request?', exact: true }).getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await expect(page.getByRole('alert').first()).toBeVisible()
  expect(staffApi.state.cancellationReceipts.size).toBe(0)
  await page.reload()
  await expect(page.getByRole('dialog', { name: 'Availability request', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel Request', exact: true })).toHaveCount(0)
  await expect(page.getByRole('dialog', { name: 'Availability request', exact: true })).toContainText('Rejected')
})

test('API cancellation recovery releases its pending intent after a definitive competing decision', async ({ page, staffApi }) => {
  await openRequest(page, staffApi)
  staffApi.state.cancellationAbsentUnknown = true
  await cancel(page)
  await expect(page.getByRole('button', { name: 'Check Cancellation', exact: true })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('button', { name: 'Check Request Cancellation', exact: true })).toBeVisible()
  Object.assign(staffApi.state.messageRecords[0].value.request, { status: 'rejected', version: 2, resolved_at: '2026-10-13T16:00:00Z' })
  await page.getByRole('button', { name: 'Check Request Cancellation', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Availability request', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog', { name: 'Availability request', exact: true })).toContainText('Rejected')
  await expect(page.getByRole('button', { name: 'Check Request Cancellation', exact: true })).toHaveCount(0)
  expect(staffApi.state.cancellationReceipts.size).toBe(0)
})

test('API postponed-session cancellation preserves the original booking and Open proposal after reload', async ({ page, staffApi }) => {
  await openRequest(page, staffApi, { kind: 'session_postpone', client_id: directoryId(7), purchase_id: directoryId(4), session_id: directoryId(5), old_date: '2026-10-14', old_start: '10:00:00', old_end: '11:00:00', slots: [] })
  await expect(page.getByLabel('Current at request')).toContainText('10:00–11:00')
  await expect(page.getByLabel('Requested', { exact: true })).toContainText('Open session · Date/time not set')
  await cancel(page)
  await expect(page.getByText(/Cancelled by/)).toBeVisible()
  await page.reload()
  await expect(page.getByRole('dialog', { name: 'Postponement request', exact: true })).toBeVisible()
  await expect(page.getByLabel('Current at request')).toContainText('10:00–11:00')
  await expect(page.getByLabel('Requested', { exact: true })).toContainText('Open session · Date/time not set')
  expect(staffApi.state.messageRecords[0].value.request.old_start).toBe('10:00:00')
  expect(staffApi.state.messageRecords[0].value.request.new_start).toBeNull()
  expect(staffApi.state.cancellationAttempts).toHaveLength(1)
})

test('API cancellation of an Open-session booking proposal retains its empty original interval', async ({ page, staffApi }) => {
  await openRequest(page, staffApi, { kind: 'session_time', client_id: directoryId(7), purchase_id: directoryId(4), session_id: directoryId(5), new_date: '2026-10-14', new_start: '10:00:00', new_end: '11:00:00', slots: [] })
  await expect(page.getByLabel('Current at request')).toContainText('Open session · Date/time not set')
  await expect(page.getByLabel('Requested', { exact: true })).toContainText('10:00–11:00')
  await cancel(page)
  await expect(page.getByText(/Cancelled by/)).toBeVisible()
  await page.reload()
  await expect(page.getByRole('dialog', { name: 'Session time request', exact: true })).toBeVisible()
  await expect(page.getByLabel('Current at request')).toContainText('Open session · Date/time not set')
  await expect(page.getByLabel('Requested', { exact: true })).toContainText('10:00–11:00')
  expect(staffApi.state.messageRecords[0].value.request.old_date).toBeNull()
  expect(staffApi.state.cancellationAttempts).toHaveLength(1)
})
