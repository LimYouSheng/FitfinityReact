// Every persisted UI action uses the shared top banner; services remain UI-independent.
export function scheduleNotification(subject, result) {
  return result.outcome === 'requested'
    ? { tone: 'info', message: `${subject} request sent for owner approval.` }
    : { tone: 'success', message: `${subject} saved.` }
}

export function exerciseNotification(previous, saved) {
  if (!previous) return { tone: 'success', message: 'Exercise created.' }
  if (previous.status !== saved.status) return saved.status === 'inactive'
    ? { tone: 'warning', message: 'Exercise deactivated.' }
    : { tone: 'success', message: 'Exercise reactivated.' }
  if (previous.media && !saved.media) return { tone: 'warning', message: 'Attachment removed. Exercise saved.' }
  return { tone: 'success', message: 'Exercise saved.' }
}

export function planNotification(previous, next) {
  if (previous.some(item => item.videoAttached && !next.find(entry => entry.id === item.id)?.videoAttached)) {
    return { tone: 'warning', message: 'Video removed. Exercise plan saved.' }
  }
  if (next.some(item => {
    const old = previous.find(entry => entry.id === item.id)
    return item.videoAttached && (!old?.videoAttached || item.video?.attachedAt !== old.video?.attachedAt)
  })) {
    return { tone: 'success', message: 'Video saved.' }
  }
  return { tone: 'success', message: 'Exercise plan saved.' }
}
