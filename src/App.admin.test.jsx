import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import App from './App.jsx'
import { ActionConfirmationProvider } from './components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from './components/EditGuardProvider.jsx'
import { NotificationProvider } from './components/NotificationProvider.jsx'
import { mockDb } from './services/mockDb.js'
import { MOCK_SESSION_KEY } from './services/authService.js'
import { createConfiguredPortalServices } from './services/defaultPortalServices.js'
import { directoryData, directoryId } from './test/directory.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from './test/api.js'

beforeEach(() => {
  localStorage.clear(); mockDb.reset()
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
function show(route = 'dashboard', { admin = false, services } = {}) {
  window.history.replaceState({}, '', `/#${route}`)
  if (admin) mockDb.mutate(db => { db.users.push({ id: 'test-admin', name: 'Operations Admin', email: 'admin@example.test', role: 'admin', status: 'active' }) })
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: admin ? 'test-admin' : 'u-owner', expiresAt: Date.now() + 3600000 }))
  render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider><App services={services} /></EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
}
it('places Create Admin first in the Owner popup, opens personal details and returns through Back', async () => {
  // This journey checks real routing and permissions, not simulated transport latency.
  vi.spyOn(await import('./services/mockDb.js'), 'delay').mockResolvedValue()
  await act(async () => { show() })
  await waitFor(() => expect(document.querySelector('main.content .page-head h1')).toHaveTextContent('Owner Dashboard'))
  expect(within(document.querySelector('main.content .page-head')).getByRole('heading', { name: 'Owner Dashboard' })).toBeVisible()
  fireEvent.click(within(document.querySelector('.topbar')).getByRole('button', { name: 'Open profile menu' }))
  const menu = screen.getByRole('menu', { name: 'Profile menu' })
  expect(within(menu).getAllByRole('menuitem')[0]).toHaveTextContent('Create Admin')
  await act(async () => { fireEvent.click(within(menu).getByRole('menuitem', { name: 'Create Admin' })) })
  const dialog = screen.getByRole('dialog', { name: 'Create Admin' })
  expect(within(dialog).getByLabelText('Staff name')).toBeVisible()
  await act(async () => { history.back() })
  // Native Back is asynchronous. Wait for its destination and the rendered page
  // before calculating accessible names, or finishing with traversal still queued.
  await waitFor(() => {
    expect(location.hash).toBe('#dashboard')
    expect(document.querySelector('main.content .page-head h1')).toHaveTextContent('Owner Dashboard')
    expect(dialog).not.toBeInTheDocument()
  })
  expect(within(document.querySelector('main.content .page-head')).getByRole('heading', { name: 'Owner Dashboard' })).toBeVisible()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
it('guards a dirty Admin form through native Back and Cancel without losing its draft or history entry', async () => {
  show()
  await screen.findByRole('heading', { name: 'Owner Dashboard' })
  fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Create Admin' }))
  await screen.findByRole('dialog', { name: 'Create Admin' })
  fireEvent.change(screen.getByLabelText('Staff name'), { target: { value: 'Unsaved staff' } })
  await act(async () => { history.back() })
  const nativeLeave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  expect(location.hash).toBe('#/owner-profile/create-admin')
  expect(history.state.fitfinityDepth).toBe(1)
  await act(async () => { fireEvent.click(within(nativeLeave).getByRole('button', { name: 'Cancel' })) })
  expect(screen.getByLabelText('Staff name')).toHaveValue('Unsaved staff')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
  const leave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  await act(async () => { fireEvent.click(within(leave).getByRole('button', { name: 'Cancel' })) })
  expect(screen.getByLabelText('Staff name')).toHaveValue('Unsaved staff')
  await act(async () => { history.back() })
  const confirmedLeave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  await act(async () => { fireEvent.click(within(confirmedLeave).getByRole('button', { name: 'Leave Without Saving' })) })
  await screen.findByRole('heading', { name: 'Owner Dashboard' })
  expect(history.state.fitfinityDepth).toBe(0)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
it('gives Admin operational trainer access without rates, remuneration or privileged menu actions', async () => {
  show('trainers/t1', { admin: true })
  await screen.findByRole('heading', { name: 'Marcus Tan' })
  expect(screen.queryByRole('heading', { name: 'Training & Rates' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'Edit', exact: true }).length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: 'Remuneration', includeHidden: true })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
  expect(screen.queryByRole('menuitem', { name: 'Create Admin' })).not.toBeInTheDocument()
  await act(async () => { location.hash = 'remuneration' })
  await screen.findByText('Remuneration is unavailable for this account.')
  await act(async () => { location.hash = 'owner-profile/create-admin' })
  await screen.findByText('This profile is available to the owner.')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
it('lets Admin finish Add Trainer without a rate step, rate review or rate inputs', async () => {
  // This UI contract uses the real services, identity and storage; artificial
  // demo latency is covered separately and must not drive transition polling.
  vi.spyOn(await import('./services/mockDb.js'), 'delay').mockResolvedValue()
  HTMLElement.prototype.scrollIntoView = vi.fn()
  await act(async () => { show('trainers/new', { admin: true }) })
  const content = within(document.querySelector('main.content'))
  await content.findByRole('heading', { name: 'Add New Trainer' })
  const form = within(content.getByRole('form', { name: 'Trainer creation' }))
  for (const [label, value] of [['Trainer name', 'Admin Created Coach'], ['Trainer email', 'admin-coach@example.test'], ['Trainer phone number', '91234567'], ['Trainer birthday', '1990-01-02'], ['Trainer gender', 'Female'], ['Trainer type', 'Personal']]) {
    fireEvent.change(form.getByLabelText(label, { exact: true }), { target: { value } })
  }
  expect(form.getByLabelText('Creation progress')).toHaveTextContent('Step 1 of 4')
  expect(screen.queryByLabelText(/session rate/)).not.toBeInTheDocument()
  fireEvent.click(form.getByRole('button', { name: 'Continue to Trainer Availability' }))
  fireEvent.click(await form.findByRole('button', { name: 'Sunday', exact: true }))
  fireEvent.click(form.getByRole('button', { name: 'Add Time', exact: true }))
  fireEvent.click(form.getByRole('button', { name: 'Continue to Owner Approval Needed' }))
  fireEvent.click(form.getByRole('button', { name: 'Continue to Review & Confirm' }))
  await form.findByRole('heading', { name: 'Review & Confirm', exact: true })
  expect(screen.queryByText('Training & Rates', { exact: true })).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/session rate/)).not.toBeInTheDocument()
  fireEvent.click(form.getByRole('button', { name: 'Create Trainer', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'Create Admin Created Coach?' })
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Create Trainer' })) })
  await content.findByRole('heading', { name: 'Admin Created Coach', exact: true })
  expect(screen.queryByRole('heading', { name: 'Training & Rates' })).not.toBeInTheDocument()
  const state = mockDb.read()
  expect(state.trainers.find(row => row.email === 'admin-coach@example.test').rates).toEqual(state.settings.trainerRates)
})
it('opens the demo Admin profile from its menu and returns to the previous trainer through Back', async () => {
  show('trainers/t1', { admin: true })
  await screen.findByRole('heading', { name: 'Marcus Tan' })
  fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'My Profile' }))
  await screen.findByRole('heading', { name: 'Operations Admin', exact: true })
  expect(screen.getByText('Operations Admin', { exact: true, selector: '.info-row strong' })).toBeVisible()
  expect(screen.getByText('admin@example.test', { exact: true })).toBeVisible()
  expect(screen.getByText('Admin', { exact: true, selector: '.info-row strong' })).toBeVisible()
  expect(screen.queryByText(/Changes and other workflows will be available/)).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Page unavailable' })).not.toBeInTheDocument()
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  await act(async () => { history.back() })
  await screen.findByRole('heading', { name: 'Marcus Tan' })
})
it('loads the demo Admin account directly and returns there from password settings', async () => {
  show('account', { admin: true })
  await screen.findByRole('heading', { name: 'Operations Admin', exact: true })
  expect(screen.getByText('admin@example.test', { exact: true })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Remuneration', includeHidden: true })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Change Password', exact: true }))
  await screen.findByRole('heading', { name: 'Change Password' })
  await act(async () => { history.back() })
  await screen.findByRole('heading', { name: 'Operations Admin', exact: true })
  expect(screen.getByText('Admin', { exact: true, selector: '.info-row strong' })).toBeVisible()
})
it('renders the live Admin directory without expecting hidden rate fields or enabling demo workflows', async () => {
  const raw = directoryData()
  delete raw.trainers[0].peak_rate_cents; delete raw.trainers[0].off_peak_rate_cents
  const fetchImpl = vi.fn(async url => jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? raw : { ...sessionInfo(), user: { ...sessionInfo().user, role: 'admin' } }))
  const services = createConfiguredPortalServices({ mode: 'api', baseUrl: 'https://api.example', fetchImpl })
  show(`trainers/${directoryId(1)}`, { services })
  await screen.findByRole('heading', { name: 'API Trainer' })
  expect(screen.queryByText(/\/ session/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit', exact: true })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Demo account')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'My Profile' }))
  await screen.findByRole('heading', { name: 'Owner', exact: true })
  expect(screen.getByText('Admin', { exact: true, selector: '.info-row strong' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Account', exact: true })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Home', exact: true }))
  await screen.findByRole('heading', { name: 'Your account', exact: true })
  expect(screen.getByText(/Changes and other workflows will be available/)).toBeVisible()
})


