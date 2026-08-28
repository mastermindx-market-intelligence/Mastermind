from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane.session_truth_contract import SessionTruthContractError

try:
    from control_plane.session_truth_snapshots import (
        EXECUTIVE_SCHEMA,
        GITHUB_SCHEMA,
        IDENTITY_SCHEMA,
        LINEAR_SCHEMA,
        SLACK_SCHEMA,
        load_snapshot,
        normalize_executive,
        normalize_github,
        normalize_identities,
        normalize_linear,
        normalize_slack,
    )
except ModuleNotFoundError as exc:
    if exc.name != "control_plane.session_truth_snapshots":
        raise
    GITHUB_SCHEMA = "mastermind.github_observation.v1"
    LINEAR_SCHEMA = "mastermind.linear_observation.v1"
    SLACK_SCHEMA = "mastermind.slack_observation.v1"
    EXECUTIVE_SCHEMA = "mastermind.executive_observation.v1"
    IDENTITY_SCHEMA = "mastermind.identity_observation.v1"

    def _missing(*_args, **_kwargs):
        raise NotImplementedError("session_truth_snapshots not implemented")

    load_snapshot = _missing
    normalize_github = _missing
    normalize_linear = _missing
    normalize_slack = _missing
    normalize_executive = _missing
    normalize_identities = _missing


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "session_truth"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_github_snapshot_normalizes_exact_fields_and_order(tmp_path):
    doc = _fixture("github_minimal.json")
    second = copy.deepcopy(doc["pull_requests"][0])
    second.update(
        {
            "number": 12,
            "head_sha": "c" * 40,
            "base_sha": "d" * 40,
            "pickup_head_sha": "c" * 40,
            "operation_key": "earlier-operation",
        }
    )
    doc["pull_requests"] = [doc["pull_requests"][0], second]
    path = tmp_path / "github.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    loaded = load_snapshot(path, GITHUB_SCHEMA)
    normalized = normalize_github(loaded)

    assert normalized["available"] is True
    assert normalized["observed_at"] == "2026-08-27T08:00:00Z"
    assert [row["number"] for row in normalized["pull_requests"]] == [12, 169]
    row = normalized["pull_requests"][1]
    assert set(row) == {
        "repository",
        "number",
        "state",
        "draft",
        "head_sha",
        "base_sha",
        "merge_sha",
        "ci",
        "workstream",
        "linear",
        "portfolio_mode",
        "wave",
        "authority",
        "completion",
        "proof_state",
        "operation_key",
        "pickup_head_sha",
    }
    assert row["merge_sha"] is None
    assert row["linear"] is None


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("number", "169"),
        ("draft", 1),
        ("ci", "mystery"),
    ],
)
def test_github_rejects_coercion_and_owner_independent_enum_drift(field, bad_value):
    doc = _fixture("github_minimal.json")
    doc["pull_requests"][0][field] = bad_value
    with pytest.raises(SessionTruthContractError):
        normalize_github(doc)


@pytest.mark.parametrize(
    ("portfolio_mode", "authority", "completion", "proof_state"),
    [
        (
            "architecture",
            "chairman-approved architecture + implementation plans",
            "records-only-plan-freeze-merged",
            "complete",
        ),
        (
            "implementation",
            "implementation+conformance",
            "hosted-ci+adversarial-review+sol-acceptance",
            "proven_live",
        ),
        (
            "implementation",
            "implementation+production-proof",
            "hosted-ci+security+adversarial-review+claude-preflight+codex-delivery-canary+sol-acceptance",
            "future_owner_state",
        ),
    ],
)
def test_github_preserves_repository_owned_pr_metadata_as_opaque_strings(
    portfolio_mode,
    authority,
    completion,
    proof_state,
):
    """PRs #171/#173/#174 and future owner values remain observable verbatim."""

    doc = _fixture("github_minimal.json")
    doc["pull_requests"][0].update(
        {
            "portfolio_mode": portfolio_mode,
            "authority": authority,
            "completion": completion,
            "proof_state": proof_state,
        }
    )
    normalized = normalize_github(doc)["pull_requests"][0]
    assert normalized["portfolio_mode"] == portfolio_mode
    assert normalized["authority"] == authority
    assert normalized["completion"] == completion
    assert normalized["proof_state"] == proof_state


def test_linear_preserves_repository_owned_completion_as_an_opaque_string():
    doc = _fixture("linear_minimal.json")
    doc["issues"][0]["completion"] = "future-owner-completion-v2"
    normalized = normalize_linear(doc)
    assert normalized["issues"][0]["completion"] == "future-owner-completion-v2"


def test_linear_normalizes_relation_class_and_rejects_bad_revision():
    doc = _fixture("linear_minimal.json")
    normalized = normalize_linear(doc)
    issue = normalized["issues"][0]

    assert set(issue) == {
        "id",
        "status",
        "parent_id",
        "workstream",
        "completion",
        "projection_revision",
        "github_relations",
        "updated_at",
    }
    assert issue["parent_id"] is None
    assert issue["github_relations"] == [
        {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "number": 155,
            "relation": "program_gate",
        }
    ]

    bad = copy.deepcopy(doc)
    bad["issues"][0]["projection_revision"] = "7"
    with pytest.raises(SessionTruthContractError):
        normalize_linear(bad)

    bad = copy.deepcopy(doc)
    bad["issues"][0]["github_relations"][0]["relation"] = "looks_related"
    with pytest.raises(SessionTruthContractError):
        normalize_linear(bad)


