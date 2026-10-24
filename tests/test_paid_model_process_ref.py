"""Boundary tests for the closed paid model process identity contract.

The positive paths build evidence from the live Python/OS process so
the refusals prove real strictness rather than fixture luck.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import platform
import re
import sys
import subprocess
import unittest
from pathlib import Path
from types import MappingProxyType

from control_plane import worker_execution_contract as wec


def _process_start_identity() -> str:
    if sys.platform == "darwin":
        return "ps-lstart:" + subprocess.check_output(
            ["ps", "-p", str(os.getpid()), "-o", "lstart="], text=True,
        ).strip()
    stat_text = Path("/proc/self/stat").read_text()
    tail = stat_text[stat_text.rindex(")") + 1:].split()
    return f"starttime-{tail[19]}"


def _boot_session_id() -> str:
    if sys.platform == "darwin":
        return "kern.boottime:" + subprocess.check_output(
            ["sysctl", "-n", "kern.boottime"], text=True,
        ).strip()
    for line in Path("/proc/stat").read_text().splitlines():
        if line.startswith("btime"):
            return f"btime-{line.split()[1]}"
    raise AssertionError("actual boot observation unavailable")


def real_binary_attestation() -> wec.BinaryAttestation:
    executable = os.path.realpath(sys.executable)
    info = os.stat(executable)
    with open(executable, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return wec.BinaryAttestation(
        path=sys.executable,
        real_path=executable,
        version=platform.python_version(),
        sha256=digest,
        team_identifier=None,
        size=info.st_size,
        device=info.st_dev,
        inode=info.st_ino,
        mode=info.st_mode,
        uid=info.st_uid,
        gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )


def host_ref() -> str:
    node = os.uname().nodename.split(".")[0] or "localhost"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", node) is None:
        return "localhost"
    return node


def live_fields(**overrides) -> dict:
    run_id = f"run-{os.getpid()}-0000000000000000000000000000000"
    fields = {
        "run_id": run_id,
        "worker_id": "worker-1",
        "host_ref": host_ref(),
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "session_id": os.getsid(0),
        "process_start_identity": _process_start_identity(),
        "boot_session_id": _boot_session_id(),
        "launch_nonce": os.urandom(16).hex(),
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "effective_uid": os.geteuid(),
        "effective_gid": os.getegid(),
        "real_uid": os.getuid(),
        "real_gid": os.getgid(),
        "binary": real_binary_attestation(),
        "stdout_path": f"/tmp/{run_id}/stdout",
        "stderr_path": f"/tmp/{run_id}/stderr",
        "result_path": f"/tmp/{run_id}/result",
    }
    fields.update(overrides)
    return fields


def live_ref(**overrides) -> wec.PaidModelProcessRef:
    return wec.PaidModelProcessRef(**live_fields(**overrides))


def wire(ref: wec.PaidModelProcessRef) -> dict:
    return ref.to_dict()


class ClosedFieldsTest(unittest.TestCase):
    def test_field_order_and_schema_default_last(self) -> None:
        names = [field.name for field in dataclasses.fields(wec.PaidModelProcessRef)]
        self.assertEqual(
            names,
            [
                "run_id", "worker_id", "host_ref", "pid", "pgid", "session_id",
                "process_start_identity", "boot_session_id", "launch_nonce",
                "started_at", "effective_uid", "effective_gid", "real_uid",
                "real_gid", "binary", "stdout_path", "stderr_path",
                "result_path", "schema_version",
            ],
        )
        self.assertEqual(
            wec.PAID_MODEL_PROCESS_REF_SCHEMA,
            "mastermind.paid_model_process_ref/v1",
        )
        self.assertEqual(
            dataclasses.fields(wec.PaidModelProcessRef)[-1].default,
            wec.PAID_MODEL_PROCESS_REF_SCHEMA,
        )

    def test_error_is_secret_free_valueerror_subtype(self) -> None:
        self.assertTrue(issubclass(wec.PaidModelProcessRefError, ValueError))
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(pid=0)

    def test_non_utf8_or_oversized_byte_identity_is_refused(self) -> None:
        for value in ("\ud800", "界" * 200):
            with self.subTest(value_type="invalid UTF8 or byte length"):
                with self.assertRaises(wec.PaidModelProcessRefError):
                    live_ref(process_start_identity=value)
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(stdout_path="/tmp/" + "\ud800")

    def test_frozen(self) -> None:
        ref = live_ref()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.pid = 1  # type: ignore[misc]


class LiveRoundtripTest(unittest.TestCase):
    def test_roundtrip_is_canonical_and_json_safe(self) -> None:
        ref = live_ref()
        payload = wire(ref)
        self.assertEqual(payload["schema_version"], wec.PAID_MODEL_PROCESS_REF_SCHEMA)
        self.assertIsInstance(payload["binary"], dict)
        json.dumps(payload)
        restored = wec.PaidModelProcessRef.from_dict(json.loads(json.dumps(payload)))
        self.assertEqual(restored, ref)
        self.assertEqual(wire(restored), payload)
        self.assertEqual(wire(wec.PaidModelProcessRef.from_dict(payload)), payload)

    def test_to_dict_is_detached(self) -> None:
        ref = live_ref()
        payload = wire(ref)
        payload["pid"] = 1
        payload["binary"]["sha256"] = "0" * 64
        payload["binary"] = None
        self.assertEqual(ref.pid, os.getpid())
        self.assertEqual(wire(ref)["binary"]["sha256"], ref.binary.sha256)
        self.assertIsNotNone(wire(ref)["binary"])

    def test_from_dict_rejects_subclasses_and_custom_mappings(self) -> None:
        payload = wire(live_ref())

        class WireDict(dict):
            pass

        for suspect in (
            WireDict(payload),
            MappingProxyType(payload),
            tuple(payload.items()),
            None,
        ):
            with self.assertRaises(wec.PaidModelProcessRefError):
                wec.PaidModelProcessRef.from_dict(suspect)


class LegacyUnchangedTest(unittest.TestCase):
    def test_legacy_worker_process_ref_accepts_legacy_shape(self) -> None:
        self.assertEqual(
            [field.name for field in dataclasses.fields(wec.WorkerProcessRef)],
            [
                "run_id", "pid", "pgid", "process_start_identity",
                "boot_session_id", "launch_nonce", "provider_session_id",
                "stdout_path", "stderr_path", "result_path", "started_at",
                "binary", "base_sha", "session_id", "effective_uid",
                "effective_gid", "real_uid", "real_gid",
            ],
        )
        legacy = wec.WorkerProcessRef(
            run_id="run-1",
            pid=-5,
            pgid=0,
            process_start_identity="",
            boot_session_id="btime-0",
            launch_nonce="n",
            provider_session_id="provider-session",
            stdout_path="relative",
            stderr_path="relative",
            result_path="relative",
            started_at="not-a-time",
            binary=real_binary_attestation(),
            base_sha="c" * 64,
        )
        self.assertEqual(legacy.provider_session_id, "provider-session")
        self.assertEqual(legacy.base_sha, "c" * 64)

    def test_legacy_constants_and_export_surface(self) -> None:
        for name in (
            "WORKER_EXECUTION_CONTRACT_VERSION",
            "LAUNCH_ATTESTATION_SCHEMA_VERSION",
            "WORKER_RECOVERY_BINDING_VERSION",
            "WORKER_REMOTE_RECOVERY_BINDING_VERSION",
            "DURABLE_COLLECTION_CONTRACT_VERSION",
            "MAX_ARTIFACTS",
            "MAX_ARTIFACT_BYTES",
            "MAX_ARTIFACT_TOTAL_BYTES",
            "ArtifactReceipt",
            "BinaryAttestation",
            "CancelReceipt",
            "CollectionReceipt",
            "LaunchAttestation",
            "ProcessInspector",
            "ValidationReceipt",
            "WorkerLaunchSpec",
            "WorkerRecoveryBinding",
            "WorkerRecoveryContractError",
            "worker_launch_spec_sha256",
            "WorkerProcessRef",
            "WorkerResult",
            "WorkerRunStatus",
        ):
            self.assertIn(name, wec.__all__)
        self.assertEqual(
            wec.__all__[-3:],
            [
                "PAID_MODEL_PROCESS_REF_SCHEMA",
                "PaidModelProcessRef",
                "PaidModelProcessRefError",
            ],
        )

    def test_collection_receipt_typing_untouched(self) -> None:
        self.assertEqual(
            [field.name for field in dataclasses.fields(wec.CollectionReceipt)],
            ["process_ref", "result", "stdout_sha256", "stderr_sha256", "result_sha256"],
        )
        self.assertEqual(
            wec.CollectionReceipt.__dataclass_fields__["process_ref"].type,
            "WorkerProcessRef",
        )


class SchemaDiscriminatorTest(unittest.TestCase):
    def test_wrong_schema_versions_refuse(self) -> None:
        for bad in (
            "mastermind.worker_execution_contract/v1",
            "mastermind.paid_model_process_ref/v2",
            "mastermind.paid_model_process_ref",
            "paid_model_process_ref/v1",
            "",
            "mastermind.paid_model_process_ref/v1 ",
        ):
            with self.assertRaises(wec.PaidModelProcessRefError):
                live_ref(schema_version=bad)

    def test_missing_or_none_schema_refuses(self) -> None:
        with self.assertRaises(wec.PaidModelProcessRefError):
            wec.PaidModelProcessRef(**{
                key: value
                for key, value in live_fields().items()
                if key != "schema_version"
            } | {"schema_version": None})


class WireKeyClosureTest(unittest.TestCase):
    def test_legacy_and_mixed_keys_refuse(self) -> None:
        payload = wire(live_ref())
        for extra in (
            "provider_session_id",
            "base_sha",
            "home",
            "provider_home",
            "canary",
            "subscription_canary_claim",
            "secret",
            "expected_base_sha",
        ):
            poisoned = dict(payload)
            poisoned[extra] = None
            with self.assertRaises(wec.PaidModelProcessRefError):
                wec.PaidModelProcessRef.from_dict(poisoned)

    def test_legacy_v1_shape_refuses(self) -> None:
        legacy = {
            "run_id": "run-1",
            "pid": 1,
            "pgid": 1,
            "process_start_identity": "starttime-1",
            "boot_session_id": "btime-0",
            "launch_nonce": "nonce",
            "provider_session_id": None,
            "stdout_path": "/tmp/o",
            "stderr_path": "/tmp/e",
            "result_path": "/tmp/r",
            "started_at": "2026-01-01T00:00:00+00:00",
            "binary": dataclasses.asdict(real_binary_attestation()),
            "base_sha": "c" * 64,
            "session_id": 1,
            "effective_uid": 1,
            "effective_gid": 1,
            "real_uid": 1,
            "real_gid": 1,
        }
        with self.assertRaises(wec.PaidModelProcessRefError):
            wec.PaidModelProcessRef.from_dict(legacy)

    def test_missing_and_unknown_keys_refuse(self) -> None:
        payload = wire(live_ref())
        for key in payload:
            missing = {name: value for name, value in payload.items() if name != key}
            with self.assertRaises(wec.PaidModelProcessRefError):
                wec.PaidModelProcessRef.from_dict(missing)
        with self.assertRaises(wec.PaidModelProcessRefError):
            wec.PaidModelProcessRef.from_dict(dict(payload, unknown=1))
        with self.assertRaises(wec.PaidModelProcessRefError):
            wec.PaidModelProcessRef.from_dict({})

    def test_binary_wire_requires_exact_dict(self) -> None:
        payload = wire(live_ref())
        as_instance = dict(payload)
        as_instance["binary"] = live_ref().binary
        with self.assertRaises(wec.PaidModelProcessRefError):
            wec.PaidModelProcessRef.from_dict(as_instance)
        for mutation in (
            lambda binary: dict(binary, extra=1),
            lambda binary: {k: v for k, v in binary.items() if k != "mode"},
            lambda binary: dict(binary, sha256=binary["sha256"].upper()),
            lambda binary: dict(binary, size=-1),
            lambda binary: dict(binary, mode=True),
            lambda binary: dict(binary, path="relative/path"),
            lambda binary: dict(binary, real_path="/tmp//x"),
            lambda binary: dict(binary, version=""),
            lambda binary: dict(binary, team_identifier=""),
            lambda binary: dict(binary, uid=None),
            lambda binary: list(binary.values()),
        ):
            mutated = dict(payload)
            mutated["binary"] = mutation(dict(payload["binary"]))
            with self.assertRaises(wec.PaidModelProcessRefError):
                wec.PaidModelProcessRef.from_dict(mutated)

    def test_team_identifier_none_is_explicitly_allowed(self) -> None:
        ref = live_ref()
        self.assertIsNone(ref.binary.team_identifier)
        self.assertIsNone(wire(ref)["binary"]["team_identifier"])


class ScalarRefusalTest(unittest.TestCase):
    def test_bool_is_never_an_int(self) -> None:
        for field_name in ("pid", "pgid", "session_id", "effective_uid",
                           "effective_gid", "real_uid", "real_gid"):
            for value in (True, False):
                with self.assertRaises(wec.PaidModelProcessRefError):
                    live_ref(**{field_name: value})

    def test_no_type_coercion_from_strings_or_floats(self) -> None:
        for field_name in ("pid", "pgid", "session_id", "effective_uid", "real_gid"):
            for value in ("1", 1.0, None, [1]):
                with self.assertRaises(wec.PaidModelProcessRefError):
                    live_ref(**{field_name: value})

    def test_positive_process_identity_bounds(self) -> None:
        for field_name in ("pid", "pgid", "session_id"):
            for value in (0, -1, 2**63, -(2**63)):
                with self.assertRaises(wec.PaidModelProcessRefError):
                    live_ref(**{field_name: value})
            self.assertEqual(
                live_ref(**{field_name: 2**63 - 1}).pid if field_name == "pid"
                else getattr(live_ref(**{field_name: 2**63 - 1}), field_name),
                2**63 - 1,
            )

    def test_uid_bounds_and_mismatch(self) -> None:
        for field_name in ("effective_uid", "effective_gid", "real_uid", "real_gid"):
            for value in (-1, 2**31, None):
                with self.assertRaises(wec.PaidModelProcessRefError):
                    live_ref(**{field_name: value})
        self.assertEqual(
            live_ref(effective_uid=2**31 - 1, real_uid=2**31 - 1).effective_uid,
            2**31 - 1,
        )
        self.assertEqual(
            live_ref(effective_gid=2**31 - 1, real_gid=2**31 - 1).effective_gid,
            2**31 - 1,
        )
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(effective_uid=os.geteuid(), real_uid=os.geteuid() + 1)
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(effective_gid=os.getegid(), real_gid=os.getegid() + 1)

    def test_identifier_bounds(self) -> None:
        self.assertEqual(live_ref(run_id="a" * 128).run_id, "a" * 128)
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(run_id="a" * 129)
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(worker_id="_leading-underscore")
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(host_ref="")
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(host_ref="host name")

    def test_identity_text_bounds_and_edges(self) -> None:
        self.assertEqual(
            live_ref(launch_nonce="a" * 512).launch_nonce, "a" * 512
        )
        for field_name in ("process_start_identity", "boot_session_id", "launch_nonce"):
            for value in ("", "a" * 513, " padded", "padded ", "line\n", "a\x00b", None):
                with self.assertRaises(wec.PaidModelProcessRefError):
                    live_ref(**{field_name: value})

    def test_started_at_requires_timezone_aware_iso8601(self) -> None:
        self.assertEqual(
            live_ref(started_at="2026-10-22T13:16:00+00:00").started_at,
            "2026-10-22T13:16:00+00:00",
        )
        self.assertEqual(
            live_ref(started_at="2026-10-22T15:16:00+02:00").started_at,
            "2026-10-22T15:16:00+02:00",
        )
        self.assertEqual(
            live_ref(started_at="2026-10-22T13:16:00Z").started_at,
            "2026-10-22T13:16:00Z",
        )
        for value in (
            "2026-10-22T13:16:00",
            "not-a-time",
            "",
            "2026-13-45T99:99:99+00:00",
            None,
            17,
        ):
            with self.assertRaises(wec.PaidModelProcessRefError):
                live_ref(started_at=value)

    def test_output_paths_are_canonical_absolute_and_distinct(self) -> None:
        fields = live_fields()
        self.assertEqual(live_ref().stdout_path, fields["stdout_path"])
        for field_name in ("stdout_path", "stderr_path", "result_path"):
            for value in (
                "relative/path",
                "/tmp/../etc/passwd",
                "/tmp//double",
                "/tmp/trailing/",
                "/tmp/./dot",
                "",
                "/tmp/\x00",
                " /tmp/lead",
                "/tmp/trail ",
                "/tmp/" + "a" * 4096,
                None,
            ):
                with self.assertRaises(wec.PaidModelProcessRefError):
                    live_ref(**{field_name: value})
        self.assertEqual(
            live_ref(stdout_path="/" + "a" * 4095).stdout_path, "/" + "a" * 4095
        )
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(stderr_path=fields["stdout_path"])
        with self.assertRaises(wec.PaidModelProcessRefError):
            live_ref(
                stdout_path=fields["stdout_path"],
                stderr_path=fields["stdout_path"],
                result_path=fields["stdout_path"],
            )


if __name__ == "__main__":
    unittest.main()
