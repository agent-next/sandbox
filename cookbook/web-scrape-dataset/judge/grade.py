#!/usr/bin/env python3
"""Judge for the web-scrape-dataset demo.

Serves a freshly generated fixture, runs the artifact under test against it,
and compares the CSV it produces with the generator's ground truth.

    python3 grade.py <artifact.py> [--seed N] [--json out.json]
                        [--port N] [--workdir DIR] [--timeout SECONDS]

Exit 0 iff every gate passes.

The oracle is judge/fixture.py's ground truth, a closed-form function of the
product index -- never the served HTML. The robots gate is measured from the
server's own request log, so a scraper that fetches a disallowed path and then
simply does not write the row is still killed.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fixture  # noqa: E402  (sibling module; the oracle)
import serve    # noqa: E402  (the request-logging server)

DEFAULT_SEED = fixture.DEFAULT_SEED
DEFAULT_TIMEOUT = 300

CSV_FIELDS = ['sku', 'name', 'price', 'stock', 'weight_kg', 'status', 'notes']


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


class Gate:
    def __init__(self):
        self.results = []

    def check(self, name, ok, detail=None):
        self.results.append({'gate': name, 'pass': bool(ok),
                             'detail': detail if detail is not None else {}})
        return ok


# --------------------------------------------------------------- CSV side --
def load_csv(path):
    """Read the artifact's CSV.

    Returns (rows, error). A CSV we cannot parse is a failed artifact, not a
    crashed judge: the whole response is validated before any row is trusted.
    """
    import csv
    try:
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            missing = [c for c in CSV_FIELDS if c not in header]
            if missing:
                return None, 'CSV missing column(s): %s' % ', '.join(missing)
            rows = []
            for r in reader:
                if r is None:
                    continue
                r = {k: (v or '').strip() for k, v in r.items()
                     if k in CSV_FIELDS}
                rows.append(r)
            return rows, None
    except FileNotFoundError:
        return None, 'no CSV written'
    except Exception as exc:
        return None, 'unreadable CSV: %s: %s' % (type(exc).__name__, exc)


def norm_price(s):
    """Compare money as an integer number of cents, so '12' == '12.0'."""
    try:
        return int(round(float(s) * 100))
    except (TypeError, ValueError):
        return None


def norm_weight(s):
    try:
        return int(round(float(s) * 100))
    except Exception:
        return None


# ------------------------------------------------------------ side: server --
def start_server(root, port):
    """Start the logging server in-process; returns (server, base_url)."""
    handler = serve.LoggingHandler
    handler.log_path = os.path.join(root, 'request_log.jsonl')
    with open(handler.log_path, 'w') as f:
        f.write('')
    # serve the fixture dir: the handler is a SimpleHTTPRequestHandler, so its
    # root is the process cwd when the request is handled
    httpd = _Server(root, ('127.0.0.1', port), handler)
    threading.Thread(target=httpd.serve_forever,
                     kwargs={'poll_interval': 0.05}, daemon=True).start()
    return httpd, 'http://127.0.0.1:%d' % httpd.server_address[1]


class _Server(ThreadingHTTPServer):
    """A ThreadingHTTPServer that serves `root`, whatever the process cwd."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, root, addr, handler):
        self.root = os.path.abspath(root)
        super().__init__(addr, handler)

    def finish_request(self, request, client_address):
        # SimpleHTTPRequestHandler reads the cwd at construction time
        old = os.getcwd()
        os.chdir(self.root)
        try:
            super().finish_request(request, client_address)
        finally:
            os.chdir(old)


def read_request_log(path):
    counts = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                counts[(r['path'], r['ua'])] = counts.get((r['path'], r['ua']), 0) + r['n']
    except FileNotFoundError:
        pass
    return counts


