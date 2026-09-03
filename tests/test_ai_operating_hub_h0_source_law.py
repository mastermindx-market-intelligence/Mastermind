"""Source law for the AI Operating Hub H0 current-estate freeze.

These tests are deliberately *discriminating*: they parse the real Control Room
source with :mod:`ast` and assert the frozen H0 evidence still describes it.  If
the compositor's closed output contract changes, if the remote release closure
gains or loses a runtime path, if the local and remote contracts are collapsed
into one schema, or if the four H0 records drift apart, these fail.

No repository module is imported.  Everything is read as text and parsed, so the
battery stays hermetic and cannot be satisfied by import side effects.  Nothing
here fetches from GitHub or Macro at test time either: the accepted-capability
citations and PR archaeology are dated observations (see CONTRACT_LAW in the
evidence file) verified for *internal* consistency, not against a live refetch.
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

H1_NINE_PATHS = frozenset(
    {
        "control_plane/ai_operating_hub_workroom.py",
        "app/static/chairman_control/hub_workroom.js",
        "app/static/chairman_control/hub_workroom.css",
        "tests/test_ai_operating_hub_workroom.py",
        "tests/test_chairman_control_room_ai_hub.py",
        "tests/test_chairman_control_room_ui_ai_hub.py",
        "docs/superpowers/plans/2026-09-03-ai-operating-hub-h1-implementation-receipt.md",
        "scripts/chairman_control_room.py",
        "app/static/chairman_control/index.html",
    }
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PLACEHOLDER_DATE_RE = re.compile(r"\d{4}-\d{2}-XX")
_URL_RE = re.compile(r"^https://[^\s]+$")


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


def _collapsed(text: str) -> str:
    """Whitespace-collapsed text for prose substring checks that must survive
    hand-authored markdown line wraps without caring about exact line breaks."""
    return re.sub(r"\s+", " ", text)


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _string_values(v)]
    if isinstance(value, list):
        return [s for v in value for s in _string_values(v)]
    return []


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


def test_h1_misclassification_guards_are_recorded() -> None:
    guards = _evidence()["owner_boundaries"]["h1_misclassification_guards"]
    joined = " | ".join(guards).lower()
    for phrase in ("terminal attempt", "nonblank watcher", "causally after"):
        assert phrase in joined, f"missing H1 misclassification guard: {phrase}"


def test_dialogue_boundary_owner_matches_pr_357() -> None:
    boundaries = _evidence()["owner_boundaries"]
    assert "PR #357" in boundaries["dialogue_boundary_owner"]
    assert "b28023f92458ba186937afa1e619f3b4464e149f" in boundaries["dialogue_boundary_owner"]


# ---------------------------------------------------------------------------
# organizational ownership
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# accepted capability truth vs. this carrier's observation ceiling
# ---------------------------------------------------------------------------


_MACRO_SOURCE_RE = re.compile(
    r"^mastermindx-market-intelligence/macro@[0-9a-f]{40}:"
    r"agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM\.md$"
)


def test_accepted_capabilities_are_backed_by_a_real_citation() -> None:
    """Every PROVEN_LIVE row must cite real accepted owner evidence, not this
    carrier's own say-so — and every citation must name a real Agent OS source,
    not a fabricated one."""
    evidence = _evidence()
    ledger = evidence["capability_ledger"]
    citations = evidence["capability_ledger_citations"]
    proven_live_keys = {k for k, v in ledger.items() if v == "PROVEN_LIVE"}
    assert proven_live_keys, "expected at least one accepted PROVEN_LIVE capability"
    for key in proven_live_keys:
        assert key in citations, f"PROVEN_LIVE key {key!r} has no capability_ledger_citations entry"
        row = citations[key]
        assert row["claim"].strip()
        assert row["observed_at"]
        assert _MACRO_SOURCE_RE.match(row["source"]), f"{key}: not a real Agent OS source: {row['source']!r}"
        assert row["receipts"], f"{key}: no receipt PRs cited"


def test_accepted_capability_cannot_be_cosmetically_downgraded() -> None:
    """Discriminator: local P0A+H0 and X1-local acceptance must not regress."""
    ledger = _evidence()["capability_ledger"]
    assert ledger["local_p0a_accepted_path"] == "PROVEN_LIVE"
    assert ledger["remote_x1_accepted_local_proof"] == "PROVEN_LIVE"


def test_local_x1_proof_cannot_be_promoted_to_remote_production() -> None:
    """Discriminator: local acceptance of X1's code/contract must never bleed
    into a claim that a remote-socket production instance is deployed."""
    ledger = _evidence()["capability_ledger"]
    assert ledger["remote_x1_accepted_local_proof"] == "PROVEN_LIVE"
    assert ledger["remote_x1_deployed_production"] != "PROVEN_LIVE"
    citation = _evidence()["capability_ledger_citations"]["remote_x1_accepted_local_proof"]
    assert "loopback" in citation["scope"].lower()
    assert "not a deployed remote-socket production instance" in citation["scope"]


def test_overall_workstream_partial_does_not_conflict_with_sub_capability_rows() -> None:
    ledger = _evidence()["capability_ledger"]
    assert ledger["chairman_control_room_workstream_overall"] == "PARTIAL"
    assert ledger["local_p0a_accepted_path"] == "PROVEN_LIVE"
    assert ledger["remote_x1_accepted_local_proof"] == "PROVEN_LIVE"
    discriminators = " ".join(_evidence()["capability_ledger_discriminators"]).lower()
    assert "demoting" in discriminators and "promoting" in discriminators


def test_unaccepted_pr_326_projection_stays_unpromoted() -> None:
    """This carrier's own observation ceiling: PR #326's dispatch projection is
    not independently accepted, so it must stay BUILT_NOT_PROVEN, never PROVEN_LIVE."""
    ledger = _evidence()["capability_ledger"]
    assert ledger["autonomy_responsibility_projection"] == "BUILT_NOT_PROVEN"
    assert not (ROOT / "control_plane" / "autonomy_control_room_projection.py").exists()


# ---------------------------------------------------------------------------
# the four records agree with each other
# ---------------------------------------------------------------------------


def test_records_pin_the_same_protected_master() -> None:
    evidence = _evidence()
    protected = evidence["protected_master"]
    assert _SHA_RE.fullmatch(protected)
    assert _SHA_RE.fullmatch(evidence["protected_master_tree"])
    assert _frontmatter(RECORD)["protected_master"] == protected
    assert _frontmatter(PLAN)["protected_master_at_freeze"] == protected


def test_records_agree_on_the_selected_consumer() -> None:
    evidence = _evidence()
    selected = evidence["selected_first_consumer"]
    assert selected["selected"] == "local P0A Chairman Control Room"
    assert selected["not_selected"] == "remote X1"
    assert selected["falsifier"].strip(), "consumer selection has no falsifier"
    assert _frontmatter(RECORD)["selected_first_consumer"] == selected["selected"]


# ---------------------------------------------------------------------------
# H1 nine-path ceiling and dual-protection gate
# ---------------------------------------------------------------------------


def test_h1_ceiling_is_exactly_nine_paths_and_agrees_with_the_plan() -> None:
    ceiling = _evidence()["h1_path_ceiling"]
    may_create = set(ceiling["may_create"])
    may_modify = set(ceiling["may_modify_only_after_h0_and_pr_326_protect"])
    all_paths = may_create | may_modify
    assert all_paths == H1_NINE_PATHS, f"H1 ceiling drifted from the frozen nine paths: {all_paths}"
    assert len(may_create) == 7
    assert len(may_modify) == 2
    plan = _collapsed(_text(PLAN))
    for relative in all_paths:
        assert relative in plan, f"H1 plan omits ceiling path {relative}"
    for relative in ceiling["forbidden_paths"]:
        assert relative in plan, f"H1 plan omits forbidden path {relative}"


def test_h1_ceiling_never_permits_a_forbidden_owner_path() -> None:
    ceiling = _evidence()["h1_path_ceiling"]
    permitted = set(ceiling["may_create"]) | set(
        ceiling["may_modify_only_after_h0_and_pr_326_protect"]
    )
    forbidden = set(ceiling["forbidden_paths"])
    assert not (permitted & forbidden), "H1 ceiling permits a forbidden owner path"
    for critical in (
        "control_plane/chairman_control_room.py",
        "control_plane/chairman_control_room_remote.py",
        "scripts/chairman_control_room_remote.py",
        "app/static/chairman_control/remote.html",
        "ops/control_room_remote/install.sh",
        "control_plane/autonomy_control_room_projection.py",
        "integrations/slack_agent_dialogue/engine_v2.py",
        "integrations/slack_agent_dialogue/wake_projection.py",
    ):
        assert critical in forbidden, f"H1 ceiling fails to protect {critical}"


def test_h1_receipt_path_has_no_placeholder_date() -> None:
    """Discriminator: a 2026-09-XX placeholder path fails; the receipt path
    must be one exact, dated path."""
    ceiling = _evidence()["h1_path_ceiling"]
    receipt_paths = [p for p in ceiling["may_create"] if "implementation-receipt" in p]
    assert len(receipt_paths) == 1, "expected exactly one H1 receipt path"
    receipt = receipt_paths[0]
    assert not _PLACEHOLDER_DATE_RE.search(receipt), f"H1 receipt path is a placeholder: {receipt}"
    assert re.search(r"2026-09-\d{2}-ai-operating-hub-h1-implementation-receipt\.md$", receipt)
    assert receipt in _text(PLAN)
    assert "2026-09-XX" not in _text(PLAN), "H1 plan still contains a placeholder receipt date"
    assert "2026-09-XX" not in _text(RECORD), "H0 record still contains a placeholder receipt date"


def test_h1_start_is_gated_on_both_h0_and_pr_326_not_ui_paths_alone() -> None:
    """Discriminator: H1 pre-#326 (or pre-H0) START permission must fail — the
    gate covers all nine paths, not merely the two that touch PR #326's files."""
    ceiling = _evidence()["h1_path_ceiling"]
    gate = ceiling["gate"].lower()
    assert "all nine paths" in gate
    assert "not authorized" in gate
    plan = _collapsed(_text(PLAN)).lower()
    assert "held until both this h0 record and pr #326 are protected" in plan
    assert "not authorized" in plan
    # The old framing ("may create paths 1-4 early") must not survive the repair.
    assert "may begin with paths" not in plan
    assert "limited to paths 1" not in plan


