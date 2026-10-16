import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'
async function open(page, staffApi, role = 'owner', supervised = true) {
  const state = staffApi.state
  state.step = 'SOFTWARE_TOKEN_MFA'; state.user = { ...state.user, role, ...(role === 'trainer' ? { trainerId: directoryId(1) } : {}) }
  state.directory = { ...directoryData(), viewerId: state.user.id, clientWeeklyScheduleWrites: true, personalMessages: true }
  state.directory.trainers[0].approve_weekly_schedule = supervised; state.messageRecords = []
  if (role === 'admin') for (const t of state.directory.trainers) { delete t.peak_rate_cents; delete t.off_peak_rate_cents }
  if (role === 'trainer') state.directory.packages = []
  await page.goto(staffApi.origin); await passwordSignIn(page); await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/clients/${directoryId(7)}`)
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
}
const panel = page => page.locator('.schedule-panel')
async function edit(page) {
  await panel(page).getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Monday from', { exact: true }).fill('12:00')
  await page.getByLabel('Monday to', { exact: true }).fill('13:00')
}
async function confirm(page, requested = false) {
  await panel(page).getByRole('button', { name: 'Save', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Save fixed weekly schedule?' })
  await expect(dialog).toContainText(requested ? 'owner approval' : '1 eligible upcoming sessions')
  await dialog.getByRole('button', { name: 'Save Schedule', exact: true }).click()
}
for (const [role, supervised] of [['owner', true], ['admin', true], ['trainer', false], ['trainer', true]]) test(`API ${role} ${supervised ? 'supervised' : 'direct'} weekly times persist with correct approval behavior`, async ({ page, staffApi }) => {
  await open(page, staffApi, role, supervised)
  const before = structuredClone(staffApi.state.directory.clients[0].purchases[0]), requested = role === 'trainer' && supervised
  await edit(page); await confirm(page, requested)
  await expect(panel(page).getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  await expect(panel(page)).toContainText(requested ? '10:00–11:00' : '12:00–13:00')
  const after = staffApi.state.directory.clients[0].purchases[0]
  if (requested) { expect(after).toEqual(before); expect(staffApi.state.weeklyProposal.slots[0].startsAt).toBe('12:00') }
  else { expect(after).toEqual({ ...before, version: before.version + 1, schedule: [{ ...before.schedule[0], starts_at: '12:00:00', ends_at: '13:00:00' }] }) }
  await page.reload(); await expect(panel(page)).toContainText(requested ? '10:00–11:00' : '12:00–13:00')
  expect(staffApi.state.weeklyAttempts).toHaveLength(1)
})
test('API checks a committed interrupted schedule with frozen times and no duplicate write', async ({ page, staffApi }) => {
  await open(page, staffApi); staffApi.state.weeklyUnknown = true
  await edit(page); await confirm(page)
  await expect(page.getByLabel('Monday from', { exact: true })).toBeDisabled()
  await panel(page).getByRole('button', { name: 'Check Schedule', exact: true }).click()
  await expect(panel(page)).toContainText('12:00–13:00')
  expect(staffApi.state.weeklyAttempts).toHaveLength(1)
})
test('API retains absent weekly receipt across directory refresh and explicitly retries identical intent', async ({ page, staffApi }) => {
  await open(page, staffApi); staffApi.state.weeklyAbsent = true
  await edit(page); await confirm(page)
  await expect(panel(page).getByRole('button', { name: 'Check Schedule', exact: true })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Check Weekly Schedule' })).toBeVisible()
  await page.getByRole('button', { name: 'Check Schedule', exact: true }).click()
  await expect(panel(page)).toContainText('12:00–13:00')
  expect(staffApi.state.weeklyAttempts).toHaveLength(2)
  expect(staffApi.state.weeklyAttempts[0]).toEqual(staffApi.state.weeklyAttempts[1])
})
test('API retains confirmed weekly save when directory refresh fails', async ({ page, staffApi }) => {
  await open(page, staffApi); staffApi.state.weeklyRefreshFailure = true
  await edit(page); await confirm(page)
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false; await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(panel(page)).toContainText('12:00–13:00')
  expect(staffApi.state.weeklyAttempts).toHaveLength(1)
})
test('API rejects stale weekly preview without overwriting approved times', async ({ page, staffApi }) => {
  await open(page, staffApi); await edit(page)
  staffApi.state.directory.clients[0].version++
  await panel(page).getByRole('button', { name: 'Save', exact: true }).click()
  await expect(panel(page).getByRole('alert')).toBeVisible()
  expect(staffApi.state.weeklyAttempts ?? []).toHaveLength(0)
  expect(staffApi.state.directory.clients[0].purchases[0].schedule[0].starts_at).toBe('10:00:00')
})
