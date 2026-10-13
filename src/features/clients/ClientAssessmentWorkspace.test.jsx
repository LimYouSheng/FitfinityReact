import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import ClientAssessmentWorkspace from './ClientAssessmentWorkspace.jsx'

vi.mock('../../hooks/usePortalActions.js', () => ({ default: () => ({ runAction: operation => operation() }) }))
afterEach(cleanup)
const client = { id: 'client', version: 1, status: 'active', people: [{ id: 'person', version: 1, name: 'Client', birthday: '1990-01-01' }] }
const viewer = { name: 'Owner', role: 'owner' }
const records = { businessDate: '2026-10-13', people: client.people.map(person => ({ ...person, assessments: {} })), pending: null }

it('retains edited answers across an equivalent directory refresh without another record load', async () => {
  const services = { readClientAssessments: vi.fn().mockResolvedValue(records), clientService: {} }
  const onEditChange = vi.fn()
  const view = value => <ActionConfirmationProvider><ClientAssessmentWorkspace client={value} viewer={viewer} services={services} generation={1} timeZone="Asia/Singapore" onEditChange={onEditChange} /></ActionConfirmationProvider>
  const { rerender } = render(view(client))
  fireEvent.click(await screen.findByRole('button', { name: 'Static Balance — Not filled', exact: true }))
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Eyes open — trial 1 (seconds)', exact: true }), { target: { value: '7' } })
  rerender(view(structuredClone(client)))
  expect(screen.getByRole('spinbutton', { name: 'Eyes open — trial 1 (seconds)', exact: true }).value).toBe('7')
  expect(services.readClientAssessments).toHaveBeenCalledTimes(1)
})

it('retires open private forms immediately when the login generation changes', async () => {
  let resolve
  const pending = new Promise(done => { resolve = done })
  const services = { readClientAssessments: vi.fn().mockResolvedValueOnce(records).mockReturnValueOnce(pending), clientService: {} }
  const onEditChange = vi.fn()
  const view = generation => <ActionConfirmationProvider><ClientAssessmentWorkspace client={client} viewer={viewer} services={services} generation={generation} timeZone="Asia/Singapore" onEditChange={onEditChange} /></ActionConfirmationProvider>
  const { rerender } = render(view(1))
  fireEvent.click(await screen.findByRole('button', { name: 'Static Balance — Not filled', exact: true }))
  rerender(view(2))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.getByRole('status').textContent).toContain('Loading assessment')
  await act(async () => resolve(records))
  expect(screen.queryByRole('dialog')).toBeNull()
})
