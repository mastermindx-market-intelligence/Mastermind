from __future__ import annotations

import dataclasses
import errno
import hashlib
import http.server
import json
import os
import platform
import shutil
import signal
import socket
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import pytest

from experiments.codeintel_supply import hosted_runner as runner

HEX_A = "a" * 40
HEX_B = "b" * 40
HEX_C = "c" * 40
HEX_D = "d" * 40
SHA_A = "a" * 64
SHA_B = "b" * 64


def _github_hosted_environment(tmp_path: Path) -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "RUNNER_TEMP": os.fspath(tmp_path),
        "ImageOS": "ubuntu24",
    }


def _require_exact_github_hosted_userns_runner(
    environment: Mapping[str, str],
) -> None:
    if runner.is_exact_github_hosted_userns_runner(environment):
        return
    if environment.get("GITHUB_ACTIONS") == "true":
        pytest.fail(
            "GitHub Actions runner identity drifted from the exact hosted "
            "Ubuntu 24.04 x64 contract"
        )
    pytest.skip(
        "live user-namespace boundary requires the exact GitHub-hosted "
        "Ubuntu 24.04 x64 runner"
    )


@pytest.fixture
def github_hosted_userns_policy() -> Iterator[runner.HostUsernsPolicyEvidence]:
    _require_exact_github_hosted_userns_runner(os.environ)
    with runner.github_hosted_userns_policy_window() as evidence:
        yield evidence


def _restored_policy_evidence(
    *, original_value: int = 1
) -> runner.HostUsernsPolicyEvidence:
    return runner.HostUsernsPolicyEvidence(
        scope=runner.HOST_USERNS_SCOPE,
        control_key=runner.HOST_USERNS_SYSCTL_KEY,
        control_path=os.fspath(runner.HOST_USERNS_SYSCTL_PATH),
        original_value=original_value,
        active_value=runner.HOST_USERNS_ACTIVE_VALUE,
        mutation_performed=original_value != runner.HOST_USERNS_ACTIVE_VALUE,
        active_readback_verified=True,
        restored_value=original_value,
        restore_readback_verified=True,
    )


def _restored_policy_payload(*, original_value: int = 1) -> dict[str, object]:
    return {
        "scope": runner.HOST_USERNS_SCOPE,
        "control_key": runner.HOST_USERNS_SYSCTL_KEY,
        "control_path": os.fspath(runner.HOST_USERNS_SYSCTL_PATH),
        "original_value": original_value,
        "active_value": runner.HOST_USERNS_ACTIVE_VALUE,
        "mutation_performed": original_value != runner.HOST_USERNS_ACTIVE_VALUE,
        "active_readback_verified": True,
        "restored_value": original_value,
        "restore_readback_verified": True,
        "abrupt_termination_cleanup": "github_hosted_vm_decommission",
    }


def test_live_fixture_fails_closed_on_github_actions_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _github_hosted_environment(tmp_path)
    environment["RUNNER_ARCH"] = "ARM64"
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(
        pytest.fail.Exception,
        match="GitHub Actions runner identity drifted",
    ):
        _require_exact_github_hosted_userns_runner(environment)


def _request(**changes: str) -> runner.ExperimentRequest:
    values = {
        "operation_key": runner.Z0_OPERATION_KEY,
        "consumer_sha": HEX_A,
        "consumer_tree_sha": HEX_B,
        "forge_sha": HEX_C,
        "forge_tree_sha": HEX_D,
        "lock_sha256": SHA_A,
        "workflow_sha256": SHA_B,
    }
    values.update(changes)
    return runner.ExperimentRequest.from_values(**values)


def _payload_tree(root: Path) -> None:
    (root / "bin").mkdir(parents=True)
    (root / "meta").mkdir()
    (root / "bin/zoekt-git-index").write_bytes(b"indexer\n")
    (root / "bin/zoekt-webserver").write_bytes(b"server\n")
    os.chmod(root / "bin/zoekt-git-index", 0o755)
    os.chmod(root / "bin/zoekt-webserver", 0o755)
    (root / "meta/sbom.json").write_text('{"modules":[]}\n', encoding="utf-8")
    (root / "meta/NOTICE.txt").write_text("Apache-2.0 notices\n", encoding="utf-8")
    (root / "meta/provenance.json").write_text(
        '{"schema_version":"mastermind.codeintel_phase_p_provenance.v1"}\n',
        encoding="utf-8",
    )
    (root / "meta/toolchain-lock.json").write_text("{}\n", encoding="utf-8")


def test_request_identity_is_closed_canonical_and_content_addressed() -> None:
    request = _request()
    assert request.mode == "Z0"
    assert request.repository == "mastermindx-market-intelligence/Mastermind"
    assert request.operation_key == runner.Z0_OPERATION_KEY
    assert request.digest == hashlib.sha256(request.canonical_bytes).hexdigest()
    assert json.loads(request.canonical_bytes)["consumer_sha"] == HEX_A


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_key", "arbitrary-command"),
        ("consumer_sha", "A" * 40),
        ("consumer_sha", "main"),
        ("consumer_sha", "a" * 39 + ";"),
        ("consumer_tree_sha", "refs/heads/main"),
        ("forge_sha", "0" * 39),
        ("lock_sha256", "v1"),
        ("workflow_sha256", "f" * 63),
    ],
)
def test_request_rejects_moved_refs_shell_payloads_and_wrong_operation(
    field: str, value: str
) -> None:
    with pytest.raises(runner.HostedRunnerError, match="INVALID_REQUEST"):
        _request(**{field: value})


def test_consumer_path_census_accepts_only_the_z0_ceiling() -> None:
    accepted = runner.validate_consumer_paths(
        [
            "experiments/code_discovery/z0_runner.py",
            "tests/code_discovery/test_z0_runner.py",
            "tests/fixtures/code_discovery/manifest.json",
            "research/code_intelligence_fabric/z0-path-policy.json",
            "research/code_intelligence_fabric/z0-result.schema.json",
            "research/code_intelligence_fabric/Z0_GLOBAL_DISCOVERY_FALSIFIER_RESULT.md",
        ]
    )
    assert accepted == tuple(sorted(accepted))

    for hostile in (
        "control_plane/runner.py",
        "experiments/code_discovery/../codeintel_supply/hosted_runner.py",
        "/experiments/code_discovery/z0_runner.py",
        "experiments/code_discovery/link",
        "research/code_intelligence_fabric/C0_SEMANTIC_RESULT.md",
    ):
        with pytest.raises(runner.HostedRunnerError, match="CONSUMER_PATH_VIOLATION"):
            runner.validate_consumer_paths([hostile])


def test_consumer_git_identity_requires_exact_head_tree_and_same_repo(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "consumer"
    repo.mkdir()
    runner.run_checked(["git", "init", "-q", "-b", "codeintel-z0-consumer"], cwd=repo)
    runner.run_checked(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/mastermindx-market-intelligence/Mastermind.git",
        ],
        cwd=repo,
    )
    (repo / "experiments/code_discovery").mkdir(parents=True)
    (repo / "experiments/code_discovery/z0_runner.py").write_text(
        "print('fixed')\n", encoding="utf-8"
    )
    runner.run_checked(["git", "add", "."], cwd=repo)
    runner.run_checked(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repo,
    )
    head = runner.git_stdout(repo, "rev-parse", "HEAD")
    tree = runner.git_stdout(repo, "rev-parse", "HEAD^{tree}")

    identity = runner.verify_consumer_checkout(repo, head, tree)
    assert identity.commit_sha == head
    assert identity.tree_sha == tree

    with pytest.raises(runner.HostedRunnerError, match="CONSUMER_MISMATCH"):
        runner.verify_consumer_checkout(repo, "0" * 40, tree)
    runner.run_checked(["git", "switch", "-q", "-c", "wrong-consumer-role"], cwd=repo)
    with pytest.raises(runner.HostedRunnerError, match="CONSUMER_BRANCH_MISMATCH"):
        runner.verify_consumer_checkout(repo, head, tree)
    runner.run_checked(["git", "switch", "-q", "codeintel-z0-consumer"], cwd=repo)
    runner.run_checked(
        ["git", "remote", "set-url", "origin", "https://github.com/evil/fork.git"],
        cwd=repo,
    )
    with pytest.raises(runner.HostedRunnerError, match="CONSUMER_REPOSITORY_MISMATCH"):
        runner.verify_consumer_checkout(repo, head, tree)


def test_consumer_ignores_unselected_legacy_link_but_rejects_selected_link(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "consumer"
    repo.mkdir()
    runner.run_checked(["git", "init", "-q", "-b", "codeintel-z0-consumer"], cwd=repo)
    runner.run_checked(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/mastermindx-market-intelligence/Mastermind.git",
        ],
        cwd=repo,
    )
    (repo / "experiments/code_discovery").mkdir(parents=True)
    (repo / "experiments/code_discovery/z0_runner.py").write_text(
        "print('fixed')\n", encoding="utf-8"
    )
    (repo / "vendor").mkdir()
    (repo / "vendor/macro").symlink_to("../external-macro")
    runner.run_checked(["git", "add", "."], cwd=repo)
    runner.run_checked(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repo,
    )
    head = runner.git_stdout(repo, "rev-parse", "HEAD")
    tree = runner.git_stdout(repo, "rev-parse", "HEAD^{tree}")

    assert runner.verify_consumer_checkout(repo, head, tree).commit_sha == head
    assert runner.selected_source_digest(
        repo, includes=("experiments/code_discovery/*",), excludes=()
    )

    (repo / "experiments/code_discovery/z0_runner.py").unlink()
    (repo / "experiments/code_discovery/z0_runner.py").symlink_to("/etc/passwd")
    with pytest.raises(runner.HostedRunnerError, match="CONSUMER_FILE_UNSAFE"):
        runner.selected_source_digest(
            repo, includes=("experiments/code_discovery/*",), excludes=()
        )


def test_consumer_effective_diff_rejects_changed_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "consumer"
    repo.mkdir()
    runner.run_checked(["git", "init", "-q", "-b", "codeintel-z0-consumer"], cwd=repo)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    runner.run_checked(["git", "add", "."], cwd=repo)
    runner.run_checked(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=repo,
    )
    forge_sha = runner.git_stdout(repo, "rev-parse", "HEAD")
    (repo / "experiments/code_discovery").mkdir(parents=True)
    (repo / "experiments/code_discovery/z0_runner.py").symlink_to("/etc/passwd")
    runner.run_checked(["git", "add", "."], cwd=repo)
    runner.run_checked(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "hostile consumer",
        ],
        cwd=repo,
    )
    consumer_sha = runner.git_stdout(repo, "rev-parse", "HEAD")

    with pytest.raises(runner.HostedRunnerError, match="CONSUMER_FILE_UNSAFE"):
        runner.consumer_effective_paths(
            repo, consumer_sha=consumer_sha, forge_sha=forge_sha
        )


