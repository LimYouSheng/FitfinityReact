function timestamp(value) {
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

export function orderMessages(messages) {
  return [...messages].sort((a, b) => {
    const readOrder = Number(Boolean(a.read)) - Number(Boolean(b.read))
    if (readOrder !== 0) return readOrder

    const aActivity = a.read ? a.readAt ?? a.createdAt : a.createdAt
    const bActivity = b.read ? b.readAt ?? b.createdAt : b.createdAt
    const activityOrder = timestamp(bActivity) - timestamp(aActivity)

    return activityOrder || timestamp(b.createdAt) - timestamp(a.createdAt)
  })
}
