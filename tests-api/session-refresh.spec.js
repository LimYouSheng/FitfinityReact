import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'owner') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(row => row.name === `${info.project.name} ${purpose}`)
  const sessions = (await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(sessions).toHaveLength(2)
  await page.goto(`/#/sessions/${sessions[0].id}`)
  await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
  return { id: sessions[0].id, client, directory }
}
async function planDraft(page) {
  await page.getByRole('button', { name: 'Start Plan', exact: true }).click()
  await page.getByRole('combobox', { name: 'Exercise 1 name', exact: true }).click()
  await page.getByRole('button', { name: 'Custom Exercise', exact: true }).click()
  await page.getByLabel('Exercise 1 custom name', { exact: true }).fill('Retained independent plan')
  await page.getByRole('button', { name: 'Use Custom Exercise', exact: true }).click()
  for (const [field, value] of [['weight', '17 kg'], ['reps', '8'], ['rounds', '3'], ['rest', '60s']]) await page.getByLabel(`Exercise 1 ${field}`, { exact: true }).fill(value)
}

for (const kind of ['plan', 'outcome', 'summary']) test(`${kind} draft survives an interrupted background read and persists after retry and fresh login`, async ({ page, browser }, info) => {
  const purpose = `${kind}refresh`, { id, client, directory } = await open(page, info, purpose)
  const foreign = directory.clients.find(row => row.id !== client.id)
  expect(foreign).toBeTruthy()
  let panel, field
  if (kind === 'plan') {
    await planDraft(page)
    panel = page.locator('.exercise-plan-panel')
    field = page.getByLabel('Exercise 1 weight', { exact: true })
  } else {
    panel = page.locator(kind === 'outcome' ? '.session-outcome-panel' : '.client-summary-panel')
    await panel.getByRole('button', { name: 'Edit', exact: true }).click()
    field = page.getByRole('textbox', { name: kind === 'outcome' ? 'Trainer comments' : 'Client-facing summary', exact: true })
    await field.fill(`Retained ${kind} draft`)
  }
  let interrupted = false
  await page.route(`**/api/sessions/${id}/details`, async route => {
    if (interrupted) return route.continue()
    interrupted = true
    await route.abort('failed')
  })
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('button', { name: 'Retry session', exact: true })).toBeVisible()
  await expect(field).toHaveValue(kind === 'plan' ? '17 kg' : `Retained ${kind} draft`)
  await page.getByRole('button', { name: 'Retry session', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Retry session', exact: true })).toHaveCount(0)
  await expect(field).toHaveValue(kind === 'plan' ? '17 kg' : `Retained ${kind} draft`)
  await (kind === 'plan' ? page : panel).getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: kind === 'plan' ? 'Save Plan' : kind === 'outcome' ? 'Save Outcome' : 'Save Summary', exact: true }).click()
  await expect(field).toHaveCount(0)
  await page.reload()
  await expect(page.getByText(kind === 'plan' ? 'Retained independent plan' : `Retained ${kind} draft`, { exact: true }).first()).toBeVisible()
  const context = await freshContext(browser, page)
  try {
    const next = await context.newPage()
    await signIn(next, 'owner', account(purpose))
    const saved = await read(next, `/api/sessions/${id}/details`)
    if (kind === 'plan') expect(saved.exercisePlan).toMatchObject([{ name: 'Retained independent plan', weight: '17 kg' }])
    else expect(saved[kind === 'outcome' ? 'trainerComments' : 'clientSummary']).toBe(`Retained ${kind} draft`)
    expect((await read(next, '/api/directory')).clients.find(row => row.id === foreign.id)).toEqual(foreign)
  } finally { await context.close() }
})

test('competing booking refresh preserves reviewed draft and stale rejection, then Cancel displays current times', async ({ page }, info) => {
  const { id } = await open(page, info, 'bookingrefresh')
  const panel = page.locator('.session-overview-panel')
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Session start time', { exact: true }).fill('14:00')
  await page.getByLabel('Session end time', { exact: true }).fill('15:00')
  const review = await read(page, `/api/sessions/${id}/booking-review`)
  expect((await post(page, `/api/sessions/${id}/booking`, { expected: review.expected, date: review.session.date, startsAt: '16:00', endsAt: '17:00', trainerId: review.session.trainerId })).status()).toBe(200)
  const refreshed = page.waitForResponse(response => response.url().endsWith(`/api/sessions/${id}/details`))
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  expect((await refreshed).status()).toBe(200)
  await expect(page.getByLabel('Session start time', { exact: true })).toHaveValue('14:00')
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  const rejected = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/api/sessions/${id}/booking`))
  await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  expect((await rejected).status()).toBe(409)
  await expect(page.getByLabel('Session start time', { exact: true })).toHaveValue('14:00')
  await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(panel).toContainText('16:00–17:00')
  expect((await read(page, `/api/sessions/${id}/details`)).session.startsAt).toBe('16:00')
})

test('assignment change retires a Trainer plan draft while retaining only historical read access', async ({ page, browser }, info) => {
  const { id } = await open(page, info, 'planrevoked', 'trainer')
  await planDraft(page)
  const context = await freshContext(browser, page)
  try {
    const owner = await context.newPage()
    await signIn(owner, 'owner', account('planrevoked'))
    const review = await read(owner, `/api/sessions/${id}/booking-review`)
    const replacement = review.trainers.find(row => row.id !== review.session.trainerId)
    expect(replacement).toBeTruthy()
    await owner.goto(`/#/sessions/${id}`)
    const overview = owner.locator('.session-overview-panel')
    await overview.getByRole('button', { name: 'Edit', exact: true }).click()
    await owner.getByLabel('Session start time', { exact: true }).fill('16:00')
    await owner.getByLabel('Session end time', { exact: true }).fill('17:00')
    await owner.getByRole('combobox', { name: 'Session trainer', exact: true }).click()
    await owner.getByRole('listbox', { name: 'Session trainer', exact: true }).getByRole('option', { name: replacement.name, exact: true }).click()
    await overview.getByRole('button', { name: 'Save', exact: true }).click()
    await owner.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
    await expect(overview).toContainText('16:00–17:00')
    await expect(overview).toContainText(replacement.name)
    expect((await read(owner, `/api/sessions/${id}/details`)).session.trainerId).toBe(replacement.id)
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(page.getByLabel('Exercise 1 weight', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Start Plan', exact: true })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
    expect((await page.request.get(`/api/sessions/${id}/plan-review`)).status()).toBe(404)
    expect((await read(owner, `/api/sessions/${id}/details`)).exercisePlan).toEqual([])
  } finally { await context.close() }
})
