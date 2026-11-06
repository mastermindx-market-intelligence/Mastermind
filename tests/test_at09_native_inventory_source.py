"""AT09 real presenter + signed fixed Workspace HTTP; inert cache/census ports.

No live capabilities are inspected. The published temporary Control Room source
and synthetic enrolled principal are explicit premises, not installed proof.
"""
import asyncio
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from common import executive_workspace_contract as wire
from control_plane.workspace_control_room_presenter import ExistingControlRoomPresenter
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane import chairman_control_room as compositor
from integrations.chairman_surfaces import capability
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import (
    BINDINGS_SCHEMA, principal_frame, workspace_authorizers,
)
from scripts import chairman_control_room as ccr
from tests.test_workspace_read_app import _authenticator, _workspace_token, rsa_key, NOW
from tests.test_workspace_read_service import cache_fixture, STAMP

ROUTE = "/workspace/control-room/state/current"


def source(tmp_path, key):
    owners, source_clock, cache = cache_fixture(tmp_path)
    owner = owners[0]
    # Use the actual complete canonical compositor, not the smaller cache unit
    # fixture's intentionally partial Program row. No Runtime root is invented.
    doc = compositor.compose_control_room(inbox=None, boot_packet=None,
        active_builds=None, bindings=None, binding_problems=(), generated_at=STAMP,
        agent_os_state={"schema":"agent_os_state.v1","generated_at":STAMP,
            "workstreams":[{"key":"ONE","title":"One","owner":"ceo-sol","status":"active"}]},
        runtime_jobs=[])
    owner.state_cache["doc"] = doc
    calls = []
    def no_runner(*args, **kwargs):
        pytest.fail("an absent inert census must never run a binary")
    # Actual census composer, controlled absence ports; no host/PATH/app probe.
    census = capability.census(runner=no_runner,
        which=lambda name: calls.append(("which", name)) or None,
        app_exists=lambda path: calls.append(("app", path)) or False)
    owner.state_cache.update(capabilities=census, composed_at=STAMP)
    with owner.state_lock:
        ccr._publish_source_validity(owner, doc, tuple(source_clock), tuple(source_clock))
    auth = _authenticator(key)
    token = _workspace_token(key)
    principal = asyncio.run(auth.verify_authorization_header("Bearer " + token, now=NOW))
    bindings = {"schema": BINDINGS_SCHEMA, "profiles": {
        "web": {"enabled": True, "binding": {**principal_frame(principal), "permission_digest": "a" * 64}},
        "mac": {"enabled": False, "binding": None},
    }}
    authorize_principal, authorize_frame = workspace_authorizers(policy=auth.policy, load_bindings=lambda: bindings)
    presenter = ExistingControlRoomPresenter(cache, authorize=authorize_frame)
    service = WorkspaceReadService(cache=cache, runtime=object(), authorize=authorize_frame,
        armed={}, runtime_identity={}, control_room_presenter=presenter)
    frames = []
    class Transport:
        after = None
        async def request(self, frame):
            frames.append(copy.deepcopy(frame))
            assert (frame["schema"] == "mastermind.workspace_control_room_read.v1"
                    and frame["operation"] == "state") or frame["operation"] == "programs"
            result = await service.handle_frame(frame)
            if self.after:
                self.after()
            return result
    transport = Transport()
    clock = [NOW]
    config = WorkspaceAppConfig(authenticator=auth, authorize_principal=authorize_principal,
        client=transport, now=lambda: clock[0])
    http = TestClient(create_workspace_app(config))
    return SimpleNamespace(http=http, token=token, owner=owner, owners=owners, cache=cache,
        source_clock=source_clock, service=service, bindings=bindings, config=config,
        transport=transport, frames=frames, principal=principal, clock=clock, census_calls=calls)


def sample(response, path):
    return {"request": {"method": "GET", "path": path, "query": "", "body": None},
        "response": {"status": response.status_code, "content_type": response.headers.get("content-type"),
            "cache_control": response.headers.get("cache-control"), "body": response.json()}}


