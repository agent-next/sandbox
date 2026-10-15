"""Physics/receipt contracts, no GL context or remote API required."""

import json
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render


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


def test_target_ghost_uses_unmodified_same_step_states(monkeypatch):
    class Renderer:
        def __init__(self, model, **kwargs):
            self.model = model
            self.scene = render.mujoco.MjvScene(model, maxgeom=100)

        def update_scene(self, data, camera):
            render.mujoco.mjv_updateScene(
                self.model, data, render.mujoco.MjvOption(), None, camera,
                render.mujoco.mjtCatBit.mjCAT_ALL, self.scene)

        def render(self):
            return np.zeros((850, 640, 3), dtype=np.uint8)

        def close(self):
            pass

    monkeypatch.setattr(render.mujoco, "Renderer", Renderer)
    model = render.engine.make_model(render.engine.DEFAULT_PARAMS)
    truth = model.qpos0.copy()
    candidate = truth.copy()
    candidate[0] += .07
    traces = {"default_0_qpos": candidate[None], "truth_0_qpos": truth[None],
              "default_0_qvel": np.zeros((1, model.nv)),
              "truth_0_qvel": np.zeros((1, model.nv))}
    meta = {"roles": {r: render.engine.DEFAULT_PARAMS for r in render.ROLES},
            "timestep_s": .002,
            "initial_conditions": [{"c1a": 0, "c2a": 0, "c1b": 0, "c2b": 0}]}
    replay = render.Replay("default", meta, traces)
    replay.frame(0, 0, "box", 0)
    np.testing.assert_array_equal(replay.data.qpos, candidate)
    np.testing.assert_array_equal(replay.reference_data.qpos, truth)
    for geom, name in zip(replay.renderer.scene.geoms[
            replay.renderer.scene.ngeom - 3:replay.renderer.scene.ngeom],
            ("boxgeom", "l1", "l2")):
        gid = render.mujoco.mj_name2id(replay.reference_model,
                                     render.mujoco.mjtObj.mjOBJ_GEOM, name)
        np.testing.assert_array_equal(
            geom.pos, replay.reference_data.geom_xpos[gid].astype(geom.pos.dtype))
    replay.close()
