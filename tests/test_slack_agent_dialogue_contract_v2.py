from __future__ import annotations

import copy
import hashlib
import json

import pytest

from integrations.slack_agent_dialogue.contract import (
    DialogueContractError,
    PARENT_SCHEMA,
    build_parent,
    parse_parent_frame,
    render_parent,
)

REPO = "mastermindx-market-intelligence/Mastermind"


def commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def raw_parent(
    *,
    operation_key: str = "worker-presence-dialogue-canary-20260827-001",
    watch_mode: object = None,
    created_at: str = "2026-08-27T13:00:00Z",
) -> dict[str, object]:
    from integrations.slack_agent_dialogue.contract_v2 import PARENT_SCHEMA_V2

    return {
        "schema": PARENT_SCHEMA_V2,
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "operation_key": operation_key,
        "watch_mode": watch_mode,
        "allowed_sol_user_ids": ["U0BRETDUAS2", "U0BSB73JWNL"],
        "created_at": created_at,
    }


def _expected_fingerprint(document: dict[str, object]) -> str:
    semantic = {
        key: value
        for key, value in document.items()
        if key not in {"created_at", "fingerprint"}
    }
    canonical = json.dumps(
        semantic,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_build_parent_v2_freezes_exact_parent_shape() -> None:
    from integrations.slack_agent_dialogue.contract_v2 import build_parent_v2

    raw = raw_parent()
    value = build_parent_v2(raw)

    assert value == {
        **raw,
        "fingerprint": _expected_fingerprint(raw),
    }


def test_parent_v2_watch_and_operation_are_semantic_identity() -> None:
    from integrations.slack_agent_dialogue.contract_v2 import (
        TURN_WATCH_MODE_V1,
        build_parent_v2,
    )

    ordinary = build_parent_v2(raw_parent())
    clock_only = build_parent_v2(raw_parent(created_at="2026-08-27T13:00:01Z"))
    watched = build_parent_v2(raw_parent(watch_mode=TURN_WATCH_MODE_V1))
    other_operation = build_parent_v2(
        raw_parent(operation_key="worker-presence-dialogue-canary-20260827-002")
    )

    assert ordinary["fingerprint"] == clock_only["fingerprint"]
    assert ordinary["fingerprint"] != watched["fingerprint"]
    assert ordinary["fingerprint"] != other_operation["fingerprint"]


@pytest.mark.parametrize(
    "operation_key",
    [
        "",
        "short",
        "Worker-presence-dialogue",
        "worker presence dialogue",
        "_worker-presence-dialogue",
        "worker-presence-dialogue/",
        "a" * 129,
        "sk-" + "a" * 30,
    ],
)
def test_parent_v2_rejects_invalid_operation_keys(operation_key: str) -> None:
    from integrations.slack_agent_dialogue.contract_v2 import build_parent_v2

    with pytest.raises(DialogueContractError) as exc:
        build_parent_v2(raw_parent(operation_key=operation_key))
    assert exc.value.code == "PARENT_INVALID"


@pytest.mark.parametrize(
    "watch_mode",
    ["", "turn_watch_v2", "TURN_WATCH_V1", False, 1, []],
)
def test_parent_v2_rejects_unknown_watch_modes(watch_mode: object) -> None:
    from integrations.slack_agent_dialogue.contract_v2 import build_parent_v2

    with pytest.raises(DialogueContractError) as exc:
        build_parent_v2(raw_parent(watch_mode=watch_mode))
    assert exc.value.code == "PARENT_INVALID"


@pytest.mark.parametrize("mutation", ["extra", "missing", "prefingerprinted"])
def test_parent_v2_is_closed_and_builder_rejects_claimed_identity(mutation: str) -> None:
    from integrations.slack_agent_dialogue.contract_v2 import build_parent_v2

    raw = raw_parent()
    if mutation == "extra":
        raw["provider_account"] = "claude5"
    elif mutation == "missing":
        raw.pop("operation_key")
    else:
        raw["fingerprint"] = "c" * 64

    with pytest.raises(DialogueContractError) as exc:
        build_parent_v2(raw)
    assert exc.value.code == "PARENT_INVALID"


def test_parent_v2_validation_detects_changed_payload_under_fingerprint() -> None:
    from integrations.slack_agent_dialogue.contract_v2 import (
        build_parent_v2,
        validate_parent_v2,
    )

    value = build_parent_v2(raw_parent())
    value["operation_key"] = "worker-presence-dialogue-canary-20260827-002"

    with pytest.raises(DialogueContractError) as exc:
        validate_parent_v2(value)
    assert exc.value.code == "FINGERPRINT_MISMATCH"


def test_parent_v2_canonical_frame_round_trip_and_duplicate_refusal() -> None:
    from integrations.slack_agent_dialogue.contract_v2 import (
        PARENT_DISCRIMINATOR_V2,
        build_parent_v2,
        parse_parent_frame_v2,
        render_parent_v2,
    )

    value = build_parent_v2(raw_parent(watch_mode="turn_watch_v1"))
    assert parse_parent_frame_v2(render_parent_v2(value)) == value

    noncanonical = PARENT_DISCRIMINATOR_V2 + "\n" + json.dumps(
        value, sort_keys=True
    )
    with pytest.raises(DialogueContractError) as exc:
        parse_parent_frame_v2(noncanonical)
    assert exc.value.code == "FRAME_INVALID"

    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    duplicate = canonical[:-1] + ',"schema":"mastermind.agent_dialogue_parent.v2"}'
    with pytest.raises(DialogueContractError) as exc:
        parse_parent_frame_v2(PARENT_DISCRIMINATOR_V2 + "\n" + duplicate)
    assert exc.value.code == "FRAME_INVALID"


def test_v1_parent_remains_ordinary_and_has_no_watcher_semantics() -> None:
    raw_v1 = {
        "schema": PARENT_SCHEMA,
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "allowed_sol_user_ids": ["U0BRETDUAS2", "U0BSB73JWNL"],
        "created_at": "2026-08-27T13:00:00Z",
    }
    value = build_parent(raw_v1)
    assert parse_parent_frame(render_parent(value)) == value

    widened = copy.deepcopy(raw_v1)
    widened["watch_mode"] = "turn_watch_v1"
    with pytest.raises(DialogueContractError):
        build_parent(widened)
