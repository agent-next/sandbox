#!/usr/bin/env bash
# Verifier for task systemd-unit.
#
# Oracle: reference execution + a spec mask over the unit grammar.
#   * the unit file is parsed with the real systemd unit grammar (ini with
#     duplicate keys rejected, which is what systemd does too);
#   * the mask pins the keys the task states, and resolves User against the
#     account database and ExecStart against the filesystem;
#   * then the verifier *executes* the program ExecStart names, with
#     --self-test, and compares stdout with the recorded token.  A unit file
#     that parses but points at the wrong program fails.
set -euo pipefail

WORK="${1:?usage: verify.sh <work-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -I - "$WORK" "$HERE/expected.json" <<'PY'
import configparser
import json
import os
import pwd
import shlex
import stat
import subprocess
import sys

work, exp_path = sys.argv[1], sys.argv[2]
exp = json.load(open(exp_path))
unit_path = os.path.join(work, exp["unit"])
problems = []


def bad(msg):
    problems.append(msg)
    print("FAIL:", msg)


if not os.path.isfile(unit_path):
    bad(f"{exp['unit']} is missing")
    sys.exit(1)

# 1. parse with the systemd grammar: duplicate keys are an error
parser = configparser.ConfigParser(strict=True, interpolation=None,
                                   delimiters=("=",), comment_prefixes=("#", ";"),
                                   empty_lines_in_values=False)
parser.optionxform = str  # keys are case-sensitive in systemd
try:
    with open(unit_path, encoding="utf-8") as fh:
        parser.read_file(fh)
except configparser.Error as exc:
    bad(f"the unit file does not parse: {exc}")
    sys.exit(1)

for section in exp["required_sections"]:
    if not parser.has_section(section):
        bad(f"missing section [{section}]")

service = parser["Service"] if parser.has_section("Service") else {}
for key in exp["required_service_keys"]:
    if key == "WantedBy":
        continue
    if key not in service:
        bad(f"[Service] is missing {key}=")

install = parser["Install"] if parser.has_section("Install") else {}
if "WantedBy" not in install:
    bad("[Install] is missing WantedBy=")

# 2. the mask over the values the task states
if service.get("Type") not in exp["allowed_type"]:
    bad(f"Type={service.get('Type')!r}, expected one of {exp['allowed_type']}")
if service.get("Restart") not in exp["allowed_restart"]:
    bad(f"Restart={service.get('Restart')!r}, "
        f"expected one of {exp['allowed_restart']}")
if install.get("WantedBy") != "multi-user.target":
    bad(f"WantedBy={install.get('WantedBy')!r}, expected multi-user.target")
if service.get("WorkingDirectory") != exp["expected_working_directory"]:
    bad(f"WorkingDirectory={service.get('WorkingDirectory')!r}, "
        f"expected {exp['expected_working_directory']}")

user = service.get("User", "")
try:
    pwd.getpwnam(user)
except KeyError:
    bad(f"User={user!r} is not an account on this image")

# 3. ExecStart must name a real executable, and the first argument must
#    be the self-test flag
argv = shlex.split(service.get("ExecStart", ""))
if not argv:
    bad("ExecStart= is empty")
    sys.exit(1)
prog = argv[0]
# the fixture tree is a stand-in root: /usr/local/bin/ingestd means
# <work>/usr/local/bin/ingestd, exactly as the tree lays it out
prog_abs = (os.path.join(work, prog.lstrip("/")) if os.path.isabs(prog)
            else os.path.join(work, prog))
if not os.path.isfile(prog_abs):
    bad(f"ExecStart names {prog!r}, which does not exist under the tree")
elif not os.access(prog_abs, os.X_OK):
    bad(f"ExecStart names {prog!r}, which is not executable "
        f"(mode {oct(stat.S_IMODE(os.stat(prog_abs).st_mode))})")
if argv[1:] != exp["exec_start_argv"]:
    bad(f"ExecStart arguments are {argv[1:]!r}, "
        f"expected {exp['exec_start_argv']!r}")

# 4. run it: the program the unit names must actually work
if not problems:
    run = subprocess.run([prog_abs, *exp["exec_start_argv"]],
                         capture_output=True, text=True, timeout=30)
    if run.returncode != 0:
        bad(f"{prog} --self-test exited {run.returncode}: "
            f"{run.stderr.strip()[:200]}")
    elif run.stdout.strip() != exp["token"]:
        bad(f"{prog} --self-test printed {run.stdout.strip()!r}, "
            f"expected {exp['token']!r}")

if problems:
    print(f"systemd-unit: {len(problems)} problem(s)")
    sys.exit(1)
print(f"systemd-unit: OK (parses, ExecStart={prog} --self-test works, "
      f"User={user})")
PY
