import { fetchRoute, test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function openPackage(page, info, purpose) {
  await signIn(page, 'owner', account(purpose))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(row => row.name === `${info.project.name} ${purpose}`)
  expect(client).toBeDefined()
  await page.goto(`/#/clients/${client.id}`)
  const menu = page.locator('details.profile-menu')
  await expect(menu).toBeVisible()
  if (await menu.locator('summary').isVisible() && await menu.getAttribute('open') === null) await menu.locator('summary').click()
  await menu.getByRole('button', { name: 'Package', exact: true }).click()
  return client
}

test('package deactivation, deletion and Messages Undo persist after fresh login', async ({ page, browser }, info) => {
  const client = await openPackage(page, info, 'packagedelete')
  const original = (await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id)
  expect(original).toHaveLength(2)
  await page.getByRole('button', { name: 'Deactivate Package', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate Package', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Delete Upcoming Sessions', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Delete Upcoming Sessions', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete Sessions', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.reload()
  expect((await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id)).toEqual([])
  const messages = await read(page, '/api/messages')
  const notice = messages.find(row => row.clientId === client.id && row.undo?.kind === 'package_deletion')
  expect(notice.undo.count).toBe(2)
  await page.goto('/#/messages')
  await page.getByRole('button', { name: `Undo ${notice.title}`, exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Undo Change', exact: true }).click()
  await expect(page.getByText('Undone', { exact: true })).toBeVisible()
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, 'owner', account('packagedelete'))
    const restored = (await read(fresh, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id)
    expect(restored.map(row => row.id).sort()).toEqual(original.map(row => row.id).sort())
    const saved = (await read(fresh, '/api/directory')).clients.find(row => row.id === client.id)
    expect(saved.purchases[0].status).toBe('inactive')
    expect(saved.purchases[0].used).toBe(client.purchases[0].used)
  } finally { await context.close() }
})

test('lost package deactivation response recovers the original write without resubmission', async ({ page }, info) => {
  const client = await openPackage(page, info, 'packageloss')
  let writes = 0
  await page.route('**/api/clients/*/purchases/*/actions', async route => {
    writes++
    const response = await fetchRoute(route)
    expect(response.status()).toBe(200)
    await route.abort('failed')
  })
  await page.getByRole('button', { name: 'Deactivate Package', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Deactivate Package', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Check Original Request', exact: true })).toBeVisible()
  await expect(dialog.getByRole('checkbox')).toBeDisabled()
  await dialog.getByRole('button', { name: 'Check Original Request', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes).toBe(1)
  await page.reload()
  expect((await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id)).toEqual([])
  expect((await read(page, '/api/directory')).clients.find(row => row.id === client.id).purchases[0].status).toBe('inactive')
})

test('stale package confirmation cannot delete bookings and Trainer cannot invoke the action', async ({ page, browser }, info) => {
  const client = await openPackage(page, info, 'packagestale')
  const directory = await read(page, '/api/directory')
  const foreign = directory.clients.find(row => row.id !== client.id && row.purchases.length)
  expect(foreign).toBeDefined()
  const before = (await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === foreign.id)
  const path = `/api/clients/${client.id}/purchases/${client.purchases[0].id}`
  await page.getByRole('button', { name: 'Deactivate Package', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('checkbox').check()
  const review = await read(page, `${path}/action-review?operation=deactivate`)
  expect((await post(page, `${path}/actions`, { operation: 'deactivate', expected: review.expected, deleteUpcomingSessions: false })).status()).toBe(200)
  await dialog.getByRole('button', { name: 'Deactivate Package', exact: true }).click()
  await expect(dialog.getByRole('alert')).toBeVisible()
  expect((await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === client.id)).toHaveLength(2)
  expect((await read(page, '/api/session-calendar')).sessions.filter(row => row.clientId === foreign.id)).toEqual(before)
  expect((await page.request.get(`/api/clients/${foreign.id}/purchases/${client.purchases[0].id}/action-review?operation=deactivate`)).status()).toBe(404)
  const context = await freshContext(browser, page)
  try {
    const trainer = await context.newPage()
    await signIn(trainer, 'trainer', `${info.project.name}-packagestale@example.test`)
    expect((await trainer.request.get(`${path}/action-review?operation=deactivate`)).status()).toBe(403)
    expect((await post(trainer, `${path}/actions`, { operation: 'deactivate', expected: review.expected, deleteUpcomingSessions: true })).status()).toBe(403)
  } finally { await context.close() }
})