def test_consumer_effective_diff_rejects_cross_boundary_rename(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "consumer"
    repo.mkdir()
    runner.run_checked(["git", "init", "-q", "-b", "codeintel-z0-consumer"], cwd=repo)
    (repo / "control_plane").mkdir()
    (repo / "control_plane/authority.py").write_text("outside\n", encoding="utf-8")
    runner.run_checked(["git", "add", "."], cwd=repo)
    runner.run_checked(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=repo,
    )
    forge_sha = runner.git_stdout(repo, "rev-parse", "HEAD")
    (repo / "experiments/code_discovery").mkdir(parents=True)
    runner.run_checked(
        [
            "git",
            "mv",
            "control_plane/authority.py",
            "experiments/code_discovery/z0_runner.py",
        ],
        cwd=repo,
    )
    runner.run_checked(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "hostile cross-boundary rename",
        ],
        cwd=repo,
    )
    consumer_sha = runner.git_stdout(repo, "rev-parse", "HEAD")

    with pytest.raises(runner.HostedRunnerError, match="CONSUMER_PATH_VIOLATION"):
        runner.consumer_effective_paths(
            repo, consumer_sha=consumer_sha, forge_sha=forge_sha
        )


def test_content_addressed_bundle_is_byte_identical_across_mtime_and_order(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "one"
    second_root = tmp_path / "two"
    _payload_tree(first_root)
    _payload_tree(second_root)
    for index, path in enumerate(reversed(tuple(second_root.rglob("*"))), start=1):
        os.utime(path, (1_800_000_000 + index, 1_800_000_000 + index))

    context = {
        "request_digest": _request().digest,
        "lock_sha256": SHA_A,
        "build_recipe_sha256": "9" * 64,
    }
    first = runner.create_content_addressed_bundle(
        first_root, tmp_path / "out-one", context=context
    )
    second = runner.create_content_addressed_bundle(
        second_root, tmp_path / "out-two", context=context
    )

    assert first.sha256 == second.sha256
    assert first.path.read_bytes() == second.path.read_bytes()
    assert first.name == f"codeintel-z0-{first.sha256}.tar.gz"
    verified = runner.verify_bundle(first.path, expected_sha256=first.sha256)
    assert verified.manifest_sha256 == first.manifest_sha256
    assert {row["path"] for row in verified.manifest["files"]} >= {
        "bin/zoekt-git-index",
        "bin/zoekt-webserver",
        "meta/sbom.json",
        "meta/NOTICE.txt",
        "meta/provenance.json",
        "meta/toolchain-lock.json",
    }


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_bundle_builder_rejects_symlink_and_special_payload(
    tmp_path: Path, kind: str
) -> None:
    root = tmp_path / "payload"
    _payload_tree(root)
    hostile = root / "meta/hostile"
    if kind == "symlink":
        hostile.symlink_to("/etc/passwd")
    else:
        os.mkfifo(hostile)
    with pytest.raises(runner.HostedRunnerError, match="BUNDLE_PAYLOAD_UNSAFE"):
        runner.create_content_addressed_bundle(root, tmp_path / "out", context={})


def test_bundle_substitution_and_post_launch_drift_are_detected(tmp_path: Path) -> None:
    root = tmp_path / "payload"
    _payload_tree(root)
    bundle = runner.create_content_addressed_bundle(root, tmp_path / "out", context={})
    body = bytearray(bundle.path.read_bytes())
    body[-1] ^= 1
    bundle.path.write_bytes(body)
    with pytest.raises(runner.HostedRunnerError, match="BUNDLE_DIGEST_MISMATCH"):
        runner.verify_bundle(bundle.path, expected_sha256=bundle.sha256)


def test_replay_returns_prior_semantic_receipt_and_changed_request_conflicts(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "semantic-receipt.json"
    request = _request()
    written = runner.write_semantic_receipt(
        receipt_path,
        request=request,
        status="COMPLETED",
        effect="APPLIED",
        evidence={"bundle_sha256": "8" * 64},
    )

    resolution = runner.reconcile_receipt(receipt_path, request)
    assert resolution.disposition is runner.ReplayDisposition.RETURN_PRIOR
    assert resolution.receipt == written

    with pytest.raises(runner.HostedRunnerError, match="REQUEST_CONFLICT"):
        runner.reconcile_receipt(receipt_path, _request(consumer_sha="e" * 40))


def test_effect_unknown_is_durable_and_never_retried(tmp_path: Path) -> None:
    receipt_path = tmp_path / "semantic-receipt.json"
    request = _request()
    runner.write_semantic_receipt(
        receipt_path,
        request=request,
        status="RECONCILIATION_REQUIRED",
        effect="EFFECT_UNKNOWN",
        evidence={"phase": "consumer_launched_response_lost"},
    )

    with pytest.raises(runner.HostedRunnerError, match="EFFECT_UNKNOWN_REPLAY_BLOCKED"):
        runner.reconcile_receipt(receipt_path, request)


def test_github_replay_census_reads_every_page_and_rejects_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        1: {"total_count": 2, "workflow_runs": [{"id": 101}]},
        2: {"total_count": 2, "workflow_runs": [{"id": 102}]},
    }

    network_environment = {
        "HTTPS_PROXY": "http://127.0.0.1:12345",
        "HTTP_PROXY": "http://127.0.0.1:12345",
    }

    def stable(
        endpoint: str, *, network_environment: dict[str, str]
    ) -> dict[str, object]:
        assert network_environment["HTTPS_PROXY"] == "http://127.0.0.1:12345"
        page = int(endpoint.rsplit("page=", 1)[1])
        return pages[page]

    monkeypatch.setattr(runner, "_gh_json", stable)
    rows = runner._gh_paginated_rows(  # noqa: SLF001 - replay safety boundary
        "repos/example/actions/runs?event=workflow_dispatch",
        field="workflow_runs",
        max_rows=10,
        network_environment=network_environment,
    )
    assert [row["id"] for row in rows] == [101, 102]

    def moved(
        endpoint: str, *, network_environment: dict[str, str]
    ) -> dict[str, object]:
        assert network_environment["HTTPS_PROXY"] == "http://127.0.0.1:12345"
        page = int(endpoint.rsplit("page=", 1)[1])
        if page == 1:
            return {"total_count": 2, "workflow_runs": [{"id": 101}]}
        return {"total_count": 3, "workflow_runs": [{"id": 102}]}

    monkeypatch.setattr(runner, "_gh_json", moved)
    with pytest.raises(runner.HostedRunnerError, match="EFFECT_UNKNOWN_REPLAY_BLOCKED"):
        runner._gh_paginated_rows(  # noqa: SLF001 - replay safety boundary
            "repos/example/actions/runs?event=workflow_dispatch",
            field="workflow_runs",
            max_rows=10,
            network_environment=network_environment,
        )


def test_prior_refusal_returns_identical_receipt_and_preserves_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    source = tmp_path / "source-receipt.json"
    runner.write_semantic_receipt(
        source,
        request=request,
        status="REFUSED",
        effect="NOT_APPLIED",
        evidence={"failure": {"code": "NETWORK_SEAL_UNAVAILABLE"}},
    )
    receipt_bytes = source.read_bytes()

    def rows(
        endpoint: str,
        *,
        field: str,
        max_rows: int,
        network_environment: dict[str, str],
    ) -> list[dict[str, object]]:
        del max_rows
        assert network_environment["HTTPS_PROXY"].startswith("http://127.0.0.1:")
        if field == "workflow_runs":
            return [
                {
                    "id": 101,
                    "status": "completed",
                    "display_title": runner.workflow_run_name(request),
                }
            ]
        assert field == "artifacts"
        assert endpoint.endswith("/actions/runs/101/artifacts")
        return [
            {
                "id": 202,
                "name": runner.operation_artifact_name(),
                "expired": False,
                "size_in_bytes": len(receipt_bytes) + 256,
            }
        ]

    def download(
        artifact_id: int,
        destination: Path,
        *,
        network_environment: dict[str, str],
    ) -> None:
        assert artifact_id == 202
        assert network_environment["HTTPS_PROXY"].startswith("http://127.0.0.1:")
        with runner.zipfile.ZipFile(
            destination, mode="w", compression=runner.zipfile.ZIP_STORED
        ) as archive:
            archive.writestr("semantic-receipt.json", receipt_bytes)

    monkeypatch.setattr(runner, "_gh_paginated_rows", rows)
    monkeypatch.setattr(runner, "_gh_download_artifact", download)
    destination = tmp_path / "prior/semantic-receipt.json"
    github_output = tmp_path / "github-output"

    resolution = runner.reconcile_prior_runs(
        request,
        current_run_id=999,
        destination=destination,
        github_output=github_output,
    )

    assert resolution.disposition is runner.ReplayDisposition.RETURN_PRIOR
    assert destination.read_bytes() == receipt_bytes
    assert github_output.read_text(encoding="utf-8").splitlines() == [
        "disposition=RETURN_PRIOR",
        "prior_returncode=1",
    ]


def test_phase_p_failure_records_refusal_before_any_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()

    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        raise runner.HostedRunnerError("ARCHIVE_DIGEST_MISMATCH", "fixed archive")

    monkeypatch.setattr(runner, "prepare_phase_p", fail)
    receipt_path = tmp_path / "receipt/semantic-receipt.json"
    with pytest.raises(runner.HostedRunnerError, match="ARCHIVE_DIGEST_MISMATCH"):
        runner.prepare_phase_p_or_record_refusal(
            tmp_path / "forge",
            request,
            scratch_root=tmp_path / "scratch",
            output_directory=tmp_path / "output",
            github_output=tmp_path / "github-output",
            receipt_path=receipt_path,
        )

    receipt = runner.load_semantic_receipt(receipt_path)
    assert receipt["status"] == "REFUSED"
    assert receipt["effect"] == "NOT_APPLIED"
    assert receipt["evidence"]["failure"] == {
        "code": "ARCHIVE_DIGEST_MISMATCH",
        "detail": "fixed archive",
    }
    assert receipt["evidence"]["consumer_launched"] is False


def test_phase_p_io_failure_is_typed_and_receipted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()

    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        raise OSError("private local detail")

    monkeypatch.setattr(runner, "prepare_phase_p", fail)
    receipt_path = tmp_path / "receipt/semantic-receipt.json"
    with pytest.raises(runner.HostedRunnerError, match="PHASE_P_IO_FAILED"):
        runner.prepare_phase_p_or_record_refusal(
            tmp_path / "forge",
            request,
            scratch_root=tmp_path / "scratch",
            output_directory=tmp_path / "output",
            github_output=tmp_path / "github-output",
            receipt_path=receipt_path,
        )

    receipt = runner.load_semantic_receipt(receipt_path)
    assert receipt["status"] == "REFUSED"
    assert receipt["evidence"]["failure"] == {
        "code": "PHASE_P_IO_FAILED",
        "detail": "Phase P filesystem operation failed",
    }


def test_network_namespace_boundary_always_writes_typed_receipt(tmp_path: Path) -> None:
    request = _request()
    refused_path = tmp_path / "refused/semantic-receipt.json"
    refused = runner.write_network_seal_boundary_receipt(
        request,
        refused_path,
        effect_unknown=False,
    )
    assert refused["status"] == "REFUSED"
    assert refused["effect"] == "NOT_APPLIED"
    assert refused["evidence"]["failure"]["code"] == "NETWORK_SEAL_UNAVAILABLE"
    assert refused["evidence"]["consumer_launched"] is False
    assert (
        runner.reconcile_receipt(refused_path, request).disposition
        is runner.ReplayDisposition.RETURN_PRIOR
    )

    unknown_path = tmp_path / "unknown/semantic-receipt.json"
    unknown = runner.write_network_seal_boundary_receipt(
        request,
        unknown_path,
        effect_unknown=True,
    )
    assert unknown["status"] == "RECONCILIATION_REQUIRED"
    assert unknown["effect"] == "EFFECT_UNKNOWN"
    assert unknown["evidence"]["consumer_launch_state"] == "UNKNOWN"
    assert "consumer_launched" not in unknown["evidence"]
    with pytest.raises(runner.HostedRunnerError, match="EFFECT_UNKNOWN_REPLAY_BLOCKED"):
        runner.reconcile_receipt(unknown_path, request)


@pytest.mark.parametrize(
    ("status", "effect"),
    [
        ("COMPLETED", "NOT_APPLIED"),
        ("COMPLETED", "EFFECT_UNKNOWN"),
        ("REFUSED", "APPLIED"),
        ("REFUSED", "EFFECT_UNKNOWN"),
        ("RECONCILIATION_REQUIRED", "APPLIED"),
        ("RECONCILIATION_REQUIRED", "NOT_APPLIED"),
    ],
)
def test_receipt_rejects_every_ambiguous_status_effect_pair(
    tmp_path: Path, status: str, effect: str
) -> None:
    with pytest.raises(runner.HostedRunnerError, match="RECEIPT_INVALID"):
        runner.write_semantic_receipt(
            tmp_path / "semantic-receipt.json",
            request=_request(),
            status=status,
            effect=effect,
            evidence={},
        )


def test_receipt_digest_and_schema_reject_tampering(tmp_path: Path) -> None:
    receipt_path = tmp_path / "semantic-receipt.json"
    runner.write_semantic_receipt(
        receipt_path,
        request=_request(),
        status="COMPLETED",
        effect="APPLIED",
        evidence={"result_sha256": "7" * 64},
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["effect"] = "NOT_APPLIED"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(runner.HostedRunnerError, match="RECEIPT_DIGEST_MISMATCH"):
        runner.reconcile_receipt(receipt_path, _request())


def test_candidate_environment_is_minimal_and_contains_no_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_do_not_inherit")
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "runtime-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "cloud-secret")
    env = runner.sanitized_consumer_environment(tmp_path)

    assert set(env) == {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "TMPDIR",
        "TZ",
    }
    assert "GITHUB_TOKEN" not in env
    assert "ACTIONS_RUNTIME_TOKEN" not in env
    assert "ghp_do_not_inherit" not in json.dumps(env)
    assert env["PATH"] == "/usr/bin:/bin"


@pytest.mark.parametrize(
    "payload",
    [
        {"authorization": "Bearer abc"},
        {"token": "ghp_abcdefghijklmnopqrstuvwxyz1234567890"},
        {"stderr": "Authorization: Basic Zm9vOmJhcg=="},
        {"data": "-----BEGIN PRIVATE KEY-----"},
        {"env": "${{ secrets.ADMIN_TOKEN }}"},
        {"path": "/Users/private/worktree"},
        {"path": "/home/runner/work/private"},
    ],
)
def test_receipt_and_bundle_metadata_reject_secrets_and_private_paths(
    payload: dict[str, str],
) -> None:
    with pytest.raises(runner.HostedRunnerError, match="SECRET_BEARING_OUTPUT"):
        runner.assert_secret_free(payload)


def test_fixed_consumer_argv_has_no_caller_controlled_module_or_suffix(
    tmp_path: Path,
) -> None:
    argv = runner.fixed_consumer_argv(
        python_executable=Path("/usr/bin/python3"),
        consumer_root=tmp_path / "consumer",
        manifest=tmp_path / "manifest.json",
        path_policy=tmp_path / "z0-path-policy.json",
        indexer=tmp_path / "bundle/bin/zoekt-git-index",
        indexer_sha256="1" * 64,
        webserver=tmp_path / "bundle/bin/zoekt-webserver",
        webserver_sha256="2" * 64,
        shard_root=tmp_path / "shards",
        log_root=tmp_path / "logs",
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
    )
    joined = "\0".join(argv)
    assert "experiments.code_discovery.z0_runner" in joined
    assert "--manifest" in argv
    assert "--path-policy" in argv
    assert "shell=True" not in joined
    assert not any(
        "serena" in value.lower() or "pyright" in value.lower() for value in argv
    )


def test_repeat_build_uses_only_supplied_go_and_fresh_explicit_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned_go = tmp_path / "pinned/go/bin/go"
    pinned_go.parent.mkdir(parents=True)
    pinned_go.write_bytes(b"pinned-go")
    os.chmod(pinned_go, 0o755)
    ambient = tmp_path / "ambient"
    ambient.mkdir()
    (ambient / "go").write_bytes(b"hostile-ambient-go")
    os.chmod(ambient / "go", 0o755)
    monkeypatch.setenv("PATH", os.fspath(ambient))
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run_checked(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        network_environment: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, network_environment, timeout
        captured_env = dict(env or {})
        calls.append((list(argv), captured_env))
        if "build" in argv:
            target = Path(argv[argv.index("-o") + 1])
            target.write_bytes(f"binary:{argv[-1]}".encode("ascii"))
            os.chmod(target, 0o755)
        stdout = (
            '{"Path":"github.com/sourcegraph/zoekt","Main":true}\n'
            if "list" in argv
            else ""
        )
        return runner.subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(runner, "_run_phase_p_checked", fake_run_checked)
    source = tmp_path / "source"
    source.mkdir()
    payload_bin = tmp_path / "payload/bin"
    payload_bin.mkdir(parents=True)

    result = runner._repeat_build_zoekt(  # noqa: SLF001 - exact hostile boundary
        source,
        go_binary=pinned_go,
        scratch=tmp_path / "scratch",
        payload_bin=payload_bin,
        network_environment=runner._phase_p_client_environment(  # noqa: SLF001
            "http://127.0.0.1:12345", tmp_path / "network-home"
        ),
    )

    assert calls
    assert {call[0][0] for call in calls} == {os.fspath(pinned_go.resolve())}
    assert all(call[1]["GOTOOLCHAIN"] == "local" for call in calls)
    assert all(call[1]["GOENV"] == "off" for call in calls)
    assert all(call[1]["GOVCS"] == "*:off" for call in calls)
    assert all(call[1]["HTTPS_PROXY"] == "http://127.0.0.1:12345" for call in calls)
    assert all(call[1]["NO_PROXY"] == "" for call in calls)
    assert all(
        call[1]["PATH"].startswith(f"{pinned_go.parent.resolve()}:") for call in calls
    )
    assert len({call[1]["GOCACHE"] for call in calls}) >= 5
    assert result["binaries"]["zoekt-git-index"]["byte_identical"] is True
    assert (payload_bin / "zoekt-webserver").read_bytes().startswith(b"binary:")


def test_zoekt_checkout_ignores_ambient_git_and_fetches_only_exact_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run_checked(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        network_environment: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, network_environment, timeout
        calls.append((list(argv), dict(env or {})))
        return runner.subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "run_checked", fake_run_checked)
    monkeypatch.setattr(runner, "_run_phase_p_checked", fake_run_checked)
    monkeypatch.setenv("PATH", os.fspath(tmp_path / "hostile-bin"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.fspath(tmp_path / "hostile.gitconfig"))
    destination = tmp_path / "zoekt"
    runner._checkout_exact_zoekt(  # noqa: SLF001 - exact hostile boundary
        destination,
        network_environment=runner._phase_p_client_environment(  # noqa: SLF001
            "http://127.0.0.1:12345", tmp_path / "network-home"
        ),
    )

    assert calls
    assert {argv[0] for argv, _env in calls} == {"/usr/bin/git"}
    fetch, fetch_env = next(call for call in calls if "fetch" in call[0])
    checkout, _checkout_env = next(call for call in calls if "checkout" in call[0])
    assert fetch[-1] == runner.locks.ZOEKT_COMMIT
    assert checkout[-1] == runner.locks.ZOEKT_COMMIT
    assert "main" not in fetch
    assert "http.proxy=http://127.0.0.1:12345" in fetch
    assert "http.followRedirects=false" in fetch
    assert "protocol.allow=never" in fetch
    assert "protocol.https.allow=always" in fetch
    assert fetch_env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert fetch_env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert os.fspath(tmp_path / "hostile.gitconfig") not in fetch_env.values()


def test_go_archive_rejects_disallowed_redirect_before_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_checked(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        network_environment: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, env, network_environment, timeout
        calls.append(list(argv))
        return runner.subprocess.CompletedProcess(
            argv,
            0,
            stdout=(
                f"302\n{runner.locks.GO_ARCHIVE_URL}\n"
                "https://evil.invalid/go.tar.gz\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(runner, "_run_phase_p_checked", fake_run_checked)
    with pytest.raises(
        runner.HostedRunnerError, match="ACQUISITION_REDIRECT_FORBIDDEN"
    ):
        runner._download_exact_go_archive(  # noqa: SLF001
            tmp_path / "go.tar.gz",
            network_environment=runner._phase_p_client_environment(  # noqa: SLF001
                "http://127.0.0.1:12345", tmp_path / "network-home"
            ),
        )

    assert len(calls) == 1
    assert "--location" not in calls[0]
    assert calls[0][1:4] == [
        "--disable",
        "--proxy",
        "http://127.0.0.1:12345",
    ]
    assert "https://evil.invalid/go.tar.gz" not in calls[0]


def test_go_archive_follows_only_each_validated_allowlisted_hop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"exact archive fixture"
    destination = tmp_path / "go.tar.gz"
    redirect = "https://dl.google.com/go/go1.26.5.linux-amd64.tar.gz"
    calls: list[list[str]] = []

    def fake_run_checked(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        network_environment: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, env, network_environment, timeout
        calls.append(list(argv))
        url = argv[-1]
        if url == runner.locks.GO_ARCHIVE_URL:
            destination.write_bytes(b"redirect body")
            stdout = f"302\n{url}\n{redirect}\n"
        else:
            assert url == redirect
            destination.write_bytes(body)
            stdout = f"200\n{url}\n\n"
        return runner.subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(runner, "_run_phase_p_checked", fake_run_checked)
    monkeypatch.setattr(runner.locks, "GO_ARCHIVE_SIZE", len(body))
    monkeypatch.setattr(
        runner.locks, "GO_ARCHIVE_SHA256", hashlib.sha256(body).hexdigest()
    )

    assert (
        runner._download_exact_go_archive(  # noqa: SLF001
            destination,
            network_environment=runner._phase_p_client_environment(  # noqa: SLF001
                "http://127.0.0.1:12345", tmp_path / "network-home"
            ),
        )
        == redirect
    )
    assert [argv[-1] for argv in calls] == [runner.locks.GO_ARCHIVE_URL, redirect]
    assert all("--location" not in argv for argv in calls)


def test_phase_p_allowlist_proxy_denies_non_allowlisted_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://hostile.invalid:8080")
    monkeypatch.setenv("NO_PROXY", "github.com")

    with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - network boundary
        tmp_path / "network-home"
    ) as network_environment:
        proxy = urlparse(network_environment["HTTPS_PROXY"])
        assert proxy.hostname == "127.0.0.1"
        assert proxy.port == runner._PHASE_P_PROXY_PORT  # noqa: SLF001
        assert network_environment["HTTP_PROXY"] == network_environment["HTTPS_PROXY"]
        assert network_environment["ALL_PROXY"] == network_environment["HTTPS_PROXY"]
        assert network_environment["NO_PROXY"] == ""
        assert network_environment["no_proxy"] == ""
        assert "hostile.invalid" not in repr(network_environment)

        gate_socket = Path(
            network_environment[runner._PHASE_P_GATE_ENV]
        )  # noqa: SLF001
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5)
        try:
            client.connect(os.fspath(gate_socket))
            client.sendall(
                b"CONNECT evil.invalid:443 HTTP/1.1\r\n"
                b"Host: evil.invalid:443\r\n\r\n"
            )
            response = client.recv(4096)
        finally:
            client.close()

    assert response.startswith(b"HTTP/1.1 403 Forbidden\r\n")
    with pytest.raises(
        runner.HostedRunnerError, match="ACQUISITION_ALLOWLIST_UNAVAILABLE"
    ):
        runner._validated_phase_p_client_environment(  # noqa: SLF001
            {**network_environment, "AMBIENT_PROXY_BYPASS": "1"}
        )


def test_phase_p_refuses_before_acquisition_when_allowlist_proxy_cannot_bind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_bind(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("fixture bind refusal")

    monkeypatch.setattr(runner, "_PhasePProxyServer", fail_bind)
    with pytest.raises(runner.HostedRunnerError) as raised:
        with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - network boundary
            tmp_path / "network-home"
        ):
            raise AssertionError("proxy context must not enter")

    assert raised.value.code == "ACQUISITION_ALLOWLIST_UNAVAILABLE"
    assert "could not bind" in raised.value.detail


def test_phase_p_host_allowlist_uses_exact_names_and_one_pinned_suffix() -> None:
    assert runner._acquisition_host_allowed("api.github.com")  # noqa: SLF001
    assert runner._acquisition_host_allowed(  # noqa: SLF001
        "productionresults.blob.core.windows.net"
    )
    assert not runner._acquisition_host_allowed("blob.core.windows.net")  # noqa: SLF001
    assert not runner._acquisition_host_allowed(  # noqa: SLF001
        "blob.core.windows.net.evil.invalid"
    )
    assert not runner._acquisition_host_allowed("127.0.0.1")  # noqa: SLF001


def test_github_client_receives_only_fixed_config_token_and_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "fixture-token-value")
    monkeypatch.setenv("GH_CONFIG_DIR", os.fspath(tmp_path / "hostile-gh-config"))
    monkeypatch.setenv("HTTPS_PROXY", "http://hostile.invalid:8080")
    captured: dict[str, object] = {}

    def fake_run_checked(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        network_environment: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, network_environment, timeout
        captured["argv"] = list(argv)
        captured["env"] = dict(env or {})
        return runner.subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(runner, "_run_phase_p_checked", fake_run_checked)
    network_environment = runner._phase_p_client_environment(  # noqa: SLF001
        "http://127.0.0.1:12345", tmp_path / "network-home"
    )

    assert (
        runner._gh_json(  # noqa: SLF001 - exact network client boundary
            "repos/golang/go/git/ref/tags/go1.26.5",
            network_environment=network_environment,
        )
        == {}
    )
    assert captured["argv"] == [
        "/usr/bin/gh",
        "api",
        "repos/golang/go/git/ref/tags/go1.26.5",
    ]
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["GH_TOKEN"] == "fixture-token-value"
    assert environment["GH_HOST"] == "github.com"
    assert environment["GH_PROMPT_DISABLED"] == "1"
    assert environment["GH_CONFIG_DIR"] == os.fspath(
        (tmp_path / "network-home/gh").resolve()
    )
    assert environment["HTTPS_PROXY"] == "http://127.0.0.1:12345"
    assert os.fspath(tmp_path / "hostile-gh-config") not in environment.values()
    assert "hostile.invalid" not in repr(environment)


def test_phase_p_clients_use_the_kernel_socket_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_boundary(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        network_environment: dict[str, str],
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, timeout
        captured["argv"] = list(argv)
        captured["env"] = dict(env)
        captured["network_environment"] = dict(network_environment)
        return runner.subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(runner, "_run_phase_p_checked", fake_boundary)
    network_environment = runner._phase_p_client_environment(  # noqa: SLF001
        "http://127.0.0.1:12345", tmp_path / "network-home"
    )

    assert (
        runner._gh_json(  # noqa: SLF001 - exact network client boundary
            "repos/golang/go/git/ref/tags/go1.26.5",
            network_environment=network_environment,
        )
        == {}
    )
    assert captured["argv"] == [
        "/usr/bin/gh",
        "api",
        "repos/golang/go/git/ref/tags/go1.26.5",
    ]
    assert captured["network_environment"] == network_environment
    assert runner._PHASE_P_LANDLOCK_MIN_ABI == 4  # noqa: SLF001
    assert (
        runner._PHASE_P_BOUNDARY_READY == b"CODEINTEL_PHASE_P_BOUNDARY_V1\n"
    )  # noqa: SLF001


def test_userns_policy_window_sets_zero_and_restores_exact_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"value": 1}
    writes: list[int] = []

    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: state["value"])

    def write(value: int, *, restoration: bool) -> None:
        del restoration
        writes.append(value)
        state["value"] = value

    monkeypatch.setattr(runner, "_write_host_userns_policy", write)

    with runner.github_hosted_userns_policy_window(
        _github_hosted_environment(tmp_path)
    ) as evidence:
        assert evidence.original_value == 1
        assert evidence.active_value == 0
        assert state["value"] == 0

    assert state["value"] == 1
    assert writes == [0, 1]
    assert evidence.control_key == runner.HOST_USERNS_SYSCTL_KEY
    assert evidence.control_path == os.fspath(runner.HOST_USERNS_SYSCTL_PATH)
    assert evidence.mutation_performed is True
    assert evidence.active_readback_verified is True
    assert evidence.restored_value == 1
    assert evidence.restore_readback_verified is True


def test_userns_policy_window_original_zero_proves_state_without_sudo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = 0

    def read() -> int:
        nonlocal reads
        reads += 1
        return 0

    def unexpected_write(value: int, *, restoration: bool) -> None:
        pytest.fail(f"unexpected sysctl write: value={value} restoration={restoration}")

    monkeypatch.setattr(runner, "_read_host_userns_policy", read)
    monkeypatch.setattr(runner, "_write_host_userns_policy", unexpected_write)

    with runner.github_hosted_userns_policy_window(
        _github_hosted_environment(tmp_path)
    ) as evidence:
        assert evidence.original_value == 0
        assert evidence.active_value == 0

    assert reads >= 2
    assert evidence.mutation_performed is False
    assert evidence.active_readback_verified is True
    assert evidence.restored_value == 0
    assert evidence.restore_readback_verified is True


@pytest.mark.parametrize(
    "changes",
    [
        {"GITHUB_ACTIONS": "false"},
        {"RUNNER_ENVIRONMENT": "self-hosted"},
        {"RUNNER_OS": "Windows"},
        {"RUNNER_ARCH": "ARM64"},
        {"ImageOS": "ubuntu22"},
        {"RUNNER_TEMP": ""},
    ],
)
def test_userns_policy_window_refuses_unidentified_or_self_hosted_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, str],
) -> None:
    environment = _github_hosted_environment(tmp_path)
    environment.update(changes)
    writes: list[int] = []
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: 1)
    monkeypatch.setattr(
        runner,
        "_write_host_userns_policy",
        lambda value, *, restoration: writes.append(value),
    )

    with pytest.raises(runner.HostedRunnerError) as raised:
        with runner.github_hosted_userns_policy_window(environment):
            pytest.fail("hostile runner must never enter the policy window")

    assert raised.value.code == "HOST_USERNS_POLICY_UNAVAILABLE"
    assert writes == []


@pytest.mark.parametrize("original", [-1, 2, 10, "1", None])
def test_userns_policy_window_rejects_malformed_original_without_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    original: object,
) -> None:
    writes: list[int] = []
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: original)
    monkeypatch.setattr(
        runner,
        "_write_host_userns_policy",
        lambda value, *, restoration: writes.append(value),
    )

    with pytest.raises(runner.HostedRunnerError) as raised:
        with runner.github_hosted_userns_policy_window(
            _github_hosted_environment(tmp_path)
        ):
            pytest.fail("malformed policy must never enter the window")

    assert raised.value.code == "HOST_USERNS_POLICY_UNAVAILABLE"
    assert writes == []


