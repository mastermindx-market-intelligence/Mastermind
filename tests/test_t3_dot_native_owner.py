import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from integrations.session_bridge.t3_dot_native_owner import (
    NativeDotFleetOwner, BoundedNativeRunner, read_profile, validate_profile,
)
from integrations.session_bridge.t3_dot_tools import T3DotTools, TOOLS
from integrations.session_bridge.t3_native_client import Rejected, Conflict, Unavailable
from integrations.session_bridge.t3_web_client import CliInvocation, CliResult
from test_t3_native_client import SCHEMAS, schema, Native


def run(value):
    return asyncio.run(value)


def profile():
    return {"schema": "mastermind.t3_dot_native_profile.v1", "principal_key": "p:tunnel:account-a",
            "connection_id": "existing-native-connection", "native_command": ["/qualified/t3"],
            "t3_home": "/owner/.t3", "local_environment_id": "native-env-1",
            "environments": [{"environment_id": "native-env-1", "project_ids": ["project-1", "project-2"]},
                             {"environment_id": "remote-env", "project_ids": ["remote-project"]}],
            "operations": [row["name"] for row in TOOLS], "delete_thread_ids": [], "timeout_seconds": 30}


class Runner:
    def __init__(self):
        self.calls = []
        self.native = Native()
        self.root = "native-env-1"
        self.remote = "remote-env"
        self.catalog = {**SCHEMAS, "t3_environment_read": schema("environmentId"),
                        "t3_project_list": schema("environmentId")}
        self.projects = [{"projectId": "project-1", "name": "One"}, {"projectId": "project-2", "name": "Two"},
                         {"projectId": "private-project", "name": "Not allowed"}]
        self.links = [{"environmentId": "remote-env", "status": "reachable", "access": "full-access",
                       "urls": ["https://private-route.example"], "expiresAt": "2026-12-01T00:00:00Z"}]
        self.fail = None

    async def __call__(self, invocation):
        self.calls.append(invocation)
        if self.fail:
            raise self.fail
        argv = list(invocation.argv)
        if "native-catalog" in argv:
            body = {"tools": [{"name": name, "inputSchema": value} for name, value in self.catalog.items()]}
        elif "environment" in argv:
            body = self.links
        else:
            name = argv[argv.index("native") + 1]
            args = json.loads(invocation.stdin)
            if name == "t3_environment_read":
                body = {"structuredContent": {"environmentId": self.root if not args else self.remote,
                                               "label": "Native", "serverVersion": "0.1.7"}, "isError": False}
            elif name == "t3_project_list":
                body = {"structuredContent": {"projects": self.projects}, "isError": False}
            else:
                body = await self.native(name, args)
        return CliResult(0, json.dumps(body), "")


class NativeOwnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = Runner()
        self.profile = profile()
        self.owner = NativeDotFleetOwner(self.profile, runner=self.runner)
        self.tools = T3DotTools(self.owner)

    def call(self, tool, args, principal="p:tunnel:account-a"):
        return run(self.tools.call(principal, tool, args))

    def test_profile_closed_and_no_wildcard(self):
        for change in ({"token": "bad"}, {"native_command": ["sh", "-c", "x"]},
                       {"principal_key": "somebody"}, {"timeout_seconds": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_profile({**profile(), **change})
        value = profile(); value["environments"][0]["project_ids"] = ["*"]
        with self.assertRaises(ValueError): validate_profile(value)

    def test_private_account_mismatch_before_runner(self):
        value = self.call("t3_fleet_environments", {}, principal="p:tunnel:account-b")
        self.assertEqual(value["status"], "REJECTED")
        self.assertFalse(self.runner.calls)

    def test_current_profile_revoked_before_runner(self):
        self.owner.current_profile = lambda: {**profile(), "timeout_seconds": 31}
        self.assertEqual(self.call("t3_fleet_environments", {})["status"], "REJECTED")
        self.assertFalse(self.runner.calls)

    def test_scoped_operations_and_projects(self):
        self.owner.profile["operations"].remove("t3_thread_launch")
        value = self.call("t3_thread_read", {"environment_id": "native-env-1", "project_id": "private-project", "thread_id": "thread-1"})
        self.assertEqual(value["status"], "REJECTED")
        self.assertFalse(self.runner.calls)

    def test_environment_inventory_native_owner_no_urls(self):
        value = self.call("t3_fleet_environments", {})
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual([row["environment_id"] for row in value["data"]["environments"]], ["native-env-1", "remote-env"])
        self.assertNotIn("private-route", json.dumps(value))
        self.assertEqual(value["data"]["execution_admission"], "NOT_OBSERVED")

    def test_missing_native_link_is_not_ready(self):
        self.runner.links = []
        value = self.call("t3_fleet_environments", {})
        self.assertEqual(value["data"]["environments"][1]["status"], "not_linked")

    def test_foreign_native_environment_rejected(self):
        self.runner.root = "another-host"
        value = self.call("t3_fleet_environments", {})
        self.assertEqual(value["status"], "UNAVAILABLE")
        self.assertFalse(any("environment" in call.argv for call in self.runner.calls))

    def test_project_catalog_filtered_and_locally_paginated(self):
        value = self.call("t3_fleet_projects", {"environment_id": "native-env-1", "limit": 1})
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual(value["data"]["projects"], [{"projectId": "project-1", "name": "One"}])
        self.assertEqual(value["data"]["next_cursor"], 1)
        value = self.call("t3_fleet_projects", {"environment_id": "native-env-1", "limit": 1, "cursor": 1})
        self.assertEqual(value["data"]["projects"], [{"projectId": "project-2", "name": "Two"}])
        self.assertIsNone(value["data"]["next_cursor"])

    def test_remote_scope_preserves_local_connection_guard(self):
        value = self.call("t3_capacity_models", {"environment_id": "remote-env", "project_id": "remote-project"})
        self.assertEqual(value["status"], "OBSERVED")
        last = self.runner.calls[-1]
        self.assertIn("--expected-environment-id", last.argv)
        self.assertEqual(last.argv[-1], "native-env-1")
        self.assertEqual(json.loads(last.stdin)["environmentId"], "remote-env")

    def test_remote_environment_cannot_be_substituted(self):
        self.runner.remote = "foreign-env"
        value = self.call("t3_capacity_models", {"environment_id": "remote-env", "project_id": "remote-project"})
        self.assertEqual(value["status"], "CONFLICT")
        self.assertFalse(self.runner.native.calls)

    def test_remote_without_native_routing_never_falls_back_local(self):
        self.runner.catalog["t3_environment_read"] = schema()
        value = self.call("t3_capacity_models", {"environment_id": "remote-env", "project_id": "remote-project"})
        self.assertEqual(value["status"], "UNAVAILABLE")
        self.assertFalse(self.runner.native.calls)

    def test_delete_profile_requires_explicit_target(self):
        args = {"environment_id": "native-env-1", "project_id": "project-1", "thread_id": "thread-1",
                "operation_id": "delete-1", "snapshot": {"sequence": 1, "title": "T", "updated_at": "now",
                "provider_id": "capacity_fabric", "model": "x", "archived": False, "deleted": False},
                "confirmed_title": "T", "confirm_delete": True}
        self.assertEqual(self.call("t3_thread_delete", args)["status"], "REJECTED")
        self.assertFalse(self.runner.calls)

    def test_native_read_failure_no_fallback(self):
        self.runner.fail = OSError("private credentials must not leak")
        value = self.call("t3_fleet_environments", {})
        self.assertEqual(value["status"], "UNAVAILABLE")
        self.assertNotIn("credentials", json.dumps(value))
        self.assertEqual(len(self.runner.calls), 1)

    def test_profile_file_hash_custody_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            raw = json.dumps(profile()).encode()
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(read_profile(str(path), digest), profile())
            path.write_bytes(raw + b" ")
            with self.assertRaises(Conflict): read_profile(str(path), digest)
            path.write_bytes(raw)
            path.chmod(0o666)
            with self.assertRaises(ValueError): read_profile(str(path), digest)
            path.chmod(0o600)
            alias = Path(temp) / "alias.json"
            alias.symlink_to(path)
            with self.assertRaises(OSError): read_profile(str(alias), digest)
            bad = b'{"schema":"x","schema":"y"}'
            path.write_bytes(bad)
            with self.assertRaises(ValueError): read_profile(str(path), hashlib.sha256(bad).hexdigest())

    def test_runner_refuses_non_native_command_before_spawn(self):
        runner = BoundedNativeRunner(profile())
        for args in (("/bin/sh", "-c", "touch /tmp/no"), ("/qualified/t3", "auth", "pairing", "create")):
            with self.assertRaises(Rejected):
                run(runner(CliInvocation(args, None)))
            self.assertIsNone(runner.last_effect)


if __name__ == "__main__":
    unittest.main()