def test_same_cache_signed_inventory_and_programs_are_source_produced(tmp_path, rsa_key):
    s = source(tmp_path, rsa_key)
    before = s.owner.state_published_seq
    headers = {"Authorization": "Bearer " + s.token}
    inventory = s.http.get(ROUTE, headers=headers)
    programs = s.http.get("/workspace/programs/current", headers=headers)
    assert inventory.status_code == programs.status_code == 200
    body = inventory.json()
    assert body["control_room"] == programs.json()["control_room"] == s.owner.state_cache["doc"]
    assert body["capabilities"]["codex"]["state"] == "NOT_INSTALLED"
    assert body["capabilities"]["aionui"]["state"] == "UNSUPPORTED"
    assert body["source_validity"]["publication_seq"] == before
    assert inventory.headers["cache-control"] == "no-store"
    assert s.owner.state_published_seq == before and s.owner.state_compose_seq == 0
    assert [frame["operation"] for frame in s.frames] == ["state", "programs"]
    output = os.environ.get("MM_AT09_SOURCE_OUTPUT")
    if output:
        document = {"schema": "mastermind.at09_native_inventory_fixture.v1", "capture_state": "COMPLETE",
            "recorded_clock_ms": NOW * 1000,
            "source": {"cache_publication": before, "work_ref": "WS:ONE", "root_job_id": None},
            "premises": ["Synthetic fixture JWKS/JWT and existing enrolled Workspace binding",
                "Canonical temporary published Control Room cache input; actual presenter/service/HTTP owner",
                "Actual capability.census with controlled absent executable/app ports; no real host probe",
                "Same-cache Programs result; no Runtime/Job/Attempt/provider/liveness/eligibility claim"],
            "samples": [sample(inventory, ROUTE), sample(programs, "/workspace/programs/current")]}
        dest = Path(output); dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + ".tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        os.replace(temporary, dest)


@pytest.mark.parametrize("kind", ["unsigned", "foreign", "scope", "query", "body", "method", "alias"])
def test_scope_and_zero_selector_fences_refuse_before_owner(tmp_path, rsa_key, kind):
    s = source(tmp_path, rsa_key)
    headers = {"Authorization": "Bearer " + s.token}; path = ROUTE
    if kind == "unsigned": headers = {}
    elif kind == "foreign": headers = {"Authorization": "Bearer " + _workspace_token(rsa_key, sub="foreign")}
    elif kind == "scope": headers = {"Authorization": "Bearer " + _workspace_token(rsa_key, scope="mastermind.workspace.content.read")}
    elif kind == "query": path += "?host_ref=foreign"
    elif kind == "alias": path += "/"
    response = s.http.request("POST" if kind == "method" else "GET", path, headers=headers,
        content=b"{}" if kind == "body" else None)
    assert response.status_code in (400, 401, 403, 404, 405)
    assert s.frames == [] and "capabilities" not in response.text


def test_missing_existing_presenter_stays_unavailable(tmp_path, rsa_key):
    s = source(tmp_path, rsa_key); s.service._control_room_presenter = None
    response = s.http.get(ROUTE, headers={"Authorization": "Bearer " + s.token})
    assert response.status_code == 503 and "capabilities" not in response.text


def test_publication_drift_discards_captured_body(tmp_path, rsa_key, monkeypatch):
    s = source(tmp_path, rsa_key); original = ccr._cached_state_snapshot
    def drift(owner):
        body = original(owner)
        owner.state_published_seq += 1
        return body
    monkeypatch.setattr(ccr, "_cached_state_snapshot", drift)
    response = s.http.get(ROUTE, headers={"Authorization": "Bearer " + s.token})
    assert response.status_code == 503 and "capabilities" not in response.text


@pytest.mark.parametrize("kind", ["grant", "expiry", "owner"])
def test_http_release_rechecks_current_owner_grant_and_expiry(tmp_path, rsa_key, kind):
    s = source(tmp_path, rsa_key)
    def withdraw():
        if kind == "grant": s.bindings["profiles"]["web"]["enabled"] = False
        elif kind == "expiry": s.clock[0] = s.principal.expires_at
        else: object.__setattr__(s.config, "authorize_principal", lambda _: True)
    s.transport.after = withdraw
    response = s.http.get(ROUTE, headers={"Authorization": "Bearer " + s.token})
    assert response.status_code == 403 and "capabilities" not in response.text

