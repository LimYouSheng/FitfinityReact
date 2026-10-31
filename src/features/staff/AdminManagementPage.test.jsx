import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import { ADMIN_APPROVAL_FIELDS } from '../../app/adminApprovals.js'
import AdminManagementPage from './AdminManagementPage.jsx'

afterEach(cleanup)
it('keeps an uncertain Admin policy save frozen until the original attempt is recovered', async () => {
  const record = { id: 'admin', role: 'admin', version: 1, status: 'active',
    details: { name: 'Test Admin', email: 'admin@example.test', phone_country_code: '+65', phone_number: '91234567', birthday: '1990-01-01', gender: 'Other' },
    approvalNeeded: Object.fromEntries(ADMIN_APPROVAL_FIELDS.map(([area]) => [area, ['exerciseLibrary', 'content'].includes(area)])),
  }
  const changed = { ...record, version: 2, approvalNeeded: { ...record.approvalNeeded, content: false } }
  const update = vi.fn().mockRejectedValueOnce(new Error('Lost response')).mockResolvedValue(changed)
  render(<ActionConfirmationProvider><EditGuardProvider><AdminManagementPage selectedId="admin" today="2026-10-31" services={{ staffService: { getById: async () => record, update } }} /></EditGuardProvider></ActionConfirmationProvider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Approval Requirements', exact: true }))
  expect(screen.getByRole('checkbox', { name: 'Manage content', exact: true })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Manage the Exercise Library', exact: true })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Share progress reports', exact: true })).not.toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Manage content', exact: true }))
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirm', exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Lost response')
  expect(screen.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Back to Admin' })).toBeDisabled()
  expect(screen.getByRole('checkbox', { name: 'Manage content', exact: true })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'General Details', exact: true }))
  expect(screen.getByRole('heading', { name: 'Approval Requirements', exact: true })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Retry Original Save' }))
  await screen.findByRole('button', { name: 'Edit', exact: true })
  expect(screen.getByRole('checkbox', { name: 'Manage content', exact: true })).not.toBeChecked()
  expect(update).toHaveBeenCalledTimes(2)
  expect(update.mock.calls[1][0]).toEqual(update.mock.calls[0][0])
})
