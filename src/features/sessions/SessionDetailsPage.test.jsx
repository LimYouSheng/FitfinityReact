import { browserReportService } from '../../services/reportService.js'
import { drawSignature } from '../../test/drawSignature.js'
import { signatureFixture } from '../../test/fixtures/signature.js'
import { mockPolicy } from '../../data/mockPolicy.js'
import { StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import AppShell from '../../components/AppShell.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import SessionDetailsPage from './SessionDetailsPage.jsx'

beforeEach(() => {
  vi.spyOn(browserReportService, 'sessionFile').mockResolvedValue(new File(['%PDF-1.4'], 'amanda-session-4-summary.pdf', { type: 'application/pdf' }))
})
async function shareButton() {
  const button = screen.getByRole('button', { name: 'Share PDF', exact: true })
  await waitFor(() => expect(button).toBeEnabled())
  return button
}

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

it('keeps inactive client sessions viewable while blocking edit, signature, requests and summary export for both roles', () => {
  for (const role of ['owner', 'trainer']) {
    const props = renderDetails({ user: { id: `u-${role}`, role, trainerId: 't1' }, client: { ...client, status: 'inactive' } })
    expect(screen.getByText('Client inactive', { exact: true })).toBeVisible()
    for (const button of screen.queryAllByRole('button', { name: /^(Edit|Request Time Change|Request Trainer Change)$/ })) expect(button).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Client Signature', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export Summary' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'View Client' }))
    expect(props.onOpenClient).toHaveBeenCalledTimes(1)
    expect(props.onAcknowledge).not.toHaveBeenCalled()
    cleanup()
  }
})

