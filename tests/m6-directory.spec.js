import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

async function profileTab(page, name) {
  const menu = page.locator('details.profile-menu')
  const button = menu.getByRole('button', { name, exact: true })
  if (!(await button.isVisible())) await menu.locator('summary').click()
  await button.click()
}
async function openDirectory(page, staffApi, legacy = false) {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  staffApi.state.directory = directoryData()
  if (legacy) delete staffApi.state.directory.packagePolicy
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
}

test('API trainer email stays pending until account-holder verification and reconciles a lost result', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.trainerEmailWrites = true
  await page.reload()
  await page.getByRole('button', { name: 'View Trainers', exact: true }).click()
  await page.getByRole('button', { name: 'View API Trainer', exact: true }).click()
  await page.getByRole('button', { name: 'Change Login Email', exact: true }).click()
  await page.getByLabel('New trainer login email', { exact: true }).fill('new@fixture.test')
  const submit = async () => {
    await page.getByRole('button', { name: 'Request Verification', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Request Verification', exact: true }).click()
  }
  staffApi.state.emailRequestUnknown = true
  await submit()
  await expect(page.getByRole('alert')).toHaveText('Staff service unavailable. Please retry.')
  await submit()
  await expect(page.getByText(/Awaiting the trainer’s verification/)).toBeVisible()
  expect(staffApi.state.directory.trainers[0].email).toBe('trainer@fixture.test')
  expect(staffApi.state.mutations.filter(m => m.path === `/api/trainers/${directoryId(1)}/email-change`)).toHaveLength(1)
  await page.reload()
  await expect(page.getByText(/Awaiting the trainer’s verification/)).toBeVisible()
  await page.getByRole('button', { name: 'Home', exact: true }).click()
  await page.getByRole('button', { name: 'Sign Out', exact: true }).click()
  staffApi.state.user = { id: directoryId(80), name: 'API Trainer', role: 'trainer', trainerId: directoryId(1), email: 'trainer@fixture.test' }
  staffApi.state.directory.viewerId = directoryId(80)
  staffApi.state.directory.packages = []
  await page.getByLabel('Email', { exact: true }).fill('trainer@fixture.test')
  await page.getByLabel('Password', { exact: true }).fill('initial-password')
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await verifyAuthenticator(page)
  await page.getByRole('button', { name: 'Send Verification Code', exact: true }).click()
  await page.getByLabel('Email verification code', { exact: true }).fill('123456')
  staffApi.state.emailVerifyUnknown = true
  await page.getByRole('button', { name: 'Verify New Email', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Verify New Email', exact: true })).toBeDisabled()
  expect(staffApi.state.user.email).toBe('trainer@fixture.test')
  await page.getByRole('button', { name: 'Check Verification Status', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  expect(staffApi.state.user.email).toBe('new@fixture.test')
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/verify'))).toHaveLength(1)
  await page.getByLabel('Email', { exact: true }).fill('new@fixture.test')
  await page.getByLabel('Password', { exact: true }).fill('initial-password')
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await verifyAuthenticator(page)
  await expect(page.getByText('new@fixture.test', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Verify your new email', exact: true })).toHaveCount(0)
})

test('API directory searches clients and opens purchased terms with working Back', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Clients', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add New Client' })).toHaveCount(0)
  await page.getByLabel('Search client', { exact: true }).fill('API Client')
  await page.getByRole('button', { name: 'View API Client', exact: true }).click()
  await expect(page.getByText('client@fixture.test', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Health & Assessments' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0)
  await profileTab(page, 'Package')
  await expect(page.getByText('Purchased Twelve', { exact: true })).toBeVisible()
  await expect(page.getByLabel('25% package used')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add Package' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Back', exact: true }).click()
  await expect(page.getByLabel('Search client', { exact: true })).toHaveValue('API Client')
})

test('older API keeps trainer and package writes unavailable without the package policy', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi, true)
  await page.getByRole('button', { name: 'View Trainers', exact: true }).click()
  await page.getByRole('button', { name: 'View API Trainer', exact: true }).click()
  await expect(page.getByText('$80 / session', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0)
  await profileTab(page, 'Availability')
  await expect(page.getByText('10:00am–11:00am', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Home', exact: true }).click()
  await page.getByRole('button', { name: 'View Packages', exact: true }).click()
  await page.getByRole('button', { name: 'View package Current Template', exact: true }).click()
  await expect(page.getByText('180 days', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit Package', exact: true })).toHaveCount(0)
})

test('API empty purchase and interrupted refresh never become fabricated or cached records', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.clients[0].purchases = []
  await page.reload()
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await page.getByRole('button', { name: 'View API Client', exact: true }).click()
  await profileTab(page, 'Package')
  await expect(page.getByText('No active current package.', { exact: true })).toBeVisible()
  staffApi.state.unavailable = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'API Client' })).toHaveCount(0)
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'API Client' })).toBeVisible()
  const saved = await page.evaluate(() => JSON.stringify({ local: localStorage, session: sessionStorage }))
  expect(saved).not.toContain('client@fixture.test')
  expect(saved).not.toContain('91234568')
  await page.getByRole('button', { name: 'Home', exact: true }).click()
  await page.getByRole('button', { name: 'Sign Out', exact: true }).click()
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
})

