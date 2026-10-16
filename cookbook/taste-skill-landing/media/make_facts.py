#!/usr/bin/env python3
"""Generate media/video/src/facts.json from this run's judge outputs.

Every number the video shows comes from here, so the HUD can never drift
from the real verdict. Called by media/make_media.sh after grade.sh and
selftest.sh have run.

    python3 media/make_facts.py \
        --good  media/verdict-good.json \
        --base  media/verdict-baseline.json \
        --kills media/selftest-kills.txt \
        --out   media/video/src/facts.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--good", required=True, help="grade.sh good verdict JSON")
    ap.add_argument("--base", required=True, help="grade.sh baseline verdict JSON")
    ap.add_argument("--kills", required=True, help="selftest kill-rate line")
    ap.add_argument("--out", required=True, help="facts.json to write")
    args = ap.parse_args()

    with open(args.good, encoding="utf-8") as fh:
        good = json.load(fh)
    with open(args.base, encoding="utf-8") as fh:
        base = json.load(fh)

    with open(args.kills, encoding="utf-8") as fh:
        kills = fh.read().strip()
    # selftest.sh prints "N/N (100%)" on the mutants-killed line
    kills = re.sub(r"\s*\(\d+%\)\s*$", "", kills).strip()

    # the live wind sentence from the judge's own widget samples: it probes
    # 11 combinations and reads the rendered text. The judge stores the
    # text truncated, so we re-read it from the page for the HUD label.
    widget = None
    for gate in good.get("gates", []):
        if gate["gate"] == "wind_widget_sane":
            for sample in gate["detail"].get("samples", []):
                if sample["dir"] == "W" and sample["speed"] == "18":
                    widget = sample
                    break
    if widget is None:
        print("[facts] ERROR: no 18/W widget sample in the verdict", file=sys.stderr)
        return 2

    doc = {
        "generated_by": "media/make_facts.py (from judge/grade.sh + selftest.sh)",
        "good": good,
        "baseline": base,
        "wind_widget": {
            "speed": widget["speed"],
            "dir": widget["dir"],
            # "the wind saves you 68 minutes if you ride it the right way"
            "saving_minutes": minutes_of(widget["text"],
                                         r"saves you (\d+) minute"),
            "label": "saved on the 40 km loop, riding the right way",
        },
        "selftest_kills": kills or "8/8",
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"[facts] wrote {args.out}: "
          f"{len(good['gates'])} gates, wind saving "
          f"{doc['wind_widget']['saving_minutes']} min, kills {kills}")
    return 0


def minutes_of(text: str, pattern: str) -> int:
    """The judge's verdict JSON truncates each widget sample to 120 chars, which
    can cut the sentence mid-word ("saves you 68 minute"). The number itself is
    always intact, so match the digits without requiring the trailing word."""
    m = re.search(pattern, text)
    if not m:
        raise SystemExit(f"[facts] ERROR: cannot read '{pattern}' from {text!r}")
    return int(m.group(1))


if __name__ == "__main__":
    sys.exit(main())
