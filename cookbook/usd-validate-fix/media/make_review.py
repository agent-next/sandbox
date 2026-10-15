#!/usr/bin/env python3
"""REVIEW.json -- the two blind judge verdicts on demo.mp4.

DEMO-STANDARD.md: "Two vision models from different families judge
media/demo.mp4 blind -- no README, no repo context -- using
cookbook/tools/video_review_prompt.md, scoring 1-10. Pass = both judges score
visual_quality_1_10 >= 8, wow_1_10 >= 7, clarity_1_10 >= 7, report
payoff_visible_by_s <= 2, and understandable_muted true. Store both raw JSON
verdicts in media/REVIEW.json."

That panel cannot run here: it needs two vision models from different families
answering outside this sandbox, and this environment has no such access. So
this script does NOT invent verdicts -- an invented verdict is a false
acceptance, which is worse than a missing one (LESSONS.md: "A lost reply is
not a confirmation: verify, and report failure instead of claiming success").
It writes the panel's required schema with every judge slot marked
`status: "pending"`, `pass: false`, and the exact reason, so a cold-start
reviewer sees what is missing instead of a green tick that never happened.

Fill it in by running the panel and re-running this script with
--json <from-panel>; the pass flag is then computed from the real verdicts.
"""
import json
import os
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))

PANEL = [
    {"model_family": "CLAUDE", "model": "<model that ran the review>",
     "ran_here": False,
     "why": "no vision-model API access in this sandbox (no ANTHROPIC_API_KEY)"},
    {"model_family": "GEMINI", "model": "<model that ran the review>",
     "ran_here": False,
     "why": "no Google API access in this sandbox (no GEMINI_API_KEY)"},
]

# the exact fields the standard's prompt asks each judge for (see
# cookbook/tools/video_review_prompt.md)
FIELDS = ["frame0_what", "hook_type", "payoff_visible_by_s", "on_screen_text",
          "understandable_muted", "visual_quality_1_10", "wow_1_10",
          "clarity_1_10", "why", "fixes"]


def passthrough(from_panel):
    """Reproduce real panel verdicts and compute `pass` from them."""
    with open(from_panel, encoding="utf-8") as fh:
        raw = json.load(fh)
    keys = list(raw)
    reviewers, families = [], []
    for slot, entry in zip(PANEL, keys):
        verdict = raw[entry]
        missing = [f for f in FIELDS if f not in verdict]
        if missing:
            raise SystemExit("panel verdict from %s is missing %s"
                             % (entry, ", ".join(missing)))
        reviewers.append({"model_family": slot["model_family"],
                          "model": entry, "ran_here": True,
                          "verdict": {f: verdict[f] for f in FIELDS}})
        families.append(slot["model_family"])
    if len(set(families)) < 2:
        raise SystemExit("the panel must use two different model families, "
                         "got %r" % families)
    return reviewers


def empty():
    """The schema with every judge slot pending, and pass computed as false."""
    reviewers = []
    for slot in PANEL:
        reviewers.append({
            "model_family": slot["model_family"],
            "model": slot["model"],
            "ran_here": slot["ran_here"],
            "status": "pending",
            "why_pending": slot["why"],
            "verdict": {f: None for f in FIELDS},
        })
    return reviewers


def main():
    from_panel = None
    if "--json" in sys.argv:
        from_panel = sys.argv[sys.argv.index("--json") + 1]

    if from_panel:
        reviewers = passthrough(from_panel)
        review = {
            "note": "Blind verdicts on media/demo.mp4 from two vision models "
                    "of different families (cookbook/tools/"
                    "video_review_prompt.md), passed through unchanged.",
            "reviewers": reviewers,
            "pass": all_passes(reviewers),
        }
    else:
        reviewers = empty()
        review = {
            "note": "The blind review panel has NOT been run: it requires two "
                    "vision models from different families answering outside "
                    "this sandbox, and no vision-model API access exists "
                    "here. Every judge slot is pending; nothing is invented. "
                    "Pass is false because no judge has scored the video.",
            "panel_required_by": "cookbook/DEMO-STANDARD.md # Review panel",
            "panel_prompt": "cookbook/tools/video_review_prompt.md",
            "pass_rules": {"visual_quality_1_10": ">= 8",
                           "wow_1_10": ">= 7", "clarity_1_10": ">= 7",
                           "payoff_visible_by_s": "<= 2",
                           "understandable_muted": True},
            "reviewers": reviewers,
            "pass": False,
        }

    with open(os.path.join(MEDIA, "REVIEW.json"), "w", encoding="utf-8") as fh:
        json.dump(review, fh, indent=2)
        fh.write("\n")
    if from_panel:
        print("make_review: wrote media/REVIEW.json from the panel verdicts "
              "(pass=%s)" % review["pass"])
    else:
        print("make_review: wrote media/REVIEW.json with the panel PENDING "
              "(pass=false) -- no vision-model access here to run it")


def all_passes(reviewers):
    """Pass only when every reviewer meets every standard's threshold."""
    for r in reviewers:
        v = r["verdict"]
        if not (v["visual_quality_1_10"] >= 8 and v["wow_1_10"] >= 7
                and v["clarity_1_10"] >= 7
                and v["payoff_visible_by_s"] <= 2
                and v["understandable_muted"] is True):
            return False
    return True


if __name__ == "__main__":
    main()
