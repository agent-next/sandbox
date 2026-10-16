<!-- Independent reproduction by a different agent/model family (z.ai GLM),
     run from README.md alone before RECEIPT.md was read; scratch in /tmp/repro-scratch (deleted after). -->
VERDICT: REPRODUCED

Independent reproduction of `cookbook/ovui-native-ui/` from README.md alone
(read-only). Builder's RECEIPT.md/SPEC.md/media contents were not opened; the
three judge scripts were executed exactly as the README instructs, unread.
All scratch under `/tmp/repro-scratch/`; the repo was left byte-identical
(git status unchanged; byproducts `__pycache__`/`imgui.ini` written by
`run.py --help` were removed — they did not exist before this session).

## 1. Environment

```text
Linux instance 6.1.175 #1 SMP PREEMPT_DYNAMIC Wed Jul 22 20:03:46 CST 2026 x86_64 GNU/Linux
Python 3.12.15
gcc (Debian 12.2.0-14+deb12u1) 12.2.0
user (non-root)
```

Same class as the README's receipt environment (Debian 12, Python 3.12, x86_64,
no GPU).

## 2. `judge/setup.sh` (fresh `TOOLS_DIR=/tmp/repro-tools`)

Command: `cd /home/user/w/cookbook/ovui-native-ui && { time TOOLS_DIR=/tmp/repro-tools bash judge/setup.sh; }` — wall **15.5 s**, **exit 0**.

```text
[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run: python3 -m pip install --upgrade pip
/tmp/repro-tools/wheels.dl/ovui-0.3.0-cp312-cp312-manylinux_2_35_x86_64.whl: OK
/tmp/repro-tools/wheels.dl/pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl: OK
/tmp/repro-tools/wheels.dl/numpy-2.5.4-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl: OK
generated stubs: 34 cudart + 8 driver symbols
omni.ui import OK
setup OK: /tmp/repro-tools

real	0m15.542s
user	0m12.249s
sys	0m2.051s
EXIT_CODE=0
```

