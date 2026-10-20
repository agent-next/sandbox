"""Tests for cookbook/tools/video_gate.py.

Every fixture is generated with ffmpeg's lavfi sources inside the test run —
no binary is ever committed. The recipes:

* bars/colour segments are static; `testsrc2` moves continuously
  (frame-to-frame YDIF ~1.9); hard cuts between segments score ~0.7 in
  select='gt(scene,0.3)' and are counted; solid colours score 0 cuts.
  `testsrc2` with negate or hue+vflip is a different-looking moving shot, so
  cuts between the three variants count too.
* the passing recipe is moving shots cut every few seconds, ending on a
  static SMPTE-bars end card; each defect below changes exactly one property
  of it. The slideshow defect is the same cut rhythm built from still frames.

Run:  pytest -q -s cookbook/tools     (from the repo root; -s shows the
baseline table for the committed demo.mp4 files)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video_gate  # noqa: E402

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[1]
RATE = 30
HD = "1920x1080"


def _encode(
    out: Path,
    segments: list[tuple[str, str | None]],
    size: str = HD,
    crf: int = 34,  # moving testsrc2 shots need it to stay under 8 MiB
    faststart: bool = True,
    audio: bool = False,
):
    """Concat lavfi segments into one H.264/yuv420p mp4.

    segments: (lavfi source expression, optional pre-concat filter or None).
    """
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for src, _ in segments:
        cmd += ["-f", "lavfi", "-i", src]
    if audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    chains = []
    for i, (_, vf) in enumerate(segments):
        chains.append(f"[{i}:v]{vf}[v{i}]" if vf else f"[{i}:v]null[v{i}]")
    if len(segments) > 1:
        inputs = "".join(f"[v{i}]" for i in range(len(segments)))
        graph = ";".join(chains) + f";{inputs}concat=n={len(segments)}:v=1:a=0[o]"
    else:
        graph = ";".join(chains) + ";[v0]null[o]"
    cmd += ["-filter_complex", graph, "-map", "[o]"]
    if audio:
        cmd += ["-map", f"{len(segments)}:a", "-c:a", "aac", "-shortest"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
    ]
    if faststart:
        cmd += ["-movflags", "+faststart"]
    cmd += [str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"fixture encode failed: {proc.stderr}"
    return out


def _bars(pattern: str, seconds: float, size: str = HD) -> str:
    return f"{pattern}=duration={seconds}:size={size}:rate={RATE}"


def _color(hexcolor: str, seconds: float, size: str = HD) -> str:
    return f"color=c={hexcolor}:duration={seconds}:size={size}:rate={RATE}"


MOVING_LOOKS = [None, "negate", "hue=h=120,vflip"]


def passing_segments(size: str = HD, first=None, tail=None):
    """The baseline recipe: moving shots cut every few seconds, static end card."""
    if first is None:
        first = (_bars("smptehdbars", 4, size), None)
    if tail is None:
        tail = (_bars("smptebars", 5, size), None)
    moving = [
        (_bars("testsrc2", 4, size), MOVING_LOOKS[i % 3]) for i in range(6)
    ]
    return [first, *moving, tail]


def slideshow_segments(size: str = HD):
    """Same cut rhythm as the passing recipe, but every shot is a still."""
    return [
        (_bars("smptehdbars", 4, size), None),
        (_color("0x1E6FD9", 4, size), None),
        (_bars("smptebars", 4, size), None),
        (_color("0xD94A1E", 4, size), None),
        (_bars("smptehdbars", 4, size), None),
        (_color("0x7A1E1E", 4, size), None),
        (_bars("smptebars", 4, size), None),
        (_bars("smptebars", 5, size), None),
    ]


# --- fixtures (generated once per session, never committed) -------------------


@pytest.fixture(scope="session")
def good(tmp_path_factory):
    out = tmp_path_factory.mktemp("good") / "good.mp4"
    return _encode(out, passing_segments())


@pytest.fixture(scope="session")
def good_with_audio(tmp_path_factory):
    out = tmp_path_factory.mktemp("audio") / "good_audio.mp4"
    return _encode(out, passing_segments(), audio=True)


@pytest.fixture(scope="session")
def defect_dark_first(tmp_path_factory):
    out = tmp_path_factory.mktemp("dark") / "dark_first.mp4"
    # Dark but textured: two luma levels (50/3), mean ~13 < 20, std ~19 > 12,
    # spread ~47 -> only the luma-mean check fails.
    dim = "lutyuv=y=if(gt(val\\,128)\\,50\\,3)"
    first = (_bars("smptehdbars", 4), dim)
    return _encode(out, passing_segments(first=first))


@pytest.fixture(scope="session")
def defect_four_by_three(tmp_path_factory):
    out = tmp_path_factory.mktemp("aspect") / "four_by_three.mp4"
    # 1920x1440 is 4:3 while width and height both still clear their bars.
    return _encode(out, passing_segments(size="1920x1440"))


@pytest.fixture(scope="session")
def defect_too_short(tmp_path_factory):
    out = tmp_path_factory.mktemp("short") / "too_short.mp4"
    segments = [
        (_bars("smptehdbars", 3), None),
        (_bars("testsrc2", 3), None),
        (_bars("testsrc2", 4), "negate"),
        (_bars("smptebars", 3), None),
    ]
    return _encode(out, segments)


@pytest.fixture(scope="session")
def defect_no_cuts(tmp_path_factory):
    out = tmp_path_factory.mktemp("nocuts") / "no_cuts.mp4"
    # One continuous moving scene, frozen for the last 4 s: no hard cut, so
    # the cut rate is 0 while the end card stays static.
    segments = [(_bars("testsrc2", 28), "tpad=stop_mode=clone:stop_duration=4")]
    return _encode(out, segments)


@pytest.fixture(scope="session")
def defect_moving_end(tmp_path_factory):
    out = tmp_path_factory.mktemp("movingend") / "moving_end.mp4"
    tail = (_bars("testsrc2", 5), None)  # moving tail instead of an end card
    return _encode(out, passing_segments(tail=tail))


@pytest.fixture(scope="session")
def defect_slideshow(tmp_path_factory):
    out = tmp_path_factory.mktemp("slides") / "slideshow.mp4"
    return _encode(out, slideshow_segments())


@pytest.fixture(scope="session")
def defect_ken_burns(tmp_path_factory):
    out = tmp_path_factory.mktemp("kenburns") / "ken_burns.mp4"
    # Slow zoom on stills between cuts: every frame changes a little
    # (YDIF ~0.4), which is still a slide, not a moving result.
    zoom = "zoompan=z='min(zoom+0.0008,1.3)':d=1:s=1920x1080:fps=30"
    segments = [(src, zoom) for src, _ in slideshow_segments()[:-1]]
    return _encode(out, [*segments, slideshow_segments()[-1]])


@pytest.fixture(scope="session")
def defect_720p(tmp_path_factory):
    out = tmp_path_factory.mktemp("sd") / "sd_720p.mp4"
    return _encode(out, passing_segments(size="1280x720"))


@pytest.fixture(scope="session")
def defect_no_faststart(tmp_path_factory):
    out = tmp_path_factory.mktemp("nofast") / "no_faststart.mp4"
    return _encode(out, passing_segments(), faststart=False)


@pytest.fixture(scope="session")
def defect_blank_first(tmp_path_factory):
    out = tmp_path_factory.mktemp("blank") / "blank_first.mp4"
    first = (_color("0x101010", 4), None)  # near-black solid colour
    return _encode(out, passing_segments(first=first))


DEFECTS = {
    "defect_dark_first": {"first_frame_luma_mean"},
    "defect_four_by_three": {"aspect_ratio"},
    "defect_too_short": {"duration_s"},
    "defect_no_cuts": {"scene_cuts_per_10s"},
    "defect_moving_end": {"endcard_static"},
    "defect_slideshow": {"motion_fraction"},
    "defect_ken_burns": {"motion_fraction"},
    "defect_720p": {"width", "height"},
    "defect_no_faststart": {"faststart"},
    "defect_blank_first": {
        "first_frame_luma_mean",
        "first_frame_luma_std",
        "first_frame_not_solid",
    },
}


# --- the gate itself ----------------------------------------------------------


def _failed_names(video: Path) -> set[str]:
    verdict = video_gate.judge(str(video))
    return set(verdict["failed"])


def test_good_passes_every_check(good):
    verdict = video_gate.judge(str(good))
    assert verdict["passed"], json.dumps(verdict["checks"], indent=2)
    names = {c["name"] for c in verdict["checks"]}
    assert {
        "width", "height", "aspect_ratio", "duration_s", "fps", "codec",
        "pix_fmt", "size_mib", "faststart", "first_frame_luma_mean",
        "first_frame_luma_std", "first_frame_not_solid", "scene_cuts_per_10s",
        "motion_fraction", "endcard_static", "audio",
    } == names
    audio = next(c for c in verdict["checks"] if c["name"] == "audio")
    assert audio["measured"] == "absent"  # audio optional: silence passes


def test_audio_stream_is_reported_and_optional(good_with_audio):
    verdict = video_gate.judge(str(good_with_audio))
    assert verdict["passed"], json.dumps(verdict["checks"], indent=2)
    audio = next(c for c in verdict["checks"] if c["name"] == "audio")
    assert audio["measured"] == "present"


@pytest.mark.parametrize("fixture_name, expected", sorted(DEFECTS.items()))
def test_single_defect_fails_exactly_the_intended_check(
    fixture_name, expected, request
):
    video = request.getfixturevalue(fixture_name)
    failed = _failed_names(video)
    assert failed == expected, (
        f"{fixture_name}: expected exactly {sorted(expected)} to fail, "
        f"got {sorted(failed)}"
    )


def test_every_check_reports_measured_threshold_pass(good):
    verdict = video_gate.judge(str(good))
    for check in verdict["checks"]:
        assert set(check) == {"name", "measured", "threshold", "pass"}
        assert isinstance(check["pass"], bool)
        assert check["threshold"]


# --- the CLI ------------------------------------------------------------------


def _cli(video: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(TOOLS_DIR / "video_gate.py"), str(video), *extra],
        capture_output=True, text=True,
    )


def test_cli_exit_0_and_json_out_on_pass(good, tmp_path):
    out_json = tmp_path / "verdict.json"
    proc = _cli(good, "--json", str(out_json))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    stdout_verdict = json.loads(proc.stdout)
    assert stdout_verdict["passed"] is True
    assert json.loads(out_json.read_text()) == stdout_verdict


def test_cli_exit_1_on_failure(defect_720p):
    proc = _cli(defect_720p)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["failed"] == ["width", "height"]


def test_cli_exit_2_on_missing_file(tmp_path):
    proc = _cli(tmp_path / "nope.mp4")
    assert proc.returncode == 2
    assert "not found" in json.loads(proc.stdout)["error"]


def test_cli_exit_2_on_non_video(tmp_path):
    bogus = tmp_path / "not_a_video.mp4"
    bogus.write_text("definitely not an mp4")
    proc = _cli(bogus)
    assert proc.returncode == 2
    assert "error" in json.loads(proc.stdout)


# --- committed demos: the known-fail baseline ----------------------------------
# These videos predate the gate and are expected to fail while they are re-cut
# to the standard. Every other committed demo must pass. Remove a name from
# KNOWN_FAIL once its re-cut passes; add one only in the change that adds a
# new check (solidcraft-cad and taste-skill-landing: motion_fraction).
KNOWN_FAIL = {"fea-calculix", "firmware-qemu", "gpu-kernel", "plc-st", "render-pathtrace", "sim-engine-arena", "solidcraft-cad", "spice-filter", "taste-skill-landing"}


def test_committed_demo_baseline():
    demos = sorted(d for d in REPO_ROOT.glob("cookbook/*/media/demo.mp4")
                   if not d.parent.parent.name.startswith("_"))  # _template holds a placeholder
    assert demos, "no committed cookbook/*/media/demo.mp4 found"
    header = f"{'demo':<20} {'gate':<6} failed checks"
    print("\n" + header + "\n" + "-" * len(header))
    must_pass = []
    for demo in demos:
        verdict = video_gate.judge(str(demo))
        for check in verdict["checks"]:  # well-formed even for known fails
            assert set(check) == {"name", "measured", "threshold", "pass"}
        name = demo.parent.parent.name
        gate = "PASS" if verdict["passed"] else "FAIL"
        print(f"{name:<20} {gate:<6} {', '.join(verdict['failed']) or '-'}")
        if name not in KNOWN_FAIL and not verdict["passed"]:
            must_pass.append(f"{name}: {', '.join(verdict['failed'])}")
    print("-" * len(header))
    assert not must_pass, "demos outside the known-fail baseline must pass: " + "; ".join(must_pass)


def test_motion_window_ignores_a_video_start_offset(good, tmp_path):
    # Video delayed 5 s behind audio: pts start at 5 s, the duration is
    # unchanged, so the motion window must be measured from the first frame.
    shifted = tmp_path / "shifted.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-itsoffset", "5", "-i", str(good),
                    "-f", "lavfi", "-t", "5", "-i", "anullsrc=r=48000:cl=stereo",
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-movflags", "+faststart", str(shifted)], check=True)
    base = video_gate.judge(str(good))
    moved = video_gate.judge(str(shifted))
    fraction = {c["name"]: c["measured"] for c in base["checks"]}["motion_fraction"]
    shifted_fraction = {c["name"]: c["measured"] for c in moved["checks"]}["motion_fraction"]
    assert shifted_fraction == pytest.approx(fraction, abs=0.02)


def test_non_square_pixels_judged_by_display_aspect(good, tmp_path):
    wide = tmp_path / "wide.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(good), "-c", "copy", "-aspect", "32:9",
                    "-movflags", "+faststart", str(wide)], check=True)
    verdict = video_gate.judge(str(wide))
    assert verdict["failed"] == ["aspect_ratio"]
