"""Executive OS Phase 1D-A tests — the read-only CEO boot packet.

Covers:
  1. The packet's shape is exactly the nine declared keys, with the Agent OS
     ``ceo_brief.v1`` document embedded verbatim
  2. A missing Macro checkout degrades with warnings and STILL exits 0 (fail open)
  3. The bridge writes NOTHING into the Macro checkout — the whole fixture tree is
     hashed around a CLI run, and ``data/governance/.ceo_brief_last`` must not appear
     (which is the same thing as proving ``--no-remember`` was passed)
  4. ``next_recommended_act`` walks its fixed precedence, and a
     broken strategic state outranks a pending CEO ruling
  5. Two frozen-clock runs over the same store are byte-identical
  6. The text form always carries its headers, and never suppresses DEGRADED
  7. A brief whose schema is not ``ceo_brief.v1`` is embedded anyway and named in
     ``degraded`` — Agent OS owns that contract, this bridge only reports on it
  8. The macro-root ladder resolves flag > env > sibling > vendor and records why
     each rejected candidate was rejected

Hermetic: no network, no real Macro checkout, no PyYAML in the fixtures.  The Agent OS
CLI is replaced by a stdlib-only stub that carries the ``--no-remember`` trap.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from control_plane import ceo_boot_packet as mod
from control_plane import strategic_state as ss
from control_plane.ceo_boot_packet import (
    BRIEF_SCHEMA,
    ENV_MACRO_ROOT,
    HANDOFF_LIMIT,
    SCHEMA,
    build_packet,
    collect_handoffs,
    next_recommended_act,
    render_packet,
    resolve_macro_root,
)
from scripts.ceo_boot_packet import main as cli_main

_PACKET_KEYS = {
    "schema", "generated_at", "mastermind", "macro", "strategic_state",
    "brief", "handoffs", "degraded", "next_recommended_act",
}

#: Handoff records in the fixture store, plus one non-.md file that must be ignored.
_HANDOFF_FILES = (
    "WS-AGENT-OS-2026-08-10.md",
    "WS-AGENT-OS-2026-08-12.md",
    "WS-CN-LIMIT-ALPHA-2026-08-13.md",
    "WS-DRL-2026-08-09.md",
    "WS-ETF-PAGE-2026-08-11.md",
    "WS-GMI-THEME-2026-08-08.md",
    "NOTES.txt",
)

#: Filename order, descending, capped at HANDOFF_LIMIT.  NOT mtime order — the fixture
#: deliberately stamps the oldest record with the newest mtime (see make_macro_root).
_EXPECTED_HANDOFFS = [
    "WS-GMI-THEME-2026-08-08",
    "WS-ETF-PAGE-2026-08-11",
    "WS-DRL-2026-08-09",
    "WS-CN-LIMIT-ALPHA-2026-08-13",
    "WS-AGENT-OS-2026-08-12",
]

# A stdlib-only stand-in for Macro `scripts/agentos.py`.  It must not import yaml: the
# bridge shells out with `sys.executable`, and a fixture that needed third-party code
# would be testing the runner's site-packages instead of the bridge.
_AGENTOS_STUB = r'''#!/usr/bin/env python3
"""Test stub for Macro scripts/agentos.py (the `brief` subcommand only)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARGV = sys.argv[1:]

# THE TRAP.  The real cmd_brief records a check-in marker INSIDE the Macro checkout
# unless --no-remember is passed.  A bridge that forgets the flag writes here, and
# tests/test_ceo_boot_packet.py::test_no_write_into_macro_checkout catches it.
if "--no-remember" not in ARGV:
    mark = ROOT / "data" / "governance" / ".ceo_brief_last"
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text("checked-in\n", encoding="utf-8")

NOW = ARGV[ARGV.index("--now") + 1] if "--now" in ARGV else "2026-08-13T12:00:00Z"
LABEL = ARGV[ARGV.index("--since") + 1] if "--since" in ARGV else "24h"
WS = "agentos/workstreams"

