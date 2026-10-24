import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function saveSummary(page, info, purpose) {
  await signIn(page, 'trainer', `${info.project.name}-${purpose}@example.test`)
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(row => row.name === `${info.project.name} ${purpose}`)
  expect(client).toBeTruthy()
  const sessions = (await read(page, '/api/session-calendar')).sessions
  expect(sessions).toHaveLength(2)
  const session = sessions.find(row => row.clientId === client.id && row.sessionNumber === 1)
  const before = await read(page, `/api/sessions/${session.id}/details`)
  await page.goto(`/#/sessions/${session.id}`)
  const panel = page.locator('.client-summary-panel')
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await panel.getByLabel('Client-facing summary', { exact: true }).fill('Summary to reverse after review.')
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog', { name: 'Save client-facing summary?', exact: true }).getByRole('button', { name: 'Save Summary', exact: true }).click()
  await expect(page.getByText('Client-facing summary saved.', { exact: true })).toBeVisible()
  const notice = (await read(page, '/api/messages')).find(row => row.clientId === client.id && row.undo?.kind === 'session_change')
  expect(notice).toBeTruthy()
  await page.goto('/#/messages')
  await expect(page.getByRole('button', { name: `Undo ${notice.title}`, exact: true })).toBeVisible()
  return { session, client, before, notice }
}

function noticeCard(page, notice) {
  return page.getByRole('article').filter({ has: page.locator(`time[datetime="${notice.createdAt}"]`) }).filter({ has: page.getByRole('button', { name: `Open ${notice.title}`, exact: true }) })
}

async function confirmUndo(page, notice) {
  await noticeCard(page, notice).getByRole('button', { name: `Undo ${notice.title}`, exact: true }).click()
  await page.getByRole('dialog', { name: 'Undo session change?', exact: true }).getByRole('button', { name: 'Undo Change', exact: true }).click()
}

function retained(after, before) {
  expect(after.clientSummary).toBe(before.clientSummary)
  for (const key of ['acknowledgementHistory', 'purchase', 'exerciseResults', 'trainerComments', 'whatsappOpenedAt', 'whatsappOpenCount']) expect(after[key]).toEqual(before[key])
  expect(after.session.status).toBe(before.session.status)
}

test('Trainer UI Undo persists after fresh login while keeping completion and credit evidence', async ({ page, browser }, info) => {
  const { session, before, notice } = await saveSummary(page, info, 'summaryundo')
  await confirmUndo(page, notice)
  await expect(page.getByText('Undone', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Undone', { exact: true })).toBeVisible()
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, 'trainer', `${info.project.name}-summaryundo@example.test`)
    retained(await read(fresh, `/api/sessions/${session.id}/details`), before)
    expect((await read(fresh, '/api/messages')).find(row => row.id === notice.id).undo.status).toBe('undone')
  } finally { await context.close() }
})

test('lost committed Undo reconciles the private original receipt without a second write', async ({ page, browser }, info) => {
  const { session, before, notice } = await saveSummary(page, info, 'summaryundoloss')
  let writes = 0, key
  await page.route('**/api/session-changes/*/undo', async route => {
    writes++; key = route.request().headers()['idempotency-key']
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    await route.abort('failed')
  })
  await confirmUndo(page, notice)
  await expect(page.getByLabel('Message list').getByRole('alert')).toBeVisible()
  await confirmUndo(page, notice)
  await expect(page.getByText('Undone', { exact: true })).toBeVisible()
  expect(writes).toBe(1)
  retained(await read(page, `/api/sessions/${session.id}/details`), before)
  expect((await read(page, `/api/session-undos/${key}`)).actionId).toBe(notice.undo.id)
  const context = await freshContext(browser, page)
  try {
    const owner = await context.newPage()
    await signIn(owner, 'owner', account('summaryundoloss'))
    expect((await owner.request.get(`/api/session-undos/${key}`)).status()).toBe(404)
  } finally { await context.close() }
})

test('later writes and foreign changes cannot be overwritten through stale Undo controls', async ({ page, browser }, info) => {
  const { session, client, notice } = await saveSummary(page, info, 'summaryundostale')
  const viewed = await read(page, `/api/session-changes/${notice.undo.id}/undo-review`)
  const context = await freshContext(browser, page)
  try {
    const owner = await context.newPage()
    await signIn(owner, 'owner', account('summaryundostale'))
    const review = await read(owner, `/api/sessions/${session.id}/summary-review`)
    expect((await post(owner, `/api/sessions/${session.id}/summary`, { expected: review.expected, summary: 'Later Owner correction' })).status()).toBe(200)
    await confirmUndo(page, notice)
    await expect(page.getByLabel('Message list').getByRole('alert').filter({ hasText: /changed|review/i })).toBeVisible()
    expect((await post(page, `/api/session-changes/${notice.undo.id}/undo`, { expected: viewed.expected })).status()).toBe(409)
    expect((await read(owner, `/api/sessions/${session.id}/details`)).clientSummary).toBe('Later Owner correction')
    const foreign = (await read(owner, '/api/directory')).clients.find(row => row.name === `${info.project.name} summaryundoforeign`)
    expect(foreign.id).not.toBe(client.id)
    const foreignSession = (await read(owner, '/api/session-calendar')).sessions.find(row => row.clientId === foreign.id && row.sessionNumber === 1)
    const foreignReview = await read(owner, `/api/sessions/${foreignSession.id}/summary-review`)
    expect((await post(owner, `/api/sessions/${foreignSession.id}/summary`, { expected: foreignReview.expected, summary: 'Foreign summary retained' })).status()).toBe(200)
    const foreignNotice = (await read(owner, '/api/messages')).find(row => row.clientId === foreign.id && row.undo?.kind === 'session_change')
    expect((await page.request.get(`/api/session-changes/${foreignNotice.undo.id}/undo-review`)).status()).toBe(404)
    expect((await post(page, `/api/session-changes/${foreignNotice.undo.id}/undo`, { expected: viewed.expected })).status()).toBe(404)
    expect((await read(owner, `/api/sessions/${foreignSession.id}/details`)).clientSummary).toBe('Foreign summary retained')
  } finally { await context.close() }
})

