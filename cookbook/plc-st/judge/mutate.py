#!/usr/bin/env python3
"""Single-edit textual mutants of examples/good/tank_ctrl.st.

Each mutant flips one line/condition of the known-good controller, so a judge
that fails on it has caught a real single-token behavioral deviation.

Usage:
    mutate.py <good.st> <outdir>     writes <name>.st for each mutant
    mutate.py --list                 prints names + one-line description
"""
import sys
import os

MUTATIONS = [
    ('inverted_dryrun',
     'IF level < 15.0 OR low_ls THEN',
     'IF level > 15.0 OR low_ls THEN',
     'dry-run interlock inverted: pump shutdown fires only above the band'),

    ('missing_estop_latch',
     'IF estop THEN\n    stop_latch := TRUE;\n  END_IF;',
     'IF FALSE THEN\n    stop_latch := TRUE;\n  END_IF;',
     'E-stop no longer latches the stop state'),

    ('swapped_valves',
     'IF mode_fill THEN\n      inlet_valve  := TRUE;\n      pump         := FALSE;\n      outlet_valve := FALSE;\n    ELSE\n      inlet_valve  := FALSE;\n      IF level > 15.0 AND NOT low_ls THEN\n        pump         := TRUE;\n        outlet_valve := TRUE;',
     'IF mode_fill THEN\n      inlet_valve  := TRUE;\n      pump         := FALSE;\n      outlet_valve := FALSE;\n    ELSE\n      outlet_valve := FALSE;\n      IF level > 15.0 AND NOT low_ls THEN\n        pump         := TRUE;\n        inlet_valve := TRUE;',
     'drain mode energizes the inlet valve instead of the outlet (fills while draining)'),

    ('missing_overflow_guard',
     'IF level > 88.0 THEN\n      inlet_valve := FALSE;   (* overflow guard: hard cap even if switch lies *)',
     'IF level > 88.0 THEN\n      inlet_valve := inlet_valve;   (* overflow guard *)',
     'overflow guard no longer closes the inlet (tank can exceed the design cap)'),

    ('no_dry_restart',
     'IF low_ls THEN\n      mode_fill := TRUE;    (* tank dry: start filling *)',
     'IF low_ls THEN\n      mode_fill := mode_fill;    (* tank dry: start filling *)',
     'low switch no longer restarts filling (controller stuck in drain)'),

    ('estop_not_safe',
     'IF stop_latch OR fault_latch THEN',
     'IF fault_latch THEN',
     'E-stop no longer forces the safe hold branch'),
]


def apply(src, old, new):
    assert old in src, f'pattern not found: {old[:60]!r}'
    return src.replace(old, new, 1)


def main():
    if sys.argv[1] == '--list':
        for name, _, _, desc in MUTATIONS:
            print(f'{name}: {desc}')
        return 0
    good, outdir = sys.argv[1], sys.argv[2]
    src = open(good).read()
    os.makedirs(outdir, exist_ok=True)
    for name, old, new, desc in MUTATIONS:
        mutant = apply(src, old, new)
        with open(os.path.join(outdir, name + '.st'), 'w') as f:
            f.write(mutant)
        print(f'{name}: {desc}')
    print(f'wrote {len(MUTATIONS)} mutants to {outdir}/')
    return 0


if __name__ == '__main__':
    sys.exit(main())