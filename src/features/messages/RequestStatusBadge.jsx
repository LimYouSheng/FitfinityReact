import StatusBadge from '../../components/StatusBadge.jsx'

const STATES = {
  pending: { label: 'Pending', tone: 'amber' },
  approved: { label: 'Approved', tone: 'green' },
  rejected: { label: 'Rejected', tone: 'red' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

export default function RequestStatusBadge({ message }) {
  const isRequest = message.request || message.requestId || message.kind?.endsWith('_request') || message.kind === 'request_decision' || message.kind === 'remuneration_approval'
  const state = isRequest && STATES[message.status]
  if (!state) return null
  return <StatusBadge tone={state.tone} className="request-status"><span className="request-status-dot" aria-hidden="true" />{state.label}</StatusBadge>
}
