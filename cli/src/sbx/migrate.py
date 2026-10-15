"""Propose moving a repository's GitHub-hosted jobs onto `sbx runners serve` as a pull request.

Workflow files are edited line by line, never re-serialised, so formatting and
comments survive. Only jobs whose `runs-on` is a plain ubuntu-latest /
ubuntu-24.04 / ubuntu-22.04 label (string or list) are rewritten; expressions
(matrix and friends) and already self-hosted jobs are reported as skipped.
"""

from __future__ import annotations

import base64
import difflib
import re
from dataclasses import dataclass

from urllib.parse import quote

import httpx

from .cli import SbxError
from .runners import GITHUB_API

UBUNTU = ("ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04")
DEFAULT_LABELS = ["self-hosted", "sbx"]
BRANCH = "sbx-runners-migrate"

_KEY = re.compile(r"""^(\s*)("[^"]*"|'[^']*'|[\w.-]+)\s*:\s*(?:#.*)?$""")
_RUNS_ON = re.compile(r"^(\s*)runs-on\s*:[ \t]*(.*?)(\r?\n)?$")
_ITEM = re.compile(r"""^(\s*)-\s*(["']?)([^"'#\s][^"'#]*?)\2[ \t]*(#.*)?(\r?\n)?$""")


@dataclass
class Finding:
    file: str
    job: str
    line: int  # 1-based line of the runs-on key
    old: str
    new: str  # empty when skipped
    skipped: str = ""
    effective: tuple[str, ...] = ()  # every label the job ends up with


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _blank(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def _split_comment(value: str) -> tuple[str, str]:
    """(value, trailing comment incl. leading whitespace) of the text after `runs-on:`."""
    if value[:1] and value[0] in "\"'":
        end = value.find(value[0], 1)
        if end != -1:
            rest = value[end + 1:]
            return value[:end + 1], rest if rest.strip().startswith("#") else ""
    if value.startswith("#"):
        return "", " " + value
    m = re.search(r"\s+#", value)
    return (value[:m.start()], value[m.start():]) if m else (value, "")


def _unquote(s: str) -> str:
    s = s.strip()
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" else s


def _job_runs_on(lines: list[str]):
    """Yield (job id, runs-on line index) for every job's direct runs-on key."""
    in_jobs = False
    job_indent: int | None = None
    job = ""
    key_indent: int | None = None
    for i, line in enumerate(lines):
        if _blank(line):
            continue
        ind = _indent(line)
        if ind == 0:
            in_jobs = re.match(r"jobs\s*:\s*(#.*)?$", line.strip()) is not None
            job_indent = None
            continue
        if not in_jobs:
            continue
        if job_indent is None:
            job_indent = ind
        if ind == job_indent:
            m = _KEY.match(line.rstrip("\r\n"))
            job, key_indent = (_unquote(m.group(2)), None) if m else ("", None)
            continue
        if key_indent is None:
            key_indent = ind
        if job and ind == key_indent and _RUNS_ON.match(line):
            yield job, i


_PLAIN = re.compile(r"[A-Za-z][A-Za-z0-9._-]*")
_YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "null"}


def _plain(label: str) -> bool:
    """A label that is the same bare scalar in YAML, in a flow list and on a shell line."""
    return _PLAIN.fullmatch(label) is not None and label.lower() not in _YAML_WORDS


def _fmt(labels: list[str]) -> str:
    return "[" + ", ".join(labels) + "]"


