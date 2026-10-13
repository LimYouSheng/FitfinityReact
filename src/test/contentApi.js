import { directoryId } from './directory.js'

export const contentDraft = { key: 'studio/details', title: 'Studio details', body: 'Staff content.', status: 'draft' }
export const contentState = (patch = {}) => ({ id: directoryId(70), version: 1, ...contentDraft,
  created_at: '2026-10-13T10:00:00Z', updated_at: '2026-10-13T10:00:00Z', ...patch })
