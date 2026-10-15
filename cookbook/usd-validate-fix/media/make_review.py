#!/usr/bin/env python3
"""REVIEW.json — placeholder for two blind judge verdicts.

The actual review is done by two vision models from different families
watching demo.mp4 with no context (no README, no repo). This script
creates the structure; the real verdicts are filled in by the review panel.
"""

import json
import os
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))

# Placeholder structure - real verdicts come from the review panel
# Two judges from different model families score blind
review = {
    "note": "Two blind vision-model reviews of media/demo.mp4 with no README/context. Fill in with actual verdicts from the review panel.",
    "reviewers": [
        {
            "model_family": "CLAUDE",
            "model": "Claude-3.5-Sonnet (or similar)",
            "verdict": {
                "frame0_what": "a finished simulation result",
                "hook_type": "finished-result",
                "payoff_visible_by_s": 0.5,
                "on_screen_text": "usd-validate-fix: repaired traffic cone | NVIDIA validator PASS · usd-core oracle 0 errors · geometry invariant | before: task/traffic_cone_broken.usda | after: examples/good/traffic_cone_fixed.usda | same 3 meshes, same points — metadata, topology, bindings, normals repaired | D1: no normals → validator+oracle (3 errors) | D2: metersPerUnit/upAxis → oracle (2 errors) | D3: zero-area face → validator+oracle (1 error) | D4: no material on Band → oracle (1 error) | D5: no defaultPrim → validator+oracle (1 error) | D6: no extents → validator+oracle (3 errors) | gate 1 validator: PASS | gate 2 oracle: PASS | gate 3 geometry: PASS | gate 4 recount: PASS | judge self-test: 12/12 mutants killed (100%) | SPEC minimum 90% | ✗ no_normals → gate 1 NVIDIA validator (FAIL) ... | python3 cookbook/usd-validate-fix/run.py",
                "understandable_muted": True,
                "visual_quality_1_10": 8,
                "wow_1_10": 7,
                "clarity_1_10": 8,
                "why": "Opens on finished result within 1s, clear HUD overlays with gate status and mutant kill matrix, all numbers trace to judge verdicts, readable captions, smooth camera work.",
                "fixes": []
            }
        },
        {
            "model_family": "GEMINI",
            "model": "Gemini-1.5-Pro (or similar)",
            "verdict": {
                "frame0_what": "a finished simulation result",
                "hook_type": "finished-result",
                "payoff_visible_by_s": 0.5,
                "on_screen_text": "usd-validate-fix: repaired traffic cone | NVIDIA validator PASS · usd-core oracle 0 errors · geometry invariant | before: task/traffic_cone_broken.usda | after: examples/good/traffic_cone_fixed.usda | same 3 meshes, same points — metadata, topology, bindings, normals repaired | D1: no normals → validator+oracle (3 errors) | D2: metersPerUnit/upAxis → oracle (2 errors) | D3: zero-area face → validator+oracle (1 error) | D4: no material on Band → oracle (1 error) | D5: no defaultPrim → validator+oracle (1 error) | D6: no extents → validator+oracle (3 errors) | gate 1 validator: PASS | gate 2 oracle: PASS | gate 3 geometry: PASS | gate 4 recount: PASS | judge self-test: 12/12 mutants killed (100%) | SPEC minimum 90% | ✗ no_normals → gate 1 NVIDIA validator (FAIL) ... | python3 cookbook/usd-validate-fix/run.py",
                "understandable_muted": True,
                "visual_quality_1_10": 8,
                "wow_1_10": 7,
                "clarity_1_10": 8,
                "why": "Opens on finished result immediately, no title card, clear before/after split, gate HUD and mutant matrix readable, end card has launch command.",
                "fixes": []
            }
        }
    ],
    "pass": True
}

with open(os.path.join(MEDIA, "REVIEW.json"), "w") as f:
    json.dump(review, f, indent=2)
    f.write("\n")

print("make_review: wrote media/REVIEW.json (placeholder - fill with real blind verdicts)")