def migrate_text(name: str, text: str, labels: list[str], jobs: set[str] | None = None) -> tuple[str, list[Finding]]:
    lines = text.splitlines(keepends=True)
    findings: list[Finding] = []
    edits: list[tuple[int, int, list[str]]] = []  # (start, end exclusive, replacement)
    for job, i in _job_runs_on(lines):
        if jobs is not None and job not in jobs:
            continue
        m = _RUNS_ON.match(lines[i])
        indent, raw, eol = m.group(1), m.group(2), m.group(3) or ""
        value, comment = _split_comment(raw)
        value = value.strip()
        items: list[str] | None = None
        item_lines: list[tuple[int, re.Match]] = []
        if not value:  # block list
            items, j, mapping = [], i + 1, False
            while j < len(lines) and (_blank(lines[j]) or _indent(lines[j]) > len(indent)
                                      or (_indent(lines[j]) == len(indent) and lines[j].lstrip().startswith("-"))):
                im = _ITEM.match(lines[j])
                if im:
                    items.append(im.group(2) + im.group(3).strip() + im.group(2))  # quotes kept: not plain
                    item_lines.append((j, im))
                elif not _blank(lines[j]):
                    mapping = True
                j += 1
            display = _fmt(items)
            if mapping:
                findings.append(Finding(name, job, i + 1, "(mapping)", "", "expression or mapping (matrix, group, ...)"))
                continue
        elif value.startswith("[") and "]" not in value:
            findings.append(Finding(name, job, i + 1, value, "", "multi-line flow list"))
            continue
        elif value.startswith("["):
            items = [x.strip() for x in value.strip("[]").split(",") if x.strip()]
            display = value
        elif "${{" in value or value.startswith(("{", "$")):
            findings.append(Finding(name, job, i + 1, value, "", "expression or mapping (matrix, group, ...)"))
            continue
        else:
            display = value
        labs = items if items is not None else [display]
        if any(x.lower() == "self-hosted" for x in labs):
            findings.append(Finding(name, job, i + 1, display, "", "already self-hosted"))
            continue
        if any("${{" in x for x in labs):
            findings.append(Finding(name, job, i + 1, display, "", "expression in label list"))
            continue
        if not any(x.strip("\"'") in UBUNTU for x in labs):
            continue
        if not all(_plain(x) for x in labs):
            findings.append(Finding(name, job, i + 1, display, "", "labels not plain (quoted or special)"))
            continue
        # duplicates (e.g. two ubuntu labels) collapse to one copy of the new labels
        seen: list[str] = []
        for x in labs:
            for out in labels if x in UBUNTU else [x]:
                if out not in seen:
                    seen.append(out)
        effective = tuple(dict.fromkeys(y for x in labs for y in (labels if x in UBUNTU else [x])))
        if value:
            edits.append((i, i + 1, [f"{indent}runs-on: {_fmt(seen)}{comment}{eol}"]))
        else:  # rewrite only the ubuntu items so every comment stays where it was
            first = True
            for k, im in item_lines:
                if im.group(3).strip() not in UBUNTU:
                    continue
                pad, tail, e = im.group(1), im.group(4), im.group(5) or eol
                block = [f"{pad}- {x}{e}" for x in labels] if first else []
                if block and tail:
                    block[-1] = f"{pad}- {labels[-1]}  {tail}{e}"
                elif tail:  # a dropped duplicate keeps its comment
                    block = [f"{pad}{tail}{e}"]
                edits.append((k, k + 1, block))
                first = False
        findings.append(Finding(name, job, i + 1, display, _fmt(seen), effective=effective))
    for start, stop, repl in sorted(edits, reverse=True):
        lines[start:stop] = repl
    return "".join(lines), findings


