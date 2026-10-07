import { test, expect, waitForPortal, selectDemoIdentity, drawClientSignature } from './fixtures.js'
import { signatureFixture } from '../src/test/fixtures/signature.js'
import { createDemoSeed } from '../src/data/seed.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const instant = new Date('2026-10-03T01:00:00Z')
const read = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
const activate = (locator, isMobile, options) => isMobile ? locator.tap(options) : locator.click(options)
async function start(page, { twice = false, supervised = false, past = false, inactive = false, conflict = false } = {}) {
  const data = createDemoSeed('2026-10-03')
  const client = data.clients.find(item => item.id === 'c1')
  client.name = 'Postpone Client'; client.status = inactive ? 'inactive' : 'active'; client.trainerId = 't1'
  client.fixedWeeklySchedule = [{ id: 'mon', day: 'Monday', from: '10:00', to: '11:00' }, ...(twice ? [{ id: 'thu', day: 'Thursday', from: '10:00', to: '11:00' }] : [])]
  Object.assign(client.package, { used: 0, status: 'active', startDate: '2026-09-01', endDate: '2026-12-31', fixedWeeklySchedule: structuredClone(client.fixedWeeklySchedule) })
  const original = data.sessions.find(item => item.clientId === 'c1')
  data.sessions = (twice ? ['2026-10-05', '2026-10-08', '2026-10-12', '2026-10-15'] : ['2026-10-05', '2026-10-12', '2026-10-19']).map((date, index) => ({ ...original,
    id: `undo-s${index + 1}`, clientId: client.id, trainerId: 't1', packageId: client.package.id, date: past && !index ? '2026-10-03' : date,
    from: past && !index ? '08:00' : '10:00', to: past && !index ? '09:00' : '11:00', weeklySlotId: twice && index % 2 ? 'thu' : 'mon',
    sessionNumber: index + 1, status: 'planned', acknowledgement: null, acknowledgementHistory: [], clientSummary: '',
    exercisePlan: [], exerciseResults: undefined }))
  if (conflict) {
    Object.assign(data.sessions[0], { date: '2026-10-06', from: '12:00', to: '13:00' })
    const other = data.clients.find(item => item.id === 'c2')
    other.status = 'active'; other.package.status = 'active'
    data.sessions.push({ ...data.sessions[0], id: 'occupied-tail', clientId: other.id, packageId: other.package.id, date: '2026-10-26', from: '10:00', to: '11:00' })
  }
  for (const trainer of data.trainers) { trainer.status = 'active'; trainer.approvalNeeded.sessionTime = supervised }
  data.messages = []; data.packageCreditTransactions = []; data.remunerationApprovals = []
  await page.clock.setFixedTime(instant)
  await page.addInitScript(({ key, data }) => { if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(data)) }, { key: KEY, data })
  await page.goto('/#/sessions/undo-s1'); await waitForPortal(page)
  await expect(page.getByRole('heading', { name: 'Session Overview', exact: true })).toBeVisible()
}
async function postpone(page, isMobile) {
  await activate(page.getByRole('button', { name: 'Postpone', exact: true }), isMobile)
  const dialog = page.getByRole('dialog', { name: 'Postpone this session?', exact: true })
  await expect(dialog).toBeVisible()
  await activate(dialog.getByRole('button', { name: 'Confirm Postponement', exact: true }), isMobile)
  await expect(dialog).toHaveCount(0); await waitForPortal(page)
}
async function messages(page) {
  await page.goto('/#/messages'); await waitForPortal(page)
  await expect(page).toHaveURL(/#\/messages$/)
  await expect(page.getByRole('heading', { name: 'Messages', exact: true })).toBeVisible()
}
async function reverse(page, isMobile, row) {
  const title = await row.getByRole('button', { name: /^Open / }).getAttribute('aria-label')
  const stableRow = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: title, exact: true }) })
  await activate(row.getByRole('button', { name: /^Undo / }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Undo session change?', exact: true }).getByRole('button', { name: 'Undo Change', exact: true }), isMobile)
  await expect(stableRow.getByRole('status')).toHaveText('Undone'); await waitForPortal(page)
}
const postponedRow = page => page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: 'Open Session postponed: Postpone Client', exact: true }) })