def test_h1_remains_held() -> None:
    assert _frontmatter(PLAN)["authorization_state"] == "HELD"


# ---------------------------------------------------------------------------
# exact local route / security / cache / threat-boundary law
# ---------------------------------------------------------------------------


def test_h1_route_security_contract_is_frozen_and_honest() -> None:
    contract = _evidence()["h1_route_security_contract"]
    assert contract["route"] == "/api/hub/workstream/chairman-control-room"
    assert contract["http_method"] == "GET"
    assert contract["resolves_to_literal_workstream"] == "WS:CHAIRMAN-CONTROL-ROOM"
    for forbidden in (
        "network call",
        "subprocess",
        "arbitrary workstream query parameter",
        "fuzzy match",
        "second compositor",
    ):
        assert forbidden in contract["forbidden"]
    for preserved in ("Host header check", "Origin header check", "X-CCR-Token gate", "CSP"):
        assert preserved in contract["preserved_from_api_state"]
    honesty = contract["token_honesty_law"]
    assert "not authentication against another same-user local process" in honesty
    assert "must not claim a verified user identity" in honesty
    plan = _collapsed(_text(PLAN))
    assert "/api/hub/workstream/chairman-control-room" in plan
    assert "X-CCR-Token" in plan
    assert "not authentication against another same-user local process" in plan