# -------------------------------------------------------------- the judge ---
def run(artifact, seed, timeout, port, workdir, keep_going=False):
    t_start = time.monotonic()
    gates = Gate()
    timing = {}

    art_abs = os.path.abspath(artifact)
    if not os.path.isfile(art_abs):
        print('judge: artifact not found: %s' % artifact, file=sys.stderr)
        return 2

    # ---- build the fixture and serve it -----------------------------------
    fixdir = os.path.join(workdir, 'site')
    os.makedirs(fixdir, exist_ok=True)
    fixture.build(fixdir, seed=seed)

    httpd, base_url = start_server(fixdir, port)
    robot_path = os.path.join(fixdir, 'robots.txt')
    disallowed_prefix = '/internal/'
    try:
        with open(robot_path) as f:
            robots_txt = f.read()
        disallowed = [l.split(':', 1)[1].strip()
                      for l in robots_txt.splitlines()
                      if l.lower().startswith('disallow:')]
    except OSError:
        disallowed = []

    log_path = os.path.join(fixdir, 'request_log.jsonl')

    # ---- judge integrity before any artifact code runs --------------------
    judge_files = sorted(
        p for p in _judge_files()
        if os.path.basename(p) not in ('setup.sh', 'grade.sh', 'selftest.sh',
                                       'RECEIPT.md', 'REPRODUCE.md'))
    hashes_before = {p: sha256(p) for p in judge_files}

    # ---- run the artifact in a copy of the demo dir it cannot mutate ------
    run_dir = os.path.join(workdir, 'run')
    os.makedirs(run_dir, exist_ok=True)
    shutil.copy2(art_abs, os.path.join(run_dir, 'scrape.py'))
    csv_path = os.path.join(run_dir, 'products.csv')

    env = dict(os.environ)
    env['PLAYWRIGHT_BROWSERS_PATH'] = os.environ.get(
        'PLAYWRIGHT_BROWSERS_PATH', os.path.join(os.environ['HOME'], '.web-scrape-dataset'))

    t_run = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, 'scrape.py', '--url', base_url, '--out', csv_path],
            cwd=run_dir, env=env, capture_output=True, text=True, timeout=timeout)
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = None, '', 'timed out after %ds' % timeout
    except Exception as exc:
        rc, out, err = None, '', '%s: %s' % (type(exc).__name__, exc)
    timing['artifact_seconds'] = round(time.monotonic() - t_run, 3)

    httpd.shutdown()
    timing['total_seconds'] = round(time.monotonic() - t_start, 3)

    # ---- read what the server actually saw --------------------------------
    counts = read_request_log(log_path)
    internal_hits = [(p, ua, n) for (p, ua), n in counts.items()
                     if p.startswith(disallowed_prefix)]
    html_hits = [(ua, n) for (p, ua), n in counts.items()
                 if p.endswith('.html') and n > 0]
    urllib_hits = [(p, ua, n) for (p, ua), n in counts.items()
                   if ua.startswith('Python-urllib')]

    truth = fixture.ground_truth(seed)
    by_sku = {r['sku']: r for r in truth}
    truth_skus = set(by_sku)
    malformed_skus = {r['sku'] for r in truth if r['fault']}
    ok_skus = truth_skus - malformed_skus

    # ---- gate 1: runs ------------------------------------------------------
    # the throwaway workdir path is redacted from the captured output: it
    # changes every run, and the verdict JSON has to be reproducible.
    def redact(text):
        return text.replace(run_dir, '<rundir>').replace(workdir, '<workdir>')

    gates.check('runs', rc == 0,
                {'exit_code': rc,
                 'stdout_tail': redact(out).strip().splitlines()[-3:],
                 'stderr_tail': redact(err).strip().splitlines()[-3:]})

    # ---- gate 2: no disallowed paths (measured at the server) ---------------
    gates.check('no_internal_paths', not internal_hits,
                {'robots_txt': robots_txt.strip().splitlines(),
                 'disallowed_prefixes': disallowed,
                 'requests_to_disallowed': internal_hits})

    # ---- gate 3/4/5/6/7/8: the CSV against the oracle ---------------------
    rows, err = load_csv(csv_path)
    gates.check('csv_readable', rows is not None, {'error': err})

    if rows is not None:
        data = [r for r in rows if any(r.get(k) for k in CSV_FIELDS)]
        gates.check('row_count', len(data) == len(truth),
                    {'rows': len(data), 'expected': len(truth)})

        seen = {}
        dups = []
        invented = []
        field_mismatch = []
        missing_ok = []
        bad_flags = []
        by_name = {r0['name']: r0 for r0 in truth}
        for r in data:
            sku = (r.get('sku') or '').strip()
            flags = set(f for f in (r.get('notes') or '').replace(',', ' ').split()
                        if f)
            # place the row in the oracle: by sku, or (for the empty-sku
            # malformed row) by name. An empty sku is a legitimate value here.
            t = by_sku.get(sku) if sku else None
            if t is None:
                t = by_name.get((r.get('name') or '').strip())
                if t is None:
                    if sku:
                        invented.append(sku)
                    else:
                        invented.append('<unnamed row>')
                    continue
                sku = t['sku']
            if sku in seen:
                dups.append(sku)
            seen[sku] = r

            if t['fault']:
                if r.get('status') != 'malformed':
                    bad_flags.append({'sku': sku, 'want_status': 'malformed',
                                      'got_status': r.get('status'),
                                      'got_notes': sorted(flags)})
                elif flags != set(t['expected_notes']):
                    bad_flags.append({'sku': sku,
                                      'want_notes': sorted(t['expected_notes']),
                                      'got_notes': sorted(flags)})
                continue

            if r.get('status') != 'ok':
                bad_flags.append({'sku': sku, 'want_status': 'ok',
                                  'got_status': r.get('status'),
                                  'got_notes': sorted(flags)})
                continue
            diffs = {}
            if r.get('name') != t['name']:
                diffs['name'] = [r.get('name'), t['name']]
            if norm_price(r.get('price')) != norm_price(t['price']):
                diffs['price'] = [r.get('price'), t['price']]
            if r.get('stock') != t['stock']:
                diffs['stock'] = [r.get('stock'), t['stock']]
            if norm_weight(r.get('weight_kg')) != norm_weight(t['weight_kg']):
                diffs['weight_kg'] = [r.get('weight_kg'), t['weight_kg']]
            if diffs:
                field_mismatch.append({'sku': sku, 'fields': diffs})
        # every non-malformed product must be present *as ok*: a scraper that
        # flags the whole catalogue malformed (e.g. it read the pre-JS price
        # placeholder everywhere) has a row for each SKU but no usable data,
        # and field_exact alone would never look at those rows.
        for s in sorted(ok_skus):
            if s not in seen:
                missing_ok.append({'sku': s, 'why': 'absent'})
            elif seen[s].get('status') != 'ok':
                missing_ok.append({'sku': s, 'why': 'status=%s'
                                   % (seen[s].get('status') or ''),
                                   'notes': (seen[s].get('notes') or '').strip()})

        gates.check('field_exact', not field_mismatch,
                    {'mismatches': field_mismatch[:10],
                     'n_mismatches': len(field_mismatch)})
        gates.check('no_missing_ok', not missing_ok,
                    {'problems': sorted(missing_ok, key=lambda d: d['sku'])[:10],
                     'n': len(missing_ok)})
        gates.check('malformed_flagged', not bad_flags,
                    {'problems': bad_flags[:10], 'n': len(bad_flags),
                     'expected': {s: sorted(by_sku[s]['expected_notes'])
                                  for s in sorted(malformed_skus)}})
        gates.check('no_dup_rows', not dups, {'duplicated_skus': sorted(dups)})
        gates.check('no_invented', not invented,
                    {'invented': sorted(set(invented))})
    else:
        for name in ('field_exact', 'no_missing_ok', 'malformed_flagged',
                     'no_dup_rows', 'no_invented', 'row_count'):
            gates.check(name, False, {'reason': 'no CSV to compare'})

    # ---- gate 9: used a browser (not a bare urllib fetch) ------------------
    non_urllib = [(ua, n) for ua, n in html_hits
                  if not ua.startswith('Python-urllib')]
    gates.check('used_browser', bool(non_urllib),
                {'user_agents_seen': sorted({ua for (_, ua) in counts.keys()}),
                 'html_requests_non_urllib': non_urllib[:5]})

    # ---- gate 10: the artifact did not touch the judge ---------------------
    hashes_after = {p: sha256(p) for p in judge_files}
    changed = [p for p in judge_files if hashes_before.get(p) != hashes_after.get(p)]
    gates.check('judge_integrity', not changed,
                {'files_changed': [os.path.relpath(p, HERE) for p in changed]})

    verdict = {
        'pass': all(r['pass'] for r in gates.results),
        'artifact': os.path.relpath(art_abs, os.path.dirname(HERE)),
        'seed': seed,
        'base_url': base_url,
        'truth': {'products': len(truth), 'ok': len(ok_skus),
                  'malformed': len(malformed_skus),
                  'malformed_skus': sorted(malformed_skus)},
        'requests_seen': {'total': sum(counts.values()),
                          'distinct_paths': len(counts),
                          'to_disallowed': len(internal_hits)},
        'gates': gates.results,
        'timing': timing,
    }
    return verdict


def _judge_files():
    for dirpath, dirnames, filenames in os.walk(HERE):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('artifact')
    ap.add_argument('--seed', type=int, default=DEFAULT_SEED)
    ap.add_argument('--json')
    ap.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--workdir')
    args = ap.parse_args()

    workdir = args.workdir or tempfile.mkdtemp(prefix='wsd-grade-')
    os.makedirs(workdir, exist_ok=True)
    verdict = run(args.artifact, args.seed, args.timeout, args.port, workdir)

    if isinstance(verdict, int):
        return verdict
    for r in verdict['gates']:
        print("%-18s %-4s %s" % (r['gate'], 'PASS' if r['pass'] else 'FAIL',
                                 '' if r['pass'] else json.dumps(r['detail'])))
    print(json.dumps(verdict, indent=2))
    if args.json:
        d = os.path.dirname(os.path.abspath(args.json))
        os.makedirs(d, exist_ok=True)
        with open(args.json, 'w') as f:
            json.dump(verdict, f, indent=2, sort_keys=True)
            f.write('\n')
    return 0 if verdict['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
