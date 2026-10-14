#!/usr/bin/env python3
"""Independent judge for the tank controller demo (cookbook/plc-st).

Usage:
    JUDGE_DIR=...    directory containing harness.c (default: this file's dir)
    judge.py <build_dir> [--json out.json] [--seed N] [--trace DIR]

Runs a set of deterministic scenarios against a compiled scan-cycle engine and
checks numeric safety / liveness / recovery properties. The plant is an
analytic tank model integrated per scan (an independent oracle from the
controller's own logic).

The engine is compiled separately by grade.sh into $build_dir/engine:
    $build_dir/tank_ctrl.st  (the artifact under test)
    $build_dir/engine        (harness.c + generated C)

Exit 0 iff every scenario passes; otherwise exit 1 and print failures.
"""
import subprocess
import sys
import json
import os
import random
import csv

# --------------------------------------------------------------------------
# plant parameters (cm, s)
# --------------------------------------------------------------------------
DT = 0.010               # scan period = 10 ms
FILL_RATE = 2.0          # cm/s while inlet open
DRAIN_RATE = 3.0         # cm/s while pump + outlet open
HIGH_SET = 85.0          # cm high switch trips
LOW_SET = 15.0           # cm low switch trips
LEVEL_MAX = 100.0
LEVEL_MIN = 0.0
DRY_BAND = 15.0          # below this the pump must never run
OVERFILL = 88.0          # analog overflow guard point
DESIGN_CAP = 94.0        # hard limit never exceeded in any scenario
MAX_STEPS = 12000        # 120 s


def _here():
    return os.path.dirname(os.path.abspath(__file__))


class Plant:
    def __init__(self, level0=50.0):
        self.level = level0

    def step(self, pump, inlet, outlet, estop):
        if estop:
            return
        if inlet:
            self.level += FILL_RATE * DT
        if pump and outlet:
            self.level -= DRAIN_RATE * DT
        self.level = max(LEVEL_MIN, min(LEVEL_MAX, self.level))

    def sensors(self, high_override=None, low_override=None):
        return {
            'high_ls': float(high_override if high_override is not None
                             else (self.level >= HIGH_SET)),
            'low_ls':  float(low_override if low_override is not None
                             else (self.level <= LOW_SET)),
        }


def run_scenario(engine, events, level0=50.0, max_steps=MAX_STEPS,
                 high_override_map=None, low_override_map=None, trace_path=None):
    """events: list of (scan_index, {input:value}).
    override_maps: list of (start, end, forced_value) applied to that sensor
    for that scan window -- deterministic sensor faults.
    trace_path: if provided, write CSV trace of (t, level, pump, valve_in, valve_out, estop, alarms)"""
    plant = Plant(level0)
    cur = {'start': 0, 'estop': 0}
    ev = {}
    eidx = 0
    outs = []
    trace_f = None
    trace_writer = None
    if trace_path:
        trace_f = open(trace_path, 'w', newline='')
        trace_writer = csv.writer(trace_f)
        trace_writer.writerow(['t', 'level', 'pump', 'valve_in', 'valve_out', 'estop', 'alarms'])
    for k in range(max_steps):
        if eidx < len(events) and events[eidx][0] == k:
            ev = events[eidx][1]
            eidx += 1
        if 'start' in ev:
            cur['start'] = ev['start']
        if 'estop' in ev:
            cur['estop'] = ev['estop']
        hi = lo = None
        for ks, ke, val in (high_override_map or []):
            if ks <= k < ke:
                hi = val
                break
        for ks, ke, val in (low_override_map or []):
            if ks <= k < ke:
                lo = val
                break
        s = plant.sensors(hi, lo)
        line = "%d %d %d %d %.4f\n" % (cur['start'], cur['estop'],
                                       int(s['high_ls']), int(s['low_ls']),
                                       plant.level)
        engine.stdin.write(line)
        engine.stdin.flush()
        out = engine.stdout.readline()
        if not out:
            break
        try:
            p, iv, ov, al, run = (int(x) for x in out.split())
        except ValueError:
            break
        outs.append({'k': k, 'pump': p, 'inlet': iv, 'outlet': ov,
                     'alarm': al, 'running': run, 'level': plant.level,
                     'estop': cur['estop']})
        if trace_writer:
            t = k * DT
            trace_writer.writerow([f'{t:.3f}', f'{plant.level:.3f}', p, iv, ov, cur['estop'], al])
        plant.step(p, iv, ov, cur['estop'])
    if trace_f:
        trace_f.close()
    return outs


