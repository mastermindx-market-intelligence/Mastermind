from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from control_plane.codex_provider_realm import (
    ALIBABA_TOKEN_PLAN,
    PROVIDER_CREDENTIAL_FILENAME,
    ProviderRealmError,
    load_private_provider_credential,
)
from scripts.executive_os_phase1c_worker import (
    CONFIG_SCHEMA_VERSION,
    SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
    WorkerConfigError,
    _assert_service_activation_allowed,
    _load_config,
    _resolve_subscription_binding,
    _resolve_subscription_realm,
)


ALIBABA_BINDING = "alibaba-token-plan-personal.codex-responses"


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


class SubscriptionWorkerConfigTest(unittest.TestCase):
    def test_existing_v4_config_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = _config(root, schema=CONFIG_SCHEMA_VERSION)
            loaded = _load_config(
                _write_config(root, value), require_root_owner=False
            )
            self.assertEqual(loaded["schema_version"], CONFIG_SCHEMA_VERSION)
            self.assertNotIn("harness_binding_id", loaded)

    def test_v5_resolves_only_reviewed_codex_subscription_binding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = _config(
                root,
                schema=SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
                binding_id=ALIBABA_BINDING,
            )
            loaded = _load_config(
                _write_config(root, value), require_root_owner=False
            )
            binding = _resolve_subscription_binding(loaded["harness_binding_id"])
            realm = _resolve_subscription_realm(binding)
            self.assertEqual(realm, ALIBABA_TOKEN_PLAN)
            with self.assertRaisesRegex(
                WorkerConfigError, "not armed for autonomous service"
            ):
                _assert_service_activation_allowed(loaded)

    def test_v5_rejects_spec_only_or_wrong_harness(self) -> None:
        for binding_id in (
            "minimax-token-plan.openai-compatible",
            "alibaba-token-plan-personal.claude-code-anthropic",
        ):
            with self.subTest(binding_id=binding_id):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    value = _config(
                        root,
                        schema=SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
                        binding_id=binding_id,
                    )
                    with self.assertRaises(WorkerConfigError):
                        _load_config(
                            _write_config(root, value), require_root_owner=False
                        )

    def test_v5_rejects_operator_harness_arming(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = _config(
                root,
                schema=SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
                binding_id=ALIBABA_BINDING,
            )
            value["operator_harness_armed"] = True
            with self.assertRaisesRegex(
                WorkerConfigError, "cannot arm the operator harness"
            ):
                _load_config(
                    _write_config(root, value), require_root_owner=False
                )

    def test_provider_credential_uses_existing_private_provider_home(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "provider-home"
            home.mkdir(mode=0o700)
            credential = home / PROVIDER_CREDENTIAL_FILENAME
            credential.write_text("opaque-subscription-key", encoding="utf-8")
            os.chown(credential, os.getuid(), os.getgid())
            credential.chmod(0o600)
            self.assertEqual(
                load_private_provider_credential(
                    home, expected_uid=os.getuid(), expected_gid=os.getgid()
                ),
                "opaque-subscription-key",
            )

    def test_provider_credential_rejects_unsafe_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "provider-home"
            home.mkdir(mode=0o700)
            credential = home / PROVIDER_CREDENTIAL_FILENAME
            credential.write_text("opaque-subscription-key", encoding="utf-8")
            os.chown(credential, os.getuid(), os.getgid())
            credential.chmod(0o644)
            with self.assertRaisesRegex(
                ProviderRealmError, "provider credential is unavailable"
            ):
                load_private_provider_credential(
                    home, expected_uid=os.getuid(), expected_gid=os.getgid()
                )

            credential.unlink()
            target = home / "elsewhere"
            target.write_text("opaque-subscription-key", encoding="utf-8")
            os.chown(target, os.getuid(), os.getgid())
            target.chmod(0o600)
            credential.symlink_to(target)
            with self.assertRaises(ProviderRealmError):
                load_private_provider_credential(
                    home, expected_uid=os.getuid(), expected_gid=os.getgid()
                )


if __name__ == "__main__":
    unittest.main()
