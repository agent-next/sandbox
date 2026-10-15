#!/usr/bin/env python3
"""Generate the doc-extract-convert corpus and its ground truth.

Everything here is a pure function of --seed: the record list, the layouts,
the raster degradations and the ground-truth JSON.  Rendering goes through
Pillow; the fonts come from the pinned fonts-dejavu-core package, so the
raster is reproducible across machines (Pillow's default bitmap font is
not).

The ground truth is written by *this generator*, in the same pass that
draws the pixels, and never by an OCR step -- that is what makes it an
independent oracle for judge/grade.sh.

Usage:
    python3 fixtures.py --seed 42 --out CORPUS_DIR [--truth FILE]

Outputs (into CORPUS_DIR):
    pages/p000.png ... p011.png   grayscale PNG scans
    pages/pages.json              {"pages":[{"page_id","file","width","height"}]}
    truth.json                    the answer key

The answer key is deliberately *not* inside pages/: that is the only
directory the extractor is pointed at, so it cannot read the answers out of
its own input.
"""

import argparse
import decimal
import hashlib
import json
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

PAGE_W, PAGE_H = 900, 1270
N_PAGES = 12

FONT_DIR = os.environ.get("DOCEX_FONT_DIR", "/usr/share/fonts/truetype/dejavu")
FONTS = {
    "serif": "DejaVuSerif.ttf",
    "serif_bold": "DejaVuSerif-Bold.ttf",
    "sans": "DejaVuSans.ttf",
    "sans_bold": "DejaVuSans-Bold.ttf",
    "mono": "DejaVuSansMono.ttf",
}
_font_cache = {}


def font(name, size):
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            os.path.join(FONT_DIR, FONTS[name]), size)
    return _font_cache[key]


# --------------------------------------------------------------------------
# Record pool.  Totals are exact decimals built as integer cents, so the
# ground truth is never a rounded float.
# --------------------------------------------------------------------------

VENDORS = [
    "NORTHWIND TRADING COMPANY",
    "ACME INDUSTRIAL SUPPLY",
    "HELVETIA PARTS AG",
    "BLUE RIDGE LOGISTICS",
    "ORION OFFICE SYSTEMS",
    "CASCADE BUILDING SUPPLY",
    "MERIDIAN ELECTRIC WORKS",
    "FOXGLOVE PAPER MILLS",
    "PINEHURST MEDICAL SUPPLY",
    "ATLAS FASTENER WORKS",
    "KESTREL PRINT & COPY",
    "SUMMIT LAB SUPPLIES",
]

ITEMS = [
    "Widget assembly", "Hex bolt M8", "Copier toner", "A4 paper ream",
    "Shipping crate", "Cable spool", "Safety gloves", "Lab beaker",
    "Pallet wrap", "Label roll", "Desk lamp", "Toner cartridge",
]


