import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { ActionConfirmationProvider } from './components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from './components/EditGuardProvider.jsx'
import { NotificationProvider } from './components/NotificationProvider.jsx'
import { createConfiguredPortalServices } from './services/defaultPortalServices.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from './test/api.js'
import { directoryData, directoryId } from './test/directory.js'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
function show(route = 'dashboard', data = directoryData()) {
  window.history.replaceState({}, '', `/#${route}`)
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  const state = { data, unavailable: false, signedIn: true }
  const fetchImpl = vi.fn(async url => {
    const path = new URL(url, 'https://api.example').pathname
    if (path === '/auth/policy') return jsonResponse(authPolicy)
    if (path === '/api/directory') return state.unavailable ? failure('service_unavailable', 503) : jsonResponse(state.data)
    if (path === '/auth/sign-out') { state.signedIn = false; return jsonResponse({ signedOut: true }) }
    if (path === '/me' || path === '/auth/session') return state.signedIn ? jsonResponse(sessionInfo()) : failure('SESSION_EXPIRED')
    throw new Error(`Unexpected path ${path}`)
  })
  const services = createConfiguredPortalServices({ mode: 'api', baseUrl: 'https://api.example', fetchImpl })
  render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider><App services={services} /></EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
  return state
}
function tab(label) {
  const menu = document.querySelector('details.profile-menu')
  menu?.setAttribute('open', '')
  fireEvent.click(within(menu).getByRole('button', { name: label, exact: true }))
}
it('shows real client/package details through existing pages and preserves Back navigation', async () => {
  show()
  await screen.findByRole('heading', { name: 'Your account' })
  fireEvent.click(screen.getByRole('button', { name: 'View Clients' }))
  await screen.findByRole('heading', { name: 'Clients', exact: true })
  expect(screen.queryByRole('button', { name: 'Add New Client' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'View API Client' }))
  await screen.findByRole('heading', { name: 'General Information' })
  expect(screen.getByText('client@fixture.test')).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Health & Assessments' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit', exact: true })).not.toBeInTheDocument()
  tab('Package')
  expect(screen.getByText('Purchased Twelve')).toBeVisible()
  expect(screen.getByLabelText('25% package used')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Add Package' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Back', exact: true }))
  await screen.findByRole('heading', { name: 'Clients', exact: true })
})
it('shows real trainer availability and template details without enabling mutations', async () => {
  show(`trainers/${directoryId(1)}`)
  await screen.findByRole('heading', { name: 'API Trainer' })
  expect(screen.getByText('$80 / session')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Edit', exact: true })).not.toBeInTheDocument()
  tab('Availability')
  expect(screen.getByText('10:00am–11:00am')).toBeVisible()
  await act(async () => { window.location.hash = `packages/${directoryId(5)}` })
  await screen.findByRole('heading', { name: 'Current Template' })
  expect(screen.getByText('180 days')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Edit Package' })).not.toBeInTheDocument()
})
it('handles no current package and removes private directory data on a failed refresh', async () => {
  const raw = directoryData(); raw.clients[0].purchases = []
  const state = show(`clients/${directoryId(7)}`, raw)
  await screen.findByRole('heading', { name: 'API Client' })
  tab('Package')
  expect(screen.getByText('No active current package.')).toBeVisible()
  state.unavailable = true
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  await screen.findByRole('heading', { name: 'Unable to load the portal' })
  expect(screen.queryByText('API Client')).not.toBeInTheDocument()
  state.unavailable = false
  fireEvent.click(screen.getByRole('button', { name: 'Retry', exact: true }))
  await screen.findByRole('heading', { name: 'API Client' })
})
it('rejects a direct route to an unavailable write workflow', async () => {
  show('clients/new')
  await screen.findByText('This workflow is not available yet.')
  expect(screen.queryByRole('button', { name: 'Save Client' })).not.toBeInTheDocument()
})

it.each([[true, 'Visible'], [false, 'Hidden']])('renders API public_profile=%s using the canonical visibility value', async (visible, expected) => {
  const raw = directoryData(); raw.trainers[0].public_profile = visible
  show(`trainers/${directoryId(1)}`, raw)
  await screen.findByRole('heading', { name: 'API Trainer' })
  const label = screen.getByText('Public profile', { selector: '.info-row span' })
  expect(label.parentElement.querySelector('strong')).toHaveTextContent(expected)
})
