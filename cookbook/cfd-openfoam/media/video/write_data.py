#!/usr/bin/env python3
"""Write media/clips/data.json — the Remotion props — from THIS run's
judge verdict JSONs.  Every number on screen traces to a verdict file;
nothing is hand-edited.

Usage: write_data.py <replay_dir> <clips_dir>
"""
import glob
import json
import os
import sys


def load(p):
    with open(p) as f:
        return json.load(f)


def _gate_rows(cav, poi):
    """Five unique gate rows across both verdicts, display names."""
    seen, rows = set(), []
    for v in (poi, cav):
        for g in v['gates']:
            n = g['name'].replace('Poiseuille mesh convergence',
                                  'Mesh convergence')
            if n in seen:
                continue
            seen.add(n)
            rows.append((n, bool(g['passed'])))
    return rows


def gate(v, n):
    for g in v['gates']:
        if g['gate'] == n:
            return g
    raise KeyError('gate %d not in verdict' % n)


def main():
    replay, clips = sys.argv[1], sys.argv[2]
    cav = load(os.path.join(replay, 'verdicts/04_cavity_good.json'))
    poi = load(os.path.join(replay, 'verdicts/05_poiseuille_good.json'))

    res = gate(cav, 2)['details']['final_initial_residuals']
    resid = max(res.values())
    cells = gate(cav, 1)['details']['cells']
    g3 = gate(poi, 3)['details']
    g4 = gate(poi, 4)['details']
    g5 = gate(cav, 5)['details']

    mutants = sorted(glob.glob(os.path.join(replay, 'mutants/*.json')))
    kills = sum(1 for m in mutants
                if not load(m)['all_gates_passed'])

    wall = sum(load(v).get('timing', {}).get('wall_seconds', 0)
               for v in glob.glob(os.path.join(replay, 'verdicts/*.json')))
    wall += sum(load(m).get('timing', {}).get('wall_seconds', 0)
               for m in mutants)

    data = {
        'clips': {
            'hook': 'hook.mp4',
            'develop': 'develop.mp4',
            'closeup': 'closeup.mp4',
            'agent': 'agent.mp4',
            'proof': 'proof.mp4',
            'verdict': 'verdict.mp4',
            'endcardStill': 'endcard_still.jpg',
        },
        'hud': {
            'residFinal': '%.1e' % resid,
            'cellCount': str(int(cells[0] * cells[1] * cells[2])),
            'l2': '%.4f' % g3['l2_error'],
            'orders': '%.2f / %.2f' % tuple(g4['orders'][:2]),
            'ghiaU': '%.4f' % g5['max_u_error'],
            'ghiaV': '%.4f' % g5['max_v_error'],
            'kills': '%d/%d' % (kills, len(mutants)),
            'continuity': '%.1e'
                % gate(cav, 2)['details']['global_continuity_error'],
            'tEnd': '30',
        },
        'agent': {
            'wallSeconds': int(round(wall)),
            # wall-clock of all judge runs / the 5 s on-screen segment
            'speed': '%dx' % max(1, round(wall / 5.0)),
        },
        'verdict': {
            'pass': bool(cav['all_gates_passed']
                         and poi['all_gates_passed']),
            'gates': [
                {'name': n, 'ok': ok}
                for n, ok in _gate_rows(cav, poi)
            ],
        },
    }
    os.makedirs(clips, exist_ok=True)
    out = os.path.join(clips, 'data.json')
    with open(out, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print('[data] wrote %s — wall %d s, kills %s, l2 %s'
          % (out, data['agent']['wallSeconds'], data['hud']['kills'],
             data['hud']['l2']))


if __name__ == '__main__':
    main()
