#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Each mutant is the good artifact with exactly one scripted edit; the
self-test expects every mutant to fail at least one gate (SPEC.md). The
cheats named in the demo brief are all covered: bicubic passed off as model
output, dropped frames, wrong scale, channel swap, temporal frame reorder,
plus identity-init, pass-through, and a muted model.
"""

import os
import sys

# (name, must-exist-literal, replacement)
EDIT = [
    ("bicubic_as_model",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0)",
     "    return torch.nn.functional.interpolate(frames, scale_factor=4,\n"
     "        mode='bicubic', antialias=True)"),
    ("drop_frames",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0)",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0)[::2]"),
    ("wrong_scale",
     "        feat = self.act(self.conv_up1(F.interpolate(feat, scale_factor=2,\n"
     "                                                    mode=\"nearest\")))\n"
     "        feat = self.act(self.conv_up2(F.interpolate(feat, scale_factor=2,\n"
     "                                                    mode=\"nearest\")))",
     "        feat = self.act(self.conv_up1(F.interpolate(feat, scale_factor=2,\n"
     "                                                    mode=\"nearest\")))"),
    ("channel_swap",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0)",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0)[:, [2, 1, 0], :, :]"),
    ("frame_reorder",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0)",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0).flip(0)"),
    ("identity_model",
     "    params = checkpoint.get(\"params_ema\", checkpoint)\n"
     "    model.load_state_dict(params, strict=True)",
     "    params = checkpoint.get(\"params_ema\", checkpoint)\n"
     "    pass  # load_state_dict skipped: identity-init cheat"),
    ("pass_through",
     "    with torch.no_grad():\n        out = model(frames)\n    return out.clamp(0.0, 1.0)",
     "    return frames.repeat_interleave(4, dim=2).repeat_interleave(4, dim=3)"),
    ("mute_model",
     "        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))\n"
     "        return x5 * 0.2 + x",
     "        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))\n"
     "        return x  # RRDB body muted to a no-op"),
]


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    good = open(os.path.join(src_dir, "upscale.py")).read()
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, old, new in EDIT:
        if old not in good:
            raise SystemExit(f"mutant {name}: edit anchor not found in good artifact")
        mutant = good.replace(old, new, 1)
        if mutant == good:
            raise SystemExit(f"mutant {name}: edit produced no change")
        path = os.path.join(out_dir, name + ".py")
        with open(path, "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
