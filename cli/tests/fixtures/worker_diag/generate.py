"""Extract a minimal, sanitized fixture from a public actions/runner worker log.

Usage: python generate.py /path/to/Worker_20260731-172150-utc.log
Source and format references are in README.md. No credentials are retained.
"""

import json
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
prefix, body = text.split(" INFO Worker] Job message:\n", 1)
message, _ = json.JSONDecoder().raw_decode(body.lstrip())
values = {pair["k"]: pair["v"] for pair in message["contextData"]["github"]["d"]}
replacements = {
    "repository": "acme/app", "run_id": "9", "run_attempt": "2", "sha": "a" * 40,
}
github = message["contextData"]["github"]
github["d"] = [
    {**pair, "v": replacements[pair["k"]]}
    for pair in github["d"] if pair["k"] in replacements
]
assert replacements.keys() <= values.keys()
message = {
    "variables": {"system.github.job": {
        **message["variables"]["system.github.job"], "value": "test",
    }},
    "contextData": {"github": github},
}
fixture = (
    prefix.rsplit("\n", 1)[-1] + " INFO Worker] Job message:\n "
    + json.dumps(message, indent=2)
    + "\n" + next(line for line in text.splitlines()
                  if " INFO Worker] Listening for cancel message" in line) + "\n"
)
Path(__file__).with_name("Worker_20260731-172150-utc.log").write_text(fixture)
