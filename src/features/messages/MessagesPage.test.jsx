import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import RenewalDismissal from './RenewalDismissal.jsx'
import userEvent from '@testing-library/user-event'
import MessagesPage, { MessageInbox } from './MessagesPage.jsx'
const message = {id:'row-test',title:'Availability request',body:'Review availability.',recipientRole:'owner',kind:'availability_request',status:'pending',read:false,createdAt:'2026-09-05T09:00:00Z'}
function show(markRead) {
  history.replaceState({}, '', '/')
  return render(<MessagesPage user={{id:'owner',role:'owner'}} messages={[message]} onMarkRead={markRead} onOpenRelated={()=>{}} />)
}
beforeEach(() => { vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} })) })
afterEach(()=>{cleanup();vi.unstubAllGlobals();history.replaceState({}, '', '/')})
it('opens the message from time, approval status, row space and either keyboard-accessible button',async()=>{
  for(const target of ['time','status','row','read','title']){
    const markRead=vi.fn().mockResolvedValue(undefined),user=userEvent.setup()
    const {container}=show(markRead)
    const heading = screen.getByRole('heading', { name: 'Messages', exact: true })
    expect(heading.nextElementSibling).toHaveTextContent('1 new')
    expect(heading.parentElement).toHaveClass('heading-with-status')
    if(target==='time')await user.click(container.querySelector('time'))
    if(target==='status')await user.click(screen.getByText('Pending',{exact:true}))
    if(target==='row')await user.click(container.querySelector('article'))
    if(target==='read')await user.click(screen.getByRole('button',{name:'Unread Availability request',exact:true}))
    if(target==='title'){
      screen.getByRole('button',{name:'Open Availability request',exact:true}).focus()
      await user.keyboard('{Enter}')
    }
    expect(await screen.findByRole('dialog',{name:message.title})).toBeVisible()
    expect(markRead).toHaveBeenCalledExactlyOnceWith(message.id)
    expect(history.state.fitfinityDepth).toBe(1)
    cleanup()
  }
})
it('coalesces repeated clicks while marking the message read into one dialog and history entry',async()=>{
  let finish
  const markRead=vi.fn(()=>new Promise(resolve=>{finish=resolve}))
  const {container}=show(markRead)
  fireEvent.click(container.querySelector('time'))
  fireEvent.click(screen.getByText('Pending',{exact:true}))
  expect(markRead).toHaveBeenCalledTimes(1)
  await act(async()=>finish())
  expect(screen.getAllByRole('dialog',{name:message.title})).toHaveLength(1)
  expect(history.state.fitfinityDepth).toBe(1)
})
it.each(['unmount', 'category'])('does not open a delayed message after a %s navigation', async change => {
  let finish
  const view = show(() => new Promise(resolve => { finish = resolve }))
  fireEvent.click(screen.getByRole('button', { name: 'Open Availability request', exact: true }))
  if (change === 'unmount') view.unmount()
  history.pushState({ fitfinityDepth: 2 }, '', '/#/messages/renewals')
  await act(async () => finish())
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(history.state).toEqual({ fitfinityDepth: 2 })
})
it('coalesces repeated popup Close clicks into one native Back', async () => {
  show(vi.fn().mockResolvedValue(undefined))
  fireEvent.click(screen.getByRole('button', { name: 'Open Availability request', exact: true }))
  await screen.findByRole('dialog')
  const back = vi.spyOn(history, 'back').mockImplementation(() => {})
  fireEvent.click(screen.getByRole('button', { name: 'Close message', exact: true }))
  fireEvent.click(screen.getByRole('button', { name: 'Close message', exact: true }))
  expect(back).toHaveBeenCalledTimes(1)
  back.mockRestore()
})
it('marks the selected message unread once and closes the popup after persistence succeeds', async () => {
  history.replaceState({fitfinityOverlay:'message',messageId:message.id}, '', '/')
  let finish
  const markUnread = vi.fn(() => new Promise(resolve => { finish = resolve }))
  const back = vi.spyOn(history, 'back').mockImplementation(() => {})
  render(<MessagesPage user={{id:'owner',role:'owner'}} messages={[{...message,read:true}]} onMarkUnread={markUnread} />)
  fireEvent.click(screen.getByRole('button', {name:'Mark as Unread',exact:true}))
  fireEvent.click(screen.getByRole('button', {name:'Marking…',exact:true}))
  expect(markUnread).toHaveBeenCalledExactlyOnceWith(message.id)
  expect(screen.getByRole('dialog')).toBeVisible()
  await act(async () => finish())
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(back).toHaveBeenCalledTimes(1)
  back.mockRestore()
})
it('keeps the popup open with a retryable error when marking unread fails', async () => {
  history.replaceState({fitfinityOverlay:'message',messageId:message.id}, '', '/')
  const markUnread = vi.fn().mockRejectedValue(new Error('Could not save unread status.'))
  render(<MessagesPage user={{id:'owner',role:'owner'}} messages={[{...message,read:true}]} onMarkUnread={markUnread} />)
  await userEvent.click(screen.getByRole('button',{name:'Mark as Unread',exact:true}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not save unread status.')
  expect(screen.getByRole('dialog')).toBeVisible()
  expect(screen.getByRole('button',{name:'Mark as Unread',exact:true})).toBeEnabled()
})

it('category buttons combine with search and reset pagination without marking messages read', async () => {
  const user = userEvent.setup(), markRead = vi.fn()
  const renewals = Array.from({ length: 12 }, (_, index) => ({ ...message, id: `r${index}`, title: `Renewal ${index}`, kind: 'renewal' }))
  render(<MessagesPage user={{ id: 'owner', role: 'owner' }} messages={[...renewals, { ...message, id: 's1', kind: 'session', title: 'Morning session' }]} onMarkRead={markRead} />)
  const categories = within(screen.getByRole('group', { name: 'Message categories' }))
  await user.click(categories.getByRole('button', { name: 'Renewals', exact: true }))
  expect(screen.getByLabelText('Message list').querySelectorAll('article')).toHaveLength(10)
  await user.click(screen.getByRole('button', { name: 'Next', exact: true }))
  expect(screen.getByLabelText('Message list').querySelectorAll('article')).toHaveLength(2)
  await user.click(categories.getByRole('button', { name: 'Sessions', exact: true }))
  expect(screen.getByRole('button', { name: 'Open Morning session' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Previous', exact: true })).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('Search messages'), 'Renewal')
  expect(screen.getByText('No messages match these filters.')).toBeVisible()
  await user.click(categories.getByRole('button', { name: 'Renewals', exact: true }))
  expect(screen.getByLabelText('Message list').querySelectorAll('article')).toHaveLength(10)
  expect(markRead).not.toHaveBeenCalled()
})

it('dashboard renewals are recipient-scoped, limited to a preview and use the shared retryable opening flow', async () => {
  const user = userEvent.setup()
  const trainer = { id: 'trainer-user', role: 'trainer', trainerId: 't1' }
  const markRead = vi.fn().mockRejectedValueOnce(new Error('Read state unavailable')).mockResolvedValue(undefined)
  const records = Array.from({ length: 5 }, (_, index) => ({ ...message, id: `r${index}`, kind: 'renewal', title: `Renewal ${index}`, recipientTrainerId: 't1' }))
  records[0].title = 'Renewal 0 · A full package renewal title with scheduling preferences and continued strength coaching goals'
  const { rerender } = render(<MessageInbox embedded category="renewals" user={trainer} messages={[...records, { ...message, kind: 'renewal', title: 'Another trainer', recipientTrainerId: 't2' }]} onMarkRead={markRead} />)
  const list = screen.getByLabelText('Renewal messages')
  expect(list.querySelectorAll('article')).toHaveLength(3)
  for (const row of list.querySelectorAll('article')) {
    expect(within(row).getAllByRole('button')).toHaveLength(2)
    expect(row.querySelector('time, .message-approval-status')).toBeNull()
  }
  expect(list.querySelector('.message-title-head')).toBeNull()
  expect(within(list).queryByText(message.body)).not.toBeInTheDocument()
  const openRenewal = within(list).getByRole('button', { name: `Open ${records[0].title}`, exact: true })
  expect(openRenewal).toHaveTextContent(records[0].title)
  expect(openRenewal).toHaveAttribute('title', records[0].title)
  expect(screen.getByRole('status', { name: 'Total renewal follow-ups' }).querySelector('.renewal-count')).toHaveTextContent(/^5$/)
  expect(screen.queryByText('Another trainer')).not.toBeInTheDocument()
  expect(screen.queryByRole('group', { name: 'Message categories' })).not.toBeInTheDocument()
  await user.click(openRenewal)
  expect(await screen.findByRole('alert')).toHaveTextContent('Read state unavailable')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  openRenewal.focus()
  await user.keyboard('{Enter}')
  const dialog = await screen.findByRole('dialog', { name: records[0].title, exact: true })
  expect(dialog).toBeVisible()
  expect(within(dialog).getByRole('heading', { name: records[0].title })).toBeVisible()
  expect(within(dialog).getByText(message.body)).toBeVisible()
  expect(dialog.querySelector('.message-detail-meta')).toHaveTextContent('2026')
  expect(markRead).toHaveBeenCalledTimes(2)
  expect(history.state.fitfinityDepth).toBe(1)
  act(() => {
    history.replaceState({}, '', '/')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(within(list).getByRole('button', { name: `Unread ${records[0].title}`, exact: true }))
  expect(await screen.findByRole('dialog', { name: records[0].title, exact: true })).toBeVisible()
  expect(markRead).toHaveBeenCalledTimes(3)
  rerender(<MessageInbox embedded category="renewals" user={trainer} messages={records.map(item => ({ ...item, read: true }))} />)
  expect(within(list).getByRole('button', { name: `Read ${records[0].title}`, exact: true })).toBeVisible()
  expect(screen.getByRole('status', { name: 'Total renewal follow-ups' }).querySelector('.renewal-count')).toHaveTextContent(/^5$/)
  rerender(<MessageInbox embedded category="renewals" user={trainer} messages={[]} />)
  expect(screen.getByRole('status', { name: 'Total renewal follow-ups' }).querySelector('.renewal-count')).toHaveTextContent(/^0$/)
  expect(screen.getByText('No renewal messages.')).toBeVisible()
})

it('uses the shared profile dropdown on phones, updating its selected label and closing after filtering', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  const user = userEvent.setup()
  render(<MessagesPage user={{ id: 'owner', role: 'owner' }} messages={[message, { ...message, id: 'renewal', kind: 'renewal', title: 'Client renewal' }]} />)
  const categories = screen.getByRole('group', { name: 'Message categories' })
  const menu = categories.querySelector('.profile-menu'), summary = menu.querySelector('summary')
  expect(summary).toHaveTextContent('All')
  expect(menu).not.toHaveAttribute('open')
  await user.click(summary)
  await user.click(within(categories).getByRole('button', { name: 'Renewals', exact: true }))
  expect(summary).toHaveTextContent('Renewals')
  expect(menu).not.toHaveAttribute('open')
  expect(menu.querySelector('button[aria-current="true"]')).toHaveTextContent('Renewals')
  expect(screen.getByRole('button', { name: 'Open Client renewal' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Open Availability request' })).not.toBeInTheDocument()
})

const renewal = { id: 'renewal-cleanup', kind: 'renewal', clientId: 'c1', recipientRole: 'owner', recipientTrainerId: 't1',
  title: 'Renewal follow-up: Amanda Lim', body: 'Two sessions remaining.', createdAt: '2026-09-08T04:00:00Z', read: true, renewalStatus: 'active' }
const renewalClient = { id: 'c1', trainerId: 't1' }
function showRenewals(overrides = {}) {
  const props = { user: { id: 'u-owner', role: 'owner' }, messages: [renewal], clients: [renewalClient],
    category: 'renewals', onDismissRenewal: vi.fn().mockResolvedValue({ renewalStatus: 'removed' }), onMarkRead: vi.fn(), ...overrides }
  const view = render(<ActionConfirmationProvider><MessageInbox {...props} /></ActionConfirmationProvider>)
  return { ...view, props }
}
it('renewal cleanup filters completed follow-ups from the dashboard count and keeps them in All history', () => {
  const messages = [renewal, { ...renewal, id: 'renewed', title: 'Already renewed', renewalStatus: 'renewed' }, { ...renewal, id: 'removed', title: 'Previously removed', renewalStatus: 'removed' }]
  showRenewals({ embedded: true, messages })
  expect(screen.getByLabelText('Total renewal follow-ups')).toHaveTextContent('1')
  expect(screen.getByLabelText('Renewal messages').querySelectorAll('article')).toHaveLength(1)
  cleanup(); showRenewals({ category: 'all', messages })
  expect(screen.getByLabelText('Message list').querySelectorAll('article')).toHaveLength(3)
  expect(screen.getByText('Renewed', { exact: true })).toBeVisible()
  expect(screen.getByText('Removed from renewals', { exact: true })).toBeVisible()
})
it('renewal cleanup confirms row removal without opening the message and Cancel preserves the list', async () => {
  const { props } = showRenewals()
  fireEvent.click(screen.getByRole('button', { name: `Remove ${renewal.title} from renewals` }))
  const confirm = within(await screen.findByRole('dialog', { name: 'Remove renewal follow-up?' }))
  expect(screen.queryByRole('dialog', { name: renewal.title })).not.toBeInTheDocument()
  expect(props.onMarkRead).not.toHaveBeenCalled()
  fireEvent.click(confirm.getByRole('button', { name: 'Cancel', exact: true }))
  expect(props.onDismissRenewal).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: `Open ${renewal.title}` })).toBeVisible()
})
it('renewal cleanup removes from the popup once and closes only its own history entry', async () => {
  let finish
  const onDismissRenewal = vi.fn(() => new Promise(resolve => { finish = resolve }))
  const { props } = showRenewals({ embedded: true, onDismissRenewal })
  const preview = within(screen.getByLabelText('Renewal messages'))
  expect(preview.getAllByRole('button')).toHaveLength(2)
  expect(preview.queryByRole('button', { name: `Remove ${renewal.title} from renewals` })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: `Open ${renewal.title}` }))
  const popup = within(await screen.findByRole('dialog', { name: renewal.title }))
  const back = vi.spyOn(history, 'back').mockImplementation(() => {})
  fireEvent.click(popup.getByRole('button', { name: `Remove ${renewal.title} from renewals` }))
  const confirm = within(await screen.findByRole('dialog', { name: 'Remove renewal follow-up?' }))
  await act(async () => fireEvent.click(confirm.getByRole('button', { name: 'Remove', exact: true })))
  expect(popup.getByRole('button', { name: `Remove ${renewal.title} from renewals` })).toBeDisabled()
  await act(async () => finish({ renewalStatus: 'removed' }))
  expect(props.onDismissRenewal).toHaveBeenCalledExactlyOnceWith(renewal.id)
  expect(screen.queryByRole('dialog', { name: renewal.title })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: `Open ${renewal.title}` })).not.toBeInTheDocument()
  expect(back).toHaveBeenCalledTimes(1); back.mockRestore()
})
it('renewal cleanup keeps a failed removal retryable and hides only after confirmed success', async () => {
  const onDismissRenewal = vi.fn().mockRejectedValueOnce(new Error('Storage full')).mockResolvedValueOnce({ renewalStatus: 'removed' })
  showRenewals({ onDismissRenewal })
  for (let attempt = 0; attempt < 2; attempt++) {
    fireEvent.click(screen.getByRole('button', { name: `Remove ${renewal.title} from renewals` }))
    const confirm = within(await screen.findByRole('dialog', { name: 'Remove renewal follow-up?' }))
    await act(async () => fireEvent.click(confirm.getByRole('button', { name: 'Remove', exact: true })))
    if (attempt === 0) {
      expect(screen.getByRole('alert')).toHaveTextContent('Storage full')
      expect(screen.getByRole('button', { name: `Open ${renewal.title}` })).toBeVisible()
    }
  }
  expect(onDismissRenewal).toHaveBeenCalledTimes(2)
  expect(screen.queryByRole('button', { name: `Open ${renewal.title}` })).not.toBeInTheDocument()
})
it.each(['space', 'deadline', 'reason', 'expired', 'undone'])('message row hit area opens from Undo %s without invoking Undo', async target => {
  const now = Date.now(), onUndo = vi.fn()
  const item = { ...message, undo: { id: 'row-mutation', expiresAt: new Date(now + 86400000).toISOString(), count: 1,
    status: target === 'expired' ? 'expired' : target === 'undone' ? 'undone' : target === 'reason' ? 'blocked' : 'available',
    ...(target === 'reason' ? { reason: 'Later session change.' } : {}) } }
  const props = { user: { id: 'owner', role: 'owner' }, messages: [item], onMarkRead: vi.fn().mockResolvedValue(), onUndo }
  const { container } = render(<ActionConfirmationProvider><MessageInbox {...props} /></ActionConfirmationProvider>)
  const row = within(container.querySelector('article'))
  const area = container.querySelector('.message-undo-action')
  const node = target === 'space' ? area : target === 'deadline' ? row.getByText(/^Until /) :
    target === 'reason' ? row.getByText('Later session change.') : target === 'expired' ? row.getByText('Undo expired') : row.getByText('Undone')
  fireEvent.click(node)
  expect(await screen.findByRole('dialog', { name: item.title, exact: true })).toBeVisible()
  expect(props.onMarkRead).toHaveBeenCalledExactlyOnceWith(item.id)
  expect(onUndo).not.toHaveBeenCalled()
  expect(screen.queryByRole('dialog', { name: 'Undo session change?' })).not.toBeInTheDocument()
})
it('message row hit area opens from Remove section space and retry feedback', async () => {
  for (const target of ['space', 'error']) {
    const { props, container } = showRenewals({ messages: [{ ...renewal, read: false }], onDismissRenewal: vi.fn().mockRejectedValue(new Error('Removal unavailable')) })
    if (target === 'error') {
      fireEvent.click(screen.getByRole('button', { name: `Remove ${renewal.title} from renewals` }))
      fireEvent.click(within(await screen.findByRole('dialog', { name: 'Remove renewal follow-up?' })).getByRole('button', { name: 'Remove', exact: true }))
      await screen.findByRole('alert')
    }
    fireEvent.click(target === 'space' ? container.querySelector('.renewal-remove-action') : screen.getByRole('alert'))
    expect(await screen.findByRole('dialog', { name: renewal.title, exact: true })).toBeVisible()
    expect(props.onMarkRead).toHaveBeenCalledExactlyOnceWith(renewal.id)
    expect(props.onDismissRenewal).toHaveBeenCalledTimes(target === 'error' ? 1 : 0)
    cleanup(); history.replaceState({}, '', '/')
  }
})
it('message row hit area keeps enabled and disabled Undo buttons separate from opening the message', async () => {
  for (const status of ['available', 'blocked']) {
    const onMarkRead = vi.fn(), onUndo = vi.fn()
    const item = { ...message, undo: { id: 'button-mutation', count: 1, status, expiresAt: new Date(Date.now() + 86400000).toISOString() } }
    render(<ActionConfirmationProvider><MessageInbox user={{ id: 'owner', role: 'owner' }} messages={[item]} onMarkRead={onMarkRead} onUndo={onUndo} /></ActionConfirmationProvider>)
    fireEvent.click(screen.getByRole('button', { name: `Undo ${item.title}`, exact: true }))
    expect(onMarkRead).not.toHaveBeenCalled(); expect(onUndo).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog', { name: item.title, exact: true })).not.toBeInTheDocument()
    if (status === 'available') {
      const dialog = within(await screen.findByRole('dialog', { name: 'Undo session change?' }))
      fireEvent.click(dialog.getByRole('button', { name: 'Cancel', exact: true }))
    } else expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    cleanup()
  }
})
it('renewal cleanup hides Remove after trainer reassignment while preserving the historical message', () => {
  showRenewals({ user: { id: 'u-marcus', role: 'trainer', trainerId: 't1' }, clients: [{ ...renewalClient, trainerId: 't2' }] })
  expect(screen.getByRole('button', { name: `Open ${renewal.title}` })).toBeVisible()
  expect(screen.queryByRole('button', { name: `Remove ${renewal.title} from renewals` })).not.toBeInTheDocument()
})
it('renewal cleanup does not submit a confirmation after its initiating control unmounts', async () => {
  const onDismiss = vi.fn()
  const view = render(<ActionConfirmationProvider><RenewalDismissal message={renewal} onDismiss={onDismiss} /></ActionConfirmationProvider>)
  fireEvent.click(screen.getByRole('button', { name: `Remove ${renewal.title} from renewals` }))
  const confirm = within(await screen.findByRole('dialog', { name: 'Remove renewal follow-up?' }))
  view.rerender(<ActionConfirmationProvider>{null}</ActionConfirmationProvider>)
  await act(async () => fireEvent.click(confirm.getByRole('button', { name: 'Remove', exact: true })))
  expect(onDismiss).not.toHaveBeenCalled()
})
