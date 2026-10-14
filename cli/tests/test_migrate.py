import base64
import json

import httpx
import pytest

from sbx import cli, migrate

LABELS = ["self-hosted", "sbx"]

STRING = """name: ci
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

LIST = """jobs:
  a:
    runs-on: [ubuntu-22.04]
  b:
    runs-on:
      - ubuntu-24.04   # pinned
      - extra
    steps: []
"""

MATRIX = """jobs:
  build:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
  other:
    runs-on: "ubuntu-latest"
"""

COMMENTS = """# top comment
jobs:
  # the build
  build:
    runs-on: ubuntu-latest  # fast path
    steps:
      - name: not a runner
        with:
          runs-on: ubuntu-latest
"""

MULTI = """jobs:
  lint:
    runs-on: ubuntu-latest
  test:
    runs-on: ubuntu-22.04
  win:
    runs-on: windows-latest
  mac:
    runs-on: macos-14
"""

DONE = """jobs:
  a:
    runs-on: [self-hosted, sbx]
  b:
    runs-on: self-hosted
"""


def test_string_becomes_flow_list():
    new, found = migrate.migrate_text("ci.yml", STRING, LABELS)
    assert new == STRING.replace("runs-on: ubuntu-latest", "runs-on: [self-hosted, sbx]")
    assert [(f.job, f.line, f.old, f.new) for f in found] == [("test", 5, "ubuntu-latest", "[self-hosted, sbx]")]


def test_flow_and_block_lists_keep_other_labels_and_comments():
    new, found = migrate.migrate_text("ci.yml", LIST, LABELS)
    assert new == """jobs:
  a:
    runs-on: [self-hosted, sbx]
  b:
    runs-on:
      - self-hosted
      - sbx  # pinned
      - extra
    steps: []
