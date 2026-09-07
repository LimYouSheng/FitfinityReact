import { useEffect, useLayoutEffect, useState } from 'react'
import { afterEach, beforeEach, expect, it } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from '../components/EditGuardProvider.jsx'
import useAppNavigation from './useAppNavigation.js'

function Harness() {
  const { path, navigate, goBack } = useAppNavigation()
  const { setActiveEdit } = useEditGuard()
  const [draft, setDraft] = useState('')
  useEffect(() => { setActiveEdit(draft ? 'Draft' : null) }, [draft, setActiveEdit])
  return <><output>{path}</output><input aria-label="Draft" value={draft} onChange={event => setDraft(event.target.value)} />
    <button onClick={() => navigate('clients/c1')}>Client one</button><button onClick={() => navigate('clients/c2')}>Client two</button>
    <button onClick={() => goBack('clients')}>App Back</button></>
}
const output = () => screen.getByRole('status')
const dialog = () => screen.getByRole('dialog', { name: 'Leave this edit?' })
const traverse = async direction => { await act(async () => { history.go(direction) }) }
const decide = async name => {
  fireEvent.click(within(dialog()).getByRole('button', { name, exact: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
}
beforeEach(() => {
  history.replaceState(null, '', '/#/clients')
  render(<ActionConfirmationProvider><EditGuardProvider><Harness /></EditGuardProvider></ActionConfirmationProvider>)
})
afterEach(cleanup)

it('restores the current entry before native Back confirmation, retains the draft on Cancel, then leaves once', async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Client one' }))
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'unsaved' } })
  await traverse(-1)
  await waitFor(() => expect(dialog()).toBeInTheDocument())
  expect(location.hash).toBe('#/clients/c1')
  expect(history.state.fitfinityDepth).toBe(1)
  expect(output()).toHaveTextContent('clients/c1')
  await decide('Cancel')
  expect(screen.getByLabelText('Draft')).toHaveValue('unsaved')
  await traverse(-1)
  await waitFor(() => expect(dialog()).toBeInTheDocument())
  await decide('Leave Without Saving')
  await waitFor(() => expect(location.hash).toBe('#/clients'))
  expect(output()).toHaveTextContent(/^clients$/)
  expect(history.state.fitfinityDepth).toBe(0)
})

it('guards native Forward and preserves the Forward entry after cancellation', async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Client one' }))
  fireEvent.click(screen.getByRole('button', { name: 'Client two' }))
  await traverse(-1)
  await waitFor(() => expect(location.hash).toBe('#/clients/c1'))
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'keep' } })
  await traverse(1)
  await waitFor(() => expect(dialog()).toBeInTheDocument())
  expect(location.hash).toBe('#/clients/c1')
  await decide('Cancel')
  await traverse(1)
  await waitFor(() => expect(dialog()).toBeInTheDocument())
  await decide('Leave Without Saving')
  await waitFor(() => expect(location.hash).toBe('#/clients/c2'))
  expect(output()).toHaveTextContent('clients/c2')
})

it('guards direct hash navigation and handles the duplicate hashchange event once', async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Client one' }))
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'keep' } })
  await act(async () => { location.hash = '#/sessions' })
  await waitFor(() => expect(dialog()).toBeInTheDocument())
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(location.hash).toBe('#/clients/c1')
  await decide('Cancel')
  expect(output()).toHaveTextContent('clients/c1')
  expect(screen.getByLabelText('Draft')).toHaveValue('keep')
})

it('does not prompt twice for App Back and supports repeating the same clean Back destination', async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Client one' }))
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'edit' } })
  fireEvent.click(screen.getByRole('button', { name: 'App Back' }))
  await decide('Leave Without Saving')
  await waitFor(() => expect(location.hash).toBe('#/clients'))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: 'Client one' }))
  await traverse(-1)
  await waitFor(() => expect(location.hash).toBe('#/clients'))
  expect(output()).toHaveTextContent(/^clients$/)
})


it('synchronizes a route changed during mount before history listeners are attached', () => {
  cleanup()
  function MountNavigation() {
    const { path } = useAppNavigation()
    useLayoutEffect(() => {
      history.replaceState(null, '', '/#/sessions/s1')
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    }, [])
    return <output>{path}</output>
  }
  render(<ActionConfirmationProvider><EditGuardProvider><MountNavigation /></EditGuardProvider></ActionConfirmationProvider>)
  expect(location.hash).toBe('#/sessions/s1')
  expect(output()).toHaveTextContent('sessions/s1')
})
