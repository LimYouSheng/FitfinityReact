import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import ClientNoteRecovery from './ClientNoteRecovery.jsx'

afterEach(cleanup)
const view = props => <ActionConfirmationProvider><ClientNoteRecovery {...props} /></ActionConfirmationProvider>

it('checks without writing and requires confirmation before resuming the original save', async () => {
  const services = { recoverClientNotes: vi.fn().mockResolvedValue({ pending: true, recovered: false }), resumeClientNotes: vi.fn().mockResolvedValue({}) }
  const onRecovered = vi.fn()
  render(view({ services, generation: 1, onRecovered }))
  fireEvent.click(await screen.findByRole('button', { name: 'Check Previous Notes Save' }))
  await waitFor(() => expect(services.recoverClientNotes).toHaveBeenCalledTimes(2))
  expect(services.resumeClientNotes).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry Original Notes Save' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
  expect(services.resumeClientNotes).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry Original Notes Save' }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry Original Save', exact: true }))
  await waitFor(() => expect(services.resumeClientNotes).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(onRecovered).toHaveBeenCalledTimes(1))
})

it('ignores late recovery results from an old login', async () => {
  let resolve
  const services = { recoverClientNotes: vi.fn().mockReturnValueOnce(new Promise(done => { resolve = done })).mockResolvedValue({ pending: false, recovered: false }) }
  const onRecovered = vi.fn()
  const { rerender } = render(view({ services, generation: 1, onRecovered }))
  rerender(view({ services, generation: 2, onRecovered }))
  resolve({ pending: true, recovered: true })
  await waitFor(() => expect(services.recoverClientNotes).toHaveBeenCalledTimes(2))
  expect(screen.queryByRole('button', { name: 'Retry Original Notes Save' })).toBeNull()
  expect(onRecovered).not.toHaveBeenCalled()
})

it('renders nothing for demo services without a login generation or recovery capability', () => {
  const { container } = render(view({ services: {}, onRecovered: vi.fn() }))
  expect(container).toBeEmptyDOMElement()
})
