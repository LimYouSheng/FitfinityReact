import { directoryData } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openContent(page, staffApi, role = 'owner') {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  staffApi.state.directory = directoryData()
  staffApi.state.directory.contentWorkflows = true
  if (role === 'admin') {
    staffApi.state.user = { ...staffApi.state.user, role, name: 'API Admin' }
    delete staffApi.state.directory.trainers[0].peak_rate_cents
    delete staffApi.state.directory.trainers[0].off_peak_rate_cents
  }
  if (role === 'trainer') {
    staffApi.state.user = { ...staffApi.state.user, role, trainerId: staffApi.state.directory.trainers[0].id }
    staffApi.state.directory.packages = []
  }
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/content/new`)
}
async function draft(page) {
  await page.getByLabel('Content title', { exact: true }).fill('API studio')
  await page.getByLabel('Content key', { exact: true }).fill('api/studio')
  await page.getByLabel('Content body', { exact: true }).fill('Saved staff content')
}
async function save(page) {
  await page.getByRole('button', { name: 'Save Content', exact: true }).click()
  await page.getByRole('dialog', { name: 'Save content?', exact: true }).getByRole('button', { name: 'Save Content', exact: true }).click()
}
const writes = staffApi => staffApi.state.mutations.filter(row => row.path === '/api/content')

test('API content reconciles an interrupted creation and retains later archive edits across reload', async ({ page, staffApi }) => {
  await openContent(page, staffApi)
  await draft(page)
  staffApi.state.contentUnknown = true
  await save(page)
  await expect(page.getByLabel('Content title', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Check Content Save', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/content/${staffApi.state.contentRecords[0].id}$`))
  await expect(page.getByLabel('Content body', { exact: true })).toHaveValue('Saved staff content')
  expect(writes(staffApi)).toHaveLength(1)
  await page.getByLabel('Content status', { exact: true }).selectOption('archived')
  await save(page)
  await expect(page.getByRole('button', { name: 'Edit Content', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Content status', { exact: true })).toHaveValue('archived')
  expect(writes(staffApi)).toHaveLength(2)
  expect(staffApi.state.contentRecords[0].version).toBe(2)
})

test('API Admin content save stays committed when the saved-record read fails', async ({ page, staffApi }) => {
  await openContent(page, staffApi, 'admin')
  await draft(page)
  staffApi.state.contentRefreshFailure = true
  await save(page)
  await expect(page.getByRole('button', { name: 'Retry Content', exact: true })).toBeVisible()
  expect(writes(staffApi)).toHaveLength(1)
  staffApi.state.contentReadFailure = false
  await page.getByRole('button', { name: 'Retry Content', exact: true }).click()
  await expect(page.getByLabel('Content title', { exact: true })).toHaveValue('API studio')
  await page.reload()
  await expect(page.getByLabel('Content body', { exact: true })).toHaveValue('Saved staff content')
  expect(writes(staffApi)).toHaveLength(1)
})

test('API Trainer cannot open staff content or trigger a content read', async ({ page, staffApi }) => {
  await openContent(page, staffApi, 'trainer')
  await expect(page.getByRole('heading', { name: 'Page unavailable', exact: true })).toBeVisible()
  expect(staffApi.state.contentReads ?? 0).toBe(0)
  await expect(page.getByLabel('Content title', { exact: true })).toHaveCount(0)
})
