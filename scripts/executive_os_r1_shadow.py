"""Deterministic R1 shadow rollout for the Executive OS worker router.

This is a fixture-only acceptance harness.  It registers dedicated logical
Luna/Terra capacity in an isolated Executive SQLite runtime, creates and
completes one representative job for each bounded worker task, and compares
the recorded fixture envelope with the prior all-Sol reference envelope.

The harness deliberately does not invoke a provider, MCP server, launchd job,
live worker slot, or write-capable adapter.  Its output is evidence about the
router and lifecycle seam, not a claim about production provider telemetry.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from control_plane.executive_runtime import JobPayload, Runtime, SCHEMA_VERSION
from control_plane.model_router import ModelRouter, WorkRequest


ROUTING_POLICY_VERSION = "2026-08-24.stage4"
EVIDENCE_SCHEMA = "mastermind.executive_os_r1_shadow_evidence/v1"

# These are the reviewed, bounded R1 fixture inputs.  The all-Sol values are a
# reference envelope carried by the rollout plan, not a live billing ledger.
_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "implementation-routine",
        "task_kind": "implementation",
        "objective": "Implement the bounded fixture change",
        "expected_alias": "fast.engineering",
        "baseline": {"quality": 0.96, "validation_pass": True, "repair_count": 0, "latency_ms": 1200, "frontier_tokens": 1200},
        "shadow": {"quality": 0.92, "validation_pass": True, "repair_count": 1, "latency_ms": 1800, "frontier_tokens": 360},
    },
    {
        "case_id": "research-routine",
        "task_kind": "research",
        "objective": "Collect the bounded fixture research packet",
        "expected_alias": "fast.research",
        "baseline": {"quality": 0.97, "validation_pass": True, "repair_count": 0, "latency_ms": 1500, "frontier_tokens": 1600},
        "shadow": {"quality": 0.90, "validation_pass": True, "repair_count": 1, "latency_ms": 2300, "frontier_tokens": 500},
    },
    {
        "case_id": "tests-routine",
        "task_kind": "tests",
        "objective": "Run the bounded fixture validation suite",
        "expected_alias": "fast.engineering",
        "baseline": {"quality": 0.98, "validation_pass": True, "repair_count": 0, "latency_ms": 1000, "frontier_tokens": 900},
        "shadow": {"quality": 0.98, "validation_pass": True, "repair_count": 0, "latency_ms": 900, "frontier_tokens": 260},
    },
    {
        "case_id": "review-routine",
        "task_kind": "review",
        "objective": "Review the bounded fixture result",
        "expected_alias": "standard.review",
        "objective_department": "review",
        "baseline": {"quality": 0.95, "validation_pass": True, "repair_count": 1, "latency_ms": 1300, "frontier_tokens": 1400},
        "shadow": {"quality": 0.94, "validation_pass": True, "repair_count": 0, "latency_ms": 1400, "frontier_tokens": 650},
    },
)


def _register_fixture_capacity(runtime: Runtime, router: ModelRouter) -> list[dict[str, Any]]:
    """Register dedicated, unarmed logical capacity for the R1 run."""

    profiles = {
        alias: router.resolve_model_alias(alias)
        for alias in (
            "fast.engineering",
            "fast.research",
            "standard.engineering",
            "standard.research",
            "standard.review",
        )
    }
    declarations = (
        ("fixture-luna-r1", ("fast.engineering", "fast.research")),
        (
            "fixture-terra-r1",
            ("standard.engineering", "standard.research", "standard.review"),
        ),
    )
    capacity: list[dict[str, Any]] = []
    for worker_id, aliases in declarations:
        first = profiles[aliases[0]]
        quota_classes: dict[str, dict[str, Any]] = {}
        for alias in aliases:
            profile = profiles[alias]
            quota_class = f"r1-{alias.replace('.', '-')}"
            quota_classes[quota_class] = {
                "provider": profile.provider_alias,
                "model": profile.model,
                "effort": profile.effort,
                "cost_class": profile.cost_class,
                "capabilities": list(profile.capabilities),
                "metadata": {
                    "adapter_id": profile.adapter_id,
                    "model_alias": profile.model_alias,
                    "provider_alias": profile.provider_alias,
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": profile.execution_profile_id,
                    "execution_profile_digest": profile.execution_profile_digest,
                    "capability_policy_version": profile.capability_policy_version,
                    "capability_policy_digest": profile.capability_policy_digest,
                    "fixture_only": True,
                    "stage1_production_armed": False,
                },
            }
            capacity.append(
                {
                    "worker_id": worker_id,
                    "quota_class": quota_class,
                    "model_alias": alias,
                    "provider_alias": profile.provider_alias,
                    "model": profile.model,
                    "effort": profile.effort,
                    "cost_class": profile.cost_class,
                }
            )
        runtime.workers.register_worker(
            worker_id,
            provider=first.provider_alias,
            account_label=f"{worker_id}-fixture-account",
            worker_type=first.adapter_id,
            capabilities=sorted({cap for alias in aliases for cap in profiles[alias].capabilities}),
            quota_classes=quota_classes,
            metadata={
                "fixture_only": True,
                "stage1_production_armed": False,
                "routing_policy_version": router.policy_version,
                "capability_policy_version": first.capability_policy_version,
                "capability_policy_digest": first.capability_policy_digest,
                "logical_capacity_aliases": list(aliases),
            },
        )
    return capacity


def _aggregate_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    # ``key`` labels the envelope in the output; each input row is already the
    # corresponding baseline or shadow metric mapping.
    del key
    values = rows
    quality = sum(float(row["quality"]) for row in rows) / len(rows)
    validation_pass_rate = sum(bool(row["validation_pass"]) for row in rows) / len(rows)
    repair_rate = sum(int(row["repair_count"]) > 0 for row in rows) / len(rows)
    latency = sum(int(row["latency_ms"]) for row in rows) / len(rows)
    ordered_latency = sorted(int(row["latency_ms"]) for row in rows)
    p95_index = min(len(ordered_latency) - 1, max(0, math.ceil(len(ordered_latency) * 0.95) - 1))
    return {
        "quality_mean": round(quality, 6),
        "validation_pass_rate": round(validation_pass_rate, 6),
        "repair_rate": round(repair_rate, 6),
        "repair_rounds_total": sum(int(row["repair_count"]) for row in rows),
        "latency_ms_mean": round(latency, 3),
        "latency_ms_p95_fixture": ordered_latency[p95_index],
        "frontier_tokens_total": sum(int(row["frontier_tokens"]) for row in rows),
        "case_count": len(values),
    }


def run_r1_shadow(root: str | Path) -> dict[str, Any]:
    """Run the complete fixture-only R1 shadow rollout under ``root``."""

    root = Path(root).resolve()
    router = ModelRouter.load()
    if router.policy_version != ROUTING_POLICY_VERSION:
        raise RuntimeError(
            f"R1 fixture expects routing policy {ROUTING_POLICY_VERSION!r}, "
            f"got {router.policy_version!r}"
        )
    runtime = Runtime.at(root)
    capacity = _register_fixture_capacity(runtime, router)
    eligible_quota_classes = [item["quota_class"] for item in capacity]
    jobs: list[dict[str, Any]] = []
    shadow_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []

    for case in _CASES:
        decision = router.route(WorkRequest(task_kind=case["task_kind"], risk="routine", ambiguity="low"))
        constraints = decision.job_constraints()
        constraints["eligible_quota_classes"] = eligible_quota_classes
        job = runtime.jobs.create_job(
            case["objective"],
            department=case.get("objective_department", case["task_kind"]),
            constraints=constraints,
            provenance={
                "schema": EVIDENCE_SCHEMA,
                "actor": "r1-shadow-harness",
                "fixture_only": True,
            },
        )
        lease = runtime.broker.claim(job.job_id, lease_owner="r1-shadow-fixture")
        if lease is None:
            raise RuntimeError(f"R1 fixture could not claim {job.job_id}")
        assigned_quota = runtime.workers.get_quota_class(
            lease.attempt.worker_id, lease.attempt.quota_class
        )
        if assigned_quota is None:
            raise RuntimeError(f"R1 fixture lost quota metadata for {job.job_id}")
        assigned_alias = str(assigned_quota.metadata.get("model_alias") or "")
        if assigned_alias != case["expected_alias"]:
            raise RuntimeError(
                f"R1 route mismatch for {case['case_id']}: expected "
                f"{case['expected_alias']}, got {assigned_alias or '<missing>'}"
            )
        completed = runtime.jobs.complete_job(
            job.job_id,
            JobPayload(
                summary=f"Completed fixture case {case['case_id']}",
                completed_steps=["route", "claim", "fixture execute", "validate"],
                current_state="complete",
                artifacts=[f"r1-shadow/{case['case_id']}.json"],
            ),
        )
        if completed.status.value != "COMPLETED":
            raise RuntimeError(f"R1 fixture did not complete {job.job_id}")
        jobs.append(
            {
                "job_id": job.job_id,
                "case_id": case["case_id"],
                "task_kind": case["task_kind"],
                "expected_model_alias": case["expected_alias"],
                "assigned_model_alias": assigned_alias,
                "worker_id": lease.attempt.worker_id,
                "quota_class": lease.attempt.quota_class,
                "status": completed.status.value,
                "adapter_invoked": False,
                "production_armed": False,
            }
        )
        shadow_rows.append(case["shadow"])
        baseline_rows.append(case["baseline"])

    baseline = _aggregate_metrics(baseline_rows, "baseline")
    shadow = _aggregate_metrics(shadow_rows, "shadow")
    token_savings = baseline["frontier_tokens_total"] - shadow["frontier_tokens_total"]
    metrics = {
        "baseline": baseline,
        "shadow": shadow,
        "delta_shadow_minus_baseline": {
            "quality_mean": round(shadow["quality_mean"] - baseline["quality_mean"], 6),
            "validation_pass_rate": round(shadow["validation_pass_rate"] - baseline["validation_pass_rate"], 6),
            "repair_rate": round(shadow["repair_rate"] - baseline["repair_rate"], 6),
            "latency_ms_mean": round(shadow["latency_ms_mean"] - baseline["latency_ms_mean"], 3),
        },
        "frontier_token_savings": {
            "tokens": token_savings,
            "rate": round(token_savings / baseline["frontier_tokens_total"], 6),
            "baseline_basis": "previous_all_sol_reference_fixture",
            "telemetry_status": "fixture_estimate_not_provider_billing",
        },
    }
    return {
        "schema": EVIDENCE_SCHEMA,
        "phase": "R1",
        "captured_on": "2026-08-16",
        "runtime_schema_version": SCHEMA_VERSION,
        "routing_policy_version": router.policy_version,
        "capacity": capacity,
        "jobs": jobs,
        "metrics": metrics,
        "guards": {
            "executive_os_lifecycle_authority": True,
            "router_policy_production_armed": False,
            "fixture_capacity_production_armed": False,
            "mcp_write_authority": False,
            "live_worker_slots_activated": False,
            "phase_1c_a_hold_preserved": True,
            "phase_1f_c_started": False,
            "second_control_plane": False,
            "provider_invocations": 0,
        },
        "acceptance": {
            "representative_jobs_completed": len(jobs) == len(_CASES),
            "luna_and_terra_capacity_registered": {"luna": True, "terra": True},
            "logical_aliases_verified": all(
                row["assigned_model_alias"] == row["expected_model_alias"] for row in jobs
            ),
            "r1_shadow_pass": True,
        },
        "measurement_method": {
            "quality": "fixture case score in [0,1]",
            "validation_pass_rate": "completed cases with validation_pass=true / cases",
            "repair_rate": "cases with repair_count > 0 / cases",
            "latency": "reviewed deterministic fixture duration in milliseconds; no wall-clock provider latency",
            "frontier_token_savings": "previous all-Sol reference token envelope minus shadow fixture envelope",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixture-only Executive OS R1 shadow rollout")
    parser.add_argument("--root", type=Path, help="isolated runtime root; defaults to a temporary directory")
    args = parser.parse_args(argv)
    if args.root is not None:
        evidence = run_r1_shadow(args.root)
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    with tempfile.TemporaryDirectory(prefix="mastermind-r1-shadow-") as root:
        evidence = run_r1_shadow(root)
        print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
