#!/usr/bin/env python3
"""Grade a doc-extract-convert artifact.  Writes one JSON verdict.

This is the part the artifact cannot fool.  It

  1. regenerates the corpus at the requested seed and refuses to grade if
     the regenerated truth or any page digest differs from the checked-in
     judge/truth.json + judge/corpus.sha256,
  2. copies the artifact to scratch and runs it there, twice: once on the
     clean corpus and once on the corpus with two pages corrupted, and
  3. compares what the artifact claims against the generator's truth
     (exact string / Decimal), re-measures the page raster to check every
     bounding box really sits on the ink, and checks that the corrupted
     pages came back quarantined rather than invented.

Usage (normally via judge/grade.sh):
    python3 check_gates.py <artifact_dir> [--json out.json] [--seed N]
                           [--work DIR] [--skip-corrupt]
"""

import argparse
import decimal
import json
import os
import subprocess
import sys
import tempfile

# The judge's own modules live next to this file; say so explicitly rather
# than relying on the interpreter's default sys.path[0], which `python3 -I`
# removes.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corrupt as corrupt_mod          # noqa: E402
import fixtures                        # noqa: E402

FIELDS = ("vendor", "invoice_no", "date", "total")
REASON_CODES = {"LOW_CONFIDENCE", "NO_TEXT", "MALFORMED_FIELD",
                "UNREADABLE_PAGE"}
MAX_BOX_AREA_RATIO = 0.08        # SPEC.md: a box covers at most 8 % of the page
INK_MIN_RATIO = 0.01             # at least 1 % of the box is dark pixels
INK_MAX_RATIO = 0.60             # ...and at most 60 %
FIELD_ACCURACY_MIN = 0.95        # SPEC.md G1
EXTRACT_TIMEOUT = 1800


def die(msg):
    print("[judge] ERROR: %s" % msg, file=sys.stderr)
    raise SystemExit(2)


def run_extractor(artifact, in_dir, out_dir, seed, log_path):
    """Run the artifact's extract.py in a scratch copy of the artifact."""
    with open(log_path, "w") as log:
        proc = subprocess.run(
            [sys.executable, os.path.join(artifact, "extract.py"),
             "--in", in_dir, "--out", out_dir, "--seed", str(seed)],
            stdout=log, stderr=subprocess.STDOUT, cwd=artifact,
            timeout=EXTRACT_TIMEOUT)
    with open(log_path) as log:
        return proc.returncode, log.read()


def load_report(out_dir):
    """Read the artifact's two output files, or explain why we cannot."""
    rec_path = os.path.join(out_dir, "records.json")
    qua_path = os.path.join(out_dir, "quarantine.json")
    for path in (rec_path, qua_path):
        if not os.path.isfile(path):
            return None, "missing %s" % os.path.basename(path)
    try:
        with open(rec_path) as f:
            records = json.load(f)
        with open(qua_path) as f:
            quarantine = json.load(f)
    except ValueError as exc:
        return None, "output is not valid JSON: %s" % exc
    if not isinstance(records, dict) or not isinstance(records.get("pages"), list):
        return None, "records.json has no 'pages' list"
    if not isinstance(quarantine, dict) or not isinstance(quarantine.get("pages"), list):
        return None, "quarantine.json has no 'pages' list"
    return (records["pages"], quarantine["pages"]), None


# --------------------------------------------------------------------------
# G0 — schema and containment
# --------------------------------------------------------------------------

