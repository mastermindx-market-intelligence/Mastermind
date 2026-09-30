"""Decision tests for Z0's path-policy evidence gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from experiments.code_discovery import z0_runner as runner
from experiments.code_discovery.discovery_contract import RepositoryIndexStatus
from experiments.code_discovery.z0_benchmark import (
    PathPolicyError,
    PathPolicyMeasurement,
    select_path_policy,
)


_HOST_IDENTITIES = {
    "request_digest": "1" * 64,
    "toolchain_lock_sha256": "2" * 64,
    "bundle_sha256": "3" * 64,
    "bundle_manifest_sha256": "4" * 64,
}
_B0_RESULT_FIELDS = {
    "schema_version",
    "decision",
    "generated_at",
    *_HOST_IDENTITIES,
    "manifest_digest",
    "path_policy_digest",
    "tool_schema_digest",
    "zoekt_source_commit",
    "binary_digests",
    "repository_statuses",
    "resource_observations",
}


def _status() -> RepositoryIndexStatus:
    observed = datetime(2026, 8, 30, 12, tzinfo=UTC)
    return RepositoryIndexStatus(
        repository_id="mastermind",
        ref_label="master",
        indexed_commit_sha="a" * 40,
        source_tree_digest="b" * 64,
        shard_namespace="z0-mastermind",
        health="healthy",
        coverage="covered",
        generated_at=observed,
        observed_at=observed,
        freshness_seconds=1.0,
    )


class _ClosedFakeProcesses:
    """Replace only the external child processes while exercising the real consumer."""

    def __init__(self, **_kwargs: object) -> None:
        self.closed = False

    def build_indexes(self, _manifest: object) -> tuple[RepositoryIndexStatus, ...]:
        return (_status(),)

    def start_search(self) -> None:
        return None

    def assert_search_alive(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _consumer_argv(
    tmp_path: Path,
    identities: dict[str, str] | None = None,
) -> list[str]:
    path_policy = tmp_path / "z0-path-policy.json"
    path_policy.write_text("{}\n", encoding="utf-8")
    values = identities or _HOST_IDENTITIES
    argv = [
        "--manifest",
        str(tmp_path / "manifest.json"),
        "--path-policy",
        str(path_policy),
        "--indexer",
        str(tmp_path / "bundle/bin/zoekt-git-index"),
        "--indexer-sha256",
        "5" * 64,
        "--webserver",
        str(tmp_path / "bundle/bin/zoekt-webserver"),
        "--webserver-sha256",
        "6" * 64,
        "--shard-root",
        str(tmp_path / "shards"),
        "--log-root",
        str(tmp_path / "logs"),
        "--result",
        str(tmp_path / "output/z0-result.json"),
        "--report",
        str(tmp_path / "output/z0-report.md"),
    ]
    for field, value in values.items():
        argv.extend((f"--{field.replace('_', '-')}", value))
    return argv


def _run_real_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identities: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    monkeypatch.setattr(runner, "load_index_manifest", lambda _path: object())
    monkeypatch.setattr(runner, "material_source_manifest_digest", lambda _manifest: "7" * 64)
    monkeypatch.setattr(runner, "discovery_tool_schema_digest", lambda: "8" * 64)
    monkeypatch.setattr(runner, "ZoektProcessSet", _ClosedFakeProcesses)

    assert runner.main(_consumer_argv(tmp_path, identities)) == 0
    return tmp_path / "output/z0-result.json", tmp_path / "output/z0-report.md"


def _assert_b0_compatible(
    result_path: Path,
    report_path: Path,
    expected_identities: dict[str, str],
) -> None:
    schema = json.loads(
        Path("research/code_intelligence_fabric/z0-result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    assert set(payload) == _B0_RESULT_FIELDS
    for field, expected in expected_identities.items():
        assert payload[field] == expected, field

    assert report_path.read_bytes() == (
        "# Z0 Global Discovery Falsifier Result\n\n"
        f"Decision: {payload['decision']}\n\n"
        f"Generated at: {payload['generated_at']}\n\n"
        f"Request digest: {expected_identities['request_digest']}\n\n"
        f"Toolchain lock SHA-256: {expected_identities['toolchain_lock_sha256']}\n\n"
        f"Bundle SHA-256: {expected_identities['bundle_sha256']}\n\n"
        f"Bundle manifest SHA-256: {expected_identities['bundle_manifest_sha256']}\n\n"
        "## Repository/ref status\n\n"
        f"- mastermind/master: health=healthy; coverage=covered; indexed_sha={'a' * 40}\n\n"
        "This is a disposable production-inert experiment result. It does not "
        "provision a persistent service, capability profile, credential, MCP "
        "endpoint, CI3 grant, or deployment.\n"
    ).encode("utf-8")


def _measurement(policy_id: str, case_id: str, **overrides: object) -> PathPolicyMeasurement:
    values: dict[str, object] = {
        "policy_id": policy_id,
        "case_id": case_id,
        "relevant_path_recall": 1.0,
        "false_positive_count": 10,
        "indexed_file_count": 100,
        "indexed_bytes": 1_000,
        "shard_bytes": 500,
        "build_seconds": 3.0,
        "refresh_seconds": 1.0,
        "query_latency_ms": 10.0,
    }
    values.update(overrides)
    return PathPolicyMeasurement(**values)


def _complete(**overrides: object) -> tuple[PathPolicyMeasurement, ...]:
    return tuple(
        _measurement(policy, case, **overrides)
        for policy in ("P0", "P1", "P2")
        for case in ("E1", "X3", "R3", "A1")
    )


def test_selects_narrow_full_recall_policy_from_complete_case_evidence() -> None:
    """P1/P2 win only with answer-key coverage plus lower measured burden."""

    measurements = list(_complete())
    for index, measurement in enumerate(measurements):
        if measurement.policy_id == "P1":
            measurements[index] = _measurement(
                "P1",
                measurement.case_id,
                false_positive_count=2,
                indexed_bytes=600,
                shard_bytes=300,
                build_seconds=2,
                refresh_seconds=0.8,
                query_latency_ms=8,
            )

    assert select_path_policy(tuple(measurements)) == "P1"


def test_refuses_incomplete_evidence_and_p0_recall_only_selection() -> None:
    """No policy can graduate without all cases or by broad recall alone."""

    with pytest.raises(PathPolicyError, match="cover"):
        select_path_policy(_complete()[:-1])

    measurements = list(_complete())
    for index, measurement in enumerate(measurements):
        if measurement.policy_id == "P0":
            measurements[index] = _measurement(
                "P0",
                measurement.case_id,
                false_positive_count=99,
                indexed_bytes=9_000,
                shard_bytes=9_000,
                build_seconds=99,
                refresh_seconds=99,
                query_latency_ms=99,
            )
    assert select_path_policy(tuple(measurements)) == "P1"


def test_real_consumer_round_trips_the_exact_b0_identity_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping any identity from the real emitter breaks B0's zero-exit contract."""

    result_path, report_path = _run_real_consumer(tmp_path, monkeypatch)

    _assert_b0_compatible(result_path, report_path, _HOST_IDENTITIES)


