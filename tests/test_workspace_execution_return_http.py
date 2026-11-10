"""The fixed authenticated execution-return GET through the real app dispatcher.

Fixtures only: a disposable ``RuntimeStore`` under ``tmp_path`` carrying the
exact event rows the seam writes.  These are source/transport proofs — no test
delivers, retries, admits or changes a real job.  The route's only caller
selection is the strict v2 ``?attempt_id=<run id>`` query key; any other input
is refused before the installed source is reached.  The ``bridge`` fixture
runs every test twice: once in-process (asgi) and once through the real CEO
ingress unix socket + mounted executive MCP fence (unix), which exercises the
``installed.py`` frame-validation branch on the socket path.
"""
import asyncio

import pytest

from common import workspace_execution_return_contract as wire
from control_plane.workspace_execution_return_read import ExistingExecutionReturnSource
from control_plane.workspace_read_service import WorkspaceReadService
from tests import test_workspace_admitted_plan_read as transport_suite
from tests.test_workspace_admitted_plan_read import plan_owner
from tests.test_workspace_read_app import _workspace_token, rsa_key
from tests.test_workspace_read_socket import short_socket_root
from tests.test_workspace_t3_attempt_fleet_read import bridge, in_process_transport

ROUTE = "/workspace/resources/execution-returns/current"
ATTEMPT = "runs/att-1"
JOB = "JOB-42"
NOW_ISO = "2026-11-10T12:00:00+00:00"
RECEIPT_DIGEST = "a" * 64
TRANSPORT_REF = "t3://thread/abc/run/77"

RECEIPT = {
    "schema": wire.DELIVERY_SCHEMA,
    "return_id": "ret-1",
    "return_digest": RECEIPT_DIGEST,
    "conversation_id": "conv-1",
    "submission_id": "execret-" + "0" * 32,
    "state": "delivered",
    "transport_ref": TRANSPORT_REF,
    "refusal_code": None,
}


def _clock():
    from datetime import datetime, timezone
    return datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _write_store(tmp_path, events):
    """Create a real RuntimeStore and append the seam-shaped rows through it."""
    from control_plane.executive_runtime import RuntimeStore

    store = RuntimeStore(tmp_path)
    with store.transaction() as connection:
        for event in events:
            store.append_event(
                connection,
                aggregate_type=event.get("aggregate_type", "attempt"),
                aggregate_id=event.get("aggregate_id", ATTEMPT),
                event_type=event["event_type"],
                job_id=event.get("job_id"),
                attempt_id=event.get("attempt_id"),
                payload=event.get("payload") or {},
                command_id=event.get("command_id"),
            )
    return RuntimeStore(tmp_path)


def _receipt_event(payload=None):
    from control_plane.execution_return_wiring import (
        EXECUTION_RETURN_DELIVERY_EVENT,
        execution_return_receipt_command_id,
    )
    return {
        "event_type": EXECUTION_RETURN_DELIVERY_EVENT,
        "job_id": JOB,
        "attempt_id": ATTEMPT,
        "payload": {"delivery": dict(RECEIPT)} if payload is None else payload,
        "command_id": execution_return_receipt_command_id(ATTEMPT),
    }


def _job_created(job_id, provenance):
    return {
        "aggregate_type": "job", "aggregate_id": job_id,
        "event_type": "JOB_CREATED", "job_id": job_id,
        "payload": {"provenance": provenance},
    }


def installed_source(tmp_path, events=()):
    return ExistingExecutionReturnSource(
        store=_write_store(tmp_path, list(events)), clock=_clock)


def _compose(monkeypatch, source):
    def service(owner, authorize=lambda _: True):
        return WorkspaceReadService(
            cache=owner["cache"], runtime=owner["writer"], authorize=authorize,
            armed={}, runtime_identity={"db_present": True},
            execution_return_source=source,
            bounded_runtime=lambda actual: owner["reader"]
            if actual is owner["writer"] else pytest.fail("wrong owner"))
    monkeypatch.setattr(transport_suite, "service", service)


@pytest.fixture
def composed(tmp_path, monkeypatch):
    source = installed_source(tmp_path, [_receipt_event()])
    _compose(monkeypatch, source)
    return source


def _event_rows(source):
    return [(e.event_type, e.command_id) for e in source.store.list_events()]


# ── available document ──────────────────────────────────────────────────────


