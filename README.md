# Fitfinity canonical React frontend — M1

This is the first clean React/Vite reconstruction slice based on the frozen v0.57 behaviour.

## Included in M1
- React-owned owner/trainer portal shell
- development-only mock identity switcher
- deterministic mock data with localStorage persistence
- owner/trainer client list filtering
- client profile Overview with v0.57 section order
- owner-only General Information and Fixed Weekly Schedule editing
- assigned-trainer Health / Limitation Notes and Remarks editing
- trainer approval-needed settings with final checkbox semantics
- Vitest domain tests
- Playwright desktop/phone/iPad smoke tests

## Intentionally not migrated yet
Requests, Sessions, Remuneration, Exercise Library, Website Content, the public-facing website, and full PWA/service-worker behaviour remain subsequent migration slices.

## Local run
```bash
npm install
npm run dev -- --host
```
Open the localhost URL shown by Vite. For another device on the same Wi-Fi, use the Network URL printed by Vite.

## Tests
```bash
npm test
npm run build
npx playwright install
npm run test:e2e
```

## Rule
Do not import the old v0.xx patch CSS/JS chain into this app. Reconstruct final behaviour in the owning React feature and protect it with tests.
