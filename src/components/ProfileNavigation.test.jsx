import { mockPolicy } from '../data/mockPolicy.js'
import { useEffect, useState } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ProfileNavigation from './ProfileNavigation.jsx'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from './EditGuardProvider.jsx'
import TrainerProfilePage from '../features/trainers/TrainerProfilePage.jsx'
import { seed } from '../data/seed.js'

vi.mock('../features/trainers/TrainerAvailabilityEditor.jsx', () => ({ default: () => null }))

const items = [['overview', 'Overview'], ['history', 'Session History']]
let media

beforeEach(() => {
  const listeners = new Set()
  media = {
    matches: false,
    addEventListener: (_type, listener) => listeners.add(listener),
    removeEventListener: (_type, listener) => listeners.delete(listener),
    resize(matches) {
      this.matches = matches
      listeners.forEach(listener => listener({ matches }))
    },
  }
  vi.stubGlobal('matchMedia', () => media)
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function Providers({ children }) {
  return <ActionConfirmationProvider><EditGuardProvider>{children}</EditGuardProvider></ActionConfirmationProvider>
}

it('uses the committed selection for its label and current item across mobile and inline layouts', async () => {
  const user = userEvent.setup()
  const onSelect = vi.fn()
  const { container, rerender } = render(<ProfileNavigation items={items} activeKey="overview" onSelect={onSelect} />)
  const menu = container.querySelector('details')
  const summary = container.querySelector('summary')
  expect(summary).toHaveTextContent('Overview')
  await user.click(summary)
  await user.click(screen.getByRole('button', { name: 'Session History' }))
  expect(onSelect).toHaveBeenCalledWith('history')
  expect(summary).toHaveTextContent('Overview')
  expect(menu).not.toHaveAttribute('open')

  rerender(<ProfileNavigation items={items} activeKey="history" onSelect={onSelect} />)
  expect(summary).toHaveTextContent('Session History')
  act(() => media.resize(true))
  expect(menu).toHaveAttribute('open')
  expect(screen.getByRole('button', { name: 'Session History' })).toHaveAttribute('aria-current', 'true')
  expect(screen.getByRole('button', { name: 'Overview' })).not.toHaveAttribute('aria-current')
  act(() => media.resize(false))
  expect(menu).not.toHaveAttribute('open')
  expect(summary).toHaveTextContent('Session History')
})

function GuardedNavigation() {
  const [activeKey, setActiveKey] = useState('overview')
  const { guardNavigation, setActiveEdit } = useEditGuard()
  useEffect(() => { setActiveEdit('Client information') }, [setActiveEdit])
  return <ProfileNavigation items={items} activeKey={activeKey} onSelect={key => guardNavigation(() => setActiveKey(key))} />
}

it('keeps the current label when leaving an edit is cancelled and changes it after confirmation', async () => {
  const { container } = render(<Providers><GuardedNavigation /></Providers>)
  const summary = container.querySelector('summary')
  fireEvent.click(summary)
  fireEvent.click(screen.getByRole('button', { name: 'Session History' }))
  expect(summary).toHaveTextContent('Overview')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(summary).toHaveTextContent('Overview')
  fireEvent.click(summary)
  fireEvent.click(screen.getByRole('button', { name: 'Session History' }))
  fireEvent.click(screen.getByRole('button', { name: 'Leave Without Saving' }))
  await waitFor(() => expect(summary).toHaveTextContent('Session History'))
})

it('keeps Assigned Clients for owners and removes both its control and content for a trainer', () => {
  media.matches = true
  const trainer = seed.trainers.find(item => item.id === 't1')
  const props = { trainer, trainers: seed.trainers, clients: seed.clients, sessions: seed.sessions }
  const page = viewer => <Providers><TrainerProfilePage policy={mockPolicy} {...props} viewer={viewer} /></Providers>
  const { container, rerender } = render(page(seed.users.find(user => user.role === 'owner')))
  fireEvent.click(screen.getByRole('button', { name: 'Assigned Clients' }))
  expect(screen.getByRole('heading', { name: 'Assigned Clients' })).toBeInTheDocument()
  expect(screen.getByLabelText('Assigned client list')).toHaveTextContent('Amanda Lim')
  expect(container.querySelector('summary')).toHaveTextContent('Assigned Clients')

  rerender(page(seed.users.find(user => user.trainerId === 't1')))
  expect(screen.queryByRole('button', { name: 'Assigned Clients' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Assigned client list')).not.toBeInTheDocument()
  expect(container.querySelector('summary')).toHaveTextContent('Overview')
  expect(screen.getByRole('heading', { name: 'General Information' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Availability', exact: true }))
  expect(container.querySelector('summary')).toHaveTextContent('Availability')
  expect(screen.getByRole('heading', { name: 'Approved Availability' })).toBeInTheDocument()
})
