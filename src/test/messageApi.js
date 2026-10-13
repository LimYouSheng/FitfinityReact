import { directoryId } from './directory.js'
import { staff } from './api.js'

export const personalNotice = (patch = {}) => ({ id: directoryId(90), version: 1, read: false, readAt: null,
  recipientUserId: staff.id, kind: 'saved_edit', title: 'Saved staff notice', body: 'A saved change is available.',
  createdAt: '2026-10-13T10:00:00Z', actorId: staff.id, actorName: staff.name, clientId: null, purchaseId: null,
  sessionId: null, trainerId: null, requestId: null, exerciseId: null, packageId: null, contentId: null,
  remunerationCycle: null, request: null, renewalStatus: null, ...patch })
export const messageRequest = (patch = {}) => ({ id: directoryId(91), version: 1, kind: 'trainer_availability', status: 'pending',
  trainer_id: directoryId(1), client_id: null, purchase_id: null, session_id: null, expected_version: 1, replacement_trainer_id: null,
  old_date: null, old_start: null, old_end: null, new_date: null, new_start: null, new_end: null, resolved_at: null, resolution_note: '',
  slots: ['old', 'new'].map((side, index) => ({ side, slot_identity: directoryId(92), weekday: 0, starts_at: `${10 + index}:00:00`, ends_at: `${11 + index}:00:00` })), ...patch })
