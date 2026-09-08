import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
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
  const { rerender } = render(<MessageInbox embedded category="renewals" user={trainer} messages={[...records, { ...message, kind: 'renewal', title: 'Another trainer', recipientTrainerId: 't2' }]} onMarkRead={markRead} />)
  const list = screen.getByLabelText('Renewal messages')
  expect(list.querySelectorAll('article')).toHaveLength(3)
  expect(screen.getByRole('status', { name: 'Total renewal follow-ups' }).querySelector('.renewal-count')).toHaveTextContent(/^5$/)
  expect(screen.queryByText('Another trainer')).not.toBeInTheDocument()
  expect(screen.queryByRole('group', { name: 'Message categories' })).not.toBeInTheDocument()
  await user.click(within(list).getByRole('button', { name: 'Open Renewal 0' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Read state unavailable')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(within(list).getByRole('button', { name: 'Open Renewal 0' }))
  expect(await screen.findByRole('dialog', { name: 'Renewal 0' })).toBeVisible()
  expect(markRead).toHaveBeenCalledTimes(2)
  rerender(<MessageInbox embedded category="renewals" user={trainer} messages={records.map(item => ({ ...item, read: true }))} />)
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
