import { cycleTrainers, remunerationCycles, payCycle } from '../../app/remuneration.js'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import { NotificationProvider, useNotifications } from '../../components/NotificationProvider.jsx'
import RemunerationPage from './RemunerationPage.jsx'
import { payFixture } from '../../test/fixtures/remuneration.js'
const owner = {id:'owner',role:'owner'}
function NotifiedRemuneration(props) {
  const { runAction } = useNotifications()
  const data = props.data, policy = data.settings
  const views = props.views ?? remunerationCycles(data, props.user, props.now).map(key => ({ key, cycle: payCycle(key, policy.remuneration), trainers: cycleTrainers(data, key, props.user, props.now) }))
  return <RemunerationPage {...props} views={views} policy={policy} onApprove={(...args) => runAction(() => props.onApprove(...args), { message: 'Remuneration approved.' })} />
}
function show(props) {
  return render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider><NotifiedRemuneration user={owner} data={payFixture()} cycleKey="2026-09" onNavigate={()=>{}} onOpenSession={()=>{}} {...props}/></EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
}
afterEach(cleanup)
it('hides amounts until requested and scopes trainer rows and deep links to the signed-in trainer', async () => {
  show({user:{id:'trainer',role:'trainer',trainerId:'t1'}})
  expect(screen.queryByRole('button',{name:'View remuneration for Marcus'})).not.toBeInTheDocument()
  expect(screen.getByLabelText('Cycle session breakdown')).toHaveTextContent('Amanda')
  expect(screen.queryByRole('table',{name:'Trainer remuneration'})).not.toBeInTheDocument()
  expect(document.querySelector('.page-head p')).toBeNull()
  expect(screen.getByRole('button',{name:'Show remuneration amounts'})).toHaveClass('remuneration-money-toggle')
  expect(screen.queryByRole('button',{name:'View remuneration for Rachel'})).not.toBeInTheDocument()
  expect(screen.queryByText(/80\.00/)).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button',{name:'Show remuneration amounts'}))
  expect(screen.getAllByText(/80\.00/).length).toBeGreaterThan(0)
  cleanup()
  show({user:{id:'trainer',role:'trainer',trainerId:'t1'},trainerId:'t2'})
  expect(screen.getByText('This remuneration record is unavailable for your account.')).toBeVisible()
  expect(screen.queryByText('Rachel')).not.toBeInTheDocument()
})
it('shows a retryable error if the automatic total changes before approval', async () => {
  const approve = vi.fn().mockRejectedValue(new Error('Rates changed. Refresh and review.'))
  const db = payFixture(); db.sessions[0].date = '2020-08-20'
  show({data:db,cycleKey:'2020-09',trainerId:'t1',onApprove:approve})
  await userEvent.click(screen.getByRole('button',{name:'Show remuneration amounts'}))
  await userEvent.click(screen.getByRole('button',{name:'Approve Remuneration',exact:true}))
  const dialog = screen.getByRole('dialog',{name:'Approve trainer remuneration?'})
  expect(approve).not.toHaveBeenCalled()
  await userEvent.click(within(dialog).getByRole('button',{name:'Approve Remuneration',exact:true}))
  expect(await screen.findAllByRole('alert')).toHaveLength(2)
  expect(document.querySelector('.notification-error')).toHaveTextContent('Rates changed.')
  expect(screen.getByRole('button',{name:'Approve Remuneration',exact:true})).toBeEnabled()
})
it('requires visible amounts and confirmation before approving a closed reviewed cycle', async () => {
  // A historical fixture keeps this test independent of the machine date.
  const db = payFixture()
  db.sessions[0].date = '2020-08-20'
  const approve = vi.fn().mockResolvedValue(undefined)
  show({data:db,cycleKey:'2020-09',trainerId:'t1',onApprove:approve})
  await userEvent.click(screen.getByRole('button',{name:'Approve Remuneration',exact:true}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(approve).not.toHaveBeenCalled()
  expect(screen.getByRole('status')).toHaveTextContent('Show amounts to review the total before approving.')
  expect(screen.getByRole('status').closest('.notification-info')).not.toBeNull()
  expect(document.querySelector('.remuneration-page')).not.toHaveTextContent('Show amounts to review the total before approving.')
  await userEvent.click(screen.getByRole('button',{name:'Show remuneration amounts'}))
  await userEvent.click(screen.getByRole('button',{name:'Approve Remuneration',exact:true}))
  const dialog = screen.getByRole('dialog',{name:'Approve trainer remuneration?'})
  expect(dialog).toHaveTextContent(/80\.00/)
  expect(approve).not.toHaveBeenCalled()
  await userEvent.click(within(dialog).getByRole('button',{name:'Approve Remuneration',exact:true}))
  expect(approve).toHaveBeenCalledTimes(1)
  expect(await screen.findByRole('status')).toHaveTextContent('Remuneration approved.')
  expect(screen.getByRole('status').closest('.notification-success')).not.toBeNull()
  expect(document.querySelector('.remuneration-page [role="status"]')).toBeNull()
})
it('opens the paginated pay-cycle list before the owner trainer list and fixed trainer breakdown', async () => {
  const navigate = vi.fn()
  show({ cycleKey: undefined, onNavigate: navigate })
  expect(screen.getByLabelText('Pay cycles')).toBeVisible()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.queryByRole('table', { name: 'Trainer remuneration' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'View pay cycle 2026-09' }))
  expect(navigate).toHaveBeenCalledExactlyOnceWith('remuneration/2026-09')
  cleanup()
  show({ onNavigate: navigate })
  expect(screen.getByRole('table', { name: 'Trainer remuneration' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'View remuneration for Marcus' }))
  expect(navigate).toHaveBeenLastCalledWith('remuneration/2026-09/t1')
  cleanup()
  show({ trainerId: 't1' })
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.getByText('16 Aug 2026 – 15 Sept 2026')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Back to Pay Cycle' })).not.toBeInTheDocument()
})

it('lists the current cycle first, paginates history and excludes future bookings for both roles', async () => {
  const data = payFixture(), now = new Date('2026-09-09T04:00:00Z')
  data.sessions.push({ ...data.sessions[0], id: 'future', date: '2026-12-20', status: 'planned', acknowledgement: null })
  data.sessions.push(...Array.from({ length: 12 }, (_, index) => ({ ...data.sessions[0], id: `older-${index}`, date: new Date(Date.UTC(2026, 7 - index, 1)).toISOString().slice(0, 10) })))
  const keys = remunerationCycles(data, owner, now)
  for (const user of [owner, { id: 'trainer', role: 'trainer', trainerId: 't1' }]) {
    const views = keys.map((key, index) => ({ key, isCurrent: index === 0, cycle: payCycle(key, data.settings.remuneration), trainers: cycleTrainers(data, key, user, now) }))
    const navigate = vi.fn()
    show({ views, user, cycleKey: undefined, onNavigate: navigate })
    const list = screen.getByLabelText('Pay cycles')
    expect(list.querySelectorAll('article')).toHaveLength(10)
    expect(list.querySelector('article')).toHaveAttribute('data-cycle-key', '2026-09')
    expect(list.querySelector('article')).toHaveTextContent('Current')
    expect(screen.queryByRole('button', { name: 'View pay cycle 2027-01' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Next', exact: true }))
    expect(list.querySelectorAll('article')).toHaveLength(3)
    await userEvent.click(within(list).getAllByRole('button')[0])
    expect(navigate).toHaveBeenCalledExactlyOnceWith(`remuneration/${keys[10]}`)
    cleanup()
    show({ views, user, cycleKey: '2026-09' })
    expect(document.querySelector('.remuneration-totals')).toHaveTextContent('Completed sessions1')
    expect(Boolean(document.querySelector('.remuneration-session'))).toBe(user.role === 'trainer')
    cleanup()
    show({ views, user, cycleKey: '2027-01' })
    expect(screen.getByText('This remuneration record is unavailable for your account.')).toBeVisible()
    cleanup()
  }
})
it('shows only the client, date, amount and View Session in each compact row and opens that session', async () => {
  const open = vi.fn()
  const {container} = show({trainerId:'t1',onOpenSession:open})
  const row = container.querySelector('.remuneration-session')
  expect(row).toHaveTextContent('Amanda')
  expect(row.querySelector('time')).toHaveTextContent('20 Aug 2026')
  expect(row.querySelector('dl')).toBeNull()
  expect(within(row).queryByRole('combobox')).not.toBeInTheDocument()
  expect(row).not.toHaveTextContent(/Client type|Duration|Acknowledgement|18:00|Rate band/)
  expect(row.querySelector('.remuneration-session-rate')).toHaveTextContent('••••')
  await userEvent.click(screen.getByRole('button',{name:'Show remuneration amounts'}))
  expect(row.querySelector('.remuneration-session-rate')).toHaveTextContent('80.00')
  await userEvent.click(within(row).getByRole('button',{name:/View Session/}))
  expect(open).toHaveBeenCalledExactlyOnceWith('pay1')
})
it('shows In progress before cycle close and Pending review until every session is acknowledged', () => {
  const db = payFixture()
  db.sessions.push({ ...db.sessions[0], id: 'missed-session', status: 'planned', acknowledgement: null })
  for (const user of [owner, { id: 'trainer', role: 'trainer', trainerId: 't1' }]) {
    show({ data: db, user, trainerId: 't1', now: new Date('2026-09-15T15:59:59Z') })
    expect(document.querySelector('.remuneration-section-head')).toHaveTextContent('In progress')
    expect(screen.queryByText(/Approval opens after/)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.remuneration-session')).toHaveLength(2)
    if (user.role === 'owner') expect(screen.getByRole('button', { name: 'Approve Remuneration', exact: true })).toBeDisabled()
    cleanup()
    show({ data: db, user, trainerId: 't1', now: new Date('2026-09-15T16:00:00Z') })
    expect(document.querySelector('.remuneration-section-head')).toHaveTextContent('Pending review')
    expect(screen.getByRole('alert')).toHaveTextContent('1 session(s) need attention')
    if (user.role === 'owner') expect(screen.getByRole('button', { name: 'Approve Remuneration', exact: true })).toBeDisabled()
    else expect(screen.queryByRole('button', { name: 'Approve Remuneration', exact: true })).not.toBeInTheDocument()
    cleanup()
  }
  Object.assign(db.sessions[1], { status: 'completed', acknowledgement: { method: 'late_no_show', recordedAt: '2026-09-15T15:59:59Z' } })
  delete db.sessions[0].outcome
  delete db.sessions[1].outcome
  show({ data: db, trainerId: 't1', now: new Date('2026-09-15T16:00:00Z') })
  expect(document.querySelector('.remuneration-section-head')).toHaveTextContent('Pending approval')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve Remuneration', exact: true })).toBeEnabled()
})
