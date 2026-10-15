"""Oracle for the control-tuning demo judge.

Everything here is derived by the judge itself: the artifact under test only
supplies LQR weights (Q, R). The judge recomputes K with control.lqr(),
simulates the linear and nonlinear plant, measures the spec mask and the
loop-at-a-time margins, and runs the Monte-Carlo robustness sweep.

Plant: inverted pendulum on a cart, linearised about the upright.
Standard model (point-mass pendulum, massless rod, no friction):

    (M + m) xdd + m l thedd = F
    m l xdd + m l^2 thedd = m g l theta + tau

State [x, xdot, theta, thetadot]; inputs [F (cart force), tau (pendulum
torque)]; theta measured from upright. Actuator limits |F| <= FMAX,
|tau| <= TAUMAX are hard clamps in the nonlinear simulation; the demand is
measured before clamping.
"""
import math
import os

import numpy as np
from scipy.integrate import solve_ivp

# --- judge-fixed plant constants (artifact cannot change these) ---
G = 9.81          # m/s^2
M0 = 1.0          # cart mass, kg
M1 = 0.1          # pendulum mass, kg
L0 = 0.5          # pivot -> COM distance, m
FMAX = 10.0       # N
TAUMAX = 1.0      # N*m

THETA0 = 0.15     # initial lean, rad (scenario 1)
XDISP = 1.0       # initial cart displacement, m (scenario 2)

THETA_BAND = 0.02 * THETA0    # 2 % settling band for theta, rad
X_BAND = 0.01                 # settling band for x, m (scenario 1)

SIM_T = 10.0


def ab_of(M, m, l):
    """Linearised A, B for cart mass M, pendulum mass m, COM distance l.

    Lagrangian (point-mass bob, massless rod, th from upright):
    L = (M+m)v^2/2 + m l v w cos(th) + m l^2 w^2/2 - m g l cos(th), so
    M(q) qdd = b with M = [[M+m, m l cos th], [m l cos th, m l^2]] —
    symmetric, hence cos(th) in BOTH off-diagonals. Solving the th = 0
    system for [xdd, thedd] gives A, B (torque authority (M+m)/(M m l^2)).
    """
    A = np.array([
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, -m * G / M, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, G * (M + m) / (M * l), 0.0],
    ])
    B = np.array([
        [0.0, 0.0],
        [1.0 / M, -1.0 / (M * l)],
        [0.0, 0.0],
        [-1.0 / (M * l), (M + m) / (M * m * l * l)],
    ])
    return A, B


A0, B0 = ab_of(M0, M1, L0)


def nonlinear_rhs(K, M, m, l):
    """Full nonlinear cart-pole right-hand side with input clamping."""
    def rhs(t, s):
        F = float(np.clip(-(K[0] @ s), -FMAX, FMAX))
        tu = float(np.clip(-(K[1] @ s), -TAUMAX, TAUMAX))
        x, v, th, w = s
        a11 = M + m
        a12 = m * l * math.cos(th)
        a21 = m * l * math.cos(th)
        a22 = m * l * l
        b1 = F + m * l * w * w * math.sin(th)
        b2 = tu + m * G * l * math.sin(th)
        det = a11 * a22 - a12 * a21
        return [v, (b1 * a22 - b2 * a12) / det,
                w, (a11 * b2 - a21 * b1) / det]
    return rhs


def sim_nonlinear(K, M, m, l, ic, T=SIM_T, max_step=0.01,
                  rtol=1e-8, atol=1e-10):
    sol = solve_ivp(nonlinear_rhs(K, M, m, l), [0.0, T], ic,
                    max_step=max_step, rtol=rtol, atol=atol,
                    dense_output=True)
    t = np.linspace(0.0, T, int(T * 100) + 1)
    return t, sol.sol(t)


def settling_time(t, y, band):
    """First sample after which |y| stays inside band forever after.

    Returns 0.0 if |y| is always inside; t[-1] if it never settles (the
    sample grid's last timestamp — the signal is still outside its band
    at the horizon, so every settling gate fails on it).
    """
    idx = np.where(np.abs(y) > band)[0]
    if not len(idx):
        return 0.0
    i = idx[-1] + 1
    return float(t[i]) if i < len(t) else float(t[-1])


def demands(K, Y):
    """Unclamped actuator demands along a trajectory."""
    F = np.array([-(K[0] @ Y[:, j]) for j in range(Y.shape[1])])
    T = np.array([-(K[1] @ Y[:, j]) for j in range(Y.shape[1])])
    return F, T


