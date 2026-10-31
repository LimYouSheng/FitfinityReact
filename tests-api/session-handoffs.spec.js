import { readFile } from 'node:fs/promises'
import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'trainer') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
  const client = (await read(page, '/api/directory')).clients.find(c => c.name === `${info.project.name} ${purpose}`)
  expect(client).toBeTruthy()
  const sessions = (await read(page, '/api/session-calendar')).sessions
  if (role === 'trainer') expect(sessions).toHaveLength(2)
  else expect(sessions.some(s => s.clientId !== client.id)).toBe(true)
  const session = sessions.find(s => s.clientId === client.id && s.sessionNumber === 1)
  const before = await read(page, `/api/sessions/${session.id}/details`)
  expect(before.whatsappOpenCount).toBe(0)
  await page.goto(`/#/sessions/${session.id}`)
  await expect(page.getByRole('button', { name: 'Export Summary', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: /WhatsApp/ })).toHaveCount(0)
  return { client, session, before }
}
function unchanged(after, before) {
  expect(after.session.status).toBe(before.session.status)
  for (const field of ['acknowledgementHistory', 'purchase', 'exerciseResults', 'trainerComments', 'clientSummary']) expect(after[field]).toEqual(before[field])
}

for (const [purpose, role] of [['handoff', 'trainer'], ['handoffadmin', 'admin']]) test(`${role} PDF UI does not fabricate handoff; explicit compatibility action persists once`, async ({ page, browser }, info) => {
  const { session, before } = await open(page, info, purpose, role)
  const preparationStarted = performance.now()
  await page.getByRole('button', { name: 'Export Summary', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Export Summary', exact: true })
  await expect(dialog).toBeVisible()
  const downloadButton = dialog.getByRole('button', { name: 'Download PDF', exact: true })
  await expect(downloadButton).toBeEnabled()
  info.annotations.push({ type: 'pdf-ready-ms', description: String(Math.round(performance.now() - preparationStarted)) })
  const download = page.waitForEvent('download')
  await downloadButton.click()
  const file = await download
  expect(await file.failure()).toBeNull()
  expect((await readFile(await file.path())).subarray(0, 5).toString()).toBe('%PDF-')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  expect((await read(page, `/api/sessions/${session.id}/details`)).whatsappOpenCount).toBe(0)
  const review = await read(page, `/api/sessions/${session.id}/handoff-review`)
  const key = crypto.randomUUID(), body = { expected: review.expected }
  const first = await post(page, `/api/sessions/${session.id}/handoff`, body, key)
  expect(first.status()).toBe(200)
  expect(await (await post(page, `/api/sessions/${session.id}/handoff`, body, key)).json()).toEqual(await first.json())
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account(purpose))
  const after = await read(staff, `/api/sessions/${session.id}/details`)
  unchanged(after, before)
  expect(after.whatsappOpenCount).toBe(1)
  expect(after.whatsappOpenedAt).toBeTruthy()
  expect((await staff.request.get(`/api/session-handoffs/${key}`)).status()).toBe(404)
  await context.close()
})

test('handoff rejects foreign, future, stale and forged actions without partial effects', async ({ page, browser }, info) => {
  const { session, before } = await open(page, info, 'handoffforeign')
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('handoffforeign'))
  const all = (await read(staff, '/api/session-calendar')).sessions
  const foreign = all.find(s => s.clientId !== session.clientId)
  expect(foreign).toBeTruthy()
  const review = await read(page, `/api/sessions/${session.id}/handoff-review`)
  expect((await post(page, `/api/sessions/${foreign.id}/handoff`, { expected: review.expected })).status()).toBe(404)
  expect((await post(page, `/api/sessions/${session.id}/handoff`, { expected: review.expected, delivered: true })).status()).toBe(422)
  const futureClient = (await read(staff, '/api/directory')).clients.find(c => c.name === `${info.project.name} handofffuture`)
  const future = all.find(s => s.clientId === futureClient.id)
  expect((await staff.request.get(`/api/sessions/${future.id}/handoff-review`)).status()).toBe(409)
  const key = crypto.randomUUID()
  const first = await post(page, `/api/sessions/${session.id}/handoff`, { expected: review.expected }, key)
  expect(first.status()).toBe(200)
  expect((await post(page, `/api/sessions/${session.id}/handoff`, { expected: review.expected })).status()).toBe(409)
  expect((await post(page, `/api/sessions/${session.id}/handoff`, { expected: '0'.repeat(64) }, key)).status()).toBe(409)
  const after = await read(staff, `/api/sessions/${session.id}/details`)
  unchanged(after, before)
  expect(after.whatsappOpenCount).toBe(1)
  await context.close()
})

test('lost compatibility response recovers its original receipt without a second opening', async ({ page, browser }, info) => {
  const { session, before } = await open(page, info, 'handoffloss')
  const review = await read(page, `/api/sessions/${session.id}/handoff-review`)
  const auth = await read(page, '/auth/session'), key = crypto.randomUUID()
  const outcome = await page.evaluate(async ({ id, expected, csrf, key }) => {
    try {
      const response = await fetch(`/api/sessions/${id}/handoff`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Idempotency-Key': key }, body: JSON.stringify({ expected }) })
      if (!response.ok) return `HTTP ${response.status}`
      await response.text()
      throw new TypeError('Lost committed opening response')
    } catch (error) { return error.message }
  }, { id: session.id, expected: review.expected, csrf: auth.csrfToken, key })
  expect(outcome).toBe('Lost committed opening response')
  const receipt = await read(page, `/api/session-handoffs/${key}`)
  expect(receipt.whatsappOpenCount).toBe(1)
  await page.reload()
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('handoffloss'))
  const after = await read(staff, `/api/sessions/${session.id}/details`)
  unchanged(after, before)
  expect(after.whatsappOpenCount).toBe(1)
  await context.close()
})
