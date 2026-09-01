# First run on your Mac

## 1. Check Node
Open Terminal inside this project folder and run:

```bash
node -v
npm -v
```

Use Node 22 if possible. Current Vite 8 requires a modern Node release.

## 2. Install dependencies

```bash
npm install
```

This creates `node_modules` and `package-lock.json`. Commit `package-lock.json` once the first install succeeds so future installs are reproducible.

## 3. Open the app in your browser

```bash
npm run dev -- --host
```

Vite prints both a Local URL and a Network URL.

- On your Mac: open the Local URL.
- On an iPhone/iPad connected to the same Wi-Fi: open the Network URL.
- Keep Terminal running while testing.
- Stop the server with Control+C.

## 4. What to test first

1. Owner / Chau → Clients → Amanda Lim → View.
2. Confirm Overview order: General Information + Fixed Weekly Schedule, then Health / Limitation Notes, then Remarks.
3. Edit General Information and refresh; mock state should persist.
4. Owner → Trainers → Marcus Tan → Edit Autonomy & Approvals.
5. All four boxes should initially be checked.
6. Uncheck Session time changes → Save → Edit again; it should remain unchecked.
7. Switch Mock identity to Marcus Tan.
8. Clients should show only Amanda Lim.
9. Amanda's general information is read-only, while Health / Limitation Notes and Remarks remain editable for the assigned trainer.
10. Click Reset Demo Data to restore the seed state.

## 5. Run fast tests

```bash
npm test
npm run build
```

## 6. Install browser-test engines once

```bash
npx playwright install
```

Then run:

```bash
npm run test:e2e
```

The current Playwright configuration checks desktop Chrome, an iPhone-sized viewport, and iPad.

## 7. Test the production bundle

```bash
npm run build
npm run preview -- --host
```

Use this before accepting a migration slice. Development mode alone is not the final gate.
