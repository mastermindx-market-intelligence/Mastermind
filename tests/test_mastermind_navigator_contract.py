from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest



ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plugins/mastermind-navigator"
EXPECTED_FILES = {
    ".codex-plugin/plugin.json",
    "fixtures/capability-health-cases.json",
    "fixtures/fresh-session-routing-cases.json",
    "references/boot-sources.json",
    "references/capability-health.schema.json",
    "references/capability-state-rules.json",
    "references/catalog.fragment.json",
    "references/navigator-boundary.md",
    "references/owner-routing.json",
    "references/role-profiles.json",
    "skills/navigate-mastermind-universe/SKILL.md",
}
REQUIRED_ROUTE_OWNERS = {
    "lifecycle": ("Executive OS", "executive-os"),
    "organizational_continuity": ("Agent OS", "agent-os"),
    "source_pr_ci": ("GitHub", "github"),
    "selected_project_action": ("Workbench", "workbench"),
    "local_machine_process": ("Studio Direct / existing fleet owner", "studio-direct"),
    "worker_browser": ("Worker Browser", "worker-browser"),
    "exact_chatgpt_actuation": ("Web-Sol + RuntimeBinding", "web-sol-runtime-binding"),
    "domain_deploy": ("domain owner", "domain-deploy-owner"),
    "domain_data": ("domain owner", "domain-data-owner"),
    "domain_design": ("domain owner", "domain-design-owner"),
    "domain_comms": ("domain owner", "domain-comms-owner"),
}
REQUIRED_PROFILES = {
    "web_ceo_core",
    "native_builder_operator",
    "browser_provider_operator",
}
REQUIRED_OVERLAYS = {
    "domain_deploy",
    "domain_data",
    "domain_design",
    "domain_comms",
}
DIMENSIONS = (
    "installed",
    "enabled",
    "authenticated_or_connected",
    "callable",
    "organizationally_authorized",
    "proven_live",
)


def _load(relative: str) -> object:
    return json.loads((PACKAGE / relative).read_text(encoding="utf-8"))


def _materialize_health_packet(packet: object) -> dict[str, object]:
    encoded = json.dumps(packet).replace("FIXTURE_PROTECTED_MASTER_SHA", "a" * 40)
    materialized = json.loads(encoded)
    assert isinstance(materialized, dict)
    return materialized


def _package_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.rglob("*"))
        if path.is_file()
    )


def _derive_state(facts: dict[str, object], rules: dict[str, object]) -> str:
    ordered = rules["ordered_rules"]
    assert isinstance(ordered, list)
    for rule in ordered:
        assert isinstance(rule, dict)
        when = rule["when"]
        assert isinstance(when, dict)
        all_values = when.get("all")
        any_values = when.get("any")
        none_values = when.get("none")
        if all_values is not None and not all(
            facts.get(item["field"]) == item["equals"] for item in all_values
        ):
            continue
        if any_values is not None and not any(
            facts.get(item["field"]) == item["equals"] for item in any_values
        ):
            continue
        if none_values is not None and any(
            facts.get(item["field"]) == item["equals"] for item in none_values
        ):
            continue
        return str(rule["state"])
    raise AssertionError("capability state rules are not total")


def test_navigator_package_has_the_closed_isolated_inventory() -> None:
    actual = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file()
    }
    assert actual == EXPECTED_FILES


def test_manifest_declares_one_read_only_navigation_skill() -> None:
    manifest = _load(".codex-plugin/plugin.json")
    assert manifest == {
        "name": "mastermind-navigator",
        "version": "0.1.0",
        "description": (
            "Role-scoped, owner-preserving navigation from a fresh Mastermind session "
            "to the smallest currently evidenced operator surface."
        ),
        "author": {"name": "Mastermind-X"},
        "skills": "./skills/",
        "interface": {
            "displayName": "Mastermind Navigator",
            "shortDescription": "Find the current owner and smallest proven surface",
            "longDescription": (
                "Compose current owner-native capability observations into an honest "
                "role-filtered health view, then route one bounded action without "
                "creating lifecycle, permission, session, or capability authority."
            ),
            "developerName": "Mastermind-X",
            "category": "Productivity",
            "capabilities": ["Read"],
        },
    }


def test_owner_routing_covers_every_required_fresh_session_case() -> None:
    document = _load("references/owner-routing.json")
    assert document["schema"] == "mastermind.navigator_owner_routing.v1"
    routes = document["routes"]
    assert isinstance(routes, list)
    by_class = {route["capability_class"]: route for route in routes}
    assert REQUIRED_ROUTE_OWNERS.keys() <= by_class.keys()

    for capability_class, (owner, tool_family) in REQUIRED_ROUTE_OWNERS.items():
        route = by_class[capability_class]
        assert route["canonical_owner"] == owner
        assert route["minimal_tool_family"] == tool_family
        assert route["owner_native_probe"]
        assert route["binding_requirements"]
        assert route["forbidden_substitutions"]
        assert route["static_liveness_claim"] is False

    project_route = by_class["selected_project_action"]
    assert project_route["read_fallback_owner"] == "Workbench Read"
    assert project_route["action_requires_separate_proof"] is True
    assert project_route["action_binding_requirements"] == [
        "owner-admitted execution mode",
        "authenticated subject or approved native context",
        "exact current session generation or Executive Job/Attempt/Worker generation",
        "owner-issued target context",
        "current policy and capability generation",
        "expiry and revocation state",
        "current selected-project binding",
    ]
    assert project_route["attended_mode_owner"] == "current session and RuntimeBinding owners"
    assert project_route["worker_mode_owner"] == "Executive OS Job/Attempt/Worker"
    assert by_class["exact_chatgpt_actuation"]["binding_requirements"] == [
        "authenticated subject",
        "exact conversation or session identity",
        "current RuntimeBinding generation",
        "owner-issued target context",
        "current authorization",
    ]


