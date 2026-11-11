"""Discovery-first repository test gate.

Every ``tests/**/test_*.py`` module runs unless its exact path is listed in
``ci/pytest_exclusions.toml``. New tests are included automatically. Exclusions
are fail-closed and cannot remove constitutional/security modules.

``--jobs N`` splits the *already resolved* included set across N concurrent
pytest processes inside this one gate invocation. It is a placement decision
only: the discovery/exclusion policy above runs first and unchanged, and the
partition is verified to be a total, disjoint cover of that exact set before
any process starts. The gate therefore executes the same modules whatever
``--jobs`` is, and a nonzero exit from any shard fails the whole gate.

The default ``--jobs`` command runs concurrent subprocesses inside one job.
A separately qualified workflow may instead dispatch the same verified
partition to distinct hosted runners. In that arrangement a fail-closed fan-in
job named ``test`` must require every matrix member to succeed and must
reverify the canonical complete plan. The branch-protection context remains
exactly ``test``; dynamic ``pytest shard N`` contexts alone cannot replace it.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from yaml.constructor import ConstructorError as YAMLConstructorError


EXCLUSIONS_RELATIVE = Path("ci") / "pytest_exclusions.toml"
WORKFLOW_RELATIVE = Path(".github") / "workflows" / "ci.yml"
AUTHORITATIVE_STEP_NAME = "Run repository test gate"
AUTHORITATIVE_RUNNER = "scripts/ci_pytest.py"
REQUIRED_WORKFLOW_EVENTS = ("pull_request", "merge_group", "push", "workflow_dispatch")
REQUIRED_MERGE_GROUP_TRIGGER = {"types": ["checks_requested"]}
REQUIRED_PUSH_TRIGGER = {"branches": ["master"]}
PROTECTED_EXACT = frozenset(
    {
        "tests/test_ci_pytest_policy.py",
        "tests/test_secret_redaction.py",
        "tests/test_gate.py",
        "tests/test_vendored_read_ratchet.py",
        "tests/test_deploy_provenance.py",
        "tests/test_auth.py",
        "tests/test_book_state_isolation.py",
        "tests/test_web_exception_sanitization.py",
    }
)
PROTECTED_PREFIXES = ("tests/test_executive_",)
_TEST_MODULE_RE = re.compile(r"^test_.*\.py$")
_WORKFLOW_TEST_FILE_RE = re.compile(r"^tests/(?:[\w./-]+/)?test_\w+\.py$")


class PolicyError(ValueError):
    """The exclusion manifest or workflow coverage policy is invalid."""


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "tests").is_dir():
            return candidate
    raise PolicyError("could not resolve repository root from ci_pytest.py")


def discover_test_modules(root: Path) -> tuple[str, ...]:
    tests_root = (root / "tests").resolve()
    found: list[str] = []
    for path in tests_root.rglob("test_*.py"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.name.startswith("test_") and path.suffix == ".py":
            found.append(relative)
    return tuple(sorted(found))


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be a table")
    return value


def load_exclusions(root: Path, relative: Path = EXCLUSIONS_RELATIVE) -> tuple[dict[str, Any], ...]:
    path = root / relative
    if not path.is_file():
        raise PolicyError(f"exclusion manifest is missing: {relative.as_posix()}")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version != 1:
        raise PolicyError("exclusion manifest version must be 1")
    raw = payload.get("exclude", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise PolicyError("exclude must be an array of tables")
    rows: list[dict[str, Any]] = []
    for item in raw:
        rows.append(dict(_require_mapping(item, label="exclude entry")))
    return tuple(rows)


def is_protected(relative: str) -> bool:
    if relative in PROTECTED_EXACT:
        return True
    return any(relative.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def validate_exclusions(
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    discovered: Sequence[str],
) -> tuple[str, ...]:
    discovered_set = set(discovered)
    seen: set[str] = set()
    excluded: list[str] = []
    for row in rows:
        path = str(row.get("path") or "").strip()
        reason = str(row.get("reason") or "").strip()
        replacement = str(row.get("replacement_gate") or "").strip()
        if not path:
            raise PolicyError("exclusion path cannot be empty")
        if any(character in path for character in ("*", "?", "[", "]")):
            raise PolicyError(f"wildcard exclusion is forbidden: {path}")
        if path.endswith("/") or path == "tests" or path == "tests/":
            raise PolicyError(f"directory exclusion is forbidden: {path}")
        rendered = Path(path)
        if rendered.is_absolute() or ".." in rendered.parts:
            raise PolicyError(f"path escape is forbidden: {path}")
        if rendered.parts[:1] != ("tests",):
            raise PolicyError(f"exclusion path must be under tests/: {path}")
        if rendered.as_posix() != path:
            raise PolicyError(f"exclusion path must be a normalized posix path: {path}")
        if not _TEST_MODULE_RE.fullmatch(rendered.name):
            raise PolicyError(f"exclusion basename must be a pytest test module: {path}")
        if path in seen:
            raise PolicyError(f"duplicate exclusion: {path}")
        seen.add(path)
        if path not in discovered_set:
            raise PolicyError(f"stale exclusion names a missing file: {path}")
        if not reason:
            raise PolicyError(f"exclusion reason cannot be empty: {path}")
        if not replacement:
            raise PolicyError(f"replacement_gate is required: {path}")
        if is_protected(path):
            raise PolicyError(f"protected test cannot be excluded: {path}")
        excluded.append(path)
    return tuple(excluded)


def included_modules(discovered: Sequence[str], excluded: Sequence[str]) -> tuple[str, ...]:
    excluded_set = set(excluded)
    included = tuple(path for path in discovered if path not in excluded_set)
    if not included:
        raise PolicyError("included test set is empty")
    missing = excluded_set - set(discovered)
    if missing:
        raise PolicyError(f"excluded paths are not discovered: {sorted(missing)}")
    return included


def coverage_plan(
    *,
    discovered: Sequence[str],
    excluded: Sequence[str],
    included: Sequence[str],
) -> dict[str, int]:
    return {
        "discovered": len(discovered),
        "excluded": len(excluded),
        "running": len(included),
    }


def format_plan(plan: Mapping[str, int], *, shards: Sequence[Sequence[str]] | None = None) -> str:
    rendered = (
        f"discovered={plan['discovered']} "
        f"excluded={plan['excluded']} "
        f"running={plan['running']}"
    )
    if shards is not None:
        sizes = ",".join(str(len(shard)) for shard in shards)
        rendered += f" jobs={len(shards)} shard_modules={sizes}"
    return rendered


def pytest_argv(
    included: Sequence[str], *, python: str | None = None, progress: bool = False,
) -> list[str]:
    # Observability only: report bounded slowest setup/call/teardown durations
    # without dropping a test, changing its order, or creating new CI contexts.
    prefix = [python or sys.executable]
    if progress:
        prefix.append("-u")
    prefix.extend(["-m", "pytest"])
    if progress:
        prefix.extend(["-p", "scripts.ci_pytest_timing"])
    return [*prefix, "--durations=25", "-q", *included]


_MEASURED_THREE_JOB_PLACEMENT = {
    # Keep the protected-master hot-module pins. A previous two-module
    # capacity-host/walkforward swap overloaded shard 1 with cold setup; do
    # not repeat that uncompensated swap. In PR #1763 CI 41251754394, shard 0
    # ended without a completed pytest step or cleanup after ~51 minutes.
    # Its job log is unavailable, so this is a measured load mitigation, NOT
    # an assertion that any individual test failed. Last successful CI
    # 41243150199 measured capacity-host at ~846s in shard 0, while native
    # Fabric quota (~258s), walkforward (~154s) and deploy provenance (~74s)
    # ran in shard 1. Move the long capacity module to shard 1 only while
    # moving ALL three other measured modules back to shard 0. This balances
    # both runners without dropping tests or changing other SHA-256 placements.
    "tests/test_capacity_host_artifacts.py": 1,
    "tests/test_native_fabric_quota_continuity.py": 0,
    "tests/test_trend_persistence_walkforward.py": 0,
    "tests/test_deploy_provenance.py": 0,
    "tests/test_executive_runtime_bounded_acquisition.py": 1,
    "tests/test_mastermind_window_reader_static_fences.py": 1,
    # The protected one-runner CI gate measured these further slow modules.
    "tests/test_market_view.py": 1,
    "tests/test_product_acceptance_original_selector.py": 1,
    "tests/test_executive_os_phase1fc.py": 2,
}


_MEASURED_SIX_JOB_PLACEMENT = {
    # Exact CI_MODULE hosted merge-group run 42708053350 (master 2614ecbae,
    # 2026-11-09, all six shards green). CI Lightning F3 re-derivation: the
    # 150 slowest measured included modules are placed longest-processing-
    # time-first onto the least-loaded shard, where each shard's starting load
    # is its measured non-runner overhead (native admission gate on shard 5),
    # fixed runner overhead, the hash-placed remainder, and the hermes-forward
    # keep-pin on shard 4. The five non-pytest qualification gates left shard
    # zero for a parallel job (F3). Evidence: ci/shard_timings/42708053350.json.
    # Changes require new timings and policy review. Hash placement for others.
    'tests/test_capacity_host_artifacts.py': 2,  # 834.1s
    'tests/test_hermes_primary_application_enrollment.py': 4,  # 224.2s keep-pin (hermes-forward)
    'tests/test_native_fabric_quota_continuity_a_f.py': 1,  # 191.9s
    'tests/test_trend_persistence_walkforward.py': 3,  # 189.0s
    'tests/test_host_pull_publisher_lifecycle.py': 1,  # 166.0s
    'tests/test_fabric_request_turn_budget.py': 4,  # 163.2s
    'tests/test_native_fabric_quota_continuity_g_o.py': 0,  # 137.3s
    'tests/test_glm_native_application_enrollment.py': 3,  # 128.0s
    'tests/test_executive_persistent_origin_integration.py': 0,  # 124.7s
    'tests/test_native_fabric_quota_continuity_p_z.py': 1,  # 120.8s
    'tests/test_project_journey_canonical_create.py': 4,  # 98.2s
    'tests/test_executive_acceptance_schema_transition.py': 3,  # 93.1s
    'tests/test_project_execution_code_continuity.py': 4,  # 92.1s
    'tests/test_web_ceo_offline_delivery_canary.py': 0,  # 89.5s
    'tests/test_os_gateway_successor_publication.py': 1,  # 84.3s
    'tests/test_deploy_provenance.py': 3,  # 81.9s
    'tests/test_executive_os_sqlite.py': 0,  # 75.5s
    'tests/test_executive_installed_migration_successor.py': 4,  # 74.6s
    'tests/test_mastermind_plugin_packages.py': 1,  # 72.7s
    'tests/test_executive_schema_upgrade_evidence.py': 3,  # 69.9s
    'tests/test_executive_runtime_bounded_role_result.py': 1,  # 69.4s
    'tests/test_product_acceptance_original_selector.py': 0,  # 68.5s
    'tests/test_executive_acceptance_v5_to_v7.py': 4,  # 67.9s
    'tests/test_executive_current_agentos_context.py': 3,  # 66.5s
    'tests/test_fresh_conversation_created_project.py': 4,  # 61.9s
    'tests/test_executive_prepared_migration_successor.py': 0,  # 58.7s
    'tests/test_native_fabric_quota_continuity.py': 1,  # 56.7s
    'tests/test_executive_installed_preparation_chain.py': 3,  # 56.5s
    'tests/test_memory_evaluation_owner.py': 1,  # 55.3s
    'tests/test_executive_service.py': 0,  # 53.4s
    'tests/test_executive_supervisor.py': 4,  # 51.2s
    'tests/test_fabric_job_view_hierarchy.py': 3,  # 48.8s
    'tests/test_installed_current_agentos_context.py': 2,  # 48.5s
    'tests/test_hermes_project_continuity.py': 0,  # 47.1s
    'tests/test_hermes_native_agentos_memory.py': 1,  # 43.7s
    'tests/test_mastermind_window_reader_static_fences.py': 4,  # 43.6s
    'tests/test_company_inbox_iac1.py': 2,  # 43.2s
    'tests/test_hermes_application_consumer_export.py': 3,  # 42.2s
    'tests/test_chairman_coordination_parent.py': 4,  # 41.3s
    'tests/test_workspace_admitted_plan_read.py': 1,  # 41.0s
    'tests/test_executive_codex_sidecar_install.py': 3,  # 40.2s
    'tests/test_claude_cli_protocol.py': 2,  # 39.1s
    'tests/test_executive_repair_review_input.py': 0,  # 37.9s
    'tests/test_project_plan_proposal_consumer_export.py': 2,  # 36.7s
    'tests/test_fresh_conversation_root_validation.py': 3,  # 36.4s
    'tests/test_fresh_conversation_turn.py': 0,  # 35.7s
    'tests/test_native_company_answer_dispatch.py': 1,  # 35.6s
    'tests/test_trend_persistence_group.py': 4,  # 34.8s
    'tests/test_product_acceptance_acquisition_service.py': 4,  # 34.4s
    'tests/test_os_gateway_publication_owner.py': 0,  # 34.4s
    'tests/test_executive_mcp_web_ceo_v2.py': 1,  # 33.8s
    'tests/test_executive_installed_macro_epochs.py': 3,  # 33.3s
    'tests/test_hermes_primary_retained_enrollment.py': 2,  # 33.3s
    'tests/test_workspace_fabric_produced_boundary.py': 2,  # 32.8s
    'tests/test_executive_os_phase1fc.py': 3,  # 31.1s
    'tests/test_executive_physical_schema_upgrade.py': 1,  # 31.0s
    'tests/test_project_discovery_installed_plan.py': 4,  # 30.4s
    'tests/test_product_acceptance_read_projection.py': 0,  # 30.3s
    'tests/test_native_company_consumption.py': 4,  # 30.0s
    'tests/test_executive_service_control.py': 0,  # 29.9s
    'tests/test_h24_team_reader.py': 3,  # 29.0s
    'tests/test_advisor_paper_selection.py': 1,  # 28.9s
    'tests/test_h24_team_projection.py': 2,  # 28.4s
    'tests/test_fresh_conversation_source_check.py': 3,  # 27.8s
    'tests/test_product_acceptance_ruling_owner.py': 1,  # 27.2s
    'tests/test_project_planning_compiler_source.py': 4,  # 26.5s
    'tests/test_session_bridge_original_operation_read.py': 0,  # 26.3s
    'tests/test_workspace_result_service.py': 2,  # 26.0s
    'tests/test_project_execution_service.py': 0,  # 25.2s
    'tests/test_company_consultation_host.py': 4,  # 25.1s
    'tests/test_experiential_harness_endpoint.py': 2,  # 23.3s
    'tests/test_executive_identity_review.py': 1,  # 23.2s
    'tests/test_pfolio_pnl_display.py': 3,  # 22.8s
    'tests/test_executive_runtime_bounded_acquisition.py': 2,  # 22.8s
    'tests/test_hermes_primary_application_host.py': 1,  # 22.2s
    'tests/test_project_execution_continuation.py': 3,  # 21.9s
    'tests/test_project_discovery_factory_join.py': 0,  # 21.9s
    'tests/test_host_pull_h1_mode_integration.py': 4,  # 21.7s
    'tests/test_executive_inbox.py': 3,  # 21.5s
    'tests/test_executive_fabric_release_identity_review.py': 1,  # 21.5s
    'tests/test_fresh_conversation.py': 2,  # 21.4s
    'tests/test_a2_agent_relay_host_prepare.py': 4,  # 21.1s
    'tests/test_chairman_coordination_acquisition.py': 0,  # 21.1s
    'tests/test_chairman_coordination_commission.py': 5,  # 21.1s
    'tests/test_product_acceptance_request_owner.py': 3,  # 20.5s
    'tests/test_chairman_coordination_host.py': 1,  # 20.1s
    'tests/test_native_capacity_source_closure.py': 2,  # 19.9s
    'tests/test_executive_coo_tick_liveness.py': 4,  # 19.6s
    'tests/test_remote_wake_ack_conformance.py': 0,  # 19.2s
    'tests/test_company_consultation_targeted_carrier.py': 5,  # 19.1s
    'tests/test_executive_release_stage_only.py': 1,  # 19.0s
    'tests/test_c1_installer_control_config.py': 0,  # 18.9s
    'tests/test_workspace_project_git_publisher.py': 2,  # 18.6s
    'tests/test_hermes_leadership_organization.py': 3,  # 18.6s
    'tests/test_project_creation_source_owner.py': 4,  # 18.4s
    'tests/test_executive_mcp_installed_fabric_composition.py': 5,  # 18.1s
    'tests/test_finite_initial_physical_admission.py': 4,  # 18.1s
    'tests/test_executive_coo_active_review_frontier.py': 2,  # 18.1s
    'tests/test_executive_precensus_recovery.py': 3,  # 18.0s
    'tests/test_w6c2_consultation_runtime.py': 0,  # 17.9s
    'tests/test_chairman_coordination_review.py': 1,  # 17.7s
    'tests/test_project_canonical_data.py': 5,  # 17.6s
    'tests/test_executive_coo_hierarchy_service.py': 1,  # 17.4s
    'tests/test_hermes_selected_child_target.py': 0,  # 17.4s
    'tests/test_trend_persistence_null.py': 3,  # 17.3s
    'tests/test_mastermind_workspace_repositories.py': 4,  # 17.3s
    'tests/test_cap_s1_mastermind_operator_canary.py': 2,  # 17.3s
    'tests/test_executive_release_actuator.py': 5,  # 17.2s
    'tests/test_project_planning_issued_capture.py': 1,  # 17.2s
    'tests/test_executive_repair_input.py': 0,  # 17.0s
    'tests/test_project_data_continuity_reader.py': 3,  # 16.7s
    'tests/test_rakazo_qualification.py': 4,  # 16.6s
    'tests/test_workspace_retained_root_selection.py': 2,  # 16.5s
    'tests/test_executive_backup.py': 5,  # 16.3s
    'tests/test_native_launcher_successor_transition.py': 2,  # 16.0s
    'tests/test_worker_execution_contract.py': 4,  # 16.0s
    'tests/test_os_public_edge_publication.py': 3,  # 15.9s
    'tests/test_executive_release_closure.py': 0,  # 15.9s
    'tests/test_knowledge_memory_app_source.py': 1,  # 15.8s
    'tests/test_finite_initial_transaction.py': 5,  # 15.6s
    'tests/test_mastermind_steward_app_live_window.py': 2,  # 15.4s
    'tests/test_ci_parallel_fanin.py': 3,  # 15.3s
    'tests/test_mastermind_cortex_contracts.py': 4,  # 15.2s
    'tests/test_support_policy_status.py': 0,  # 15.0s
    'tests/test_trend_persistence_panel.py': 1,  # 15.0s
    'tests/test_workspace_instruction_admission.py': 5,  # 14.9s
    'tests/test_hermes_leadership.py': 1,  # 14.6s
    'tests/test_plan_adoption_canonical_publication.py': 3,  # 14.2s
    'tests/test_executive_release_publication.py': 0,  # 14.2s
    'tests/test_response_cache.py': 4,  # 14.1s
    'tests/test_workspace_resource_capacity_read.py': 2,  # 14.0s
    'tests/test_executive_coo_ready_frontier.py': 5,  # 13.8s
    'tests/test_fabric_remote_lane_root.py': 2,  # 13.6s
    'tests/test_runtime_admitted_plan_read.py': 4,  # 13.4s
    'tests/test_session_bridge_reply_event_host_integration.py': 0,  # 13.0s
    'tests/test_executive_coo_hierarchy.py': 3,  # 12.9s
    'tests/test_product_acceptance_phase_separation.py': 1,  # 12.9s
    'tests/test_project_planning_factory.py': 5,  # 12.9s
    'tests/test_executive_schema_upgrade_pre_census_evidence.py': 3,  # 12.8s
    'tests/test_instruction_admission_runtime.py': 0,  # 12.8s
    'tests/test_memory_v3_completed_service_read.py': 1,  # 12.5s
    'tests/test_product_acceptance_installed_target.py': 4,  # 12.5s
    'tests/test_executive_autonomy_control.py': 2,  # 12.4s
    'tests/test_product_acceptance_relay_composition.py': 5,  # 12.3s
    'tests/test_workspace_host_observation.py': 1,  # 12.3s
    'tests/test_fabric_result_projection.py': 0,  # 12.1s
    'tests/test_executive_release_root_start.py': 4,  # 11.9s
    'tests/test_liquidity_transmission.py': 3,  # 11.8s
    'tests/test_project_execution_conversation_read.py': 2,  # 11.8s
    'tests/test_executive_dr.py': 5,  # 11.7s
    'tests/test_os_release_assets.py': 3,  # 11.7s
}


def partition_modules(
    included: Sequence[str], *, jobs: int
) -> tuple[tuple[str, ...], ...]:
    """Split ``included`` into ``jobs`` shards that exactly re-cover it.

    A module's shard is a stable function of its own path, not of its position
    in the list. Round-robin would be perfectly balanced, but adding a single
    test file shifts every module after it into a different shard -- and since
    sharding changes which modules share a pytest process, that reshuffle can
    surface a latent cross-module ordering dependency in a completely unrelated
    PR. (This is not hypothetical: `--jobs 4` exposed one on its first CI run,
    where `tests/test_governance_ledger.py` was leaking `sys.modules` stubs.)
    Hashing keeps that blast radius to the file actually being added or removed.

    sha256 rather than ``hash()``: the builtin is salted per process, so the
    same checkout would shard differently on every run and a failure would not
    reproduce.

    For the production three-job gate, the explicitly measured hot modules
    are pinned to less-loaded shards. Every other path keeps stable hash
    placement, including when a new test is added. Other job counts retain
    unmodified hashes. This is placement, not exclusion: verify_partition
    checks the exact complete test coverage.
    Shard sizes remain visible in the plan line. (Do not introduce bare
    three-digit constants outside tests/: the identity guard forbids them.)
    """

    if jobs < 1:
        raise PolicyError("jobs must be at least 1")
    if jobs > len(included):
        raise PolicyError(
            f"jobs ({jobs}) cannot exceed the number of included modules "
            f"({len(included)})"
        )
    buckets: list[list[str]] = [[] for _ in range(jobs)]
    for path in included:
        digest = hashlib.sha256(path.encode("utf-8")).digest()
        hashed = int.from_bytes(digest[:8], "big") % jobs
        target = (_MEASURED_THREE_JOB_PLACEMENT.get(path, hashed) if jobs == 3
                  else _MEASURED_SIX_JOB_PLACEMENT.get(path, hashed) if jobs == 6
                  else hashed)
        buckets[target].append(path)
    shards = tuple(tuple(bucket) for bucket in buckets)
    verify_partition(included, shards)
    return shards


def verify_partition(
    included: Sequence[str], shards: Sequence[Sequence[str]]
) -> None:
    """Fail closed unless the shards are a total, disjoint cover of ``included``.

    This is the whole safety argument for ``--jobs``: a partition bug must
    never be able to drop a module and still let the gate report success.
    Checked against multiset equality, so a duplicated module (which would
    hide a dropped one behind an equal total) is rejected too.
    """

    flattened = [path for shard in shards for path in shard]
    if len(flattened) != len(included):
        raise PolicyError(
            f"shard plan runs {len(flattened)} modules but the gate resolved "
            f"{len(included)}"
        )
    if sorted(flattened) != sorted(included):
        raise PolicyError("shard plan is not an exact cover of the included set")
    if any(not shard for shard in shards):
        raise PolicyError("shard plan contains an empty shard")


def run_shards(
    shards: Sequence[Sequence[str]],
    *,
    root: Path,
    python: str | None = None,
) -> int:
    """Run every shard and return the lowest-indexed nonzero exit code, else 0.

    Every shard is always waited on, even after one fails: a partial result
    would make the gate's own report unreliable, and the remaining shards'
    failures are exactly what a reviewer needs in one pass.

    Ordinary output stays grouped under its shard's final banner. Only the
    timing plugin's module records stream immediately, under a shard label,
    so a job timeout leaves the unfinished module and prior module timings.
    These records are diagnostics only; every process exit still governs.
    """

    output_lock = threading.Lock()

    def _run(index: int) -> tuple[int, int, str, float]:
        started = time.monotonic()
        captured: list[str] = []
        with subprocess.Popen(
            pytest_argv(shards[index], python=python, progress=True),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                if line.startswith("CI_MODULE "):
                    with output_lock:
                        print(f"--- shard {index + 1}/{len(shards)} progress --- "
                              + line.rstrip("\n"), flush=True)
                else:
                    captured.append(line)
            returncode = process.wait()
        elapsed = max(0.0, time.monotonic() - started)
        return index, returncode, "".join(captured), elapsed

    codes: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        futures = [pool.submit(_run, index) for index in range(len(shards))]
        for future in as_completed(futures):
            index, returncode, output, elapsed = future.result()
            codes[index] = returncode
            with output_lock:
                print(
                    f"--- shard {index + 1}/{len(shards)} "
                    f"({len(shards[index])} modules) exit={returncode} elapsed_s={elapsed:.2f} ---",
                    flush=True,
                )
                print(output, end="" if output.endswith("\n") else "\n", flush=True)

    # Lowest shard index wins so the reported code is stable across runs
    # rather than depending on which shard happened to finish first.
    for index in sorted(codes):
        if codes[index] != 0:
            return codes[index]
    return 0


def workflow_contains_positive_allowlist(text: str) -> bool:
    """True when a workflow run block lists several tests/test_*.py files."""

    consecutive = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            consecutive = 0
            continue
        if _WORKFLOW_TEST_FILE_RE.fullmatch(stripped):
            consecutive += 1
            if consecutive >= 3:
                return True
            continue
        consecutive = 0
    return False


_TRUE_FALSE_BOOL_PATTERN = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")


class _WorkflowYAMLLoader(yaml.SafeLoader):
    """Private loader used only for workflow YAML, never for anything else.

    GitHub Actions treats the trigger key as the literal, case-sensitive
    string "on" - it is not a YAML 1.1 boolean. Stock SafeLoader disagrees:
    it coerces on/On/ON/off/Off/OFF/yes/no (and case variants) to Python
    booleans, which hides a literal "on" key behind `True` and makes a
    quoted "on" and an unquoted on collide as different-looking keys that
    are actually identical once parsed. This subclass narrows that resolver
    to true/false only (on/off/yes/no become plain strings, matching
    GitHub's real semantics) and separately rejects duplicate mapping keys
    instead of silently keeping the last one. yaml.SafeLoader itself is
    never modified: PyYAML's add_implicit_resolver/add_constructor copy the
    inherited tables onto the subclass before mutating them, so this can
    only affect _WorkflowYAMLLoader.
    """


class _DuplicateMappingKeyError(YAMLConstructorError):
    """A workflow mapping defines the exact same key more than once.

    __str__ is overridden to a fixed literal: the inherited
    MarkedYAMLError.__str__ renders a snippet of the surrounding source
    text via Mark.get_snippet(), which could otherwise echo the offending
    key (or nearby secret-shaped content) even though the "problem" text
    passed to __init__ is itself already a fixed, non-interpolated string.
    """

    def __str__(self) -> str:
        return "found a duplicate mapping key"


class _UnhashableMappingKeyError(YAMLConstructorError):
    """A workflow mapping uses a YAML complex (unhashable) key.

    See _DuplicateMappingKeyError for why __str__ is overridden.
    """

    def __str__(self) -> str:
        return "found an unhashable mapping key"


def _reject_duplicate_mapping_keys(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            is_duplicate = key in mapping
        except TypeError:
            # A YAML explicit complex key (e.g. `? [a, b]`) constructs to an
            # unhashable Python object (list/dict); membership-testing it
            # against `mapping` raises a raw TypeError. Convert it to a
            # stable, distinctly classified error instead of letting it
            # escape uncaught. Chained `from None`: the original TypeError
            # is not needed and dropping it narrows the cause chain.
            raise _UnhashableMappingKeyError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from None
        if is_duplicate:
            raise _DuplicateMappingKeyError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate mapping key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_WorkflowYAMLLoader.yaml_implicit_resolvers = {
    key: [item for item in resolvers if item[0] != "tag:yaml.org,2002:bool"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_WorkflowYAMLLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", _TRUE_FALSE_BOOL_PATTERN, list("tTfF")
)
# YAML merge keys (`<<: *anchor`) must stay unconstructible: replacing the
# stock map constructor leaves tag:yaml.org,2002:merge without a constructor,
# so a merge makes the workflow invalid. If this constructor ever flattens
# merges, an alias could splice keys into a job or the root that the exact
# key pins in ci_parallel_shard.py would then have to be re-proven against.
_WorkflowYAMLLoader.add_constructor(
    "tag:yaml.org,2002:map", _reject_duplicate_mapping_keys
)


def _workflow_trigger_mapping(payload: Mapping[str, Any]) -> Any:
    # Checked first, unconditionally: an explicit tag (`!!bool on`) bypasses
    # the narrowed implicit resolver entirely and still constructs to True
    # (the bool constructor function itself is untouched), and a bareword
    # `true`/`false` top-level key still resolves to a real bool by design.
    # Either can sit alongside an otherwise-valid lowercase "on" key, so
    # every top-level key must be a string before anything else is checked.
    non_string_keys = [key for key in payload if not isinstance(key, str)]
    if non_string_keys:
        # Fixed, stable, secret-free message: the offending keys come from
        # untrusted workflow content and must never be interpolated in.
        raise PolicyError("workflow top-level keys must be strings")
    # Checked unconditionally, even when the literal "on" key is present:
    # a sibling case-variant key (On/ON/oN/...) parses as a distinct string
    # under this loader (it no longer collapses into "on" via boolean
    # coercion), so it would otherwise sit alongside a valid "on" mapping
    # and be silently ignored instead of rejected.
    case_variant = next(
        (key for key in payload if key != "on" and key.lower() == "on"),
        None,
    )
    if case_variant is not None:
        raise PolicyError(
            "workflow trigger key must be the literal lowercase 'on', "
            f"not {case_variant!r}"
        )
    if "on" in payload:
        return payload["on"]
    raise PolicyError("workflow is missing an 'on' trigger mapping")


def validate_workflow_events(payload: Mapping[str, Any]) -> None:
    events = _workflow_trigger_mapping(payload)
    if not isinstance(events, dict):
        raise PolicyError("workflow 'on' trigger must be a mapping of event names")
    non_string_keys = [key for key in events if not isinstance(key, str)]
    if non_string_keys:
        # Keys must be validated as strings before any set difference is
        # sorted for an error message: sorting a set that mixes str with
        # int/bool/None raises an uncaught TypeError instead of failing
        # closed with a stable PolicyError.
        raise PolicyError("workflow 'on' trigger keys must be event name strings")
    found = set(events)
    required = set(REQUIRED_WORKFLOW_EVENTS)
    missing = required - found
    if missing:
        raise PolicyError(
            f"workflow 'on' is missing required event(s): {sorted(missing)}"
        )
    extra = found - required
    if extra:
        # Fixed, stable, secret-free message: unlike `missing` (always a
        # subset of our own known REQUIRED_WORKFLOW_EVENTS), `extra` names
        # come straight from untrusted workflow content and must never be
        # interpolated in.
        raise PolicyError("workflow 'on' has unexpected event(s)")
    if events["pull_request"] is not None:
        raise PolicyError("workflow 'pull_request' trigger must have no filters")
    if events["workflow_dispatch"] is not None:
        raise PolicyError("workflow 'workflow_dispatch' trigger must have no filters")
    if events["merge_group"] != REQUIRED_MERGE_GROUP_TRIGGER:
        raise PolicyError(
            "workflow 'merge_group' trigger must be exactly "
            f"{REQUIRED_MERGE_GROUP_TRIGGER!r}"
        )
    if events["push"] != REQUIRED_PUSH_TRIGGER:
        raise PolicyError(
            f"workflow 'push' trigger must be exactly {REQUIRED_PUSH_TRIGGER!r}"
        )


def validate_workflow(text: str) -> None:
    if AUTHORITATIVE_RUNNER not in text:
        raise PolicyError(
            f"authoritative CI step must invoke {AUTHORITATIVE_RUNNER}"
        )
    if AUTHORITATIVE_STEP_NAME not in text:
        raise PolicyError(
            f"CI workflow must name the step {AUTHORITATIVE_STEP_NAME!r}"
        )
    if workflow_contains_positive_allowlist(text):
        raise PolicyError(
            "CI workflow must not contain a positive tests/test_*.py filename allowlist"
        )
    try:
        payload = yaml.load(text, Loader=_WorkflowYAMLLoader)
    except _DuplicateMappingKeyError as exc:
        raise PolicyError("workflow YAML contains a duplicate mapping key") from exc
    except _UnhashableMappingKeyError as exc:
        raise PolicyError("workflow YAML contains an unhashable mapping key") from exc
    except yaml.YAMLError as exc:
        raise PolicyError("workflow is not valid YAML") from exc
    if not isinstance(payload, dict):
        raise PolicyError("workflow document must be a mapping")
    validate_workflow_events(payload)


def resolve_gate(root: Path) -> dict[str, Any]:
    discovered = discover_test_modules(root)
    rows = load_exclusions(root)
    excluded = validate_exclusions(root, rows, discovered)
    included = included_modules(discovered, excluded)
    workflow = root / WORKFLOW_RELATIVE
    if workflow.is_file():
        validate_workflow(workflow.read_text(encoding="utf-8"))
    return {
        "discovered": discovered,
        "excluded": excluded,
        "included": included,
        "plan": coverage_plan(
            discovered=discovered, excluded=excluded, included=included
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the coverage plan and exit without running pytest",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (defaults to the checkout that contains this script)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "run the resolved module set as this many concurrent pytest "
            "processes (default 1). Placement only: the same modules run "
            "either way, and any shard failing fails the gate."
        ),
    )
    parser.add_argument(
        "--progress", action="store_true",
        help="stream the existing module timing records for the serial gate",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve() if args.root else repo_root()
    try:
        if args.jobs < 1:
            raise PolicyError("jobs must be at least 1")
        gate = resolve_gate(root)
        # jobs=1 keeps the historical module set/order and default argv.
        # Progress is opt-in and changes observability only, never placement.
        shards = (
            partition_modules(gate["included"], jobs=args.jobs)
            if args.jobs > 1
            else None
        )
    except PolicyError as exc:
        print(f"ci_pytest policy error: {exc}", file=sys.stderr)
        return 2
    print(format_plan(gate["plan"], shards=shards), flush=True)
    if args.plan_only:
        return 0
    if shards is not None:
        return run_shards(shards, root=root)
    completed = subprocess.run(
        pytest_argv(gate["included"], progress=args.progress),
        cwd=root,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
