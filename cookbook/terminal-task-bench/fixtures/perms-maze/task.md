# Task: fix the permissions maze

`work/opt/bench` is a small tool tree whose mode bits are wrong. The runner
`work/opt/bench/bin/run.sh` cannot be executed, its data cannot be read,
and a credential file that was meant to be owner-only is readable by every
account on the box.

Repair the mode bits in place so that:

- `opt/bench/bin/run.sh` executes and prints its token;
- the shell scripts under `opt/bench/bin` and `opt/bench/lib` are
  executable, and `opt/bench/data/input.txt` and `opt/bench/README` are
  readable;
- every directory in the tree is traversable by its owner;
- the credential file `opt/bench/data/private.txt` is **not** readable by
  anyone but its owner;
- the file contents are unchanged — fix modes, not bytes.

The judge runs the runner, then walks the whole tree's modes and
permissions. A blanket `chmod -R` in either direction fails.

Verify with `bash verify.sh "$PWD/work"` (from this directory).
