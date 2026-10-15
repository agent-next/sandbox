#!/usr/bin/env python3
"""doc-extract-convert — reference extractor.

Reads a directory of scanned invoice/receipt pages and writes

    records.json      one grounded record per page read with confidence
    quarantine.json   one entry per page it refuses to guess at

Every field value carries the page-pixel bbox it was read from.  The
pipeline is deliberately boring and inspectable:

    load -> denoise -> OCR (tesseract TSV) -> anchor on the field's printed
    label -> read the value on the label's line -> normalise -> validate ->
    confidence -> accept or quarantine

Quarantine is the default: a page is only reported when all four fields
were found, validated and read with confidence >= CONF_THRESHOLD.

Usage:
    python3 extract.py --in <pages_dir> --out <out_dir> [--seed N]

Only the standard library and Pillow are needed; tesseract must be on PATH.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation

from PIL import Image, ImageFilter

# Confidence floor for accepting a page.  Calibrated against this corpus
# rather than picked: the lowest confidence the extractor assigns to a
# field on a page it reads correctly is 0.66 (a dust-speckled total); the
# highest it assigns to a field on a page it must refuse is 0.38 (letters
# tesseract invented inside a mis-feed smear).  0.60 sits between the two
# with room on both sides, which is what makes the accept/quarantine
# decision decisive instead of knife-edge.
CONF_THRESHOLD = 0.60

# --------------------------------------------------------------------------
# Label anchors.  Each layout family prints its own label; the extractor
# knows the label vocabulary, not the layout.  Anchoring on the label (not
# on page position) is what makes the box a real grounding: the box is the
# region the *value* was read from.
# --------------------------------------------------------------------------

LABELS = {
    # OCR inserts and drops spaces inside labels ("invoice _no:", "Noo"),
    # so labels are matched against the token text with its spaces removed.
    "invoice_no": [r"invoice_?no\.?", r"docid", r"^no\.?$"],
    "date": [r"invoicedate", r"^date$", r"^issued$"],
    "total": [r"totaldue", r"amountpayable", r"total", r"^amount$"],
    "vendor": [r"^vendor$"],
}

INVOICE_NO_RE = re.compile(r"^[A-Z]{2,4}-?\d{3,}$", re.I)
DATE_FORMATS = (
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), (1, 2, 3)),
    (re.compile(r"^(\d{4})/(\d{2})/(\d{2})$"), (1, 2, 3)),
    (re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"), (3, 2, 1)),   # DD/MM/YYYY
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$"), (3, 2, 1)),  # DD.MM.YYYY
)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
TEXT_DATE_RE = re.compile(r"^(\d{1,2})\s*([A-Za-z]{3,})\s*(\d{4})$")
MONEY_RE = re.compile(r"^-?\d{1,3}(?:[, ]\d{3})*(?:\.\d{2})$|^-?\d+\.\d{2}$")


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------

def ocr_tsv(image_path):
    """Run tesseract in TSV mode; return a list of word dicts with boxes.

    A blank page yields no words; a smear page yields few, garbage words.
    Both are visible to the caller as an empty/short list, which is what
    routes them to quarantine.

    Tesseract is pinned to one thread (OMP_THREAD_LIMIT=1) for two reasons:
    it is ~14x faster here (0.54 s vs 7.3 s per page on a 2 vCPU box, where
    the OpenMP thread pool costs far more than it saves on a single page),
    and it keeps the word confidences bit-identical run to run.
    """
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    proc = subprocess.run(
        ["tesseract", image_path, "stdout", "--psm", "6", "-l", "eng", "tsv"],
        capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        return []
    words = []
    lines = proc.stdout.splitlines()
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) < 12 or not cells[11].strip():
            continue
        try:
            conf = float(cells[10])
        except ValueError:
            continue
        if conf < 0:
            continue
        words.append({
            "text": cells[11].strip(),
            "x": int(cells[6]), "y": int(cells[7]),
            "w": int(cells[8]), "h": int(cells[9]),
            "conf": conf,
            "line": (int(cells[1]), int(cells[2]), int(cells[3]), int(cells[4])),
        })
    return words


def group_lines(words):
    """Group words into printed lines, left to right, top to bottom."""
    by_line = {}
    for w in words:
        by_line.setdefault(w["line"], []).append(w)
    out = []
    for key in sorted(by_line, key=lambda k: (k[0], k[1], k[2], k[3])):
        ws = sorted(by_line[key], key=lambda w: w["x"])
        out.append(ws)
    return out


def line_text(ws):
    return " ".join(w["text"] for w in ws)


def strip_trailing_punct(tok):
    return tok.strip(".,;:()[]|\"'“”‘’-–—_~*#")


# --------------------------------------------------------------------------
# Field readers.  Each returns (value, bbox, confidence) or None.
# --------------------------------------------------------------------------

def _join_value_words(ws, sep=""):
    """Merge a run of words into one value token and its bounding box.

    OCR attaches the page's punctuation to the value ("“INV-3270", "169.61|"),
    so each word is stripped of leading/trailing punctuation before joining.
    The bbox keeps the *printed* extent, which is what the grounding check
    measures.
    """
    text = sep.join(strip_trailing_punct(w["text"]) for w in ws)
    x0 = min(w["x"] for w in ws)
    y0 = min(w["y"] for w in ws)
    x1 = max(w["x"] + w["w"] for w in ws)
    y1 = max(w["y"] + w["h"] for w in ws)
    conf = min(w["conf"] for w in ws)
    return text, [x0, y0, x1, y1], conf / 100.0


def _candidates(ws, limit=3):
    """Every plausible way OCR might have split one printed value.

    A value can come back as one token, as a run joined by spaces
    ("NORTHWIND TRADING COMPANY"), or as a run split mid-token
    ("INV" "3654").  Rather than guess, hand the reader both joins and let
    the field's own validator choose.
    """
    out = []
    for n in range(1, min(limit, len(ws)) + 1):
        for sep in (" ", ""):
            out.append(_join_value_words(ws[:n], sep))
    return out


def _value_after_label(ws, start, field):
    """Read a field's value from the tokens at/after position `start`."""
    rest = ws[start:]
    if not rest:
        return None
    if field == "vendor":
        # Longest first: "NORTHWIND TRADING" is a valid-looking prefix of
        # "NORTHWIND TRADING COMPANY", so the shortest match would silently
        # truncate the name.
        for cand in reversed(_candidates(rest, limit=len(rest))):
            val = normalise_vendor(cand[0])
            if val is not None and not VENDOR_STOP.match(val):
                return cand
        return None
    if field == "invoice_no":
        for w in rest:
            tok = strip_trailing_punct(w["text"])
            if INVOICE_NO_RE.match(tok):
                return _join_value_words([w])
        for cand in _candidates(rest):
            if INVOICE_NO_RE.match(strip_trailing_punct(cand[0])):
                return cand
        return None
    if field == "date":
        for w in rest:
            if parse_date(strip_trailing_punct(w["text"])) is not None:
                return _join_value_words([w])
        for cand in _candidates(rest):
            if parse_date(cand[0]) is not None:
                return cand
        return None
    if field == "total":
        for w in reversed(rest):
            tok = strip_trailing_punct(w["text"])
            if MONEY_RE.match(tok):
                return _join_value_words([w])
        for cand in _candidates(rest):
            if MONEY_RE.match(strip_trailing_punct(cand[0])):
                return cand
        return None
    return None


