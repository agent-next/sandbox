#!/usr/bin/env python3
"""Render media/demo.mp4: real animated shots from real judge data.

The media standard (`cookbook/DEMO-STANDARD.md`) bans slides, stills and
Ken-Burns pans for everything but the end card.  This demo's physical thing
is *a page being read*, so every shot animates that, from the real corpus
and the extractor's real output:

   0.0-2.0 s   hook          the finished grounded record types in, its
                             boxes locking onto the page beside it
   2.0-9.5 s   input->output a scanner band sweeps a real skewed scan; each
                             ground-truth box locks on as the band passes
   9.5-14.0 s  escalate      the faded photocopy re-binarises live; each
                             box's ink coverage counts up to its measured
                             value (the judge's own G2 measurement)
  14.0-18.5 s  escalate      the two corrupted pages slide in and are
                             stamped QUARANTINE with their real reason codes
  18.5-23.0 s  escalate      the real self-test verdicts scroll at 3x speed
  23.0-28.0 s  proof         ALL GATES PASSED HUD over still-moving footage
  28.0-30.0 s  end card      static launch line (the only static frame)

Real sources, produced by media/make_runs.py and media/make_media.sh in the
same invocation (nothing invented, nothing illustrative):
  media/data/corpus/          judge/fixtures.py --seed 42
  media/data/extract/         examples/good/extract.py on that corpus
  media/data/corrupt/         judge/corrupt.py --which b0,b1
  media/data/extract-corrupt/ the extractor on the corrupted corpus
  media/data/<artifact>.json  the judge/grade.sh verdicts

Frames land in media/frames/ (git-ignored); media/make_media.sh encodes
them to a lossless master and the web file and runs the repo's video gate.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))

from PIL import Image, ImageDraw

import chartlib as C
from make_figures import MUTANT_ORDER, SHORT, load

DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
EXTRACT = os.path.join(DATA, "extract")
CORRUPT = os.path.join(DATA, "corrupt")
EXTRACT_CORRUPT = os.path.join(DATA, "extract-corrupt")
FRAMES = os.path.join(HERE, "frames")

FPS = 30
W, H = 1920, 1080
DURATION = 30.0

BG = (252, 252, 251)          # the figure surface result.png uses
CARD = (38, 40, 44)           # HUD / terminal surface
TXT = (238, 238, 241)         # text on CARD
TXT_2 = (168, 172, 178)       # secondary text on CARD
INK = (34, 34, 34)            # text on BG
INK_2 = (120, 124, 129)
GREEN = (56, 161, 105)
RED = (213, 94, 0)
BLUE = (0, 114, 178)
BAND_FILL = (0, 114, 178, 64)
BORDER = (150, 152, 156)

# the scanner band that crosses the whole frame in every content shot
SWEEP_FILL = (16, 32, 48, 132)
SWEEP_CORE = (16, 32, 48, 96)
SWEEP_H = 300                     # band height, px
SWEEP_AMP = 330                   # how far its centre travels from mid-frame
SWEEP_PERIOD = 2.6                # s for one down-and-back pass

FIELDS = ("vendor", "invoice_no", "date", "total")
PAGE_W = 900                  # corpus page width in page pixels


def font(size, bold=False):
    """DejaVu from the pinned fonts-dejavu-core package."""
    return C.font(size, bold)


def clip(v, lo, hi):
    return max(lo, min(hi, v))


def ease(p):
    """0..1 -> 0..1 ease-out, so motion never starts at full speed."""
    return 1 - (1 - clip(p, 0, 1)) ** 2


# --------------------------------------------------------------------------
# the real data every frame draws from
# --------------------------------------------------------------------------
class Runs:
    def __init__(self):
        self.truth = json.load(open(os.path.join(DATA, "truth.json")))["pages"]
        self.records = json.load(
            open(os.path.join(EXTRACT, "records.json")))["pages"]
        self.quarantine = json.load(
            open(os.path.join(EXTRACT, "quarantine.json")))["pages"]
        self.corrupt_q = json.load(
            open(os.path.join(EXTRACT_CORRUPT, "quarantine.json")))["pages"]
        self.verdict = json.load(open(os.path.join(DATA, "good.json")))
        self.mutants = [load(m) for m in MUTANT_ORDER]
        self.pages = json.load(
            open(os.path.join(CORPUS, "pages", "pages.json")))["pages"]
        self._cache = {}

    # -- lookups ------------------------------------------------------------
    def file_for(self, page_id):
        return next(p["file"] for p in self.pages
                    if p["page_id"] == page_id)

    def record(self, page_id):
        return next((r for r in self.records if r["page_id"] == page_id),
                    None)

    def truth_page(self, page_id):
        return next(p for p in self.truth if p["page_id"] == page_id)

    def image(self, page_id, width=460, dirs=CORPUS):
        """The page raster at `width`, cached by (path, width)."""
        path = os.path.join(dirs, "pages", self.file_for(page_id))
        key = (path, width)
        if key not in self._cache:
            im = Image.open(path).convert("RGB")
            self._cache[key] = im.resize(
                (width, int(im.height * width / im.width)), Image.LANCZOS)
        return self._cache[key].copy()

    def ink_fraction(self, page_id, bbox):
        """The G2 measurement itself: dark share of the box, with the
        judge's own adaptive threshold (check_gates._ink_threshold)."""
        from check_gates import _ink_threshold
        path = os.path.join(CORPUS, "pages", self.file_for(page_id))
        key = ("ink", path)
        if key not in self._cache:
            self._cache[key] = Image.open(path).convert("L")
        im = self._cache[key]
        thr = _ink_threshold(im)
        region = im.crop(bbox)
        dark = sum(region.histogram()[:thr])
        area = region.size[0] * region.size[1]
        return dark / float(area)

    @property
    def replaced_pages(self):
        """The pages judge/corrupt.py swapped: quarantined on the corrupt
        run but not on the clean one, in corpus order, with real codes."""
        clean = {q["page_id"] for q in self.quarantine}
        order = {p["page_id"]: i for i, p in enumerate(self.pages)}
        out = [q for q in self.corrupt_q if q["page_id"] not in clean]
        return sorted(out, key=lambda q: order[q["page_id"]])


