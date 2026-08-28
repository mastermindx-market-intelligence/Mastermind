from __future__ import annotations

import copy

import pytest

try:
    from control_plane.session_truth import compute_admission
    from control_plane.session_truth_rules import (
        FINDING_REGISTRY,
        build_indexes,
        detect_findings,
    )
except ModuleNotFoundError as exc:
    if exc.name != "control_plane.session_truth_rules":
        raise
    FINDING_REGISTRY = {}

    def _missing(*_args, **_kwargs):
        raise NotImplementedError("session_truth_rules not implemented")

    compute_admission = _missing
    build_indexes = _missing
    detect_findings = _missing


MASTER = "mastermindx-market-intelligence/Mastermind"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
NOW = "2026-08-27T08:00:00Z"

STATE_DIGEST = "sha256:" + "7" * 64
CONTEXT_DIGEST = "sha256:" + "8" * 64

EXPECTED_REGISTRY = {
    "AGENTOS_RECORD_IDENTITY_UNAVAILABLE": ("BLOCKING", "agentos", "agentos"),
    "COMPLETION_OWNER_EVIDENCE_UNKNOWN": (
        "BLOCKING",
        "declared_completion_owner",
        "declared_completion_owner",
    ),
    "STALE_LINEAR_PROJECTION": ("WARNING", "agentos", "linear"),
    "FALSE_LINEAR_COMPLETION": ("BLOCKING", "declared_completion_owner", "linear"),
    "MISSING_LINEAR_PROJECTION": ("WARNING", "agentos", "linear"),
    "LINEAR_PARENT_CHILD_DIVERGENCE": ("WARNING", "linear_projection", "linear"),
    "ORPHAN_LINEAR_ISSUE": ("WARNING", "agentos", "linear"),
    "BUILD_VISIBILITY_STALE": ("INFO", "github_or_linear", "slack"),
    "GITHUB_PR_UNBOUND": ("WARNING", "github", "github"),
    "GITHUB_MERGE_WITH_PROOF_OPEN": ("BLOCKING", "declared_completion_owner", "linear"),
    "ORPHAN_GITHUB_CARRIER": ("WARNING", "agentos", "github"),
    "MULTIPLE_ACTIVE_CARRIERS": ("FATAL", "github", "github"),
    "CARRIER_HEAD_MOVED": ("BLOCKING", "github", "github"),
    "PR_BINDING_CONFLICT": ("FATAL", "github", "github"),
    "AGENTOS_GITHUB_DISAGREEMENT": ("WARNING", "agentos_or_github_by_fact", "agentos_or_github"),
    "STALE_HANDOFF": ("WARNING", "agentos", "agentos"),
    "SUPERSEDED_NEXT_ACTION": ("WARNING", "agentos", "agentos"),
    "DIRECT_GENERATED_STATE_DIVERGENCE": ("WARNING", "agentos_direct", "agentos_generated"),
    "SLACK_TRANSPORT_WITHOUT_RECEIVER": ("BLOCKING", "executive_or_active_session", "slack"),
    "SLACK_TRANSPORT_WITHOUT_ACK": ("WARNING", "runtime_session", "slack"),
    "CEO_SEAT_USED_AS_WORKER": ("FATAL", "identity_registry", "slack"),
    "DUPLICATE_OPERATION_CARRIER": ("FATAL", "executive_or_carrier_owner", "slack_or_github"),
    "POST_FREEZE_DISPATCH_VIOLATION": ("BLOCKING", "source_law", "slack"),
    "RUNTIME_STATE_UNAVAILABLE": ("BLOCKING", "executive", "executive"),
    "RUNTIME_STATE_STALE": ("BLOCKING", "executive", "executive"),
    "SLACK_ACK_WITHOUT_EXECUTIVE_STATE": ("BLOCKING", "executive", "slack"),
    "EXECUTIVE_GROUNDING_DIVERGED": ("BLOCKING", "executive", "executive"),
    "UNKNOWN_SEAT_IDENTITY": ("WARNING", "identity_registry", "identity_registry"),
    "SERVICE_ACTOR_UNBOUND": ("BLOCKING", "identity_registry", "identity_registry"),
    "ACTOR_ROLE_COLLISION": ("FATAL", "identity_registry", "identity_registry"),
}

