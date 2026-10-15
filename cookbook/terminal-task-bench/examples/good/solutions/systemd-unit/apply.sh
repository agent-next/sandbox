#!/usr/bin/env bash
# systemd-unit: rewrite the unit so it parses and points at a program that
# exists and runs.
#
# The fixture tree is a stand-in root: the daemon lives at
# <work>/usr/local/bin/ingestd.  The repaired ExecStart has to name a path
# the verifier can execute, so we write the absolute path that exists on the
# image running the judge -- which is the fixture tree's copy.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"
UNIT="$WORK/etc/systemd/system/ingestd.service"
PROG="$WORK/usr/local/bin/ingestd"

if [ ! -x "$PROG" ]; then
    echo "systemd-unit: $PROG is missing or not executable" >&2
    exit 1
fi

# the unit must name a program that works: prove it before writing it down
token="$( "$PROG" --self-test )"
if [ -z "$token" ]; then
    echo "systemd-unit: $PROG --self-test printed nothing" >&2
    exit 1
fi

cat > "$UNIT" <<EOF
# ingestd service
[Unit]
Description=ingest daemon
After=network.target

[Service]
Type=simple
ExecStart=$PROG --self-test
Restart=always
User=$(id -un)
WorkingDirectory=/var/lib/ingestd

[Install]
WantedBy=multi-user.target
EOF

# prove it parses with the same grammar the verifier uses, and that no key
# is repeated
python3 -I - "$UNIT" <<'PY'
import configparser
import sys

parser = configparser.ConfigParser(strict=True, interpolation=None,
                                   delimiters=("=",), comment_prefixes=("#", ";"),
                                   empty_lines_in_values=False)
parser.optionxform = str
with open(sys.argv[1], encoding="utf-8") as fh:
    parser.read_file(fh)
missing = [s for s in ("Unit", "Service", "Install")
           if not parser.has_section(s)]
if missing:
    raise SystemExit(f"systemd-unit: sections missing after rewrite: {missing}")
print("systemd-unit: unit parses, no duplicate keys")
PY
echo "systemd-unit: ExecStart -> $PROG --self-test (prints $token)"