def test_userns_policy_window_refuses_missing_sysctl_without_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: list[int] = []

    def missing() -> int:
        raise runner.HostedRunnerError(
            "HOST_USERNS_POLICY_UNAVAILABLE", "forced missing sysctl"
        )

    monkeypatch.setattr(runner, "_read_host_userns_policy", missing)
    monkeypatch.setattr(
        runner,
        "_write_host_userns_policy",
        lambda value, *, restoration: writes.append(value),
    )
    with pytest.raises(runner.HostedRunnerError) as raised:
        with runner.github_hosted_userns_policy_window(
            _github_hosted_environment(tmp_path)
        ):
            pytest.fail("missing policy must never enter the window")

    assert raised.value.code == "HOST_USERNS_POLICY_UNAVAILABLE"
    assert writes == []


def test_userns_policy_window_restores_after_body_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"value": 1}
    writes: list[int] = []
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: state["value"])

    def write(value: int, *, restoration: bool) -> None:
        del restoration
        writes.append(value)
        state["value"] = value

    monkeypatch.setattr(runner, "_write_host_userns_policy", write)

    with pytest.raises(RuntimeError, match="forced body failure"):
        with runner.github_hosted_userns_policy_window(
            _github_hosted_environment(tmp_path)
        ):
            raise RuntimeError("forced body failure")

    assert state["value"] == 1
    assert writes == [0, 1]