# Owner-record identity amendment §8 freezes ``pickup_head_sha`` as provenance,
# not an expected immutable carrier head.  The V1 envelope has no exact
# expected/prior-observed head fact, so this registry code remains public but no
# V1 detector may fabricate it from ordinary implementation progress.
V1_EMITTABLE_REGISTRY = frozenset(EXPECTED_REGISTRY) - {"CARRIER_HEAD_MOVED"}


def _workstream() -> dict:
    return {
        "key": "TARGET",
        "status": "active",
        "repos": ["mastermind"],
        "next_action": "Complete the R1 receipt.",
        "updated": "2026-08-27",
        "projection_revision": 7,
        "waves": {"in_progress": 1, "done": 0},
        "wave_detail": [
            {
                "id": "R1",
                "status": "in_progress",
                "next_action": "Complete the R1 receipt.",
                "prs": [170],
                "done_at": None,
            }
        ],
        "prs": [
            {"number": 170, "state": "open", "wave": "R1", "merged_at": None}
        ],
        "warnings": [],
        "source": "agentos/workstreams/WS-TARGET.md",
    }


def _handoff_context() -> dict:
    return {
        "schema": "context_bundle.v1",
        "target": {"workstream": "WS:TARGET", "resolution": "explicit"},
        "sections": [
            {
                "id": "handoff",
                "items": [
                    {
                        "kind": "handoff",
                        "key": "WS-TARGET-2026-08-27",
                        "path": "agentos/handoffs/WS-TARGET-2026-08-27.md",
                        "locator": "frontmatter",
                        "authority_class": "A2",
                        "status": "current",
                        "updated": "2026-08-27",
                        "excerpt": "next_actions: Complete the R1 receipt.",
                        "why_included": "latest handoff for WS:TARGET",
                    }
                ],
            }
        ],
        "excluded": [],
        "omitted_due_to_budget": [],
        "degraded": [],
        "source_records_digest": CONTEXT_DIGEST,
    }


def _pr(number: int = 170, *, operation_key: str = "op-main") -> dict:
    return {
        "repository": MASTER,
        "number": number,
        "state": "open",
        "draft": True,
        "head_sha": SHA_B,
        "base_sha": SHA_A,
        "merge_sha": None,
        "ci": "success",
        "workstream": "WS:TARGET",
        "linear": "MAS-10",
        "portfolio_mode": "implementation",
        "wave": "R1",
        "authority": "implementation",
        "completion": "hosted-ci+current-estate-proof+sol-acceptance",
        "proof_state": "open",
        "operation_key": operation_key,
        "pickup_head_sha": SHA_B,
    }


def _issue(issue_id: str = "MAS-10") -> dict:
    return {
        "id": issue_id,
        "status": "In Progress",
        "parent_id": None,
        "workstream": "WS:TARGET",
        "completion": "hosted-ci+current-estate-proof+sol-acceptance",
        "projection_revision": 7,
        "github_relations": [
            {"repository": MASTER, "number": 170, "relation": "program_gate"}
        ],
        "updated_at": NOW,
    }


def _slack_message(*, operation_key: str = "op-main") -> dict:
    return {
        "channel_id": "C-DISPATCH",
        "ts": "1787817955.208049",
        "thread_ts": None,
        "sender_id": "U-SOL",
        "operation_key": operation_key,
        "payload_hash": HASH_1,
        "transport": "DELIVERY_ONLY",
        "message_class": "PICKUP",
        "target_principal_id": "U-WORKER",
        "delivered": True,
        "acked": True,
        "receiver_eligible": True,
        "ack_required": True,
        "created_at": "2026-08-27T07:59:00Z",
        "source_law_sha": SHA_A,
        "freeze_at": None,
    }


