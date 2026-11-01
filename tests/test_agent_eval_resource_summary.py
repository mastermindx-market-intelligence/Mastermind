"""Exercise the existing ArtifactStore/finalizer, not a parallel run schema."""
import json

import pytest

from tests.agent_eval_factories import (
    REPO_REF_BASE, build_baseline_scenario, build_baseline_configuration,
    build_alternate_configuration, build_two_arm_experiment, build_run_draft,
)
from scripts.agent_eval.store import ArtifactStore
from scripts.agent_eval.validity import finalize_run_receipt
from scripts.agent_eval.resource_summary import summarize_resources
from scripts.fabric_graph_plan import main


@pytest.fixture
def population(tmp_path):
    source = ArtifactStore(tmp_path / "existing-eval")
    scenario = build_baseline_scenario()
    a, b = build_baseline_configuration(), build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, a, b)
    for document in (scenario, a, b, experiment):
        source.create(document)

    def add(*, alternate=False, resources=None, invalid=False):
        config = b if alternate else a
        draft = build_run_draft(scenario, config, experiment,
                                arm_id="arm_b" if alternate else "arm_a", replicate_index=1,
                                model_served="different-model" if invalid else None)
        if resources:
            draft["resources"].update(resources)
        run = finalize_run_receipt(scenario, config, experiment, draft,
                                  validator_id="graph-resource-tests", validator_version="1",
                                  validator_code_ref=REPO_REF_BASE,
                                  validated_at="2026-08-25T00:00:06Z", created_at="2026-08-25T00:00:07Z")
        source.create(run)
        return run

    return source, experiment, add


def test_unknown_usage_and_invalid_runs_are_not_dropped(population):
    source, experiment, add = population
    add()
    add(alternate=True, invalid=True, resources={"input_tokens": None, "estimated_marginal_cost": None})
    before = {str(p): p.read_bytes() for p in source.root.rglob("*") if p.is_file()}
    result = summarize_resources(source.root, experiment["experiment_id"])
    summary = result["summary"]
    assert summary["run_count"] == 2
    assert summary["validity_status_counts"]["INVALID_CONFIGURATION"] == 1
    assert summary["input_tokens"] == {"known_sum": 100, "total": None, "reported_runs": 1, "missing_runs": 1}
    assert summary["total_tokens"]["total"] is None
    assert summary["estimated_cost"]["missing_runs"] == 1
    assert summary["provider_usage_reference_runs"] == 0
    assert result["cost_per_accepted_outcome"] is None
    assert result["external_content_verified"] is False
    assert before == {str(p): p.read_bytes() for p in source.root.rglob("*") if p.is_file()}


def test_complete_zero_is_distinct_from_missing_and_currencies_stay_separate(population):
    source, experiment, add = population
    add(resources={"input_tokens": 0, "output_tokens": 0, "estimated_marginal_cost": "0", "cost_currency": "USD"})
    add(alternate=True, resources={"input_tokens": 0, "output_tokens": 0, "estimated_marginal_cost": "0.1", "cost_currency": "EUR"})
    summary = summarize_resources(source.root, experiment["experiment_id"])["summary"]
    assert summary["total_tokens"]["total"] == 0
    assert summary["estimated_cost"]["complete_single_currency"] is False
    assert [item["currency"] for item in summary["estimated_cost"]["by_currency"]] == ["EUR", "USD"]


def test_empty_observations_do_not_report_zero_cost(population):
    source, experiment, _ = population
    result = summarize_resources(source.root, experiment["experiment_id"])
    assert result["summary"]["run_count"] == 0
    assert result["summary"]["input_tokens"]["total"] is None
    assert result["summary"]["estimated_cost"]["complete_single_currency"] is False
    assert result["all_expected_runs_observed"] is None


def test_real_cli_never_creates_a_missing_store(tmp_path, capsys):
    missing = tmp_path / "absent"
    code = main(["resources", "--root", str(missing), "--experiment-id", "experiment:11111111-1111-4111-8111-111111111111"])
    assert code == 2 and not missing.exists()
    assert json.loads(capsys.readouterr().out)["runtime_changed"] is False


def test_real_cli_consumes_existing_verified_population(population, capsys):
    source, experiment, add = population
    add()
    assert main(["resources", "--root", str(source.root), "--experiment-id", experiment["experiment_id"]]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["total_tokens"]["total"] == 300
    assert result["verification_scope"] == "EVALUATION_GRAPH_VERIFIED"


def test_negative_cost_is_rejected_as_bad_economic_input(population):
    source, experiment, add = population
    add(resources={"estimated_marginal_cost": "-1"})
    with pytest.raises(ValueError, match="nonnegative"):
        summarize_resources(source.root, experiment["experiment_id"])


def test_decimal_cost_is_not_rounded_by_float_or_default_precision(population):
    source, experiment, add = population
    a = "123456789012345678901234567890.123456789"
    add(resources={"estimated_marginal_cost": a})
    add(alternate=True, resources={"estimated_marginal_cost": "0.000000001"})
    cost = summarize_resources(source.root, experiment["experiment_id"])["summary"]["estimated_cost"]
    assert cost["by_currency"][0]["known_estimated_sum"] == "123456789012345678901234567890.123456790"


def test_duplicate_receipts_cannot_inflate_consumption(population):
    source, experiment, add = population
    run = add()
    original = next(p for p in (source.root / "runs").rglob("receipt.json") if run["run_id"] in p.read_text())
    duplicate = source.root / "runs" / "duplicate" / "receipt.json"
    duplicate.parent.mkdir()
    duplicate.write_bytes(original.read_bytes())
    with pytest.raises(ValueError):
        summarize_resources(source.root, experiment["experiment_id"])


def test_single_mislocated_receipt_cannot_claim_verified_population(population):
    source, experiment, add = population
    run = add()
    original = next(p for p in (source.root / "runs").rglob("receipt.json") if run["run_id"] in p.read_text())
    wrong = source.root / "runs" / "mislocated" / "receipt.json"
    wrong.parent.mkdir()
    original.rename(wrong)
    with pytest.raises(ValueError, match="canonical identity"):
        summarize_resources(source.root, experiment["experiment_id"])
