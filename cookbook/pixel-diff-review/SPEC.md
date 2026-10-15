# pixel-diff-review — the unblinking reviewer

## Goal

Show an agent building the review gate a human never is: a **component-level
pixel diff** between two builds of the same web page. It must say, in numbers,
*every* region that changed, how big it is, and how far it moved — so that a
footer that silently shifted 3 px while you were looking at a card fails the
build, instead of slipping through because "only the card changed".

The artifact is a single stdlib-only Python program, `review.py`: it takes the
two screenshots of the same route (`/dashboard`) from two deployments of a
fixture app, and reports every changed region with its bounding box, area and
offset, using a block-hash grid diff and connected-component clustering. The
judge decides pass/fail from that report against an **analytic mask** it
computes itself, from the browser's own layout geometry — never from the
agent's numbers.

## What the fixture app is

`fixture/gen.py` (seeded, stdlib only) writes three build trees of one small
dashboard app:

| build | what it is |
|---|---|
| `base` | the route before the change |
| `head` | the route after the intended change |
| `sneaky` | `head`, plus one extra cosmetic edit that must **not** be there |

The intended change rewrites the *Signups* card only: its number, its delta
badge, and its background. That card carries `data-pdr-intended="1"` in every
build. The sneaky edit adds `transform: translateY(-3px)` to the page footer
(`[data-region="footer"]`), which moves the footer up by exactly 3 CSS px and
reflows nothing.

The three builds are identical byte for byte apart from those edits, and the
generator writes a real unified diff (`patch.diff`, base → head) so the demo's
"apply the patch, then review it" story is literal.

## Non-goals

- Not a general-purpose visual-regression tool. One fixed route, one fixed
  viewport, one fixed grid contract.
- Not a test of the browser. Chromium is pinned because two renders must be
  byte-identical, not because rendering speed or engine quirks are graded.
- The judge owns the screenshots, deliberately: an artifact that also takes
  the pictures can picture whatever it likes. The agent owns the analysis
  (grid diff, hashing, clustering, offset measurement, reporting) and nothing
  else. See "Deviations" in `RECEIPT.md` for why this is a narrowing of the
  prompt and what it costs.
- Not a check of desktop/mobile/print rendering, fonts the page does not load,
  or anything above the fold.
- Timing is not graded. Wall time is reported because a judge that takes an
  hour is useless, not because speed is scored.

## The artifact

`examples/good/review.py`, and any drop-in replacement for it. The contract
is a command line and a JSON report; nothing else is fixed.

```
review.py --base BASE.png --head HEAD.png --cols C --rows R \
          [--allow-bbox X,Y,W,H] [--json OUT.json]
```

- `--base` / `--head`: two PNGs of the **same viewport** (`COLS × ROWS` is
  passed, so the artifact never has to guess the grid).
- `--allow-bbox` (optional): a rectangle, in device pixels of the base
  screenshot, that the change is confined to. When given, the program also
  prints `verdict: pass|fail` and `regions_outside_allowed`.
- `--json` writes the report; without it the report goes to stdout.

The report (one JSON object):

| field | type | meaning |
|---|---|---|
| `schema` | string | `pixel-diff-review/report/1` |
| `inputs` | object | `{"base": "<sha256>", "head": "<sha256>"}` of the two PNGs read |
| `grid` | object | `{"cols": C, "rows": R, "block_w": bw, "block_h": bh}` |
| `regions` | array | one object per changed region (below) |
| `changed_blocks` | integer | total changed blocks over all regions |
| `verdict` | string | `pass` / `fail` when `--allow-bbox` was given, else `report` |

and each region:

| field | type | meaning |
|---|---|---|
| `id` | integer | 1-based, sorted by `bbox_blocks` |
| `bbox_blocks` | array | `[c0, r0, c1, r1]`, inclusive block coordinates |
| `bbox_px` | array | `[x, y, w, h]` device pixels, derived from `bbox_blocks` |
| `area_blocks` | integer | changed blocks in this region |
| `area_px` | integer | `area_blocks × block_w × block_h` (the changed pixel area) |
| `blocks` | array | `[[c, r], ...]` — the 4-connected changed blocks |
| `offset_px` | array | `[dx, dy]` — displacement of the region's content, integer px |
| `hash_delta_max` | integer | worst per-block pHash Hamming distance in the region |
| `mean_delta_max` | integer | worst per-block mean-gray difference in the region |

### The diff, exactly

For block cell `(c, r)` covering device pixels `x ∈ [c·bw, (c+1)·bw)`,
`y ∈ [r·bh, (r+1)·bh)`:

1. decode the PNG to grayscale (luminance 0–255, `Y = 0.299R + 0.587G +
   0.114B`, rounded);
2. box-average the block down to **9 × 8** grayscale;
3. **dHash**: bit `i` of a 64-bit value is 1 iff cell `(i mod 9)` of row
   `i // 9` is darker than cell 0… precisely: for row `k` (0..7) and column
   `j` (0..7), bit `8k + j` = 1 iff `v[k][j] < v[k][j+1]`, where `v` is the
   9 × 8 average. (A left-to-right gradient bit set.)
4. `mean` = the block's mean grayscale, 0–255.

A block is **changed** iff

```
popcount(hash_base ^ hash_head) >= HASH_THRESHOLD        (default 4 / 64)
   or |mean_base - mean_head| >= MEAN_THRESHOLD          (default 10 / 255)
```

Both thresholds default to `4` and `10`; the judge does not pass them, so the
artifact's defaults are what is graded. A quiet block — one the patch did not
touch — therefore has `hash_delta == 0` **and** `mean_delta == 0`, which is
what makes gate 7 (`no_false_positives`) and gate 6 (`recall`) exact rather
than statistical.

