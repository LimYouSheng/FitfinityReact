import { CUSTOM_EXERCISE, EXERCISE_LIBRARY } from './exerciseLibrary.js'

export const exerciseCategories = Object.keys(EXERCISE_LIBRARY)
export const DEFAULT_EXERCISES = Object.entries(EXERCISE_LIBRARY).flatMap(([category, names]) => names.map(name => ({ category, name })))
  .map((entry, index) => ({ ...entry, id: `library-${String(index + 1).padStart(3, '0')}`, description: '', status: 'active', media: null, version: 1, createdAt: '2026-08-01T00:00:00Z' }))
export const exerciseCatalog = db => db.exerciseLibrary ?? DEFAULT_EXERCISES
const normalizedName = name => String(name ?? '').trim().replace(/\s+/g, ' ').toLowerCase()

export function exerciseDraftErrors(draft, catalog, id) {
  const errors = {}
  if (!draft.name?.trim()) errors.name = 'Enter the exercise name.'
  else if (draft.name.trim().length > 180) errors.name = 'Use 180 characters or fewer.'
  else if (['custom exercise', CUSTOM_EXERCISE].includes(normalizedName(draft.name)) || catalog.some(item => item.id !== id && normalizedName(item.name) === normalizedName(draft.name))) errors.name = 'This exercise name is already in use.'
  if (!exerciseCategories.includes(draft.category)) errors.category = 'Choose a category.'
  if ((draft.description ?? '').length > 2000) errors.description = 'Use 2,000 characters or fewer.'
  if (!['active', 'inactive'].includes(draft.status)) errors.status = 'Choose an active or inactive status.'
  return errors
}

export function filterExerciseCatalog(catalog, { query = '', category = '', status = 'active' } = {}) {
  const search = query.trim().toLowerCase()
  return catalog.filter(item => (!status || item.status === status) && (!category || item.category === category) && (!search || `${item.name} ${item.description}`.toLowerCase().includes(search)))
    .sort((a, b) => (a.status === 'inactive') - (b.status === 'inactive') || b.createdAt.localeCompare(a.createdAt) || a.id.localeCompare(b.id))
}

export function groupedActiveExercises(catalog = DEFAULT_EXERCISES) {
  return exerciseCategories.map(category => [category, catalog.filter(item => item.status === 'active' && item.category === category).map(item => item.name)])
    .filter(([, names]) => names.length)
}

export const EXERCISE_MEDIA_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/webm', 'video/quicktime']
export function exerciseMediaError(file) {
  if (!file || !EXERCISE_MEDIA_TYPES.includes(file.type)) return 'Choose a JPG, PNG, WebP, MP4, WebM or MOV file.'
  if (!file.size || file.size > 50 * 1024 * 1024) return 'Choose a non-empty file up to 50 MB.'
  return ''
}
