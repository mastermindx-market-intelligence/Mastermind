"""Protect the single required CI status while pytest shards use separate runners."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"


def test_live_ci_workflow_fan_in_is_fail_closed_and_uses_six_full_shards() -> None:
    text = _WORKFLOW.read_text(encoding="utf-8")
    fan.validate_parallel_workflow(text)
    import yaml

    data = yaml.load(text, Loader=cip._WorkflowYAMLLoader)
    assert data["on"] == {
        "pull_request": None,
        "merge_group": {"types": ["checks_requested"]},
        "push": {"branches": ["master"]},
        "workflow_dispatch": None,
    }
    assert set(data["jobs"]) == {"pr_scope", "pr_fast", "pin_guards", "qualification", "pytest_shards", "test"}
    shards = data["jobs"]["pytest_shards"]
    assert shards["strategy"]["matrix"]["index"] == [0, 1, 2, 3, 4, 5]
    assert shards["strategy"]["fail-fast"] is False
    assert shards["strategy"]["max-parallel"] == 6
    assert shards["runs-on"] == "ubuntu-24.04"
    assert shards["env"] == {"CI_PYTEST_WORKERS": "4"}
    assert type(shards["timeout-minutes"]) is int
    assert 45 <= shards["timeout-minutes"] <= 75
    assert type(data["jobs"]["test"]["timeout-minutes"]) is int
    assert shards["timeout-minutes"] + data["jobs"]["test"]["timeout-minutes"] <= 100
    assert data["jobs"]["test"]["name"] == "test"
    assert data["jobs"]["test"]["needs"] == ["pr_scope", "pr_fast", "pin_guards", "qualification", "pytest_shards"]


def test_smoke_checkout_uses_the_full_shard_pinned_fixture_without_credentials():
    import yaml

    text = _WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=cip._WorkflowYAMLLoader)
    smoke = workflow["jobs"]["pr_fast"]["steps"][3]
    full = next(
        step for step in workflow["jobs"]["pytest_shards"]["steps"]
        if step.get("name") == "Checkout pinned Macro engine"
    )
    assert smoke["name"] == "Checkout pinned Macro engine for source-proximate tests"
    assert smoke["uses"] == full["uses"] == "actions/checkout@v4"
    assert smoke["with"] == full["with"]
    assert smoke["with"]["persist-credentials"] is False
    assert smoke["if"] == "${{ needs.pr_scope.outputs.mode == 'smoke' }}"
    fan.validate_parallel_workflow(text)


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "ref", "repository", "path", "sparse-checkout",
    "credentials", "missing-credentials", "string-credentials", "numeric-credentials",
    "token", "action", "condition", "missing-condition", "reordered",
    "continue-on-error", "extra-command",
])
def test_smoke_dependency_checkout_cannot_drift_or_bypass_its_boundary(mutation):
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    steps = workflow["jobs"]["pr_fast"]["steps"]
    fixture = steps[3]
    assert fixture["name"] == "Checkout pinned Macro engine for source-proximate tests"
    fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
    if mutation == "missing":
        steps.pop(3)
    elif mutation == "duplicate":
        steps.insert(4, dict(fixture))
    elif mutation in {"ref", "repository", "path", "sparse-checkout", "token"}:
        fixture["with"][mutation] = {
            "ref": "master",
            "repository": "other/repository",
            "path": ".",
            "sparse-checkout": "engine\n",
            "token": "${{ secrets.OTHER_TOKEN }}",
        }[mutation]
    elif mutation == "credentials":
        fixture["with"]["persist-credentials"] = True
    elif mutation == "missing-credentials":
        fixture["with"].pop("persist-credentials")
    elif mutation == "string-credentials":
        fixture["with"]["persist-credentials"] = "false"
    elif mutation == "numeric-credentials":
        fixture["with"]["persist-credentials"] = 0
    elif mutation == "action":
        fixture["uses"] = "actions/checkout@v3"
    elif mutation == "condition":
        fixture["if"] = "${{ always() }}"
    elif mutation == "missing-condition":
        fixture.pop("if")
    elif mutation == "reordered":
        steps[3], steps[4] = steps[4], steps[3]
    elif mutation == "continue-on-error":
        fixture["continue-on-error"] = True
    else:
        fixture["run"] = "echo unexpected"
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize(
    ("preimage", "mutation"),
    [
        # Finite wall-clock budgets are mandatory; no silent removal or
        # enormous timeout may bypass the queue's 100-minute check window.
        ("    timeout-minutes: 75", ""),
        ("    timeout-minutes: 75", "    timeout-minutes: null"),
        ("    timeout-minutes: 75", "    timeout-minutes: true"),
        ("    timeout-minutes: 75", '    timeout-minutes: "75"'),
        ("    timeout-minutes: 75", "    timeout-minutes: 0"),
        ("    timeout-minutes: 75", "    timeout-minutes: -5"),
        ("    timeout-minutes: 75", "    timeout-minutes: 44"),
        ("    timeout-minutes: 75", "    timeout-minutes: 76"),
        ("    timeout-minutes: 75", "    timeout-minutes: 93"),
        ("    timeout-minutes: 75", "    timeout-minutes: 120"),
        ("    timeout-minutes: 8", ""),
        ("    timeout-minutes: 8", "    timeout-minutes: null"),
        ("    timeout-minutes: 8", "    timeout-minutes: 0"),
        ("    timeout-minutes: 8", "    timeout-minutes: 90"),
        ("fail-fast: false", "fail-fast: true"),
        ("index: [0, 1, 2, 3, 4, 5]", "index: [0, 2, 3, 4, 5]"),
        # Matrix exclude can delete shard zero while leaving the remaining
        # jobs green; the fan-in only sees the matrix's overall success.
        (
            "index: [0, 1, 2, 3, 4, 5]",
            "index: [0, 1, 2, 3, 4, 5]\n        exclude:\n          - index: 0",
        ),
        (
            "index: [0, 1, 2, 3, 4, 5]",
            "index: [0, 1, 2, 3, 4, 5]\n        include:\n          - index: 6",
        ),
        (
            "index: [0, 1, 2, 3, 4, 5]",
            "index: [0, 1, 2, 3, 4, 5]\n        python: [3.12]",
        ),
        ("needs: [pr_scope, pr_fast, pin_guards, qualification, pytest_shards]", "needs: []"),
        ("if: ${{ always() }}", "if: false"),
        ("SHARDS_STATUS: ${{ needs.pytest_shards.result }}", "SHARDS_STATUS: wrong"),
        ('if [ "$PR_SCOPE_STATUS" != success ]; then', "if [ \"$PR_SCOPE_STATUS\" = failure ]; then"),
        ("exit 1", "exit 0"),
        ("exit 1", "# exit 1"),
        (
            "      - name: Run repository test gate\n        env:",
            "      - name: Run repository test gate\n        if: false\n        env:",
        ),
        (
            "      - name: Run repository test gate\n        env:",
            "      - name: Run repository test gate\n        if: ${{ github.event_name == 'pull_request' }}\n        env:",
        ),
        ("exit 1\n            fi", "echo \"not stopping\"\n            fi\n            exit 1"),
        (
            "python -m scripts.ci_parallel_shard --jobs 6 --index ${{ matrix.index }}",
            "python -m scripts.ci_parallel_shard --jobs 6 --index 0",
        ),
        # CI Lightning F3: the Fabric gate lives in the qualification lane;
        # regressions target the lane's exact step text (no shard `if`).
        (
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        working-directory: integrations/studio_direct_mcp",
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        if: false\n"
            "        working-directory: integrations/studio_direct_mcp",
        ),
        (
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        working-directory: integrations/studio_direct_mcp",
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        if: matrix.index == 2\n"
            "        working-directory: integrations/studio_direct_mcp",
        ),
        (
            # Target the *required Fabric gate*, not whichever earlier
            # independent Studio/ Paper qualification step shares its cwd.
            # Otherwise a new legitimate preflight silently redirects this
            # regression to the wrong tool and produces a false failure.
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        working-directory: integrations/studio_direct_mcp",
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        working-directory: integrations/wrong_mcp",
        ),
        (
            "      - name: Verify Paper Studio prepare guard\n        working-directory: integrations/studio_direct_mcp",
            "      - name: Verify Paper Studio prepare guard\n        if: false\n        working-directory: integrations/studio_direct_mcp",
        ),
        (
            "gateway-shared-backend.test.mjs ",
            "",
        ),
        (
            "gateway-fleet-git-failure.test.mjs ",
            "",
        ),
        (
            "control_bundle*test.py",
            "",
        ),
        (
            "python -m unittest discover -s . -p 'private_service*test.py'",
            "echo bypass",
        ),
        (
            "npm ci --ignore-scripts --no-audit --no-fund",
            "echo bypass",
        ),
        (
            "python scripts/ci_pytest.py --plan-only --jobs 6",
            "python scripts/ci_pytest.py --jobs 1",
        ),
    ],
)
def test_unsafe_matrix_or_required_fanin_regression_is_refused(
    preimage: str, mutation: str
) -> None:
    baseline = _WORKFLOW.read_text(encoding="utf-8")
    assert preimage in baseline
    changed = baseline.replace(preimage, mutation, 1)
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(changed)


def test_all_matrix_shards_exactly_cover_canonical_discovery_once() -> None:
    gate = cip.resolve_gate(_ROOT)
    included = gate["included"]
    shards = cip.partition_modules(included, jobs=6)
    cip.verify_partition(included, shards)
    assert len(shards) == 6
    seen: set[str] = set()
    digests: set[str] = set()
    for index in range(6):
        plan, selected, digest = fan.shard_plan(_ROOT, jobs=6, index=index)
        assert plan["included"] == included
        assert selected == shards[index]
        assert seen.isdisjoint(selected)
        seen.update(selected)
        digests.add(digest)
    assert seen == set(included)
    assert len(digests) == 1


def _stub_gate(monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    included = tuple(f"tests/test_fixture_{index}.py" for index in range(120))
    monkeypatch.setattr(
        fan.ci_pytest, "resolve_gate",
        lambda root: {
            "included": included,
            "plan": {
                "discovered": len(included),
                "excluded": 0,
                "running": len(included),
            },
        },
    )
    monkeypatch.setattr(fan, "validate_parallel_workflow", lambda text: None)
    return included


def test_worker_executes_only_its_exact_canonical_shard_and_preserves_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    included = _stub_gate(monkeypatch)
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text("fixture", encoding="utf-8")
    recorded: list[tuple[list[str], Path, bool]] = []

    def fake_run(args, *, cwd, check):
        recorded.append((args, cwd, check))
        return subprocess.CompletedProcess(args=args, returncode=17)

    monkeypatch.setattr(fan.subprocess, "run", fake_run)
    code = fan.main(["--jobs", "6", "--index", "1", "--root", str(tmp_path)])
    assert code == 17  # A failed shard cannot become a green matrix leg.
    expected = cip.partition_modules(included, jobs=6)[1]
    assert recorded == [
        (cip.pytest_argv(expected, progress=True), tmp_path.resolve(), False),
    ]


@pytest.mark.parametrize(
    ("jobs", "index"),
    [(0, 0), (1, 0), (2, 0), (4, 0), (6, -1), (6, 6)],
)
def test_invalid_worker_configuration_is_refused_before_execution(
    jobs: int, index: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_gate(monkeypatch)
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(
        fan.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("invalid shard must not run pytest"),
    )
    assert (
        fan.main(
            ["--jobs", str(jobs), "--index", str(index), "--root", str(tmp_path)]
        )
        == 2
    )


def test_plan_only_does_not_run_any_test(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_gate(monkeypatch)
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(
        fan.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("plan-only must not spawn pytest"),
    )
    assert fan.main(
        ["--jobs", "6", "--index", "2", "--plan-only", "--root", str(tmp_path)]
    ) == 0
    assert "parallel_shard=3/6" in capsys.readouterr().out


def _shard_runner_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    included = _stub_gate(monkeypatch)
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True, exist_ok=True)
    (workflow / "ci.yml").write_text("fixture", encoding="utf-8")
    return included


def test_worker_switch_runs_shard_pytest_under_loadfile_xdist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    included = _shard_runner_env(tmp_path, monkeypatch)
    monkeypatch.setenv("CI_PYTEST_WORKERS", "4")
    recorded: list[list[str]] = []
    monkeypatch.setattr(
        fan.subprocess, "run",
        lambda args, **kwargs: (recorded.append(list(args)),
                                subprocess.CompletedProcess(args=args, returncode=0))[1],
    )
    assert fan.main(["--jobs", "6", "--index", "1", "--root", str(tmp_path)]) == 0
    assert len(recorded) == 1
    argv = recorded[0]
    assert argv[argv.index("-q") + 1:argv.index("-q") + 5] == [
        "-n", "4", "--dist", "loadfile",
    ]
    expected = cip.partition_modules(included, jobs=6)[1]
    assert argv[-len(expected):] == list(expected)
    out = capsys.readouterr().out
    assert "pytest_workers=4 dist=loadfile" in out
    assert out.index("parallel_shard=2/6") < out.index("pytest_workers=4")


def test_worker_switch_serial_rollback_runs_exact_serial_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _shard_runner_env(tmp_path, monkeypatch)
    monkeypatch.setenv("CI_PYTEST_WORKERS", "1")
    recorded: list[list[str]] = []
    monkeypatch.setattr(
        fan.subprocess, "run",
        lambda args, **kwargs: (recorded.append(list(args)),
                                subprocess.CompletedProcess(args=args, returncode=0))[1],
    )
    assert fan.main(["--jobs", "6", "--index", "1", "--root", str(tmp_path)]) == 0
    assert len(recorded) == 1
    assert "-n" not in recorded[0] and "--dist" not in recorded[0]
    out = capsys.readouterr().out
    assert "pytest_workers=" not in out


def test_malformed_worker_switch_refuses_before_any_pytest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _shard_runner_env(tmp_path, monkeypatch)
    monkeypatch.setenv("CI_PYTEST_WORKERS", "many")
    monkeypatch.setattr(
        fan.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("malformed switch must not run pytest"),
    )
    assert fan.main(["--jobs", "6", "--index", "1", "--root", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    "env_value",
    [None, "2", "8", "04", {"CI_PYTEST_WORKERS": "4", "OTHER": "1"}, {"CI_PYTEST_WORKER": "4"}],
)
def test_shard_worker_switch_env_is_pinned_by_the_validator(env_value) -> None:
    import yaml

    payload = yaml.load(
        _WORKFLOW.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader
    )
    shards = payload["jobs"]["pytest_shards"]
    if env_value is None:
        shards.pop("env")
    else:
        shards["env"] = env_value
    with pytest.raises(cip.PolicyError, match="CI_PYTEST_WORKERS"):
        fan.validate_parallel_workflow(yaml.dump(payload))


@pytest.mark.parametrize("rollback", ["0", "1", "4"])
def test_validator_accepts_only_the_pinned_worker_switch_values(rollback: str) -> None:
    import copy
    import yaml

    payload = yaml.load(
        _WORKFLOW.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader
    )
    payload["jobs"]["pytest_shards"]["env"] = {"CI_PYTEST_WORKERS": rollback}
    fan.validate_parallel_workflow(yaml.dump(payload))


def test_same_sha_reuse_is_step_scoped_and_required_fanin_stays_unconditional() -> None:
    """Only the pytest step can be omitted after a verified merge-group run."""
    import yaml

    data = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    assert data["permissions"] == {"contents": "read"}
    assert data["jobs"]["pytest_shards"]["permissions"] == {"contents": "read", "actions": "read"}
    steps = data["jobs"]["pytest_shards"]["steps"]
    proof_step = next(s for s in steps if s.get("id") == "previous_ci")
    shard_step = next(s for s in steps if s.get("name") == "Run repository test shard")
    assert steps.index(proof_step) < steps.index(shard_step)
    assert proof_step == {
        "name": "Verify exact prior merge-group CI",
        "id": "previous_ci",
        "env": {"GH_TOKEN": "${{ github.token }}"},
        "run": "python -m scripts.ci_postmerge_proof",
    }
    assert shard_step == {
        "name": "Run repository test shard",
        "if": "${{ steps.previous_ci.outputs.reuse != 'true' }}",
        "timeout-minutes": 45,
        "run": "python -m scripts.ci_parallel_shard --jobs 6 --index ${{ matrix.index }}",
    }
    assert "env" not in shard_step  # Do not expose the Actions token to pytest.
    assert data["jobs"]["test"]["if"] == "${{ always() }}"
    fan.validate_parallel_workflow(_WORKFLOW.read_text())


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("      actions: read", "      actions: write"),
        ("      actions: read", ""),
        ("id: previous_ci", "id: bypass"),
        ("GH_TOKEN: ${{ github.token }}", "GH_TOKEN: hardcoded"),
        ("python -m scripts.ci_postmerge_proof", "echo 'reuse=true' >> $GITHUB_OUTPUT"),
        ("python -m scripts.ci_postmerge_proof", "echo bypass"),
        (
            "      - name: Verify exact prior merge-group CI\n        id: previous_ci",
            "      - name: Verify exact prior merge-group CI\n        if: false\n        id: previous_ci",
        ),
        (
            "if: ${{ steps.previous_ci.outputs.reuse != 'true' }}",
            "if: true",
        ),
        (
            "if: ${{ steps.previous_ci.outputs.reuse != 'true' }}",
            "if: ${{ github.event_name == 'push' }}",
        ),
        (
            "if: ${{ steps.previous_ci.outputs.reuse != 'true' }}",
            "if: ${{ steps.previous_ci.outputs.reuse == 'true' }}",
        ),
        (
            "      - name: Run repository test shard\n        if:",
            "      - name: Run repository test shard\n        continue-on-error: true\n        if:",
        ),
    ],
)
def test_untrusted_proof_or_skip_mutations_are_refused(old: str, new: str):
    baseline = _WORKFLOW.read_text()
    assert old in baseline
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(baseline.replace(old, new, 1))


@pytest.mark.parametrize("forged_id", ["previous_ci", "PREVIOUS_CI", "Previous_Ci"])
def test_forged_duplicate_proof_step_id_is_refused(forged_id: str):
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    steps.append({
        "name": "Forged reuse output",
        "id": forged_id,
        "run": "echo 'reuse=true' >> \"$GITHUB_OUTPUT\"",
    })
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("forged_id", ["previous_ci", "PREVIOUS_CI", "Previous_Ci"])
def test_cross_job_duplicate_proof_step_id_is_refused(forged_id: str):
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    workflow["jobs"]["test"]["steps"].append({
        "name": "Forged cross-job proof", "id": forged_id, "run": "echo ignored",
    })
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


def test_proof_after_pytest_is_refused():
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    proof_step = next(s for s in steps if s.get("id") == "previous_ci")
    steps.remove(proof_step)
    steps.append(proof_step)
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("name", [
    "Fast source-bound release preflight",
    "H1 initializer Linux fast preflight",
    "H1 required real Linux no-ACL positive journey",
])
@pytest.mark.parametrize("mode", ["missing", "duplicate", "reuse-gated"])
def test_reuse_cannot_remove_or_condition_current_release_gates(name, mode) -> None:
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader)
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    selected = next(step for step in steps if step.get("name") == name)
    if mode == "missing":
        steps.remove(selected)
    elif mode == "duplicate":
        steps.append(dict(selected))
    else:
        selected["if"] = "${{ steps.previous_ci.outputs.reuse != 'true' }}"
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("timeout", [None, 0, 46, 45.0, True])
def test_reuse_preserves_finite_existing_full_pytest_step_timeout(timeout) -> None:
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader)
    runner = next(step for step in workflow["jobs"]["pytest_shards"]["steps"]
                  if step.get("name") == "Run repository test shard")
    runner["timeout-minutes"] = timeout
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("mutation", ["missing", "reuse-gated", "wrong-directory", "wrong-command", "continue-on-error", "moved-back-into-shard-zero", "duplicate"])
def test_released_paper_prepare_gate_cannot_be_omitted_or_weakened(mutation):
    # CI Lightning F3: the released Paper prepare guard lives in the
    # qualification lane with its exact body pinned; weakening it there, or
    # moving a copy back into a shard, must fail the workflow validator.
    import yaml
    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    shard_steps = workflow["jobs"]["pytest_shards"]["steps"]
    qual_steps = workflow["jobs"]["qualification"]["steps"]
    guard = next(step for step in qual_steps
                 if step.get("name") == "Verify Paper Studio prepare guard")
    if mutation == "missing":
        qual_steps.remove(guard)
    elif mutation == "reuse-gated":
        guard["if"] = "${{ steps.previous_ci.outputs.reuse != 'true' }}"
    elif mutation == "wrong-directory":
        guard["working-directory"] = "."
    elif mutation == "wrong-command":
        guard["run"] = "echo skipped"
    elif mutation == "continue-on-error":
        guard["continue-on-error"] = True
    elif mutation == "moved-back-into-shard-zero":
        # The pre-F3 location is exactly the bypass this split removed: a
        # shard copy could be dropped or reuse-gated while the lane looks
        # green, so the gate must exist ONLY in the qualification job.
        qual_steps.remove(guard)
        moved = dict(guard)
        moved["if"] = "matrix.index == 0"
        shard_steps.insert(
            next(i for i, step in enumerate(shard_steps) if step.get("id") == "previous_ci"),
            moved,
        )
    else:
        qual_steps.append(dict(guard))
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


def test_primary_checkout_never_persists_expanded_proof_credentials():
    import yaml
    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    primary = workflow["jobs"]["pytest_shards"]["steps"][1]
    assert primary["name"] == "Checkout event source"
    assert primary["uses"] == "actions/checkout@v4"
    assert primary["with"].get("persist-credentials") is False
    assert primary["with"].get("fetch-depth") == 0
    fan.validate_parallel_workflow(_WORKFLOW.read_text())


@pytest.mark.parametrize("mutation", ["missing", "true", "string-false", "numeric-zero", "fetch-depth", "conditional", "duplicate", "malformed-inputs"])
def test_primary_checkout_credential_boundary_is_load_bearing(mutation):
    import yaml
    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    primary = steps[1]
    primary["with"]["persist-credentials"] = False
    fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
    if mutation == "missing":
        primary["with"].pop("persist-credentials")
    elif mutation == "true":
        primary["with"]["persist-credentials"] = True
    elif mutation == "string-false":
        primary["with"]["persist-credentials"] = "false"
    elif mutation == "numeric-zero":
        primary["with"]["persist-credentials"] = 0
    elif mutation == "fetch-depth":
        primary["with"]["fetch-depth"] = 1
    elif mutation == "conditional":
        primary["if"] = "${{ false }}"
    elif mutation == "malformed-inputs":
        primary["with"] = []
    else:
        steps.append(dict(primary))
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


@pytest.mark.parametrize("mutation", [
    "wrong-anchor", "missing-anchor", "missing-event", "reversed", "interposed-code",
    "anchor-credentials", "anchor-conditional", "anchor-path", "anchor-depth-type",
    "event-ref", "event-continue", "missing-proof", "wrong-event-proof", "ignored-proof",
    "explicit-root-checkout", "other-root-checkout", "fixture-root-path", "fixture-credentials",
])
def test_fixture_anchor_acquisition_preserves_event_source_boundary(mutation):
    import yaml
    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    if mutation == "wrong-anchor":
        steps[0]["with"]["ref"] = "0" * 40
    elif mutation == "missing-anchor":
        steps.pop(0)
    elif mutation == "missing-event":
        steps.pop(1)
    elif mutation == "reversed":
        steps[0], steps[1] = steps[1], steps[0]
    elif mutation == "interposed-code":
        steps.insert(1, {"run": "python -m scripts.ci_parallel_shard"})
    elif mutation == "anchor-credentials":
        steps[0]["with"]["persist-credentials"] = True
    elif mutation == "anchor-conditional":
        steps[0]["if"] = "${{ false }}"
    elif mutation == "anchor-path":
        steps[0]["with"]["path"] = "other"
    elif mutation == "anchor-depth-type":
        steps[0]["with"]["fetch-depth"] = True
    elif mutation == "event-ref":
        steps[1]["with"]["ref"] = "master"
    elif mutation == "event-continue":
        steps[1]["continue-on-error"] = True
    elif mutation == "missing-proof":
        steps.pop(2)
    elif mutation == "wrong-event-proof":
        steps[2]["run"] = "git cat-file -e HEAD"
    elif mutation in {"explicit-root-checkout", "other-root-checkout"}:
        repository = ("mastermindx-market-intelligence/Mastermind"
                      if mutation == "explicit-root-checkout" else "other/repository")
        steps.append({"uses": "actions/checkout@v4", "with": {"repository": repository}})
    elif mutation in {"fixture-root-path", "fixture-credentials"}:
        fixture = next(step for step in steps if step.get("name") == "Checkout pinned Macro engine")
        if mutation == "fixture-root-path":
            fixture["with"]["path"] = "."
        else:
            fixture["with"]["persist-credentials"] = True
    else:
        steps[2]["continue-on-error"] = True
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))


def test_new_ci_selector_first_install_fallback_is_real_full_mode(tmp_path):
    """Hosted first-install when protected base has no classifier: full suite.

    Execute the exact shell fallback, not a string-only claim that it would
    set mode=full. A literal backslash-n must never reach the fan-in status.
    """
    import os
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    scope = next(
        step for step in workflow["jobs"]["pr_scope"]["steps"]
        if step.get("id") == "scope"
    )
    fallback = [
        line.strip() for line in scope["run"].splitlines()
        if line.strip().startswith("printf 'mode=full")
    ]
    assert len(fallback) == 1
    target = tmp_path / "github_output"
    result = subprocess.run(
        ["bash", "-e", "-c", fallback[0]], env={
            **os.environ, "GITHUB_OUTPUT": str(target),
        }, capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert target.read_text().splitlines() == [
        "mode=full", "tier=HOLD", "needs_node=false",
    ]


# Execute the workflow's real shell gate, not just its mirrored validator text.
# Only canonical plan execution is replaced with a recording stub; separate
# tests above prove the real discovery plan's exact six-shard coverage.
# states: (PR_SCOPE, PR_FAST, SHARDS, GUARDS, QUAL)
# Every case is a path the trusted classifier can actually produce. There is
# no merge_group smoke case: since #2439 a STANDARD merge group is full, so
# that path is unreachable (see the never-smoke test below).
_GATE_PASS_CASES = [
    ("pull_request", "full", ("success", "skipped", "success", "success", "success")),
    ("pull_request", "fast", ("success", "success", "skipped", "success", "skipped")),
    ("pull_request", "smoke", ("success", "success", "skipped", "success", "skipped")),
    ("merge_group", "full", ("success", "skipped", "success", "success", "success")),
    ("merge_group", "fast", ("success", "success", "skipped", "success", "skipped")),
    ("push", "", ("skipped", "skipped", "success", "success", "success")),
    ("workflow_dispatch", "", ("skipped", "skipped", "success", "success", "success")),
]


@pytest.mark.parametrize("tier", ["FAST", "STANDARD", "CRITICAL", "HOLD"])
def test_merge_group_scope_is_never_smoke_for_any_review_tier(
    tmp_path, monkeypatch, tier,
):
    """A merge group reaches the fan-in as fast (FAST) or full, never smoke.

    The risk tier is forced so the mapping is covered for every tier the
    shared policy can return, through the real classifier entry point the
    workflow calls. The same diff as a pull request does reach smoke, so the
    assertion is not vacuous.
    """
    import json
    import types

    from control_plane.github_review_risk_policy import ReviewTier
    from scripts import ci_pr_scope as scope

    repository = "mastermindx-market-intelligence/Mastermind"
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True,
            text=True, timeout=8,
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "example@example.test")
    git("config", "user.name", "Test")
    (root / "app").mkdir()
    (root / "app" / "customer.py").write_text("value = 1\n")
    git("add", ".")
    git("commit", "-qm", "protected base")
    base = git("rev-parse", "HEAD")
    (root / "app" / "customer.py").write_text("value = 2\n")
    git("add", ".")
    git("commit", "-qm", "queued change")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/master", base)
    monkeypatch.setattr(
        scope, "assess_review_risk",
        lambda facts: types.SimpleNamespace(tier=ReviewTier(tier)),
    )

    group = tmp_path / "merge-group.json"
    group.write_text(json.dumps({
        "repository": {"full_name": repository},
        "merge_group": {
            "base_sha": base, "head_sha": head, "base_ref": "refs/heads/master",
            "head_ref": "refs/heads/gh-readonly-queue/master/pr-42-verified",
        },
    }))
    queued = scope.select_scope(
        root, group, expected_repository=repository,
        event_type="merge_group", protected_base_sha=base,
    )
    assert queued.tier == tier
    assert queued.mode == ("fast" if tier == "FAST" else "full")
    assert queued.mode != "smoke"

    pull = tmp_path / "pull-request.json"
    pull.write_text(json.dumps({
        "repository": {"full_name": repository},
        "pull_request": {
            "number": 42,
            "head": {"sha": head, "repo": {"full_name": repository}},
            "base": {"sha": base, "repo": {"full_name": repository}},
        },
    }))
    as_pull_request = scope.select_scope(root, pull, expected_repository=repository)
    assert (as_pull_request.mode == "smoke") is (tier == "STANDARD")
    assert not [case for case in _GATE_PASS_CASES if case[:2] == ("merge_group", "smoke")]


def _run_exact_workflow_gate(tmp_path, event, mode, states, *, plan_exit=0):
    import os
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    gate = next(step for step in workflow["jobs"]["test"]["steps"]
                if step.get("name") == "Run repository test gate")
    calls = tmp_path / "plan-calls"
    python_stub = tmp_path / "python"
    python_stub.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CI_GATE_TEST_CALLS\"\n"
        "exit \"$CI_GATE_TEST_PLAN_EXIT\"\n"
    )
    python_stub.chmod(0o700)
    result = subprocess.run(
        ["/bin/bash", "-c", gate["run"]], cwd=tmp_path,
        env={
            "PATH": str(tmp_path) + os.pathsep + os.defpath,
            "EVENT_TYPE": event,
            "PR_SCOPE_MODE": mode,
            "PR_SCOPE_STATUS": states[0],
            "PR_FAST_STATUS": states[1],
            "SHARDS_STATUS": states[2],
            "GUARDS_STATUS": states[3],
            "QUAL_STATUS": states[4],
            "CI_GATE_TEST_CALLS": str(calls),
            "CI_GATE_TEST_PLAN_EXIT": str(plan_exit),
        }, capture_output=True, text=True, timeout=5,
    )
    return result, calls.read_text().splitlines() if calls.exists() else []


@pytest.mark.parametrize("event,mode,states", _GATE_PASS_CASES)
def test_actual_shell_gate_accepts_only_the_complete_expected_path(
    tmp_path, event, mode, states,
):
    result, calls = _run_exact_workflow_gate(tmp_path, event, mode, states)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == ["scripts/ci_pytest.py --plan-only --jobs 6"]


@pytest.mark.parametrize("event,mode,states,field,bad_status", [
    (*case, field, bad_status)
    for case in _GATE_PASS_CASES
    for field in range(5)
    for bad_status in ("success", "skipped", "failure", "cancelled", "", "unknown")
    if bad_status != case[2][field]
])
def test_actual_shell_gate_rejects_missing_failed_cancelled_or_wrong_job_states(
    tmp_path, event, mode, states, field, bad_status,
):
    changed = list(states)
    changed[field] = bad_status
    result, calls = _run_exact_workflow_gate(tmp_path, event, mode, changed)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize("mode", ["", "HOLD", "FAST", "unqualified"])
@pytest.mark.parametrize("states", [
    ("success", "skipped", "success", "success", "success"),
    ("success", "success", "skipped", "success", "skipped"),
])
def test_actual_shell_gate_rejects_unqualified_pr_modes(tmp_path, mode, states):
    result, calls = _run_exact_workflow_gate(tmp_path, "pull_request", mode, states)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
@pytest.mark.parametrize("mode", ["fast", "smoke"])
def test_actual_shell_gate_never_uses_pr_fast_results_for_release(tmp_path, event, mode):
    result, calls = _run_exact_workflow_gate(
        tmp_path, event, mode, ("success", "success", "skipped", "success", "success"),
    )
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize("event,mode,states", _GATE_PASS_CASES)
def test_actual_shell_gate_preserves_canonical_plan_failure(tmp_path, event, mode, states):
    result, calls = _run_exact_workflow_gate(
        tmp_path, event, mode, states, plan_exit=17,
    )
    assert result.returncode == 17
    assert calls == ["scripts/ci_pytest.py --plan-only --jobs 6"]


def test_actual_group_prerequisite_budget_cannot_preempt_repository_allowance():
    """Group514aa2/run42499015733: preflight16:16:23→repo16:39:17.

    The real job60 deadline cancelled repo after37m14, before its45m allowance.
    This is budget assembly only; final module summary did not prove process exit.
    """
    import yaml
    data = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    job = data['jobs']['pytest_shards']
    runner = next(s for s in job['steps'] if s.get('name') == 'Run repository test shard')
    upload = next(s for s in job['steps'] if s.get('name') == 'Upload fixed test diagnostics')
    observed_prerequisite_seconds = 22 * 60 + 54
    assert runner['timeout-minutes'] == 45
    assert upload['timeout-minutes'] == 2
    assert (observed_prerequisite_seconds + 60 * runner['timeout-minutes']
            + 60 * upload['timeout-minutes']) < 60 * job['timeout-minutes']
    assert job['timeout-minutes'] + data['jobs']['test']['timeout-minutes'] <= 100


@pytest.mark.parametrize("job", ["pytest_shards", "pr_fast"])
@pytest.mark.parametrize(
    "runner",
    ["ubuntu-latest", ["self-hosted", "linux", "x64"], "${{ vars.TEST_RUNNER }}"],
)
def test_test_executing_jobs_cannot_leave_the_hosted_image(job: str, runner) -> None:
    """Shards and the fast lane run the suite, so a shared-label runner is refused."""
    import yaml

    workflow = yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader)
    assert workflow["jobs"][job]["runs-on"] == fan.HOSTED_TEST_RUNNER == "ubuntu-24.04"
    # Scope classification and the fan-in run no suite and keep the shared label.
    assert workflow["jobs"]["pr_scope"]["runs-on"] == "ubuntu-latest"
    assert workflow["jobs"]["test"]["runs-on"] == "ubuntu-latest"
    workflow["jobs"][job]["runs-on"] = runner
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
