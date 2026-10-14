#!/usr/bin/env python3
"""G2 differential driver: random programs on the DUT vs the Python ISS.

For each program i of a run:
  program seed  = gen.program_seed(seed, i)      (deterministic, printed
                                                  on any mismatch)
  the program   = gen coverage block + random filler + epilogue that
                  stores x1..x31 to the signature region then 1 to tohost
  ISS run       = judge/iss.py RV32ISS, in-process (the oracle)
  DUT run       = the Verilator sim built from tb.cpp + the CPU under
                  grade, invoked with --latency --seed <program seed>
                  (random mem_ready latency 0-7, seeded per program)
  comparison    = the 31 signature words (x1..x31) the epilogue stored

Prints one line per program only on failure; a summary at the end.
Exit 0 iff every program agrees (DUT RESULT PASS, tohost==1, and all 31
signature words equal the ISS image).

Usage:
  g2check.py --sim SIM [--seed S] [--count N] [--len L] [--max-cycles C]
             [--no-latency]
"""

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen
import iss
import memh

SIG_WORD0 = gen.SIG_BASE // 4     # word index of x1's slot
SIG_N = 31                        # x1..x31


def sig_of(words):
    return words[SIG_WORD0:SIG_WORD0 + SIG_N]


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sim", required=True, help="Verilator sim binary (tb.cpp)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--len", type=int, default=500)
    p.add_argument("--max-cycles", type=int, default=400000)
    p.add_argument("--no-latency", action="store_true",
                   help="disable the random mem_ready latency")
    a = p.parse_args(argv[1:])

    if not os.path.isfile(a.sim) or not os.access(a.sim, os.X_OK):
        print("error: sim not executable: %s" % a.sim, file=sys.stderr)
        return 2

    work = tempfile.mkdtemp(prefix="g2check.")
    agree = 0
    fails = 0
    for i in range(a.count):
        pseed = gen.program_seed(a.seed, i)
        words = gen.generate(pseed, a.len)

        # ---- oracle: ISS ------------------------------------------------
        m = iss.RV32ISS(words)
        status = m.run()
        if status != "PASS":
            print("   G2: JUDGE ERROR: ISS did not reach tohost==1 "
                  "(program seed=%d, status=%s) - generator/ISS bug, "
                  "not a DUT failure" % (pseed, status))
            fails += 1
            break
        expected = sig_of(m.image())

        # ---- DUT: Verilator sim -----------------------------------------
        hexf = os.path.join(work, "p.hex")
        memh.dump_memh(words, hexf)
        dump = os.path.join(work, "p.dump.hex")
        cmd = [a.sim, "--hex", hexf, "--seed", str(pseed),
               "--max-cycles", str(a.max_cycles), "--dump", dump]
        if not a.no_latency:
            cmd.append("--latency")
        r = subprocess.run(cmd, capture_output=True, text=True)
        line = r.stdout.strip()
        if not line.startswith("RESULT PASS"):
            print("   G2: MISMATCH program seed=%d: DUT '%s' but ISS PASS"
                  % (pseed, line))
            fails += 1
            break
        got = sig_of(memh.load_memh(dump))

        # ---- signature compare ------------------------------------------
        if got != expected:
            for r_ in range(SIG_N):
                if got[r_] != expected[r_]:
                    print("   G2: MISMATCH program seed=%d reg x%d: "
                          "ISS=0x%08x DUT=0x%08x"
                          % (pseed, r_ + 1, expected[r_], got[r_]))
                    break
            fails += 1
            break
        agree += 1
    if fails == 0 and agree == a.count:
        print("   G2: %d/%d programs agree (ISS == DUT signature)"
              % (agree, a.count))
        return 0
    print("   G2: %d/%d programs agree" % (agree, a.count))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