def test_userns_policy_window_activation_write_failure_still_restores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"value": 1}
    writes: list[tuple[int, bool]] = []
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: state["value"])

    def write(value: int, *, restoration: bool) -> None:
        writes.append((value, restoration))
        if not restoration:
            raise runner.HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE", "forced sudo refusal"
            )
        state["value"] = value

    monkeypatch.setattr(runner, "_write_host_userns_policy", write)

    with pytest.raises(runner.HostedRunnerError) as raised:
        with runner.github_hosted_userns_policy_window(
            _github_hosted_environment(tmp_path)
        ):
            pytest.fail("failed activation must not enter the window")

    assert raised.value.code == "HOST_USERNS_POLICY_UNAVAILABLE"
    assert state["value"] == 1
    assert writes == [(0, False), (1, True)]


def test_phase_p_activation_failure_receipt_reports_only_observed_policy_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    receipt = tmp_path / "receipts/semantic-receipt.json"
    environment = _github_hosted_environment(tmp_path)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    state = {"value": 1}
    writes: list[tuple[int, bool]] = []
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: state["value"])

    def write(value: int, *, restoration: bool) -> None:
        writes.append((value, restoration))
        if not restoration:
            raise runner.HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE", "forced sudo refusal"
            )
        state["value"] = value

    monkeypatch.setattr(runner, "_write_host_userns_policy", write)

    with pytest.raises(runner.HostedRunnerError) as raised:
        runner.prepare_phase_p_hosted(
            tmp_path,
            request,
            scratch_root=tmp_path / "scratch",
            output_directory=tmp_path / "output",
            github_output=tmp_path / "github-output",
            receipt_path=receipt,
        )

    assert raised.value.code == "HOST_USERNS_POLICY_UNAVAILABLE"
    assert writes == [(0, False), (1, True)]
    payload = runner.load_semantic_receipt(receipt)
    assert (payload["status"], payload["effect"]) == ("REFUSED", "NOT_APPLIED")
    assert payload["evidence"]["host_userns_policy"] == {
        "scope": runner.HOST_USERNS_SCOPE,
        "control_key": runner.HOST_USERNS_SYSCTL_KEY,
        "control_path": os.fspath(runner.HOST_USERNS_SYSCTL_PATH),
        "original_value": 1,
        "active_readback_verified": False,
        "restored_value": 1,
        "restore_readback_verified": True,
        "abrupt_termination_cleanup": "github_hosted_vm_decommission",
    }


