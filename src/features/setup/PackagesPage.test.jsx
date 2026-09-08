import { mockPolicy } from '../../data/mockPolicy.js'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'

import { DEFAULT_PACKAGES } from '../../data/mockPackages.js'
import PackagesPage from './PackagesPage.jsx'

afterEach(cleanup)
const show = props => render(<ActionConfirmationProvider><EditGuardProvider><PackagesPage policy={mockPolicy} packages={DEFAULT_PACKAGES} selectedId="new" onNavigate={() => {}} {...props} /></EditGuardProvider></ActionConfirmationProvider>)

it('keeps invalid count text visible and accepts a custom integer with policy-derived validity', async () => {
  const user = userEvent.setup(), onSave = vi.fn().mockResolvedValue({ id: 'custom' })
  show({ onSave })
  await user.type(screen.getByLabelText('Package name'), 'Custom count')
  const count = screen.getByLabelText('Package session count')
  expect(count).toHaveAttribute('inputmode', 'numeric')
  for (const invalid of ['0', '366', '1.5', '1e2']) {
    await user.clear(count); await user.type(count, invalid)
    await user.click(screen.getByRole('button', { name: 'Create Package', exact: true }))
    expect(count).toHaveValue(invalid)
    expect(count).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Enter a whole number from 1 to 365.')).toBeVisible()
    expect(onSave).not.toHaveBeenCalled()
  }
  await user.clear(count); await user.type(count, '18')
  await user.click(screen.getByRole('button', { name: 'Create Package', exact: true }))
  const dialog = screen.getByRole('dialog', { name: 'Create Package?' })
  expect(dialog).toHaveTextContent('18 sessions · 135 days')
  await user.click(within(dialog).getByRole('button', { name: 'Create Package', exact: true }))
  expect(onSave.mock.calls[0][0].draft.total).toBe(18)
})

it('requires a name, reviews the correct validity and saves only after confirmation', async () => {
  const user = userEvent.setup(), onSave = vi.fn().mockResolvedValue({ id: 'new-package' }), onNavigate = vi.fn()
  show({ onSave, onNavigate })
  await user.click(screen.getByRole('button', { name: 'Create Package', exact: true }))
  expect(screen.getByRole('textbox', { name: 'Package name' })).toHaveAttribute('aria-invalid', 'true')
  expect(onSave).not.toHaveBeenCalled()
  await user.type(screen.getByRole('textbox', { name: 'Package name' }), 'New package')
  await user.type(screen.getByRole('textbox', { name: 'Package session count' }), '36')
  expect(screen.queryByText(/Clients choose their weekly frequency/)).not.toBeInTheDocument()
  expect(screen.queryByText(/270-day validity/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Create Package', exact: true }))
  let dialog = screen.getByRole('dialog', { name: 'Create Package?' })
  expect(dialog).toHaveTextContent('36 sessions · 270 days')
  expect(onSave).not.toHaveBeenCalled()
  await user.click(within(dialog).getByRole('button', { name: 'Cancel', exact: true }))
  expect(screen.getByRole('textbox', { name: 'Package name' })).toHaveValue('New package')
  await user.click(screen.getByRole('button', { name: 'Create Package', exact: true }))
  dialog = screen.getByRole('dialog', { name: 'Create Package?' })
  await user.click(within(dialog).getByRole('button', { name: 'Create Package', exact: true }))
  expect(onSave).toHaveBeenCalledExactlyOnceWith({ id: undefined, expectedVersion: undefined, draft: { name: 'New package', total: 36, status: 'active' } })
  await waitFor(() => expect(onNavigate).toHaveBeenCalledExactlyOnceWith('packages/new-package', { replace: true }))
})

it('retains values after a failed edit and retries with the same optimistic version', async () => {
  const user = userEvent.setup(), onSave = vi.fn().mockRejectedValueOnce(new Error('Storage full')).mockResolvedValue({ id: 'package-12' })
  show({ selectedId: 'package-12', onSave })
  await user.click(screen.getByRole('button', { name: 'Edit Package' }))
  const name = screen.getByRole('textbox', { name: 'Package name' })
  await user.clear(name); await user.type(name, 'Changed package')
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await user.click(screen.getByRole('button', { name: 'Save Package', exact: true }))
    const dialog = screen.getByRole('dialog', { name: 'Save Package?' })
    await user.click(within(dialog).getByRole('button', { name: 'Save Package', exact: true }))
    if (!attempt) { expect(await screen.findByRole('alert')).toHaveTextContent('Storage full'); expect(name).toHaveValue('Changed package') }
  }
  expect(onSave).toHaveBeenCalledTimes(2)
  expect(onSave.mock.calls[1][0]).toMatchObject({ id: 'package-12', expectedVersion: 1, draft: { name: 'Changed package', total: 12 } })
})
