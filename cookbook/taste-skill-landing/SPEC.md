# SPEC: taste-skill landing page (design-taste skill, judged in a browser)

## Goal

An agent loads the design-taste rules of the open-source **taste-skill**
(Leonxlnx/taste-skill, MIT, pinned at commit
`f624f37a8c650b9cc550253104925efe4c8de246` — the `skills/taste-skill/SKILL.md`
"tasteskill v2" skill) and builds a polished one-page marketing site for the
fictional product in [`brief.md`](brief.md), inside a disposable agent-next
sandbox. A judge the artifact cannot fool then loads the page in a headless,
pinned Chromium (Playwright 1.63.0) at three widths and decides, from the
**computed styles of the real rendered page**, whether the site is clean,
complete and in taste: zero console errors and failed requests, no horizontal
overflow, WCAG AA contrast, every brief section present, and the taste-skill's
own measurable house rules (typefaces, type scale, spacing scale, fonts
loaded, alt text, tap targets, no gradients / shadows / thin rules /
monospace / index numbering, headline line counts, image floor) — each gate
cites the skill rule it enforces.

`examples/baseline/` is the same brief built **without** the skill (an honest
plain first attempt: default fonts, small grey text, a fixed-width container,
gradient and shadow ornaments). The same judge grades it; the verdict numbers
show the before/after difference the skill makes.

## Non-goals

- No Lighthouse run (see Deviations in [RECEIPT.md](RECEIPT.md)): axe-core
  4.10.3 (pinned tarball, sha256-checked) is the accessibility oracle, per the
  demo brief's "equivalent axe-core check" option.
- No runtime network: the site is static and self-contained (fonts and images
  committed); the judge blocks and flags any non-localhost request.
- No visual-regression or screenshot diffing; no subjective beauty score.
- No build step for the artifact (plain HTML/CSS/JS committed as written).
- Not grading taste rules that are not machine-measurable from computed
  styles (e.g. "the idea comes from the subject"); those stay in the skill.

## Artifact

A static site directory:

```
<artifact>/
├── index.html      # one page, all brief sections
├── assets/         # css, js, self-hosted woff2 fonts, committed PNG images
└── (nothing else; no build output, no node_modules)
```

Known-good: `examples/good/site/`. Baseline (no skill): `examples/baseline/site/`.
The judge serves a scratch copy over `http://127.0.0.1:<port>/` (port derived
from `--seed`), never the committed tree, and checksums `judge/` before and
after to prove the artifact cannot modify the judge.

The brief's machine-readable contract is the fenced `json` block in
`brief.md`: required `sections` (id + heading text each), brand `colors`
(`ground`, `ink`, `accent`), and the product name.

## Gates (numeric pass rules)

All measurements come from Playwright 1.63.0 driving pinned Chromium
headless (no CPU throttling), at widths **375, 768 and 1440 px**
(device scale 1, reduced-motion preference set).

### Gate 1 — clean load
- `console` messages of type `error`: **0**.
- Request failures and HTTP responses with status >= 400: **0**.
- Requests to hosts other than `127.0.0.1`: **0** (no runtime network).

### Gate 2 — no horizontal overflow
- At each width: `document.documentElement.scrollWidth <= clientWidth + 1`.

### Gate 3 — WCAG AA contrast (computed styles)
- For every visible text node: contrast ratio of computed `color` against the
  nearest ancestor with a non-transparent `background-color` (page ground if
  none) is **>= 4.5:1** (font < 24 px) or **>= 3:1** (>= 24 px, or >= 18.66 px
  bold). Skill cite: `references/colour.md` §8 "Body text 4.5:1 or better;
  display type and large numerals 3:1 or better".

### Gate 4 — brief completeness
- Every section in `brief.md` json block: element `#<id>` exists and its
  heading (first `h1`–`h3` descendant, or the element itself) contains the
  brief's `heading` text (case-insensitive).
- Computed `body` background-color equals the brief `colors.ground`.

