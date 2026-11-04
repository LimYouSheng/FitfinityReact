import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
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
  expect(screen.queryByText(/Role: Admin\./)).not.toBeInTheDocument()
  expect(screen.getAllByRole('checkbox')).toHaveLength(17)
  expect(within(screen.getByRole('region', { name: 'Sharing', exact: true })).getAllByRole('checkbox')).toHaveLength(2)
  expect(within(screen.getByRole('region', { name: 'Clients', exact: true })).getAllByRole('checkbox')).toHaveLength(4)
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
  const deactivate = screen.getByRole('button', { name: 'Deactivate', exact: true })
  expect(deactivate).toHaveClass('profile-menu-danger')
  fireEvent.click(deactivate)
  expect(screen.getByRole('button', { name: 'Deactivate Admin', exact: true })).toHaveClass('danger-button')
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Admin', exact: true }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByRole('button', { name: 'Confirm', exact: true })).toHaveClass('danger-button')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel', exact: true }))
  expect(update).toHaveBeenCalledTimes(2)
})

function adminRecord(id, name, gender = 'Female', status = 'active') {
  return { id, role: 'admin', version: 1, status,
    details: { name, email: `${id}@example.test`, phone_country_code: '+65', phone_number: '91234567', birthday: '1990-01-01', gender },
    approvalNeeded: Object.fromEntries(ADMIN_APPROVAL_FIELDS.map(([area]) => [area, false])),
  }
}

it('keeps list and profile responses bound to the selected route during click-through and Back', async () => {
  const record = adminRecord('first', 'First Admin')
  let finishDetail
  const getById = vi.fn(() => new Promise(resolve => { finishDetail = resolve }))
  const services = { staffService: { getAll: vi.fn().mockResolvedValue([record]), getById } }
  const onNavigate = vi.fn()
  const view = selectedId => <ActionConfirmationProvider><EditGuardProvider><AdminManagementPage services={services} selectedId={selectedId} onNavigate={onNavigate} today="2026-11-03" /></EditGuardProvider></ActionConfirmationProvider>
  const { rerender } = render(view())
  await screen.findByText('First Admin')
  rerender(view('first'))
  expect(screen.getByText('Loading Admin details…')).toBeVisible()
  await act(async () => finishDetail(record))
  expect(screen.getByRole('heading', { name: 'First Admin' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'General Information' })).toBeVisible()
  rerender(view())
  await screen.findByText('First Admin')
  expect(screen.queryByRole('heading', { name: 'General Information' })).not.toBeInTheDocument()
})

it('filters and paginates Admin records independently and opens the selected result', async () => {
  const records = Array.from({ length: 12 }, (_, i) => adminRecord(`admin${i}`, `Admin ${String(i).padStart(2, '0')}`, i % 2 ? 'Male' : 'Female', i === 11 ? 'inactive' : 'active'))
  const onNavigate = vi.fn()
  render(<AdminManagementPage services={{ staffService: { getAll: async () => records } }} onNavigate={onNavigate} />)
  const list = await screen.findByLabelText('Admin list')
  expect(within(list).getAllByRole('button', { name: /^View / })).toHaveLength(10)
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(within(list).getAllByRole('button', { name: /^View / })).toHaveLength(2)
  fireEvent.change(screen.getByLabelText('Filter admins by status'), { target: { value: 'inactive' } })
  expect(within(list).getAllByRole('button', { name: /^View / })).toHaveLength(1)
  fireEvent.change(screen.getByLabelText('Filter admins by gender'), { target: { value: 'Female' } })
  expect(screen.getByText('No matching admins.')).toBeVisible()
  fireEvent.change(screen.getByLabelText('Filter admins by status'), { target: { value: 'all' } })
  expect(within(list).getAllByRole('button', { name: /^View / })).toHaveLength(6)
  fireEvent.change(screen.getByLabelText('Search admin'), { target: { value: 'admin4@example.test' } })
  fireEvent.click(within(list).getByRole('button', { name: 'View Admin 04' }))
  expect(onNavigate).toHaveBeenCalledWith('admins/admin4')
})