Commentary: clean pass — sha-checked wheels for the pinned stack (ovui 0.3.0,
matching the README's "ovui 0.3.0 is required"), CUDA stubs generated, and
`import omni.ui` succeeds without a GPU. 15.5 s is below the README's 44–92 s
cold range; no apt activity appeared, so this host already had the system
packages (the "apt +" part of the cold figure never ran). It is above the 8 s
warm figure, consistent with a fresh TOOLS_DIR downloading wheels.

## 3. `judge/selftest.sh`

Command: `{ time TOOLS_DIR=/tmp/repro-tools bash judge/selftest.sh; }` — wall **23.1 s**, **exit 0**.

```text
wrote 11 mutants to /tmp/tmp.G7HfhxUoMq: missing_slider wrong_range wrong_swatch_color swatch_overflow empty_window wrong_button_text wrong_swatch_size missing_checkbox missing_swatch baked_png nondeterministic
good: PASS (verdict byte-identical across 2 runs)
mutant baked_png: FAILS (widget_tree,pixels)
mutant empty_window: FAILS (widget_tree,pixels)
mutant missing_checkbox: FAILS (widget_tree,pixels)
mutant missing_slider: FAILS (widget_tree)
mutant missing_swatch: FAILS (widget_tree,pixels)
mutant nondeterministic: FAILS (determinism)
mutant swatch_overflow: FAILS (widget_tree,pixels)
mutant wrong_button_text: FAILS (widget_tree)
mutant wrong_range: FAILS (widget_tree)
mutant wrong_swatch_color: FAILS (widget_tree,pixels)
mutant wrong_swatch_size: FAILS (widget_tree,pixels)
kill rate: 11/11 = 100% (counting only mutants a judge gate failed)
self-test OK

real	0m23.057s
user	0m15.647s
sys	0m3.149s
EXIT_CODE=0
```

Kill-rate line, verbatim: `kill rate: 11/11 = 100% (counting only mutants a judge gate failed)`

Commentary: exactly as the README describes — known-good passes (and is itself
checked byte-identical across 2 runs), all 11 mutants die on gate assertions,
none merely crashes, and the mutant names map one-to-one onto the README's
list (layout overflow = swatch_overflow, invisible-panel window =
empty_window, baked-PNG artifact = baked_png). Wall time 23.1 s is below the
README's 44–123 s range — this machine renders faster; direction of the claim
(selftest dominated by 26 renders) is consistent.

## 4. `judge/grade.sh examples/good/panel.py` (run 1)

Command: `{ time TOOLS_DIR=/tmp/repro-tools bash judge/grade.sh examples/good/panel.py --json /tmp/repro-scratch/grade1.json; }` — wall **2.06 s**, **exit 0**.

```json
{
  "gates": [
    { "gate": "rendered_png", "ok": true, "size": [1280, 720] },
    { "gate": "widget_tree", "ok": true,
      "detail": { "button_ok": true, "checkbox_ok": true, "ref_names_missing": [],
                  "refs_live": true, "sliders_distinct": true, "sliders_ok": true,
                  "swatch_color_ok": true, "swatch_size_ok": true, "swatch_type_ok": true,
                  "window_ok": true } },
    { "gate": "pixels", "ok": true,
      "detail": { "bbox_mismatch": [], "bg_lum": 69.0, "button_face_lum": 41.0,
                  "button_text_px": 127, "overflow": [], "rects_missing": [],
                  "swatch_median": [51.0, 128.0, 230.0], "swatch_ok": true,
                  "swatch_std": [0.0, 0.0, 0.0], "swatch_target": [51.0, 128.0, 230.0],
                  "title_px": 328, "undrawn": [] } },
    { "gate": "determinism", "ok": true, "facts_match": true,
      "sha256": "0d8e03dcb161d859", "shots_match": true }
  ],
  "pass": true
}
```

(The stdout JSON above is verbatim apart from re-indentation; the `--json`
file additionally carries `"seed": 1234` and `"timing": {"render_wall_s": 1}`,
which the stdout print omits.)

Key numbers: **pass: true**; **gates 4/4 ok** (rendered_png, widget_tree,
pixels, determinism); swatch median RGB **[51, 128, 230]** — exactly the
analytic target, std 0; determinism **sha256 0d8e03dcb161d859** (first 16);
**timing.render_wall_s = 1** (from the --json file).

Commentary: every gate the README describes passes with the numbers it
predicts, including the exact swatch target [51, 128, 230] within ±12 (here
±0). Wall 2.06 s is just under the README's 3–12 s grade range, and
render_wall_s 1 s under its ~2–4.5 s per-render figure — same
faster-machine effect as above, not a functional discrepancy.

## 5. Grade run 2 — determinism of the verdict

Run 2: wall 2.07 s, exit 0, JSON written to `/tmp/repro-scratch/grade2.json`.
`cmp grade1.json grade2.json` → identical. The two verdict JSONs are
**byte-identical: yes** — trivially so after excluding the `timing` key,
since the raw files already match byte-for-byte *including* `timing`
(`render_wall_s: 1` in both). This is DEMO-STANDARD's "grade.sh run twice
gives byte-identical verdict JSON" requirement, met on my machine too.

## 6. README media claims vs reality

```text
$ stat -c %s media/demo.mp4
2890730
$ ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,width,height,r_frame_rate,codec_type -of default media/demo.mp4
[STREAM]
codec_name=h264
codec_type=video
width=1920
height=1080
r_frame_rate=30/1
[/STREAM]
[FORMAT]
duration=38.067000
size=2890730
[/FORMAT]
EXISTS: media/STORYBOARD.md
MISSING: media/REVIEW.json
MISSING: REPRODUCE.md
EXISTS: media/result.png
EXISTS: media/loop.png
EXISTS: media/MANIFEST.json
EXISTS: media/result.json
```

Commentary: duration 38.067 s matches "38.1 s"; codec/resolution/frame rate
match (H.264, 1920×1080, 30 fps). Two claims fail: the README says the video
is "4.5 MB" but the on-disk file is 2,890,730 bytes ≈ 2.9 MB (the working
tree carries uncommitted changes to `media/demo.mp4`, so the README may
describe an older encode — either way README ≠ reality right now); and
`media/REVIEW.json`, which the README's Media section describes, does not
exist. `REPRODUCE.md` (required by DEMO-STANDARD before merge) also does not
exist yet — this report is that reproduction, so that is expected at this
stage rather than a defect, but it is not yet mergeable state.

## 7. One-command run (`run.py`) — what is possible here

```text
$ python3 -m py_compile run.py && python3 run.py --help
py_compile: OK
usage: run.py [-h] [--ref REF] [--keep] [--timeout-min TIMEOUT_MIN]
... (full argparse help; flags --ref (default main), --keep, --timeout-min N)
EXIT_CODE_HELP=0
```

Full help text captured in the session; the flags and defaults exactly match
the README's line `python3 cookbook/ovui-native-ui/run.py  # --ref main (default), --keep, --timeout-min N`. The real run needs the `sbx` CLI and
`SBX_API_KEY` and creates a cloud sandbox — impossible from inside this
sandbox, as anticipated. Side observation: `run.py --help` took ~20 s and
imported the render stack at module load, writing `imgui.ini` and
`__pycache__/` into the demo directory (both removed; neither existed
before).

## 8. Verbatim failures / mismatches

None of the three judge steps failed; all exited 0. The mismatches found:

```text
README: "a 38.1 s, 1920×1080, 30 fps walkthrough ... (4.5 MB H.264 ...)"
REAL:   size 2890730 bytes (≈2.9 MB); duration 38.067 s; h264 1920x1080 30/1

README: "media/REVIEW.json — the two blind vision-model verdicts on that video"
REAL:   media/REVIEW.json: No such file or directory

README: media table / DEMO-STANDARD pre-merge requirement for REPRODUCE.md
REAL:   REPRODUCE.md: No such file or directory

README wall-time table: setup cold 44–92 s / warm 8 s; selftest 44–123 s;
grade 3–12 s; one render ~2–4.5 s
REAL:   setup 15.5 s; selftest 23.1 s; grade 2.06/2.07 s; render_wall_s 1
```

## README step issues

1. **`media/demo.mp4` size claim wrong on disk**: README says 4.5 MB; the
   file is 2,890,730 bytes (≈2.9 MB). (Working tree has uncommitted changes
   to `media/demo.mp4`; whichever way, the README does not describe the file
   a visitor gets.) Duration/codec/resolution/fps claims all match.
2. **`media/REVIEW.json` does not exist**, though the README's Media section
   describes it ("the two blind vision-model verdicts"). Either the file was
   never produced/regenerated, or the README ships ahead of the media.
3. **`REPRODUCE.md` does not exist** — required by DEMO-STANDARD before
   merge; fine pre-merge, but the README/Files table does not mention it
   either (the standard's file table in DEMO-STANDARD.md line 18 does).
4. **Wall-time table runs high on this host**: every measured step is below
   the README's stated range (setup 15.5 s vs 44–92 s cold / 8 s warm;
   selftest 23.1 s vs 44–123 s; grade 2.06 s vs 3–12 s; per-render 1 s vs
   ~2–4.5 s). The README scopes the table "From the receipt (2 vCPU, ~4 GB
   RAM)", so this is an environment difference, not a wrong method — but a
   cold run here produced no apt output, suggesting the table's lower bounds
   assume slower hardware than many hosts will have.
5. **Minor**: the grade JSON printed to stdout omits the `timing` (and
   `seed`) keys that only appear in the `--json` file; a reader following
   the README's `bash judge/grade.sh panel.py --json /tmp/v.json` gets them,
   but the printed verdict alone has no `timing.render_wall_s` to read.

Everything the judge measures reproduces exactly: kill rate 11/11 = 100%,
swatch median [51, 128, 230] against target [51, 128, 230], byte-identical
verdict across repeat grades, sha16 0d8e03dcb161d859.
