# app-builder-preview: prompt-to-running-web-app demo — SPEC

An agent works inside a disposable sandbox on a real front-end engineering
problem: turn a neutral app spec (required routes, element ids, behaviours)
into a running web app — a todo list with live stats — that a judge it cannot
fool drives through headless Chromium. The judge never accepts "the page
loaded": every flow asserts exact DOM state after each step, and the build
must stay under a size budget with zero console errors.

## Goal

- Artifact: a Vite + React app in `app/` built from `spec.json` (the neutral
  app spec below), served from `dist/` on localhost.
- Judge: `judge/grade.sh` runs `npm ci` and `npm run build` in the sandbox,
  serves `dist/`, drives headless Chromium (Playwright, pinned) through 6
  scripted user flows, asserts DOM state after each, captures a screenshot
  per flow, and checks build size and console errors.
- Self-test: `judge/selftest.sh` proves the judge fails known-bad apps.

## Non-goals

- Any backend, database, or network calls: the app is a pure client-side
  SPA; persistence is `localStorage` only.
- Any framework other than React + Vite: the artifact contract is React 19
  + Vite 8, pinned in `app/package-lock.json`.
- Visual design review: the judge checks DOM structure and behaviour, not
  aesthetics (screenshots are captured for humans, not scored).
- Lighthouse or performance budgets beyond the build-size gate: no runtime
  performance gate is enforced.

## The neutral app spec (`spec.json`, committed in `judge/`)

The agent sees `spec.json` and nothing else — it contains routes, element
ids, and behaviours, and **no implementation**.

```json
{
  "app": "todo-stats",
  "routes": ["/"],
  "elements": {
    "todo-input": "text input for a new todo",
    "todo-add": "button that adds the typed todo",
    "todo-list": "ul containing one li per todo",
    "todo-item": "li for one todo; data-id attribute is the todo id",
    "todo-text": "span holding the todo text",
    "todo-toggle": "button that toggles done/not-done",
    "todo-delete": "button that removes the todo",
    "filter-all": "button: show all todos",
    "filter-active": "button: show only not-done todos",
    "filter-done": "button: show only done todos",
    "stats-total": "span: total todo count",
    "stats-active": "span: not-done count",
    "stats-done": "span: done count"
  },
  "behaviours": {
    "add": "typing text and clicking todo-add appends an li to todo-list with that text; the input clears",
    "toggle": "clicking todo-toggle on an item flips its done state; the item gets class 'done'",
    "delete": "clicking todo-delete removes exactly that li from todo-list",
    "filter": "filter-all/active/done show only matching items; the active filter button gets class 'active'",
    "stats": "stats-total/active/done always show the integer counts of all/not-done/done items",
    "persist": "the todo list survives a page reload (localStorage)"
  }
}
```

## The artifact contract

`app/` is a Vite + React project:

1. `app/package.json` with `react`, `react-dom`, `vite`, `@vitejs/plugin-react`
   pinned in `app/package-lock.json` (committed).
2. `app/vite.config.js` with the React plugin.
3. `app/index.html` with `<div id="root">` and a module script.
4. `app/src/main.jsx` mounting the app into `#root`.
5. `app/src/App.jsx` implementing every element and behaviour in
   `spec.json`.
6. `app/src/app.css` for styling (including the `.done` and `.active`
   classes).

Rules the judge enforces:

- The element names in `spec.json` (`todo-input`, `stats-total`, …) are the
  DOM ids; the values are descriptions. The judge drives exactly those
  names, and the app must derive its ids from the spec it fetches at
  runtime (`fetch('/spec.json')`) — not hardcode them.
- The judge owns `spec.json`: it drops `judge/spec.json` into the
  artifact copy's `public/` before building, so the app always reads the
  judge's copy. An artifact that ships a `public/` directory is rejected
  (gate 1) rather than silently merged.
- The app must import `react`, build with `npm run build` into
  `dist/index.html`, and stay within the size/console budgets of gate 5.
- Hardcoding expected counts is caught by gate 4: the 6 flows expect
  different counts (3, 2, 2, 2, 2, 4 items), so a hardcoded count fails
  at least one flow.
