const messageId = prefix => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

export function appendSavedEditMessage(db, {
  title,
  body,
  clientId,
  trainerId,
  sessionId,
  exerciseId,
  packageId,
  kind = 'saved_edit',
}) {
  db.messages ??= []
  db.messages.push({
    id: messageId('saved-edit'),
    createdAt: new Date().toISOString(),
    recipientRole: 'owner',
    ...(trainerId ? { recipientTrainerId: trainerId, trainerId } : {}),
    ...(clientId ? { clientId } : {}),
    ...(sessionId ? { sessionId } : {}),
    ...(exerciseId ? { exerciseId } : {}),
    ...(packageId ? { packageId } : {}),
    title,
    body,
    kind,
    read: false,
  })
}

export function savedFields(patch) {
  return Object.keys(patch)
    .map(field => field.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase())
    .join(', ')
}
