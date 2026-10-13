import { directoryData, directoryId } from '../src/test/directory.js'
import { calendarData, sessionDetailData } from '../src/test/sessionReads.js'
import { expect, passwordSignIn, test } from './auth-api-fixture.js'
async function open(page, staffApi, role = 'owner', cover = false, completed = false) {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'; state.user = { ...state.user, role, ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  state.directory = { ...directoryData(), viewerId: state.user.id, sessionReads: true, personalMessages: true }; state.messageRecords = []
  const calendar = calendarData(); calendar.viewerId = state.user.id
  calendar.sessions[0].readAccess = role === 'trainer' ? 'assigned' : 'operations'
  calendar.sessions[0].date = state.directory.businessDate
  if (role === 'admin') for (const t of state.directory.trainers) { delete t.peak_rate_cents; delete t.off_peak_rate_cents }
  if (role === 'trainer') state.directory.packages = []
  if (cover) { state.directory.clients = []; calendar.clients[0].name = 'Covered Couple'; calendar.clients[0].kind = 'couple' }
  const detail = { ...sessionDetailData(), session: calendar.sessions[0], client: calendar.clients[0], trainer: calendar.trainers[0], purchase: calendar.purchases[0] }
  if (completed) {
    detail.session.status = 'completed'; detail.purchase.used = 1
    detail.acknowledgementHistory = [{ id: directoryId(45), sequence: 1, method: 'late_no_show', signerName: null, signature: null, note: 'Recorded acknowledgement', recordedAt: `${state.directory.businessDate}T02:00:00Z`, recordedBy: { id: state.user.id, name: state.user.name } }]
  }
  const undated = { ...calendar.sessions[0], id: directoryId(31), scheduleState: 'open', sessionNumber: null, date: null, startsAt: null, endsAt: null, status: 'scheduled' }
  calendar.sessions.push(undated)
  state.sessionCalendar = calendar; state.sessionDetails = { [detail.session.id]: detail, [undated.id]: { ...detail, session: undated, acknowledgementHistory: [] } }
  await page.goto(staffApi.origin); await passwordSignIn(page)
  await page.getByLabel('Authenticator code').fill('123456')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByRole('heading', { name: `${role === 'owner' ? 'Owner' : role === 'admin' ? 'Admin' : 'Trainer'} Dashboard`, exact: true })).toBeVisible()
}
for (const role of ['owner', 'admin']) test(`API ${role} dashboard opens real calendar evidence with read-only details`, async ({ page, staffApi }) => {
  await open(page, staffApi, role)
  await page.goto(`${staffApi.origin}/#/dashboard/day/${staffApi.state.directory.businessDate}`)
  const dialog = page.getByRole('dialog', { name: 'Calendar sessions' })
  await expect(dialog).toBeVisible(); await expect(dialog.locator('.calendar-event')).toHaveCount(1)
  await dialog.getByRole('button', { name: /10:00–11:00, API Client/ }).click()
  await expect(page.getByText('Stored instruction', { exact: true })).toBeVisible()
  await expect(page.getByText('Stored outcome', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Export Summary', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Client Signature', exact: true })).toHaveCount(0)
})
test('API session list search and period survive detail Back and reload', async ({ page, staffApi }) => {
  await open(page, staffApi)
  await page.goto(`${staffApi.origin}/#/sessions`)
  await page.getByLabel('Filter sessions by period', { exact: true }).selectOption('all')
  await page.getByLabel('Search sessions', { exact: true }).fill('API Client')
  await expect(page.locator('.session-list-row')).toHaveCount(2)
  await page.getByRole('button', { name: /View session for API Client on/ }).click()
  await expect(page.getByText('Stored client summary', { exact: true })).toBeVisible()
  await page.goBack(); await expect(page.getByLabel('Search sessions', { exact: true })).toHaveValue('API Client')
  await page.reload(); await expect(page.getByLabel('Filter sessions by period', { exact: true })).toHaveValue('all')
  await expect(page.locator('.session-list-row')).toHaveCount(2)
})
test('API active cover opens limited client names without exposing a full profile', async ({ page, staffApi }) => {
  await open(page, staffApi, 'trainer', true)
  await page.goto(`${staffApi.origin}/#/sessions/${directoryId(30)}`)
  await page.getByRole('button', { name: 'View Client', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Session Client' })
  await expect(dialog).toContainText('Covered First'); await expect(dialog).toContainText('Covered Second')
  await expect(dialog).not.toContainText('Health')
  await page.goto(`${staffApi.origin}/#/clients`)
  await expect(page.locator('main')).not.toContainText('Covered Couple')
})
test('API completed cover retains acknowledgement history but ends temporary client access', async ({ page, staffApi }) => {
  await open(page, staffApi, 'trainer', true, true)
  await page.goto(`${staffApi.origin}/#/sessions/${directoryId(30)}`)
  await expect(page.getByText('Recorded acknowledgement', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'View Client', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Client Signature', exact: true })).toHaveCount(0)
})
test('API Open session remains visible without a fabricated date or sequence', async ({ page, staffApi }) => {
  await open(page, staffApi)
  await page.goto(`${staffApi.origin}/#/sessions`)
  await expect(page.getByText('Date/time not set', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /with date\/time not set/ }).click()
  await expect(page.locator('main')).toContainText('Open session')
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
})
test('API session background refresh displays the newer persisted evidence', async ({ page, staffApi }) => {
  await open(page, staffApi)
  const signedInRequests = structuredClone(staffApi.state.mutations)
  await page.goto(`${staffApi.origin}/#/sessions/${directoryId(30)}`)
  await expect(page.getByText('Stored client summary', { exact: true })).toBeVisible()
  staffApi.state.sessionDetails[directoryId(30)].clientSummary = 'New persisted summary'
  staffApi.state.sessionCalendar.sessions[0].version++
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByText('New persisted summary', { exact: true })).toBeVisible()
  expect(staffApi.state.mutations).toEqual(signedInRequests)
})
test('API failed detail read retries the authorized record without a demo fallback', async ({ page, staffApi }) => {
  await open(page, staffApi); staffApi.state.sessionReadUnavailable = true
  await page.goto(`${staffApi.origin}/#/sessions/${directoryId(30)}`)
  await expect(page.getByRole('button', { name: 'Retry session', exact: true })).toBeVisible()
  await expect(page.getByText('Stored client summary', { exact: true })).toHaveCount(0)
  staffApi.state.sessionReadUnavailable = false
  await page.getByRole('button', { name: 'Retry session', exact: true }).click()
  await expect(page.getByText('Stored client summary', { exact: true })).toBeVisible()
})
