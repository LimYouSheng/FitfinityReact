import { useEffect, useState } from 'react'

const INLINE_PROFILE_NAV = '(min-width: 700px)'

function inlineMatches() {
  return typeof window !== 'undefined' && window.matchMedia(INLINE_PROFILE_NAV).matches
}

export default function ProfileNavigation({ items, activeKey, onSelect, children }) {
  const [inline, setInline] = useState(inlineMatches)
  const [open, setOpen] = useState(inlineMatches)
  const activeLabel = items.find(([key]) => key === activeKey)?.[1] ?? 'Profile Menu'

  useEffect(() => {
    const media = window.matchMedia(INLINE_PROFILE_NAV)
    const sync = event => {
      setInline(event.matches)
      setOpen(event.matches)
    }

    setInline(media.matches)
    setOpen(media.matches)
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  return (
    <details
      className="profile-menu"
      open={inline || open}
      onToggle={event => {
        if (!inline) setOpen(event.currentTarget.open)
      }}
      onClick={event => {
        if (!inline && event.target === event.currentTarget) setOpen(false)
      }}
    >
      <summary>{activeLabel}</summary>

      <div
        className="profile-tabs"
        onClick={event => {
          if (!inline && event.target.closest('button')) setOpen(false)
        }}
      >
        {items.map(([key, label]) => (
          <button
            key={key}
            className={activeKey === key ? 'active' : ''}
            aria-current={activeKey === key ? 'true' : undefined}
            type="button"
            onClick={() => onSelect(key)}
          >
            {label}
          </button>
        ))}

        {children}
      </div>
    </details>
  )
}
