"""Shared numbers and checks for the skill-ab-bench media.

Every figure and every frame of `demo.mp4` reads the same judge-written
files in `media/data/`; nothing here computes a curve from scratch.  The
only code that *produces* numbers is the pinned judge and the bench:

  data/bench-run.log              judge/bench.py      (48 pairs, pass counts)
  data/bench-fresh-results.json   judge/bench.py      (per-arm answers+verdicts)
  data/verdict-*.json             judge/grade.sh      (gate numbers, CIs, p)
  data/selftest.log               judge/selftest.sh   (11/11 kill rate)
  data/mutants.log                judge/mutants.py    (mutant -> gate map)

`media/scripts/answers.py` loads the *pinned skill policy* that
`judge/arms.py` loads for the skill arm (examples/good/skill/reference.py)
and calls it on the pinned corpus -- that is the policy's own answer
procedure, so the frame does not synthesise a value.

Also here: the overlap check the demo standard requires of every figure
(a text bbox that leaves the figure or intersects another text bbox
raises), and the palette/type constants the figures and the video share.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MEDIA = Path(__file__).resolve().parent.parent          # media/
DEMO = MEDIA.parent                                     # cookbook/skill-ab-bench/
DATA = MEDIA / "data"
REQUIRED = (
    "bench-run.log",
    "bench-fresh-results.json",
    "mutants.log",
    "selftest.log",
    "verdict-good.json",
    "verdict-bench-fresh.json",
    "verdict-arms-swapped.json",
    "verdict-marginal-win.json",
    "verdict-dropped-task.json",
    "verdict-fabricated-verdict.json",
    "verdict-fabricated-arm-answers.json",
    "verdict-shared-answer-arms.json",
    "verdict-significant-placebo.json",
    "verdict-policy-relabelled.json",
    "verdict-judge-no-bad-answers.json",
    "verdict-judge-reference-drift.json",
    "verdict-judge-unverifiable-task.json",
)

# Colour-blind-safe (Okabe-Ito); every figure and every frame uses these.
INK = "#222222"
MUTED = "#6e6e6e"
SKILL = "#0072B2"
NOSKILL = "#D55E00"
PLACEBO = "#009E73"
GRID = "#d8d8d8"
FAIL = "#cc0000"
LIGHT = "#f4f4f4"

FRAMES_PER_S = 30          # every clip is 30 fps
WIDTH, HEIGHT = 1920, 1080

# Demo-standard craft rules.
MIN_CAPTION_PT = 45        # cap height >= 45 px ~ 4.2 % of frame height
PASS_LINE_PTS = 25.0       # judge/G6's delta bar


def fail(msg: str) -> None:
    raise SystemExit(f"media: {msg}")


def require_sources() -> None:
    """Fail loudly when a file the figures need is missing."""
    missing = [name for name in REQUIRED if not (DATA / name).is_file()]
    if missing:
        fail("missing source data (run media/replay_judge.sh first): "
             + ", ".join(missing))


def load_verdict(name: str) -> dict:
    """One committed judge verdict, e.g. load_verdict("verdict-good")."""
    path = DATA / f"{name}.json"
    if not path.is_file():
        fail(f"{path} is missing")
    doc = json.loads(path.read_text())
    if not isinstance(doc, dict) or "gates" not in doc:
        fail(f"{path} is not a grade verdict")
    return doc


def load_records() -> dict:
    """The bench experiment record, keyed by task id."""
    path = DATA / "bench-fresh-results.json"
    if not path.is_file():
        fail(f"{path} is missing")
    doc = json.loads(path.read_text())
    return {t["task_id"]: t for t in doc["tasks"]}


def gate(doc: dict, name: str) -> dict:
    """A gate block; the numbers the video and figures read."""
    block = doc.get("gates", {}).get(name)
    if not isinstance(block, dict):
        fail(f"{doc.get('schema', '?')} verdict has no {name} block")
    return block


def ci_block(doc: dict, gate_name: str = "G6_effect_size") -> dict:
    ci = gate(doc, gate_name).get("ci")
    if not isinstance(ci, dict):
        fail(f"{gate_name} has no bootstrap CI (did the gate stop earlier?)")
    return ci


def pass_counts(doc: dict) -> dict:
    """Skill / no-skill / placebo pass counts in points, from G5/G6/G7."""
    g6, g7 = gate(doc, "G6_effect_size"), gate(doc, "G7_placebo_control")
    out = {
        "skill": g6["skill_passes"],
        "noskill": g6["noskill_passes"],
        "placebo": g7["placebo_passes"],
    }
    return {k: v * 100.0 / 16.0 for k, v in out.items()}


def fisher_p(doc: dict) -> float:
    return float(gate(doc, "G5_power")["fisher_p"])


def bench_summary() -> dict:
    """Pass counts, per-arm and per-task verdicts, straight from the record."""
    records = load_records()
    arms = ("skill", "noskill", "placebo")
    counts = {a: sum(1 for t in records.values() if t[a]["passed"]) for a in arms}
    return {
        "records": records,
        "counts": counts,
        "points": {a: counts[a] * 100.0 / 16.0 for a in arms},
        "task_ids": list(records),
    }


def grade_wall_s(name: str) -> float:
    """Wall time of one grade, from the verdict's timing block."""
    return float(load_verdict(name).get("timing", {}).get("wall_s") or 0.0)