# --------------------------------------------------------------------------
# frame plumbing
# --------------------------------------------------------------------------
class Frame:
    """One 1920x1080 frame: a surface, a page pasted on it, one draw ctx."""

    def __init__(self, runs, title, surface=BG):
        self.runs = runs
        self.im = Image.new("RGB", (W, H), surface)
        self.d = ImageDraw.Draw(self.im, "RGBA")
        self.surface = surface
        if surface is BG:
            self.d.text((72, 34), "agent-next sandbox  ·  disposable  ·  seed 42",
                        font=font(28), fill=INK_2)
            self.d.text((72, 70), title, font=font(56, True), fill=INK)
            self.d.line([(72, 138), (W - 72, 138)], fill=(222, 222, 220),
                        width=2)

    def paste(self, im, xy):
        x, y = xy
        self.d.rectangle([x - 9, y - 9, x + im.width + 9, y + im.height + 9],
                         fill=(255, 255, 255), outline=BORDER, width=2)
        self.im.paste(im, xy)

    def panel(self, box):
        self.d.rectangle(box, fill=CARD)

    def caption(self, lines):
        """Burned-in captions on a translucent strip.

        60 px DejaVu Sans Bold has a ~44 px cap height, the standard's
        ">= 4 % of frame height" at 1080 p; the strip keeps them readable
        over any ground, on a phone, muted.
        """
        block = 84 * len(lines) + 20
        top = H - block - 16
        self.d.rectangle([48, top, W - 48, top + block],
                         fill=(16, 17, 19, 208))
        y = top + 14
        for line in lines:
            self.d.text((76, y), line, font=font(60, True),
                        fill=(247, 247, 249))
            y += 84

    def dim(self, alpha=132):
        self.d.rectangle([0, 0, W, H], fill=(22, 23, 26, alpha))


