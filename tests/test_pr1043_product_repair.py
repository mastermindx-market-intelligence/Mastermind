"""Focused tests for the PR-1043 product repair.

These tests exercise the narrow seams added by the product repair without
requiring the full Executive OS runtime.  They cover:

* enrolled v5 attended worker activation succeeds while unenrolled v5 still
  refuses (and v5 generation of type ``bool`` is rejected);
* the wire payload omits the empty claim by default;
* the configured Control service registers the exact READ-only quota
  metadata and enriches one already-claimed spec through the existing
  observation function before adapter start;
* ordinary service composition never calls the observation function and
  retains ordinary capabilities;
* the install script source includes/executes the v4 versus v5 emission and
  digest fence.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from control_plane.executive_worker_broker import _launch_spec_to_json
from control_plane.worker_execution_contract import WorkerLaunchSpec
from scripts.executive_os_phase1c_worker import (
    SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
    WorkerConfigError,
    _assert_service_activation_allowed,
    _load_config,
)

ALIBABA_BINDING = "alibaba-token-plan-personal.codex-responses"
_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(root: Path, *, schema: str, binding_id: str | None = None) -> dict:
    value = {
        "schema_version": schema,
        "control_uid": 450,
        "worker_uid": os.getuid(),
        "worker_gid": os.getgid(),
        "allowed_supplementary_gids": [12, 61, 100],
        "worker_user": "_mastermind_fixture",
        "worker_id": "subscription-fixture-01",
        "workspace_root": str(root / "workspaces"),
        "run_root": str(root / "runs"),
        "provider_home": str(root / "provider-home"),
        "codex_binary": str(root / "bin" / "codex"),
        "codex_attestation_receipt": str(root / "state" / "attestation.json"),
        "allowed_codex_versions": ["0.147.0"],
        "required_team_identifier": "2DC432GLL2",
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": str(root / "state" / "sweep.json"),
        "require_secret_canary": True,
        "operator_harness_armed": False,
    }
    if binding_id is not None:
        value["harness_binding_id"] = binding_id
    return value


def _write_config(root: Path, value: dict) -> Path:
    path = root / "worker.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o440)
    return path


def _claim_dict(
    *,
    run_id: str = "attempt-1",
    job_id: str = "job-1",
    worker_id: str = "codex-01",
    binding_id: str = "b",
    realm_sha: str = "0" * 64,
    realm_generation: int = 1,
    issued_at_ms: int = 1000,
    expires_at_ms: int = 2000,
) -> dict:
    return {
        "schema": "mastermind.subscription_canary_claim/v1",
        "execution_mode": "interactive_canary",
        "run_id": run_id,
        "job_id": job_id,
        "worker_id": worker_id,
        "quota_class": "interactive",
        "fence_generation": 1,
        "capacity_generation": 1,
        "capacity_state": "BUSY",
        "held_attempt_id": run_id,
        "current_attempt_id": run_id,
        "binding_id": binding_id,
        "profile_id": "p",
        "adapter_id": "codex-cli",
        "model": "m",
        "realm_config_sha256": realm_sha,
        "realm_generation": realm_generation,
        "catalog_digest": "1" * 64,
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": expires_at_ms,
        "observation_digest": "2" * 64,
    }


# ---------------------------------------------------------------------------
# Gap 1: enrolled v5 attended activation + bool generation rejection
# ---------------------------------------------------------------------------


class EnrolledV5ActivationTest(unittest.TestCase):
    def test_enrolled_v5_attended_activation_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = _config(
                root,
                schema=SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
                binding_id=ALIBABA_BINDING,
            )
            value["subscription_realm_enrollment"] = {
                "binding_id": ALIBABA_BINDING,
                "generation": 3,
            }
            loaded = _load_config(
                _write_config(root, value), require_root_owner=False,
            )
            _assert_service_activation_allowed(loaded)

    def test_unenrolled_v5_still_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = _config(
                root,
                schema=SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
                binding_id=ALIBABA_BINDING,
            )
            loaded = _load_config(
                _write_config(root, value), require_root_owner=False,
            )
            with self.assertRaisesRegex(
                WorkerConfigError, "not armed for autonomous service",
            ):
                _assert_service_activation_allowed(loaded)

    def test_v5_rejects_boolean_generation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = _config(
                root,
                schema=SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
                binding_id=ALIBABA_BINDING,
            )
            value["subscription_realm_enrollment"] = {
                "binding_id": ALIBABA_BINDING,
                "generation": True,
            }
            with self.assertRaisesRegex(
                WorkerConfigError, "subscription realm enrollment contract is invalid",
            ):
                _load_config(
                    _write_config(root, value), require_root_owner=False,
                )


# ---------------------------------------------------------------------------
# Gap 2: launch-spec wire payload + ordinary broker refusal
# ---------------------------------------------------------------------------


class LaunchSpecWireTest(unittest.TestCase):
    def _base_spec(self) -> WorkerLaunchSpec:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "ws").mkdir()
            (root / "rd").mkdir()
            return WorkerLaunchSpec(
                run_id="attempt-1",
                job_id="job-1",
                worker_id="codex-01",
                workspace_path=root / "ws",
                run_dir=root / "rd",
                prompt="hello",
                result_schema_path=root / "rd" / "schema.json",
            )

    def test_ordinary_wire_payload_omits_empty_claim(self) -> None:
        spec = self._base_spec()
        self.assertFalse(spec.subscription_canary_claim)
        serialized = _launch_spec_to_json(spec)
        self.assertNotIn("subscription_canary_claim", serialized)

    def test_canary_wire_payload_includes_claim(self) -> None:
        spec = self._base_spec()
        claim = _claim_dict()
        claim_spec = dataclasses.replace(spec, subscription_canary_claim=claim)
        serialized = _launch_spec_to_json(claim_spec)
        self.assertIn("subscription_canary_claim", serialized)
        # Round-trip: serialized claim must equal the input shape (mapping).
        self.assertEqual(dict(serialized["subscription_canary_claim"]), claim)

# ---------------------------------------------------------------------------
# Gap 2 (Control): ServiceConfig realm registration + READ-only quota metadata
# ---------------------------------------------------------------------------


class ServiceConfigRealmTest(unittest.TestCase):
    def _config_kwargs(self) -> dict:
        from control_plane.executive_service import ServiceConfig
        return dict(
            runtime_root=Path("/var/db/mastermind-executive"),
            socket_path=Path("/var/run/mastermind-executive/control.sock"),
            proof_source_repository=Path("/var/db/mastermind-executive/source"),
            proof_workspace_root=Path(
                "/var/db/mastermind-executive/jobs/workspaces",
            ),
            proof_base_sha="0" * 40,
            proof_branch="codex/phase1c-a-proof",
            backup_root=Path("/var/db/mastermind-executive/control/backups"),
            worker_id="codex-01",
            quota_class="codex-native",
            model="gpt-5.6-sol",
            effort="xhigh",
            cost_class="standard",
        )

    def _realm_config_kwargs(self) -> dict:
        from control_plane.subscription_harness_bindings import get_binding
        from control_plane.subscription_provider_profiles import get_profile

        binding = get_binding(ALIBABA_BINDING)
        profile = get_profile(binding.profile_id)
        value = self._config_kwargs()
        value.update(
            provider=binding.provider,
            worker_type=binding.adapter_id,
            model=binding.model_for(profile),
        )
        return value

    def _descriptor(self, cfg) -> tuple[dict, tuple[str, ...]]:
        from control_plane.executive_service import ExecutiveControlService
        service = ExecutiveControlService.__new__(ExecutiveControlService)
        service.config = cfg
        return service._primary_quota_descriptor(
            default_capabilities=["code", "research", "tests"],
        )

    def test_ordinary_config_keeps_default_capabilities(self) -> None:
        from control_plane.executive_service import ServiceConfig
        cfg = ServiceConfig(**self._config_kwargs())
        self.assertIsNone(cfg.subscription_canary_realm())
        descriptor, capabilities = self._descriptor(cfg)
        self.assertEqual(tuple(capabilities), ("code", "research", "tests"))
        self.assertEqual(descriptor["model"], "gpt-5.6-sol")
        self.assertEqual(descriptor["provider"], "codex")
        self.assertNotIn(
            "subscription_canary_realm", descriptor.get("metadata", {}),
        )

    def test_configured_realm_registers_read_only_quota_metadata(self) -> None:
        from control_plane.executive_service import ServiceConfig
        from control_plane.subscription_harness_bindings import get_binding

        binding = get_binding(ALIBABA_BINDING)
        from control_plane.subscription_provider_profiles import get_profile
        profile = get_profile(binding.profile_id)
        cfg = ServiceConfig(
            **self._realm_config_kwargs(),
            subscription_canary_realm_binding_id=ALIBABA_BINDING,
            subscription_canary_realm_generation=4,
            subscription_canary_realm_config_sha256="0" * 64,
        )
        realm = cfg.subscription_canary_realm()
        self.assertIsNotNone(realm)
        self.assertEqual(realm["binding_id"], ALIBABA_BINDING)
        self.assertEqual(realm["generation"], 4)
        self.assertEqual(realm["config_sha256"], "0" * 64)
        descriptor, capabilities = self._descriptor(cfg)
        self.assertEqual(tuple(capabilities), ("read",))
        self.assertEqual(descriptor["provider"], binding.provider)
        self.assertEqual(
            descriptor["model"], binding.model_for(profile),
        )
        metadata = descriptor["metadata"]
        self.assertIn("subscription_canary_realm", metadata)
        self.assertEqual(
            dict(metadata["subscription_canary_realm"]), dict(realm),
        )

    def test_configured_realm_registration_is_exact_and_idempotent(self) -> None:
        from control_plane.executive_runtime import Runtime
        from control_plane.executive_service import (
            ExecutiveControlService,
            ServiceConfig,
        )

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            kwargs = self._realm_config_kwargs()
            kwargs.update(
                runtime_root=root / "runtime",
                socket_path=root / "runtime" / "control.sock",
                proof_source_repository=root / "source",
                proof_workspace_root=root / "workspaces",
                backup_root=root / "backups",
                subscription_canary_realm_binding_id=ALIBABA_BINDING,
                subscription_canary_realm_generation=4,
                subscription_canary_realm_config_sha256="0" * 64,
            )
            config = ServiceConfig(**kwargs)
            service = ExecutiveControlService.__new__(ExecutiveControlService)
            service.config = config
            service.runtime = Runtime.at(config.runtime_root)

            first = service._register_worker()
            second = service._register_worker()
            self.assertEqual(first.worker_id, second.worker_id)
            self.assertEqual(first.provider, "alibaba")
            self.assertEqual(first.capabilities, ["read"])
            self.assertEqual(list(second.quota_classes), [config.quota_class])
            quota = service.runtime.workers.get_quota_class(
                config.worker_id, config.quota_class,
            )
            self.assertEqual(quota.capabilities, ["read"])
            self.assertEqual(
                quota.metadata,
                {"subscription_canary_realm": dict(config.subscription_canary_realm())},
            )

    def test_realm_rejects_unreviewed_binding(self) -> None:
        from control_plane.executive_service import ServiceConfig
        cfg_kwargs = self._realm_config_kwargs()
        cfg_kwargs["subscription_canary_realm_binding_id"] = "not-a-real-binding"
        cfg_kwargs["subscription_canary_realm_generation"] = 1
        cfg_kwargs["subscription_canary_realm_config_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "binding is not reviewed"):
            ServiceConfig(**cfg_kwargs)

    def test_realm_rejects_boolean_generation(self) -> None:
        from control_plane.executive_service import ServiceConfig
        cfg_kwargs = self._realm_config_kwargs()
        cfg_kwargs["subscription_canary_realm_binding_id"] = ALIBABA_BINDING
        cfg_kwargs["subscription_canary_realm_generation"] = True
        cfg_kwargs["subscription_canary_realm_config_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "generation is invalid"):
            ServiceConfig(**cfg_kwargs)

    def test_realm_rejects_mismatched_provider(self) -> None:
        from control_plane.executive_service import ServiceConfig
        cfg_kwargs = self._realm_config_kwargs()
        cfg_kwargs["subscription_canary_realm_binding_id"] = ALIBABA_BINDING
        cfg_kwargs["subscription_canary_realm_generation"] = 1
        cfg_kwargs["subscription_canary_realm_config_sha256"] = "0" * 64
        cfg_kwargs["provider"] = "wrong-provider"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            ServiceConfig(**cfg_kwargs)

    def test_realm_rejects_mismatched_model_and_uppercase_sha(self) -> None:
        from control_plane.executive_service import ServiceConfig

        cfg_kwargs = self._realm_config_kwargs()
        cfg_kwargs.update(
            subscription_canary_realm_binding_id=ALIBABA_BINDING,
            subscription_canary_realm_generation=1,
            subscription_canary_realm_config_sha256="a" * 64,
            model="not-the-reviewed-model",
        )
        with self.assertRaisesRegex(ValueError, "model disagrees"):
            ServiceConfig(**cfg_kwargs)
        cfg_kwargs = self._realm_config_kwargs()
        cfg_kwargs.update(
            subscription_canary_realm_binding_id=ALIBABA_BINDING,
            subscription_canary_realm_generation=1,
            subscription_canary_realm_config_sha256="A" * 64,
        )
        with self.assertRaisesRegex(ValueError, "config_sha256 is invalid"):
            ServiceConfig(**cfg_kwargs)


# ---------------------------------------------------------------------------
# Gap 2 (Control): supervisor seam + ordinary composition does not call
# the observation owner.
# ---------------------------------------------------------------------------


class SupervisorClaimProviderTest(unittest.TestCase):
    def _runtime_mock(self) -> mock.MagicMock:
        runtime = mock.MagicMock()
        runtime.store.lease_seconds = 30
        return runtime

    def test_supervisor_enriches_spec_with_claim(self) -> None:
        from control_plane.executive_supervisor import ExecutiveSupervisor

        calls: list[tuple[str, str]] = []
        claim = _claim_dict()

        def claim_provider(attempt_id: str, binding_id: str) -> dict:
            calls.append((attempt_id, binding_id))
            return dict(claim)

        supervisor = ExecutiveSupervisor(
            self._runtime_mock(), mock.MagicMock(),
            subscription_canary_claim_provider=claim_provider,
            subscription_canary_binding_id="b",
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec = WorkerLaunchSpec(
                run_id="attempt-1",
                job_id="job-1",
                worker_id="codex-01",
                workspace_path=root / "workspace",
                run_dir=root / "run",
                prompt="bounded canary",
                result_schema_path=root / "run" / "result.schema.json",
                model="m",
            )
            enriched = supervisor._enrich_spec_with_canary_claim(
                spec, mock.MagicMock(),
            )
        # Claim provider was invoked exactly once with (attempt_id, binding_id).
        self.assertEqual(calls, [("attempt-1", "b")])
        self.assertIsInstance(enriched, WorkerLaunchSpec)
        self.assertEqual(
            enriched.subscription_canary_claim["binding_id"], "b",
        )
        self.assertEqual(
            enriched.subscription_canary_claim["schema"],
            "mastermind.subscription_canary_claim/v1",
        )

    def test_supervisor_passthrough_when_no_provider(self) -> None:
        from control_plane.executive_supervisor import ExecutiveSupervisor
        supervisor = ExecutiveSupervisor(self._runtime_mock(), mock.MagicMock())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec = WorkerLaunchSpec(
                run_id="attempt-2",
                job_id="job-2",
                worker_id="codex-01",
                workspace_path=root / "workspace",
                run_dir=root / "run",
                prompt="ordinary",
                result_schema_path=root / "run" / "result.schema.json",
            )
            enriched = supervisor._enrich_spec_with_canary_claim(
                spec, mock.MagicMock(),
            )
            # No provider means the same immutable object is returned untouched.
            self.assertIs(enriched, spec)

    def test_production_composition_injects_owner_only_for_realm(self) -> None:
        from control_plane.executive_runtime import Runtime
        from scripts import executive_os_phase1c as service_cli

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            raw = {
                "runtime_root": root / "runtime",
                "control_socket_path": root / "control.sock",
                "launchd_socket_name": "Operator",
                "worker_broker_socket_path": root / "worker.sock",
                "worker_runs_root": root / "runs",
                "receipts_root": root / "receipts",
                "proof_source_repository": root / "source",
                "proof_workspace_root": root / "workspaces",
                "proof_base_sha": "0" * 40,
                "backup_root": root / "backups",
                "shared_run_gid": os.getgid(),
                "worker_user": "fixture-worker",
                "worker_uid": os.getuid(),
                "worker_gid": os.getgid(),
                "allowed_peer_uids": [os.getuid()],
            }
            captured: dict[str, object] = {}

            def capture_service(config, **kwargs):
                captured["config"] = config
                captured["kwargs"] = kwargs
                return object()

            realm = {
                "binding_id": ALIBABA_BINDING,
                "generation": 7,
                "config_sha256": "a" * 64,
            }
            with mock.patch.object(
                service_cli, "ExecutiveControlService", capture_service,
            ), mock.patch.object(
                service_cli, "activate_launchd_socket", return_value=object(),
            ):
                service_cli._service_from_config(
                    {**raw, "subscription_canary_realm": realm}
                )
            config = captured["config"]
            self.assertEqual(config.provider, "alibaba")
            self.assertEqual(config.worker_type, "codex-cli")
            runtime = Runtime.at(root / "composition-runtime")
            supervisor = captured["kwargs"]["supervisor_factory"](runtime)
            self.assertTrue(callable(supervisor._subscription_canary_claim_provider))
            self.assertEqual(
                supervisor._subscription_canary_binding_id,
                ALIBABA_BINDING,
            )

            captured.clear()
            with mock.patch.object(
                service_cli, "ExecutiveControlService", capture_service,
            ), mock.patch.object(
                service_cli, "activate_launchd_socket", return_value=object(),
            ):
                service_cli._service_from_config(raw)
            ordinary = captured["kwargs"]["supervisor_factory"](runtime)
            self.assertIsNone(ordinary._subscription_canary_claim_provider)
            self.assertIsNone(ordinary._subscription_canary_binding_id)


# ---------------------------------------------------------------------------
# Gap 2 (Control/Installer): install.sh emission block + digest fence
# ---------------------------------------------------------------------------


def _extract_emission_block(install_text: str) -> str:
    """Return the inner Python script from the worker-config emission block.

    The block is delimited by a single ``<<'PY'`` heredoc marker and a
    closing ``PY`` line.
    """
    command_marker = (
        'PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BINARY" -I -S -B - '
        '"$WORKER_CONFIG"'
    )
    command = install_text.index(command_marker)
    start_marker = "<<'PY'\n"
    end_marker = "\nPY\n"
    start = install_text.index(start_marker, command) + len(start_marker)
    end = install_text.index(end_marker, start)
    return install_text[start:end]


class InstallerEmissionTest(unittest.TestCase):
    def test_install_source_includes_v5_emission_and_digest_fence(self) -> None:
        install = (_REPO_ROOT / "ops" / "executive_os" / "install.sh").read_text()
        # v5 emission path
        self.assertIn("executive_worker_broker_config/v5", install)
        self.assertIn("subscription_realm_enrollment", install)
        # v4 legacy path is still emitted when no realm is configured
        self.assertIn("executive_worker_broker_config/v4", install)
        # Digest fence on the v5 path
        self.assertIn("observed != expected", install)

    def test_install_bash_syntax_is_valid(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(_REPO_ROOT / "ops" / "executive_os" / "install.sh")],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(
            completed.returncode, 0,
            msg=completed.stderr or completed.stdout,
        )

    def test_v5_emit_then_digest_fence_matches_control_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            worker_path = tmp_path / "worker.json"
            ws = tmp_path / "ws"; ws.mkdir()
            runs = tmp_path / "runs"; runs.mkdir()
            home = tmp_path / "home"; home.mkdir()
            cb = tmp_path / "codex"; cb.touch()
            ar = tmp_path / "attestation.json"; ar.touch()
            control_path = tmp_path / "control.json"

            # Pre-compute the expected on-disk SHA-256 by serialising the
            # exact value the v5 emission block would write (sorted keys,
            # indent=2, trailing newline) so the digest fence accepts.
            pre_value = {
                "control_uid": 450,
                "worker_uid": os.getuid(),
                "worker_gid": os.getgid(),
                "allowed_supplementary_gids": [12, 61, 100],
                "worker_user": "_mastermind_worker",
                "worker_id": "codex-01",
                "workspace_root": str(ws),
                "run_root": str(runs),
                "provider_home": str(home),
                "codex_binary": str(cb),
                "codex_attestation_receipt": str(ar),
                "allowed_codex_versions": ["0.147.0"],
                "required_team_identifier": "2DC432GLL2",
                "launchd_socket_name": "WorkerBroker",
                "uid_sweep_receipt": str(home.parent / "state" / "uid-sweep.json"),
                "require_secret_canary": True,
                "operator_harness_armed": False,
                "schema_version": "mastermind.executive_worker_broker_config/v5",
                "harness_binding_id": ALIBABA_BINDING,
                "subscription_realm_enrollment": {
                    "binding_id": ALIBABA_BINDING,
                    "generation": 5,
                },
            }
            pre_bytes = (
                json.dumps(pre_value, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            realm_sha = hashlib.sha256(pre_bytes).hexdigest()

            control_payload = {
                "control_uid": 450,
                "subscription_canary_realm": {
                    "binding_id": ALIBABA_BINDING,
                    "generation": 5,
                    "config_sha256": realm_sha,
                },
                "coo_operator_harness_armed": False,
            }
            control_path.write_text(json.dumps(control_payload), encoding="utf-8")

            argv = [
                "ignored.py",
                str(worker_path),
                "450", str(os.getuid()), str(os.getgid()),
                "12 61 100",
                str(ws), str(runs), str(home),
                str(cb), "0.147.0",
                str(ar), str(control_path),
            ]
            install_text = (
                _REPO_ROOT / "ops" / "executive_os" / "install.sh"
            ).read_text()
            block = _extract_emission_block(install_text)
            with mock.patch.object(sys, "argv", list(argv)):
                exec(
                    compile(block, "<install-emit>", "exec"),
                    {"__name__": "__main__"},
                )

            observed = json.loads(worker_path.read_text(encoding="utf-8"))
            self.assertEqual(
                observed["schema_version"],
                "mastermind.executive_worker_broker_config/v5",
            )
            self.assertEqual(observed["harness_binding_id"], ALIBABA_BINDING)
            self.assertEqual(
                observed["subscription_realm_enrollment"],
                {"binding_id": ALIBABA_BINDING, "generation": 5},
            )

    def test_v4_emit_unchanged_when_no_realm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            worker_path = tmp_path / "worker.json"
            ws = tmp_path / "ws"; ws.mkdir()
            runs = tmp_path / "runs"; runs.mkdir()
            home = tmp_path / "home"; home.mkdir()
            cb = tmp_path / "codex"; cb.touch()
            ar = tmp_path / "attestation.json"; ar.touch()
            control_path = tmp_path / "control.json"
            control_path.write_text(
                json.dumps({"control_uid": 450}), encoding="utf-8",
            )

            argv = [
                "ignored.py",
                str(worker_path),
                "450", str(os.getuid()), str(os.getgid()),
                "12 61 100",
                str(ws), str(runs), str(home),
                str(cb), "0.147.0",
                str(ar), str(control_path),
            ]
            install_text = (
                _REPO_ROOT / "ops" / "executive_os" / "install.sh"
            ).read_text()
            block = _extract_emission_block(install_text)
            with mock.patch.object(sys, "argv", list(argv)):
                exec(
                    compile(block, "<install-emit>", "exec"),
                    {"__name__": "__main__"},
                )

            observed = json.loads(worker_path.read_text(encoding="utf-8"))
            self.assertEqual(
                observed["schema_version"],
                "mastermind.executive_worker_broker_config/v4",
            )
            self.assertNotIn("harness_binding_id", observed)
            self.assertNotIn("subscription_realm_enrollment", observed)


if __name__ == "__main__":
    unittest.main()
