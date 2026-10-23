import { randomUUID } from 'node:crypto'
import { test, expect, signIn, read, confirm, post, account, freshContext } from './fixtures.js'

for (const role of ['owner', 'admin']) test(`${role} package edits persist through a fresh login without changing purchased terms`, async ({ page, browser }) => {
  await signIn(page, role, account('catalogue', role))
  const before = await read(page, '/api/directory')
  const name = `Browser ${randomUUID()}`
  await page.goto('/#/packages/new')
  await page.getByLabel('Package name', { exact: true }).fill(name)
  await page.getByLabel('Package session count', { exact: true }).fill('18')
  await confirm(page, 'Create Package')
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  await expect(page.getByText('135 days', { exact: true })).toBeVisible()
  const created = (await read(page, '/api/directory')).packages.find(p => p.name === name)
  expect(created).toMatchObject({ total_sessions: 18, validity_days: 135, status: 'active', version: 1 })
  await page.getByRole('button', { name: 'Edit Package', exact: true }).click()
  await page.getByLabel('Package session count', { exact: true }).fill('13')
  await confirm(page, 'Save Package')
  await expect(page.getByText('98 days', { exact: true })).toBeVisible()
  await confirm(page, 'Deactivate Package')
  await expect(page.getByRole('button', { name: 'Reactivate Package', exact: true })).toBeVisible()
  const fresh = await freshContext(browser, page)
  try {
    const second = await fresh.newPage()
    await signIn(second, role, account('catalogue', role))
    await second.goto(`/#/packages/${created.id}`)
    await expect(second.getByRole('heading', { name, exact: true })).toBeVisible()
    await expect(second.getByText('98 days', { exact: true })).toBeVisible()
    await expect(second.getByRole('button', { name: 'Reactivate Package', exact: true })).toBeVisible()
    const after = await read(second, '/api/directory')
    expect(after.packages.find(p => p.id === created.id)).toMatchObject({ total_sessions: 13, validity_days: 98, status: 'inactive', version: 3 })
    expect(after.clients.filter(c => ['Browser Client', 'Other Client'].includes(c.name))).toEqual(before.clients.filter(c => ['Browser Client', 'Other Client'].includes(c.name)))
    if (role === 'admin') for (const trainer of after.trainers) {
      expect(trainer).not.toHaveProperty('peak_rate_cents')
      expect(trainer).not.toHaveProperty('off_peak_rate_cents')
    }
  } finally { await fresh.close() }
})

test('server rejects stale and conflicting retry writes without changing the committed package', async ({ page }) => {
  await signIn(page, 'owner', account('retry'))
  const key = randomUUID(), draft = { name: `Retry ${randomUUID()}`, total: 12, status: 'active' }
  const first = await post(page, '/api/packages', { draft }, key)
  expect(first.status()).toBe(200)
  const saved = await first.json()
  const retry = await post(page, '/api/packages', { draft }, key)
  expect(retry.status()).toBe(200); expect(await retry.json()).toEqual(saved)
  const changed = await post(page, '/api/packages', { draft: { ...draft, total: 24 } }, key)
  expect(changed.status()).toBe(409)
  const edit = await post(page, '/api/packages', { id: saved.id, expectedVersion: saved.version, draft: { ...draft, total: 18 } })
  expect(edit.status()).toBe(200)
  const stale = await post(page, '/api/packages', { id: saved.id, expectedVersion: saved.version, draft })
  expect(stale.status()).toBe(409)
  await page.goto(`/#/packages/${saved.id}`)
  // These commands came from another API client; reload the browser's directory snapshot.
  await page.reload()
  await expect(page.getByText('135 days', { exact: true })).toBeVisible()
  expect((await read(page, '/api/directory')).packages.filter(p => p.name === draft.name)).toEqual([await edit.json()])
})

test('Trainer reads persisted assigned sessions but cannot mutate packages or access initial assessments', async ({ page, browser }) => {
  await signIn(page, 'trainer')
  const directory = await read(page, '/api/directory')
  expect(directory.packages).toEqual([])
  expect(directory.clients.map(c => c.name)).toEqual(['Browser Client'])
  // Include a real foreign record: an empty/single-client fixture cannot prove scoping.
  const observer = await freshContext(browser, page)
  let foreign
  try {
    const admin = await observer.newPage()
    await signIn(admin, 'admin')
    const all = await read(admin, '/api/session-calendar')
    const otherClient = all.clients.find(c => c.name === 'Other Client')
    expect(otherClient).toBeDefined()
    foreign = all.sessions.find(s => s.clientId === otherClient.id)
    expect(foreign).toBeDefined()
  } finally { await observer.close() }
  expect((await page.request.get(`/api/sessions/${foreign.id}/details`)).status()).toBe(404)
  const calendar = await read(page, '/api/session-calendar')
  expect(calendar.sessions.length).toBeGreaterThan(0)
  expect(calendar.sessions.every(s => s.readAccess === 'assigned' && s.trainerId === directory.trainers[0].id)).toBe(true)
  const session = calendar.sessions[0]
  await page.goto(`/#/sessions/${session.id}`)
  await expect(page.locator('main')).toContainText('Browser Client')
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  await page.reload()
  await expect(page.locator('main')).toContainText('Browser Client')
  const denied = await post(page, '/api/packages', { draft: { name: `Denied ${randomUUID()}`, total: 12, status: 'active' } })
  expect(denied.status()).toBe(403)
  const person = directory.clients[0].people[0]
  const assessment = await page.request.get(`/api/people/${person.id}/assessments`)
  expect(assessment.status()).toBe(403)
  expect((await read(page, '/api/session-calendar')).sessions).toEqual(calendar.sessions)
})
