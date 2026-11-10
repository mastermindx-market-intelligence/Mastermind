"""The fixed authenticated T3 thread-list GET through the real app dispatcher.

Fixtures only: a disposable adapter-state file under ``tmp_path`` and a
disposable attested environment fact.  These are source/transport proofs — no
test launches, interrupts, sends to or changes anything live.  The route takes
no caller selection at all: any query key is a 400 and the installed source is
never reached.
"""
import asyncio
import json
import sqlite3

import pytest

from common import workspace_t3_thread_projection_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.workspace_t3_thread_projection_read import ExistingT3ThreadProjectionSource
from tests import test_workspace_admitted_plan_read as transport_suite
from tests.test_workspace_admitted_plan_read import plan_owner
from tests.test_workspace_read_app import _workspace_token, rsa_key
from tests.test_workspace_read_socket import short_socket_root
from tests.test_t3_attempt_fleet_projection import NOW_ISO, THREAD_1, _intent, _spec
from tests.test_workspace_t3_attempt_fleet_read import bridge, in_process_transport

ROUTE = "/workspace/resources/t3/threads/current"
ENVIRONMENT_ID = "m2studio"
HTTPS_LINK = "https://t3.example.com/threads/abc"
ENVIRONMENT_DOC = {
    "schema": "mastermind.t3_environment_observation/v1",
    "environment_id": ENVIRONMENT_ID,
    "observed_at_utc": NOW_ISO,
    "source": "tests.workspace_t3_thread_projection_http",
}


# ── fixture state (real adapter schema; synthetic rows) ─────────────────────


def _state_file(tmp_path, rows):
    from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore

    path = tmp_path / "t3_adapter_state.sqlite3"
    store = SQLiteT3AdapterStateStore(path)
    store.close()
    connection = sqlite3.connect(path)
    for index, status in enumerate(rows):
        intent = _intent(run_id=f"runs/att-{index}")
        intent["envelope"]["title"] = f"thread {index}"
        receipt = {
            "schema": "mastermind.t3_thread_launch_receipt/v1",
            "thread_id": THREAD_1 if index == 0 else "mcp:launch:" + format(index, "064d"),
            "run_id": "run:thread:x:ordinal:" + str(index),
            "project_id": "",
            "status": status,
            "link": HTTPS_LINK if index == 0 else "",
            "created_at": NOW_ISO,
        }
        connection.execute(
            "INSERT INTO t3_adapter_runs (run_id, intent_json, receipt_json,"
            " spec_json, cursor_text, schema_version, updated_ms)"
            " VALUES (?,?,?,?,?,?,?)",
            (f"runs/att-{index}", json.dumps(intent), json.dumps(receipt),
             json.dumps(_spec()), "", "mastermind.t3_adapter_state/v1", 1),
        )
    connection.commit()
    connection.close()
    return path


def _environment_file(tmp_path):
    path = tmp_path / "t3_environment_observation.json"
    path.write_text(json.dumps(ENVIRONMENT_DOC), encoding="utf-8")
    return path


def installed_source(tmp_path, rows=("preparing",)):
    return ExistingT3ThreadProjectionSource(
        adapter_state_path=_state_file(tmp_path, rows),
        environment_path=_environment_file(tmp_path),
    )


EXPECTED_THREAD = {
    "threadId": THREAD_1,
    "environment": ENVIRONMENT_ID,
    "title": "thread 0",
    "runState": "running",
    "lastActivity": NOW_ISO,
    "prLink": HTTPS_LINK,
    "repository": None,
    "companyManaged": True,
}


def _compose(monkeypatch, source):
    def service(owner, authorize=lambda _: True):
        return WorkspaceReadService(
            cache=owner["cache"], runtime=owner["writer"], authorize=authorize,
            armed={}, runtime_identity={"db_present": True},
            t3_thread_projection_source=source,
            bounded_runtime=lambda actual: owner["reader"]
            if actual is owner["writer"] else pytest.fail("wrong owner"))
    monkeypatch.setattr(transport_suite, "service", service)


@pytest.fixture
def composed(tmp_path, monkeypatch):
    source = installed_source(tmp_path)
    _compose(monkeypatch, source)
    return source


# ── available document ──────────────────────────────────────────────────────


