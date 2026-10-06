"""Read diagnostics must identify the observed boundary without implying execution."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile

import pytest

from integrations.executive_mcp.schemas import RESULT_SCHEMA, bound_document
from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_SERVER_VERSION
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient,
    CeoIngressReadGateway,
    CeoIngressResponse,
    TRANSPORT_NOT_SENT,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
    WebCeoCeoIngressReadGateway,
    WebCeoV2CeoIngressReadGateway,
)
from integrations.mosyle_mdm.executive import WebCeoV3CeoIngressReadGateway


SECRET = "/Users/private-owner/credentials/example-secret-value"


class UnusedMdm:
    async def list_macos_devices(self):
        raise AssertionError("Executive reads must not fall back to MDM")


def reader(profile, path, client):
    if profile is WebCeoV3CeoIngressReadGateway:
        return profile(path, client, mdm_reader=UnusedMdm())
    return profile(path, client)


PROFILES = (
    CeoIngressReadGateway,
    WebCeoCeoIngressReadGateway,
    WebCeoV2CeoIngressReadGateway,
    WebCeoV3CeoIngressReadGateway,
)

INGRESS_SERVER_VERSION = {
    CeoIngressReadGateway: "1.0.0",
    WebCeoCeoIngressReadGateway: "1.1.0",
    WebCeoV2CeoIngressReadGateway: "1.2.0",
    WebCeoV3CeoIngressReadGateway: "1.2.0",
}
OUTPUT_SERVER_VERSION = {
    **INGRESS_SERVER_VERSION,
    WebCeoV3CeoIngressReadGateway: WEB_CEO_V3_SERVER_VERSION,
}


def canonical_result(
    profile=CeoIngressReadGateway,
    *,
    ok=True,
    code="not_found",
    message="No matching runtime record",
):
    return {
        "schema": RESULT_SCHEMA,
        "tool": "executive_state",
        "ok": ok,
        "server_version": INGRESS_SERVER_VERSION[profile],
        "mode": "readonly",
        "generated_at": "2026-10-04T03:00:00+00:00",
        "grounding": ({
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
            "macro": {"root": "/macro", "sha": "b" * 40},
            "mastermind": {"branch": "HEAD", "root": "/mastermind", "sha": "a" * 40},
            "runtime": "readonly:installed-executive-runtime",
            "runtime_db": {"path": "/runtime/executive.sqlite3", "present": True},
        } if ok else {}),
        "data": {
            "mastermind": {"branch": "HEAD", "root": "/mastermind", "sha": "a" * 40},
            "macro": {"root": "/macro", "sha": "b" * 40, "resolved_via": "flag"},
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
            "inbox_schema": "mastermind.executive_inbox.v2",
            "strategic_state": {
            "schema": "mastermind.strategic_state.v1",
            "company_phase": "PRE_REVENUE_MVP_CONVERGENCE",
            "north_star": ["Build a trustworthy product."],
            "p0": [{
                "id": "EXECUTIVE_OS",
                "department": "executive",
                "objective": "Establish durable execution.",
                "status": "active",
            }],
            "constraints": {
                "new_feature_expansion": "constrained",
                "autonomous_production_deploy": "prohibited",
                "autonomous_live_capital_execution": "prohibited",
                "duplicate_control_planes": "prohibited",
                "marketing_org_expansion_before_distribution_proof": "prohibited",
                "unbounded_autonomous_strategic_modification": "prohibited",
            },
        },
            "next_recommended_act": "Review current attention.",
            "runtime_db": {"path": "/runtime/executive.sqlite3", "present": True},
            "runtime_counts": {
            "jobs": {
                "total": 2,
                "by_status": {
                    "QUEUED": 2, "RUNNING": 0, "CHECKPOINTED": 0,
                    "COMPLETED": 0, "FAILED": 0, "CANCEL_REQUESTED": 0,
                    "CANCELLED": 0, "LOST": 0, "RATE_LIMITED": 0,
                },
            },
            "attempts": {
                "total": 0,
                "by_status": {
                    "CLAIMED": 0, "RUNNING": 0, "CHECKPOINTED": 0,
                    "COMPLETED": 0, "FAILED": 0, "CANCEL_REQUESTED": 0,
                    "CANCELLED": 0, "LOST": 0, "RATE_LIMITED": 0,
                },
            },
            "workers": {
                "total": 0,
                "by_status": {
                    "AVAILABLE": 0, "BUSY": 0, "DRAINING": 0,
                    "OFFLINE": 0, "ERROR": 0, "RATE_LIMITED": 0,
                },
            },
        },
            "attention_counts": {"total": 0, "chairman": 0, "ceo": 0, "coo": 0},
            "handoffs": [],
        } if ok else None,
        "degraded": [],
        "bounded": [],
        "error": None if ok else {"code": code, "message": message},
    }


async def socket_read(profile, wire):
    frames = []
    completed = asyncio.Event()

    async def backend(stream, writer):
        try:
            frames.append(json.loads(await stream.readline()))
            if wire is not None:
                payload = wire if isinstance(wire, bytes) else json.dumps(wire).encode() + b"\n"
                writer.write(payload)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            completed.set()

    # Short AF_UNIX paths are required on macOS; never contact the installed socket.
    with tempfile.TemporaryDirectory(prefix="erd-", dir="/tmp") as directory:
        path = str(Path(directory) / "reader.sock")
        server = await asyncio.start_unix_server(backend, path=path)
        async with server:
            gateway = reader(profile, path, CeoIngressClient(connect_timeout=1, read_timeout=1))
            result = await gateway.call("executive_state", {})
            await asyncio.wait_for(completed.wait(), 1)
            await gateway.aclose()
        assert len(frames) == 1
        assert frames[0]["tool"] == "executive_state"
        assert frames[0]["arguments"] == {}
        return result


def assert_diagnostic(result, code, category):
    assert result["schema"] == RESULT_SCHEMA
    assert result["tool"] == "executive_state"
    assert result["ok"] is False
    assert result["mode"] == "readonly"
    assert result["data"] is None
    assert result["grounding"] == {}
    assert set(result["error"]) == {"code", "message"}
    assert result["error"]["code"] == code
    message = result["error"]["message"]
    assert category in message
    assert "read operation" in message
    assert "submission and execution readiness were not observed" in message
    assert SECRET not in json.dumps(result)
    assert "effect_unknown" not in json.dumps(result)
    assert "retry" not in message.lower()


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(
    ("wire", "code", "category"),
    [
        (None, "backend_unavailable", "after the read request was attempted"),
        (b"not-json\\n", "backend_unavailable", "after the read request was attempted"),
        ({"ok": 1}, "backend_unavailable", "after the read request was attempted"),
        ({"ok": False, "error": {"code": "peer_denied", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "peer_credentials_unavailable", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "unsupported_ingress_schema", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "internal_error", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "authority_refused", "message": SECRET}},
         "backend_refused", "permission was refused"),
        ({"ok": False, "error": {"code": "ingress_unavailable", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "backend_unavailable", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "invalid_input", "message": SECRET}},
         "backend_refused", "request was refused"),
        ({"ok": False, "error": {"code": "unrecognized-" + SECRET, "message": SECRET}},
         "backend_unavailable", "invalid response"),
    ],
)
def test_real_read_transport_distinguishes_failure_without_replay(profile, wire, code, category):
    assert_diagnostic(asyncio.run(socket_read(profile, wire)), code, category)


@pytest.mark.parametrize("profile", PROFILES)
def test_missing_socket_does_not_claim_reader_or_execution_ready(profile):
    with tempfile.TemporaryDirectory(prefix="erd-", dir="/tmp") as directory:
        gateway = reader(profile, str(Path(directory) / "absent.sock"), CeoIngressClient())
        result = asyncio.run(gateway.call("executive_state", {}))
    assert_diagnostic(result, "backend_unavailable", "request was not sent")


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(("mutate", "case"), [
    (lambda value: value.__setitem__("schema", "wrong-schema"), "wrong-schema"),
    (lambda value: value.__setitem__("tool", "executive_job"), "wrong-tool"),
    (lambda value: value.__setitem__("ok", 1), "non-bool-ok"),
    (lambda value: value.__setitem__("ok", None), "null-ok"),
    (lambda value: value.__setitem__("private_detail", SECRET), "extra-private-field"),
    (lambda value: value.__setitem__("mode", "write"), "wrong-mode"),
    (lambda value: value.__setitem__("server_version", "9.9.9"), "wrong-version"),
    (lambda value: value.__setitem__("generated_at", 1), "bad-generated-at"),
    (lambda value: value.__setitem__("generated_at", "not-a-time"), "malformed-generated-at"),
    (lambda value: value["grounding"].__setitem__("private_detail", SECRET), "private-grounding-field"),
    (lambda value: value["data"].__setitem__("execution_ready", True), "forged-readiness-field"),
    (lambda value: value["data"]["macro"].__setitem__("execution_ready", True), "nested-macro-readiness"),
    (lambda value: value["data"]["macro"].__setitem__("private_detail", SECRET), "nested-macro-private"),
    (lambda value: value["data"]["strategic_state"].__setitem__("private_detail", SECRET), "strategic-private"),
    (lambda value: value["data"]["strategic_state"]["p0"][0].__setitem__("private_detail", SECRET), "strategic-p0-private"),
    (lambda value: value["data"]["strategic_state"]["constraints"].__setitem__("execution_ready", "true"), "strategic-constraint-extra"),
    (lambda value: value["data"]["runtime_counts"].__setitem__("private_detail", SECRET), "runtime-counts-private"),
    (lambda value: value["data"]["attention_counts"].__setitem__("execution_ready", 1), "attention-counts-private"),
    (lambda value: value["data"]["handoffs"].append({"name": "x", "path": "agentos/handoffs/x.md", "private_detail": SECRET}), "handoff-private"),
    (lambda value: value.__setitem__("data", None), "null-success-data"),
    (
        lambda value: value.__setitem__(
            "bounded",
            [{"bounded": True, "original_bytes": 10, "returned_bytes": 5,
              "field": "x", "private_detail": SECRET}],
        ),
        "private-bounding-field",
    ),
    (lambda value: value.__setitem__("grounding", []), "bad-grounding"),
    (lambda value: value.__setitem__("degraded", [1]), "bad-degraded"),
    (lambda value: value.__setitem__("bounded", ["not-a-receipt"]), "bad-bounded"),
    (
        lambda value: value.__setitem__(
            "error", {"code": "not_found", "message": SECRET}
        ),
        "success-with-error",
    ),
])
def test_untrusted_success_envelope_is_not_a_success_or_permission_refusal(
    profile, mutate, case
):
    result = canonical_result(profile)
    mutate(result)
    observed = asyncio.run(socket_read(profile, {"ok": True, "result": result}))
    assert_diagnostic(observed, "backend_unavailable", "invalid response")


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(("mutate", "case"), [
    (
        lambda value: value.__setitem__(
            "data", {"runtime_counts": {"jobs": 99}, "private_detail": SECRET}
        ),
        "failure-with-data",
    ),
    (
        lambda value: value["error"].__setitem__("private_detail", SECRET),
        "failure-extra-error-field",
    ),
    (
        lambda value: value["error"].__setitem__("code", "future-error-code"),
        "unknown-error-code",
    ),
    (
        lambda value: value["error"].__setitem__("message", {"private": SECRET}),
        "non-string-error-message",
    ),
    (lambda value: value.__setitem__("error", None), "missing-error-shape"),
])
def test_malformed_inner_error_envelope_is_refused_without_leak(
    profile, mutate, case
):
    result = canonical_result(
        profile, ok=False, code="authority_refused", message=SECRET
    )
    mutate(result)
    observed = asyncio.run(socket_read(profile, {"ok": True, "result": result}))
    assert_diagnostic(observed, "backend_unavailable", "invalid response")


@pytest.mark.parametrize("profile", PROFILES)
def test_valid_canonical_read_success_is_preserved(profile):
    wire = canonical_result(profile)
    expected = copy.deepcopy(wire)
    expected["server_version"] = OUTPUT_SERVER_VERSION[profile]
    observed = asyncio.run(
        socket_read(profile, {"ok": True, "result": copy.deepcopy(wire)})
    )
    assert observed == expected


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(
    ("upstream_code", "code", "category"),
    [
        ("authority_refused", "backend_refused", "permission was refused"),
        ("not_found", "backend_refused", "request was refused"),
        ("invalid_input", "backend_refused", "request was refused"),
        ("backend_unavailable", "backend_unavailable", "unavailable in the installed backend"),
        ("grounding_unavailable", "backend_unavailable", "unavailable in the installed backend"),
        ("timeout", "backend_unavailable", "unavailable in the installed backend"),
        ("internal_error", "backend_unavailable", "unavailable in the installed backend"),
    ],
)
def test_canonical_inner_error_is_classified_and_redacted(
    profile, upstream_code, code, category
):
    wire = canonical_result(
        profile, ok=False, code=upstream_code, message=SECRET
    )
    observed = asyncio.run(
        socket_read(profile, {"ok": True, "result": copy.deepcopy(wire)})
    )
    assert_diagnostic(observed, code, category)


def test_intent_status_receipt_must_match_requested_intent():
    from control_plane import ceo_intent

    requested = "auto-" + "1" * 32
    other = "auto-" + "2" * 32
    gateway = WebCeoV2CeoIngressReadGateway("/unused", object())
    receipt = {
        "schema": ceo_intent.RECEIPT_SCHEMA_V2,
        "intent_id": other,
        "fingerprint": "a" * 64,
        "job_id": "JOB-003",
        "status": "QUEUED",
        "accepted": True,
        "duplicate": False,
        "dispatched": False,
        "authority": {
            "requested": ["READ", "RESEARCH"],
            "policy_sha256": "b" * 64,
            "authority_level": "A0",
        },
        "grounding": {
            "mastermind_sha": "c" * 40,
            "macro_sha": "d" * 40,
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
        },
        "created_at_ms": 1,
        "work_ref": "WS:EXECUTIVE-CAPACITY-FABRIC",
    }
    envelope = {
        "schema": RESULT_SCHEMA,
        "tool": "ceo_intent_status",
        "ok": True,
        "server_version": "1.2.0",
        "mode": "readonly",
        "generated_at": "2026-10-06T06:00:00Z",
        "grounding": {
            "runtime": "readonly:installed-executive-runtime",
            "source": "control_plane.ceo_intent.resolve_intent",
        },
        "data": receipt,
        "degraded": [],
        "bounded": [],
        "error": None,
    }
    assert gateway._is_canonical_read_result(
        envelope, tool="ceo_intent_status", arguments={"intent_id": requested}
    ) is False
    receipt["intent_id"] = requested
    assert gateway._is_canonical_read_result(
        envelope, tool="ceo_intent_status", arguments={"intent_id": requested}
    ) is True


def test_fabric_root_projection_must_match_requested_root():
    from control_plane import fabric_job_view

    requested = "JOB-003"
    gateway = WebCeoV2CeoIngressReadGateway("/unused", object())
    data = _canonical_fabric_root_detail(requested)
    child = copy.deepcopy(data["root"])
    child.update(
        job_id="JOB-006",
        parent_job_id=requested,
        depth=1,
        orchestration_role="plan",
    )
    data["children"] = [child]
    assert gateway._valid_fabric_data(
        data, arguments={"view": "root", "root_job_id": requested}
    ) is True

    data["root"]["job_id"] = "JOB-013"
    assert gateway._valid_fabric_data(
        data, arguments={"view": "root", "root_job_id": requested}
    ) is False
    data["root"]["job_id"] = requested
    data["children"][0]["root_job_id"] = "JOB-013"
    assert gateway._valid_fabric_data(
        data, arguments={"view": "root", "root_job_id": requested}
    ) is False
    data["children"][0]["root_job_id"] = requested
    data["runtime"]["acquisition"]["query"]["root_job_id"] = "JOB-013"
    assert gateway._valid_fabric_data(
        data, arguments={"view": "root", "root_job_id": requested}
    ) is False


def test_v2_and_v3_fabric_readers_reject_legacy_root_projection():
    from control_plane import fabric_job_view

    requested = "JOB-003"
    arguments = {"view": "root", "root_job_id": requested}
    legacy = {
        "schema": fabric_job_view.SCHEMA,
        "generated_at": "2026-10-06T06:00:00Z",
        "runtime": {"root": None, "db_present": True, "identity": None},
        "armed": {},
        "root": {"job_id": requested, "root_job_id": requested},
        "children": [],
        "unjoined_job_count": 0,
        "unjoined_job_ids": [],
        "degraded": [],
        "missingness": [],
        "capability": {},
    }
    assert WebCeoCeoIngressReadGateway._valid_fabric_data(
        legacy, arguments=arguments
    ) is True
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        legacy, arguments=arguments
    ) is False
    assert WebCeoV3CeoIngressReadGateway._valid_fabric_data(
        legacy, arguments=arguments
    ) is False

    current = _canonical_fabric_root_detail(requested)
    assert WebCeoCeoIngressReadGateway._valid_fabric_data(
        current, arguments=arguments
    ) is False
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        current, arguments=arguments
    ) is True


def _canonical_fabric_roots(limit=3):
    from control_plane import fabric_job_view

    roots = [
        {
            "job_id": f"JOB-{index}",
            "status": "QUEUED",
            "depth": 0,
            "parent_job_id": None,
            "orchestration_role": "aggregation" if index == 3 else None,
        }
        for index in range(1, 4)
    ][:limit]
    acquisition = fabric_job_view._acquisition_receipt(kind="root_discovery")
    acquisition["snapshot_digest"] = "a" * 64
    acquisition["provenance"] = {
        "state": "PARTIAL",
        "unjoined_job_ids": [row["job_id"] for row in roots],
    }
    acquisition["generation"] = {
        "schema": "mastermind.runtime_read_observation.v1",
        "state": "SAME",
        "source_identity": "runtime-source-1",
        "before": 2,
        "after": 2,
    }
    return {
        "schema": fabric_job_view.ROOT_LIST_SCHEMA_V2,
        "generated_at": "2026-10-06T08:00:00Z",
        "runtime": {
            "root": None,
            "db_present": True,
            "identity": None,
            "acquisition": acquisition,
        },
        "roots": roots,
        "count": len(roots),
        "total": len(roots),
        "truncated": False,
        "degraded": [],
    }


def test_v2_fabric_root_list_requires_owner_acquisition_and_row_contract():
    arguments = {"view": "roots", "limit": 3}
    canonical = _canonical_fabric_roots()
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        canonical, arguments=arguments
    ) is True
    assert WebCeoV3CeoIngressReadGateway._valid_fabric_data(
        canonical, arguments=arguments
    ) is True

    mutations = []

    missing = copy.deepcopy(canonical)
    missing["runtime"].pop("acquisition")
    mutations.append(missing)

    wrong_query = copy.deepcopy(canonical)
    wrong_query["runtime"]["acquisition"]["query"] = {
        "kind": "root_detail",
        "root_job_id": "JOB-001",
    }
    mutations.append(wrong_query)

    private_row = copy.deepcopy(canonical)
    private_row["roots"][0]["execution_ready"] = True
    mutations.append(private_row)

    over_limit = copy.deepcopy(canonical)
    over_limit["roots"].append({
        "job_id": "JOB-004",
        "status": "QUEUED",
        "depth": 0,
        "parent_job_id": None,
        "orchestration_role": None,
    })
    over_limit["count"] = len(over_limit["roots"])
    over_limit["total"] = len(over_limit["roots"])
    over_limit["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"].append("JOB-004")
    mutations.append(over_limit)

    false_truncation = copy.deepcopy(canonical)
    false_truncation["truncated"] = True
    mutations.append(false_truncation)

    private_identity = copy.deepcopy(canonical)
    private_identity["runtime"]["identity"] = {
        "execution_ready": True,
        "private_detail": SECRET,
    }
    mutations.append(private_identity)

    for value in mutations:
        assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
            value, arguments=arguments
        ) is False
        assert WebCeoV3CeoIngressReadGateway._valid_fabric_data(
            value, arguments=arguments
        ) is False


def test_legacy_fabric_root_list_remains_v1_only():
    from control_plane import fabric_job_view

    legacy = {
        "schema": fabric_job_view.ROOT_LIST_SCHEMA,
        "generated_at": "2026-10-06T08:00:00Z",
        "runtime": {"root": None, "db_present": True, "identity": None},
        "roots": [{
            "job_id": "JOB-003",
            "status": "QUEUED",
            "depth": 0,
            "parent_job_id": None,
            "orchestration_role": "aggregation",
        }],
        "count": 1,
        "total": 1,
        "truncated": False,
        "degraded": [],
    }
    arguments = {"view": "roots", "limit": 3}
    assert WebCeoCeoIngressReadGateway._valid_fabric_data(
        legacy, arguments=arguments
    ) is True
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        legacy, arguments=arguments
    ) is False
    assert WebCeoV3CeoIngressReadGateway._valid_fabric_data(
        legacy, arguments=arguments
    ) is False


def _canonical_inbox_data():
    counts = copy.deepcopy(canonical_result()["data"]["runtime_counts"])
    return {
        "schema": "mastermind.executive_inbox.v2",
        "generated_at": "2026-10-06T08:00:00Z",
        "grounding": {
            "mastermind": {
                "branch": "HEAD",
                "root": "/mastermind",
                "sha": "a" * 40,
            },
            "macro": {"root": "/macro", "sha": "b" * 40},
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
            "runtime_db": {
                "path": "/runtime/executive.sqlite3",
                "present": True,
            },
        },
        "attention": [{
            "attention_id": "eia-" + "1" * 12,
            "target": "coo",
            "kind": "job_failed",
            "source": "runtime",
            "job_id": "JOB-006",
            "workstream": None,
            "status": "FAILED",
            "reason": "JOB-006 is FAILED after 1 of 1 attempt(s)",
            "evidence": [
                {"ref": "job:JOB-006", "field": "status", "value": "FAILED"}
            ],
            "existing_next_actions": [],
            "parent_job_id": "JOB-003",
            "root_job_id": "JOB-003",
            "depth": 1,
            "owner_seat": "coo",
            "escalation_target": "coo",
            "business_impact": "routine",
            "review_required": False,
            "reviews_job_id": None,
        }],
        "runtime_counts": counts,
        "suppressed": {
            "clean_completed": 0,
            "queued": 3,
            "running": 0,
            "checkpointed": 0,
            "cancelled": 0,
        },
        "degraded": [],
    }


def test_inbox_nested_public_contract_rejects_private_and_readiness_fields():
    canonical = _canonical_inbox_data()
    assert WebCeoV2CeoIngressReadGateway._valid_inbox_data(canonical, bounded=[]) is True

    mutations = []

    attention = copy.deepcopy(canonical)
    attention["attention"][0]["execution_ready"] = True
    mutations.append(attention)

    grounding = copy.deepcopy(canonical)
    grounding["grounding"]["mastermind"]["private_detail"] = SECRET
    mutations.append(grounding)

    counts = copy.deepcopy(canonical)
    counts["runtime_counts"]["private_detail"] = SECRET
    mutations.append(counts)

    suppressed = copy.deepcopy(canonical)
    suppressed["suppressed"]["private_detail"] = SECRET
    mutations.append(suppressed)

    evidence = copy.deepcopy(canonical)
    evidence["attention"][0]["evidence"][0]["private_detail"] = SECRET
    mutations.append(evidence)

    for value in mutations:
        assert WebCeoV2CeoIngressReadGateway._valid_inbox_data(value, bounded=[]) is False


def test_inbox_accepts_canonical_bounded_attention_receipts():
    result = canonical_result(WebCeoV2CeoIngressReadGateway)
    result["tool"] = "executive_inbox"
    data = _canonical_inbox_data()
    data["attention"][0]["reason"] = "R" * 20_000
    data["attention"][0]["evidence"][0]["value"] = "E" * 12_000
    data["attention"][0]["existing_next_actions"] = ["N" * 8_000]
    bounded_data, receipts = bound_document(data, limit=4_096)
    assert receipts
    result["data"] = bounded_data
    result["bounded"] = receipts

    gateway = WebCeoV2CeoIngressReadGateway("/tmp/not-used.sock", CeoIngressClient())
    assert gateway._is_canonical_read_result(
        result, tool="executive_inbox", arguments={}
    ) is True

    forged = copy.deepcopy(result)
    replacement = forged["data"]["attention"][0]["reason"]
    assert type(replacement) is dict and replacement["bounded"] is True
    replacement["returned_bytes"] += 1
    assert gateway._is_canonical_read_result(
        forged, tool="executive_inbox", arguments={}
    ) is False


@pytest.mark.parametrize("target", ["grounding-branch", "evidence-ref"])
def test_inbox_bounding_rejects_identity_and_reference_replacements(target):
    result = canonical_result(WebCeoV2CeoIngressReadGateway)
    result["tool"] = "executive_inbox"
    data = _canonical_inbox_data()
    field = (
        "grounding.mastermind.branch"
        if target == "grounding-branch"
        else "attention[0].evidence[0].ref"
    )
    replacement = {
        "bounded": True,
        "original_bytes": 700,
        "returned_bytes": 7,
        "field": field,
        "preview": "forged!",
    }
    if target == "grounding-branch":
        data["grounding"]["mastermind"]["branch"] = replacement
    else:
        data["attention"][0]["evidence"][0]["ref"] = replacement
    result["data"] = data
    result["bounded"] = [{
        "bounded": True,
        "original_bytes": 700,
        "returned_bytes": 7,
        "field": field,
    }]

    gateway = WebCeoV2CeoIngressReadGateway("/tmp/not-used.sock", CeoIngressClient())
    assert gateway._is_canonical_read_result(
        result, tool="executive_inbox", arguments={}
    ) is False


def test_inbox_bounded_preview_cannot_exceed_owner_limit():
    from integrations.executive_mcp.schemas import BOUND_PREVIEW_CHARS

    result = canonical_result(WebCeoV2CeoIngressReadGateway)
    result["tool"] = "executive_inbox"
    data = _canonical_inbox_data()
    field = "attention[0].reason"
    preview = "R" * (BOUND_PREVIEW_CHARS + 1)
    replacement = {
        "bounded": True,
        "original_bytes": len(preview) + 100,
        "returned_bytes": len(preview.encode("utf-8")),
        "field": field,
        "preview": preview,
    }
    data["attention"][0]["reason"] = replacement
    result["data"] = data
    result["bounded"] = [{
        "bounded": True,
        "original_bytes": replacement["original_bytes"],
        "returned_bytes": replacement["returned_bytes"],
        "field": field,
    }]

    gateway = WebCeoV2CeoIngressReadGateway("/tmp/not-used.sock", CeoIngressClient())
    assert gateway._is_canonical_read_result(
        result, tool="executive_inbox", arguments={}
    ) is False


def test_inbox_accepts_canonical_agent_os_attention_shape():
    value = _canonical_inbox_data()
    value["attention"] = [{
        "attention_id": "eia-" + "2" * 12,
        "target": "ceo",
        "kind": "ceo_decision_pending",
        "source": "agent_os",
        "job_id": None,
        "workstream": "WS:EXECUTIVE-CAPACITY-FABRIC",
        "status": None,
        "reason": "Choose the next accepted action.",
        "evidence": [
            {
                "ref": "agentos:needs_ceo",
                "field": "workstream",
                "value": "WS:EXECUTIVE-CAPACITY-FABRIC",
            },
            {
                "ref": "boot_packet",
                "field": "schema",
                "value": "mastermind.ceo_boot_packet.v1",
            },
        ],
        "existing_next_actions": [],
    }]
    assert WebCeoV2CeoIngressReadGateway._valid_inbox_data(value, bounded=[]) is True


def _canonical_executive_job_data(job_id="JOB-003", *, with_attempt=False):
    import dataclasses
    from control_plane.executive_runtime import Attempt, Job

    job = {field.name: None for field in dataclasses.fields(Job)}
    job.update(
        job_id=job_id,
        status="QUEUED",
        attempt_count=1 if with_attempt else 0,
        attempt_limit=1,
    )
    attempts = []
    if with_attempt:
        attempt = {field.name: None for field in dataclasses.fields(Attempt)}
        attempt.update(
            attempt_id="ATT-" + "1" * 32,
            job_id=job_id,
            attempt_number=1,
            status="CLAIMED",
        )
        attempts.append(attempt)
    return {
        "job": job,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "attempt_limit": 1,
        "latest_attempt": copy.deepcopy(attempts[-1]) if attempts else None,
    }


def test_executive_job_closes_job_and_attempt_rows_and_relationships():
    requested = "JOB-003"
    arguments = {"job_id": requested}
    canonical = _canonical_executive_job_data(requested, with_attempt=True)
    assert WebCeoV2CeoIngressReadGateway._valid_job_data(
        canonical, arguments=arguments
    ) is True

    job_private = copy.deepcopy(canonical)
    job_private["job"]["execution_ready"] = True
    assert WebCeoV2CeoIngressReadGateway._valid_job_data(
        job_private, arguments=arguments
    ) is False

    attempt_private = copy.deepcopy(canonical)
    attempt_private["attempts"][0]["private_detail"] = SECRET
    assert WebCeoV2CeoIngressReadGateway._valid_job_data(
        attempt_private, arguments=arguments
    ) is False

    wrong_count = copy.deepcopy(canonical)
    wrong_count["attempt_count"] = 0
    assert WebCeoV2CeoIngressReadGateway._valid_job_data(
        wrong_count, arguments=arguments
    ) is False

    wrong_latest = copy.deepcopy(canonical)
    wrong_latest["latest_attempt"]["attempt_id"] = "ATT-" + "2" * 32
    assert WebCeoV2CeoIngressReadGateway._valid_job_data(
        wrong_latest, arguments=arguments
    ) is False


def _canonical_fabric_root_detail(root_job_id="JOB-003"):
    from types import SimpleNamespace
    from control_plane import fabric_job_view

    root_job = SimpleNamespace(
        job_id=root_job_id,
        status="QUEUED",
        parent_job_id=None,
        root_job_id=root_job_id,
        depth=0,
        orchestration_role="aggregation",
        plan_step_id=None,
        attempt_count=0,
        attempt_limit=1,
        current_attempt_id=None,
        repair_round=None,
        supersedes_job_id=None,
        review_required=False,
        reviews_job_id=None,
        result=None,
        checkpoint=None,
    )
    root, _ = fabric_job_view._job_card(
        root_job, (), {}, contract_version=2
    )
    snapshot = SimpleNamespace(
        snapshot_digest="a" * 64,
        jobs_truncated=False,
        attempts_truncated_job_ids=(),
        truncated=False,
    )
    acquisition = fabric_job_view._acquisition_receipt(
        kind="root_detail",
        root_job_id=root_job_id,
        snapshot=snapshot,
        unjoined=(),
    )
    acquisition["generation"] = {
        "schema": "mastermind.runtime_read_observation.v1",
        "state": "SAME",
        "source_identity": "runtime-source-1",
        "before": 2,
        "after": 2,
    }
    return {
        "schema": fabric_job_view.SCHEMA_V2,
        "generated_at": "2026-10-06T09:00:00Z",
        "runtime": {
            "root": None,
            "db_present": True,
            "identity": None,
            "acquisition": acquisition,
        },
        "armed": {},
        "root": root,
        "children": [],
        "unjoined_job_count": 0,
        "unjoined_job_ids": [],
        "degraded": [],
        "missingness": [],
        "capability": {},
    }


def test_v2_fabric_root_detail_closes_runtime_acquisition_and_job_cards():
    requested = "JOB-003"
    arguments = {"view": "root", "root_job_id": requested}
    canonical = _canonical_fabric_root_detail(requested)
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        canonical, arguments=arguments
    ) is True
    assert WebCeoV3CeoIngressReadGateway._valid_fabric_data(
        canonical, arguments=arguments
    ) is True

    runtime_private = copy.deepcopy(canonical)
    runtime_private["runtime"]["execution_ready"] = True
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        runtime_private, arguments=arguments
    ) is False

    acquisition_private = copy.deepcopy(canonical)
    acquisition_private["runtime"]["acquisition"]["private_detail"] = SECRET
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        acquisition_private, arguments=arguments
    ) is False

    root_private = copy.deepcopy(canonical)
    root_private["root"]["execution_ready"] = True
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        root_private, arguments=arguments
    ) is False

    attempt_private = copy.deepcopy(canonical)
    attempt_private["root"]["attempts"] = [{
        "attempt_id": "ATT-" + "1" * 32,
        "attempt_number": 1,
        "status": "CLAIMED",
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "has_result": False,
        "error": None,
        "private_detail": SECRET,
    }]
    attempt_private["root"]["latest_attempt"] = copy.deepcopy(
        attempt_private["root"]["attempts"][0]
    )
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        attempt_private, arguments=arguments
    ) is False


def _canonical_fabric_result(root_job_id="JOB-003"):
    from control_plane import (
        executive_orchestration_result as result_owner,
        fabric_result_projection,
    )

    job_id = "JOB-004"
    attempt_id = "ATT-" + "1" * 32
    envelope_digest = "b" * 64
    role_result = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root_job_id,
        "plan_attempt_id": "ATT-" + "2" * 32,
        "plan_digest": "c" * 64,
        "plan_step_id": "step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    result = {
        "schema": fabric_result_projection.FABRIC_ROLE_RESULT_VIEW_SCHEMA,
        "selection": {
            "root_job_id": root_job_id,
            "job_id": job_id,
            "attempt_id": attempt_id,
            "result_envelope_digest": envelope_digest,
        },
        "role": "work",
        "execution_status": "COMPLETED",
        "acceptance": "NOT_PROJECTED",
        "role_result_digest": result_owner.canonical_digest(role_result),
        "generation": {
            "schema": "mastermind.runtime_read_observation.v1",
            "state": "SAME",
            "source_identity": "d" * 32,
            "before": 2,
            "after": 2,
        },
        "availability": "AVAILABLE",
        "content_complete": True,
        "review": None,
        "counts": {"findings": None, "next_actions": 0},
        "content": {
            "role_result": role_result,
            "summary": "completed",
            "next_actions": [],
        },
        "omitted": [],
    }
    arguments = {
        "view": "result",
        "root_job_id": root_job_id,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "result_envelope_digest": envelope_digest,
    }
    return result, arguments


def test_v2_fabric_result_closes_projection_and_content_contracts():
    canonical, arguments = _canonical_fabric_result()
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        canonical, arguments=arguments
    ) is True
    assert WebCeoV3CeoIngressReadGateway._valid_fabric_data(
        canonical, arguments=arguments
    ) is True

    private_projection = copy.deepcopy(canonical)
    private_projection["private_detail"] = SECRET
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        private_projection, arguments=arguments
    ) is False

    private_role_result = copy.deepcopy(canonical)
    private_role_result["content"]["role_result"]["private_detail"] = SECRET
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        private_role_result, arguments=arguments
    ) is False

    private_generation = copy.deepcopy(canonical)
    private_generation["generation"]["private_detail"] = SECRET
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        private_generation, arguments=arguments
    ) is False

    wrong_digest = copy.deepcopy(canonical)
    wrong_digest["role_result_digest"] = "e" * 64
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        wrong_digest, arguments=arguments
    ) is False

    over_budget = copy.deepcopy(canonical)
    over_budget.update(
        availability="CONTENT_OVER_BUDGET",
        content_complete=False,
        content=None,
        omitted=["role_result", "summary", "next_actions"],
    )
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        over_budget, arguments=arguments
    ) is True

    forged_omission = copy.deepcopy(over_budget)
    forged_omission["omitted"].append("private_detail")
    assert WebCeoV2CeoIngressReadGateway._valid_fabric_data(
        forged_omission, arguments=arguments
    ) is False


def _canonical_receipt(schema, intent_id):
    return {
        "schema": schema,
        "intent_id": intent_id,
        "fingerprint": "a" * 64,
        "job_id": "JOB-003",
        "status": "QUEUED",
        "accepted": True,
        "duplicate": False,
        "dispatched": False,
        "authority": {
            "requested": ["READ", "RESEARCH"],
            "policy_sha256": "b" * 64,
            "authority_level": "A0",
        },
        "grounding": {
            "mastermind_sha": "c" * 40,
            "macro_sha": "d" * 40,
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
        },
        "created_at_ms": 1,
    }


def test_intent_status_refuses_noncanonical_job_status():
    from control_plane import ceo_intent

    intent_id = "auto-" + "9" * 32
    receipt = _canonical_receipt(ceo_intent.RECEIPT_SCHEMA_V2, intent_id)
    receipt["status"] = "EXECUTION_READY"
    assert WebCeoV2CeoIngressReadGateway._valid_intent_receipt(
        receipt, arguments={"intent_id": intent_id}
    ) is False


def test_intent_status_accepts_service_and_principal_receipt_families():
    from control_plane import ceo_intent
    from control_plane.coo_principal_request import principal_intent_id

    service_id = "svc-status-proof"
    service = _canonical_receipt(ceo_intent.RECEIPT_SCHEMA_SERVICE, service_id)
    assert WebCeoV2CeoIngressReadGateway._valid_intent_receipt(
        service, arguments={"intent_id": service_id}
    ) is True

    request_ref = "req-coo-" + "1" * 32
    principal_id = principal_intent_id(request_ref)
    principal = _canonical_receipt(
        ceo_intent.RECEIPT_SCHEMA_PRINCIPAL, principal_id
    )
    principal["principal"] = {
        "seat": "coo",
        "work_ref": "WS:EXECUTIVE-CAPACITY-FABRIC",
        "principal_binding_digest": "e" * 64,
        "mission_authority_ref": "MAS-1143",
        "authority_generation_digest": "f" * 64,
    }
    principal["request_ref"] = request_ref
    assert WebCeoV2CeoIngressReadGateway._valid_intent_receipt(
        principal, arguments={"intent_id": principal_id}
    ) is True

    principal["request_ref"] = "req-coo-" + "2" * 32
    assert WebCeoV2CeoIngressReadGateway._valid_intent_receipt(
        principal, arguments={"intent_id": principal_id}
    ) is False


class ClassifiedClient:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def send_frame(self, path, frame):
        self.calls += 1
        return self.response


@pytest.mark.parametrize("response", [
    CeoIngressResponse(transport="future-" + SECRET, detail=SECRET),
    CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error={"code": [SECRET]}),
    CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error=None),
    CeoIngressResponse(transport=TRANSPORT_NOT_SENT, ok=True, result=canonical_result(), detail=SECRET),
    CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN, ok=False,
                       error={"code": "peer_denied"}, detail=SECRET),
])
def test_incoherent_classified_response_cannot_fabricate_permission_or_send_facts(response):
    client = ClassifiedClient(response)
    result = asyncio.run(CeoIngressReadGateway("/unused", client).call("executive_state", {}))
    assert client.calls == 1
    assert_diagnostic(result, "backend_unavailable", "invalid response")


def test_local_write_refusal_sends_no_read_frame():
    client = ClassifiedClient(CeoIngressResponse(transport=TRANSPORT_NOT_SENT))
    result = asyncio.run(CeoIngressReadGateway("/unused", client).call("submit_ceo_intent", {}))
    assert result["error"]["code"] == "authority_refused"
    assert client.calls == 0


@pytest.mark.parametrize("failure_point", ["write", "drain"])
def test_failed_socket_write_does_not_claim_request_delivery(failure_point, monkeypatch):
    connections = []

    class FailingWriter:
        def write(self, _data):
            if failure_point == "write":
                raise OSError("write failed " + SECRET)

        async def drain(self):
            raise OSError("drain failed " + SECRET)

        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def connect(path, **_kwargs):
        connections.append(path)
        return object(), FailingWriter()

    monkeypatch.setattr(asyncio, "open_unix_connection", connect)
    gateway = CeoIngressReadGateway("/unused", CeoIngressClient())
    result = asyncio.run(gateway.call("executive_state", {}))
    assert connections == ["/unused"]
    assert_diagnostic(result, "backend_unavailable", "after the read request was attempted")
    assert "read request was sent" not in result["error"]["message"]