def check_all(outs, gates):
    return [label for label, p in gates if not p(outs)]


# ---------------------------------------------------------------- gates ---
def max_level_gate(cap=DESIGN_CAP):
    return ('max_level<=%.0f' % cap,
            lambda o: max(x['level'] for x in o) <= cap)


def pump_never_dry_gate():
    return ('pump_never_dry',
            lambda o: all(not (x['pump'] and x['level'] < DRY_BAND) for x in o))


def no_pump_inlet_gate():
    return ('no_pump_inlet',
            lambda o: all(not (x['pump'] and x['inlet']) for x in o))


def autocycle_gate(min_cycles=2):
    """Tank must complete min_cycles full fill-phases: rise from below 25 to
    above 80 at least min_cycles times."""
    def count(o):
        n, below = 0, True
        for x in o:
            if below and x['level'] > 80.0:
                n += 1
                below = False
            elif x['level'] < 25.0:
                below = True
        return n
    return ('autocycle>=%d' % min_cycles, lambda o: count(o) >= min_cycles)


def estop_off_gate(hold_from):
    return ('estop_off_from_%d' % hold_from,
            lambda o: all(not (x['pump'] or x['inlet'] or x['outlet'])
                          for x in o if x['k'] >= hold_from))


def no_actuation_between_gate(a, b):
    return ('no_actuation_%d_%d' % (a, b),
            lambda o: all(not (x['pump'] or x['inlet'] or x['outlet'])
                          for x in o if a <= x['k'] < b))


def recovers_gate(tail=300):
    return ('recovers', lambda o: any(x['running'] for x in o[-tail:]))


def pump_stops_within_gate(trip_scan, window=200):
    def pred(o):
        after = [x for x in o if x['k'] >= trip_scan]
        return bool(after) and all(not x['pump'] for x in after[:window])
    return ('pump_stops_within_%d' % window, pred)


