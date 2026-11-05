"""Regression: ``brief.inputs.degraded`` warnings must reach the executive Inbox.

The boot-packet renderer discloses ``brief.inputs.degraded``, but the Inbox
consumer read only the packet's top-level ``degraded`` — which does not carry
them — so every supply warning the collector recorded about its inputs vanished
before reaching an executive surface.  The four-warning packet below is the
actual source-bound minimal fixture (packet
ee1aeed54bc48724031fdbe5d6e1fdf340a5d97dc0040b85acb3dd3e323741cf): its
top-level ``degraded`` is empty while the nested list carries four live
disclosures.

Scope: focused consumer regression for the ``control_plane.executive_inbox``
fix.  Nested warnings must be disclosed verbatim, in source order, duplicates
kept; malformed shapes must be named (never stringified, never char-split);
optional-field absence must keep legacy fixtures byte-identical; no attention
id, row, count, or ordering may change; and nested warnings must survive even a
malformed ``needs_ceo``.  Tests import the real module normally; the incumbent
fixture suite remains authoritative in the parent tree.
"""

import copy
from types import SimpleNamespace

import control_plane.executive_inbox as inbox

GENERATED_AT = "2026-10-14T00:00:00Z"

# The exact four supplied strings from the source-bound minimal fixture,
# in fixture order.
FOUR_WARNINGS = [
    "active_builds.v1 open_prs is TRUNCATED at the gh --limit cap — some "
    "open PRs are missing from the join, so a wave may read 'unknown' while "
    "its PR is open",
    "active_builds.v1 merged window is TRUNCATED — a merged PR may read "
    "'unknown'",
    "uncommitted-work scan skipped over 0 worktrees (one `git status` each) "
    "— re-run with --scan-uncommitted for stranded work",
    "active_builds.v1 is 420h old — PR state predates the last nightly "
    "sweep",
]


def _four_warning_packet():
    """The actual minimal fixture packet, fresh per call."""
    return {
        "schema": "mastermind.ceo_boot_packet.v1",
        "degraded": [],
        "brief": {
            "schema": "ceo_brief.v1",
            "needs_ceo": [],
            "inputs": {
                "active_builds_age_hours": 419.7,
                "degraded": list(FOUR_WARNINGS),
                "worktrees": 0,
            },
        },
    }


def _needs_ceo_row(workstream, question):
    return {"workstream": workstream, "question": question}


def _runtime_projection(attention=()):
    return SimpleNamespace(
        attention=list(attention), degraded=[], counts={}, suppressed=[]
    )


def _compose(packet, attention=()):
    return inbox.compose_inbox(
        runtime_projection=_runtime_projection(attention),
        boot_packet=packet,
        mastermind_grounding={},
        runtime_grounding={},
        generated_at=GENERATED_AT,
    )


def test_four_warning_fixture_discloses_every_warning():
    """Regression (fails on the old source): all four nested warnings surface."""
    items, degraded = inbox.project_needs_ceo(_four_warning_packet())
    assert items == []
    assert degraded == [f"boot_packet: {warning}" for warning in FOUR_WARNINGS]


def test_compose_inbox_propagates_nested_warnings():
    """Regression (fails on the old source): the warnings reach the inbox."""
    result = _compose(_four_warning_packet())
    assert result["degraded"] == [
        f"boot_packet: {warning}" for warning in FOUR_WARNINGS
    ]
    assert result["grounding"]["boot_packet_schema"] == inbox.BOOT_PACKET_SCHEMA
    assert result["attention"] == []


def test_nested_warning_order_and_duplicates_preserved():
    """Regression (fails on the old source): no sort, no dedupe."""
    packet = _four_warning_packet()
    packet["brief"]["inputs"] = {
        "degraded": ["beta warning", "alpha warning", "beta warning"],
    }
    _, degraded = inbox.project_needs_ceo(packet)
    assert degraded == [
        "boot_packet: beta warning",
        "boot_packet: alpha warning",
        "boot_packet: beta warning",
    ]


def test_attention_identity_and_order_unchanged():
    """Compatibility: nested warnings must not move, rename, or re-id any row."""
    rows = [
        _needs_ceo_row("ws-alpha", "Ship the rollback now?"),
        _needs_ceo_row("ws-alpha", "Ship the rollback now?"),
        _needs_ceo_row("ws-beta", "Who owns the cut?"),
    ]
    with_inputs = _four_warning_packet()
    with_inputs["brief"]["needs_ceo"] = rows
    without_inputs = copy.deepcopy(with_inputs)
    del without_inputs["brief"]["inputs"]

    items_with, _ = inbox.project_needs_ceo(with_inputs)
    items_without, _ = inbox.project_needs_ceo(without_inputs)
    assert items_with == items_without
    assert [item["reason"] for item in items_with] == [
        "Ship the rollback now?",
        "Ship the rollback now?",
        "Who owns the cut?",
    ]
    assert [item["attention_id"] for item in items_with] == [
        inbox.attention_id(
            target="ceo",
            kind="ceo_decision_pending",
            source="agent_os",
            job_id=None,
            workstream=row["workstream"],
            reason=row["question"],
            ordinal=index,
        )
        for index, row in enumerate(rows)
    ]
    # Byte-identical rows are two rulings: the ordinal keeps both ids alive.
    assert len({item["attention_id"] for item in items_with}) == 3

    coo_item = {
        "target": "coo",
        "kind": "runtime_stalled",
        "source": "runtime",
        "job_id": "job-9",
        "workstream": None,
        "status": "running",
        "reason": "build stuck",
        "evidence": [],
        "existing_next_actions": [],
    }
    result = _compose(with_inputs, attention=[coo_item])
    assert [item["target"] for item in result["attention"]] == [
        "ceo", "ceo", "ceo", "coo",
    ]


