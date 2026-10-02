import js from '@eslint/js'
import globals from 'globals'
import hooks from 'eslint-plugin-react-hooks'

export default [
  { ignores: ['node_modules/**', 'dist/**', 'dist-pages/**', 'dist-api-test/**', 'coverage/**', 'test-results/**', 'playwright-report/**'] },
  {
    files: ['src/**/*.{js,jsx}', 'scripts/**/*.mjs', 'tests/**/*.{js,mjs}', '*.js', 'public/**/*.js'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: 'error' },
    rules: {
      ...js.configs.recommended.rules,
      'no-unused-vars': ['error', { args: 'after-used', caughtErrors: 'none', ignoreRestSiblings: true }],
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
  { files: ['src/**/*.{js,jsx}'], languageOptions: { globals: globals.browser },
    plugins: { 'react-hooks': hooks }, rules: { 'react-hooks/rules-of-hooks': 'error', 'react-hooks/exhaustive-deps': 'error' } },
  { files: ['tests/**/*.{js,mjs}'], languageOptions: { globals: globals.browser } },
  // Playwright requires an empty destructured first fixture argument.
  { files: ['tests/auth-api-fixture.js'], rules: { 'no-empty-pattern': ['error', { allowObjectPatternsAsParameters: true }] } },
  // These expressions deliberately strip control characters from text/logs.
  { files: ['src/utils/reportText.js', 'scripts/verify-test-results.mjs'], rules: { 'no-control-regex': 'off' } },
  { files: ['scripts/**/*.mjs', 'tests/**/*.{js,mjs}', '*.js', 'src/**/*.test.{js,jsx}', 'src/test/**'], languageOptions: { globals: globals.node } },
  { files: ['public/sw.js'], languageOptions: { globals: globals.serviceworker } },
]
