"""Record sanitized, real GitHub Actions API fixtures. Requires authenticated gh.

python cli/scripts/record_runner_stats.py --repo OWNER/REPO --run ID --output FILE

Only timing/status fields survive unchanged. Repository, job, step and runner
names and IDs are replaced, and labels are allowlisted, before anything is saved.
Raw responses are hashed in memory, never written or printed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone


def api(endpoint):
    result = subprocess.run(
        ["gh", "api", "-H", "X-GitHub-Api-Version: 2022-11-28", endpoint],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise SystemExit("GitHub API recording failed; check gh authentication and Actions read access")
    return json.loads(result.stdout), hashlib.sha256(result.stdout).hexdigest()


def select(item, keys):
    return {key: item.get(key) for key in keys}


def record(repo, run_id, prefix, serve_log=None):
    run, digest = api(f"repos/{repo}/actions/runs/{run_id}")
    attempt = run["run_attempt"]
    out = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "api_version": "2022-11-28",
        "sanitization": "Names and IDs replaced; labels allowlisted; timing/status unchanged.",
        "source_sha256": [digest],
        "run": {**select(run, ("status", "conclusion", "created_at", "run_attempt")), "id": 1},
        "jobs_pages": [],
    }
    page, index, aliases = 1, 0, {}
    allowed = {"self-hosted", "sbx", "linux", "x64", "ubuntu-latest",
               "small", "standard", "sbx-small", "sbx-standard"}
    while True:
        body, digest = api(
            f"repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=5&page={page}"
        )
        out["source_sha256"].append(digest)
        jobs = []
        for job in body["jobs"]:
            index += 1
            name = job.get("runner_name") or ""
            runner = (f"sbx-{index:08x}" if name.startswith(prefix) else
                      f"GitHub Actions {index}" if name.startswith("GitHub Actions") else
                      f"other-{index}" if name else "")
            if name.startswith(prefix):
                aliases[name] = runner
            steps = [
                {**select(step, ("number", "status", "conclusion", "started_at", "completed_at")),
                 "name": f"Step {step['number']}"}
                for step in job.get("steps", [])
            ]
            jobs.append({
                **select(job, ("status", "conclusion", "created_at", "started_at",
                               "completed_at", "run_attempt")),
                "id": index, "run_id": 1, "name": f"Job {index}", "runner_name": runner,
                "labels": [label for label in job.get("labels", []) if label.lower() in allowed],
                "steps": steps,
            })
        out["jobs_pages"].append({"total_count": body["total_count"], "jobs": jobs})
        if len(body["jobs"]) < 5:
            break
        page += 1
    if serve_log:
        raw = serve_log.read_bytes()
        out["serve_log_sha256"] = hashlib.sha256(raw).hexdigest()
        out["serve_events"] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("runner") in aliases and event.get("event") in {
                "spawn", "sandbox", "online", "killed",
            }:
                out["serve_events"].append({
                    **{key: event[key] for key in ("event", "t", "create_s", "boot_s") if key in event},
                    "runner": aliases[event["runner"]],
                })
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--prefix", default="sbx-")
    parser.add_argument("--serve-log", type=Path, help="also record sanitized lifecycle events for these jobs")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo) or args.run < 1 or not args.prefix.strip():
        parser.error("need OWNER/REPO, a positive run ID and a nonempty prefix")
    data = record(args.repo, args.run, args.prefix, args.serve_log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Compact JSON keeps full API step arrays without a large, noisy fixture diff.
    args.output.write_text(json.dumps(data, sort_keys=True) + "\n")
    count = sum(len(page["jobs"]) for page in data["jobs_pages"])
    print(f"Recorded {count} jobs, {len(data['jobs_pages'])} pages; names sanitized")


if __name__ == "__main__":
    main()
