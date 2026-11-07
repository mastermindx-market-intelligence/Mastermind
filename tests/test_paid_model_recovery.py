"""Focused tests for the paid model-only durable recovery contract.

The tests import the production contract modules directly; there is no stub,
no fake process ref, and no downgrade path.  Every prompt fixture is a real
temporary private file created with mode ``0600`` and read through the exact
production permission, symlink, and ownership boundaries.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from control_plane.worker_execution_contract import (
    DURABLE_COLLECTION_CONTRACT_VERSION,
    WORKER_RECOVERY_BINDING_VERSION,
    WORKER_REMOTE_RECOVERY_BINDING_VERSION,
    BinaryAttestation,
    OrchestrationLaunchSpec,
    PaidModelProcessRef,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
    WorkerRecoveryContractError,
    _canonical_sha256,
    _control_recovery_digest,
    worker_launch_spec_sha256,
)
from control_plane.paid_model_recovery import (
    PAID_MODEL_ADAPTER_ID,
    PAID_MODEL_RECOVERY_BINDING_VERSION,
    PaidModelRecoveryBinding,
    PaidModelRecoveryRefused,
)

_LAUNCH_SPEC_FIELDS = {
    "fields",
    "prompt_path",
    "prompt_sha256",
    "control_recovery",
    "control_recovery_sha256",
}
_BINDING_FIELDS = {
    "schema_version",
    "adapter_id",
    "collection_contract_version",
    "launch_spec_sha256",
    "launch_spec",
    "process_ref",
    "launch_attestation_sha256",
    "launch_identity_sha256",
    "capture_root",
}


def _write_private(path: Path, payload: bytes) -> Path:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    return path


def _binary_attestation(root: Path) -> BinaryAttestation:
    binary = root / "paid-worker.bin"
    if not binary.exists():
        _write_private(binary, b"paid-binary")
    info = binary.lstat()
    return BinaryAttestation(
        path=str(binary),
        real_path=str(binary),
        version="1.2.3",
        sha256=hashlib.sha256(b"paid-binary").hexdigest(),
        team_identifier=None,
        size=info.st_size,
        device=info.st_dev,
        inode=info.st_ino,
        mode=stat.S_IMODE(info.st_mode),
        uid=info.st_uid,
        gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )


class _Harness:
    """One real private Control prompt and inert paid process identity DATA."""

    def __init__(self, root: Path, prompt_text: str = "paid recovery prompt\n") -> None:
        root = root.resolve(strict=False)
        self.root = root
        self.input_root = root / "control-input"
        self.source_workspace = root / "control-src"
        self.remote_workspace = root / "remote-ws"
        self.run_dir = root / "run"
        self.capture_root = root / "remote-capture"
        for directory in (
            self.input_root,
            self.source_workspace,
            self.remote_workspace,
            self.run_dir / "input",
        ):
            directory.mkdir(parents=True)
        self.prompt_text = prompt_text
        self.prompt_path = _write_private(
            self.input_root / "prompt.txt", prompt_text.encode("utf-8"),
        )
        self.schema_path = _write_private(
            self.run_dir / "input" / "result_schema.json", b"{}\n",
        )
        self.control_recovery = {
            "input_root": str(self.input_root),
            "source_workspace": str(self.source_workspace),
        }

    def spec(
        self, prompt: str | None = None, spec_type=WorkerLaunchSpec, **overrides,
    ) -> WorkerLaunchSpec:
        values = {
            "run_id": "run-paid-1",
            "job_id": "job-paid-1",
            "worker_id": "worker-paid-1",
            "workspace_path": self.remote_workspace,
            "run_dir": self.run_dir,
            "prompt": self.prompt_text if prompt is None else prompt,
            "result_schema_path": self.schema_path,
            "authorities": ("fabric.exec",),
            "allowed_artifact_paths": ("artifacts/out.jsonl",),
        }
        values.update(overrides)
        return spec_type(**values)

    def ref(self, spec: WorkerLaunchSpec, **overrides) -> PaidModelProcessRef:
        values = {
            "run_id": spec.run_id,
            "worker_id": spec.worker_id,
            "host_ref": "paid-host-7",
            "pid": 4173,
            "pgid": 4173,
            "session_id": 90210,
            "process_start_identity": "4173-112233445566",
            "boot_session_id": "boot-session-9",
            "launch_nonce": "launch-nonce-paid-1",
            "started_at": "2026-10-22T13:00:00Z",
            "effective_uid": os.geteuid(),
            "effective_gid": os.getegid(),
            "real_uid": os.geteuid(),
            "real_gid": os.getegid(),
            "binary": _binary_attestation(self.root),
            "stdout_path": str(self.capture_root / (spec.run_id + ".paid") / "stdout.jsonl"),
            "stderr_path": str(self.capture_root / (spec.run_id + ".paid") / "stderr.jsonl"),
            "result_path": str(self.capture_root / (spec.run_id + ".paid") / "result.json"),
        }
        values.update(overrides)
        return PaidModelProcessRef(**values)

    def bind(self, *, spec=None, ref=None, prompt_path=None, **overrides):
        values = {
            "adapter_id": PAID_MODEL_ADAPTER_ID,
            "spec": self.spec() if spec is None else spec,
            "process_ref": self.ref(self.spec()) if ref is None else ref,
            "prompt_path": self.prompt_path if prompt_path is None else prompt_path,
            "control_recovery": dict(self.control_recovery),
            "capture_root": str(self.capture_root),
            "launch_attestation_sha256": hashlib.sha256(b"attestation").hexdigest(),
            "launch_identity_sha256": hashlib.sha256(b"identity").hexdigest(),
        }
        values.update(overrides)
        return PaidModelRecoveryBinding.bind(**values)


class PaidModelRecoveryBindingTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="paid-model-recovery-")
        self.addCleanup(temporary.cleanup)
        self.harness = _Harness(Path(temporary.name))

    def test_bind_roundtrip_keeps_closed_shape_and_hashes(self) -> None:
        binding = self.harness.bind()
        self.assertEqual(binding.schema_version, PAID_MODEL_RECOVERY_BINDING_VERSION)
        self.assertEqual(binding.adapter_id, "canonical-paid-fabric")
        self.assertEqual(
            binding.collection_contract_version,
            DURABLE_COLLECTION_CONTRACT_VERSION,
        )
        self.assertEqual(
            binding.launch_spec_sha256,
            worker_launch_spec_sha256(self.harness.spec()),
        )
        self.assertEqual(set(binding.launch_spec), _LAUNCH_SPEC_FIELDS)
        self.assertEqual(
            binding.launch_spec["prompt_sha256"],
            hashlib.sha256(self.harness.prompt_text.encode("utf-8")).hexdigest(),
        )
        prompt_path = Path(binding.launch_spec["prompt_path"])
        self.assertTrue(prompt_path.is_absolute())
        prompt_path.relative_to(self.harness.input_root)
        self.assertEqual(dict(binding.control_recovery), self.harness.control_recovery)
        self.assertEqual(
            binding.launch_attestation_sha256,
            hashlib.sha256(b"attestation").hexdigest(),
        )
        self.assertEqual(
            binding.launch_identity_sha256,
            hashlib.sha256(b"identity").hexdigest(),
        )
        # The Control source workspace is retained verbatim and is never
        # asserted equal to the remote spec workspace.
        self.assertNotEqual(
            Path(self.harness.control_recovery["source_workspace"]),
            self.harness.spec().workspace_path,
        )
        self.assertEqual(self.harness.bind(), self.harness.bind())

    def test_to_dict_is_detached_plain_json_with_exact_fields(self) -> None:
        wire = self.harness.bind().to_dict()
        self.assertEqual(set(wire), _BINDING_FIELDS)
        reparsed = json.loads(json.dumps(wire))
        self.assertEqual(reparsed, wire)
        mutated = json.loads(json.dumps(wire))
        mutated["launch_spec"]["fields"]["run_id"] = "tampered"
        mutated["process_ref"]["run_id"] = "tampered"
        self.assertEqual(self.harness.bind().to_dict(), wire)
        rebuilt = PaidModelRecoveryBinding.from_dict(wire)
        self.assertEqual(rebuilt.launch_spec["fields"]["run_id"], "run-paid-1")

    def test_wire_roundtrip_recovers_the_same_spec(self) -> None:
        binding = self.harness.bind()
        wire = binding.to_dict()
        restored = PaidModelRecoveryBinding.from_dict(wire)
        self.assertEqual(restored, binding)
        self.assertEqual(
            restored.process_ref, self.harness.ref(self.harness.spec()),
        )
        self.assertIs(restored.validate_wire(), restored)
        recovered = restored.recover_launch_spec()
        self.assertEqual(recovered, self.harness.spec())
        self.assertEqual(recovered.prompt, self.harness.prompt_text)
        self.assertEqual(
            worker_launch_spec_sha256(recovered), binding.launch_spec_sha256,
        )
        self.assertEqual(recovered.run_id, restored.process_ref.run_id)
        self.assertEqual(recovered.worker_id, restored.process_ref.worker_id)

    def test_binding_is_immutable_and_coordinates_are_frozen(self) -> None:
        binding = self.harness.bind()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            binding.adapter_id = "other"
        with self.assertRaises(TypeError):
            binding.control_recovery["input_root"] = "/elsewhere"
        with self.assertRaises(TypeError):
            binding.launch_spec["fields"]["run_id"] = "other"
        self.assertEqual(dict(binding.control_recovery), self.harness.control_recovery)

    def test_orchestration_spec_roundtrip(self) -> None:
        grant = hashlib.sha256(b"grant").hexdigest()
        spec = self.harness.spec(
            spec_type=OrchestrationLaunchSpec, effective_grant_digest=grant,
        )
        ref = self.harness.ref(spec)
        binding = self.harness.bind(spec=spec, ref=ref)
        self.assertIs(binding.validate_wire(), binding)
        recovered = binding.recover_launch_spec(spec_type=OrchestrationLaunchSpec)
        self.assertEqual(recovered, spec)
        self.assertEqual(worker_launch_spec_sha256(recovered), binding.launch_spec_sha256)
        with self.assertRaises(WorkerRecoveryContractError):
            binding.recover_launch_spec(spec_type=WorkerLaunchSpec)

    def test_recover_rejects_invalid_launch_types(self) -> None:
        binding = self.harness.bind()
        for spec_type in ("WorkerLaunchSpec", int, None, object):
            with self.assertRaises(WorkerRecoveryContractError):
                binding.recover_launch_spec(spec_type=spec_type)
        with self.assertRaises(WorkerRecoveryContractError):
            binding.recover_launch_spec(spec_type=OrchestrationLaunchSpec)


    def test_mutated_control_coordinates_are_refused(self) -> None:
        wire = self.harness.bind().to_dict()

        def moved_input_root(candidate: dict) -> None:
            candidate["launch_spec"]["control_recovery"]["input_root"] = str(
                self.harness.root / "other-input",
            )

        def moved_source_workspace(candidate: dict) -> None:
            candidate["launch_spec"]["control_recovery"]["source_workspace"] = str(
                self.harness.root / "other-src",
            )

        def dropped_coordinates(candidate: dict) -> None:
            candidate["launch_spec"]["control_recovery"] = {
                "input_root": str(self.harness.run_dir / "input"),
                "source_workspace": str(self.harness.remote_workspace),
            }

        def drifted_control_digest(candidate: dict) -> None:
            candidate["launch_spec"]["control_recovery_sha256"] = "0" * 64

        for mutate in (
            moved_input_root,
            moved_source_workspace,
            dropped_coordinates,
            drifted_control_digest,
        ):
            candidate = json.loads(json.dumps(wire))
            mutate(candidate)
            with self.assertRaises(WorkerRecoveryContractError):
                PaidModelRecoveryBinding.from_dict(candidate)

    def test_malformed_control_coordinates_are_refused_at_bind(self) -> None:
        bad_shapes = (
            {"input_root": str(self.harness.input_root)},
            {
                "input_root": str(self.harness.input_root),
                "source_workspace": "control-src",
            },
            {
                "input_root": str(self.harness.root / "control-input" / ".."),
                "source_workspace": str(self.harness.source_workspace),
            },
        )
        for control_recovery in bad_shapes:
            with self.assertRaises(WorkerRecoveryContractError):
                self.harness.bind(control_recovery=control_recovery)

    def test_mutated_wire_digests_are_refused(self) -> None:
        wire = self.harness.bind().to_dict()
        for name, value in (
            ("launch_spec_sha256", hashlib.sha256(b"drift").hexdigest()),
            ("launch_attestation_sha256", "not-a-digest"),
            ("launch_identity_sha256", ""),
            ("schema_version", "mastermind.worker_recovery_binding/v2"),
        ):
            candidate = json.loads(json.dumps(wire))
            candidate[name] = value
            with self.assertRaises(WorkerRecoveryContractError):
                PaidModelRecoveryBinding.from_dict(candidate)
        candidate = json.loads(json.dumps(wire))
        candidate["launch_spec"]["prompt_sha256"] = "zz"
        with self.assertRaises(WorkerRecoveryContractError):
            PaidModelRecoveryBinding.from_dict(candidate)

    def test_validate_wire_detects_field_and_digest_drift(self) -> None:
        wire = self.harness.bind().to_dict()
        candidate = json.loads(json.dumps(wire))
        candidate["launch_spec"]["fields"]["timeout_seconds"] = 99.0
        drifted = PaidModelRecoveryBinding.from_dict(candidate)
        with self.assertRaises(WorkerRecoveryContractError):
            drifted.validate_wire()
        candidate = json.loads(json.dumps(wire))
        del candidate["launch_spec"]["fields"]["authorities"]
        candidate["launch_spec_sha256"] = _canonical_sha256({
            **candidate["launch_spec"]["fields"],
            "prompt_sha256": candidate["launch_spec"]["prompt_sha256"],
        })
        candidate["launch_spec"]["control_recovery_sha256"] = _control_recovery_digest(
            candidate["launch_spec_sha256"], candidate["launch_spec"],
        )
        reshaped = PaidModelRecoveryBinding.from_dict(candidate)
        with self.assertRaises(WorkerRecoveryContractError):
            reshaped.validate_wire()

    def test_process_output_paths_must_stay_under_remote_capture_namespace(self) -> None:
        wire = self.harness.bind().to_dict()
        escapes = (
            str(self.harness.run_dir / ".." / "escape.jsonl"),
            str(self.harness.root / "elsewhere.jsonl"),
            str(self.harness.input_root / "prompt.txt"),
            "../escape.jsonl",
        )
        for index, escaped in enumerate(escapes):
            candidate = json.loads(json.dumps(wire))
            name = ("stdout_path", "stderr_path", "result_path")[index % 3]
            candidate["process_ref"][name] = escaped
            try:
                rebuilt = PaidModelRecoveryBinding.from_dict(candidate)
            except WorkerRecoveryContractError:
                # Escaping output paths may already be refused by the paid
                # process ref's own closed validation.
                continue
            with self.assertRaises(WorkerRecoveryContractError):
                rebuilt.validate_wire()
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(
                ref=self.harness.ref(
                    self.harness.spec(),
                    result_path=str(self.harness.root / "result.json"),
                ),
            ).validate_wire()

    def test_control_paths_remain_local_and_capture_root_is_mandatory(self):
        binding = self.harness.bind()
        self.assertNotEqual(binding.launch_spec["fields"]["run_dir"], binding.capture_root)
        binding.validate_wire()
        self.assertEqual(binding.recover_launch_spec().run_dir, self.harness.run_dir)
        wire = binding.to_dict()
        del wire["capture_root"]
        with self.assertRaises(PaidModelRecoveryRefused):
            PaidModelRecoveryBinding.from_dict(wire)
        for bad in ("/", "relative", "/tmp/../capture", "/tmp//capture", "/tmp/capture/", None):
            with self.subTest(root=bad), self.assertRaises(PaidModelRecoveryRefused):
                self.harness.bind(capture_root=bad)

    def test_prompt_symlinks_are_refused(self) -> None:
        inside = self.harness.input_root / "inside-link.txt"
        os.symlink(self.harness.prompt_path, inside)
        bound = self.harness.bind(prompt_path=inside)
        # An in-root symlink resolves transparently to the private target and
        # the binding retains the resolved real path, never the link.
        self.assertEqual(
            Path(bound.launch_spec["prompt_path"]),
            self.harness.prompt_path.resolve(strict=True),
        )
        outside = _write_private(
            self.harness.root / "outside.txt",
            self.harness.prompt_text.encode("utf-8"),
        )
        escape = self.harness.input_root / "escape-link.txt"
        os.symlink(outside, escape)
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=escape)
        # A symlink swapped in at the recorded prompt path is refused at
        # recovery time even when the target holds identical private bytes.
        binding = self.harness.bind()
        recorded = Path(binding.launch_spec["prompt_path"])
        swapped = _write_private(
            self.harness.root / "swapped-prompt.txt",
            self.harness.prompt_text.encode("utf-8"),
        )
        recorded.unlink()
        os.symlink(swapped, recorded)
        self.assertIs(binding.validate_wire(), binding)
        with self.assertRaises(WorkerRecoveryContractError):
            binding.recover_launch_spec()

    def test_private_prompt_boundaries_are_refused(self) -> None:
        group_readable = _write_private(
            self.harness.input_root / "group-readable.txt",
            self.harness.prompt_text.encode("utf-8"),
        )
        os.chmod(group_readable, 0o640)
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=group_readable)
        world_readable = _write_private(
            self.harness.input_root / "world-readable.txt",
            self.harness.prompt_text.encode("utf-8"),
        )
        os.chmod(world_readable, 0o644)
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=world_readable)
        linked = _write_private(
            self.harness.input_root / "linked.txt",
            self.harness.prompt_text.encode("utf-8"),
        )
        os.link(linked, self.harness.input_root / "hardlink.txt")
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=linked)
        directory = self.harness.input_root / "prompt-dir"
        directory.mkdir()
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=directory)
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=self.harness.input_root / "missing.txt")
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path="control-input/prompt.txt")

    def test_oversized_and_empty_prompts_are_refused(self) -> None:
        oversized = tempfile.TemporaryDirectory(prefix="paid-model-recovery-big-")
        self.addCleanup(oversized.cleanup)
        big_harness = _Harness(Path(oversized.name), prompt_text="p" * (1024 * 1024 + 1))
        big_spec = big_harness.spec()
        with self.assertRaises(WorkerRecoveryContractError):
            big_harness.bind(spec=big_spec, ref=big_harness.ref(big_spec))
        empty_harness = _Harness(Path(oversized.name) / "empty", prompt_text="")
        empty_spec = empty_harness.spec()
        with self.assertRaises(WorkerRecoveryContractError):
            empty_harness.bind(spec=empty_spec, ref=empty_harness.ref(empty_spec))

    def test_prompt_bytes_must_match_the_launch_specification(self) -> None:
        other = _write_private(
            self.harness.input_root / "other.txt", b"different prompt bytes\n",
        )
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=other)
        outside = _write_private(
            self.harness.root / "outside-copy.txt",
            self.harness.prompt_text.encode("utf-8"),
        )
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(prompt_path=outside)

    def test_changed_prompt_refuses_recovery_but_wire_stays_valid(self) -> None:
        binding = self.harness.bind()
        self.assertIs(binding.validate_wire(), binding)
        with open(self.harness.prompt_path, "r+b") as handle:
            handle.write(b"tampered prompt\n")
            handle.truncate()
        self.assertIs(binding.validate_wire(), binding)
        with self.assertRaises(WorkerRecoveryContractError):
            binding.recover_launch_spec()
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind()


    def test_identity_and_adapter_mismatch_is_refused(self) -> None:
        spec = self.harness.spec()
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(ref=self.harness.ref(spec, run_id="run-other"))
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(ref=self.harness.ref(spec, worker_id="worker-other"))
        for adapter in (
            "attended-fabric",
            "",
            " canonical-paid-fabric",
            "canonical-paid-fabric ",
        ):
            with self.assertRaises(PaidModelRecoveryRefused) as caught:
                self.harness.bind(adapter_id=adapter)
            self.assertIsInstance(caught.exception, WorkerRecoveryContractError)
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(launch_attestation_sha256="")
        with self.assertRaises(WorkerRecoveryContractError):
            self.harness.bind(launch_identity_sha256="ZZ")

    def test_from_dict_rejects_broken_shapes(self) -> None:
        wire = self.harness.bind().to_dict()
        for candidate in (
            "paid-model-recovery-binding",
            None,
            {name: value for name, value in wire.items()
             if name != "launch_identity_sha256"},
            {**wire, "provider_session": "session"},
            {**wire, "home": "/home/worker"},
            {**wire, "base_sha": "0" * 64},
        ):
            with self.assertRaises(WorkerRecoveryContractError):
                PaidModelRecoveryBinding.from_dict(candidate)
        broken_launch = json.loads(json.dumps(wire))
        broken_launch["launch_spec"] = "launch material"
        with self.assertRaises(WorkerRecoveryContractError):
            PaidModelRecoveryBinding.from_dict(broken_launch)
        broken_ref = json.loads(json.dumps(wire))
        broken_ref["process_ref"] = "process ref"
        with self.assertRaises(WorkerRecoveryContractError):
            PaidModelRecoveryBinding.from_dict(broken_ref)

    def test_legacy_bindings_stay_exact_and_never_interchange(self) -> None:
        harness = self.harness
        spec = harness.spec()
        legacy_ref = WorkerProcessRef(
            run_id=spec.run_id,
            pid=4173,
            pgid=4173,
            process_start_identity="4173-112233445566",
            boot_session_id="boot-session-9",
            launch_nonce="launch-nonce-legacy-1",
            provider_session_id=None,
            stdout_path=str(harness.run_dir / "stdout.jsonl"),
            stderr_path=str(harness.run_dir / "stderr.jsonl"),
            result_path=str(harness.run_dir / "result.json"),
            started_at="2026-10-22T13:00:00Z",
            binary=_binary_attestation(harness.root),
            base_sha="0" * 64,
        )
        legacy_prompt = _write_private(
            harness.run_dir / "input" / "legacy-prompt.txt",
            harness.prompt_text.encode("utf-8"),
        )
        legacy = WorkerRecoveryBinding.bind(
            adapter_id="legacy-adapter",
            spec=spec,
            process_ref=legacy_ref,
            prompt_path=legacy_prompt,
        )
        remote = WorkerRecoveryBinding.bind(
            adapter_id="attended-fabric",
            spec=spec,
            process_ref=legacy_ref,
            prompt_path=harness.prompt_path,
            control_recovery=dict(harness.control_recovery),
        )
        self.assertEqual(legacy.schema_version, WORKER_RECOVERY_BINDING_VERSION)
        self.assertEqual(remote.schema_version, WORKER_REMOTE_RECOVERY_BINDING_VERSION)
        self.assertEqual(
            set(legacy.to_dict()),
            {
                "schema_version",
                "adapter_id",
                "collection_contract_version",
                "launch_spec_sha256",
                "launch_spec",
                "process_ref",
            },
        )
        self.assertIs(legacy.validate_wire(), legacy)
        self.assertEqual(legacy.recover_launch_spec(), spec)
        self.assertIs(remote.validate_wire(), remote)
        self.assertEqual(remote.recover_launch_spec(), spec)
        self.assertEqual(dict(remote.control_recovery), harness.control_recovery)

    def test_paid_binding_never_downgrades_to_legacy_shapes(self) -> None:
        self.assertFalse(issubclass(PaidModelRecoveryBinding, WorkerRecoveryBinding))
        paid = self.harness.bind()
        legacy_payload = paid.to_dict()
        self.assertIsInstance(paid.process_ref, PaidModelProcessRef)
        self.assertNotIsInstance(paid.process_ref, WorkerProcessRef)
        for candidate in (
            {**legacy_payload, "process_ref": {
                **legacy_payload["process_ref"], "base_sha": "0" * 64,
            }},
            {**legacy_payload, "process_ref": {
                **legacy_payload["process_ref"],
                "provider_session_id": "provider-session",
            }},
            {**legacy_payload, "process_ref": {
                **legacy_payload["process_ref"], "home": "/home/worker",
            }},
        ):
            with self.assertRaises(WorkerRecoveryContractError):
                PaidModelRecoveryBinding.from_dict(candidate)
        legacy_ref = WorkerProcessRef(
            run_id=paid.process_ref.run_id,
            pid=paid.process_ref.pid,
            pgid=paid.process_ref.pgid,
            process_start_identity=paid.process_ref.process_start_identity,
            boot_session_id=paid.process_ref.boot_session_id,
            launch_nonce=paid.process_ref.launch_nonce,
            provider_session_id=None,
            stdout_path=paid.process_ref.stdout_path,
            stderr_path=paid.process_ref.stderr_path,
            result_path=paid.process_ref.result_path,
            started_at=paid.process_ref.started_at,
            binary=paid.process_ref.binary,
            base_sha="0" * 64,
        )
        with self.assertRaises(WorkerRecoveryContractError):
            PaidModelRecoveryBinding(
                schema_version=PAID_MODEL_RECOVERY_BINDING_VERSION,
                adapter_id=PAID_MODEL_ADAPTER_ID,
                collection_contract_version=DURABLE_COLLECTION_CONTRACT_VERSION,
                launch_spec_sha256=paid.launch_spec_sha256,
                launch_spec=dict(paid.launch_spec),
                process_ref=legacy_ref,
                launch_attestation_sha256=paid.launch_attestation_sha256,
                launch_identity_sha256=paid.launch_identity_sha256,
                capture_root=paid.capture_root,
            )


if __name__ == "__main__":
    unittest.main()
