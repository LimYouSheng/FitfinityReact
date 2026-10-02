import { emptyDirectory } from '../../test/directory.js'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import SignInPage from './SignInPage.jsx'
import App from '../../App.jsx'
import { createConfiguredPortalServices } from '../../services/defaultPortalServices.js'
import { NotificationProvider } from '../../components/NotificationProvider.jsx'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import { authPolicy, challenge, csrfToken, failure, jsonResponse, sessionInfo } from '../../test/api.js'

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
const fill = (name, value) => fireEvent.change(screen.getByLabelText(name), { target: { value } })
const credentials = () => { fill('Email', 'owner@example.test'); fill('Password', 'initial-password') }
const props = overrides => ({ policy: authPolicy.password, onSignIn: vi.fn().mockResolvedValue(challenge()), onChallenge: vi.fn().mockResolvedValue(sessionInfo()), onAuthenticated: vi.fn(), ...overrides })

it('requires the authenticator before loading the account and clears the password from the form', async () => {
  const actions = props()
  render(<SignInPage {...actions} />)
  credentials(); fireEvent.click(screen.getByRole('button', { name: 'Sign In', exact: true }))
  await screen.findByRole('heading', { name: 'Authenticator verification' })
  expect(actions.onAuthenticated).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  expect(screen.queryByText('Demo password:')).not.toBeInTheDocument()
  fill('Authenticator code', '123456'); fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  await waitFor(() => expect(actions.onAuthenticated).toHaveBeenCalledTimes(1))
  expect(actions.onChallenge).toHaveBeenCalledWith({ code: '123456' })
})
it('handles temporary password, strict policy and TOTP enrollment using the existing screen', async () => {
  const actions = props({ onSignIn: vi.fn().mockResolvedValue(challenge('NEW_PASSWORD_REQUIRED')), onChallenge: vi.fn().mockResolvedValueOnce(challenge('MFA_SETUP')).mockResolvedValueOnce(sessionInfo()) })
  render(<SignInPage {...actions} />)
  credentials(); fireEvent.click(screen.getByRole('button', { name: 'Sign In', exact: true }))
  await screen.findByRole('heading', { name: 'Choose a new password' })
  fill('New password', 'not allowed spaces'); fill('Confirm new password', 'not allowed spaces')
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(screen.getByRole('alert')).toHaveTextContent('without spaces')
  expect(actions.onChallenge).not.toHaveBeenCalled()
  fill('New password', 'long-lowercase-passphrase'); fill('Confirm new password', 'long-lowercase-passphrase')
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  await screen.findByRole('heading', { name: 'Set up your authenticator' })
  expect(screen.getByLabelText('Authenticator setup key')).toHaveTextContent('ABCDEFGHIJKLMNOP234567')
  fill('Authenticator code', '123456'); fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  await waitFor(() => expect(actions.onAuthenticated).toHaveBeenCalledTimes(1))
  expect(screen.queryByLabelText('Authenticator setup key')).not.toBeInTheDocument()
})
it('does not duplicate a pending sign-in and retains an invalid-code error for correction', async () => {
  let finish
  const actions = props({ onSignIn: vi.fn(() => new Promise(resolve => { finish = resolve })), onChallenge: vi.fn().mockRejectedValue(new Error('The code is incorrect.')) })
  render(<SignInPage {...actions} />)
  credentials()
  fireEvent.submit(screen.getByLabelText('Password').closest('form')); fireEvent.submit(screen.getByLabelText('Password').closest('form'))
  expect(actions.onSignIn).toHaveBeenCalledTimes(1)
  await act(async () => finish(challenge()))
  fill('Authenticator code', '123456'); fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('code is incorrect')
  expect(screen.getByLabelText('Authenticator code')).toHaveValue('123456')
})
it('expires the challenge and removes the enrollment secret', async () => {
  vi.useFakeTimers()
  const actions = props({ onSignIn: vi.fn().mockResolvedValue(challenge('MFA_SETUP')) })
  render(<SignInPage {...actions} />)
  credentials()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Sign In', exact: true })))
  expect(screen.getByLabelText('Authenticator setup key')).toBeInTheDocument()
  await act(async () => vi.advanceTimersByTime(300001))
  expect(screen.queryByLabelText('Authenticator setup key')).not.toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('expired')
  expect(screen.getByLabelText('Password')).toHaveValue('')
})
it('recovers by verified email and returns to sign-in without authenticating', async () => {
  const actions = props({ onForgotPassword: vi.fn().mockResolvedValue({ message: 'If eligible, check your email.' }), onResetPassword: vi.fn().mockResolvedValue({ signedOut: true }) })
  render(<SignInPage {...actions} />)
  fill('Email', 'owner@example.test'); fireEvent.click(screen.getByRole('button', { name: 'Forgot password?' }))
  fireEvent.click(screen.getByRole('button', { name: 'Send recovery code' }))
  await screen.findByRole('heading', { name: 'Enter recovery code' })
  fill('Recovery code', '987654'); fill('New password', 'recovered-separator-password'); fill('Confirm new password', 'recovered-separator-password')
  fireEvent.click(screen.getByRole('button', { name: 'Reset Password', exact: true }))
  await screen.findByRole('heading', { name: 'Sign in' })
  expect(actions.onResetPassword).toHaveBeenCalledWith({ code: '987654', newPassword: 'recovered-separator-password' })
  expect(actions.onAuthenticated).not.toHaveBeenCalled()
  expect(screen.getByRole('status')).toHaveTextContent('Password reset')
})
it('retries only account loading when MFA succeeded but the following read failed', async () => {
  const actions = props({ onAuthenticated: vi.fn().mockRejectedValueOnce(new Error('Temporary outage.')).mockResolvedValueOnce() })
  render(<SignInPage {...actions} />)
  credentials(); fireEvent.click(screen.getByRole('button', { name: 'Sign In', exact: true }))
  await screen.findByLabelText('Authenticator code')
  fill('Authenticator code', '123456'); fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading account' }))
  await waitFor(() => expect(actions.onAuthenticated).toHaveBeenCalledTimes(2))
  expect(actions.onChallenge).toHaveBeenCalledTimes(1)
})
it('mounts the real account boundary, signs out after password change and never loads demo records', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  window.history.replaceState({}, '', '/#dashboard')
  let signedIn = true
  const fetch = vi.fn(async (url, options) => {
    const path = new URL(url).pathname
    if (path === '/auth/policy') return jsonResponse(authPolicy)
    if (path === '/api/directory') return jsonResponse(emptyDirectory())
    if (path === '/me') return signedIn ? jsonResponse(sessionInfo()) : failure('SESSION_EXPIRED')
    if (path === '/auth/change-password') {
      expect(options.headers['X-CSRF-Token']).toBe(csrfToken)
      expect(JSON.parse(options.body)).toEqual({ currentPassword: 'old-password', newPassword: 'replacement-passphrase' })
      signedIn = false
      return jsonResponse({ passwordChanged: true, signedOut: true })
    }
    throw new Error(`Unexpected path ${path}`)
  })
  const services = createConfiguredPortalServices({ mode: 'api', baseUrl: 'https://api.example', fetchImpl: fetch })
  render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider><App services={services} /></EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
  await screen.findByRole('heading', { name: 'Your account' })
  expect(screen.queryByText('Reset Demo')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Change Password', exact: true }))
  await screen.findByLabelText('Current password')
  fill('Current password', 'old-password'); fill('New password', 'replacement-passphrase'); fill('Confirm new password', 'replacement-passphrase')
  fireEvent.click(screen.getByRole('button', { name: 'Save Password' }))
  await screen.findByRole('dialog')
  fireEvent.click(screen.getByRole('button', { name: 'Change Password', exact: true }))
  await screen.findByRole('heading', { name: 'Sign in' })
  expect(screen.queryByText('owner@example.test')).not.toBeInTheDocument()
})