for (const twice of [false, true]) test(`session actions: ${twice ? 'twice' : 'once'} weekly preview, single move and persistent Undo`, async ({ page, isMobile }) => {
  await start(page, { twice }); const before = await read(page)
  await activate(page.getByRole('button', { name: 'Postpone', exact: true }), isMobile)
  const preview = page.getByRole('dialog', { name: 'Postpone this session?', exact: true })
  await expect(preview.locator('tbody tr')).toHaveCount(1)
  await expect(preview).toContainText('package credits and validity stay unchanged')
  await activate(preview.getByRole('button', { name: 'Cancel', exact: true }), isMobile)
  expect((await read(page)).sessions).toEqual(before.sessions)
  await postpone(page, isMobile)
  expect((await read(page)).sessions.map(item => item.date)).toEqual(twice ? [null, '2026-10-08', '2026-10-12', '2026-10-15'] : [null, '2026-10-12', '2026-10-19'])
  expect((await read(page)).sessions.slice(1).map(({ sessionNumber, ...rest }) => rest)).toEqual(before.sessions.slice(1).map(({ sessionNumber, ...rest }) => rest))
  await messages(page)
  const row = postponedRow(page); await expect(row.getByRole('button', { name: /^Undo / })).toBeEnabled()
  await reverse(page, isMobile, row); await page.reload(); await waitForPortal(page)
  const after = await read(page)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.clients.find(item => item.id === 'c1').package.used).toBe(0)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  await expect(row.getByRole('status')).toHaveText('Undone')
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
})