def test_h1_route_contract_missing_any_law_element_would_be_caught() -> None:
    """Discriminator: a route/token/cache/threat-boundary law with a missing
    required element fails — verified here by asserting the full required set
    is present, not a subset."""
    contract = _evidence()["h1_route_security_contract"]
    required_forbidden = {
        "request-time re-gather",
        "network call",
        "subprocess",
        "file discovery",
        "arbitrary workstream query parameter",
        "fuzzy match",
        "second compositor",
    }
    assert required_forbidden.issubset(set(contract["forbidden"]))
    required_preserved = {
        "loopback-only binding",
        "Host header check",
        "Origin header check",
        "CSP",
        "request body bound",
        "response body bound",
        "X-CCR-Token gate",
    }
    assert required_preserved.issubset(set(contract["preserved_from_api_state"]))


# ---------------------------------------------------------------------------
# evidence-link typing law
# ---------------------------------------------------------------------------


def test_evidence_link_law_defines_typed_absence_and_real_examples() -> None:
    law = _evidence()["evidence_link_law"]
    assert law["not_available_meaning"].strip()
    assert law["not_applicable_meaning"].strip()
    assert law["example_real_deep_links"], "no real deep-link examples cited"
    for url in law["example_real_deep_links"]:
        assert _URL_RE.match(url), f"not a real URL: {url}"
        assert url.startswith("https://github.com/mastermindx-market-intelligence/Mastermind/pull/")