function recoveryApp(route = 'owner-profile/create-admin') {
  const state = { unavailable: false, token: sessionInfo().csrfToken, user: sessionInfo().user, posts: [], post: async () => { throw new Error('Interrupted response') } }
  const fetchImpl = vi.fn(async (url, request) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me') || url.endsWith('/auth/session')) return state.session ? state.session() : state.user ? jsonResponse({ ...sessionInfo(), user: state.user, csrfToken: state.token }) : failure('SESSION_EXPIRED')
    if (url.endsWith('/auth/sign-out')) { state.user = null; return jsonResponse({ signedOut: true }) }
    if (url.endsWith('/api/directory')) {
      if (state.directoryRead) return state.directoryRead()
      const raw = directoryData(); raw.viewerId = state.user.id
      if (state.user.role === 'admin') for (const trainer of raw.trainers) { delete trainer.peak_rate_cents; delete trainer.off_peak_rate_cents }
      return state.unavailable ? failure('service_unavailable', 503) : jsonResponse(raw)
    }
    if (url.endsWith('/api/staff/admins')) { state.posts.push(request); return state.post() }
    throw new Error(`Unexpected request: ${url}`)
  })
  show(route, { services: createConfiguredPortalServices({ mode: 'api', baseUrl: 'https://api.example', fetchImpl }) })
  return state
}
function fillRecoveryAdmin() {
  for (const [label, value] of [['Staff name', 'Recovery Staff'], ['Staff email', 'recovery@example.test'], ['Staff phone number', '91234567'], ['Staff birthday', '1990-01-02'], ['Staff gender', 'Female']]) {
    fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } })
  }
}
const createdAdminResponse = () => jsonResponse({ id: directoryId(88), role: 'admin', name: 'Recovery Staff', email: 'recovery@example.test', invitation: 'sent' })
async function outage(state, event = 'focus') {
  state.unavailable = true
  await act(async () => { window.dispatchEvent(new Event(event)) })
  await screen.findByRole('heading', { name: 'Unable to load the portal' })
  expect(screen.queryByLabelText('Staff name')).not.toBeInTheDocument()
  expect(screen.queryByText('API Client')).not.toBeInTheDocument()
}
async function recover(state) {
  state.unavailable = false
  fireEvent.click(screen.getByRole('button', { name: 'Retry', exact: true }))
  await screen.findByRole('dialog', { name: 'Create Admin' })
}
it.each(['focus', 'storage'])('recovers an unsaved Admin draft after a %s refresh outage and re-verifies its Owner', async event => {
  const state = recoveryApp()
  await screen.findByRole('dialog', { name: 'Create Admin' })
  fireEvent.change(screen.getByLabelText('Staff name'), { target: { value: 'Unsaved Admin' } })
  await outage(state, event)
  expect(screen.getByText(/Your Admin setup progress is retained/)).toBeVisible()
  const leaving = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(leaving)
  expect(leaving.defaultPrevented).toBe(true)
  await recover(state)
  expect(screen.getByLabelText('Staff name')).toHaveValue('Unsaved Admin')
  expect(state.posts).toHaveLength(0)
})
it('reconciles an ambiguous Admin POST with its original frozen payload and key after a directory outage', async () => {
  const state = recoveryApp()
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByText('The response was interrupted. Check the current state before trying again.')
  await outage(state); await recover(state)
  expect(screen.getByLabelText('Staff email')).toBeDisabled()
  expect(screen.getByLabelText('Staff email')).toHaveValue('recovery@example.test')
  state.post = async () => createdAdminResponse()
  fireEvent.click(screen.getByRole('button', { name: 'Check Account Setup' }))
  await screen.findByText(/has been created as an Admin/)
  expect(state.posts).toHaveLength(2)
  expect(state.posts[1].body).toBe(state.posts[0].body)
  expect(state.posts[1].headers['Idempotency-Key']).toBe(state.posts[0].headers['Idempotency-Key'])
})
it('recovers a confirmed Admin result after its follow-up directory read fails without another POST', async () => {
  const state = recoveryApp()
  state.post = async () => { state.unavailable = true; return createdAdminResponse() }
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByRole('heading', { name: 'Unable to load the portal' })
  await recover(state)
  await screen.findByText(/has been created as an Admin/)
  expect(screen.getByRole('button', { name: 'Done' })).toBeVisible()
  expect(state.posts).toHaveLength(1)
})
it('keeps an in-flight Admin request busy across an outage and accepts its later success once', async () => {
  const state = recoveryApp(); let finish
  state.post = () => new Promise(resolve => { finish = resolve })
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await waitFor(() => expect(state.posts).toHaveLength(1))
  await outage(state); await recover(state)
  expect(screen.getByRole('button', { name: 'Creating…' })).toBeDisabled()
  fireEvent.submit(screen.getByLabelText('Staff name').closest('form'))
  await act(async () => { finish(createdAdminResponse()) })
  await screen.findByText(/has been created as an Admin/)
  expect(state.posts).toHaveLength(1)
})
it.each(['different Owner', 'lost Owner role', 'expired session'])('discards Admin recovery on %s and never restores it when the old Owner returns', async transition => {
  const state = recoveryApp(), original = state.user
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  await outage(state)
  state.user = transition === 'different Owner' ? { ...original, id: directoryId(99) } : transition === 'lost Owner role' ? { ...original, role: 'admin' } : null
  state.unavailable = false
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry', exact: true })) })
  await waitFor(() => expect(screen.queryByRole('heading', { name: 'Unable to load the portal' })).not.toBeInTheDocument())
  if (transition === 'different Owner') {
    await act(async () => { location.hash = 'owner-profile/create-admin' })
    expect(await screen.findByLabelText('Staff name')).toHaveValue('')
  } else expect(screen.queryByLabelText('Staff name')).not.toBeInTheDocument()
  state.user = original
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  await waitFor(() => {
    expect(document.querySelector('.portal-shell')).toHaveAttribute('data-user-id', original.id)
    expect(document.querySelector('.role-chip')).toHaveTextContent(/Owner/i)
  })
  await act(async () => { location.hash = 'owner-profile/create-admin' })
  await waitFor(() => expect(screen.getByLabelText('Staff name')).toHaveValue(''))
})
it('invalidates a forbidden creation attempt and requires a fresh verified Owner workflow', async () => {
  const state = recoveryApp()
  state.post = async () => failure('forbidden', 403)
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByRole('heading', { name: 'Unable to load the portal' })
  await recover(state)
  expect(screen.getByLabelText('Staff name')).toHaveValue('')
  expect(screen.getByLabelText('Staff email')).toBeEnabled()
})
it('ignores a late Admin response after sign-out and cannot revive it for a later sign-in', async () => {
  const state = recoveryApp(), original = state.user; let finish
  state.post = () => new Promise(resolve => { finish = resolve })
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await waitFor(() => expect(state.posts).toHaveLength(1))
  fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Sign Out' }))
  const leave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  await act(async () => { fireEvent.click(within(leave).getByRole('button', { name: 'Leave Without Saving' })) })
  await act(async () => { finish(createdAdminResponse()) })
  expect(screen.queryByText(/has been created as an Admin/)).not.toBeInTheDocument()
  state.user = original
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  await waitFor(() => {
    expect(document.querySelector('.portal-shell')).toHaveAttribute('data-user-id', original.id)
    expect(document.querySelector('.role-chip')).toHaveTextContent(/Owner/i)
  })
  await act(async () => { location.hash = 'owner-profile/create-admin' })
  expect(await screen.findByLabelText('Staff name')).toHaveValue('')
})

