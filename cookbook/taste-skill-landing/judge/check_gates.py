#!/usr/bin/env python3
"""check_gates.py — the taste-skill landing judge.

Loads the artifact in pinned headless Chromium (Playwright 1.63.0) at 375,
768 and 1440 px and measures every gate of SPEC.md from the live DOM:

  gate 1  clean load        zero console errors, zero failed/blocked/4xx
                            requests, zero non-localhost requests
  gate 2  no overflow       scrollWidth <= clientWidth + 1 at each width
  gate 3  WCAG AA contrast  computed color vs nearest background, 4.5:1 /
                            3:1 large text (skill references/colour.md §8)
  gate 4  brief             every brief.md section present + brand ground
  gate 5  taste rules       14 sub-checks, each citing the skill rule
  gate 6  axe-core          zero critical/serious violations at 1440/375
  gate 7  wind widget       the hero widget's "N minutes" figures are all
                            non-negative integers at every slider position
                            and direction probed

Writes one JSON verdict; exit 0 only if every gate passes. Nothing in the
verdict depends on wall time or environment: two runs at the same seed are
byte-identical (grade.sh adds only the `timing` key afterwards).
"""

import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

WIDTHS = [1440, 768, 375]
TAP_WIDTH = 375
GENERIC_OR_WEBSAFE = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded",
    "Times", "Times New Roman", "Arial", "Helvetica", "Verdana", "Tahoma",
    "Trebuchet MS", "Courier", "Courier New", "Georgia", "Impact",
    "Comic Sans MS",
}
MONO_HINTS = ("mono", "courier", "consol")  # monospace family detection

# DOM collector: everything the Python side needs, measured in one pass.
COLLECT_JS = r"""
() => {
  const px = v => parseFloat(v) || 0;
  const rgba = s => {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return p; // [r, g, b, a?]
  };
  function nearestBg(el) {
    let n = el;
    while (n) {
      const c = rgba(getComputedStyle(n).backgroundColor);
      if (c && (c.length < 4 || c[3] > 0)) return c;
      n = n.parentElement;
    }
    return [244, 241, 234, 1]; // page ground fallback (checked separately)
  }
  function lineCount(el) {
    const r = document.createRange();
    r.selectNodeContents(el);
    const rects = [...r.getClientRects()].filter(x => x.height > 4 && x.width > 2);
    return new Set(rects.map(x => Math.round(x.top / 4))).size;
  }
  const res = {texts: [], headings: [], imgs: [], targets: [], spacings: [],
               borders: [], shadows: [], gradients: [], families: [],
               sizes1440: [], ids: [], bodyBg: '', overflow: null, fontCheck: {}};
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (!el.getClientRects().length) continue;
    const rect = el.getBoundingClientRect();

    // -- own text -----------------------------------------------------
    let own = '';
    for (const n of el.childNodes) if (n.nodeType === 3) own += n.data;
    own = own.replace(/\s+/g, ' ').trim();
    const isHeading = /^H[1-6]$/.test(el.tagName);
    if (own) {
      const bg = nearestBg(el);
      const fam = cs.fontFamily.split(',')[0].replace(/["']/g, '').trim();
      res.texts.push({
        tag: el.tagName, id: el.id || '', text: own.slice(0, 120), len: own.length,
        color: cs.color, bg: `rgb(${bg[0]}, ${bg[1]}, ${bg[2]})`,
        size: cs.fontSize, weight: cs.fontWeight, family: fam,
        code: !!el.closest('pre, code, [data-ui]'),
      });
      res.families.push(fam);
      if (window.__W === 1440) res.sizes1440.push(Math.round(parseFloat(cs.fontSize) * 10) / 10);
    }
    if (isHeading) {
      res.headings.push({tag: el.tagName, text: (el.textContent || '').trim()
        .replace(/\s+/g, ' ').slice(0, 80), lines: lineCount(el)});
    }

    // -- spacing (gate 5.4): padding + gap on all, margin on sections ---
    const sp = [];
    for (const k of ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft']) {
      const v = Math.round(px(cs[k]));
      if (v) sp.push([el.tagName + '.' + k, v]);
    }
    for (const k of ['rowGap', 'columnGap']) {
      const raw = cs[k];
      if (raw && raw !== 'normal') {
        const v = Math.round(px(raw));
        if (v) sp.push([el.tagName + '.' + k, v]);
      }
    }
    if (el.tagName === 'SECTION') {
      for (const k of ['marginTop', 'marginBottom']) {
        const v = Math.round(px(cs[k]));
        if (v) sp.push(['section.' + k, v]);
      }
    }
    if (sp.length) res.spacings.push(...sp);

    // -- thin rules (5.9) ----------------------------------------------
    for (const k of ['borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth']) {
      const v = px(cs[k]);
      if (v && !el.closest('pre, code, input, select, textarea, table, [data-ui]')) {
        res.borders.push([el.tagName + '.' + k, v]);
      }
    }

    // -- shadows (5.8) ---------------------------------------------------
    if (cs.boxShadow !== 'none' || cs.textShadow !== 'none') {
      res.shadows.push(el.tagName + (el.id ? '#' + el.id : ''));
    }

    // -- gradients (5.7) -------------------------------------------------
    const bgis = [cs.backgroundImage, cs.borderImageSource, cs.maskImage]
      .filter(v => v && v !== 'none');
    if (bgis.some(v => v.includes('gradient('))) {
      res.gradients.push(el.tagName + (el.id ? '#' + el.id : ''));
    }

    // -- interactive targets (5.6) ---------------------------------------
    if (el.matches('a, button, input, select, label, [role="button"]')
        && rect.width > 0 && rect.height > 0) {
      res.targets.push({tag: el.tagName, text: (el.textContent || el.getAttribute('name') || '')
        .trim().slice(0, 40), w: Math.round(rect.width * 10) / 10,
        h: Math.round(rect.height * 10) / 10});
    }
  }

  for (const im of document.images) {
    res.imgs.push({src: im.getAttribute('src') || '', alt: im.hasAttribute('alt')
      ? (im.getAttribute('alt') || '') : null, ok: im.naturalWidth > 0});
  }

  const de = document.documentElement;
  for (const el of document.querySelectorAll('[id]')) {
    const h = el.querySelector('h1, h2, h3');
    res.ids.push({id: el.id,
      heading: h ? (h.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80) : ''});
  }
  res.overflow = {scroll: de.scrollWidth, client: de.clientWidth};
  res.bodyBg = getComputedStyle(document.body).backgroundColor;
  for (const f of new Set(res.families)) {
    res.fontCheck[f] = document.fonts.check('16px "' + f + '"');
  }
  return res;
}
"""

