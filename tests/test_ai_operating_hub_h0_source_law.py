"""Source law for the AI Operating Hub H0 current-estate freeze.

These tests are deliberately *discriminating*: they parse the real Control Room
source with :mod:`ast` and assert the frozen H0 evidence still describes it.  If
the compositor's closed output contract changes, if the remote release closure
gains or loses a runtime path, if the local and remote contracts are collapsed
into one schema, or if the three H0 records drift apart, these fail.

No repository module is imported.  Everything is read as text and parsed, so the
battery stays hermetic and cannot be satisfied by import side effects.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

RECORD = ROOT / "research" / "MASTERMIND_AI_OPERATING_HUB_H0_CURRENT_ESTATE_2026-09-03.md"
EVIDENCE = ROOT / "research" / "evidence" / "ai_operating_hub_h0_archaeology_2026-09-03.json"
PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-09-03-ai-operating-hub-h1-read-only-workstream.md"
)

COMPOSITOR = ROOT / "control_plane" / "chairman_control_room.py"
REMOTE = ROOT / "control_plane" / "chairman_control_room_remote.py"
P0A_SERVER = ROOT / "scripts" / "chairman_control_room.py"
X1_SERVER = ROOT / "scripts" / "chairman_control_room_remote.py"

OWNED_PATHS = (
    "research/MASTERMIND_AI_OPERATING_HUB_H0_CURRENT_ESTATE_2026-09-03.md",
    "research/evidence/ai_operating_hub_h0_archaeology_2026-09-03.json",
    "docs/superpowers/plans/2026-09-03-ai-operating-hub-h1-read-only-workstream.md",
    "tests/test_ai_operating_hub_h0_source_law.py",
)

CAPABILITY_VOCABULARY = frozenset(
    {
        "PROVEN_LIVE",
        "BUILT_NOT_PROVEN",
        "PARTIAL",
        "DARK_OR_DISCONNECTED",
        "BROKEN",
        "SPEC_ONLY",
        "NOT_BUILT",
        "REJECTED_BY_DESIGN",
    }
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"missing protected source-law record: {path}"
    return path.read_text(encoding="utf-8")


def _evidence() -> dict:
    value = json.loads(_text(EVIDENCE))
    assert value["schema"] == "mastermind.ai_operating_hub_h0_archaeology.v1"
    return value


def _module(path: pathlib.Path) -> ast.Module:
    return ast.parse(_text(path))


def _module_str_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings."""
    out: dict[str, str] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not isinstance(statement.value, ast.Constant):
            continue
        if not isinstance(statement.value.value, str):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name):
                out[target.id] = statement.value.value
    return out


def _assigned(tree: ast.Module, name: str) -> ast.expr:
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            return statement.value
    raise AssertionError(f"module-level assignment not found: {name}")


def _str_constant(tree: ast.Module, name: str) -> str:
    node = _assigned(tree, name)
    value = ast.literal_eval(node)
    assert isinstance(value, str)
    return value


def _resolved_frozenset(tree: ast.Module, name: str) -> set[str]:
    """``frozenset({...})`` of string literals and/or module-level constants."""
    node = _assigned(tree, name)
    assert isinstance(node, ast.Call), f"{name} is not a call"
    assert isinstance(node.func, ast.Name) and node.func.id == "frozenset"
    assert len(node.args) == 1 and not node.keywords
    env = _module_str_constants(tree)
    values: set[str] = set()
    for element in node.args[0].elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            values.add(element.value)
        elif isinstance(element, ast.Name):
            assert element.id in env, f"{name}: unresolvable name {element.id}"
            values.add(env[element.id])
        else:
            raise AssertionError(f"{name}: unresolvable element {ast.dump(element)}")
    return values


def _path_equality_routes(tree: ast.Module) -> set[str]:
    """Every ``path == "<literal>"`` route comparison in a server module."""
    routes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not (isinstance(node.left, ast.Name) and node.left.id == "path"):
            continue
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant):
                if isinstance(comparator.value, str):
                    routes.add(comparator.value)
    return routes


def _frontmatter(path: pathlib.Path) -> dict[str, str]:
    text = _text(path)
    assert text.startswith("---\n"), f"{path} has no YAML frontmatter"
    block = text.split("---\n", 2)[1]
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


# ---------------------------------------------------------------------------
# the four owned paths exist and nothing else was claimed
# ---------------------------------------------------------------------------