def healthy_inputs() -> dict:
    return {
        "schema": "mastermind.session_truth_inputs.v1",
        "scope": {
            "workstreams": ["WS:TARGET"],
            "linear": ["MAS-10"],
            "repositories": [MASTER],
            "operation_key": "op-main",
            "requires_executive": False,
        },
        "skillpack": {
            "repository": MASTER,
            "sha": SHA_A,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.0",
            "minimum_bootstrap_major": 1,
            "available": True,
        },
        "agentos": {
            "available": True,
            "source_sha": SHA_C,
            "state": {
                "schema": "agent_os_state.v1",
                "generated_at": NOW,
                "source_records_digest": STATE_DIGEST,
                "direct_state_hash": HASH_1,
                "generated_state_hash": HASH_1,
                "workstreams": [_workstream()],
                "warnings": [],
            },
            "contexts": [_handoff_context()],
            "warnings": [],
        },
        "github": {
            "available": True,
            "observed_at": NOW,
            "pull_requests": [_pr()],
        },
        "linear": {
            "available": True,
            "observed_at": NOW,
            "issues": [_issue()],
        },
        "slack": {
            "available": True,
            "observed_at": NOW,
            "channels": [
                {
                    "channel_id": "C-DISPATCH",
                    "member_ids": ["U-SOL", "U-WORKER", "U-SERVICE"],
                }
            ],
            "messages": [_slack_message()],
        },
        "executive": {
            "available": True,
            "observed_at": NOW,
            "fresh": True,
            "do_not_submit": False,
            "grounding_sha": SHA_A,
            "operations": [
                {
                    "operation_key": "op-main",
                    "payload_hash": HASH_1,
                    "status": "RUNNING",
                    "effect_unknown": False,
                    "carrier": "executive",
                }
            ],
        },
        "identities": {
            "available": True,
            "observed_at": NOW,
            "bindings": [
                {
                    "seat": "ChatGPT2",
                    "slack_principal": "U-SOL",
                    "github_account": "mastermindx-2",
                    "linear_actor": "linear-sol-2",
                    "executive_worker": None,
                    "provider_realm": "codex-pro-02",
                    "role": "sol_ceo",
                    "service_actor": None,
                },
                {
                    "seat": "Claude8",
                    "slack_principal": "U-WORKER",
                    "github_account": None,
                    "linear_actor": None,
                    "executive_worker": "worker-8",
                    "provider_realm": "claude-08",
                    "role": "worker",
                    "service_actor": None,
                },
                {
                    "seat": "AgentRelay",
                    "slack_principal": "U-SERVICE",
                    "github_account": None,
                    "linear_actor": None,
                    "executive_worker": None,
                    "provider_realm": None,
                    "role": "service_actor",
                    "service_actor": "agent-relay",
                },
            ],
        },
    }


@pytest.fixture()
def healthy() -> dict:
    return healthy_inputs()


def _codes(doc: dict) -> set[str]:
    return {finding["code"] for finding in detect_findings(doc)}