@pytest.mark.skipif(os.environ.get("MM_AT09_NATIVE_BRIDGE") != "1", reason="opt-in Mac Rust/owned HTTP bridge only")
def test_registered_native_read_crosses_signed_http_and_actual_presenter(tmp_path, rsa_key, monkeypatch):
    """Real Rust request/body/generation code; fixed-origin loopback test shim.

    The production command still has no caller URL. The ignored Rust test alone
    maps its verified fixed request to this owned temporary HTTP listener.
    """
    import http.server
    import subprocess
    import threading
    s = source(tmp_path, rsa_key)
    original_presenter = s.service._control_room_presenter
    original_snapshot = ccr._cached_state_snapshot
    phases = {"number": 0, "drift": False}
    def snapshot(owner):
        body = original_snapshot(owner)
        if phases["drift"]:
            owner.state_published_seq += 1
        return body
    monkeypatch.setattr(ccr, "_cached_state_snapshot", snapshot)
    samples = []
    # Same cache publication, before adverse mutations, no transplanted receipt.
    programs = s.http.get("/workspace/programs/current", headers={"Authorization":"Bearer "+s.token})
    assert programs.status_code == 200
    samples.append(sample(programs,"/workspace/programs/current"))
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            assert self.path == ROUTE and self.headers["Host"] == "mcp.mastermind-x.com"
            assert self.headers["Accept"] == "application/json" and self.headers["Cache-Control"] == "no-store"
            assert self.headers.get("Content-Length") in (None,"0")
            phase = phases["number"]; phases["number"] += 1
            s.service._control_room_presenter = None if phase == 1 else original_presenter
            s.bindings["profiles"]["web"]["enabled"] = phase != 2
            phases["drift"] = phase == 3
            response = s.http.get(ROUTE, headers={"Authorization":self.headers.get("Authorization","")})
            samples.append(sample(response,ROUTE))
            self.send_response(response.status_code)
            self.send_header("Content-Type", response.headers["content-type"])
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers(); self.wfile.write(response.content)
    listener = http.server.HTTPServer(("127.0.0.1",0),Handler)
    thread = threading.Thread(target=listener.serve_forever,daemon=True); thread.start()
    native_return = tmp_path/"native-result.json"
    env = dict(os.environ)
    for key in ("GH_TOKEN","GITHUB_TOKEN","OPENAI_API_KEY","ANTHROPIC_API_KEY"):
        env.pop(key,None)
    env.update(MM_AT09_FIXTURE_ORIGIN=f"http://127.0.0.1:{listener.server_port}/",
        MM_AT09_FIXTURE_TOKEN=s.token, MM_AT09_NATIVE_RETURN=str(native_return))
    result = None
    try:
        result = subprocess.run(["cargo","test","--offline","auth::control_room_read::tests::same_run_signed_http_fixture_bridge",
            "--","--ignored","--exact"], cwd=Path(__file__).parents[1]/"app/mastermind_os/src-tauri",
            env=env,capture_output=True,text=True,timeout=180)
    finally:
        listener.shutdown();listener.server_close();thread.join(timeout=2)
        output = os.environ.get("MM_AT09_HTTP_OUTPUT")
        if output:
            document = {"schema":"mastermind.at09_native_inventory_http_fixture.v1",
                "capture_state":"COMPLETE" if result is not None and result.returncode == 0 and len(samples)==5 else "PARTIAL_UNQUALIFIED",
                "recorded_clock_ms":NOW*1000,"samples":samples,
                "native":json.loads(native_return.read_text()) if native_return.exists() else None,
                "premises":["Synthetic enrolled signed Workspace JWT/JWKS, never real credentials",
                    "Actual canonical compositor/cache/census with controlled absence ports",
                    "Actual Rust fixed HTTPS request validated then mapped only by cfg(test) to owned loopback listener",
                    "Actual HTTP Workspace authentication/frame/service/presenter and native bounded read",
                    "Four fresh phases: available, missing presenter, revoked binding, mid-read publication drift",
                    "No live origin/server installation/host probe/Runtime/Job/Attempt/provider/eligibility proof"]}
            dest=Path(output);temporary=dest.with_name(dest.name+".tmp")
            temporary.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n")
            os.replace(temporary,dest)
    assert result is not None and result.returncode == 0, (result.stderr.replace(s.token,"[FIXTURE_TOKEN]")[-6000:] if result else "no native result")
    assert [row["response"]["status"] for row in samples] == [200,200,503,403,503]
    assert samples[0]["response"]["body"]["control_room"] == samples[1]["response"]["body"]["control_room"]
