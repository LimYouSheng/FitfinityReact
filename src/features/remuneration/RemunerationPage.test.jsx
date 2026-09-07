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
  return <RemunerationPage {...props} onApprove={(...args) => runAction(() => props.onApprove(...args), { message: 'Remuneration approved.' })} />
}
function show(props) {
  return render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider><NotifiedRemuneration user={owner} data={payFixture()} cycleKey="2026-09" onNavigate={()=>{}} onOpenSession={()=>{}} {...props}/></EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
}
afterEach(cleanup)
it('hides amounts until requested and scopes trainer rows and deep links to the signed-in trainer', async () => {
  show({user:{id:'trainer',role:'trainer',trainerId:'t1'}})
  expect(screen.getByRole('button',{name:'View remuneration for Marcus'})).toBeVisible()
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
it('keeps the cycle selector on the list and shows only the fixed cycle in a trainer breakdown', async () => {
  const navigate = vi.fn(), back = vi.fn()
  show({onNavigate:navigate})
  expect(screen.getByRole('combobox',{name:'Pay cycle'})).toBeVisible()
  expect(document.querySelector('.page-head p')).toBeNull()
  expect(screen.getByRole('button',{name:'Show remuneration amounts'})).toHaveClass('remuneration-money-toggle')
  cleanup()
  show({trainerId:'t1',onBack:back})
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.getByText('16 Aug 2026 – 15 Sept 2026')).toBeVisible()
  await userEvent.click(screen.getByRole('button',{name:'Back to Pay Cycle'}))
  expect(back).toHaveBeenCalledTimes(1)
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
