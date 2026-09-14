from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from integrations.workbench_local_mcp import schemas as profile_schemas
from integrations.workbench_local_mcp.adapter import LocalWorkbenchGateway
from integrations.workbench_local_mcp.schemas import (
    CONFIG_SCHEMA,
    PROFILE_PRO_READ_PREPARE,
    LocalProfileError,
    TOOL_SPECS,
    load_config,
    parse_config,
    schema_snapshot,
    schema_snapshot_sha256,
)


class LocalWorkbenchProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.file = self.project / "README.md"
        self.file.write_text("# Mastermind\nvalue = 1\n", encoding="utf-8")
        nested = self.project / "tests"
        nested.mkdir()
        (nested / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        self.payload = {
            "schema": CONFIG_SCHEMA,
            "profile": PROFILE_PRO_READ_PREPARE,
            "project_ref": "mastermind",
            "project_root": str(self.project),
            "allowed_paths": ["README.md", "tests/test_demo.py"],
            "committed_head": "a" * 40,
            "lease_expires_at_ms": int(time.time() * 1000) + 60000,
        }
        self.config = parse_config(self.payload)
        self.gateway = LocalWorkbenchGateway.open(self.config)

    def tearDown(self) -> None:
        try:
            self.gateway.close()
        finally:
            self.tmp.cleanup()

    def call(self, name: str, arguments: dict | None = None) -> dict:
        return self.gateway.call(name, arguments or {})

    def test_surface_is_uniformly_read_only(self) -> None:
        snapshot = schema_snapshot()
        self.assertFalse(snapshot["mutation_allowed"])
        self.assertEqual(schema_snapshot_sha256(), hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest())
        self.assertEqual(
            [spec.name for spec in TOOL_SPECS],
            ["workspace_manifest", "read_project_file", "preview_text_replace", "preview_project_command"],
        )
        for spec in TOOL_SPECS:
            self.assertTrue(spec.annotations["readOnlyHint"])
            self.assertFalse(spec.annotations["destructiveHint"])
            self.assertTrue(spec.annotations["idempotentHint"])
            self.assertFalse(spec.annotations["openWorldHint"])

    def test_manifest_exposes_no_private_root_and_no_effects(self) -> None:
        result = self.call("workspace_manifest")
        self.assertTrue(result["ok"])
        text = json.dumps(result)
        self.assertNotIn(str(self.project), text)
        self.assertFalse(result["mutation_allowed"])
        self.assertEqual(
            result["data"]["effects"],
            {"file_write": False, "process_start": False, "network_call": False, "durable_prepare": False},
        )

    def test_read_uses_fixed_allowed_project(self) -> None:
        result = self.call("read_project_file", {"relative_path": "README.md"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["project_ref"], "mastermind")
        self.assertEqual(result["data"]["content"], "# Mastermind\nvalue = 1\n")
        self.assertNotIn(str(self.project), json.dumps(result))
        refused = self.call("read_project_file", {"relative_path": "secrets.env"})
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"]["code"], "PROJECT_READ_REFUSED")

    def test_preview_replace_does_not_modify_file(self) -> None:
        before = self.file.read_bytes()
        preimage = hashlib.sha256(before).hexdigest()
        result = self.call(
            "preview_text_replace",
            {
                "relative_path": "README.md",
                "expected_sha256": preimage,
                "old_text": "value = 1",
                "new_text": "value = 2",
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["status"], "PREVIEW_ONLY")
        self.assertFalse(result["data"]["applied"])
        self.assertFalse(result["data"]["persisted"])
        self.assertIn("+value = 2", result["data"]["diff"])
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(hashlib.sha256(self.file.read_bytes()).hexdigest(), preimage)

    def test_preview_requires_current_preimage(self) -> None:
        result = self.call(
            "preview_text_replace",
            {
                "relative_path": "README.md",
                "expected_sha256": "0" * 64,
                "old_text": "value = 1",
                "new_text": "value = 2",
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "PREIMAGE_MISMATCH")

    def test_preview_requires_unique_exact_old_text(self) -> None:
        self.file.write_text("x\nx\n", encoding="utf-8")
        preimage = hashlib.sha256(self.file.read_bytes()).hexdigest()
        result = self.call(
            "preview_text_replace",
            {
                "relative_path": "README.md",
                "expected_sha256": preimage,
                "old_text": "x",
                "new_text": "y",
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "PREVIEW_NOT_APPLICABLE")
        self.assertEqual(self.file.read_text(encoding="utf-8"), "x\nx\n")

    def test_command_preview_never_starts_process(self) -> None:
        result = self.call(
            "preview_project_command",
            {"recipe": "pytest_targets", "targets": ["tests/test_demo.py"]},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["data"]["argv"],
            ["python3", "-m", "pytest", "-q", "tests/test_demo.py"],
        )
        self.assertFalse(result["data"]["started"])
        self.assertIsNone(result["data"]["process_ref"])

    def test_command_preview_refuses_arbitrary_shell_and_paths(self) -> None:
        for request in (
            {"recipe": "bash", "targets": ["rm -rf /"]},
            {"recipe": "pytest_targets", "targets": ["../test.py"]},
            {"recipe": "pytest_targets", "targets": ["scripts/tool.py"]},
            {"recipe": "git_diff_check", "targets": ["README.md"]},
        ):
            result = self.call("preview_project_command", request)
            self.assertFalse(result["ok"], request)
            self.assertEqual(result["error"]["code"], "INVALID_REQUEST")

    def test_unknown_or_extra_tool_input_refuses(self) -> None:
        private_name = "private-" + "x" * 4096
        result = self.call(private_name, {"command": "whoami"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "TOOL_NOT_AVAILABLE")
        self.assertEqual(result["tool"], "unknown")
        self.assertNotIn(private_name, json.dumps(result))
        result = self.call("read_project_file", {"relative_path": "README.md", "root": "/"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")

    def test_config_is_closed_and_excludes_git_metadata(self) -> None:
        for mutation in (
            {**self.payload, "extra": True},
            {**self.payload, "profile": "business_full"},
            {**self.payload, "project_root": "relative"},
            {**self.payload, "allowed_paths": [".git/config"]},
            {**self.payload, "allowed_paths": ["../outside"]},
            {**self.payload, "committed_head": "A" * 40},
        ):
            with self.assertRaises(LocalProfileError):
                parse_config(mutation)

    def test_config_loader_refuses_symlink_and_writable_config(self) -> None:
        config_path = self.root / "profile.json"
        config_path.write_text(json.dumps(self.payload), encoding="utf-8")
        loaded = load_config(str(config_path))
        self.assertEqual(loaded.project_ref, "mastermind")
        link = self.root / "profile-link.json"
        link.symlink_to(config_path)
        with self.assertRaises(LocalProfileError):
            load_config(str(link))
        config_path.chmod(0o666)
        with self.assertRaises(LocalProfileError):
            load_config(str(config_path))

    def test_config_loader_uses_required_nonblocking_and_nofollow_flags(self) -> None:
        config_path = self.root / "profile-flags.json"
        config_path.write_text(json.dumps(self.payload), encoding="utf-8")
        original_open = profile_schemas.os.open
        observed: list[int] = []

        def observe_open(path, flags, *args, **kwargs):
            observed.append(flags)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(profile_schemas.os, "open", side_effect=observe_open):
            self.assertEqual(load_config(str(config_path)).project_ref, "mastermind")
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0] & profile_schemas.os.O_NONBLOCK)
        self.assertTrue(observed[0] & profile_schemas.os.O_NOFOLLOW)
        self.assertTrue(observed[0] & profile_schemas.os.O_CLOEXEC)

    def test_config_loader_requires_every_platform_safety_flag(self) -> None:
        config_path = self.root / "profile-required-flags.json"
        config_path.write_text(json.dumps(self.payload), encoding="utf-8")
        for flag_name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
            with self.subTest(flag_name=flag_name):
                with mock.patch.object(profile_schemas.os, flag_name, 0):
                    with self.assertRaisesRegex(
                        LocalProfileError, "^CONFIGURATION_REFUSED$"
                    ):
                        load_config(str(config_path))

    def test_config_loader_fifo_swap_cannot_block_or_pass(self) -> None:
        config_path = self.root / "profile-fifo.json"
        config_path.write_text(json.dumps(self.payload), encoding="utf-8")
        original_open = profile_schemas.os.open

        def replace_with_fifo(path, flags, *args, **kwargs):
            config_path.unlink()
            os.mkfifo(config_path)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(
            profile_schemas.os, "open", side_effect=replace_with_fifo
        ):
            with self.assertRaisesRegex(
                LocalProfileError, "^CONFIGURATION_REFUSED$"
            ):
                load_config(str(config_path))

    def test_config_loader_refuses_initial_and_opened_hardlinks(self) -> None:
        initial = self.root / "profile-initial-link.json"
        initial.write_text(json.dumps(self.payload), encoding="utf-8")
        initial_link = self.root / "profile-initial-link-copy.json"
        os.link(initial, initial_link)
        with self.assertRaisesRegex(LocalProfileError, "^CONFIGURATION_REFUSED$"):
            load_config(str(initial))

        opened = self.root / "profile-opened-link.json"
        opened.write_text(json.dumps(self.payload), encoding="utf-8")
        opened_link = self.root / "profile-opened-link-copy.json"
        original_open = profile_schemas.os.open

        def add_link_before_open(path, flags, *args, **kwargs):
            os.link(opened, opened_link)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(
            profile_schemas.os, "open", side_effect=add_link_before_open
        ):
            with self.assertRaisesRegex(
                LocalProfileError, "^CONFIGURATION_REFUSED$"
            ):
                load_config(str(opened))

    def test_config_loader_refuses_final_identity_and_link_changes(self) -> None:
        identity = self.root / "profile-identity.json"
        identity.write_text(json.dumps(self.payload), encoding="utf-8")
        replacement = self.root / "profile-replacement.json"
        replacement.write_text(json.dumps(self.payload), encoding="utf-8")
        original_close = profile_schemas.os.close

        def close_then_replace(descriptor):
            original_close(descriptor)
            os.replace(replacement, identity)

        with mock.patch.object(
            profile_schemas.os, "close", side_effect=close_then_replace
        ):
            with self.assertRaisesRegex(
                LocalProfileError, "^CONFIGURATION_REFUSED$"
            ):
                load_config(str(identity))

        linked = self.root / "profile-final-link.json"
        linked.write_text(json.dumps(self.payload), encoding="utf-8")
        final_link = self.root / "profile-final-link-copy.json"

        def close_then_link(descriptor):
            original_close(descriptor)
            os.link(linked, final_link)

        with mock.patch.object(
            profile_schemas.os, "close", side_effect=close_then_link
        ):
            with self.assertRaisesRegex(
                LocalProfileError, "^CONFIGURATION_REFUSED$"
            ):
                load_config(str(linked))

    def test_config_loader_preserves_close_uncertainty_over_read_refusal(self) -> None:
        config_path = self.root / "profile-close-uncertain.json"
        config_path.write_text(json.dumps(self.payload), encoding="utf-8")
        original_close = profile_schemas.os.close

        def close_then_fail(descriptor):
            original_close(descriptor)
            raise OSError("simulated close uncertainty")

        with (
            mock.patch.object(
                profile_schemas.os,
                "read",
                side_effect=LocalProfileError("CONFIGURATION_REFUSED"),
            ),
            mock.patch.object(
                profile_schemas.os, "close", side_effect=close_then_fail
            ),
        ):
            with self.assertRaises(LocalProfileError) as caught:
                load_config(str(config_path))
        self.assertEqual(caught.exception.code, "CONFIGURATION_CLEANUP_UNCERTAIN")

    def test_config_loader_refuses_same_inode_rewrite_after_read(self) -> None:
        config_path = self.root / "profile-same-inode-rewrite.json"
        original_bytes = json.dumps(self.payload).encode("utf-8")
        replacement_bytes = original_bytes.replace(b"mastermind", b"mastermimd", 1)
        self.assertEqual(len(replacement_bytes), len(original_bytes))
        config_path.write_bytes(original_bytes)
        before = config_path.stat()
        writer = os.open(config_path, os.O_WRONLY)
        original_read = profile_schemas.os.read
        rewritten = False

        def read_then_rewrite(descriptor: int, count: int) -> bytes:
            nonlocal rewritten
            chunk = original_read(descriptor, count)
            if chunk and not rewritten:
                time.sleep(0.01)
                os.pwrite(writer, replacement_bytes, 0)
                os.fsync(writer)
                os.utime(
                    config_path,
                    ns=(before.st_atime_ns, before.st_mtime_ns),
                )
                rewritten = True
            return chunk

        try:
            with mock.patch.object(
                profile_schemas.os, "read", side_effect=read_then_rewrite
            ):
                with self.assertRaisesRegex(
                    LocalProfileError, "^CONFIGURATION_REFUSED$"
                ):
                    load_config(str(config_path))
        finally:
            os.close(writer)
        after = config_path.stat()
        self.assertTrue(rewritten)
        self.assertEqual(after.st_ino, before.st_ino)
        self.assertEqual(after.st_size, before.st_size)
        self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
        self.assertNotEqual(after.st_ctime_ns, before.st_ctime_ns)

    def test_gateway_close_uncertainty_is_sticky_without_descriptor_retry(self) -> None:
        other = LocalWorkbenchGateway.open(self.config)
        descriptor = other._project.fd
        close_attempts: list[int] = []

        def fail_without_closing(selected: int) -> None:
            close_attempts.append(selected)
            raise OSError("simulated ambiguous close")

        try:
            with mock.patch.object(
                profile_schemas.os, "close", side_effect=fail_without_closing
            ):
                with self.assertRaises(LocalProfileError) as first:
                    other.close()
                with self.assertRaises(LocalProfileError) as repeated:
                    other.close()
            self.assertEqual(first.exception.code, "PROJECT_CLEANUP_UNCERTAIN")
            self.assertIs(repeated.exception, first.exception)
            self.assertEqual(close_attempts, [descriptor])
            os.fstat(descriptor)
            with self.assertRaisesRegex(
                LocalProfileError, "^PROJECT_CLEANUP_UNCERTAIN$"
            ):
                other._scope()
        finally:
            os.close(descriptor)

    def test_gateway_close_uncertainty_remains_sticky_when_fd_was_closed(self) -> None:
        other = LocalWorkbenchGateway.open(self.config)
        descriptor = other._project.fd
        original_close = profile_schemas.os.close
        close_attempts: list[int] = []

        def close_then_fail(selected: int) -> None:
            close_attempts.append(selected)
            original_close(selected)
            raise OSError("simulated lost close acknowledgement")

        with mock.patch.object(
            profile_schemas.os, "close", side_effect=close_then_fail
        ):
            with self.assertRaises(LocalProfileError) as first:
                other.close()
            with self.assertRaises(LocalProfileError) as repeated:
                other.close()
        self.assertEqual(first.exception.code, "PROJECT_CLEANUP_UNCERTAIN")
        self.assertIs(repeated.exception, first.exception)
        self.assertEqual(close_attempts, [descriptor])
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_read_cleanup_uncertainty_still_closes_owned_root_once(self) -> None:
        other = LocalWorkbenchGateway.open(self.config)
        descriptor = other._project.fd
        original_close = os.close
        close_attempts: list[int] = []

        def close_first_then_fail(selected: int) -> None:
            close_attempts.append(selected)
            original_close(selected)
            if len(close_attempts) == 1:
                raise OSError("PRIVATE_CLOSE_DETAIL")

        try:
            with mock.patch.object(
                profile_schemas.os, "close", side_effect=close_first_then_fail
            ):
                result = other.call(
                    "read_project_file", {"relative_path": "README.md"}
                )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["error"]["code"], "PROJECT_CLEANUP_UNCERTAIN"
                )
                os.fstat(descriptor)
                with self.assertRaises(LocalProfileError) as first_close:
                    other.close()
                with self.assertRaises(LocalProfileError) as repeated_close:
                    other.close()
            self.assertEqual(first_close.exception.code, "PROJECT_CLEANUP_UNCERTAIN")
            self.assertIs(repeated_close.exception, first_close.exception)
            self.assertEqual(close_attempts.count(descriptor), 1)
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        finally:
            try:
                os.fstat(descriptor)
            except OSError:
                pass
            else:
                original_close(descriptor)

    def test_expired_profile_fails_closed(self) -> None:
        expired = parse_config({**self.payload, "lease_expires_at_ms": int(time.time() * 1000) - 1})
        other = LocalWorkbenchGateway.open(expired)
        try:
            result = other.call("workspace_manifest", {})
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "PROJECT_READ_REFUSED")
        finally:
            other.close()

    def test_no_project_write_or_process_modules_in_adapter(self) -> None:
        source = Path("integrations/workbench_local_mcp/adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.write", source)
        self.assertNotIn("os.replace", source)
        self.assertNotIn("os.rename", source)
        self.assertNotIn("os.unlink", source)
        self.assertNotIn("os.remove", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("from socket", source)


if __name__ == "__main__":
    unittest.main()