def test_owned_paths_exist_and_match_the_declared_ceiling() -> None:
    declared = _evidence()["collision_census"]["owned_paths"]
    assert list(declared) == list(OWNED_PATHS), "H0 path ceiling drifted"
    assert len(set(declared)) == 4
    for relative in declared:
        assert (ROOT / relative).is_file(), f"declared owned path missing: {relative}"


def test_collision_census_records_a_clean_pre_start_estate() -> None:
    census = _evidence()["collision_census"]
    assert census["exact_branch"] == (
        "sol/ai-operating-hub-h0-current-estate-freeze-20260903"
    )
    assert census["exact_branch_present_before_start"] is False
    assert census["exact_branch_present_on_remote_before_start"] is False
    assert census["exact_operation_pr_present_before_start"] is False
    assert census["worktree_present_at_target_path_before_start"] is False
    assert census["owned_paths_present_on_protected_master_before_start"] == []


# ---------------------------------------------------------------------------
# the frozen contract values still describe the real source
# ---------------------------------------------------------------------------


def test_compositor_contract_matches_frozen_evidence() -> None:
    frozen = _evidence()["frozen_contract_values"]
    tree = _module(COMPOSITOR)
    assert _str_constant(tree, "SCHEMA") == frozen["compositor_schema"]
    assert _resolved_frozenset(tree, "OUTPUT_KEYS") == set(
        frozen["compositor_output_keys"]
    )


def test_remote_contract_and_release_closure_match_frozen_evidence() -> None:
    frozen = _evidence()["frozen_contract_values"]
    tree = _module(REMOTE)
    assert _str_constant(tree, "REMOTE_SCHEMA") == frozen["remote_schema"]
    assert _str_constant(tree, "RELEASE_SCHEMA") == frozen["release_schema"]
    assert _resolved_frozenset(tree, "REQUIRED_RUNTIME_PATHS") == set(
        frozen["required_runtime_paths"]
    )
    assert _resolved_frozenset(tree, "COLLECTOR_SOURCES") == set(
        frozen["collector_sources"]
    )


def test_local_p0a_transport_and_routes_match_frozen_evidence() -> None:
    frozen = _evidence()["frozen_contract_values"]
    tree = _module(P0A_SERVER)
    assert ast.literal_eval(_assigned(tree, "DEFAULT_PORT")) == frozen["p0a_default_port"]
    assert _str_constant(tree, "HOST") == frozen["p0a_host"]
    assert list(ast.literal_eval(_assigned(tree, "_ALLOWED_HOSTNAMES"))) == list(
        frozen["p0a_allowed_hostnames"]
    )
    assert _path_equality_routes(tree) == set(frozen["p0a_path_equality_routes"])


def test_remote_x1_route_allowlist_matches_frozen_evidence() -> None:
    frozen = _evidence()["frozen_contract_values"]
    tree = _module(X1_SERVER)
    static_routes = ast.literal_eval(_assigned(tree, "STATIC_ROUTES"))
    assert sorted(static_routes) == list(frozen["x1_static_routes"])
    read_routes = _assigned(tree, "READ_ROUTES")
    extras = sorted(
        node.value
        for node in ast.walk(read_routes)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )
    assert extras == list(frozen["x1_read_routes_extra_literals"])


def test_remote_x1_allowlist_exposes_no_mutation_route() -> None:
    """X1 is read-only by construction; the P0A mutation routes must never appear."""
    frozen = _evidence()["frozen_contract_values"]
    allowed = set(frozen["x1_static_routes"]) | set(
        frozen["x1_read_routes_extra_literals"]
    )
    for mutation_route in ("/api/open", "/api/bind", "/api/unbind", "/api/refresh-builds"):
        assert mutation_route not in allowed, (
            f"remote X1 allowlist exposes mutation route {mutation_route}"
        )


# ---------------------------------------------------------------------------
# owner boundaries
# ---------------------------------------------------------------------------


def test_local_p0a_and_remote_x1_are_never_collapsed() -> None:
    boundaries = _evidence()["owner_boundaries"]
    local_schema = boundaries["local_p0a"]["contract_schema"]
    remote_schema = boundaries["remote_x1"]["contract_schema"]
    assert local_schema != remote_schema, "local P0A and remote X1 contracts collapsed"
    assert local_schema == _str_constant(_module(COMPOSITOR), "SCHEMA")
    assert remote_schema == _str_constant(_module(REMOTE), "REMOTE_SCHEMA")
    assert boundaries["remote_x1"]["mutation"] == "none - read-only by construction"


