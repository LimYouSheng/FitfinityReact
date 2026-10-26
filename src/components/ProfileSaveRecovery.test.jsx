import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { ProfileSaveRecoveryPanel } from './ProfileSaveRecovery.jsx'

afterEach(cleanup)
const view = props => <ActionConfirmationProvider><ProfileSaveRecoveryPanel {...props} /></ActionConfirmationProvider>

it('checks without writing and requires confirmation before resuming the original save', async () => {
  const services = { recoverProfileSaves: vi.fn().mockResolvedValue({ pending: [{ kind: 'notes', label: 'Notes' }], recovered: false }), resumeProfileSave: vi.fn().mockResolvedValue({}) }
  const onRecovered = vi.fn()
  render(view({ services, generation: 1, onRecovered }))
  fireEvent.click(await screen.findByRole('button', { name: 'Check Previous Notes Save' }))
  await waitFor(() => expect(services.recoverProfileSaves).toHaveBeenCalledTimes(2))
  expect(services.resumeProfileSave).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry Original Notes Save' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
  expect(services.resumeProfileSave).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry Original Notes Save' }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry Original Save', exact: true }))
  await waitFor(() => expect(services.resumeProfileSave).toHaveBeenCalledExactlyOnceWith({ kind: 'notes' }))
  await waitFor(() => expect(onRecovered).toHaveBeenCalledTimes(1))
})

it('ignores late recovery results from an old login', async () => {
  let resolve
  const services = { recoverProfileSaves: vi.fn().mockReturnValueOnce(new Promise(done => { resolve = done })).mockResolvedValue({ pending: [], recovered: false }) }
  const onRecovered = vi.fn()
  const { rerender } = render(view({ services, generation: 1, onRecovered }))
  rerender(view({ services, generation: 2, onRecovered }))
  resolve({ pending: [{ kind: 'notes', label: 'Notes' }], recovered: true })
  await waitFor(() => expect(services.recoverProfileSaves).toHaveBeenCalledTimes(2))
  expect(screen.queryByRole('button', { name: 'Retry Original Notes Save' })).toBeNull()
  expect(onRecovered).not.toHaveBeenCalled()
})

it('renders nothing for demo services without a login generation or recovery capability', () => {
  const { container } = render(view({ services: {}, onRecovered: vi.fn() }))
  expect(container).toBeEmptyDOMElement()
})

it('leaves receipt ownership with an active editor until Cancel releases it', async () => {
  const services = { recoverProfileSaves: vi.fn().mockResolvedValue({ pending: [{ kind: 'packages', label: 'Package Setup' }], recovered: false }) }
  const onRecovered = vi.fn()
  const { rerender } = render(view({ services, generation: 1, onRecovered, editing: true }))
  expect(services.recoverProfileSaves).not.toHaveBeenCalled()
  rerender(view({ services, generation: 1, onRecovered, editing: false }))
  await waitFor(() => expect(services.recoverProfileSaves).toHaveBeenCalledTimes(1))
  expect(onRecovered).not.toHaveBeenCalled()
})