def test_no_fabricated_deep_link_present_in_evidence() -> None:
    """Discriminator: a fabricated deep link fails.  Every URL claimed in the
    github.com/.../pull/N deep-link convention this record uses must be one of
    the cited real deep links.  A loopback address quoted as literal evidence
    provenance (e.g. inside an accepted-capability citation's scope) is not a
    claimed deep link and is out of scope for this check."""
    evidence = _evidence()
    allowed = set(evidence["evidence_link_law"]["example_real_deep_links"])
    deep_link_pattern = re.compile(r"https://github\.com/\S+/pull/\d+")
    for text in _string_values(evidence):
        for url in deep_link_pattern.findall(text):
            url = url.rstrip(".,)")
            assert url in allowed, f"unrecognized/fabricated deep link in evidence: {url}"


# ---------------------------------------------------------------------------
# immutable contract vs. dated observation
# ---------------------------------------------------------------------------


def test_contract_law_separates_immutable_from_dated_fields() -> None:
    law = _evidence()["contract_law"]
    assert set(law["dated_observation_fields"]) & set(_evidence().keys()) == set(
        law["dated_observation_fields"]
    ), "a declared dated_observation_field is not a real top-level evidence key"
    assert "immutable_contract_fields" in law
    assert "rule" in law and law["rule"].strip()
    rule = law["rule"].lower()
    assert "does not compare against a live-fetched" in rule
    assert "does not itself turn this record red" in rule


def test_dated_fields_carry_observed_at_receipts() -> None:
    evidence = _evidence()
    assert evidence["observed_at"]
    for row in evidence["pr_archaeology"]:
        if row["state"] == "OPEN_DRAFT" and "reviews" in row:
            assert row.get("observed_at"), f"PR #{row['number']} missing observed_at receipt"
    assert evidence["linear_portfolio"]["observed_at"]
    for citation in evidence["capability_ledger_citations"].values():
        assert citation["observed_at"]


