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


def _media_drift_pair(case):
    base = make_doc()
    request = base["paths"]["/sandboxes"]["post"]["requestBody"]["content"]
    response = base["paths"]["/sandboxes"]["get"]["responses"]["200"]["content"]
    if case.startswith("encoding_"):
        request["multipart/form-data"] = {"schema": {"type": "object"}}
    elif case == "response_example_change":
        response["text/plain"] = {"example": "before"}
    elif case == "request_examples_change":
        request["text/plain"] = {"examples": {"sample": {"value": "before"}}}
    new = copy.deepcopy(base)
    new_request = new["paths"]["/sandboxes"]["post"]["requestBody"]["content"]
    new_response = new["paths"]["/sandboxes"]["get"]["responses"]["200"]["content"]
    if case.startswith("request_") and case.endswith(("_add", "_remove")):
        new_request["text/plain"] = {}
    elif case.startswith("response_") and case.endswith(("_add", "_remove")):
        new_response["text/plain"] = {}
    elif case.startswith("encoding_"):
        new_request["multipart/form-data"]["encoding"] = {
            "file": {"contentType": "application/octet-stream"}}
    elif case == "response_example_change":
        new_response["text/plain"]["example"] = "after"
    elif case == "request_examples_change":
        new_request["text/plain"]["examples"]["sample"]["value"] = "after"
    else:
        raise AssertionError(f"unknown media regression case: {case}")
    return (new, base) if case.endswith("_remove") else (base, new)


@pytest.mark.parametrize("case,tokens", [
    ("request_add", ("POST /sandboxes request", "media type added: text/plain")),
    ("request_remove", ("POST /sandboxes request", "media type removed: text/plain")),
    ("response_add", ("GET /sandboxes response 200", "media type added: text/plain")),
    ("response_remove", ("GET /sandboxes response 200", "media type removed: text/plain")),
    ("encoding_add", ("POST /sandboxes request", "multipart/form-data", "encoding")),
    ("encoding_remove", ("POST /sandboxes request", "multipart/form-data", "encoding")),
    ("response_example_change", ("GET /sandboxes response 200", "text/plain", "example")),
    ("request_examples_change", ("POST /sandboxes request", "text/plain", "examples")),
], ids=["request_add", "request_remove", "response_add", "response_remove",
        "encoding_add", "encoding_remove", "response_example_change", "request_examples_change"])
def test_media_entry_drift_detected(case, tokens, tmp_path, capsys):
    base, new = _media_drift_pair(case)
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    original = snapshot.read_bytes(), live.read_bytes()
    assert drift.main(["--snapshot", str(snapshot), "--file", str(live)]) == 1, case
    captured = capsys.readouterr()
    assert captured.out.startswith("API drift: "), case
    assert any(all(token in line for token in tokens)
               for line in captured.out.splitlines()[1:]), case
    assert "no drift" not in captured.out, case
    assert not captured.err, case
    assert (snapshot.read_bytes(), live.read_bytes()) == original, case


@pytest.mark.parametrize("old_present,old_entry,new_present,new_entry", [
    (False, None, True, None),
    (True, None, False, None),
    (True, None, True, {}),
    (True, {}, True, None),
    (True, {}, True, {"schema": None}),
    (True, {"schema": None}, True, {}),
    (True, {"schema": None}, True, {"schema": {}}),
    (True, {"schema": {}}, True, {"schema": None}),
    (True, {}, True, {"schema": {}}),
    (True, {"schema": {}}, True, {}),
], ids=["missing_to_null", "null_to_missing", "null_to_empty", "empty_to_null",
        "absent_schema_to_null", "null_schema_to_absent", "null_schema_to_empty",
        "empty_schema_to_null", "absent_schema_to_empty", "empty_schema_to_absent"])
def test_media_entry_state_distinctions(old_present, old_entry, new_present, new_entry,
                                       tmp_path, capsys):
    base, new = make_doc(), make_doc()
    for doc, present, entry in ((base, old_present, old_entry), (new, new_present, new_entry)):
        if present:
            doc["paths"]["/sandboxes"]["post"]["requestBody"]["content"]["text/plain"] = entry
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    original = snapshot.read_bytes(), live.read_bytes()
    assert drift.main(["--snapshot", str(snapshot), "--file", str(live)]) == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("API drift: ")
    assert any("POST /sandboxes request" in line and "text/plain" in line
               for line in captured.out.splitlines()[1:])
    assert "no drift" not in captured.out
    assert not captured.err
    assert (snapshot.read_bytes(), live.read_bytes()) == original


@pytest.mark.parametrize("old_present,old_content,new_present,new_content", [
    (False, None, True, None),
    (True, None, False, None),
    (True, None, True, {}),
    (True, {}, True, None),
    (False, None, True, {}),
    (True, {}, False, None),
], ids=["missing_to_null", "null_to_missing", "null_to_empty", "empty_to_null",
        "missing_to_empty", "empty_to_missing"])
def test_content_container_state_distinctions(old_present, old_content,
                                             new_present, new_content, tmp_path, capsys):
    base, new = make_doc(), make_doc()
    for doc, present, content in ((base, old_present, old_content),
                                 (new, new_present, new_content)):
        node = doc["paths"]["/sandboxes"]["post"]["requestBody"]
        if present:
            node["content"] = content
        else:
            node.pop("content")
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", new)
    original = snapshot.read_bytes(), live.read_bytes()
    assert drift.main(["--snapshot", str(snapshot), "--file", str(live)]) == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("API drift: ")
    assert "POST /sandboxes request.content:" in captured.out
    assert "no drift" not in captured.out
    assert not captured.err
    assert (snapshot.read_bytes(), live.read_bytes()) == original


@pytest.mark.parametrize("entry", [
    {}, None, {"schema": None}, {"schema": {}}, {"example": "unchanged"},
], ids=["empty", "null", "null_schema", "empty_schema", "example"])
def test_unchanged_media_entry_not_drift(entry, tmp_path, capsys):
    base = make_doc()
    base["paths"]["/sandboxes"]["post"]["requestBody"]["content"]["text/plain"] = entry
    snapshot = write_doc(tmp_path / "snapshot.json", drift.normalize(base))
    live = write_live(tmp_path / "live.json", base)
    original = snapshot.read_bytes(), live.read_bytes()
    assert drift.main(["--snapshot", str(snapshot), "--file", str(live)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("no drift: ")
    assert "API drift:" not in captured.out
    assert not captured.err
    assert (snapshot.read_bytes(), live.read_bytes()) == original
