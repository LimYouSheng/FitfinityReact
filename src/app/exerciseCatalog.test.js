import { describe, expect, it } from 'vitest'
import { exerciseCatalog, exerciseDraftErrors, exerciseMediaError, filterExerciseCatalog, groupedActiveExercises } from './exerciseCatalog.js'
import { DEFAULT_EXERCISES } from '../data/mockExercises.js'
import { CUSTOM_EXERCISE, exerciseChoiceFor } from './exerciseLibrary.js'
import { exerciseLibraryNames } from '../data/mockExercises.js'

const draft = { name: 'Band row', category: 'Upper Body', description: 'Seated cable alternative', status: 'active' }
describe('managed exercise catalog', () => {
  it('retains all 49 original exercises and six groups without mutating an older database', () => {
    const older = { sessions: [] }
    const db = { ...older, exerciseLibrary: structuredClone(DEFAULT_EXERCISES) }
    expect(exerciseCatalog(db).map(item => item.name)).toEqual(exerciseLibraryNames)
    expect(new Set(exerciseCatalog(db).map(item => item.id)).size).toBe(49)
    expect(groupedActiveExercises(exerciseCatalog(db))).toHaveLength(6)
    expect(older).toEqual({ sessions: [] })
  })
  it('rejects normalized duplicates even when inactive and reserves Custom Exercise', () => {
    const catalog = [{ ...draft, id: 'one', status: 'inactive' }]
    expect(exerciseDraftErrors({ ...draft, name: '  BAND   row ' }, catalog).name).toMatch(/already/)
    expect(exerciseDraftErrors(draft, catalog, 'one')).toEqual({})
    expect(exerciseDraftErrors({ ...draft, name: CUSTOM_EXERCISE }, []).name).toMatch(/already/)
    expect(exerciseDraftErrors({ ...draft, name: 'Custom Exercise' }, []).name).toMatch(/already/)
  })
  it('validates compulsory fields, lengths and lifecycle state', () => {
    expect(exerciseDraftErrors({ name: '', category: 'Unknown', description: 'x'.repeat(2001), status: 'deleted' }, [])).toEqual({ name: expect.any(String), category: expect.any(String), description: expect.any(String), status: expect.any(String) })
    expect(exerciseDraftErrors({ ...draft, name: 'x'.repeat(181) }, []).name).toMatch(/180/)
  })
  it('combines filters and includes only active managed names in the session picker', () => {
    const added = { ...draft, id: 'new', createdAt: '2026-09-06T00:00:00Z' }
    const catalog = [added, { ...DEFAULT_EXERCISES[0], status: 'inactive' }, ...DEFAULT_EXERCISES.slice(1)]
    expect(filterExerciseCatalog(catalog, { query: 'cable alternative', category: 'Upper Body' })).toEqual([added])
    expect(filterExerciseCatalog(catalog, { status: 'inactive' })).toHaveLength(1)
    expect(groupedActiveExercises(catalog).flatMap(([, names]) => names)).not.toContain(DEFAULT_EXERCISES[0].name)
    expect(exerciseChoiceFor(draft.name, catalog)).toBe(draft.name)
    expect(exerciseChoiceFor(DEFAULT_EXERCISES[0].name, catalog)).toBe(CUSTOM_EXERCISE)
  })
  it('rejects unsupported, empty and oversized attachments while allowing the supported image/video formats', () => {
    for (const type of ['image/png', 'image/jpeg', 'image/webp', 'video/mp4', 'video/webm', 'video/quicktime']) expect(exerciseMediaError({ type, size: 100 })).toBe('')
    for (const file of [{ type: 'text/html', size: 100 }, { type: 'video/mp4', size: 0 }, { type: 'video/mp4', size: 50 * 1024 * 1024 + 1 }]) expect(exerciseMediaError(file)).not.toBe('')
  })
})
