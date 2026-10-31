import { fetchRoute, test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'trainer') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(row => row.name === `${info.project.name} ${purpose}`)
  expect(client).toBeDefined()
  const bookings = (await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id)
  const booking = bookings.find(row => row.sessionNumber === 1)
  const detail = await read(page, `/api/sessions/${booking.id}/details`)
  const item = detail.exercisePlan[0]
  expect(item.name).toBe('Recorded squat')
  await page.goto(`/#/sessions/${booking.id}`)
  await page.getByRole('button', { name: 'Manage video for Recorded squat', exact: true }).click()
  return { booking, item, path: `/api/sessions/${booking.id}/exercises/${item.id}/video` }
}
async function choose(page) {
  await page.getByLabel('Attach video for Recorded squat', { exact: true }).setInputFiles('tests/fixtures/silent-one-second.webm')
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Save Video', exact: true })).toBeEnabled()
}
async function save(page) {
  await page.getByRole('dialog').getByRole('button', { name: 'Save Video', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
}

test('Trainer recording UI persists real bytes after fresh login and removal remains durable', async ({ page, browser }, info) => {
  const original = await open(page, info, 'videowrite')
  await choose(page)
  await save(page)
  await page.reload()
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, 'trainer', `${info.project.name}-videowrite@example.test`)
    await fresh.goto(`/#/sessions/${original.booking.id}`)
    await fresh.getByRole('button', { name: 'Manage video for Recorded squat', exact: true }).click()
    await expect(fresh.locator('video')).toHaveAttribute('src', /^blob:/)
    await expect(fresh.getByText('Available until', { exact: false })).toBeVisible()
    const detail = await read(fresh, `/api/sessions/${original.booking.id}/details`)
    expect(detail.exercisePlan[0]).toMatchObject({ id: original.item.id, name: 'Recorded squat', videoAttached: true })
    expect(detail.purchase.used).toBe(0)
    await fresh.getByRole('button', { name: 'Remove saved video', exact: true }).click()
    await fresh.getByRole('dialog').getByRole('button', { name: 'Remove Video', exact: true }).click()
    await expect(fresh.getByRole('dialog')).toHaveCount(0)
    await fresh.reload()
    expect(await read(fresh, original.path)).toBeNull()
    expect((await read(fresh, `/api/sessions/${original.booking.id}/details`)).exercisePlan[0]).toMatchObject({ id: original.item.id, videoAttached: false })
  } finally { await context.close() }
})

test('lost recording commit freezes the original action and recovers without another upload', async ({ page }, info) => {
  const original = await open(page, info, 'videoloss', 'owner')
  await choose(page)
  let commits = 0, uploads = 0
  page.on('request', request => { if (request.method() === 'PUT') uploads++ })
  await page.route('**/api/session-media/intents/*/commit', async route => {
    commits++
    const response = await fetchRoute(route)
    expect(response.status()).toBe(200)
    await route.abort('failed')
  })
  await page.getByRole('dialog').getByRole('button', { name: 'Save Video', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('button', { name: 'Check Original Request', exact: true })).toBeVisible()
  await expect(dialog.locator('input[type=file]')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Check Original Request', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(commits).toBe(1); expect(uploads).toBe(1)
  await page.reload()
  expect((await read(page, `/api/sessions/${original.booking.id}/details`)).exercisePlan[0].videoAttached).toBe(true)
})

test('stale recording review and foreign Trainer requests leave all records unchanged', async ({ page, browser }, info) => {
  const original = await open(page, info, 'videostale')
  await choose(page)
  const context = await freshContext(browser, page)
  try {
    const owner = await context.newPage()
    await signIn(owner, 'owner', account('videostale'))
    const review = await read(owner, `/api/sessions/${original.booking.id}/plan-review`)
    const items = review.items.map(({ id, name, reps, rounds, rest, customDetails }) => ({ id, name, weight: '18 kg', reps, rounds, rest, customDetails }))
    expect((await post(owner, `/api/sessions/${original.booking.id}/plan`, { expected: review.expected, items })).status()).toBe(200)
    const rejected = page.waitForResponse(response => response.url().endsWith('/api/session-media/intents') && response.request().method() === 'POST')
    await page.getByRole('dialog').getByRole('button', { name: 'Save Video', exact: true }).click()
    await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible()
    expect((await rejected).status()).toBe(409)
    expect(await read(owner, original.path)).toBeNull()
    const directory = await read(owner, '/api/directory')
    const foreign = directory.clients.find(row => row.name === `${info.project.name} videoforeign`)
    expect(foreign).toBeDefined()
    const booking = (await read(owner, '/api/session-calendar')).sessions.find(row => row.clientId === foreign.id && row.sessionNumber === 1)
    const item = (await read(owner, `/api/sessions/${booking.id}/details`)).exercisePlan[0]
    const foreignPath = `/api/sessions/${booking.id}/exercises/${item.id}/video`
    const viewed = await read(owner, `${foreignPath}/review`)
    expect((await page.request.get(foreignPath)).status()).toBe(404)
    expect((await post(page, '/api/session-media/intents', { sessionId: booking.id, exerciseId: item.id, expected: viewed.expected, remove: true, upload: null })).status()).toBe(404)
    expect(await read(owner, `${foreignPath}/review`)).toEqual(viewed)
  } finally { await context.close() }
})
