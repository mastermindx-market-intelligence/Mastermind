"""Source-only regression contract for substantial Web mission continuation.

These tests protect prompt/export consistency and safety wording. They do NOT
prove actual model duration, behavior, live Project installation or background work.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs/sol_skills/BOOTSTRAP_KERNEL.md"
EXPORT = ROOT / "docs/evidence/2026-11-07-mission-continuation-project-instructions.txt"
ACCOUNT = ROOT / "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md"
GLOBAL = ROOT / "docs/evidence/2026-11-07-global-continuation-custom-instructions.txt"


def _block() -> str:
    source = KERNEL.read_text(encoding="utf-8")
    return source.split("## Approved Project instruction text", 1)[1].split(
        "```text\n", 1
    )[1].split("\n```", 1)[0]


def _flat(source: str) -> str:
    return " ".join(source.split())


def test_manual_project_export_is_exact_and_fits_char_and_byte_limits():
    block = _block()
    assert EXPORT.read_text(encoding="utf-8") == block + "\n"
    assert len(block) <= 8000
    assert len(block.encode("utf-8")) <= 8000
    assert block.startswith("MASTERMIND SOL BOOTSTRAP\n")
    for number in ("5.", "5A.", "6.", "6A.", "6B.", "9A.", "18.", "33.", "39.", "40."):
        assert sum(line.startswith(number + " ") for line in block.splitlines()) == 1


def test_substantial_assignment_must_start_next_phase_before_finalizing():
    block = _block()
    for phrase in (
        "LONG-HORIZON DEFAULT (substantial missions):",
        "A phase/PR/CI/checkpoint is not DONE_WHEN",
        "VERIFY -> SAVE/READBACK -> REASSESS parent DONE_WHEN -> START",
        "same healthy turn",
        "No Chairman reprompt",
        "authorized independent fallback",
        "18. Phase ladder: first exact input/action/proof, next safe phase",
        "PRE-FINAL FALSIFIER:",
        "MORE_WORK_EXISTS: START it before answering",
        "No phase/checkpoint/time-based exit",
    ):
        assert phrase in block, phrase


def test_default_preserves_real_stops_and_existing_safety_fences():
    block = _block()
    for phrase in (
        "a proven ACTIVE_EXECUTION boundary",
        "never pad time",
        "No denied-effect/EFFECT_UNKNOWN carrier swap",
        "Explicit safety/permission denial ends that action",
        "never self-approve/self-merge/falsify/bypass",
        "Never bulk-arm/clear other holds",
        "Native review != GitHub APPROVED",
        "HARD_ROTATION",
        "CHECKPOINTED_CONTINUATION",
        "DURABLE_EXECUTION_RUNNING needs STARTED/RUNNING plus return path",
        "No duplicate runners/queues",
        "HANDOFF_SOURCE_LINK_V1",
    ):
        assert phrase in block, phrase


def test_account_instruction_turns_continuation_into_specific_blocker_behaviors():
    account = _flat(ACCOUNT.read_text(encoding="utf-8"))
    for phrase in (
        "## Long-horizon Web execution: finish the mission, not the first phase",
        "first **executable** phase",
        "one lawful blocker fallback",
        "BEGIN its first useful action in this same healthy turn",
        "CI/review/merge pending",
        "Another writer owns live files",
        "Install/browser/host path unavailable",
        "Security/permission denial or `EFFECT_UNKNOWN`",
        "Repeated no-progress steps",
        "Before any incomplete final response, falsify the stop",
        "MORE_WORK_EXISTS",
        "start now",
        "CHECKPOINTED_CONTINUATION",
        "A Web response does not continue thinking or work after it ends",
        "Never create busywork",
    ):
        assert phrase in account, phrase


def test_manual_rollout_remains_explicit_and_not_claimed_installed():
    account = _flat(ACCOUNT.read_text(encoding="utf-8"))
    kernel = _flat(KERNEL.read_text(encoding="utf-8"))
    for phrase in (
        "each **distinct** authorized Mastermind Project",
        "preserving newer valid Project-specific rules",
        "8,000-character and UTF-8 byte budgets",
        "fresh-chat action scenarios per intended member account",
        "not proof of ChatGPT settings installation",
    ):
        assert phrase in account, phrase
    assert "source publication does not install live ChatGPT Project settings" in kernel

def test_account_global_overlay_covers_outside_project_without_overclaiming():
    global_text = GLOBAL.read_text(encoding="utf-8")
    account = _flat(ACCOUNT.read_text(encoding="utf-8"))
    assert len(global_text) <= 1500
    for phrase in (
        "LONG-HORIZON EXECUTION DEFAULT",
        "not simple questions",
        "VERIFY -> SAVE material progress -> REASSESS",
        "START the next safe, authorized, in-scope action",
        "Do not end just to ask me to say",
        "Is DONE_WHEN really proved?",
        "Respect real permission/safety denials",
        "No bypasses, busywork, guaranteed hours or fictional background work",
    ):
        assert phrase in global_text, phrase
    assert "Project instructions apply" in account
    assert "override global custom instructions" in account
    assert "This is a **supplement**" in account

def test_task_first_direct_execution_is_visible_in_project_and_native_briefs():
    block = _block()
    native = (ROOT / "docs/NATIVE_EXECUTION_BRIEF.md").read_text(encoding="utf-8")
    assert "9A. TASK FIRST: operational fix -> authorized host/service direct + live proof" in block
    assert "no PR absent source change" in block
    assert "21. Select fastest lawful route:" in block
    assert "without a failed Fabric attempt" in block
    assert "No extra review/handoff ceremony" in block
    assert "No denied-effect/EFFECT_UNKNOWN carrier swap" in block
    assert "Operational repair: use actually authorized host/service tools" in native
    assert "No PR absent" in native
    assert "A failed\n  worker dispatch is not required" in native
    assert "## Keep real boundaries" in native