test('session actions: Undo expires while confirmation is open', async ({ page, isMobile }) => {
  await start(page); await postpone(page, isMobile); await messages(page)
  const row = postponedRow(page)
  await activate(row.getByRole('button', { name: /^Undo / }), isMobile)
  const before = await read(page), expiry = before.sessionMutations.at(-1).expiresAt
  await page.clock.setFixedTime(new Date(expiry))
  await activate(page.getByRole('dialog', { name: 'Undo session change?', exact: true }).getByRole('button', { name: 'Undo Change', exact: true }), isMobile)
  await expect(row.getByRole('alert')).toContainText('Undo expired')
  expect((await read(page)).sessions).toEqual(before.sessions)
  await page.reload(); await waitForPortal(page)
  await expect(row.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  await expect(row).toContainText('Undo expired')
})

test('session actions: supervised postponement is approved then reversed without reopening', async ({ page, isMobile }) => {
  await start(page, { supervised: true }); const before = await read(page)
  await selectDemoIdentity(page, 'u-marcus'); await page.goto('/#/sessions/undo-s1'); await waitForPortal(page)
  await postpone(page, isMobile)
  expect((await read(page)).sessions).toEqual(before.sessions)
  await selectDemoIdentity(page, 'u-owner'); await messages(page)
  const title = 'Postponement requested: Postpone Client'
  await activate(page.getByRole('button', { name: `Open ${title}`, exact: true }), isMobile)
  await expect(page.getByRole('region', { name: 'Requested change' })).toContainText('Open session · Date/time not set')
  await activate(page.getByRole('button', { name: 'Approve Request', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Approve request?', exact: true }).getByRole('button', { name: 'Approve Request', exact: true }), isMobile)
  await expect.poll(async () => (await read(page)).sessions[0].date).toBe(null)
  await activate(page.getByRole('button', { name: 'Close message', exact: true }), isMobile)
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${title}`, exact: true }) })
  await reverse(page, isMobile, row)
  const after = await read(page)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.messages.find(item => item.request?.type === 'session_postpone').status).toBe('reversed')
})

for (const method of ['signature', 'late_no_show']) test(`session actions: ${method} acknowledgement is final in Messages`, async ({ page, isMobile }) => {
  await start(page, { past: true })
  await activate(page.getByRole('button', { name: 'Client Signature', exact: true }), isMobile)
  if (method === 'signature') await drawClientSignature(page)
  else await activate(page.getByRole('button', { name: 'Record late / no-show instead', exact: true }), isMobile)
  await activate(page.getByRole('button', { name: 'Review Completion', exact: true }), isMobile)
  const confirmation = page.getByRole('dialog', { name: 'Complete this session?', exact: true })
  await expect(confirmation).toContainText('It cannot be undone')
  await activate(confirmation.getByRole('button', { name: 'Complete Session', exact: true }), isMobile)
  await expect.poll(async () => (await read(page)).sessions[0].status).toBe('completed')
  const completed = await read(page)
  expect(completed.clients.find(item => item.id === 'c1').package.used).toBe(1)
  await messages(page)
  const title = 'Session acknowledgement saved: Postpone Client'
  await expect(page.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  await activate(page.getByRole('button', { name: `Open ${title}`, exact: true }), isMobile)
  await expect(page.getByRole('dialog', { name: title, exact: true }).getByRole('button', { name: /^Undo / })).toHaveCount(0)
  await activate(page.getByRole('button', { name: 'Close message', exact: true }), isMobile)
  await page.reload(); await waitForPortal(page)
  await expect(page.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  const after = await read(page)
  expect(after.sessions).toEqual(completed.sessions)
  expect(after.clients.find(item => item.id === 'c1').package.used).toBe(1)
  expect(after.packageCreditTransactions.map(item => item.type)).toEqual(['session_debit'])
  await selectDemoIdentity(page, 'u-marcus'); await messages(page)
  await expect(page.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(1)
  await expect(page.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  await page.goto('/#/sessions/undo-s1'); await waitForPortal(page)
  if (method === 'late_no_show') {
    await activate(page.getByRole('button', { name: 'Correct to Client Signature', exact: true }), isMobile)
    await drawClientSignature(page)
    await activate(page.getByRole('button', { name: 'Review Completion', exact: true }), isMobile)
    await expect(confirmation).toContainText('No additional credit will be used')
    await activate(confirmation.getByRole('button', { name: 'Complete Session', exact: true }), isMobile)
    await expect(page.getByRole('button', { name: 'View Client Signature', exact: true })).toBeVisible()
    const corrected = await read(page)
    expect(corrected.sessions[0].acknowledgementHistory).toHaveLength(2)
    expect(corrected.sessions[0].acknowledgementHistory[0]).toEqual(completed.sessions[0].acknowledgement)
    expect(corrected.packageCreditTransactions).toEqual(completed.packageCreditTransactions)
    await messages(page)
    await expect(page.getByRole('button', { name: `Open ${title}`, exact: true })).toHaveCount(2)
    await expect(page.getByRole('button', { name: /^Undo / })).toHaveCount(0)
    await page.reload(); await waitForPortal(page)
    await expect(page.getByRole('button', { name: /^Undo / })).toHaveCount(0)
  } else {
    await expect(page.getByRole('button', { name: 'View Client Signature', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Correct to Client Signature', exact: true })).toHaveCount(0)
  }
})

test('session actions: legacy acknowledgement Messages offer no Undo and preserve their evidence', async ({ page, isMobile }) => {
  await start(page, { past: true })
  await page.evaluate(({ key, signature }) => {
    const data = JSON.parse(localStorage.getItem(key)), session = data.sessions[0], before = structuredClone(session)
    const at = new Date().toISOString(), client = data.clients.find(item => item.id === 'c1')
    session.acknowledgement = { method: 'signature', signerName: client.name, signature, note: '', recordedAt: at, recordedBy: { id: 'u-marcus', name: 'Marcus Tan', role: 'trainer' } }
    session.acknowledgementHistory = [structuredClone(session.acknowledgement)]; session.status = 'completed'
    client.package.used = 1
    const debit = { id: 'legacy-debit', type: 'session_debit', sessionId: session.id, clientId: client.id, packageId: client.package.id, amount: -1, createdAt: at }
    data.packageCreditTransactions = [debit]
    data.messages = [{ id: 'legacy-message', title: 'Legacy acknowledgement', kind: 'saved_edit', body: 'Acknowledgement recorded.', createdAt: at,
      recipientRole: 'owner', recipientTrainerId: 't1', sessionId: session.id, clientId: client.id, readBy: {}, mutationId: 'legacy-operation' }]
    data.sessionMutations = [{ id: 'legacy-operation', operation: 'session.acknowledge', status: 'available',
      actor: { id: 'u-marcus', name: 'Marcus Tan', role: 'trainer', trainerId: 't1' }, committedAt: at, expiresAt: new Date(Date.now() + 86400000).toISOString(),
      sessions: [{ id: session.id, position: 0, before, after: structuredClone(session) }], patches: [], debits: [debit], creditUsage: { 'legacy-debit': 1 },
      requests: [], proposals: [], dependencies: [], messageIds: ['legacy-message'] }]
    localStorage.setItem(key, JSON.stringify(data))
  }, { key: KEY, signature: signatureFixture })
  await page.reload(); await waitForPortal(page); await messages(page)
  const before = await read(page)
  for (const user of ['u-owner', 'u-marcus']) {
    await selectDemoIdentity(page, user); await messages(page)
    await expect(page.getByRole('button', { name: /^Undo / })).toHaveCount(0)
    await activate(page.getByRole('button', { name: 'Open Legacy acknowledgement', exact: true }), isMobile)
    const dialog = page.getByRole('dialog', { name: 'Legacy acknowledgement', exact: true })
    await expect(dialog.getByRole('button', { name: /^Undo / })).toHaveCount(0)
    await activate(page.getByRole('button', { name: 'Close message', exact: true }), isMobile)
  }
  const after = await read(page)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.sessionMutations).toEqual(before.sessionMutations)
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  expect(after.clients.find(item => item.id === 'c1').package.used).toBe(1)
})

test('session actions: summary edit Undo preserves message overlay Back navigation', async ({ page, isMobile }) => {
  await start(page)
  const original = (await read(page)).sessions[0].clientSummary
  const panel = page.locator('.client-summary-panel')
  await activate(panel.getByRole('button', { name: 'Edit', exact: true }), isMobile)
  await panel.locator('textarea').fill('A newly edited client summary.')
  await activate(panel.getByRole('button', { name: 'Save', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Save client-facing summary?', exact: true }).getByRole('button', { name: 'Save Summary', exact: true }), isMobile)
  await expect(panel.locator('.client-summary-copy')).toHaveText('A newly edited client summary.')
  await messages(page)
  const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: /^Undo / }) })
  await expect(row).toHaveCount(1)
  await activate(row.getByRole('button', { name: /^Open / }), isMobile)
  await expect(page.getByRole('button', { name: 'Close message', exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Close message', exact: true })).toHaveCount(0)
  await expect(page).toHaveURL(/#\/messages$/)
  await reverse(page, isMobile, row)
  expect((await read(page)).sessions[0].clientSummary).toBe(original)
})

test('message rows: Undo whitespace and state text open details while the Undo button stays separate', async ({ page, isMobile }) => {
  await start(page); await postpone(page, isMobile); await messages(page)
  const row = postponedRow(page), title = 'Session postponed: Postpone Client'
  const saved = await read(page)
  const dialog = page.getByRole('dialog', { name: title, exact: true })
  for (const target of ['time', 'space', 'deadline']) {
    const control = target === 'time' ? row.locator('time') : target === 'deadline' ? row.getByText(/^Until /) : row.locator('.message-undo-action')
    await control.scrollIntoViewIfNeeded()
    let options
    if (target === 'space') {
      const point = await control.evaluate(element => {
        const rect = element.getBoundingClientRect(), x = rect.width - 3, y = rect.height / 2
        return { x, y, hitsSpace: document.elementFromPoint(rect.left + x, rect.top + y) === element }
      })
      expect(point.hitsSpace).toBe(true)
      options = { position: { x: point.x, y: point.y } }
    }
    await activate(control, isMobile, options)
    await expect(dialog).toBeVisible()
    await expect(page.getByRole('dialog', { name: 'Undo session change?', exact: true })).toHaveCount(0)
    expect((await read(page)).sessions).toEqual(saved.sessions)
    await activate(dialog.getByRole('button', { name: 'Close message', exact: true }), isMobile)
    await expect(dialog).toHaveCount(0)
  }
  await activate(row.getByRole('button', { name: /^Undo / }), isMobile)
  const confirm = page.getByRole('dialog', { name: 'Undo session change?', exact: true })
  await expect(confirm).toBeVisible(); await expect(dialog).toHaveCount(0)
  await activate(confirm.getByRole('button', { name: 'Cancel', exact: true }), isMobile)
  await expect(confirm).toHaveCount(0)
  for (const state of ['blocked', 'expired', 'undone']) {
    await page.evaluate(({ key, saved, state }) => {
      const data = structuredClone(saved), entry = data.sessionMutations.find(item => item.operation === 'session.postpone')
      if (state === 'expired') entry.expiresAt = '2026-10-03T00:59:59Z'
      if (state === 'undone') { entry.status = 'undone'; entry.undoneAt = '2026-10-03T01:00:00Z' }
      if (state === 'blocked') data.sessions.find(item => item.id === entry.sessions[0].id).clientSummary = 'Later change'
      localStorage.setItem(key, JSON.stringify(data))
    }, { key: KEY, saved, state })
    await page.reload(); await waitForPortal(page)
    const text = state === 'expired' ? row.getByText('Undo expired', { exact: true }) : state === 'undone' ? row.getByText('Undone', { exact: true }) : row.getByText(/The session changed again/)
    await expect(text).toBeVisible()
    const before = await read(page)
    await activate(text, isMobile)
    await expect(dialog).toBeVisible()
    expect((await read(page)).sessions).toEqual(before.sessions)
    expect((await read(page)).sessionMutations).toEqual(before.sessionMutations)
    await activate(dialog.getByRole('button', { name: 'Close message', exact: true }), isMobile)
    await expect(dialog).toHaveCount(0)
  }
})

test('package finality: legacy package Messages retain history without Undo for owner and trainer', async ({ page, isMobile }) => {
  await start(page)
  await page.evaluate(key => {
    const data = JSON.parse(localStorage.getItem(key))
    data.messages = []; data.sessionMutations = []
    for (const operation of ['client.renewPackage', 'client.deactivatePackage', 'client.reactivatePackage']) for (const status of ['available', 'undone']) {
      const id = `${operation}-${status}`
      data.messages.push({ id: `${id}-message`, mutationId: id, title: `Legacy ${id}`, body: 'Preserved package history.', clientId: 'c1',
        recipientRole: 'owner', recipientTrainerId: 't1', createdAt: '2026-10-03T01:00:00Z', kind: 'client_update', readBy: {} })
      data.sessionMutations.push({ id, operation, status, actor: { id: 'u-owner', role: 'owner', name: 'Owner' },
        committedAt: '2026-10-03T01:00:00Z', expiresAt: '2026-10-04T01:00:00Z', sessions: [], patches: [], dependencies: [], proposals: [], requests: [], messageIds: [`${id}-message`] })
    }
    localStorage.setItem(key, JSON.stringify(data))
  }, KEY)
  await page.reload(); await waitForPortal(page)
  const stored = await read(page)
  for (const actor of ['u-owner', 'u-marcus']) {
    if (actor === 'u-marcus') { await selectDemoIdentity(page, actor); await waitForPortal(page) }
    await messages(page)
    for (const message of stored.messages) {
      const row = page.locator('.message-title-row').filter({ has: page.getByRole('button', { name: `Open ${message.title}`, exact: true }) })
      await expect(row).toBeVisible()
      await expect(row.locator('.message-undo-action')).toHaveCount(0)
      await activate(row.getByRole('button', { name: `Open ${message.title}`, exact: true }), isMobile)
      const dialog = page.getByRole('dialog', { name: message.title, exact: true })
      await expect(dialog).toContainText('Preserved package history.')
      await expect(dialog.locator('.message-undo-action')).toHaveCount(0)
      await activate(dialog.getByRole('button', { name: 'Close message', exact: true }), isMobile)
      await expect(dialog).toHaveCount(0)
    }
    const current = await read(page)
    expect(current.sessionMutations).toEqual(stored.sessionMutations)
    expect(current.sessions).toEqual(stored.sessions)
    expect(current.clients).toEqual(stored.clients)
  }
})

test('session actions: a new booking blocks Undo without partial restoration', async ({ page, isMobile }) => {
  await start(page); await postpone(page, isMobile)
  await page.evaluate(key => {
    const data = JSON.parse(localStorage.getItem(key))
    const other = data.clients.find(item => item.id === 'c2')
    data.sessions.push({ ...data.sessions[0], id: 'conflicting-booking', scheduleState: 'scheduled', from: '10:00', to: '11:00', clientId: other.id, packageId: other.package.id, date: '2026-10-05' })
    localStorage.setItem(key, JSON.stringify(data))
  }, KEY)
  // A hash route change keeps mockDb's current snapshot. Reload injected storage first.
  await page.reload(); await waitForPortal(page)
  await messages(page); const before = await read(page), row = postponedRow(page)
  expect(before.sessions.some(item => item.id === 'conflicting-booking')).toBe(true)
  await activate(row.getByRole('button', { name: /^Undo / }), isMobile)
  await activate(page.getByRole('dialog', { name: 'Undo session change?', exact: true }).getByRole('button', { name: 'Undo Change', exact: true }), isMobile)
  await expect(row.getByRole('alert')).toContainText('conflicts')
  expect((await read(page)).sessions).toEqual(before.sessions)
  expect((await read(page)).sessionMutations.at(-1).status).toBe('available')
})

test('session actions: started and inactive sessions cannot be postponed', async ({ page }) => {
  await start(page, { past: true })
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  await page.evaluate(key => { const data = JSON.parse(localStorage.getItem(key)); data.clients.find(item => item.id === 'c1').status = 'inactive'; localStorage.setItem(key, JSON.stringify(data)) }, KEY)
  await page.goto('/#/sessions/undo-s2')
  // Load the injected inactive client into the app, not only browser storage.
  await page.reload(); await waitForPortal(page)
  await expect(page.getByText('Client inactive', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  expect((await read(page)).sessionMutations ?? []).toHaveLength(0)
})


test('session actions: postpone opens a session without a replacement slot even when the former suggestion conflicts', async ({ page, isMobile }) => {
  await start(page, { conflict: true }); const before = await read(page)
  await postpone(page, isMobile)
  const after = await read(page)
  expect(after.sessions[0]).toMatchObject({ scheduleState: 'open', date: null, from: null, to: null, sessionNumber: null })
  expect(after.sessions.slice(1).map(({ sessionNumber, ...rest }) => rest)).toEqual(before.sessions.slice(1).map(({ sessionNumber, ...rest }) => rest))
  expect(after.packageCreditTransactions).toEqual(before.packageCreditTransactions)
  await page.reload(); await waitForPortal(page); await messages(page)
  await reverse(page, isMobile, postponedRow(page))
  expect((await read(page)).sessions).toEqual(before.sessions)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
})

for (const actor of ['u-owner', 'u-marcus']) for (const entry of ['upcoming', 'all']) test(`open sessions: ${actor} schedules from ${entry} with multiple open records and refresh`, async ({ page, isMobile }) => {
  await start(page)
  if (actor === 'u-marcus') await selectDemoIdentity(page, actor)
  await page.goto('/#/sessions/undo-s1'); await waitForPortal(page); await postpone(page, isMobile)
  await page.goto('/#/sessions/undo-s2'); await waitForPortal(page); await postpone(page, isMobile)
  const open = await read(page)
  if (entry === 'all') {
    await page.goto('/#/sessions'); await waitForPortal(page)
    await page.getByLabel('Filter sessions by period').selectOption('all')
  } else {
    await page.goto('/#/clients/c1'); await waitForPortal(page)
    if (await page.locator('.profile-menu summary').isVisible()) await activate(page.locator('.profile-menu summary'), isMobile)
    await activate(page.getByRole('button', { name: 'Upcoming Sessions', exact: true }), isMobile)
  }
  await page.reload(); await waitForPortal(page)
  const rows = page.locator('.open-session-row')
  await expect(rows).toHaveCount(2)
  await expect(rows.first()).toContainText('Date/time not set')
  await expect(rows.first()).toContainText('Open session')
  await expect(rows.first()).not.toContainText('Session 1 /')
  await activate(rows.first().getByRole('button', { name: /View/ }), isMobile)
  await expect(page).toHaveURL(/sessions\/undo-s1$/)
  await activate(page.getByRole('button', { name: 'Change ad-hoc date/time', exact: true }), isMobile)
  const owner = actor === 'u-owner'
  const dateLabel = owner ? 'Session date' : 'Requested session date'
  await activate(page.getByLabel(dateLabel, { exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: `${dateLabel} calendar`, exact: true }).getByRole('button', { name: '13 Oct 2026', exact: true }), isMobile)
  await page.getByLabel(owner ? 'Session start time' : 'Requested start time', { exact: true }).fill('13:00')
  await page.getByLabel(owner ? 'Session end time' : 'Requested end time', { exact: true }).fill('14:00')
  await activate(page.getByRole('button', { name: owner ? 'Save' : 'Review Request', exact: true }), isMobile)
  await activate(page.getByRole('dialog', { name: owner ? 'Save session details?' : 'Submit time-change request?', exact: true }).getByRole('button', { name: owner ? 'Save Changes' : 'Submit Request', exact: true }), isMobile)
  await expect.poll(async () => (await read(page)).sessions[0].scheduleState).toBe('scheduled')
  const after = await read(page)
  expect(after.sessions[0]).toMatchObject({ id: 'undo-s1', date: '2026-10-13', sessionNumber: 1 })
  expect(after.sessions[1]).toMatchObject({ scheduleState: 'open', sessionNumber: null })
  expect(after.clients).toEqual(open.clients)
  expect(after.packageCreditTransactions).toEqual(open.packageCreditTransactions)
  await page.goto('/#/sessions'); await waitForPortal(page); await page.reload(); await waitForPortal(page)
  await expect(page.locator('.open-session-row')).toHaveCount(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
})