def test_userns_policy_window_rejects_failed_active_readback_and_restores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = iter([1, 1, 1])
    writes: list[tuple[int, bool]] = []
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: next(reads))
    monkeypatch.setattr(
        runner,
        "_write_host_userns_policy",
        lambda value, *, restoration: writes.append((value, restoration)),
    )

    with pytest.raises(runner.HostedRunnerError) as raised:
        with runner.github_hosted_userns_policy_window(
            _github_hosted_environment(tmp_path)
        ):
            pytest.fail("failed readback must not enter the window")

    assert raised.value.code == "HOST_USERNS_POLICY_UNAVAILABLE"
    assert writes == [(0, False), (1, True)]


@pytest.mark.parametrize("failure", ["write", "readback"])
def test_userns_policy_window_restore_failure_overrides_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    state = {"value": 1}
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: state["value"])

    def write(value: int, *, restoration: bool) -> None:
        if restoration and failure == "write":
            raise runner.HostedRunnerError(
                "HOST_USERNS_POLICY_RESTORE_FAILED", "forced restore refusal"
            )
        state["value"] = 0 if restoration and failure == "readback" else value

    monkeypatch.setattr(runner, "_write_host_userns_policy", write)

    with pytest.raises(runner.HostedRunnerError) as raised:
        with runner.github_hosted_userns_policy_window(
            _github_hosted_environment(tmp_path)
        ):
            assert state["value"] == 0

    assert raised.value.code == "HOST_USERNS_POLICY_RESTORE_FAILED"


def test_phase_e_restoration_failure_receipt_does_not_claim_restore_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    forge = tmp_path / "forge"
    consumer = tmp_path / "consumer"
    forge.mkdir()
    consumer.mkdir()
    receipt = tmp_path / "receipts/semantic-receipt.json"
    environment = _github_hosted_environment(tmp_path)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    state = {"value": 1}
    monkeypatch.setattr(runner, "_read_host_userns_policy", lambda: state["value"])

    def write(value: int, *, restoration: bool) -> None:
        if restoration:
            raise runner.HostedRunnerError(
                "HOST_USERNS_POLICY_RESTORE_FAILED", "forced restore refusal"
            )
        state["value"] = value

    def fake_invoke(
        argv: list[str], **kwargs: object
    ) -> runner.subprocess.CompletedProcess[str]:
        del kwargs
        staging = Path(
            next(value for value in argv if value.startswith("RECEIPT_PATH=")).split(
                "=", 1
            )[1]
        )
        runner.write_semantic_receipt(
            staging,
            request=request,
            status="COMPLETED",
            effect="APPLIED",
            evidence={"consumer_launched": True},
        )
        return runner.subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_write_host_userns_policy", write)
    monkeypatch.setattr(runner, "_invoke_phase_p_boundary", fake_invoke)

    with pytest.raises(runner.HostedRunnerError) as raised:
        runner.run_phase_e_hosted(
            forge,
            consumer,
            request,
            request_path=tmp_path / "request.json",
            bundle_path=tmp_path / "bundle.tar.gz",
            bundle_sha256=SHA_A,
            sealed_home=tmp_path / "sealed-home",
            scratch_root=tmp_path / "scratch",
            result_directory=tmp_path / "result",
            receipt_path=receipt,
        )

    assert raised.value.code == "HOST_USERNS_POLICY_RESTORE_FAILED"
    payload = runner.load_semantic_receipt(receipt)
    assert (payload["status"], payload["effect"]) == (
        "RECONCILIATION_REQUIRED",
        "EFFECT_UNKNOWN",
    )
    assert payload["evidence"]["host_userns_policy"] == {
        "scope": runner.HOST_USERNS_SCOPE,
        "control_key": runner.HOST_USERNS_SYSCTL_KEY,
        "control_path": os.fspath(runner.HOST_USERNS_SYSCTL_PATH),
        "original_value": 1,
        "active_value": 0,
        "mutation_performed": True,
        "active_readback_verified": True,
        "restore_readback_verified": False,
        "abrupt_termination_cleanup": "github_hosted_vm_decommission",
    }
    assert "restored_value" not in payload["evidence"]["host_userns_policy"]


def test_phase_p_hosted_restore_failure_cannot_publish_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    receipt = tmp_path / "receipts/semantic-receipt.json"

    @contextmanager
    def failed_restore() -> Iterator[runner.HostUsernsPolicyEvidence]:
        yield runner.HostUsernsPolicyEvidence(
            scope=runner.HOST_USERNS_SCOPE,
            original_value=1,
            active_value=0,
        )
        raise runner.HostedRunnerError(
            "HOST_USERNS_POLICY_RESTORE_FAILED", "forced restore failure"
        )

    monkeypatch.setattr(runner, "github_hosted_userns_policy_window", failed_restore)
    monkeypatch.setattr(
        runner,
        "prepare_phase_p_or_record_refusal",
        lambda *args, **kwargs: {"would_have_been": "success"},
    )

    with pytest.raises(runner.HostedRunnerError) as raised:
        runner.prepare_phase_p_hosted(
            tmp_path,
            request,
            scratch_root=tmp_path / "scratch",
            output_directory=tmp_path / "output",
            github_output=tmp_path / "github-output",
            receipt_path=receipt,
        )

    assert raised.value.code == "HOST_USERNS_POLICY_RESTORE_FAILED"
    payload = runner.load_semantic_receipt(receipt)
    assert (payload["status"], payload["effect"]) == ("REFUSED", "NOT_APPLIED")
    assert payload["evidence"]["failure"]["code"] == (
        "HOST_USERNS_POLICY_RESTORE_FAILED"
    )


def test_phase_e_hosted_restore_failure_discards_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    forge = tmp_path / "forge"
    consumer = tmp_path / "consumer"
    forge.mkdir()
    consumer.mkdir()
    receipt = tmp_path / "receipts/semantic-receipt.json"

    @contextmanager
    def failed_restore() -> Iterator[runner.HostUsernsPolicyEvidence]:
        yield runner.HostUsernsPolicyEvidence(
            scope=runner.HOST_USERNS_SCOPE,
            original_value=1,
            active_value=0,
        )
        raise runner.HostedRunnerError(
            "HOST_USERNS_POLICY_RESTORE_FAILED", "forced restore failure"
        )

    def fake_invoke(
        argv: list[str], **kwargs: object
    ) -> runner.subprocess.CompletedProcess[str]:
        del kwargs
        staging = Path(
            next(value for value in argv if value.startswith("RECEIPT_PATH=")).split(
                "=", 1
            )[1]
        )
        runner.write_semantic_receipt(
            staging,
            request=request,
            status="COMPLETED",
            effect="APPLIED",
            evidence={"would_have_been": "accepted"},
        )
        return runner.subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "github_hosted_userns_policy_window", failed_restore)
    monkeypatch.setattr(runner, "_invoke_phase_p_boundary", fake_invoke)

    with pytest.raises(runner.HostedRunnerError) as raised:
        runner.run_phase_e_hosted(
            forge,
            consumer,
            request,
            request_path=tmp_path / "request.json",
            bundle_path=tmp_path / "bundle.tar.gz",
            bundle_sha256=SHA_A,
            sealed_home=tmp_path / "sealed-home",
            scratch_root=tmp_path / "scratch",
            result_directory=tmp_path / "result",
            receipt_path=receipt,
        )

    assert raised.value.code == "HOST_USERNS_POLICY_RESTORE_FAILED"
    payload = runner.load_semantic_receipt(receipt)
    assert (payload["status"], payload["effect"]) == (
        "RECONCILIATION_REQUIRED",
        "EFFECT_UNKNOWN",
    )
    assert payload["evidence"]["failure"]["code"] == (
        "HOST_USERNS_POLICY_RESTORE_FAILED"
    )
    assert payload["evidence"].get("would_have_been") is None