def test_every_recorded_owner_path_exists_in_the_repository() -> None:
    boundaries = _evidence()["owner_boundaries"]
    for surface in ("local_p0a", "remote_x1"):
        row = boundaries[surface]
        candidates = [row["server_entrypoint"], row["ui_entry"]]
        candidates += list(row["shared_static_paths"])
        candidates += list(row.get("release_paths", []))
        for key in ("compositor", "projection"):
            if key in row:
                candidates.append(row[key])
        for relative in candidates:
            assert (ROOT / relative).is_file(), f"recorded owner path missing: {relative}"


def test_required_runtime_paths_all_exist() -> None:
    """The X1 release closure must not pin a path the repository does not ship."""
    for relative in _evidence()["frozen_contract_values"]["required_runtime_paths"]:
        assert (ROOT / relative).exists(), f"REQUIRED_RUNTIME_PATHS names {relative}"


# ---------------------------------------------------------------------------
# organizational ownership
# ---------------------------------------------------------------------------


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _string_values(v)]
    if isinstance(value, list):
        return [s for v in value for s in _string_values(v)]
    return []


def test_binds_the_existing_workstream_and_creates_no_new_one() -> None:
    evidence = _evidence()
    assert evidence["reference_workstream"] == "WS:CHAIRMAN-CONTROL-ROOM"
    assert evidence["collision_census"]["ws_ai_hub_present_on_protected_master"] is False

    # WS:AI-HUB may be named only to forbid it.  Every occurrence — in an
    # evidence value or a prose line — must carry a negation on the same
    # string, so a future edit that quietly mints the workstream fails here.
    negation = re.compile(r"\b(no|not|never|without|absent|forbidden)\b", re.IGNORECASE)
    for text in _string_values(evidence):
        if "WS:AI-HUB" in text:
            assert negation.search(text), f"evidence binds WS:AI-HUB in {text!r}"
    for path in (RECORD, PLAN):
        for number, line in enumerate(_text(path).splitlines(), start=1):
            if "WS:AI-HUB" in line:
                assert negation.search(line), f"{path}:{number} mints WS:AI-HUB"

    assert _frontmatter(RECORD)["organizational_owner"] == "WS:CHAIRMAN-CONTROL-ROOM"
    assert _frontmatter(PLAN)["workstream"] == "WS:CHAIRMAN-CONTROL-ROOM"


def test_capability_ledger_uses_only_the_closed_vocabulary() -> None:
    evidence = _evidence()
    assert set(evidence["capability_vocabulary"]) == CAPABILITY_VOCABULARY
    ledger = evidence["capability_ledger"]
    assert ledger, "capability ledger is empty"
    for capability, state in ledger.items():
        assert state in CAPABILITY_VOCABULARY, f"{capability} invented state {state!r}"
    assert ledger["parallel_hub_control_plane"] == "REJECTED_BY_DESIGN"


def test_no_unproven_capability_is_promoted_to_proven_live() -> None:
    """H0 observed source only; nothing in this freeze may claim production proof."""
    ledger = _evidence()["capability_ledger"]
    assert "PROVEN_LIVE" not in set(ledger.values()), (
        "H0 observed no production readback; no sub-capability may claim PROVEN_LIVE"
    )


# ---------------------------------------------------------------------------
# the three records agree with each other
# ---------------------------------------------------------------------------


def test_records_pin_the_same_protected_master() -> None:
    evidence = _evidence()
    protected = evidence["protected_master"]
    assert _SHA_RE.fullmatch(protected)
    assert _SHA_RE.fullmatch(evidence["protected_master_tree"])
    assert evidence["current_protected_at_delivery"] == protected
    assert _frontmatter(RECORD)["protected_master"] == protected
    assert _frontmatter(PLAN)["protected_master_at_freeze"] == protected


def test_records_agree_on_the_selected_consumer() -> None:
    evidence = _evidence()
    selected = evidence["selected_first_consumer"]
    assert selected["selected"] == "local P0A Chairman Control Room"
    assert selected["not_selected"] == "remote X1"
    assert selected["falsifier"].strip(), "consumer selection has no falsifier"
    assert _frontmatter(RECORD)["selected_first_consumer"] == selected["selected"]


