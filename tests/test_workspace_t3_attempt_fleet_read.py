"""Per-attempt T3 fleet reads through the signed Workspace path.

All state files, censuses, clocks and credentials below are disposable test
fixtures.  These are source/transport proofs, never live thread, process or
adapter-state observations: no test launches, interrupts or writes the real
adapter state.  Honest unknowns stay 200; typed refusals carry no evidence;
request and auth faults are the only 4xx.
"""
import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from common import workspace_t3_attempt_fleet_contract as wire
from control_plane.t3_attempt_fleet_projection import FLEET_SCHEMA, T3AttemptFleetError
from control_plane.t3_process_census import CensusProcess, CensusSnapshot
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.workspace_t3_attempt_fleet_read import (
    ExistingT3AttemptFleetSource, handle_t3_attempt_fleet_frame,
)
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from tests import test_workspace_admitted_plan_read as transport_suite
from tests.test_workspace_admitted_plan_read import plan_owner
from tests.test_workspace_read_app import NOW, _authenticator, _workspace_token, rsa_key
from tests.test_workspace_read_socket import short_socket_root
from tests.test_t3_attempt_fleet_projection import (
    CLAUDE_HARNESS_ARGV, KEY_A, NS, NOW as PROJ_NOW, NOW_ISO, THREAD_1,
    WORKSPACE, _intent, _receipt, _spec,
)

ROUTE = "/workspace/resources/t3/attempts/current"
ATTEMPT_ID = "runs/att-1"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "integrations/mmos/fixtures/t3_attempt_fleet_v1"


# ── fixture state (real adapter schema; synthetic census; fixed clock) ──────


def _state_file(tmp_path, rows):
    """Create the REAL adapter-state schema, then insert raw JSON rows."""
    from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore

    path = tmp_path / "t3_adapter_state.sqlite3"
    store = SQLiteT3AdapterStateStore(path)  # writes the reviewed schema only
    store.close()
    connection = sqlite3.connect(path)
    for record in rows:
        connection.execute(
            "INSERT INTO t3_adapter_runs (run_id, intent_json, receipt_json,"
            " spec_json, cursor_text, schema_version, updated_ms)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                record["run_id"],
                json.dumps(record.get("intent")),
                json.dumps(record.get("receipt")) if record.get("receipt") else None,
                json.dumps(record.get("spec")) if record.get("spec") else None,
                "",
                "mastermind.t3_adapter_state/v1",
                1,
            ),
        )
    connection.commit()
    connection.close()
    return path


def healthy_state(tmp_path):
    return _state_file(
        tmp_path,
        [{"run_id": ATTEMPT_ID, "intent": _intent(), "receipt": _receipt(), "spec": _spec()}],
    )


def fresh_census():
    return CensusSnapshot(
        observed_at_utc=NOW_ISO,
        processes=(CensusProcess(pid=100, ppid=1, argv=tuple(CLAUDE_HARNESS_ARGV), started_epoch_s=1_800_000_000.0),),
    )


def installed_source(tmp_path, *, census=lambda: fresh_census()):
    return ExistingT3AttemptFleetSource(
        adapter_state_path=healthy_state(tmp_path),
        census=census,
        clock=lambda: PROJ_NOW,
    )


# ── composition ─────────────────────────────────────────────────────────────


def test_composition_reads_real_schema_and_projects_one_proven_attempt(tmp_path):
    document = installed_source(tmp_path).read(ATTEMPT_ID)
    assert wire.validate_document(document) is document
    attempt = document["attempts"][0]
    assert attempt["attempt_id"] == ATTEMPT_ID
    assert attempt["invariant"] == {
        "exactly_one_thread": "PROVEN",
        "exactly_one_harness": "PROVEN",
    }
    assert attempt["harness_process"]["pid"] == 100
    assert attempt["duplicate_launcher"]["observed"] is False
    assert document["notes"] == []
    assert document["evaluated_at_utc"] == "2026-11-09T12:00:00+00:00"


def test_composition_missing_state_is_honest_empty_unknown(tmp_path):
    source = ExistingT3AttemptFleetSource(
        adapter_state_path=tmp_path / "absent.sqlite3",
        census=lambda: fresh_census(),
        clock=lambda: PROJ_NOW,
    )
    document = source.read(ATTEMPT_ID)
    assert document["schema"] == FLEET_SCHEMA
    assert document["notes"] == ["ADAPTER_STATE_EMPTY"]
    attempt = document["attempts"][0]
    assert attempt["t3_thread"]["thread_id"] is None
    assert attempt["t3_thread"]["unknown_reason"] == "NO_ADAPTER_ROW"
    assert attempt["invariant"]["exactly_one_thread"] == "UNKNOWN"


def test_composition_failed_census_is_absent_evidence_not_a_dead_read(tmp_path):
    def broken_census():
        raise RuntimeError("no ps on this host")
    document = installed_source(tmp_path, census=broken_census).read(ATTEMPT_ID)
    assert "CENSUS_ABSENT" in document["notes"]
    attempt = document["attempts"][0]
    assert attempt["harness_process"]["pid"] is None
    assert attempt["harness_process"]["unknown_reason"] == "CENSUS_ABSENT"
    assert attempt["invariant"]["exactly_one_harness"] == "UNKNOWN"


