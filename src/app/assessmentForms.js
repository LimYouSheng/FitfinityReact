// Owner-supplied paper fields and retained v1 answers. Never infer clinical clearance.
const notes = (id, label) => ({ id, label, type: 'textarea' })
export const ASSESSMENT_FORMS = [
  {
    id: "health_history", title: "Lifestyle & Health History", subtitle: "Health, habits and goals", version: 1, source: "5_Sample_Lifestyle_and_Health-History_Questionnaire.pdf", paperTitle: "Sample Lifestyle and Health-History Questionnaire",
    sections: [
      { title: "Medical Information", fields: [
        {"id": "health", "label": "Current state of health", "type": "select", "options": ["Very well", "Healthy", "Unhealthy", "Unwell", "Other", "Unknown"]},
        {"id": "health_details", "label": "Health details", "type": "textarea"},
        {"id": "medications", "label": "Medications, frequency and dosage", "type": "textarea"},
        {"id": "medication_adherence", "label": "Taking medication as prescribed?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "medication_reason", "label": "If not, why?", "type": "textarea"},
        {"id": "supplements", "label": "Taking supplements?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "supplement_details", "label": "Supplement types and amounts", "type": "textarea"},
        {"id": "physician_visit", "label": "Last physician visit", "type": "text"},
        {"id": "cholesterol_checked", "label": "Cholesterol checked?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "cholesterol_date", "label": "Cholesterol check date", "type": "text"},
        {"id": "cholesterol_results", "label": "Cholesterol results (total, HDL, LDL, triglycerides; include units)", "type": "textarea"},
        {"id": "blood_sugar_checked", "label": "Blood sugar checked?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "blood_sugar_results", "label": "Blood sugar results (include date and units)", "type": "textarea"},
        {"id": "condition_0", "label": "Allergies", "type": "checkbox"},
        {"id": "condition_1", "label": "Amenorrhea", "type": "checkbox"},
        {"id": "condition_2", "label": "Anemia", "type": "checkbox"},
        {"id": "condition_3", "label": "Anxiety", "type": "checkbox"},
        {"id": "condition_4", "label": "Arthritis", "type": "checkbox"},
        {"id": "condition_5", "label": "Asthma", "type": "checkbox"},
        {"id": "condition_6", "label": "Celiac disease", "type": "checkbox"},
        {"id": "condition_7", "label": "Chronic sinus condition", "type": "checkbox"},
        {"id": "condition_8", "label": "Constipation", "type": "checkbox"},
        {"id": "condition_9", "label": "Crohn’s disease", "type": "checkbox"},
        {"id": "condition_10", "label": "Depression", "type": "checkbox"},
        {"id": "condition_11", "label": "Diabetes", "type": "checkbox"},
        {"id": "condition_12", "label": "Diarrhea", "type": "checkbox"},
        {"id": "condition_13", "label": "Disordered eating", "type": "checkbox"},
        {"id": "condition_14", "label": "Gastroesophageal reflux disease (GERD)", "type": "checkbox"},
        {"id": "condition_15", "label": "High blood pressure", "type": "checkbox"},
        {"id": "condition_16", "label": "Hypoglycemia", "type": "checkbox"},
        {"id": "condition_17", "label": "Hypo/hyperthyroidism", "type": "checkbox"},
        {"id": "condition_18", "label": "Insomnia", "type": "checkbox"},
        {"id": "condition_19", "label": "Intestinal problems", "type": "checkbox"},
        {"id": "condition_20", "label": "Irritability", "type": "checkbox"},
        {"id": "condition_21", "label": "Irritable bowel syndrome (IBS)", "type": "checkbox"},
        {"id": "condition_22", "label": "Menopausal symptoms", "type": "checkbox"},
        {"id": "condition_23", "label": "Osteoporosis", "type": "checkbox"},
        {"id": "condition_24", "label": "Premenstrual syndrome (PMS)", "type": "checkbox"},
        {"id": "condition_25", "label": "Polycystic ovary syndrome (PCOS)", "type": "checkbox"},
        {"id": "condition_26", "label": "Pregnant", "type": "checkbox"},
        {"id": "condition_27", "label": "Skin problems", "type": "checkbox"},
        {"id": "condition_28", "label": "Ulcer", "type": "checkbox"},
        {"id": "conditions", "label": "Current or past health conditions", "type": "textarea"},
        {"id": "surgeries", "label": "Major surgeries", "type": "textarea"},
        {"id": "injuries", "label": "Past injuries", "type": "textarea"},
        {"id": "other_conditions", "label": "Other conditions", "type": "textarea"},
      ] },
      { title: "Family History", fields: [
        {"id": "family_0", "label": "Heart disease — relationship and age at diagnosis (or none / unknown)", "type": "textarea"},
        {"id": "family_1", "label": "High cholesterol — relationship and age at diagnosis (or none / unknown)", "type": "textarea"},
        {"id": "family_2", "label": "High blood pressure — relationship and age at diagnosis (or none / unknown)", "type": "textarea"},
        {"id": "family_3", "label": "Cancer — relationship and age at diagnosis (or none / unknown)", "type": "textarea"},
        {"id": "family_4", "label": "Diabetes — relationship and age at diagnosis (or none / unknown)", "type": "textarea"},
        {"id": "family_5", "label": "Osteoporosis — relationship and age at diagnosis (or none / unknown)", "type": "textarea"},
      ] },
      { title: "Nutrition", fields: [
        {"id": "nutrition_goals", "label": "Nutrition goals", "type": "textarea"},
        {"id": "modified_diet", "label": "Modified diet?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "diet_changes", "label": "Diet modifications", "type": "textarea"},
        {"id": "eating_plan", "label": "Following a special eating plan?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "plan_type", "label": "Plan type and reason", "type": "textarea"},
        {"id": "plan_reason", "label": "Reason for choosing the eating plan", "type": "textarea"},
        {"id": "plan_prescribed", "label": "Plan prescribed?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "plan_duration", "label": "Time on this plan", "type": "text"},
        {"id": "dietitian", "label": "Seen a dietitian or diabetes educator?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "dietitian_interest", "label": "Interested in seeing one?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "nutrition_issues", "label": "Nutritional issues", "type": "textarea"},
        {"id": "water", "label": "Water per day (8-ounce glasses)", "type": "number", "min": 0},
        {"id": "other_drinks", "label": "Other drinks and amounts", "type": "textarea"},
        {"id": "food_allergies", "label": "Food allergies?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "food_allergy_details", "label": "Food allergy details", "type": "textarea"},
        {"id": "food_shopper", "label": "Who shops for food?", "type": "text"},
        {"id": "food_preparer", "label": "Who prepares food?", "type": "text"},
        {"id": "dining_out", "label": "Dining out (times per week)", "type": "number", "min": 0},
        {"id": "restaurant_breakfast", "label": "Breakfast — restaurant types", "type": "text"},
        {"id": "restaurant_lunch", "label": "Lunch — restaurant types", "type": "text"},
        {"id": "restaurant_dinner", "label": "Dinner — restaurant types", "type": "text"},
        {"id": "restaurant_snacks", "label": "Snacks — restaurant types", "type": "text"},
        {"id": "cravings", "label": "Food cravings?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "craving_details", "label": "Craving details", "type": "textarea"},
      ] },
      { title: "Substance-related Habits", fields: [
        {"id": "alcohol", "label": "Alcohol use?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "alcohol_amount", "label": "Alcohol frequency and average amount", "type": "text"},
        {"id": "caffeine", "label": "Caffeine use?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "caffeine_amount", "label": "Caffeinated drinks per day", "type": "number", "min": 0},
        {"id": "tobacco", "label": "Tobacco use?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "tobacco_amount", "label": "Tobacco amount", "type": "text"},
      ] },
      { title: "Physical Activity", fields: [
        {"id": "structured_exercise", "label": "Structured exercise?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "cardio_minutes", "label": "Cardio minutes per session", "type": "number", "min": 0},
        {"id": "cardio_frequency", "label": "Cardio sessions per week", "type": "number", "min": 0},
        {"id": "strength_frequency", "label": "Strength sessions per week", "type": "number", "min": 0},
        {"id": "flexibility_frequency", "label": "Flexibility sessions per week", "type": "number", "min": 0},
        {"id": "sport_minutes", "label": "Sport minutes per week", "type": "number", "min": 0},
        {"id": "activities", "label": "Sports and activities", "type": "textarea"},
        {"id": "other_activity", "label": "Other physical activity?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "other_activity_details", "label": "Other activity details", "type": "textarea"},
        {"id": "injury_restriction", "label": "Injury affecting activity?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "activity_injuries", "label": "Injuries affecting physical activity", "type": "textarea"},
        {"id": "restrictions", "label": "Injuries and activity restrictions", "type": "textarea"},
        {"id": "exercise_feelings", "label": "Feelings about exercise", "type": "textarea"},
        {"id": "favorite_activities", "label": "Favourite activities", "type": "textarea"},
      ] },
      { title: "Occupational", fields: [
        {"id": "working", "label": "Currently working?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "occupation", "label": "Occupation", "type": "text"},
        {"id": "work_schedule", "label": "Work schedule", "type": "text"},
        {"id": "work_activity", "label": "Activity level at work", "type": "text"},
      ] },
      { title: "Sleep and Stress", fields: [
        {"id": "sleep_hours", "label": "Sleep per night (hours)", "type": "number", "min": 0, "max": 24},
        {"id": "stress", "label": "Stress level (1–10)", "type": "number", "min": 1, "max": 10},
        {"id": "stressors", "label": "Sources of stress", "type": "textarea"},
        {"id": "appetite", "label": "Effect of stress on appetite", "type": "select", "options": ["Increased", "Unaffected", "Decreased", "Unknown"]},
      ] },
      { title: "Weight History", fields: [
        {"id": "present_weight", "label": "Present weight (kg)", "type": "number", "min": 0},
        {"id": "weight_goal", "label": "Desired weight change", "type": "select", "options": ["Lose", "Gain", "Maintain", "Unknown"]},
        {"id": "lowest_weight", "label": "Lowest weight in five years (kg)", "type": "number", "min": 0},
        {"id": "highest_weight", "label": "Highest weight in five years (kg)", "type": "number", "min": 0},
        {"id": "ideal_weight", "label": "Ideal weight (kg)", "type": "number", "min": 0},
        {"id": "waist", "label": "Waist (cm)", "type": "number", "min": 0},
        {"id": "hip", "label": "Hip (cm)", "type": "number", "min": 0},
        {"id": "body_fat", "label": "Body fat (%)", "type": "number", "min": 0, "max": 100},
      ] },
      { title: "Weight measurements not known", fields: [
        {"id": "unknown_measurements", "label": "Measurements unknown or not taken", "type": "textarea"},
      ] },
      { title: "Goals", fields: [
        {"id": "readiness", "label": "Likelihood of adopting a healthy lifestyle (1–10)", "type": "number", "min": 1, "max": 10},
        {"id": "specific_goals", "label": "Specific goals?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "goals", "label": "Personal goals", "type": "textarea"},
        {"id": "weight_loss_goal", "label": "Weight loss goal?", "type": "select", "options": ["Yes", "No", "Unknown", "Not applicable"]},
        {"id": "weight_loss_details", "label": "Weight loss goal and reason", "type": "textarea"},
        {"id": "weight_loss_reason", "label": "Reason for wanting to lose weight", "type": "textarea"},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "cholesterol_total", "label": "Total cholesterol (include units)", "type": "text"},
        {"id": "cholesterol_hdl", "label": "HDL cholesterol (include units)", "type": "text"},
        {"id": "cholesterol_ldl", "label": "LDL cholesterol (include units)", "type": "text"},
        {"id": "triglycerides", "label": "Triglycerides (include units)", "type": "text"},
        {"id": "allergies_specify", "label": "Allergies — specify", "type": "text"},
        {"id": "surgeries_selected", "label": "Major surgeries — selected", "type": "checkbox"},
        {"id": "injuries_selected", "label": "Past injuries — selected", "type": "checkbox"},
        {"id": "other_conditions_selected", "label": "Other health conditions — selected", "type": "checkbox"},
        {"id": "family_0_selected", "label": "Family history — Heart disease", "type": "checkbox"},
        {"id": "family_0_relation", "label": "Heart disease — relationship", "type": "text"},
        {"id": "family_0_age", "label": "Heart disease — age at diagnosis", "type": "text"},
        {"id": "family_1_selected", "label": "Family history — High cholesterol", "type": "checkbox"},
        {"id": "family_1_relation", "label": "High cholesterol — relationship", "type": "text"},
        {"id": "family_1_age", "label": "High cholesterol — age at diagnosis", "type": "text"},
        {"id": "family_2_selected", "label": "Family history — High blood pressure", "type": "checkbox"},
        {"id": "family_2_relation", "label": "High blood pressure — relationship", "type": "text"},
        {"id": "family_2_age", "label": "High blood pressure — age at diagnosis", "type": "text"},
        {"id": "family_3_selected", "label": "Family history — Cancer", "type": "checkbox"},
        {"id": "family_3_relation", "label": "Cancer — relationship", "type": "text"},
        {"id": "family_3_age", "label": "Cancer — age at diagnosis", "type": "text"},
        {"id": "family_4_selected", "label": "Family history — Diabetes", "type": "checkbox"},
        {"id": "family_4_relation", "label": "Diabetes — relationship", "type": "text"},
        {"id": "family_4_age", "label": "Diabetes — age at diagnosis", "type": "text"},
        {"id": "family_5_selected", "label": "Family history — Osteoporosis", "type": "checkbox"},
        {"id": "family_5_relation", "label": "Osteoporosis — relationship", "type": "text"},
        {"id": "family_5_age", "label": "Osteoporosis — age at diagnosis", "type": "text"},
        {"id": "food_preparation_self", "label": "Food shopping and preparation — Self", "type": "checkbox"},
        {"id": "food_preparation_spouse", "label": "Food shopping and preparation — Spouse", "type": "checkbox"},
        {"id": "food_preparation_parent", "label": "Food shopping and preparation — Parent", "type": "checkbox"},
        {"id": "food_preparation_minimal", "label": "Food shopping and preparation — Minimal preparation", "type": "checkbox"},
        {"id": "alcohol_frequency", "label": "Alcohol — times per week", "type": "number", "min": 0},
        {"id": "alcohol_average", "label": "Alcohol — average amount", "type": "text"},
        {"id": "present_weight_unknown", "label": "Present weight — don’t know", "type": "checkbox"},
        {"id": "ideal_weight_unknown", "label": "Ideal weight — don’t know", "type": "checkbox"},
        {"id": "circumferences_unknown", "label": "Waist and hip — don’t know", "type": "checkbox"},
        {"id": "body_fat_unknown", "label": "Body fat — don’t know", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "upper_flexibility", title: "Upper Body Flexibility", subtitle: "Range of motion and observations", version: 1, source: "10_Flexibility_Assessment_Form-Upper_Body.pdf", paperTitle: "Flexibility Assessment Form: Upper Body",
    sections: [
      { title: "Shoulder flexion", fields: [
        {"id": "shoulder_flexion_observations", "label": "Shoulder flexion — observations", "type": "textarea"},
        {"id": "shoulder_flexion_left", "label": "Shoulder flexion — left (degrees)", "type": "number", "min": 0},
        {"id": "shoulder_flexion_right", "label": "Shoulder flexion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Shoulder extension", fields: [
        {"id": "shoulder_extension_observations", "label": "Shoulder extension — observations", "type": "textarea"},
        {"id": "shoulder_extension_left", "label": "Shoulder extension — left (degrees)", "type": "number", "min": 0},
        {"id": "shoulder_extension_right", "label": "Shoulder extension — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Shoulder abduction", fields: [
        {"id": "shoulder_abduction_observations", "label": "Shoulder abduction — observations", "type": "textarea"},
        {"id": "shoulder_abduction_left", "label": "Shoulder abduction — left (degrees)", "type": "number", "min": 0},
        {"id": "shoulder_abduction_right", "label": "Shoulder abduction — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Shoulder internal rotation", fields: [
        {"id": "shoulder_internal_observations", "label": "Shoulder internal rotation — observations", "type": "textarea"},
        {"id": "shoulder_internal_left", "label": "Shoulder internal rotation — left (degrees)", "type": "number", "min": 0},
        {"id": "shoulder_internal_right", "label": "Shoulder internal rotation — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Shoulder external rotation", fields: [
        {"id": "shoulder_external_observations", "label": "Shoulder external rotation — observations", "type": "textarea"},
        {"id": "shoulder_external_left", "label": "Shoulder external rotation — left (degrees)", "type": "number", "min": 0},
        {"id": "shoulder_external_right", "label": "Shoulder external rotation — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Shoulder horizontal adduction", fields: [
        {"id": "shoulder_horizontal_adduction_observations", "label": "Shoulder horizontal adduction — observations", "type": "textarea"},
        {"id": "shoulder_horizontal_adduction_left", "label": "Shoulder horizontal adduction — left (degrees)", "type": "number", "min": 0},
        {"id": "shoulder_horizontal_adduction_right", "label": "Shoulder horizontal adduction — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Shoulder horizontal abduction", fields: [
        {"id": "shoulder_horizontal_abduction_observations", "label": "Shoulder horizontal abduction — observations", "type": "textarea"},
        {"id": "shoulder_horizontal_abduction_left", "label": "Shoulder horizontal abduction — left (degrees)", "type": "number", "min": 0},
        {"id": "shoulder_horizontal_abduction_right", "label": "Shoulder horizontal abduction — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Elbow flexion", fields: [
        {"id": "elbow_flexion_observations", "label": "Elbow flexion — observations", "type": "textarea"},
        {"id": "elbow_flexion_left", "label": "Elbow flexion — left (degrees)", "type": "number", "min": 0},
        {"id": "elbow_flexion_right", "label": "Elbow flexion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Elbow extension", fields: [
        {"id": "elbow_extension_observations", "label": "Elbow extension — observations", "type": "textarea"},
        {"id": "elbow_extension_left", "label": "Elbow extension — left (degrees)", "type": "number", "min": 0},
        {"id": "elbow_extension_right", "label": "Elbow extension — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Forearm pronation", fields: [
        {"id": "pronation_observations", "label": "Forearm pronation — observations", "type": "textarea"},
        {"id": "pronation_left", "label": "Forearm pronation — left (degrees)", "type": "number", "min": 0},
        {"id": "pronation_right", "label": "Forearm pronation — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Forearm supination", fields: [
        {"id": "supination_observations", "label": "Forearm supination — observations", "type": "textarea"},
        {"id": "supination_left", "label": "Forearm supination — left (degrees)", "type": "number", "min": 0},
        {"id": "supination_right", "label": "Forearm supination — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Wrist flexion", fields: [
        {"id": "wrist_flexion_observations", "label": "Wrist flexion — observations", "type": "textarea"},
        {"id": "wrist_flexion_left", "label": "Wrist flexion — left (degrees)", "type": "number", "min": 0},
        {"id": "wrist_flexion_right", "label": "Wrist flexion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Wrist extension", fields: [
        {"id": "wrist_extension_observations", "label": "Wrist extension — observations", "type": "textarea"},
        {"id": "wrist_extension_left", "label": "Wrist extension — left (degrees)", "type": "number", "min": 0},
        {"id": "wrist_extension_right", "label": "Wrist extension — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Wrist radial deviation", fields: [
        {"id": "radial_deviation_observations", "label": "Wrist radial deviation — observations", "type": "textarea"},
        {"id": "radial_deviation_left", "label": "Wrist radial deviation — left (degrees)", "type": "number", "min": 0},
        {"id": "radial_deviation_right", "label": "Wrist radial deviation — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Wrist ulnar deviation", fields: [
        {"id": "ulnar_deviation_observations", "label": "Wrist ulnar deviation — observations", "type": "textarea"},
        {"id": "ulnar_deviation_left", "label": "Wrist ulnar deviation — left (degrees)", "type": "number", "min": 0},
        {"id": "ulnar_deviation_right", "label": "Wrist ulnar deviation — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "shoulder_flexion_reference_checked", "label": "Shoulder flexion — paper ROM checkbox", "type": "checkbox"},
        {"id": "shoulder_extension_reference_checked", "label": "Shoulder extension — paper ROM checkbox", "type": "checkbox"},
        {"id": "shoulder_abduction_reference_checked", "label": "Shoulder abduction — paper ROM checkbox", "type": "checkbox"},
        {"id": "shoulder_internal_reference_checked", "label": "Shoulder internal rotation — paper ROM checkbox", "type": "checkbox"},
        {"id": "shoulder_external_reference_checked", "label": "Shoulder external rotation — paper ROM checkbox", "type": "checkbox"},
        {"id": "shoulder_horizontal_adduction_reference_checked", "label": "Shoulder horizontal adduction — paper ROM checkbox", "type": "checkbox"},
        {"id": "shoulder_horizontal_abduction_reference_checked", "label": "Shoulder horizontal abduction — paper ROM checkbox", "type": "checkbox"},
        {"id": "elbow_flexion_reference_checked", "label": "Elbow flexion — paper ROM checkbox", "type": "checkbox"},
        {"id": "elbow_extension_reference_checked", "label": "Elbow extension — paper ROM checkbox", "type": "checkbox"},
        {"id": "pronation_reference_checked", "label": "Forearm pronation — paper ROM checkbox", "type": "checkbox"},
        {"id": "supination_reference_checked", "label": "Forearm supination — paper ROM checkbox", "type": "checkbox"},
        {"id": "wrist_flexion_reference_checked", "label": "Wrist flexion — paper ROM checkbox", "type": "checkbox"},
        {"id": "wrist_extension_reference_checked", "label": "Wrist extension — paper ROM checkbox", "type": "checkbox"},
        {"id": "radial_deviation_reference_checked", "label": "Wrist radial deviation — paper ROM checkbox", "type": "checkbox"},
        {"id": "ulnar_deviation_reference_checked", "label": "Wrist ulnar deviation — paper ROM checkbox", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "lower_flexibility", title: "Lower Body Flexibility", subtitle: "Range of motion and observations", version: 1, source: "11_Flexibility_Assessment_Form-Lower_Body.pdf", paperTitle: "Flexibility Assessment Form: Lower Body",
    sections: [
      { title: "Hip flexion", fields: [
        {"id": "hip_flexion_observations", "label": "Hip flexion — observations", "type": "textarea"},
        {"id": "hip_flexion_left", "label": "Hip flexion — left (degrees)", "type": "number", "min": 0},
        {"id": "hip_flexion_right", "label": "Hip flexion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Hip extension", fields: [
        {"id": "hip_extension_observations", "label": "Hip extension — observations", "type": "textarea"},
        {"id": "hip_extension_left", "label": "Hip extension — left (degrees)", "type": "number", "min": 0},
        {"id": "hip_extension_right", "label": "Hip extension — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Hip abduction", fields: [
        {"id": "hip_abduction_observations", "label": "Hip abduction — observations", "type": "textarea"},
        {"id": "hip_abduction_left", "label": "Hip abduction — left (degrees)", "type": "number", "min": 0},
        {"id": "hip_abduction_right", "label": "Hip abduction — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Hip adduction", fields: [
        {"id": "hip_adduction_observations", "label": "Hip adduction — observations", "type": "textarea"},
        {"id": "hip_adduction_left", "label": "Hip adduction — left (degrees)", "type": "number", "min": 0},
        {"id": "hip_adduction_right", "label": "Hip adduction — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Hip internal rotation", fields: [
        {"id": "hip_internal_observations", "label": "Hip internal rotation — observations", "type": "textarea"},
        {"id": "hip_internal_left", "label": "Hip internal rotation — left (degrees)", "type": "number", "min": 0},
        {"id": "hip_internal_right", "label": "Hip internal rotation — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Hip external rotation", fields: [
        {"id": "hip_external_observations", "label": "Hip external rotation — observations", "type": "textarea"},
        {"id": "hip_external_left", "label": "Hip external rotation — left (degrees)", "type": "number", "min": 0},
        {"id": "hip_external_right", "label": "Hip external rotation — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Knee flexion", fields: [
        {"id": "knee_flexion_observations", "label": "Knee flexion — observations", "type": "textarea"},
        {"id": "knee_flexion_left", "label": "Knee flexion — left (degrees)", "type": "number", "min": 0},
        {"id": "knee_flexion_right", "label": "Knee flexion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Knee extension", fields: [
        {"id": "knee_extension_observations", "label": "Knee extension — observations", "type": "textarea"},
        {"id": "knee_extension_left", "label": "Knee extension — left (degrees)", "type": "number", "min": 0},
        {"id": "knee_extension_right", "label": "Knee extension — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Ankle dorsiflexion", fields: [
        {"id": "ankle_dorsiflexion_observations", "label": "Ankle dorsiflexion — observations", "type": "textarea"},
        {"id": "ankle_dorsiflexion_left", "label": "Ankle dorsiflexion — left (degrees)", "type": "number", "min": 0},
        {"id": "ankle_dorsiflexion_right", "label": "Ankle dorsiflexion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Ankle plantarflexion", fields: [
        {"id": "ankle_plantarflexion_observations", "label": "Ankle plantarflexion — observations", "type": "textarea"},
        {"id": "ankle_plantarflexion_left", "label": "Ankle plantarflexion — left (degrees)", "type": "number", "min": 0},
        {"id": "ankle_plantarflexion_right", "label": "Ankle plantarflexion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Subtalar inversion", fields: [
        {"id": "subtalar_inversion_observations", "label": "Subtalar inversion — observations", "type": "textarea"},
        {"id": "subtalar_inversion_left", "label": "Subtalar inversion — left (degrees)", "type": "number", "min": 0},
        {"id": "subtalar_inversion_right", "label": "Subtalar inversion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Subtalar eversion", fields: [
        {"id": "subtalar_eversion_observations", "label": "Subtalar eversion — observations", "type": "textarea"},
        {"id": "subtalar_eversion_left", "label": "Subtalar eversion — left (degrees)", "type": "number", "min": 0},
        {"id": "subtalar_eversion_right", "label": "Subtalar eversion — right (degrees)", "type": "number", "min": 0},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "hip_flexion_reference_checked", "label": "Hip flexion — paper ROM checkbox", "type": "checkbox"},
        {"id": "hip_extension_reference_checked", "label": "Hip extension — paper ROM checkbox", "type": "checkbox"},
        {"id": "hip_abduction_reference_checked", "label": "Hip abduction — paper ROM checkbox", "type": "checkbox"},
        {"id": "hip_adduction_reference_checked", "label": "Hip adduction — paper ROM checkbox", "type": "checkbox"},
        {"id": "hip_internal_reference_checked", "label": "Hip internal rotation — paper ROM checkbox", "type": "checkbox"},
        {"id": "hip_external_reference_checked", "label": "Hip external rotation — paper ROM checkbox", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "hurdle_step", title: "Hurdle Step Screen", subtitle: "Stepping over a hurdle", version: 1, source: "03-02-CMES-HurdleStepScreen.pdf", paperTitle: "Hurdle-Step Screen",
    sections: [
      { title: "Assessment details", fields: [
        {"id": "side", "label": "Side assessed", "type": "select", "options": ["Left", "Right", "Both", "Not recorded"]},
      ] },
      { title: "Front view: feet", fields: [
        {"id": "feet_observation", "label": "Front view: feet — compensation observed", "type": "textarea"},
        {"id": "feet_overactive", "label": "Front view: feet — suspected overactive muscles", "type": "textarea"},
        {"id": "feet_underactive", "label": "Front view: feet — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: knees", fields: [
        {"id": "knees_observation", "label": "Front view: knees — compensation observed", "type": "textarea"},
        {"id": "knees_overactive", "label": "Front view: knees — suspected overactive muscles", "type": "textarea"},
        {"id": "knees_underactive", "label": "Front view: knees — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: hips", fields: [
        {"id": "hips_observation", "label": "Front view: hips — compensation observed", "type": "textarea"},
        {"id": "hips_overactive", "label": "Front view: hips — suspected overactive muscles", "type": "textarea"},
        {"id": "hips_underactive", "label": "Front view: hips — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: torso", fields: [
        {"id": "torso_observation", "label": "Front view: torso — compensation observed", "type": "textarea"},
        {"id": "torso_overactive", "label": "Front view: torso — suspected overactive muscles", "type": "textarea"},
        {"id": "torso_underactive", "label": "Front view: torso — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: raised leg", fields: [
        {"id": "raised_leg_observation", "label": "Front view: raised leg — compensation observed", "type": "textarea"},
        {"id": "raised_leg_overactive", "label": "Front view: raised leg — suspected overactive muscles", "type": "textarea"},
        {"id": "raised_leg_underactive", "label": "Front view: raised leg — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: pelvis / low back", fields: [
        {"id": "pelvis_observation", "label": "Side view: pelvis / low back — compensation observed", "type": "textarea"},
        {"id": "pelvis_overactive", "label": "Side view: pelvis / low back — suspected overactive muscles", "type": "textarea"},
        {"id": "pelvis_underactive", "label": "Side view: pelvis / low back — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "feet_reference_observed", "label": "Front view: feet — reference finding observed", "type": "checkbox"},
        {"id": "knees_reference_observed", "label": "Front view: knees — reference finding observed", "type": "checkbox"},
        {"id": "hips_reference_observed", "label": "Front view: hips — reference finding observed", "type": "checkbox"},
        {"id": "torso_reference_observed", "label": "Front view: torso — reference finding observed", "type": "checkbox"},
        {"id": "raised_leg_reference_observed", "label": "Front view: raised leg — reference finding observed", "type": "checkbox"},
        {"id": "pelvis_reference_observed", "label": "Side view: pelvis / low back — reference finding observed", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "bend_lift", title: "Bend & Lift", subtitle: "Squat movement pattern", version: 1, source: "23_Bend_and_Lift_Assessment_Form.pdf", paperTitle: "Bend-and-Lift Assessment Form",
    sections: [
      { title: "Front view: feet", fields: [
        {"id": "front_feet_observation", "label": "Front view: feet — compensation observed", "type": "textarea"},
        {"id": "front_feet_overactive", "label": "Front view: feet — suspected overactive muscles", "type": "textarea"},
        {"id": "front_feet_underactive", "label": "Front view: feet — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: knees", fields: [
        {"id": "front_knees_observation", "label": "Front view: knees — compensation observed", "type": "textarea"},
        {"id": "front_knees_overactive", "label": "Front view: knees — suspected overactive muscles", "type": "textarea"},
        {"id": "front_knees_underactive", "label": "Front view: knees — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: torso", fields: [
        {"id": "front_torso_observation", "label": "Front view: torso — compensation observed", "type": "textarea"},
        {"id": "front_torso_overactive", "label": "Front view: torso — suspected overactive muscles", "type": "textarea"},
        {"id": "front_torso_underactive", "label": "Front view: torso — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: feet", fields: [
        {"id": "side_feet_observation", "label": "Side view: feet — compensation observed", "type": "textarea"},
        {"id": "side_feet_overactive", "label": "Side view: feet — suspected overactive muscles", "type": "textarea"},
        {"id": "side_feet_underactive", "label": "Side view: feet — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: hip / knee", fields: [
        {"id": "hip_knee_observation", "label": "Side view: hip / knee — compensation observed", "type": "textarea"},
        {"id": "hip_knee_overactive", "label": "Side view: hip / knee — suspected overactive muscles", "type": "textarea"},
        {"id": "hip_knee_underactive", "label": "Side view: hip / knee — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: hip / knee — contact behind knee", fields: [
        {"id": "knee_contact_observation", "label": "Side view: hip / knee — contact behind knee — compensation observed", "type": "textarea"},
        {"id": "knee_contact_overactive", "label": "Side view: hip / knee — contact behind knee — suspected overactive muscles", "type": "textarea"},
        {"id": "knee_contact_underactive", "label": "Side view: hip / knee — contact behind knee — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: lumbar / thoracic spine", fields: [
        {"id": "spine_observation", "label": "Side view: lumbar / thoracic spine — compensation observed", "type": "textarea"},
        {"id": "spine_overactive", "label": "Side view: lumbar / thoracic spine — suspected overactive muscles", "type": "textarea"},
        {"id": "spine_underactive", "label": "Side view: lumbar / thoracic spine — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: head", fields: [
        {"id": "head_observation", "label": "Side view: head — compensation observed", "type": "textarea"},
        {"id": "head_overactive", "label": "Side view: head — suspected overactive muscles", "type": "textarea"},
        {"id": "head_underactive", "label": "Side view: head — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "front_feet_selected", "label": "Front view: feet — selected", "type": "checkbox"},
        {"id": "front_knees_selected", "label": "Front view: knees — selected", "type": "checkbox"},
        {"id": "front_torso_selected", "label": "Front view: torso — selected", "type": "checkbox"},
        {"id": "front_torso_compensations", "label": "Front view: torso — key suspected compensations", "type": "textarea"},
        {"id": "side_feet_selected", "label": "Side view: feet — selected", "type": "checkbox"},
        {"id": "hip_knee_selected", "label": "Side view: hip / knee — selected", "type": "checkbox"},
        {"id": "hip_knee_compensations", "label": "Side view: hip / knee — key suspected compensations", "type": "textarea"},
        {"id": "knee_contact_selected", "label": "Side view: hip / knee — contact behind knee — selected", "type": "checkbox"},
        {"id": "knee_contact_compensations", "label": "Side view: hip / knee — contact behind knee — key suspected compensations", "type": "textarea"},
        {"id": "spine_selected", "label": "Side view: lumbar / thoracic spine — selected", "type": "checkbox"},
        {"id": "head_selected", "label": "Side view: head — selected", "type": "checkbox"},
        {"id": "head_compensations", "label": "Side view: head — key suspected compensations", "type": "textarea"},
      ] },
    ],
  },
  {
    id: "single_leg", title: "Single-Leg Assessment", subtitle: "Step-up movement pattern", version: 1, source: "25_Single_Leg_Assessment_Form.pdf", paperTitle: "Single-Leg Assessment Form",
    sections: [
      { title: "Assessment details", fields: [
        {"id": "side", "label": "Side assessed", "type": "select", "options": ["Left", "Right", "Both", "Not recorded"]},
      ] },
      { title: "Front view: feet", fields: [
        {"id": "feet_observation", "label": "Front view: feet — compensation observed", "type": "textarea"},
        {"id": "feet_overactive", "label": "Front view: feet — suspected overactive muscles", "type": "textarea"},
        {"id": "feet_underactive", "label": "Front view: feet — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: knees", fields: [
        {"id": "knees_observation", "label": "Front view: knees — compensation observed", "type": "textarea"},
        {"id": "knees_overactive", "label": "Front view: knees — suspected overactive muscles", "type": "textarea"},
        {"id": "knees_underactive", "label": "Front view: knees — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: hips", fields: [
        {"id": "hips_observation", "label": "Front view: hips — compensation observed", "type": "textarea"},
        {"id": "hips_overactive", "label": "Front view: hips — suspected overactive muscles", "type": "textarea"},
        {"id": "hips_underactive", "label": "Front view: hips — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: torso", fields: [
        {"id": "torso_observation", "label": "Front view: torso — compensation observed", "type": "textarea"},
        {"id": "torso_overactive", "label": "Front view: torso — suspected overactive muscles", "type": "textarea"},
        {"id": "torso_underactive", "label": "Front view: torso — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Front view: raised leg", fields: [
        {"id": "raised_leg_observation", "label": "Front view: raised leg — compensation observed", "type": "textarea"},
        {"id": "raised_leg_overactive", "label": "Front view: raised leg — suspected overactive muscles", "type": "textarea"},
        {"id": "raised_leg_underactive", "label": "Front view: raised leg — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: pelvis / low back", fields: [
        {"id": "pelvis_observation", "label": "Side view: pelvis / low back — compensation observed", "type": "textarea"},
        {"id": "pelvis_overactive", "label": "Side view: pelvis / low back — suspected overactive muscles", "type": "textarea"},
        {"id": "pelvis_underactive", "label": "Side view: pelvis / low back — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "feet_selected", "label": "Front view: feet — selected", "type": "checkbox"},
        {"id": "knees_selected", "label": "Front view: knees — selected", "type": "checkbox"},
        {"id": "hips_selected", "label": "Front view: hips — selected", "type": "checkbox"},
        {"id": "torso_selected", "label": "Front view: torso — selected", "type": "checkbox"},
        {"id": "torso_compensations", "label": "Front view: torso — key suspected compensations", "type": "textarea"},
        {"id": "raised_leg_selected", "label": "Front view: raised leg — selected", "type": "checkbox"},
        {"id": "pelvis_selected", "label": "Side view: pelvis / low back — selected", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "push", title: "Push Assessment", subtitle: "Shoulder push stabilization", version: 1, source: "27_Push_Assessment_Form.pdf", paperTitle: "Push Assessment Form",
    sections: [
      { title: "Side view: scapulothoracic", fields: [
        {"id": "scapula_observation", "label": "Side view: scapulothoracic — compensation observed", "type": "textarea"},
        {"id": "scapula_suspected", "label": "Side view: scapulothoracic — key suspected compensations", "type": "textarea"},
      ] },
      { title: "Side view: trunk", fields: [
        {"id": "trunk_observation", "label": "Side view: trunk — compensation observed", "type": "textarea"},
        {"id": "trunk_suspected", "label": "Side view: trunk — key suspected compensations", "type": "textarea"},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "scapula_selected", "label": "Side view: scapulothoracic — selected", "type": "checkbox"},
        {"id": "trunk_selected", "label": "Side view: trunk — selected", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "pull", title: "Pull Assessment", subtitle: "Standing row", version: 1, source: "29_Pull_Assessment_Form.pdf", paperTitle: "Pull Assessment Form",
    sections: [
      { title: "Side view: lumbar spine", fields: [
        {"id": "lumbar_observation", "label": "Side view: lumbar spine — compensation observed", "type": "textarea"},
        {"id": "lumbar_overactive", "label": "Side view: lumbar spine — suspected overactive muscles", "type": "textarea"},
        {"id": "lumbar_underactive", "label": "Side view: lumbar spine — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Rear view: scapulothoracic (1)", fields: [
        {"id": "scapula_1_observation", "label": "Rear view: scapulothoracic (1) — compensation observed", "type": "textarea"},
        {"id": "scapula_1_overactive", "label": "Rear view: scapulothoracic (1) — suspected overactive muscles", "type": "textarea"},
        {"id": "scapula_1_underactive", "label": "Rear view: scapulothoracic (1) — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Side view: head", fields: [
        {"id": "head_observation", "label": "Side view: head — compensation observed", "type": "textarea"},
        {"id": "head_overactive", "label": "Side view: head — suspected overactive muscles", "type": "textarea"},
        {"id": "head_underactive", "label": "Side view: head — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Rear view: scapulothoracic (2)", fields: [
        {"id": "scapula_2_observation", "label": "Rear view: scapulothoracic (2) — compensation observed", "type": "textarea"},
        {"id": "scapula_2_overactive", "label": "Rear view: scapulothoracic (2) — suspected overactive muscles", "type": "textarea"},
        {"id": "scapula_2_underactive", "label": "Rear view: scapulothoracic (2) — suspected underactive muscles", "type": "textarea"},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "lumbar_selected", "label": "Side view: lumbar spine — selected", "type": "checkbox"},
        {"id": "scapula_1_selected", "label": "Rear view: scapulothoracic (1) — selected", "type": "checkbox"},
        {"id": "head_selected", "label": "Side view: head — selected", "type": "checkbox"},
        {"id": "scapula_2_selected", "label": "Rear view: scapulothoracic (2) — selected", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "rotation", title: "Rotation Assessment", subtitle: "Thoracic spine mobility", version: 1, source: "31_Rotation_Assessment_Form.pdf", paperTitle: "Rotation Assessment Form",
    sections: [
      { title: "Front / rear view: trunk (1)", fields: [
        {"id": "trunk_1_observation", "label": "Front / rear view: trunk (1) — compensation observed", "type": "textarea"},
        {"id": "trunk_1_biomechanical", "label": "Front / rear view: trunk (1) — possible biomechanical problems", "type": "textarea"},
      ] },
      { title: "Front / rear view: trunk (2)", fields: [
        {"id": "trunk_2_observation", "label": "Front / rear view: trunk (2) — compensation observed", "type": "textarea"},
        {"id": "trunk_2_biomechanical", "label": "Front / rear view: trunk (2) — possible biomechanical problems", "type": "textarea"},
      ] },
      { title: "Paper form answers", fields: [
        {"id": "trunk_1_selected", "label": "Front / rear view: trunk (1) — selected", "type": "checkbox"},
        {"id": "trunk_2_selected", "label": "Front / rear view: trunk (2) — selected", "type": "checkbox"},
      ] },
    ],
  },
  {
    id: "balance", title: "Static Balance", subtitle: "Unipedal stance · three trials", version: 1, source: "35_Static_Balance_Assessment_Form.pdf", paperTitle: "Static Balance Assessment Form",
    sections: [
      { title: "Assessment details", fields: [
        {"id": "side", "label": "Side assessed", "type": "select", "options": ["Left", "Right", "Both", "Not recorded"]},
      ] },
      { title: "Unipedal Stance Test", fields: [
        {"id": "eyes_open_1", "label": "Eyes open — trial 1 (seconds)", "type": "number", "min": 0},
        {"id": "eyes_closed_1", "label": "Eyes closed — trial 1 (seconds)", "type": "number", "min": 0},
        {"id": "eyes_open_2", "label": "Eyes open — trial 2 (seconds)", "type": "number", "min": 0},
        {"id": "eyes_closed_2", "label": "Eyes closed — trial 2 (seconds)", "type": "number", "min": 0},
        {"id": "eyes_open_3", "label": "Eyes open — trial 3 (seconds)", "type": "number", "min": 0},
        {"id": "eyes_closed_3", "label": "Eyes closed — trial 3 (seconds)", "type": "number", "min": 0},
      ] },
    ],
  },
  {
    id: "anthropometric", title: "Anthropometric Measurements", subtitle: "Body measurements and skinfolds", version: 1, source: "46_Anthropometric_Measurements_Form.pdf", paperTitle: "Anthropometric Measurements Form",
    sections: [
      { title: "Height, Weight, and Body Mass Index", fields: [
        {"id": "weight_lb", "label": "Weight (lb)", "type": "number", "min": 0},
        {"id": "height_in", "label": "Height (in)", "type": "number", "min": 0},
        {"id": "weight", "label": "Weight (kg)", "type": "number", "min": 0},
        {"id": "height", "label": "Height (m)", "type": "number", "min": 0},
        {"id": "bmi", "label": "Recorded BMI (kg/m²)", "type": "number", "min": 0},
      ] },
      { title: "Skinfold Measurements", fields: [
        {"id": "male_chest", "label": "Chest skinfold (mm)", "type": "number", "min": 0},
        {"id": "female_triceps", "label": "Triceps skinfold (mm)", "type": "number", "min": 0},
        {"id": "male_abdomen", "label": "Abdomen skinfold (mm)", "type": "number", "min": 0},
        {"id": "female_suprailium", "label": "Suprailium skinfold (mm)", "type": "number", "min": 0},
        {"id": "male_thigh", "label": "Male thigh skinfold (mm)", "type": "number", "min": 0},
        {"id": "female_thigh", "label": "Female thigh skinfold (mm)", "type": "number", "min": 0},
        {"id": "male_total", "label": "Male skinfold total (mm)", "type": "number", "min": 0},
        {"id": "female_total", "label": "Female skinfold total (mm)", "type": "number", "min": 0},
      ] },
      { title: "Body-fat estimation", fields: [
        {"id": "body_fat", "label": "Estimated body fat (%)", "type": "number", "min": 0, "max": 100},
        {"id": "body_fat_method", "label": "Body fat estimation method", "type": "text"},
      ] },
      { title: "Circumference Measurements", fields: [
        {"id": "abdomen", "label": "Abdomen circumference (cm)", "type": "number", "min": 0},
        {"id": "hip", "label": "Hip circumference (cm)", "type": "number", "min": 0},
        {"id": "waist", "label": "Waist circumference (cm)", "type": "number", "min": 0},
        {"id": "ratio", "label": "Recorded waist-to-hip ratio", "type": "number", "min": 0},
        {"id": "biceps", "label": "Biceps circumference (cm)", "type": "number", "min": 0},
        {"id": "thigh", "label": "Mid-thigh circumference (cm)", "type": "number", "min": 0},
      ] },
    ],
  },
]

export const assessmentFields = definition => [...definition.sections.flatMap(item => item.fields), notes('notes', 'Additional observations / items not assessed')]
export const assessmentForm = id => ASSESSMENT_FORMS.find(item => item.id === id)
const hasValue = value => value !== undefined && value !== null && String(value).trim() !== ''
const validDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value

export function assessmentErrors(id, draft) {
  const definition = assessmentForm(id)
  if (!definition || !draft || typeof draft !== 'object') return { form: 'Choose a supported assessment form.' }
  const errors = {}
  if (!validDate(draft.date)) errors.date = 'Enter a valid assessment date.'
  if (typeof draft.assessor !== 'string' || !draft.assessor.trim()) errors.assessor = 'Enter the assessor’s name.'
  const fields = assessmentFields(definition)
  const answers = draft.answers
  if (!answers || typeof answers !== 'object' || Array.isArray(answers)) return { ...errors, answers: 'Record at least one answer or observation.' }
  if (Object.keys(answers).some(key => !fields.some(field => field.id === key))) errors.answers = 'This form contains an unsupported field.'
  // This paper checklist has no free-answer slots; an explicitly saved unchecked checklist is valid.
  if (id !== 'hurdle_step' && !fields.some(field => field.id !== 'side' && hasValue(answers[field.id]))) errors.answers = 'Record at least one answer or observation.'
  for (const field of fields) {
    const value = answers[field.id]
    if (!hasValue(value)) continue
    if (typeof value !== 'string' && typeof value !== 'number') errors[field.id] = 'Enter a text or numeric answer.'
    else if (field.type === 'checkbox' && value !== 'Yes') errors[field.id] = 'Select the condition or leave it unselected.'
    else if (field.type === 'select' && !field.options.includes(value)) errors[field.id] = 'Choose a listed option.'
    else if (field.type === 'number' && (!Number.isFinite(Number(value)) || Number(value) < field.min || (field.max !== undefined && Number(value) > field.max))) {
      errors[field.id] = field.max === undefined ? `Enter a number of ${field.min} or more.` : `Enter a number from ${field.min} to ${field.max}.`
    }
  }
  return errors
}

export function saveAssessment(id, draft, savedAt = new Date().toISOString()) {
  const errors = assessmentErrors(id, draft)
  if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
  const definition = assessmentForm(id)
  const answers = Object.fromEntries(assessmentFields(definition).filter(field => hasValue(draft.answers[field.id])).map(field =>
    [field.id, field.type === 'number' ? Number(draft.answers[field.id]) : String(draft.answers[field.id]).trim()]))
  return { formId: id, version: definition.version, status: 'filled', date: draft.date, assessor: draft.assessor.trim(), savedAt, answers }
}

export function normaliseAssessments(records = {}) {
  if (!records || typeof records !== 'object' || Array.isArray(records)) throw new Error('Review the assessment records.')
  return Object.fromEntries(Object.entries(records).map(([id, record]) => {
    if (record?.formId !== id || record.version !== assessmentForm(id)?.version || record.status !== 'filled'
      || typeof record.savedAt !== 'string' || !Number.isFinite(Date.parse(record.savedAt))) throw new Error('Review the assessment record version and status.')
    return [id, saveAssessment(id, record, record.savedAt)]
  }))
}
