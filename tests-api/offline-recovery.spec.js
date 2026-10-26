import { test, expect, signIn, read, account, freshContext } from './fixtures.js'

/** Real notes workflow, with connectivity loss rather than substituted API responses. */
async function notesPage(page, info) {
  await signIn(page, 'owner', account('contacts'))
  const client = (await read(page, '/api/directory')).clients.find(row => row.name === `${info.project.name} contacts`)
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