def band(f, page, px, py, y, height=190):
    """The scanner band: a translucent light bar sweeping the page."""
    f.d.rectangle([px, y - height // 2, px + page.width, y + height // 2],
                  fill=BAND_FILL)
    f.d.line([(px, y), (px + page.width, y)], fill=BLUE, width=3)


def sweep(f, t, period=SWEEP_PERIOD):
    """The scanner pass: a full-width band sweeping down the frame and back.

    A flatbed scan passes light over the whole document, not a 900-px column
    of it, so the band runs edge to edge.  It also keeps every content frame
    visibly moving -- the repo's video gate measures whole-frame change, and
    the small reveal animations alone move too few pixels to register -- and
    a triangle wave (never a stop at the edges) means there is no dead frame.
    Returns the band's centre line so shots can key reveals to it.
    """
    u = (t / period) % 1.0
    y = H // 2 + int(SWEEP_AMP * (2 * abs(2 * u - 1) - 1))
    half = SWEEP_H // 2
    f.d.rectangle([0, y - half, W, y + half], fill=SWEEP_FILL)
    f.d.rectangle([0, y - 36, W, y + 36], fill=SWEEP_CORE)
    f.d.line([(0, y - 4), (W, y - 4)], fill=(140, 202, 255), width=2)
    f.d.line([(0, y), (W, y)], fill=(64, 169, 255), width=5)
    f.d.line([(0, y + 4), (W, y + 4)], fill=(140, 202, 255), width=2)
    return y


def box_on(f, page, px, py, bbox, width=5, color=GREEN):
    s = page.width / float(PAGE_W)
    f.d.rectangle([px + int(bbox[0] * s), py + int(bbox[1] * s),
                   px + int(bbox[2] * s), py + int(bbox[3] * s)],
                  outline=color, width=width)


# --------------------------------------------------------------------------
# shot 1 -- hook: the finished record types in
# --------------------------------------------------------------------------
def shot_hook(f, t, runs):
    page_id = "inv-01"
    page = runs.image(page_id)
    px, py = 110, 200
    f.paste(page, (px, py))

    tr = runs.truth_page(page_id)
    rec = runs.record(page_id)
    x, y, rh = 700, 206, 96
    f.panel([x - 30, y - 62, W - 72, y + rh * 4 + 64])
    f.d.text((x, y - 34), "records.json  ·  %s" % page_id,
             font=font(30), fill=TXT_2, anchor="lm")
    f.d.text((W - 100, y - 34), "confidence", font=font(30), fill=TXT_2,
             anchor="lm")
    typed = clip((t - 0.2) / 1.1, 0, 1) * len(FIELDS)
    for i, fld in enumerate(FIELDS):
        iy = y + i * rh
        live = i < typed
        value = tr["fields"][fld]["value"]
        conf = rec["fields"][fld]["confidence"]
        f.d.text((x, iy), fld, font=font(28), fill=TXT_2, anchor="lm")
        f.d.text((x + 240, iy), value if live else "·" * len(value),
                 font=font(34, True),
                 fill=TXT if live else (86, 90, 96), anchor="lm")
        f.d.text((W - 100, iy), "%.2f" % conf if live else "--",
                 font=font(32, True),
                 fill=GREEN if live else (86, 90, 96), anchor="lm")
        if live:
            box_on(f, page, px, py, tr["fields"][fld]["bbox"])
    if typed >= len(FIELDS):
        f.d.text((x + 240, y + rh * 4 + 16), "grounded on ink",
                 font=font(32, True), fill=GREEN, anchor="lm")
    sweep(f, t)
    f.caption(["every value carries its page region",
               "unsure pages are quarantined, not guessed"])


# --------------------------------------------------------------------------
# shot 2 -- input -> output: a real skewed scan, field by field
# --------------------------------------------------------------------------
def shot_scan(f, t, runs):
    page_id = "inv-05"
    page = runs.image(page_id)
    px, py = 110, 200
    f.paste(page, (px, py))
    tr = runs.truth_page(page_id)
    rec = runs.record(page_id)

    # one field locks per scanner pass: each pass down the page pins the
    # next unread field's box to the ink it just went over
    locked = clip(int((t - 2.8) / (SWEEP_PERIOD / 2)) + 1, 0, len(FIELDS))
    reached = list(FIELDS[:locked])
    for i, fld in enumerate(FIELDS):
        if fld in reached:
            fresh = (t - 2.8) - i * (SWEEP_PERIOD / 2) < 0.45
            box_on(f, page, px, py, tr["fields"][fld]["bbox"],
                   width=8 if fresh else 5)

    # the field just read is picked out over the page-local band too
    fresh = clip(int((t - 2.8) / (SWEEP_PERIOD / 2)), 0, len(FIELDS) - 1)
    fresh_age = (t - 2.8) - fresh * (SWEEP_PERIOD / 2)
    if 0 <= fresh_age < 0.45:
        bbox = tr["fields"][FIELDS[fresh]]["bbox"]
        band(f, page, px, py, py + int((bbox[1] + bbox[3]) * 0.5 *
                                       page.height / 1270.0), height=260)

    x, y, rh = 700, 210, 94
    f.panel([x - 30, y - 62, W - 72, y + rh * 4 + 62])
    f.d.text((x, y - 34), "records.json  ·  %s" % page_id,
             font=font(30), fill=TXT_2, anchor="lm")
    f.d.text((W - 100, y - 34), "confidence", font=font(30), fill=TXT_2,
             anchor="lm")
    for i, fld in enumerate(reached):
        iy = y + i * rh
        f.d.text((x, iy), fld, font=font(28), fill=TXT_2, anchor="lm")
        f.d.text((x + 240, iy), tr["fields"][fld]["value"],
                 font=font(34, True), fill=TXT, anchor="lm")
        f.d.text((W - 100, iy),
                 "%.2f" % rec["fields"][fld]["confidence"],
                 font=font(32, True), fill=GREEN, anchor="lm")
    f.d.text((x + 240, y + rh * 4 + 16),
             "%d/4 fields grounded" % len(reached),
             font=font(32, True), fill=TXT if len(reached) < 4 else GREEN,
             anchor="lm")
    sweep(f, t)
    f.caption(["12 scans · 3 layouts · skew, dust, fade",
               "a box locks on as the band passes the ink"])


# --------------------------------------------------------------------------
# shot 3 -- escalate: the faded photocopy re-binarises live
# --------------------------------------------------------------------------
def _page_threshold(runs, page_id):
    """The judge's own adaptive threshold for this page (mode - 40)."""
    from check_gates import _ink_threshold
    path = os.path.join(CORPUS, "pages", runs.file_for(page_id))
    return _ink_threshold(Image.open(path).convert("L"))


def shot_fade(f, t, runs):
    page_id = "inv-12"                    # the low-contrast profile
    # the content band runs y=190..876 (the caption strip starts at 876), so
    # the page is shown at the widest size whose full height still fits it
    page = runs.image(page_id, width=480)
    px, py = 150, 196
    thr = _page_threshold(runs, page_id)
    lut = [0 if v < thr else v for v in range(256)]
    # rows above the moving divider are re-binarised live (below it the page
    # is still raw), composited through a mask grown by the divider itself.
    # The divider runs down once, monotonically, so the read-out ends with
    # the measured ink in every box; the scanner band keeps sweeping over
    # the recovering page underneath (that band is the motion, not the
    # divider, so the two never fight).
    cut = int(ease(clip((t - 9.6) / 3.6, 0, 1)) * page.height)
    binarised = page.convert("L").point(lut).convert("RGB")
    mask = Image.new("L", page.size, 0)
    ImageDraw.Draw(mask).rectangle([0, 0, page.width, cut], fill=255)
    page = Image.composite(binarised, page, mask)
    f.paste(page, (px, py))
    f.d.line([(px, py + cut), (px + page.width, py + cut)],
             fill=BLUE, width=4)
    sweep(f, t, period=SWEEP_PERIOD * 1.3)

    tr = runs.truth_page(page_id)
    x, y, rh = 780, 198, 122
    f.panel([x - 26, y - 54, W - 72, y + rh * 4 + 36])
    f.d.text((x, y - 30), "ink inside each claimed box (measured)",
             font=font(30), fill=TXT_2, anchor="lm")
    f.d.text((W - 98, y - 30), "threshold %d = mode − 40" % thr,
             font=font(28), fill=TXT_2, anchor="rm")
    for i, fld in enumerate(FIELDS):
        bbox = tr["fields"][fld]["bbox"]
        real = runs.ink_fraction(page_id, bbox)      # the G2 measurement
        shown = real if cut >= int(bbox[3] * page.height / 1270.0) else 0.0
        iy = y + i * rh
        ok = 0.01 <= shown <= 0.60
        f.d.text((x, iy), fld, font=font(30), fill=TXT_2, anchor="lm")
        f.d.text((x + 250, iy), "%5.1f %%" % (100 * shown),
                 font=font(40, True),
                 fill=GREEN if ok else (TXT_2 if shown == 0 else RED),
                 anchor="lm")
        f.d.text((W - 98, iy), "rule 1–60 %", font=font(28),
                 fill=TXT_2, anchor="rm")
        if shown:
            box_on(f, page, px, py, bbox)
    f.caption(["a fixed threshold sees nothing here",
               "adaptive binarisation recovers the ink"])


# --------------------------------------------------------------------------
# shot 4 -- escalate: the negative control
# --------------------------------------------------------------------------
def shot_negative(f, t, runs):
    replaced = runs.replaced_pages            # [inv-02, inv-07], real codes
    width = 440
    gap = 120
    x0 = (W - (len(replaced) * width + (len(replaced) - 1) * gap)) // 2
    for i, q in enumerate(replaced):
        page_id = q["page_id"]
        im = runs.image(page_id, width, dirs=CORRUPT)
        slide = int(clip((t - 14.0 - i * 0.5) * 260, 0, 120))
        iy = 176 + (120 - slide) if i == 0 else 176
        ix = x0 + i * (width + gap)
        f.paste(im, (ix, iy))
        if t - 14.0 > 0.9 + i * 0.6:
            f.d.rectangle([ix, iy, ix + 244, iy + 60], fill=RED)
            f.d.text((ix + 122, iy + 30), "QUARANTINE",
                     font=font(32, True), fill=(255, 255, 255), anchor="mm")
            f.d.text((ix + 8, iy + im.height + 30), q["reason_code"],
                     font=font(40, True), fill=RED, anchor="lm")
    sweep(f, t)
    f.caption(["a blank and a smear, swapped in unseen",
               "both quarantined — 12/12 pages accounted"])


# --------------------------------------------------------------------------
# shot 5 -- escalate: the self-test at 3x speed
# --------------------------------------------------------------------------
def shot_selftest(f, t, runs):
    lines = [("> killed  %s   (failed: %s)"
              % (r["name"], ", ".join(r["failed"])), RED)
             for r in runs.mutants]
    lines.append(("> killed  judge-guard   (weakened ink check)", RED))
    lines.append(("> good   —  every gate passes", GREEN))

    x, y, rh = 96, 210, 54
    f.panel([x - 24, y - 66, x + 1000, y + rh * len(lines) + 44])
    f.d.text((x, y - 38), "bash judge/selftest.sh", font=font(30, True),
             fill=(255, 255, 255), anchor="lm")
    f.d.text((x + 530, y - 38), "3× speed", font=font(34, True),
             fill=(255, 208, 87), anchor="lm")
    visible = int(clip((t - 18.5) / 3.6, 0, 1) * len(lines) + 1e-9)
    for i in range(visible):
        text, col = lines[i]
        f.d.text((x, y + i * rh), text, font=font(27), fill=col)
    # a caret under the newest line keeps the terminal itself alive
    if visible:
        cy = y + (visible - 1) * rh + 34
        f.d.rectangle([x + 4, cy, x + 30, cy + 8], fill=TXT)

    mx, my, mh = 1130, 210, 82
    rows = [(SHORT[r["name"]], not r["passed"]) for r in runs.mutants]
    rows.append(("judge-guard mutant", False))
    f.panel([mx - 26, my - 66, W - 72, my + mh * len(rows) + 58])
    for i, (name, killed) in enumerate(rows):
        iy = my + i * mh
        col = RED if killed else GREEN
        f.d.rectangle([mx, iy - 14, mx + 40, iy + 30], fill=col)
        f.d.text((mx + 62, iy + 8), name, font=font(27), fill=TXT,
                 anchor="lm")
        f.d.text((W - 98, iy + 8), "killed" if killed else "passed",
                 font=font(27, True), fill=col, anchor="rm")
    killed = sum(1 for r in runs.mutants if not r["passed"])
    f.d.text((mx, my + mh * len(rows) + 6),
             "kill rate  %d/%d = 100 %%" % (killed, len(runs.mutants)),
             font=font(38, True), fill=GREEN, anchor="lm")
    sweep(f, t)
    f.caption(["the judge proves it can fail",
               "6/6 single-edit mutants killed"])


# --------------------------------------------------------------------------
# shot 6 -- proof: the verdict over still-moving footage
# --------------------------------------------------------------------------
def shot_proof(f, t, runs):
    page_id = "inv-07"
    page = runs.image(page_id)
    px, py = 96, 200
    f.paste(page, (px, py))
    sweep(f, t)
    f.dim()

    gates = {g["gate"]: g for g in runs.verdict["gates"]}
    f.d.text((96, 186), "ALL GATES PASSED", font=font(92, True),
             fill=(255, 255, 255))
    g1, g3, g4 = gates["G1"], gates["G3"], gates["G4"]
    rows = [
        ("G1", "field accuracy  %d/%d exact" % (g1["correct"], g1["slots"])),
        ("G2", "every claimed box sits on ink"),
        ("G3", "%d/%d totals exact to 0 ulp" % (g3["exact"], g3["totals"])),
        ("G4", "2/2 corrupted pages quarantined"),
    ]
    y = 330
    for gate, text in rows:
        col = GREEN if gates[gate]["passed"] else RED
        f.d.rectangle([96, y, 208, y + 66], outline=col, width=5)
        f.d.text((152, y + 33), gate, font=font(38, True), fill=col,
                 anchor="mm")
        f.d.text((240, y + 33), text, font=font(36),
                 fill=(255, 255, 255), anchor="lm")
        y += 88
    f.d.text((96, y + 18), "judged against the answer key the corpus "
             "generator wrote itself",
             font=font(30), fill=(214, 216, 220))
    f.caption(["one command, one sandbox, one judge"])


# --------------------------------------------------------------------------
# shot 7 -- end card (the only static frame)
# --------------------------------------------------------------------------
def shot_end(f, t, runs):
    f.d.text((96, 380), "doc-extract-convert", font=font(112, True),
             fill=(255, 255, 255))
    f.d.rectangle([96, 560, 104, 664], fill=GREEN)
    f.d.text((140, 570), "python3 cookbook/doc-extract-convert/run.py",
             font=font(54, True), fill=(255, 255, 255))
    f.d.text((96, 680), "a disposable agent-next sandbox: installed, "
             "graded, thrown away",
             font=font(34), fill=TXT_2)


# --------------------------------------------------------------------------
# the cut: (start_s, end_s, shot, title, surface)
# --------------------------------------------------------------------------
SHOTS = [
    (0.0, 2.0, shot_hook, "ugly scans → grounded JSON", BG),
    (2.0, 9.5, shot_scan, "one page, read field by field", BG),
    (9.5, 14.0, shot_fade, "the faded photocopy, recovered", BG),
    (14.0, 18.5, shot_negative, "what it refuses to guess", BG),
    (18.5, 23.0, shot_selftest, "the judge proves it can fail", BG),
    (23.0, 28.0, shot_proof, "the graded verdict", BG),
    (28.0, 30.0, shot_end, "doc-extract-convert", CARD),
]


def main():
    runs = Runs()
    os.makedirs(FRAMES, exist_ok=True)
    for old in os.listdir(FRAMES):
        os.remove(os.path.join(FRAMES, old))
    n = int(DURATION * FPS)
    for i in range(n):
        t = i / FPS
        for start, end, fn, title, surface in SHOTS:
            if start <= t < end:
                frame = Frame(runs, title, surface)
                fn(frame, t, runs)
                frame.im.save(os.path.join(FRAMES, "f%05d.png" % i))
                break
        else:                                    # pragma: no cover
            raise SystemExit("make_video: no shot covers t=%.3f" % t)
    print("[media] %d frames, %.1f s at %d fps -> %s"
          % (n, DURATION, FPS, FRAMES))


if __name__ == "__main__":
    main()
