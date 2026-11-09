"""Source-only economics explanations; no provider or runtime admission."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.model_router import DEFAULT_POLICY_PATH, ModelRouter, RoutingPolicyError, WorkRequest
from scripts.executive_os_phase1b import main as cli_main

ROOT = Path(__file__).resolve().parents[1]


def _rows(report):
    return {row["model_alias"]: row for row in report["aliases"]}


def _router(tmp_path, mutate):
    raw = json.loads(DEFAULT_POLICY_PATH.read_text())
    mutate(raw)
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(raw))
    return ModelRouter.load(path)


def test_explanation_preserves_decision_and_never_claims_economics():
    router = ModelRouter.load()
    request = WorkRequest("implementation", excluded_worker_ids=("builder-1",))
    report = router.explain_route(request)
    assert report["schema"] == "mastermind.model_route_explanation/v1"
    assert report["decision"] == router.route(request).to_dict()
    assert report["authority"] == "NONE_SOURCE_PREVIEW_ONLY"
    assert report["live_admission"] is False
    assert report["runtime_observation"] == "NOT_PERFORMED"
    assert report["economic_comparison"] == "NOT_PERFORMED"
    assert report["selected_worker"] is None
    rows = _rows(report)
    assert rows["fast.engineering"]["source_disposition"] == "FIRST_LAWFUL_TIER"
    assert rows["standard.engineering"]["source_disposition"] == "FIRST_LAWFUL_TIER"
    assert rows["frontier.orchestrator"]["source_disposition"] == "NOT_WORKER_ELIGIBLE"
    assert rows["fast.research"]["source_disposition"] == "MISSING_REQUIRED_CAPABILITIES"
    assert rows["coo.sealed"]["source_disposition"] == "NOT_IN_TASK_ROUTE"
    assert all(row["measured_cost"] is None for row in rows.values())
    assert report["decision"]["excluded_worker_ids"] == ["builder-1"]


def test_absent_alias_is_not_enrolled_or_silently_omitted():
    report = ModelRouter.load().explain_route(WorkRequest("tests"), considered_aliases=("glm.flash",))
    row = _rows(report)["glm.flash"]
    assert row["source_disposition"] == "NOT_CONFIGURED"
    assert row["configured"] is False and row["model"] is None
    assert row["admission_cost_class"] is None and row["measured_cost"] is None


def test_later_tier_is_explained_but_never_promoted(tmp_path):
    def mutate(raw):
        raw["routes"]["implementation"]["routine"].append({
            "tier_id": "implementation.routine.fallback", "model_aliases": ["coo.sealed"]
        })
    router = _router(tmp_path, mutate)
    before = router.route(WorkRequest("implementation")).job_constraints()
    report = router.explain_route(WorkRequest("implementation"))
    assert _rows(report)["coo.sealed"]["source_disposition"] == "LATER_SUITABILITY_TIER"
    assert report["decision"]["preferred_model_aliases"] == ["fast.engineering", "standard.engineering"]
    assert router.route(WorkRequest("implementation")).job_constraints() == before


def test_admission_class_and_fast_name_are_not_price_evidence(tmp_path):
    def mutate(raw):
        raw["model_aliases"]["fast.engineering"]["model"] = "gpt-5.6-sol"
    report = _router(tmp_path, mutate).explain_route(WorkRequest("mechanical"))
    row = _rows(report)["fast.engineering"]
    assert row["model"] == "gpt-5.6-sol"
    assert row["admission_cost_class"] == "small"
    assert row["measured_cost"] is None
    assert report["economic_comparison"] == "NOT_PERFORMED"


def test_principal_judgment_does_not_become_worker_admission():
    # OQ-8 (WO-06): the principal-judgment lane is a lead task_kind; critical
    # risk / high ambiguity no longer inflate worker cognition into it.
    report = ModelRouter.load().explain_route(WorkRequest("planning"))
    assert report["decision"]["mode"] == "frontier_lead"
    assert report["decision"]["worker_eligible"] is False
    assert _rows(report)["frontier.orchestrator"]["source_disposition"] == "FRONTIER_JUDGMENT_ROUTE"
    assert _rows(report)["fast.engineering"]["source_disposition"] == "PRINCIPAL_JUDGMENT_REQUIRED"
    assert report["live_admission"] is False


@pytest.mark.parametrize("aliases", ["glm.flash", [None], [True], ["bad/alias"], ["a"] * 33])
def test_considered_aliases_are_bounded_and_strict(aliases):
    with pytest.raises(RoutingPolicyError):
        ModelRouter.load().explain_route(WorkRequest("tests"), considered_aliases=aliases)


def test_alias_order_is_deterministic_and_disabled_provider_is_source_only(tmp_path):
    def disable_glm(raw):
        raw["providers"]["glm"]["enabled"] = False
        raw["providers"]["glm"]["autonomous_allowed"] = False
        for profile in raw["model_aliases"].values():
            if profile["provider_alias"] == "glm":
                profile["worker_eligible"] = False
    router = _router(tmp_path, disable_glm)
    one = router.explain_route(WorkRequest("research"), considered_aliases=("z.flash", "a.flash"))
    two = router.explain_route(WorkRequest("research"), considered_aliases=("a.flash", "z.flash", "a.flash"))
    assert one == two
    assert [row["model_alias"] for row in one["aliases"]] == sorted(_rows(one))
    providers = {row["provider_alias"]: row for row in one["providers"]}
    assert providers["glm"]["enabled_in_source"] is False
    assert providers["glm"]["live_readiness"] == "NOT_OBSERVED"


def test_explain_cli_is_read_only_and_legacy_output_is_unchanged(tmp_path, capsys, monkeypatch):
    import scripts.executive_os_phase1b as module
    def forbidden(*args, **kwargs):
        raise AssertionError("route explanation must not open Runtime")
    monkeypatch.setattr(module.Runtime, "at", forbidden)
    root = tmp_path / "never-created"
    assert cli_main(["--root", str(root), "route", "tests"]) == 0
    legacy = json.loads(capsys.readouterr().out)
    assert legacy == ModelRouter.load().route(WorkRequest("tests")).to_dict()
    assert cli_main(["--root", str(root), "route", "tests", "--explain",
                     "--consider-model-alias", "glm.flash"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["decision"] == legacy
    assert _rows(report)["glm.flash"]["source_disposition"] == "NOT_CONFIGURED"
    assert not root.exists()


def test_consider_alias_without_explain_refuses_before_runtime(tmp_path, capsys, monkeypatch):
    import scripts.executive_os_phase1b as module
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid preview must not open Runtime")
    monkeypatch.setattr(module.Runtime, "at", forbidden)
    assert cli_main(["--root", str(tmp_path / "absent"), "route", "tests",
                     "--consider-model-alias", "glm.flash"]) == 2
    captured = capsys.readouterr()
    assert "requires --explain" in captured.err


@pytest.mark.parametrize("name", ["AGENTS.md", "CLAUDE.md"])
def test_engineering_entrypoints_share_adaptive_economics_policy(name):
    text = (ROOT / name).read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    assert "docs/sol_skills/WEB_CEO_DELEGATION.md" in agents
    assert "Assigned Codex/Claude Meta-CEO: paid Fabric delegation first" in agents
    if name == "CLAUDE.md":
        assert "`AGENTS.md`" in text
        assert "Prefer economical qualified Fabric workers for separable work." in text
        assert "Portfolio model tiers" in text
    assert "Portfolio" in text or "portfolio" in text


def test_source_policy_does_not_hardcode_premium_workers_as_economical():
    text = " ".join((ROOT / "docs/sol_skills/WEB_CEO_DELEGATION.md").read_text().split())
    assert "Quality and accepted-result cost outrank nominal token or agent-count savings." in text
    assert "Choose the shallowest capable route;" in text
    assert "Model Router fixes the first lawful suitability tier;" in text
    assert "eligible candidates within it by least cost/scarcity." in text
    assert "unknown quota/proof/budget stays unknown." in text
    addendum = " ".join((ROOT / "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md").read_text().split())
    assert "lowest-marginal-cost / least-scarce route" in addendum
    assert "when whole-cycle cost improves." in addendum
    claude = (ROOT / "CLAUDE.md").read_text()
    assert "Bias toward delegating non-Opus subtasks to Sonnet/Haiku" not in claude


def test_current_provider_source_and_responsibility_are_preserved_without_live_claims():
    router = ModelRouter.load()
    raw = json.loads(DEFAULT_POLICY_PATH.read_text())
    intent = {
        "schema_version": "mastermind.responsibility_intent/v1",
        "responsibility_role": "worker",
        "execution_mode": "execute",
    }
    request = WorkRequest("implementation", responsibility_intent=intent)
    decision = router.route(request).to_dict()
    report = router.explain_route(request)
    assert report["decision"] == decision
    assert report["decision"]["responsibility_intent"] == intent
    assert report["decision"]["responsibility_intent_digest"] == request.responsibility_intent.digest
    providers = {row["provider_alias"]: row for row in report["providers"]}
    assert set(providers) == set(raw["providers"])
    for alias, source in raw["providers"].items():
        assert providers[alias]["enabled_in_source"] is source["enabled"]
        assert providers[alias]["autonomous_allowed_in_source"] is source["autonomous_allowed"]
        assert providers[alias]["live_readiness"] == "NOT_OBSERVED"
    assert providers["glm"]["enabled_in_source"] is True
    assert report["authority"] == "NONE_SOURCE_PREVIEW_ONLY"
    assert report["runtime_observation"] == "NOT_PERFORMED"
    assert report["economic_comparison"] == "NOT_PERFORMED"
    assert report["selected_worker"] is None
    assert report["live_admission"] is False
    assert all(row["measured_cost"] is None for row in report["aliases"])


# --- WO-07 route_preview: shared-law composition (MMOS V1) ------------------
#
# The Executive MCP route_preview composes this module's explain_route source
# economics with the WO-02 shared law and host-configured owner observations.
# It stays source-only: the assertions below pin NONE_SOURCE_PREVIEW_ONLY,
# the capacity-knowledge honesty ladder and zero runtime row changes.

import sqlite3

from integrations.executive_mcp.route_preview import (
    ROUTE_PREVIEW_TOOL_NAME,
    ROUTE_PREVIEW_TOOL_SPEC,
    TOOL_AMBIGUITIES,
    TOOL_RISKS,
    TOOL_TASK_KINDS,
    RoutePreviewSource,
    compose,
    validate_route_preview_tool_arguments,
)
from integrations.executive_mcp.schemas import GatewayError


def test_route_preview_vocabularies_mirror_model_router_exactly():
    from control_plane import model_router

    assert TOOL_TASK_KINDS == model_router._WORKER_TASKS | model_router._LEAD_TASKS
    assert set(TOOL_RISKS) == set(model_router._RISKS)
    assert set(TOOL_AMBIGUITIES) == set(model_router._AMBIGUITIES)
    assert ROUTE_PREVIEW_TOOL_SPEC.read_only is True
    assert ROUTE_PREVIEW_TOOL_SPEC.annotations["readOnlyHint"] is True


def test_route_preview_is_always_none_source_preview_only():
    from control_plane.child_execution_contracts import RoutePreview

    record = compose({"route_option": "routine", "goal": "Implement a bounded module"})
    assert record["schema"] == "RoutePreview.v1"
    assert record["authority"] == "NONE_SOURCE_PREVIEW_ONLY"
    assert record["production_armed"] is False
    assert record["requested_complexity"] == "C1_ROUTINE_BOUNDED"
    assert record["effective_complexity"] == "C1_ROUTINE_BOUNDED"
    assert record["witness_disposition"] == "not_required"
    assert record["suitability_tiers"] == ["implementation.routine.primary"]
    assert record["candidate_reason_codes"]
    # With no observations the honesty fields degrade, never guess.
    assert record["capacity_knowledge"] == "unknown"
    assert record["rank_basis"] == "suitability_only"
    assert record["observed_at"] == "" and record["expires_at"] == ""
    # Distinct identities: a preview is not a decision or an attempt.
    assert record["decision_id"] == "" and record["attempt_ref"] == ""
    assert record["request_digest"] != record["preview_id"]
    # The record round-trips through the shared contract unchanged.
    assert RoutePreview.from_dict(record).to_dict() == record


def test_route_preview_frontier_witness_gate_matches_the_shared_law():
    witnessed = compose({
        "route_option": "frontier", "goal": "cognition lane",
        "context": "witness: unresolved cross-system carrier contract left open",
    })
    assert witnessed["witness_disposition"] == "accepted"
    assert witnessed["requested_complexity"] == "C3_FRONTIER_JUDGMENT"
    assert witnessed["effective_complexity"] == "C3_FRONTIER_JUDGMENT"
    downgraded = compose({"route_option": "frontier", "goal": "make it big and critical"})
    assert downgraded["requested_complexity"] == "C3_FRONTIER_JUDGMENT"
    assert downgraded["effective_complexity"] == "C2_COMPLEX_BOUNDED"
    assert downgraded["witness_disposition"] == "downgraded"


def _observation_files(tmp_path, *, with_host=True, with_registry=True, with_quota=True):
    paths = {}
    if with_host:
        host = tmp_path / "host.json"
        host.write_text(json.dumps({
            "schema": "mastermind.host_readiness_snapshot/v1",
            "host_id": "m1-studio", "collected_at": "2026-11-08T14:18:56Z",
        }))
        paths["host"] = str(host)
    if with_registry:
        registry = tmp_path / "registry.json"
        registry.write_text(json.dumps({
            "schema": "mastermind.owner_ext_registry_projection/v1",
            "registry_revision": "14259ca43e427ab28c65cb457449c909c8d3bd6862e03103cf1f6e9d504dc751",
            "produced_at": "2026-11-08T14:18:20Z",
        }))
        paths["registry"] = str(registry)
    if with_quota:
        quota = tmp_path / "quota.json"
        quota.write_text(json.dumps({
            "schema": "mastermind.quota_economics_preview/v1",
            "observed_at": "2026-11-08T14:20:00Z",
        }))
        paths["quota"] = str(quota)
    return paths


def _source(paths):
    return RoutePreviewSource(
        host_snapshot_paths=(paths["host"],) if "host" in paths else (),
        registry_projection_path=paths.get("registry"),
        quota_preview_path=paths.get("quota"),
    )


def test_route_preview_capacity_ladder_reads_owner_observations(tmp_path):
    arguments = {"route_option": "routine", "goal": "Implement a bounded module"}
    # WO-04 host snapshots alone: observed hosts, but ranking stays suitability.
    record = compose(arguments, source=_source(_observation_files(
        tmp_path, with_registry=False, with_quota=False)))
    assert record["capacity_knowledge"] == "observed"
    assert record["rank_basis"] == "suitability_only"
    assert record["observation_refs"] == ["wo04:m1-studio"]
    assert record["observed_at"] == "2026-11-08T14:18:56Z"
    assert record["expires_at"] == "2026-11-08T14:33:56Z"
    # Adding the WO-03 registry projection pins the registry revision.
    record = compose(arguments, source=_source(_observation_files(
        tmp_path, with_quota=False)))
    assert record["registry_revision"] == (
        "14259ca43e427ab28c65cb457449c909c8d3bd6862e03103cf1f6e9d504dc751")
    assert "wo03:14259ca43e427ab2" in record["observation_refs"]
    # A WO-09 quota preview is the only source that upgrades the rank basis.
    record = compose(arguments, source=_source(_observation_files(tmp_path)))
    assert record["capacity_knowledge"] == "observed"
    assert record["rank_basis"] == "observed_headroom"
    assert any(ref.startswith("wo09:") for ref in record["observation_refs"])


def test_route_preview_sanitized_or_missing_observations_degrade_honestly(tmp_path):
    arguments = {"route_option": "routine", "goal": "Implement a bounded module"}
    # The distributed WO-03 artifact redacts its revision token: the schema
    # still evidences configured ceilings (configured_only), without a pin.
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "schema": "mastermind.owner_ext_registry_projection/v1",
        "registry_revision": "<REDACTED:long-token-shaped>",
        "produced_at": "2026-11-08T14:18:20Z",
    }))
    record = compose(arguments, source=RoutePreviewSource(
        registry_projection_path=str(registry)))
    assert record["capacity_knowledge"] == "configured_only"
    assert record["rank_basis"] == "suitability_only"
    assert record["registry_revision"] == ""
    assert "wo03:sanitized" in record["observation_refs"]
    # Missing, oversized or wrong-schema files contribute nothing at all.
    missing = RoutePreviewSource(
        host_snapshot_paths=(str(tmp_path / "absent.json"),),
        registry_projection_path=str(tmp_path / "absent2.json"),
        quota_preview_path=str(tmp_path / "absent3.json"))
    record = compose(arguments, source=missing)
    assert record["capacity_knowledge"] == "unknown"
    assert record["rank_basis"] == "suitability_only"
    assert record["observation_refs"] == []
    oversized = tmp_path / "big.json"
    oversized.write_text("x" * 262145)
    record = compose(arguments, source=RoutePreviewSource(
        host_snapshot_paths=(str(oversized),)))
    assert record["capacity_knowledge"] == "unknown"


def test_route_preview_arguments_are_closed_and_bounded():
    valid = {"route_option": "hard", "goal": "bounded multi-file refactor",
             "context": "module map", "task_kind": "implementation",
             "risk": "elevated", "ambiguity": "medium",
             "required_capabilities": ["tests", "review"]}
    assert validate_route_preview_tool_arguments(
        ROUTE_PREVIEW_TOOL_NAME, valid) == {
            "route_option": "hard", "goal": "bounded multi-file refactor",
            "context": "module map", "task_kind": "implementation",
            "risk": "elevated", "ambiguity": "medium",
            "required_capabilities": ["tests", "review"]}
    assert validate_route_preview_tool_arguments(
        ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "g"})["task_kind"] is None
    bad = [
        ("wrong tool name", lambda: validate_route_preview_tool_arguments(
            "fabric_route_preview", {"route_option": "routine", "goal": "g"})),
        ("unknown argument", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "g", "pool": "p"})),
        ("unknown lane", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "domain_orchestration", "goal": "g"})),
        ("empty goal", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "   "})),
        ("oversized goal", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "x" * 4001})),
        ("bad task kind", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "g", "task_kind": "execute"})),
        ("bad risk", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "g", "risk": "existential"})),
        ("non-string capability", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "g",
                                      "required_capabilities": [7]})),
        ("too many capabilities", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, {"route_option": "routine", "goal": "g",
                                      "required_capabilities": [f"c{n}" for n in range(9)]})),
        ("non-object arguments", lambda: validate_route_preview_tool_arguments(
            ROUTE_PREVIEW_TOOL_NAME, ["routine"]),
         ),
    ]
    for name, call in bad:
        with pytest.raises(GatewayError):
            call()
    with pytest.raises(GatewayError):
        compose({"route_option": "routine", "goal": "g", "task_kind": "execute"})


def test_route_preview_call_changes_no_runtime_rows(tmp_path):
    from control_plane.executive_runtime import Runtime

    runtime = Runtime.at(tmp_path)
    database = tmp_path / "data" / "control_plane" / "executive.sqlite3"

    def counts():
        with sqlite3.connect(database) as connection:
            return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("jobs", "attempts", "worker_quota_classes"))

    assert counts() == (0, 0, 0)
    for _ in range(3):
        compose({"route_option": "hard", "goal": "bounded multi-file refactor"})
    assert counts() == (0, 0, 0)