**Regions** are the 4-connected components of the changed-block set, 8-connectivity
is not used: diagonally-touching components are deliberately separate, so a
shift that grazes a neighbour does not merge with it.

**Offset** per region: take the region's bounding box grown by `SEARCH_PX = 16`
px on every side (clipped to the image), and find the integer `(dx, dy)` with
`|dx|, |dy| ≤ 16` minimising

```
sum |base[y][x] - head[y + dy][x + dx]|
```

over the grown patch. Ties break by smallest `|dx| + |dy|`, then smallest
`dx`, then smallest `dy`. `offset_px` is the content's displacement, so a
footer moved up 3 px reads `[0, -3]`.

## Acceptance oracle

The judge never trusts the artifact to describe itself. Four independent
oracles, none of which reads the artifact's code or its numbers as truth:

1. **The browser's own layout geometry** (`analytic mask`). With both builds
   loaded, the judge evaluates `getBoundingClientRect()` on
   `[data-pdr-intended]` and on `[data-region="footer"]`, and
   `getComputedStyle(footer).transform` on the sneaky build. The expected
   number of changed regions, the expected box, and the expected offset of the
   footer are all derived from those measurements — the *spec mask* the
   standard asks for, computed from the renderer rather than from a diff.
2. **A reference diff** (`reference agreement`, `convergence`). The judge
   carries its own independent PNG decode, block hash, component extraction
   and offset estimator (`judge/reference_diff.py`), written against the same
   published definition above but sharing no code with the artifact. The
   artifact's region count and box must agree with it, and the reference diff
   must give the same answer when the grid is refined 2× — a convergence
   check, not a re-run.
3. **A fingerprint** (`inputs matched`). The report names the sha256 of the
   two PNGs it read; the judge compares them with what it captured. A report
   that analysed anything else, or nothing, fails.
4. **Judge checksums** (`judge intact`) before and after the artifact runs.

There is no "the tool ran" gate: every gate compares against one of the four
above. `engine_runs` is a schema precondition, not evidence.

## Gates

`judge/grade.sh <artifact> [--seed N] [--json out.json]` prints exactly one
JSON verdict object and exits 0 only if every gate passes. `P` is measured,
`R` is the rule.

| # | gate | what is measured | pass rule |
|---|---|---|---|
| 1 | `engine_runs` | exit code and report schema | exit 0, valid JSON, all required keys, `inputs` present |
| 2 | `inputs_matched` | report `inputs` sha256 vs captured PNG sha256 | both identical |
| 3 | `region_count` | reported regions, base → head | **exactly 1** |
| 4 | `bbox_overlap` | `\|card ∩ region_bbox\| / \|card\|`, card = `[data-pdr-intended]` rect | **≥ 0.90** |
| 5 | `no_spill` | `\|region_bbox \\ dilated_card\| / \|region_bbox\|`, dilated by 1 block | **= 0.0** |
| 6 | `recall` | reported changed blocks ⊇ reference changed blocks inside the card rect | **100 %** |
| 7 | `no_false_positives` | reported changed blocks outside the card rect dilated by 1 block | **0 blocks** |
| 8 | `area_consistent` | `area_blocks == len(blocks)`, blocks 4-connected, `area_px == area_blocks·bw·bh` | all three |
| 9 | `reference_agreement` | reported region count and box vs judge's reference diff | count equal, box within 8 px |
| 10 | `convergence` | reference diff at `40 × 30` and at `80 × 60` | same region count, card box within 16 px |
| 11 | `negctl_regions` | reported regions, base → sneaky | **exactly 2** |
| 12 | `negctl_offset` | sneaky second region `offset_px` vs the footer's measured `translateY(-3px)` | magnitude within 1.5 px of 3.0, direction within 45° of `(0, -1)` |
| 13 | `verdict_wiring` | artifact's own `verdict` under `--allow-bbox` = the card box | `pass` on head, `fail` on sneaky |
| 14 | `judge_intact` | sha256 of every file under `judge/`, before vs after | identical |

Numeric constants (environment variables, so a receipt can name them; the
defaults are what is graded):

| constant | default | meaning |
|---|---|---|
| `PDR_VIEWPORT` | `1280x720` | viewport in device px, device scale factor 1 |
| `PDR_COLS` | `40` | grid columns (`block_w = 32 px`) |
| `PDR_ROWS` | `30` | grid rows (`block_h = 24 px`) |
| `PDR_SEED` | `20261015` | seed for `fixture/gen.py` and the judge |
| `PDR_ALLOW` | `card` | what `--allow-bbox` is set to: `card`, `none`, `page` |
| `PDR_OVERLAP_MIN` | `0.90` | gate 4 floor |
| `PDR_BOX_TOL_PX` | `8` | gate 9 tolerance |
| `PDR_CONV_TOL_PX` | `16` | gate 10 tolerance |
| `PDR_OFFSET_TOL_PX` | `1.5` | gate 12 tolerance on the 3 px shift |
| `PDR_DILATE_BLOCKS` | `1` | block margin around the expected box |

## What this demo does not prove

- Nothing about how the page *looks* to a person. The judge checks geometric
  identity, not aesthetics, and a change that keeps every byte identical is
  invisible to it by construction.
- The grid contract is coarse on purpose. A 1 px text change inside a block
  whose background also changed may be missed; the gates only require that
  what is reported be true and that the card be found, not that every altered
  pixel be enumerated.
- The offset estimator is an integer cross-correlation with a ±16 px search
  window. It cannot measure a displacement larger than that, and it has no
  sub-pixel resolution.
- Only one route and one viewport. Responsive breakpoints, dark mode, print
  and any other rendering surface are out of scope.
- The judge owns capture, so an artifact cannot be blamed for (or credited
  with) a flaky screenshot — and cannot be caught forging one either.
