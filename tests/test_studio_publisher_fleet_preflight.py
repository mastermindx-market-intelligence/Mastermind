"""Hermetic regressions for the read-only installed Studio publisher census."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / "scripts/studio_publisher_fleet_preflight.py"
spec = importlib.util.spec_from_file_location("studio_publisher_fleet_preflight", MODULE)
audit_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit_module
spec.loader.exec_module(audit_module)


class FleetPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.account = "chatgpt3"
        self.base = self.root / self.account
        self.base.mkdir()
        self.secret = "DO-NOT-SERIALIZE-SENSITIVE-VALUE"
        self.config = {
            "accountLabel": self.account,
            "gitPublish": {"enabled": True, "credential": self.secret},
            "repositoryWorkspaces": {
                "enabled": True,
                "allowedRepositories": ["mastermind", "macro", "terminal"],
            },
        }
        self.manifest = {"account": self.account, "secret": self.secret}
        self.write_json("config.json", self.config)
        self.write_json("manifest.json", self.manifest)
        (self.base / "gateway.mjs").write_bytes(b"valid gateway fixture")
        (self.base / "git-publish.mjs").write_bytes(b"publisher fixture")
        (self.base / "workspace-access.mjs").write_bytes(b"workspace fixture")

    def write_json(self, name, value):
        (self.base / name).write_text(json.dumps(value))

    def test_qualified_closed_profile_never_claims_live_action_schema(self):
        gateway_hash = hashlib.sha256(b"valid gateway fixture").hexdigest()
        publisher_hash = hashlib.sha256(b"publisher fixture").hexdigest()
        workspace_hash = hashlib.sha256(b"workspace fixture").hexdigest()
        with mock.patch.object(audit_module, "REPOSITORY_GATEWAY", gateway_hash), \
             mock.patch.dict(audit_module.PUBLISHER_GENERATIONS, {publisher_hash: "MERGE_CAPABLE"}), \
             mock.patch.object(audit_module, "WORKSPACE_GENERATIONS", frozenset((workspace_hash,))):
            result = audit_module.audit(self.root, self.account)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(result["repository_schema_expected"], "YES")
        self.assertEqual(result["merge_schema_expected"], "YES")
        self.assertEqual(result["live_client_schema"], "NOT_OBSERVED")
        self.assertEqual(result["installation_proof"], "NOT_OBSERVED")
        self.assertNotIn(self.secret, json.dumps(result))
        self.assertNotIn(self.temp.name, json.dumps(result))

    def test_legacy_profile_has_no_foreign_repository_permission(self):
        self.config.pop("repositoryWorkspaces")
        self.write_json("config.json", self.config)
        result = audit_module.audit(self.root, self.account)
        self.assertEqual(result["configured_repositories"], ["mastermind"])
        self.assertEqual(result["repository_schema_expected"], "NO")

    def test_native_pin_observation_uses_existing_state_owner_location(self):
        pin = self.base / "state/native-pool-pin"
        pin.parent.mkdir()
        pin.mkdir()
        self.assertTrue(audit_module.audit(self.root, self.account)["native_pin_owner_required"])

    def test_unapproved_alias_fails_closed_without_credential_leak(self):
        self.config["repositoryWorkspaces"]["allowedRepositories"].append("executive-dr-vault")
        self.write_json("config.json", self.config)
        result = audit_module.audit(self.root, self.account)
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["reason"], "WORKSPACE_CONFIGURATION_INVALID")
        self.assertNotIn(self.secret, json.dumps(result))

    def test_duplicate_alias_fails_closed(self):
        self.config["repositoryWorkspaces"]["allowedRepositories"].append("macro")
        self.write_json("config.json", self.config)
        self.assertEqual(audit_module.audit(self.root, self.account)["status"], "REFUSED")

    def test_manifest_identity_mismatch_fails_closed(self):
        self.manifest["account"] = "chatgpt1"
        self.write_json("manifest.json", self.manifest)
        self.assertEqual(audit_module.audit(self.root, self.account)["reason"], "MANIFEST_IDENTITY_MISMATCH")

    def test_symlinked_config_refuses_without_reading_target(self):
        (self.base / "config.json").unlink()
        secret_target = self.root / "do-not-read"
        secret_target.write_text(self.secret)
        (self.base / "config.json").symlink_to(secret_target)
        result = audit_module.audit(self.root, self.account)
        self.assertEqual(result["status"], "REFUSED")
        self.assertNotIn(self.secret, json.dumps(result))

    def test_oversized_manifest_refuses_without_outputting_contents(self):
        (self.base / "manifest.json").write_bytes(b"x" * 2_000_001)
        result = audit_module.audit(self.root, self.account)
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["reason"], "FILE_UNSAFE")

    def test_scan_has_no_positive_release_or_app_proof(self):
        result = audit_module.scan(self.root, (self.account,))
        self.assertEqual(result["effect_state"], "NOT_APPLIED")
        self.assertFalse(result["live_app_catalog_proven"])
        self.assertEqual(len(result["accounts"]), 1)

    def test_unlisted_account_is_not_a_filesystem_selector(self):
        with self.assertRaisesRegex(ValueError, "ACCOUNT_NOT_ALLOWLISTED"):
            audit_module.audit(self.root, "../other")


if __name__ == "__main__":
    unittest.main()