@pytest.mark.parametrize("field", tuple(_HOST_IDENTITIES))
def test_real_consumer_requires_each_host_identity_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    """Omitting one fixed host identity must fail before any consumer process starts."""

    monkeypatch.setattr(runner, "ZoektProcessSet", _ClosedFakeProcesses)
    argv = _consumer_argv(tmp_path)
    flag = f"--{field.replace('_', '-')}"
    position = argv.index(flag)
    del argv[position : position + 2]

    with pytest.raises(SystemExit) as error:
        runner.main(argv)

    assert error.value.code == 2


@pytest.mark.parametrize("field", tuple(_HOST_IDENTITIES))
def test_real_consumer_rejects_malformed_host_identity_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
) -> None:
    """An ambient or malformed identity cannot become result authority."""

    identities = dict(_HOST_IDENTITIES)
    identities[field] = "A" * 64

    with pytest.raises(SystemExit) as error:
        _run_real_consumer(tmp_path, monkeypatch, identities)

    assert error.value.code == 2
    captured = capsys.readouterr()
    assert f"--{field.replace('_', '-')}" in captured.err
    assert "must be a lowercase SHA-256 digest" in captured.err


@pytest.mark.parametrize("field", tuple(_HOST_IDENTITIES))
def test_b0_contract_rejects_real_preserved_artifacts_from_wrong_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    """A real artifact pair cannot be relabelled under another host identity."""

    result_path, report_path = _run_real_consumer(tmp_path, monkeypatch)
    expected = dict(_HOST_IDENTITIES)
    expected[field] = "9" * 64

    with pytest.raises(AssertionError, match=field):
        _assert_b0_compatible(result_path, report_path, expected)


@pytest.mark.parametrize("field", tuple(_HOST_IDENTITIES))
def test_result_schema_rejects_real_artifact_missing_host_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    """The strict schema must reject a real result with one identity removed."""

    result_path, _report_path = _run_real_consumer(tmp_path, monkeypatch)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    del payload[field]
    schema = json.loads(
        Path("research/code_intelligence_fabric/z0-result.schema.json").read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(payload)