test('API package setup reconciles interruption and retains a committed save through refresh failure', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  await page.getByRole('button', { name: 'View Packages', exact: true }).click()
  await page.getByRole('button', { name: 'Add Package', exact: true }).click()
  await page.getByLabel('Package name', { exact: true }).fill('API Eighteen')
  await page.getByLabel('Package session count', { exact: true }).fill('18')
  const confirm = async name => {
    await page.getByRole('button', { name, exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name, exact: true }).click()
  }
  staffApi.state.packageUnknown = true
  await confirm('Create Package')
  await expect(page.locator('.package-form [role="alert"]')).toBeVisible()
  await confirm('Create Package')
  await expect(page.getByRole('heading', { name: 'API Eighteen', exact: true })).toBeVisible()
  await expect(page.getByText('135 days', { exact: true })).toBeVisible()
  expect(staffApi.state.mutations.filter(m => m.path === '/api/packages')).toHaveLength(1)
  await page.getByRole('button', { name: 'Edit Package', exact: true }).click()
  await page.getByLabel('Package name', { exact: true }).fill('API Edited')
  staffApi.state.packageRefreshFailure = true
  await confirm('Save Package')
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  const saved = staffApi.state.directory.packages.find(p => p.name === 'API Edited')
  expect(saved.version).toBe(2)
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'API Edited', exact: true })).toBeVisible()
  await confirm('Deactivate Package')
  await expect(page.getByRole('button', { name: 'Reactivate Package', exact: true })).toBeVisible()
  await confirm('Reactivate Package')
  await expect(page.getByRole('button', { name: 'Deactivate Package', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'API Edited', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Deactivate Package', exact: true })).toBeVisible()
  expect(staffApi.state.directory.clients[0].purchases[0].name).toBe('Purchased Twelve')
  await page.getByRole('button', { name: 'Back', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Packages', exact: true })).toBeVisible()
})

test('API approval settings reconcile interrupted saves and survive refresh failure without unlocking other edits', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.trainerApprovalWrites = true
  await page.reload()
  await page.getByRole('button', { name: 'View Trainers', exact: true }).click()
  await page.getByRole('button', { name: 'View API Trainer', exact: true }).click()
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Owner Approval Needed' }) })
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(1)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await panel.getByRole('checkbox', { name: 'Availability changes' }).uncheck()
  const save = async () => {
    await panel.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Save Controls', exact: true }).click()
  }
  staffApi.state.approvalUnknown = true
  await save()
  await expect(page.getByText('Staff service unavailable. Please retry.', { exact: true })).toBeVisible()
  await save()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  await expect(panel.getByRole('checkbox', { name: 'Availability changes' })).not.toBeChecked()
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/approvals'))).toHaveLength(1)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await panel.getByRole('checkbox', { name: 'Session time changes' }).uncheck()
  staffApi.state.approvalRefreshFailure = true
  await save()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  await expect(panel.getByRole('checkbox', { name: 'Session time changes' })).not.toBeChecked()
  await page.reload()
  await expect(panel.getByRole('checkbox', { name: 'Availability changes' })).not.toBeChecked()
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/approvals'))).toHaveLength(2)
  await page.getByRole('button', { name: 'Back', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Trainers', exact: true })).toBeVisible()
})

test('API client optional contacts stay cleared after saving and reloading', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.clientPersonalWrites = true
  await page.reload()
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await page.getByRole('button', { name: 'View API Client', exact: true }).click()
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information' }) })
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Client email', { exact: true }).fill('')
  await page.getByLabel('Client birthday', { exact: true }).click()
  await page.getByRole('dialog', { name: 'Client birthday calendar', exact: true }).getByRole('button', { name: 'Clear', exact: true }).click()
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  await page.reload()
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByLabel('Client email', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('Client birthday', { exact: true })).toHaveValue('')
  expect(staffApi.state.directory.clients[0].people[0].birthday).toBeNull()
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/personal-details'))).toHaveLength(1)
})

test('API client contact edits preserve purchases and reconcile before retrying an interrupted save', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.clientPersonalWrites = true
  const purchases = structuredClone(staffApi.state.directory.clients[0].purchases)
  await page.reload()
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await page.getByRole('button', { name: 'View API Client', exact: true }).click()
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information' }) })
  await expect(page.getByRole('button', { name: 'Reassign Trainer' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(1)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Client name', { exact: true }).fill('Updated API Client')
  const save = async () => {
    await panel.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  }
  staffApi.state.clientDetailUnknown = true
  await save()
  await expect(panel.getByRole('alert')).toHaveText('Staff service unavailable. Please retry.')
  await save()
  await expect(page.getByRole('heading', { name: 'Updated API Client', exact: true })).toBeVisible()
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/personal-details'))).toHaveLength(1)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Client email', { exact: true }).fill('updated@fixture.test')
  staffApi.state.clientDetailRefreshFailure = true
  await save()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText('updated@fixture.test', { exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('updated@fixture.test', { exact: true })).toBeVisible()
  expect(staffApi.state.directory.clients[0].purchases).toEqual(purchases)
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/personal-details'))).toHaveLength(2)
  await page.getByRole('button', { name: 'Back', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Clients', exact: true })).toBeVisible()
})


test('API general notes reconcile saves and survive reload without enabling assessment forms', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.clientNoteWrites = true
  await page.reload()
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await page.getByRole('button', { name: 'View API Client', exact: true }).click()
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Health / Limitation Notes', exact: true }) })
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Health / Limitation Notes', { exact: true }).fill('General knee guidance')
  const save = async () => {
    await panel.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  }
  staffApi.state.clientNoteUnknown = true
  await save()
  await expect(page.getByText('Staff service unavailable. Please retry.', { exact: true })).toBeVisible()
  await save()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  await page.reload()
  await expect(panel.getByText('General knee guidance', { exact: true })).toBeVisible()
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/notes'))).toHaveLength(1)
  await expect(page.getByRole('heading', { name: 'Initial Assessment', exact: true })).toHaveCount(0)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Health / Limitation Notes', { exact: true }).fill('')
  staffApi.state.clientNoteRefreshFailure = true
  await save()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByLabel('Health / Limitation Notes', { exact: true })).toHaveValue('')
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/notes'))).toHaveLength(2)
})

test('API Owner rates reconcile uncertain saves and persist exact cents after reload', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.trainerRateWrites = true
  await page.reload()
  await page.getByRole('button', { name: 'View Trainers', exact: true }).click()
  await page.getByRole('button', { name: 'View API Trainer', exact: true }).click()
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Training & Rates', exact: true }) })
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(1)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Peak rate', { exact: true }).fill('65.43')
  const save = async () => {
    await panel.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Save Rates', exact: true }).click()
  }
  staffApi.state.rateUnknown = true
  await save()
  await expect(page.getByText('Staff service unavailable. Please retry.', { exact: true })).toBeVisible()
  await save()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  await page.reload()
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByLabel('Peak rate', { exact: true })).toHaveValue('65.43')
  expect(staffApi.state.directory.trainers[0].peak_rate_cents).toBe(6543)
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/rates'))).toHaveLength(1)
})
