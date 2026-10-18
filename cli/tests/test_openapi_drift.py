"""Tests for the OpenAPI drift checker (scripts/openapi_drift.py).

The checker compares the live gateway OpenAPI document against the snapshot
committed at docs/contract/openapi.snapshot.json.  These tests exercise it
without touching the network: every "live" document comes either from a
mutated copy of the snapshot or from a loopback HTTP server, and any
connection attempt outside loopback fails the test.
"""

import copy
import http.server
import importlib.util
import json
import socket
import threading
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "openapi_drift.py"
_spec = importlib.util.spec_from_file_location("openapi_drift", _SCRIPT)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)


def make_doc():
    """A minimal but realistic OpenAPI document."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "agent-next sandbox gateway", "version": "0.0.19",
                 "description": "E2B-compatible gateway"},
        "servers": [{"url": "https://api.{domain}",
                     "variables": {"domain": {"default": "sbx.agent-next.com"}}}],
        "paths": {
            "/sandboxes": {
                "get": {
                    "operationId": "listSandboxes",
                    "parameters": [{"name": "status", "in": "query",
                                    "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "ok", "content": {
                        "application/json": {"schema": {
                            "$ref": "#/components/schemas/Sandbox"}}}}},
                },
                "post": {
                    "operationId": "createSandbox",
                    "requestBody": {"content": {"application/json": {"schema": {
                        "$ref": "#/components/schemas/NewSandbox"}}}},
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
        "components": {
            "schemas": {
                "NewSandbox": {
                    "type": "object",
                    "required": ["templateID"],
                    "properties": {"templateID": {"type": "string"}},
                },
                "Sandbox": {
                    "type": "object",
                    "required": ["sandboxID"],
                    "properties": {"sandboxID": {"type": "string"}},
                },
            },
        },
    }


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Any socket connect outside loopback fails the test loudly."""
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else None
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(f"test attempted a real connection to {host!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = self.server.body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def loopback_server():
    """Serve a settable JSON document on 127.0.0.1; yields (url, holder)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.body = b"{}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/openapi.json"
    yield url, server
    server.shutdown()
    server.server_close()


def write_doc(path, doc):
    """Write a document the way --update would (canonical form)."""
    path.write_text(drift.canon(doc), encoding="utf-8")
    return path


def write_live(path, doc):
    """Write a live-style document (key order as served, not canonical)."""
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return path


def test_no_drift_exits_zero(tmp_path, capsys):
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", make_doc())
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 0
    assert "no drift" in capsys.readouterr().out


def test_volatile_fields_do_not_count_as_drift(tmp_path):
    new = make_doc()
    new["info"]["version"] = "9.9.9"
    new["servers"] = [{"url": "https://api.other.example"}]
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 0


def test_added_path_and_removed_method_exit_one(tmp_path, capsys):
    new = make_doc()
    new["paths"]["/v1/things"] = {"get": {"operationId": "listThings",
                                          "responses": {"200": {"description": "ok"}}}}
    del new["paths"]["/sandboxes"]["get"]
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    out = capsys.readouterr().out
    assert "paths added: /v1/things" in out
    assert "/sandboxes: method removed: GET" in out


def test_request_schema_property_change_exits_one(tmp_path, capsys):
    new = make_doc()
    new["components"]["schemas"]["NewSandbox"]["properties"]["cpu_count"] = {"type": "integer"}
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "schema NewSandbox: property added: cpu_count" in capsys.readouterr().out


def test_response_schema_required_change_exits_one(tmp_path, capsys):
    new = make_doc()
    new["components"]["schemas"]["Sandbox"]["required"] = ["sandboxID", "clientID"]
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "schema Sandbox: now required: clientID" in capsys.readouterr().out


def test_removed_schema_property_exits_one(tmp_path, capsys):
    new = make_doc()
    del new["components"]["schemas"]["Sandbox"]["properties"]["sandboxID"]
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "schema Sandbox: property removed: sandboxID" in capsys.readouterr().out


def test_changed_operation_parameter_exits_one(tmp_path, capsys):
    new = make_doc()
    new["paths"]["/sandboxes"]["get"]["parameters"].append(
        {"name": "limit", "in": "query", "schema": {"type": "integer"}})
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "parameter added: limit (query)" in capsys.readouterr().out


def test_missing_file_exits_two(tmp_path, capsys):
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    assert drift.main(["--file", str(tmp_path / "absent.json"),
                       "--snapshot", str(snapshot)]) == 2
    assert "error:" in capsys.readouterr().err


def test_fetch_error_exits_two_never_zero(tmp_path, monkeypatch, capsys):
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))

    def fail(url, timeout=30):
        raise drift.FetchError(f"{url}: connection refused")

    monkeypatch.setattr(drift, "fetch", fail)
    assert drift.main(["--snapshot", str(snapshot)]) == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "connection refused" in err


def test_live_fetch_via_loopback_exits_zero(tmp_path, capsys, loopback_server):
    url, server = loopback_server
    server.body = json.dumps(make_doc()).encode()
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    assert drift.main(["--url", url, "--snapshot", str(snapshot)]) == 0
    assert "no drift" in capsys.readouterr().out


def test_live_fetch_via_loopback_detects_drift(tmp_path, capsys, loopback_server):
    url, server = loopback_server
    changed = make_doc()
    changed["components"]["schemas"]["Sandbox"]["properties"]["clientID"] = {"type": "string"}
    server.body = json.dumps(changed).encode()
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    assert drift.main(["--url", url, "--snapshot", str(snapshot)]) == 1
    assert "property added: clientID" in capsys.readouterr().out


def test_update_writes_normalized_snapshot(tmp_path, loopback_server):
    url, server = loopback_server
    server.body = json.dumps(make_doc()).encode()
    snapshot = tmp_path / "openapi.snapshot.json"
    assert drift.main(["--url", url, "--snapshot", str(snapshot), "--update"]) == 0
    written = json.loads(snapshot.read_text(encoding="utf-8"))
    assert "version" not in written["info"]
    assert "servers" not in written
    assert written["paths"] == make_doc()["paths"]


def test_malformed_live_json_exits_two(tmp_path, capsys, loopback_server):
    url, server = loopback_server
    server.body = b"{not json"
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    assert drift.main(["--url", url, "--snapshot", str(snapshot)]) == 2
    assert "invalid JSON" in capsys.readouterr().err


def test_snapshot_not_modified_on_drift(tmp_path):
    new = make_doc()
    new["paths"]["/extra"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    before = snapshot.read_text(encoding="utf-8")
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert snapshot.read_text(encoding="utf-8") == before


def with_component_params(doc):
    doc["components"]["parameters"] = {
        "SandboxId": {"in": "path", "name": "sandbox_id", "required": True,
                      "schema": {"type": "string"}},
        "IdempotencyKey": {"in": "header", "name": "Idempotency-Key", "required": False,
                           "schema": {"type": "string"}},
    }
    doc["paths"]["/sandboxes/{sandbox_id}/kill"] = {"post": {
        "operationId": "killSandbox",
        "parameters": [{"$ref": "#/components/parameters/SandboxId"},
                       {"$ref": "#/components/parameters/IdempotencyKey"}],
        "responses": {"200": {"description": "ok"}},
    }}
    return doc


def test_changed_parameter_schema_exits_one(tmp_path, capsys):
    new = make_doc()
    new["paths"]["/sandboxes"]["get"]["parameters"][0]["schema"] = {"type": "integer"}
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "parameter changed: status (query)" in capsys.readouterr().out


def test_removed_referenced_parameter_exits_one(tmp_path, capsys):
    base = with_component_params(make_doc())
    new = copy.deepcopy(base)
    new["paths"]["/sandboxes/{sandbox_id}/kill"]["post"]["parameters"].pop()
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "parameter removed: Idempotency-Key (header)" in capsys.readouterr().out


def test_replaced_parameter_reference_exits_one(tmp_path, capsys):
    base = with_component_params(make_doc())
    base["components"]["parameters"]["AliasId"] = {
        "in": "path", "name": "alias_id", "required": True, "schema": {"type": "string"}}
    new = copy.deepcopy(base)
    new["paths"]["/sandboxes/{sandbox_id}/kill"]["post"]["parameters"] = [
        {"$ref": "#/components/parameters/AliasId"}]
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    out = capsys.readouterr().out
    assert "parameter removed: sandbox_id (path)" in out
    assert "parameter added: alias_id (path)" in out


def test_request_body_required_change_exits_one(tmp_path, capsys):
    new = make_doc()
    new["paths"]["/sandboxes"]["post"]["requestBody"]["required"] = True
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "POST /sandboxes request.required: added" in capsys.readouterr().out


def test_removed_request_media_type_exits_one(tmp_path, capsys):
    new = make_doc()
    del new["paths"]["/sandboxes"]["post"]["requestBody"]["content"]["application/json"]
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "POST /sandboxes request: media type removed: application/json" in capsys.readouterr().out


def test_changed_response_ref_exits_one(tmp_path, capsys):
    base = make_doc()
    base["components"]["responses"] = {"Unauthorized": {"description": "bad key"},
                                       "Forbidden": {"description": "denied"}}
    base["paths"]["/sandboxes"]["get"]["responses"]["401"] = {
        "$ref": "#/components/responses/Unauthorized"}
    new = copy.deepcopy(base)
    new["paths"]["/sandboxes"]["get"]["responses"]["401"] = {
        "$ref": "#/components/responses/Forbidden"}
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "response 401.$ref: changed" in capsys.readouterr().out


def test_removed_response_header_exits_one(tmp_path, capsys):
    base = make_doc()
    base["paths"]["/sandboxes"]["get"]["responses"]["200"]["headers"] = {
        "X-Total-Running": {"schema": {"type": "integer"}}}
    new = copy.deepcopy(base)
    del new["paths"]["/sandboxes"]["get"]["responses"]["200"]["headers"]
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "response 200.headers: removed" in capsys.readouterr().out


def test_schema_level_constraint_change_exits_one(tmp_path, capsys):
    base = make_doc()
    base["components"]["schemas"]["NewSandbox"]["additionalProperties"] = True
    new = copy.deepcopy(base)
    new["components"]["schemas"]["NewSandbox"]["additionalProperties"] = False
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "schema NewSandbox.additionalProperties: changed (true -> false)" in capsys.readouterr().out


def test_path_item_summary_equal_documents_no_drift(tmp_path, capsys):
    base = make_doc()
    base["paths"]["/sandboxes"]["summary"] = "Sandbox collection"
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(copy.deepcopy(base)))
    live = write_live(tmp_path / "live.json", base)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 0
    assert "no drift" in capsys.readouterr().out


def test_path_level_parameter_change_exits_one(tmp_path, capsys):
    base = make_doc()
    base["paths"]["/sandboxes"]["parameters"] = [
        {"name": "X-API-Version", "in": "header", "schema": {"type": "string"}}]
    new = copy.deepcopy(base)
    new["paths"]["/sandboxes"]["parameters"][0]["schema"] = {"type": "integer"}
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    assert drift.main(["--file", str(live), "--snapshot", str(snapshot)]) == 1
    assert "parameter changed: X-API-Version (header)" in capsys.readouterr().out


def test_local_null_document_exits_two(tmp_path, capsys):
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    (tmp_path / "null.json").write_text("null", encoding="utf-8")
    assert drift.main(["--file", str(tmp_path / "null.json"),
                       "--snapshot", str(snapshot)]) == 2
    assert "error:" in capsys.readouterr().err


def test_local_invalid_utf8_exits_two(tmp_path, capsys):
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    (tmp_path / "bad.json").write_bytes(b"\xff\xfe\x00")
    assert drift.main(["--file", str(tmp_path / "bad.json"),
                       "--snapshot", str(snapshot)]) == 2
    assert "error:" in capsys.readouterr().err


def test_live_null_document_exits_two(tmp_path, capsys, loopback_server):
    url, server = loopback_server
    server.body = b"null"
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(make_doc()))
    assert drift.main(["--url", url, "--snapshot", str(snapshot)]) == 2
    assert "not a JSON object" in capsys.readouterr().err
