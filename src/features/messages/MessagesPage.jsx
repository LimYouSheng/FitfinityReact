import { useCallback, useEffect, useMemo, useState } from 'react'
import StatusBadge from '../../components/StatusBadge.jsx'
import Panel from '../../components/Panel.jsx'
import useSwipeBack from '../../hooks/useSwipeBack.js'

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
  onMarkRead,
}) {
  const [selectedId, setSelectedId] = useState(() =>
    history.state?.fitfinityOverlay === 'message'
      ? history.state?.messageId ?? null
      : null
  )

  const visible = useMemo(
    () => messages
      .filter(message => visibleTo(user, message))
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)),
    [messages, user],
  )

  const selected = visible.find(message => message.id === selectedId) ?? null

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
          {visible.filter(message => !message.read).length} new
        </StatusBadge>
      </div>

      <Panel>
        <div className="message-title-list" aria-label="Message list">
          {visible.map(message => (
            <article
              key={message.id}
              className={`message-title-row ${message.read ? 'read' : 'unread'}`}
            >
              <button
                type="button"
                className="message-title-button"
                aria-label={`Open ${message.title}`}
                onClick={() => openMessage(message)}
              >
                <strong>{message.title}</strong>
              </button>

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

          {!visible.length && <div className="empty">No messages.</div>}
        </div>
      </Panel>

      {selected && (
        <div
          className="modal-backdrop"
          role="presentation"
          onPointerDown={closeMessage}
        >
          <section
            className="modal-card message-detail-modal"
            role="dialog"
            onPointerDown={event => event.stopPropagation()}
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
            </div>
          </section>
        </div>
      )}
    </>
  )
}