def test_h1_ceiling_agrees_between_evidence_and_plan() -> None:
    ceiling = _evidence()["h1_path_ceiling"]
    plan = _text(PLAN)
    for relative in ceiling["may_create"]:
        assert relative in plan, f"H1 plan omits permitted path {relative}"
    for relative in ceiling["may_modify_only_after_pr_326_merges"]:
        assert relative in plan, f"H1 plan omits gated path {relative}"
    for relative in ceiling["forbidden_paths"]:
        assert relative in plan, f"H1 plan omits forbidden path {relative}"
    assert ceiling["fifth_path_disposition"].startswith("DECISION_REQUEST")


def test_h1_ceiling_never_permits_a_forbidden_owner_path() -> None:
    ceiling = _evidence()["h1_path_ceiling"]
    permitted = set(ceiling["may_create"]) | set(
        ceiling["may_modify_only_after_pr_326_merges"]
    )
    forbidden = set(ceiling["forbidden_paths"])
    assert not (permitted & forbidden), "H1 ceiling permits a forbidden owner path"
    for critical in (
        "control_plane/chairman_control_room.py",
        "control_plane/chairman_control_room_remote.py",
        "scripts/chairman_control_room_remote.py",
        "app/static/chairman_control/remote.html",
        "ops/control_room_remote/install.sh",
    ):
        assert critical in forbidden, f"H1 ceiling fails to protect {critical}"


def test_h1_remains_held_and_gated_on_pr_326() -> None:
    assert _frontmatter(PLAN)["authorization_state"] == "HELD"
    ceiling = _evidence()["h1_path_ceiling"]
    assert "326" in ceiling["blocking_precondition"]
    assert "BLOCKED UI_PATHS_CONTENDED_BY_PR_326" in ceiling["blocking_precondition"]


# ---------------------------------------------------------------------------
# PR archaeology and non-effects
# ---------------------------------------------------------------------------


def test_pr_archaeology_records_exact_immutable_identities() -> None:
    rows = {row["number"]: row for row in _evidence()["pr_archaeology"]}
    assert set(rows) == {326, 350, 416}
    for row in rows.values():
        assert _SHA_RE.fullmatch(row["head"]), f"PR #{row['number']} head is not a SHA"
    assert rows[416]["state"] == "MERGED"
    assert _SHA_RE.fullmatch(rows[416]["merge_commit"])
    assert rows[326]["state"] == "OPEN_DRAFT"
    assert rows[350]["state"] == "OPEN_DRAFT"
    assert (
        "control_plane/autonomy_control_room_projection.py" in rows[326]["owns"]
    ), "PR #326 archaeology must record the derived-status owner"
    assert rows[350]["shared_paths_with_326"], "PR #350 downstream overlap not recorded"


def test_derived_status_owner_is_not_on_protected_master() -> None:
    """PR #326's projection is BUILT_NOT_PROVEN precisely because it has not landed."""
    ledger = _evidence()["capability_ledger"]
    assert ledger["autonomy_responsibility_projection"] == "BUILT_NOT_PROVEN"
    assert not (ROOT / "control_plane" / "autonomy_control_room_projection.py").exists()


def test_non_effects_are_declared() -> None:
    non_effects = _evidence()["non_effects"]
    joined = " | ".join(non_effects).lower()
    for claim in (
        "no h1 source",
        "no deployment",
        "no ws:ai-hub created",
        "no agent os write",
        "no linear write",
    ):
        assert claim in joined, f"non-effect not declared: {claim}"
    assert _frontmatter(RECORD)["production_effect"] == "NONE"
    assert _frontmatter(PLAN)["production_effect"] == "NONE"


def test_skillpack_pin_is_exact() -> None:
    skillpack = _evidence()["skillpack"]
    assert skillpack["schema"] == "mastermind.sol_skillpack.v1"
    assert skillpack["version"] == "1.0.1"
    assert skillpack["minimum_bootstrap_major"] == 1
    index = ROOT / "docs" / "sol_skills" / "INDEX.md"
    front = _frontmatter(index)
    assert front["schema"] == skillpack["schema"]
    assert front["skillpack_version"] == skillpack["version"]
    assert int(front["minimum_bootstrap_major"]) == skillpack["minimum_bootstrap_major"]
