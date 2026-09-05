export const EXERCISE_LIBRARY = {
  'Full Body': [
    'Dumbbell renegade row',
    'Dumbbell Push and Press or a handle grips ball and Vipr',
    'RDL to bent over row with dumbbell and barbell and Vipr',
    'Cable wood chop',
    'Alternating back lunges to bicep curl with dumbbell or Vipr or barbell',
  ],
  'Upper Body': [
    'Smith chest press',
    'Smith incline shoulder press',
    'Smith bent over row',
    'LPD',
    'Seated row',
    'Assisted pull up',
    'DB chest press (incline bench and flat bench)',
    'DB shoulder press (incline bench and flat bench)',
    'DB or cable bicep curls both or single arm',
    'DB or cable lateral raise both or single arm',
    'Single arm LPD',
    'Single arm row',
    'Alternating DB chest press both or single arm',
    'Alternating DB shoulder press both or single arm',
    'Single arm DB row',
    'DB or Cable alternating front raise',
  ],
  Core: ['Upper core', 'Lower core', 'Obliques', 'Lower back'],
  'Lower Body': [
    'Leg press',
    'Smith back squat',
    'Smith deadlift',
    'Smith RDL',
    'Barbell RDL and Barbell conventional DL',
    'DB or KB Sumo Squat',
    'Leg extension',
    'DB Goblet squat',
  ],
  'Single Leg': [
    'Static lunge with DB and with Smith',
    'Single leg extension',
    'Alternating back lunge with dumbbell and with smith',
    'Side lunges with DB or KB',
    'Step up alternating with DB',
    'Walking lunges',
    'Curtsey lunges',
  ],
  Cardio: [
    'Wall Ball',
    'Alternating slam ball',
    'Miniband side walk to star jump',
    'Bench jump or Box jump',
    'Fanbike interval',
    'KB swing',
    'TRX Mountain climber',
    'Bodyweight cardio',
    'Battle Ropes',
  ],
}

export const CUSTOM_EXERCISE = '__custom__'

export const exerciseLibraryNames = Object.values(EXERCISE_LIBRARY).flat()

export function exerciseChoiceFor(name) {
  return exerciseLibraryNames.includes(name) ? name : CUSTOM_EXERCISE
}