def test_signed_http_serves_the_exact_projection_document(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            before = (plan_owner["namespace"].entries, composed.adapter_state_path.read_bytes())
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            assert wire.validate_document(body) is not None
            assert body == {"schema": wire.LIST_SCHEMA, "availability": "AVAILABLE",
                            "reason": None, "threads": [EXPECTED_THREAD]}
            assert response.headers["cache-control"] == "no-store"
            assert seen["factory"] == 1
            assert before == (plan_owner["namespace"].entries,
                              composed.adapter_state_path.read_bytes())
    asyncio.run(run())


def test_signed_http_serves_honest_empty_list_for_a_missing_store(
        plan_owner, rsa_key, tmp_path, short_socket_root, bridge, monkeypatch):
    _compose(monkeypatch, ExistingT3ThreadProjectionSource(
        adapter_state_path=tmp_path / "absent.sqlite3",
        environment_path=_environment_file(tmp_path)))

    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            assert response.json() == {"schema": wire.LIST_SCHEMA,
                                       "availability": "AVAILABLE",
                                       "reason": None, "threads": []}
    asyncio.run(run())


# ── honest absence / typed refusals are served, not 500s ────────────────────


def test_signed_http_serves_unavailable_when_the_environment_source_is_absent(
        plan_owner, rsa_key, tmp_path, short_socket_root, bridge, monkeypatch):
    _compose(monkeypatch, ExistingT3ThreadProjectionSource(
        adapter_state_path=_state_file(tmp_path, ["preparing"]),
        environment_path=None))

    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 503, response.text
            assert response.json() == wire.unavailable("T3_ENVIRONMENT_SOURCE_UNAVAILABLE")
            assert response.headers["cache-control"] == "no-store"
    asyncio.run(run())


def test_signed_http_serves_a_typed_refusal_for_a_corrupt_store(
        plan_owner, rsa_key, tmp_path, short_socket_root, bridge, monkeypatch):
    corrupt = tmp_path / "corrupt.sqlite3"
    connection = sqlite3.connect(corrupt)
    connection.execute("CREATE TABLE other (x TEXT)")
    connection.commit()
    connection.close()
    _compose(monkeypatch, ExistingT3ThreadProjectionSource(
        adapter_state_path=corrupt, environment_path=_environment_file(tmp_path)))

    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 503, response.text
            assert response.json() == wire.unavailable("ADAPTER_STATE_SCHEMA_UNKNOWN")
    asyncio.run(run())


# ── the route takes no caller selection ─────────────────────────────────────


@pytest.mark.parametrize("case", [
    "query_key", "landing_key", "duplicate_key", "missing_auth", "foreign_scope",
    "body", "post", "encoded_route",
])
def test_fixed_authenticated_read_rejects_caller_input_before_the_source(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, case, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            method, url = "GET", ROUTE
            kwargs = {"headers": {"Authorization": "Bearer " + token}}
            if case == "query_key":
                url = ROUTE + "?thread_id=" + THREAD_1
            elif case == "landing_key":
                url = ROUTE + "?environment=" + ENVIRONMENT_ID
            elif case == "duplicate_key":
                url = ROUTE + "?thread_id=a&thread_id=b"
            elif case == "missing_auth":
                kwargs["headers"] = {}
            elif case == "foreign_scope":
                kwargs["headers"]["Authorization"] = \
                    "Bearer " + _workspace_token(rsa_key, scope="mastermind.executive.read")
            elif case == "body":
                kwargs["content"] = b'{"thread_id":"' + THREAD_1.encode() + b'"}'
            elif case == "post":
                method = "POST"
            else:
                url = "/workspace/resources/t3/thr%65ads/current"
            response = await http.request(method, url, **kwargs)
            assert response.status_code in (400, 401, 403, 404, 405), response.text
            assert seen["factory"] == 0
    asyncio.run(run())


# ── release rechecks ────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", ["disabled", "permission_changed", "expired"])
def test_http_release_rechecks_auth_and_principal_expiry(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, case, bridge):
    def after(slots, clock):
        if case == "disabled":
            slots["profiles"]["web"]["enabled"] = False
        elif case == "permission_changed":
            slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64
        else:
            clock[0] += 86400

    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root, after_app=after) as (http, token, *_):
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 403, response.text
            assert THREAD_1 not in response.text
    asyncio.run(run())


def test_route_and_fleet_route_are_distinct_paths(composed, plan_owner, rsa_key,
                                                  tmp_path, short_socket_root, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            threads = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert threads.status_code == 200, threads.text
            # The thread list is its own fixed route; it accepts no attempt id.
            attempts = await http.get("/workspace/resources/t3/attempts/current",
                                      headers={"Authorization": "Bearer " + token})
            assert attempts.status_code in (400, 503), attempts.text
    asyncio.run(run())
