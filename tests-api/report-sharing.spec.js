import { fetchRoute, test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

for (const kind of ['progress', 'session']) test(`${kind} sharing waits for exact Owner approval and lost-response recovery never launches sharing`, async ({ page, browser }, info) => {
  const purpose = `reportshare${kind}`
  await signIn(page, 'owner', account(purpose))
  const admin = (await read(page, '/api/staff/admins')).find(item => item.details.email === account(purpose, 'admin'))
  const current = await read(page, `/api/staff/admins/${admin.id}`)
  expect((await post(page, `/api/staff/admins/${admin.id}`, { expectedVersion: current.version, operation: 'approvals',
    approvalNeeded: { ...current.approvalNeeded, [kind === 'progress' ? 'progressReportSharing' : 'sessionPdfSharing']: true } })).status()).toBe(200)
  const client = (await read(page, '/api/directory')).clients.find(item => item.name === `${info.project.name} ${purpose}`)
  const sessions = (await read(page, '/api/session-calendar')).sessions
  const booking = sessions.find(item => item.clientId === client.id && item.sessionNumber === 1)
  expect(sessions.some(item => item.clientId !== client.id)).toBe(true)
  const context = await freshContext(browser, page)
  try {
    const staff = await context.newPage()
    await staff.addInitScript(() => {
      window.reportShareCalls = 0
      Object.defineProperty(navigator, 'canShare', { configurable: true, value: () => true })
      Object.defineProperty(navigator, 'share', { configurable: true, value: async ({ files }) => {
        if (files.length !== 1 || files[0].type !== 'application/pdf') throw new Error('Expected a PDF')
        window.reportShareCalls++
      } })
    })
    await signIn(staff, 'admin', account(purpose, 'admin'))
    const open = async () => {
      await staff.goto(kind === 'progress' ? `/#/clients/${client.id}/progress/${booking.purchaseId}` : `/#/sessions/${booking.id}`)
      if (kind === 'session') await staff.getByRole('button', { name: 'Export Summary', exact: true }).click()
    }
    const share = () => staff.getByRole('button', { name: kind === 'progress' ? 'Share Progress Report PDF' : 'Share PDF', exact: true })
    await open()
    const download = staff.waitForEvent('download')
    await staff.getByRole('button', { name: kind === 'progress' ? 'Download Progress Report PDF' : 'Download PDF', exact: true }).click()
    expect(await (await download).failure()).toBeNull()
    expect(await read(staff, '/api/admin-requests')).toHaveLength(0)
    let writes = 0
    await staff.route('**/api/report-sharing', async route => {
      writes++
      const response = await fetchRoute(route)
      expect(response.status()).toBe(202)
      await route.abort('failed')
    })
    await share().click()
    await expect(staff.getByRole('status').filter({ hasText: 'The response was interrupted. Check the current state before trying again.' })).toBeVisible()
    await staff.unroute('**/api/report-sharing')
    await share().click()
    await expect(staff.getByRole('status').filter({ hasText: 'Waiting for Owner approval' })).toBeVisible()
    expect(writes).toBe(1)
    expect(await staff.evaluate(() => window.reportShareCalls)).toBe(0)
    const requests = await read(staff, '/api/admin-requests')
    expect(requests).toHaveLength(1)
    expect(requests[0].operation).toBe(`report.${kind}`)
    expect((await page.request.get(`/api/report-sharing/requests/${requests[0].id}`)).status()).toBe(404)
    await page.goto('/#/messages')
    await page.locator('.info-row').filter({ hasText: `${purpose} admin` }).getByRole('button', { name: 'Review', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Download Reviewed PDF', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
    await page.getByRole('dialog', { name: 'Approve?', exact: true }).getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(page.getByText(`${purpose} admin · approved`, { exact: true })).toBeVisible()
    await staff.reload()
    await open()
    await share().click()
    await expect(staff.getByRole('status').filter({ hasText: 'Report ready.' })).toBeVisible()
    expect(await staff.evaluate(() => window.reportShareCalls)).toBe(0)
    await share().click()
    await expect.poll(() => staff.evaluate(() => window.reportShareCalls)).toBe(1)
    expect(await read(staff, '/api/admin-requests')).toHaveLength(1)
    if (kind === 'progress') {
      await expect.poll(async () => (await read(page, `/api/clients/${client.id}/report-history`)).filter(item => item.kind === 'pdf_share_opened').length).toBe(1)
    } else {
      const after = await read(staff, `/api/sessions/${booking.id}/details`)
      expect(after.whatsappOpenCount).toBe(0)
      expect(after.whatsappOpenedAt).toBeNull()
    }
  } finally { await context.close() }
})
