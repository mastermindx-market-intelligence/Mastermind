"""Read-only resource coverage over the existing EVAL ArtifactStore.

Includes invalid, degraded and incomplete runs: unsuccessful work still costs
resources. No scoring, model ranking, acceptance or policy promotion is inferred.
Resource fields are reported observations/estimates, not verified provider bills.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from scripts.agent_eval import contracts
from scripts.agent_eval.canonical import digest_value
from scripts.agent_eval.store import ArtifactStore
from scripts.agent_eval.verification import verify_experiment_graph, verify_run_graph


def _usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    resources = [row["resources"] for row in rows]
    result: dict[str, Any] = {"run_count": len(rows)}
    for field in ("input_tokens", "output_tokens", "tool_calls", "elapsed_ms"):
        known = [item[field] for item in resources if item[field] is not None]
        result[field] = {
            "known_sum": sum(known) if known else None,
            "total": sum(known) if rows and len(known) == len(rows) else None,
            "reported_runs": len(known), "missing_runs": len(rows) - len(known),
        }
    token_rows = [item for item in resources
                  if item["input_tokens"] is not None and item["output_tokens"] is not None]
    result["total_tokens"] = {
        "known_sum_from_complete_runs": sum(item["input_tokens"] + item["output_tokens"]
                                            for item in token_rows) if token_rows else None,
        "total": sum(item["input_tokens"] + item["output_tokens"] for item in token_rows)
        if rows and len(token_rows) == len(rows) else None,
        "reported_runs": len(token_rows), "missing_runs": len(rows) - len(token_rows),
    }
    currencies: dict[str, list[Decimal]] = {}
    cost_missing = 0
    for item in resources:
        value, currency = item["estimated_marginal_cost"], item["cost_currency"]
        if value is None or not currency:
            cost_missing += 1
            continue
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise ValueError("estimated marginal cost must be finite and nonnegative")
        currencies.setdefault(currency, []).append(amount)
    cost_groups = []
    for currency, amounts in sorted(currencies.items()):
        # Preserve exact decimal sums even when the observed values exceed the
        # process's default Decimal precision. Never mix or convert currencies.
        with localcontext() as context:
            context.prec = max(28, sum(len(a.as_tuple().digits) + abs(a.as_tuple().exponent)
                                      for a in amounts) + len(str(len(amounts))) + 2)
            cost_groups.append({"currency": currency, "known_estimated_sum": str(sum(amounts, Decimal(0))),
                                "reported_runs": len(amounts)})
    result["estimated_cost"] = {"by_currency": cost_groups, "missing_runs": cost_missing,
                                "complete_single_currency": bool(rows) and cost_missing == 0 and len(cost_groups) == 1}
    result["provider_usage_reference_runs"] = sum(bool(item["provider_usage_ref"]) for item in resources)
    result["completion_status_counts"] = dict(sorted(Counter(row["execution"]["completion_status"] for row in rows).items()))
    result["validity_status_counts"] = dict(sorted(Counter(row["validity"]["status"] for row in rows).items()))
    return result


def summarize_resources(root: str | Path, experiment_id: str) -> dict[str, Any]:
    """Enumerate the whole existing store once; no caller-selected run subset."""
    contracts.parse_experiment_id(experiment_id)
    source = ArtifactStore(root, create_root=False)
    experiment = source.resolve_experiment(experiment_id)
    if experiment is None:
        raise ValueError("experiment is absent from the existing artifact store")
    verify_experiment_graph(experiment, source)
    population = source.enumerate_runs()
    seen: set[str] = set()
    selected = []
    for run in population:
        if run["run_id"] in seen:
            raise ValueError("duplicate run identity in the complete store enumeration")
        seen.add(run["run_id"])
        if run["comparison"]["experiment_id"] != experiment_id:
            continue
        if source.resolve_run(run["run_id"]) != run:
            raise ValueError("run does not resolve identically at its canonical identity")
        verify_run_graph(run, source)
        selected.append(run)
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for run in selected:
        key = (run["comparison"]["arm_id"], run["configuration"]["configuration_id"],
               run["scenario"]["scenario_id"], str(run["scenario"]["scenario_version"]))
        grouped.setdefault(key, []).append(run)
    return {
        "schema": "mastermind.agent_evaluation_resource_summary.v1",
        "experiment_id": experiment_id, "experiment_digest": experiment["experiment_digest"],
        "verification_scope": "EVALUATION_GRAPH_VERIFIED", "external_content_verified": False,
        "population_scope": "experiment receipts observed by one complete store enumeration",
        "observed_receipts_digest": digest_value([
            {"run_id": run["run_id"], "run_digest": run["run_digest"]} for run in selected
        ]),
        "all_expected_runs_observed": None,
        "summary": _usage(selected),
        "groups": [{"arm_id": key[0], "configuration_id": key[1], "scenario_id": key[2],
                    "scenario_version": key[3], **_usage(rows)} for key, rows in sorted(grouped.items())],
        "cost_per_accepted_outcome": None,
        "limitations": [
            "Completion and technical validity are not independent product acceptance.",
            "Elapsed sums are run-time consumption, not critical-path or wall-clock latency.",
            "Receipt usage may overlap across parents and children; unique billing attribution is not established.",
            "Input plus output tokens are recorded units, not normalized provider-billable tokens.",
            "Unrecorded attempts, parent framing, review and integration remain outside observed coverage.",
            "Usage references and estimated costs do not establish actual billing or subscription quota consumption.",
            "A missing observation is unknown, never zero; no winner or routing recommendation is produced.",
        ],
    }