it('shows package inactivity under Package Details and locks its sessions for the owner', () => {
  const purchased = { id: 'past', name: 'Past Strength Package', status: 'inactive', total: 24, used: 7,
    startDate: '2026-06-01', endDate: '2026-11-27', sessionsPerWeek: 2, validityDays: 180 }
  const current = { ...purchased, id: 'current', status: 'active', name: 'Current PT Package', total: 12, used: 3,
    startDate: '2026-12-01', endDate: '2027-02-28', sessionsPerWeek: 1, validityDays: 90 }
  for (const linked of [purchased, current]) {
    renderDetails({ user: { id: 'u-owner', role: 'owner' }, session: { ...session, packageId: linked.id, packageTotal: 99 },
      client: { ...client, package: current, packageHistory: [purchased] } })
    const details = screen.getByLabelText('Session package details')
    expect(details).toHaveTextContent(`${linked.name} · Session 4 / ${linked.total}`)
    expect(details).not.toHaveTextContent(/completed|remaining|weekly|days/)
    const dates = details.querySelectorAll('time')
    expect(dates[0]).toHaveAttribute('datetime', linked.startDate)
    expect(dates[1]).toHaveAttribute('datetime', linked.endDate)
    expect(dates[0].closest('.session-package-summary')).toContainElement(details.querySelector('strong'))
    expect(details).not.toHaveTextContent('/ 99')
    if (linked === purchased) {
      expect(details).toHaveTextContent('01 Jun 2026 – 27 Nov 2026')
      expect(details).toHaveTextContent('Package inactive')
      expect(screen.queryByRole('button', { name: 'Client Signature', exact: true })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Export Summary' })).toBeDisabled()
    } else expect(details).toHaveTextContent('01 Dec 2026 – 28 Feb 2027')
    cleanup()
  }
  renderDetails({ session: { ...session, packageId: 'unknown' }, client: { ...client, package: current } })
  expect(screen.getByLabelText('Session package details')).toHaveTextContent('Package details unavailable')
})

it('derives outcome and generated summary duration from session times instead of a stored duration', () => {
  renderDetails({ session: { ...session, from: '18:00', to: '19:45', outcome: { durationMinutes: 60, trainerComments: 'Preserved' } } })
  expect(document.querySelector('.session-outcome-list')).toHaveTextContent('105 minutes')
  expect(document.querySelector('.client-summary-copy')).toHaveTextContent('Session duration: 105 minutes')
  fireEvent.click(within(document.querySelector('.session-outcome-panel')).getByRole('button', { name: 'Edit' }))
  expect(screen.getByLabelText('Duration (minutes)')).toHaveValue(105)
  expect(screen.getByLabelText('Duration (minutes)')).toHaveAttribute('readonly')
})

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

  it('keeps request launchers disabled until a submitted request finishes so a late completion cannot close a new draft', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
    let finish
    renderDetails({ onRequestTimeChange: () => new Promise(resolve => { finish = resolve }) })
    fireEvent.click(screen.getByRole('button', { name: 'Request Time Change' }))
    fireEvent.change(screen.getByLabelText('Requested session date'), { target: { value: '2026-09-04' } })
    fireEvent.click(screen.getByRole('button', { name: 'Review Request' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit Request' }))
    await waitFor(() => expect(finish).toBeTypeOf('function'))
    expect(screen.getByRole('button', { name: 'Request Time Change' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Request Trainer Change' })).toBeDisabled()
    await act(async () => finish())
    fireEvent.click(screen.getByRole('button', { name: 'Request Time Change' }))
    expect(screen.getByRole('dialog', { name: 'Request Time Change' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Review Request' })).toBeEnabled()
  })

  it('requires only reviewed acknowledgement to complete even without outcome duration or WhatsApp', async () => {
    const props = renderDetails({ session: { ...session, outcome: { durationMinutes: 0 }, whatsappOpenedAt: null } })
    expect([...document.querySelectorAll('.panel h2')].map(heading => heading.textContent)).toEqual(['Session Overview', 'Exercise Plan', 'Session Outcome', 'Client-Facing Summary', 'Acknowledgement'])
    fireEvent.click(screen.getByRole('button', { name: 'Client Signature' }))
    drawSignature(screen.getByRole('img', { name: 'Draw client signature' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review Completion' }))
    expect(screen.queryByRole('dialog', { name: 'Client signature' })).not.toBeInTheDocument()
    const confirmation = screen.getByRole('dialog', { name: 'Complete this session?' })
    expect(confirmation).toBeVisible()
    expect(confirmation).toHaveTextContent('WhatsApp is optional')
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Complete Session' }))
    await waitFor(() => expect(props.onAcknowledge).toHaveBeenCalledOnce())
    expect(props.onAcknowledge).toHaveBeenCalledWith(expect.objectContaining({ method: 'signature', signerName: 'Amanda Lim' }))
    expect(props.onSaveOutcome).not.toHaveBeenCalled()
    expect(props.onMarkWhatsAppOpened).not.toHaveBeenCalled()
  })

  it('shows preserved acknowledgement timestamps and a read-only signature while no-show can only be corrected to a signature', () => {
    const noShow = { method: 'late_no_show', recordedAt: '2026-09-02T04:00:00.000Z', recordedBy: { id: 'u-marcus', name: 'Marcus Tan', role: 'trainer' }, note: 'Pressed no-show by mistake' }
    renderDetails({ session: { ...session, status: 'completed', acknowledgement: noShow, acknowledgementHistory: [noShow] } })
    fireEvent.click(screen.getByRole('button', { name: 'Correct to Client Signature' }))
    const signing = within(screen.getByRole('dialog', { name: 'Client signature' }))
    expect(signing.getByRole('button', { name: 'Review Completion' })).toBeDisabled()
    expect(signing.queryByRole('button', { name: 'Record late / no-show instead' })).not.toBeInTheDocument()
    expect(signing.getByLabelText('Acknowledgement note')).toHaveValue('')
    cleanup()

    const signed = { method: 'signature', signerName: 'Amanda Lim', signature: signatureFixture, recordedAt: '2026-09-02T04:10:00.000Z', recordedBy: noShow.recordedBy }
    renderDetails({ session: { ...session, status: 'completed', acknowledgement: signed, acknowledgementHistory: [noShow, signed] } })
    const history = screen.getByLabelText('Acknowledgement history')
    expect(within(history).getAllByRole('listitem')).toHaveLength(2)
    expect([...history.querySelectorAll('time')].map(time => time.dateTime)).toEqual([noShow.recordedAt, signed.recordedAt])
    expect(history).toHaveTextContent('Pressed no-show by mistake')
    expect(history).toHaveTextContent('Corrected to client signature')
    expect(within(history).getAllByText('Recorded by Marcus Tan')).toHaveLength(2)
    for (const name of ['Client Signature', 'Correct to Client Signature', 'Update Completion']) expect(screen.queryByRole('button', { name, exact: true })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View Client Signature' }))
    const preview = screen.getByRole('dialog', { name: 'Client signature' })
    expect(preview).toHaveTextContent('Signed on')
    expect(preview.querySelector('time')).toHaveAttribute('datetime', signed.recordedAt)
    expect(within(preview).getByRole('img')).toBeVisible()
    expect(within(preview).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(preview).queryByRole('button', { name: 'Clear Signature' })).not.toBeInTheDocument()
    expect(within(preview).queryByRole('button', { name: 'Review Completion' })).not.toBeInTheDocument()
  })

  it('reviews recorded video captions before sharing the summary PDF', async () => {
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
    expect(screen.getByRole('checkbox', { name: 'Include video for Romanian Deadlift' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Include Client-Facing Summary' })).toBeChecked()
    expect(dialog).toHaveTextContent('Romanian Deadlift — 40 kg · 8 reps · 2 rounds · 1 minute rest interval')
    await shareButton()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onMarkWhatsAppOpened).not.toHaveBeenCalled()
  })
})

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

it('shows planning and acknowledgement before completion, then only Completed and optional WhatsApp status', () => {
  for (const status of ['not_planned', 'planned']) {
    renderDetails({ session: { ...session, status } })
    expect(screen.getByLabelText('Session status summary')).toHaveTextContent('Not acknowledged')
    expect(screen.getByLabelText('Session status summary')).not.toHaveTextContent('WhatsApp')
    cleanup()
  }
  for (const method of ['signature', 'late_no_show']) {
    for (const whatsappOpenedAt of [null, '2026-09-02T04:30:00Z']) {
      renderDetails({ session: { ...session, status: 'completed', acknowledgement: { method, signerName: 'Amanda', signature: signatureFixture, recordedAt: '2026-09-02T04:00:00Z' }, whatsappOpenedAt } })
      const summary = screen.getByLabelText('Session status summary')
      expect(summary).toHaveTextContent(`Session · CompletedWhatsApp · ${whatsappOpenedAt ? 'Opened' : 'Not opened'}`)
      expect(summary).not.toHaveTextContent(/Acknowledgement|Signed|Late|Planned/)
      cleanup()
    }
  }
})

it('exports exactly the selected summary and captions, blocks an empty selection and clears outdated share feedback', async () => {
  const share = vi.spyOn(browserReportService, 'share').mockRejectedValueOnce(new Error('Sharing unavailable')).mockResolvedValue()
  const props = renderDetails({ session: { ...session, clientSummary: 'Private client-facing summary.', exercisePlan: [
    { id: 'one', name: 'Selected Squat', videoAttached: true }, { id: 'two', name: 'Omitted Row', videoAttached: true },
  ] } })
  fireEvent.click(screen.getByRole('button', { name: 'Export Summary', exact: true }))
  const dialog = screen.getByRole('dialog', { name: 'Export Summary' })
  expect(within(dialog).getAllByRole('group').map(group => group.querySelector('legend').textContent)).toEqual(['Selected Videos', 'Select Client Facing Summary'])
  expect(dialog.querySelector('.helper, .notice')).toBeNull()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include video for Omitted Row' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include Client-Facing Summary' }))
  fireEvent.click(await shareButton())
  await screen.findByText('Sharing unavailable')
  expect(browserReportService.sessionFile.mock.lastCall[0]).toMatchObject({ summary: '', videos: [{ id: 'one' }] })
  expect(browserReportService.sessionFile.mock.lastCall[0].videos).toHaveLength(1)
  expect(props.onMarkWhatsAppOpened).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include video for Selected Squat' }))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Share PDF' })).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include Client-Facing Summary' }))
  fireEvent.click(await shareButton())
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(browserReportService.sessionFile.mock.lastCall[0]).toMatchObject({ summary: 'Private client-facing summary.', videos: [] })
  expect(share).toHaveBeenCalledTimes(2)
})

it('M4 keeps a blocked PDF share retryable with a download fallback and never marks WhatsApp sent', async () => {
  vi.spyOn(browserReportService, 'share').mockRejectedValue(new DOMException('Blocked', 'NotAllowedError'))
  const download = vi.spyOn(browserReportService, 'download').mockImplementation(() => {})
  const props = renderDetails()
  fireEvent.click(screen.getByRole('button', { name: 'Export Summary' }))
  const button = await shareButton()
  fireEvent.click(button)
  await screen.findByText('Your browser blocked file sharing. Try Open PDF or Download PDF.')
  expect(button).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Download PDF' }))
  expect(download.mock.calls[0][0]).toBe(browserReportService.share.mock.calls[0][0])
  expect(props.onMarkWhatsAppOpened).not.toHaveBeenCalled()
  expect(props.onAcknowledge).not.toHaveBeenCalled()
})

it('M4 shares the prepared session PDF on retry after cancellation without claiming a WhatsApp handoff', async () => {
  const share = vi.spyOn(browserReportService, 'share').mockRejectedValueOnce(new DOMException('Cancelled', 'AbortError')).mockResolvedValue()
  const props = renderDetails()
  fireEvent.click(screen.getByRole('button', { name: 'Export Summary' }))
  const button = await shareButton()
  fireEvent.click(button)
  await waitFor(() => expect(button).toBeEnabled())
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  fireEvent.click(button)
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(share).toHaveBeenCalledTimes(2)
  expect(share.mock.calls[0][0]).toMatchObject({ type: 'application/pdf', size: 8 })
  expect(share.mock.calls[1][0]).toBe(share.mock.calls[0][0])
  expect(browserReportService.sessionFile).toHaveBeenCalledTimes(1)
  expect(props.onMarkWhatsAppOpened).not.toHaveBeenCalled()
  expect(props.onAcknowledge).not.toHaveBeenCalled()
})
