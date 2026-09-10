import usePageState from '../../hooks/usePageState.js'
import RequestStatusBadge from './RequestStatusBadge.jsx'
import RequestReview from './RequestReview.jsx'
import { requestTypes } from '../../app/requestTypes.js'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import StatusBadge from '../../components/StatusBadge.jsx'
import Panel from '../../components/Panel.jsx'
import useSwipeBack from '../../hooks/useSwipeBack.js'
import ModalPortal from '../../components/ModalPortal.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import DateFilterField from '../../components/DateFilterField.jsx'
import ProfileNavigation from '../../components/ProfileNavigation.jsx'
import usePagination from '../../hooks/usePagination.js'
import { filterMessages, messageCategory, MESSAGE_CATEGORIES } from './messageFilters.js'
import { orderMessages } from './messageOrdering.js'
import { relatedMessageLinks } from './messageLinks.js'
import { formatTimestamp } from '../../utils/date.js'

function visibleTo(user, message) {
  if (message.recipientUserId === user.id) return true
  if (message.recipientRole === user.role) return true
  if (user.role === 'trainer' && message.recipientTrainerId === user.trainerId) return true
  return false
}

export default function MessagesPage({ category, onCategoryChange, ...props }) {
  const [localCategory, setLocalCategory] = useState('all')
  const unread = props.messages.filter(message => visibleTo(props.user, message) && !message.read).length
  return <>
    <div className="page-head">
      <div><span className="eyebrow">Updates</span><h1>Messages</h1></div>
      <StatusBadge tone="blue">{unread} new</StatusBadge>
    </div>
    <MessageInbox {...props} category={category ?? localCategory} onCategoryChange={onCategoryChange ?? setLocalCategory} />
  </>
}

