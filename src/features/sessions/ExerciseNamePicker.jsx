import { useEffect, useMemo, useRef, useState } from 'react'
import { CUSTOM_EXERCISE } from '../../app/exerciseLibrary.js'
import { groupedActiveExercises } from '../../app/exerciseCatalog.js'

export default function ExerciseNamePicker({ catalog = [], index, choice, name, pending, onChoose, onCustomName }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [customMode, setCustomMode] = useState(false)
  const pickerRef = useRef(null)
  const customInputRef = useRef(null)

  useEffect(() => {
    const closeOutside = event => {
      if (pickerRef.current && !pickerRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside, true)
    return () => document.removeEventListener('pointerdown', closeOutside, true)
  }, [])

  useEffect(() => {
    if (open && customMode) customInputRef.current?.focus()
  }, [customMode, open])

  const filteredLibrary = useMemo(() => {
    const search = query.trim().toLowerCase()
    return groupedActiveExercises(catalog)
      .map(([category, names]) => [category, names.filter(item => item.toLowerCase().includes(search))])
      .filter(([, names]) => names.length)
  }, [catalog, query])

  const displayName = choice === CUSTOM_EXERCISE
    ? name || 'Select exercise'
    : name

  const selectLibraryExercise = exerciseName => {
    onChoose(exerciseName)
    setQuery('')
    setCustomMode(false)
    setOpen(false)
  }

  return (
    <div className="exercise-name-picker" ref={pickerRef}>
      <span className="exercise-picker-label">Exercise name</span>
      <button
        type="button"
        className={`exercise-picker-trigger ${pending ? 'pending-empty' : ''}`}
        role="combobox"
        aria-label={`Exercise ${index} name`}
        aria-expanded={open}
        onClick={() => setOpen(current => !current)}
      >
        <span>{displayName}</span>
        <span aria-hidden="true">⌄</span>
      </button>

      {open && (
        <div className="exercise-picker-menu" aria-label={`Exercise ${index} choices`}>
          <input
            type="search"
            aria-label={`Search exercise ${index}`}
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search exercises"
          />

          <button
            type="button"
            className="exercise-picker-custom"
            onClick={() => {
              onChoose(CUSTOM_EXERCISE)
              setCustomMode(true)
            }}
          >
            Custom Exercise
          </button>

          {customMode && (
            <div className="exercise-picker-custom-entry">
              <input
                ref={customInputRef}
                className={!name.trim() ? 'pending-empty' : ''}
                aria-label={`Exercise ${index} custom name`}
                value={name}
                onChange={event => onCustomName(event.target.value)}
                placeholder="Enter custom exercise name"
              />
              <button type="button" className="secondary-button" disabled={!name.trim()} onClick={() => setOpen(false)}>
                Use Custom Exercise
              </button>
            </div>
          )}

          <div className="exercise-picker-results">
            {filteredLibrary.map(([category, names]) => (
              <section className="exercise-picker-group" key={category}>
                <strong>{category}</strong>
                {names.map(exerciseName => (
                  <button type="button" key={exerciseName} onClick={() => selectLibraryExercise(exerciseName)}>
                    {exerciseName}
                  </button>
                ))}
              </section>
            ))}
            {!filteredLibrary.length && <p>No matching exercises.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