it.each(['sign-out', 'change-password'])('preserves a replacement login and its new form after delayed %s completion', async operation => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  window.history.replaceState({}, '', '/#dashboard')
  let token = csrfToken, finish, started, directoryReads = 0
  const entered = new Promise(resolve => { started = resolve })
  const fetch = vi.fn(async url => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/api/directory')) { directoryReads++; return jsonResponse(emptyDirectory()) }
    if (url.endsWith(`/auth/${operation}`)) { started(); return new Promise(resolve => { finish = resolve }) }
    return jsonResponse({ ...sessionInfo(), csrfToken: token })
  })
  const services = createConfiguredPortalServices({ mode: 'api', baseUrl: 'https://api.example', fetchImpl: fetch })
  render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider><App services={services} /></EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
  await screen.findByRole('heading', { name: 'Your account' })
  if (operation === 'sign-out') fireEvent.click(screen.getByRole('button', { name: 'Sign Out', exact: true }))
  else {
    fireEvent.click(screen.getByRole('button', { name: 'Change Password', exact: true }))
    fill('Current password', 'old-password'); fill('New password', 'old-replacement-passphrase'); fill('Confirm new password', 'old-replacement-passphrase')
    fireEvent.click(screen.getByRole('button', { name: 'Save Password' }))
    await screen.findByRole('dialog')
    fireEvent.click(screen.getByRole('button', { name: 'Change Password', exact: true }))
  }
  await entered
  const reads = directoryReads
  token = 'b'.repeat(64)
  await act(async () => window.dispatchEvent(new Event('focus')))
  await waitFor(() => expect(directoryReads).toBeGreaterThan(reads))
  if (operation === 'sign-out') fireEvent.click(screen.getByRole('button', { name: 'Change Password', exact: true }))
  await waitFor(() => expect(screen.getByLabelText('Current password')).toHaveValue(''))
  expect(screen.getByLabelText('Current password')).toBeEnabled()
  fill('Current password', 'new-session-password'); fill('New password', 'new-session-passphrase'); fill('Confirm new password', 'new-session-passphrase')
  await act(async () => finish(jsonResponse({ signedOut: true })))
  expect(screen.getByLabelText('Current password')).toHaveValue('new-session-password')
  expect(screen.getByLabelText('New password')).toHaveValue('new-session-passphrase')
  expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith(`/auth/${operation}`))).toHaveLength(1)
})