// One list, dialog, read/unread flow and history owner for both entry points.
export function MessageInbox({
  embedded = false,
  category = 'all',
  onCategoryChange,
  onViewAll,
  user,
  timeZone,
  messages,
  clients = [],
  trainers = [],
  sessions = [],
  exercises = [],
  contentEntries = [],
  packages = [],
  onMarkRead,
  onMarkUnread,
  onResolveRequest,
  onCancelRequest,
  onOpenRelated,
}) {
  const [selectedId, setSelectedId] = useState(() =>
    history.state?.fitfinityOverlay === 'message'
      ? history.state?.messageId ?? null
      : null
  )
  const openingMessage = useRef(false)
  const mounted = useRef(false)
  const closingMessage = useRef(false)
  const markingUnread = useRef(false)
  const [unreadBusy, setUnreadBusy] = useState(false)
  const [messageError, setMessageError] = useState('')
  const [query, setQuery] = usePageState('MessagesPage.query', '')
  const [fromDate, setFromDate] = usePageState('MessagesPage.fromDate', '')
  const [toDate, setToDate] = usePageState('MessagesPage.toDate', '')

  const userMessages = useMemo(
    () => orderMessages(messages.filter(message => visibleTo(user, message))),
    [messages, user],
  )
  const visible = useMemo(
    () => filterMessages(userMessages, { query, from: fromDate, to: toDate, category, timeZone }),
    [category, fromDate, query, toDate, userMessages, timeZone],
  )

  const selected = userMessages.find(message => message.id === selectedId) ?? null
  const relatedLinks = useMemo(
    () => relatedMessageLinks(selected, { user, clients, trainers, sessions, exercises, packages, contentEntries }),
    [clients, contentEntries, exercises, packages, selected, sessions, trainers, user],
  )
  const pagination = usePagination(visible, `${user.id}|${category}|${query}|${fromDate}|${toDate}`)

  useEffect(() => {
    mounted.current = true
    const syncOverlay = () => {
      closingMessage.current = false
      if (history.state?.fitfinityOverlay === 'message') {
        setSelectedId(history.state.messageId ?? null)
      } else {
        setSelectedId(null)
      }
    }

    window.addEventListener('popstate', syncOverlay)
    return () => { mounted.current = false; window.removeEventListener('popstate', syncOverlay) }
  }, [])

  const openMessage = async message => {
    if (openingMessage.current) return
    openingMessage.current = true
    const origin = `${location.href}|${history.state?.fitfinityDepth ?? 0}`
    setMessageError('')
    try {
      if (!message.read) {
        await onMarkRead(message.id)
      }

      // A delayed read receipt must not open a popup over a different page.
      if (!mounted.current || origin !== `${location.href}|${history.state?.fitfinityDepth ?? 0}`) return

      const depth = history.state?.fitfinityDepth ?? 0
      const overlayId = `message-${message.id}-${Date.now()}`

      history.pushState(
        {
          ...history.state,
          fitfinity: true,
          fitfinityDepth: depth + 1,
          fitfinityOverlay: 'message',
          fitfinityOverlayId: overlayId,
          messageId: message.id,
        },
        '',
        location.href,
      )

      setSelectedId(message.id)
    } catch (error) {
      setMessageError(error.message || 'Could not open the message. Try again.')
    } finally {
      openingMessage.current = false
    }
  }

  const closeMessage = useCallback(() => {
    if (history.state?.fitfinityOverlay === 'message') {
      if (closingMessage.current) return
      closingMessage.current = true
      history.back()
    } else {
      setSelectedId(null)
    }
  }, [])

  const markSelectedUnread = async () => {
    if (!selected || markingUnread.current) return
    const messageId = selected.id
    markingUnread.current = true
    setUnreadBusy(true)
    setMessageError('')
    try {
      await onMarkUnread(messageId)
      setSelectedId(current => current === messageId ? null : current)
      if (history.state?.fitfinityOverlay === 'message' && history.state.messageId === messageId) history.back()
    } catch (error) {
      setMessageError(error.message || 'Could not mark the message unread. Try again.')
    } finally {
      markingUnread.current = false
      setUnreadBusy(false)
    }
  }

  const openRelated = link => {
    setSelectedId(null)
    onOpenRelated(link)
  }

  useSwipeBack({
    enabled: Boolean(selected),
    onBack: closeMessage,
    routeKey: `${user.id}/${selectedId ?? ''}`,
    surface: '.message-detail-modal',
  })

  return (
    <>
      <Panel className={embedded ? 'dashboard-renewals' : ''}>
        {embedded ? <div className="section-head renewal-heading">
          <div className="renewal-total" role="status" aria-label="Total renewal follow-ups" aria-atomic="true">
            <strong className="renewal-count">{visible.length}</strong>
            <div><h2>Renewals</h2><span>Total follow-ups</span></div>
          </div>
          <button type="button" className="text-action" onClick={onViewAll}>View All Renewals</button>
        </div> : <div role="group" aria-label="Message categories">
          <ProfileNavigation items={MESSAGE_CATEGORIES.map(item => [item.key, item.label])}
            activeKey={category} onSelect={onCategoryChange} />
        </div>}
        {!selected && messageError && <p role="alert">{messageError}</p>}
        {!embedded && <div className="message-search-controls" aria-label="Message filters">
          <label>
            <span className="filter-label">Search</span>
            <input
              aria-label="Search messages"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search message content"
            />
          </label>

          <DateFilterField
            label="From"
            hint="Select start date"
            ariaLabel="Messages from date"
            value={fromDate}
            max={toDate}
            onChange={setFromDate}
          />

          <DateFilterField
            label="To"
            hint="Select end date"
            ariaLabel="Messages to date"
            value={toDate}
            min={fromDate}
            onChange={setToDate}
          />
        </div>}

        <div className="message-title-list" aria-label={embedded ? 'Renewal messages' : 'Message list'}>
          {!embedded && <div className="message-title-head message-title-grid" aria-hidden="true">
            <span>Message</span>
            <span>Date &amp; time</span>
            <span>Status</span>
            <span>Read</span>
          </div>}

          {(embedded ? visible.slice(0, 3) : pagination.items).map(message => (
            <article
              key={message.id}
              className={`message-title-row message-title-grid ${embedded ? 'message-title-preview ' : ''}${message.read ? 'read' : 'unread'}`}
              onClick={() => openMessage(message)}
            >
              <button
                type="button"
                className="message-title-button"
                aria-label={`Open ${message.title}`}
                title={embedded ? message.title : undefined}
              >
                <strong>{message.title}</strong>
              </button>

              {!embedded && <time className="message-title-time" dateTime={message.createdAt}>
                {formatTimestamp(message.createdAt, timeZone)}
              </time>}

              {!embedded && <div className="message-approval-status">
                <RequestStatusBadge message={message} />
              </div>}

              <button
                type="button"
                className={`message-state-button ${message.read ? 'read' : 'unread'}`}
                aria-label={`${message.read ? 'Read' : 'Unread'} ${message.title}`}
              >
                {message.read ? 'Read' : 'Unread'}
              </button>
            </article>
          ))}

          {!visible.length && (
            <div className="empty">
              {embedded ? 'No renewal messages.' : query || fromDate || toDate || category !== 'all' ? 'No messages match these filters.' : 'No messages.'}
            </div>
          )}
        </div>

        {!embedded && <PaginationControls {...pagination} onPage={pagination.setPage} />}
      </Panel>

      {selected && (
        <ModalPortal>
          <div
            className="modal-backdrop"
            role="presentation"
            onClick={closeMessage}
          >
            <section
              className="modal-card message-detail-modal"
              role="dialog"
              onClick={event => event.stopPropagation()}
              aria-modal="true"
              aria-label={selected.title}
            >
              <div className="modal-head">
                <h2>{selected.title}</h2>

                <button
                  type="button"
                  className="icon-button"
                  aria-label="Close message"
                  onClick={closeMessage}
                >
                  ×
                </button>
              </div>

              <div className="modal-body message-detail-body">
                <div className="message-detail-meta">
                  <span>{formatTimestamp(selected.createdAt, timeZone)}</span>

                  {messageCategory(selected) === 'renewals' && (
                    <StatusBadge tone="amber">Renewal</StatusBadge>
                  )}

                  <RequestStatusBadge message={selected} />
                </div>

                <p>{selected.body}</p>
                {selected.cancelledAt && selected.cancelledBy && <p>
                  Cancelled by {selected.cancelledBy.name} · <time dateTime={selected.cancelledAt}>{formatTimestamp(selected.cancelledAt, timeZone)}</time>
                </p>}
                {requestTypes.includes(selected.request?.type) && (user.role === 'owner' || selected.request.trainerId === user.trainerId) && (
                  <RequestReview key={selected.id} message={selected} trainers={trainers} sessions={sessions}
                    onResolve={user.role === 'owner' ? onResolveRequest : undefined}
                    onCancel={user.role === 'trainer' && selected.request.trainerId === user.trainerId ? onCancelRequest : undefined} />
                )}


                {relatedLinks.length > 0 && (
                  <nav className="message-related" aria-label="Related records">
                    <span>Related records</span>
                    <div>
                      {relatedLinks.map(link => (
                        <button
                          type="button"
                          key={`${link.type}-${link.id}`}
                          onClick={() => openRelated(link)}
                        >
                          View {link.label}
                        </button>
                      ))}
                    </div>
                  </nav>
                )}
              </div>
              <div className="modal-actions message-popup-actions">
                {messageError && <p role="alert">{messageError}</p>}
                <button type="button" className="secondary-button" disabled={unreadBusy} onClick={markSelectedUnread}>
                  {unreadBusy ? 'Marking…' : 'Mark as Unread'}
                </button>
              </div>
            </section>
          </div>
        </ModalPortal>
      )}
    </>
  )
}