def test_role_profiles_are_closed_and_discover_only_minimal_tool_families() -> None:
    document = _load("references/role-profiles.json")
    assert document["schema"] == "mastermind.navigator_role_profiles.v1"
    assert document["schema_loading_policy"] == "DISCOVER_MINIMAL_TOOL_FAMILY_ONLY"
    assert document["package_name_is_capability_evidence"] is False
    assert document["load_every_connector_by_default"] is False

    profiles = document["profiles"]
    overlays = document["domain_overlays"]
    assert document["health_observation_does_not_load_schema"] is True
    assert set(profiles) == REQUIRED_PROFILES
    assert profiles["web_ceo_core"]["default_routes"] == [
        "lifecycle",
        "organizational_continuity",
        "source_pr_ci",
        "selected_project_action",
        "local_machine_process",
        "worker_browser",
        "exact_chatgpt_actuation",
    ]
    assert set(overlays) == REQUIRED_OVERLAYS
    for profile in profiles.values():
        assert profile["default_routes"]
        assert len(profile["default_routes"]) == len(set(profile["default_routes"]))
        assert set(profile["default_routes"]).isdisjoint(profile["on_demand_routes"])
        assert profile["authority_source"] == "existing owner records only"
    for overlay_id, overlay in overlays.items():
        assert overlay["route"] == overlay_id
        assert overlay["activation"] == "explicit task need plus current authorization"
        assert overlay["grants_authority"] is False


