export function clientPackages(client) {
  return [client.package, ...(client.additionalPackages ?? []), ...(client.packageHistory ?? [])].filter(Boolean)
}

export function packageForRecord(client, record) {
  if (!client) return null
  const packages = clientPackages(client)
  if (Object.hasOwn(record, 'packageId')) return packages.find(item => item.id === record.packageId) ?? null
  const candidates = packages.filter(item => record.date >= item.startDate && record.date <= item.endDate)
  return candidates.length === 1 ? candidates[0] : null
}

// A missing legacy link may be recovered from one purchase; never guess across overlaps.
function legacyPackageForRecord(client, record) {
  if (record.packageId != null) return packageForRecord(client, record)
  const unlinked = { ...record }
  delete unlinked.packageId
  return packageForRecord(client, unlinked)
}

export function ensureClientPackageReferences(db, client) {
  if (!client.package) return
  client.package.id ??= `client-package-${client.id}`
  for (const [index, purchased] of (client.additionalPackages ?? []).entries()) purchased.id ??= `additional-package-${client.id}-${purchased.startDate}-${index}`
  client.package.trainerId ??= client.trainerId
  for (const [index, purchased] of (client.packageHistory ?? []).entries()) purchased.id ??= `legacy-package-${client.id}-${purchased.startDate}-${index}`
  for (const session of db.sessions.filter(item => item.clientId === client.id)) {
    if (session.packageId == null) session.packageId = legacyPackageForRecord(client, session)?.id ?? null
  }
  for (const exercises of [client.strengthProgress, client.progressBaseline]) {
    for (const exercise of exercises ?? []) for (const point of exercise.points ?? []) {
      const session = db.sessions.find(item => item.id === point.sessionId && item.clientId === client.id)
      if (point.sessionId) {
        const purchased = session && packageForRecord(client, session)
        if (purchased) point.packageId = purchased.id
      }
      else if (point.packageId == null) point.packageId = legacyPackageForRecord(client, point)?.id ?? null
    }
  }
}

// Keep unresolved measurements recoverable in storage, outside operational reports.
// Session evidence and report audit events are never deleted or reassigned here.
export function cleanClientProgressRecords(db, client) {
  ensureClientPackageReferences(db, client)
  let archivedRecords
  for (const field of ['strengthProgress', 'progressBaseline']) {
    if (!client[field]) continue
    client[field] = client[field].map(exercise => ({ ...exercise, points: exercise.points.filter(point => {
      const session = point.sessionId && db.sessions.find(item => item.id === point.sessionId && item.clientId === client.id)
      if (session && packageForRecord(client, session)) return true
      const entry = { clientId: client.id, exerciseId: exercise.id, exerciseName: exercise.name, point: structuredClone(point) }
      const archive = db.progressMigrationArchive ??= []
      // Index once when unresolved records exist, instead of serializing the
      // growing archive again for every comparison. Preserve its order/evidence.
      archivedRecords ??= new Set(archive.map(saved => JSON.stringify(saved)))
      const key = JSON.stringify(entry)
      if (!archivedRecords.has(key)) { archive.push(entry); archivedRecords.add(key) }
      return false
    }) })).filter(exercise => exercise.points.length)
  }
}

export function progressForPackage(client, packageId) {
  return (client.strengthProgress ?? []).map(exercise => ({ ...exercise,
    points: exercise.points.filter(point => (point.packageId ?? null) === packageId),
  })).filter(exercise => exercise.points.length)
}

export function requireActiveClient(client) {
  if (!client) throw new Error('Client not found.')
  if (client.status === 'inactive') throw new Error('Client inactive. This record is read-only.')
  return client
}

export function sessionIsInactive(client, session) {
  return client?.status === 'inactive' || packageForRecord(client, session)?.status === 'inactive'
}

export function requireActiveSessionClient(client, session) {
  requireActiveClient(client)
  if (packageForRecord(client, session)?.status === 'inactive') throw new Error('Package inactive. This session is read-only.')
  return client
}

export function pastClientPackages(client) {
  return clientPackages(client).filter(item => item.status === 'inactive' || (client.packageHistory ?? []).some(past => past.id === item.id))
}

export function deletablePackageSessions(client, packageId, sessions, transactions, clock) {
  return sessions.filter(session => session.clientId === client.id && packageForRecord(client, session)?.id === packageId &&
    !['completed', 'cancelled'].includes(session.status) && !session.acknowledgement && !session.acknowledgementHistory?.length &&
    !transactions.some(transaction => transaction.sessionId === session.id) &&
    (session.date > clock.date || (session.date === clock.date && session.from > clock.time)))
}

export function clientAssignedToTrainer(client, trainerId, sessions = []) {
  return Boolean(trainerId) && (client.trainerId === trainerId ||
    (client.trainerAssignmentHistory ?? []).some(entry => entry.from.id === trainerId || entry.to.id === trainerId) ||
    clientPackages(client).some(purchased => purchased.trainerId === trainerId) ||
    sessions.some(session => session.clientId === client.id && session.trainerId === trainerId))
}
