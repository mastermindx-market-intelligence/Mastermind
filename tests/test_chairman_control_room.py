"""control_plane.chairman_control_room — Chairman Control Room P0 Wave A tests.

``mastermind.chairman_control_room.v1`` is a deterministic, read-only
projection over four already-independent sources (Agent OS brief via the CEO
boot packet, the Executive Inbox, Macro's compiled active-build snapshot, and
the local surface-bindings navigation cache).  These tests prove the
properties the architecture doc (research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_
P0_ARCHITECTURE_AND_FABLE00_COMMISSION_2026-08-21.md §7/§10/§11/§22) demands:

  5. missing bindings is NOT degradation
  6. duplicate bindings surface a visible conflict, no winner
  8. a similar-but-different workstream key never fuzzy-joins
  9. PR joins are exact, word-boundary WS: tokens only
 10-12. each source's absence degrades by name without erasing the others
 13. determinism, including under shuffled input list order
 14. attention items pass through unmodified
 15. zero I/O in the pure compositor; zero filesystem writes in the gather
     layer over fixture-fed sources
 16. disagreements are preserved, never resolved

Hermetic: ``compose_control_room`` tests build dicts directly (it is pure —
no I/O, no clock, no subprocess).  ``build_control_room`` tests monkeypatch
the three collector functions it calls, so no real Macro checkout, Agent OS
subprocess, or Executive SQLite database is ever touched.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from control_plane import chairman_control_room as ccr
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
def bindings() -> dict:
    return _load("bindings_v1.json")


def _compose(boot_packet, inbox, active_builds, bindings, **overrides):
    kwargs = dict(
        inbox=inbox,
        boot_packet=boot_packet,
        active_builds=active_builds,
        bindings=bindings,
        binding_problems=(),
        generated_at="2026-08-21T00:10:00Z",
    )
    kwargs.update(overrides)
    return ccr.compose_control_room(**kwargs)


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
# baseline shape (sanity for the richer falsifiers below)
# ---------------------------------------------------------------------------


def test_full_fixture_scenario_shape(boot_packet, inbox, active_builds, bindings):
    doc = _compose(boot_packet, inbox, active_builds, bindings)
    refs = {c["work_ref"] for c in doc["work"]}
    assert refs == {"WS:ALPHA-ONE", "WS:ALPHA-ONEX", "WS:BETA-TWO", "WS:GAMMA-THREE"}

    alpha = _card(doc, "WS:ALPHA-ONE")
    assert alpha["agent_os"]["state"] == "in_progress"
    assert alpha["agent_os"]["title"] == "Alpha One Rollout"
    assert alpha["executive"]["jobs"] == [
        {"job_id": "job-alpha-001", "status": "failed", "workstream": "WS:ALPHA-ONE"}
    ]
    assert alpha["executive"]["joined_by"] == "ceo_intent_provenance"
    assert alpha["attention_ids"] == ["eia-aaaaaaaaaaaa", "eia-bbbbbbbbbbbb"]
    assert len(alpha["bindings"]) == 2

    gamma = _card(doc, "WS:GAMMA-THREE")
    assert gamma["agent_os"]["state"] == "ready"
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


# ---------------------------------------------------------------------------
# falsifier 13 — determinism, including under shuffled input list order
# ---------------------------------------------------------------------------


def test_falsifier_determinism_same_inputs(boot_packet, inbox, active_builds, bindings):
    doc_a = _compose(boot_packet, inbox, active_builds, bindings)
    doc_b = _compose(
        copy.deepcopy(boot_packet), copy.deepcopy(inbox),
        copy.deepcopy(active_builds), copy.deepcopy(bindings),
    )
    assert json.dumps(doc_a, sort_keys=True) == json.dumps(doc_b, sort_keys=True)


def test_falsifier_determinism_under_shuffled_input_order(
    boot_packet, inbox, active_builds, bindings
):
    doc_a = _compose(boot_packet, inbox, active_builds, bindings)

    shuffled_bindings = copy.deepcopy(bindings)
    shuffled_bindings["bindings"] = list(reversed(shuffled_bindings["bindings"]))

    shuffled_builds = copy.deepcopy(active_builds)
    shuffled_builds["repositories"][0]["open_prs"] = list(
        reversed(shuffled_builds["repositories"][0]["open_prs"])
    )

    doc_b = _compose(boot_packet, inbox, shuffled_builds, shuffled_bindings)
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
    boot_packet, inbox, active_builds, bindings, monkeypatch
):
    def _boom(*args, **kwargs):
        raise AssertionError("compose_control_room must not perform file I/O")

    monkeypatch.setattr("builtins.open", _boom)
    monkeypatch.setattr(Path, "open", _boom)

    doc = _compose(boot_packet, inbox, active_builds, bindings)
    assert doc["schema"] == ccr.SCHEMA


def _tree_snapshot(root: Path) -> set[tuple[str, int, float]]:
    snapshot = set()
    for path in root.rglob("*"):
        if path.is_file():
            stat_result = path.stat()
            snapshot.add((str(path.relative_to(root)), stat_result.st_size, stat_result.st_mtime))
    return snapshot


def test_falsifier_build_control_room_writes_nothing(
    tmp_path, monkeypatch, boot_packet, inbox, active_builds, bindings
):
    macro_root = tmp_path / "macro"
    (macro_root / "data" / "governance").mkdir(parents=True)
    active_builds_path = macro_root / "data" / "governance" / "project_active_builds.json"
    active_builds_path.write_text(json.dumps(active_builds), encoding="utf-8")

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
    assert doc["sources"]["bindings_path_present"] is True
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