def build_scenarios(seed=20261014):
    sc = []

    # 1. normal autocycle
    ev = [(0, {'start': 1}), (1, {'start': 0})]
    sc.append(('cycle', ev, 40.0, [
        max_level_gate(),
        pump_never_dry_gate(),
        no_pump_inlet_gate(),
        autocycle_gate(2),
    ], {}))

    # 2. high level switch jammed open: analog overflow guard is the only backstop
    sc.append(('overflow_guard', ev, 70.0, [
        max_level_gate(),
        pump_never_dry_gate(),
        no_pump_inlet_gate(),
    ], {'high_over': [(0, MAX_STEPS, 0.0)]}))

    # 3. start dry; pump must never run below the band and must cycle
    sc.append(('dry_run', ev, 10.0, [
        pump_never_dry_gate(),
        max_level_gate(),
        no_pump_inlet_gate(),
        autocycle_gate(2),
    ], {}))

    # 4. low switch jammed open: analog dry-run interlock is the only backstop
    sc.append(('dry_interlock_fault', ev, 40.0, [
        pump_never_dry_gate(),
        max_level_gate(),
        no_pump_inlet_gate(),
    ], {'low_over': [(0, MAX_STEPS, 0.0)]}))

    # 5. low switch falsely trips (stuck 1) while draining: pump must stop fast
    def sc_lowsw_false_trip():
        # trip at scan 1000: tank was ~63 cm, pump actively running
        events = [(0, {'start': 1}), (1, {'start': 0}), (1000, {'x': 1})]
        gates = [
            pump_stops_within_gate(1000, 200),
            pump_never_dry_gate(),
            max_level_gate(),
        ]
        return ('lowsw_false_trip', events, 80.0, gates,
                {'low_over': [(1000, MAX_STEPS, 1.0)]})
    sc.append(sc_lowsw_false_trip())

    # 6. E-stop mid-fill: everything off within one scan and stays off
    sc.append(('estop', [(0, {'start': 1}), (1, {'start': 0}),
                         (400, {'estop': 1})], 40.0,
               [estop_off_gate(401), max_level_gate()], {}))

    # 7. recovery after E-stop release
    sc.append(('recovery',
               [(0, {'start': 1}), (1, {'start': 0}),
                (400, {'estop': 1}), (500, {'estop': 0}),
                (700, {'start': 1}), (701, {'start': 0})], 40.0,
               [no_actuation_between_gate(500, 700),
                recovers_gate(),
                max_level_gate()], {}))

    # 8. seeded random sensor / E-stop faults while running
    rng = random.Random(seed)
    high_over, low_over, evf = [], [], {}
    evf[0] = evf.get(0, {}); evf[0]['start'] = 1
    evf[1] = evf.get(1, {}); evf[1]['start'] = 0
    t = 200
    while t < MAX_STEPS - 400:
        kind = rng.choice(['estop_pulse', 'high_stuck1', 'high_stuck0',
                           'low_stuck1', 'low_stuck0'])
        dur = rng.randint(200, 600)
        if kind == 'estop_pulse':
            evf.setdefault(t, {})['estop'] = 1
            evf.setdefault(t + dur, {})['estop'] = 0
        elif kind == 'high_stuck1':
            high_over.append((t, t + dur, 1.0))
        elif kind == 'high_stuck0':
            high_over.append((t, t + dur, 0.0))
        elif kind == 'low_stuck1':
            low_over.append((t, t + dur, 1.0))
        else:
            low_over.append((t, t + dur, 0.0))
        t += dur + rng.randint(100, 300)
    sc.append(('random_faults', list(evf.items()), 40.0, [
        pump_never_dry_gate(),
        max_level_gate(),
        no_pump_inlet_gate(),
    ], {'high_over': high_over, 'low_over': low_over}))

    return sc


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    build_dir = sys.argv[1]
    json_path = None
    seed = 20261014
    trace_dir = None
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--json':
            json_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--seed':
            seed = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--trace':
            trace_dir = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    exe = os.path.join(build_dir, 'engine')
    if not os.path.exists(exe):
        print(f'judge: engine not found at {exe} (run grade.sh first)', file=sys.stderr)
        return 2
    scenarios = build_scenarios(seed=seed)
    allok = True
    results = []
    for name, events, lvl0, gates, over in scenarios:
        engine = subprocess.Popen([exe], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, bufsize=1)
        trace_path = None
        if trace_dir:
            trace_path = os.path.join(trace_dir, f'trace_{name}.csv')
        outs = run_scenario(engine, events, level0=lvl0,
                            high_override_map=over.get('high_over'),
                            low_override_map=over.get('low_over'),
                            trace_path=trace_path)
        engine.stdin.close()
        engine.wait()
        if len(outs) < MAX_STEPS:
            fails = [f'engine stopped after {len(outs)} of {MAX_STEPS} scans']
        else:
            fails = check_all(outs, gates)
        ok = not fails
        allok = allok and ok
        results.append({'name': name, 'pass': ok, 'failures': fails,
                        'n_scans': len(outs),
                        'min_level': min(o['level'] for o in outs) if outs else None,
                        'max_level': max(o['level'] for o in outs) if outs else None})
        print(f"{name}: {'PASS' if ok else 'FAIL'} {fails}")

    verdict = {'pass': allok, 'scenarios': len(results),
               'results': results}
    if json_path:
        with open(json_path, 'w') as f:
            json.dump(verdict, f, indent=2)
    print(json.dumps(verdict, indent=2))
    return 0 if allok else 1


if __name__ == '__main__':
    sys.exit(main())