"""Source-only regression for Web CEO Macro merge-on-green release instructions.

The Project code fence is the deployable instruction payload. These checks do
not claim that it is installed in the active ChatGPT Project, that a native
review exists, or that any PR has been merged.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs/sol_skills/BOOTSTRAP_KERNEL.md"
DELIVERY = ROOT / "docs/DELIVERY_WORKFLOW.md"


def _approved_project_block(text: str) -> str:
    return text.split("## Approved Project instruction text", 1)[1].split(
        "```text\n", 1
    )[1].split("\n```", 1)[0]


def _contains_macro_release_instruction(text: str) -> bool:
    return all(
        snippet in _approved_project_block(text)
        for snippet in (
            "Macro release:",
            "docs/DELIVERY_WORKFLOW.md",
            "`merge-on-green`",
            "clean CI",
            "non-author review",
            "no HOLD",
            "No blanket-arming or native auto-merge",
        )
    )


def test_actual_web_project_block_exposes_release_pointer_within_budget():
    kernel = KERNEL.read_text(encoding="utf-8")
    block = _approved_project_block(kernel)
    assert _contains_macro_release_instruction(kernel)
    assert block.startswith("MASTERMIND SOL BOOTSTRAP")
    assert len(block) <= 8000
    assert len(block.encode("utf-8")) <= 8000
    assert DELIVERY.is_file()


def test_outside_fence_release_note_does_not_count_as_installed_instruction():
    kernel = KERNEL.read_text(encoding="utf-8")
    assert _contains_macro_release_instruction(kernel)
    moved = kernel.replace(
        "9A. Macro release: pinned docs/DELIVERY_WORKFLOW.md; `merge-on-green` is opt-in after clean CI, non-author review and no HOLD. No blanket-arming or native auto-merge.",
        "",
    )
    assert moved != kernel, "the exact projected rule must exist in the source"
    assert not _contains_macro_release_instruction(moved)
    assert "Cross-session PR release and auto-merge discoverability" in moved


def test_release_procedure_requires_review_holds_ci_and_real_sweeper_readback():
    delivery = DELIVERY.read_text(encoding="utf-8")
    section = delivery.split(
        "## Macro release: `merge-on-green` is opt-in, not native auto-merge",
        1,
    )[1].split("## Review-readiness liveness", 1)[0]
    for token in (
        "macro/main",
        "can_arm_merge_on_green",
        "HOLD-RELEASED",
        "APPROVED",
        "Fabric",
        "Only when release is **actually authorized**",
        "gh pr edit <number> --add-label merge-on-green",
        "failure-marker pass",
        "global CI workload cap",
        "native `gh pr merge --auto`",
        "PROVEN_LIVE",
    ):
        assert token in section, f"Macro release gate lost: {token}"
    assert section.index("Verify the applicable") < section.index(
        "Only when release is **actually authorized**"
    ), "release opt-in must come after non-author and hold checks"