def test_slack_normalizes_metadata_only_and_sorts_member_ids():
    doc = _fixture("slack_minimal.json")
    doc["channels"][0]["member_ids"] = ["U0BS3H525NW", "U0BRETDUAS2"]
    normalized = normalize_slack(doc)

    assert normalized["channels"] == [
        {
            "channel_id": "C0BSBM78V1N",
            "member_ids": ["U0BRETDUAS2", "U0BS3H525NW"],
        }
    ]
    message = normalized["messages"][0]
    assert set(message) == {
        "channel_id",
        "ts",
        "thread_ts",
        "sender_id",
        "operation_key",
        "payload_hash",
        "transport",
        "message_class",
        "target_principal_id",
        "delivered",
        "acked",
        "receiver_eligible",
        "ack_required",
        "created_at",
        "source_law_sha",
        "freeze_at",
    }
    assert "text" not in message
    assert message["acked"] is False

    bad = copy.deepcopy(doc)
    bad["messages"][0]["acked"] = "false"
    with pytest.raises(SessionTruthContractError):
        normalize_slack(bad)

    bad = copy.deepcopy(doc)
    bad["messages"][0]["text"] = "private message body must not enter the snapshot"
    with pytest.raises(SessionTruthContractError, match="unknown"):
        normalize_slack(bad)


def test_executive_unavailable_is_explicit_and_available_shape_is_closed():
    unavailable = normalize_executive(_fixture("executive_unavailable.json"))
    assert unavailable == {
        "available": False,
        "reason": "EXECUTIVE_READ_PATH_UNAVAILABLE",
    }

    available = {
        "schema": EXECUTIVE_SCHEMA,
        "available": True,
        "observed_at": "2026-08-27T08:00:00Z",
        "fresh": True,
        "do_not_submit": False,
        "grounding_sha": "a" * 40,
        "operations": [
            {
                "operation_key": "op-001",
                "payload_hash": "sha256:" + "1" * 64,
                "status": "QUEUED",
                "effect_unknown": False,
                "carrier": "executive",
            }
        ],
    }
    normalized = normalize_executive(available)
    assert normalized["operations"][0] == {
        "operation_key": "op-001",
        "payload_hash": "sha256:" + "1" * 64,
        "status": "QUEUED",
        "effect_unknown": False,
        "carrier": "executive",
    }

    bad = copy.deepcopy(available)
    bad["fresh"] = 1
    with pytest.raises(SessionTruthContractError):
        normalize_executive(bad)


def test_identity_bindings_preserve_null_and_never_guess():
    normalized = normalize_identities(_fixture("identity_minimal.json"))
    binding = normalized["bindings"][0]
    assert set(binding) == {
        "seat",
        "slack_principal",
        "github_account",
        "linear_actor",
        "executive_worker",
        "provider_realm",
        "role",
        "service_actor",
    }
    assert binding["github_account"] is None
    assert binding["linear_actor"] is None
    assert binding["executive_worker"] is None
    assert binding["service_actor"] is None


@pytest.mark.parametrize(
    "bad_key",
    ["token", "access_token", "authorization", "cookie", "secret", "password"],
)
def test_secret_key_names_are_rejected(tmp_path, bad_key):
    doc = _fixture("slack_minimal.json")
    doc[bad_key] = "do-not-copy"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SessionTruthContractError, match="secret-bearing key"):
        load_snapshot(path, SLACK_SCHEMA)


def test_secret_key_names_are_rejected_recursively(tmp_path):
    doc = _fixture("identity_minimal.json")
    doc["bindings"][0]["Authorization"] = "do-not-copy"
    path = tmp_path / "bad-nested.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SessionTruthContractError, match="secret-bearing key"):
        load_snapshot(path, IDENTITY_SCHEMA)


def test_harmless_secret_words_in_string_values_are_allowed(tmp_path):
    doc = _fixture("slack_minimal.json")
    doc["messages"][0]["operation_key"] = "review-secret-token-naming-law"
    path = tmp_path / "okay.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert load_snapshot(path, SLACK_SCHEMA)["messages"][0]["operation_key"] == (
        "review-secret-token-naming-law"
    )


def test_load_snapshot_rejects_wrong_schema(tmp_path):
    doc = _fixture("github_minimal.json")
    doc["schema"] = LINEAR_SCHEMA
    path = tmp_path / "wrong-schema.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SessionTruthContractError, match="schema"):
        load_snapshot(path, GITHUB_SCHEMA)


# --- Owner-record identity amendment falsifiers (2026-08-28, Sol) -----------------
#
# §5: snapshot loading rejects NaN / Infinity / -Infinity through ``parse_constant``;
# Python's default ``json.loads`` would otherwise admit them silently.


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_load_snapshot_rejects_non_finite_numbers(tmp_path, constant):
    doc = _fixture("github_minimal.json")
    text = json.dumps(doc)[:-1] + f', "observed_delay_hours": {constant}}}'
    path = tmp_path / "non-finite.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SessionTruthContractError):
        load_snapshot(path, GITHUB_SCHEMA)


def test_load_snapshot_still_accepts_finite_numbers(tmp_path):
    doc = _fixture("github_minimal.json")
    text = json.dumps(doc)[:-1] + ', "observed_delay_hours": 1.5}'
    path = tmp_path / "finite.json"
    path.write_text(text, encoding="utf-8")
    assert load_snapshot(path, GITHUB_SCHEMA)["observed_delay_hours"] == 1.5
