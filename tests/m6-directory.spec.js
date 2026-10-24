import { directoryData, directoryId } from '../src/test/directory.js'
import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'
import { fillClientRequiredFields } from './fixtures.js'

async function profileTab(page, name) {
  const menu = page.locator('details.profile-menu')
  const button = menu.getByRole('button', { name, exact: true })
  const summary = menu.locator('summary')
  if (await summary.isVisible() && await menu.getAttribute('open') === null) await summary.click()
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

async function beginApiClient(page, staffApi, admin = false) {
  await openDirectory(page, staffApi)
  Object.assign(staffApi.state.directory, { clientCreation: true, clientOnboardingPolicy: {
    defaultCountryCode: '+65', defaultRelationship: 'Spouse', weeklyFrequencies: [1, 2, 3, 4, 5, 6, 7], freeGymMinimumFrequency: 2, availability: { from: '18:00', to: '19:00' },
  } })
  if (admin) {
    staffApi.state.user = { ...staffApi.state.user, role: 'admin', name: 'API Admin' }
    delete staffApi.state.directory.trainers[0].peak_rate_cents
    delete staffApi.state.directory.trainers[0].off_peak_rate_cents
  }
  await page.reload()
  await page.getByRole('button', { name: 'View Clients', exact: true }).click()
  await page.getByRole('button', { name: 'Add New Client', exact: true }).click()
  await page.getByLabel('Client name', { exact: true }).fill('Created API Client')
  await fillClientRequiredFields(page)
  await page.getByRole('button', { name: 'Continue to Health & Assessments', exact: true }).click()
  await page.getByRole('button', { name: /^Static Balance — / }).click()
  const assessment = page.getByRole('dialog', { name: 'Static Balance', exact: true })
  await assessment.getByLabel('Eyes open — trial 1 (seconds)', { exact: true }).fill('10')
  await assessment.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('button', { name: 'Continue to Package & Preferences', exact: true }).click()
  await page.getByLabel('Start date', { exact: true }).fill('2027-06-07')
  await page.getByRole('button', { name: 'Continue to Client Availability', exact: true }).click()
  await page.getByRole('button', { name: 'Monday', exact: true }).click()
  await page.getByRole('button', { name: 'Add Time', exact: true }).click()
  await page.getByRole('button', { name: 'Continue to Trainer Matching', exact: true }).click()
}

test('API client creation retries matching and recovers the original save through a directory outage', async ({ page, staffApi }) => {
  staffApi.state.clientMatchFailure = true
  await beginApiClient(page, staffApi)
  await page.getByRole('button', { name: 'Retry Matching', exact: true }).click()
  await expect(page.getByLabel('Matched trainer', { exact: true })).toHaveValue(directoryId(1))
  await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
  staffApi.state.clientCreateUnknown = true
  await page.getByRole('button', { name: 'Create Client', exact: true }).click()
  await page.getByRole('dialog', { name: 'Create Created API Client?', exact: true }).getByRole('button', { name: 'Create Client', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Check Client Creation', exact: true })).toBeVisible()
  staffApi.state.unavailable = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  await expect(page.getByText(/Your client creation progress is retained/)).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await page.getByRole('button', { name: 'Check Client Creation', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`#/clients/${directoryId(100)}$`))
  await expect(page.getByRole('heading', { name: 'Created API Client', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Created API Client', exact: true })).toBeVisible()
  expect(staffApi.state.mutations.filter(m => m.path === '/api/clients')).toHaveLength(1)
  expect(staffApi.state.directory.clients.filter(c => c.name === 'Created API Client')).toHaveLength(1)
  expect(staffApi.state.clientCreationBody.people[0].assessments[0].answers).toEqual({ eyes_open_1: 10 })
  expect(staffApi.state.clientCreationBody.people[0].assessments[0]).not.toHaveProperty('assessor')
})

test('API Admin client creation remains successful when the follow-up directory read fails', async ({ page, staffApi }) => {
  await beginApiClient(page, staffApi, true)
  await expect(page.getByLabel('Matched trainer', { exact: true })).toHaveValue(directoryId(1))
  await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
  staffApi.state.clientCreateRefreshFailure = true
  await page.getByRole('button', { name: 'Create Client', exact: true }).click()
  await page.getByRole('dialog', { name: 'Create Created API Client?', exact: true }).getByRole('button', { name: 'Create Client', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`#/clients/${directoryId(100)}$`))
  await expect(page.getByRole('heading', { name: 'Created API Client', exact: true })).toBeVisible()
  expect(staffApi.state.mutations.filter(m => m.path === '/api/clients')).toHaveLength(1)
})

test('API client onboarding keeps creation blocked when the server finds no free cadence', async ({ page, staffApi }) => {
  staffApi.state.clientNoMatches = true
  await beginApiClient(page, staffApi)
  await expect(page.getByLabel('Matched trainer', { exact: true })).toBeDisabled()
  await expect(page.getByText(/No active trainer is free for every session/)).toBeVisible()
  await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Choose a matched trainer.')
  await expect(page.getByRole('button', { name: 'Create Client', exact: true })).toHaveCount(0)
  expect(staffApi.state.mutations.filter(m => m.path === '/api/clients')).toHaveLength(0)
})

test('API trainer profile saves preserve verified email and cleared optional contacts across reload', async ({ page, staffApi }) => {
  await openDirectory(page, staffApi)
  staffApi.state.directory.trainerPersonalWrites = true
  staffApi.state.directory.trainerProfilePolicy = { defaultCountryCode: '+65', trainerTypes: ['Strength & Conditioning', 'Personal Trainer'] }
  await page.reload()
  await page.getByRole('button', { name: 'View Trainers', exact: true }).click()
  await page.getByRole('button', { name: 'View API Trainer', exact: true }).click()
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information', exact: true }) })
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByLabel('Trainer email', { exact: true })).toHaveAttribute('readonly', '')
  await page.getByLabel('Trainer name', { exact: true }).fill('Updated Trainer')
  await page.getByLabel('Trainer phone number', { exact: true }).fill('')
  await page.getByLabel('Trainer birthday', { exact: true }).click()
  await page.getByRole('dialog', { name: 'Trainer birthday calendar', exact: true }).getByRole('button', { name: 'Clear', exact: true }).click()
  const save = async () => {
    await panel.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  }
  staffApi.state.trainerDetailUnknown = true
  await save()
  await expect(panel.getByRole('alert')).toHaveText('Staff service unavailable. Please retry.')
  await save()
  await expect(page.getByRole('heading', { name: 'Updated Trainer', exact: true })).toBeVisible()
  await expect(panel.locator('.info-row').filter({ hasText: 'Mobile Number' }).locator('strong')).toHaveText('')
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/personal-details'))).toHaveLength(1)
  await page.reload()
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByLabel('Trainer phone number', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('Trainer birthday', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('Trainer email', { exact: true })).toHaveValue('trainer@fixture.test')
  await page.getByLabel('Trainer qualifications', { exact: true }).fill('Revised credentials')
  staffApi.state.trainerDetailRefreshFailure = true
  await save()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText('Revised credentials', { exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  expect(staffApi.state.directory.trainers[0].peak_rate_cents).toBe(8000)
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/personal-details'))).toHaveLength(2)
})

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
  await expect(page.getByLabel('New trainer login email', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Check Original Request', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
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


async function inactiveApiTrainer(page, staffApi, admin = false) {
  await openDirectory(page, staffApi)
  staffApi.state.directory.trainerReactivationWrites = true
  staffApi.state.directory.trainers[0].status = 'inactive'
  if (admin) {
    staffApi.state.user = { ...staffApi.state.user, role: 'admin', name: 'API Admin' }
    delete staffApi.state.directory.trainers[0].peak_rate_cents
    delete staffApi.state.directory.trainers[0].off_peak_rate_cents
  }
  await page.goto(`${staffApi.origin}/#/trainers/${directoryId(1)}`)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'API Trainer', exact: true })).toBeVisible()
  const summary = page.locator('details.profile-menu > summary')
  if (await summary.isVisible()) await summary.click()
}

test('API trainer reactivation reconciles an interrupted response and persists across reload', async ({ page, staffApi }) => {
  await inactiveApiTrainer(page, staffApi)
  staffApi.state.trainerReactivationUnknown = true
  await page.getByRole('button', { name: 'Reactivate Trainer', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Reactivate API Trainer?', exact: true })
  await expect(dialog).toContainText('A fresh sign-in is required')
  await dialog.getByRole('button', { name: 'Reactivate Trainer', exact: true }).click()
  await profileTab(page, 'Check Reactivation')
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Active')
  await page.reload()
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Active')
  await expect(page.getByRole('button', { name: 'Reactivate Trainer', exact: true })).toHaveCount(0)
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/reactivation'))).toHaveLength(1)
})

test('API Admin trainer reactivation remains successful after directory refresh failure', async ({ page, staffApi }) => {
  await inactiveApiTrainer(page, staffApi, true)
  staffApi.state.trainerReactivationRefreshFailure = true
  await page.getByRole('button', { name: 'Reactivate Trainer', exact: true }).click()
  await page.getByRole('dialog', { name: 'Reactivate API Trainer?', exact: true }).getByRole('button', { name: 'Reactivate Trainer', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal', exact: true })).toBeVisible()
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Active')
  await expect(page.getByRole('heading', { name: 'Pay Rates', exact: true })).toHaveCount(0)
  expect(staffApi.state.mutations.filter(m => m.path.endsWith('/reactivation'))).toHaveLength(1)
})
