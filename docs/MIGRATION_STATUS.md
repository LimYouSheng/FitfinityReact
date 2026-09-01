# Fitfinity React migration status

Frozen behavioural source: **v0.57 FREEZE CANDIDATE**  
Source ZIP SHA-256: `f431939349c446f8c21a2d2d1596811f7bcfcd5ceb454389a1bbb039645bb723`

## M1 — implemented now

- Canonical React/Vite application shell.
- Owner/trainer mock identity switcher.
- Mock repository/service boundary and browser persistence.
- Owner/trainer navigation ownership.
- Client list with trainer scoping.
- Client Profile → Overview final v0.57 order.
- Owner edit rights for General Information and Fixed Weekly Schedule.
- Assigned trainer edit rights for Health / Limitation Notes and Remarks.
- Trainer autonomy editor with user-facing **Owner approval needed** checkbox semantics.
- Unit tests for autonomy inversion and package-day bounds.
- Playwright smoke tests for client-profile order, autonomy checkbox state, and trainer client scoping.

## M2 — next slices

1. Sessions + Session Details + exercise planning.
2. Requests + supervised/direct routing.
3. Package + acknowledgement/credit invariant UI.
4. Calendar + dashboard operational views.
5. Remuneration.
6. Add Client + trainer matching / reset behaviour.
7. Add Trainer + availability.
8. Exercise Library and Website Content.
9. Public-facing website reconstruction.
10. PWA production shell and service-worker verification.

## High-risk parity gates carried forward from v0.57

- Approval-needed checked means direct permission is false.
- Approval-needed unchecked means direct permission is true.
- A completed session can consume at most one package credit.
- Schedule changes requiring approval do not mutate future sessions until approval.
- Session details use separate View buttons for client and trainer.
- Date rows include full weekday context.
- Phone, iPad and desktop are distinct acceptance targets.

## Anti-spaghetti rule

No old v0.xx patch CSS or JS is imported into this project. A future change must modify its owning React feature/service and update the relevant tests.
