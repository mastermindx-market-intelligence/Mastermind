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
    assert set(data["jobs"]) == {"pr_scope", "pr_fast", "pin_guards", "pytest_shards", "test"}
    shards = data["jobs"]["pytest_shards"]
    assert shards["strategy"]["matrix"]["index"] == [0, 1, 2, 3, 4, 5]
    assert shards["strategy"]["fail-fast"] is False
    assert shards["strategy"]["max-parallel"] == 6
    assert shards["runs-on"] == "ubuntu-latest"
    assert type(shards["timeout-minutes"]) is int
    assert 45 <= shards["timeout-minutes"] <= 75
    assert type(data["jobs"]["test"]["timeout-minutes"]) is int
    assert shards["timeout-minutes"] + data["jobs"]["test"]["timeout-minutes"] <= 100
    assert data["jobs"]["test"]["name"] == "test"
    assert data["jobs"]["test"]["needs"] == ["pr_scope", "pr_fast", "pin_guards", "pytest_shards"]


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
        ("needs: [pr_scope, pr_fast, pin_guards, pytest_shards]", "needs: []"),
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
        ("if: matrix.index == 0", "if: matrix.index == 1"),
        (
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n        if: matrix.index == 0",
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n        if: matrix.index == 2",
        ),
        (
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n        if: matrix.index == 0",
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n        if: false",
        ),
        (
            # Target the *required Fabric gate*, not whichever earlier
            # independent Studio/ Paper qualification step shares its cwd.
            # Otherwise a new legitimate preflight silently redirects this
            # regression to the wrong tool and produces a false failure.
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        if: matrix.index == 0\n"
            "        working-directory: integrations/studio_direct_mcp",
            "      - name: Verify private Fabric HTTP compatibility and incumbent backend lifetime\n"
            "        if: matrix.index == 0\n"
            "        working-directory: integrations/wrong_mcp",
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


@pytest.mark.parametrize("mutation", ["missing", "reuse-gated", "wrong-directory", "wrong-command", "continue-on-error", "after-pytest", "duplicate"])
def test_released_paper_prepare_gate_cannot_be_omitted_or_weakened(mutation):
    import yaml
    workflow = yaml.load(_WORKFLOW.read_text(), Loader=cip._WorkflowYAMLLoader)
    steps = workflow["jobs"]["pytest_shards"]["steps"]
    # Add the exact already-released step for the RED pre-integration fixture.
    guard = next((step for step in steps if step.get("name") == "Verify Paper Studio prepare guard"), None)
    if guard is None:
        guard = {"name": "Verify Paper Studio prepare guard", "if": "matrix.index == 0",
                 "working-directory": "integrations/studio_direct_mcp",
                 "run": "node --test paper-design.test.mjs"}
        steps.insert(next(i for i, step in enumerate(steps) if step.get("id") == "previous_ci"), guard)
    fan.validate_parallel_workflow(yaml.safe_dump(workflow, sort_keys=False))
    if mutation == "missing":
        steps.remove(guard)
    elif mutation == "reuse-gated":
        guard["if"] = "${{ matrix.index == 0 && steps.previous_ci.outputs.reuse != 'true' }}"
    elif mutation == "wrong-directory":
        guard["working-directory"] = "."
    elif mutation == "wrong-command":
        guard["run"] = "echo skipped"
    elif mutation == "continue-on-error":
        guard["continue-on-error"] = True
    elif mutation == "after-pytest":
        steps.remove(guard)
        steps.append(guard)
    else:
        steps.append(dict(guard))
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
    scope = workflow["jobs"]["pr_scope"]["steps"][1]
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
_GATE_PASS_CASES = [
    ("pull_request", "full", ("success", "skipped", "success", "success")),
    ("pull_request", "fast", ("success", "success", "skipped", "success")),
    ("pull_request", "smoke", ("success", "success", "skipped", "success")),
    ("merge_group", "full", ("success", "skipped", "success", "success")),
    ("merge_group", "fast", ("success", "success", "skipped", "success")),
    ("merge_group", "smoke", ("success", "success", "skipped", "success")),
    ("push", "", ("skipped", "skipped", "success", "skipped")),
    ("workflow_dispatch", "", ("skipped", "skipped", "success", "skipped")),
]


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
    for field in range(4)
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
    ("success", "skipped", "success", "success"),
    ("success", "success", "skipped", "success"),
])
def test_actual_shell_gate_rejects_unqualified_pr_modes(tmp_path, mode, states):
    result, calls = _run_exact_workflow_gate(tmp_path, "pull_request", mode, states)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
@pytest.mark.parametrize("mode", ["fast", "smoke"])
def test_actual_shell_gate_never_uses_pr_fast_results_for_release(tmp_path, event, mode):
    result, calls = _run_exact_workflow_gate(
        tmp_path, event, mode, ("success", "success", "skipped", "success"),
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
