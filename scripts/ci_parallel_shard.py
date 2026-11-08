"""Execute exactly one canonical discovery-first pytest shard on a separate CI runner.

This is a placement adapter, not another exclusion source or test authority.
The existing ci_pytest resolver owns discovery, exclusions, stable placement,
coverage verification, pytest argv, and failure behavior. A separate fan-in
GitHub job named "test" must reject every non-success matrix result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from scripts import ci_pytest


_REQUIRED_SHARDS_IF = "${{ !cancelled() && (github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (needs.pr_scope.result == 'success' && needs.pr_scope.outputs.mode == 'full')) }}"
_REQUIRED_PR_FAST_IF = "${{ !cancelled() && (github.event_name == 'pull_request' || github.event_name == 'merge_group') && needs.pr_scope.result == 'success' && needs.pr_scope.outputs.mode != 'full' }}"

# Three exact qualification lanes preserve the incumbent commands and bootstrap.
# Each complete step list is pinned, including its source/runtime bindings.
# The native unittest prelude is separate from the existing guarded pytest block.
_QUALIFICATION_JOBS = {'source_qualification': ('Source qualification',
                          '1c1be1ac4cead6a581d44fd6888437dad10ce605f4b1c5d9589b19ba41239edf'),
 'source_qualification_fabric': ('Source qualification Fabric',
                                 '2657b140e718d6f71efb19037efe3846eb0e45b07edf107861f39605be5d81db'),
 'source_qualification_native': ('Source qualification native',
                                 '17d9ee7cafa62f8da81405956ac6dd3d4b16daae628aa8073b0a0346eb0ce314')}

_EXPECTED_SHARD_SOURCE_STEPS = [
    {"name": "Acquire immutable corpus fixture anchor", "uses": "actions/checkout@v4",
     "with": {"ref": "edd30b4686d3aaf358b4ca6ebd9485b04d15751d", "fetch-depth": 1,
              "persist-credentials": False}},
    {"name": "Checkout event source", "uses": "actions/checkout@v4",
     "with": {"fetch-depth": 0, "persist-credentials": False}},
    {"name": "Verify event source and immutable fixture anchor",
     "run": "set -euo pipefail\n"
            'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"\n'
            "git cat-file -e 'edd30b4686d3aaf358b4ca6ebd9485b04d15751d^{commit}'\n"},
]


_EXPECTED_SCOPE_STEPS = [{'uses': 'actions/checkout@v4', 'with': {'fetch-depth': 0, 'persist-credentials': False}},
 {'name': 'Classify integrated source diff using protected base code',
  'id': 'scope',
  'env': {'PR_BASE_SHA': '${{ github.event.pull_request.base.sha }}'},
  'run': 'set -euo pipefail\n'
         'trusted="$RUNNER_TEMP/ci-trusted-base"\n'
         'mkdir -p "$trusted"\n'
         'trusted_base="$PR_BASE_SHA"\n'
         'if [ "$GITHUB_EVENT_NAME" = "merge_group" ]; then\n'
         '  trusted_base="$(git rev-parse --verify refs/remotes/origin/master 2>/dev/null || true)"\n'
         'fi\n'
         'if [ -n "$trusted_base" ] &&\n'
         '   git cat-file -e "${trusted_base}:scripts/ci_pr_scope.py" 2>/dev/null &&\n'
         '   git cat-file -e "${trusted_base}:control_plane/github_review_risk_policy.py" 2>/dev/null; then\n'
         '  git archive "$trusted_base" scripts/ci_pr_scope.py control_plane/github_review_risk_policy.py |\n'
         '    tar -x -C "$trusted"\n'
         '  if grep -q \'^def classify_merge_group(\' "$trusted/scripts/ci_pr_scope.py"; then\n'
         '    PYTHONPATH="$trusted" python "$trusted/scripts/ci_pr_scope.py" \\\n'
         '      --repo "$GITHUB_WORKSPACE" --event "$GITHUB_EVENT_PATH" \\\n'
         '      --event-type "$GITHUB_EVENT_NAME" --protected-base "$trusted_base" \\\n'
         '      --repository "$GITHUB_REPOSITORY" --output "$GITHUB_OUTPUT"\n'
         '  else\n'
         '    # First protected installation: legacy scope has no merge-group\n'
         '    # support and this PR modifies CI itself, so it must run FULL.\n'
         '    PYTHONPATH="$trusted" python "$trusted/scripts/ci_pr_scope.py" \\\n'
         '      --repo "$GITHUB_WORKSPACE" --event "$GITHUB_EVENT_PATH" \\\n'
         '      --repository "$GITHUB_REPOSITORY" --output "$GITHUB_OUTPUT"\n'
         '  fi\n'
         'else\n'
         '  printf \'mode=full\\ntier=HOLD\\nneeds_node=false\\n\' >> "$GITHUB_OUTPUT"\n'
         "  echo 'CI_SCOPE source not in protected base: required full suite'\n"
         'fi\n'}]
_EXPECTED_FAST_STEPS = [{'uses': 'actions/checkout@v4', 'with': {'fetch-depth': 0, 'persist-credentials': False}},
 {'name': 'Verify exact changed source without executing untrusted PR text',
  'env': {'PR_BASE_SHA': '${{ needs.pr_scope.outputs.source_base }}',
          'PR_HEAD_SHA': '${{ needs.pr_scope.outputs.source_head }}'},
  'run': 'set -euo pipefail\n'
         'git diff --check "$PR_BASE_SHA...$PR_HEAD_SHA"\n'
         'python -m compileall -q scripts/ci_pr_scope.py control_plane/github_review_risk_policy.py\n'},
 {'uses': 'actions/setup-python@v5',
  'if': "${{ needs.pr_scope.outputs.mode == 'smoke' }}",
  'with': {'python-version': '3.12', 'cache': 'pip'}},
 {'name': 'Checkout pinned Macro engine for source-proximate tests',
  'if': "${{ needs.pr_scope.outputs.mode == 'smoke' }}",
  'uses': 'actions/checkout@v4',
  'with': {'repository': 'mastermindx-market-intelligence/macro',
           'ref': '256c757b3c4f0ec759571c29a30a71387d0a18f8',
           'path': 'vendor/macro_src',
           'sparse-checkout': 'engine\nlib\n',
           'persist-credentials': False,
           'token': '${{ secrets.MACRO_CI_READ_TOKEN || github.token }}'}},
 {'name': 'Install focused Python test dependencies',
  'if': "${{ needs.pr_scope.outputs.mode == 'smoke' }}",
  'run': 'python -m pip install --disable-pip-version-check -e ".[dev]"'},
 {'name': 'Bounded source-proximate PR tests',
  'if': "${{ needs.pr_scope.outputs.mode == 'smoke' }}",
  'env': {'PR_BASE_SHA': '${{ needs.pr_scope.outputs.source_base }}',
          'PR_HEAD_SHA': '${{ needs.pr_scope.outputs.source_head }}'},
  'run': 'python -m scripts.ci_pr_smoke --repo . --base "$PR_BASE_SHA" --head "$PR_HEAD_SHA"'},
 {'uses': 'actions/setup-node@v4',
  'if': "${{ needs.pr_scope.outputs.needs_node == 'true' }}",
  'with': {'node-version': '22.14.0',
           'cache': 'npm',
           'cache-dependency-path': 'app/mastermind_os/package-lock.json'}},
 {'name': 'Typecheck affected web application',
  'if': "${{ needs.pr_scope.outputs.needs_node == 'true' }}",
  'run': 'npm ci --prefix app/mastermind_os --ignore-scripts --no-audit --no-fund\n'
         'npm --prefix app/mastermind_os run typecheck\n'}]


def _validate_pr_fast_lane(jobs: dict) -> None:
    """Strict structure: scope from protected base, fast PR only, no bypass."""
    scope, fast = jobs["pr_scope"], jobs["pr_fast"]
    if not isinstance(scope, dict) or not isinstance(fast, dict):
        raise ci_pytest.PolicyError("PR scope and fast CI jobs must be mappings")
    if (
        scope.get("name") != "PR test scope"
        or scope.get("if") != "${{ github.event_name == 'pull_request' || github.event_name == 'merge_group' }}"
        or scope.get("needs") is not None
        or scope.get("permissions") != {"contents": "read"}
        or scope.get("runs-on") != "ubuntu-latest"
        or scope.get("timeout-minutes") != 3
        or scope.get("outputs") != {'mode': '${{ steps.scope.outputs.mode }}',
 'tier': '${{ steps.scope.outputs.tier }}',
 'needs_node': '${{ steps.scope.outputs.needs_node }}',
 'source_base': '${{ steps.scope.outputs.source_base }}',
 'source_head': '${{ steps.scope.outputs.source_head }}'}
        or scope.get("continue-on-error") is not None
        or fast.get("name") != "PR fast checks"
        or fast.get("if") != _REQUIRED_PR_FAST_IF
        or fast.get("needs") != ["pr_scope"]
        or fast.get("permissions") != {"contents": "read"}
        or fast.get("runs-on") != "ubuntu-latest"
        or fast.get("timeout-minutes") != 8
        or fast.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError("PR scope must be trusted and PR fast lane must be bounded")
    scope_steps, fast_steps = scope.get("steps"), fast.get("steps")
    if not isinstance(scope_steps, list) or len(scope_steps) != 2 or not isinstance(fast_steps, list) or len(fast_steps) != 8:
        raise ci_pytest.PolicyError("PR scope/fast steps missing or duplicated")
    if scope_steps != _EXPECTED_SCOPE_STEPS or fast_steps != _EXPECTED_FAST_STEPS:
        raise ci_pytest.PolicyError("PR fast lane source or commands drifted")
    checkout, qualifier = scope_steps
    if (
        checkout.get("uses") != "actions/checkout@v4"
        or checkout.get("with") != {"fetch-depth": 0, "persist-credentials": False}
        or qualifier.get("name") != "Classify integrated source diff using protected base code"
        or qualifier.get("id") != "scope"
        or qualifier.get("env") != {"PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}"}
        or qualifier.get("if") is not None
    ):
        raise ci_pytest.PolicyError("PR scope must use exact source-bound protected checkout")
    body = qualifier.get("run")
    # A PR author cannot override these immutable routing decisions. Checking
    # the exact required fragments prevents a casual always-FAST replacement;
    # the base-archive full path and controlled outputs are load-bearing.
    # Exact source-step pins above bind all commands, permissions and args.
    # These fragments make the trust reason explicit for error diagnosis.
    expected_scope = (
        'set -euo pipefail', 'trusted_base=', 'refs/remotes/origin/master',
        'git cat-file -e', 'git archive', 'ci_pr_scope.py',
        '--event-type', '--protected-base', 'mode=full', 'tier=HOLD',
    )
    if not isinstance(body, str) or any(x not in body for x in expected_scope):
        raise ci_pytest.PolicyError("PR scope is not protected-base, fail-closed classification")
    for job_step in [*scope_steps, *fast_steps]:
        if not isinstance(job_step, dict) or job_step.get("continue-on-error") is not None:
            raise ci_pytest.PolicyError("PR scope and fast checks may not bypass failures")
    names = [step.get("name") for step in fast_steps]
    if names != [
        None, "Verify exact changed source without executing untrusted PR text",
        None, "Checkout pinned Macro engine for source-proximate tests",
        "Install focused Python test dependencies",
        "Bounded source-proximate PR tests", None,
        "Typecheck affected web application",
    ]:
        raise ci_pytest.PolicyError("PR fast steps must preserve exact bounded checks")
    for i in (0, 2, 3, 6):
        if fast_steps[i].get("uses") != [
            "actions/checkout@v4", "actions/setup-python@v5",
            "actions/checkout@v4", "actions/setup-node@v4",
        ][(0, 2, 3, 6).index(i)]:
            raise ci_pytest.PolicyError("PR fast check toolchain is invalid")
    if fast_steps[0].get("with") != {"fetch-depth": 0, "persist-credentials": False}:
        raise ci_pytest.PolicyError("PR fast checkout must not persist credentials")
    if fast_steps[3]["with"].get("persist-credentials") is not False:
        raise ci_pytest.PolicyError("PR smoke fixture checkout must not persist credentials")
    if (
        fast_steps[2].get("if") != "${{ needs.pr_scope.outputs.mode == 'smoke' }}"
        or fast_steps[3].get("if") != fast_steps[2].get("if")
        or fast_steps[4].get("if") != fast_steps[2].get("if")
        or fast_steps[5].get("if") != fast_steps[2].get("if")
        or fast_steps[6].get("if") != "${{ needs.pr_scope.outputs.needs_node == 'true' }}"
        or fast_steps[7].get("if") != fast_steps[6].get("if")
        or "git diff --check" not in str(fast_steps[1].get("run"))
        or fast_steps[4].get("run") != 'python -m pip install --disable-pip-version-check -e ".[dev]"'
        or "python -m scripts.ci_pr_smoke" not in str(fast_steps[5].get("run"))
        or "npm --prefix app/mastermind_os run typecheck" not in str(fast_steps[7].get("run"))
    ):
        raise ci_pytest.PolicyError("PR fast lane must retain source, Python, and web checks")


_REQUIRED_GATE_RUN = (
 'set -euo pipefail\n'
 'if [ "$EVENT_TYPE" = "pull_request" ] || [ "$EVENT_TYPE" = "merge_group" ]; then\n'
 '  if [ "$PR_SCOPE_STATUS" != success ]; then\n'
 '    echo "trusted source risk qualification unavailable"\n'
 '    exit 1\n'
 '  fi\n'
 '  case "$PR_SCOPE_MODE" in\n'
 '    full)\n'
 '      if [ "$SHARDS_STATUS" != success ] || [ "$QUALIFICATION_STATUS" != success ] || [ "$FABRIC_QUALIFICATION_STATUS" != success ] || [ "$NATIVE_QUALIFICATION_STATUS" != success ] || [ "$PR_FAST_STATUS" != skipped ]; then\n'
 '        echo "critical/unqualified source must pass all six pytest shards and all three source qualification lanes"\n'
 '        exit 1\n'
 '      fi\n'
 '      ;;\n'
 '    fast|smoke)\n'
 '      if [ "$PR_FAST_STATUS" != success ] || [ "$SHARDS_STATUS" != skipped ] || [ "$QUALIFICATION_STATUS" != skipped ] || [ "$FABRIC_QUALIFICATION_STATUS" != skipped ] || [ "$NATIVE_QUALIFICATION_STATUS" != skipped ]; then\n'
 '        echo "eligible source must pass its exact fast/smoke check"\n'
 '        exit 1\n'
 '      fi\n'
 '      ;;\n'
 '    *)\n'
 '      echo "no verified CI source scope"\n'
 '      exit 1\n'
 '      ;;\n'
 '  esac\n'
 'else\n'
 '  # Protected pushes and deliberate manual CI always run all shards.\n'
 '  if [ "$SHARDS_STATUS" != success ] || [ "$QUALIFICATION_STATUS" != success ] ||\n'
 '   [ "$FABRIC_QUALIFICATION_STATUS" != success ] || [ "$NATIVE_QUALIFICATION_STATUS" != success ] ||\n'
 '     [ "$PR_FAST_STATUS" != skipped ] || [ "$PR_SCOPE_STATUS" != skipped ]; then\n'
 '    echo "integration/release CI must pass the full matrix and all three source qualification lanes"\n'
 '    exit 1\n'
 '  fi\n'
 'fi\n'
 '# Revalidate the same canonical test discovery/exclusion/cover plan.\n'
 '# Source-scoped checks never change canonical discovery.\n'
 'python scripts/ci_pytest.py --plan-only --jobs 6\n'
)



def validate_parallel_workflow(text: str) -> None:
    """Ensure the required "test" gate cannot pass without every shard."""
    import yaml

    ci_pytest.validate_workflow(text)
    payload = yaml.load(text, Loader=ci_pytest._WorkflowYAMLLoader)
    if payload.get("permissions") != {"contents": "read"}:
        raise ci_pytest.PolicyError("CI workflow root may only read source")
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"pr_scope", "pr_fast", "pytest_shards", "source_qualification", "source_qualification_fabric", "source_qualification_native", "test"}:
        raise ci_pytest.PolicyError("parallel CI requires trusted scope, fast check, shards, source qualification, and test gate")
    _validate_pr_fast_lane(jobs)
    shards, gate = jobs["pytest_shards"], jobs["test"]
    qualifications = {key: jobs[key] for key in _QUALIFICATION_JOBS}
    if not isinstance(shards, dict) or not isinstance(gate, dict):
        raise ci_pytest.PolicyError("parallel CI job configuration is invalid")
    if shards.get("permissions") != {"contents": "read", "actions": "read"} or gate.get("permissions") is not None:
        raise ci_pytest.PolicyError("Actions proof permission must be scoped to pytest shard jobs only")
    for qualification_id, (display_name, _) in _QUALIFICATION_JOBS.items():
        qualification = qualifications[qualification_id]
        if (
            not isinstance(qualification, dict)
            or set(qualification) != {"name", "needs", "if", "permissions", "runs-on", "timeout-minutes", "steps"}
            or qualification.get("name") != display_name
            or qualification.get("needs") != ["pr_scope"]
            or qualification.get("if") != _REQUIRED_SHARDS_IF
            or qualification.get("permissions") != {"contents": "read"}
            or qualification.get("runs-on") != "ubuntu-latest"
            or type(qualification.get("timeout-minutes")) is not int
            or not 1 <= qualification["timeout-minutes"] <= 30
        ):
            raise ci_pytest.PolicyError("source qualification must run independently for every full source with read-only authority")
    strategy = shards.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    indices = matrix.get("index") if isinstance(matrix, dict) else None
    if (
        not isinstance(strategy, dict)
        or set(strategy) != {"fail-fast", "max-parallel", "matrix"}
        or not isinstance(matrix, dict)
        or set(matrix) != {"index"}
        or not isinstance(indices, list)
        or [type(i) for i in indices] != [int] * 6
        or indices != list(range(6))
        or strategy.get("fail-fast") is not False
        or strategy.get("max-parallel") != 6
        or shards.get("needs") != ["pr_scope"]
        or shards.get("if") != _REQUIRED_SHARDS_IF
        or shards.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError("parallel CI must execute all six shard indices")
    if (
        gate.get("name") != "test"
        or gate.get("needs") != ["pr_scope", "pr_fast", "pytest_shards", "source_qualification", "source_qualification_fabric", "source_qualification_native"]
        or gate.get("if") != "${{ always() }}"
        or gate.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError("required test job must always aggregate all shards")

    # Guard each hosted job's total wall-clock budget, not just pytest time.
    # Retain the established shard/gate budget during the DAG canary. Source
    # qualification overlaps shards and has its own smaller finite budget.
    shard_timeout = shards.get("timeout-minutes")
    gate_timeout = gate.get("timeout-minutes")
    if (
        type(shard_timeout) is not int
        or not 45 <= shard_timeout <= 60
        or type(gate_timeout) is not int
        or not 1 <= gate_timeout <= 8
        or gate_timeout > shard_timeout
        or shard_timeout + gate_timeout > 100
    ):
        raise ci_pytest.PolicyError(
            "parallel CI timeouts must be finite, bounded, and within merge queue budget"
        )

    shard_steps = shards.get("steps", [])
    gate_steps = gate.get("steps", [])
    qualification_steps_by_job = {
        key: job.get("steps", []) for key, job in qualifications.items()
    }
    if not all(isinstance(steps, list) for steps in
               (shard_steps, gate_steps, *qualification_steps_by_job.values())):
        raise ci_pytest.PolicyError("parallel CI steps are missing")
    qualification_steps = [
        step for steps in qualification_steps_by_job.values() for step in steps
    ]
    # GitHub step expressions address IDs rather than displayed names. A later
    # duplicate, including one with different casing, could shadow the pinned
    # previous_ci producer and falsely report reuse=true to skip pytest. Require
    # global uniqueness across all CI jobs rather than depending on runner
    # behavior for duplicate IDs.
    seen_step_ids: set[str] = set()
    for step in (*jobs["pr_scope"]["steps"], *jobs["pr_fast"]["steps"], *shard_steps, *qualification_steps, *gate_steps):
        if not isinstance(step, dict):
            raise ci_pytest.PolicyError("parallel CI steps must be mappings")
        if "id" not in step:
            continue
        step_id = step["id"]
        if not isinstance(step_id, str) or not step_id:
            raise ci_pytest.PolicyError("parallel CI step IDs must be nonempty strings")
        canonical_id = step_id.casefold()
        if canonical_id in seen_step_ids:
            raise ci_pytest.PolicyError("parallel CI step IDs must be globally unique")
        seen_step_ids.add(canonical_id)
    for qualification_id, steps in qualification_steps_by_job.items():
        try:
            qualification_bytes = json.dumps(
                steps, sort_keys=True, separators=(",", ":")
            ).encode()
        except (TypeError, ValueError):
            raise ci_pytest.PolicyError("source qualification steps must preserve the exact extracted commands") from None
        if hashlib.sha256(qualification_bytes).hexdigest() != _QUALIFICATION_JOBS[qualification_id][1]:
            raise ci_pytest.PolicyError("source qualification steps must preserve the exact extracted commands")
    qualification_names = {
        step.get("name")
        for steps in qualification_steps_by_job.values() for step in steps[9:]
    }
    if any(step.get("name") in qualification_names for step in shard_steps):
        raise ci_pytest.PolicyError("singleton qualifications must not be repeated in pytest shards")
    # Job permissions apply to every step; prevent checkout from retaining the
    # expanded Actions-read token in repository Git configuration for later code.
    primary_checkouts = [
        step for step in shard_steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
        and (not isinstance(step.get("with"), dict)
             or not step["with"].get("repository"))
    ]
    # The fixed squash-source anchor is acquired first, with no repository code
    # executed before the event checkout restores GITHUB_SHA. The postcondition
    # also rejects checkout's fallback that might recreate .git and lose it.
    # Exact steps forbid credentials, alternate paths/refs, interposed commands,
    # conditional acquisition and later same-repository source replacement.
    if (len(primary_checkouts) != 2
            or shard_steps[:3] != _EXPECTED_SHARD_SOURCE_STEPS
            or any(step["with"].get("persist-credentials") is not False
                   or type(step["with"].get("fetch-depth")) is not int
                   for step in primary_checkouts)):
        raise ci_pytest.PolicyError(
            "fixed fixture acquisition must precede full-history event checkout and source proof"
        )
    # A checkout with an explicit repository also defaults to the root path.
    # Only the ordinary Macro fixture remains in each shard. The separately
    # pinned Brain fixture belongs to the exact qualification steps above.
    external_checkouts = [
        step for step in shard_steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
        and isinstance(step.get("with"), dict) and step["with"].get("repository")
    ]
    fixture_paths = {
        "Checkout pinned Macro engine": "vendor/macro_src",
    }
    if (len(external_checkouts) != 1
            or {step.get("name") for step in external_checkouts} != set(fixture_paths)
            or any(step.get("uses") != "actions/checkout@v4"
                   or step["with"].get("repository") != "mastermindx-market-intelligence/macro"
                   or step["with"].get("path") != fixture_paths.get(step.get("name"))
                   or step["with"].get("persist-credentials") is not False
                   for step in external_checkouts)):
        raise ci_pytest.PolicyError("later shard checkouts must retain the isolated Macro fixture path")
    # The single prior-CI probe is read-only and executes before the shard.
    # The final shard step can be conditional ONLY on the verified output of
    # this pinned producer. No skipping whole jobs or trusted non-pytest gates.
    proof_steps = [
        step for step in shard_steps
        if isinstance(step, dict) and step.get("name") == "Verify exact prior merge-group CI"
    ]
    shard_runner = [
        step for step in shard_steps
        if isinstance(step, dict) and step.get("name") == "Run repository test shard"
    ]
    if len(proof_steps) != 1 or len(shard_runner) != 1:
        raise ci_pytest.PolicyError("each shard needs one bounded proof and one runner")
    proof, runner = proof_steps[0], shard_runner[0]
    if (
        set(proof) != {"name", "id", "env", "run"}
        or proof.get("id") != "previous_ci"
        or proof.get("env") != {"GH_TOKEN": "${{ github.token }}"}
        or proof.get("run") != "python -m scripts.ci_postmerge_proof"
        or shard_steps.index(proof) >= shard_steps.index(runner)
        or set(runner) != {"name", "if", "run", "timeout-minutes"}
        or type(runner.get("timeout-minutes")) is not int
        or runner.get("timeout-minutes") != 45
        or runner.get("run") != "python -m scripts.ci_parallel_shard --jobs 6 --index ${{ matrix.index }} --processes 4"
        or runner.get("if") != "${{ steps.previous_ci.outputs.reuse != 'true' }}"
    ):
        raise ci_pytest.PolicyError("prior merged CI proof must fail closed before every shard")
    diagnostics = [step for step in shard_steps
                   if step.get("name") == "Upload fixed test diagnostics"]
    expected_paths = "\n".join(
        "${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/pytest-child-" + str(index) + "/" + leaf
        for leaf in ("ci-fixed-diagnostics.json",)
        for index in range(ci_pytest.MAX_PRECOLLECTION_PROCESSES)
    ) + "\n"
    expected_diagnostics = dict(name="Upload fixed test diagnostics", **{
        "if": "always()", "timeout-minutes": 2, "uses": "actions/upload-artifact@v4",
        "with": {"name": "ci-fixed-diagnostics-${{ matrix.index }}",
                 "path": expected_paths, "if-no-files-found": "warn", "retention-days": 3,
                 "compression-level": 0},
    })
    if diagnostics != [expected_diagnostics]:
        raise ci_pytest.PolicyError("child diagnostics must retain exactly the finite public leaves")
    for name in (
        "Verify Paper direct pinned MCP SDK",
        "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
        "Compile source", "Validate shell scripts",
    ):
        matches = [
            step for step in qualification_steps
            if isinstance(step, dict) and step.get("name") == name
        ]
        if len(matches) != 1 or matches[0].get("if") is not None:
            raise ci_pytest.PolicyError("non-pytest CI gates must run unconditionally in source qualification")
    # Preserve the released non-pytest Paper gate in both ordinary and reuse
    # executions. A green job alone does not prove its command actually ran.
    paper = [step for step in qualification_steps
             if step.get("name") == "Verify Paper Studio prepare guard"]
    expected_paper = {
        "name": "Verify Paper Studio prepare guard",
        "working-directory": "integrations/studio_direct_mcp",
        "run": "node --test paper-design.test.mjs",
    }
    if len(paper) != 1 or paper[0] != expected_paper:
        raise ci_pytest.PolicyError(
            "released Paper prepare guard must run unchanged in required source qualification"
        )
    # Reuse may omit only the full pytest step, never the released fast
    # preflight or either real Linux initializer qualification.
    for name, condition in {
        "Fast source-bound release preflight": None,
        "H1 initializer Linux fast preflight": "matrix.index == 2",
        "H1 required real Linux no-ACL positive journey": "matrix.index == 2",
    }.items():
        matches = [step for step in shard_steps if step.get("name") == name]
        if len(matches) != 1 or matches[0].get("if") != condition:
            raise ci_pytest.PolicyError(
                "release preflight and H1 gates must not be omitted or reuse-gated"
            )
    # Preserve the incumbent protected Fabric compatibility gate's *actual*
    # executable surface. Merely pinning its name and shard index permits a
    # false-green gate if its Node or private-service tests are silently cut.
    fabric_name = "Verify private Fabric HTTP compatibility and incumbent backend lifetime"
    fabric_step = next(
        step for step in qualification_steps
        if isinstance(step, dict) and step.get("name") == fabric_name
    )
    fabric_commands = [
        "npm ci --ignore-scripts --no-audit --no-fund",
        "node --test gateway-modern-fabric.test.mjs gateway-fleet-git-failure.test.mjs gateway.test.mjs gateway-shared-backend.test.mjs gateway-owner-lifecycle-regression.test.mjs gateway-output-budget.test.mjs fabric-backend.test.mjs private-cli.test.mjs private-tunnel-auth.test.mjs",
        "python -m unittest discover -s . -p 'private_service*test.py'",
        "python -m unittest discover -s . -p 'control_bundle*test.py'",
    ]
    actual_commands = fabric_step.get("run")
    if (
        set(fabric_step) != {"name", "working-directory", "run"}
        or fabric_step.get("working-directory") != "integrations/studio_direct_mcp"
        or not isinstance(actual_commands, str)
        or [line.strip() for line in actual_commands.splitlines() if line.strip()]
        != fabric_commands
    ):
        raise ci_pytest.PolicyError(
            "private Fabric compatibility gate must preserve its trusted directory and commands"
        )
    test_steps = [
        step for step in gate_steps
        if isinstance(step, dict) and step.get("name") == "Run repository test gate"
    ]
    if len(test_steps) != 1:
        raise ci_pytest.PolicyError("required fan-in gate step is missing")
    final = test_steps[0]
    code = final.get("run")
    # Exact gate source is tested as a whole, not by searching for "exit 1"
    # text in comments or after a branch that already accepted fast PR mode.
    env = final.get("env")
    if (
        env != {
            "EVENT_TYPE": "${{ github.event_name }}",
            "PR_SCOPE_STATUS": "${{ needs.pr_scope.result }}",
            "PR_SCOPE_MODE": "${{ needs.pr_scope.outputs.mode }}",
            "PR_FAST_STATUS": "${{ needs.pr_fast.result }}",
            "SHARDS_STATUS": "${{ needs.pytest_shards.result }}",
            "QUALIFICATION_STATUS": "${{ needs.source_qualification.result }}",
            "FABRIC_QUALIFICATION_STATUS": "${{ needs.source_qualification_fabric.result }}",
            "NATIVE_QUALIFICATION_STATUS": "${{ needs.source_qualification_native.result }}",
        }
        or code != _REQUIRED_GATE_RUN
        or final.get("shell") not in (None, "bash")
        or final.get("if") is not None
    ):
        raise ci_pytest.PolicyError(
            "required fan-in guard must enforce exact PR and integrated merge group source scope"
        )
    if any(
        isinstance(step, dict) and step.get("continue-on-error") is not None
        for step in (*shard_steps, *qualification_steps, *gate_steps)
    ):
        raise ci_pytest.PolicyError("parallel CI may not continue on test errors")


def shard_plan(
    root: Path, *, jobs: int, index: int
) -> tuple[dict, tuple[str, ...], str]:
    if jobs != 6:
        raise ci_pytest.PolicyError("parallel CI requires exactly six jobs")
    if index not in range(jobs):
        raise ci_pytest.PolicyError("parallel CI shard index is outside the plan")
    gate = ci_pytest.resolve_gate(root)
    shards = ci_pytest.partition_modules(gate["included"], jobs=jobs)
    # Deterministic shared input identity across independent runner logs.
    digest = hashlib.sha256(
        b"\0".join(path.encode("utf-8") for path in gate["included"])
    ).hexdigest()
    return gate, shards[index], digest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, required=True)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="pytest-xdist workers inside this shard (0 = one serial interpreter)",
    )
    parser.add_argument(
        "--processes", type=int, default=0,
        help="independent serial pytest children, partitioned before collection",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve() if args.root else ci_pytest.repo_root()

    try:
        validate_parallel_workflow(
            (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        )
        gate, selected, digest = shard_plan(
            root, jobs=args.jobs, index=args.index
        )
        if args.processes and args.workers:
            raise ci_pytest.PolicyError("independent processes and xdist workers are mutually exclusive")
        if not 0 <= args.processes <= ci_pytest.MAX_PRECOLLECTION_PROCESSES:
            raise ci_pytest.PolicyError("independent process count is outside the worker budget")
        children = (ci_pytest.partition_modules(selected, jobs=args.processes, inner=True)
                    if args.processes else None)
        shard_argv = ci_pytest.pytest_argv(selected, progress=True, workers=args.workers)
    except ci_pytest.PolicyError as error:
        print(f"ci_parallel_shard policy error: {error}", file=sys.stderr)
        return 2

    print(ci_pytest.format_plan(gate["plan"]), flush=True)
    print(
        f"parallel_shard={args.index + 1}/{args.jobs} "
        f"modules={len(selected)} included_sha256={digest} workers={args.workers}"
        + (f" processes={args.processes}" if args.processes else ""),
        flush=True,
    )
    if args.plan_only:
        if children is not None:
            print("child_modules=" + ",".join(str(len(child)) for child in children), flush=True)
        return 0
    # No hand-written selectors, mutating retry, positive allowlist or shell.
    if children is not None:
        try:
            return ci_pytest.run_shards(children, root=root, completion_proof=True)
        except ci_pytest.PolicyError as error:
            print(f"ci_parallel_shard policy error: {error}", file=sys.stderr)
            return 2
    if args.workers:
        # Every xdist worker must collect the identical item list; a
        # parametrize over a set/dict iterates in hash order, which differs
        # per interpreter unless the seed is pinned. Workers inherit this.
        env = dict(os.environ)
        env.setdefault("PYTHONHASHSEED", "0")
        completed = subprocess.run(shard_argv, cwd=root, check=False, env=env)
    else:
        completed = subprocess.run(
            [*shard_argv, "--ci-case-evidence"],
            cwd=root,
            check=False,
        )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
