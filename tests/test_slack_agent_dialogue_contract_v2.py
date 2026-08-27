from __future__ import annotations

import hashlib
import json

REPO = "mastermindx-market-intelligence/Mastermind"


def commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
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
    from integrations.slack_agent_dialogue.contract_v2 import (
        PARENT_SCHEMA_V2,
        build_parent_v2,
    )

    raw: dict[str, object] = {
        "schema": PARENT_SCHEMA_V2,
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "operation_key": "worker-presence-dialogue-canary-20260827-001",
        "watch_mode": None,
        "allowed_sol_user_ids": ["U0BRETDUAS2", "U0BSB73JWNL"],
        "created_at": "2026-08-27T13:00:00Z",
    }

    value = build_parent_v2(raw)

    assert value == {
        **raw,
        "fingerprint": _expected_fingerprint(raw),
    }
