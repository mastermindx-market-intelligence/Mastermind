"""Hermetic, adversarial tests for the incumbent-owner Fabric visibility join."""
from __future__ import annotations

import copy
import unittest

from control_plane.workspace_fabric_authorized import (
    FabricScopeDenied, FabricSourceUnavailable, WorkspaceFabricAuthorizedStatus,
    selection,
)

ROOT = "fabric-root-01"
RUN = "fabric-run-01"
WORK = "WS:MMOS_FABRIC"
STAMP = "a" * 64
REVISION = "b" * 64
FRAME = {
    "policy_id": "policy", "issuer_digest": "c" * 64, "subject_digest": "d" * 64,
    "client_ref": "e" * 64, "resource": "https://mcp.mastermind-x.com/workspace/read",
    "scopes": ["mastermind.workspace.read"],
}


def binding():
    return {
        "schema": "mastermind.executive_fabric_attempt_binding.v1",
        "work_ref": WORK, "root_job_id": "JOB-1", "job_id": "JOB-2",
        "attempt_id": "ATT-" + "1" * 32,
        "fabric_root_id": ROOT, "fabric_run_id": RUN,
        "effective_grant_digest": "f" * 64,
        "authority_generation_digest": "1" * 64, "current": True,
    }


def grant():
    return {
        "schema": "mastermind.agentos_fabric_visibility.v1", "work_ref": WORK,
        "principal_binding_digest": STAMP, "permission_revision": REVISION,
        "enabled": True, "actions": ["fabric_status"],
    }


def status():
    return {
        "schema": "mastermind.fabric_task_status.v1", "run_id": RUN,
        "root_id": ROOT, "parent_run_id": ROOT,
        "state": "TERMINAL", "rc": 0, "signal": "ok", "result_available": True,
        "result_bytes": 3672, "accepted": False, "accepted_by": "none",
        "acceptance_state": "NOT_ACCEPTED", "acceptance_reason": "not_accepted",
        "prompt": "PRIVATE WORKER PROMPT THAT MUST NEVER RETURN",
        "controller_output": "private log", "credentials": "private",
    }


class Fixture:
    def __init__(self):
        self.ex = binding()
        self.gr = grant()
        self.st = status()
        self.calls = []
        self.effect = None

    def executive(self, root, run):
        self.calls.append(("executive", root, run))
        return copy.deepcopy(self.ex)

    def agent(self, principal, work):
        self.calls.append(("agent", principal["client_ref"], work))
        return copy.deepcopy(self.gr)

    async def m2(self, root, run):
        self.calls.append(("m2", root, run))
        if self.effect:
            self.effect(self)
        return copy.deepcopy(self.st)

    def owner(self):
        return WorkspaceFabricAuthorizedStatus(
            executive_binding=self.executive,
            agent_permission=self.agent,
            status_reader=self.m2,
        )

    async def read(self):
        return await self.owner().read(
            principal_frame=FRAME, principal_stamp=STAMP,
            root_id=ROOT, run_id=RUN,
        )


class AuthorizedFabricStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_run_passes_twice_checked_owner_and_strips_untrusted_source(self):
        f = Fixture()
        result = await f.read()
        self.assertEqual(result["run_id"], RUN)
        self.assertEqual(result["accepted"], False)
        self.assertNotIn("prompt", result)
        self.assertNotIn("credentials", result)
        self.assertNotIn("controller_output", result)
        self.assertEqual(
            [call[0] for call in f.calls],
            ["executive", "agent", "m2", "executive", "agent"],
        )

    async def test_principal_binding_mismatch_denies_before_machine_read(self):
        f = Fixture()
        f.gr["principal_binding_digest"] = "e" * 64
        with self.assertRaises(FabricScopeDenied):
            await f.read()
        self.assertFalse(any(call[0] == "m2" for call in f.calls))

    async def test_disabled_or_missing_grant_denies_before_machine_read(self):
        for invalid in (None, {"enabled": False}, {"permissions": ["all"]}):
            with self.subTest(invalid=invalid):
                f = Fixture()
                f.gr = invalid
                with self.assertRaises(FabricScopeDenied):
                    await f.read()
                self.assertFalse(any(call[0] == "m2" for call in f.calls))

    async def test_wrong_scope_workstream_and_run_refuse(self):
        for key, bad in [
            ("work_ref", "WS:OTHER_WORKSTREAM"),
            ("fabric_run_id", "other-run"),
            ("fabric_root_id", "other-root"),
            ("current", False),
            ("attempt_id", "ATT-2"),
            ("effective_grant_digest", "unverified"),
        ]:
            with self.subTest(key=key):
                f = Fixture()
                f.ex[key] = bad
                with self.assertRaises(FabricScopeDenied):
                    await f.read()
                self.assertFalse(any(call[0] == "m2" for call in f.calls))

    async def test_revocation_during_await_blocks_returned_data(self):
        f = Fixture()
        f.effect = lambda fixture: fixture.gr.update(enabled=False)
        with self.assertRaises(FabricScopeDenied):
            await f.read()
        self.assertEqual([c[0] for c in f.calls].count("m2"), 1)

    async def test_revision_rotation_during_await_blocks_returned_data(self):
        f = Fixture()
        f.effect = lambda fixture: fixture.gr.update(permission_revision="3" * 64)
        with self.assertRaises(FabricScopeDenied):
            await f.read()

    async def test_exec_assignment_change_during_await_blocks_returned_data(self):
        f = Fixture()
        f.effect = lambda fixture: fixture.ex.update(attempt_id="ATT-" + "4" * 32)
        with self.assertRaises(FabricScopeDenied):
            await f.read()

    async def test_runtime_authority_rotation_during_await_blocks_returned_data(self):
        f = Fixture()
        f.effect = lambda fixture: fixture.ex.update(authority_generation_digest="5" * 64)
        with self.assertRaises(FabricScopeDenied):
            await f.read()

    async def test_return_source_must_match_exact_original_identity(self):
        for key, wrong in [
            ("root_id", "other-root"), ("run_id", "other-run"),
            ("accepted", True), ("result_available", "no"),
            ("result_bytes", -1), ("state", "RUNNING"),
        ]:
            with self.subTest(key=key):
                f = Fixture()
                f.st[key] = wrong
                with self.assertRaises(FabricSourceUnavailable):
                    await f.read()

    async def test_missing_root_and_machine_status_fail_closed(self):
        f = Fixture()
        f.st["root_id"] = None
        with self.assertRaises(FabricSourceUnavailable):
            await f.read()
        f = Fixture()
        async def unavailable(root, run):
            raise TimeoutError()
        owner = WorkspaceFabricAuthorizedStatus(
            executive_binding=f.executive, agent_permission=f.agent,
            status_reader=unavailable,
        )
        with self.assertRaises(FabricSourceUnavailable):
            await owner.read(principal_frame=FRAME, principal_stamp=STAMP,
                             root_id=ROOT, run_id=RUN)

    async def test_bad_principal_stamp_or_selection_denies(self):
        f = Fixture()
        for stamp in (None, "a", "0" * 63, True):
            with self.subTest(stamp=stamp), self.assertRaises(FabricScopeDenied):
                await f.owner().read(principal_frame=FRAME,
                                      principal_stamp=stamp, root_id=ROOT, run_id=RUN)
        for root, run in (("../etc", RUN), (ROOT, ""), (ROOT, "x" * 129)):
            with self.subTest(root=root, run=run), self.assertRaises(ValueError):
                await f.owner().read(principal_frame=FRAME,
                                      principal_stamp=STAMP, root_id=root, run_id=run)

    def test_no_untrusted_writer_or_catalog_constructor(self):
        with self.assertRaises(ValueError):
            WorkspaceFabricAuthorizedStatus(
                executive_binding=lambda *_: {}, agent_permission=lambda *_: {},
                status_reader=lambda *_: {},
            )
        with self.assertRaises(ValueError):
            selection("root", "bad/run")


if __name__ == "__main__":
    unittest.main()