it('blocks invalid optional client contacts before the normal Save confirmation and persistence', async () => {
  show('clients/c1')
  const heading = await screen.findByRole('heading', { name: 'General Information' })
  const panel = within(heading.closest('section')), before = mockDb.read()
  fireEvent.click(panel.getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(screen.getByLabelText('Client email'), { target: { value: 'not-an-email' } })
  fireEvent.change(screen.getByLabelText('Client phone number'), { target: { value: 'letters-only' } })
  fireEvent.click(panel.getByRole('button', { name: 'Save', exact: true }))
  expect(screen.getByLabelText('Client email')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByLabelText('Client phone number')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.queryByRole('dialog', { name: 'Save client information?' })).not.toBeInTheDocument()
  expect(mockDb.reload()).toEqual(before)
})

it.each(['different Owner', 'lost Owner role'])('retires Admin recovery on %s even while the directory remains unavailable', async transition => {
  const state = recoveryApp(), original = state.user
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  await outage(state)
  state.user = transition === 'different Owner' ? { ...original, id: directoryId(99) } : { ...original, role: 'admin' }
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  await waitFor(() => expect(screen.queryByText(/Your Admin setup progress is retained/)).not.toBeInTheDocument())
  state.user = original
  await recover(state)
  expect(screen.getByLabelText('Staff name')).toHaveValue('')
})

async function openRecoveryAdmin() {
  await screen.findByRole('heading', { name: 'Your account' })
  fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Create Admin' }))
  await screen.findByRole('dialog', { name: 'Create Admin' })
}
it.each(['draft', 'uncertain POST'])('guards native Back during an outage and preserves the %s after Cancel and Retry', async stage => {
  const state = recoveryApp('dashboard'); await openRecoveryAdmin(); fillRecoveryAdmin()
  if (stage === 'uncertain POST') {
    fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
    await screen.findByText('The response was interrupted. Check the current state before trying again.')
  }
  await outage(state)
  await act(async () => { history.back() })
  const leave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  expect(location.hash).toBe('#/owner-profile/create-admin')
  expect(history.state.fitfinityDepth).toBe(1)
  // Recovery while the prompt is open must retain the same history transaction.
  await recover(state)
  await act(async () => { fireEvent.click(within(leave).getByRole('button', { name: 'Cancel' })) })
  expect(screen.getByLabelText('Staff name')).toHaveValue('Recovery Staff')
  if (stage === 'uncertain POST') {
    state.post = async () => createdAdminResponse()
    fireEvent.click(screen.getByRole('button', { name: 'Check Account Setup' }))
    await screen.findByText(/has been created as an Admin/)
    expect(state.posts).toHaveLength(2)
    expect(state.posts[1].body).toBe(state.posts[0].body)
    expect(state.posts[1].headers['Idempotency-Key']).toBe(state.posts[0].headers['Idempotency-Key'])
  }
})
it('explicitly discards an outage draft through Back, preserves Forward, and guards Forward and direct hash edits', async () => {
  const state = recoveryApp('dashboard'); await openRecoveryAdmin(); fillRecoveryAdmin()
  // Add a real forward destination, then return to the empty form before editing again.
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
  let leave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  await act(async () => { fireEvent.click(within(leave).getByRole('button', { name: 'Leave Without Saving' })) })
  await screen.findByRole('heading', { name: 'Your account' })
  await act(async () => { history.forward() })
  await screen.findByRole('dialog', { name: 'Create Admin' })
  await act(async () => { location.hash = 'account' })
  await screen.findByRole('heading', { name: 'Owner', exact: true })
  await act(async () => { history.back() })
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  await outage(state)
  for (const traverse of [() => history.forward(), () => { location.hash = 'clients' }]) {
    await act(async () => { traverse() })
    leave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
    await act(async () => { fireEvent.click(within(leave).getByRole('button', { name: 'Cancel' })) })
    expect(location.hash).toBe('#/owner-profile/create-admin')
  }
  await act(async () => { history.back() })
  leave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  await act(async () => { fireEvent.click(within(leave).getByRole('button', { name: 'Leave Without Saving' })) })
  await waitFor(() => expect(location.hash).toBe('#dashboard'))
  expect(screen.queryByText(/Your Admin setup progress is retained/)).not.toBeInTheDocument()
  await act(async () => { history.forward() })
  await waitFor(() => expect(location.hash).toBe('#/owner-profile/create-admin'))
  await recover(state)
  expect(screen.getByLabelText('Staff name')).toHaveValue('')
})
it.each(['same Owner', 'different Admin'])('keeps a newer verified %s login when an old Admin request expires', async mode => {
  const state = recoveryApp(); let finish
  state.post = () => new Promise(resolve => { finish = resolve })
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await waitFor(() => expect(state.posts).toHaveLength(1))
  state.token = 'b'.repeat(64)
  if (mode === 'different Admin') state.user = { ...state.user, id: directoryId(91), role: 'admin', name: 'New Admin' }
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  await waitFor(() => expect(document.querySelector('.portal-shell')).toHaveAttribute('data-user-id', state.user.id))
  if (mode === 'same Owner') {
    await waitFor(() => expect(screen.getByLabelText('Staff name')).toHaveValue(''))
    fireEvent.change(screen.getByLabelText('Staff name'), { target: { value: 'New session draft' } })
  }
  await act(async () => { finish(failure('SESSION_EXPIRED')) })
  expect(document.querySelector('.portal-shell')).toHaveAttribute('data-user-id', state.user.id)
  expect(screen.queryByRole('heading', { name: 'Sign In' })).not.toBeInTheDocument()
  if (mode === 'same Owner') expect(screen.getByLabelText('Staff name')).toHaveValue('New session draft')
  expect(state.posts).toHaveLength(1)
})
it('still ends the current login on a genuine terminal Admin request expiry', async () => {
  const state = recoveryApp()
  state.post = async () => { state.user = null; return failure('SESSION_EXPIRED') }
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await waitFor(() => expect(document.querySelector('.portal-shell')).toBeNull())
  expect(screen.queryByText(/Your Admin setup progress is retained/)).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Staff name')).not.toBeInTheDocument()
})

it.each(['before submit', 'during preflight', 'directory pending', 'directory failed', 'role changed'])('does not submit an old Admin draft when the session changes %s', async timing => {
  const state = recoveryApp()
  state.post = createdAdminResponse
  await screen.findByRole('dialog', { name: 'Create Admin' }); fillRecoveryAdmin()
  let release, entered = false
  if (timing === 'during preflight') {
    state.session = () => { entered = true; state.session = null; return new Promise(resolve => { release = resolve }) }
    fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
    await waitFor(() => expect(entered).toBe(true))
  }
  state.token = 'b'.repeat(64)
  if (timing === 'role changed') state.user = { ...state.user, id: directoryId(92), role: 'admin', name: 'Replacement Admin' }
  if (timing.startsWith('directory')) {
    state.directoryRead = () => { entered = true; return new Promise(resolve => { release = resolve }) }
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    await waitFor(() => expect(entered).toBe(true))
  }
  if (timing === 'during preflight') {
    await act(async () => { release(jsonResponse({ ...sessionInfo(), csrfToken: state.token })) })
  } else {
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' })) })
  }
  if (timing.startsWith('directory')) {
    state.directoryRead = null
    await act(async () => { release(timing === 'directory failed' ? failure('service_unavailable', 503) : jsonResponse(directoryData())) })
  }
  if (timing === 'directory failed') {
    await screen.findByRole('heading', { name: 'Unable to load the portal' })
    expect(screen.queryByText(/Your Admin setup progress is retained/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry', exact: true }))
  }
  if (timing === 'role changed') {
    await waitFor(() => expect(document.querySelector('.portal-shell')).toHaveAttribute('data-user-id', state.user.id))
    expect(screen.queryByLabelText('Staff name')).not.toBeInTheDocument()
  } else {
    await waitFor(() => expect(screen.getByLabelText('Staff name')).toHaveValue(''))
  }
  expect(state.posts).toHaveLength(0)
  if (timing === 'before submit') {
    fillRecoveryAdmin()
    fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
    await screen.findByText(/has been created as an Admin/)
    expect(state.posts).toHaveLength(1)
    expect(state.posts[0].headers['X-CSRF-Token']).toBe(state.token)
  }
})
