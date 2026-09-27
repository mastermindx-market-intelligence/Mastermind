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
    report = ModelRouter.load().explain_route(WorkRequest("implementation", ambiguity="high"))
    assert report["decision"]["mode"] == "frontier_lead"
    assert report["decision"]["worker_eligible"] is False
    assert _rows(report)["frontier.orchestrator"]["source_disposition"] == "FRONTIER_JUDGMENT_ROUTE"
    assert _rows(report)["fast.engineering"]["source_disposition"] == "PRINCIPAL_JUDGMENT_REQUIRED"
    assert report["live_admission"] is False


@pytest.mark.parametrize("aliases", ["glm.flash", [None], [True], ["bad/alias"], ["a"] * 33])
def test_considered_aliases_are_bounded_and_strict(aliases):
    with pytest.raises(RoutingPolicyError):
        ModelRouter.load().explain_route(WorkRequest("tests"), considered_aliases=aliases)


def test_alias_order_is_deterministic_and_disabled_provider_is_source_only():
    router = ModelRouter.load()
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
    assert "Adaptive engineering delegation" in text
    assert "docs/sol_skills/WEB_CEO_DELEGATION.md" in text
    assert "cost per accepted outcome" in text
    assert "Portfolio" in text or "portfolio" in text


def test_source_policy_does_not_hardcode_premium_workers_as_economical():
    text = (ROOT / "docs/sol_skills/WEB_CEO_DELEGATION.md").read_text()
    assert "Adaptive three-level delegation" in text
    assert "WHY_STRONG_EXECUTOR" in text
    assert "admission class" in text
    assert "GLM Flash" in text and "MiniMax" in text
    claude = (ROOT / "CLAUDE.md").read_text()
    assert "Bias toward delegating non-Opus subtasks to Sonnet/Haiku" not in claude