def _squash(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _label_positions(ws, patterns):
    """Token indices just past a label occurrence on this printed line.

    A label is matched on the space- and punctuation-stripped text of one,
    two or three consecutive tokens, which is what absorbs OCR's habit of
    splitting "invoice_no" into "invoice _no" or "No." into "Noo".
    """
    out = []
    for i in range(len(ws)):
        for n in (1, 2, 3):
            if i + n > len(ws):
                break
            squashed = _squash("".join(w["text"] for w in ws[i:i + n]))
            if not squashed:
                break
            if any(pat.search(squashed) for pat in patterns):
                out.append(i + n)
                break
    return out


def read_labelled(lines, field):
    """Find the value for `field` next to its printed label.

    Labels and values are not always on the same line: the wide-table layout
    prints a header row ("DOC ID   ISSUED") and the values on the row below.
    So after a label with nothing usable behind it, the next printed line is
    searched for the value.
    """
    patterns = [re.compile(p, re.I) for p in LABELS[field]]
    for li, ws in enumerate(lines):
        for start in _label_positions(ws, patterns):
            got = _value_after_label(ws, start, field)
            if got:
                return got
            if li + 1 < len(lines):
                got = _value_after_label(lines[li + 1], 0, field)
                if got:
                    return got
    return None


VENDOR_STOP = re.compile(
    r"^(INVOICE|ITEMS|DOC-RECORD-BEGIN|DOC-RECORD-END|DOC ID|ISSUED|DATE|"
    r"TOTAL|AMOUNT PAYABLE|VENDOR)$", re.I)


def read_vendor_heading(lines, page_h):
    """Layouts A/B/C have no `vendor:` label: the vendor is the largest
    line in the top third of the page whose words are all alphabetic
    (bar ampersand, hyphen and the OCR's stray punctuation).

    A line carrying digits, or any of the reserved heading words, is not a
    vendor name -- that is what keeps "INVOICE", "DOC ID   ISSUED" and the
    item rows from being mistaken for one.
    """
    best = None
    for ws in lines:
        if ws[0]["y"] > page_h * 0.34:
            continue
        kept = []
        for w in ws:
            tok = strip_trailing_punct(w["text"])
            if not tok:
                continue
            if any(c.isdigit() for c in tok):
                kept = []
                break
            if not re.match(r"^[A-Za-z&'\-]+$", tok):
                kept = []
                break
            kept.append(w)
        if not kept:
            continue
        text = " ".join(w["text"] for w in kept)
        if VENDOR_STOP.match(strip_trailing_punct(text).strip()):
            continue
        letters = [c for c in text if c.isalpha()]
        if len(letters) < 8:
            continue
        h = max(w["h"] for w in kept)
        if best is None or h > best[0]:
            best = (h, _join_value_words(kept, " "))
    return best[1] if best else None


def parse_date(text):
    """Normalise any printed date to YYYY-MM-DD, or return None."""
    t = text.strip().replace(",", "")
    for pat, order in DATE_FORMATS:
        m = pat.match(t)
        if m:
            y, mo, d = (int(m.group(i)) for i in order)
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return "%04d-%02d-%02d" % (y, mo, d)
    m = TEXT_DATE_RE.match(t)
    if m:
        mon = MONTHS.get(m.group(2)[:3].lower())
        if mon:
            return "%04d-%02d-%02d" % (int(m.group(3)), mon, int(m.group(1)))
    return None


def normalise_total(text):
    """Exact decimal string with two fraction digits, or None."""
    t = strip_trailing_punct(text).replace(" ", "").replace(",", "")
    if not t or not re.match(r"^-?\d+(\.\d+)?$", t):
        return None
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    if d != d.quantize(Decimal("0.01")):
        return None
    return "%.2f" % d


def normalise_vendor(text):
    t = re.sub(r"\s+", " ", text).strip(" .,;:")
    t = re.sub(r"[^A-Za-z0-9&\-' ]", "", t)
    if len(t) < 6 or len(t.split()) < 2:
        return None
    return t.upper()


# --------------------------------------------------------------------------

def extract_page(image_path, page_id):
    """Return ("ok", fields) or ("quarantine", reason_code, detail)."""
    with Image.open(image_path) as im:
        im = im.convert("L")
        w, h = im.size
        # Upscale, then despeckle: upscaling makes the small degraded pages
        # readable, and the median pass afterwards removes isolated scanner
        # dust at 2x, where it no longer touches glyph strokes.  (Denoising
        # *before* upscaling was measured to blur glyphs together -- it
        # turned INV-3654 into "INV 3654" -- so the order matters.)
        prepared = im.resize((w * 2, h * 2), Image.LANCZOS)
        prepared = prepared.filter(ImageFilter.MedianFilter(3))
        work = os.path.join(os.path.dirname(image_path), ".prep-%s.png" % page_id)
        prepared.save(work, format="PNG")
    try:
        words = ocr_tsv(work)
    finally:
        try:
            os.unlink(work)
        except OSError:
            pass
    # tesseract ran on the 2x image; bring boxes back to page pixels.
    for word in words:
        word["x"] //= 2
        word["w"] = max(1, word["w"] // 2)
        word["y"] //= 2
        word["h"] = max(1, word["h"] // 2)

    if not words:
        return ("quarantine", "NO_TEXT", "no readable text on the page")
    lines = group_lines(words)
    if len(words) < 4:
        return ("quarantine", "UNREADABLE_PAGE",
                "only %d word(s) recognised" % len(words))

    raw = {}
    for field in ("invoice_no", "date", "total"):
        got = read_labelled(lines, field)
        if got:
            raw[field] = got
    got = read_labelled(lines, "vendor") or read_vendor_heading(lines, h)
    if got:
        raw["vendor"] = got

    missing = [f for f in ("vendor", "invoice_no", "date", "total")
               if f not in raw]
    if missing:
        return ("quarantine", "UNREADABLE_PAGE",
                "no printed label/value for: %s" % ", ".join(sorted(missing)))

    values = {
        "vendor": normalise_vendor(raw["vendor"][0]),
        "invoice_no": raw["invoice_no"][0].upper(),
        "date": parse_date(raw["date"][0]),
        "total": normalise_total(raw["total"][0]),
    }
    bad = [f for f in values if values[f] is None]
    if bad:
        return ("quarantine", "MALFORMED_FIELD",
                "field(s) did not validate: %s" % ", ".join(sorted(bad)))

    fields = {}
    for name in ("vendor", "invoice_no", "date", "total"):
        _, bbox, conf = raw[name]
        fields[name] = {"value": values[name], "bbox": bbox,
                        "confidence": round(conf, 4)}

    worst = min(f["confidence"] for f in fields.values())
    if worst < CONF_THRESHOLD:
        return ("quarantine", "LOW_CONFIDENCE",
                "best field confidence %.2f < %.2f" % (worst, CONF_THRESHOLD))
    return ("ok", fields)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="in_dir", required=True)
    ap.add_argument("--out", dest="out_dir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    with open(os.path.join(args.in_dir, "pages.json")) as f:
        index = json.load(f)["pages"]
    os.makedirs(args.out_dir, exist_ok=True)

    records, quarantine = [], []
    for page in index:
        path = os.path.join(args.in_dir, page["file"])
        outcome = extract_page(path, page["page_id"])
        if outcome[0] == "ok":
            records.append({"page_id": page["page_id"], "fields": outcome[1]})
        else:
            _, reason, detail = outcome
            quarantine.append({"page_id": page["page_id"],
                               "reason_code": reason, "detail": detail})

    for name, data in (("records.json", {"pages": records}),
                       ("quarantine.json", {"pages": quarantine})):
        with open(os.path.join(args.out_dir, name), "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")

    print("[extract] %d page(s): %d record(s), %d quarantined"
          % (len(index), len(records), len(quarantine)))
    for q in quarantine:
        print("[extract]   quarantine %s: %s (%s)"
              % (q["page_id"], q["reason_code"], q["detail"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
