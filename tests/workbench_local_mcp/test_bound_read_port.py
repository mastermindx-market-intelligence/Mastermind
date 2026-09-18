from __future__ import annotations

import concurrent.futures
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from common import bounded_sync_executor as executor_module
from integrations.workbench_local_mcp import adapter
from integrations.workbench_local_mcp.adapter import create_bound_read_port
from integrations.workbench_local_mcp.schemas import (
    PROFILE_PRO_READ_PREPARE,
    LocalProfileError,
)
from integrations.workbench_read_mcp.observer import ReadRefusal, ReadScope


NOW_MS = 1_800_000_000_000


class BoundReadPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.source = self.root / "README.md"
        self.source.write_text("# Bound read\nvalue = 1\n", encoding="utf-8")
        self.root_fd = os.open(
            self.root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        current = os.fstat(self.root_fd)
        self.scope = ReadScope(
            root_fd=self.root_fd,
            root_device=current.st_dev,
            root_inode=current.st_ino,
            context_ref="context:action-runtime",
            owner_ref="owner:action-runtime",
            generation="generation:action-runtime-1",
            allowed_paths=("README.md",),
            expires_at_ms=NOW_MS + 60_000,
            committed_head="b" * 40,
        )
        self.revoked = False
        self.resolve_calls = 0

        def resolve_scope() -> ReadScope:
            self.resolve_calls += 1
            if self.revoked:
                raise ReadRefusal("SCOPE_UNAVAILABLE")
            return self.scope

        self.resolve_scope = resolve_scope
        self.port = self._create_port()

    def tearDown(self) -> None:
        self.port.close()
        os.close(self.root_fd)
        self.tmp.cleanup()

    def _create_port(self):
        return create_bound_read_port(
            "action-project",
            PROFILE_PRO_READ_PREPARE,
            ("README.md",),
            self.resolve_scope,
            lambda: NOW_MS,
        )

    @staticmethod
    def _error_code(result: dict) -> str | None:
        error = result.get("error")
        return error.get("code") if isinstance(error, dict) else None

    def test_real_borrowed_read_and_preimage_preview_use_protected_observer(self) -> None:
        before = self.source.read_bytes()
        preimage = hashlib.sha256(before).hexdigest()

        read = self.port.call(
            "read_project_file", {"relative_path": "README.md"}
        )
        self.assertTrue(read["ok"])
        self.assertEqual(read["data"]["content"], before.decode("utf-8"))
        self.assertEqual(read["data"]["file_sha256"], preimage)
        self.assertEqual(read["data"]["context_ref"], self.scope.context_ref)

        preview = self.port.call(
            "preview_text_replace",
            {
                "relative_path": "README.md",
                "expected_sha256": preimage,
                "old_text": "value = 1",
                "new_text": "value = 2",
            },
        )
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["data"]["status"], "PREVIEW_ONLY")
        self.assertIn("+value = 2", preview["data"]["diff"])
        self.assertFalse(preview["data"]["applied"])
        self.assertFalse(preview["data"]["persisted"])
        self.assertEqual(self.source.read_bytes(), before)

    def test_manifest_uses_current_scope_without_caching_live_authority(self) -> None:
        first = self.port.call("workspace_manifest", {})
        self.assertTrue(first["ok"])
        self.assertEqual(first["data"]["context_ref"], self.scope.context_ref)
        self.assertEqual(first["data"]["owner_ref"], self.scope.owner_ref)
        self.assertEqual(first["data"]["generation"], self.scope.generation)
        self.assertEqual(first["data"]["lease_expires_at_ms"], self.scope.expires_at_ms)
        self.assertEqual(first["data"]["committed_head"], self.scope.committed_head)

        self.scope = dataclasses.replace(
            self.scope,
            context_ref="context:action-runtime-2",
            owner_ref="owner:action-runtime-2",
            generation="generation:action-runtime-2",
            expires_at_ms=NOW_MS + 30_000,
            committed_head=None,
        )
        second = self.port.call("workspace_manifest", {})
        self.assertTrue(second["ok"])
        self.assertEqual(second["data"]["context_ref"], "context:action-runtime-2")
        self.assertEqual(second["data"]["owner_ref"], "owner:action-runtime-2")
        self.assertEqual(second["data"]["generation"], "generation:action-runtime-2")
        self.assertEqual(second["data"]["lease_expires_at_ms"], NOW_MS + 30_000)
        self.assertIsNone(second["data"]["committed_head"])

    def test_every_read_tool_refuses_revoked_expired_and_drifted_scope(self) -> None:
        preimage = hashlib.sha256(self.source.read_bytes()).hexdigest()
        calls = (
            ("workspace_manifest", {}),
            ("read_project_file", {"relative_path": "README.md"}),
            (
                "preview_text_replace",
                {
                    "relative_path": "README.md",
                    "expected_sha256": preimage,
                    "old_text": "value = 1",
                    "new_text": "value = 2",
                },
            ),
            ("preview_project_command", {"recipe": "git_diff_check"}),
        )

        self.revoked = True
        for name, arguments in calls:
            with self.subTest(state="revoked", tool=name):
                result = self.port.call(name, arguments)
                self.assertFalse(result["ok"])
                self.assertEqual(self._error_code(result), "PROJECT_READ_REFUSED")

        self.revoked = False
        original = self.scope
        self.scope = dataclasses.replace(original, expires_at_ms=NOW_MS)
        for name, arguments in calls:
            with self.subTest(state="expired", tool=name):
                result = self.port.call(name, arguments)
                self.assertFalse(result["ok"])
                self.assertEqual(self._error_code(result), "PROJECT_READ_REFUSED")

        self.scope = dataclasses.replace(original, root_inode=original.root_inode + 1)
        for name, arguments in calls:
            with self.subTest(state="source_drift", tool=name):
                result = self.port.call(name, arguments)
                self.assertFalse(result["ok"])
                self.assertEqual(self._error_code(result), "SOURCE_CHANGED")

    def test_bound_close_revokes_port_without_closing_borrowed_descriptor(self) -> None:
        before = os.fstat(self.root_fd)
        self.port.close()
        after = os.fstat(self.root_fd)
        self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))
        refused = self.port.call("workspace_manifest", {})
        self.assertFalse(refused["ok"])
        self.assertEqual(self._error_code(refused), "PROJECT_READ_REFUSED")

    def test_cleanup_uncertainty_is_sticky_and_forwarded_once(self) -> None:
        callbacks: list[str] = []
        port = create_bound_read_port(
            "action-project",
            PROFILE_PRO_READ_PREPARE,
            ("README.md",),
            self.resolve_scope,
            lambda: NOW_MS,
            on_cleanup_uncertain=lambda: callbacks.append("persisted"),
        )
        original_close = os.close
        close_attempts: list[int] = []

        def close_first_then_fail(descriptor: int) -> None:
            close_attempts.append(descriptor)
            original_close(descriptor)
            if len(close_attempts) == 1:
                raise OSError("PRIVATE_CLOSE_DETAIL")

        with mock.patch.object(
            adapter.os, "close", side_effect=close_first_then_fail
        ):
            first = port.call(
                "read_project_file", {"relative_path": "README.md"}
            )
        self.assertFalse(first["ok"])
        self.assertEqual(self._error_code(first), "PROJECT_CLEANUP_UNCERTAIN")
        self.assertEqual(callbacks, ["persisted"])
        attempts_after_read = list(close_attempts)

        for name, arguments in (
            ("workspace_manifest", {}),
            ("preview_project_command", {"recipe": "git_diff_check"}),
            ("read_project_file", {"relative_path": "README.md"}),
        ):
            with self.subTest(tool=name):
                refused = port.call(name, arguments)
                self.assertFalse(refused["ok"])
                self.assertEqual(
                    self._error_code(refused), "PROJECT_CLEANUP_UNCERTAIN"
                )
        self.assertEqual(callbacks, ["persisted"])
        self.assertEqual(close_attempts, attempts_after_read)
        with self.assertRaisesRegex(
            LocalProfileError, "^PROJECT_CLEANUP_UNCERTAIN$"
        ):
            port.close()
        os.fstat(self.root_fd)

    def test_simultaneous_cleanup_failures_forward_one_callback_and_error(self) -> None:
        callbacks: list[str] = []
        port = create_bound_read_port(
            "action-project",
            PROFILE_PRO_READ_PREPARE,
            ("README.md",),
            self.resolve_scope,
            lambda: NOW_MS,
            on_cleanup_uncertain=lambda: callbacks.append("persisted"),
        )
        failures_entered = threading.Barrier(2)
        first_constructor_entered = threading.Event()
        release_first_constructor = threading.Event()
        actual_error = LocalProfileError

        class ControlledLocalProfileError(actual_error):
            def __new__(cls, code: str):
                if code == "PROJECT_CLEANUP_UNCERTAIN":
                    if not first_constructor_entered.is_set():
                        first_constructor_entered.set()
                        release_first_constructor.wait(0.2)
                    else:
                        release_first_constructor.set()
                return super().__new__(cls)

        def simultaneous_observer_failure(
            _selected,
            _scope,
            *,
            clock_ms,
            on_cleanup_uncertain,
        ):
            self.assertTrue(callable(clock_ms))
            failures_entered.wait(timeout=2.0)
            on_cleanup_uncertain()
            raise ReadRefusal("CLEANUP_UNCERTAIN")

        with (
            mock.patch.object(
                adapter, "LocalProfileError", ControlledLocalProfileError
            ),
            mock.patch.object(
                adapter, "observe_file", side_effect=simultaneous_observer_failure
            ),
            concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool,
        ):
            futures = [
                pool.submit(
                    port.call,
                    "read_project_file",
                    {"relative_path": "README.md"},
                )
                for _ in range(2)
            ]
            results = [future.result(timeout=3.0) for future in futures]

        self.assertEqual(callbacks, ["persisted"])
        for result in results:
            self.assertFalse(result["ok"])
            self.assertEqual(
                self._error_code(result), "PROJECT_CLEANUP_UNCERTAIN"
            )
        sticky = []
        for _ in range(2):
            with self.assertRaises(LocalProfileError) as caught:
                port._scope()
            sticky.append(caught.exception)
        self.assertIs(sticky[0], sticky[1])
        os.fstat(self.root_fd)

    def test_tool_arguments_cannot_supply_scope_profile_caller_or_root(self) -> None:
        attempts = (
            ("workspace_manifest", {"profile": "other"}),
            (
                "read_project_file",
                {"relative_path": "README.md", "root_fd": self.root_fd},
            ),
            (
                "preview_project_command",
                {"recipe": "git_diff_check", "caller": "other"},
            ),
        )
        for name, arguments in attempts:
            with self.subTest(tool=name):
                result = self.port.call(name, arguments)
                self.assertFalse(result["ok"])
                self.assertEqual(self._error_code(result), "INVALID_REQUEST")

    def test_bind_manifest_and_command_preview_create_no_physical_owner(self) -> None:
        constructor = mock.Mock(side_effect=AssertionError("executor constructed"))
        with (
            mock.patch.object(
                adapter.os, "open", side_effect=AssertionError("descriptor opened")
            ),
            mock.patch.object(
                adapter.os, "close", side_effect=AssertionError("descriptor closed")
            ),
            mock.patch.object(
                adapter.os, "dup", side_effect=AssertionError("descriptor duplicated")
            ),
            mock.patch.object(executor_module, "BoundedSyncExecutor", constructor),
        ):
            port = self._create_port()
            manifest = port.call("workspace_manifest", {})
            command = port.call(
                "preview_project_command", {"recipe": "git_diff_check"}
            )
            port.close()
        self.assertTrue(manifest["ok"])
        self.assertTrue(command["ok"])
        self.assertEqual(command["data"]["argv"], ["git", "diff", "--check"])
        constructor.assert_not_called()
        os.fstat(self.root_fd)

    def test_factory_rejects_profile_path_and_callback_authority_widening(self) -> None:
        mutations = (
            ("wrong", ("README.md",), self.resolve_scope, lambda: NOW_MS),
            (
                PROFILE_PRO_READ_PREPARE,
                ("../outside",),
                self.resolve_scope,
                lambda: NOW_MS,
            ),
            (PROFILE_PRO_READ_PREPARE, ("README.md",), None, lambda: NOW_MS),
        )
        for profile, paths, resolver, clock in mutations:
            with self.subTest(profile=profile, paths=paths):
                with self.assertRaisesRegex(
                    LocalProfileError, "CONFIGURATION_REFUSED"
                ):
                    create_bound_read_port(
                        "action-project",
                        profile,
                        paths,
                        resolver,
                        clock,
                    )

        widened = create_bound_read_port(
            "action-project",
            PROFILE_PRO_READ_PREPARE,
            ("README.md", "other.txt"),
            self.resolve_scope,
            lambda: NOW_MS,
        )
        result = widened.call("workspace_manifest", {})
        self.assertFalse(result["ok"])
        self.assertEqual(self._error_code(result), "PROJECT_READ_REFUSED")
        widened.close()


if __name__ == "__main__":
    unittest.main()
