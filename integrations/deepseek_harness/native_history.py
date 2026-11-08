"""Finite original-Worker reads of persisted native answers, with no Session admission."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import time
import uuid

from control_plane.codex_worker import ProcessInspector, _process_group_exists

from control_plane.native_conversation_read_contract import (
    NativeReadUnavailable, NativeReadPhysicalUnknown, canonical,
    validate_native_read_association, validate_native_read_request,
    validate_native_read_response,
)
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation, base_process_identity,
)
from control_plane.operator_harness_wire import session_epoch_ref, process_generation_ref
from control_plane.operator_materialization_receipt import (
    read_operator_materialization_receipt, validate_materialization_request,
)
from integrations.acp_worker.process_resource import NativeProcessResource
from integrations.deepseek_harness.native_read_port import OwnedNativeReadPort


class NativeHistoryReader:
    """One source-qualified callback under the incumbent broker's finite read task."""
    def __init__(self, *, policy, installed, require_source, inspector=None):
        self.policy, self.installed, self.require_source = policy, installed, require_source
        self.inspector = inspector if inspector is not None else ProcessInspector()
        self.resource = None
        self.capture = None

    def _receipt(self, payload, *, content, current):
        expected = {"epoch", "generation", "history"} | ({"association", "request"} if content else set())
        if type(payload) is not dict or set(payload) != expected:
            raise NativeReadUnavailable()
        history = payload["history"]
        fields = {"principal_observation", "requested_profile_digest", "observed_attestation_digest"}
        if content:
            fields.add("materialization_receipt_sha256")
        if type(history) is not dict or set(history) != fields:
            raise NativeReadUnavailable()
        for key in fields - {"principal_observation"}:
            value = history[key]
            if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise NativeReadUnavailable()
        epoch, generation = session_epoch_ref(payload["epoch"]), process_generation_ref(payload["generation"])
        observed = OperatorPrincipalObservation.from_dict(history["principal_observation"])
        policy, installed, source = self.policy, self.installed, self.require_source
        if (epoch.worker_id != policy.worker_id or generation.worker_id != epoch.worker_id
                or generation.session_epoch_id != epoch.session_epoch_id
                or observed.attempt_id != epoch.attempt_id or observed.worker_id != epoch.worker_id
                or observed.process_generation_id != generation.process_generation_id
                or observed.os_principal_uid != policy.worker_uid
                or generation.generation_number not in (1, 2)):
            raise NativeReadUnavailable()
        kind = "start_session" if generation.generation_number == 1 else "resume_session"
        command = ("ohf-op:start:" if generation.generation_number == 1
                   else "ohf-op:recover-resume:") + epoch.attempt_id
        validate_materialization_request(operation_command_id=command, operation_kind=kind,
            attempt_id=epoch.attempt_id, worker_id=epoch.worker_id,
            session_epoch_id=epoch.session_epoch_id, process_generation_id=generation.process_generation_id,
            generation_number=generation.generation_number,
            expected_provider_session_id=observed.provider_session_id if kind == "resume_session" else None)
        def guard():
            if (self.policy is not policy or self.installed is not installed
                    or self.require_source is not source or current() is not None or source() is not None):
                raise NativeReadUnavailable()
            installed.require_current()
        guard()
        receipt = read_operator_materialization_receipt(
            policy.run_root, command, expected_owner_uid=policy.worker_uid)
        guard()
        if (receipt is None or receipt.operation_kind != kind
                or receipt.operation_command_id != command
                or receipt.attempt_id != epoch.attempt_id or receipt.worker_id != epoch.worker_id
                or receipt.session_epoch_id != epoch.session_epoch_id
                or receipt.process_generation_id != generation.process_generation_id
                or receipt.generation_number != generation.generation_number
                or receipt.provider_session_id != observed.provider_session_id
                or receipt.requested_profile_digest != history["requested_profile_digest"]
                or receipt.process_identity != base_process_identity(observed.process_identity)
                or receipt.process_credentials["os_principal_uid"] != observed.os_principal_uid
                or receipt.process_credentials["os_principal_name"] != observed.os_principal_name
                or base_process_identity(receipt.process_credentials["process_identity"]) != receipt.process_identity
                or receipt.provider_home_identity != observed.provider_home_identity
                or hashlib.sha256(canonical(receipt.observed_attestation)).hexdigest() != history["observed_attestation_digest"]
                or content and receipt.receipt_digest != history["materialization_receipt_sha256"]):
            raise NativeReadUnavailable()
        # The original writer must be physically absent, not merely retired in
        # the consumer projection. A failed inspect is never absence evidence.
        process = receipt.process_identity
        boot = self.inspector.boot_session_id()
        if process["pid"] != process["pgid"] or process["pgid"] in (os.getpid(), os.getpgrp()):
            raise NativeReadUnavailable()
        same_boot = boot == process["boot_id"]
        if not same_boot:
            # Only unequal OS-qualified UUID values prove an earlier boot absent;
            # spelling differences and adapter-scoped fallbacks do not.
            try:
                same_boot = uuid.UUID(boot) == uuid.UUID(process["boot_id"])
            except (ValueError, TypeError, AttributeError) as exc:
                raise NativeReadUnavailable() from exc
        if same_boot and _process_group_exists(process["pgid"]):
            raise NativeReadUnavailable()
        home = policy.provider_home
        info = home.lstat()
        identity = dict(path=str(home), device=info.st_dev, inode=info.st_ino,
                        uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode))
        if (home.resolve(strict=True) != home or not stat.S_ISDIR(info.st_mode)
                or identity != observed.provider_home_identity
                or identity["uid"] != policy.worker_uid or identity["gid"] != policy.worker_gid
                or identity["mode"] != 0o700):
            raise NativeReadUnavailable()
        guard()
        binding = dict(schema="mastermind.dsh.native_read_binding.v1",
            native_session_id=receipt.provider_session_id,
            native_package_sha256=installed.package_manifest_sha256, donor_sha=installed.donor_sha)
        return receipt, binding

    async def __call__(self, payload, *, content, current):
        frozen = canonical(payload)
        receipt, binding = self._receipt(payload, content=content, current=current)
        def unchanged():
            if canonical(payload) != frozen or current() is not None:
                raise NativeReadUnavailable()
            if self._receipt(payload, content=content, current=current) != (receipt, binding):
                raise NativeReadUnavailable()
        if not content:
            unchanged()
            return dict(schema="mastermind.dsh.native_history_binding.v1", binding=binding,
                        materialization_receipt_sha256=receipt.receipt_digest)
        association = validate_native_read_association(payload["association"])
        digest = hashlib.sha256(canonical(association)).hexdigest()
        request = validate_native_read_request(payload["request"], digest)
        if (association["native_session_id"] != binding["native_session_id"]
                or association["native_package_sha256"] != binding["native_package_sha256"]
                or association["donor_sha"] != binding["donor_sha"]
                or request["principal"]["principal_scope"] != association["owner_principal_scope"]
                or request["read"]["kind"] != "result"):
            raise NativeReadUnavailable()
        def authorized():
            unchanged()
            now = int(time.time())
            if not request["principal"]["issued_at"] <= now < request["principal"]["expires_at"]:
                raise NativeReadUnavailable()
        authorized()
        if self.resource is not None:
            raise NativeReadPhysicalUnknown()
        if self.capture is not None:
            # A settled child's retained diagnostics are an artifact cleanup
            # failure, not uncertain process custody. Do not start over them.
            raise NativeReadUnavailable()
        parent = child = port = None
        opening = False
        outcome = None
        original_error = None
        try:
            self.capture = Path(tempfile.mkdtemp(prefix="native-history-", dir=self.policy.run_root))
            parent, child = socket.socketpair()
            port = OwnedNativeReadPort(parent, association_sha256=digest)
            home = os.environ.get("HOME")
            if not home or not Path(home).is_absolute():
                raise NativeReadUnavailable()
            environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": home,
                "DSH_HOME": str(self.policy.provider_home), "LANG": "C.UTF-8",
                "MMX_NATIVE_COMPANY_FD": str(child.fileno()),
                "MMX_NATIVE_HISTORY_ASSOCIATION": canonical(association).decode("utf-8")}
            authorized()
            async with asyncio.timeout(4.0):
                opening = True
                self.resource = await NativeProcessResource.open(
                    binary=self.installed.binary,
                    argv=(self.installed.binary.path, str(self.installed.entrypoint), "--read-history"),
                    environment=environment, cwd=self.policy.run_root,
                    stdout_path=self.capture/"stdout.log", stderr_path=self.capture/"stderr.log",
                    stdout_limit_bytes=8192, stderr_limit_bytes=8192, settle_seconds=1.5,
                    stdout_is_protocol=False, pass_fds=(child.fileno(),), inspector=self.inspector)
                child.close(); child = None
                authorized()
                # The existing anonymous port owns its internal correlation.
                # Return its validated body under the original broker request.
                inner = await port.read(
                    principal_scope=request["principal"]["principal_scope"],
                    issued_at=request["principal"]["issued_at"], expires_at=request["principal"]["expires_at"],
                    request=request["read"], before_write=authorized)
                outcome = {**inner, "request_id": request["request_id"]}
                validate_native_read_response(outcome, request)
                authorized()
        except BaseException as exc:
            original_error = exc
        finally:
            if child is not None:
                child.close()
            if port is not None:
                port.retire()
            elif parent is not None:
                parent.close()
            if self.resource is not None:
                try:
                    settled = await self.resource.finish(None)
                    if (not settled.settled or _process_group_exists(self.resource.identity.pgid)):
                        raise NativeReadPhysicalUnknown()
                except BaseException as exc:
                    raise NativeReadPhysicalUnknown() from exc
                self.resource = None
                if settled.exit_code != 0:
                    original_error = NativeReadUnavailable()
            elif opening:
                # open() may have spawned before its own rollback raised.
                # Keep this original capture/owner; never launch a substitute.
                raise NativeReadPhysicalUnknown() from original_error
            if self.capture is not None:
                try:
                    shutil.rmtree(self.capture)
                except OSError as exc:
                    # Keep the exact owned directory for later diagnosis.
                    raise NativeReadUnavailable() from exc
                self.capture = None
        if original_error is not None:
            raise NativeReadUnavailable() from original_error
        authorized()
        if outcome is None:
            raise NativeReadUnavailable()
        return outcome
