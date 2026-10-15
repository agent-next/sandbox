#!/usr/bin/env python3
"""Unit tests for the judge-owned sweep-grid validation (no solver, no
openEMS — plain numpy + grade.py). Run: python3 judge/test_grid.py

_valid_sweep() is what keeps every acceptance value (G3 scalars, G4, G5,
G6, G8) anchored to frequencies the artifact does not choose: the
artifact's reported sweep must be strictly increasing, cover 2.2-2.7 GHz
and carry >= N_JUDGE_GRID points, on both the coarse and the fine path.
The code-review case these tests pin down: a *complete and honest*
pointwise sweep whose resonance sample is moved to the end — np.interp
clamps any query at or beyond the last sample to that sample's value, so
a scalar-only check reads the resonance dip as S11(2.45 GHz) and a
physically failing design passes G4/G5/G6/G8 unmodified.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import grade


def review_sweep():
    """The review's exact vector: 51 points, 2.2-2.7 GHz, a -20 dB
    resonance at 2.42 GHz (true value at 2.45 GHz: -5.69 dB)."""
    f = np.linspace(2.2, 2.7, 51)
    s = -4.0 - 16.0 * np.exp(-((f - 2.42) / 0.03) ** 2)
    return f, s


def shuffled(f, s):
    """Move the resonance sample (the minimum) to the end, pairs intact."""
    i = int(np.argmin(s))
    order = [k for k in range(len(f)) if k != i] + [i]
    return f[order], s[order]


class SweepGrid(unittest.TestCase):

    def test_honest_grid_accepted(self):
        f, s = review_sweep()
        ok, msg = grade._valid_sweep(f, s)
        self.assertTrue(ok, msg)

    def test_judge_grid_is_valid_and_hits_target(self):
        g = np.asarray(grade.JUDGE_FREQS_GHZ)
        self.assertTrue((np.diff(g) > 0).all())
        self.assertAlmostEqual(g[0], grade.SWEEP_LO_GHZ)
        self.assertAlmostEqual(g[-1], grade.SWEEP_HI_GHZ)
        self.assertAlmostEqual(g[int(np.argmin(abs(g - 2.45)))], 2.45)

    def test_shuffled_rejected(self):
        f, s = shuffled(*review_sweep())
        ok, msg = grade._valid_sweep(f, s)
        self.assertFalse(ok)
        self.assertIn("strictly increasing", msg)

    def test_shuffled_is_the_interp_exploit_the_review_described(self):
        # why ordering matters: with the resonance sample last, the old
        # judge's np.interp(2.45, freqs, s11) clamped to that sample and
        # reported the -20 dB dip instead of the true -9.9 dB
        f, s = shuffled(*review_sweep())
        fs, ss = review_sweep()
        self.assertLessEqual(float(np.interp(2.45, f, s)), -19.9)
        self.assertGreater(float(np.interp(2.45, fs, ss)), -10.0)

    def test_too_few_points_rejected(self):
        f = np.linspace(2.2, 2.7, 21)          # SPEC's old minimum
        ok, msg = grade._valid_sweep(f, np.zeros(21))
        self.assertFalse(ok)
        self.assertIn("points", msg)

    def test_coverage_rejected(self):
        f = np.linspace(2.3, 2.6, 51)          # in-band only
        ok, msg = grade._valid_sweep(f, np.zeros(51))
        self.assertFalse(ok)
        self.assertIn("does not cover", msg)

    def test_duplicated_frequency_rejected(self):
        f = list(np.linspace(2.2, 2.7, 51))
        f[10] = f[9]
        ok, msg = grade._valid_sweep(f, np.zeros(51))
        self.assertFalse(ok)
        self.assertIn("strictly increasing", msg)

    def test_length_mismatch_rejected(self):
        f = np.linspace(2.2, 2.7, 51)
        ok, msg = grade._valid_sweep(f, np.zeros(50))
        self.assertFalse(ok)
        self.assertIn("mismatch", msg)

    def test_single_frequency_report_rejected(self):
        # the fine path used to accept this; a 2.52 GHz resonance simply
        # disappeared from the resonance search
        ok, msg = grade._valid_sweep([2.52], [-20.0])
        self.assertFalse(ok)
        self.assertIn("points", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
