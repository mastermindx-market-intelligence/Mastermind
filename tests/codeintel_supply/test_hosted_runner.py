from __future__ import annotations

import dataclasses
import errno
import hashlib
import json
import os
from pathlib import Path

import pytest

from experiments.codeintel_supply import hosted_runner as runner

HEX_A = "a" * 40
HEX_B = "b" * 40
HEX_C = "c" * 40
HEX_D = "d" * 40
SHA_A = "a" * 64
SHA_B = "b" * 64


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

    def stable(endpoint: str) -> dict[str, object]:
        page = int(endpoint.rsplit("page=", 1)[1])
        return pages[page]

    monkeypatch.setattr(runner, "_gh_json", stable)
    rows = runner._gh_paginated_rows(  # noqa: SLF001 - replay safety boundary
        "repos/example/actions/runs?event=workflow_dispatch",
        field="workflow_runs",
        max_rows=10,
    )
    assert [row["id"] for row in rows] == [101, 102]

    def moved(endpoint: str) -> dict[str, object]:
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

    def rows(endpoint: str, *, field: str, max_rows: int) -> list[dict[str, object]]:
        del max_rows
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

    def download(artifact_id: int, destination: Path) -> None:
        assert artifact_id == 202
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
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, timeout
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

    monkeypatch.setattr(runner, "run_checked", fake_run_checked)
    source = tmp_path / "source"
    source.mkdir()
    payload_bin = tmp_path / "payload/bin"
    payload_bin.mkdir(parents=True)

    result = runner._repeat_build_zoekt(  # noqa: SLF001 - exact hostile boundary
        source,
        go_binary=pinned_go,
        scratch=tmp_path / "scratch",
        payload_bin=payload_bin,
    )

    assert calls
    assert {call[0][0] for call in calls} == {os.fspath(pinned_go.resolve())}
    assert all(call[1]["GOTOOLCHAIN"] == "local" for call in calls)
    assert all(
        call[1]["PATH"].startswith(f"{pinned_go.parent.resolve()}:") for call in calls
    )
    assert len({call[1]["GOCACHE"] for call in calls}) >= 5
    assert result["binaries"]["zoekt-git-index"]["byte_identical"] is True
    assert (payload_bin / "zoekt-webserver").read_bytes().startswith(b"binary:")


def test_zoekt_checkout_ignores_ambient_git_and_fetches_only_exact_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_checked(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, env, timeout
        calls.append(list(argv))
        return runner.subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner, "run_checked", fake_run_checked)
    monkeypatch.setenv("PATH", os.fspath(tmp_path / "hostile-bin"))
    destination = tmp_path / "zoekt"
    runner._checkout_exact_zoekt(destination)  # noqa: SLF001 - exact hostile boundary

    assert calls
    assert {argv[0] for argv in calls} == {"/usr/bin/git"}
    fetch = next(argv for argv in calls if "fetch" in argv)
    checkout = next(argv for argv in calls if "checkout" in argv)
    assert fetch[-1] == runner.locks.ZOEKT_COMMIT
    assert checkout[-1] == runner.locks.ZOEKT_COMMIT
    assert "main" not in fetch


def test_go_archive_rejects_disallowed_redirect_before_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_checked(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, env, timeout
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

    monkeypatch.setattr(runner, "run_checked", fake_run_checked)
    with pytest.raises(
        runner.HostedRunnerError, match="ACQUISITION_REDIRECT_FORBIDDEN"
    ):
        runner._download_exact_go_archive(tmp_path / "go.tar.gz")  # noqa: SLF001

    assert len(calls) == 1
    assert "--location" not in calls[0]
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
        timeout: float = 60,
    ) -> runner.subprocess.CompletedProcess[str]:
        del cwd, env, timeout
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

    monkeypatch.setattr(runner, "run_checked", fake_run_checked)
    monkeypatch.setattr(runner.locks, "GO_ARCHIVE_SIZE", len(body))
    monkeypatch.setattr(
        runner.locks, "GO_ARCHIVE_SHA256", hashlib.sha256(body).hexdigest()
    )

    assert runner._download_exact_go_archive(destination) == redirect  # noqa: SLF001
    assert [argv[-1] for argv in calls] == [runner.locks.GO_ARCHIVE_URL, redirect]
    assert all("--location" not in argv for argv in calls)


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
