"""Execute exactly one canonical discovery-first pytest shard on a separate CI runner.

This is a placement adapter, not another exclusion source or test authority.
The existing ci_pytest resolver owns discovery, exclusions, stable placement,
coverage verification, pytest argv, and failure behavior. A separate fan-in
GitHub job named "test" must reject every non-success matrix result.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from scripts import ci_pytest


_REQUIRED_SHARDS_IF = "${{ !cancelled() && (github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (needs.pr_scope.result == 'success' && needs.pr_scope.outputs.mode == 'full')) }}"
_REQUIRED_QUALIFICATION_IF = _REQUIRED_SHARDS_IF
_REQUIRED_PR_FAST_IF = "${{ !cancelled() && (github.event_name == 'pull_request' || github.event_name == 'merge_group') && needs.pr_scope.result == 'success' && needs.pr_scope.outputs.mode != 'full' }}"
_REQUIRED_PIN_GUARDS_IF = "${{ !cancelled() }}"

_PIN_GUARDS_RUN_STEP = "Run pinned source-identity guard suite"

_EXPECTED_PIN_GUARDS_STEPS = [
    {"uses": "actions/checkout@v4",
     "with": {"fetch-depth": 0, "persist-credentials": False}},
    {"uses": "actions/setup-python@v5",
     "with": {"python-version": "3.12", "cache": "pip"}},
    {"name": "Install project",
     "run": "python -m pip install --upgrade pip\n"
            'python -m pip install -e ".[dev]"'},
    {"name": _PIN_GUARDS_RUN_STEP,
     "run": "python -m scripts.ci_pin_guards"},
]

# CI Lightning F3: the five once-per-checkout non-pytest qualification gates
# (Paper pinned MCP SDK, Paper Studio prepare guard, private Fabric HTTP
# compatibility, compileall, shell validation) moved verbatim out of shard
# zero into a parallel job. The exact-step list below preserves each gate's
# trusted working directory and command surface; a green job that silently
# cut a command can no longer pass the workflow validator.
# Sixth gate: the web application typecheck. pr_fast owns it for fast/smoke
# candidates and is skipped in full mode, so the qualification job is the
# only place a full merge group, push or manual run can typecheck
# app/mastermind_os. It is unconditional: pr_scope never runs on
# push/dispatch and every fail-closed HOLD decision reports
# needs_node=false, so that output cannot be its condition.
_TYPECHECK_GATE_NAME = "Typecheck web application"
_TYPECHECK_COMMAND = "npm --prefix app/mastermind_os run typecheck"
_EXPECTED_QUALIFICATION_STEPS = [
    {'uses': 'actions/checkout@v4',
     'with': {'fetch-depth': 0, 'persist-credentials': False}},
    {'uses': 'actions/setup-node@v4',
     'with': {'node-version': '22.14.0',
              'cache': 'npm',
              'cache-dependency-path': 'integrations/studio_direct_mcp/package-lock.json\n'
                                       'app/mastermind_os/package-lock.json\n'}},
    {'uses': 'actions/setup-python@v5', 'with': {'python-version': '3.12', 'cache': 'pip'}},
    {'name': 'Install project',
     'run': 'python -m pip install --upgrade pip\npython -m pip install -e ".[dev]"'},
    {'name': 'Verify Paper direct pinned MCP SDK',
     'run': 'PAPER_MCP_VENV="$RUNNER_TEMP/paper-direct-mcp-ci"\n'
            'python -m venv "$PAPER_MCP_VENV"\n'
            '"$PAPER_MCP_VENV/bin/python" -m pip install --disable-pip-version-check \\\n'
            '  -r integrations/paper_desktop/requirements-mcp.txt\n'
            'PAPER_DIRECT_PINNED_SDK_TESTS=1 "$PAPER_MCP_VENV/bin/python" -I -m unittest '
            "discover -s tests -p 'test_paper_direct*.py'\n"
            'PAPER_DIRECT_PINNED_SDK_TESTS=1 "$PAPER_MCP_VENV/bin/python" -I -m unittest '
            "discover -s tests -p 'test_paper_mcp_results.py'\n"},
    {'name': 'Verify Paper Studio prepare guard',
     'working-directory': 'integrations/studio_direct_mcp',
     'run': 'node --test paper-design.test.mjs'},
    {'name': 'Verify private Fabric HTTP compatibility and incumbent backend lifetime',
     'working-directory': 'integrations/studio_direct_mcp',
     'run': 'npm ci --ignore-scripts --no-audit --no-fund\n'
            'node --test gateway-modern-fabric.test.mjs gateway-fleet-git-failure.test.mjs '
            'gateway.test.mjs gateway-shared-backend.test.mjs '
            'gateway-owner-lifecycle-regression.test.mjs gateway-output-budget.test.mjs '
            'fabric-backend.test.mjs private-cli.test.mjs private-tunnel-auth.test.mjs\n'
            "python -m unittest discover -s . -p 'private_service*test.py'\n"
            "python -m unittest discover -s . -p 'control_bundle*test.py'\n"},
    {'name': 'Compile source',
     'run': 'python -m compileall -q app bot brain bridge common control_plane data_layer '
            'integrations loop portfolio scripts'},
    {'name': 'Validate shell scripts',
     'run': "find scripts ops/executive_os -type f -name '*.sh' -print0 |\n"
            '  xargs -0 -n1 bash -n\n'},
    {'name': _TYPECHECK_GATE_NAME,
     'run': 'npm ci --prefix app/mastermind_os --ignore-scripts --no-audit --no-fund\n'
            + _TYPECHECK_COMMAND + '\n'},
]

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
 {'uses': 'actions/setup-python@v5', 'with': {'python-version': '3.12'}},
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
         '   git cat-file -e "${trusted_base}:scripts/__init__.py" 2>/dev/null &&\n'
         '   git cat-file -e "${trusted_base}:scripts/ci_pr_scope.py" 2>/dev/null &&\n'
         '   git cat-file -e "${trusted_base}:control_plane/__init__.py" 2>/dev/null &&\n'
         '   git cat-file -e "${trusted_base}:control_plane/github_review_risk_policy.py" 2>/dev/null; then\n'
         '  git archive "$trusted_base" scripts/__init__.py scripts/ci_pr_scope.py control_plane/__init__.py control_plane/github_review_risk_policy.py |\n'
         '    tar -x -C "$trusted"\n'
         "  # The current classifier's closure is the four files above. A PR\n"
         '  # whose recorded base predates #2439 still classifies with a\n'
         '  # protected classifier that imports the smoke selector; only that\n'
         '  # legacy classifier receives its own protected-base copy.\n'
         '  if grep -q \'^from scripts\\.ci_pr_smoke import \' "$trusted/scripts/ci_pr_scope.py"; then\n'
         '    git archive "$trusted_base" scripts/ci_pr_smoke.py | tar -x -C "$trusted"\n'
         '  fi\n'
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
 {'uses': 'actions/setup-python@v5',
  'with': {'python-version': '3.12', 'cache': 'pip'}},
 {'name': 'Verify exact changed source without executing untrusted PR text',
  'env': {'PR_BASE_SHA': '${{ needs.pr_scope.outputs.source_base }}',
          'PR_HEAD_SHA': '${{ needs.pr_scope.outputs.source_head }}'},
  'run': 'set -euo pipefail\n'
         'git diff --check "$PR_BASE_SHA...$PR_HEAD_SHA"\n'
         'python -m compileall -q scripts/ci_pr_scope.py control_plane/github_review_risk_policy.py\n'},
 {'name': 'Checkout pinned Macro engine for source-proximate tests',
  'if': "${{ needs.pr_scope.outputs.mode == 'smoke' }}",
  'uses': 'actions/checkout@v4',
  'with': {'repository': 'mastermindx-market-intelligence/macro',
           'ref': '268a89e3828d848848c77dfe69191c3fa7319361',
           'path': 'vendor/macro_src',
           'sparse-checkout': 'engine\nlib\nconfig\n',
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


# Full pytest shards, the PR fast lane and the non-pytest qualification gates
# use a GitHub-hosted image. In this organization `ubuntu-latest` can also
# select persistent, multi-slot self-hosted runners, where this suite's
# single-tenant host assertions (ancestor directory identity, modes, ACLs,
# private temp tree) and the Fabric gate's source-directory custody fail
# independently of the change under test. No self-hosted runner carries this
# label. Scope classification and the `test` fan-in run no suite.
HOSTED_TEST_RUNNER = "ubuntu-24.04"
_PIN_GUARDS_JOB_KEYS = frozenset(
    {"name", "if", "permissions", "runs-on", "timeout-minutes", "steps"})
_QUALIFICATION_JOB_KEYS = frozenset(
    {"name", "needs", "if", "permissions", "runs-on", "timeout-minutes", "steps"})


def _validate_pin_guards_lane(jobs: dict) -> None:
    """Strict structure for the early source-identity guard job; no bypass."""
    guards = jobs["pin_guards"]
    if not isinstance(guards, dict):
        raise ci_pytest.PolicyError("pin guards job must be a mapping")
    # Exact job keys: env/defaults/container/strategy/services could change
    # what the pinned step text actually executes.
    if set(guards) != _PIN_GUARDS_JOB_KEYS:
        raise ci_pytest.PolicyError("pin guards job keys drifted")
    if (
        guards.get("name") != "Pin and identity guards"
        or guards.get("if") != _REQUIRED_PIN_GUARDS_IF
        or guards.get("needs") is not None
        or guards.get("permissions") != {"contents": "read"}
        or guards.get("runs-on") != "ubuntu-latest"
        or guards.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError(
            "pin guards must run on every non-cancelled CI event"
        )
    timeout = guards.get("timeout-minutes")
    if type(timeout) is not int or not 1 <= timeout <= 15:
        raise ci_pytest.PolicyError("pin guards timeout must be finite and bounded")
    steps = guards.get("steps")
    if not isinstance(steps, list) or len(steps) != len(_EXPECTED_PIN_GUARDS_STEPS):
        raise ci_pytest.PolicyError("pin guards steps missing or duplicated")
    if steps != _EXPECTED_PIN_GUARDS_STEPS:
        raise ci_pytest.PolicyError("pin guards lane source or commands drifted")
    for step in steps:
        if not isinstance(step, dict) or step.get("continue-on-error") is not None:
            raise ci_pytest.PolicyError("pin guards may not bypass failures")
        if step.get("if") is not None:
            raise ci_pytest.PolicyError("pin guards steps must be unconditional")


def _validate_qualification_lane(jobs: dict) -> None:
    """Exact shape for the parallel non-pytest qualification job; no bypass."""
    qual = jobs["qualification"]
    if not isinstance(qual, dict):
        raise ci_pytest.PolicyError("qualification job must be a mapping")
    # Exact job keys: env/defaults/container/strategy/services could change
    # what the pinned gate text actually executes.
    if set(qual) != _QUALIFICATION_JOB_KEYS:
        raise ci_pytest.PolicyError("qualification job keys drifted")
    if (
        qual.get("name") != "Non-pytest qualification gates"
        or qual.get("if") != _REQUIRED_QUALIFICATION_IF
        or qual.get("needs") != ["pr_scope"]
        or qual.get("permissions") != {"contents": "read"}
        or qual.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError(
            "qualification gates must run exactly when the pytest shards run"
        )
    # Hosted-only: the Fabric gate refuses the shared self-hosted hosts'
    # group-writable checkouts, and those hosts also carry "ubuntu-latest".
    if qual.get("runs-on") != HOSTED_TEST_RUNNER:
        raise ci_pytest.PolicyError(
            "qualification gates must run on a clean GitHub-hosted runner"
        )
    timeout = qual.get("timeout-minutes")
    if type(timeout) is not int or not 5 <= timeout <= 20:
        raise ci_pytest.PolicyError("qualification timeout must be finite and bounded")
    steps = qual.get("steps")
    # The typecheck is required here by name and command, exactly once: it
    # is the only typecheck a full merge group, push or manual run gets.
    typecheck = [
        step for step in steps
        if isinstance(step, dict) and step.get("name") == _TYPECHECK_GATE_NAME
    ] if isinstance(steps, list) else []
    if (
        len(typecheck) != 1
        or typecheck[0].get("if") is not None
        or typecheck[0].get("continue-on-error") is not None
        or _TYPECHECK_COMMAND not in str(typecheck[0].get("run", "")).splitlines()
    ):
        raise ci_pytest.PolicyError(
            "qualification job must typecheck the web application unconditionally"
        )
    if not isinstance(steps, list) or len(steps) != len(_EXPECTED_QUALIFICATION_STEPS):
        raise ci_pytest.PolicyError("qualification steps missing or duplicated")
    if steps != _EXPECTED_QUALIFICATION_STEPS:
        raise ci_pytest.PolicyError("qualification lane source or commands drifted")
    for step in steps:
        if not isinstance(step, dict) or step.get("continue-on-error") is not None:
            raise ci_pytest.PolicyError("qualification gates may not bypass failures")
        if step.get("if") is not None:
            raise ci_pytest.PolicyError("qualification steps must be unconditional")
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            with_ = step.get("with")
            if not isinstance(with_, dict) or (
                with_.get("persist-credentials") is not False
                or type(with_.get("fetch-depth")) is not int
            ):
                raise ci_pytest.PolicyError(
                    "qualification checkout must be full-history without credentials"
                )


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
        or fast.get("runs-on") != HOSTED_TEST_RUNNER
        or fast.get("timeout-minutes") != 8
        or fast.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError("PR scope must be trusted and PR fast lane must be bounded")
    scope_steps, fast_steps = scope.get("steps"), fast.get("steps")
    if not isinstance(scope_steps, list) or len(scope_steps) != 3 or not isinstance(fast_steps, list) or len(fast_steps) != 8:
        raise ci_pytest.PolicyError("PR scope/fast steps missing or duplicated")
    if scope_steps != _EXPECTED_SCOPE_STEPS or fast_steps != _EXPECTED_FAST_STEPS:
        raise ci_pytest.PolicyError("PR fast lane source or commands drifted")
    checkout, python_setup, qualifier = scope_steps
    if (
        checkout.get("uses") != "actions/checkout@v4"
        or checkout.get("with") != {"fetch-depth": 0, "persist-credentials": False}
        or python_setup.get("uses") != "actions/setup-python@v5"
        or python_setup.get("with") != {"python-version": "3.12"}
        or python_setup.get("if") is not None
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
        None, None, "Verify exact changed source without executing untrusted PR text",
        "Checkout pinned Macro engine for source-proximate tests",
        "Install focused Python test dependencies",
        "Bounded source-proximate PR tests", None,
        "Typecheck affected web application",
    ]:
        raise ci_pytest.PolicyError("PR fast steps must preserve exact bounded checks")
    for i in (0, 1, 3, 6):
        if fast_steps[i].get("uses") != [
            "actions/checkout@v4", "actions/setup-python@v5",
            "actions/checkout@v4", "actions/setup-node@v4",
        ][(0, 1, 3, 6).index(i)]:
            raise ci_pytest.PolicyError("PR fast check toolchain is invalid")
    if fast_steps[0].get("with") != {"fetch-depth": 0, "persist-credentials": False}:
        raise ci_pytest.PolicyError("PR fast checkout must not persist credentials")
    if fast_steps[3]["with"].get("persist-credentials") is not False:
        raise ci_pytest.PolicyError("PR smoke fixture checkout must not persist credentials")
    if (
        fast_steps[1].get("if") is not None
        or fast_steps[3].get("if") != "${{ needs.pr_scope.outputs.mode == 'smoke' }}"
        or fast_steps[4].get("if") != fast_steps[3].get("if")
        or fast_steps[5].get("if") != fast_steps[3].get("if")
        or fast_steps[6].get("if") != "${{ needs.pr_scope.outputs.needs_node == 'true' }}"
        or fast_steps[7].get("if") != fast_steps[6].get("if")
        or "git diff --check" not in str(fast_steps[2].get("run"))
        or fast_steps[4].get("run") != 'python -m pip install --disable-pip-version-check -e ".[dev]"'
        or "python -m scripts.ci_pr_smoke" not in str(fast_steps[5].get("run"))
        or "npm --prefix app/mastermind_os run typecheck" not in str(fast_steps[7].get("run"))
    ):
        raise ci_pytest.PolicyError("PR fast lane must retain source, Python, and web checks")


_REQUIRED_GATE_RUN = ('set -euo pipefail\n'
 'if [ "$EVENT_TYPE" = "pull_request" ] || [ "$EVENT_TYPE" = "merge_group" ]; then\n'
 '  if [ "$PR_SCOPE_STATUS" != success ]; then\n'
 '    echo "trusted source risk qualification unavailable"\n'
 '    exit 1\n'
 '  fi\n'
 '  if [ "$GUARDS_STATUS" != success ]; then\n'
 '    echo "pinned source-identity guards must pass"\n'
 '    exit 1\n'
 '  fi\n'
 '  case "$PR_SCOPE_MODE" in\n'
 '    full)\n'
 '      if [ "$SHARDS_STATUS" != success ] || [ "$QUAL_STATUS" != success ] || [ "$PR_FAST_STATUS" != skipped ]; then\n'
 '        echo "critical/unqualified source must pass all six pytest shards"\n'
 '        exit 1\n'
 '      fi\n'
 '      ;;\n'
 '    fast|smoke)\n'
 '      if [ "$PR_FAST_STATUS" != success ] || [ "$SHARDS_STATUS" != skipped ] || [ "$QUAL_STATUS" != skipped ]; then\n'
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
 '  # Protected pushes and deliberate manual CI always run all shards\n'
 '  # and every non-pytest qualification gate. Excluded guard modules\n'
 '  # must pass here too: manual runs and pushes without reusable\n'
 '  # proof still require complete coverage.\n'
 '  if [ "$SHARDS_STATUS" != success ] || [ "$QUAL_STATUS" != success ] ||\n'
 '     [ "$PR_FAST_STATUS" != skipped ] || [ "$PR_SCOPE_STATUS" != skipped ] ||\n'
 '     [ "$GUARDS_STATUS" != success ]; then\n'
 '    echo "integration/release CI must pass the full matrix"\n'
 '    exit 1\n'
 '  fi\n'
 'fi\n'
 '# Revalidate the same canonical test discovery/exclusion/cover plan.\n'
 '# Source-scoped checks never change canonical discovery.\n'
 'python scripts/ci_pytest.py --plan-only --jobs 6\n')



def validate_parallel_workflow(text: str) -> None:
    """Ensure the required "test" gate cannot pass without every shard."""
    import yaml

    ci_pytest.validate_workflow(text)
    payload = yaml.load(text, Loader=ci_pytest._WorkflowYAMLLoader)
    if payload.get("permissions") != {"contents": "read"}:
        raise ci_pytest.PolicyError("CI workflow root may only read source")
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"pr_scope", "pr_fast", "pin_guards", "qualification", "pytest_shards", "test"}:
        raise ci_pytest.PolicyError("parallel CI requires one trusted scope, PR fast check, pin guards, qualification gates, shards, and test gate")
    _validate_pr_fast_lane(jobs)
    _validate_pin_guards_lane(jobs)
    _validate_qualification_lane(jobs)
    shards, gate = jobs["pytest_shards"], jobs["test"]
    if not isinstance(shards, dict) or not isinstance(gate, dict):
        raise ci_pytest.PolicyError("parallel CI job configuration is invalid")
    if shards.get("permissions") != {"contents": "read", "actions": "read"} or gate.get("permissions") is not None:
        raise ci_pytest.PolicyError("Actions proof permission must be scoped to pytest shard jobs only")
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
    if shards.get("runs-on") != HOSTED_TEST_RUNNER:
        raise ci_pytest.PolicyError("pytest shards must run on the GitHub-hosted test image")
    if (
        gate.get("name") != "test"
        or gate.get("needs") != ["pr_scope", "pr_fast", "pin_guards", "qualification", "pytest_shards"]
        or gate.get("if") != "${{ always() }}"
        or gate.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError("required test job must always aggregate all shards")

    # Guard each hosted job's total wall-clock budget, not just pytest time.
    # Preserve the existing <=100-minute shard+fan-in source contract (the
    # current server queue is180m). Real prerequisites took ~23m before the
    # unchanged45m repository step; reserve bounded upload/cleanup headroom.
    # The qualification lane runs beside the shards (not on their critical
    # path) and is bounded inside _validate_qualification_lane.
    shard_timeout = shards.get("timeout-minutes")
    gate_timeout = gate.get("timeout-minutes")
    if (
        type(shard_timeout) is not int
        or not 45 <= shard_timeout <= 75
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
    if not isinstance(shard_steps, list) or not isinstance(gate_steps, list):
        raise ci_pytest.PolicyError("parallel CI steps are missing")
    # GitHub step expressions address IDs rather than displayed names. A later
    # duplicate, including one with different casing, could shadow the pinned
    # previous_ci producer and falsely report reuse=true to skip pytest. Require
    # global uniqueness across both CI jobs rather than depending on runner
    # behavior for duplicate IDs.
    seen_step_ids: set[str] = set()
    for step in (*jobs["pr_scope"]["steps"], *jobs["pr_fast"]["steps"],
                 *jobs["pin_guards"]["steps"], *jobs["qualification"]["steps"],
                 *shard_steps, *gate_steps):
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
    # Only the two incumbent Macro fixtures may follow the event checkout;
    # their dedicated paths cannot replace the selected repository source.
    external_checkouts = [
        step for step in shard_steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
        and isinstance(step.get("with"), dict) and step["with"].get("repository")
    ]
    fixture_paths = {
        "Checkout pinned Macro engine": "vendor/macro_src",
        "Checkout paired Brain production owner fixture": ".ci-production-macro",
    }
    if (len(external_checkouts) != 2
            or {step.get("name") for step in external_checkouts} != set(fixture_paths)
            or any(step.get("uses") != "actions/checkout@v4"
                   or step["with"].get("repository") != "mastermindx-market-intelligence/macro"
                   or step["with"].get("path") != fixture_paths.get(step.get("name"))
                   or step["with"].get("persist-credentials") is not False
                   for step in external_checkouts)):
        raise ci_pytest.PolicyError("later checkouts must retain the two isolated Macro fixture paths")
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
        or runner.get("run") != "python -m scripts.ci_parallel_shard --jobs 6 --index ${{ matrix.index }}"
        or runner.get("if") != "${{ steps.previous_ci.outputs.reuse != 'true' }}"
    ):
        raise ci_pytest.PolicyError("prior merged CI proof must fail closed before every shard")
    native = [step for step in shard_steps
              if step.get("name") == "Verify native application admission and dispatch custody"]
    if (len(native) != 1 or native[0].get("if") != "matrix.index == 5"
            or shard_steps.index(native[0]) >= shard_steps.index(proof)):
        raise ci_pytest.PolicyError(
            "native admission gate must run once on assigned shard five before reuse proof"
        )
    # CI Lightning F3: the five non-pytest qualification gates moved out of
    # shard zero into the parallel qualification job (their exact trusted
    # bodies are pinned by _EXPECTED_QUALIFICATION_STEPS). They must not
    # linger inside a shard: a second copy would re-serialize the same
    # minutes the split removed, and the qualification lane is the only
    # allowed owner of these command surfaces. The same holds for the
    # web application typecheck added to that job.
    for name in (
        "Verify Paper direct pinned MCP SDK",
        "Verify Paper Studio prepare guard",
        "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
        "Compile source", "Validate shell scripts", _TYPECHECK_GATE_NAME,
    ):
        if any(isinstance(step, dict) and step.get("name") == name
               for step in shard_steps):
            raise ci_pytest.PolicyError(
                "non-pytest qualification gates must run only in the qualification job"
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
            "GUARDS_STATUS": "${{ needs.pin_guards.result }}",
            "QUAL_STATUS": "${{ needs.qualification.result }}",
            "SHARDS_STATUS": "${{ needs.pytest_shards.result }}",
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
        for step in (*shard_steps, *gate_steps)
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
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve() if args.root else ci_pytest.repo_root()

    try:
        validate_parallel_workflow(
            (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        )
        gate, selected, digest = shard_plan(
            root, jobs=args.jobs, index=args.index
        )
    except ci_pytest.PolicyError as error:
        print(f"ci_parallel_shard policy error: {error}", file=sys.stderr)
        return 2

    print(ci_pytest.format_plan(gate["plan"]), flush=True)
    print(
        f"parallel_shard={args.index + 1}/{args.jobs} "
        f"modules={len(selected)} included_sha256={digest}",
        flush=True,
    )
    if args.plan_only:
        return 0
    # No hand-written selectors, mutating retry, positive allowlist or shell.
    completed = subprocess.run(
        ci_pytest.pytest_argv(selected, progress=True),
        cwd=root,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