def test_phase_e_hosted_publishes_staged_receipt_only_after_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    forge = tmp_path / "forge"
    consumer = tmp_path / "consumer"
    forge.mkdir()
    consumer.mkdir()
    receipt = tmp_path / "receipts/semantic-receipt.json"

    @contextmanager
    def restored() -> Iterator[runner.HostUsernsPolicyEvidence]:
        yield _restored_policy_evidence()

    def fake_invoke(
        argv: list[str], **kwargs: object
    ) -> runner.subprocess.CompletedProcess[str]:
        del kwargs
        staging = Path(
            next(value for value in argv if value.startswith("RECEIPT_PATH=")).split(
                "=", 1
            )[1]
        )
        runner.write_semantic_receipt(
            staging,
            request=request,
            status="COMPLETED",
            effect="APPLIED",
            evidence={"consumer_launched": True},
        )
        assert not receipt.exists()
        return runner.subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "github_hosted_userns_policy_window", restored)
    monkeypatch.setattr(runner, "_invoke_phase_p_boundary", fake_invoke)

    runner.run_phase_e_hosted(
        forge,
        consumer,
        request,
        request_path=tmp_path / "request.json",
        bundle_path=tmp_path / "bundle.tar.gz",
        bundle_sha256=SHA_A,
        sealed_home=tmp_path / "sealed-home",
        scratch_root=tmp_path / "scratch",
        result_directory=tmp_path / "result",
        receipt_path=receipt,
    )

    payload = runner.load_semantic_receipt(receipt)
    assert (payload["status"], payload["effect"]) == ("COMPLETED", "APPLIED")
    assert payload["evidence"]["host_userns_policy"] == _restored_policy_payload()


def test_phase_e_hosted_zero_exit_without_receipt_is_effect_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    forge = tmp_path / "forge"
    consumer = tmp_path / "consumer"
    forge.mkdir()
    consumer.mkdir()
    receipt = tmp_path / "receipts/semantic-receipt.json"

    @contextmanager
    def restored() -> Iterator[runner.HostUsernsPolicyEvidence]:
        yield _restored_policy_evidence()

    monkeypatch.setattr(runner, "github_hosted_userns_policy_window", restored)
    monkeypatch.setattr(
        runner,
        "_invoke_phase_p_boundary",
        lambda argv, **kwargs: runner.subprocess.CompletedProcess(
            argv, 0, stdout="", stderr=""
        ),
    )

    with pytest.raises(runner.HostedRunnerError) as raised:
        runner.run_phase_e_hosted(
            forge,
            consumer,
            request,
            request_path=tmp_path / "request.json",
            bundle_path=tmp_path / "bundle.tar.gz",
            bundle_sha256=SHA_A,
            sealed_home=tmp_path / "sealed-home",
            scratch_root=tmp_path / "scratch",
            result_directory=tmp_path / "result",
            receipt_path=receipt,
        )

    assert raised.value.code == "NETWORK_SEAL_EFFECT_UNKNOWN"
    payload = runner.load_semantic_receipt(receipt)
    assert (payload["status"], payload["effect"]) == (
        "RECONCILIATION_REQUIRED",
        "EFFECT_UNKNOWN",
    )
    assert payload["evidence"]["consumer_launch_state"] == "UNKNOWN"
    assert payload["evidence"]["host_userns_policy"] == _restored_policy_payload()


def test_phase_e_hosted_namespace_argv_is_fixed_and_secret_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_hostile_secret_value_123456789")
    argv = runner._phase_e_namespace_command(  # noqa: SLF001 - exact boundary law
        forge_root=tmp_path / "forge",
        consumer_root=tmp_path / "consumer",
        request_path=tmp_path / "request.json",
        bundle_path=tmp_path / "bundle.tar.gz",
        bundle_sha256=SHA_A,
        sealed_home=tmp_path / "home",
        scratch_root=tmp_path / "scratch",
        result_directory=tmp_path / "result",
        receipt_path=tmp_path / "receipt.json",
    )

    assert argv[:8] == [
        "/usr/bin/unshare",
        "--user",
        "--map-root-user",
        "--net",
        "--",
        "/usr/bin/env",
        "-i",
        f"HOME={tmp_path / 'home'}",
    ]
    assert argv[-6:-2] == ["--noprofile", "--norc", "-euo", "pipefail"]
    assert argv[-2] == "-c"
    assert "run-phase-e" in argv[-1]
    assert "probe-phase-e-hosted" not in argv[-1]
    assert "GITHUB_TOKEN" not in repr(argv)
    assert "ghp_hostile_secret_value" not in repr(argv)
    assert "--module" not in argv[-1]


def test_phase_p_process_refuses_when_kernel_boundary_receipt_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        argv: list[str], **kwargs: object
    ) -> runner.subprocess.CompletedProcess[str]:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return runner.subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "_invoke_phase_p_boundary", fake_run)
    with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - live gate fixture
        tmp_path / "network-home"
    ) as network_environment:
        with pytest.raises(runner.HostedRunnerError) as raised:
            runner._run_phase_p_checked(  # noqa: SLF001 - kernel boundary seam
                ["/usr/bin/true"],
                cwd=tmp_path,
                env=network_environment,
                network_environment=network_environment,
            )

    assert raised.value.code == "ACQUISITION_ALLOWLIST_UNAVAILABLE"
    wrapper_argv = captured["argv"]
    assert isinstance(wrapper_argv, list)
    assert wrapper_argv[:11] == [
        "/usr/bin/unshare",
        "--user",
        "--map-current-user",
        "--keep-caps",
        "--mount",
        "--net",
        "--",
        "/usr/bin/python3",
        "-I",
        "-S",
        "-c",
    ]
    assert wrapper_argv[-1] == "/usr/bin/true"
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["close_fds"] is True
    assert kwargs["start_new_session"] is True
    assert runner._PHASE_P_GATE_ENV not in kwargs["env"]  # noqa: SLF001


def test_phase_p_process_accepts_only_unforgeable_boundary_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(
        argv: list[str], **kwargs: object
    ) -> runner.subprocess.CompletedProcess[str]:
        status_fd = kwargs["pass_fds"][0]  # type: ignore[index]
        os.write(status_fd, runner._PHASE_P_BOUNDARY_READY)  # noqa: SLF001
        return runner.subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(runner, "_invoke_phase_p_boundary", fake_run)
    with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - live gate fixture
        tmp_path / "network-home"
    ) as network_environment:
        completed = runner._run_phase_p_checked(  # noqa: SLF001 - boundary seam
            ["/usr/bin/true"],
            cwd=tmp_path,
            env=network_environment,
            network_environment=network_environment,
        )
        assert completed.stdout == "ok"

        with pytest.raises(runner.HostedRunnerError) as raised:
            runner._run_phase_p_checked(  # noqa: SLF001 - alternate proxy seam
                ["/usr/bin/true"],
                cwd=tmp_path,
                env={
                    **network_environment,
                    "FTP_PROXY": "http://evil.invalid:8080",
                },
                network_environment=network_environment,
            )
    assert raised.value.code == "ACQUISITION_ALLOWLIST_UNAVAILABLE"


def test_phase_p_process_timeout_never_blocks_on_a_leaked_receipt_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaked_writer = -1

    def fake_timeout(argv: list[str], **kwargs: object) -> None:
        nonlocal leaked_writer
        leaked_writer = os.dup(kwargs["pass_fds"][0])  # type: ignore[index]
        raise subprocess.TimeoutExpired(argv, 0.01)

    monkeypatch.setattr(runner, "_invoke_phase_p_boundary", fake_timeout)
    started = time.monotonic()
    try:
        with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - live gate fixture
            tmp_path / "network-home"
        ) as network_environment:
            with pytest.raises(runner.HostedRunnerError) as raised:
                runner._run_phase_p_checked(  # noqa: SLF001 - timeout seam
                    ["/usr/bin/true"],
                    cwd=tmp_path,
                    env=network_environment,
                    network_environment=network_environment,
                    timeout=0.01,
                )
        assert raised.value.code == "ACQUISITION_ALLOWLIST_UNAVAILABLE"
        assert time.monotonic() - started < 1
    finally:
        if leaked_writer >= 0:
            os.close(leaked_writer)


def test_phase_p_boundary_bootstrap_is_fixed_valid_python() -> None:
    compile(  # noqa: S102 - compile validates the fixed wrapper source
        runner._PHASE_P_BOUNDARY_BOOTSTRAP,  # noqa: SLF001
        "<codeintel-phase-p-boundary>",
        "exec",
    )


