"""Static regression pins for the Sol active-execution discipline.

These checks prove that the protected procedural contract is present and internally
coherent. They do not prove fresh-model behavior or production execution.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "docs" / "sol_skills"
ACTIVE = SKILLS / "ACTIVE_EXECUTION.md"
INDEX = SKILLS / "INDEX.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "missing skill frontmatter"
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def test_active_execution_skill_is_compatible_with_current_pack():
    text = _read(ACTIVE)
    meta = _frontmatter(text)
    assert meta == {
        "schema": "mastermind.sol_skillpack.v1",
        "skillpack_version": "1.0.1",
        "minimum_bootstrap_major": "1",
        "skill": "active_execution",
    }


def test_index_registers_active_execution_and_forward_motion_law():
    text = _read(INDEX)
    assert "### `ACTIVE_EXECUTION.md`" in text
    assert re.search(r"^23\.\s+Forward execution\.", text, re.MULTILINE)
    assert "MORE_WORK_EXISTS" in text


def test_final_response_gate_is_closed_vocabulary_and_more_work_cannot_finalize():
    text = _read(ACTIVE)
    for state in (
        "PROVEN_OUTCOME",
        "EXACT_HUMAN_GATE",
        "EFFECT_UNKNOWN",
        "ALL_SCOPED_LANES_BLOCKED",
        "PLATFORM_FAILURE",
        "DURABLE_EXECUTION_RUNNING",
        "MORE_WORK_EXISTS",
    ):
        assert state in text
    assert "If the truthful classification is `MORE_WORK_EXISTS`, **do not finalize**" in text


def test_non_delta_loop_forces_replan_before_third_artifact_cycle():
    text = _read(ACTIVE)
    assert "two consecutive material work cycles" in text
    assert "NO_DELTA_LOOP" in text
    assert "Do not produce a third equivalent" in text


def test_blocked_lane_does_not_end_turn_while_independent_work_exists():
    text = _read(ACTIVE)
    assert "Treat a blocker as lane-local first" in text
    assert "switch to it immediately and continue" in text
    assert "every materially useful in-scope lane is blocked" in text


def test_effect_unknown_is_terminal_only_when_no_safe_independent_lane_remains():
    text = _read(ACTIVE)
    assert "does not itself permit finalization while another useful lane is provably independent" in text
    assert "makes every remaining useful in-scope action" in text
    assert "independent of that uncertainty" in text


def test_tool_reprobe_requires_a_material_capability_reason():
    text = _read(ACTIVE)
    assert "discover the needed schema/capability once" in text
    assert "do not repeatedly rediscover the same failure" in text
    assert "connection/device/schema change" in text


def test_background_continuation_requires_a_real_durable_owner():
    text = _read(ACTIVE)
    assert "A ChatGPT reasoning turn is not a daemon" in text
    assert "Never claim work will continue in the background" in text
    assert "real external durable owner" in text


def test_procedure_rejects_a_duplicate_control_plane():
    text = _read(ACTIVE)
    assert "does **not** create a lifecycle, scheduler, retry engine, memory store, queue" in text
    assert "no new lifecycle, queue, retry, memory, permission, or control plane" in text
