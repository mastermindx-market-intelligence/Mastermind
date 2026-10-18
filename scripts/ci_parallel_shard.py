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


def validate_parallel_workflow(text: str) -> None:
    """Ensure the required "test" gate cannot pass without every shard."""
    import yaml

    ci_pytest.validate_workflow(text)
    payload = yaml.load(text, Loader=ci_pytest._WorkflowYAMLLoader)
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"pytest_shards", "test"}:
        raise ci_pytest.PolicyError("parallel CI jobs must be exactly shards and test gate")
    shards, gate = jobs["pytest_shards"], jobs["test"]
    if not isinstance(shards, dict) or not isinstance(gate, dict):
        raise ci_pytest.PolicyError("parallel CI job configuration is invalid")
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
        or shards.get("if") is not None
        or shards.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError("parallel CI must execute all six shard indices")
    if (
        gate.get("name") != "test"
        or gate.get("needs") != ["pytest_shards"]
        or gate.get("if") != "${{ always() }}"
        or gate.get("continue-on-error") is not None
    ):
        raise ci_pytest.PolicyError("required test job must always aggregate all shards")

    shard_steps = shards.get("steps", [])
    gate_steps = gate.get("steps", [])
    if not isinstance(shard_steps, list) or not isinstance(gate_steps, list):
        raise ci_pytest.PolicyError("parallel CI steps are missing")
    shard_runner = [
        step for step in shard_steps
        if isinstance(step, dict) and step.get("name") == "Run repository test shard"
    ]
    if (
        len(shard_runner) != 1
        or shard_runner[0].get("run")
        != "python -m scripts.ci_parallel_shard --jobs 6 --index ${{ matrix.index }}"
        or shard_runner[0].get("if") is not None
    ):
        raise ci_pytest.PolicyError("each matrix member must run its canonical shard")
    for name in (
        "Verify Paper direct pinned MCP SDK",
        "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
        "Compile source", "Validate shell scripts",
    ):
        matches = [
            step for step in shard_steps
            if isinstance(step, dict) and step.get("name") == name
        ]
        if len(matches) != 1 or matches[0].get("if") != "matrix.index == 0":
            raise ci_pytest.PolicyError("non-pytest CI gates must run in shard zero")
    # Preserve the incumbent protected Fabric compatibility gate's *actual*
    # executable surface. Merely pinning its name and shard index permits a
    # false-green gate if its Node or private-service tests are silently cut.
    fabric_name = "Verify private Fabric HTTP compatibility and incumbent backend lifetime"
    fabric_step = next(
        step for step in shard_steps
        if isinstance(step, dict) and step.get("name") == fabric_name
    )
    fabric_commands = [
        "npm ci --ignore-scripts --no-audit --no-fund",
        "node --test gateway-modern-fabric.test.mjs gateway.test.mjs gateway-shared-backend.test.mjs gateway-owner-lifecycle-regression.test.mjs gateway-output-budget.test.mjs fabric-backend.test.mjs private-cli.test.mjs private-tunnel-auth.test.mjs",
        "python -m unittest discover -s . -p 'private_service*test.py'",
    ]
    actual_commands = fabric_step.get("run")
    if (
        set(fabric_step) != {"name", "if", "working-directory", "run"}
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
    # The control-flow guard must be executable and ordered. A substring
    # search would falsely accept a commented-out `exit 1` or an exit placed
    # after `fi`, allowing a failed matrix to report a successful `test`.
    expected_lines = [
        'if [ "$SHARDS_STATUS" != success ]; then',
        'echo "required pytest shard matrix did not fully succeed"',
        "exit 1",
        "fi",
        "# Same discovery/exclusion/total-cover plan, never a test skip.",
        "python scripts/ci_pytest.py --plan-only --jobs 6",
    ]
    actual_lines = [line.strip() for line in code.splitlines() if line.strip()] if isinstance(code, str) else []
    env = final.get("env")
    if (
        not isinstance(env, dict)
        or env.get("SHARDS_STATUS") != "${{ needs.pytest_shards.result }}"
        or actual_lines != expected_lines
        or final.get("shell") not in (None, "bash")
        # A skipped required step can make the whole `test` job green while
        # its matrix failed, even when its shell body is otherwise correct.
        or final.get("if") is not None
    ):
        raise ci_pytest.PolicyError("required fan-in guard must reject non-success before parsing the plan")
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
