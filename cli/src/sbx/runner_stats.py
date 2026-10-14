"""Pure timing and cost calculations over GitHub jobs and serve events."""

from __future__ import annotations

from datetime import datetime
import math
from statistics import median


SIZES = {"small": 2, "standard": 4}


def timestamp(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.timestamp() if date.year > 1 and date.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def elapsed(start: float | None, end: float | None) -> float | None:
    return round(end - start, 3) if start is not None and end is not None and end >= start else None


def distribution(values: list[float]) -> dict:
    """Nearest-rank p95; unknown durations do not enter the sample."""
    ordered = sorted(values)
    return {
        "samples": len(ordered),
        "median": median(ordered) if ordered else None,
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1] if ordered else None,
    }


def _lifetimes(events: list[dict]) -> dict[str, list[dict]]:
    names = {"spawn": "spawn_at", "sandbox": "vm_ready_at",
             "online": "runner_online_at", "killed": "killed_at"}
    valid = [event for event in events if event.get("event") in names
             and isinstance(event.get("runner"), str)
             and type(event.get("t")) in (int, float) and math.isfinite(event["t"])]
    out: dict[str, list[dict]] = {}
    for event in sorted(valid, key=lambda event: event["t"]):
        lifetimes = out.setdefault(event["runner"], [])
        if not lifetimes or event["event"] == "spawn":
            lifetimes.append({})
        current = lifetimes[-1]
        current.setdefault(names[event["event"]], event["t"])
        for field in ("create_s", "boot_s"):
            value = event.get(field)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                current.setdefault(field, value)
    return out


def _lifecycle(job: dict, lifetimes: list[dict]) -> dict:
    start, end = timestamp(job.get("started_at")), timestamp(job.get("completed_at"))
    life = {}
    for candidate in lifetimes:
        born, killed = candidate.get("spawn_at"), candidate.get("killed_at")
        if start is not None and (born is None or born <= start) and (killed is None or killed >= start):
            life = candidate
    born, ready = life.get("spawn_at"), life.get("vm_ready_at")
    online, killed = life.get("runner_online_at"), life.get("killed_at")
    queued = timestamp(job.get("created_at"))
    queue_ready = round(max(0, ready - queued), 3) if ready is not None and queued is not None else None
    return {
        "spawn_at": born, "vm_ready_at": ready, "runner_online_at": online, "killed_at": killed,
        "vm_ready_s": elapsed(born, ready) if born is not None else life.get("create_s"),
        "runner_online_s": elapsed(born, online) if born is not None else life.get("boot_s"),
        "queue_to_vm_ready_s": queue_ready,
        "reclaim_s": elapsed(end, killed),
    }


def _job(job: dict, provider: str, size: str, lifetimes: dict) -> dict:
    labels = {label.lower() for label in job.get("labels", [])}
    explicit = {label.removeprefix("sbx-") for label in labels
                if label in SIZES or label in {"sbx-small", "sbx-standard"}}
    chosen = next(iter(explicit)) if len(explicit) == 1 else size if not explicit else None
    if provider != "sbx":
        chosen = None  # the jobs API cannot establish hosted runner CPU count or price
    runner = job.get("runner_name") or ""
    return {
        "id": job["id"], "run_id": job["run_id"], "run_attempt": job.get("run_attempt", 1),
        "name": job["name"], "status": job["status"], "conclusion": job.get("conclusion"),
        "runner": runner, "provider": provider, "size": chosen, "vcpus": SIZES.get(chosen),
        "size_source": ("label" if len(explicit) == 1 else "assumed" if not explicit else "unknown")
                       if provider == "sbx" else "unknown",
        "created_at": job.get("created_at"), "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "wait_s": elapsed(timestamp(job.get("created_at")), timestamp(job.get("started_at"))),
        "run_s": elapsed(timestamp(job.get("started_at")), timestamp(job.get("completed_at"))),
        "steps": [{
            "number": step["number"], "name": step["name"], "status": step["status"],
            "conclusion": step.get("conclusion"),
            "started_at": step.get("started_at"), "completed_at": step.get("completed_at"),
            "run_s": None if step.get("conclusion") == "skipped" else
                     elapsed(timestamp(step.get("started_at")), timestamp(step.get("completed_at"))),
        } for step in job.get("steps", [])],
        "lifecycle": _lifecycle(job, lifetimes.get(runner, [])) if provider == "sbx" else None,
    }


def _summary(jobs: list[dict], price: float) -> dict:
    costs = [job["run_s"] / 60 * job["vcpus"] for job in jobs
             if job["run_s"] is not None and job["vcpus"] is not None]
    out = {
        "jobs": len(jobs),
        "failures": sum(job["conclusion"] == "failure" for job in jobs),
        "cancelled": sum(job["conclusion"] == "cancelled" for job in jobs),
        "incomplete": sum(job["status"] != "completed" for job in jobs),
        "size_assumed_jobs": sum(job["size_source"] == "assumed" for job in jobs),
        "cost_samples": len(costs),
        "vcpu_minutes": sum(costs) if costs else None,
        "estimated_cost": sum(costs) * price if costs else None,
    }
    for field in ("wait_s", "run_s", "vm_ready_s", "runner_online_s", "reclaim_s"):
        values = [job.get(field) if field in ("wait_s", "run_s") else
                  (job["lifecycle"] or {}).get(field) for job in jobs]
        out[field] = distribution([value for value in values if value is not None])
    return out