def _mutate(code: str, doc: dict) -> None:
    if code == "AGENTOS_RECORD_IDENTITY_UNAVAILABLE":
        del doc["agentos"]["state"]["source_records_digest"]
    elif code == "COMPLETION_OWNER_EVIDENCE_UNKNOWN":
        doc["linear"]["issues"][0]["status"] = "Done"
        doc["github"]["pull_requests"][0]["proof_state"] = "unknown"
    elif code == "STALE_LINEAR_PROJECTION":
        doc["linear"]["issues"][0]["projection_revision"] = 6
    elif code == "FALSE_LINEAR_COMPLETION":
        doc["linear"]["issues"][0]["status"] = "Done"
    elif code == "MISSING_LINEAR_PROJECTION":
        doc["scope"]["linear"].append("MAS-11")
    elif code == "LINEAR_PARENT_CHILD_DIVERGENCE":
        parent = _issue("MAS-20")
        parent.update({"status": "Done", "github_relations": []})
        child = _issue("MAS-21")
        child.update({"parent_id": "MAS-20", "github_relations": []})
        doc["linear"]["issues"].extend([parent, child])
    elif code == "ORPHAN_LINEAR_ISSUE":
        doc["linear"]["issues"][0]["workstream"] = "WS:GHOST"
    elif code == "BUILD_VISIBILITY_STALE":
        doc["slack"]["observed_at"] = "2026-08-27T07:00:00Z"
    elif code == "GITHUB_PR_UNBOUND":
        doc["github"]["pull_requests"][0]["workstream"] = None
    elif code == "GITHUB_MERGE_WITH_PROOF_OPEN":
        pr = doc["github"]["pull_requests"][0]
        pr.update({"state": "merged", "merge_sha": SHA_C})
    elif code == "ORPHAN_GITHUB_CARRIER":
        doc["github"]["pull_requests"][0]["workstream"] = "WS:GHOST"
    elif code == "MULTIPLE_ACTIVE_CARRIERS":
        second = _pr(171)
        second["head_sha"] = SHA_C
        second["pickup_head_sha"] = SHA_C
        doc["github"]["pull_requests"].append(second)
    elif code == "PR_BINDING_CONFLICT":
        doc["github"]["pull_requests"][0]["linear"] = "MAS-11"
    elif code == "AGENTOS_GITHUB_DISAGREEMENT":
        doc["agentos"]["state"]["workstreams"][0]["prs"][0]["state"] = "merged"
    elif code == "STALE_HANDOFF":
        doc["agentos"]["contexts"][0]["sections"][0]["items"][0]["updated"] = "2026-08-20"
    elif code == "SUPERSEDED_NEXT_ACTION":
        doc["agentos"]["contexts"][0]["excluded"].append(
            {
                "kind": "handoff",
                "path": "agentos/handoffs/WS-TARGET-2026-08-26.md",
                "reason": "superseded_next_action",
            }
        )
    elif code == "DIRECT_GENERATED_STATE_DIVERGENCE":
        doc["agentos"]["state"]["generated_state_hash"] = HASH_2
    elif code == "SLACK_TRANSPORT_WITHOUT_RECEIVER":
        message = doc["slack"]["messages"][0]
        message.update({"receiver_eligible": False, "acked": False})
    elif code == "SLACK_TRANSPORT_WITHOUT_ACK":
        doc["slack"]["messages"][0]["acked"] = False
    elif code == "CEO_SEAT_USED_AS_WORKER":
        doc["slack"]["messages"][0]["target_principal_id"] = "U-SOL"
    elif code == "DUPLICATE_OPERATION_CARRIER":
        doc["slack"]["messages"][0]["payload_hash"] = HASH_2
    elif code == "POST_FREEZE_DISPATCH_VIOLATION":
        doc["slack"]["messages"][0]["freeze_at"] = "2026-08-27T07:00:00Z"
    elif code == "RUNTIME_STATE_UNAVAILABLE":
        doc["scope"]["requires_executive"] = True
        doc["executive"] = {"available": False, "reason": "EXECUTIVE_READ_PATH_UNAVAILABLE"}
    elif code == "RUNTIME_STATE_STALE":
        doc["scope"]["requires_executive"] = True
        doc["executive"]["fresh"] = False
    elif code == "SLACK_ACK_WITHOUT_EXECUTIVE_STATE":
        # The amendment gates this finding on a scope that positively owes Executive
        # state, with Executive itself readable.
        doc["scope"]["requires_executive"] = True
        doc["executive"]["operations"] = []
    elif code == "EXECUTIVE_GROUNDING_DIVERGED":
        doc["executive"]["grounding_sha"] = SHA_C
    elif code == "UNKNOWN_SEAT_IDENTITY":
        doc["identities"]["bindings"][0]["slack_principal"] = None
    elif code == "SERVICE_ACTOR_UNBOUND":
        doc["identities"]["bindings"][2]["service_actor"] = None
    elif code == "ACTOR_ROLE_COLLISION":
        collision = copy.deepcopy(doc["identities"]["bindings"][1])
        collision.update({"seat": "WorkerCollision", "slack_principal": "U-SOL"})
        doc["identities"]["bindings"].append(collision)
    else:  # pragma: no cover - registry/test maintenance guard
        raise AssertionError(f"no mutation fixture for {code}")


