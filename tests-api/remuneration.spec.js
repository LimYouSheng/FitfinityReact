import { test, expect, signIn, read, post, account, freshContext, confirm } from './fixtures.js'

async function open(page, info, purpose) {
  await signIn(page, 'owner', account(purpose))
  const trainer = (await read(page, '/api/directory')).trainers.find(t => t.name === `${info.project.name} ${purpose} Trainer`)
  expect(trainer).toBeTruthy()
  const views = await read(page, '/api/remuneration')
  expect(views.some(view => view.trainers.some(row => row.trainerId !== trainer.id))).toBe(true)
  const view = views.find(view => view.trainers.some(row => row.trainerId === trainer.id && row.sessions === 2))
  expect(view).toBeTruthy()
  await page.goto(`/#/remuneration/${view.key}/${trainer.id}`)
  await expect(page.getByRole('heading', { name: trainer.name, exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Show remuneration amounts' }).click()
  await expect(page.getByRole('button', { name: 'Approve Remuneration', exact: true })).toBeEnabled()
  return { trainer, cycle: view.key, review: view.trainers.find(row => row.trainerId === trainer.id) }
}

test('Owner approval survives fresh Trainer login with original amounts and Admin financial denial', async ({ page, browser }, info) => {
  const { trainer, cycle, review } = await open(page, info, 'pay')
  const response = page.waitForResponse(r => r.url().endsWith(`/api/remuneration/${cycle}/${trainer.id}/approval`) && r.request().method() === 'POST')
  await confirm(page, 'Approve Remuneration')
  expect((await response).status()).toBe(200)
  await expect(page.getByText('Approved', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Approved', { exact: true })).toBeVisible()
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'trainer', `${info.project.name}-pay@example.test`)
  const views = await read(staff, '/api/remuneration')
  expect(views.every(v => v.trainers.every(r => r.trainerId === trainer.id))).toBe(true)
  await staff.goto(`/#/remuneration/${cycle}`)
  await expect(staff.getByText('Approved', { exact: true })).toBeVisible()
  await expect(staff.getByRole('button', { name: 'Approve Remuneration', exact: true })).toHaveCount(0)
  const saved = await read(staff, `/api/remuneration/${cycle}/${trainer.id}`)
  expect(saved).toMatchObject({ amountCents: review.amountCents, minutes: review.minutes, sessions: 2, status: 'Approved' })
  await context.close()
  const adminContext = await freshContext(browser, page), admin = await adminContext.newPage()
  await signIn(admin, 'admin', account('pay', 'admin'))
  expect((await admin.request.get('/api/remuneration')).status()).toBe(403)
  expect((await admin.request.get(`/api/remuneration/${cycle}/${trainer.id}`)).status()).toBe(403)
  expect((await post(admin, `/api/remuneration/${cycle}/${trainer.id}/approval`, { revision: review.revision })).status()).toBe(403)
  await adminContext.close()
})

test('changed rates reject stale UI approval and Trainer cannot read foreign pay or Owner receipts', async ({ page, browser }, info) => {
  const { trainer, cycle, review } = await open(page, info, 'paystale')
  const changed = await post(page, `/api/trainers/${trainer.id}/rates`, { expectedVersion: trainer.version, rates: { peak: 12345, offPeak: 6789 } })
  expect(changed.status()).toBe(200)
  await confirm(page, 'Approve Remuneration')
  await expect(page.getByRole('alert').first()).toContainText('Record changed')
  expect((await read(page, `/api/remuneration/${cycle}/${trainer.id}`)).status).toBe('Pending approval')
  await page.reload()
  await expect(page.getByRole('button', { name: 'Approve Remuneration', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Hide remuneration amounts' })).toBeVisible()
  const revisedTotal = review.rows.reduce((sum, row) => sum + (row.band === 'peak' ? 12345 : 6789), 0)
  await expect(page.getByText(new Intl.NumberFormat('en-SG', { style: 'currency', currency: 'SGD' }).format(revisedTotal / 100), { exact: true })).toBeVisible()
  await confirm(page, 'Approve Remuneration')
  await expect(page.getByText('Approved', { exact: true })).toBeVisible()
  const foreign = (await read(page, '/api/remuneration')).flatMap(v => v.trainers).find(r => r.trainerId !== trainer.id)
  expect(foreign).toBeTruthy()
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'trainer', `${info.project.name}-paystale@example.test`)
  expect((await staff.request.get(`/api/remuneration/${foreign.cycle.key}/${foreign.trainerId}`)).status()).toBe(404)
  expect((await post(staff, `/api/remuneration/${cycle}/${trainer.id}/approval`, { revision: review.revision })).status()).toBe(403)
  expect((await staff.request.get(`/api/remuneration-approvals/${crypto.randomUUID()}`)).status()).toBe(403)
  await context.close()
})

for (const recovery of ['inline', 'refresh']) test(`lost committed approval uses ${recovery} recovery with one original write`, async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window)
    window.payWrites = 0
    window.fetch = async (url, options) => {
      const response = await fetch(url, options)
      if (options?.method === 'POST' && /\/api\/remuneration\/[^/]+\/[^/]+\/approval$/.test(String(url))) {
        window.payWrites++
        if (window.payWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed approval') }
      }
      return response
    }
  })
  const purpose = recovery === 'refresh' ? 'payrefresh' : 'payloss'
  const { trainer, cycle, review } = await open(page, info, purpose)
  await confirm(page, 'Approve Remuneration')
  await expect(page.getByRole('button', { name: 'Check original remuneration approval', exact: true })).toBeVisible()
  if (recovery === 'refresh') await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check original remuneration approval', exact: true }).click()
  await expect(page.getByText('Approved', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.payWrites)).toBe(1)
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'trainer', `${info.project.name}-${purpose}@example.test`)
  const saved = await read(staff, `/api/remuneration/${cycle}/${trainer.id}`)
  expect(saved).toMatchObject({ amountCents: review.amountCents, sessions: 2, status: 'Approved' })
  await context.close()
})
