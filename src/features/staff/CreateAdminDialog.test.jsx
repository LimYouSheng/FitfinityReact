import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import CreateAdminDialog from './CreateAdminDialog.jsx'
import { createAdminCreationState } from '../../app/adminOnboarding.js'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from '../../components/EditGuardProvider.jsx'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
function show(onCreate, onClose = vi.fn()) {
  render(<ActionConfirmationProvider><EditGuardProvider><CreateAdminDialog creation={createAdminCreationState("owner")} today="2026-09-24" realAuthentication onCreate={onCreate} onClose={onClose} /></EditGuardProvider></ActionConfirmationProvider>)
}
function fill() {
  for (const [label, value] of [['Staff name', 'New Staff'], ['Staff email', ' STAFF@EXAMPLE.TEST '], ['Staff phone number', '91234567'], ['Staff birthday', '1990-01-02'], ['Staff gender', 'Female']]) fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } })
}
it('protects the draft as soon as the edited field is committed, before deferred effects can run', async () => {
  function GuardStatus() {
    const { activeEdit } = useEditGuard()
    return <output aria-label="Active edit">{activeEdit ?? 'none'}</output>
  }
  render(<ActionConfirmationProvider><EditGuardProvider>
    <CreateAdminDialog creation={createAdminCreationState("owner")} today="2026-09-24" onCreate={vi.fn()} onClose={vi.fn()} />
    <GuardStatus />
  </EditGuardProvider></ActionConfirmationProvider>)
  const field = screen.getByLabelText('Staff name')
  const status = screen.getByLabelText('Active edit')
  // Native input and a DOM observer retain the browser's commit boundary.
  // RTL's act wrapper would flush passive effects and hide this timing gap.
  const previousActEnvironment = globalThis.IS_REACT_ACT_ENVIRONMENT
  globalThis.IS_REACT_ACT_ENVIRONMENT = false
  let observer
  try {
    const atCommit = new Promise(resolve => {
      observer = new MutationObserver(() => {
        if (field.getAttribute('value') !== 'Unsaved staff') return
        observer.disconnect()
        resolve(status.textContent)
      })
      observer.observe(field, { attributes: true, attributeFilter: ['value'] })
    })
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, 'Unsaved staff')
    field.dispatchEvent(new Event('input', { bubbles: true }))
    expect(await atCommit).toBe('New Admin')
  } finally {
    observer?.disconnect()
    globalThis.IS_REACT_ACT_ENVIRONMENT = previousActEnvironment
  }
})
it('requires the five personal details, defaults to +65 and omits every trainer-specific input', async () => {
  const create = vi.fn()
  show(create)
  expect(screen.getByLabelText('Staff phone country code')).toHaveValue('+65')
  for (const label of ['Trainer type', 'Qualifications', 'Public profile', 'Peak rate', 'Off-peak rate']) expect(screen.queryByLabelText(label)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await waitFor(() => expect(screen.getByLabelText('Staff name')).toHaveAttribute('aria-invalid', 'true'))
  expect(create).not.toHaveBeenCalled()
})
it('submits normalized details once and reports the requested email without exposing credentials', async () => {
  let finish
  const create = vi.fn(() => new Promise(resolve => { finish = resolve }))
  show(create); fill()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  fireEvent.submit(screen.getByLabelText('Staff name').closest('form'))
  expect(create).toHaveBeenCalledTimes(1)
  expect(create.mock.calls[0][0]).toEqual({ name: 'New Staff', email: 'staff@example.test', phone_country_code: '+65', phone_number: '91234567', birthday: '1990-01-02', gender: 'Female' })
  expect(screen.getByLabelText('Staff name')).toBeDisabled()
  finish({ id: crypto.randomUUID(), name: 'New Staff', email: 'staff@example.test', role: 'admin', invitation: 'sent' })
  await screen.findByText(/invitation email was requested/)
  expect(screen.getByRole('button', { name: 'Done' })).toBeVisible()
  expect(screen.queryByLabelText('Staff name')).not.toBeInTheDocument()
})
it('retains the exact key and frozen details after an interrupted response', async () => {
  const create = vi.fn().mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValueOnce({ name: 'New Staff', email: 'staff@example.test', invitation: 'unknown' })
  show(create); fill()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByText('Connection interrupted')
  expect(screen.getByLabelText('Staff email')).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Check Account Setup' }))
  await screen.findByText(/Invitation delivery is not confirmed/)
  expect(create.mock.calls[1]).toEqual(create.mock.calls[0])
})
it('allows correction of a duplicate email rejected before creation', async () => {
  const create = vi.fn().mockRejectedValue(Object.assign(new Error('Email already exists'), { code: 'STAFF_EMAIL_EXISTS' }))
  show(create); fill()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByText('Email already exists')
  expect(screen.getByLabelText('Staff email')).not.toBeDisabled()
})
it('creates a valid request ID when HTTP preview has getRandomValues but no randomUUID', async () => {
  const browserCrypto = globalThis.crypto
  vi.stubGlobal('crypto', { getRandomValues: browserCrypto.getRandomValues.bind(browserCrypto) })
  const create = vi.fn().mockResolvedValue({ name: 'New Staff', email: 'staff@example.test', invitation: 'demo' })
  show(create); fill()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByText('This is a demo account. No email was sent.')
  expect(create).toHaveBeenCalledTimes(1)
  expect(create.mock.calls[0][1]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  expect(screen.queryByRole('button', { name: 'Creating…' })).not.toBeInTheDocument()
})
it('recovers from a local ID-generation failure without sending a request or freezing the form', async () => {
  const browserCrypto = globalThis.crypto
  const random = vi.fn().mockImplementationOnce(() => { throw new Error('Secure random source unavailable. Try again.') }).mockImplementation(browserCrypto.getRandomValues.bind(browserCrypto))
  vi.stubGlobal('crypto', { getRandomValues: random })
  const create = vi.fn().mockResolvedValue({ name: 'New Staff', email: 'staff@example.test', invitation: 'demo' })
  show(create); fill()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByRole('alert')
  expect(create).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Staff email')).not.toBeDisabled()
  expect(screen.getByLabelText('Staff name')).toHaveValue('New Staff')
  expect(screen.getByRole('button', { name: 'Create Admin & Send Invitation' })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Create Admin & Send Invitation' }))
  await screen.findByText('This is a demo account. No email was sent.')
  expect(create).toHaveBeenCalledTimes(1)
})