def test_finding_registry_is_exact_and_frozen():
    assert FINDING_REGISTRY == EXPECTED_REGISTRY


@pytest.mark.parametrize("code", sorted(V1_EMITTABLE_REGISTRY))
def test_every_required_finding_has_positive_and_negative_case(code, healthy):
    assert code not in _codes(healthy), f"healthy fixture unexpectedly emits {code}"
    changed = copy.deepcopy(healthy)
    _mutate(code, changed)
    assert code in _codes(changed), f"mutation did not emit {code}"


def test_findings_have_exact_keys_registry_severity_and_consequence(healthy):
    changed = copy.deepcopy(healthy)
    _mutate("FALSE_LINEAR_COMPLETION", changed)
    finding = next(
        item for item in detect_findings(changed)
        if item["code"] == "FALSE_LINEAR_COMPLETION"
    )
    assert set(finding) == {
        "code",
        "severity",
        "canonical_owner",
        "subject",
        "source_a",
        "source_b",
        "repair_owner",
        "modification_consequence",
        "details",
    }
    assert finding["severity"] == "BLOCKING"
    assert finding["canonical_owner"] == "declared_completion_owner"
    assert finding["repair_owner"] == "linear"
    assert finding["modification_consequence"] == "requested_modification_blocked"


def test_findings_sort_fatal_then_blocking_warning_info(healthy):
    changed = copy.deepcopy(healthy)
    for code in (
        "BUILD_VISIBILITY_STALE",
        "STALE_LINEAR_PROJECTION",
        "RUNTIME_STATE_STALE",
        "ACTOR_ROLE_COLLISION",
    ):
        _mutate(code, changed)
    findings = detect_findings(changed)
    rank = {"FATAL": 0, "BLOCKING": 1, "WARNING": 2, "INFO": 3}
    keys = [(rank[item["severity"]], item["code"], item["subject"]) for item in findings]
    assert keys == sorted(keys)


def test_two_projections_cannot_outvote_owner(healthy):
    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    visibility = _slack_message(operation_key="visibility-done")
    visibility.update(
        {
            "ts": "1787817956.208049",
            "message_class": "BUILD_EVENT",
            "target_principal_id": None,
            "ack_required": False,
            "acked": False,
            "receiver_eligible": None,
        }
    )
    changed["slack"]["messages"].append(visibility)
    assert "FALSE_LINEAR_COMPLETION" in _codes(changed)


@pytest.mark.parametrize("proof_state", ["complete", "proven_live", "not_required"])
def test_non_merge_linear_done_with_exact_terminal_proof_is_not_false_completion(
    healthy, proof_state
):
    """A terminal owner proof, not completion-string spelling, decides validity."""

    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    changed["github"]["pull_requests"][0]["proof_state"] = proof_state
    codes = _codes(changed)
    assert "FALSE_LINEAR_COMPLETION" not in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" not in codes


@pytest.mark.parametrize(
    "proof_state",
    ["open", "not_built", "spec_only", "partial", "built_not_proven", "blocked"],
)
def test_linear_done_with_exact_nonterminal_owner_is_false_completion(
    healthy, proof_state
):
    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    changed["github"]["pull_requests"][0]["proof_state"] = proof_state
    codes = _codes(changed)
    assert "FALSE_LINEAR_COMPLETION" in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" not in codes


@pytest.mark.parametrize("proof_state", ["future_owner_state", "unknown", None])
def test_linear_done_with_unknown_exact_owner_blocks_without_false_claim(
    healthy, proof_state
):
    """Opaque or absent exact-owner proof is blocking uncertainty, not false proof."""

    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    changed["github"]["pull_requests"][0]["proof_state"] = proof_state
    findings = detect_findings(changed)
    codes = {finding["code"] for finding in findings}
    assert "FALSE_LINEAR_COMPLETION" not in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" in codes
    admission = compute_admission(changed, findings)
    assert admission["mode"] == "DIALOGUE_ONLY"
    assert admission["modification_safe"] is False
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" in admission["blocking_codes"]