"""
    assert [f.job for f in found] == ["a", "b"]


def test_block_list_comment_on_key_line_survives():
    text = "jobs:\n  a:\n    runs-on:  # where\n      - ubuntu-latest\n"
    new, _ = migrate.migrate_text("ci.yml", text, LABELS)
    assert new == "jobs:\n  a:\n    runs-on:  # where\n      - self-hosted\n      - sbx\n"


def test_matrix_expression_skipped_with_reason_and_quoted_string_migrated():
    new, found = migrate.migrate_text("ci.yml", MATRIX, LABELS)
    assert new == MATRIX.replace('runs-on: "ubuntu-latest"', "runs-on: [self-hosted, sbx]")
    by = {f.job: f for f in found}
    assert by["build"].new == "" and "expression" in by["build"].skipped and by["build"].old == "${{ matrix.os }}"
    assert by["other"].new == "[self-hosted, sbx]"


def test_comments_preserved_and_step_with_runs_on_untouched():
    new, found = migrate.migrate_text("ci.yml", COMMENTS, LABELS)
    assert new == COMMENTS.replace("runs-on: ubuntu-latest  # fast", "runs-on: [self-hosted, sbx]  # fast")
    assert new.count("runs-on: ubuntu-latest") == 1  # the one under steps/with
    assert len(found) == 1


def test_multiple_jobs_only_ubuntu_changed():
    new, found = migrate.migrate_text("ci.yml", MULTI, LABELS)
    assert [f.job for f in found] == ["lint", "test"]
    assert "windows-latest" in new and "macos-14" in new and new.count("[self-hosted, sbx]") == 2


def test_jobs_filter():
    new, found = migrate.migrate_text("ci.yml", MULTI, LABELS, jobs={"test"})
    assert [f.job for f in found] == ["test"]
    assert "runs-on: ubuntu-latest" in new


def test_already_migrated_is_unchanged_and_reported():
    new, found = migrate.migrate_text("ci.yml", DONE, LABELS)
    assert new == DONE
    assert [(f.job, f.new, f.skipped) for f in found] == [("a", "", "already self-hosted"), ("b", "", "already self-hosted")]


def test_crlf_preserved():
    text = STRING.replace("\n", "\r\n")
    new, _ = migrate.migrate_text("ci.yml", text, LABELS)
    assert new == text.replace("runs-on: ubuntu-latest", "runs-on: [self-hosted, sbx]")


def test_custom_labels_and_parse():
    assert migrate.parse_labels("[self-hosted, sbx, big]") == ["self-hosted", "sbx", "big"]
    assert migrate.parse_labels("a,b") == ["a", "b"]
    with pytest.raises(cli.SbxError):
        migrate.parse_labels("[]")
    new, _ = migrate.migrate_text("ci.yml", STRING, ["self-hosted", "big"])
    assert "runs-on: [self-hosted, big]" in new


def test_diff_and_table():
    new, found = migrate.migrate_text("ci.yml", STRING, LABELS)
    diff = migrate.unified_diff("ci.yml", STRING, new)
    assert diff.startswith("--- a/ci.yml\n+++ b/ci.yml\n")
    assert "-    runs-on: ubuntu-latest\n+    runs-on: [self-hosted, sbx]\n" in diff
    rows = migrate.table(found).splitlines()
    assert rows[0].split() == ["file", "job", "old", "new"]
    assert rows[1].split(None, 3) == ["ci.yml", "test", "ubuntu-latest", "[self-hosted, sbx]"]


class FakeRepo:
    """A tiny GitHub contents/git API over httpx.MockTransport."""

    def __init__(self, files, branch_exists=False):
        self.files = files  # name -> text
        self.calls = []
        self.puts = []
        self.branch_exists = branch_exists

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.calls.append((req.method, path))
        if req.method == "GET" and path == "/repos/o/r":
            return httpx.Response(200, json={"default_branch": "trunk"})
        if req.method == "GET" and path == "/repos/o/r/contents/.github/workflows":
            assert req.url.params["ref"] == "trunk"
            return httpx.Response(200, json=[{"type": "file", "name": n, "path": f".github/workflows/{n}"} for n in self.files]
                                  + [{"type": "dir", "name": "sub", "path": ".github/workflows/sub"}])
        if req.method == "GET" and path.startswith("/repos/o/r/contents/.github/workflows/"):
            name = path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"content": base64.b64encode(self.files[name].encode()).decode(), "sha": "sha-" + name})
        if req.method == "GET" and path == "/repos/o/r/git/ref/heads/trunk":
            return httpx.Response(200, json={"object": {"sha": "HEAD1"}})
        if req.method == "POST" and path == "/repos/o/r/git/refs":
            assert json.loads(req.content) == {"ref": "refs/heads/sbx-runners-migrate", "sha": "HEAD1"}
            return httpx.Response(422 if self.branch_exists else 201, json={})
        if req.method == "PUT":
            self.puts.append(json.loads(req.content))
            return httpx.Response(200, json={})
        if req.method == "POST" and path == "/repos/o/r/pulls":
            self.pr = json.loads(req.content)
            return httpx.Response(201, json={"html_url": "https://github.com/o/r/pull/9"})
        return httpx.Response(404, text="unexpected " + path)

    def client(self):
        return httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(self.handler))


def test_dry_run_makes_no_writes():
    repo = FakeRepo({"ci.yml": STRING, "done.yml": DONE})
    out = migrate.run("o/r", "t", apply=False, labels=LABELS, only=None, jobs=None, base=None, client=repo.client())
    assert "+    runs-on: [self-hosted, sbx]" in out and "skipped: already self-hosted" in out
    assert "pull request:" not in out
    assert all(m == "GET" for m, _ in repo.calls)


def test_apply_commits_changed_files_only_and_opens_pr():
    repo = FakeRepo({"ci.yml": STRING, "done.yml": DONE})
    out = migrate.run("o/r", "t", apply=True, labels=LABELS, only=None, jobs=None, base="trunk", client=repo.client())
    assert out.endswith("pull request: https://github.com/o/r/pull/9")
    assert len(repo.puts) == 1
    put = repo.puts[0]
    assert put["branch"] == "sbx-runners-migrate" and put["sha"] == "sha-ci.yml"
    assert base64.b64decode(put["content"]).decode() == STRING.replace("ubuntu-latest", "[self-hosted, sbx]")
    assert repo.pr["head"] == "sbx-runners-migrate" and repo.pr["base"] == "trunk"
    assert "sbx runners serve --repo o/r" in repo.pr["body"] and "Revert" in repo.pr["body"]


def test_apply_with_nothing_to_change_opens_no_pr():
    repo = FakeRepo({"done.yml": DONE})
    out = migrate.run("o/r", "t", apply=True, labels=LABELS, only=None, jobs=None, base="trunk", client=repo.client())
    assert "nothing to change" in out
    assert not any(m != "GET" for m, _ in repo.calls)


def test_only_and_unknown_file_and_jobs():
    repo = FakeRepo({"ci.yml": STRING, "other.yml": MULTI})
    out = migrate.run("o/r", "t", apply=False, labels=LABELS, only="ci.yml", jobs=None, base="trunk", client=repo.client())
    assert "other.yml" not in out
    with pytest.raises(cli.SbxError, match="no such workflow"):
        migrate.run("o/r", "t", apply=False, labels=LABELS, only="nope.yml", jobs=None, base="trunk", client=repo.client())
    with pytest.raises(cli.SbxError, match="no migratable job named ghost"):
        migrate.run("o/r", "t", apply=False, labels=LABELS, only=None, jobs={"ghost"}, base="trunk", client=repo.client())


def test_existing_branch_is_an_error_and_default_branch_is_read():
    repo = FakeRepo({"ci.yml": STRING}, branch_exists=True)
    with pytest.raises(cli.SbxError, match="already exists"):
        migrate.run("o/r", "t", apply=True, labels=LABELS, only=None, jobs=None, base=None, client=repo.client())
    assert ("GET", "/repos/o/r") in repo.calls
    assert repo.puts == []


def test_no_workflows_dir():
    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(lambda r: httpx.Response(404, json={})))
    with pytest.raises(cli.SbxError, match="no .github/workflows"):
        migrate.Migrator("o/r", client).workflows("main")


def test_cli_dry_run_default_and_flags(monkeypatch, capsys):
    seen = {}

    def fake_run(repo, token, **kw):
        seen.update(repo=repo, token=token, **kw)
        return "DIFF"

    monkeypatch.setattr(migrate, "run", fake_run)
    monkeypatch.setenv("GH_TOKEN", "<FAKE>")
    assert cli.main(["runners", "migrate", "--repo", "o/r", "--jobs", "a, b", "--only", "ci.yml", "--base", "dev"]) == 0
    assert seen == {"repo": "o/r", "token": "<FAKE>", "apply": False, "labels": LABELS, "only": "ci.yml", "jobs": {"a", "b"}, "base": "dev"}
    assert capsys.readouterr().out.strip() == "DIFF"
    assert cli.main(["runners", "migrate", "--repo", "o/r", "--apply", "--label", "self-hosted,big"]) == 0
    assert seen["apply"] is True and seen["labels"] == ["self-hosted", "big"]


def test_cli_apply_and_dry_run_conflict(capsys):
    with pytest.raises(SystemExit):
        cli.main(["runners", "migrate", "--repo", "o/r", "--apply", "--dry-run"])


def test_redirected_repo_is_followed():
    seen = []

    def handler(req):
        seen.append(req.url.path)
        if req.url.path == "/repos/o/old":
            return httpx.Response(301, headers={"location": "https://api.github.com/repositories/42"})
        if req.url.path == "/repositories/42":
            return httpx.Response(200, json={"default_branch": "main"})
        return httpx.Response(404)

    real = httpx.Client
    orig = migrate.httpx.Client
    migrate.httpx.Client = lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    try:
        http = migrate.make_client("<FAKE>")
        assert migrate.Migrator("o/old", http).default_branch() == "main"
    finally:
        migrate.httpx.Client = orig
    assert seen == ["/repos/o/old", "/repositories/42"]


def test_non_2xx_without_redirect_is_a_clear_error():
    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(
        lambda r: httpx.Response(301, headers={"location": "https://api.github.com/x"})))
    with pytest.raises(cli.SbxError, match="HTTP 301"):
        migrate.Migrator("o/r", client).default_branch()


def test_pr_body_captures_only_the_snapshot_line():
    body = migrate.pr_body("o/r", LABELS, [migrate.Finding("a.yml", "j", 1, "ubuntu-latest", "[self-hosted, sbx]")])
    assert "snap=$(sbx runners image | tail -1)" in body