def check_schema(records, quarantine, truth):
    """Return a list of violation strings; empty means the report is sane."""
    problems = []
    by_id = {p["page_id"]: p for p in truth["pages"]}
    w, h = truth["page_width"], truth["page_height"]

    seen = {}
    for page in records:
        if not isinstance(page, dict) or "page_id" not in page:
            problems.append("record without page_id")
            continue
        pid = page["page_id"]
        if pid in seen:
            problems.append("%s: reported twice" % pid)
        seen[pid] = "record"
        if pid not in by_id:
            problems.append("%s: unknown page id" % pid)
        fields = page.get("fields")
        if not isinstance(fields, dict):
            problems.append("%s: 'fields' is not an object" % pid)
            continue
        for name in FIELDS:
            entry = fields.get(name)
            if not isinstance(entry, dict):
                problems.append("%s: field %s missing" % (pid, name))
                continue
            if not isinstance(entry.get("value"), str):
                problems.append("%s/%s: value is not a string" % (pid, name))
            conf = entry.get("confidence")
            if not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
                problems.append("%s/%s: confidence %r outside [0,1]"
                                % (pid, name, conf))
            bbox = entry.get("bbox")
            if (not isinstance(bbox, list) or len(bbox) != 4
                    or not all(isinstance(v, int) for v in bbox)):
                problems.append("%s/%s: bbox is not 4 integers" % (pid, name))
                continue
            x0, y0, x1, y1 = bbox
            if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
                problems.append("%s/%s: bbox %r not inside the %dx%d page"
                                % (pid, name, bbox, w, h))
                continue
            area_ratio = ((x1 - x0) * (y1 - y0)) / float(w * h)
            if area_ratio > MAX_BOX_AREA_RATIO:
                problems.append("%s/%s: bbox covers %.1f%% of the page (max %.0f%%)"
                                % (pid, name, area_ratio * 100,
                                   MAX_BOX_AREA_RATIO * 100))
        total = fields.get("total")
        if isinstance(total, dict) and isinstance(total.get("value"), str):
            if not _is_exact_decimal(total["value"]):
                problems.append("%s/total: %r is not an exact 2-decimal value"
                                % (pid, total["value"]))
        date = fields.get("date")
        if isinstance(date, dict) and isinstance(date.get("value"), str):
            if not _is_iso_date(date["value"]):
                problems.append("%s/date: %r is not YYYY-MM-DD"
                                % (pid, date["value"]))

    for page in quarantine:
        if not isinstance(page, dict) or "page_id" not in page:
            problems.append("quarantine entry without page_id")
            continue
        pid = page["page_id"]
        if pid in seen:
            problems.append("%s: present in both records.json and quarantine.json"
                            % pid)
        seen[pid] = "quarantine"
        if pid not in by_id:
            problems.append("%s: unknown page id in quarantine" % pid)
        if page.get("reason_code") not in REASON_CODES:
            problems.append("%s: reason_code %r is not one of %s"
                            % (pid, page.get("reason_code"),
                               "/".join(sorted(REASON_CODES))))

    for pid in by_id:
        if pid not in seen:
            problems.append("%s: page missing from both files" % pid)
    return problems


def _is_exact_decimal(text):
    if not isinstance(text, str) or not text:
        return False
    try:
        value = decimal.Decimal(text)
    except decimal.InvalidOperation:
        return False
    return value == value.quantize(decimal.Decimal("0.01"))


def _is_iso_date(text):
    if not isinstance(text, str) or len(text) != 10:
        return False
    if text[4] != "-" or text[7] != "-":
        return False
    y, m, d = text[:4], text[5:7], text[8:]
    if not (y.isdigit() and m.isdigit() and d.isdigit()):
        return False
    return 1 <= int(m) <= 12 and 1 <= int(d) <= 31


# --------------------------------------------------------------------------
# G1 / G3 — accuracy and exact totals, against the generator's truth
# --------------------------------------------------------------------------

def score_accuracy(records, truth):
    """Compare every non-quarantined field with the truth, exactly."""
    by_id = {p["page_id"]: p for p in truth["pages"]}
    slots = correct = 0
    exact_totals = correct_totals = 0
    wrong = []
    for page in records:
        pid = page.get("page_id")
        expected = by_id.get(pid)
        if expected is None or expected["status"] != "ok":
            # A record for a page the truth says is unreadable: every field
            # it claims is wrong by construction.
            fields = page.get("fields") or {}
            for name in FIELDS:
                slots += 1
                if isinstance(fields.get(name), dict):
                    wrong.append("%s/%s: claimed a value for an unreadable page"
                                 % (pid, name))
            continue
        fields = page.get("fields") or {}
        for name in FIELDS:
            slots += 1
            entry = fields.get(name)
            got = entry.get("value") if isinstance(entry, dict) else None
            want = expected["fields"][name]["value"]
            if name == "total":
                if got == want:
                    correct_totals += 1
                exact_totals += 1
                if got is not None and _is_exact_decimal(got):
                    if decimal.Decimal(got) != decimal.Decimal(want):
                        wrong.append("%s/total: %s != %s" % (pid, got, want))
                elif got != want:
                    wrong.append("%s/total: %r != %r" % (pid, got, want))
            elif got == want:
                correct += 1
            else:
                wrong.append("%s/%s: %r != %r" % (pid, name, got, want))
            if name != "total" and got == want:
                pass
    # totals counted once, above
    correct += correct_totals
    return {"slots": slots, "correct": correct, "wrong": wrong,
            "exact_totals": exact_totals, "correct_totals": correct_totals}


# --------------------------------------------------------------------------
# G2 — grounding: the box must sit on ink
# --------------------------------------------------------------------------

