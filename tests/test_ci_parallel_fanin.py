"""Protect the single required CI status while pytest shards use separate runners."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"


def test_live_ci_workflow_fan_in_is_fail_closed_and_uses_three_full_shards() -> None:
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
    assert set(data["jobs"]) == {"pytest_shards", "test"}
    shards = data["jobs"]["pytest_shards"]
    assert shards["strategy"]["matrix"]["index"] == [0, 1, 2]
    assert shards["strategy"]["fail-fast"] is False
    assert shards["strategy"]["max-parallel"] == 3
    assert shards["runs-on"] == "ubuntu-latest"
    assert data["jobs"]["test"]["name"] == "test"
    assert data["jobs"]["test"]["needs"] == ["pytest_shards"]


@pytest.mark.parametrize(
    ("preimage", "mutation"),
    [
        ("fail-fast: false", "fail-fast: true"),
        ("index: [0, 1, 2]", "index: [0, 2]"),
        # Matrix exclude can delete shard zero while leaving the remaining
        # jobs green; the fan-in only sees the matrix's overall success.
        (
            "index: [0, 1, 2]",
            "index: [0, 1, 2]\n        exclude:\n          - index: 0",
        ),
        (
            "index: [0, 1, 2]",
            "index: [0, 1, 2]\n        include:\n          - index: 3",
        ),
        (
            "index: [0, 1, 2]",
            "index: [0, 1, 2]\n        python: [3.12]",
        ),
        ("needs: [pytest_shards]", "needs: []"),
        ("if: ${{ always() }}", "if: false"),
        ("SHARDS_STATUS: ${{ needs.pytest_shards.result }}", "SHARDS_STATUS: wrong"),
        ('if [ "$SHARDS_STATUS" != success ]; then', "if [ \"$SHARDS_STATUS\" = failure ]; then"),
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
        ("exit 1\n          fi", "echo \"not stopping\"\n          fi\n          exit 1"),
        (
            "python -m scripts.ci_parallel_shard --jobs 3 --index ${{ matrix.index }}",
            "python -m scripts.ci_parallel_shard --jobs 3 --index 0",
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
            "working-directory: integrations/studio_direct_mcp",
            "working-directory: integrations/wrong_mcp",
        ),
        (
            "gateway-shared-backend.test.mjs ",
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
            "python scripts/ci_pytest.py --plan-only --jobs 3",
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
    shards = cip.partition_modules(included, jobs=3)
    cip.verify_partition(included, shards)
    assert len(shards) == 3
    seen: set[str] = set()
    digests: set[str] = set()
    for index in range(3):
        plan, selected, digest = fan.shard_plan(_ROOT, jobs=3, index=index)
        assert plan["included"] == included
        assert selected == shards[index]
        assert seen.isdisjoint(selected)
        seen.update(selected)
        digests.add(digest)
    assert seen == set(included)
    assert len(digests) == 1


def _stub_gate(monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    included = tuple(f"tests/test_fixture_{index}.py" for index in range(12))
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
    code = fan.main(["--jobs", "3", "--index", "1", "--root", str(tmp_path)])
    assert code == 17  # A failed shard cannot become a green matrix leg.
    expected = cip.partition_modules(included, jobs=3)[1]
    assert recorded == [
        (cip.pytest_argv(expected, progress=True), tmp_path.resolve(), False),
    ]


@pytest.mark.parametrize(
    ("jobs", "index"),
    [(0, 0), (1, 0), (2, 0), (4, 0), (3, -1), (3, 3)],
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
        ["--jobs", "3", "--index", "2", "--plan-only", "--root", str(tmp_path)]
    ) == 0
    assert "parallel_shard=3/3" in capsys.readouterr().out



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
        "run": "python -m scripts.ci_parallel_shard --jobs 3 --index ${{ matrix.index }}",
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