- The judge runs the artifact from a copy; sha256 checksums of `judge/`
  before and after must match.

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json]`
exits 0 only if gates 1–5 all pass. `--seed` (default 0) is recorded in
the verdict and seeds the judge's own reference build (the reference is
re-run every grade so the comparison stays live).

1. **structure** — `app/package.json` is at most 64 KiB, `app/src/App.jsx`
   is at most 32 KiB, both byte-compile (JSON parse / esbuild transform),
   the app imports `react`, and reads `spec.json` at runtime (`spec.json`
   load in text).
2. **build** — `npm ci` and `npm run build` exit 0 within 300 s, producing
   `dist/index.html`. A crash, a missing `dist/`, or a timeout fails this
   gate.
3. **serve** — `npm run preview` (or `vite preview`) serves `dist/` on
   localhost within 30 s, and `GET /` returns 200 with the root div. A
   crash or a non-200 fails this gate.
4. **flows** — the judge drives headless Chromium through 6 scripted
   flows, **each starting from a fresh browser context** (clean
   `localStorage`, so the expected numbers below hold per flow), asserting
   DOM state after each step and capturing one screenshot per flow
   (`grade.sh --shots DIR` saves them). Each flow must pass every
   assertion:

   | flow | steps | assertions |
   |---|---|---|
   | add | type "buy milk", click add; type "walk dog", click add; type "read book", click add | 3 li in todo-list; each li's todo-text matches; input cleared; stats-total = 3 |
   | complete | add 2 todos, toggle the first | first li has class 'done'; stats-active = 1; stats-done = 1 |
   | delete | add 3 todos, delete the second | 2 li remain; the remaining texts are the first and third; stats-total = 2 |
   | filter | add 3 todos, toggle the first, click filter-active | 2 li visible; both lack class 'done'; filter-active has class 'active' |
   | persist | add 2 todos, toggle the first, reload | 2 li after reload; first li has class 'done'; stats-total = 2 |
   | stats | add 5 todos, toggle 2, delete 1 | stats-total = 4; stats-active = 2; stats-done = 2 |

   Numeric pass rules: every assertion is an exact DOM equality (count,
   text, class, or visibility). A single wrong count, missing class, or
   extra/missing item fails the flow.
5. **hygiene** — the built `dist/` is under 250 KiB uncompressed (sum of
   file sizes), the browser console has zero errors during all 6 flows,
   and the judge's own reference build (a known-good React app the judge
   controls, built from the same spec) produces the same final DOM state
   as the artifact after each flow (cross-check agreement).

Tolerances: none — every assertion is exact. The build-size limit (250 KiB)
is loose enough that a correct Vite + React build passes with margin
(measured: the good app builds to ~223 KiB), tight enough that a bloated
or broken build fails.

## Acceptance oracle

The judge never trusts the artifact's own idea of correct. Correctness is
decided by exact DOM state after each scripted flow (counts, texts,
classes, visibility), plus an independent reference tool — the judge's own
React app built from the same spec under a judge-controlled seed — as the
cross-check agreement. An artifact that merely "loads" without matching
the expected DOM state fails.

## Known-bad examples (self-test)

`judge/mutants.py` derives 6 known-bad artifacts from the known-good one
by scripted single edits:

| mutant | edit | gate that kills it |
|---|---|---|
| broken_delete | delete handler removes the wrong item (index off by one) | flows (delete) |
| stats_wrong_span | stats-total shows the done count instead of the total | flows (stats) |
| no_persist | the localStorage save is removed | flows (persist) |
| console_error | a `console.error` on mount | hygiene (console) |
| wrong_element_id | the `todo-text` id is renamed | flows (add) |
| build_broken | the vite config points at a missing entry | build |

`judge/selftest.sh` grades the known-good (must pass) and every mutant
(each must fail ≥ 1 gate), prints the kill rate, and checks determinism:
two grades of the good artifact, and two grades of a failing artifact
(`build_broken`), must each produce byte-identical verdicts except the
`timing` key. It exits non-zero unless the kill rate is ≥ 90 %.

## Determinism

The app is a pure client-side SPA with no randomness; the reference build
is seeded via `--seed`. Two grades of the same artifact give
byte-identical verdict JSON except `timing` — enforced by `selftest.sh`,
for a passing and for a failing artifact. A failing verdict quotes tool
output, which can carry the per-run scratch directory, so `_grade.py`
rewrites those paths to a stable placeholder before writing the verdict.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.tools/app-builder-preview/` exactly:
Node.js 22.23.3 (official tarball, sha256-checked), Playwright 1.63.0
(npm, with Chromium), and the app's npm dependencies (pinned in
`app/package-lock.json`, installed with `npm ci`). Every download is
sha256-checked; every pinned release predates 2026-09-30 (nothing
published in the two weeks before this demo was built).
`judge/VERSIONS.txt` records what setup actually installed.
