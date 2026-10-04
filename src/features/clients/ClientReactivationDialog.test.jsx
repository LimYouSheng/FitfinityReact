import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import { formatDate } from '../../utils/date.js'
import ClientReactivationDialog from './ClientReactivationDialog.jsx'

const fixture = () => {
  const client = { id: 'c1', name: 'Client One', status: 'inactive', package: { id: 'p1', status: 'inactive', deactivationReason: 'client', deactivatedAt: '2026-09-01T00:00:00Z' } }
  return { client, clients: [client, { id: 'c2', status: 'active', package: { id: 'p2', status: 'active' } }],
    trainers: [{ id: 't1', name: 'Trainer One', status: 'active' }], sessions: [
      { id: 'a', clientId: 'c1', packageId: 'p1', trainerId: 't1', date: '2026-09-10', from: '10:00', to: '11:00', status: 'planned' },
      { id: 'b', clientId: 'c1', packageId: 'p1', trainerId: 't1', date: '2026-09-10', from: '12:00', to: '13:00', status: 'planned' },
      { id: 'taken', clientId: 'c2', packageId: 'p2', trainerId: 't1', date: '2026-09-10', from: '10:00', to: '13:00', status: 'planned' },
    ] }
}
const view = props => <ActionConfirmationProvider><EditGuardProvider><ClientReactivationDialog {...props} /></EditGuardProvider></ActionConfirmationProvider>
const saveButton = () => screen.getByRole('button', { name: 'Reactivate Client', exact: true })
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-02T04:00:00Z')) })
afterEach(() => { cleanup(); vi.useRealTimers() })
it('labels each conflicting session separately and uses the calendar to resolve dates before submitting', async () => {
  const onSave = vi.fn().mockResolvedValue(), onClose = vi.fn()
  render(view({ ...fixture(), onSave, onClose }))
  const a = screen.getByRole('textbox', { name: /Session 1/ }), b = screen.getByRole('textbox', { name: /Session 2/ })
  expect(a).toHaveValue('2026-09-10'); expect(b).toHaveValue('2026-09-10'); expect(saveButton()).toBeDisabled()
  fireEvent.keyDown(a, { key: 'Enter' })
  const calendar = screen.getByRole('dialog', { name: /Session 1.*calendar/ })
  fireEvent.click(within(calendar).getByRole('button', { name: formatDate('2026-09-11'), exact: true }))
  expect(a).toHaveValue('2026-09-11'); expect(saveButton()).toBeDisabled()
  fireEvent.change(b, { target: { value: '2026-09-11' } })
  expect(saveButton()).toBeEnabled()
  fireEvent.click(saveButton())
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
  expect(onSave).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ dates: { a: '2026-09-11', b: '2026-09-11' }, expected: expect.objectContaining({ status: 'inactive' }) }))
})
it('keeps drafts and the dialog open when saving fails', async () => {
  const onSave = vi.fn().mockRejectedValue(new Error('A new booking conflicts.')), onClose = vi.fn()
  render(view({ ...fixture(), onSave, onClose }))
  for (const field of screen.getAllByRole('textbox')) fireEvent.change(field, { target: { value: '2026-09-12' } })
  fireEvent.click(saveButton())
  expect(await screen.findByRole('alert')).toHaveTextContent('A new booking conflicts.')
  expect(onClose).not.toHaveBeenCalled()
  for (const field of screen.getAllByRole('textbox')) expect(field).toHaveValue('2026-09-12')
  expect(saveButton()).toBeEnabled()
})
it('blocks malformed dates and conflicts introduced by proposed moves', () => {
  const props = fixture(); props.sessions[1].date = '2026-09-11'; props.sessions[1].from = '10:00'; props.sessions[1].to = '11:00'
  render(view({ ...props, onSave: vi.fn(), onClose: vi.fn() }))
  const a = screen.getByRole('textbox', { name: /Session 1/ })
  fireEvent.change(a, { target: { value: '2026-02-31' } }); expect(saveButton()).toBeDisabled()
  fireEvent.change(a, { target: { value: '2026-09-11' } }); expect(saveButton()).toBeDisabled()
  const b = screen.getByRole('textbox', { name: /Session 2/ })
  fireEvent.change(b, { target: { value: '2026-09-12' } }); expect(saveButton()).toBeEnabled()
})
it('requires a new review if a session is deleted while edited without crashing or silently saving', () => {
  const props = { ...fixture(), onSave: vi.fn(), onClose: vi.fn() }, rendered = render(view(props))
  fireEvent.change(screen.getByRole('textbox', { name: /Session 1/ }), { target: { value: '2026-09-12' } })
  rendered.rerender(view({ ...props, sessions: props.sessions.filter(s => s.id !== 'a') }))
  expect(screen.getByRole('alert')).toHaveTextContent('Close and reopen')
  expect(saveButton()).toBeDisabled(); expect(props.onSave).not.toHaveBeenCalled()
})
it('prevents a second save or dismissal while reactivation is pending', async () => {
  let finish
  const onSave = vi.fn(() => new Promise(resolve => { finish = resolve })), onClose = vi.fn(), props = fixture()
  props.sessions = props.sessions.filter(s => s.id !== 'taken')
  render(view({ ...props, onSave, onClose }))
  fireEvent.click(saveButton())
  expect(screen.getByRole('button', { name: 'Reactivating…' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' })); expect(onClose).not.toHaveBeenCalled()
  expect(onSave).toHaveBeenCalledOnce()
  finish(); await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
})

it('package reactivation reviews only the selected purchase and retains a failed draft for retry', async () => {
  const props = fixture(), onSave = vi.fn().mockRejectedValueOnce(new Error('Storage full')).mockResolvedValue(), onClose = vi.fn()
  props.client.status = 'active'; props.client.package.deactivationReason = 'package'
  props.client.additionalPackages = [{ id: 'other', status: 'inactive', deactivationReason: 'package' }]
  props.sessions.push({ ...props.sessions[0], id: 'other-frozen', packageId: 'other' })
  render(view({ ...props, packageId: 'p1', onSave, onClose }))
  const dialog = screen.getByRole('dialog', { name: 'Reactivate Package?' })
  expect(dialog).toHaveTextContent('Used credits and the expiry date stay the same')
  expect(dialog).toHaveTextContent('Deleted sessions are not recreated')
  expect(dialog).not.toHaveTextContent('cannot be undone')
  expect(screen.getAllByRole('textbox')).toHaveLength(2)
  const save = within(dialog).getByRole('button', { name: 'Reactivate Package', exact: true })
  expect(save).toBeDisabled()
  for (const field of screen.getAllByRole('textbox')) fireEvent.change(field, { target: { value: '2026-09-12' } })
  fireEvent.click(save)
  expect(await screen.findByRole('alert')).toHaveTextContent('Storage full')
  expect(onClose).not.toHaveBeenCalled()
  expect(screen.getAllByRole('textbox').every(field => field.value === '2026-09-12')).toBe(true)
  fireEvent.click(save)
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
  expect(onSave).toHaveBeenLastCalledWith(expect.objectContaining({ packageId: 'p1', dates: { a: '2026-09-12', b: '2026-09-12' } }))
})

it('package reactivation blocks overlapping purchases and stale package state', () => {
  const props = fixture()
  props.client.status = 'active'
  Object.assign(props.client.package, { startDate: '2026-09-01', endDate: '2026-11-29' })
  props.client.additionalPackages = [{ id: 'other', status: 'active', startDate: '2026-10-01', endDate: '2026-12-29' }]
  props.sessions = []
  const onSave = vi.fn(), rendered = render(view({ ...props, packageId: 'p1', onSave, onClose: vi.fn() }))
  expect(screen.getByRole('alert')).toHaveTextContent('Another active package overlaps')
  expect(screen.getByRole('button', { name: 'Reactivate Package', exact: true })).toBeDisabled()
  const changed = structuredClone(props); changed.client.additionalPackages = []
  rendered.rerender(view({ ...changed, packageId: 'p1', onSave, onClose: vi.fn() }))
  expect(screen.getByRole('alert')).toHaveTextContent('Close and reopen')
  expect(screen.getByRole('button', { name: 'Reactivate Package', exact: true })).toBeDisabled()
  expect(onSave).not.toHaveBeenCalled()
})