def build_report(repo: str, jobs: list[dict], *, prefix: str = "sbx-", size: str = "small",
                 price_per_vcpu_min: float = 0.002, events: list[dict] | None = None) -> dict:
    """No I/O, clock reads or mutation. Costs cover known job runtime, not idle VMs."""
    if not prefix.strip() or size not in SIZES or not math.isfinite(price_per_vcpu_min) or price_per_vcpu_min < 0:
        raise ValueError("need a nonempty prefix, valid size and finite nonnegative price")
    lifetimes = _lifetimes(events or [])
    sbx, hosted = [], []
    for job in jobs:
        runner = job.get("runner_name") or ""
        if runner.startswith(prefix):
            sbx.append(_job(job, "sbx", size, lifetimes))
        elif runner.startswith("GitHub Actions") and "self-hosted" not in {
            label.lower() for label in job.get("labels", [])
        }:
            hosted.append(_job(job, "github-hosted", size, lifetimes))
    comparisons = []
    cohorts = {}
    for job in sbx + hosted:
        cohort = cohorts.setdefault((job["run_id"], job["run_attempt"]), {"sbx": [], "github-hosted": []})
        cohort[job["provider"]].append(job)
    for (run_id, attempt), cohort in sorted(cohorts.items()):
        if not cohort["sbx"] or not cohort["github-hosted"]:
            continue
        left = _summary(cohort["sbx"], price_per_vcpu_min)
        right = _summary(cohort["github-hosted"], price_per_vcpu_min)
        comparison = {"run_id": run_id, "run_attempt": attempt, "sbx": left, "github_hosted": right}
        for field in ("wait", "run"):
            a, b = left[f"{field}_s"]["median"], right[f"{field}_s"]["median"]
            comparison[f"median_{field}_delta_s"] = round(a - b, 3) if a is not None and b is not None else None
        comparisons.append(comparison)
    return {
        "repo": repo, "prefix": prefix, "assumed_size": size,
        "price_per_vcpu_min": price_per_vcpu_min,
        "jobs": sbx, "summary": _summary(sbx, price_per_vcpu_min),
        "github_hosted": {"jobs": hosted, "summary": _summary(hosted, price_per_vcpu_min)},
        "comparisons": comparisons,
    }


def format_report(report: dict) -> str:
    def number(value):
        return f"{value:g}" if value is not None else "?"

    lines = [f"{report['repo']} (runner prefix {report['prefix']})",
             "JOB\tRUN/ATTEMPT\tCONCLUSION\tRUNNER\tSIZE\tWAIT(s)\tRUN(s)\tVM-READY(s)\tRECLAIM(s)"]
    for job in report["jobs"]:
        life = job["lifecycle"]
        size = (job["size"] or "?") + ("*" if job["size_source"] == "assumed" else "")
        lines.append("\t".join([
            f"{job['id']} {job['name']}", f"{job['run_id']}/{job['run_attempt']}",
            job["conclusion"] or job["status"], job["runner"], size,
            number(job["wait_s"]), number(job["run_s"]),
            number(life["vm_ready_s"]), number(life["reclaim_s"]),
        ]))
        for step in job["steps"]:
            lines.append(f"  step {step['number']} {step['name']}: "
                         f"{number(step['run_s'])}s ({step['conclusion'] or step['status']})")
    for name, summary in (("sbx", report["summary"]), ("GitHub-hosted", report["github_hosted"]["summary"])):
        lines.append(f"{name}: {summary['jobs']} jobs, {summary['failures']} failures, "
                     f"{summary['cancelled']} cancelled; wait median/p95 "
                     f"{number(summary['wait_s']['median'])}/{number(summary['wait_s']['p95'])}s, "
                     f"run median/p95 {number(summary['run_s']['median'])}/{number(summary['run_s']['p95'])}s")
    summary = report["summary"]
    lines.append(f"sbx runtime estimate: {number(summary['vcpu_minutes'])} vCPU-min, "
                 f"${number(summary['estimated_cost'])} at ${report['price_per_vcpu_min']:g}/vCPU-min "
                 f"({summary['cost_samples']}/{summary['jobs']} jobs)")
    for comparison in report["comparisons"]:
        lines.append(f"run {comparison['run_id']}/{comparison['run_attempt']} sbx minus GitHub-hosted "
                     f"median: wait {number(comparison['median_wait_delta_s'])}s, "
                     f"run {number(comparison['median_run_delta_s'])}s (unmatched job cohorts)")
    lines.append(f"* size assumed from --size {report['assumed_size']} unless size-labelled; "
                 "estimate excludes boot, idle and reclaim time. ? = unknown.")
    return "\n".join(lines)
