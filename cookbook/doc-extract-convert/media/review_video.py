#!/usr/bin/env python3
"""Blind review panel for media/demo.mp4 (cookbook/DEMO-STANDARD.md).

The standard requires *two vision models from different families* to judge
`media/demo.mp4` blind -- no README, no repo, no knowledge of what the demo
is meant to show -- with the prompt in `cookbook/tools/video_review_prompt.md`.
Their raw JSON replies are stored verbatim in `media/REVIEW.json`.

This tool has two halves:

  --dump            write evenly spaced stills to a directory, one per
                    second-ish slice a judge is asked to look at.  The judge
                    reads those (consecutive pairs carry the motion), not the
                    video, so any vision-capable agent can take part.
  --record A.json   take two reviewers' raw JSON verdicts (each produced
                    from the prompt alone) and write media/REVIEW.json with
                    both verdicts verbatim plus the panel's pass rule.

Run the panel with the prompt text alone; `media/REVIEW.json` records what
each judge answered, without editing.

    python3 media/review_video.py --dump /tmp/blind
    <a vision model, given /tmp/blind/* and the review prompt, replies JSON>
    python3 media/review_video.py --record judge-a.json judge-b.json
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(HERE, "demo.mp4")
PROMPT = os.path.join(HERE, "..", "..", "tools", "video_review_prompt.md")
REVIEW = os.path.join(HERE, "REVIEW.json")

# from the standard: both judges must reach these on 1-10 scores
MIN_VISUAL = 8
MIN_WOW = 7
MIN_CLARITY = 7
MAX_PAYOFF_S = 2

REQUIRED_FIELDS = (
    "frame0_what", "hook_type", "payoff_visible_by_s", "on_screen_text",
    "understandable_muted", "visual_quality_1_10", "wow_1_10",
    "clarity_1_10", "why", "fixes",
)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("review_video: %s failed: %s"
                 % (cmd[0], (p.stderr or p.stdout).strip()[:400]))
    return p.stdout


def duration():
    return float(run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                      "-show_entries", "format=duration", "-of",
                      "csv=p=0", VIDEO]).strip())


def dump(count, out_dir):
    """Still frames, evenly spaced across the whole clip."""
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    d = duration()
    # inclusive of both ends: the t=0 still is the evidence for
    # payoff_visible_by_s (a judge with no opening frame cannot credit a
    # sub-2 s payoff), the last is the end card.  A stamp at exactly the
    # duration reads past the last frame and writes nothing, so clamp to
    # one frame inside it.
    last = round(d - 1.0 / 30, 2)
    stamps = [min(round(i * d / (count - 1), 2), last) for i in range(count)]
    for t in stamps:
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%s" % t, "-i",
             VIDEO, "-frames:v", "1", "-update", "1",
             os.path.join(out_dir, "t%.2fs.png" % t)])
    print("review_video: %d stills from %s (%.1f s) -> %s"
          % (len(stamps), VIDEO, d, out_dir))
    return out_dir


def verdict_ok(v):
    """The standard's pass rule for one judge's reply."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in v:
            errors.append("missing %s" % field)
    if errors:
        return errors
    if v["visual_quality_1_10"] < MIN_VISUAL:
        errors.append("visual_quality_1_10 = %s < %d"
                      % (v["visual_quality_1_10"], MIN_VISUAL))
    if v["wow_1_10"] < MIN_WOW:
        errors.append("wow_1_10 = %s < %d" % (v["wow_1_10"], MIN_WOW))
    if v["clarity_1_10"] < MIN_CLARITY:
        errors.append("clarity_1_10 = %s < %d"
                      % (v["clarity_1_10"], MIN_CLARITY))
    payoff = v["payoff_visible_by_s"]
    if payoff is None or payoff > MAX_PAYOFF_S:
        errors.append("payoff_visible_by_s = %s (must be <= %s)"
                      % (payoff, MAX_PAYOFF_S))
    if v["understandable_muted"] is not True:
        errors.append("understandable_muted = %s"
                      % v["understandable_muted"])
    return errors


def record(paths):
    with open(VIDEO, "rb") as f:
        import hashlib
        sha = hashlib.sha256(f.read()).hexdigest()
    judges = []
    for path in paths:
        with open(path) as f:
            raw = f.read()
        v = json.loads(raw)
        judges.append({"verdict": v, "errors": verdict_ok(v),
                       "passed": not verdict_ok(v)})
    panel_pass = all(j["passed"] for j in judges) and len(judges) >= 2
    out = {
        "video": "media/demo.mp4",
        "video_sha256": sha,
        "review_prompt": ("cookbook/tools/video_review_prompt.md, "
                          "given blind: no README, no repo, no context"),
        "stills_seen": sorted(os.path.basename(p) for p in
                              glob.glob("/tmp/blind/t*.png")) or None,
        "panel_passed": panel_pass,
        "thresholds": {"visual_quality_1_10": ">= %d" % MIN_VISUAL,
                       "wow_1_10": ">= %d" % MIN_WOW,
                       "clarity_1_10": ">= %d" % MIN_CLARITY,
                       "payoff_visible_by_s": "<= %s" % MAX_PAYOFF_S,
                       "understandable_muted": True},
        "judges": judges,
    }
    with open(REVIEW, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print("review_video: REVIEW.json written (panel %s)"
          % ("PASS" if panel_pass else "FAIL"))
    for j in judges:
        if j["errors"]:
            print("  judge errors: %s" % "; ".join(j["errors"]))
    return 0 if panel_pass else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dump", metavar="DIR",
                    help="write stills for a blind judge")
    ap.add_argument("--record", nargs="+", metavar="JSON",
                    help="write media/REVIEW.json from judges' raw verdicts")
    ap.add_argument("--still-count", type=int, default=8)
    args = ap.parse_args()
    if args.dump:
        dump(args.still_count, args.dump)
        return 0
    if args.record:
        return record(args.record)
    ap.error("give --dump DIR or --record JSON [JSON ...]")


if __name__ == "__main__":
    sys.exit(main())
