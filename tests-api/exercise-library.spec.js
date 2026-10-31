import { fetchRoute, test, expect, signIn, read, post, account, freshContext, confirm } from './fixtures.js'
import { createHash } from 'node:crypto'

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGMwaPj/HwAFQgKv8Qz/1QAAAABJRU5ErkJggg==', 'base64')
const catalogue = page => read(page, '/api/exercise-library')
async function create(page, name, media = false) {
  await page.goto('/#/exercises/new')
  await page.getByLabel('Exercise name', { exact: false }).fill(name)
  if (media) await page.getByLabel('Photo / video', { exact: true }).setInputFiles({ name: 'reference.png', mimeType: 'image/png', buffer: png })
  const refreshed = page.waitForResponse(async response => response.url().endsWith('/api/exercise-library') && response.request().method() === 'GET' && response.ok() && (await response.json()).items.some(item => item.name === name))
  await confirm(page, 'Create Exercise')
  await refreshed
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  return (await catalogue(page)).items.find(item => item.name === name)
}

for (const role of ['owner', 'admin']) test(`${role} library UI stores real media and retains it after fresh login`, async ({ page, browser }, info) => {
  const scope = role === 'owner' ? 'library' : 'libraryadmin', email = account(scope, role)
  const name = `${info.project.name} ${role} persisted movement`
  await signIn(page, role, email)
  const saved = await create(page, name, true)
  expect(saved.media).toMatchObject({ name: 'reference.png', type: 'image/png', size: png.length })
  await expect(page.getByAltText('Exercise reference')).toBeVisible()
  expect(await page.getByAltText('Exercise reference').evaluate(image => image.naturalWidth)).toBe(1)
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, role, email)
    await fresh.goto(`/#/exercises/${saved.id}`)
    await expect(fresh.getByRole('heading', { name, exact: true })).toBeVisible()
    await expect(fresh.getByAltText('Exercise reference')).toBeVisible()
    expect(await fresh.getByAltText('Exercise reference').evaluate(image => image.naturalWidth)).toBe(1)
    await fresh.getByRole('button', { name: 'Edit Exercise', exact: true }).click()
    await fresh.getByRole('button', { name: 'Remove Attachment', exact: true }).click()
    await confirm(fresh, 'Save Exercise')
    await expect(fresh.getByText('No attachment', { exact: true })).toBeVisible()
    await fresh.reload()
    await expect(fresh.getByText('No attachment', { exact: true })).toBeVisible()
    expect((await fresh.request.get(`/api/exercise-library/media/${saved.media.id}`)).status()).toBe(404)
    expect((await catalogue(fresh)).items.find(item => item.id === saved.id)).toMatchObject({ version: 2, media: null })
  } finally { await context.close() }
})

test('stale library edits, foreign recovery and Trainer mutations cannot change stored records', async ({ page, browser }, info) => {
  await signIn(page, 'owner', account('librarystale'))
  const saved = await create(page, `${info.project.name} original library`)
  const key = crypto.randomUUID()
  const body = { id: saved.id, expectedVersion: saved.version, name: `${info.project.name} reviewed library`, category: saved.category, description: 'Original reviewed change', status: 'active' }
  expect((await post(page, '/api/exercise-library/save-intents', body, key)).status()).toBe(200)
  const stale = crypto.randomUUID()
  expect((await post(page, '/api/exercise-library/save-intents', { ...body, name: `${info.project.name} stale library` }, stale)).status()).toBe(200)
  const changed = await post(page, `/api/exercise-library/save-intents/${key}/commit`, {}, key)
  expect(changed.status()).toBe(200)
  expect((await post(page, `/api/exercise-library/save-intents/${stale}/commit`, {}, stale)).status()).toBe(409)
  expect((await post(page, `/api/exercise-library/save-intents/${key}/commit`, { actorId: saved.id }, key)).status()).toBe(422)
  const hidden = await create(page, `${info.project.name} inactive library`)
  await confirm(page, 'Deactivate Exercise')
  const context = await freshContext(browser, page)
  try {
    const other = await context.newPage()
    await signIn(other, 'owner', account('libraryforeign'))
    expect((await other.request.get(`/api/exercise-library/save-intents/${key}`)).status()).toBe(404)
    expect((await catalogue(other)).items.some(item => item.id === hidden.id)).toBe(true)
  } finally { await context.close() }
  const trainerContext = await freshContext(browser, page)
  try {
    const trainer = await trainerContext.newPage()
    await signIn(trainer, 'trainer')
    const visible = (await catalogue(trainer)).items
    expect(visible.some(item => item.id === saved.id)).toBe(true)
    expect(visible.some(item => item.id === hidden.id)).toBe(false)
    expect((await post(trainer, '/api/exercise-library/save-intents', body)).status()).toBe(403)
    expect((await trainer.request.get(`/api/exercise-library/save-intents/${key}`)).status()).toBe(403)
  } finally { await trainerContext.close() }
  const current = (await catalogue(page)).items.find(item => item.id === saved.id)
  expect(current).toMatchObject({ version: 2, name: body.name, description: body.description })
})