def bench_wall_s() -> float:
    """Wall time of the bench run, from data/bench-run.log (the bench prints
    `48 pairs in 16.2 s`)."""
    match = re.search(r"in ([0-9.]+) s", (DATA / "bench-run.log").read_text())
    if match is None:
        fail("bench-run.log has no '48 pairs in N.N s' line")
    return float(match.group(1))


# ---------------------------------------------------------------- kill matrix

def kill_matrix() -> list[dict]:
    """The 11 self-test kills, from data/mutants.log.

    Every row is a line `mutants: <record> [G3_verifier_replay]  <what>`;
    the gate in brackets is the gate that killed it.
    """
    rows: list[dict] = []
    text = (DATA / "mutants.log").read_text()
    for line in text.splitlines():
        if not line.startswith("mutants:") or "[" not in line:
            continue
        record, bracket, why = line[len("mutants:"):].split("[", 1)[0].strip(), \
            line.split("[", 1)[1].split("]", 1)[0].strip(), \
            line.split("]", 1)[1].strip()
        rows.append({"record": record, "gate": bracket, "why": why})
    if not rows:
        fail("mutants.log holds no kill lines (run judge/mutants.py)")
    return rows


def kill_rate() -> tuple[int, int, float]:
    """(killed, total, rate) from data/selftest.log's `kill rate 11/11 = 100%`
    line -- the line the self-test prints, so the figure cannot drift from it."""
    text = (DATA / "selftest.log").read_text()
    marker = "kill rate "
    line = next((ln for ln in text.splitlines() if marker in ln), None)
    if line is None:
        fail("selftest.log has no kill-rate line")
    left, _, pct = line.split(marker, 1)[1].partition(" = ")
    killed, _, total = left.partition("/")
    return int(killed), int(total), float(pct.rstrip("%"))


# ------------------------------------------------------------- answer tracing

def technique_call(task_id: str, skill_dir: Path = DEMO / "examples/good/skill"):
    """Call the pinned skill policy's technique for one task on its pinned
    input, exactly as judge/arms.py does for the skill arm, and return
    (function_name, call_text, answer)."""
    import importlib.util

    sys.path.insert(0, str(DEMO / "judge"))
    spec = importlib.util.spec_from_file_location(
        "skill_reference", skill_dir / "reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tasks = json.loads((DEMO / "judge/tasks.json").read_text())["tasks"]
    task = next(t for t in tasks if t["task_id"] == task_id)
    params = dict(task["params"])
    if task["kind"] == "kv":
        if "csv_row" in params:
            answer = module.TECHNIQUES["csv_lookup"](
                task["input"], params["csv_row"], params["csv_col"])
            call = (f'TECHNIQUES["csv_lookup"]({task["input"]!r}, '
                    f'{params["csv_row"]!r}, {params["csv_col"]!r})')
        else:
            answer = module.TECHNIQUES["ini_lookup"](task["input"], **params)
            call = f'TECHNIQUES["ini_lookup"]({task["input"]!r}, **{params!r})'
        return "ini_lookup", call, answer
    how = params.pop("how")
    answer = module.TECHNIQUES[how](task["input"], **params)
    call = f'TECHNIQUES["{how}"]({task["input"]!r}, **{params!r})'
    return how, call, answer


def python_source() -> str:
    """The 12-line slice of the technique table the skill arm loads
    (examples/good/skill/reference.py, digits_join .. trailing_int)."""
    lines = (DEMO / "examples/good/skill/reference.py").read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("def digits_join"))
    end = next(i for i, ln in enumerate(lines) if ln.startswith("TECHNIQUES = {"))
    return "\n".join(lines[start:end]).rstrip()


# ------------------------------------------------------------- layout checks

def check_layout(fig) -> None:
    """Fail when any text bbox leaves the figure or overlaps another.

    The demo standard: no clipping, no overlapping text.  Renders the
    canvas, measures every visible Text's bbox in display space, and
    raises naming the offending texts.  Artists hidden behind a
    visibility flag (a tick's unrendered mirror label) and boxes the
    draw never laid out (unit-sized) are skipped; a rendered text
    that is clipped by its own axes is caught by the figure-bounds
    test only, so panels are given real margins instead.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    def rendered(artist):
        while artist is not None:
            if not artist.get_visible():
                return False
            artist = artist.parent
        return True

    boxes = []
    for text in fig.findobj(match=matplotlib.text.Text):
        if not text.get_text().strip() or not rendered(text):
            continue
        box = text.get_window_extent(renderer=renderer)
        if box.width <= 1.5 and box.height <= 1.5:
            continue
        boxes.append((text, box))
    for i, (a, box_a) in enumerate(boxes):
        if (box_a.x0 < -0.5 or box_a.y0 < -0.5
                or box_a.x1 > fig.bbox.width + 0.5
                or box_a.y1 > fig.bbox.height + 0.5):
            fail(f"text leaves the figure: {a.get_text()!r}")
        for b, box_b in boxes[i + 1:]:
            if box_a.overlaps(box_b):
                fail(f"texts overlap: {a.get_text()!r} x {b.get_text()!r}")
