import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import OwnerProfilePage from './OwnerProfilePage.jsx'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'

const record = { id: 'owner', version: 1, name: 'Owner Original', email: 'owner@example.test', phone_country_code: '+65', phone_number: '91234567', birthday: '1990-01-02', gender: 'Other' }
afterEach(cleanup)
function show(saveProfile) {
  const onSaved = vi.fn().mockResolvedValue(undefined)
  render(<ActionConfirmationProvider><EditGuardProvider><OwnerProfilePage user={{ id: 'owner', role: 'owner', name: record.name }} services={{ ownerService: { getProfile: vi.fn().mockResolvedValue(record), saveProfile } }} today="2026-11-27" onSaved={onSaved} /></EditGuardProvider></ActionConfirmationProvider>)
  return onSaved
}

it('uses shared contact fields and saves the reviewed version while keeping email read-only', async () => {
  const save = vi.fn(async input => ({ ...record, ...input.details, version: 2 }))
  const onSaved = show(save)
  await userEvent.click(await screen.findByRole('button', { name: 'Edit', exact: true }))
  expect(screen.getByLabelText('Owner email')).toHaveAttribute('readonly')
  expect(screen.getByLabelText('Owner phone country code')).toHaveValue('+65')
  expect(screen.getByLabelText('Owner phone number')).toHaveValue('91234567')
  await userEvent.clear(screen.getByLabelText('Owner name'))
  await userEvent.type(screen.getByLabelText('Owner name'), 'Updated Owner')
  await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }))
  expect(save).not.toHaveBeenCalled()
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save Changes' }))
  expect(await screen.findByRole('heading', { name: 'Updated Owner' })).toBeVisible()
  expect(save).toHaveBeenCalledExactlyOnceWith({ id: 'owner', expectedVersion: 1, details: { name: 'Updated Owner', email: record.email, phone_country_code: '+65', phone_number: '91234567', birthday: record.birthday, gender: record.gender } })
  expect(onSaved).toHaveBeenCalledOnce()
})

it('locks an uncertain save to its original fields and retries the same reviewed input', async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValue({ ...record, version: 2 })
  show(save)
  await userEvent.click(await screen.findByRole('button', { name: 'Edit', exact: true }))
  await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }))
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save Changes' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost')
  expect(screen.getByLabelText('Owner name')).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Check Original Save' }))
  expect(await screen.findByRole('button', { name: 'Edit', exact: true })).toBeVisible()
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0])
})
