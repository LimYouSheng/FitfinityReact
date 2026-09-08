import { DEFAULT_EXERCISES } from '../data/mockExercises.js'
import { describe, expect, it } from 'vitest'
import { CUSTOM_EXERCISE, exerciseChoiceFor } from './exerciseLibrary.js'
import { EXERCISE_LIBRARY, exerciseLibraryNames } from '../data/mockExercises.js'

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
    expect(exerciseChoiceFor('Smith chest press', DEFAULT_EXERCISES)).toBe('Smith chest press')
    expect(exerciseChoiceFor('My custom movement')).toBe(CUSTOM_EXERCISE)
  })
})
