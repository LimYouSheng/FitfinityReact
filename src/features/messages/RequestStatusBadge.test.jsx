import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import RequestStatusBadge from './RequestStatusBadge.jsx'
afterEach(cleanup)
it.each([['pending','Pending','amber'],['approved','Approved','green'],['rejected','Rejected','red'],['cancelled','Cancelled','neutral']])('renders readable %s approval status in its assigned colour', (status,label,tone)=>{
  render(<RequestStatusBadge message={{kind:'schedule_request',status,read:true}} />)
  expect(screen.getByText(label)).toHaveClass('status-badge',tone,'request-status')
})
it('does not display approval status for an ordinary informational message',()=>{
  const {container}=render(<RequestStatusBadge message={{kind:'renewal',status:'pending'}} />)
  expect(container).toBeEmptyDOMElement()
})