def test_source_law_does_not_compare_against_a_live_fetch() -> None:
    """This test file itself must stay hermetic: no real import of a
    subprocess/network module.  Checked via ast so that merely *documenting*
    a forbidden word (e.g. inside the route-contract discriminator test's own
    string literals) does not trip this check."""
    banned_modules = {"subprocess", "urllib", "requests", "socket", "http.client"}
    tree = ast.parse(_text(pathlib.Path(__file__)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in banned_modules, (
                    f"source law test file is not hermetic: imports {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in banned_modules, (
                f"source law test file is not hermetic: imports from {node.module}"
            )


# ---------------------------------------------------------------------------
# PR archaeology and non-effects
# ---------------------------------------------------------------------------


def test_pr_archaeology_records_exact_immutable_identities() -> None:
    rows = {row["number"]: row for row in _evidence()["pr_archaeology"]}
    assert set(rows) == {326, 350, 357, 416, 421}
    for row in rows.values():
        assert _SHA_RE.fullmatch(row["head"]), f"PR #{row['number']} head is not a SHA"
    assert rows[416]["state"] == "MERGED"
    assert _SHA_RE.fullmatch(rows[416]["merge_commit"])
    assert rows[357]["state"] == "MERGED"
    assert _SHA_RE.fullmatch(rows[357]["merge_commit"])
    assert rows[421]["state"] == "MERGED"
    assert _SHA_RE.fullmatch(rows[421]["merge_commit"])
    assert rows[350]["state"] == "OPEN_DRAFT"


def test_pr_326_is_recorded_as_unresolved_at_its_current_head() -> None:
    rows = {row["number"]: row for row in _evidence()["pr_archaeology"]}
    row = rows[326]
    assert row["head"] == "b59753a4deab4b7748b2896a518d9532762d8a74"
    assert row["state"] == "OPEN_DRAFT"
    assert row["unresolved"] is True
    assert row["review_classification"] == "FULL_REREVIEW_REQUIRED"
    assert row["effective_delta_paths"] == 10
    review_states = {r["state"] for r in row["reviews"]}
    assert review_states == {"CHANGES_REQUESTED"}
    assert len(row["reviews"]) == 2
    latest = max(row["reviews"], key=lambda r: r["submitted_at"])
    assert latest["id"] == 5103135217
    assert (
        "control_plane/autonomy_control_room_projection.py" in row["owns"]
    ), "PR #326 archaeology must record the derived-status owner"


def test_stale_326_head_would_be_caught() -> None:
    """Discriminator: a stale #326 pin fails.  This asserts the record does not
    contain the superseded head from before the dispatch projection was added."""
    stale_head = "2eb9d23b2f1fc116cd4071c1f4651da9e87366f2"
    rows = {row["number"]: row for row in _evidence()["pr_archaeology"]}
    assert rows[326]["head"] != stale_head
    for path in (RECORD, PLAN, EVIDENCE):
        assert stale_head not in _text(path), f"{path} still pins the stale PR #326 head"


def test_pr_357_agent_dialogue_boundary_is_disjoint_from_h0_and_owner_paths() -> None:
    rows = {row["number"]: row for row in _evidence()["pr_archaeology"]}
    row = rows[357]
    owned = set(_evidence()["collision_census"]["owned_paths"])
    forbidden_or_owner = set(_evidence()["h1_path_ceiling"]["forbidden_paths"]) | {
        p for surface in ("local_p0a", "remote_x1") for p in _string_values(
            _evidence()["owner_boundaries"][surface]
        )
    }
    for path in row["owns"]:
        assert path not in owned, f"PR #357 path collides with an H0 owned path: {path}"
        assert path.startswith("integrations/slack_agent_dialogue/")
    # #357's dialogue modules must themselves be in the H1 forbidden list.
    for path in row["owns"]:
        assert path in _evidence()["h1_path_ceiling"]["forbidden_paths"], (
            f"H1 ceiling fails to forbid Agent Dialogue path {path}"
        )


def test_pr_421_linear_epoch_is_disjoint_from_h0_owned_paths() -> None:
    rows = {row["number"]: row for row in _evidence()["pr_archaeology"]}
    row = rows[421]
    owned = set(_evidence()["collision_census"]["owned_paths"])
    for path in row["owns"]:
        assert path not in owned, f"PR #421 path collides with an H0 owned path: {path}"


def test_derived_status_owner_is_not_on_protected_master() -> None:
    """PR #326's projection is BUILT_NOT_PROVEN precisely because it is unresolved."""
    ledger = _evidence()["capability_ledger"]
    assert ledger["autonomy_responsibility_projection"] == "BUILT_NOT_PROVEN"
    assert not (ROOT / "control_plane" / "autonomy_control_room_projection.py").exists()


# ---------------------------------------------------------------------------
# Linear portfolio — current epoch and the obsolete-epoch discriminator
# ---------------------------------------------------------------------------


def test_linear_portfolio_reports_the_current_epoch() -> None:
    portfolio = _evidence()["linear_portfolio"]
    assert portfolio["initiatives"] == 7
    assert portfolio["projects"] == 65
    assert portfolio["projects_with_one_primary_initiative"] == 63
    assert portfolio["unassigned_exceptions"] == 2
    assert sum(portfolio["group_membership_counts"]) == 63
    assert portfolio["group_membership_counts"] == [10, 17, 11, 6, 4, 8, 7]
    assert "WS:TEMPORAL-GRAIN-INTELLIGENCE" in portfolio["new_membership"]
    assert "runtime, completion, or Hub truth authority" in portfolio["ruling"]


def test_obsolete_linear_epoch_would_be_caught() -> None:
    """Discriminator: an obsolete 64/62 epoch presented as current fails."""
    portfolio = _evidence()["linear_portfolio"]
    assert (portfolio["projects"], portfolio["projects_with_one_primary_initiative"]) != (64, 62)
    for path in (RECORD, EVIDENCE):
        text = _text(path)
        assert "7 Initiatives / 64 Projects / 62 memberships / 2 exceptions" not in text or (
            "prior" in text.lower() or "stale" in text.lower() or "became stale" in text.lower()
        ), f"{path} presents the obsolete 64/62 epoch without marking it superseded"


def test_non_effects_are_declared() -> None:
    non_effects = _evidence()["non_effects"]
    joined = " | ".join(non_effects).lower()
    for claim in (
        "no h1 source",
        "no deployment",
        "no ws:ai-hub created",
        "no agent os write",
        "no linear write",
        "pr #357",
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