def check_grounding(records, pages_dir, truth, rng=None):
    """Re-read each claimed region from the raster and require ink in it.

    A box on blank paper, or a box around the whole page, fails.  The
    threshold is a band (1 %..60 % dark pixels) rather than a tight match
    because the box is allowed to be slightly loose; it is not allowed to
    point somewhere else.
    """
    from PIL import Image
    problems = []
    images = {}
    for page in records:
        pid = page.get("page_id")
        fields = page.get("fields") or {}
        for name in FIELDS:
            entry = fields.get(name)
            if not isinstance(entry, dict):
                continue
            bbox = entry.get("bbox")
            if (not isinstance(bbox, list) or len(bbox) != 4
                    or not all(isinstance(v, int) for v in bbox)):
                continue                       # already reported by G0
            page_meta = next((p for p in _index(pages_dir) if p["page_id"] == pid),
                             None)
            if page_meta is None:
                continue
            if pid not in images:
                images[pid] = Image.open(
                    os.path.join(pages_dir, page_meta["file"])).convert("L")
            im = images[pid]
            x0, y0, x1, y1 = bbox
            if not (0 <= x0 < x1 <= im.width and 0 <= y0 < y1 <= im.height):
                continue                       # already reported by G0
            crop = im.crop((x0, y0, x1, y1))
            dark = sum(1 for v in crop.getdata() if v < 128)
            ratio = dark / float(crop.width * crop.height)
            if ratio < INK_MIN_RATIO:
                problems.append("%s/%s: bbox %r has no ink (%.2f%% dark)"
                                % (pid, name, bbox, ratio * 100))
            elif ratio > INK_MAX_RATIO:
                problems.append("%s/%s: bbox %r is %.0f%% ink, too dense to be "
                                "one value" % (pid, name, bbox, ratio * 100))
    return problems


_page_index_cache = {}


def _index(pages_dir):
    if pages_dir not in _page_index_cache:
        with open(os.path.join(pages_dir, "pages.json")) as f:
            _page_index_cache[pages_dir] = json.load(f)["pages"]
    return _page_index_cache[pages_dir]


# --------------------------------------------------------------------------
# G4 — the negative control
# --------------------------------------------------------------------------