@pytest.mark.parametrize(
    "relation",
    ["contributing", "architecture_evidence", "ignored_wrong_id"],
)
def test_non_owner_pr_relation_cannot_decide_linear_completion(healthy, relation):
    """Only an owner-produced completion-gate relation can testify for Done."""

    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    changed["linear"]["issues"][0]["github_relations"][0]["relation"] = relation
    assert changed["github"]["pull_requests"][0]["proof_state"] == "open"
    codes = _codes(changed)
    assert "FALSE_LINEAR_COMPLETION" not in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" in codes


def test_one_way_completion_relation_is_not_exact_owner_evidence(healthy):
    """A Linear relation without the PR's reciprocal binding cannot decide completion."""

    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    changed["github"]["pull_requests"][0]["linear"] = None
    codes = _codes(changed)
    assert "FALSE_LINEAR_COMPLETION" not in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" in codes


def test_same_pr_number_in_other_repository_is_not_completion_owner(healthy):
    """Repository plus PR number, not a bare number, qualifies owner evidence."""

    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    changed["github"]["pull_requests"][0]["repository"] = OTHER_REPO
    codes = _codes(changed)
    assert "FALSE_LINEAR_COMPLETION" not in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" in codes


def test_foreign_same_number_nonterminal_does_not_outvote_exact_terminal_owner(healthy):
    """An exact repository-qualified terminal owner stays healthy despite # collision."""

    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["status"] = "Done"
    changed["github"]["pull_requests"][0]["proof_state"] = "complete"
    foreign = copy.deepcopy(changed["github"]["pull_requests"][0])
    foreign.update(
        {
            "repository": OTHER_REPO,
            "proof_state": "open",
            "linear": "MAS-10",
            "wave": "R1-FOREIGN",
            "operation_key": "op-foreign",
        }
    )
    changed["github"]["pull_requests"].append(foreign)
    codes = _codes(changed)
    assert "FALSE_LINEAR_COMPLETION" not in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" not in codes


@pytest.mark.parametrize("proof_state", ["future_owner_state", "unknown", None])
def test_merged_non_merge_completion_with_unknown_proof_blocks_as_uncertain(
    healthy, proof_state
):
    """A merge cannot make unknown non-merge completion evidence safe."""

    changed = copy.deepcopy(healthy)
    changed["github"]["pull_requests"][0].update(
        {
            "state": "merged",
            "merge_sha": SHA_C,
            "proof_state": proof_state,
        }
    )
    codes = _codes(changed)
    assert "GITHUB_MERGE_WITH_PROOF_OPEN" not in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" in codes


def test_merged_non_merge_completion_with_nonterminal_proof_is_proof_open(healthy):
    changed = copy.deepcopy(healthy)
    changed["github"]["pull_requests"][0].update(
        {"state": "merged", "merge_sha": SHA_C, "proof_state": "built_not_proven"}
    )
    codes = _codes(changed)
    assert "GITHUB_MERGE_WITH_PROOF_OPEN" in codes
    assert "COMPLETION_OWNER_EVIDENCE_UNKNOWN" not in codes


def test_ordinary_open_carrier_progress_is_not_unexpected_head_movement(healthy):
    """The original pickup SHA is provenance and may differ after lawful commits."""

    changed = copy.deepcopy(healthy)
    changed["github"]["pull_requests"][0]["head_sha"] = SHA_C
    assert changed["github"]["pull_requests"][0]["pickup_head_sha"] == SHA_B
    assert "CARRIER_HEAD_MOVED" not in _codes(changed)


