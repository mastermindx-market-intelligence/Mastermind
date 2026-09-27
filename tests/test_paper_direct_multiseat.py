"""Multi-seat transport tests. No real tunnel, credential, or Paper mutation is used."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest import mock

from paper_direct_test_support import PrivatePython

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "integrations/paper_desktop/direct_service.py"
BRIDGE = ROOT / "integrations/paper_desktop/bridge.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MultiSeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._python_fixture = PrivatePython()
        cls.private_python = cls._python_fixture.python

    @classmethod
    def tearDownClass(cls):
        cls._python_fixture.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.binary = self.home / "tunnel-client"
        self.binary.write_text("#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o700)
        self.svc = load("paper_direct_multiseat_service", SERVICE)
        self.bridge = load("paper_direct_multiseat_bridge", BRIDGE)

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, seat_id):
        root = self.home / seat_id
        value = self.svc.stage(
            root,
            python=self.private_python,
            tunnel_client=self.binary,
            source_revision="a" * 40,
            allow_prepare=True,
            allow_write=True,
            seat_id=seat_id,
        )
        return root, value

    def test_stage_v3_manifest_and_launchd_are_seat_specific(self):
        root, value = self.stage("c1")
        self.assertEqual(value["schema"], "mastermind.paper_direct_install.v3")
        self.assertEqual(value["seat_id"], "c1")
        label = "com.mastermind.paper-direct.business.c1"
        plist_path = root / f"service/{label}.plist"
        self.assertTrue(plist_path.exists())
        plist = plistlib.loads(plist_path.read_bytes())
        self.assertEqual(plist["Label"], label)
        self.assertIn("launch", plist["ProgramArguments"])
        self.assertEqual(self.svc.verify(root)["seat_id"], "c1")

    def test_invalid_seat_id_refuses_before_install(self):
        for value in ("", "C1", "../c1", "c1/other", "c1 space", "a" * 49):
            with self.subTest(value=value):
                target = self.home / ("candidate-" + str(len(value)))
                with self.assertRaisesRegex(self.svc.Refusal, "SEAT_ID_REQUIRED"):
                    self.svc.stage(
                        target,
                        python=self.private_python,
                        tunnel_client=self.binary,
                        source_revision="a" * 40,
                        seat_id=value,
                    )
                self.assertFalse(target.exists())

    def test_distinct_seats_have_distinct_transport_singletons(self):
        _, c1 = self.stage("c1")
        _, c2 = self.stage("c2")
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            owner1 = self.svc.service_owner(c1)
            owner2 = self.svc.service_owner(c2)
            self.assertNotEqual(owner1, owner2)
            with self.svc.service_lock(owner1):
                with self.svc.service_lock(owner2):
                    with self.assertRaisesRegex(self.svc.Refusal, "ALREADY_RUNNING"):
                        with self.svc.service_lock(owner1):
                            self.fail("same seat acquired duplicate transport lock")

    def test_binding_uses_existing_tunnel_without_fabricated_workspace_id(self):
        root, _ = self.stage("c3")
        tunnel = "tunnel_" + "b" * 32
        value = self.svc.bind(root, tunnel, None)
        self.assertEqual(value["schema"], "mastermind.paper_direct_binding.v2")
        self.assertEqual(value["seat_id"], "c3")
        self.assertEqual(value["tunnel_id"], tunnel)
        self.assertIsNone(value["workspace_id"])
        self.assertFalse(value["workspace_access_verified"])
        self.assertEqual(self.svc.verify_binding(root)["tunnel_id"], tunnel)

    def test_v3_binding_can_pin_exact_openai_organization(self):
        root, _ = self.stage("c1")
        tunnel = "tunnel_" + "b" * 32
        org = "org-2KfBEPZB4fcssTJfl9q9PVmM"
        value = self.svc.bind(root, tunnel, None, org)
        self.assertEqual(value["organization_id"], org)
        profile = (root / "connection/profile.yaml").read_text()
        self.assertIn(f'organization_id: "{org}"', profile)
        self.assertEqual(self.svc.verify_binding(root)["organization_id"], org)

    def test_v3_binding_without_org_keeps_c2_shape(self):
        root, _ = self.stage("c2")
        tunnel = "tunnel_" + "b" * 32
        value = self.svc.bind(root, tunnel, None)
        self.assertIsNone(value["organization_id"])
        self.assertNotIn("organization_id:", (root / "connection/profile.yaml").read_text())

    def test_invalid_org_refuses_before_binding_write(self):
        root, _ = self.stage("c4")
        tunnel = "tunnel_" + "b" * 32
        for value in ("", "../org", "org bad", "org:\nattack", "x" * 200):
            with self.subTest(value=value):
                with self.assertRaisesRegex(self.svc.Refusal, "ORGANIZATION_ID_REQUIRED"):
                    self.svc.bind(root, tunnel, None, value)
                self.assertFalse((root / "connection").exists())

    def test_legacy_v2_bundle_still_requires_workspace_id_and_global_owner(self):
        root = self.home / "legacy"
        value = self.svc.stage(
            root,
            python=self.private_python,
            tunnel_client=self.binary,
            source_revision="a" * 40,
            allow_write=True,
        )
        self.assertEqual(value["schema"], "mastermind.paper_direct_install.v2")
        with self.assertRaisesRegex(self.svc.Refusal, "WORKSPACE_ID_REQUIRED"):
            self.svc.bind(root, "tunnel_" + "b" * 32, None)
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            self.assertEqual(
                self.svc.service_owner(value),
                self.home / ".local/state/mastermind-paper/direct-business",
            )

    def test_paper_desktop_mutex_remains_shared_across_seats(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            expected = self.home / ".local/state/mastermind-paper"
            self.assertEqual(self.bridge.state_root(), expected)
            _, c1 = self.stage("c1")
            _, c4 = self.stage("c4")
            self.assertNotEqual(self.svc.service_owner(c1), self.svc.service_owner(c4))
            self.assertEqual(self.bridge.state_root(), expected)


if __name__ == "__main__":
    unittest.main()