def test_composition_corrupt_row_is_typed_refusal_never_partial(tmp_path):
    path = healthy_state(tmp_path)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE t3_adapter_runs SET intent_json='not-json' WHERE run_id=?", (ATTEMPT_ID,))
    connection.commit()
    connection.close()
    document = ExistingT3AttemptFleetSource(path, census=lambda: fresh_census(), clock=lambda: PROJ_NOW).read(ATTEMPT_ID)
    assert document == {"schema": FLEET_SCHEMA, "refusal": "ADAPTER_ROW_MALFORMED", "attempts": []}
    assert wire.validate_document(document) is document


def test_composition_foreign_schema_is_typed_refusal(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE other (x TEXT)")
    connection.commit()
    connection.close()
    document = ExistingT3AttemptFleetSource(path, census=lambda: fresh_census(), clock=lambda: PROJ_NOW).read(ATTEMPT_ID)
    assert document == {"schema": FLEET_SCHEMA, "refusal": "ADAPTER_STATE_SCHEMA_UNKNOWN", "attempts": []}


def test_every_projection_refusal_code_is_wire_legal():
    # Completeness: no T3AttemptFleetError code can make the envelope itself
    # invalid — the fail-closed path always has a typed document.
    import inspect
    from control_plane import t3_attempt_fleet_projection as projection
    raisable = set()
    source = inspect.getsource(projection)
    marker = "_refuse("
    index = 0
    while True:
        index = source.find(marker, index)
        if index < 0:
            break
        tail = source[index + len(marker):]
        token = tail.split('"')[1]
        if token and token.isupper():  # skip prose fragments and non-code matches
            raisable.add(token)
        index += len(marker)
    assert raisable <= wire.REFUSALS, raisable - wire.REFUSALS


@pytest.mark.parametrize("bad", ["", "../escape", "runs/att-1 extra", "runs/" + "x" * 200, 403, None])
def test_attempt_id_grammar_refuses_paths_and_oversize(bad):
    with pytest.raises(ValueError):
        wire.attempt_id(bad)


# ── frame handler ───────────────────────────────────────────────────────────


class _Owner:
    def __init__(self, source):
        self._t3_attempt_fleet_source = source
        self.authorize = lambda principal: True
        self.authorize.binding_digest = lambda principal: "a" * 64


def _frame():
    return {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
            "selection": ATTEMPT_ID, "principal": {"sub": "fixture"}}


def test_frame_handler_without_installed_source_serves_typed_refusal():
    result = asyncio.run(handle_t3_attempt_fleet_frame(_Owner(None), _frame()))
    assert result == {"ok": True, "result": {"schema": FLEET_SCHEMA, "refusal": "SOURCE_UNAVAILABLE", "attempts": []}}


def test_frame_handler_refuses_foreign_frame_shape():
    owner = _Owner(None)
    for frame in (None, {}, {**_frame(), "schema": "foreign"}, {**_frame(), "extra": 1},
                  {**_frame(), "selection": "../escape"}):
        result = asyncio.run(handle_t3_attempt_fleet_frame(owner, frame))
        assert result["ok"] is False and result["status"] == 400


def test_frame_handler_serves_source_swapped_as_source_changed(tmp_path, monkeypatch):
    owner = _Owner(installed_source(tmp_path))
    real_read = ExistingT3AttemptFleetSource.read

    def swap_mid_read(self, attempt_id):
        owner._t3_attempt_fleet_source = ExistingT3AttemptFleetSource(
            adapter_state_path=self.adapter_state_path, census=self.census, clock=self.clock)
        return real_read(self, attempt_id)

    monkeypatch.setattr(ExistingT3AttemptFleetSource, "read", swap_mid_read)
    result = asyncio.run(handle_t3_attempt_fleet_frame(owner, _frame()))
    assert result == {"ok": True, "result": {"schema": FLEET_SCHEMA, "refusal": "SOURCE_CHANGED", "attempts": []}}


def test_frame_handler_denies_revoked_principal(tmp_path, monkeypatch):
    owner = _Owner(installed_source(tmp_path))
    calls = {"authorize": 0}

    def authorize(principal):
        calls["authorize"] += 1
        return calls["authorize"] == 1  # revoked between stamp and recheck

    owner.authorize = authorize
    result = asyncio.run(handle_t3_attempt_fleet_frame(owner, _frame()))
    assert result["ok"] is False and result["status"] == 403


# ── signed HTTP route (real app dispatcher) ─────────────────────────────────


@asynccontextmanager
async def in_process_transport(owner, key, tmp_path, socket_root, *, after_app=None):
    auth = _authenticator(key)
    token = _workspace_token(key)
    principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
    slots = {"schema": BINDINGS_SCHEMA, "profiles": {
        "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
        "mac": {"enabled": False, "binding": None}}}
    app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
    clock, seen = [NOW], {"factory": 0}
    class Client:
        async def request(self, frame):
            seen["factory"] += 1
            result = await transport_suite.service(owner, authorize=control_auth).handle_frame(frame)
            if after_app:
                after_app(slots, clock)
            return result
    app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: clock[0],
        authorize_principal=app_auth, client=Client()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as http:
        yield http, token, slots, seen


@pytest.fixture(params=["asgi", "unix"])
def bridge(request):
    return in_process_transport if request.param == "asgi" else transport_suite.transport


@pytest.fixture
def composed(tmp_path, monkeypatch):
    source = installed_source(tmp_path)
    def service(owner, authorize=lambda _: True):
        return WorkspaceReadService(cache=owner["cache"], runtime=owner["writer"], authorize=authorize,
            armed={}, runtime_identity={"db_present": True}, t3_attempt_fleet_source=source,
            bounded_runtime=lambda actual: owner["reader"] if actual is owner["writer"] else pytest.fail("wrong owner"))
    monkeypatch.setattr(transport_suite, "service", service)
    return source


def test_signed_http_serves_the_exact_fixture_document(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            before = plan_owner["namespace"].entries, composed.adapter_state_path.read_bytes()
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT_ID},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            assert response.json() == json.loads((FIXTURE_DIR / "attempt.json").read_text())
            assert response.headers["cache-control"] == "no-store"
            assert seen["factory"] == 1
            assert before == (plan_owner["namespace"].entries, composed.adapter_state_path.read_bytes())
            # raw (unencoded) slash in the query value rides the same decoder
            raw = await http.get(ROUTE + "?attempt_id=" + ATTEMPT_ID,
                                 headers={"Authorization": "Bearer " + token})
            assert raw.status_code == 200 and raw.json()["attempts"][0]["attempt_id"] == ATTEMPT_ID
    asyncio.run(run())


def test_signed_http_serves_honest_unknown_for_unrecorded_attempt(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, params={"attempt_id": "runs/never-recorded"},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            # The store holds one recorded attempt; an unrecorded id is an
            # honestly unknown attempt, not an empty-store note.
            assert body["notes"] == []
            assert body["attempts"][0]["t3_thread"]["unknown_reason"] == "NO_ADAPTER_ROW"
            assert body["attempts"][0]["invariant"]["exactly_one_thread"] == "UNKNOWN"
    asyncio.run(run())


def test_signed_http_serves_typed_refusal_for_corrupt_state(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge, monkeypatch):
    corrupt = tmp_path / "corrupt.sqlite3"
    connection = sqlite3.connect(corrupt)
    connection.execute("CREATE TABLE other (x TEXT)")
    connection.commit()
    connection.close()
    def service(owner, authorize=lambda _: True):
        return WorkspaceReadService(cache=owner["cache"], runtime=owner["writer"], authorize=authorize,
            armed={}, runtime_identity={"db_present": True},
            t3_attempt_fleet_source=ExistingT3AttemptFleetSource(corrupt, census=lambda: fresh_census(), clock=lambda: PROJ_NOW),
            bounded_runtime=lambda actual: owner["reader"] if actual is owner["writer"] else pytest.fail("wrong owner"))
    monkeypatch.setattr(transport_suite, "service", service)
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT_ID},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            assert response.json() == json.loads((FIXTURE_DIR / "refusal.json").read_text())
    asyncio.run(run())


@pytest.mark.parametrize("case", [
    "missing_query", "foreign_key", "duplicate_key", "bad_id", "missing_auth",
    "foreign_scope", "body", "post", "encoded_route",
])
def test_fixed_authenticated_read_rejects_caller_sources_before_factory(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, case, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            method, url = "GET", ROUTE
            kwargs = {"headers": {"Authorization": "Bearer " + token}}
            if case == "missing_query": url = ROUTE
            elif case == "foreign_key": url = ROUTE + "?attempt=runs/att-1"
            elif case == "duplicate_key": url = ROUTE + "?attempt_id=runs/att-1&attempt_id=runs/att-2"
            elif case == "bad_id": url = ROUTE + "?attempt_id=../escape"
            elif case == "missing_auth": kwargs["headers"] = {}
            elif case == "foreign_scope": kwargs["headers"]["Authorization"] = "Bearer " + _workspace_token(rsa_key, scope="mastermind.executive.read")
            elif case == "body": kwargs["content"] = b'{"attempt_id":"runs/att-1"}'
            elif case == "post": method = "POST"
            else: url = "/workspace/resources/t3/att%65mpts/current?attempt_id=" + ATTEMPT_ID
            response = await http.request(method, url, **kwargs)
            assert response.status_code in (400, 401, 403, 404, 405), response.text
            assert seen["factory"] == 0
    asyncio.run(run())


@pytest.mark.parametrize("case", ["disabled", "permission_changed", "expired"])
def test_http_release_rechecks_auth_and_principal_expiry(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, case, bridge):
    def after(slots, clock):
        if case == "disabled": slots["profiles"]["web"]["enabled"] = False
        elif case == "permission_changed": slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64
        else: clock[0] += 86400
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root, after_app=after) as (http, token, *_):
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT_ID},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 403, response.text
            assert "att-1" not in response.text
    asyncio.run(run())
