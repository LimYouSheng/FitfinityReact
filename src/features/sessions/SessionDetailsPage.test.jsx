import { drawSignature } from '../../test/drawSignature.js'
import { mockPolicy } from '../../data/mockPolicy.js'
import { StrictMode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import AppShell from '../../components/AppShell.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import SessionDetailsPage from './SessionDetailsPage.jsx'

const session = {
  id: 's1',
  clientId: 'c1',
  trainerId: 't1',
  date: '2026-09-02',
  from: '18:00',
  to: '19:00',
  sessionNumber: 4,
  packageTotal: 12,
  status: 'planned',
  exercisePlan: [],
}
const client = { id: 'c1', name: 'Amanda Lim', phone: { countryCode: '+65', number: '90001122' } }
const trainer = { id: 't1', name: 'Marcus Tan', status: 'active' }
const trainers = [trainer, { id: 't2', name: 'Rachel Ong', status: 'active' }]

function renderDetails(overrides = {}) {
  const props = {
    user: { id: 'u-marcus', role: 'trainer', trainerId: 't1' },
    session,
    client,
    trainer,
    trainers,
    onOpenClient: vi.fn(),
    onOpenTrainer: vi.fn(),
    onSavePlan: vi.fn(),
    onAcknowledge: vi.fn(),
    onSaveOutcome: vi.fn(),
    onSaveClientSummary: vi.fn(),
    onMarkWhatsAppOpened: vi.fn(),
    onSaveDetails: vi.fn(),
    onRequestTimeChange: vi.fn(),
    onRequestTrainerChange: vi.fn(),
    ...overrides,
  }

  render(
    <StrictMode>
      <ActionConfirmationProvider>
        <EditGuardProvider>
          <AppShell
            user={props.user}
            users={[props.user]}
            userId={props.user.id}
            route="sessions"
            messages={[]}
            onRoute={vi.fn()}
            onUserChange={vi.fn()}
            onReset={vi.fn()}
          >
            <SessionDetailsPage policy={mockPolicy} {...props} />
          </AppShell>
        </EditGuardProvider>
      </ActionConfirmationProvider>
    </StrictMode>,
  )

  return props
}

describe('session detail confirmations', () => {
  it('opens the API confirmation after reviewing a time change', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
    const props = renderDetails()
    fireEvent.click(screen.getByRole('button', { name: 'Request Time Change' }))
    expect(screen.getByLabelText('Requested session date')).toHaveAttribute('min', '2026-09-02')
    expect(screen.getByLabelText('Requested start time')).toHaveAttribute('min', '12:00')
    fireEvent.change(screen.getByLabelText('Requested session date'), { target: { value: '2026-09-01' } })
    expect(screen.getByRole('button', { name: 'Review Request' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('in the future')
    fireEvent.change(screen.getByLabelText('Requested session date'), { target: { value: '2026-09-02' } })
    fireEvent.change(screen.getByLabelText('Requested start time'), { target: { value: '12:00' } })
    expect(screen.getByRole('button', { name: 'Review Request' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Requested start time'), { target: { value: '12:01' } })
    expect(screen.getByRole('button', { name: 'Review Request' })).toBeEnabled()
    fireEvent.change(screen.getByLabelText('Requested session date'), { target: { value: '2026-09-04' } })
    expect(screen.getByLabelText('Requested start time')).not.toHaveAttribute('min')
    fireEvent.click(screen.getByRole('button', { name: 'Review Request' }))
    expect(screen.queryByRole('dialog', { name: 'Request Time Change' })).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Submit time-change request?' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Request Time Change' })).toBeVisible())
    fireEvent.click(screen.getByRole('button', { name: 'Review Request' }))
    vi.setSystemTime(new Date('2026-09-02T10:00:00Z'))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Request' }))
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Request Time Change' })).toBeVisible())
    expect(screen.getByRole('alert')).toHaveTextContent('before the session starts')
    expect(props.onRequestTimeChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('button', { name: 'Request Time Change' })).toBeDisabled()
    for (const status of ['completed', 'cancelled']) {
      cleanup()
      renderDetails({ session: { ...session, date: '2026-09-04', status } })
      expect(screen.getByRole('button', { name: 'Request Time Change' })).toBeDisabled()
    }
  })

  it('opens the API confirmation after reviewing acknowledgement', () => {
    renderDetails()
    fireEvent.click(screen.getByRole('button', { name: 'Client Signature' }))
    drawSignature(screen.getByRole('img', { name: 'Draw client signature' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review Completion' }))
    expect(screen.queryByRole('dialog', { name: 'Client signature' })).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Complete this session?' })).toBeVisible()
  })

  it('reviews recorded videos before exporting the summary to WhatsApp', () => {
    const onMarkWhatsAppOpened = vi.fn()
    renderDetails({
      onMarkWhatsAppOpened,
      session: {
        ...session,
        exercisePlan: [{
          id: 'e1',
          name: 'Romanian Deadlift',
          weight: '40 kg',
          reps: '8',
          rounds: '2',
          rest: '60 sec',
          videoAttached: true,
        }],
      },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Export Summary' }))
    const dialog = screen.getByRole('dialog', { name: 'Export Summary' })
    expect(dialog).toBeVisible()
    expect(screen.getByRole('checkbox')).toBeChecked()
    expect(dialog).toHaveTextContent('Romanian Deadlift — 40 kg · 8 reps · 2 rounds · 1 minute rest interval')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onMarkWhatsAppOpened).not.toHaveBeenCalled()
  })
})

afterEach(() => { cleanup(); vi.useRealTimers() })

it('M4 keeps a blocked WhatsApp export retryable and never marks it sent', () => {
  const open=vi.spyOn(window,'open').mockReturnValue(null)
  const props=renderDetails()
  fireEvent.click(screen.getByRole('button',{name:'Export Summary'}))
  fireEvent.click(screen.getByRole('button',{name:'Continue to WhatsApp'}))
  expect(screen.getByRole('link',{name:'Open summary in WhatsApp'})).toHaveAttribute('href',expect.stringMatching(/^https:\/\/wa.me\//))
  expect(props.onMarkWhatsAppOpened).not.toHaveBeenCalled()
  open.mockRestore()
})

it('M4 records an opened WhatsApp handoff without claiming delivery',async()=>{
  const popup={opener:{},location:{replace:vi.fn()}}
  const open=vi.spyOn(window,'open').mockReturnValue(popup)
  const props=renderDetails()
  fireEvent.click(screen.getByRole('button',{name:'Export Summary'}))
  fireEvent.click(screen.getByRole('button',{name:'Continue to WhatsApp'}))
  await waitFor(()=>expect(props.onMarkWhatsAppOpened).toHaveBeenCalledTimes(1))
  expect(popup.opener).toBeNull()
  expect(popup.location.replace).toHaveBeenCalledWith(expect.stringMatching(/^https:\/\/wa.me\//))
  open.mockRestore()
})
