import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MessagesPage from './MessagesPage.jsx'
const message = {id:'row-test',title:'Availability request',body:'Review availability.',recipientRole:'owner',kind:'availability_request',status:'pending',read:false,createdAt:'2026-09-05T09:00:00Z'}
function show(markRead) {
  history.replaceState({}, '', '/')
  return render(<MessagesPage user={{id:'owner',role:'owner'}} messages={[message]} onMarkRead={markRead} onOpenRelated={()=>{}} />)
}
afterEach(()=>{cleanup();history.replaceState({}, '', '/')})
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
