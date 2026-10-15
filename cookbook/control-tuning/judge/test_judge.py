#!/usr/bin/env python3
"""Unit tests for judge_lib — plant physics, linearisation, margins,
settling. Run from the demo root: python3 -m unittest judge/test_judge.py -v

The tests exercise the public API only (nonlinear_rhs, siso_margins,
settling_time, ab_of), so they also run against a regression copy of the
module and fail there with wrong numbers, not missing names.
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge_lib as jl  # noqa: E402


def drive(s, F, tu):
    """Nonlinear [xdd, thedd] at state s under inputs (F, tu).

    Uses the same mass-matrix path as the simulator: pick a K whose
    feedback -K @ s equals (F, tu) at this s (needs one nonzero state
    component to load the input onto).
    """
    s = np.asarray(s, dtype=float)
    i = int(np.argmax(np.abs(s)))
    if s[i] == 0.0:
        raise ValueError("need a nonzero state component to inject inputs")
    K = np.zeros((2, 4))
    K[0, i] = -F / s[i]
    K[1, i] = -tu / s[i]
    a = jl.nonlinear_rhs(K, jl.M0, jl.M1, jl.L0)(0.0, s)
    return np.array([a[1], a[3]])


def accel_closed_form(s, F, tu):
    """Independent reference solve of M(q) qdd = b, straight from the
    Lagrangian mass matrix [[M+m, m l cos th], [m l cos th, m l^2]]."""
    _x, _v, th, w = s
    M, m, l, g = jl.M0, jl.M1, jl.L0, jl.G
    mat = np.array([[M + m, m * l * math.cos(th)],
                    [m * l * math.cos(th), m * l * l]])
    b = np.array([F + m * l * w * w * math.sin(th),
                  tu + m * g * l * math.sin(th)])
    return np.linalg.solve(mat, b)


class TestNonlinearPlant(unittest.TestCase):
    def test_angular_accel_matches_closed_form(self):
        # Review case: th = 0.5 rad, F = 10 N, tau = 0, zero velocity.
        # Closed form gives -7.04 rad/s^2 (the buggy a21 gave -9.54).
        s = (0.0, 0.0, 0.5, 0.0)
        acc = drive(s, 10.0, 0.0)
        ref = accel_closed_form(s, 10.0, 0.0)
        np.testing.assert_allclose(acc, ref, rtol=1e-9, atol=1e-9)
        self.assertAlmostEqual(acc[1], -7.04, delta=0.01)

    def test_mass_matrix_symmetric_in_theta(self):
        # a21 must carry the same cos(th) as a12: check at several angles.
        for th in (-0.7, -0.3, 0.3, 0.9):
            s = (0.0, 0.0, th, 0.0)
            np.testing.assert_allclose(
                drive(s, 7.0, -0.4), accel_closed_form(s, 7.0, -0.4),
                rtol=1e-9, atol=1e-9)


class TestLinearisation(unittest.TestCase):
    def test_B_columns_match_nonlinear_jacobian(self):
        # d/dF and d/dtau of [xdd, thedd] at the upright equal B columns
        # (torque authority (M+m)/(M m l^2) = 44, not (M+m)/(m l) = 22).
        s = (0.0, 0.0, 1e-6, 0.0)      # nonzero theta to load inputs onto
        eps = 1e-3
        for j, (dF, dT) in enumerate(((eps, 0.0), (0.0, eps))):
            col = (drive(s, dF, dT) - drive(s, -dF, -dT)) / (2.0 * eps)
            np.testing.assert_allclose(
                col, jl.B0[[1, 3], j], rtol=1e-5, atol=1e-5)

    def test_A_accel_rows_match_nonlinear_jacobian(self):
        eps = 1e-6
        for j in range(4):
            dp = np.zeros(4)
            dp[j] = eps
            col = (drive(dp, 0.0, 0.0) - drive(-dp, 0.0, 0.0)) / (2.0 * eps)
            np.testing.assert_allclose(
                col, jl.A0[[1, 3], j], rtol=1e-4, atol=1e-4)


def _margins_on(mag_knots, ph_knots):
    """(gm, pm) of a synthetic loop given as (w, mag) and (w, ph) knots,
    interpolated linearly in log w onto the judge's sweep grid. ph in
    radians, unwrapped. Monkeypatches loop_response so siso_margins runs
    on the synthetic curve."""
    w = jl.W_SWEEP
    lw = np.log(w)
    mag = np.interp(lw, np.log(mag_knots[0]), mag_knots[1])
    ph = np.interp(lw, np.log(ph_knots[0]), ph_knots[1])
    orig = jl.loop_response
    jl.loop_response = lambda Ki, bi: (mag, ph)
    try:
        return jl.siso_margins(np.zeros(4), np.zeros(4))
    finally:
        jl.loop_response = orig


class TestMargins(unittest.TestCase):
    def test_gain_margin_sees_positive_180_crossing(self):
        # Review case: phase crosses +180 deg at 0.624 rad/s with
        # |L| = 2.990 -> GM = -20log10(2.990) = -9.51 dB. The old code
        # scanned only -180 deg multiples and reported the 99 dB
        # sentinel.
        wk = np.array([0.01, 0.624, 1.8658, 1000.0])
        ph = math.pi + 0.5 * np.log(wk / 0.624)     # crosses +pi at 0.624
        mag = 2.990 * 0.624 / wk                    # |L| = 2.990 at 0.624
        gm, _pm = _margins_on((wk, mag), (wk, ph))
        self.assertAlmostEqual(gm, -9.51, delta=0.05)

    def test_phase_margin_normalised_signed(self):
        # Review case: |L| = 1 where the unwrapped phase is +29.48 deg.
        # The old code normalised before adding 180 and reported
        # 209.48 deg; the conventional signed margin is -150.52 deg.
        wk = np.array([0.01, 1.0, 1000.0])
        mag = np.array([10.0, 1.0, 0.1])
        ph = np.full(3, math.radians(29.48))
        _gm, pm = _margins_on((wk, mag), (wk, ph))
        self.assertAlmostEqual(pm, -150.52, delta=0.02)

    def test_gain_margin_every_odd_multiple(self):
        # A loop crossing both -180 deg (|L| = 0.5 -> +6.02 dB) and
        # -540 deg (|L| = 20 -> -26.02 dB): the worst crossing wins.
        wk = np.array([0.01, 1.0, 10.0, 1000.0])
        # linear-in-log-w phase from -2 rad to -10.5 rad: crosses -pi
        # near w = 0.047 and -3 pi near w = 233
        ph = np.interp(np.log(wk), np.log([0.01, 1000.0]), [-2.0, -10.5])
        mag = np.array([0.5, 0.5, 20.0, 20.0])
        gm, _pm = _margins_on((wk, mag), (wk, ph))
        self.assertAlmostEqual(gm, -26.02, delta=0.05)


class TestSettling(unittest.TestCase):
    def test_settle_is_first_sample_of_permanent_inside(self):
        # Review case: sample at 0.70 s is still outside the 0.003 rad
        # band (0.0030082); the signal enters for good at 0.71 s.
        t = np.arange(0.0, 10.01, 0.01)
        y = np.zeros_like(t)
        y[:71] = 0.01
        y[70] = 0.0030082
        self.assertAlmostEqual(jl.settling_time(t, y, 0.003), 0.71)

    def test_settle_reentry_counts(self):
        t = np.arange(0.0, 10.01, 0.01)
        y = np.full_like(t, 0.001)
        y[500] = 0.5          # brief excursion at 5.00 s
        self.assertAlmostEqual(jl.settling_time(t, y, 0.003), 5.01)

    def test_never_settles_returns_horizon(self):
        t = np.arange(0.0, 10.01, 0.01)
        self.assertAlmostEqual(
            jl.settling_time(t, np.full_like(t, 1.0), 0.003), 10.0)

    def test_always_inside_returns_zero(self):
        t = np.arange(0.0, 10.01, 0.01)
        self.assertEqual(jl.settling_time(t, np.zeros_like(t), 0.003), 0.0)


if __name__ == "__main__":
    unittest.main()
