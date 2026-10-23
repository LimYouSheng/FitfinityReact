import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'trainer') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(c => c.name === `${info.project.name} ${purpose}`)
  expect(client).toBeTruthy()
  const all = (await read(page, '/api/session-calendar')).sessions
  const sessions = all.filter(s => s.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(sessions).toHaveLength(2)
  if (role === 'trainer') expect(all).toHaveLength(2)
  else expect(all.some(s => s.clientId !== client.id)).toBe(true)
  await page.goto(`/#/sessions/${sessions[0].id}`)
  await expect(page.getByRole('button', { name: 'Start Plan', exact: true })).toBeEnabled()
  return { client, sessions }
}
async function draft(page, name = 'Stored custom squat') {
  await page.getByRole('button', { name: 'Start Plan', exact: true }).click()
  await page.getByRole('combobox', { name: 'Exercise 1 name', exact: true }).click()
  await page.getByRole('button', { name: 'Custom Exercise', exact: true }).click()
  await page.getByLabel('Exercise 1 custom name', { exact: true }).fill(name)
  await page.getByRole('button', { name: 'Use Custom Exercise', exact: true }).click()
  for (const [field, value] of [['weight', '16 kg'], ['reps', '8'], ['rounds', '3'], ['rest', '60s']]) await page.getByLabel(`Exercise 1 ${field}`, { exact: true }).fill(value)
  for (const [index, text] of ['Slow descent', 'Keep heels down'].entries()) {
    await page.getByRole('button', { name: 'Add details for exercise 1', exact: true }).click()
    await page.getByLabel(`Exercise 1 details ${index + 1}`, { exact: true }).fill(text)
  }
}
async function submit(page) {
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog', { name: 'Save exercise plan?', exact: true }).getByRole('button', { name: 'Save Plan', exact: true }).click()
}
for (const [purpose, role] of [['plan', 'trainer'], ['planadmin', 'admin']]) {
  test(`${role} UI plan persists ordered details across reload and fresh login without enabling media`, async ({ page, browser }, info) => {
    const before = await open(page, info, purpose, role)
    await draft(page)
    await submit(page)
    await expect(page.getByText('Exercise plan saved.', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByLabel('Exercise plan', { exact: true }).getByText('Keep heels down', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Manage video for Stored custom squat', exact: true })).toHaveCount(0)
    const fresh = await freshContext(browser, page), next = await fresh.newPage()
    await signIn(next, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
    const detail = await read(next, `/api/sessions/${before.sessions[0].id}/details`)
    expect(detail.exercisePlan).toHaveLength(1)
    expect(detail.exercisePlan[0]).toMatchObject({ name: 'Stored custom squat', weight: '16 kg', reps: '8', rounds: '3', rest: '60s', videoAttached: false })
    expect(detail.exercisePlan[0].customDetails.map(d => d.value)).toEqual(['Slow descent', 'Keep heels down'])
    expect(detail.purchase.used).toBe(0)
    await next.goto(`/#/sessions/${before.sessions[0].id}`)
    await next.getByRole('button', { name: 'Edit exercise plan', exact: true }).click()
    await next.getByLabel('Exercise 1 weight', { exact: true }).fill('20 kg')
    await submit(next)
    await expect(next.getByText('Exercise plan saved.', { exact: true })).toBeVisible()
    const edited = await read(next, `/api/sessions/${before.sessions[0].id}/details`)
    expect(edited.exercisePlan[0]).toMatchObject({ id: detail.exercisePlan[0].id, weight: '20 kg' })
    expect(edited.exercisePlan[0].customDetails).toEqual(detail.exercisePlan[0].customDetails)
    await fresh.close()
  })
}

test('stale plan UI cannot overwrite a competing Owner save and foreign records stay inaccessible', async ({ page, browser }, info) => {
  const before = await open(page, info, 'planstale')
  await draft(page, 'Trainer draft')
  const owner = await freshContext(browser, page), staff = await owner.newPage()
  await signIn(staff, 'owner', account('planstale'))
  const id = before.sessions[0].id, reviewed = await read(staff, `/api/sessions/${id}/plan-review`)
  const items = [{ id: 'draft-owner', name: 'Owner plan', weight: '5 kg', reps: '10', rounds: '2', rest: '30s', customDetails: [] }]
  const saved = await post(staff, `/api/sessions/${id}/plan`, { expected: reviewed.expected, items })
  expect(saved.ok()).toBe(true)
  await submit(page)
  await expect(page.getByRole('alert').filter({ hasText: /changed|reload/i })).toBeVisible()
  expect((await read(staff, `/api/sessions/${id}/details`)).exercisePlan.map(p => p.name)).toEqual(['Owner plan'])
  const all = (await read(staff, '/api/session-calendar')).sessions
  const foreign = all.find(s => s.clientId !== before.client.id)
  expect(foreign).toBeTruthy()
  expect((await page.request.get(`/api/sessions/${foreign.id}/plan-review`)).status()).toBe(404)
  expect((await post(page, `/api/sessions/${foreign.id}/plan`, { expected: reviewed.expected, items })).status()).toBe(404)
  await owner.close()
})

test('committed lost plan response freezes fields and focus refresh recovers the original receipt', async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window)
    window.planWrites = 0
    window.fetch = async (url, options) => {
      const response = await fetch(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/plan$/.test(String(url))) {
        window.planWrites++
        window.planKey = options.headers['Idempotency-Key']
        if (window.planWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed plan response') }
      }
      return response
    }
  })
  const before = await open(page, info, 'planloss')
  await draft(page)
  await submit(page)
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByLabel('Exercise 1 weight', { exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Add Exercise', exact: true })).toBeDisabled()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Exercise plan', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Check original save', exact: true }).click()
  await expect(page.getByText('Original exercise plan confirmed.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.planWrites)).toBe(1)
  const key = await page.evaluate(() => window.planKey)
  expect((await read(page, `/api/session-plans/${key}`)).sessionId).toBe(before.sessions[0].id)
  const owner = await freshContext(browser, page), staff = await owner.newPage()
  await signIn(staff, 'owner', account('planloss'))
  expect((await staff.request.get(`/api/session-plans/${key}`)).status()).toBe(404)
  expect((await read(staff, `/api/sessions/${before.sessions[0].id}/details`)).exercisePlan).toHaveLength(1)
  await owner.close()
})
