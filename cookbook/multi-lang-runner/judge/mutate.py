#!/usr/bin/env python3
"""Single-edit mutants of examples/good/ for the multi-lang-runner judge.

Each mutant applies one copy() call that breaks one solution file with a
small, language-appropriate edit (a wrong cap, a swapped argument, a
dropped newline). A judge that passes any of them has missed a real
behavioral deviation, so every mutant must fail at least one gate.

Usage:
    mutate.py <good_root> <outdir>     writes <name>/ tree for each mutant
    mutate.py --list                   prints names + one-line description
"""
import os
import shutil
import sys

# Each mutation: (name, relative file path, old, new, description).
MUTATIONS = [
    # --- python ---
    ('python_sumsq_wrong_cap',
     'solutions/python/sumsq.py',
     'total > 10 ** 18:\n            total = 10 ** 18',
     'total > 10 ** 17:\n            total = 10 ** 17',
     'sumsq cap lowered to 10^17: capped sums print one digit too few'),
    ('python_rle_no_trailing_newline',
     'solutions/python/rle.py',
     'sys.stdout.write("".join(out) + "\\n")',
     'sys.stdout.write("".join(out))',
     'rle output loses its trailing newline: byte compare fails'),
    ('python_primes_off_by_one',
     'solutions/python/primes.py',
     'sieve[i * i::i] = bytearray(len(sieve[i * i::i]))',
     'sieve[i * i::i] = bytearray(len(sieve[i * i::i]) - 1)',
     'sieve clears one entry too few: a composite survives into the count'),
    # --- node ---
    ('node_sumsq_wrong_cap',
     'solutions/node/sumsq.js',
     'const CAP = 1000000000000000000n;',
     'const CAP = 100000000000000000n;',
     'sumsq cap lowered: capped sums print wrong'),
    ('node_rle_no_trailing_newline',
     'solutions/node/rle.js',
     "process.stdout.write(out + '\\n');",
     'process.stdout.write(out);',
     'rle output loses its trailing newline'),
    ('node_primes_off_by_one',
     'solutions/node/primes.js',
     'for (let j = i * i; j <= hi; j += i) sieve[j] = 0;',
     'for (let j = i * i; j <= hi; j += 2 * i) sieve[j] = 0;',
     'sieve steps by 2*i: odd multiples of i stay prime'),
    # --- go ---
    ('go_sumsq_wrong_cap',
     'solutions/go/sumsq.go',
     'if total > 1_000_000_000_000_000_000 {',
     'if total > 1_000_000_000_000_000_00 {',
     'sumsq cap lowered: capped sums print wrong'),
    ('go_rle_no_trailing_newline',
     'solutions/go/rle.go',
     'fmt.Fprintln(w)',
     'fmt.Fprint(w, "")',
     'rle output loses its trailing newline'),
    ('go_primes_off_by_one',
     'solutions/go/primes.go',
     'for j := i * i; j <= hi; j += i {',
     'for j := i * i; j <= hi; j += 2 * i {',
     'sieve steps by 2*i: odd multiples of i stay prime'),
    # --- rust ---
    ('rust_sumsq_wrong_cap',
     'solutions/rust/sumsq.rs',
     'if total > 1_000_000_000_000_000_000 {',
     'if total > 1_000_000_000_000_000_00 {',
     'sumsq cap lowered: capped sums print wrong'),
    ('rust_rle_no_trailing_newline',
     'solutions/rust/rle.rs',
     "out.push('\\n');",
     "out.push(' ');",
     'rle output ends in a space instead of a newline'),
    ('rust_primes_off_by_one',
     'solutions/rust/primes.rs',
     'while j <= hi {\n                sieve[j] = true;\n                j += i;',
     'while j <= hi {\n                sieve[j] = true;\n                j += 2 * i;',
     'sieve steps by 2*i: odd multiples of i stay prime'),
    # --- bash ---
    ('bash_sumsq_wrong_cap',
     'solutions/bash/sumsq.sh',
     'cap=1000000000000000000',
     'cap=100000000000000000',
     'sumsq cap lowered: capped sums print wrong'),
    ('bash_rle_no_trailing_newline',
     'solutions/bash/rle.sh',
     'echo "$out"',
     'printf \'%s\' "$out"',
     'rle output loses its trailing newline'),
    ('bash_primes_off_by_one',
     'solutions/bash/primes.sh',
     'awk \'NF == 2 { n++ } END { print n + 0 }\'',
     'awk \'NF == 1 { n++ } END { print n + 0 }\'',
     'primes counts empty lines instead of prime lines: always 0'),
    # --- c ---
    ('c_sumsq_wrong_cap',
     'solutions/c/sumsq.c',
     'long long cap = 1000000000000000000LL;',
     'long long cap = 100000000000000000LL;',
     'sumsq cap lowered: capped sums print wrong'),
    ('c_rle_no_trailing_newline',
     'solutions/c/rle.c',
     'printf("%d%c\\n", count, prev);',
     'printf("%d%c", count, prev);',
     'rle output loses its trailing newline'),
    ('c_primes_off_by_one',
     'solutions/c/primes.c',
     'for (int j = i * i; j <= hi; j += i) sieve[j] = 1;',
     'for (int j = i * i; j <= hi; j += 2 * i) sieve[j] = 1;',
     'sieve steps by 2*i: odd multiples of i stay prime'),
]


def list_mutations():
    for name, path, _old, _new, desc in MUTATIONS:
        print(f'{name}: {desc}  [{path}]')
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if sys.argv[1] == '--list':
        return list_mutations()
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    good_root, outdir = sys.argv[1], sys.argv[2]
    if not os.path.isdir(good_root):
        print(f'mutate: good root not found: {good_root}', file=sys.stderr)
        return 2
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    written = 0
    for name, relpath, old, new, desc in MUTATIONS:
        src = os.path.join(good_root, relpath)
        if not os.path.isfile(src):
            print(f'mutate: source missing for {name}: {src}', file=sys.stderr)
            return 2
        text = open(src).read()
        if old not in text:
            print(f'mutate: pattern not found for {name} in {src}', file=sys.stderr)
            return 2
        mutant_root = os.path.join(outdir, name)
        shutil.copytree(good_root, mutant_root)
        target = os.path.join(mutant_root, relpath)
        with open(target, 'w') as f:
            f.write(text.replace(old, new, 1))
        written += 1
    print(f'mutate: wrote {written} mutants to {outdir}/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
