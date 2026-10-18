"""Tests for scripts/contract_check.py.

Fixtures are docs trees built in tmp_path, served to the checks by an
http.server on 127.0.0.1 (started here, not downloaded). The three real
drifts the contract exists to catch are each reproduced: a GPU template the
docs name and the live catalog lacks, a documented tool list that disagrees
with the server's, and a doc link that 404s.

Run:  pytest -q scripts     (from the repo root)
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_check as cc  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

README = """# demo

See [the console]({base}/console) and
[the docs]({base}/docs/page).
"""

PLUGIN_README = """# sandbox plugin

Tools: `sandboxes_list`, `sandbox_templates`,
`sandbox_create`, `sandbox_exec`, `sandbox_exec_output`,
`sandbox_files_read`, `sandbox_files_write`, `sandbox_preview_url`,
`sandbox_workspace`, `sandbox_kill`. Server URL:
`https://api.sbx.agent-next.com/mcp/v1`.
"""

PLUGIN_SKILL = """---
name: sandbox
---

# Use the sandbox

GPU: call `sandbox_templates` for the live catalog. The catalog on the live
service today is `gpu-lease-v06`, `mujoco`, `kernel` (`sbx gpu templates`
lists it for the CLI); an unknown template name is refused.
"""

# The tool list the plugin README documents (10 entries), and the catalog the
# skill documents. The server's lists differ from both, as in the real drifts.
DOCUMENTED_TOOLS = ["sandboxes_list", "sandbox_templates", "sandbox_create",
                    "sandbox_exec", "sandbox_exec_output", "sandbox_files_read",
                    "sandbox_files_write", "sandbox_preview_url",
                    "sandbox_workspace", "sandbox_kill"]
LIVE_TOOLS = ["sandboxes_list", "sandbox_templates", "sandbox_create",
              "sandbox_exec", "sandbox_exec_output", "sandbox_files_read",
              "sandbox_files_write", "sandbox_preview_url", "sandbox_workspace",
              "sandbox_kill", "sandbox_workspace_logs"]
LIVE_GPU_TEMPLATES = ["gpu-lease-v06", "mujoco", "browser", "blender",
                      "omniverse", "robotsim"]


class Handler(BaseHTTPRequestHandler):
    """Answers the links check, the MCP tools/list call and the GPU catalog."""

    links: dict[str, int] = {}
    # Paths that answer 405 to HEAD and GET, as the live MCP endpoint does.
    refused: set[str] = {"/mcp/v1"}
    tools: list[str] = []
    gpu_templates: list[str] = []
    statuses: list[tuple[str, str]] = []

    def log_message(self, *args):  # keep pytest output readable
        pass

    def _send(self, status: int, body: bytes = b"", content_type: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_HEAD(self):
        self.statuses.append(("HEAD", self.path))
        if self.path in self.refused:
            self._send(405)
            return
        self._send(self.links.get(self.path, 404))  # the stub serves exactly what the test declared

    def do_GET(self):
        self.statuses.append(("GET", self.path))
        if self.path in self.refused:
            self._send(405)  # the real endpoint refuses a plain GET, too
            return
        if self.path == "/gpu/templates":
            body = json.dumps({"templates": [{"name": n} for n in self.gpu_templates]}).encode()
            self._send(200, body, "application/json")
            return
        self._send(self.links.get(self.path, 404))

    def do_POST(self):
        self.statuses.append(("POST", self.path))
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/mcp/v1":
            if request.get("method") != "tools/list":
                self._send(400, b'{"error":"unknown method"}', "application/json")
                return
            body = json.dumps({"jsonrpc": "2.0", "id": request.get("id"),
                               "result": {"tools": [{"name": n} for n in self.tools]}}).encode()
            self._send(200, body, "application/json")
            return
        self._send(404)


@pytest.fixture
def server(monkeypatch):
    """A stub service on 127.0.0.1; every test gets a fresh one.

    The links check skips localhost URLs by design; these tests exercise it
    against this stub, so the skip list is emptied for the run.
    """
    monkeypatch.setattr(cc, "SKIP_URL_PARTS", ())
    Handler.links, Handler.tools, Handler.gpu_templates, Handler.statuses = {}, [], [], []
    Handler.refused = {"/mcp/v1"}
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.fixture
def docs(tmp_path: Path, server) -> Path:
    """A docs tree whose links point at the stub, with the real drift cases."""
    base = f"http://127.0.0.1:{server.server_address[1]}"
    (tmp_path / "cli").mkdir()
    (tmp_path / "plugins" / "sandbox" / "skills" / "sandbox").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(README.format(base=base), encoding="utf-8")
    (tmp_path / "cli" / "README.md").write_text(README.format(base=base), encoding="utf-8")
    (tmp_path / cc.PLUGIN_README).write_text(PLUGIN_README, encoding="utf-8")
    (tmp_path / cc.PLUGIN_SKILL).write_text(PLUGIN_SKILL, encoding="utf-8")
    (tmp_path / "docs" / "acceptance.md").write_text(
        f"See [{base}/alive]({base}/alive).\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def service(docs, server):
    """The base URL of the stub the docs tree points at, with drift data loaded."""
    Handler.links = {"/alive": 200, "/console": 200, "/docs/page": 200}
    Handler.tools = list(LIVE_TOOLS)
    Handler.gpu_templates = list(LIVE_GPU_TEMPLATES)
    return f"http://127.0.0.1:{server.server_address[1]}"


# --- the doc sources ----------------------------------------------------

def test_the_repo_docs_parse():
    """The real docs yield the tool list and the catalog the checks compare."""
    names = cc.documented_tool_names((REPO / cc.PLUGIN_README).read_text(encoding="utf-8"))
    assert names == DOCUMENTED_TOOLS
    templates = cc.documented_gpu_templates((REPO / cc.PLUGIN_SKILL).read_text(encoding="utf-8"))
    assert templates == ["gpu-lease-v06", "mujoco", "browser", "blender", "omniverse", "robotsim"]


def test_doc_urls_skips_fences_and_placeholders(tmp_path):
    page = tmp_path / "page.md"
    page.write_text(
        "real https://a.example/1\n"
        "```\n"
        "curl https://a.example/2\n"
        "```\n"
        "placeholder https://<port>-<id>.sbx.agent-next.com and https://a.example/$id\n"
        "local http://localhost:8000/x and https://127.0.0.1:9/y\n"
        "example https://example.com/z\n",
        encoding="utf-8")
    assert cc.doc_urls(page) == [(1, "https://a.example/1")]


# --- links: the dead-link drift ----------------------------------------

def test_links_fail_on_a_dead_link(docs, service):
    """A doc URL that answers 404 fails the check and names the file and line."""
    Handler.links["/docs/page"] = 404
    check = cc.check_links(docs)
    assert check.failed, "a 404 in the docs must fail the links check"
    assert any("/page" in line and "404" in line for line in check.failed)


def test_links_fail_names_the_doc_and_line(docs, service):
    dead = docs / "docs" / "dead.md"
    dead.write_text(f"[dead]({service}/gone)\n", encoding="utf-8")
    Handler.links["/gone"] = 404
    check = cc.check_links(docs)
    assert any("docs/dead.md:1" in line for line in check.failed)


def test_links_pass_when_every_url_answers(docs, service):
    check = cc.check_links(docs)
    assert not check.failed
    assert any("/alive" in line for line in check.ok)


def test_links_retry_a_refused_head(docs, service):
    """A server that refuses HEAD but serves GET is not a dead link."""
    base = docs_port(service)
    (docs / "docs" / "post.md").write_text(f"[x](http://127.0.0.1:{base}/mcp/v1)\n",
                                           encoding="utf-8")
    check = cc.check_links(docs)
    assert any("refuses GET/HEAD" in line for line in check.ok)
    assert any(method == "HEAD" for method, _ in Handler.statuses)


def test_links_count_a_refused_head_as_alive(docs, service):
    base = docs_port(service)
    (docs / "docs" / "mcp.md").write_text(f"[x](http://127.0.0.1:{base}/mcp/v1)\n",
                                          encoding="utf-8")
    check = cc.check_links(docs)
    assert not check.failed


# --- mcp: the tool-list drift ------------------------------------------

def test_mcp_pass_when_the_lists_agree(docs, service):
    Handler.tools = list(DOCUMENTED_TOOLS)
    check = cc.check_mcp(docs, "k", f"http://127.0.0.1:{docs_port(service)}/mcp/v1")
    assert not check.failed, check.failed
    assert any("equals" in line for line in check.ok)


def test_mcp_fail_on_a_documented_tool_the_server_lacks(docs, service):
    """The README naming a tool the server does not expose fails the check."""
    Handler.tools = [n for n in DOCUMENTED_TOOLS if n != "sandbox_workspace"]
    check = cc.check_mcp(docs, "k", f"http://127.0.0.1:{docs_port(service)}/mcp/v1")
    assert any("sandbox_workspace" in line and "does not expose" in line for line in check.failed)


def test_mcp_fail_on_a_server_tool_the_readme_lacks(docs, service):
    """The server exposing a tool the README omits fails the check."""
    check = cc.check_mcp(docs, "k", f"http://127.0.0.1:{docs_port(service)}/mcp/v1")
    assert any("sandbox_workspace_logs" in line and "does not document" in line
               for line in check.failed)


def test_mcp_fail_when_the_readme_states_no_tool_list(docs, service):
    (docs / cc.PLUGIN_README).write_text("# sandbox plugin\n\nNo tools here.\n", encoding="utf-8")
    check = cc.check_mcp(docs, "k", f"http://127.0.0.1:{docs_port(service)}/mcp/v1")
    assert check.failed


def test_mcp_skips_when_the_service_refuses(docs, server):
    """A service error is a SKIP that says why, never a silent pass."""
    base = f"http://127.0.0.1:{server.server_address[1]}"
    (docs / "docs" / "mcp.md").write_text(f"[x]({base}/mcp/v1)\n", encoding="utf-8")
    Handler.tools = []
    check = cc.check_mcp(docs, "bad-key", base)  # nothing serves the bare path
    assert check.skip_reason is not None
    assert "404" in check.skip_reason or "refused" in check.skip_reason


# --- gpu: the template drift -------------------------------------------

def test_gpu_pass_when_every_documented_template_is_live(docs, service):
    (docs / cc.PLUGIN_SKILL).write_text(
        PLUGIN_SKILL.replace("`kernel`", "`blender`"), encoding="utf-8")
    check = cc.check_gpu(docs, "k", f"http://127.0.0.1:{docs_port(service)}/gpu/templates")
    assert not check.failed, check.failed


def test_gpu_fail_on_a_template_the_catalog_lacks(docs, service):
    """The docs naming a GPU template the live catalog lacks fails the check."""
    check = cc.check_gpu(docs, "k", f"http://127.0.0.1:{docs_port(service)}/gpu/templates")
    assert any("kernel" in line and "catalog lacks" in line for line in check.failed)


def test_gpu_fail_when_the_skill_states_no_catalog(docs, service):
    (docs / cc.PLUGIN_SKILL).write_text("# Use the sandbox\n", encoding="utf-8")
    check = cc.check_gpu(docs, "k", f"http://127.0.0.1:{docs_port(service)}/gpu/templates")
    assert check.failed


def test_gpu_template_payload_accepts_id_and_template_id(docs, service):
    payload = {"templates": [{"templateID": "mujoco"}, {"id": "browser"}, "blender"]}
    assert cc.gpu_templates_from_payload(payload) == ["mujoco", "browser", "blender"]


# --- the entry point ----------------------------------------------------

def test_main_offline_skips_the_link_check(docs, service):
    assert cc.main(["--root", str(docs), "--offline"]) == 0


def test_main_fails_on_the_real_drifts(docs, service):
    assert cc.main(["--root", str(docs), "--api-key", "k",
                    "--mcp-url", f"http://127.0.0.1:{docs_port(service)}/mcp/v1",
                    "--gpu-url", f"http://127.0.0.1:{docs_port(service)}/gpu/templates"]) == 1


def test_main_passes_when_the_docs_match_the_service(docs, service):
    (docs / cc.PLUGIN_SKILL).write_text(
        PLUGIN_SKILL.replace("`kernel`", "`blender`"), encoding="utf-8")
    Handler.tools = list(DOCUMENTED_TOOLS)
    assert cc.main(["--root", str(docs), "--api-key", "k",
                    "--mcp-url", f"http://127.0.0.1:{docs_port(service)}/mcp/v1",
                    "--gpu-url", f"http://127.0.0.1:{docs_port(service)}/gpu/templates"]) == 0


def test_main_prints_a_reason_when_it_skips(docs, service, capsys):
    cc.main(["--root", str(docs)])
    out = capsys.readouterr().out
    assert "SKIP mcp:" in out and "SBX_API_KEY" in out
    assert "SKIP gpu:" in out and "SBX_API_KEY" in out


def test_main_skips_checks_2_and_3_without_a_key(docs, service):
    """No key: the link check still runs for real, the live ones say why."""
    assert cc.main(["--root", str(docs)]) == 0


def docs_port(base: str) -> int:
    return int(base.rsplit(":", 1)[1])