def test_name_similarity_never_binds_ceo_to_worker(healthy):
    changed = copy.deepcopy(healthy)
    changed["identities"]["bindings"] = [
        {
            "seat": "ChatGPT2",
            "slack_principal": "U-CHATGPT2",
            "github_account": None,
            "linear_actor": None,
            "executive_worker": None,
            "provider_realm": "codex-pro-02",
            "role": "sol_ceo",
            "service_actor": None,
        }
    ]
    message = _slack_message()
    message["target_principal_id"] = "U-CHATGPT2"
    changed["slack"]["channels"][0]["member_ids"] = ["U-CHATGPT2"]
    changed["slack"]["messages"] = [message]
    assert "CEO_SEAT_USED_AS_WORKER" in _codes(changed)


def test_same_operation_key_changed_payload_is_fatal(healthy):
    changed = copy.deepcopy(healthy)
    changed["slack"]["messages"][0]["payload_hash"] = HASH_2
    finding = next(
        item for item in detect_findings(changed)
        if item["code"] == "DUPLICATE_OPERATION_CARRIER"
    )
    assert finding["severity"] == "FATAL"
    assert finding["modification_consequence"] == "new_modification_refused"


def test_effect_unknown_is_fatal_duplicate_operation_conflict(healthy):
    changed = copy.deepcopy(healthy)
    changed["executive"]["operations"][0]["effect_unknown"] = True
    assert "DUPLICATE_OPERATION_CARRIER" in _codes(changed)


def test_build_indexes_uses_exact_ids_not_titles(healthy):
    indexes = build_indexes(healthy)
    assert indexes["workstreams"]["WS:TARGET"]["key"] == "TARGET"
    assert indexes["linear"]["MAS-10"]["id"] == "MAS-10"
    assert indexes["github"][(MASTER, 170)]["number"] == 170
    assert indexes["identities_by_slack"]["U-SOL"][0]["seat"] == "ChatGPT2"


def test_rules_never_mutate_input(healthy):
    before = copy.deepcopy(healthy)
    build_indexes(healthy)
    detect_findings(healthy)
    assert healthy == before


UNAVAILABLE_LINEAR = {"available": False, "reason": "LINEAR_READ_PATH_UNAVAILABLE"}


def _linear_unavailable(doc: dict) -> dict:
    doc["linear"] = copy.deepcopy(UNAVAILABLE_LINEAR)
    return doc


def test_unavailable_linear_never_fabricates_a_binding_conflict(healthy):
    """D2: inability to look up MAS-10 is unknown, not proof the issue is absent."""

    changed = _linear_unavailable(copy.deepcopy(healthy))
    assert changed["github"]["pull_requests"][0]["linear"] == "MAS-10"
    codes = _codes(changed)
    assert "PR_BINDING_CONFLICT" not in codes
    assert "MISSING_LINEAR_PROJECTION" not in codes


def test_unavailable_linear_never_fabricates_a_missing_projection(healthy):
    changed = _linear_unavailable(copy.deepcopy(healthy))
    changed["scope"]["linear"] = ["MAS-10", "MAS-11"]
    assert "MISSING_LINEAR_PROJECTION" not in _codes(changed)


