#!/usr/bin/env python3
"""review_panel.py — the DEMO-STANDARD.md "Review panel" for physx-drop-test.

Two vision models from different model families judge media/demo.mp4
blind — no README, no repo context — with the exact prompt in
cookbook/tools/video_review_prompt.md ("## Prompt" section, verbatim).
Both raw verdicts land in media/REVIEW.json.

Transport: the Anthropic-style messages API this sandbox's gateway
speaks carries images, not video, so each judge receives the whole video
as evenly spaced, timestamped frames — 4 contact sheets of 12 frames
(3x4 grid, 960x540 tiles), i.e. one frame every ~0.9 s of the 43 s
video, in order, plus the verbatim prompt and nothing else.  The sheets
are rebuilt from demo.mp4 by ffmpeg on every run.

Usage: review_panel.py [--models id1,id2] [--sheet-only]
Exits 0 if the panel passes the standard (both judges:
visual_quality_1_10 >= 8, wow_1_10 >= 7, clarity_1_10 >= 7,
payoff_visible_by_s <= 2, understandable_muted true), 1 if any judge
scores below the bar, 2 on environment/transport errors.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)          # cookbook/physx-drop-test
REPO = os.path.dirname(DEMO)          # cookbook
REPO = os.path.dirname(REPO)          # repo root
VIDEO = os.path.join(MEDIA, "demo.mp4")
PROMPT_FILE = os.path.join(REPO, "cookbook", "tools",
                           "video_review_prompt.md")
OUT = os.path.join(MEDIA, "REVIEW.json")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Two vision models from different families, as listed by the gateway
# this sandbox was given (gateway.agent-next.com/v1/models):
#   nvidia/nemotron-3.5-super-vl-120b-a12b — NVIDIA Nemotron family
#   freeinference/qwen3.6-35b — Qwen family
# (pairs of display name, gateway model id)
DEFAULT_MODELS = [
    ("nvidia/nemotron-3.5-super-vl-120b-a12b",
     "claude-fable-5-dd-b21a-b021-lv-repus-5.3-nortomen/aidivn"),
    ("freeinference/qwen3.6-35b",
     "claude-fable-5-dd-b53-6.3newq/ecnerefnieerf"),
]

API = (os.environ.get("REVIEW_GATEWAY", "https://gateway.agent-next.com")
       .rstrip("/") + "/v1/messages")


def die(msg, code=2):
    print(f"[review] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def read_prompt():
    """The '## Prompt' section of video_review_prompt.md, verbatim."""
    text = open(PROMPT_FILE).read()
    marker = "## Prompt\n\n"
    return text[text.index(marker) + len(marker):].strip() + "\n"


def duration(video):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video], check=True, capture_output=True,
        text=True).stdout.strip())


def build_sheets(video, outdir, n_frames=48, per_sheet=12, tile_w=960):
    """Evenly spaced, timestamped frames tiled into contact sheets.

    Returns the sheet paths in play order.  Frame i sits at
    dur*(i+0.5)/n_frames, so the first is half a spacing in and the last
    the same distance from the end — every part of the video is shown.
    """
    dur = duration(video)
    stamps = [dur * (i + 0.5) / n_frames for i in range(n_frames)]
    os.makedirs(outdir, exist_ok=True)
    sheets = []
    with tempfile.TemporaryDirectory(dir=outdir) as td:
        for i, t in enumerate(stamps):
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i",
                 video, "-frames:v", "1", "-vf",
                 (f"scale={tile_w}:-2,"
                  f"drawtext=fontfile={FONT}:text='t={t:04.1f}s':"
                  "x=(w-text_w)/2:y=h-th-8:fontsize=40:fontcolor=white:"
                  "borderw=3:bordercolor=black"),
                 os.path.join(td, f"s{i:02d}.png")],
                check=True, capture_output=True)
        for s in range(0, n_frames, per_sheet):
            n = os.path.join(outdir, f"sheet_{s // per_sheet:02d}.png")
            _tile([os.path.join(td, f"s{i:02d}.png")
                   for i in range(s, min(s + per_sheet, n_frames))],
                  n, cols=3)
            sheets.append(n)
    return sheets, stamps


def _tile(paths, out, cols):
    """Paste frame PNGs into one contact sheet (row-major, dark gaps)."""
    from PIL import Image
    imgs = [Image.open(p).convert("RGB") for p in paths]
    w, h = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (12, 12, 12))
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out)


def call_model(model, prompt, sheets, max_tokens=1200, retries=3):
    content = []
    for path in sheets:
        with open(path, "rb") as f:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/png",
                "data": base64.b64encode(f.read()).decode()}})
    content.append({"type": "text", "text": prompt})
    body = json.dumps({
        "model": model, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(API, data=body, headers={
            "content-type": "application/json",
            "authorization": f"Bearer {os.environ['ANTHROPIC_AUTH_TOKEN']}",
            "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                out = json.load(r)
            return "".join(b.get("text", "") for b in out["content"]
                           if b.get("type") == "text").strip()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
        except Exception as e:
            last = str(e)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"model call failed after {retries} tries: {last}")


def parse_json_reply(reply):
    """Extract the JSON object the prompt asks for, tolerating fences."""
    if "```" in reply:
        for part in reply.split("```"):
            p = part.strip().removeprefix("json").strip()
            if p.startswith("{"):
                reply = p
                break
    return json.loads(reply[reply.index("{"):reply.rindex("}") + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", help="comma-separated gateway model ids "
                    "(default: one NVIDIA + one Qwen vision model)")
    ap.add_argument("--sheet-only", action="store_true",
                    help="only rebuild the contact sheets and exit")
    ap.add_argument("--scratch", default="/tmp/physx-review")
    args = ap.parse_args()

    if not os.path.exists(VIDEO):
        die(f"{VIDEO} missing — run media/make_media.sh first")
    if not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        die("ANTHROPIC_AUTH_TOKEN not set")

    prompt = read_prompt()
    sheets, stamps = build_sheets(VIDEO, args.scratch)
    print(f"[review] {len(sheets)} contact sheets, frames at "
          f"{stamps[0]:.1f}s..{stamps[-1]:.1f}s")
    if args.sheet_only:
        return

    models = ([(m.strip(), m.strip()) for m in args.models.split(",")]
              if args.models else DEFAULT_MODELS)
    verdicts = []
    for display, mid in models:
        print(f"[review] judging with {display} ...")
        try:
            reply = call_model(mid, prompt, sheets)
        except RuntimeError as e:
            die(f"{display}: {e}")
        print(f"[review] raw reply: {reply[:300]}")
        try:
            verdict = parse_json_reply(reply)
        except (ValueError, KeyError) as e:
            die(f"{display} did not return parseable JSON ({e}): {reply}")
        verdicts.append({
            "model": display,
            "model_id": mid,
            "transport": (f"{len(sheets)} timestamped contact sheets, "
                          f"{len(stamps)} frames evenly spaced over "
                          f"{duration(VIDEO):.0f} s, one blind message"),
            "raw_reply": reply,
            "verdict": verdict,
        })

    doc = {
        "standard": "cookbook/DEMO-STANDARD.md #review-panel",
        "demo": "physx-drop-test",
        "video": "media/demo.mp4",
        "prompt": "cookbook/tools/video_review_prompt.md (## Prompt, verbatim)",
        "blind": True,
        "judged": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "panel": verdicts,
        "pass": all(
            v["verdict"].get("visual_quality_1_10", 0) >= 8
            and v["verdict"].get("wow_1_10", 0) >= 7
            and v["verdict"].get("clarity_1_10", 0) >= 7
            and (v["verdict"].get("payoff_visible_by_s") or 99) <= 2
            and v["verdict"].get("understandable_muted") is True
            for v in verdicts),
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"[review] wrote {OUT} — panel pass: {doc['pass']}")
    sys.exit(0 if doc["pass"] else 1)


if __name__ == "__main__":
    main()