### Gate 5 — taste rules (each sub-check cites the skill)
| # | rule (skill citation) | numeric pass |
|---|---|---|
| 5.1 | two typefaces at most (SKILL.md house rules: "Two typefaces at most, usually one") | distinct primary font families used by visible text <= 2 |
| 5.2 | no default browser fonts (SKILL.md laws of the craft / type: the dealt type system, fonts loaded) | every visible-text element's primary family is a loaded web font (`document.fonts.check` true) and not a generic family or web-safe default ({serif, sans-serif, monospace, cursive, fantasy, system-ui, Times, Times New Roman, Arial, Helvetica, Verdana, Tahoma, Trebuchet MS, Courier, Courier New, Georgia, Impact, Comic Sans MS}); monospace is legal only inside `pre`/`code` |
| 5.3 | type-scale ceiling (SKILL.md laws: "Five sizes on a page is the ceiling"; `assets/base.css` ships exactly 5 `--step-*` tokens) | distinct computed font sizes among visible text elements at 1440 px <= 5 |
| 5.4 | consistent spacing scale (SKILL.md laws of space: one grid, one pair of tight margins 16–32 px; `references/layout.md` §2) | every non-zero computed padding, gap and section margin value (px, rounded) is a multiple of 4, at 1440 and 375 px |
| 5.5 | alt text (SKILL.md step 6.7: "Real links and buttons, visible focus, alt text") | every `img` has a non-empty `alt` |
| 5.6 | touch targets (references/layout.md: "Touch targets at least 44px high") | at 375 px every visible `a`, `button`, `input`, `select`, `label` has bounding box width >= 44 px and height >= 44 px |
| 5.7 | no gradients (house rules: "No gradients. Not as backgrounds, not on buttons, not in text") | no element's computed `background-image` contains `gradient(`; no `text-shadow`/`background-clip:text` gradients |
| 5.8 | no shadows at rest (house rules: "No shadows on things at rest... glows") | computed `box-shadow`/`text-shadow` of every element is `none` |
| 5.9 | no thin rules (house rules: "No hairline dividers, no 1px outlined boxes"; `pre`/`code`, form fields and `[data-ui]` exempt) | every non-zero computed border width outside exemptions >= 2 px |
| 5.10 | no monospace outside code (house rules: "No monospace outside real code blocks") | no visible text element outside `pre`/`code`/`[data-ui]` resolves to a monospace family |
| 5.11 | no index numbering (house rules: "No 01 / 02 / 03, no (001), no 'Step 2'") | no `h1`–`h6` text matches `^\s*(0\d|[1-9]\d?)[\s.):.-]` and none contains `step \d` (case-insensitive) |
| 5.12 | running text 16 px+ (SKILL.md step 6.6: "Running text is in the full ink at 16px or more"; layout.md "Body text 16–18px") | every visible paragraph-scale text node (>= 60 chars) has computed font-size >= 16 px at 1440 and 375 |
| 5.13 | headline line count (house rules: "Headlines: two lines or fewer, at every width") | every visible `h1`–`h6` occupies <= 2 line boxes (Range client rects) at each width |
| 5.14 | image floor (SKILL.md step 6.4: "at least four real pictures on the page... SVG drawings do not count") | count of `img` with raster src and `naturalWidth > 0` >= 4 |

### Gate 6 — axe-core accessibility
- axe-core 4.10.3 injected at 1440 and 375 px: violations with impact
  `critical` or `serious`: **0** (equivalent of the brief's "Lighthouse
  accessibility >= 90" target; Deviation logged in RECEIPT.md).

### Gate 7 — wind widget sanity (brief hero: "the honest time saved")
- The rendered `#wind-result` text is read at the default slider position,
  at the slider's `min` and `max`, and at every `#wind-dir` option.
- Every `N minutes` figure must be an integer in **[0, 600]**: a negative
  or NaN minute value, or a widget that renders no figure, fails the gate.
- A page with no `#wind-speed`/`#wind-result` widget passes with a note
  (the baseline has none; the widget is a good-site feature).

## Mutants (judge self-test)

`judge/mutants.py` single-edits the good site; each must fail >= 1 gate:
`low_contrast` (ink lightened), `fixed_container` (1200 px min-width body),
`missing_section` (pricing removed), `console_error` (stray script),
`default_font` (Times/serif), `tiny_taps` (nav/button padding shrunk),
`img_no_alt` (alt stripped), `wind_sign_bug` (wind saving computed as an
ordered difference, so some wind directions print a negative saving),
`gradient_button` (CSS appended). Kill rate
>= 90 % required (9/9 expected). `examples/baseline/site` is graded as a
known-bad reference row (expected to fail several gates) but is not in the
kill-rate denominator.

## Acceptance oracle

Nothing passes because "the page renders": every gate is a count or ratio
measured by the judge from the live DOM (console/requests, scrollWidth,
computed color/background-color pairs, font sets, computed geometry,
rendered widget text), a machine-readable brief contract, or a pinned
third-party oracle (axe-core).

**Exit-code contract.** `grade.sh` exits 0 only when every gate passes;
any failed gate exits 1 and still writes the verdict JSON (exit 2 is a
harness/integrity error, not a verdict). `selftest.sh` asserts the
contract: the no-skill baseline must exit non-zero *and* leave a readable
verdict. `run.py` checks both channels the same way for the two artifacts
it grades: the good site must return rc 0 + `all_gates_passed: true`, the
baseline rc != 0 + `all_gates_passed: false` + >= 1 failed gate.

`judge/selftest.sh` proves each gate can fail: good passes, every mutant
fails, two grades at the same seed are byte-identical outside `timing`, and
`judge/` checksums are unchanged by grading.
