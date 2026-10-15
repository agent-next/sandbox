# Task: fix the broken unit file

`work/etc/systemd/system/ingestd.service` was hand-edited and no longer
parses: it sets `Restart` twice, its `ExecStart` names a path that does not
exist, and its `User=` names an account this image does not have.

Repair the unit file in place so that:

- it parses: every section and every key appears at most once, and the keys
  `Type`, `ExecStart`, `User`, `WorkingDirectory` are present under
  `[Service]`, with `[Unit]` and `[Install]` present too;
- `ExecStart` names an **existing, executable** file, and the first
  argument after the path is `--self-test`;
- `User` is an account that exists on this image;
- `WantedBy` is `multi-user.target`, `Type` is `simple` or `exec`, and
  `Restart` is `always` or `on-failure`.

There is no systemd on this image, so nothing boots. The judge parses the
file and then **runs** what `ExecStart` names with `--self-test`, so the
program it points at has to actually work.

Verify with `bash verify.sh "$PWD/work"` (from this directory).
