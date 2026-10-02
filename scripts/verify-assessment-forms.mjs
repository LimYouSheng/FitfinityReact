// Cross-language release check: the frozen DB definition must match the current paper UI.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { ASSESSMENT_FORMS, assessmentFields } from '../src/app/assessmentForms.js'

const root = fileURLToPath(new URL('../', import.meta.url))
const read = path => readFileSync(resolve(root, path))
const digest = bytes => createHash('sha256').update(bytes).digest('hex')
const layouts = JSON.parse(read('src/app/assessmentPaperLayouts.json'))
const definitions = JSON.parse(read('backend/migrations/definitions/20260921_assessments_v1.json'))
assert.equal(ASSESSMENT_FORMS.length, 11, 'Review the form release when the source set changes')
assert.equal(definitions.length, ASSESSMENT_FORMS.length)
let answerFields = 0
for (const form of ASSESSMENT_FORMS) {
  const stored = definitions.find(row => row.form_id === form.id && row.version === form.version)
  assert.ok(stored, `Missing database form version: ${form.id}`)
  assert.equal(stored.title, form.title)
  assert.equal(stored.source_filename, form.source)
  assert.equal(stored.source_sha256, digest(read(`public/assessment-forms/${form.source}`)))
  assert.equal(stored.layout_sha256, digest(JSON.stringify(layouts[form.id])))
  assert.deepEqual(stored.definition.pages, layouts[form.id].map(page => ({
    asset: page.asset, sha256: digest(read(`public/assessment-forms/pages/${page.asset}`)),
  })))
  const placements = layouts[form.id].flatMap(page => page.fields).filter(field => !field.id.startsWith('$'))
  const paperIds = new Set(placements.map(field => field.id))
  const fields = {}
  for (const field of assessmentFields(form).filter(field => paperIds.has(field.id))) {
    const expected = { type: field.type, label: field.label }
    if (field.type === 'number') {
      expected.min = field.min
      if (field.max !== undefined) expected.max = field.max
    } else if (field.type === 'select' || field.type === 'checkbox') {
      expected.options = [...new Set(placements.filter(item => item.id === field.id).map(item => item.value))]
      assert.ok(expected.options.every(option => typeof option === 'string'))
    } else expected.max_length = field.type === 'textarea' ? 4000 : 500
    fields[field.id] = expected
  }
  assert.equal(Object.keys(fields).length, paperIds.size)
  assert.deepEqual(stored.definition.fields, fields, `Paper/backend answer drift: ${form.id}`)
  assert.deepEqual(stored.definition.legacy_field_ids,
    assessmentFields(form).filter(field => !paperIds.has(field.id)).map(field => field.id))
  assert.equal(stored.definition.allow_empty_completion, form.id === 'hurdle_step')
  assert.equal(stored.definition.max_bytes, 65536)
  answerFields += paperIds.size
}
console.log(`\u001b[32mPASS — ${definitions.length} immutable form versions / ${answerFields} paper answer fields match the frontend and source assets.\u001b[0m`)
