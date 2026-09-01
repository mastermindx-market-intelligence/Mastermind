from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-package-identity-amendment.md"
)
DESIGN = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-package-generation-design.md"
)
CORRECTION = ROOT / (
    "docs/superpowers/specs/"
    "2026-09-01-sol-capability-fabric-package-content-digest-correction.md"
)
PLAN = ROOT / (
    "docs/superpowers/plans/"
    "2026-09-01-sol-capability-fabric-package-generation.md"
)
DEFAULT_POLICY = ROOT / "config/executive_agent_capabilities.json"

CORRECT_PACKAGE_DIGEST = (
    "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306"
)
SUPERSEDED_PACKAGE_DIGEST = (
    "a82a274a82ed84c6e82a1c34b67c1f2f0a70cc465c26d0fcf64f648ac295cf16"
)


def _read(path: Path) -> str:
    payload = path.read_bytes()
    assert payload
    assert payload.endswith(b"\n")
    assert b"\x00" not in payload
    return payload.decode("utf-8")


def _marked_block(text: str, begin: str, end: str) -> str:
    before, marker, remainder = text.partition(begin)
    assert marker and before is not None
    body, marker, _after = remainder.partition(end)
    assert marker
    return body.strip()


def _fenced_body(block: str, language: str) -> str:
    opener = f"```{language}\n"
    assert block.startswith(opener)
    assert block.endswith("```")
    return block[len(opener) : -3].strip()


def test_amendment_has_narrow_precedence_and_preserves_completion_honesty() -> None:
    amendment = _read(AMENDMENT)
    design = _read(DESIGN)
    correction = _read(CORRECTION)
    plan = _read(PLAN)

    assert "supplements and, where it conflicts, supersedes" in amendment
    assert DESIGN.name in amendment
    assert PLAN.name in amendment
    assert CORRECT_PACKAGE_DIGEST in amendment
    assert CORRECT_PACKAGE_DIGEST in correction
    assert SUPERSEDED_PACKAGE_DIGEST in correction
    assert "SCF-PKG0 = SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED" in amendment
    assert "authorizes no implementation START" in amendment

    # The historical draft value may remain visible in the original records only
    # because the correction and this later amendment explicitly supersede it.
    assert SUPERSEDED_PACKAGE_DIGEST in design
    assert "package-content digest correction remains separately controlling" in amendment
    assert CORRECT_PACKAGE_DIGEST in plan


def test_v4_source_packages_do_not_reuse_the_runtime_plugin_namespace() -> None:
    amendment = _read(AMENDMENT)
    block = _marked_block(
        amendment,
        "<!-- SCF_PKG1_V4_ROOT_BEGIN -->",
        "<!-- SCF_PKG1_V4_ROOT_END -->",
    )
    root = json.loads(_fenced_body(block, "json"))

    assert set(root) == {
        "schema_version",
        "policy_version",
        "lifecycle_authority",
        "production_armed",
        "mcp_servers",
        "resources",
        "capability_packages",
        "plugins",
        "profiles",
    }
    assert root["schema_version"] == "mastermind.executive_agent_capabilities/v4"
    assert root["lifecycle_authority"] == "executive_os"
    assert root["production_armed"] is False
    assert root["capability_packages"] == {}
    assert root["plugins"] == {}

    assert "`capability_packages`, not a second registry" in amendment
    assert "plugins={}" in amendment
    assert "installed/runtime plugin grant namespace" in amendment


def test_v4_profile_uses_exact_skill_capabilities_without_overloading_skills() -> None:
    amendment = _read(AMENDMENT)

    assert '"skills": []' in amendment
    assert '"skill_capabilities": [' in amendment
    assert "V4 has no `skill_capabilities` key" not in amendment
    assert "V3 has no `skill_capabilities` key" in amendment
    assert "resolved dataclass `profile.skills`" in amendment
    assert "resolved dataclass `profile.skill_grants`" in amendment
    assert "Raw `skills` remains the legacy runtime-name" in amendment


def test_identity_digest_graph_is_acyclic_and_has_the_required_layering() -> None:
    amendment = _read(AMENDMENT)
    block = _marked_block(
        amendment,
        "<!-- SCF_PKG1_IDENTITY_DAG_BEGIN -->",
        "<!-- SCF_PKG1_IDENTITY_DAG_END -->",
    )
    lines = _fenced_body(block, "text").splitlines()
    edges: list[tuple[str, str]] = []
    for line in lines:
        left, arrow, right = line.partition(" -> ")
        assert arrow and left and right
        edges.append((left, right))

    required = {
        ("file_rows", "package_content_digest"),
        ("package_content_digest", "package_source_digest"),
        ("package_source_digest", "skill_grant_digest"),
        ("skill_content_digest", "skill_grant_digest"),
        ("skill_grant_digest", "package_generation_digest"),
        ("package_generation_digest", "profile_digest"),
        ("profile_digest", "policy_digest"),
    }
    assert required <= set(edges)
    assert ("package_generation_digest", "skill_grant_digest") not in edges

    nodes = {node for edge in edges for node in edge}
    incoming = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for left, right in edges:
        outgoing[left].append(right)
        incoming[right] += 1

    queue = deque(sorted(node for node, count in incoming.items() if count == 0))
    visited: list[str] = []
    while queue:
        node = queue.popleft()
        visited.append(node)
        for target in outgoing[node]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)

    assert set(visited) == nodes, "identity digest graph must be acyclic"
    assert "No digest requires a fixed point" in amendment


def test_corrected_interfaces_remove_the_circular_package_grant_reference() -> None:
    amendment = _read(AMENDMENT)
    dataclass_section = amendment.split("### 4.7 Corrected dataclass fields", 1)[1].split(
        "---", 1
    )[0]

    assert "package_source_digest: str" in dataclass_section
    assert "package_generation_digest: str" in dataclass_section
    assert "package_grant_digest" not in dataclass_section
    assert "EffectiveSkillGrant.package_grant_digest" in amendment
    assert "are superseded" in amendment


def test_parser_and_verifier_hardening_is_explicit_and_bounded() -> None:
    amendment = _read(AMENDMENT)

    for marker in (
        "reject duplicate keys at every JSON object depth",
        "duplicate root, package, file-row, Skill and profile keys",
        "0 <= byte_length <= MAX_PACKAGE_FILE_BYTES",
        "Perform a second complete-tree enumeration",
        "Final-`fstat` every retained directory",
        "post-census insertion/removal/rename",
        "Sleeps and probabilistic races are not acceptable",
        "Close every descriptor on success and every refusal",
    ):
        assert marker in amendment

    default_policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    assert default_policy["schema_version"] == "mastermind.executive_agent_capabilities/v3"
    assert default_policy["plugins"] == {}
    assert "capability_packages" not in default_policy


def test_corrected_implementation_scope_remains_the_same_six_code_paths() -> None:
    amendment = _read(AMENDMENT)
    expected = {
        "control_plane/executive_capability_packages.py",
        "control_plane/executive_agent_capabilities.py",
        "tests/fixtures/executive_agent_capabilities_v4_mastermind_operator.json",
        "tests/test_executive_capability_packages.py",
        "tests/test_executive_agent_capabilities.py",
        "tests/test_executive_agent_capabilities_v4.py",
    }
    for path in expected:
        assert path in amendment

    for protected in (
        "current default config",
        "route",
        "autonomy",
        "OHF comparator",
        "Codex adapter",
        "worker composition",
        "package-source",
        "Browser",
        "Business",
        "PPF",
        "Agent OS",
        "host",
        "deployment",
    ):
        assert protected in amendment
