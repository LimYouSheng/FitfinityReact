function initials(name) {
  return String(name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join('')
    .toUpperCase()
}

export default function ProfileAvatar({ name }) {
  return (
    <span className="profile-avatar" aria-hidden="true">
      {initials(name)}
    </span>
  )
}
