"""C0 falsifier — B6: the sandbox is enforcement, not a claim.

A closed environment variable set is not a disabled network. These tests require
the launch contract to actually deny network, actually bound CPU/memory/files/
processes, actually create an isolated process group, and actually prove
descendants died — or to fail closed with a typed blocker that the result must
carry instead of an unearned `network_policy: enforced`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from experiments.code_intelligence.sandbox import (
    DEFAULT_LIMITS,
    LaunchLimits,
    SandboxContract,
    SandboxUnavailable,
    build_sandbox,
)

PYTHON = Path(sys.executable).resolve()


class TestContractConstruction:
    def test_sandbox_is_built_with_a_launcher_and_a_digest(self, tmp_path: Path) -> None:
        contract = build_sandbox(scratch=tmp_path)
        assert contract.network_denied is True
        assert contract.launcher_argv, "a real launcher prefix is required"
        assert len(contract.profile_digest) == 64
        assert contract.limits == DEFAULT_LIMITS

    def test_contract_is_immutable(self, tmp_path: Path) -> None:
        contract = build_sandbox(scratch=tmp_path)
        with pytest.raises(Exception):
            contract.network_denied = False  # type: ignore[misc]

    def test_missing_launcher_fails_closed_with_a_typed_blocker(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "experiments.code_intelligence.sandbox._launcher_path",
            lambda: None,
        )
        with pytest.raises(SandboxUnavailable) as excinfo:
            build_sandbox(scratch=tmp_path)
        assert excinfo.value.code == "SANDBOX_NETWORK_DENIAL_UNAVAILABLE"

    def test_opting_out_of_network_denial_is_recorded_not_hidden(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "experiments.code_intelligence.sandbox._launcher_path", lambda: None
        )
        contract = build_sandbox(scratch=tmp_path, require_network_denial=False)
        assert contract.network_denied is False
        assert contract.launcher_argv == ()


class TestNetworkDenialIsAttested:
    def test_canary_proves_the_network_is_actually_denied(self, tmp_path: Path) -> None:
        contract = build_sandbox(scratch=tmp_path)
        receipt = contract.attest_no_network()
        assert receipt["network_denied"] is True
        assert receipt["probe"] == "tcp+dns"
        assert receipt["detail"]

    def test_the_same_probe_succeeds_without_the_sandbox(self, tmp_path: Path) -> None:
        # Guards against a vacuous canary: if the probe fails everywhere, the
        # sandbox proves nothing. This test is the falsifier for the falsifier.
        unsandboxed = build_sandbox(
            scratch=tmp_path, require_network_denial=False
        )
        receipt = unsandboxed.attest_no_network()
        assert receipt["network_denied"] is False, (
            "network is unreachable even outside the sandbox, so the denial "
            "canary would be vacuous on this host"
        )


class TestResourceLimits:
    def test_defaults_are_bounded(self) -> None:
        assert DEFAULT_LIMITS.cpu_seconds > 0
        assert DEFAULT_LIMITS.address_space_bytes > 0
        assert DEFAULT_LIMITS.max_open_files > 0

    def test_limits_are_applied_to_the_child(self, tmp_path: Path) -> None:
        contract = build_sandbox(
            scratch=tmp_path,
            limits=LaunchLimits(
                cpu_seconds=5, address_space_bytes=512 * 1024 * 1024,
                max_open_files=64, max_processes=32,
            ),
        )
        observed = contract.run_probe(
            PYTHON,
            (
                "-c",
                "import resource,json;"
                "print(json.dumps({'cpu':resource.getrlimit(resource.RLIMIT_CPU)[0],"
                "'nofile':resource.getrlimit(resource.RLIMIT_NOFILE)[0]}))",
            ),
        )
        assert observed["cpu"] == 5
        assert observed["nofile"] == 64

    def test_enforcement_is_measured_not_assumed(self, tmp_path: Path) -> None:
        contract = build_sandbox(scratch=tmp_path)
        measured = set(contract.enforced_limits) | set(contract.unenforced_limits)
        assert measured == {
            "RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_NOFILE", "RLIMIT_NPROC"
        }
        assert not (set(contract.enforced_limits) & set(contract.unenforced_limits))

    def test_memory_ceiling_either_kills_or_is_declared_unenforceable(
        self, tmp_path: Path
    ) -> None:
        contract = build_sandbox(
            scratch=tmp_path,
            limits=LaunchLimits(
                cpu_seconds=20, address_space_bytes=64 * 1024 * 1024,
                max_open_files=64, max_processes=32,
            ),
        )
        if "RLIMIT_AS" in contract.enforced_limits:
            with pytest.raises(Exception):
                contract.run_probe(
                    PYTHON, ("-c", "x = bytearray(512 * 1024 * 1024); print(len(x))")
                )
        else:
            # Darwin rejects RLIMIT_AS. That must be a NAMED gap the result
            # carries, never an unclaimed silent failure.
            assert "RLIMIT_AS" in contract.unenforced_limits


class TestProcessGroupAndDescendants:
    def test_child_runs_in_its_own_process_group(self, tmp_path: Path) -> None:
        contract = build_sandbox(scratch=tmp_path)
        observed = contract.run_probe(
            PYTHON,
            ("-c", "import os,json;print(json.dumps({'pgid':os.getpgid(0),'pid':os.getpid()}))"),
        )
        assert observed["pgid"] == observed["pid"], "child must lead its own group"
        assert observed["pgid"] != os.getpgid(0), "child must not share our group"
