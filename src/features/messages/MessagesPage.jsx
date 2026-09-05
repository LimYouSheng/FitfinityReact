import { useCallback, useEffect, useMemo, useState } from 'react'
import StatusBadge from '../../components/StatusBadge.jsx'
import Panel from '../../components/Panel.jsx'
import useSwipeBack from '../../hooks/useSwipeBack.js'
import ModalPortal from '../../components/ModalPortal.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import DateFilterField from '../../components/DateFilterField.jsx'
import usePagination from '../../hooks/usePagination.js'
import { filterMessages } from './messageFilters.js'
import { orderMessages } from './messageOrdering.js'
import { relatedMessageLinks } from './messageLinks.js'

function visibleTo(user, message) {
  if (message.recipientUserId === user.id) return true
  if (message.recipientRole === user.role) return true
  if (user.role === 'trainer' && message.recipientTrainerId === user.trainerId) return true
  return false
}

function formatStamp(value) {
  try {
    return new Intl.DateTimeFormat('en-SG', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return value
  }
}

export default function MessagesPage({
  user,
  messages,
  clients = [],
  trainers = [],
  sessions = [],
  onMarkRead,
  onOpenRelated,
}) {
  const [selectedId, setSelectedId] = useState(() =>
    history.state?.fitfinityOverlay === 'message'
      ? history.state?.messageId ?? null
      : null
  )
  const [query, setQuery] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const userMessages = useMemo(
    () => orderMessages(messages.filter(message => visibleTo(user, message))),
    [messages, user],
  )
  const visible = useMemo(
    () => filterMessages(userMessages, { query, from: fromDate, to: toDate }),
    [fromDate, query, toDate, userMessages],
  )

  const selected = userMessages.find(message => message.id === selectedId) ?? null
  const relatedLinks = useMemo(
    () => relatedMessageLinks(selected, { user, clients, trainers, sessions }),
    [clients, selected, sessions, trainers, user],
  )
  const pagination = usePagination(visible, `${user.id}|${query}|${fromDate}|${toDate}`)

  useEffect(() => {
    const syncOverlay = () => {
      if (history.state?.fitfinityOverlay === 'message') {
        setSelectedId(history.state.messageId ?? null)
      } else {
        setSelectedId(null)
      }
    }

    window.addEventListener('popstate', syncOverlay)
    return () => window.removeEventListener('popstate', syncOverlay)
  }, [])

  const openMessage = async message => {
    if (!message.read) {
      await onMarkRead(message.id)
    }

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
  }

  const closeMessage = useCallback(() => {
    if (history.state?.fitfinityOverlay === 'message') {
      history.back()
    } else {
      setSelectedId(null)
    }
  }, [])

  const openRelated = link => {
    setSelectedId(null)
    onOpenRelated(link)
  }

  useSwipeBack({
    enabled: Boolean(selected),
    onBack: closeMessage,
  })

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Updates</span>
          <h1>Messages</h1>
        </div>

        <StatusBadge tone="blue">
          {userMessages.filter(message => !message.read).length} new
        </StatusBadge>
      </div>

      <Panel>
        <div className="message-search-controls" aria-label="Message filters">
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
        </div>

        <div className="message-title-list" aria-label="Message list">
          <div className="message-title-head message-title-grid" aria-hidden="true">
            <span>Message</span>
            <span>Date &amp; time</span>
            <span>Status</span>
          </div>

          {pagination.items.map(message => (
            <article
              key={message.id}
              className={`message-title-row message-title-grid ${message.read ? 'read' : 'unread'}`}
            >
              <button
                type="button"
                className="message-title-button"
                aria-label={`Open ${message.title}`}
                onClick={() => openMessage(message)}
              >
                <strong>{message.title}</strong>
              </button>

              <time className="message-title-time" dateTime={message.createdAt}>
                {formatStamp(message.createdAt)}
              </time>

              <button
                type="button"
                className={`message-state-button ${message.read ? 'read' : 'unread'}`}
                aria-label={`${message.read ? 'Read' : 'Unread'} ${message.title}`}
                onClick={() => openMessage(message)}
              >
                {message.read ? 'Read' : 'Unread'}
              </button>
            </article>
          ))}

          {!visible.length && (
            <div className="empty">
              {query || fromDate || toDate ? 'No messages match your search.' : 'No messages.'}
            </div>
          )}
        </div>

        <PaginationControls {...pagination} onPage={pagination.setPage} />
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
                  <span>{formatStamp(selected.createdAt)}</span>

                  {selected.kind === 'renewal' && (
                    <StatusBadge tone="amber">Renewal</StatusBadge>
                  )}

                  {selected.status === 'pending' && (
                    <StatusBadge tone="blue">Pending</StatusBadge>
                  )}
                </div>

                <p>{selected.body}</p>

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
            </section>
          </div>
        </ModalPortal>
      )}
    </>
  )
}
