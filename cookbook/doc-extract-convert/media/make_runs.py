#!/usr/bin/env python3
"""Produce the real runs media/demo.mp4 draws from.

The video must show real pixels from the corpus the judge grades and the
JSON the extractor actually wrote -- no illustrative data.  This script
reproduces exactly what judge/grade.sh does to build those runs, at the
seed the demo is pinned to, and leaves them under media/data/:

    media/data/corpus/          judge/fixtures.py --seed 42 --out
    media/data/extract/         examples/good/extract.py on the clean corpus
    media/data/corrupt/         judge/corrupt.py --which b0,b1
    media/data/extract-corrupt/ examples/good/extract.py on the corrupted one
    media/data/truth.json       the generator's answer key, byte-for-byte

Nothing here re-implements a judge rule: it calls the judge's own modules,
so the frames are the same bytes the gates were measured over.

Usage:  python3 media/make_runs.py            (Writes ~1 MB, git-ignored)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
JUDGE = os.path.join(DEMO, "judge")
DATA = os.path.join(HERE, "data")

sys.path.insert(0, JUDGE)

import corrupt as corrupt_mod          # noqa: E402  (the judge's own module)
import fixtures as fixtures_mod        # noqa: E402


def run(artifact, pages_dir, out_dir, seed):
    """Run the extractor exactly as check_gates.run_extractor does."""
    import subprocess
    cmd = [sys.executable, os.path.join(artifact, "extract.py"),
           "--in", pages_dir, "--out", out_dir, "--seed", str(seed)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    corpus = os.path.join(DATA, "corpus")
    extract = os.path.join(DATA, "extract")
    corrupt_dir = os.path.join(DATA, "corrupt")
    extract_corrupt = os.path.join(DATA, "extract-corrupt")
    for d in (corpus, extract, corrupt_dir, extract_corrupt):
        os.makedirs(d, exist_ok=True)

    print("[runs] generating the corpus (seed %d)" % seed)
    truth = fixtures_mod.generate(seed, corpus)

    print("[runs] running the known-good extractor (clean corpus)")
    rc, log = run(os.path.join(DEMO, "examples", "good"),
                  os.path.join(corpus, "pages"), extract, seed)
    assert rc == 0, log[-2000:]
    recs = json.load(open(os.path.join(extract, "records.json")))
    quar = json.load(open(os.path.join(extract, "quarantine.json")))
    print("[runs]   records=%d quarantined=%d"
          % (len(recs["pages"]), len(quar["pages"])))

    print("[runs] corrupting (b0 blank, b1 smear) and re-running")
    meta = corrupt_mod.corrupt(corpus, corrupt_dir, ("b0", "b1"), seed)
    rc, log = run(os.path.join(DEMO, "examples", "good"),
                  os.path.join(corrupt_dir, "pages"), extract_corrupt, seed)
    assert rc == 0, log[-2000:]
    cq = json.load(open(os.path.join(extract_corrupt, "quarantine.json")))
    print("[runs]   corrupted pages: %s"
          % ", ".join(m["page_id"] for m in meta))
    print("[runs]   quarantined on the corrupt run: %s"
          % ", ".join(q["page_id"] for q in cq["pages"]))

    with open(os.path.join(DATA, "truth.json"), "w") as f:
        json.dump(truth, f, indent=2)
        f.write("\n")
    print("[runs] wrote media/data/{corpus,extract,corrupt,extract-corrupt}")


if __name__ == "__main__":
    main()
