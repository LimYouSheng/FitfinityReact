import { describe, expect, it } from 'vitest'
import { CUSTOM_EXERCISE, EXERCISE_LIBRARY, exerciseChoiceFor, exerciseLibraryNames } from './exerciseLibrary.js'

describe('exercise library', () => {
  it('matches the categorized Oracle exercise list', () => {
    expect(Object.keys(EXERCISE_LIBRARY)).toEqual([
      'Full Body',
      'Upper Body',
      'Core',
      'Lower Body',
      'Single Leg',
      'Cardio',
    ])
    expect(exerciseLibraryNames).toHaveLength(49)
    expect(exerciseChoiceFor('Smith chest press')).toBe('Smith chest press')
    expect(exerciseChoiceFor('My custom movement')).toBe(CUSTOM_EXERCISE)
  })
})
