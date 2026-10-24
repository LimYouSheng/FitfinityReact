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
  const panel = page.locator('.session-outcome-panel')
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(panel.getByLabel('Load (kg) for Measured squat', { exact: true })).toHaveValue('12')
  return { client, session, before, panel }
}
async function draft(panel, weight = '25') {
  await panel.getByLabel('Trainer comments', { exact: true }).fill('Measured safely and reviewed')
  await panel.getByLabel('Load (kg) for Measured squat', { exact: true }).fill(weight)
  await panel.getByLabel('Reps for Measured squat', { exact: true }).fill('10')
  await panel.getByLabel('Sets for Measured squat', { exact: true }).fill('4')
}
async function submit(page, panel) {
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog', { name: 'Save session outcome?', exact: true }).getByRole('button', { name: 'Save Outcome', exact: true }).click()
}
for (const [purpose, role] of [['outcome', 'trainer'], ['outcomeadmin', 'admin']]) {
  test(`${role} outcome UI saves real measurements and fresh-login client progress without changing signed credit evidence`, async ({ page, browser }, info) => {
    const { client, session, before, panel } = await open(page, info, purpose, role)
    await draft(panel)
    await submit(page, panel)
    await expect(page.getByText('Session outcome saved.', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('Measured safely and reviewed', { exact: true })).toBeVisible()
    const context = await freshContext(browser, page), next = await context.newPage()
    await signIn(next, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
    const after = await read(next, `/api/sessions/${session.id}/details`)
    expect(after.exerciseResults).toHaveLength(1)
    expect(after.exerciseResults[0]).toMatchObject({ loadKg: 25, reps: 10, sets: 4 })
    expect(after.acknowledgementHistory).toEqual(before.acknowledgementHistory)
    expect(after.purchase.used).toBe(before.purchase.used)
    await next.goto(`/#/clients/${client.id}/progress/${session.purchaseId}`)
    const chart = next.getByRole('button', { name: 'Show Measured squat progress chart', exact: true })
    await expect(chart).toBeVisible()
    await expect(chart).toHaveText(/25 kg/)
    await expect(next.getByRole('button', { name: 'Download Progress Report PDF', exact: true })).toHaveCount(0)
    await expect(next.getByRole('button', { name: 'View Export/WhatsApp History', exact: true })).toHaveCount(0)
    await context.close()
  })
}

test('stale measured outcome cannot overwrite a competing save and foreign session/profile scope stays denied', async ({ page, browser }, info) => {
  const { client, session, panel } = await open(page, info, 'outcomestale')
  await draft(panel)
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('outcomestale'))
  const review = await read(staff, `/api/sessions/${session.id}/outcome-review`)
  const response = await post(staff, `/api/sessions/${session.id}/outcome`, { expected: review.expected, trainerComments: 'Owner measured', measurements: [{ id: review.rows[0].id, loadKg: 40, reps: 6, sets: 2 }] })
  expect(response.ok()).toBe(true)
  await submit(page, panel)
  await expect(page.getByRole('alert').filter({ hasText: /changed|reload/i })).toBeVisible()
  expect((await read(staff, `/api/sessions/${session.id}/details`)).exerciseResults[0].loadKg).toBe(40)
  const foreign = (await read(staff, '/api/session-calendar')).sessions.find(s => s.clientId !== client.id)
  expect(foreign).toBeTruthy()
  expect((await page.request.get(`/api/sessions/${foreign.id}/outcome-review`)).status()).toBe(404)
  expect((await post(page, `/api/sessions/${foreign.id}/outcome`, { expected: review.expected, trainerComments: 'Forged', measurements: [] })).status()).toBe(404)
  expect((await page.request.get(`/api/clients/${foreign.clientId}/progress`)).status()).toBe(404)
  await context.close()
})

test('lost committed outcome freezes measured fields and focus refresh recovers one original write', async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window)
    window.outcomeWrites = 0
    window.fetch = async (url, options) => {
      const response = await fetch(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/outcome$/.test(String(url))) {
        window.outcomeWrites++
        window.outcomeKey = options.headers['Idempotency-Key']
        if (window.outcomeWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed outcome') }
      }
      return response
    }
  })
  const { session, before, panel } = await open(page, info, 'outcomeloss')
  await draft(panel)
  await submit(page, panel)
  await expect(panel.getByLabel('Load (kg) for Measured squat', { exact: true })).toBeDisabled()
  await expect(panel.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check original outcome', exact: true }).click()
  await expect(page.getByText('Original session outcome confirmed.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.outcomeWrites)).toBe(1)
  const key = await page.evaluate(() => window.outcomeKey)
  expect((await read(page, `/api/session-outcomes/${key}`)).sessionId).toBe(session.id)
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('outcomeloss'))
  expect((await staff.request.get(`/api/session-outcomes/${key}`)).status()).toBe(404)
  const after = await read(staff, `/api/sessions/${session.id}/details`)
  expect(after.exerciseResults[0].loadKg).toBe(25)
  expect(after.purchase.used).toBe(before.purchase.used)
  expect(after.acknowledgementHistory).toEqual(before.acknowledgementHistory)
  await context.close()
})