def save_trace(path, t, Y, F, T):
    """Write one simulation trace as CSV: time, states, unclamped demands.

    Trace output only (gate numbers never read it back); the verdict is
    byte-identical whether or not traces are written.
    """
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("t_s,x_m,xdot_m_s,theta_rad,thetadot_rad_s,"
                 "F_demand_N,tau_demand_Nm\n")
        for j in range(len(t)):
            row = (t[j], Y[0, j], Y[1, j], Y[2, j], Y[3, j], F[j], T[j])
            fh.write(",".join(f"{v:.10e}" for v in row) + "\n")


GM_NO_CROSSING_DB = 99.0   # phase never crosses -180 deg in the sweep band
W_SWEEP = np.logspace(-2.0, 3.0, 6000)


def loop_response(Ki, bi):
    """Loop-at-a-time frequency response L(jw) = Ki (jwI - A0)^-1 bi.

    Returns (mag, ph) sampled on W_SWEEP, ph unwrapped — the curves the
    margin gate is measured on.
    """
    L = np.array([Ki @ np.linalg.solve(1j * wi * np.eye(4) - A0, bi)
                  for wi in W_SWEEP])
    return np.abs(L), np.unwrap(np.angle(L))


def _level_crossings(w, y, level):
    """Frequencies where curve y(w) crosses `level`, linear in log w."""
    lw = np.log(w)
    out = []
    for i in range(len(w) - 1):
        d0, d1 = y[i] - level, y[i + 1] - level
        if d0 * d1 <= 0 and y[i] != y[i + 1]:
            f = d0 / (d0 - d1)
            out.append(math.exp(lw[i] + f * (lw[i + 1] - lw[i])))
    return out


def margins_from_sweep(w, mag, ph):
    """Gain/phase margins on a swept L(jw), negative feedback assumed.

    w, mag, ph (ph unwrapped, radians) sampled on the same frequency grid.
    Gain margin comes from every phase crossing of an odd multiple of
    180 deg, on either side of 0 deg (a +180 deg crossing is just as
    unstable under a gain change as a -180 deg one). Phase margin comes
    from every |L| = 1 crossing, normalised to the conventional signed
    range (-180, 180] deg — a 209 deg margin is really -151 deg.
    Returns (gm_db, pm_deg); gm_db is GM_NO_CROSSING_DB when no odd
    multiple of 180 deg is crossed, pm_deg is 180.0 when |L| never
    crosses 1.
    """
    lw = np.log(w)

    def interp(wc, y):
        return float(np.interp(math.log(wc), lw, y))

    gms = []
    kmin = int(math.floor(ph.min() / math.pi)) - 1
    kmax = int(math.ceil(ph.max() / math.pi)) + 1
    for k in range(kmin, kmax + 1):
        if k % 2 == 0:
            continue                       # only odd multiples of 180 deg
        for wc in _level_crossings(w, ph, k * math.pi):
            gms.append(-20.0 * math.log10(interp(wc, mag)))
    pms = [180.0 - (180.0 - (180.0 + math.degrees(interp(wc, ph)))) % 360.0
           for wc in _level_crossings(w, mag, 1.0)]
    return (min(gms) if gms else GM_NO_CROSSING_DB,
            min(pms) if pms else 180.0)


def siso_margins(Ki, bi):
    """Loop-at-a-time margins: L(s) = Ki (sI - A0)^-1 bi, negative feedback."""
    mag, ph = loop_response(Ki, bi)
    return margins_from_sweep(W_SWEEP, mag, ph)


# --- gate thresholds ---
EIG_MAX_REAL_MAX = -0.05      # closed-loop poles left of -0.05
OVERSHOOT_MAX = 0.10          # fraction of THETA0
S1_SETTLE_MAX = 5.0           # s (theta and x, scenario 1)
S2_SETTLE_MAX = 7.0           # s (x, scenario 2)
PEAK_THETA_MAX = 0.5          # rad, pendulum never falls over
END_THETA_MAX = 1e-3          # rad steady state
END_X_MAX = 0.01              # m steady state
GM_MIN_DB = 6.0
PM_MIN_DEG = 45.0
MC_N = 200
MC_FRACTION_MIN = 0.95
MC_SETTLE_MAX = 8.0           # s, lean-IC theta settling (relaxed)
MC_X_SETTLE_MAX = 7.0          # s, displacement-IC x settling (spec value)
XDISP_BAND = 0.02              # m, 2 % settling band for x (displacement IC)