sys.stdout.write(json.dumps({
    "schema": "__SCHEMA__",
    "generated_at": NOW,
    "since": "2026-08-12T12:00:00Z",
    "since_label": LABEL,
    "counts": {"total": 6, "active": 2, "awaiting_ci": 1, "blocked": 1,
               "done_in_window": 1},
    "inputs": {"active_builds_age_hours": 3.5, "worktrees": 11, "degraded": []},
    "needs_ceo": [{"workstream": "WS-CN-LIMIT-ALPHA",
                   "question": "Authorize the bulk limit-up backfill?",
                   "options": ["authorize", "defer"], "recommendation": "authorize",
                   "by_when": "2026-08-15", "blocks_waves": 2,
                   "source": WS + "/WS-CN-LIMIT-ALPHA.md"}],
    "blocked": [{"workstream": "WS-GMI-THEME-GRAPH", "title": "Theme graph W3",
                 "blocked_by": ["Sat 2026-08-15 scrape"], "record_stale_days": 2,
                 "source": WS + "/WS-GMI-THEME-GRAPH.md"}],
    "finished": [{"workstream": "WS-WATCHLIST-PORTFOLIO-CEO", "wave": "W0",
                  "title": "CEO revamp W0", "prs": [{"number": 5457, "state": "merged"}],
                  "done_at": "2026-08-12T18:00:00Z",
                  "source": WS + "/WS-WATCHLIST-PORTFOLIO-CEO.md"}],
    "running": {"active": 2, "awaiting_ci": 1, "awaiting_review": 0, "blocked": 1,
                "proposed": 2, "open_prs": 3, "stale_claims": 0,
                "claims_without_worktree": 0},
    "unblocked": [{"workstream": "WS-AGENT-OS", "wave": "W3",
                   "title": "Context compiler", "p0": "EXECUTIVE_OS",
                   "p0_active": True, "unblocks": 1, "claimed": False,
                   "next_action": "Draft the compile-context projection",
                   "source": WS + "/WS-AGENT-OS.md"}],
    "unblocked_scope": "ready waves with no open dependency",
    "warnings": [],
}, indent=2, sort_keys=True) + "\n")
'''


def make_macro_root(
    tmp_path: Path, *, name: str = "macro", schema: str = BRIEF_SCHEMA
) -> Path:
    """A minimal Macro checkout: an agentos/ store plus a stubbed agentos CLI."""
    root = tmp_path / name
    handoffs = root / "agentos" / "handoffs"
    handoffs.mkdir(parents=True)
    (root / "agentos" / "workstreams").mkdir(parents=True)
    (root / "agentos" / "workstreams" / ".gitkeep").write_text("", encoding="utf-8")
    for filename in _HANDOFF_FILES:
        (handoffs / filename).write_text(f"# {filename}\n", encoding="utf-8")

    # Invert mtime against filename order: the OLDEST record gets the NEWEST stamp.
    # A reader that sorted by mtime would put it first and fail _EXPECTED_HANDOFFS.
    oldest = handoffs / "WS-AGENT-OS-2026-08-10.md"
    os.utime(oldest, (4_000_000_000, 4_000_000_000))

    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "agentos.py").write_text(
        _AGENTOS_STUB.replace("__SCHEMA__", schema), encoding="utf-8"
    )
    return root


def snapshot_tree(root: Path) -> dict[str, str]:
    """sha256 of every file under `root`, keyed by relative path."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.fixture(autouse=True)
def _clear_strategic_cache():
    """The strategic-state reader caches per process; don't leak across tests."""
    ss._reset()
    yield
    ss._reset()


@pytest.fixture
def frozen_git(monkeypatch):
    """Pin the git probes so a non-repo tmp fixture cannot manufacture warnings."""
    monkeypatch.setattr(mod, "_git_sha", lambda path: "a" * 40)
    monkeypatch.setattr(mod, "_git_branch", lambda path: "master")


# ---------------------------------------------------------------------------
# 1. shape
# ---------------------------------------------------------------------------

def test_packet_shape_and_embedded_brief(tmp_path):
    macro = make_macro_root(tmp_path)
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z",
    )

    assert set(packet) == _PACKET_KEYS
    assert packet["schema"] == "mastermind.ceo_boot_packet.v1" == SCHEMA
    assert packet["generated_at"] == "2026-08-13T00:00:00Z"

    assert isinstance(packet["mastermind"], dict)
    assert isinstance(packet["mastermind"]["root"], str)
    assert packet["mastermind"]["sha"] is None or isinstance(
        packet["mastermind"]["sha"], str
    )
    assert packet["mastermind"]["branch"] is None or isinstance(
        packet["mastermind"]["branch"], str
    )

    assert packet["macro"]["root"] == os.fspath(macro)
    assert packet["macro"]["resolved_via"] == "flag"
    assert packet["macro"]["sha"] is None or isinstance(packet["macro"]["sha"], str)
    assert isinstance(packet["macro"]["candidates_tried"], list)
    assert packet["macro"]["candidates_tried"][0] == {
        "via": "flag", "path": os.fspath(macro), "usable": True, "reason": None,
    }

    assert isinstance(packet["strategic_state"], dict)
    assert packet["strategic_state"]["company_phase"]
    assert isinstance(packet["strategic_state"]["north_star"], list)
    assert isinstance(packet["strategic_state"]["p0"], list)
    assert set(packet["strategic_state"]["p0"][0]) == {
        "id", "department", "objective", "status"
    }
    # constraints project to a flat {name: level} mapping of strings
    constraints = packet["strategic_state"]["constraints"]
    assert isinstance(constraints, dict)
    assert all(isinstance(v, str) for v in constraints.values())
    assert constraints["duplicate_control_planes"] == "prohibited"

    # The Agent OS document is embedded verbatim, keys and all.
    brief = packet["brief"]
    assert isinstance(brief, dict)
    assert brief["schema"] == "ceo_brief.v1" == BRIEF_SCHEMA
    assert brief["counts"]["total"] == 6
    assert brief["needs_ceo"][0]["workstream"] == "WS-CN-LIMIT-ALPHA"
    # Its own degraded list stays NESTED — the packet displays, never re-derives.
    assert brief["inputs"]["degraded"] == []

    assert [h["name"] for h in packet["handoffs"]] == _EXPECTED_HANDOFFS
    assert len(packet["handoffs"]) == HANDOFF_LIMIT
    assert all(h["path"].startswith("agentos/handoffs/") for h in packet["handoffs"])
    assert not any(h["name"] == "NOTES" for h in packet["handoffs"])

    assert isinstance(packet["degraded"], list)
    assert all(isinstance(entry, str) for entry in packet["degraded"])
    assert isinstance(packet["next_recommended_act"], str)
    assert packet["next_recommended_act"].startswith("Rule on 1 pending CEO decision")


def test_since_is_passed_through_to_the_brief(tmp_path):
    macro = make_macro_root(tmp_path)
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z", since="7d",
    )
    assert packet["brief"]["since_label"] == "7d"
    assert packet["brief"]["generated_at"] == "2026-08-13T00:00:00Z"


# ---------------------------------------------------------------------------
# 2. degraded when the Macro checkout is missing — the fail-open proof
# ---------------------------------------------------------------------------

def test_missing_macro_root_degrades_and_still_exits_zero(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "nowhere"
    lonely = tmp_path / "lonely"          # no sibling "Macro Dashboard", no vendor/
    lonely.mkdir()

    packet = build_packet(
        repo_root=lonely, macro_root_flag=os.fspath(missing), environ={},
        now="2026-08-13T00:00:00Z",
    )

    assert packet["schema"] == SCHEMA
    assert packet["brief"] is None
    assert packet["macro"]["root"] is None
    assert packet["macro"]["sha"] is None
    assert packet["macro"]["resolved_via"] is None
    assert [c["via"] for c in packet["macro"]["candidates_tried"]] == [
        "flag", "sibling", "vendor",
    ]
    assert all(c["usable"] is False for c in packet["macro"]["candidates_tried"])
    assert packet["handoffs"] == []
    assert packet["degraded"]
    assert "no Agent OS store resolved" in packet["degraded"][0]
    assert packet["next_recommended_act"].startswith("Restore the Agent OS read path")

    # The CLI must still exit 0 and emit a whole, parseable packet.
    monkeypatch.setattr(mod, "_REPO_ROOT", lonely)
    monkeypatch.delenv(ENV_MACRO_ROOT, raising=False)
    assert cli_main(["--json", "--macro-root", os.fspath(missing),
                     "--now", "2026-08-13T00:00:00Z"]) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["schema"] == SCHEMA
    assert set(emitted) == _PACKET_KEYS
    assert emitted["brief"] is None
    assert emitted["degraded"]


# ---------------------------------------------------------------------------
# 3. no write path into the Macro checkout
# ---------------------------------------------------------------------------

def test_no_write_into_macro_checkout(tmp_path, monkeypatch, capsys):
    macro = make_macro_root(tmp_path)
    before = snapshot_tree(macro)
    assert before, "fixture is empty — the snapshot would pass vacuously"

    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    assert cli_main(["--macro-root", os.fspath(macro),
                     "--now", "2026-08-13T00:00:00Z"]) == 0
    capsys.readouterr()

    after = snapshot_tree(macro)
    assert after == before
    assert len(after) == len(before)
    # The check-in marker the real brief writes without --no-remember.  Its absence is
    # the flag's receipt: the stub creates it whenever the bridge omits --no-remember.
    assert not (macro / "data" / "governance" / ".ceo_brief_last").exists()
    assert not (macro / "data").exists()


# ---------------------------------------------------------------------------
# 4. the next_recommended_act ladder
# ---------------------------------------------------------------------------

_LADDER = [
    ("needs_ceo", {"needs_ceo": [{"workstream": "WS-A", "question": "Ship it?"}],
                   "blocked": [{"workstream": "WS-B", "blocked_by": ["x"]}],
                   "unblocked": [{"workstream": "WS-C", "wave": "W1"}]},
     "Rule on 1 pending CEO decision(s). First: WS:WS-A — Ship it?"),
    ("blocked", {"needs_ceo": [],
                 "blocked": [{"workstream": "WS-B", "blocked_by": ["scrape", "ruling"]}],
                 "unblocked": [{"workstream": "WS-C", "wave": "W1"}]},
     "Clear 1 blocked workstream(s). First: WS:WS-B (blocked by: scrape, ruling)"),
    ("blocked_unspecified", {"needs_ceo": [],
                             "blocked": [{"workstream": "WS-B", "blocked_by": []}],
                             "unblocked": []},
     "Clear 1 blocked workstream(s). First: WS:WS-B (blocked by: unspecified)"),
    ("legacy_unblocked_ignored", {"needs_ceo": [], "blocked": [],
                                  "unblocked": [{"workstream": "WS-C", "wave": "W2",
                                                 "title": "t", "next_action": "Draft the spec"}]},
     "Consult the canonical Improvement Agenda for the highest-priority next work."),
    ("legacy_unblocked_title_ignored", {"needs_ceo": [], "blocked": [],
                                        "unblocked": [{"workstream": "WS-C", "wave": "W2",
                                                       "title": "Cut the arc"}]},
     "Consult the canonical Improvement Agenda for the highest-priority next work."),
    ("quiet", {"needs_ceo": [], "blocked": [], "unblocked": []},
     "Consult the canonical Improvement Agenda for the highest-priority next work."),
]


@pytest.mark.parametrize("label,brief,expected", _LADDER, ids=[c[0] for c in _LADDER])
def test_next_act_ladder_through_build_packet(
    tmp_path, monkeypatch, label, brief, expected
):
    macro = make_macro_root(tmp_path)
    monkeypatch.setattr(mod, "collect_brief", lambda *a, **k: (dict(brief), []))
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z",
    )
    assert packet["next_recommended_act"] == expected


def test_unreadable_strategic_state_outranks_a_pending_ruling(tmp_path, monkeypatch):
    """Rung 1 beats rung 3: no objective set means no correct prioritization."""
    macro = make_macro_root(tmp_path)
    monkeypatch.setattr(
        mod, "load_strategic_summary",
        lambda: (None, "config/strategic_state.yml: missing required key(s): p0"),
    )
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z",
    )

    assert packet["strategic_state"] is None
    assert packet["brief"]["needs_ceo"], "a ruling IS pending — rung 3 was reachable"
    assert packet["next_recommended_act"].startswith("Repair config/strategic_state.yml")
    assert "missing required key(s): p0" in packet["next_recommended_act"]
    assert any("strategic state unreadable" in d for d in packet["degraded"])


def test_next_act_rung_two_names_the_first_degraded_entry():
    act = next_recommended_act({"company_phase": "X"}, None, None, ["store is gone"])
    assert act == (
        "Restore the Agent OS read path — store is gone. "
        "Sol has no organizational state until then."
    )


def test_legacy_unblocked_is_embedded_but_never_promoted_as_priority(
    tmp_path, frozen_git
):
    """Phase 2b retires the rival list while preserving old brief compatibility."""
    macro = make_macro_root(tmp_path)
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z",
    )

    assert packet["brief"]["unblocked"], "the legacy brief must remain embedded verbatim"
    rendered = render_packet(packet)
    assert "READY NEXT" not in rendered
    assert "Draft the compile-context projection" not in rendered
    final_act = next_recommended_act(
        packet["strategic_state"], None,
        {"needs_ceo": [], "blocked": [], "unblocked": packet["brief"]["unblocked"]},
        [],
    )
    assert "Improvement Agenda" in final_act
    assert "Start the top ready item" not in final_act


# ---------------------------------------------------------------------------
# 5. determinism
# ---------------------------------------------------------------------------

def test_frozen_clock_runs_are_byte_identical(tmp_path, monkeypatch, capsys):
    macro = make_macro_root(tmp_path)
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    argv = ["--json", "--macro-root", os.fspath(macro), "--now", "2026-08-13T00:00:00Z"]

    assert cli_main(argv) == 0
    first = capsys.readouterr().out
    assert cli_main(argv) == 0
    second = capsys.readouterr().out

    assert first == second
    assert json.loads(first)["generated_at"] == "2026-08-13T00:00:00Z"


# ---------------------------------------------------------------------------
# 6. text rendering
# ---------------------------------------------------------------------------

def test_text_render_carries_every_section(tmp_path, frozen_git):
    macro = make_macro_root(tmp_path)
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z",
    )
    assert packet["degraded"] == [], packet["degraded"]

    text = render_packet(packet)
    assert "CEO BOOT PACKET — 2026-08-13T00:00:00Z" in text
    assert "schema mastermind.ceo_boot_packet.v1" in text
    assert "STRATEGY — " in text
    assert "north star:" in text
    assert "AGENT OS — ceo_brief.v1 @" in text
    assert "WS-CN-LIMIT-ALPHA" in text
    assert "NEEDS CEO (1)" in text
    assert "BLOCKED (1)" in text
    assert "READY NEXT" not in text
    assert "Draft the compile-context projection" not in text
    assert "HANDOFFS (latest 5)" in text
    assert "NEXT RECOMMENDED ACT" in text
    assert "DEGRADED" not in text
    assert max(len(line) for line in text.splitlines()) <= 80


def test_text_render_never_suppresses_degraded(tmp_path):
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    packet = build_packet(
        repo_root=lonely, macro_root_flag=os.fspath(tmp_path / "nowhere"), environ={},
        now="2026-08-13T00:00:00Z",
    )
    text = render_packet(packet)
    assert "DEGRADED" in text
    assert "no Agent OS state — see DEGRADED" in text
    assert "HANDOFFS (latest 0)" in text
    assert "none on file" in text
    assert "NEXT RECOMMENDED ACT" in text


def test_text_render_surfaces_the_briefs_own_degraded_entries(tmp_path, monkeypatch):
    """Agent OS's own degradation is displayed, still nested, prefixed as its own."""
    macro = make_macro_root(tmp_path)
    monkeypatch.setattr(mod, "_git_sha", lambda path: "b" * 40)
    monkeypatch.setattr(mod, "_git_branch", lambda path: "master")
    monkeypatch.setattr(mod, "collect_brief", lambda *a, **k: (
        {"schema": BRIEF_SCHEMA, "generated_at": "2026-08-13T00:00:00Z",
         "since_label": "24h", "counts": {}, "needs_ceo": [], "blocked": [],
         "unblocked": [], "inputs": {"degraded": ["active_builds map is 31h stale"]}},
        [],
    ))
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z",
    )
    assert packet["degraded"] == []
    text = render_packet(packet)
    assert "⚠ DEGRADED (1)" in text
    assert "- brief: active_builds map is 31h stale" in text


# ---------------------------------------------------------------------------
# 7. brief schema mismatch
# ---------------------------------------------------------------------------

def test_unknown_brief_schema_is_embedded_and_named(tmp_path):
    macro = make_macro_root(tmp_path, schema="ceo_brief.v99")
    packet = build_packet(
        repo_root=tmp_path, macro_root_flag=os.fspath(macro), environ={},
        now="2026-08-13T00:00:00Z",
    )
    assert packet["brief"] is not None, "an unknown schema must not drop the document"
    assert packet["brief"]["schema"] == "ceo_brief.v99"
    assert packet["brief"]["counts"]["total"] == 6
    named = [d for d in packet["degraded"] if "ceo_brief.v99" in d]
    assert named, packet["degraded"]
    assert "embedded as-is" in named[0]


# ---------------------------------------------------------------------------
# 8. macro-root resolution ladder
# ---------------------------------------------------------------------------

def test_flag_outranks_env(tmp_path):
    env_root = make_macro_root(tmp_path, name="from_env")
    flag_root = make_macro_root(tmp_path, name="from_flag")

    resolved, via, candidates = resolve_macro_root(
        os.fspath(flag_root), {ENV_MACRO_ROOT: os.fspath(env_root)}, tmp_path
    )
    assert resolved == flag_root
    assert via == "flag"
    # The ladder stops at the first usable candidate; env was never reached.
    assert [c["via"] for c in candidates] == ["flag"]


def test_env_is_used_when_no_flag_is_given(tmp_path):
    env_root = make_macro_root(tmp_path, name="from_env")
    resolved, via, candidates = resolve_macro_root(
        None, {ENV_MACRO_ROOT: os.fspath(env_root)}, tmp_path
    )
    assert resolved == env_root
    assert via == "env"
    assert [c["via"] for c in candidates] == ["env"]


def test_unusable_candidates_are_recorded_with_reasons(tmp_path):
    absent = tmp_path / "absent"

    no_script = tmp_path / "no_script"
    (no_script / "agentos").mkdir(parents=True)

    no_store = tmp_path / "no_store"
    (no_store / "scripts").mkdir(parents=True)
    (no_store / "scripts" / "agentos.py").write_text("", encoding="utf-8")

    good = make_macro_root(tmp_path, name="good")

    # Stage them through the ladder: flag -> env -> sibling.  The sibling slot is
    # `<repo_root>/../Macro Dashboard`, so build a repo_root whose parent holds one.
    home = tmp_path / "home"
    (home / "sub").mkdir(parents=True)
    (home / "Macro Dashboard").symlink_to(good, target_is_directory=True)

    resolved, via, candidates = resolve_macro_root(
        os.fspath(absent), {ENV_MACRO_ROOT: os.fspath(no_script)}, home / "sub"
    )
    assert via == "sibling"
    assert resolved == home / "Macro Dashboard"
    assert [(c["via"], c["usable"], c["reason"]) for c in candidates] == [
        ("flag", False, "missing"),
        ("env", False, "no scripts/agentos.py"),
        ("sibling", True, None),
    ]

    # And the third rejection reason, on its own.
    _, via_none, only = resolve_macro_root(os.fspath(no_store), {}, tmp_path / "sub")
    assert via_none is None
    assert only[0] == {
        "via": "flag", "path": os.fspath(no_store), "usable": False,
        "reason": "no agentos/ store",
    }


def test_vendor_is_last_because_the_pin_is_stale_by_design(tmp_path):
    """`vendor/macro` is a pinned engine mirror; organizational state must be fresh."""
    repo = tmp_path / "home" / "mastermind"
    (repo / "vendor").mkdir(parents=True)
    vendor_target = make_macro_root(tmp_path, name="vendor_macro")
    (repo / "vendor" / "macro").symlink_to(vendor_target, target_is_directory=True)

    # No sibling: vendor is the only usable rung left.
    resolved, via, candidates = resolve_macro_root(None, {}, repo)
    assert via == "vendor"
    assert resolved == vendor_target.resolve()
    assert [c["via"] for c in candidates] == ["sibling", "vendor"]

    # Add a sibling and it must win, even though vendor still resolves.
    sibling = make_macro_root(tmp_path / "home", name="Macro Dashboard")
    resolved2, via2, _ = resolve_macro_root(None, {}, repo)
    assert via2 == "sibling"
    assert resolved2 == sibling


# ---------------------------------------------------------------------------
# handoff collection edge cases
# ---------------------------------------------------------------------------

def test_missing_handoffs_directory_warns_without_raising(tmp_path):
    root = tmp_path / "bare"
    (root / "agentos").mkdir(parents=True)
    handoffs, warning = collect_handoffs(root)
    assert handoffs == []
    assert warning and "handoffs" in warning


def test_empty_handoffs_directory_is_not_a_warning(tmp_path):
    root = tmp_path / "empty"
    (root / "agentos" / "handoffs").mkdir(parents=True)
    handoffs, warning = collect_handoffs(root)
    assert handoffs == []
    assert warning is None


# ---------------------------------------------------------------------------
# boundary: the module may not import anything that executes
# ---------------------------------------------------------------------------

def test_module_imports_no_execution_plane():
    """The read-only bridge stays decoupled from the worker/executive runtimes."""
    import ast

    source = Path(mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = {
        name for name in imported
        if name.startswith("control_plane.")
        and name != "control_plane.strategic_state"
    }
    assert not forbidden, f"read-only bridge must not import {sorted(forbidden)}"
