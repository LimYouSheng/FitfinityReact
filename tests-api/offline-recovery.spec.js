import { test, expect, signIn, read, account, freshContext } from './fixtures.js'

/** Real notes workflow, with connectivity loss rather than substituted API responses. */
async function notesPage(page, info, purpose = 'contacts') {
  await signIn(page, 'owner', account(purpose))
  const client = (await read(page, '/api/directory')).clients.find(row => row.name === `${info.project.name} ${purpose}`)
  await page.goto(`/#/clients/${client.id}`)
  const panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Remarks', exact: true }) })
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  return { client, panel }
}

test('offline notes retain the original draft through Retry, persist once and clear the connection warning', async ({ page, context, browser }, info) => {
  const { client, panel } = await notesPage(page, info)
  const value = `Recovered private draft ${info.project.name}`
  await page.getByRole('textbox', { name: 'Remarks', exact: true }).fill(value)
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  await context.setOffline(true)
  await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  // A normal focus refresh reaches the same error path as the periodic identity check.
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Remarks', exact: true })).toHaveCount(0)
  await context.setOffline(false)
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(panel).toContainText('Your unsaved draft is available')
  await expect(page.getByText('Unable to reach the staff service. Check your connection and retry.', { exact: true })).toHaveCount(0)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Remarks', exact: true })).toHaveValue(value)
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  await expect(panel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  const saved = await read(page, `/api/clients/${client.id}/notes`)
  expect(saved.remarks).toBe(value)
  expect(saved.version).toBe(client.version + 1)
  const fresh = await freshContext(browser, page)
  try {
    const next = await fresh.newPage()
    await signIn(next, 'owner', account('contacts'))
    await next.goto(`/#/clients/${client.id}`)
    await expect(next.getByText(value, { exact: true })).toBeVisible()
  } finally { await fresh.close() }
})

test('an outage draft cannot cross a verified account change', async ({ page, context }, info) => {
  const { client, panel } = await notesPage(page, info)
  await page.getByRole('textbox', { name: 'Remarks', exact: true }).fill('Must not appear for Admin')
  await context.setOffline(true)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  await context.setOffline(false)
  const another = await context.newPage()
  await another.goto('/#/account')
  await another.getByRole('button', { name: 'Sign Out', exact: true }).click()
  await expect(another.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  await signIn(another, 'admin')
  await another.close()
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Admin Dashboard', exact: true })).toBeVisible()
  await page.goto(`/#/clients/${client.id}`)
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Remarks', exact: true })).not.toHaveValue('Must not appear for Admin')
  await expect(page.getByText('Your unsaved draft is available. Choose Edit to resume it.', { exact: true })).toHaveCount(0)
})

test('notes Retry refreshes stale directory authority after another device saves', async ({ page, context }, info) => {
  const { client, panel } = await notesPage(page, info)
  await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Home', exact: true }).click()
  const another = await context.newPage()
  try {
    await another.goto(`/#/clients/${client.id}`)
    const notes = another.locator('.panel').filter({ has: another.getByRole('heading', { name: 'Remarks', exact: true }) })
    await notes.getByRole('button', { name: 'Edit', exact: true }).click()
    const value = `Other device revision ${info.project.name}`
    await another.getByRole('textbox', { name: 'Remarks', exact: true }).fill(value)
    await notes.getByRole('button', { name: 'Save', exact: true }).click()
    await another.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
    await notes.getByRole('button', { name: 'Edit', exact: true }).waitFor()
    await page.goto(`/#/clients/${client.id}`)
    await page.getByRole('button', { name: 'Retry client notes', exact: true }).click()
    await expect(panel.getByText(value, { exact: true })).toBeVisible()
    expect((await read(page, `/api/clients/${client.id}/notes`)).version).toBe(client.version + 1)
    await panel.getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByRole('textbox', { name: 'Remarks', exact: true }).fill('Unsaved after refreshed review')
    const refreshed = page.waitForResponse(response => response.url().endsWith('/api/session-calendar'))
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await refreshed
    await expect(page.getByRole('textbox', { name: 'Remarks', exact: true })).toHaveValue('Unsaved after refreshed review')
  } finally { await another.close() }
})

test('an active notes draft survives a concurrent directory version and still rejects a stale write', async ({ page, context }, info) => {
  const { client, panel } = await notesPage(page, info, 'notes-stale')
  const draft = `Preserved draft ${info.project.name}`
  await page.getByRole('textbox', { name: 'Remarks', exact: true }).fill(draft)
  const another = await context.newPage()
  try {
    await another.goto(`/#/clients/${client.id}`)
    const otherPanel = another.locator('.panel').filter({ has: another.getByRole('heading', { name: 'Remarks', exact: true }) })
    await otherPanel.getByRole('button', { name: 'Edit', exact: true }).click()
    await another.getByRole('textbox', { name: 'Remarks', exact: true }).fill('Concurrent committed value')
    await otherPanel.getByRole('button', { name: 'Save', exact: true }).click()
    await another.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
    await expect(otherPanel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
    const refreshed = page.waitForResponse(response => response.url().endsWith('/api/session-calendar'))
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await refreshed
    await expect(page.getByRole('textbox', { name: 'Remarks', exact: true })).toHaveValue(draft)
    const rejected = page.waitForResponse(response => response.url().endsWith(`/api/clients/${client.id}/notes`) && response.request().method() === 'POST')
    await panel.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
    expect((await rejected).status()).toBe(409)
    await expect(page.getByRole('textbox', { name: 'Remarks', exact: true })).toHaveValue(draft)
    expect((await read(page, `/api/clients/${client.id}/notes`)).remarks).toBe('Concurrent committed value')
  } finally { await another.close() }
})

for (const committed of [true, false]) test(`cancelled notes recover their original ${committed ? 'committed' : 'uncommitted'} command without replacing its intent`, async ({ page, browser }, info) => {
  const purpose = committed ? 'notes-committed' : 'notes-uncommitted'
  const { client, panel } = await notesPage(page, info, purpose)
  const original = `Original uncertain ${committed} ${info.project.name}`
  await page.getByRole('textbox', { name: 'Remarks', exact: true }).fill(original)
  const writes = []
  await page.route(`**/api/clients/${client.id}/notes`, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    writes.push({ body: route.request().postData(), key: route.request().headers()['idempotency-key'] })
    if (writes.length > 1) return route.continue()
    if (committed) expect((await route.fetch()).status()).toBe(200)
    await route.abort('failed')
  })
  await panel.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
  await expect(panel.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled()
  await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Check Previous Notes Save', exact: true }).click()
  expect(writes).toHaveLength(1)
  if (!committed) {
    await page.getByRole('button', { name: 'Retry Original Notes Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Retry Original Save', exact: true }).click()
  }
  await expect(panel.getByText(original, { exact: true })).toBeVisible()
  await expect(page.getByText('The response was interrupted. Check the current state before trying again.', { exact: true })).toHaveCount(0)
  expect(writes).toHaveLength(committed ? 1 : 2)
  if (!committed) expect(writes[1]).toEqual(writes[0])
  const fresh = await freshContext(browser, page)
  try {
    const next = await fresh.newPage()
    await signIn(next, 'owner', account(purpose))
    const saved = await read(next, `/api/clients/${client.id}/notes`)
    expect(saved.remarks).toBe(original)
    expect(saved.version).toBe(client.version + 1)
    // A resolved command must no longer block a different client or a fresh intent.
    const other = (await read(page, '/api/directory')).clients.find(row => row.name === `${info.project.name} contacts`)
    expect(other.id).not.toBe(client.id)
    await page.goto(`/#/clients/${other.id}`)
    await expect(page.getByRole('heading', { name: other.name, exact: true })).toBeVisible()
    const otherPanel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Remarks', exact: true }) })
    await otherPanel.getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByRole('textbox', { name: 'Remarks', exact: true }).fill(`Fresh intent after ${committed}`)
    await otherPanel.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
    await expect(otherPanel.getByText(`Fresh intent after ${committed}`, { exact: true })).toBeVisible()
    expect((await read(next, `/api/clients/${client.id}/notes`))).toEqual(saved)
  } finally { await fresh.close() }
})

for (const editor of ['general information', 'assessment']) test(`${editor} draft survives another device's notes write`, async ({ page, context }, info) => {
  const { client, panel } = await notesPage(page, info, editor === 'assessment' ? 'draft-assessment' : 'draft-general')
  await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
  let field
  if (editor === 'general information') {
    const general = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information', exact: true }) })
    await general.getByRole('button', { name: 'Edit', exact: true }).click()
    field = page.getByLabel('Client email', { exact: true })
    await field.fill('preserve-unsaved@example.test')
  } else {
    await page.getByRole('button', { name: 'Static Balance — Not filled', exact: true }).click()
    field = page.getByRole('dialog', { name: 'Static Balance', exact: true }).getByRole('spinbutton', { name: 'Eyes open — trial 1 (seconds)', exact: true })
    await field.fill('17')
  }
  const another = await context.newPage()
  try {
    await another.goto(`/#/clients/${client.id}`)
    const otherPanel = another.locator('.panel').filter({ has: another.getByRole('heading', { name: 'Remarks', exact: true }) })
    await otherPanel.getByRole('button', { name: 'Edit', exact: true }).click()
    await another.getByRole('textbox', { name: 'Remarks', exact: true }).fill(`Concurrent notes while editing ${editor}`)
    await otherPanel.getByRole('button', { name: 'Save', exact: true }).click()
    await another.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click()
    await expect(otherPanel.getByRole('button', { name: 'Edit', exact: true })).toBeVisible()
    const refreshed = page.waitForResponse(response => response.url().endsWith('/api/session-calendar'))
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await refreshed
    await expect(field).toHaveValue(editor === 'assessment' ? '17' : 'preserve-unsaved@example.test')
    expect((await read(page, `/api/clients/${client.id}/notes`)).version).toBe(client.version + 1)
  } finally { await another.close() }
})