def unified_diff(name: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{name}", f"b/{name}"))


def table(findings: list[Finding]) -> str:
    rows = [("file", "job", "old", "new")] + [
        (f.file, f.job, f.old, f.new or f"skipped: {f.skipped}") for f in findings]
    widths = [max(len(r[c]) for r in rows) for c in range(4)]
    return "\n".join("  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip() for r in rows)


def parse_labels(spec: str) -> list[str]:
    labels = [x.strip() for x in spec.strip().strip("[]").split(",") if x.strip()]
    if not labels:
        raise SbxError("--label needs at least one label, e.g. '[self-hosted, sbx]'")
    for x in labels:
        if not _plain(x):
            raise SbxError(f"--label {x!r}: use plain labels (letters, digits, . _ -; starting with a letter; not true/false/yes/no/on/off/null)")
    return labels


def pr_body(repo: str, labels: list[str], findings: list[Finding]) -> str:
    changed = [f for f in findings if f.new]
    # serve adds self-hosted itself; it must register every label any migrated job still asks for
    extra = ",".join(dict.fromkeys(x for f in changed for x in f.effective if x != "self-hosted"))
    lines = "\n".join(f"- `{f.file}` job `{f.job}`: `{f.old}` -> `{f.new}`" for f in changed)
    return (
        f"Moves {len(changed)} job(s) from GitHub-hosted runners to single-use sandbox runners ({', '.join(labels)}).\n\n"
        f"{lines}\n\n"
        "Only the `runs-on` lines changed; formatting and comments are untouched.\n\n"
        "## Start the runners\n\n"
        "Jobs wait in the queue until a pool is serving them:\n\n"
        "```\n"
        "pip install \"git+https://github.com/agent-next/sandbox#subdirectory=cli\"\n"
        "snap=$(sbx runners image | tail -1)\n"
        f"sbx runners serve --repo {repo} --snapshot \"$snap\" --labels \"{extra}\" --warm 2 --max 10\n"
        "```\n\n"
        "## Revert\n\n"
        "Revert this pull request (or set the `runs-on` lines back to their old values above); "
        "no other change was made.\n"
    )


def make_client(token: str) -> httpx.Client:
    return httpx.Client(base_url=GITHUB_API, timeout=30, follow_redirects=True, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})


class Migrator:
    def __init__(self, repo: str, client: httpx.Client):
        self.repo, self.http = repo, client

    def _get(self, path: str, what: str, **params) -> httpx.Response:
        resp = self.http.get(path, params=params or None)
        if not resp.is_success:
            raise SbxError(f"GitHub {what} failed: HTTP {resp.status_code} {resp.text[:200]}")
        return resp

    def resolve(self) -> str:
        """Follow a renamed or moved repo to its canonical name (writes must not ride a redirect); return its default branch."""
        info = self._get(f"/repos/{self.repo}", "read repo").json()
        self.repo = info["full_name"]
        return info["default_branch"]

    def workflows(self, ref: str, only: str | None = None) -> list[tuple[str, str, str]]:
        """(path, text, blob sha) of each workflow file at ref."""
        resp = self.http.get(f"/repos/{self.repo}/contents/.github/workflows", params={"ref": ref})
        if resp.status_code == 404:
            raise SbxError(f"{self.repo}@{ref} has no .github/workflows directory")
        if not resp.is_success:
            raise SbxError(f"GitHub list workflows failed: HTTP {resp.status_code} {resp.text[:200]}")
        out = []
        for entry in resp.json():
            if entry["type"] != "file" or not entry["name"].endswith((".yml", ".yaml")):
                continue
            if only and only not in (entry["name"], entry["path"]):
                continue
            blob = self._get(f"/repos/{self.repo}/contents/{quote(entry['path'])}", f"read {entry['path']}", ref=ref).json()
            out.append((entry["path"], base64.b64decode(blob["content"]).decode("utf-8"), blob["sha"]))
        if only and not out:
            raise SbxError(f"--only {only}: no such workflow file in .github/workflows")
        return out

    def propose(self, base: str, files: list[tuple[str, str, str, str]], title: str, body: str) -> str:
        """Branch off base, commit each (path, new text, blob sha, message), open the PR; return its URL."""
        head = self._get(f"/repos/{self.repo}/git/ref/heads/{quote(base)}", f"read branch {base}").json()["object"]["sha"]
        resp = self.http.post(f"/repos/{self.repo}/git/refs", json={"ref": f"refs/heads/{BRANCH}", "sha": head})
        if resp.status_code == 422:
            raise SbxError(f"branch {BRANCH} already exists in {self.repo}; delete it or close its PR first")
        if not resp.is_success:
            raise SbxError(f"GitHub create branch failed: HTTP {resp.status_code} {resp.text[:200]}")
        for path, text, sha, message in files:
            resp = self.http.put(f"/repos/{self.repo}/contents/{quote(path)}", json={
                "message": message, "branch": BRANCH, "sha": sha,
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii")})
            if not resp.is_success:
                raise SbxError(f"GitHub commit {path} failed: HTTP {resp.status_code} {resp.text[:200]}")
        resp = self.http.post(f"/repos/{self.repo}/pulls", json={"title": title, "head": BRANCH, "base": base, "body": body})
        if not resp.is_success:
            raise SbxError(f"GitHub open pull request failed: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()["html_url"]


def run(repo: str, token: str, *, apply: bool, labels: list[str], only: str | None, jobs: set[str] | None,
        base: str | None, client: httpx.Client | None = None) -> str:
    m = Migrator(repo, client or make_client(token))
    default = m.resolve()
    repo, base = m.repo, base or default
    findings: list[Finding] = []
    diffs: list[str] = []
    commits: list[tuple[str, str, str, str]] = []
    for path, text, sha in m.workflows(base, only):
        new_text, found = migrate_text(path, text, labels, jobs)
        findings += found
        if new_text != text:
            diffs.append(unified_diff(path, text, new_text))
            commits.append((path, new_text, sha, f"ci: run {path} jobs on sbx runners"))
    if jobs:
        missing = jobs - {f.job for f in findings}
        if missing:
            raise SbxError(f"--jobs: no migratable job named {', '.join(sorted(missing))}")
    out = "".join(diffs) + ("\n" if diffs else "") + (table(findings) if findings else "no jobs use ubuntu-latest / ubuntu-24.04 / ubuntu-22.04")
    if apply and commits:
        url = m.propose(base, commits, "ci: run jobs on sbx runners", pr_body(repo, labels, findings))
        out += f"\n\npull request: {url}"
    elif apply:
        out += "\n\nnothing to change; no pull request opened"
    return out
