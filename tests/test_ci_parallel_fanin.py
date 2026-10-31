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
    assert type(shards["timeout-minutes"]) is int
    assert 45 <= shards["timeout-minutes"] <= 60
    assert type(data["jobs"]["test"]["timeout-minutes"]) is int
    assert shards["timeout-minutes"] + data["jobs"]["test"]["timeout-minutes"] <= 100
    assert data["jobs"]["test"]["name"] == "test"
    assert data["jobs"]["test"]["needs"] == ["pytest_shards"]


@pytest.mark.parametrize(
    ("preimage", "mutation"),
    [
        # Finite wall-clock budgets are mandatory; no silent removal or
        # enormous timeout may bypass the queue's 100-minute check window.
        ("    timeout-minutes: 60", ""),
        ("    timeout-minutes: 60", "    timeout-minutes: null"),
        ("    timeout-minutes: 60", "    timeout-minutes: true"),
        ("    timeout-minutes: 60", '    timeout-minutes: "60"'),
        ("    timeout-minutes: 60", "    timeout-minutes: 0"),
        ("    timeout-minutes: 60", "    timeout-minutes: -5"),
        ("    timeout-minutes: 60", "    timeout-minutes: 44"),
        ("    timeout-minutes: 60", "    timeout-minutes: 61"),
        ("    timeout-minutes: 60", "    timeout-minutes: 93"),
        ("    timeout-minutes: 60", "    timeout-minutes: 120"),
        ("    timeout-minutes: 8", ""),
        ("    timeout-minutes: 8", "    timeout-minutes: null"),
        ("    timeout-minutes: 8", "    timeout-minutes: 0"),
        ("    timeout-minutes: 8", "    timeout-minutes: 90"),
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