def test_signed_http_serves_the_exact_projection_document(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            before = (plan_owner["namespace"].entries, _event_rows(composed))
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            assert wire.validate_document(body) is not None
            assert body == {"schema": wire.READ_SCHEMA, "availability": "AVAILABLE",
                            "reason": None, "attempt_id": ATTEMPT, "job_id": JOB,
                            "delivery": RECEIPT, "stage": None,
                            "refusal_detail": None, "original_requester": None,
                            "read_at_utc": NOW_ISO}
            assert response.headers["cache-control"] == "no-store"
            assert seen["factory"] == 1
            # The read never appended or rewrote a store row.
            assert before == (plan_owner["namespace"].entries, _event_rows(composed))
            # The raw (unencoded) slash of a run id rides the same decoder.
            raw = await http.get(ROUTE + "?attempt_id=" + ATTEMPT,
                                 headers={"Authorization": "Bearer " + token})
            assert raw.status_code == 200 and raw.json()["attempt_id"] == ATTEMPT
    asyncio.run(run())


def test_signed_http_projects_job_id_stage_and_the_requester_join(
        plan_owner, rsa_key, tmp_path, short_socket_root, bridge, monkeypatch):
    requester = {"teammate_id": "hermes-engineering", "conversation_id": "sess-3f9c2",
                 "project_id": "proj-mmos-v1", "carrier_kind": ""}
    source = installed_source(tmp_path, [
        _receipt_event(payload={"delivery": dict(RECEIPT), "stage": "checks_green"}),
        _job_created(JOB, {"original_requester": requester}),
    ])
    _compose(monkeypatch, source)

    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["job_id"] == JOB
            assert body["stage"] == "checks_green"
            assert body["original_requester"] == requester
            assert body["delivery"]["transport_ref"] == TRANSPORT_REF
    asyncio.run(run())


# ── honest absence / typed refusals are served, not 500s ────────────────────


def test_signed_http_serves_honest_absence_for_an_unrecorded_attempt(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, params={"attempt_id": "runs/never-recorded"},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body == wire.unavailable("runs/never-recorded",
                                            "EXECUTION_RETURN_NOT_RECORDED", NOW_ISO)
            assert body["delivery"] is None and body["job_id"] is None
    asyncio.run(run())


def test_signed_http_serves_a_typed_refusal_for_a_malformed_receipt_row(
        plan_owner, rsa_key, tmp_path, short_socket_root, bridge, monkeypatch):
    source = installed_source(tmp_path, [
        _receipt_event(payload={"delivery": {**RECEIPT, "state": "maybe"}})])
    _compose(monkeypatch, source)

    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["availability"] == "UNAVAILABLE"
            assert body["reason"] == "RECEIPT_PAYLOAD_MALFORMED"
            assert RECEIPT_DIGEST not in response.text  # never a partial receipt
    asyncio.run(run())


def test_signed_http_serves_source_unavailable_when_no_source_is_installed(
        plan_owner, rsa_key, tmp_path, short_socket_root, bridge, monkeypatch):
    _compose(monkeypatch, None)

    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["availability"] == "UNAVAILABLE"
            assert body["reason"] == "SOURCE_UNAVAILABLE"
    asyncio.run(run())


# ── caller input is refused before the source ────────────────────────────────


@pytest.mark.parametrize("case", [
    "query_key", "missing_attempt", "duplicate_key", "bad_attempt", "missing_auth",
    "foreign_scope", "body", "post", "encoded_route",
])
def test_fixed_authenticated_read_rejects_caller_input_before_the_source(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, case, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            method, url = "GET", ROUTE + "?attempt_id=" + ATTEMPT
            kwargs = {"headers": {"Authorization": "Bearer " + token}}
            if case == "query_key":
                url += "&extra=1"
            elif case == "missing_attempt":
                url = ROUTE
            elif case == "duplicate_key":
                url = ROUTE + "?attempt_id=a&attempt_id=b"
            elif case == "bad_attempt":
                url = ROUTE + "?attempt_id=../escape"
            elif case == "missing_auth":
                kwargs["headers"] = {}
            elif case == "foreign_scope":
                kwargs["headers"]["Authorization"] = \
                    "Bearer " + _workspace_token(rsa_key, scope="mastermind.executive.read")
            elif case == "body":
                kwargs["content"] = b'{"attempt_id":"' + ATTEMPT.encode() + b'"}'
            elif case == "post":
                method = "POST"
            else:
                url = "/workspace/resources/execution-r%65turns/current?attempt_id=" + ATTEMPT
            response = await http.request(method, url, **kwargs)
            assert response.status_code in (400, 401, 403, 404, 405), response.text
            assert seen["factory"] == 0
    asyncio.run(run())


def test_an_unauthorized_principal_gets_todays_refusal_and_no_receipt_facts(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge):
    """The required negative: a token outside this read's scope is refused
    exactly as every other fixed workspace read refuses it today — closed
    4xx, no receipt byte, the source never reached."""
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            foreign = _workspace_token(rsa_key, scope="mastermind.executive.read")
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT},
                                      headers={"Authorization": "Bearer " + foreign})
            assert response.status_code in (401, 403), response.text
            assert TRANSPORT_REF not in response.text
            assert RECEIPT_DIGEST not in response.text
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
            response = await http.get(ROUTE, params={"attempt_id": ATTEMPT},
                                      headers={"Authorization": "Bearer " + token})
            assert response.status_code == 403, response.text
            assert TRANSPORT_REF not in response.text
    asyncio.run(run())