# Wind-widget probe: read the rendered #wind-result text at the default
# slider position and two others, then at every direction option, and
# extract every "N minutes" figure (NaN/Infinity serialise as null).
# Returns {present, samples:[{speed, dir, text, minutes}]}.
WIND_JS = r"""
async () => {
  const speed = document.getElementById('wind-speed');
  const dir = document.getElementById('wind-dir');
  const out = document.getElementById('wind-result');
  if (!speed || !out) return {present: false, samples: []};
  const read = () => {
    const text = out.textContent || '';
    const mins = [...text.matchAll(/(-?\d+|NaN|Infinity)\s*minutes/g)]
      .map(m => m[1] === 'NaN' || m[1] === 'Infinity'
                ? NaN : parseInt(m[1], 10));
    return {speed: speed.value, dir: dir ? dir.value : '',
            text: text, minutes: mins};
  };
  const set = (el, v) => {
    el.value = v;
    el.dispatchEvent(new Event('input', {bubbles: true}));
  };
  const home = speed.value;
  const samples = [read()];                  // default slider position
  for (const v of [speed.min, speed.max]) {  // two other positions
    set(speed, v);
    samples.push(read());
  }
  set(speed, home);                          // back to default speed
  if (dir) {                                 // every compass direction
    for (const o of dir.options) {
      set(dir, o.value);
      samples.push(read());
    }
  }
  return {present: true, samples: samples};
}
"""

AXE_RUN_JS = r"""
async () => {
  const r = await window.axe.run(document, {
    resultTypes: ['violations'],
    rules: { 'color-contrast': { enabled: true } },
  });
  return r.violations
    .filter(v => v.impact === 'critical' || v.impact === 'serious')
    .map(v => ({id: v.id, impact: v.impact, help: v.help,
                nodes: v.nodes.map(n => (n.target || []).join(' ')).sort()}))
    .sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
}
"""


# ---------------------------------------------------------------------------
# WCAG contrast, Python side
# ---------------------------------------------------------------------------

