"""control_plane.chairman_control_room — Chairman Control Room P0 Wave A(.1) tests.

``mastermind.chairman_control_room.v1`` is a deterministic, read-only
projection over six already-independent sources: the Agent OS brief (via the
CEO boot packet), the Executive Inbox, Macro's compiled active-build
snapshot, Macro's compiled ``agent_os_state.v1`` artifact, runtime jobs read
via public executive_runtime/executive_inbox APIs, and the local
surface-bindings navigation cache.  The last three (``agent_os_state``,
``runtime_jobs``, and the PR file-path join) are the Wave A.1 amendment
adjudicated on top of the original Wave A commission.  These tests prove the
properties the architecture doc (research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_
P0_ARCHITECTURE_AND_FABLE00_COMMISSION_2026-08-21.md §7/§10/§11/§22) demands:

  5. missing bindings is NOT degradation
  6. duplicate bindings surface a visible conflict, no winner
  8. a similar-but-different workstream key never fuzzy-joins
  9. PR joins are exact, word-boundary WS: tokens only (title AND, Wave A.1,
     exact workstream-file / handoff-file-prefix citations)
 10-12. each source's absence degrades by name without erasing the others
 13. determinism, including under shuffled input list order
 14. attention items pass through unmodified
 15. zero I/O in the pure compositor; zero filesystem writes in the gather
     layer over fixture-fed sources
 16. disagreements are preserved, never resolved (including, Wave A.1, an
     agent_os_state-vs-brief-readiness disagreement)

Wave A.1 additions: ``agent_os_state=None`` degrades by name without erasing
other-source cards; ``runtime_jobs=None`` degrades by name while
attention-derived jobs still show (this closes the acceptance-row-3
suppressed-healthy-job blindness the other direction: ``runtime_jobs``
present surfaces a job the inbox itself suppressed); PR file-path join
exactness (``WS-XY.md`` never joins ``WS:X``; a handoff-file prefix match
requires the full key before the hyphen).

Hermetic: ``compose_control_room`` tests build dicts directly (it is pure —
no I/O, no clock, no subprocess).  ``build_control_room`` tests monkeypatch
the collector functions it calls, so no real Macro checkout, Agent OS
subprocess, or Executive SQLite database is ever touched.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
from pathlib import Path

import pytest

from control_plane import chairman_control_room as ccr
from control_plane import executive_orchestration_principal as principal
from control_plane import executive_placement_selection as eps
from control_plane import executive_steward as es
from control_plane import surface_bindings as sb

_FIXTURES = Path(__file__).parent / "fixtures" / "chairman_control_room"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def boot_packet() -> dict:
    return _load("boot_packet_v1.json")


@pytest.fixture
def inbox() -> dict:
    return _load("executive_inbox_v2.json")


@pytest.fixture
def active_builds() -> dict:
    return _load("active_builds_v1.json")


@pytest.fixture
def agent_os_state() -> dict:
    return _load("agent_os_state_v1.json")


@pytest.fixture
def runtime_jobs() -> list:
    return _load("runtime_jobs_v1.json")


@pytest.fixture
def bindings() -> dict:
    return _load("bindings_v1.json")


def _compose(
    boot_packet, inbox, active_builds, bindings,
    *, agent_os_state=None, runtime_jobs=None, **overrides,
):
    kwargs = dict(
        inbox=inbox,
        boot_packet=boot_packet,
        active_builds=active_builds,
        agent_os_state=agent_os_state,
        runtime_jobs=runtime_jobs,
        bindings=bindings,
        binding_problems=(),
        generated_at="2026-08-21T00:10:00Z",
    )
    kwargs.update(overrides)
    return ccr.compose_control_room(**kwargs)


def _compose_full(boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings, **overrides):
    """Compose with every Wave A + Wave A.1 source present — the rich scenario."""
    return _compose(
        boot_packet, inbox, active_builds, bindings,
        agent_os_state=agent_os_state, runtime_jobs=runtime_jobs, **overrides,
    )


def _card(doc: dict, work_ref: str) -> dict:
    matches = [c for c in doc["work"] if c["work_ref"] == work_ref]
    assert len(matches) == 1, f"expected exactly one card for {work_ref}, got {matches}"
    return matches[0]


# ---------------------------------------------------------------------------
# schema pins + closed output contract
# ---------------------------------------------------------------------------


def test_schema_pin():
    assert ccr.SCHEMA == "mastermind.chairman_control_room.v1"


def test_output_keys_are_exactly_the_frozen_set(boot_packet, inbox, active_builds, bindings):
    doc = _compose(boot_packet, inbox, active_builds, bindings)
    assert set(doc.keys()) == {
        "schema", "generated_at", "sources", "degraded", "attention", "work",
        "unjoined_open_prs", "unbound_surfaces", "binding_conflicts",
        "placement_selection",
    }
    # No facts document was supplied (the common case) -> no section, no
    # degraded entry named for it (CAP-C1).
    assert doc["placement_selection"] is None
    assert not any(entry.startswith("placement_selection:") for entry in doc["degraded"])
    assert set(doc["sources"].keys()) == {
        "mastermind_sha", "mastermind_branch", "macro_sha", "macro_root",
        "executive_inbox_schema", "agent_os_brief_schema",
        "agent_os_state_schema", "agent_os_state_generated_at",
        "active_builds_schema", "active_builds_collected_at",
        "runtime_db_present", "bindings_path_present",
    }


def test_no_overall_or_combined_status_field_anywhere(boot_packet, inbox, active_builds, bindings):
    doc = _compose(boot_packet, inbox, active_builds, bindings)

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert "overall" not in str(key).lower(), key
                assert "combined" not in str(key).lower(), key
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(doc)


# ---------------------------------------------------------------------------
# regression — readiness container key is "records", NEVER "items"
# (Wave D production defect, 2026-08-22: "items" was compute_readiness()'s
# INTERNAL Python variable name in scripts/agentos.py, not the emitted JSON
# key. `python3 scripts/agentos.py brief --json --no-remember` against a
# fresh origin/main Macro checkout emits `readiness == {"schema":
# "agentos.readiness.v1", "degraded": [...], "records": [...341 rows
# live...]}`. The Wave A fixture encoded the wrong key too, so every test
# passed while production composed zero brief workstreams. These two tests
# pin the PUBLISHED contract, not the legacy guess, in both directions.)
# ---------------------------------------------------------------------------


def _minimal_boot_packet_with_readiness(readiness: dict) -> dict:
    return {
        "schema": ccr.BOOT_PACKET_SCHEMA,
        "mastermind": {"root": "/x", "sha": "a" * 40, "branch": "main"},
        "macro": {"root": "/y", "sha": "b" * 40},
        "degraded": [],
        "brief": {
            "schema": ccr.AGENT_OS_BRIEF_SCHEMA,
            "readiness": readiness,
            "blocked": [], "finished": [], "needs_ceo": [],
        },
    }


_LIVE_SHAPE_RECORD = {
    "workstream": "LIVE-KEY", "wave": None, "state": "blocked",
    "reason_code": "workstream_blocked",
    "reason": "Authored workstream status is blocked.",
    "depends_on": [], "unmet_dependencies": [],
    "source": "agentos/workstreams/WS-LIVE-KEY.md",
}


def test_readiness_records_is_the_published_contract():
    """A fixture whose readiness carries ONLY ``records`` (no ``items`` key
    anywhere) yields a non-empty brief-sourced workstream set — the real,
    live-verified shape.
    """
    boot_packet = _minimal_boot_packet_with_readiness({
        "schema": "agentos.readiness.v1",
        "degraded": [],
        "records": [_LIVE_SHAPE_RECORD],
    })
    assert "items" not in boot_packet["brief"]["readiness"]

    doc = ccr.compose_control_room(
        inbox=None, boot_packet=boot_packet, active_builds=None,
        agent_os_state=None, runtime_jobs=None, bindings=None,
        generated_at="2026-08-21T00:00:00Z",
    )
    refs = {c["work_ref"] for c in doc["work"]}
    assert refs == {"WS:LIVE-KEY"}
    card = _card(doc, "WS:LIVE-KEY")
    assert card["agent_os"]["state"] == "blocked"


def test_readiness_items_alone_yields_zero_brief_workstreams():
    """The inverse falsifier: a document carrying ONLY the legacy ``items``
    key (no ``records`` anywhere) must NOT be read — pinning that this
    module follows the published contract, not the source-code guess that
    caused the Wave D defect.
    """
    boot_packet = _minimal_boot_packet_with_readiness({
        "schema": "agentos.readiness.v1",
        "degraded": [],
        "items": [_LIVE_SHAPE_RECORD],
    })
    assert "records" not in boot_packet["brief"]["readiness"]

    doc = ccr.compose_control_room(
        inbox=None, boot_packet=boot_packet, active_builds=None,
        agent_os_state=None, runtime_jobs=None, bindings=None,
        generated_at="2026-08-21T00:00:00Z",
    )
    # The brief itself was present and schema-valid (no "unavailable"/schema
    # mismatch degraded entry) — it just legitimately named zero
    # workstreams, because this module correctly did not read "items".
    assert not any(entry.startswith("boot_packet:") for entry in doc["degraded"])
    assert doc["work"] == []


# ---------------------------------------------------------------------------
# baseline shape (sanity for the richer falsifiers below)
# ---------------------------------------------------------------------------


def test_full_fixture_scenario_shape(boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings):
    doc = _compose_full(boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings)
    refs = {c["work_ref"] for c in doc["work"]}
    assert refs == {
        "WS:ALPHA-ONE", "WS:ALPHA-ONEX", "WS:BETA-TWO", "WS:GAMMA-THREE",
        "WS:DELTA-FOUR",  # minted purely from the agent_os_state artifact
    }
    assert doc["sources"]["agent_os_state_schema"] == ccr.AGENT_OS_STATE_SCHEMA
    assert doc["sources"]["agent_os_state_generated_at"] == "2026-08-21T00:04:00Z"

    alpha = _card(doc, "WS:ALPHA-ONE")
    # brief readiness overlay, unchanged from Wave A:
    assert alpha["agent_os"]["state"] == "in_progress"
    # agent_os_state artifact enrichment (Wave A.1), exact source key names:
    assert alpha["agent_os"]["title"] == "Alpha One Rollout"
    assert alpha["agent_os"]["status"] == "active"
    assert alpha["agent_os"]["program"] == "EXEC-OS"
    assert alpha["agent_os"]["next_action"] == "Get the CEO ruling on ship vs hold"
    # executive.jobs is the union of attention-derived (job-alpha-001, FAILED)
    # and runtime_jobs-derived (job-alpha-002, QUEUED — never an inbox
    # attention item, since queued jobs are suppressed there) job rows.
    assert alpha["executive"]["jobs"] == [
        {"job_id": "job-alpha-001", "status": "failed", "workstream": "WS:ALPHA-ONE"},
        {"job_id": "job-alpha-002", "status": "queued", "workstream": "WS:ALPHA-ONE"},
    ]
    assert alpha["executive"]["joined_by"] == "ceo_intent_provenance"
    assert alpha["attention_ids"] == ["eia-aaaaaaaaaaaa", "eia-bbbbbbbbbbbb"]
    assert len(alpha["bindings"]) == 2

    delta = _card(doc, "WS:DELTA-FOUR")
    assert delta["agent_os"] == {
        "workstream": "DELTA-FOUR",
        "title": "Delta Four (artifact-only workstream)",
        "status": "proposed",
        "program": "EXEC-OS",
        "next_action": "Kickoff wave 1",
        "state": None,
        "reason_code": None,
        "reason": None,
        "source": None,
        "depends_on": [],
        "unmet_dependencies": [],
    }
    assert delta["executive"] == {"jobs": [], "joined_by": None}
    assert delta["github"] == {"prs": []}

    gamma = _card(doc, "WS:GAMMA-THREE")
    assert gamma["agent_os"]["state"] == "ready"
    assert gamma["agent_os"]["status"] is None  # not in the agent_os_state fixture
    assert gamma["executive"] == {"jobs": [], "joined_by": None}
    assert gamma["github"] == {"prs": []}
    assert gamma["bindings"] == []
    assert gamma["disagreements"] == []

    assert doc["unjoined_open_prs"] == [
        {
            "repo": "mastermindx-market-intelligence/Mastermind",
            "number": 111,
            "url": "https://github.com/mastermindx-market-intelligence/Mastermind/pull/111",
            "title": "chore: unrelated cleanup, no workstream cited",
            "branch": "chore/cleanup",
            "draft": True,
            "merge_state": "CLEAN",
        }
    ]

    assert doc["unbound_surfaces"] == [{
        "binding_id": "33333333-3333-4333-8333-333333333333",
        "work_ref": "WS:ZETA-UNKNOWN",
        "role": "worker",
        "provider": "codex",
        "seat_ref": None,
        "locator_kind": "codex_session",
        "observed_at": "2026-08-21T00:02:00Z",
        "last_verified_at": "2026-08-21T00:03:00Z",
    }]


# ---------------------------------------------------------------------------
# falsifier 5 — missing bindings is not degradation
# ---------------------------------------------------------------------------


def test_falsifier_missing_bindings_is_not_degraded(boot_packet, inbox, active_builds):
    doc = _compose(boot_packet, inbox, active_builds, bindings=None, binding_problems=())
    assert doc["sources"]["bindings_path_present"] is False
    assert not any("surface_bindings" in entry for entry in doc["degraded"])
    assert doc["unbound_surfaces"] == []
    assert doc["binding_conflicts"] == []
    for card in doc["work"]:
        assert card["bindings"] == []


def test_falsifier_bindings_load_problems_do_degrade(boot_packet, inbox, active_builds):
    doc = _compose(
        boot_packet, inbox, active_builds, bindings=None,
        binding_problems=["surface_bindings.json: invalid JSON (boom)"],
    )
    assert any(
        entry.startswith("surface_bindings: ") for entry in doc["degraded"]
    ), doc["degraded"]


# ---------------------------------------------------------------------------
# falsifier 6 — duplicate bindings, no winner (compose-level)
# ---------------------------------------------------------------------------


def test_falsifier_duplicate_bindings_visible_conflict_both_listed(
    boot_packet, inbox, active_builds, bindings
):
    doc = _compose(boot_packet, inbox, active_builds, bindings)
    assert doc["binding_conflicts"] == [{
        "work_ref": "WS:ALPHA-ONE",
        "role": "ceo",
        "binding_ids": sorted([
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
        ]),
    }]
    alpha = _card(doc, "WS:ALPHA-ONE")
    ids = {b["binding_id"] for b in alpha["bindings"]}
    assert ids == {
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
    }


# ---------------------------------------------------------------------------
# falsifier 8 — similar-but-different workstream titles: no fuzzy join
# ---------------------------------------------------------------------------


def test_falsifier_similar_title_no_fuzzy_join(boot_packet, inbox, active_builds, bindings):
    doc = _compose(boot_packet, inbox, active_builds, bindings)
    alpha = _card(doc, "WS:ALPHA-ONE")
    alphax = _card(doc, "WS:ALPHA-ONEX")
    assert alpha["github"]["prs"] == []  # PR #112 cites ALPHA-ONEX, not ALPHA-ONE
    assert [pr["number"] for pr in alphax["github"]["prs"]] == [112]
    assert alphax["agent_os"] is None  # never in the brief; PR-only card


# ---------------------------------------------------------------------------
# falsifier 9 — exact, word-boundary WS: token join
# ---------------------------------------------------------------------------


def _minimal_active_builds(*pr_titles: str) -> dict:
    return {
        "schema": ccr.ACTIVE_BUILDS_SCHEMA,
        "collected_at": "2026-08-21T00:00:00Z",
        "repositories": [{
            "open_prs": [
                {
                    "repo": "org/repo", "number": i + 1,
                    "url": f"https://github.com/org/repo/pull/{i + 1}",
                    "title": title, "branch": f"b{i}", "draft": False,
                    "merge_state": "CLEAN",
                }
                for i, title in enumerate(pr_titles)
            ],
        }],
    }


def test_falsifier_ws_token_word_boundary_exact_match():
    active_builds = _minimal_active_builds(
        "fix WS:X full stop", "unrelated WS:XY change", "also AWS:X not a citation",
    )
    doc = ccr.compose_control_room(
        inbox=None, boot_packet=None, active_builds=active_builds, bindings=None,
        generated_at="2026-08-21T00:00:00Z",
    )
    refs = {c["work_ref"] for c in doc["work"]}
    assert "WS:X" in refs
    assert "WS:XY" in refs

    x_card = _card(doc, "WS:X")
    xy_card = _card(doc, "WS:XY")
    assert [pr["number"] for pr in x_card["github"]["prs"]] == [1]
    assert [pr["number"] for pr in xy_card["github"]["prs"]] == [2]
    # PR #3 ("also AWS:X ...") cites no WS: token at all (AWS:X is not a
    # word-boundary citation of WS:X) and so is unjoined, not a phantom
    # citation of WS:X.
    assert [pr["number"] for pr in doc["unjoined_open_prs"]] == [3]
    assert all(pr["number"] != 3 for pr in x_card["github"]["prs"])


def _pr_row(number: int, *, title: str = "no workstream cited", files=()) -> dict:
    return {
        "repo": "org/repo", "number": number,
        "url": f"https://github.com/org/repo/pull/{number}",
        "title": title, "branch": f"b{number}", "draft": False,
        "merge_state": "CLEAN", "files": list(files),
    }


def _active_builds_with_prs(*prs: dict) -> dict:
    return {
        "schema": ccr.ACTIVE_BUILDS_SCHEMA,
        "collected_at": "2026-08-21T00:00:00Z",
        "repositories": [{"open_prs": list(prs)}],
    }


def test_falsifier_workstream_file_join_exact_key_no_join_on_similar_key():
    """agentos/workstreams/WS-XY.md joins WS:XY, never WS:X (Wave A.1)."""
    pr1 = _pr_row(1, files=["agentos/workstreams/WS-X.md"])
    pr2 = _pr_row(2, files=["agentos/workstreams/WS-XY.md"])
    active_builds = _active_builds_with_prs(pr1, pr2)

    doc = ccr.compose_control_room(
        inbox=None, boot_packet=None, active_builds=active_builds, bindings=None,
        generated_at="2026-08-21T00:00:00Z",
    )
    refs = {c["work_ref"] for c in doc["work"]}
    assert {"WS:X", "WS:XY"} <= refs

    x_card = _card(doc, "WS:X")
    xy_card = _card(doc, "WS:XY")
    assert [pr["number"] for pr in x_card["github"]["prs"]] == [1]
    assert [pr["number"] for pr in xy_card["github"]["prs"]] == [2]
    assert doc["unjoined_open_prs"] == []


def test_falsifier_handoff_file_join_requires_full_key_before_hyphen():
    """agentos/handoffs/<KEY>- must match the FULL candidate key (Wave A.1).

    A candidate key "X" (minted from a title token on PR #1) must NOT be
    joined by PR #2's handoff citation "agentos/handoffs/XY-2026-08-21.md" —
    "XY-..." does not start with "X-".  PR #3's handoff citation
    "agentos/handoffs/X-2026-08-21.md" DOES start with "X-" and joins.
    Handoff citations can only attach to an existing candidate key — they
    never mint a new card on their own (PR #2's own citation mints WS:XY
    only because #2 ALSO carries the workstream-file citation, added purely
    to prove #2 exists as a card and its handoff file still does not leak
    into WS:X).
    """
    pr1 = _pr_row(1, title="fix WS:X full stop")
    pr2 = _pr_row(2, files=[
        "agentos/workstreams/WS-XY.md",
        "agentos/handoffs/XY-2026-08-21.md",
    ])
    pr3 = _pr_row(3, files=["agentos/handoffs/X-2026-08-21.md"])
    active_builds = _active_builds_with_prs(pr1, pr2, pr3)

    doc = ccr.compose_control_room(
        inbox=None, boot_packet=None, active_builds=active_builds, bindings=None,
        generated_at="2026-08-21T00:00:00Z",
    )
    x_card = _card(doc, "WS:X")
    xy_card = _card(doc, "WS:XY")
    assert {pr["number"] for pr in x_card["github"]["prs"]} == {1, 3}
    assert {pr["number"] for pr in xy_card["github"]["prs"]} == {2}
    assert doc["unjoined_open_prs"] == []


def test_falsifier_handoff_citation_alone_never_mints_a_card():
    """A handoff-file citation for a key nobody else mentions stays unjoined."""
    pr1 = _pr_row(1, files=["agentos/handoffs/GHOST-KEY-2026-08-21.md"])
    active_builds = _active_builds_with_prs(pr1)

    doc = ccr.compose_control_room(
        inbox=None, boot_packet=None, active_builds=active_builds, bindings=None,
        generated_at="2026-08-21T00:00:00Z",
    )
    assert doc["work"] == []
    assert [pr["number"] for pr in doc["unjoined_open_prs"]] == [1]


# ---------------------------------------------------------------------------
# falsifiers 10-12 — per-source absence degrades by name, others survive
# ---------------------------------------------------------------------------


def test_falsifier_inbox_none_degrades_named_not_zero_workstreams(
    boot_packet, active_builds, bindings
):
    doc = _compose(boot_packet, None, active_builds, bindings)
    assert any(entry.startswith("executive_inbox: unavailable") for entry in doc["degraded"])
    assert doc["attention"] == {"chairman": [], "ceo": [], "coo": []}
    # Cards from Agent OS / GitHub still exist.
    refs = {c["work_ref"] for c in doc["work"]}
    assert "WS:ALPHA-ONE" in refs
    assert "WS:BETA-TWO" in refs
    alpha = _card(doc, "WS:ALPHA-ONE")
    assert alpha["executive"] == {"jobs": [], "joined_by": None}
    assert alpha["attention_ids"] == []


def test_falsifier_boot_packet_none_degrades_named_cards_survive(
    inbox, active_builds, bindings
):
    doc = _compose(None, inbox, active_builds, bindings)
    assert any(entry.startswith("boot_packet: unavailable") for entry in doc["degraded"])
    refs = {c["work_ref"] for c in doc["work"]}
    # No Agent OS brief at all -> no agent_os-sourced cards, but the
    # executive-joined and GitHub-joined cards still exist.
    assert "WS:ALPHA-ONE" in refs  # from the runtime job's provenance workstream
    assert "WS:ALPHA-ONEX" in refs  # from the PR token
    assert "WS:BETA-TWO" in refs  # from the PR token (#110 cites WS:BETA-TWO)
    for card in doc["work"]:
        assert card["agent_os"] is None


def test_falsifier_active_builds_none_no_completion_or_status_change(
    boot_packet, inbox, bindings
):
    with_builds = _compose(boot_packet, inbox, _load_active_builds(), bindings)
    without_builds = _compose(boot_packet, inbox, None, bindings)

    assert any(entry.startswith("active_builds: unavailable") for entry in without_builds["degraded"])

    by_ref_with = {c["work_ref"]: c for c in with_builds["work"]}
    by_ref_without = {c["work_ref"]: c for c in without_builds["work"]}

    # Cards that do not depend on active_builds for their existence
    # (agent_os- or executive-sourced) still exist, and their agent_os /
    # executive subtrees are byte-identical whether or not active_builds
    # was available — active_builds' absence changes github/disagreements
    # only, never a completion or status fact from another source.
    for ref in ("WS:ALPHA-ONE", "WS:BETA-TWO", "WS:GAMMA-THREE"):
        assert ref in by_ref_with and ref in by_ref_without
        assert by_ref_with[ref]["agent_os"] == by_ref_without[ref]["agent_os"]
        assert by_ref_with[ref]["executive"] == by_ref_without[ref]["executive"]

    assert without_builds["unjoined_open_prs"] == []
    for card in without_builds["work"]:
        assert card["github"] == {"prs": []}


def _load_active_builds() -> dict:
    return _load("active_builds_v1.json")


def test_falsifier_agent_os_state_none_degrades_named_not_zero_workstreams(
    boot_packet, inbox, active_builds, runtime_jobs, bindings
):
    """Wave A.1: agent_os_state=None degrades by name; other-source cards unaffected."""
    with_state = _compose(
        boot_packet, inbox, active_builds, bindings,
        agent_os_state=_load("agent_os_state_v1.json"), runtime_jobs=runtime_jobs,
    )
    without_state = _compose(
        boot_packet, inbox, active_builds, bindings,
        agent_os_state=None, runtime_jobs=runtime_jobs,
    )

    assert any(
        entry.startswith("agent_os_state: unavailable") for entry in without_state["degraded"]
    )
    # The artifact-only card disappears (nothing else names it)...
    refs_without = {c["work_ref"] for c in without_state["work"]}
    assert "WS:DELTA-FOUR" not in refs_without
    # ...but every card another source names is still there, NOT a
    # zero-workstreams claim.
    assert "WS:ALPHA-ONE" in refs_without
    assert "WS:BETA-TWO" in refs_without
    assert "WS:GAMMA-THREE" in refs_without

    # The brief-readiness half of agent_os survives untouched; only the
    # artifact-owned fields (title/status/program/next_action) go missing.
    alpha_with = _card(with_state, "WS:ALPHA-ONE")
    alpha_without = _card(without_state, "WS:ALPHA-ONE")
    assert alpha_with["agent_os"]["state"] == alpha_without["agent_os"]["state"]
    assert alpha_without["agent_os"]["status"] is None
    assert alpha_without["agent_os"]["program"] is None


def test_falsifier_runtime_jobs_none_degrades_named_attention_jobs_survive(
    boot_packet, inbox, active_builds, agent_os_state, bindings
):
    """Wave A.1: runtime_jobs=None degrades by name; attention-derived jobs still present."""
    doc = _compose(
        boot_packet, inbox, active_builds, bindings,
        agent_os_state=agent_os_state, runtime_jobs=None,
    )
    assert any(
        entry.startswith("executive_runtime: unavailable") for entry in doc["degraded"]
    )
    alpha = _card(doc, "WS:ALPHA-ONE")
    # job-alpha-001 comes from the Executive Inbox attention item and does
    # NOT depend on runtime_jobs at all.
    assert alpha["executive"]["jobs"] == [
        {"job_id": "job-alpha-001", "status": "failed", "workstream": "WS:ALPHA-ONE"}
    ]
    assert alpha["executive"]["joined_by"] == "ceo_intent_provenance"


# ---------------------------------------------------------------------------
# falsifier 13 — determinism, including under shuffled input list order
# ---------------------------------------------------------------------------


def test_falsifier_determinism_same_inputs(
    boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings
):
    doc_a = _compose_full(boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings)
    doc_b = _compose_full(
        copy.deepcopy(boot_packet), copy.deepcopy(inbox),
        copy.deepcopy(active_builds), copy.deepcopy(agent_os_state),
        copy.deepcopy(runtime_jobs), copy.deepcopy(bindings),
    )
    assert json.dumps(doc_a, sort_keys=True) == json.dumps(doc_b, sort_keys=True)


def test_falsifier_determinism_under_shuffled_input_order(
    boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings
):
    doc_a = _compose_full(boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings)

    shuffled_bindings = copy.deepcopy(bindings)
    shuffled_bindings["bindings"] = list(reversed(shuffled_bindings["bindings"]))

    shuffled_builds = copy.deepcopy(active_builds)
    shuffled_builds["repositories"][0]["open_prs"] = list(
        reversed(shuffled_builds["repositories"][0]["open_prs"])
    )

    shuffled_state = copy.deepcopy(agent_os_state)
    shuffled_state["workstreams"] = list(reversed(shuffled_state["workstreams"]))

    shuffled_runtime_jobs = list(reversed(copy.deepcopy(runtime_jobs)))

    doc_b = _compose_full(
        boot_packet, inbox, shuffled_builds, shuffled_state, shuffled_runtime_jobs,
        shuffled_bindings,
    )
    assert json.dumps(doc_a, sort_keys=True) == json.dumps(doc_b, sort_keys=True)


# ---------------------------------------------------------------------------
# falsifier 14 — attention items pass through unmodified
# ---------------------------------------------------------------------------


def test_falsifier_attention_passthrough_no_added_or_removed_keys(
    boot_packet, inbox, active_builds, bindings
):
    doc = _compose(boot_packet, inbox, active_builds, bindings)
    input_by_id = {item["attention_id"]: item for item in inbox["attention"]}

    seen = 0
    for target_items in doc["attention"].values():
        for item in target_items:
            seen += 1
            expected = input_by_id[item["attention_id"]]
            assert item == expected

    assert seen == len(inbox["attention"])
    assert doc["attention"]["ceo"][0]["attention_id"] == "eia-bbbbbbbbbbbb"
    assert doc["attention"]["coo"][0]["attention_id"] == "eia-aaaaaaaaaaaa"
    assert doc["attention"]["chairman"] == []


# ---------------------------------------------------------------------------
# falsifier 15 — no I/O in the compositor; no writes in the gather layer
# ---------------------------------------------------------------------------


def test_falsifier_compose_control_room_performs_no_io(
    boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings, monkeypatch
):
    def _boom(*args, **kwargs):
        raise AssertionError("compose_control_room must not perform file I/O")

    monkeypatch.setattr("builtins.open", _boom)
    monkeypatch.setattr(Path, "open", _boom)

    doc = _compose_full(boot_packet, inbox, active_builds, agent_os_state, runtime_jobs, bindings)
    assert doc["schema"] == ccr.SCHEMA


def _tree_snapshot(root: Path) -> set[tuple[str, int, float]]:
    snapshot = set()
    for path in root.rglob("*"):
        if path.is_file():
            stat_result = path.stat()
            snapshot.add((str(path.relative_to(root)), stat_result.st_size, stat_result.st_mtime))
    return snapshot


def test_falsifier_build_control_room_writes_nothing(
    tmp_path, monkeypatch, boot_packet, inbox, active_builds, agent_os_state, bindings
):
    macro_root = tmp_path / "macro"
    (macro_root / "data" / "governance").mkdir(parents=True)
    active_builds_path = macro_root / "data" / "governance" / "project_active_builds.json"
    active_builds_path.write_text(json.dumps(active_builds), encoding="utf-8")
    agent_os_state_path = macro_root / "data" / "governance" / "agent_os_state.json"
    agent_os_state_path.write_text(json.dumps(agent_os_state), encoding="utf-8")
    # Runtime DB deliberately absent: `_read_runtime_jobs` must degrade by
    # name rather than write/create anything (mirrors executive_inbox.py's
    # own existence-check-before-construction contract).

    bindings_path = tmp_path / "bindings" / "surface_bindings.json"
    sb.save_bindings(bindings, path=bindings_path)

    fixture_packet = copy.deepcopy(boot_packet)
    fixture_packet["macro"]["root"] = str(macro_root)

    fixture_inbox = copy.deepcopy(inbox)
    fixture_inbox["grounding"]["macro"]["root"] = str(macro_root)

    def _fake_build_packet(**kwargs):
        return fixture_packet

    def _fake_build_inbox(**kwargs):
        assert kwargs.get("boot_packet") == fixture_packet  # ONE subprocess proof
        return fixture_inbox

    monkeypatch.setattr(ccr.ceo_boot_packet, "build_packet", _fake_build_packet)
    monkeypatch.setattr(ccr.executive_inbox, "build_inbox", _fake_build_inbox)

    before = _tree_snapshot(tmp_path)
    doc = ccr.build_control_room(
        repo_root=tmp_path, now="2026-08-21T00:10:00Z", bindings_path=bindings_path,
    )
    after = _tree_snapshot(tmp_path)

    assert doc["schema"] == ccr.SCHEMA
    assert doc["sources"]["macro_root"] == str(macro_root)
    assert doc["sources"]["active_builds_schema"] == ccr.ACTIVE_BUILDS_SCHEMA
    assert doc["sources"]["agent_os_state_schema"] == ccr.AGENT_OS_STATE_SCHEMA
    assert doc["sources"]["bindings_path_present"] is True
    assert any(entry.startswith("executive_runtime: unavailable") for entry in doc["degraded"])
    assert before == after


# ---------------------------------------------------------------------------
# falsifier 16 — disagreement preservation
# ---------------------------------------------------------------------------


def test_falsifier_disagreement_preservation(boot_packet, inbox, active_builds, bindings):
    doc = _compose(boot_packet, inbox, active_builds, bindings)

    beta = _card(doc, "WS:BETA-TWO")
    assert beta["disagreements"] == [
        "agent_os reports this workstream readiness state=done while github "
        "lists 1 open PR(s) citing it"
    ]
    # Both raw source values are still present, unchanged, alongside the
    # disagreement note — never resolved, averaged, or overwritten.
    assert beta["agent_os"]["state"] == "done"
    assert [pr["number"] for pr in beta["github"]["prs"]] == [110]

    alpha = _card(doc, "WS:ALPHA-ONE")
    assert alpha["disagreements"] == [
        "executive reports 1 failed job(s) (job-alpha-001) for this workstream "
        "while agent_os reports readiness state=in_progress"
    ]
    assert alpha["agent_os"]["state"] == "in_progress"
    assert alpha["executive"]["jobs"][0]["status"] == "failed"


def test_falsifier_artifact_vs_brief_disagreement_preservation():
    """Wave A.1: the artifact's authored status and the live readiness state can

    themselves disagree (one is a materialized snapshot, the other live) —
    preserved as a disagreement, both raw values kept, never resolved.
    """
    boot_packet = {
        "schema": ccr.BOOT_PACKET_SCHEMA,
        "mastermind": {"root": "/x", "sha": "a" * 40, "branch": "main"},
        "macro": {"root": "/y", "sha": "b" * 40},
        "degraded": [],
        "brief": {
            "schema": ccr.AGENT_OS_BRIEF_SCHEMA,
            "readiness": {
                "schema": "agentos.readiness.v1",
                "degraded": [],
                "records": [{
                    "workstream": "ZETA-SIX", "wave": None, "state": "in_progress",
                    "reason_code": "status_in_progress",
                    "reason": "Authored workstream status is active.",
                    "depends_on": [], "unmet_dependencies": [],
                    "source": "agentos/workstreams/WS-ZETA-SIX.md",
                }],
            },
            "blocked": [], "finished": [], "needs_ceo": [],
        },
    }
    agent_os_state = {
        "schema": ccr.AGENT_OS_STATE_SCHEMA,
        "generated_at": "2026-08-21T00:00:00Z",
        "workstreams": [{
            "key": "ZETA-SIX", "title": "Zeta Six", "status": "done",
            "program": "P0-EXEC", "next_action": "",
        }],
    }

    doc = ccr.compose_control_room(
        inbox=None, boot_packet=boot_packet, active_builds=None,
        agent_os_state=agent_os_state, runtime_jobs=None, bindings=None,
        generated_at="2026-08-21T00:00:00Z",
    )
    card = _card(doc, "WS:ZETA-SIX")
    assert card["disagreements"] == [
        "agent_os_state reports status='done' while agent os readiness "
        "reports state='in_progress' for this workstream"
    ]
    # Both raw values survive unchanged alongside the disagreement note.
    assert card["agent_os"]["status"] == "done"
    assert card["agent_os"]["state"] == "in_progress"


# ---------------------------------------------------------------------------
# CAP-C1 — placement_selection (compose_control_room pure input)
# ---------------------------------------------------------------------------


def _placement_source(owner: es.SourceOwner, ref: str) -> es.SourceRef:
    return es.SourceRef(owner=owner, ref=ref, observed_at="2026-09-01T00:00:00Z", freshness=es.Freshness.CURRENT)


def _placement_responsibility(*, ref: str = "WS:CAP-C1", state: str | None = "waiting_capacity") -> es.ResponsibilityFact:
    return es.ResponsibilityFact(
        responsibility_ref=ref,
        title="Deterministic placement selection",
        accountable_seat=es.Seat.COO,
        state=state,
        root_job_id=None,
        source=_placement_source(es.SourceOwner.AGENT_OS, "agentos/workstreams/WS-CAP-C1.md"),
    )


def _placement_candidate(worker_id: str = "worker-1") -> eps.PlacementCandidateFact:
    return eps.PlacementCandidateFact(
        worker_id=worker_id,
        provider="acme",
        account_label="account1",
        quota_class="standard",
        capabilities=frozenset({"cap_a"}),
        observed_at_ms=1000,
        occupancy=eps.OccupancyState.FREE,
        occupancy_source=_placement_source(es.SourceOwner.RUNTIME_BINDING, f"binding-{worker_id}"),
        capacity_state=es.CapacityState.AVAILABLE,
        capacity_source=_placement_source(es.SourceOwner.CAPACITY, f"capacity-{worker_id}"),
        host_source_closure_proven=True,
        closure_source=_placement_source(es.SourceOwner.CAPACITY, f"closure-{worker_id}"),
        effect_state=es.EffectState.NONE,
        # Mode wave: a fresh lane whose creation bools are both True.
        mode=eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
        creation_surface_accessible=True,
        session_creation_allowed=True,
    )


def _valid_placement_selection_wire_dict() -> dict:
    decision = eps.select_placement(
        responsibility=_placement_responsibility(),
        demand=eps.PlacementDemand(
            required_capabilities=frozenset({"cap_a"}), quota_class="standard", provider="acme",
            allowed_modes=frozenset({
                eps.PlacementMode.EXISTING_SESSION_REUSE, eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
            }),
        ),
        candidates=(_placement_candidate(),),
    )
    assert decision.state is eps.SelectionState.SELECTED
    return decision.to_dict()


def test_compose_control_room_renders_a_valid_placement_selection_section_verbatim(
    boot_packet, inbox, active_builds, bindings
):
    wire = _valid_placement_selection_wire_dict()
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=wire)
    assert doc["placement_selection"] == wire
    assert not any(entry.startswith("placement_selection:") for entry in doc["degraded"])


def test_compose_control_room_degrades_an_invalid_placement_selection_wire_dict(
    boot_packet, inbox, active_builds, bindings
):
    invalid = {"schema_version": eps.SELECTION_SCHEMA, "not_a_recognized_key": True}
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=invalid)
    assert doc["placement_selection"] is None
    assert any(entry.startswith("placement_selection:") for entry in doc["degraded"])
    # compose_control_room stays total — it degrades, it never raises.
    assert doc["schema"] == ccr.SCHEMA


def test_compose_control_room_never_raises_on_a_garbage_placement_selection_value(
    boot_packet, inbox, active_builds, bindings
):
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection="not even a mapping")
    assert doc["placement_selection"] is None
    assert any(entry.startswith("placement_selection:") for entry in doc["degraded"])


# ---------------------------------------------------------------------------
# CAP-C1 — placement_selection (build_control_room gather layer)
# ---------------------------------------------------------------------------


def _facts_document(*, responsibility_state: str = "waiting_capacity") -> dict:
    source = {
        "owner": "agent_os", "ref": "agentos/workstreams/WS-CAP-C1.md",
        "observed_at": "2026-09-01T00:00:00Z", "freshness": "current",
    }
    candidate_source = lambda owner, ref: {  # noqa: E731 — tiny local test helper
        "owner": owner, "ref": ref, "observed_at": "2026-09-01T00:00:00Z", "freshness": "current",
    }
    return {
        "responsibility": {
            "responsibility_ref": "WS:CAP-C1",
            "title": "Deterministic placement selection",
            "accountable_seat": "coo",
            "state": responsibility_state,
            "root_job_id": None,
            "source": source,
        },
        "demand": {
            "required_capabilities": ["cap_a"],
            "quota_class": "standard",
            "provider": "acme",
            "allowed_modes": ["existing_session_reuse", "new_session_materialization"],
        },
        "candidates": [
            {
                "worker_id": "worker-1",
                "provider": "acme",
                "account_label": "account1",
                "quota_class": "standard",
                "capabilities": ["cap_a"],
                "observed_at_ms": 1000,
                "occupancy": "free",
                "occupancy_source": candidate_source("runtime_binding", "binding-worker-1"),
                "capacity_state": "available",
                "capacity_source": candidate_source("capacity", "capacity-worker-1"),
                "host_source_closure_proven": True,
                "closure_source": candidate_source("capacity", "closure-worker-1"),
                "effect_state": "none",
                "mode": "new_session_materialization",
                "creation_surface_accessible": True,
                "session_creation_allowed": True,
            }
        ],
    }


def test_build_control_room_flows_a_valid_facts_document_to_a_selected_section(
    tmp_path, monkeypatch, boot_packet, inbox, active_builds, agent_os_state, bindings
):
    macro_root = tmp_path / "macro"
    (macro_root / "data" / "governance").mkdir(parents=True)
    (macro_root / "data" / "governance" / "project_active_builds.json").write_text(
        json.dumps(active_builds), encoding="utf-8"
    )
    (macro_root / "data" / "governance" / "agent_os_state.json").write_text(
        json.dumps(agent_os_state), encoding="utf-8"
    )

    bindings_path = tmp_path / "bindings" / "surface_bindings.json"
    sb.save_bindings(bindings, path=bindings_path)

    facts_path = tmp_path / "placement_facts.json"
    facts_path.write_text(json.dumps(_facts_document()), encoding="utf-8")

    fixture_packet = copy.deepcopy(boot_packet)
    fixture_packet["macro"]["root"] = str(macro_root)
    fixture_inbox = copy.deepcopy(inbox)
    fixture_inbox["grounding"]["macro"]["root"] = str(macro_root)

    monkeypatch.setattr(ccr.ceo_boot_packet, "build_packet", lambda **kwargs: fixture_packet)
    monkeypatch.setattr(
        ccr.executive_inbox, "build_inbox",
        lambda **kwargs: fixture_inbox,
    )

    doc = ccr.build_control_room(
        repo_root=tmp_path, now="2026-08-21T00:10:00Z", bindings_path=bindings_path,
        placement_selection_path=facts_path,
    )

    assert doc["placement_selection"] is not None
    assert doc["placement_selection"]["state"] == "selected"
    assert doc["placement_selection"]["selected"]["worker_id"] == "worker-1"
    # Mode wave discriminator 6: consumer disclosure — selected_mode flows
    # end-to-end from the facts document through to the composed section.
    assert doc["placement_selection"]["selected_mode"] == "new_session_materialization"
    assert doc["placement_selection"]["evidence"][0]["mode"] == "new_session_materialization"
    assert not any(entry.startswith("placement_selection:") for entry in doc["degraded"])


def test_build_control_room_names_a_malformed_facts_document_as_degraded(
    tmp_path, monkeypatch, boot_packet, inbox, active_builds, agent_os_state, bindings
):
    macro_root = tmp_path / "macro"
    (macro_root / "data" / "governance").mkdir(parents=True)
    (macro_root / "data" / "governance" / "project_active_builds.json").write_text(
        json.dumps(active_builds), encoding="utf-8"
    )
    (macro_root / "data" / "governance" / "agent_os_state.json").write_text(
        json.dumps(agent_os_state), encoding="utf-8"
    )

    bindings_path = tmp_path / "bindings" / "surface_bindings.json"
    sb.save_bindings(bindings, path=bindings_path)

    facts_path = tmp_path / "placement_facts.json"
    facts_path.write_text("{ not valid json", encoding="utf-8")

    fixture_packet = copy.deepcopy(boot_packet)
    fixture_packet["macro"]["root"] = str(macro_root)
    fixture_inbox = copy.deepcopy(inbox)
    fixture_inbox["grounding"]["macro"]["root"] = str(macro_root)

    monkeypatch.setattr(ccr.ceo_boot_packet, "build_packet", lambda **kwargs: fixture_packet)
    monkeypatch.setattr(
        ccr.executive_inbox, "build_inbox",
        lambda **kwargs: fixture_inbox,
    )

    doc = ccr.build_control_room(
        repo_root=tmp_path, now="2026-08-21T00:10:00Z", bindings_path=bindings_path,
        placement_selection_path=facts_path,
    )

    assert doc["placement_selection"] is None
    matching = [entry for entry in doc["degraded"] if entry.startswith("placement_selection:")]
    assert matching
    # gather layer never raises even on a broken facts document.
    assert doc["schema"] == ccr.SCHEMA
    # Reviewer m-7: the degraded row never embeds the raw facts-document
    # path or the exception text itself — only the exception CLASS name.
    assert str(facts_path) not in matching[0]
    assert "not valid json" not in matching[0]


def test_build_control_room_never_leaks_a_bad_wire_value_in_the_degraded_entry(
    tmp_path, monkeypatch, boot_packet, inbox, active_builds, agent_os_state, bindings
):
    """Reviewer m-7: a facts document whose exception message WOULD embed
    the caller-supplied value verbatim (a stdlib enum ``ValueError`` reads
    ``"'<value>' is not a valid <EnumName>"``) must still never surface
    that value through the ``degraded`` list — only the exception class.
    """
    macro_root = tmp_path / "macro"
    (macro_root / "data" / "governance").mkdir(parents=True)
    (macro_root / "data" / "governance" / "project_active_builds.json").write_text(
        json.dumps(active_builds), encoding="utf-8"
    )
    (macro_root / "data" / "governance" / "agent_os_state.json").write_text(
        json.dumps(agent_os_state), encoding="utf-8"
    )

    bindings_path = tmp_path / "bindings" / "surface_bindings.json"
    sb.save_bindings(bindings, path=bindings_path)

    facts = _facts_document()
    secret_marker = "TOTALLY_SECRET_OCCUPANCY_VALUE_XYZ"
    facts["candidates"][0]["occupancy"] = secret_marker
    facts_path = tmp_path / "placement_facts.json"
    facts_path.write_text(json.dumps(facts), encoding="utf-8")

    fixture_packet = copy.deepcopy(boot_packet)
    fixture_packet["macro"]["root"] = str(macro_root)
    fixture_inbox = copy.deepcopy(inbox)
    fixture_inbox["grounding"]["macro"]["root"] = str(macro_root)

    monkeypatch.setattr(ccr.ceo_boot_packet, "build_packet", lambda **kwargs: fixture_packet)
    monkeypatch.setattr(
        ccr.executive_inbox, "build_inbox",
        lambda **kwargs: fixture_inbox,
    )

    doc = ccr.build_control_room(
        repo_root=tmp_path, now="2026-08-21T00:10:00Z", bindings_path=bindings_path,
        placement_selection_path=facts_path,
    )

    assert doc["placement_selection"] is None
    matching = [entry for entry in doc["degraded"] if entry.startswith("placement_selection:")]
    assert matching
    blob = json.dumps(doc)
    assert secret_marker not in blob
    assert str(facts_path) not in matching[0]


def test_build_control_room_without_the_flag_composes_no_placement_selection(
    tmp_path, monkeypatch, boot_packet, inbox, active_builds, agent_os_state, bindings
):
    macro_root = tmp_path / "macro"
    (macro_root / "data" / "governance").mkdir(parents=True)
    (macro_root / "data" / "governance" / "project_active_builds.json").write_text(
        json.dumps(active_builds), encoding="utf-8"
    )
    (macro_root / "data" / "governance" / "agent_os_state.json").write_text(
        json.dumps(agent_os_state), encoding="utf-8"
    )

    bindings_path = tmp_path / "bindings" / "surface_bindings.json"
    sb.save_bindings(bindings, path=bindings_path)

    fixture_packet = copy.deepcopy(boot_packet)
    fixture_packet["macro"]["root"] = str(macro_root)
    fixture_inbox = copy.deepcopy(inbox)
    fixture_inbox["grounding"]["macro"]["root"] = str(macro_root)

    monkeypatch.setattr(ccr.ceo_boot_packet, "build_packet", lambda **kwargs: fixture_packet)
    monkeypatch.setattr(
        ccr.executive_inbox, "build_inbox",
        lambda **kwargs: fixture_inbox,
    )

    doc = ccr.build_control_room(
        repo_root=tmp_path, now="2026-08-21T00:10:00Z", bindings_path=bindings_path,
    )

    assert doc["placement_selection"] is None
    assert not any(entry.startswith("placement_selection:") for entry in doc["degraded"])


def test_compose_and_gather_degrade_by_name_when_selector_module_is_not_shipped(
    tmp_path, monkeypatch, boot_packet, inbox, active_builds, bindings
):
    """The extracted control-room-remote release stages an exact file
    allowlist (ops/control_room_remote/install.sh, an active-PR-held path)
    that need not include the optional CAP-C1 selector module.  This module
    must still import, compose a complete document, and degrade the
    placement section by name — never raise — when the selector is absent."""
    monkeypatch.setattr(ccr, "executive_placement_selection", None)

    wire = _valid_placement_selection_wire_dict()
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=wire)
    assert doc["placement_selection"] is None
    assert "placement_selection: unavailable (module not shipped)" in doc["degraded"]
    assert doc["schema"] == ccr.SCHEMA

    facts_path = tmp_path / "facts.json"
    facts_path.write_text("{}", encoding="utf-8")
    result, failure = ccr._read_placement_selection(facts_path)
    assert result is None
    assert failure == "unavailable (module not shipped)"
    assert str(facts_path) not in failure


def test_module_boots_with_both_selector_modules_absent_at_import_time(tmp_path):
    """Stronger than the monkeypatch test above: pin absence at IMPORT time.

    A meta-path finder blocks both optional modules the way a genuinely
    unshipped extracted release would (find_spec resolves to "not found"),
    then chairman_control_room is imported FRESH.  A future static
    ``from control_plane import executive_placement_selection`` re-added at
    the top of the module would make this test fail with ImportError —
    exactly the extracted-release regression class the optional import
    exists to prevent."""
    import importlib
    import sys

    blocked = {
        "control_plane.executive_placement_selection",
        "control_plane.executive_steward",
    }

    class _AbsenceFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname in blocked:
                raise ModuleNotFoundError(f"blocked for test: {fullname}")
            return None

    saved = {name: sys.modules.get(name) for name in blocked}
    saved["control_plane.chairman_control_room"] = sys.modules.get(
        "control_plane.chairman_control_room"
    )
    finder = _AbsenceFinder()
    sys.meta_path.insert(0, finder)
    for name in blocked:
        sys.modules.pop(name, None)
    sys.modules.pop("control_plane.chairman_control_room", None)
    try:
        fresh = importlib.import_module("control_plane.chairman_control_room")
        assert fresh.executive_placement_selection is None
        assert fresh.executive_steward is None
        facts_path = tmp_path / "facts.json"
        facts_path.write_text("{}", encoding="utf-8")
        result, failure = fresh._read_placement_selection(facts_path)
        assert result is None
        assert failure == "unavailable (module not shipped)"
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("control_plane.chairman_control_room", None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
            else:
                sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# CAP-C1 wire-integrity repair — the Control Room is the real consumer
#
# Review 5084378111 MAJOR 3: `validate_placement_selection`'s top-level
# exact-key error rendered `sorted(value)` — the CALLER's own key names —
# and `compose_control_room()` appends `str(exc)` verbatim to its
# Chairman-visible `degraded` list. These tests drive the REAL, unmodified
# `compose_control_room()`; nothing here stubs or monkeypatches the
# validator, so they prove the end-to-end product behaviour, not a unit
# contract.
# ---------------------------------------------------------------------------

#: Shaped like a credential so a leak is unmistakable in any output.
_SECRET_SHAPED_KEY = "AWS_SECRET_ACCESS_KEY_AKIAIOSFODNN7EXAMPLE"


def _placement_degraded(doc) -> list[str]:
    return [entry for entry in doc["degraded"] if entry.startswith("placement_selection:")]


def test_compose_never_echoes_a_secret_shaped_unknown_top_level_key(
    boot_packet, inbox, active_builds, bindings
):
    forged = dict(_valid_placement_selection_wire_dict())
    forged[_SECRET_SHAPED_KEY] = "s3cr3t-value"
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)

    assert doc["placement_selection"] is None
    assert _placement_degraded(doc)  # it DID degrade, by name
    # Zero echo anywhere in the Chairman-visible document — not just in the
    # degraded list: the key name, and the value it carried.
    rendered = json.dumps(doc, sort_keys=True)
    assert _SECRET_SHAPED_KEY not in rendered
    assert "s3cr3t-value" not in rendered
    assert "AKIAIOSFODNN7EXAMPLE" not in rendered
    # compose stays total.
    assert doc["schema"] == ccr.SCHEMA


def test_compose_degraded_reason_for_an_unknown_key_is_constant(
    boot_packet, inbox, active_builds, bindings
):
    """Two different caller-controlled key names must produce the IDENTICAL
    degraded reason — that is what "constant, field-only" means, and it is
    the property that makes an echo impossible rather than merely absent in
    one sample."""
    reasons = []
    for key in (_SECRET_SHAPED_KEY, "another_totally_different_caller_key"):
        forged = dict(_valid_placement_selection_wire_dict())
        forged[key] = "x"
        doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)
        reasons.append(_placement_degraded(doc))
    assert reasons[0] == reasons[1]
    assert reasons[0]


def test_compose_never_echoes_a_secret_shaped_type_name(
    boot_packet, inbox, active_builds, bindings
):
    class AKIAIOSFODNN7EXAMPLE:  # a caller-controlled type name
        pass

    doc = _compose(
        boot_packet, inbox, active_builds, bindings,
        placement_selection=AKIAIOSFODNN7EXAMPLE(),
    )
    assert doc["placement_selection"] is None
    assert _placement_degraded(doc)
    assert "AKIAIOSFODNN7EXAMPLE" not in json.dumps(doc, sort_keys=True)


def test_compose_refuses_a_forged_selection_naming_a_worker_it_never_observed(
    boot_packet, inbox, active_builds, bindings
):
    """The product-level statement of BLOCKER 1: a separately valid
    snapshot for worker B, stapled onto evidence about worker-1, must NOT
    reach the Chairman as a rendered selection."""
    forged = dict(_valid_placement_selection_wire_dict())
    assert [row["worker_id"] for row in forged["evidence"]] == ["worker-1"]
    forged["selected"] = principal.build_placement_snapshot(
        worker_id="worker-b", quota_class="standard", provider="acme",
        account_label="account1", observed_at_ms=1000,
    )
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)
    assert doc["placement_selection"] is None
    assert _placement_degraded(doc)
    # and the forged worker id never renders anywhere
    assert "worker-b" not in json.dumps(doc, sort_keys=True)


def test_compose_refuses_a_forged_selection_with_a_mismatched_mode(
    boot_packet, inbox, active_builds, bindings
):
    forged = dict(_valid_placement_selection_wire_dict())
    assert forged["selected_mode"] == "new_session_materialization"
    forged["selected_mode"] = "existing_session_reuse"
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)
    assert doc["placement_selection"] is None
    assert _placement_degraded(doc)


def test_compose_refuses_evidence_attributed_to_a_non_authoritative_owner(
    boot_packet, inbox, active_builds, bindings
):
    """The product-level statement of BLOCKER 2: occupancy re-attributed to
    Agent OS must not render as a Chairman-visible decision."""
    forged = _valid_placement_selection_wire_dict()
    forged["evidence"][0]["occupancy_source"]["owner"] = "agent_os"
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)
    assert doc["placement_selection"] is None
    assert _placement_degraded(doc)


def test_compose_still_renders_a_genuine_selection_verbatim_after_the_repair(
    boot_packet, inbox, active_builds, bindings
):
    """The repair must tighten forgeries WITHOUT narrowing a real decision:
    a genuine select_placement() output still renders byte-identically."""
    wire = _valid_placement_selection_wire_dict()
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=wire)
    assert doc["placement_selection"] == wire
    assert json.dumps(doc["placement_selection"], sort_keys=True) == json.dumps(wire, sort_keys=True)
    assert not _placement_degraded(doc)
    assert doc["placement_selection"]["selection_is_commitment"] is False


def test_compose_never_echoes_a_secret_shaped_key_nested_in_selected(
    boot_packet, inbox, active_builds, bindings
):
    """Found by the exact-head review of the first repair pass: fixing only
    the TOP-LEVEL key error left a sibling echo. `selected` is an equally
    caller-controlled sub-mapping, validated by
    `executive_orchestration_principal.validate_placement_snapshot`, whose
    closed-key error renders `sorted(value)` and whose
    `OrchestrationPrincipalError` is a ValueError — so it landed in
    Chairman-visible `degraded` verbatim."""
    secret = "AWS_SECRET_ACCESS_KEY_AKIA5EXAMPLE"
    token = "sk-ant-api03-LEAKED-TOKEN-TAIL"
    forged = dict(_valid_placement_selection_wire_dict())
    forged["selected"] = {secret: 1, token: 2}
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)

    assert doc["placement_selection"] is None
    assert _placement_degraded(doc)
    rendered = json.dumps(doc, sort_keys=True)
    assert secret not in rendered
    assert token not in rendered
    assert "AKIA5EXAMPLE" not in rendered
    assert doc["schema"] == ccr.SCHEMA


def test_compose_degraded_reason_for_a_bad_selected_snapshot_is_constant(
    boot_packet, inbox, active_builds, bindings
):
    reasons = []
    for keys in (
        {"AWS_SECRET_ACCESS_KEY_AKIA5EXAMPLE": 1},
        {"a_totally_different_caller_key": 1, "and_another": 2},
    ):
        forged = dict(_valid_placement_selection_wire_dict())
        forged["selected"] = keys
        doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)
        reasons.append(_placement_degraded(doc))
    assert reasons[0] == reasons[1]
    assert reasons[0]


# ---------------------------------------------------------------------------
# CAP-C1 provenance wave — forged decisions must not reach the Chairman
#
# The validator now recomputes each decision through the one canonical
# select_placement(). These drive the REAL, unmodified compose_control_room()
# to prove the product consequence: a decision the selector could not have
# produced renders NOTHING and degrades value-free.
# ---------------------------------------------------------------------------

def _two_candidate_selected_wire() -> dict:
    """A genuine SELECTED decision: worker-1 AVAILABLE beats worker-2 DEGRADED."""
    winner = _placement_candidate("worker-1")
    runner_up = dataclasses.replace(
        _placement_candidate("worker-2"), capacity_state=es.CapacityState.DEGRADED
    )
    decision = eps.select_placement(
        responsibility=_placement_responsibility(),
        demand=eps.PlacementDemand(
            required_capabilities=frozenset({"cap_a"}), quota_class="standard", provider="acme",
            allowed_modes=frozenset({
                eps.PlacementMode.EXISTING_SESSION_REUSE,
                eps.PlacementMode.NEW_SESSION_MATERIALIZATION,
            }),
        ),
        candidates=(winner, runner_up),
    )
    assert decision.state is eps.SelectionState.SELECTED
    payload = decision.to_dict()
    assert payload["selected"]["worker_id"] == "worker-1"
    return payload


def _forged(mutate) -> dict:
    payload = _two_candidate_selected_wire()
    mutate(payload)
    return payload


def _evidence_row_for(payload: dict, worker_id: str) -> dict:
    return [r for r in payload["evidence"] if r["worker_id"] == worker_id][0]


FORGERIES = {
    "snapshot_provider_unbound":
        lambda p: p["selected"].update(provider="attacker-cloud"),
    "snapshot_account_label_unbound":
        lambda p: p["selected"].update(account_label="victim-billing-account"),
    "snapshot_quota_class_unbound":
        lambda p: p["selected"].update(quota_class="unlimited"),
    "snapshot_observed_at_unbound":
        lambda p: p["selected"].update(observed_at_ms=999999999),
    "winner_evidence_says_occupied":
        lambda p: _evidence_row_for(p, "worker-1").update(occupancy="occupied"),
    "winner_evidence_capacity_unknown":
        lambda p: _evidence_row_for(p, "worker-1").update(capacity_state="unknown"),
    "winner_evidence_closure_unproven":
        lambda p: _evidence_row_for(p, "worker-1").update(host_source_closure_proven=False),
    "winner_evidence_effect_unknown":
        lambda p: _evidence_row_for(p, "worker-1").update(effect_state="effect_unknown"),
    "winner_evidence_stale_capacity_source":
        lambda p: _evidence_row_for(p, "worker-1")["capacity_source"].update(freshness="stale"),
    "forged_aggregate_state":
        lambda p: p.update(state="no_eligible_candidate", selected=None, selected_mode=None),
    "exclusion_reason_contradicts_evidence":
        lambda p: p.update(exclusions=[{"worker_id": "worker-2", "reason": "occupied"}]),
    "tie_across_unequal_ranks":
        lambda p: p.update(
            state="tie_abstained", selected=None, selected_mode=None,
            tied_worker_ids=["worker-1", "worker-2"],
        ),
    "demand_provider_swapped":
        lambda p: p["demand"].update(provider="other-cloud"),
    "demand_mode_narrowed":
        lambda p: p["demand"].update(allowed_modes=["existing_session_reuse"]),
    "responsibility_freshness_flipped":
        lambda p: p.update(responsibility_freshness="stale"),
}


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_compose_refuses_every_forged_decision_and_degrades_value_free(
    name, boot_packet, inbox, active_builds, bindings
):
    forged = _forged(FORGERIES[name])
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=forged)

    # nothing forged reaches the Chairman
    assert doc["placement_selection"] is None, name
    rows = _placement_degraded(doc)
    assert rows, name
    # the degraded reason is value-free: it names the failure, never the data
    for token in ("attacker-cloud", "victim-billing-account", "unlimited", "999999999"):
        assert token not in json.dumps(doc, sort_keys=True), (name, token)
    # compose stays total
    assert doc["schema"] == ccr.SCHEMA


def test_compose_forged_degraded_reasons_are_the_same_constant(
    boot_packet, inbox, active_builds, bindings
):
    """Two structurally different forgeries must degrade identically —
    otherwise the reason string is leaking which field was tampered with."""
    seen = set()
    for name in ("snapshot_provider_unbound", "snapshot_account_label_unbound"):
        doc = _compose(
            boot_packet, inbox, active_builds, bindings,
            placement_selection=_forged(FORGERIES[name]),
        )
        seen.add(tuple(_placement_degraded(doc)))
    assert len(seen) == 1


def test_compose_still_renders_a_genuine_two_candidate_selection_verbatim(
    boot_packet, inbox, active_builds, bindings
):
    wire = _two_candidate_selected_wire()
    doc = _compose(boot_packet, inbox, active_builds, bindings, placement_selection=wire)
    assert doc["placement_selection"] == wire
    assert not _placement_degraded(doc)
    assert doc["placement_selection"]["selection_is_commitment"] is False


# ---------------------------------------------------------------------------
# review 5086941171 BLOCKER 3 — cold vs warm live-cache placement parity
#
# `_compose_state_doc()` passes `placement_selection_path` into
# `ccr.build_control_room()`. Once the live active-build cache is populated
# it instead calls `_compose_with_live_active_builds()`, which gathered
# everything else but never read the placement facts and never passed a
# `placement_selection=` argument — so the SAME configured C1 input silently
# disappeared from /api/state, with no placement degradation either.
# ---------------------------------------------------------------------------

from scripts import chairman_control_room as server_mod  # noqa: E402


def _server_config(tmp_path, facts_path=None):
    return server_mod.ServerConfig(
        repo_root=tmp_path, macro_root=None, bindings_path=tmp_path / "bindings.json",
        token="t", origin="http://localhost", port=0,
        placement_selection_path=facts_path,
    )


def _stub_gather(monkeypatch, boot_packet, inbox, bindings):
    """Pin every gather call BOTH composition paths make, so a cold-vs-warm
    difference can only come from the placement seam itself."""
    monkeypatch.setattr(server_mod.ceo_boot_packet, "build_packet",
                        lambda **kw: boot_packet)
    monkeypatch.setattr(server_mod.executive_inbox, "build_inbox",
                        lambda **kw: inbox)
    monkeypatch.setattr(server_mod.ccr, "_read_agent_os_state", lambda root: (None, None))
    monkeypatch.setattr(server_mod.ccr, "_read_runtime_jobs", lambda root: (None, None))
    monkeypatch.setattr(server_mod.sb, "load_bindings", lambda path: (bindings, ()))


def _warm_doc(monkeypatch, tmp_path, facts_path, boot_packet, inbox, bindings, active_builds):
    _stub_gather(monkeypatch, boot_packet, inbox, bindings)
    config = _server_config(tmp_path, facts_path)
    return server_mod._compose_with_live_active_builds(
        config, active_builds, "2026-09-02T00:00:00Z",
    )


def _cold_doc(facts_path, boot_packet, inbox, bindings, active_builds):
    """The cold path's placement contract, expressed exactly as
    build_control_room() applies it."""
    placement, failure = ccr._read_placement_selection(facts_path)
    doc = ccr.compose_control_room(
        inbox=inbox, boot_packet=boot_packet, active_builds=active_builds,
        agent_os_state=None, runtime_jobs=None, bindings=bindings,
        binding_problems=(), generated_at="2026-09-02T00:00:00Z",
        placement_selection=placement,
    )
    if failure:
        doc = dict(doc)
        doc["degraded"] = sorted(list(doc["degraded"]) + [f"placement_selection: {failure}"])
    return doc


@pytest.mark.parametrize(
    "responsibility_state, expected_state",
    [
        ("waiting_capacity", "selected"),
    ],
)
def test_warm_cache_path_renders_the_same_placement_selection_as_cold(
    monkeypatch, tmp_path, boot_packet, inbox, active_builds, bindings,
    responsibility_state, expected_state,
):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(
        json.dumps(_facts_document(responsibility_state=responsibility_state)),
        encoding="utf-8",
    )
    warm = _warm_doc(monkeypatch, tmp_path, facts_path, boot_packet, inbox, bindings, active_builds)
    cold = _cold_doc(facts_path, boot_packet, inbox, bindings, active_builds)

    assert cold["placement_selection"] is not None
    assert cold["placement_selection"]["state"] == expected_state
    # THE parity assertion: a populated live cache must not drop the section
    assert warm["placement_selection"] == cold["placement_selection"]
    assert [d for d in warm["degraded"] if d.startswith("placement_selection:")] == \
           [d for d in cold["degraded"] if d.startswith("placement_selection:")]


def test_warm_cache_path_degrades_a_malformed_facts_document_like_cold(
    monkeypatch, tmp_path, boot_packet, inbox, active_builds, bindings,
):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text("{not json", encoding="utf-8")
    warm = _warm_doc(monkeypatch, tmp_path, facts_path, boot_packet, inbox, bindings, active_builds)
    cold = _cold_doc(facts_path, boot_packet, inbox, bindings, active_builds)

    assert warm["placement_selection"] is None
    warm_rows = [d for d in warm["degraded"] if d.startswith("placement_selection:")]
    cold_rows = [d for d in cold["degraded"] if d.startswith("placement_selection:")]
    assert warm_rows == cold_rows
    assert warm_rows, "a configured but unreadable facts document must degrade by name"
    # value-free: neither the path nor the file body may be echoed
    assert "not json" not in json.dumps(warm, sort_keys=True)
    assert str(facts_path) not in json.dumps(warm, sort_keys=True)


def test_warm_cache_path_composes_no_placement_section_when_unconfigured(
    monkeypatch, tmp_path, boot_packet, inbox, active_builds, bindings,
):
    """An unconfigured path stays a true no-op on BOTH paths — no section
    and no degraded row, so this repair cannot become a false alarm."""
    warm = _warm_doc(monkeypatch, tmp_path, None, boot_packet, inbox, bindings, active_builds)
    assert warm["placement_selection"] is None
    assert not [d for d in warm["degraded"] if d.startswith("placement_selection:")]


def test_server_config_placement_path_is_actually_read_by_the_warm_path(
    monkeypatch, tmp_path, boot_packet, inbox, active_builds, bindings,
):
    """Passthrough pin: dropping `config.placement_selection_path` from the
    warm seam, or hard-coding a state, must fail. The configured document
    yields `reconciliation_required` — a state no default could invent."""
    facts = _facts_document()
    facts["candidates"] = [facts["candidates"][0], dict(facts["candidates"][0])]
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts), encoding="utf-8")
    warm = _warm_doc(monkeypatch, tmp_path, facts_path, boot_packet, inbox, bindings, active_builds)
    assert warm["placement_selection"] is not None
    assert warm["placement_selection"]["state"] == "reconciliation_required"


# ---------------------------------------------------------------------------
# review 5086941171 BLOCKER 4 — selector present, steward absent
# ---------------------------------------------------------------------------

def test_module_boots_with_selector_present_but_steward_absent(tmp_path):
    """The ASYMMETRIC packaging case the existing regression never covered.

    `_optional_control_plane_module` caught `ModuleNotFoundError` only around
    `find_spec`. With the selector shipped and the steward absent, the
    selector's own spec resolves fine, `import_module` then runs the
    selector's static `from control_plane.executive_steward import ...`, and
    the unguarded `ModuleNotFoundError` aborts the whole
    `control_plane.chairman_control_room` import — a hard crash instead of
    the documented fail-closed degrade.
    """
    import importlib
    import sys

    blocked = {"control_plane.executive_steward"}
    dependent = "control_plane.executive_placement_selection"

    class _AbsenceFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname in blocked:
                raise ModuleNotFoundError(f"blocked for test: {fullname}")
            return None

    names = blocked | {dependent, "control_plane.chairman_control_room"}
    saved = {name: sys.modules.get(name) for name in names}
    finder = _AbsenceFinder()
    sys.meta_path.insert(0, finder)
    for name in names:
        sys.modules.pop(name, None)
    try:
        fresh = importlib.import_module("control_plane.chairman_control_room")
        # fail CLOSED — both optional names absent, no crash
        assert fresh.executive_steward is None
        assert fresh.executive_placement_selection is None
        facts_path = tmp_path / "facts.json"
        facts_path.write_text("{}", encoding="utf-8")
        result, failure = fresh._read_placement_selection(facts_path)
        assert result is None
        assert failure == "unavailable (module not shipped)"
    finally:
        sys.meta_path.remove(finder)
        for name in names:
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
        importlib.import_module("control_plane.chairman_control_room")