def test_available_linear_with_genuinely_absent_issue_is_still_fatal(healthy):
    changed = copy.deepcopy(healthy)
    changed["github"]["pull_requests"][0]["linear"] = "MAS-11"
    findings = [f for f in detect_findings(changed) if f["code"] == "PR_BINDING_CONFLICT"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "FATAL"
    assert findings[0]["subject"] == f"{MASTER}#170"


def test_available_linear_with_mismatched_relation_is_still_fatal(healthy):
    changed = copy.deepcopy(healthy)
    changed["linear"]["issues"][0]["github_relations"] = [
        {"repository": MASTER, "number": 171, "relation": "program_gate"}
    ]
    findings = [f for f in detect_findings(changed) if f["code"] == "PR_BINDING_CONFLICT"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "FATAL"


def test_available_linear_with_absent_scope_issue_is_still_reported(healthy):
    changed = copy.deepcopy(healthy)
    changed["scope"]["linear"] = ["MAS-10", "MAS-11"]
    codes = _codes(changed)
    assert "MISSING_LINEAR_PROJECTION" in codes


def test_unavailable_linear_does_not_silence_non_linear_findings(healthy):
    changed = _linear_unavailable(copy.deepcopy(healthy))
    changed["github"]["pull_requests"][0]["workstream"] = None
    assert "GITHUB_PR_UNBOUND" in _codes(changed)


def test_unavailable_linear_is_typed_unknown_in_indexes(healthy):
    changed = _linear_unavailable(copy.deepcopy(healthy))
    indexes = build_indexes(changed)
    assert indexes["linear"] == {}
    assert indexes["linear_available"] is False
    assert build_indexes(healthy)["linear_available"] is True


# --- Owner-record identity amendment falsifiers (2026-08-28, Sol) -----------------
#
# §6: SLACK_ACK_WITHOUT_EXECUTIVE_STATE fires only for a scope that positively owes
# Executive state while Executive itself is readable.
# §7: a bare Agent OS PR number never binds across multiple repositories.

OTHER_REPO = "mastermindx-market-intelligence/macro"


def test_ack_without_executive_scope_creates_no_executive_finding(healthy):
    """A lawful read-only/active-session ACK owes no Executive operation record."""

    doc = copy.deepcopy(healthy)
    assert doc["scope"]["requires_executive"] is False
    doc["executive"]["operations"] = []
    assert "SLACK_ACK_WITHOUT_EXECUTIVE_STATE" not in _codes(doc)


def test_ack_with_executive_unavailable_defers_to_required_source_path(healthy):
    """An unreadable Executive cannot testify that the operation record is absent."""

    doc = copy.deepcopy(healthy)
    doc["scope"]["requires_executive"] = True
    doc["executive"] = {
        "available": False,
        "reason": "EXECUTIVE_READ_PATH_UNAVAILABLE",
    }
    codes = _codes(doc)
    assert "SLACK_ACK_WITHOUT_EXECUTIVE_STATE" not in codes
    assert "RUNTIME_STATE_UNAVAILABLE" in codes


def test_ack_with_executive_required_and_available_still_fires(healthy):
    doc = copy.deepcopy(healthy)
    doc["scope"]["requires_executive"] = True
    doc["executive"]["operations"] = []
    assert "SLACK_ACK_WITHOUT_EXECUTIVE_STATE" in _codes(doc)


def _two_repo_same_number(doc: dict) -> None:
    """Two repositories carry the same PR number bound to the same workstream."""

    other = _pr(170, operation_key="op-other")
    other["repository"] = OTHER_REPO
    other["state"] = "merged"
    other["merge_sha"] = SHA_C
    other["completion"] = "merge-is-done"
    other["linear"] = None
    other["wave"] = "R1-OTHER"
    doc["github"]["pull_requests"].append(other)


def test_bare_agentos_pr_number_never_binds_across_repositories(healthy):
    doc = copy.deepcopy(healthy)
    doc["scope"]["repositories"] = [MASTER, OTHER_REPO]
    _two_repo_same_number(doc)
    # The Agent OS record says #170 is open; the foreign repository's #170 is merged.
    # With two repositories in scope the bare number is AMBIGUOUS/UNBOUND: no join,
    # so no disagreement may be fabricated from the foreign repository's state.
    assert "AGENTOS_GITHUB_DISAGREEMENT" not in _codes(doc)


def test_single_repository_scope_qualifies_bare_pr_number(healthy):
    doc = copy.deepcopy(healthy)
    assert doc["scope"]["repositories"] == [MASTER]
    doc["agentos"]["state"]["workstreams"][0]["prs"][0]["state"] = "merged"
    assert "AGENTOS_GITHUB_DISAGREEMENT" in _codes(doc)


def test_single_repository_scope_never_joins_the_foreign_repository(healthy):
    doc = copy.deepcopy(healthy)
    assert doc["scope"]["repositories"] == [MASTER]
    _two_repo_same_number(doc)
    # The scoped repository's #170 agrees with the Agent OS record; only the foreign
    # repository's #170 disagrees, and it is outside the one-repository qualification.
    assert "AGENTOS_GITHUB_DISAGREEMENT" not in _codes(doc)