def test_health_schema_is_closed_and_accepts_only_source_attributed_observations() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load("references/capability-health.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)

    fixture = _load("fixtures/capability-health-cases.json")
    validator = jsonschema.Draft202012Validator(schema)
    for case in fixture["cases"]:
        packet = _materialize_health_packet(case["packet"])
        validator.validate(packet)
        surface = packet["surfaces"][0]
        assert tuple(surface[dimension] for dimension in DIMENSIONS)
        assert surface["evidence"]
        assert surface["blocker"] is not None or surface["state"] == "PROVEN_LIVE"
        assert surface["next_probe"] is not None or surface["state"] == "PROVEN_LIVE"

    hostile = _materialize_health_packet(fixture["cases"][0]["packet"])
    hostile["surfaces"][0]["secret"] = "do-not-accept"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(hostile)

    missing_evidence = _materialize_health_packet(fixture["cases"][0]["packet"])
    missing_evidence["surfaces"][0]["evidence"] = []
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(missing_evidence)


def test_capability_state_rules_are_total_and_discriminate_live_degraded_unavailable_unknown() -> None:
    rules = _load("references/capability-state-rules.json")
    fixture = _load("fixtures/capability-health-cases.json")
    assert rules["schema"] == "mastermind.navigator_capability_state_rules.v1"
    assert rules["dimensions"] == list(DIMENSIONS)
    assert [rule["state"] for rule in rules["ordered_rules"]] == [
        "PROVEN_LIVE",
        "UNAVAILABLE",
        "BUILT_NOT_PROVEN",
        "DEGRADED",
        "UNKNOWN",
    ]
    assert rules["unknown_never_promotes"] is True
    assert rules["package_name_never_promotes"] is True

    observed_states = set()
    for case in fixture["cases"]:
        surface = case["packet"]["surfaces"][0]
        derived = _derive_state(surface, rules)
        assert derived == surface["state"] == case["expected_state"]
        observed_states.add(derived)
    assert observed_states == {
        "PROVEN_LIVE",
        "UNAVAILABLE",
        "BUILT_NOT_PROVEN",
        "DEGRADED",
        "UNKNOWN",
    }


def test_role_filtered_health_composition_suppresses_irrelevant_surfaces() -> None:
    fixture = _load("fixtures/capability-health-cases.json")
    composition = fixture["role_filter_case"]
    profiles = _load("references/role-profiles.json")["profiles"]
    profile = profiles[composition["profile"]]
    allowed_routes = set(profile["default_routes"]) | {composition["requested_route"]}
    visible = [
        surface["surface_id"]
        for surface in composition["source_surfaces"]
        if surface["capability_class"] in allowed_routes
    ]
    suppressed = [
        surface["surface_id"]
        for surface in composition["source_surfaces"]
        if surface["capability_class"] not in allowed_routes
    ]
    assert visible == composition["expected_visible_surface_ids"]
    assert suppressed == composition["expected_suppressed_surface_ids"]
    assert composition["load_schemas_for"] == [composition["expected_selected_tool_family"]]


def test_fresh_session_cases_route_to_one_owner_native_surface() -> None:
    fixture = _load("fixtures/fresh-session-routing-cases.json")
    routing = _load("references/owner-routing.json")
    by_class = {route["capability_class"]: route for route in routing["routes"]}
    assert fixture["schema"] == "mastermind.navigator_fresh_session_cases.v1"
    assert len(fixture["cases"]) >= 8
    case_ids = {case["id"] for case in fixture["cases"]}
    assert {
        "lifecycle-to-executive-os",
        "continuity-to-agent-os",
        "source-pr-ci-to-github",
        "selected-project-action-to-workbench",
        "local-process-to-studio-direct",
        "worker-browser-to-worker-browser",
        "exact-chatgpt-actuation-to-web-sol-runtime-binding",
        "domain-work-to-domain-owner",
    } <= case_ids
    for case in fixture["cases"]:
        route = by_class[case["capability_class"]]
        assert case["expected_owner"] == route["canonical_owner"]
        assert case["expected_tool_family"] == route["minimal_tool_family"]
        assert case["expected_schema_loads"] == [route["minimal_tool_family"]]
        assert case["owner_native_action"]
        assert case["does_not_claim_live_before_probe"] is True


def test_boot_sources_compose_existing_owners_without_replacing_them() -> None:
    document = _load("references/boot-sources.json")
    assert document["schema"] == "mastermind.navigator_boot_sources.v1"
    sources = {source["source_id"]: source for source in document["sources"]}
    assert {
        "protected-master-skillpack",
        "ceo-boot-packet",
        "executive-steward-health",
        "surface-bindings-navigation",
        "runtime-binding-target",
    } <= sources.keys()
    assert sources["ceo-boot-packet"]["source_coordinate"] == "control_plane.ceo_boot_packet"
    assert sources["executive-steward-health"]["source_coordinate"] == "control_plane.executive_steward"
    assert sources["surface-bindings-navigation"]["source_coordinate"] == "control_plane.surface_bindings"
    assert sources["surface-bindings-navigation"]["authority_ceiling"] == "navigation only; not session authority"
    for source in sources.values():
        assert source["consumption"] == "read-only"
        assert source["navigator_becomes_owner"] is False


def test_skill_requires_current_evidence_and_one_smallest_owner_native_action() -> None:
    skill = (PACKAGE / "skills/navigate-mastermind-universe/SKILL.md").read_text(encoding="utf-8")
    required_phrases = (
        "Read protected Mastermind `master`",
        "docs/sol_skills/INDEX.md",
        "existing owner-native observations",
        "plugin name is not evidence",
        "installed",
        "enabled",
        "authenticated or connected",
        "callable",
        "organizationally authorized",
        "PROVEN_LIVE",
        "DEGRADED",
        "UNAVAILABLE",
        "UNKNOWN",
        "Do not load every connector or tool schema",
        "Health observation does not load a tool schema",
        "owner-admitted execution mode",
        "exact current session generation or Executive Job/Attempt/Worker generation",
        "smallest role-appropriate tool family",
        "one owner-native action",
        "EFFECT_UNKNOWN",
    )
    for phrase in required_phrases:
        assert phrase in skill
    for reference in (
        "../../references/navigator-boundary.md",
        "../../references/owner-routing.json",
        "../../references/role-profiles.json",
        "../../references/boot-sources.json",
        "../../references/capability-health.schema.json",
        "../../references/capability-state-rules.json",
    ):
        assert reference in skill


def test_catalog_fragment_is_package_local_and_requires_shared_owner_admission() -> None:
    fragment = _load("references/catalog.fragment.json")
    assert fragment == {
        "schema": "mastermind.navigator_catalog_fragment.v1",
        "plugin": "mastermind-navigator",
        "package_path": "plugins/mastermind-navigator",
        "manifest_path": "plugins/mastermind-navigator/.codex-plugin/plugin.json",
        "skills": ["navigate-mastermind-universe"],
        "capabilities": ["Read"],
        "source_state": "SOURCE_CANDIDATE",
        "installation_state": "NOT_INSTALLED",
        "shared_owner_action": "ADMIT_PACKAGE_AND_CATALOG_FRAGMENT",
    }


def test_package_contains_no_lifecycle_permission_registry_or_static_live_claim() -> None:
    text = _package_text().lower()
    forbidden = (
        "create a new lifecycle",
        "navigator is the authority",
        "capability registry of record",
        "session registry of record",
        "navigator grants permission authority",
        "all tools are live",
        "navigator provides an omnipotent mastermind mcp",
    )
    assert not any(phrase in text for phrase in forbidden)
    boundary = (PACKAGE / "references/navigator-boundary.md").read_text(encoding="utf-8")
    for phrase in (
        "No truth database",
        "No lifecycle",
        "No capability registry",
        "No permission authority",
        "No session registry",
        "No static liveness list",
        "No omnipotent Mastermind MCP",
    ):
        assert phrase in boundary
