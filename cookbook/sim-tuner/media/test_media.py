"""Physics/receipt contracts, no GL context or remote API required."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render
import manifest


def test_rendered_state_must_be_exact():
    render.assert_state([1., 2.], [1., 2.], "positive")
    with pytest.raises(AssertionError, match="differs from graded state"):
        render.assert_state([1., 2.001], [1., 2.], "corrupted frame")
    with pytest.raises(AssertionError, match="differs from graded state"):
        render.assert_state([float("nan")], [1.], "nonfinite")


@pytest.mark.parametrize("light", [False, True])
def test_scene_dressing_keeps_physics(light):
    params = render.engine.DEFAULT_PARAMS
    original = render.engine.make_model(params)
    styled = render.visual_model(params, "tuned", light)
    for field in ("body_mass", "body_inertia", "dof_damping", "dof_armature"):
        np.testing.assert_array_equal(getattr(styled, field), getattr(original, field))
    mount = render.mujoco.mj_name2id(styled, render.mujoco.mjtObj.mjOBJ_GEOM, "mount")
    assert styled.geom_contype[mount] == styled.geom_conaffinity[mount] == 0


def test_real_run_receipt_is_green():
    report = json.loads((HERE / "data/run-1.json").read_text())
    assert report["verdict"]["pass"] and report["verdict"]["judge_intact"]
    assert report["stages"]["grade"]["wall_s"] is not None
    assert len(render.kills_from_report(report)) == 18


def test_missing_mutant_kill_is_not_media_proof():
    with pytest.raises(AssertionError):
        render.kills_from_report({"stages": {"selftest": {"stdout_tail":
            "selftest: kill rate: 18/18 = 100%"}}})


def test_overlay_uses_unmodified_same_step_states(monkeypatch):
    class Renderer:
        def __init__(self, model, **kwargs):
            self.model = model
            self.scene = render.mujoco.MjvScene(model, maxgeom=100)

        def update_scene(self, data, camera, scene_option):
            render.mujoco.mjv_updateScene(
                self.model, data, scene_option, None, camera,
                render.mujoco.mjtCatBit.mjCAT_ALL, self.scene)

        def render(self):
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

        def close(self):
            pass

    monkeypatch.setattr(render.mujoco, "Renderer", Renderer)
    model = render.engine.make_model(render.engine.DEFAULT_PARAMS)
    truth = model.qpos0.copy()
    candidate = truth.copy()
    candidate[0] += .07
    traces = {f"{r}_0_qpos": (candidate if r == "default" else truth)[None]
              for r in render.ROLES}
    traces.update({f"{r}_0_qvel": np.zeros((1, model.nv)) for r in render.ROLES})
    meta = {"roles": {r: render.engine.DEFAULT_PARAMS for r in render.ROLES},
            "timestep_s": .002,
            "initial_conditions": [{"c1a": 0, "c2a": 0, "c1b": 0, "c2b": 0}]}
    replay = render.Replay(meta, traces)
    replay.frame(0, 0, "box", 0)
    np.testing.assert_array_equal(replay.states["default"].qpos, candidate)
    for role in ("tuned", "truth"):
        np.testing.assert_array_equal(replay.states[role].qpos, truth)
    # Twelve orange and twelve white edge midpoints on the actual boxes.
    scene = replay.renderer.scene
    for start, state in ((scene.ngeom - 24, candidate), (scene.ngeom - 12, truth)):
        edges = scene.geoms[start:start + 12]
        np.testing.assert_allclose(np.mean([g.pos for g in edges], axis=0),
                                   state[:3], atol=1e-7)
        assert len(edges) == 12
    replay.close()


def test_case_order_is_measured_not_fabricated():
    meta, _, traces = render.read_inputs()
    order = meta["presentation_order"]
    assert [c["source_recording"] for c in order] == [2, 3, 0, 1]
    assert [c["max_default_box_gap_cm"] for c in order] == sorted(
        [c["max_default_box_gap_cm"] for c in order], reverse=True)
    for case in order:
        i = case["source_recording"]
        gap = np.max(np.abs(traces[f"default_{i}_qpos"][:, 0] -
                           traces[f"truth_{i}_qpos"][:, 0])) * 100
        assert case["max_default_box_gap_cm"] == gap
    for role, key in (("default", "default_err"), ("tuned", "heldout_err")):
        aggregate = np.sqrt(np.mean([c[f"{role}_error"] ** 2 for c in order]))
        assert round(float(aggregate), 6) == meta["gates"]["G3_heldout"][key]


def test_cut_is_real_slow_motion_with_one_short_end_card():
    assert [s[3] for s in render.SHOTS[:4]] == [0, 1, 2, 3]
    for _, seconds, _, _, start, stride in render.SHOTS:
        assert isinstance(start, int) and isinstance(stride, int) and stride > 0
        assert start + (seconds * 30 - 1) * stride <= render.engine.NSTEP
        assert 30 * stride * .002 == .06
    assert 2 <= render.END_FRAMES / 30 <= 2.5
    assert 25 <= sum(s[1] for s in render.SHOTS) + render.END_FRAMES / 30 <= 60


def test_parameter_hud_names_and_values_come_from_graded_model():
    meta, _, _ = render.read_inputs()
    assert [p[0] for p in render.PARAM_LABELS] == render.engine.PARAM_NAMES
    assert meta["roles"]["default"] == render.engine.DEFAULT_PARAMS
    assert meta["roles"]["tuned"] == json.loads(
        (HERE.parent / "examples/good/params.json").read_text())
    assert meta["roles"]["truth"] == render.engine.gen_scenario(meta["seed"])["truth"]
    assert render.COLORS["truth"] == "#f0f2f0"


@pytest.mark.parametrize("elapsed", [0, 6, 11, 17, 19, 22])
def test_every_hud_fits_and_has_phone_readable_cap_height(monkeypatch, elapsed):
    meta, _, traces = render.read_inputs()
    recording = meta["presentation_order"][0]["source_recording"]
    replay = SimpleNamespace(
        states={r: SimpleNamespace(qpos=traces[f"{r}_{recording}_qpos"][200])
                for r in render.ROLES},
        frame=lambda *args: render.Image.new("RGB", (1920, 1080)),
    )
    original_label = render.label
    captions = []

    def checked_label(image, xy, text, size=40, fill=render.INK, bold=False):
        font = render.ImageFont.truetype(render.BOLD if bold else render.FONT, size)
        bounds = font.getbbox("H")
        assert bounds[3] - bounds[1] >= 1080 * .04
        captions.append(text)
        original_label(image, xy, text, size, fill, bold)

    monkeypatch.setattr(render, "label", checked_label)
    render.composition(replay, meta, 200, "box", .25, 0, elapsed, elapsed >= 21)
    if elapsed < 21:
        param = sum(elapsed >= boundary for boundary in render.PARAM_BOUNDARIES[1:-1])
        name = render.PARAM_LABELS[param][0]
        for role in render.ROLES:
            assert f"{meta['roles'][role][name]:.6f}" in captions


def test_manifest_invalidates_only_previous_cut_reviews(monkeypatch, tmp_path):
    (tmp_path / "data").mkdir()
    for name in ("run-1.json", "replay.json", "provenance.json"):
        (tmp_path / "data" / name).write_bytes((HERE / "data" / name).read_bytes())
    (tmp_path / "demo.mp4").write_bytes(b"new video")
    review_path = tmp_path / "REVIEW.json"
    review_path.write_text(json.dumps({
        "video_sha256": "old video", "passed": False, "judges": ["stale verdict"],
    }))
    monkeypatch.setattr(manifest, "HERE", tmp_path)
    manifest.main()
    review = json.loads(review_path.read_text())
    assert review["status"] == "pending" and review["passed"] is None
    assert review["judges"] == []
    assert review["video_sha256"] == manifest.hashlib.sha256(b"new video").hexdigest()
    review["judges"] = ["new panel"]
    review_path.write_text(json.dumps(review))
    manifest.main()
    assert json.loads(review_path.read_text())["judges"] == ["new panel"]
