import { delay, mockDb } from './mockDb.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { formatMoney, remunerationDraft, remunerationRecord, remunerationCycles, cycleTrainers } from '../app/remuneration.js'

function ownerOnly(db, actor) {
  const owner = requireActiveActor(db, actor)
  if (owner.role !== 'owner') throw new Error('Only the owner can approve remuneration.')
  return owner
}
function freshDraft(db, cycle, trainerId, revision) {
  const draft = remunerationDraft(db, cycle, trainerId)
  if ((db.remunerationApprovals ?? []).some(record => record.cycle.key === cycle && record.trainerId === trainerId)) throw new Error('This trainer’s pay cycle is already approved.')
  if (draft.revision !== revision) throw new Error('The sessions or rates changed. Refresh the page and review them again.')
  return draft
}

export const remunerationService = {
  list(actor, now) {
    const db = mockDb.read(), user = requireActiveActor(db, actor)
    return remunerationCycles(db, user, now).map(key => ({ key, trainers: cycleTrainers(db, key, user, now) }))
  },
  detail(cycle, trainerId, actor, now) {
    const db = mockDb.read(), user = requireActiveActor(db, actor)
    if (user.role !== 'owner' && user.trainerId !== trainerId) throw new Error('This remuneration belongs to another trainer.')
    return remunerationRecord(db, cycle, trainerId, now)
  },
  async approve(cycle, trainerId, revision, actor) {
    await delay(100)
    return mockDb.mutate(db => {
      const owner = ownerOnly(db, actor)
      const draft = freshDraft(db, cycle, trainerId, revision)
      if (!draft.closed) throw new Error('Approve this cycle from its payout date, after all cycle dates have passed.')
      if (!draft.sessions || draft.reviewCount) throw new Error('Correct the session details or missing trainer rates before approval.')
      const approvedAt = new Date().toISOString()
      const record = { ...draft, status: 'Approved', approvedAt, approvedBy: owner.id }
      db.remunerationApprovals = [...(db.remunerationApprovals ?? []), record]
      const base = { trainerId, remunerationCycle: cycle, title: `Remuneration approved · ${draft.trainerName} · ${cycle}`,
        body: `${draft.sessions} completed sessions approved at ${formatMoney(draft.amountCents, db.settings)} for ${draft.cycle.start} to ${draft.cycle.end}. Open the remuneration breakdown for the approved record.`,
        kind: 'remuneration_approval', status: 'approved', createdAt: approvedAt, read: false }
      db.messages.push({ ...base, id: `remuneration-approved-${cycle}-${trainerId}-owner`, recipientRole: 'owner' },
        { ...base, id: `remuneration-approved-${cycle}-${trainerId}-trainer`, recipientTrainerId: trainerId })
    })
  },
}