def evaluate(Q, R, seed=20260101, n_mc=MC_N, run_mc=True, trace_dir=None):
    """Run every gate. Q, R are validated numpy arrays. Returns verdict.

    trace_dir, when set, additionally receives CSV traces of the two
    deterministic scenarios (time, states, unclamped demands) and of the
    margin-gate frequency sweeps. Writing traces changes no gate value.
    """
    import control

    if Q.ndim == 1:
        Q = np.diag(Q)
    if R.ndim == 1:
        R = np.diag(R)

    verdict = {"gates": {}, "passed": False}

    def gate(name, value, ok):
        verdict["gates"][name] = {"value": value, "pass": bool(ok)}

    # design: K is recomputed here, never read from the artifact
    try:
        K, _, _ = control.lqr(A0, B0, Q, R)
        K = np.atleast_2d(np.asarray(K, dtype=float))
    except Exception as exc:                       # slycot raises on bad Q/R
        verdict["error"] = f"lqr failed: {type(exc).__name__}"
        return verdict
    if not np.all(np.isfinite(K)):
        verdict["error"] = "lqr returned non-finite K"
        return verdict
    verdict["K"] = K.tolist()

    ev = np.linalg.eigvals(A0 - B0 @ K)
    eig_max = float(np.max(np.real(ev)))
    gate("design_stable", eig_max, eig_max < EIG_MAX_REAL_MAX)

    # scenario 1: recover from a 0.15 rad lean, nonlinear plant, clamped inputs
    t1, Y1 = sim_nonlinear(K, M0, M1, L0, (0.0, 0.0, THETA0, 0.0))
    th1, x1 = Y1[2], Y1[0]
    if not np.all(np.isfinite(Y1)):
        verdict["error"] = "nonlinear sim diverged (scenario 1)"
        return verdict
    F1, T1 = demands(K, Y1)
    if trace_dir:
        save_trace(os.path.join(trace_dir, "s1_trace.csv"), t1, Y1, F1, T1)
    gate("s1_F_demand_max_N", float(np.abs(F1).max()),
         np.abs(F1).max() <= FMAX)
    gate("s1_tau_demand_max_Nm", float(np.abs(T1).max()),
         np.abs(T1).max() <= TAUMAX)
    ov = float(np.abs(th1).max() / THETA0 - 1.0)
    gate("s1_theta_overshoot", ov, ov <= OVERSHOOT_MAX)
    st = settling_time(t1, th1, THETA_BAND)
    gate("s1_theta_settle_s", st, st <= S1_SETTLE_MAX)
    st = settling_time(t1, x1, X_BAND)
    gate("s1_x_settle_s", st, st <= S1_SETTLE_MAX)
    gate("s1_theta_end_rad", float(abs(th1[-1])),
         abs(th1[-1]) <= END_THETA_MAX)
    gate("s1_x_end_m", float(abs(x1[-1])), abs(x1[-1]) <= END_X_MAX)

    # scenario 2: cart displaced 1 m, pendulum upright
    t2, Y2 = sim_nonlinear(K, M0, M1, L0, (XDISP, 0.0, 0.0, 0.0))
    th2, x2 = Y2[2], Y2[0]
    if not np.all(np.isfinite(Y2)):
        verdict["error"] = "nonlinear sim diverged (scenario 2)"
        return verdict
    F2, T2 = demands(K, Y2)
    if trace_dir:
        save_trace(os.path.join(trace_dir, "s2_trace.csv"), t2, Y2, F2, T2)
    gate("s2_peak_theta_rad", float(np.abs(th2).max()),
         np.abs(th2).max() <= PEAK_THETA_MAX)
    gate("s2_F_demand_max_N", float(np.abs(F2).max()),
         np.abs(F2).max() <= FMAX)
    gate("s2_tau_demand_max_Nm", float(np.abs(T2).max()),
         np.abs(T2).max() <= TAUMAX)
    st = settling_time(t2, x2, 0.02)
    gate("s2_x_settle_s", st, st <= S2_SETTLE_MAX)
    gate("s2_theta_end_rad", float(abs(th2[-1])),
         abs(th2[-1]) <= END_THETA_MAX)

    # loop-at-a-time margins on the linearised plant
    gmf, pmf = siso_margins(K[0], B0[:, 0])
    gmt, pmt = siso_margins(K[1], B0[:, 1])
    gate("gm_force_db", gmf, gmf >= GM_MIN_DB)
    gate("pm_force_deg", pmf, pmf >= PM_MIN_DEG)
    gate("gm_torque_db", gmt, gmt >= GM_MIN_DB)
    gate("pm_torque_deg", pmt, pmt >= PM_MIN_DEG)
    if trace_dir:
        for name, Ki, bi in (("force", K[0], B0[:, 0]),
                             ("torque", K[1], B0[:, 1])):
            mag, ph = loop_response(Ki, bi)
            with open(os.path.join(trace_dir, f"margins_{name}.csv"),
                      "w", encoding="utf-8") as fh:
                fh.write("w_rad_s,mag,mag_db,phase_deg\n")
                for wi, mi, pi in zip(W_SWEEP, mag, ph):
                    fh.write(f"{wi:.10e},{mi:.10e},"
                             f"{20.0 * math.log10(mi):.10e},"
                             f"{math.degrees(pi):.10e}\n")

    # Monte-Carlo robustness: +-20 % on M, m, l, nonlinear plant. Each
    # sample runs BOTH spec scenarios — the 0.15 rad lean (gate 3) and the
    # 1 m cart displacement (gate 4) — and passes only if both stay finite,
    # never peak past 0.5 rad, and settle inside the spec bands (theta:
    # 0.003 rad by 8 s on the lean, x: 0.02 m by 7 s on the displacement).
    # The displacement criterion is the load-bearing one: theta recovery is
    # torque-authoritative and survives +-20 % plant drift for any design
    # that passes the deterministic gates, while displacement settling is
    # margin-limited and genuinely degrades under perturbation.
    if run_mc:
        rng = np.random.default_rng(seed)
        npass = 0
        th_worst = 0.0
        x_worst = 0.0
        tmc = np.linspace(0.0, SIM_T, 501)
        if trace_dir:
            mc_fh = open(os.path.join(trace_dir, "mc_samples.csv"),
                         "w", encoding="utf-8")
            mc_fh.write("sample,M_kg,m_kg,l_m,"
                        "theta_settle_s,x_settle_s,pass\n")
        for i in range(n_mc):
            M_ = M0 * rng.uniform(0.8, 1.2)
            m_ = M1 * rng.uniform(0.8, 1.2)
            l_ = L0 * rng.uniform(0.8, 1.2)
            ok = True
            th_st = 0.0
            x_st = 0.0
            for ic in ((0.0, 0.0, THETA0, 0.0), (XDISP, 0.0, 0.0, 0.0)):
                try:
                    smc = solve_ivp(nonlinear_rhs(K, M_, m_, l_),
                                    [0.0, SIM_T], ic, max_step=0.02,
                                    rtol=1e-7, atol=1e-9,
                                    dense_output=True)
                    Ymc = smc.sol(tmc)
                except Exception:
                    ok = False
                    break
                if not np.all(np.isfinite(Ymc)):
                    ok = False
                    break
                if np.abs(Ymc[2]).max() > PEAK_THETA_MAX:
                    ok = False
                    break
                if ic[0] == 0.0:
                    # lean scenario: SPEC's theta-settling criterion
                    th_st = settling_time(tmc, Ymc[2], THETA_BAND)
                    th_worst = max(th_worst, th_st)
                    if th_st > MC_SETTLE_MAX:
                        ok = False
                        break
                else:
                    # displacement scenario: SPEC's x-settling criterion
                    x_st = settling_time(tmc, Ymc[0], XDISP_BAND)
                    x_worst = max(x_worst, x_st)
                    if x_st > MC_X_SETTLE_MAX:
                        ok = False
                        break
            if trace_dir:
                mc_fh.write("%d,%.10e,%.10e,%.10e,%.10e,%.10e,%d\n"
                            % (i, M_, m_, l_, th_st, x_st, int(ok)))
            if ok:
                npass += 1
        if trace_dir:
            mc_fh.close()
        frac = npass / n_mc
        verdict["mc_pass"] = npass
        verdict["mc_n"] = n_mc
        verdict["mc_seed"] = seed
        verdict["mc_theta_settle_worst_s"] = th_worst
        verdict["mc_x_settle_worst_s"] = x_worst
        gate("mc_pass_fraction", frac, frac >= MC_FRACTION_MIN)

    verdict["passed"] = all(g["pass"] for g in verdict["gates"].values())
    return verdict
