"""BSC-E1 admission composition + the authorized ``ceo_request`` helper.

Two independent things are proven here, in one file per the commission's
ceiling (no new test path was authorized):

1. :func:`control_plane.ceo_request.app_request_ref` — the ONE additive pure
   function the P5-authorized 11th path added.  Determinism, format
   compliance, domain separation from ``mcp_intent_id``/``slack_intent_id``,
   distinctness across operation keys, a mutation proving the domain
   separator is load-bearing, and a REGRESSION PIN proving every existing
   identity vector (``mcp_intent_id``, ``slack_intent_id``,
   ``automated_intent_id``) is unchanged.
2. :mod:`integrations.mastermind_executive_app.admission` — the ADMISSION
   composition, using a fake :class:`CeoIngressClient` so this file exercises
   ONLY the app's own logic (payload validation, privileged-field rejection,
   request_ref derivation, grounding, frame shape, response classification,
   duplicate/conflict, and the effect_unknown/reconciliation contract). The
   real, no-execution, temporary CeoIngress/Runtime canary (real RS256 +
   negative token matrix over a REAL socket) lives in
   ``tests/test_mastermind_executive_app_asgi.py`` so this file stays fast
   and hermetic.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from control_plane import ceo_request
from control_plane import executive_ceo_ingress as ceo_ingress
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_executive_app import admission
from integrations.mastermind_executive_app import gateway
from integrations.mastermind_executive_app.gateway import (
    READ_SCOPE,
    SUBMIT_SCOPE,
    CeoIngressResponse,
    TRANSPORT_NOT_SENT,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
)


def _run(coroutine):
    return asyncio.run(coroutine)


# ===========================================================================
# 1. control_plane.ceo_request.app_request_ref (BSC-E1 authorized 11th path)
# ===========================================================================

#: Frozen literal cross-transport regression vectors, computed BEFORE the
#: BSC-E1 change and pinned here byte-for-byte -- a mutation to
#: mcp_intent_id/slack_intent_id/automated_intent_id must fail these, not
#: app_request_ref's own tests.
LITERAL_OPERATION_KEY = "options-chain-browser-closure-001"
LITERAL_MCP_INTENT_ID = "mcp-400560e76b2e72590f12d30f782bfc4d"
LITERAL_SLACK_INTENT_ID = "slack-4e40f3d7656227ee9dcead6b00c9d5f2"
LITERAL_APP_REQUEST_REF = "req-5190b5c603d29cb547605fc7443220f1"
LITERAL_AUTOMATED_INTENT_ID_FROM_APP_REF = "auto-0e1a2916a9034ce7d67d36055e92513e"


def test_app_request_ref_is_deterministic():
    first = ceo_request.app_request_ref(LITERAL_OPERATION_KEY)
    second = ceo_request.app_request_ref(LITERAL_OPERATION_KEY)
    assert first == second == LITERAL_APP_REQUEST_REF


def test_app_request_ref_matches_automated_request_ref_shape():
    value = ceo_request.app_request_ref(LITERAL_OPERATION_KEY)
    assert ceo_request.AUTOMATED_REQUEST_REF_RE.fullmatch(value) is not None
    assert value.startswith("req-")


def test_app_request_ref_is_accepted_by_automated_intent_id_unchanged():
    ref = ceo_request.app_request_ref(LITERAL_OPERATION_KEY)
    intent_id = ceo_request.automated_intent_id(ref)
    assert intent_id == LITERAL_AUTOMATED_INTENT_ID_FROM_APP_REF
    assert ceo_request.ceo_intent.INTENT_ID_RE.fullmatch(intent_id) is not None


def test_app_request_ref_is_domain_separated_from_mcp_and_slack():
    app_ref = ceo_request.app_request_ref(LITERAL_OPERATION_KEY)
    mcp_id = ceo_request.mcp_intent_id(LITERAL_OPERATION_KEY)
    slack_id = ceo_request.slack_intent_id(LITERAL_OPERATION_KEY)
    assert app_ref != mcp_id
    assert app_ref != slack_id
    # Never merely a re-prefix of the same digest bytes.
    assert app_ref.removeprefix("req-") != mcp_id.removeprefix("mcp-")
    assert app_ref.removeprefix("req-") != slack_id.removeprefix("slack-")


def test_app_request_ref_distinct_operation_keys_yield_distinct_refs():
    other_key = "options-chain-browser-closure-002"
    assert ceo_request.app_request_ref(LITERAL_OPERATION_KEY) != ceo_request.app_request_ref(
        other_key
    )


def test_app_request_ref_domain_separator_is_load_bearing(monkeypatch):
    """Mutating the domain separator changes the output (proves it is used)."""

    import hashlib

    real_sha256 = hashlib.sha256
    captured: list[bytes] = []

    def spying_sha256(data: bytes = b""):
        captured.append(bytes(data))
        return real_sha256(data)

    monkeypatch.setattr(ceo_request.hashlib, "sha256", spying_sha256)
    ceo_request.app_request_ref(LITERAL_OPERATION_KEY)
    assert captured, "app_request_ref must hash something"
    assert captured[-1].startswith(ceo_request._APP_REQUEST_REF_DOMAIN)
    assert not captured[-1].startswith(ceo_request._MCP_INTENT_ID_DOMAIN)
    assert not captured[-1].startswith(ceo_request._SLACK_INTENT_ID_DOMAIN)

    # And an actual mutation of the separator changes the emitted ref.
    original_domain = ceo_request._APP_REQUEST_REF_DOMAIN
    try:
        ceo_request._APP_REQUEST_REF_DOMAIN = b"mutated-domain\x00"
        mutated = ceo_request.app_request_ref(LITERAL_OPERATION_KEY)
    finally:
        ceo_request._APP_REQUEST_REF_DOMAIN = original_domain
    assert mutated != LITERAL_APP_REQUEST_REF


def test_app_request_ref_refuses_invalid_operation_key():
    with pytest.raises(ceo_request.CeoRequestInvalid):
        ceo_request.app_request_ref("Not Legal!")


def test_regression_pin_mcp_slack_automated_unchanged_by_app_request_ref():
    """The additive change touched nothing else. Byte-for-byte regression."""

    assert ceo_request.mcp_intent_id(LITERAL_OPERATION_KEY) == LITERAL_MCP_INTENT_ID
    assert ceo_request.slack_intent_id(LITERAL_OPERATION_KEY) == LITERAL_SLACK_INTENT_ID
    automated_ref = "req-chairman-ceo-20260829-001"
    assert (
        ceo_request.automated_intent_id(automated_ref)
        == "auto-7f73c16f713e8251775a37fee5ce66d2"
    )


def test_app_request_ref_in_module_all():
    assert "app_request_ref" in ceo_request.__all__


# ===========================================================================
# 2. admission composition (fake CeoIngressClient; no real socket)
# ===========================================================================

MASTERMIND_SHA = "1111111111111111111111111111111111111111"
MACRO_SHA = "2222222222222222222222222222222222222222"


class _FakeClient:
    """Records every frame sent; returns a scripted, ordered response list."""

    def __init__(self, responses: list[CeoIngressResponse]) -> None:
        self._responses = list(responses)
        self.sent_frames: list[dict[str, Any]] = []
        self.sent_paths: list[Any] = []

    async def send_frame(self, socket_path, frame):
        self.sent_frames.append(dict(frame))
        self.sent_paths.append(socket_path)
        if not self._responses:
            raise AssertionError("no more scripted responses")
        return self._responses.pop(0)


def _principal(*, scopes: tuple[str, ...]) -> VerifiedPrincipal:
    return VerifiedPrincipal(
        policy_id="mastermind-executive-app-submit-example",
        issuer="https://issuer.mastermind.example.com",
        issuer_digest="a" * 64,
        resource="https://executive-app.mastermind.example.com/mcp",
        subject_digest="b" * 64,
        client_ref="c" * 64,
        scopes=scopes,
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest=None,
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "operation_key": LITERAL_OPERATION_KEY,
        "objective": "Read the Q3 board packet and summarize open risks.",
        "department": "executive-infrastructure",
        "priority": 5,
        "execution_profile": "research_only",
    }
    payload.update(overrides)
    return payload


def _accepted_response(*, dispatched: Any = False, **extra: Any) -> CeoIngressResponse:
    result = {
        "intent_id": "auto-0e1a2916a9034ce7d67d36055e92513e",
        "fingerprint": "f" * 64,
        "job_id": "JOB-000001",
        "status": "QUEUED",
        "accepted": True,
        "duplicate": False,
        "dispatched": dispatched,
        "created_at_ms": 1_788_000_000_000,
    }
    result.update(extra)
    return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=result)


def _make_request(
    payload: dict[str, Any],
    *,
    client: _FakeClient,
    scopes: tuple[str, ...] = (READ_SCOPE, SUBMIT_SCOPE),
    macro_root_flag: str | None = None,
    environ: dict[str, str] | None = None,
    mastermind_root: Any = None,
) -> admission.AdmissionRequest:
    return admission.AdmissionRequest(
        payload=payload,
        principal=_principal(scopes=scopes),
        ceo_ingress_socket_path="/tmp/does-not-matter.sock",
        mastermind_root=mastermind_root if mastermind_root is not None else Path("."),
        macro_root_flag=macro_root_flag,
        environ=environ or {},
        client=client,
    )


@pytest.fixture(autouse=True)
def _stub_grounding(monkeypatch):
    """Every composition test below fixes grounding so it never depends on
    this worktree's real git state; the real-git-read path is proven
    separately by ``test_observe_trusted_grounding_reads_real_head_sha``."""

    def fake_observe(*, mastermind_root, macro_root_flag, environ):
        return {
            "mastermind_sha": MASTERMIND_SHA,
            "macro_sha": MACRO_SHA,
            "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
        }

    monkeypatch.setattr(admission, "observe_trusted_grounding", fake_observe)
    yield


def test_compose_admission_sends_exact_v2_frame_to_dedicated_socket():
    client = _FakeClient([_accepted_response()])
    request = _make_request(_payload(), client=client)
    outcome = _run(admission.compose_admission(request))

    assert outcome.status == admission.STATUS_ACCEPTED
    assert outcome.receipt["dispatched"] is False
    assert len(client.sent_frames) == 1
    assert client.sent_paths[0] == "/tmp/does-not-matter.sock"
    frame = client.sent_frames[0]
    assert frame["schema"] == ceo_ingress.SUBMIT_SCHEMA_V2
    assert frame["request_ref"] == LITERAL_APP_REQUEST_REF
    assert frame["observed_grounding"] == {
        "mastermind_sha": MASTERMIND_SHA,
        "macro_sha": MACRO_SHA,
        "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
    }
    # operation_key must NOT appear inside the semantic request (AD-ID1 v2).
    assert "operation_key" not in frame["request"]
    assert set(frame["request"]) <= ceo_request.AUTOMATED_REQUIRED_FIELDS | ceo_request.AUTOMATED_OPTIONAL_FIELDS
    assert ceo_request.AUTOMATED_REQUIRED_FIELDS <= set(frame["request"])


def test_compose_admission_derives_request_ref_from_operation_key_only():
    client = _FakeClient([_accepted_response()])
    request = _make_request(_payload(operation_key=LITERAL_OPERATION_KEY), client=client)
    outcome = _run(admission.compose_admission(request))
    assert outcome.request_ref == ceo_request.app_request_ref(LITERAL_OPERATION_KEY)


@pytest.mark.parametrize(
    "field",
    [
        "actor",
        "authority_level",
        "requested_authorities",
        "branch",
        "worktree",
        "grounding",
        "request_ref",
        "intent_id",
        "job_id",
        "status",
        "dispatched",
        "schema",
    ],
)
def test_privileged_fields_are_structurally_impossible(field):
    client = _FakeClient([])
    request = _make_request(_payload(**{field: "attacker-value"}), client=client)
    with pytest.raises(admission.AdmissionError) as excinfo:
        _run(admission.compose_admission(request))
    assert excinfo.value.code == "invalid_input"
    assert client.sent_frames == []  # refused before any socket effect


def test_read_scope_only_principal_is_refused_for_submit():
    client = _FakeClient([])
    request = _make_request(_payload(), client=client, scopes=(READ_SCOPE,))
    with pytest.raises(admission.AdmissionError) as excinfo:
        _run(admission.compose_admission(request))
    assert excinfo.value.code == "authority_refused"
    assert client.sent_frames == []


def test_submit_scope_only_principal_is_refused_for_submit():
    client = _FakeClient([])
    request = _make_request(_payload(), client=client, scopes=(SUBMIT_SCOPE,))
    with pytest.raises(admission.AdmissionError) as excinfo:
        _run(admission.compose_admission(request))
    assert excinfo.value.code == "authority_refused"
    assert client.sent_frames == []


def test_dispatched_true_is_backend_refusal_never_success():
    client = _FakeClient([_accepted_response(dispatched=True)])
    request = _make_request(_payload(), client=client)
    with pytest.raises(admission.AdmissionError) as excinfo:
        _run(admission.compose_admission(request))
    assert excinfo.value.code == "backend_refused"


def test_dispatched_missing_is_backend_refusal_never_success():
    response = _accepted_response()
    del response.result["dispatched"]
    client = _FakeClient([response])
    request = _make_request(_payload(), client=client)
    with pytest.raises(admission.AdmissionError) as excinfo:
        _run(admission.compose_admission(request))
    assert excinfo.value.code == "backend_refused"


def test_dispatched_non_boolean_is_backend_refusal_never_success():
    client = _FakeClient([_accepted_response(dispatched=1)])
    request = _make_request(_payload(), client=client)
    with pytest.raises(admission.AdmissionError):
        _run(admission.compose_admission(request))


def test_duplicate_receipt_is_accepted_with_same_identity():
    client = _FakeClient([_accepted_response(duplicate=True)])
    request = _make_request(_payload(), client=client)
    outcome = _run(admission.compose_admission(request))
    assert outcome.status == admission.STATUS_ACCEPTED
    assert outcome.receipt["duplicate"] is True


def test_operation_conflict_is_reported_with_zero_second_job():
    client = _FakeClient(
        [
            CeoIngressResponse(
                transport=TRANSPORT_SENT_OK,
                ok=False,
                error={"code": "operation_conflict", "message": "changed payload"},
            )
        ]
    )
    request = _make_request(_payload(), client=client)
    outcome = _run(admission.compose_admission(request))
    assert outcome.status == admission.STATUS_CONFLICT
    assert outcome.receipt is None
    assert outcome.code == "operation_conflict"


def test_grounding_unavailable_refuses_before_any_socket_effect(monkeypatch):
    def raising_observe(**_kwargs):
        raise admission.GroundingUnavailable("no sha")

    monkeypatch.setattr(admission, "observe_trusted_grounding", raising_observe)
    client = _FakeClient([])
    request = _make_request(_payload(), client=client)
    with pytest.raises(admission.AdmissionError) as excinfo:
        _run(admission.compose_admission(request))
    assert excinfo.value.code == "grounding_unavailable"
    assert client.sent_frames == []


# --- transport-outcome classification (never resubmit; reconcile instead) --


def test_ingress_unavailable_before_send_is_zero_effect():
    client = _FakeClient([CeoIngressResponse(transport=TRANSPORT_NOT_SENT, detail="connect failed")])
    request = _make_request(_payload(), client=client)
    outcome = _run(admission.compose_admission(request))
    assert outcome.status == admission.STATUS_TRANSPORT_UNAVAILABLE


def test_effect_unknown_after_send_never_raises_never_resends():
    client = _FakeClient(
        [CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN, detail="read timed out after send")]
    )
    request = _make_request(_payload(), client=client)
    outcome = _run(admission.compose_admission(request))
    assert outcome.status == admission.STATUS_EFFECT_UNKNOWN
    assert outcome.request_ref == LITERAL_APP_REQUEST_REF
    # Exactly one frame was ever sent for this call.
    assert len(client.sent_frames) == 1


def test_reconcile_by_request_ref_sends_v2_status_frame_never_a_submit():
    client = _FakeClient([_accepted_response()])
    outcome = _run(
        admission.reconcile_by_request_ref(
            client, socket_path="/tmp/does-not-matter.sock", request_ref=LITERAL_APP_REQUEST_REF
        )
    )
    assert outcome.status == admission.STATUS_ACCEPTED
    frame = client.sent_frames[0]
    assert frame["schema"] == ceo_ingress.STATUS_SCHEMA_V2
    assert frame == {"schema": ceo_ingress.STATUS_SCHEMA_V2, "request_ref": LITERAL_APP_REQUEST_REF}


def test_reconcile_never_carries_a_request_body():
    """The status v2 frame is exactly {schema, request_ref} -- proves this
    module cannot smuggle a semantic payload into a 'reconciliation'."""

    client = _FakeClient([_accepted_response()])
    _run(
        admission.reconcile_by_request_ref(
            client, socket_path="/tmp/x.sock", request_ref=LITERAL_APP_REQUEST_REF
        )
    )
    assert set(client.sent_frames[0]) == {"schema", "request_ref"}


def test_malformed_request_ref_is_refused_by_status_frame_construction():
    # AUTOMATED_REQUEST_REF_RE is the caller's (app.py's) own gate; this
    # proves reconcile_by_request_ref does not itself repair a bad ref, it
    # simply forwards whatever it is given -- validation lives at the edge.
    client = _FakeClient(
        [CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error={"code": "invalid_input", "message": "bad ref"})]
    )
    outcome = _run(
        admission.reconcile_by_request_ref(client, socket_path="/tmp/x.sock", request_ref="not-a-ref")
    )
    assert outcome.status == admission.STATUS_REFUSED


# ===========================================================================
# 3. gateway.observe_trusted_grounding — REAL git reads, no mocking
# ===========================================================================


def _init_git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "BSC-E1 Fixture"], check=True
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "bsc-e1-fixture@example.invalid"],
        check=True,
    )
    (path / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "fixture"], check=True)
    sha = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    return sha


def test_observe_trusted_grounding_reads_real_head_sha(tmp_path):
    mastermind_root = tmp_path / "mastermind"
    macro_root = tmp_path / "macro"
    mastermind_sha = _init_git_repo(mastermind_root)
    (macro_root / "scripts").mkdir(parents=True)
    (macro_root / "scripts" / "agentos.py").write_text("", encoding="utf-8")
    (macro_root / "agentos").mkdir()
    macro_sha = _init_git_repo(macro_root)

    grounding = gateway.observe_trusted_grounding(
        mastermind_root=mastermind_root,
        macro_root_flag=str(macro_root),
        environ={},
    )
    assert grounding == {
        "mastermind_sha": mastermind_sha,
        "macro_sha": macro_sha,
        "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
    }


def test_observe_trusted_grounding_refuses_when_mastermind_root_is_not_git(tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    with pytest.raises(gateway.GroundingUnavailable):
        gateway.observe_trusted_grounding(
            mastermind_root=not_a_repo, macro_root_flag=None, environ={}
        )


def test_observe_trusted_grounding_refuses_when_macro_root_unresolvable(tmp_path):
    mastermind_root = tmp_path / "mastermind"
    _init_git_repo(mastermind_root)
    with pytest.raises(gateway.GroundingUnavailable):
        gateway.observe_trusted_grounding(
            mastermind_root=mastermind_root,
            macro_root_flag=str(tmp_path / "does-not-exist"),
            environ={},
        )