async function openCohort(page, info, purpose, role = 'trainer') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose))
  const client = (await read(page, '/api/directory')).clients.find(row => row.name === `${info.project.name} ${purpose}`)
  const sessions = (await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(sessions).toHaveLength(2)
  await page.goto(`/#/sessions/${sessions[0].id}`)
  return { client, sessions }
}
async function undoLatest(page, client) {
  const notices = (await read(page, '/api/messages')).filter(row => row.clientId === client.id && row.undo?.kind === 'session_change')
  expect(notices.length).toBeGreaterThan(0)
  await page.goto('/#/messages')
  await confirmUndo(page, notices[0])
  await expect(noticeCard(page, notices[0]).getByRole('status')).toHaveText('Undone')
  await page.reload()
  expect((await read(page, '/api/messages')).find(row => row.id === notices[0].id).undo.status).toBe('undone')
}

test('plan UI Undo retires the saved plan and restores the empty plan after reload', async ({ page }, info) => {
  const { client, sessions } = await openCohort(page, info, 'planundo')
  await page.getByRole('button', { name: 'Start Plan', exact: true }).click()
  await page.getByRole('combobox', { name: 'Exercise 1 name', exact: true }).click()
  await page.getByRole('button', { name: 'Custom Exercise', exact: true }).click()
  await page.getByLabel('Exercise 1 custom name', { exact: true }).fill('Undo custom squat')
  await page.getByRole('button', { name: 'Use Custom Exercise', exact: true }).click()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog', { name: 'Save exercise plan?', exact: true }).getByRole('button', { name: 'Save Plan', exact: true }).click()
  await expect(page.getByText('Exercise plan saved.', { exact: true })).toBeVisible()
  expect((await read(page, `/api/sessions/${sessions[0].id}/details`)).exercisePlan).toHaveLength(1)
  await undoLatest(page, client)
  expect((await read(page, `/api/sessions/${sessions[0].id}/details`)).exercisePlan).toEqual([])
  await page.goto(`/#/sessions/${sessions[0].id}`)
  await expect(page.getByRole('button', { name: 'Start Plan', exact: true })).toBeEnabled()
})

for (const [purpose, role] of [['postponeundo', 'owner'], ['postponeundoproposal', 'trainer']]) {
  test(`${role} postponement Undo preserves bookings and proposal history after reload`, async ({ page }, info) => {
    const { client, sessions } = await openCohort(page, info, purpose, role)
    await page.getByRole('button', { name: 'Postpone', exact: true }).click()
    await page.getByRole('dialog', { name: 'Postpone this session?', exact: true }).getByRole('button', { name: 'Confirm Postponement', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const changed = (await read(page, '/api/session-calendar')).sessions.find(row => row.id === sessions[0].id)
    expect(changed.scheduleState).toBe(role === 'owner' ? 'open' : 'booked')
    await undoLatest(page, client)
    const restored = (await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
    for (const [index, row] of restored.entries()) {
      for (const key of ['id', 'date', 'startsAt', 'endsAt', 'trainerId', 'sessionNumber', 'scheduleState']) expect(row[key]).toEqual(sessions[index][key])
    }
    if (role === 'trainer') {
      const requests = (await read(page, '/api/messages')).filter(row => row.clientId === client.id && row.request)
      expect(requests.some(row => row.request.status === 'cancelled')).toBe(true)
    }
  })
}

test('recording removal Undo restores original media identity and expiry with playable bytes', async ({ page }, info) => {
  const { client, sessions } = await openCohort(page, info, 'videoundo')
  const details = await read(page, `/api/sessions/${sessions[0].id}/details`)
  const item = details.exercisePlan[0], path = `/api/sessions/${sessions[0].id}/exercises/${item.id}/video`
  await page.getByRole('button', { name: 'Manage video for Recorded squat', exact: true }).click()
  await page.getByLabel('Attach video for Recorded squat', { exact: true }).setInputFiles('tests/fixtures/silent-one-second.webm')
  await page.getByRole('dialog').getByRole('button', { name: 'Save Video', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  const original = (await read(page, `${path}/review`)).media
  await page.reload()
  await page.getByRole('button', { name: 'Manage video for Recorded squat', exact: true }).click()
  await page.getByRole('button', { name: 'Remove saved video', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Remove Video', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(await read(page, path)).toBeNull()
  const notices = (await read(page, '/api/messages')).filter(row => row.clientId === client.id && row.undo?.kind === 'session_change')
  expect(notices).toHaveLength(2)
  await page.goto('/#/messages')
  await confirmUndo(page, notices[0])
  await expect(noticeCard(page, notices[0]).getByRole('status')).toHaveText('Undone')
  await page.reload()
  expect((await read(page, `${path}/review`)).media).toMatchObject({ id: original.id, expiresAt: original.expiresAt })
  await page.goto(`/#/sessions/${sessions[0].id}`)
  await page.getByRole('button', { name: 'Manage video for Recorded squat', exact: true }).click()
  await expect(page.locator('video')).toHaveAttribute('src', /^blob:/)
})