def test_phase_p_boundary_timeout_kills_the_descendant_process_group(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "boundary-pids"
    probe = (
        "import os,time\n"
        "os.fork()\n"
        f"with open({os.fspath(pid_file)!r},'a',encoding='ascii') as target:\n"
        " target.write(str(os.getpid())+'\\n')\n"
        " target.flush()\n"
        " os.fsync(target.fileno())\n"
        "time.sleep(30)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        runner._invoke_phase_p_boundary(  # noqa: SLF001 - cleanup seam
            [sys.executable, "-c", probe],
            cwd=os.fspath(tmp_path),
            env={"PATH": "/usr/bin:/bin"},
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=0.75,
            close_fds=True,
            pass_fds=(),
            start_new_session=True,
        )

    pids = [int(row) for row in pid_file.read_text(encoding="ascii").splitlines()]
    assert len(pids) == 2

    def process_is_live(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        observed = subprocess.run(
            ["/bin/ps", "-o", "stat=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        return bool(observed) and not observed.startswith("Z")

    try:
        deadline = time.monotonic() + 3
        while any(process_is_live(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not any(process_is_live(pid) for pid in pids)
    finally:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine().lower() not in {"x86_64", "amd64"}
    or shutil.which("go") is None,
    reason="real Go loopback-bypass discriminator requires Linux/amd64 with Go",
)
def test_kernel_boundary_blocks_real_go_loopback_redirect_proxy_bypass(
    tmp_path: Path,
    github_hosted_userns_policy: runner.HostUsernsPolicyEvidence,
) -> None:
    """Prove Go's built-in localhost proxy bypass cannot open a direct socket."""

    del github_hosted_userns_policy

    source = tmp_path / "redirect_client.go"
    binary = tmp_path / "redirect-client"
    source.write_text(
        """package main
import (
    "io"
    "net/http"
    "os"
)
func main() {
    response, err := http.Get(os.Args[1])
    if err != nil { os.Exit(23) }
    defer response.Body.Close()
    body, err := io.ReadAll(response.Body)
    if err != nil || string(body) != "escaped" { os.Exit(24) }
}
""",
        encoding="utf-8",
    )
    go = shutil.which("go")
    assert go is not None
    built = subprocess.run(
        [go, "build", "-trimpath", "-o", os.fspath(binary), os.fspath(source)],
        cwd=tmp_path,
        env={
            "CGO_ENABLED": "0",
            "GO111MODULE": "off",
            "GOTOOLCHAIN": "local",
            "HOME": os.fspath(tmp_path),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert built.returncode == 0, built.stderr

    sink_hits: list[str] = []
    gate_hits: list[str] = []

    class Sink(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            sink_hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "7")
            self.end_headers()
            self.wfile.write(b"escaped")

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    class RedirectingProxy(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.2:{proxy_port}/escaped")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    proxy_hits: list[str] = []

    class HostRedirectingProxy(RedirectingProxy):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            proxy_hits.append(self.path)
            super().do_GET()

    class GateRedirectingProxy(RedirectingProxy):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            gate_hits.append(self.path)
            super().do_GET()

    proxy = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HostRedirectingProxy)
    proxy_port = int(proxy.server_address[1])
    sink = http.server.ThreadingHTTPServer(("127.0.0.2", proxy_port), Sink)

    gate_directory = Path(tempfile.mkdtemp(prefix="ci-t-", dir="/tmp"))
    os.chmod(gate_directory, 0o700)
    gate_path = gate_directory / "gate.sock"

    class UnixRedirectServer(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
        block_on_close = False

    gate = UnixRedirectServer(os.fspath(gate_path), GateRedirectingProxy)
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (sink, proxy, gate)
    ]
    for thread in threads:
        thread.start()
    try:
        network_environment = runner._phase_p_client_environment(  # noqa: SLF001
            f"http://127.0.0.1:{proxy_port}",
            tmp_path / "network-home",
            gate_socket=gate_path,
        )
        unsealed = subprocess.run(
            [os.fspath(binary), "http://outside.invalid/start"],
            cwd=tmp_path,
            env=network_environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert unsealed.returncode == 0
        assert sink_hits == ["/escaped"]
        assert len(proxy_hits) == 1
        sink_hits.clear()

        with pytest.raises(runner.HostedRunnerError) as raised:
            runner._run_phase_p_checked(  # noqa: SLF001 - kernel boundary probe
                [os.fspath(binary), "http://outside.invalid/start"],
                cwd=tmp_path,
                env=network_environment,
                network_environment=network_environment,
                timeout=15,
            )
        assert raised.value.code == "SUBPROCESS_FAILED"
        assert gate_hits == ["http://outside.invalid/start"]
        assert sink_hits == []
    finally:
        for server in (proxy, sink, gate):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
        shutil.rmtree(gate_directory, ignore_errors=True)


@pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine().lower() not in {"x86_64", "amd64"}
    or os.geteuid() == 0,
    reason="real Phase-P syscall boundary requires a non-root Linux/amd64 runner",
)
@pytest.mark.parametrize(
    "probe",
    [
        "import errno,socket,sys\n"
        "try: socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
        "except PermissionError as e: sys.exit(0 if e.errno==errno.EPERM else 31)\n"
        "sys.exit(30)\n",
        "import errno,socket,sys\n"
        "try: socket.socket(socket.AF_INET6,socket.SOCK_STREAM)\n"
        "except PermissionError as e: sys.exit(0 if e.errno==errno.EPERM else 31)\n"
        "sys.exit(30)\n",
        "import errno,socket,sys\n"
        "try: socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
        "except PermissionError as e: sys.exit(0 if e.errno==errno.EPERM else 31)\n"
        "sys.exit(30)\n",
        "import errno,socket,sys\n"
        "try: socket.socket(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_UDP)\n"
        "except PermissionError as e: sys.exit(0 if e.errno==errno.EPERM else 31)\n"
        "sys.exit(30)\n",
        "import errno,socket,sys\n"
        "stream=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
        "try: stream.sendto(b'x',0x20000000,('127.0.0.2',47853))\n"
        "except PermissionError as e: sys.exit(0 if e.errno==errno.EPERM else 31)\n"
        "sys.exit(30)\n",
        "import ctypes,errno,sys\n"
        "libc=ctypes.CDLL(None,use_errno=True)\n"
        "result=libc.syscall(425,1,ctypes.c_void_p())\n"
        "sys.exit(0 if result == -1 and ctypes.get_errno() == errno.EPERM else 30)\n",
        "import errno,os,sys\n"
        "try: os.open(f'/proc/{os.getppid()}/mem',os.O_RDWR)\n"
        "except OSError as e: sys.exit(0 if e.errno in {errno.EACCES,errno.EPERM} else 31)\n"
        "sys.exit(30)\n",
        "import ctypes,errno,os,signal,sys\n"
        "status={}\n"
        "with open('/proc/self/status',encoding='ascii') as source:\n"
        " for line in source:\n"
        "  if ':' in line:\n"
        "   key,value=line.split(':',1); status[key]=value.strip()\n"
        "if len(set(os.getresuid())) != 1 or len(set(os.getresgid())) != 1: sys.exit(32)\n"
        "if os.getuid() == 0 or os.getgid() == 0: sys.exit(33)\n"
        "if any(int(status[key],16) for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')): sys.exit(34)\n"
        "if status.get('NoNewPrivs') != '1': sys.exit(35)\n"
        "libc=ctypes.CDLL(None,use_errno=True)\n"
        "checks=((272,(0x10000000|0x40000000,)),(56,(0x10000000|signal.SIGCHLD,0,0,0,0)),(308,(-1,0)),(126,(0,0)))\n"
        "for number,args in checks:\n"
        " ctypes.set_errno(0); result=libc.syscall(number,*args)\n"
        " if result != -1 or ctypes.get_errno() != errno.EPERM: sys.exit(36)\n"
        "ctypes.set_errno(0); result=libc.syscall(435,ctypes.c_void_p(),0)\n"
        "sys.exit(0 if result == -1 and ctypes.get_errno() == errno.ENOSYS else 37)\n",
    ],
    ids=[
        "udp",
        "ipv6",
        "unix",
        "alternate-protocol",
        "fastopen",
        "io-uring",
        "supervisor-memory",
        "identity-capabilities-namespace-regain",
    ],
)
def test_kernel_boundary_denies_alternate_socket_and_async_paths(
    tmp_path: Path,
    probe: str,
    github_hosted_userns_policy: runner.HostUsernsPolicyEvidence,
) -> None:
    del github_hosted_userns_policy
    with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - real kernel boundary
        tmp_path / "network-home"
    ) as network_environment:
        completed = runner._run_phase_p_checked(  # noqa: SLF001 - hostile probe
            ["/usr/bin/python3", "-I", "-S", "-c", probe],
            cwd=tmp_path,
            env=network_environment,
            network_environment=network_environment,
            timeout=15,
        )
    assert completed.returncode == 0


@pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine().lower() not in {"x86_64", "amd64"}
    or os.geteuid() == 0,
    reason="real Phase-P descriptor boundary requires non-root Linux/amd64",
)
def test_kernel_boundary_exec_inherits_no_socket_descriptor(
    tmp_path: Path,
    github_hosted_userns_policy: runner.HostUsernsPolicyEvidence,
) -> None:
    del github_hosted_userns_policy
    probe = (
        "import os,stat,sys\n"
        "bad=[]\n"
        "for name in os.listdir('/proc/self/fd'):\n"
        " fd=int(name)\n"
        " if fd <= 2: continue\n"
        " try: mode=os.fstat(fd).st_mode\n"
        " except OSError: continue\n"
        " if stat.S_ISSOCK(mode): bad.append(fd)\n"
        "sys.exit(30 if bad else 0)\n"
    )
    with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - real kernel boundary
        tmp_path / "network-home"
    ) as network_environment:
        completed = runner._run_phase_p_checked(  # noqa: SLF001 - hostile probe
            ["/usr/bin/python3", "-I", "-S", "-c", probe],
            cwd=tmp_path,
            env=network_environment,
            network_environment=network_environment,
            timeout=15,
        )
    assert completed.returncode == 0


@pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine().lower() not in {"x86_64", "amd64"}
    or os.geteuid() == 0,
    reason="real Phase-P mount boundary requires non-root Linux/amd64",
)
def test_kernel_boundary_client_cannot_replace_the_parent_gate(
    tmp_path: Path,
    github_hosted_userns_policy: runner.HostUsernsPolicyEvidence,
) -> None:
    del github_hosted_userns_policy
    probe = (
        "import errno,os,sys\n"
        "try: os.unlink(sys.argv[1])\n"
        "except OSError as e: sys.exit(0 if e.errno == errno.EROFS else 31)\n"
        "sys.exit(30)\n"
    )
    with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - real mount boundary
        tmp_path / "network-home"
    ) as network_environment:
        gate_path = Path(network_environment[runner._PHASE_P_GATE_ENV])  # noqa: SLF001
        completed = runner._run_phase_p_checked(  # noqa: SLF001 - hostile probe
            ["/usr/bin/python3", "-I", "-S", "-c", probe, os.fspath(gate_path)],
            cwd=tmp_path,
            env=network_environment,
            network_environment=network_environment,
            timeout=15,
        )
        assert completed.returncode == 0
        assert stat.S_ISSOCK(gate_path.lstat().st_mode)


@pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine().lower() not in {"x86_64", "amd64"}
    or os.geteuid() == 0,
    reason="AppArmor userns discriminator requires non-root Linux/amd64",
)
def test_github_hosted_apparmor_policy_is_the_boundary_failure_discriminator(
    tmp_path: Path,
    github_hosted_userns_policy: runner.HostUsernsPolicyEvidence,
) -> None:
    del github_hosted_userns_policy
    with runner._phase_p_allowlist_proxy(  # noqa: SLF001 - real hosted discriminator
        tmp_path / "network-home"
    ) as network_environment:
        try:
            runner._write_host_userns_policy(1, restoration=False)  # noqa: SLF001
            assert runner._read_host_userns_policy() == 1  # noqa: SLF001
            with pytest.raises(runner.HostedRunnerError) as raised:
                runner._run_phase_p_checked(  # noqa: SLF001
                    ["/usr/bin/true"],
                    cwd=tmp_path,
                    env=network_environment,
                    network_environment=network_environment,
                    timeout=15,
                )
            assert raised.value.code == "ACQUISITION_ALLOWLIST_UNAVAILABLE"
        finally:
            runner._write_host_userns_policy(0, restoration=False)  # noqa: SLF001
            assert runner._read_host_userns_policy() == 0  # noqa: SLF001

        completed = runner._run_phase_p_checked(  # noqa: SLF001
            ["/usr/bin/true"],
            cwd=tmp_path,
            env=network_environment,
            network_environment=network_environment,
            timeout=15,
        )
        assert completed.returncode == 0


def test_github_replay_artifact_download_uses_the_same_proxy_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "fixture-token-value")
    captured: dict[str, object] = {}

    def fake_run(
        argv: list[str], **kwargs: object
    ) -> runner.subprocess.CompletedProcess[bytes]:
        captured["argv"] = list(argv)
        captured["env"] = dict(kwargs["env"])  # type: ignore[arg-type]
        captured["network_environment"] = dict(  # type: ignore[arg-type]
            kwargs["network_environment"]
        )
        output = kwargs["stdout"]
        output.write(b"fixture zip bytes")  # type: ignore[attr-defined]
        return runner.subprocess.CompletedProcess(argv, 0, stdout=None, stderr=b"")

    monkeypatch.setattr(runner, "_run_phase_p_process", fake_run)
    network_environment = runner._phase_p_client_environment(  # noqa: SLF001
        "http://127.0.0.1:12345", tmp_path / "network-home"
    )
    destination = tmp_path / "receipt.zip"

    runner._gh_download_artifact(  # noqa: SLF001 - replay network boundary
        202,
        destination,
        network_environment=network_environment,
    )

    assert captured["argv"] == [
        "/usr/bin/gh",
        "api",
        "-H",
        "Accept: application/vnd.github+json",
        "repos/mastermindx-market-intelligence/Mastermind/actions/artifacts/202/zip",
    ]
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["HTTPS_PROXY"] == "http://127.0.0.1:12345"
    assert environment["NO_PROXY"] == ""
    assert environment["GH_HOST"] == "github.com"
    assert environment["GH_TOKEN"] == "fixture-token-value"
    assert captured["network_environment"] == network_environment
    assert destination.read_bytes() == b"fixture zip bytes"


