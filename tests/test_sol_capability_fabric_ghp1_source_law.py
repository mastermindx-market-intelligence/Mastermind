from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/superpowers/specs/2026-09-03-sol-capability-fabric-github-branch-patch-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-03-sol-capability-fabric-ghp1.md"
SCOPE = ROOT / "docs/superpowers/plans/2026-09-03-sol-capability-fabric-ghp1-scope-correction.md"
STATE = ROOT / "research/sol_capability_fabric/GITHUB_BRANCH_PATCH_CURRENT_STATE_2026-09-03.md"
MODULE = ROOT / "control_plane/github_branch_patch.py"
TEST = ROOT / "tests/test_github_branch_patch.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ghp1_source_package_exists_and_names_one_operation() -> None:
    for path in (DESIGN, PLAN, SCOPE, STATE, MODULE, TEST):
        assert path.is_file(), path
    operation = "mastermind-sol-capability-fabric-ghp1-20260902-sol-001"
    for path in (DESIGN, PLAN, SCOPE, STATE):
        assert operation in _read(path)


def test_design_preserves_owner_and_no_rebuild_boundaries() -> None:
    text = _read(DESIGN)
    required = (
        "GitHub |",
        "Executive OS |",
        "Agent OS |",
        "prepare_branch_patch",
        "commit_branch_patch",
        "reconcile_branch_patch",
        "NOT_APPLIED | APPLIED | EFFECT_UNKNOWN",
        "generic repository MCP",
        "model-selected repository, branch, credential, installation or writer",
        "fuzzy/three-way patching",
        "Green source CI or a merged materializer alone establishes at most `BUILT_NOT_PROVEN`",
    )
    for marker in required:
        assert marker in text


def test_plan_freezes_six_paths_and_production_inert_stop() -> None:
    text = _read(SCOPE)
    expected = {
        "control_plane/github_branch_patch.py",
        "tests/test_github_branch_patch.py",
        "tests/test_sol_capability_fabric_ghp1_source_law.py",
        "docs/superpowers/specs/2026-09-03-sol-capability-fabric-github-branch-patch-design.md",
        "docs/superpowers/plans/2026-09-03-sol-capability-fabric-ghp1.md",
        "docs/superpowers/plans/2026-09-03-sol-capability-fabric-ghp1-scope-correction.md",
        "research/sol_capability_fabric/GITHUB_BRANCH_PATCH_CURRENT_STATE_2026-09-03.md",
    }
    for path in expected:
        assert path in text or path == "tests/test_sol_capability_fabric_ghp1_source_law.py"
    plan = _read(PLAN)
    assert "BUILT_NOT_PROVEN / PRODUCTION_INERT" in plan
    assert "Do not in GHP1:" in plan
    assert "add an MCP server or custom app" in plan
    assert "call GitHub" in plan


def test_current_state_corrects_noncanonical_chat_overstatement() -> None:
    text = _read(STATE)
    assert "Correction of non-canonical chat claims" in text
    assert "model-facing GitHub patch owner app       NOT_BUILT" in text
    assert "real >10,000-line production canary        NOT_BUILT" in text
    assert "end-to-end ChatGPT branch patch            NOT_BUILT" in text


def test_pure_module_does_not_import_integrations_or_owner_runtime() -> None:
    text = _read(MODULE)
    forbidden = (
        "from integrations",
        "import integrations",
        "github.com",
        "api.github.com",
        "httpx",
        "requests",
        "subprocess",
        "pathlib",
        "sqlite",
        "psycopg",
    )
    for marker in forbidden:
        assert marker not in text
