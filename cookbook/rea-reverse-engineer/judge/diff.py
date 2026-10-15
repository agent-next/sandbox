#!/usr/bin/env python3
"""diff.py -- differential test: run the stripped binary and reimpl.py on the
same stdin inputs and compare stdout bytes + exit code, byte for byte.

    diff.py <binary> <reimpl.py> <inputdir> <count>

Prints one line:  "OK <count>"  or  "MISMATCH <i> ..." / "COUNT <n>!=<count>".
Exit 0 iff every input matches.
"""
import os
import subprocess
import sys

TIMEOUT = 10


def run(cmd, data):
    try:
        p = subprocess.run(cmd, input=data, capture_output=True,
                           timeout=TIMEOUT)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return "timeout", b""


def main():
    binary, reimpl, indir = sys.argv[1], sys.argv[2], sys.argv[3]
    count = int(sys.argv[4])
    names = sorted(os.listdir(indir))
    if len(names) != count:
        print("COUNT %d!=%d" % (len(names), count))
        sys.exit(1)
    for i, name in enumerate(names):
        with open(os.path.join(indir, name), "rb") as fh:
            data = fh.read()
        b_rc, b_out = run([binary], data)
        r_rc, r_out = run([sys.executable, reimpl], data)
        if (b_rc, b_out) != (r_rc, r_out):
            print("MISMATCH %d %s: bin=(%r,%r) impl=(%r,%r)"
                  % (i, name, b_rc, b_out[:80], r_rc, r_out[:80]))
            sys.exit(1)
    print("OK %d" % count)


if __name__ == "__main__":
    main()