def check_negative_control(corrupt_report, truth, corrupt_meta):
    """The corrupted pages must be quarantined, with the right codes."""
    problems = []
    expected = {r["page_id"]: r for r in corrupt_meta["replaced"]}
    records, quarantine = corrupt_report
    quarantined = {p.get("page_id"): p for p in quarantine}

    got_ids = set(quarantined)
    if got_ids != set(expected):
        missing = sorted(set(expected) - got_ids)
        extra = sorted(got_ids - set(expected))
        if missing:
            problems.append("corrupted page(s) not quarantined: %s"
                            % ", ".join(missing))
        if extra:
            problems.append("quarantined page(s) that are not corrupted: %s"
                            % ", ".join(extra))

    for pid, meta in expected.items():
        entry = quarantined.get(pid)
        if entry is None:
            continue
        want = meta["reason_expected"]
        if entry.get("reason_code") != want:
            problems.append("%s: reason_code %r, expected %r"
                            % (pid, entry.get("reason_code"), want))

    invented = [p.get("page_id") for p in records
                if p.get("page_id") in expected]
    if invented:
        problems.append("invented a record for corrupted page(s): %s"
                        % ", ".join(sorted(invented)))

    accounted = len(records) + len(quarantine)
    if accounted != len(truth["pages"]):
        problems.append("page count %d != %d (records %d + quarantine %d)"
                        % (accounted, len(truth["pages"]), len(records),
                           len(quarantine)))
    return problems


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("artifact")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--work")
    ap.add_argument("--skip-corrupt", action="store_true")
    args = ap.parse_args(argv)

    decimal.getcontext().prec = 28
    artifact = os.path.abspath(args.artifact)
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isfile(os.path.join(artifact, "extract.py")):
        die("%s has no extract.py" % artifact)

    work = args.work or tempfile.mkdtemp(prefix="docjudge.")
    os.makedirs(work, exist_ok=True)
    clean_dir = os.path.join(work, "clean")
    corrupt_dir = os.path.join(work, "corrupt")
    out_clean = os.path.join(work, "out-clean")
    out_corrupt = os.path.join(work, "out-corrupt")

    gates = []
    timing = {}

    def gate(name, passed, detail, **extra):
        entry = {"gate": name, "passed": bool(passed), "detail": detail}
        entry.update(extra)
        gates.append(entry)
        return entry

    # -- corpus, and the drift check against the checked-in answer key ------
    import time
    t0 = time.time()
    truth = fixtures.generate(args.seed, clean_dir)
    timing["generate_corpus"] = round(time.time() - t0, 2)

    drift = _check_drift(here, truth, clean_dir)
    if drift:
        gate("G0", False, "fixture drift: " + "; ".join(drift))
        return _emit(args, gates, timing, work, die_on_drift=True)

    pages_dir = os.path.join(clean_dir, "pages")
    t0 = time.time()
    rc, log = run_extractor(artifact, pages_dir, out_clean, args.seed,
                            os.path.join(work, "extract-clean.log"))
    timing["extract_clean"] = round(time.time() - t0, 2)
    if rc != 0:
        gate("G0", False, "extract.py exited %d on the clean corpus "
             "(last line: %s)" % (rc, log.strip().splitlines()[-1:]))
        return _emit(args, gates, timing, work)

    report, err = load_report(out_clean)
    if err:
        gate("G0", False, err)
        return _emit(args, gates, timing, work)
    records, quarantine = report

    schema = check_schema(records, quarantine, truth)
    gate("G0", not schema,
         "%d schema violation(s)" % len(schema) if schema
         else "%d record(s) + %d quarantined, all well formed"
              % (len(records), len(quarantine)),
         violations=schema[:20])

    score = score_accuracy(records, truth)
    accuracy = (score["correct"] / score["slots"]) if score["slots"] else 0.0
    gate("G1", accuracy >= FIELD_ACCURACY_MIN and not score["wrong"],
         "field accuracy %.3f (%d/%d, min %.2f)"
         % (accuracy, score["correct"], score["slots"], FIELD_ACCURACY_MIN),
         accuracy=round(accuracy, 4), correct=score["correct"],
         slots=score["slots"], examples=score["wrong"][:20])

    grounding = check_grounding(records, pages_dir, truth)
    gate("G2", not grounding,
         "%d box(es) not grounded on ink" % len(grounding) if grounding
         else "every claimed box sits on ink", violations=grounding[:20])

    exact_ok = (score["correct_totals"] == score["exact_totals"]
                and score["exact_totals"] > 0)
    gate("G3", exact_ok,
         "%d/%d totals exact to 0 ulp"
         % (score["correct_totals"], score["exact_totals"]),
         exact=score["correct_totals"], totals=score["exact_totals"])

    if args.skip_corrupt:
        gate("G4", True, "skipped (--skip-corrupt)", skipped=True)
    else:
        t0 = time.time()
        meta = corrupt_mod.corrupt(clean_dir, corrupt_dir, ("b0", "b1"),
                                   args.seed)
        timing["corrupt_corpus"] = round(time.time() - t0, 2)
        t0 = time.time()
        rc, log = run_extractor(artifact, os.path.join(corrupt_dir, "pages"),
                                out_corrupt, args.seed,
                                os.path.join(work, "extract-corrupt.log"))
        timing["extract_corrupt"] = round(time.time() - t0, 2)
        if rc != 0:
            gate("G4", False, "extract.py exited %d on the corrupted corpus"
                 % rc)
        else:
            report, err = load_report(out_corrupt)
            if err:
                gate("G4", False, err)
            else:
                nc = check_negative_control(report, truth,
                                            {"replaced": meta})
                gate("G4", not nc,
                     "%d negative-control violation(s)" % len(nc) if nc
                     else "%d/%d corrupted pages quarantined, no invented "
                          "values, %d/%d pages accounted"
                          % (len(meta), len(meta),
                             len(report[0]) + len(report[1]),
                             len(truth["pages"])),
                     violations=nc[:20])

    return _emit(args, gates, timing, work)


def _check_drift(here, truth, clean_dir):
    """Compare the regenerated corpus against the checked-in answer key."""
    problems = []
    truth_path = os.path.join(here, "truth.json")
    sha_path = os.path.join(here, "corpus.sha256")
    if os.path.isfile(truth_path):
        with open(truth_path) as f:
            frozen = json.load(f)
        if frozen != truth:
            problems.append("regenerated truth.json differs from judge/truth.json")
    if os.path.isfile(sha_path):
        want = {}
        with open(sha_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                digest, pid = line.split(None, 1)
                want[pid.strip()] = digest
        for page in truth["pages"]:
            if want.get(page["page_id"]) != page["sha256"]:
                problems.append("%s: raster digest differs from corpus.sha256"
                                % page["page_id"])
    return problems


def _emit(args, gates, timing, work, die_on_drift=False):
    verdict = {
        "artifact": args.artifact,
        "seed": args.seed,
        "all_gates_passed": all(g["passed"] for g in gates),
        "gates": gates,
        "timing": timing,
    }
    text = json.dumps(verdict, indent=2, sort_keys=True)
    if args.json_out:
        with open(args.json_out, "w") as f:
            f.write(text + "\n")
    print(text)
    if die_on_drift:
        return 2
    return 0 if verdict["all_gates_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
