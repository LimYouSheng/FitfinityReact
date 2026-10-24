import { readFile } from 'node:fs/promises'
import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'trainer') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
  const client = (await read(page, '/api/directory')).clients.find(c => c.name === `${info.project.name} ${purpose}`)
  expect(client).toBeTruthy()
  const all = (await read(page, '/api/session-calendar')).sessions
  if (role === 'trainer') expect(all).toHaveLength(2)
  else expect(all.some(s => s.clientId !== client.id)).toBe(true)
  const session = all.find(s => s.clientId === client.id && s.sessionNumber === 1)
  await page.goto(`/#/clients/${client.id}/progress/${session.purchaseId}`)
  await expect(page.getByRole('button', { name: 'Download Progress Report PDF', exact: true })).toBeEnabled()
  return { client, session }
}
async function download(page) {
  const event = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download Progress Report PDF', exact: true }).click()
  const file = await event
  expect(file.suggestedFilename()).toMatch(/progress-report\.pdf$/)
  expect(await file.failure()).toBeNull()
  const bytes = await readFile(await file.path())
  expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
  expect(bytes.length).toBeGreaterThan(500)
}
for (const [purpose, role] of [['report', 'trainer'], ['reportadmin', 'admin']]) {
  test(`${role} actual PDF download persists one scoped audit visible to fresh-login operations`, async ({ page, browser }, info) => {
    const { client, session } = await open(page, info, purpose, role)
    const recorded = page.waitForResponse(r => r.url().endsWith(`/api/clients/${client.id}/report-actions`) && r.request().method() === 'POST')
    await download(page)
    expect((await recorded).status()).toBe(200)
    await page.reload()
    if (role === 'trainer') {
      await expect(page.getByRole('button', { name: 'View Export/WhatsApp History', exact: true })).toHaveCount(0)
      expect((await page.request.get(`/api/clients/${client.id}/report-history`)).status()).toBe(403)
    }
    const context = await freshContext(browser, page), staff = await context.newPage()
    await signIn(staff, 'owner', account(purpose))
    const rows = await read(staff, `/api/clients/${client.id}/report-history?purchase_id=${session.purchaseId}`)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ clientId: client.id, packageId: session.purchaseId, kind: 'pdf_export' })
    expect(rows[0].by.name).toBeTruthy()
    await staff.goto(`/#/clients/${client.id}/progress/${session.purchaseId}`)
    await staff.getByRole('button', { name: 'View Export/WhatsApp History', exact: true }).click()
    await expect(staff.getByLabel('Export/WhatsApp history')).toContainText('PDF export')
    await context.close()
  })
}

test('report actions reject foreign clients, forged actors, mismatched packages and conflicting keys', async ({ page, browser }, info) => {
  const { client, session } = await open(page, info, 'reportforeign')
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('reportforeign'))
  const foreign = (await read(staff, '/api/session-calendar')).sessions.find(s => s.clientId !== client.id)
  expect(foreign).toBeTruthy()
  const body = { purchaseId: session.purchaseId, kind: 'pdf_share_opened' }
  expect((await post(page, `/api/clients/${foreign.clientId}/report-actions`, { ...body, purchaseId: foreign.purchaseId })).status()).toBe(404)
  expect((await post(page, `/api/clients/${client.id}/report-actions`, { ...body, purchaseId: foreign.purchaseId })).status()).toBe(404)
  expect((await post(page, `/api/clients/${client.id}/report-actions`, { ...body, actorId: foreign.trainerId })).status()).toBe(422)
  const key = crypto.randomUUID()
  const first = await post(page, `/api/clients/${client.id}/report-actions`, body, key)
  expect(first.ok()).toBe(true)
  expect(await (await post(page, `/api/clients/${client.id}/report-actions`, body, key)).json()).toEqual(await first.json())
  expect((await post(page, `/api/clients/${client.id}/report-actions`, { ...body, kind: 'pdf_export' }, key)).status()).toBe(409)
  expect(await read(staff, `/api/clients/${client.id}/report-history`)).toHaveLength(1)
  expect((await staff.request.get(`/api/report-actions/${key}`)).status()).toBe(404)
  await context.close()
})

for (const recovery of ['inline', 'refresh']) test(`lost audit response uses ${recovery} recovery without a second PDF download or audit write`, async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window)
    window.reportWrites = 0
    window.fetch = async (url, options) => {
      const response = await fetch(url, options)
      if (options?.method === 'POST' && /\/api\/clients\/[^/]+\/report-actions$/.test(String(url))) {
        window.reportWrites++
        if (window.reportWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed report audit') }
      }
      return response
    }
  })
  let downloads = 0
  page.on('download', () => { downloads++ })
  const { client } = await open(page, info, recovery === 'refresh' ? 'reportrefresh' : 'reportloss')
  await download(page)
  await expect(page.getByRole('alert')).toContainText('history could not be saved')
  await expect(page.getByRole('button', { name: 'Download Progress Report PDF', exact: true })).toBeDisabled()
  if (recovery === 'refresh') {
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await page.getByRole('button', { name: 'Check original report history', exact: true }).click()
    await expect(page.getByText('Original report history confirmed.', { exact: true })).toBeVisible()
  } else await page.getByRole('button', { name: 'Retry History Save', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Retry History Save', exact: true })).toHaveCount(0)
  expect(downloads).toBe(1)
  expect(await page.evaluate(() => window.reportWrites)).toBe(1)
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account(recovery === 'refresh' ? 'reportrefresh' : 'reportloss'))
  expect(await read(staff, `/api/clients/${client.id}/report-history`)).toHaveLength(1)
  await context.close()
})