def test_malformed_inputs_named_and_rows_survive():
    """Regression (fails on the old source): a non-object `inputs` is named."""
    packet = _four_warning_packet()
    packet["brief"]["inputs"] = "nightly sweep skipped"
    packet["brief"]["needs_ceo"] = [_needs_ceo_row("ws-alpha", "Proceed?")]
    items, degraded = inbox.project_needs_ceo(packet)
    assert degraded == [
        "boot packet brief inputs is a str, not an object; "
        "its degraded warnings were not read",
    ]
    assert [item["reason"] for item in items] == ["Proceed?"]


def test_non_list_nested_degraded_named_not_char_split():
    """Regression (fails on the old source): a string degraded is not iterated."""
    packet = _four_warning_packet()
    packet["brief"]["inputs"] = {"degraded": "supply truncated mid-join"}
    _, degraded = inbox.project_needs_ceo(packet)
    assert degraded == [
        "boot packet brief inputs degraded is a str, not a list; "
        "its warnings were not disclosed",
    ]
    # No per-character leak: every disclosed line is a sentence, not a char.
    assert all(len(entry) > 1 for entry in degraded)


def test_non_string_member_named_not_stringified():
    """Regression (fails on the old source): bad members named by index/type."""
    packet = _four_warning_packet()
    packet["brief"]["inputs"] = {"degraded": ["real warning", 42, None]}
    _, degraded = inbox.project_needs_ceo(packet)
    assert degraded == [
        "boot_packet: real warning",
        "boot packet brief inputs degraded[1] is a int, not a string; "
        "no warning disclosed from it",
        "boot packet brief inputs degraded[2] is a NoneType, not a string; "
        "no warning disclosed from it",
    ]
    assert "boot_packet: 42" not in degraded
    assert "boot_packet: None" not in degraded


def test_foreign_brief_schema_inputs_not_read():
    """Compatibility: a foreign brief's `inputs` stays unread, named once."""
    packet = _four_warning_packet()
    packet["brief"]["schema"] = "ceo_brief.v0"
    items, degraded = inbox.project_needs_ceo(packet)
    assert items == []
    assert degraded == [
        f"boot packet brief schema is {'ceo_brief.v0'!r}, "
        f"expected {inbox.BRIEF_SCHEMA!r} — not read; "
        f"CEO attention not projected",
    ]


def test_missing_inputs_preserves_legacy_shape():
    """Compatibility: no `inputs` at all keeps the legacy inbox byte-identical."""
    packet = _four_warning_packet()
    del packet["brief"]["inputs"]
    assert inbox.project_needs_ceo(packet) == ([], [])
    assert _compose(packet) == {
        "schema": inbox.SCHEMA,
        "generated_at": GENERATED_AT,
        "grounding": {
            "mastermind": {},
            "macro": {"root": None, "sha": None},
            "boot_packet_schema": inbox.BOOT_PACKET_SCHEMA,
            "runtime_db": {},
        },
        "attention": [],
        "runtime_counts": {},
        "suppressed": [],
        "degraded": [],
    }
    # An empty inputs object is equally silent.
    packet["brief"]["inputs"] = {}
    assert inbox.project_needs_ceo(packet) == ([], [])


def test_nested_warnings_survive_malformed_needs_ceo():
    """Regression (fails on the old source): bad rows never erase the warnings."""
    packet = _four_warning_packet()
    packet["brief"]["inputs"] = {"degraded": ["first warning", "second warning"]}
    packet["brief"]["needs_ceo"] = "nightly"
    items, degraded = inbox.project_needs_ceo(packet)
    assert items == []
    assert degraded == [
        "boot_packet: first warning",
        "boot_packet: second warning",
        "boot packet needs_ceo is a str, not a list; "
        "CEO attention not projected",
    ]


def test_top_level_packet_degraded_still_bubbled():
    """Regression (fails on the old source): both warning sources surface."""
    packet = _four_warning_packet()
    packet["degraded"] = ["packet-level trouble"]
    packet["brief"]["inputs"] = {"degraded": ["nested trouble"]}
    result = _compose(packet)
    assert result["degraded"] == [
        "boot_packet: packet-level trouble",
        "boot_packet: nested trouble",
    ]


def test_missing_brief_reads_nothing_nested():
    """Compatibility: `brief: null` keeps its legacy single diagnostic."""
    packet = _four_warning_packet()
    packet["brief"] = None
    items, degraded = inbox.project_needs_ceo(packet)
    assert items == []
    assert degraded == [
        "boot packet carries no Agent OS brief; CEO attention not projected",
    ]
