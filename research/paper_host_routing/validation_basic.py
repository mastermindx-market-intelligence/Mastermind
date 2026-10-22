"""Synthetic host-routing proof. No Paper app, credential or real SSH is used."""
import asyncio
from contextlib import asynccontextmanager
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent

def module():
    spec = importlib.util.spec_from_file_location("paper_host_routes_test", ROOT / "host_routes.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

LOCAL = "host-" + "a" * 64
REMOTE = "host-" + "b" * 64

def binding(host=REMOTE):
    return {"schema": "mastermind.paper_execution_binding.v1", "host_ref": host,
            "service_ref": "c" * 64, "runtime_revision": "d" * 40,
            "bridge_sha256": "e" * 64}

def policy():
    return {"schema": "mastermind.paper_host_routes.v1", "routes": [{
        "host_ref": REMOTE, "label": "Fixture secondary", "execution_binding": binding(),
        "tool_schema_sha256": "f" * 64,
        "ssh": {"hostname": "100.100.1.2", "username": "fixture", "port": 22,
                "identity_file": "/fixture/id_ed25519", "known_hosts_file": "/fixture/known_hosts",
                "known_hosts_sha256": "1" * 64,
                "python_path": "/fixture/python", "runtime_root": "/fixture/runtime"}}]}

class RoutingPolicyTests(unittest.TestCase):
    def setUp(self): self.m = module()

    def test_valid_projection_is_defensively_copied(self):
        value = policy()
        got = self.m.validate_routes(value, LOCAL)
        value["routes"][0]["ssh"]["hostname"] = "100.100.1.3"
        self.assertEqual(got["routes"][0]["ssh"]["hostname"], "100.100.1.2")

    def test_unknown_configuration_keys_refuse(self):
        value = policy(); value["command"] = "arbitrary"
        with self.assertRaises(self.m.RouteError): self.m.validate_routes(value, LOCAL)

    def test_public_hosts_and_shell_destinations_refuse(self):
        for host in ["example.com", "8.8.8.8", "127.0.0.1", "host;echo bad", "-oProxyCommand=x"]:
            with self.subTest(host=host):
                value = policy(); value["routes"][0]["ssh"]["hostname"] = host
                with self.assertRaises(self.m.RouteError): self.m.validate_routes(value, LOCAL)

    def test_duplicate_or_local_host_refuses(self):
        value = policy(); value["routes"].append(copy.deepcopy(value["routes"][0]))
        with self.assertRaises(self.m.RouteError): self.m.validate_routes(value, LOCAL)
        value = policy(); value["routes"][0]["host_ref"] = LOCAL
        value["routes"][0]["execution_binding"]["host_ref"] = LOCAL
        with self.assertRaises(self.m.RouteError): self.m.validate_routes(value, LOCAL)

    def test_backend_binding_must_match_route(self):
        value = policy(); value["routes"][0]["execution_binding"]["host_ref"] = LOCAL
        with self.assertRaises(self.m.RouteError): self.m.validate_routes(value, LOCAL)

    def test_ssh_argv_disables_ambient_config_forwarding_and_prompts(self):
        argv = self.m.ssh_command(policy()["routes"][0], verify_files=False)
        self.assertEqual(argv[:4], ["/usr/bin/ssh", "-T", "-F", "/dev/null"])
        for item in ["BatchMode=yes", "StrictHostKeyChecking=yes", "IdentityAgent=none",
                     "ForwardAgent=no", "ClearAllForwardings=yes", "ConnectionAttempts=1"]:
            self.assertIn(item, argv)
        self.assertNotIn("-L", argv); self.assertNotIn("-R", argv)
        self.assertIn("serve", argv[-1]); self.assertIn("--host-ref", argv[-1])

    def test_paths_cannot_inject_remote_commands(self):
        for field in ["python_path", "runtime_root", "identity_file", "known_hosts_file"]:
            value = policy(); value["routes"][0]["ssh"][field] = "/tmp/a;touch /tmp/b"
            with self.subTest(field=field), self.assertRaises(self.m.RouteError):
                self.m.validate_routes(value, LOCAL)

if __name__ == "__main__": unittest.main()