def cents_str(cents):
    return "%d.%02d" % (cents // 100, cents % 100)


def build_records(rng):
    """Deterministic record list; inv-08 is the already-broken page."""
    recs = []
    for i in range(N_PAGES):
        page_id = "inv-%02d" % (i + 1)
        vendor = VENDORS[i % len(VENDORS)]
        number = 3000 + rng.randrange(0, 999)
        y, m, d = 2025 + (i % 2), 1 + rng.randrange(0, 12), 1 + rng.randrange(0, 28)
        subtotal = rng.randrange(9000, 780000)
        tax_bp = rng.choice([0, 725, 825, 1000, 1900])          # basis points
        tax = (subtotal * tax_bp + 5000) // 10000
        total = subtotal + tax
        # what the *page* prints for the date; inv-08 prints a non-date token
        printed_date = "%04d-%02d-%02d" % (y, m, d)
        date_bad = (page_id == "inv-08")
        if date_bad:
            printed_date = "SEE ATTACHED"
        recs.append({
            "page_id": page_id,
            "vendor": vendor,
            "invoice_no": "INV-%d" % number,
            "date": "%04d-%02d-%02d" % (y, m, d),
            "printed_date": printed_date,
            "date_bad": date_bad,
            "subtotal": subtotal,
            "tax_bp": tax_bp,
            "tax": tax,
            "total": total,
            "n_items": 5 + rng.randrange(0, 5),
        })
    return recs


# --------------------------------------------------------------------------
# Page drawing.  draw_field() is the single place a value is printed, so the
# bbox returned there is by construction the region the ink lives in.
# --------------------------------------------------------------------------

def _measure(draw, text, f):
    box = draw.textbbox((0, 0), text, font=f)
    return box[2] - box[0], box[3] - box[1]


def draw_field(draw, xy, text, f, fill=25, pad=2):
    """Draw one field value and return its tight bbox in page pixels."""
    x, y = xy
    w, h = _measure(draw, text, f)
    draw.text((x, y), text, font=f, fill=fill)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(PAGE_W, x + w + pad), min(PAGE_H, y + h + pad)
    return [int(x0), int(y0), int(x1), int(y1)]


def draw_label(draw, xy, text, f, fill=110):
    draw.text(xy, text, font=f, fill=fill)


def layout_three_block(draw, r, boxes):
    """Layout family A: three stacked blocks (invoice / items / total)."""
    f_head = font("serif_bold", 32)
    f_lab = font("serif", 18)
    f_val = font("serif", 22)
    draw_label(draw, (60, 44), "INVOICE", font("serif_bold", 40), fill=40)
    draw_label(draw, (60, 96), "-" * 52, f_lab)
    boxes["vendor"] = draw_field(draw, (60, 124), r["vendor"], f_head)
    y = 220
    for lab, key, val in (("Invoice No:", "invoice_no", r["invoice_no"]),
                          ("Invoice Date:", "date", r["printed_date"])):
        draw_label(draw, (60, y + 5), lab, f_lab)
        boxes[key] = draw_field(draw, (255, y), val, f_val)
        y += 40
    y += 30
    draw_label(draw, (60, y), "Items", f_lab)
    y += 30
    for i in range(r["n_items"]):
        draw_label(draw, (72, y), "%d  %s" % (2 + i, ITEMS[(i * 3) % len(ITEMS)]),
                   f_val, fill=60)
        y += 30
    y += 34
    draw_label(draw, (60, y + 8), "TOTAL DUE:", font("serif_bold", 26), fill=60)
    boxes["total"] = draw_field(draw, (430, y), cents_str(r["total"]),
                                font("serif_bold", 28))
    return boxes


def layout_wide_table(draw, r, boxes):
    """Layout family B: wide bordered table with the header top-left."""
    f_head = font("sans_bold", 30)
    f_lab = font("sans", 18)
    f_val = font("sans", 21)
    boxes["vendor"] = draw_field(draw, (55, 55), r["vendor"], f_head)
    draw.line((55, 104, PAGE_W - 55, 104), fill=90, width=2)
    y = 128
    draw_label(draw, (55, y), "DOC ID", f_lab)
    draw_label(draw, (330, y), "ISSUED", f_lab)
    y += 26
    boxes["invoice_no"] = draw_field(draw, (55, y), r["invoice_no"], f_val)
    boxes["date"] = draw_field(draw, (330, y), r["printed_date"], f_val)
    y += 60
    draw.line((55, y, PAGE_W - 55, y), fill=150)
    y += 16
    for i in range(r["n_items"]):
        draw_label(draw, (65, y), ITEMS[(i * 5) % len(ITEMS)], f_val, fill=60)
        draw_label(draw, (600, y), "%d" % (1 + i), f_val, fill=60)
        draw_label(draw, (720, y), cents_str(r["subtotal"] // r["n_items"]),
                   f_val, fill=60)
        y += 28
    y += 40
    draw_label(draw, (55, y + 10), "AMOUNT PAYABLE", font("sans_bold", 24), fill=60)
    boxes["total"] = draw_field(draw, (430, y), cents_str(r["total"]),
                                font("sans_bold", 27))
    return boxes


def layout_center_card(draw, r, boxes):
    """Layout family C: centred card, receipt style, monospace values."""
    f_head = font("sans_bold", 30)
    f_val = font("mono", 22)
    f_lab = font("sans", 18)
    w, _ = _measure(draw, r["vendor"], f_head)
    boxes["vendor"] = draw_field(draw, ((PAGE_W - w) // 2, 95), r["vendor"], f_head)
    y = 200
    for lab, key, val in (("No.", "invoice_no", r["invoice_no"]),
                          ("Date", "date", r["printed_date"])):
        wv, _ = _measure(draw, val, f_val)
        draw_label(draw, (PAGE_W // 2 - 250, y + 5), lab, f_lab)
        boxes[key] = draw_field(draw, (PAGE_W // 2 + 90 - wv // 2, y), val, f_val)
        y += 44
    y += 40
    for i in range(r["n_items"]):
        draw_label(draw, (PAGE_W // 2 - 250, y), ITEMS[(i * 7) % len(ITEMS)],
                   f_lab, fill=60)
        y += 28
    y += 50
    wt, _ = _measure(draw, cents_str(r["total"]), font("sans_bold", 30))
    draw_label(draw, (PAGE_W // 2 - 250, y + 6), "TOTAL", font("sans_bold", 26), fill=60)
    boxes["total"] = draw_field(draw, (PAGE_W // 2 + 100 - wt // 2, y),
                                cents_str(r["total"]), font("sans_bold", 30))
    return boxes


LAYOUTS = (layout_three_block, layout_wide_table, layout_center_card)


# --------------------------------------------------------------------------
# Structured documents: a raster page carrying a fenced, typed record block.
# The extractor may parse it directly; the judge's truth is unchanged.
# --------------------------------------------------------------------------

def layout_structured(draw, r, boxes):
    """Structured page: a fenced, typed record block drawn as real ink.

    Each value is drawn with draw_field right after its label, so the
    ground-truth bbox is the region the value itself occupies -- the same
    contract as the raster layouts.
    """
    f = font("mono", 15)
    x, y = 60, 70
    draw_label(draw, (x, y), "DOC-RECORD-BEGIN", font("sans_bold", 16), fill=70)
    y += 34
    rows = (("vendor", r["vendor"]),
            ("invoice_no", r["invoice_no"]),
            ("date", r["date"]),
            ("total", cents_str(r["total"])))
    for key, val in rows:
        prefix = "%s: " % key
        draw_label(draw, (x, y), prefix, f, fill=35)
        wpre, _ = _measure(draw, prefix, f)
        boxes[key] = draw_field(draw, (x + wpre, y), val, f, fill=35)
        y += 24
    draw_label(draw, (x, y + 6), "DOC-RECORD-END", font("sans_bold", 16), fill=70)
    return boxes


# --------------------------------------------------------------------------
# Degradations.  Bounded so a good OCR pass still wins, but hard enough that
# a careless extractor loses fields or confidence.
# --------------------------------------------------------------------------

def degrade_skew(rng, img):
    """Slight scanner skew: bounded at 0.5 deg so the text stays legible."""
    return img.rotate(rng.uniform(-0.5, 0.5), resample=Image.BILINEAR,
                      fillcolor=247)


def degrade_speckle(rng, img):
    """Scanner dust: isolated single dark pixels.

    Density is the realistic dust rate for a clean scan of a clean page
    (~0.03 % of pixels); denser than this and tesseract starts reading the
    dust as text and interleaving it with the words, which is a broken
    scanner, not an ugly document.
    """
    px = img.load()
    for _ in range(150):
        x, y = rng.randrange(PAGE_W), rng.randrange(PAGE_H)
        px[x, y] = rng.randrange(60, 170)
    return img


def degrade_lowcontrast(rng, img):
    """Faded photocopy: washed out but still well above the paper floor."""
    px = img.load()
    for y in range(PAGE_H):
        for x in range(PAGE_W):
            v = px[x, y]
            px[x, y] = 150 + (v * 70) // 255
    for _ in range(400):
        x, y = rng.randrange(PAGE_W), rng.randrange(PAGE_H)
        px[x, y] = 247
    return img


DEGRADATIONS = {
    "skew": degrade_skew,
    "speckle": degrade_speckle,
    "lowcontrast": degrade_lowcontrast,
}


def page_profile(idx):
    """(is_structured, layout, degradation) for page index idx."""
    if idx < 4:
        return True, None, None
    layouts = ("three_block", "wide_table", "center_card")
    degs = ("skew", "speckle", "lowcontrast")
    k = idx - 4
    return False, layouts[k % 3], degs[(k // 3) % 3]


# --------------------------------------------------------------------------

def render_page(rec, idx):
    structured, layout, deg = page_profile(idx)
    img = Image.new("L", (PAGE_W, PAGE_H), 247)
    draw = ImageDraw.Draw(img)
    boxes = {}
    if structured:
        layout_structured(draw, rec, boxes)
    else:
        {"three_block": layout_three_block,
         "wide_table": layout_wide_table,
         "center_card": layout_center_card}[layout](draw, rec, boxes)
    if deg is not None:
        # Degradation gets its own stream so changing one profile does not
        # move the pixels of another page.
        img = DEGRADATIONS[deg](random.Random(9000 + idx), img)
    return img, boxes, ("structured" if structured else layout), deg


def field_truth(rec, boxes):
    """The answer key for one page, from the generator's own bookkeeping."""
    if rec["date_bad"]:
        return {"page_id": rec["page_id"], "status": "quarantine",
                "reason_code": "MALFORMED_FIELD",
                "detail": "date field prints 'SEE ATTACHED', not a date"}
    return {
        "page_id": rec["page_id"], "status": "ok",
        "fields": {
            "vendor": {"value": rec["vendor"], "bbox": boxes["vendor"]},
            "invoice_no": {"value": rec["invoice_no"], "bbox": boxes["invoice_no"]},
            "date": {"value": rec["date"], "bbox": boxes["date"]},
            "total": {"value": cents_str(rec["total"]), "bbox": boxes["total"]},
        },
    }


def generate(seed, out_dir):
    rng = random.Random(seed)
    recs = build_records(rng)
    pages_dir = os.path.join(out_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    truth = {"seed": seed, "page_width": PAGE_W, "page_height": PAGE_H,
             "pages": []}
    index = []
    for idx, rec in enumerate(recs):
        img, boxes, layout, deg = render_page(rec, idx)
        name = "p%03d.png" % idx
        path = os.path.join(pages_dir, name)
        img.save(path, format="PNG", optimize=True)
        index.append({"page_id": rec["page_id"], "file": name,
                      "width": PAGE_W, "height": PAGE_H})
        t = field_truth(rec, boxes)
        t["layout"] = layout
        t["degradation"] = deg
        t["sha256"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        truth["pages"].append(t)
    with open(os.path.join(pages_dir, "pages.json"), "w") as f:
        json.dump({"pages": index}, f, indent=2)
        f.write("\n")
    return truth


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--truth", default=None,
                    help="where to write truth.json (default: <out>/../truth.json)")
    args = ap.parse_args(argv)

    decimal.getcontext().prec = 28
    truth = generate(args.seed, args.out)
    truth_path = args.truth or os.path.join(args.out, "truth.json")
    with open(truth_path, "w") as f:
        json.dump(truth, f, indent=2)
        f.write("\n")
    n_q = sum(1 for p in truth["pages"] if p["status"] == "quarantine")
    print("[fixtures] %d pages -> %s" % (len(truth["pages"]), args.out))
    print("[fixtures] truth  -> %s (%d already-quarantined)"
          % (truth_path, n_q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
