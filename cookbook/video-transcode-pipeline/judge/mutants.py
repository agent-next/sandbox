#!/usr/bin/env python3
"""Generate the known-bad artifacts the self-test grades.

Each mutant is the known-good pipeline.sh with exactly one edit, so a mutant
that survives points at a gate that is not measuring what it claims to.

    mutants.py <out_dir>

Writes <out_dir>/<name>/pipeline.sh for every mutant and prints one line per
mutant naming the edit. The edits are literal string substitutions; a
substitution that does not apply is an error, not a silently missing mutant.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOOD = HERE.parent / "examples" / "good" / "pipeline.sh"

# A single edit of pipeline.sh, plus the mutation it produces in the output.
# The 360p playlist marker the dropped-segment mutant edits.
DROPPED = """
# mutant: drop a middle segment from the 360p playlist, keep every .ts file
sed -i '/^seg-004\\.ts$/d' "$OUT/360p/index.m3u8"
"""

MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "wrong-resolution",
        "720p rendition scaled to 1280x960 instead of 1280x720",
        'encode 1280 720 "$AUDIO_720" 720p',
        'encode 1280 960 "$AUDIO_720" 720p',
    ),
    (
        "truncated",
        "renditions cut to 10 s (-t 10 on the input)",
        '    ffmpeg -v error -y -i "$INPUT" \\',
        '    ffmpeg -v error -y -t 10 -i "$INPUT" \\',
    ),
    (
        "dropped-segment",
        "seg-004.ts removed from the 360p playlist (the .ts files stay)",
        "# --- report ---",
        DROPPED.strip() + "\n\n# --- report ---",
    ),
    (
        "empty-captions",
        "captions.vtt replaced by WEBVTT plus one empty cue",
        'cp "$WORK/captions.vtt" "$OUT/captions.vtt"',
        "printf 'WEBVTT\\n\\n00:00:00.000 --> 00:00:01.000\\n\\n' > \"$OUT/captions.vtt\"",
    ),
    (
        "wrong-keyframe",
        "keyframe interval 8 s (KEYINT 192) instead of 4 s",
        "KEYINT=96                 # 4 s at 24 fps",
        "KEYINT=192                # mutant: 8 s at 24 fps",
    ),
    (
        "blank-poster",
        "poster.png replaced by a solid black frame",
        'ffmpeg -v error -y -ss "$POSTER_T" -i "$INPUT" -frames:v 1 -pix_fmt rgb24 "$OUT/poster.png"',
        'ffmpeg -v error -y -f lavfi -i "color=c=black:size=640x360:duration=1" '
        '-frames:v 1 -pix_fmt rgb24 "$OUT/poster.png"',
    ),
    (
        "silent-renditions",
        "renditions carry no audio stream (-an)",
        '-c:a aac -b:a "$abr" -ac 2 -ar 48000',
        "-an",
    ),
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    if not GOOD.is_file():
        print(f"mutants: known-good {GOOD} not found", file=sys.stderr)
        return 1
    source = GOOD.read_text()
    out.mkdir(parents=True, exist_ok=True)
    for name, description, old, new in MUTANTS:
        if source.count(old) != 1:
            print(f"mutants: edit for {name!r} matches {source.count(old)} times, "
                  f"expected exactly 1 -- the good pipeline changed", file=sys.stderr)
            return 1
        target = out / name
        target.mkdir(parents=True, exist_ok=True)
        path = target / "pipeline.sh"
        path.write_text(source.replace(old, new))
        path.chmod(0o755)
        # The pipeline resolves its fixtures relative to its own directory.
        fixtures = target / "fixtures"
        if fixtures.is_symlink() or fixtures.exists():
            fixtures.unlink() if fixtures.is_symlink() else shutil.rmtree(fixtures)
        shutil.copytree(HERE.parent / "fixtures", fixtures)
        print(f"mutants: {name}  edit: {description}")
    print(f"mutants: wrote {len(MUTANTS)} mutants to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