def _srgb_to_lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    r, g, b = (_srgb_to_lin(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _parse_rgb(s):
    m = re.match(r"rgba?\(([^)]+)\)", s or "")
    if not m:
        return None
    p = [float(x) for x in m.group(1).split(",")]
    if len(p) >= 3:
        return p
    return None


def _blend(fg, bg):
    if len(fg) > 3 and fg[3] < 1:
        a = fg[3]
        return [fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a),
                fg[2] * a + bg[2] * (1 - a)]
    return fg[:3]


def contrast(fg_s, bg_s):
    fg, bg = _parse_rgb(fg_s), _parse_rgb(bg_s)
    if not fg or not bg:
        return None
    f, b = _blend(fg, bg), _blend(bg, bg)
    l1, l2 = _lum(f), _lum(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def load_brief(path):
    """Extract the fenced ```json block from brief.md."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        raise SystemExit(f"check_gates: no ```json block in {path}")
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("usage: check_gates.py <artifact_dir> <base_url> "
              "[--axe path] [--json out.json] [--shots dir] [--brief path]",
              file=sys.stderr)
        return 2
    artifact, base_url = os.path.abspath(sys.argv[1]), sys.argv[2]
    axe_path = json_out = shots = None
    brief_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brief.md")
    args = sys.argv[3:]
    i = 0
    while i < len(args):
        if args[i] == "--axe" and i + 1 < len(args):
            axe_path, i = args[i + 1], i + 2
        elif args[i] == "--json" and i + 1 < len(args):
            json_out, i = args[i + 1], i + 2
        elif args[i] == "--shots" and i + 1 < len(args):
            shots, i = args[i + 1], i + 2
        elif args[i] == "--brief" and i + 1 < len(args):
            brief_path, i = args[i + 1], i + 2
        else:
            i += 1

    brief = load_brief(brief_path)
    axe_src = None
    if axe_path:
        with open(axe_path, encoding="utf-8") as f:
            axe_src = f.read()

    data = {}   # per-width measurements
    events = {}  # console/network bookkeeping
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for w in WIDTHS:
            ctx = browser.new_context(
                viewport={"width": w, "height": 900},
                reduced_motion="reduce", locale="en-US",
                device_scale_factor=1)
            page = ctx.new_page()
            console_errors, failed, bad_status, external = [], [], [], []
            page.on("console", lambda m: console_errors.append(m.text)
                    if m.type == "error" else None)
            page.on("requestfailed", lambda r: failed.append(r.url))
            page.on("response", lambda r: bad_status.append(
                f"{r.status} {r.url}") if r.status >= 400 else None)
            page.on("request", lambda r: external.append(r.url)
                    if not r.url.startswith("http://127.0.0.1:") else None)
            page.goto(base_url, wait_until="load")
            page.evaluate("() => document.fonts.ready")
            page.wait_for_timeout(400)
            page.evaluate("window.__W = %d" % w)
            data[w] = page.evaluate(COLLECT_JS)
            events[w] = {"console_errors": console_errors,
                         "request_failed": failed,
                         "status_ge_400": bad_status,
                         "external_requests": external}
            if shots:
                os.makedirs(shots, exist_ok=True)
                page.screenshot(path=os.path.join(shots, f"site-{w}.png"),
                                full_page=True)
            if axe_src and w in (1440, TAP_WIDTH):
                page.add_script_tag(content=axe_src)
                data[w]["axe"] = page.evaluate(AXE_RUN_JS)
                if w == 1440:
                    data[w]["wind"] = page.evaluate(WIND_JS)
            ctx.close()
        browser.close()

    gates = []

    def gate(name, passed, detail):
        gates.append({"gate": name, "passed": bool(passed), "detail": detail})

    # -- gate 1: clean load ---------------------------------------------
    g1 = {str(w): events[w] for w in WIDTHS}
    gate("clean_load",
         not any(events[w]["console_errors"] or events[w]["request_failed"]
                 or events[w]["status_ge_400"] or events[w]["external_requests"]
                 for w in WIDTHS),
         g1)

    # -- gate 2: no horizontal overflow -----------------------------------
    ov = {str(w): {"scroll": data[w]["overflow"]["scroll"],
                   "client": data[w]["overflow"]["client"]}
          for w in WIDTHS}
    gate("no_overflow",
         all(data[w]["overflow"]["scroll"] <= data[w]["overflow"]["client"] + 1
             for w in WIDTHS),
         ov)

    # -- gate 3: WCAG AA contrast ----------------------------------------
    worst, fails = None, []
    for w in WIDTHS:
        for t in data[w]["texts"]:
            r = contrast(t["color"], t["bg"])
            if r is None:
                continue
            px = float(t["size"].replace("px", ""))
            bold = str(t["weight"]).isdigit() and int(t["weight"]) >= 700
            large = px >= 24 or (px >= 18.66 and bold)
            need = 3.0 if large else 4.5
            if worst is None or r < worst[0]:
                worst = (r, t["text"][:40], w)
            if r < need - 1e-9:
                fails.append({"width": w, "text": t["text"][:60],
                              "ratio": round(r, 2), "need": need})
    gate("contrast_aa", not fails,
         {"min_ratio": round(worst[0], 2) if worst else None,
          "min_sample": worst[1] if worst else None,
          "failures": fails[:20]})

    # -- gate 4: brief completeness ----------------------------------------
    sec_detail, sec_ok = [], True
    ground_want = brief["colors"]["ground"].lower()
    ground_got = data[1440]["bodyBg"]
    gb = _parse_rgb(ground_got)
    ground_hex = "#%02x%02x%02x" % tuple(int(round(v)) for v in gb[:3]) if gb else None
    for s in brief["sections"]:
        want = s["heading"].lower()
        idrow = next((r for r in data[1440]["ids"] if r["id"] == s["id"]), None)
        heading_ok = bool(idrow and want in idrow["heading"].lower())
        sec_detail.append({"id": s["id"], "heading": s["heading"],
                           "element": bool(idrow), "heading_found": heading_ok})
        if not idrow or not heading_ok:
            sec_ok = False
    gate("brief_sections", sec_ok and (ground_hex == ground_want),
         {"sections": sec_detail, "ground_want": ground_want,
          "ground_got": ground_hex})

    # -- gate 5: taste rules ------------------------------------------------
    sub = []

    def sub_check(n, name, cite, passed, detail):
        sub.append({"n": n, "rule": name, "cite": cite,
                    "passed": bool(passed), "detail": detail})

    t1440 = data[1440]
    t375 = data[TAP_WIDTH]

    fams = sorted({f for w in WIDTHS for f in data[w]["families"]})
    sub_check("5.1", "two_typefaces_max",
              "SKILL.md house rules: 'Two typefaces at most, usually one'",
              len(fams) <= 2, {"families": fams})

    bad_fams = [f for f in fams if f in GENERIC_OR_WEBSAFE]
    unloaded = {f: data[1440]["fontCheck"].get(f) for f in fams
                if data[1440].get("fontCheck", {}).get(f) is not True}
    sub_check("5.2", "no_default_fonts",
              "SKILL.md laws of the craft (type): the dealt type system, loaded",
              not bad_fams and not unloaded,
              {"web_safe_or_generic": bad_fams, "not_loaded": unloaded})

    sizes = sorted(set(t1440["sizes1440"]))
    sub_check("5.3", "type_scale_max_5",
              "SKILL.md laws: 'Five sizes on a page is the ceiling'",
              len(sizes) <= 5, {"sizes_px": sizes})

    bad_sp = [{"el": e, "value": v} for w in (1440, TAP_WIDTH)
              for e, v in data[w]["spacings"] if v % 4 != 0]
    sub_check("5.4", "spacing_scale_4px",
              "SKILL.md laws of space: one grid, one pair of margins; "
              "references/layout.md §2",
              not bad_sp, {"off_scale": bad_sp[:20]})

    bad_alt = [{"src": im["src"], "alt": im["alt"]}
               for w in (1440,) for im in data[w]["imgs"] if im["ok"]
               and (im["alt"] is None or not im["alt"].strip())]
    sub_check("5.5", "alt_text",
              "SKILL.md step 6.7: 'Real links and buttons, visible focus, "
              "alt text'", not bad_alt, {"missing": bad_alt})

    tiny = [{"tag": t["tag"], "text": t["text"], "w": t["w"], "h": t["h"]}
            for t in t375["targets"] if t["w"] < 44 or t["h"] < 44]
    sub_check("5.6", "tap_targets_44px",
              "references/layout.md: 'Touch targets at least 44px high'",
              not tiny, {"under_44px": tiny[:20]})

    sub_check("5.7", "no_gradients",
              "SKILL.md house rules: 'No gradients. Not as backgrounds, not "
              "on buttons, not in text'",
              not any(data[w]["gradients"] for w in WIDTHS),
              {"elements": [g for w in WIDTHS for g in data[w]["gradients"]][:10]})

    sh = sorted({s for w in WIDTHS for s in data[w]["shadows"]})
    sub_check("5.8", "no_shadows_at_rest",
              "SKILL.md house rules: 'No shadows on things at rest'", not sh,
              {"elements": sh[:10]})

    thin = [{"el": e, "width_px": v} for w in (1440, TAP_WIDTH)
            for e, v in data[w]["borders"] if v < 2]
    sub_check("5.9", "no_thin_rules",
              "SKILL.md house rules: 'No hairline dividers, no 1px outlined "
              "boxes' (pre/code, form fields, [data-ui] exempt)",
              not thin, {"under_2px": thin[:20]})

    mono = [t["family"] for w in WIDTHS for t in data[w]["texts"]
            if not t["code"] and any(h in t["family"].lower()
                                     for h in MONO_HINTS)]
    sub_check("5.10", "no_monospace_outside_code",
              "SKILL.md house rules: 'No monospace outside real code blocks'",
              not mono, {"families": sorted(set(mono))})

    idx = [{"width": w, "text": h["text"]}
           for w in WIDTHS for h in data[w]["headings"]
           if re.match(r"^\s*(0\d|[1-9]\d?)[\s.):.-]", h["text"])
           or re.search(r"step \d", h["text"], re.I)]
    sub_check("5.11", "no_index_numbering",
              "SKILL.md house rules: 'No 01 / 02 / 03, no (001), no Step 2'",
              not idx, {"headings": idx[:10]})

    small = [{"width": w, "size": t["size"], "text": t["text"][:50]}
             for w in (1440, TAP_WIDTH) for t in data[w]["texts"]
             if t["len"] >= 60 and float(t["size"].replace("px", "")) < 16]
    sub_check("5.12", "running_text_16px",
              "SKILL.md step 6.6: 'Running text is in the full ink at 16px "
              "or more'", not small, {"under_16px": small[:10]})

    wrapped = [{"width": w, "tag": h["tag"], "text": h["text"], "lines": h["lines"]}
               for w in WIDTHS for h in data[w]["headings"] if h["lines"] > 2]
    sub_check("5.13", "headlines_two_lines",
              "SKILL.md house rules: 'Headlines: two lines or fewer, at "
              "every width'", not wrapped, {"over_two_lines": wrapped[:10]})

    raster = [im for im in data[1440]["imgs"] if im["ok"]
              and re.search(r"\.(png|jpe?g|webp|gif)(\?|$)",
                            im["src"], re.I)]
    sub_check("5.14", "image_floor_4",
              "SKILL.md step 6.4: 'at least four real pictures on the page' "
              "(SVG does not count)",
              len(raster) >= 4, {"raster_images": len(raster)})

    gate("taste_rules", all(s["passed"] for s in sub), sub)

    # -- gate 6: axe-core -------------------------------------------------
    axe = []
    for w in (1440, TAP_WIDTH):
        for v in data[w].get("axe", []):
            axe.append({"width": w, **v})
    gate("axe_a11y", not axe,
         {"critical_or_serious": axe,
          "note": "axe-core 4.10.3, the Lighthouse-accessibility equivalent "
                  "(see RECEIPT.md Deviations)"})

    # -- gate 7: wind widget sanity ---------------------------------------
    # The brief hero asks for "the honest time saved": the rendered widget
    # text is read at the default slider position, at the slider's min and
    # max, and at every direction option. Every "N minutes" figure must be
    # an integer count in [0, 600] — a negative or NaN saving, or a widget
    # that renders no figure at all, fails the gate.
    wind = data[1440].get("wind", {"present": False, "samples": []})
    if not wind["present"]:
        wind_ok, wind_bad, wind_note = True, [], "no wind widget on the page"
    else:
        wind_bad = [{"sample": s["text"][:120], "minutes": s["minutes"]}
                    for s in wind["samples"]
                    if not s["minutes"]
                    or any(not isinstance(m, int) or m < 0 or m > 600
                           for m in s["minutes"])]
        wind_ok = not wind_bad
        wind_note = None
    gate("wind_widget_sane", wind_ok,
         {"note": wind_note,
          "samples": [{"speed": s["speed"], "dir": s.get("dir", ""),
                       "text": s["text"][:120]}
                      for s in wind["samples"]],
          "bad": wind_bad})

    verdict = {
        "artifact": os.path.basename(artifact.rstrip("/")),
        "all_gates_passed": all(g["passed"] for g in gates),
        "gates": gates,
    }
    out = json.dumps(verdict, indent=2, sort_keys=False)
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    print(out)
    return 0 if verdict["all_gates_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
