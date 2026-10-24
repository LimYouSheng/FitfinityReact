import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function prepare(page, info, purpose) {
  await signIn(page, 'trainer', `${info.project.name}-${purpose}@example.test`)
  const sessions = (await read(page, '/api/session-calendar')).sessions.sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(sessions).toHaveLength(2)
  const [source, target] = sessions
  const review = await read(page, `/api/sessions/${source.id}/plan-review`)
  const response = await post(page, `/api/sessions/${source.id}/plan`, { expected: review.expected, items: [{ id: 'draft-source', name: 'Reviewed squat', weight: '12 kg', reps: '8', rounds: '3', rest: '60s', customDetails: [{ id: 'tempo', value: 'Slow descent' }] }] })
  expect(response.ok()).toBe(true)
  const saved = await response.json()
  await page.goto(`/#/sessions/${target.id}`)
  await page.getByRole('button', { name: 'Previous Plan', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Previous exercise plan', exact: true })
  await expect(dialog.getByText('Slow descent', { exact: true })).toBeVisible()
  expect((await read(page, `/api/sessions/${target.id}/details`)).exercisePlan).toEqual([])
  return { source, target, saved, dialog }
}

test('preview requires confirmation and copied prescriptions persist through a fresh login', async ({ page, browser }, info) => {
  const { source, target, saved, dialog } = await prepare(page, info, 'plancopy')
  await dialog.getByRole('button', { name: 'Replace Plan', exact: true }).click()
  await expect(page.getByText('Previous exercise plan copied.', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Exercise plan', { exact: true }).getByText('Slow descent', { exact: true })).toBeVisible()
  const context = await freshContext(browser, page), next = await context.newPage()
  await signIn(next, 'trainer', `${info.project.name}-plancopy@example.test`)
  const copied = (await read(next, `/api/sessions/${target.id}/details`)).exercisePlan
  expect(copied).toHaveLength(1)
  expect(copied[0]).toMatchObject({ name: 'Reviewed squat', customDetails: [{ id: 'tempo', value: 'Slow descent' }], videoAttached: false })
  expect(copied[0].id).not.toBe(saved.items[0].id)
  expect((await read(next, `/api/sessions/${source.id}/details`)).exercisePlan).toEqual(saved.items)
  await context.close()
})

test('a changed source cannot replace the previewed target and foreign plans are denied', async ({ page, browser }, info) => {
  const { source, target, dialog } = await prepare(page, info, 'plancopystale')
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('plancopystale'))
  const reviewed = await read(staff, `/api/sessions/${source.id}/plan-review`)
  const changed = await post(staff, `/api/sessions/${source.id}/plan`, { expected: reviewed.expected, items: [{ id: 'draft-changed', name: 'Newer prescription', weight: '', reps: '6', rounds: '2', rest: '30s', customDetails: [] }] })
  expect(changed.ok()).toBe(true)
  await dialog.getByRole('button', { name: 'Replace Plan', exact: true }).click()
  await expect(dialog.getByRole('alert')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Replace Plan', exact: true })).toBeDisabled()
  expect((await read(staff, `/api/sessions/${target.id}/details`)).exercisePlan).toEqual([])
  const foreign = (await read(staff, '/api/session-calendar')).sessions.find(s => s.clientId !== target.clientId)
  expect(foreign).toBeTruthy()
  expect((await page.request.get(`/api/sessions/${foreign.id}/previous-plan`)).status()).toBe(404)
  expect((await post(page, `/api/sessions/${foreign.id}/copy-plan`, { expected: reviewed.expected, sourceId: source.id, sourceExpected: reviewed.expected })).status()).toBe(404)
  await context.close()
})

test('lost committed copy retains the source intent through focus refresh and performs one write', async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window)
    window.copyWrites = 0
    window.fetch = async (url, options) => {
      const response = await fetch(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/copy-plan$/.test(String(url))) {
        window.copyWrites++
        window.copyKey = options.headers['Idempotency-Key']
        if (window.copyWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed copy') }
      }
      return response
    }
  })
  const { source, target, dialog } = await prepare(page, info, 'plancopyloss')
  await dialog.getByRole('button', { name: 'Replace Plan', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Check original copy', exact: true })).toBeEnabled()
  await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check original save', exact: true }).click()
  await expect(page.getByText('Original exercise plan confirmed.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.copyWrites)).toBe(1)
  const key = await page.evaluate(() => window.copyKey)
  expect(await read(page, `/api/session-plans/${key}`)).toMatchObject({ sessionId: target.id, copiedFromSessionId: source.id })
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('plancopyloss'))
  expect((await staff.request.get(`/api/session-plans/${key}`)).status()).toBe(404)
  expect((await read(staff, `/api/sessions/${target.id}/details`)).exercisePlan).toHaveLength(1)
  await context.close()
})
