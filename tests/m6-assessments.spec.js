import { directoryData, directoryId } from '../src/test/directory.js'
import { assessmentRevision } from '../src/test/assessmentApi.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function openAssessments(page, staffApi, { admin = false, existing = false, inactive = false } = {}) {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  staffApi.state.directory = directoryData()
  staffApi.state.directory.clientAssessmentWorkflows = true
  if (admin) {
    staffApi.state.user = { ...staffApi.state.user, role: 'admin', name: 'API Admin' }
    delete staffApi.state.directory.trainers[0].peak_rate_cents
    delete staffApi.state.directory.trainers[0].off_peak_rate_cents
  }
  const client = staffApi.state.directory.clients[0]
  if (inactive) client.status = 'inactive'
  if (existing) {
    const saved = assessmentRevision()
    const draft = { ...saved, id: directoryId(22), revision: 1, previous_revision: null, event: 'draft', status: 'draft' }
    staffApi.state.assessmentStore = { people: new Map([[client.people[0].id, [saved]]]), histories: new Map([[saved.assessment_id, [saved, draft]]]), receipts: new Map(), sequence: 300 }
  }
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.goto(`${staffApi.origin}/#/clients/${client.id}`)
  await expect(page.getByRole('heading', { name: 'Health & Assessments', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: `Static Balance — ${existing ? 'Filled' : 'Not filled'}`, exact: true })).toBeVisible()
}
const balance = page => page.getByRole('dialog', { name: 'Static Balance', exact: true })
const writes = staffApi => staffApi.state.mutations.filter(m => /\/people\/[^/]+\/assessments$|\/assessments\/[^/]+\/revisions$/.test(m.path))

test('API assessment drafts resume after reload and an interrupted completion is reconciled once', async ({ page, staffApi }) => {
  await openAssessments(page, staffApi)
  await page.getByRole('button', { name: 'Static Balance — Not filled', exact: true }).click()
  await balance(page).getByRole('button', { name: 'Save Draft', exact: true }).click()
  await expect(balance(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Static Balance — Draft', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'Static Balance — Draft', exact: true }).click()
  await balance(page).getByRole('button', { name: 'Resume Draft', exact: true }).click()
  await balance(page).getByRole('spinbutton', { name: 'Eyes open — trial 1 (seconds)', exact: true }).fill('0')
  staffApi.state.assessmentUnknown = true
  await balance(page).getByRole('button', { name: 'Complete Assessment', exact: true }).click()
  await balance(page).getByRole('button', { name: 'Check Assessment Save', exact: true }).click()
  await expect(balance(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Static Balance — Filled', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'Static Balance — Filled', exact: true }).click()
  await expect(balance(page).getByLabel('Eyes open — trial 1 (seconds)', { exact: true })).toHaveText('0')
  await expect(balance(page).getByRole('button', { name: 'Complete Assessment', exact: true })).toHaveCount(0)
  expect(writes(staffApi)).toHaveLength(2)
  expect(writes(staffApi)[0].body).not.toHaveProperty('assessor')
  expect(writes(staffApi)[1].body).not.toHaveProperty('date')
})

test('API Admin reassessment starts blank and retains the original occasion and revision history', async ({ page, staffApi }) => {
  await openAssessments(page, staffApi, { admin: true, existing: true })
  await page.getByRole('button', { name: 'Static Balance — Filled', exact: true }).click()
  await balance(page).getByRole('button', { name: 'Start Reassessment', exact: true }).click()
  await page.getByRole('dialog', { name: 'Start a new Static Balance assessment?', exact: true }).getByRole('button', { name: 'Start Reassessment', exact: true }).click()
  const answer = balance(page).getByRole('spinbutton', { name: 'Eyes open — trial 1 (seconds)', exact: true })
  await expect(answer).toHaveValue('')
  await answer.fill('5')
  await balance(page).getByRole('button', { name: 'Complete Assessment', exact: true }).click()
  await expect(balance(page)).toHaveCount(0)
  await page.getByRole('button', { name: 'Static Balance — Filled', exact: true }).click()
  await expect(balance(page).getByLabel('Eyes open — trial 1 (seconds)', { exact: true })).toHaveText('5')
  await balance(page).getByRole('button', { name: 'View Assessment History', exact: true }).click()
  const history = page.getByRole('dialog', { name: 'Static Balance history', exact: true })
  await expect(history.getByRole('button', { name: 'View Revisions', exact: true })).toHaveCount(2)
  await history.getByRole('button', { name: 'View Revisions', exact: true }).nth(1).click()
  await expect(history.getByRole('button', { name: 'View Saved Form', exact: true })).toHaveCount(2)
  await history.getByRole('button', { name: 'View Saved Form', exact: true }).first().click()
  await expect(balance(page).getByLabel('Eyes open — trial 1 (seconds)', { exact: true })).toHaveText('0')
  await expect(balance(page).getByRole('button', { name: 'Complete Assessment', exact: true })).toHaveCount(0)
  expect(writes(staffApi)).toHaveLength(1)
  expect(writes(staffApi)[0].body.previousAssessmentId).toBe(directoryId(20))
  expect(staffApi.state.assessmentStore.people.get(directoryId(3))).toHaveLength(2)
})

test('API assessment save stays committed when its follow-up record read fails', async ({ page, staffApi }) => {
  await openAssessments(page, staffApi)
  await page.getByRole('button', { name: 'Static Balance — Not filled', exact: true }).click()
  await balance(page).getByRole('spinbutton', { name: 'Eyes open — trial 1 (seconds)', exact: true }).fill('8')
  staffApi.state.assessmentRefreshFailure = true
  await balance(page).getByRole('button', { name: 'Complete Assessment', exact: true }).click()
  await expect(balance(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Retry Assessments', exact: true })).toBeVisible()
  staffApi.state.assessmentReadFailure = false
  await page.getByRole('button', { name: 'Retry Assessments', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Static Balance — Filled', exact: true })).toBeVisible()
  expect(writes(staffApi)).toHaveLength(1)
})

test('API inactive assessment history is read-only and assigned Trainers never load initial forms', async ({ page, staffApi }) => {
  await openAssessments(page, staffApi, { existing: true, inactive: true })
  await expect(page.getByRole('button', { name: 'Lifestyle & Health History — Not filled', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Static Balance — Filled', exact: true }).click()
  await expect(balance(page).getByRole('button', { name: 'Start Reassessment', exact: true })).toHaveCount(0)
  await expect(balance(page).getByRole('button', { name: 'View Assessment History', exact: true })).toBeVisible()
  await balance(page).getByRole('button', { name: 'Close', exact: true }).click()
  const reads = staffApi.state.assessmentReads
  staffApi.state.user = { ...staffApi.state.user, role: 'trainer', trainerId: directoryId(1) }
  staffApi.state.directory.packages = []
  await page.reload()
  await expect(page.getByRole('heading', { name: 'API Client', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Health & Assessments', exact: true })).toHaveCount(0)
  expect(staffApi.state.assessmentReads).toBe(reads)
  expect(writes(staffApi)).toHaveLength(0)
})