def test_go_module_inventory_requires_exact_pinned_main_module() -> None:
    accepted = runner._normalize_go_module_inventory(  # noqa: SLF001
        '{"Path":"github.com/sourcegraph/zoekt","Main":true}\n'
    )
    assert accepted == [{"path": "github.com/sourcegraph/zoekt", "main": True}]

    with pytest.raises(runner.HostedRunnerError, match="DEPENDENCY_GRAPH_INVALID"):
        runner._normalize_go_module_inventory(  # noqa: SLF001
            '{"Path":"sourcegraph/zoekt","Main":true}\n'
        )


def test_network_denial_must_be_proven_before_consumer_launch() -> None:
    events: list[str] = []

    def probe() -> runner.NetworkSealProof:
        events.append("probe")
        return runner.NetworkSealProof(
            interfaces=("lo",),
            non_loopback_routes=(),
            outbound_probe="DENIED",
            denial_errno=errno.ENETUNREACH,
        )

    def launch() -> runner.LaunchEvidence:
        events.append("launch")
        return runner.LaunchEvidence(
            returncode=0,
            pid=101,
            process_group=101,
            stdout_sha256=hashlib.sha256(b"").hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
            stdout_bytes=0,
            stderr_bytes=0,
            user_seconds=0.1,
            system_seconds=0.1,
            max_rss_kib=1024,
        )

    proof, evidence = runner.prove_then_launch(probe=probe, launch=launch)
    assert events == ["probe", "launch"]
    assert proof.outbound_probe == "DENIED"
    assert evidence.returncode == 0


def test_network_exposure_or_missing_probe_refuses_before_launch() -> None:
    launched = False

    def launch() -> runner.LaunchEvidence:
        nonlocal launched
        launched = True
        raise AssertionError("must not launch")

    for proof in (
        runner.NetworkSealProof(
            interfaces=("eth0", "lo"),
            non_loopback_routes=("default",),
            outbound_probe="DENIED",
            denial_errno=errno.ENETUNREACH,
        ),
        runner.NetworkSealProof(
            interfaces=("lo",),
            non_loopback_routes=(),
            outbound_probe="CONNECTED",
            denial_errno=None,
        ),
    ):
        with pytest.raises(runner.HostedRunnerError, match="NETWORK_SEAL_UNAVAILABLE"):
            runner.prove_then_launch(probe=lambda proof=proof: proof, launch=launch)
    assert launched is False


def test_cleanup_evidence_requires_dead_process_group_and_no_residue() -> None:
    assert runner.validate_cleanup(
        runner.CleanupEvidence(process_group_dead=True, unexpected_residue=())
    )
    with pytest.raises(runner.HostedRunnerError, match="CLEANUP_LEAK"):
        runner.validate_cleanup(
            runner.CleanupEvidence(
                process_group_dead=False, unexpected_residue=("pid:42",)
            )
        )


def test_cleanup_reports_hostile_non_directory_residue(tmp_path: Path) -> None:
    shard_root = tmp_path / "shards"
    log_root = tmp_path / "logs"
    shard_root.write_text("hostile file\n", encoding="utf-8")
    log_root.symlink_to(tmp_path / "missing")

    evidence = runner._cleanup_candidate_scratch(  # noqa: SLF001
        process_group=999_999_999,
        shard_root=shard_root,
        log_root=log_root,
    )

    assert evidence.process_group_dead is True
    assert evidence.unexpected_residue == ("shards", "logs")
    with pytest.raises(runner.HostedRunnerError, match="CLEANUP_LEAK"):
        runner.validate_cleanup(evidence)


def test_result_artifact_census_rejects_secret_bearing_bytes(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    (output / "z0-result.json").write_text(
        '{"token":"ghp_abcdefghijklmnopqrstuvwxyz1234567890"}\n',
        encoding="utf-8",
    )

    with pytest.raises(runner.HostedRunnerError, match="SECRET_BEARING_OUTPUT"):
        runner._result_artifact_census(output)  # noqa: SLF001


def test_dataclass_evidence_is_json_safe_and_has_no_raw_environment() -> None:
    evidence = runner.LaunchEvidence(
        returncode=0,
        pid=1,
        process_group=1,
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        stdout_bytes=1,
        stderr_bytes=2,
        user_seconds=0.0,
        system_seconds=0.0,
        max_rss_kib=1,
    )
    encoded = json.dumps(dataclasses.asdict(evidence), sort_keys=True)
    assert "GITHUB_TOKEN" not in encoded
    assert "environment" not in encoded


def test_phase_e_completed_receipt_shape_is_secret_free_and_replayable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = Path(runner.__file__).resolve().parents[2]
    lock = runner.locks.load_toolchain_lock(
        repository_root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json",
        schema_path=repository_root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json",
    )
    request = _request(lock_sha256=lock.sha256)
    forge = tmp_path / "forge"
    consumer = tmp_path / "consumer"
    forge.mkdir()
    consumer.mkdir()
    policy = consumer / "research/code_intelligence_fabric/z0-path-policy.json"
    policy.parent.mkdir(parents=True)
    policy.write_text("{}\n", encoding="utf-8")
    bundle_sha = "4" * 64
    bundle_path = tmp_path / f"codeintel-z0-{bundle_sha}.tar.gz"
    bundle_path.write_bytes(b"fixture")
    indexer_body = b"indexer"
    webserver_body = b"webserver"
    manifest = {
        "files": [
            {
                "path": "bin/zoekt-git-index",
                "sha256": hashlib.sha256(indexer_body).hexdigest(),
            },
            {
                "path": "bin/zoekt-webserver",
                "sha256": hashlib.sha256(webserver_body).hexdigest(),
            },
        ]
    }
    verified = runner.VerifiedBundle(
        path=bundle_path,
        sha256=bundle_sha,
        size=len(bundle_path.read_bytes()),
        manifest=manifest,
        manifest_sha256="5" * 64,
    )

    monkeypatch.setattr(runner, "derive_request", lambda *args, **kwargs: request)
    monkeypatch.setattr(
        runner.locks, "load_toolchain_lock", lambda *args, **kwargs: lock
    )
    monkeypatch.setattr(runner, "verify_bundle", lambda *args, **kwargs: verified)
    monkeypatch.setattr(
        runner,
        "verify_consumer_checkout",
        lambda *args, **kwargs: runner.ConsumerIdentity(
            request.consumer_sha,
            request.consumer_tree_sha,
            runner.FIXED_REPOSITORY,
            runner.FIXED_CONSUMER_BRANCH,
        ),
    )
    monkeypatch.setattr(
        runner,
        "consumer_effective_paths",
        lambda *args, **kwargs: (
            "6" * 40,
            ("experiments/code_discovery/z0_runner.py",),
        ),
    )
    monkeypatch.setattr(
        runner, "selected_source_digest", lambda *args, **kwargs: "7" * 64
    )

    def extract(bundle: runner.VerifiedBundle, destination: Path) -> dict[str, Path]:
        del bundle
        (destination / "bin").mkdir(parents=True)
        indexer = destination / "bin/zoekt-git-index"
        webserver = destination / "bin/zoekt-webserver"
        indexer.write_bytes(indexer_body)
        webserver.write_bytes(webserver_body)
        os.chmod(indexer, 0o755)
        os.chmod(webserver, 0o755)
        return {
            "bin/zoekt-git-index": indexer,
            "bin/zoekt-webserver": webserver,
        }

    monkeypatch.setattr(runner, "extract_verified_bundle", extract)
    launch = runner.LaunchEvidence(
        returncode=0,
        pid=123,
        process_group=123,
        stdout_sha256=hashlib.sha256(b"").hexdigest(),
        stderr_sha256=hashlib.sha256(b"").hexdigest(),
        stdout_bytes=0,
        stderr_bytes=0,
        user_seconds=0.1,
        system_seconds=0.1,
        max_rss_kib=1024,
    )
    proof = runner.NetworkSealProof(
        interfaces=("lo",),
        non_loopback_routes=(),
        outbound_probe="DENIED",
        denial_errno=errno.ENETUNREACH,
    )
    monkeypatch.setattr(
        runner, "_launch_fixed_consumer", lambda *args, **kwargs: launch
    )
    monkeypatch.setattr(
        runner,
        "prove_then_launch",
        lambda *, probe, launch: (proof, launch()),
    )
    monkeypatch.setattr(
        runner,
        "_cleanup_candidate_scratch",
        lambda **kwargs: runner.CleanupEvidence(True, ()),
    )
    receipt_path = tmp_path / "receipt/semantic-receipt.json"

    receipt = runner.run_phase_e(
        forge,
        consumer,
        request,
        bundle_path=bundle_path,
        bundle_sha256=bundle_sha,
        scratch_root=tmp_path / "scratch",
        result_directory=tmp_path / "result",
        receipt_path=receipt_path,
    )

    assert receipt["status"] == "COMPLETED"
    assert receipt["effect"] == "APPLIED"
    assert (
        receipt["evidence"]["consumer_invocation"]["sensitive_environment_inherited"]
        is False
    )
    assert (
        runner.reconcile_receipt(receipt_path, request).disposition
        is runner.ReplayDisposition.RETURN_PRIOR
    )