for (const interrupted of ['commit', 'upload']) test(`lost library ${interrupted} response recovers the original stored upload without repeating it`, async ({ page, browser }, info) => {
  const email = account(interrupted === 'commit' ? 'libraryloss' : 'libraryuploadloss'), name = `${info.project.name} interrupted library ${interrupted}`
  await signIn(page, 'owner', email)
  let commits = 0, uploads = 0, key
  page.on('request', request => {
    if (request.method() === 'PUT') uploads++
    if (request.method() === 'POST' && request.url().endsWith('/commit')) { commits++; key = request.url().split('/').at(-2) }
  })
  const interruptedRoute = interrupted === 'commit' ? '**/api/exercise-library/save-intents/*/commit' : '**/library/**'
  await page.route(interruptedRoute, async route => {
    if (interrupted === 'upload') {
      expect(route.request().method()).toBe('PUT')
      expect(await route.request().headerValue('x-amz-checksum-sha256')).toBe(createHash('sha256').update(png).digest('base64'))
    }
    // WebKit interception omits File body bytes. Forward the exact selected fixture
    // while retaining its real signed checksum, conditional write and length check.
    const response = await fetchRoute(route, interrupted === 'upload' ? { postData: png } : {})
    expect(response.status()).toBe(200)
    await route.abort('failed')
  })
  await page.goto('/#/exercises/new')
  await page.getByLabel('Exercise name', { exact: false }).fill(name)
  await page.getByLabel('Photo / video', { exact: true }).setInputFiles({ name: 'reference.png', mimeType: 'image/png', buffer: png })
  await confirm(page, 'Create Exercise')
  await expect(page.getByRole('button', { name: 'Check original exercise save', exact: true })).toBeVisible()
  // Focus refresh may already replace the frozen editor with the original-save recovery page.
  await expect(page.getByRole('textbox', { name: /Exercise name/ }).and(page.locator(':enabled'))).toHaveCount(0)
  await page.unroute(interruptedRoute)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check original exercise save', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Check original exercise save', exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  expect(commits).toBe(1); expect(uploads).toBe(1)
  const original = await read(page, `/api/exercise-library/save-intents/${key}`)
  expect(original.state).toBe('completed')
  expect((await catalogue(page)).items.filter(item => item.name === name)).toHaveLength(1)
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, 'owner', email)
    await fresh.goto(`/#/exercises/${original.result.id}`)
    await expect(fresh.getByAltText('Exercise reference')).toBeVisible()
    expect(await fresh.getByAltText('Exercise reference').evaluate(image => image.naturalWidth)).toBe(1)
  } finally { await context.close() }
})


test('Admin library upload waits for reviewed publication and recovers a lost Owner decision', async ({ page, browser }, info) => {
  await signIn(page, 'owner', account('libraryapproval'))
  const admin = (await read(page, '/api/staff/admins')).find(row => row.details.email === account('libraryapproval', 'admin'))
  expect(admin).toBeTruthy()
  const policy = await post(page, `/api/staff/admins/${admin.id}`, {
    expectedVersion: admin.version, operation: 'approvals',
    approvalNeeded: { ...admin.approvalNeeded, exerciseLibrary: true },
  })
  expect(policy.status()).toBe(200)
  const context = await freshContext(browser, page)
  try {
    const staff = await context.newPage(), name = `${info.project.name} approved library attachment`
    await signIn(staff, 'admin', account('libraryapproval', 'admin'))
    await staff.goto('/#/exercises/new')
    await staff.getByLabel('Exercise name', { exact: false }).fill(name)
    await staff.getByLabel('Photo / video', { exact: true }).setInputFiles({ name: 'reference.png', mimeType: 'image/png', buffer: png })
    let submissions = 0
    staff.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/commit')) submissions++ })
    await staff.route('**/api/exercise-library/save-intents/*/commit', async route => {
      const response = await fetchRoute(route)
      expect(response.status()).toBe(202)
      await route.abort('failed')
    }, { times: 1 })
    await confirm(staff, 'Create Exercise')
    await staff.getByRole('button', { name: 'Check original exercise save', exact: true }).click()
    await expect(staff.getByRole('heading', { name: 'Exercise submitted for approval', exact: true })).toBeVisible()
    expect((await catalogue(staff)).items.some(item => item.name === name)).toBe(false)
    expect(submissions).toBe(1)
    const proposals = (await read(staff, '/api/admin-requests')).filter(item => item.operation === 'library.publish' && item.body.review.proposed.name === name)
    expect(proposals).toHaveLength(1)
    const proposal = proposals[0]
    await page.goto('/#/messages')
    const row = page.locator('.info-row').filter({ hasText: proposal.actorName }).filter({ hasText: 'Manage the Exercise Library' }).filter({ hasText: 'pending' })
    await row.getByRole('button', { name: 'Review', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Save Exercise Library entry', exact: true })).toBeVisible()
    await expect(page.getByAltText('Exercise reference')).toBeVisible()
    expect(await page.getByAltText('Exercise reference').evaluate(image => image.naturalWidth)).toBe(1)
    let decisions = 0
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith(`/${proposal.id}/decision`)) decisions++ })
    await page.route(`**/api/admin-requests/${proposal.id}/decision`, async route => {
      const response = await fetchRoute(route)
      expect(response.status()).toBe(200)
      await route.abort('failed')
    }, { times: 1 })
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
    await page.getByRole('dialog', { name: 'Approve?', exact: true }).getByRole('button', { name: 'Approve', exact: true }).click()
    await page.getByRole('button', { name: 'Check Original Decision', exact: true }).click()
    await expect(page.getByText(`${proposal.actorName} · approved`, { exact: true })).toBeVisible()
    expect(decisions).toBe(1)
    expect((await page.request.get(`/api/admin-requests/${proposal.id}/attachment`)).status()).toBe(404)
    const saved = (await catalogue(staff)).items.filter(item => item.name === name)
    expect(saved).toHaveLength(1)
    expect(saved[0]).toMatchObject({ version: 1, media: { name: 'reference.png', size: png.length } })
    await staff.goto(`/#/exercises/${saved[0].id}`)
    await staff.reload()
    await expect(staff.getByRole('heading', { name, exact: true })).toBeVisible()
    await expect(staff.getByAltText('Exercise reference')).toBeVisible()
    expect(await staff.getByAltText('Exercise reference').evaluate(image => image.naturalWidth)).toBe(1)
  } finally { await context.close() }
})
