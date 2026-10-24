import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'trainer') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(c => c.name === `${info.project.name} ${purpose}`)
  expect(client).toBeTruthy()
  const all = (await read(page, '/api/session-calendar')).sessions
  if (role === 'trainer') expect(all).toHaveLength(2)
  else expect(all.some(s => s.clientId !== client.id)).toBe(true)
  const session = all.find(s => s.clientId === client.id && s.sessionNumber === 1)
  expect(session.status).toBe('completed')
  const before = await read(page, `/api/sessions/${session.id}/details`)
  await page.goto(`/#/sessions/${session.id}`)
  const panel = page.locator('.client-summary-panel')
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(panel.getByLabel('Client-facing summary', { exact: true })).toBeVisible()
  await panel.getByLabel('Client-facing summary', { exact: true }).fill('Client summary reviewed after training.')
  return { client, session, before, panel }
}

async function submit(page, panel) {
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog', { name: 'Save client-facing summary?', exact: true }).getByRole('button', { name: 'Save Summary', exact: true }).click()
}

function unchanged(after, before) {
  expect(after.session.status).toBe(before.session.status)
  for (const field of ['acknowledgementHistory', 'purchase', 'exerciseResults', 'trainerComments', 'whatsappOpenedAt', 'whatsappOpenCount']) expect(after[field]).toEqual(before[field])
}

for (const [purpose, role] of [['summary', 'trainer'], ['summaryadmin', 'admin']]) {
  test(`${role} summary UI persists through reload and fresh login without rewriting completion or delivery`, async ({ page, browser }, info) => {
    const { session, before, panel } = await open(page, info, purpose, role)
    await submit(page, panel)
    await expect(page.getByText('Client-facing summary saved.', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('Client summary reviewed after training.', { exact: true })).toBeVisible()
    const context = await freshContext(browser, page), next = await context.newPage()
    await signIn(next, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
    const after = await read(next, `/api/sessions/${session.id}/details`)
    expect(after.clientSummary).toBe('Client summary reviewed after training.')
    unchanged(after, before)
    await next.goto(`/#/sessions/${session.id}`)
    await expect(next.getByText('Client summary reviewed after training.', { exact: true })).toBeVisible()
    await context.close()
  })
}

test('stale summary cannot replace a competing Owner save and foreign sessions stay denied', async ({ page, browser }, info) => {
  const { client, session, panel } = await open(page, info, 'summarystale')
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('summarystale'))
  const review = await read(staff, `/api/sessions/${session.id}/summary-review`)
  expect((await post(staff, `/api/sessions/${session.id}/summary`, { expected: review.expected, summary: 'Owner reviewed summary' })).ok()).toBe(true)
  await submit(page, panel)
  await expect(page.getByRole('alert').filter({ hasText: /changed|reload/i })).toBeVisible()
  expect((await read(staff, `/api/sessions/${session.id}/details`)).clientSummary).toBe('Owner reviewed summary')
  const foreign = (await read(staff, '/api/session-calendar')).sessions.find(s => s.clientId !== client.id)
  expect(foreign).toBeTruthy()
  expect((await page.request.get(`/api/sessions/${foreign.id}/summary-review`)).status()).toBe(404)
  expect((await post(page, `/api/sessions/${foreign.id}/summary`, { expected: review.expected, summary: 'Forged' })).status()).toBe(404)
  await context.close()
})

test('lost committed summary freezes text and recovers the original private receipt once', async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window)
    window.summaryWrites = 0
    window.fetch = async (url, options) => {
      const response = await fetch(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/summary$/.test(String(url))) {
        window.summaryWrites++
        window.summaryKey = options.headers['Idempotency-Key']
        if (window.summaryWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed summary') }
      }
      return response
    }
  })
  const { session, before, panel } = await open(page, info, 'summaryloss')
  await submit(page, panel)
  await expect(panel.getByLabel('Client-facing summary', { exact: true })).toBeDisabled()
  await expect(panel.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check original summary', exact: true }).click()
  await expect(page.getByText('Original client summary confirmed.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.summaryWrites)).toBe(1)
  const key = await page.evaluate(() => window.summaryKey)
  expect((await read(page, `/api/session-summaries/${key}`)).summary).toBe('Client summary reviewed after training.')
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('summaryloss'))
  expect((await staff.request.get(`/api/session-summaries/${key}`)).status()).toBe(404)
  const after = await read(staff, `/api/sessions/${session.id}/details`)
  expect(after.clientSummary).toBe('Client summary reviewed after training.')
  unchanged(after, before)
  await context.close()
})
