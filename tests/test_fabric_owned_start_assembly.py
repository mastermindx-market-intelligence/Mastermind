"""Combined assembler/real original retainer; all issuer/process observations inert.

No mirrors of the validators are allowed. No child, /proc read, provider,
Control capability, enrollment or production qualification is exercised.
"""
import copy
import dataclasses
import hashlib
import json
import os
import pwd
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
from control_plane import worker_execution_contract as CONTRACT
from control_plane import executive_fabric_bridge_broker as BRIDGE
from control_plane import executive_fabric_adapter as ADAPTER
from integrations.session_bridge.bound_launch_capture import fabric_owned_start as producer
from test_fabric_owned_process_phases import lr

LANE = None

D = lambda label: hashlib.sha256(label.encode("utf-8")).hexdigest()  # noqa: E731
PROMPT = "INERT task prompt for the bounded attended worker."
LAUNCH_NONCE = "nonce-inert-00000001"
RUN_ID = "run-inert-0001"
JOB_ID = "job-inert-0001"
WORKER_ID = "worker-inert-0001"
RUN_DIR = "/tmp/fabric-inert-runs/" + RUN_ID
WORKSPACE = "/tmp/fabric-inert-workspace"


def _canary_checks():
    from control_plane.codex_worker import _SECRET_CANARY_CHECKS
    return {name: 'DENIED' for name in _SECRET_CANARY_CHECKS}


def _control_uid():
    from ops.executive_os.capacity_broker_topology import CONTROL_UID
    return CONTROL_UID


class Descriptor:
    """INERT stand-in carrying the exact prepared-descriptor attribute set."""

    def __init__(self, **fields):
        for name, value in fields.items():
            object.__setattr__(self, name, value)


class FakeProcess:
    def __init__(self, pid: int):
        self.pid = pid
        self._returncode = None

    def poll(self):
        return self._returncode


def OwnerFixture(world):
    owner = LANE.OwnedExecution(capture_identity=True)
    owner.label = world.run_id
    owner.process = FakeProcess(424242)
    owner._identity = dict(pid=424242, pgid=424242, session_id=424242,
        boot_id='inert-boot-scope', process_start_identity='linux:999888777666',
        effective_uid=world.euid, effective_gid=world.egid,
        real_uid=world.euid, real_gid=world.egid)
    owner.started_at = '2026-10-12T00:00:00Z'
    owner.launch_nonce = LAUNCH_NONCE
    return owner


class World:
    """One inert, fully qualified fixture world; nothing here is production."""

    def __init__(self, run_dir=RUN_DIR):
        self.euid = os.geteuid()
        self.egid = os.getegid()
        self.worker_user = pwd.getpwuid(self.euid).pw_name
        self.run_id = RUN_ID
        self.binary_sha = D("binary")
        control_uid = _control_uid()
        bridge_uid = max(1, self.euid) + 7
        if bridge_uid == control_uid:
            bridge_uid += 1
        self.physical = ADAPTER.FabricHostBinding(
            socket_path="/var/run/inert-fabric.sock", host_ref="host-inert",
            worker_id=WORKER_ID, worker_uid=self.euid, worker_gid=self.egid,
            provider="minimax", model="inert-model-1",
            worker_source_config_digest=D("worker-source-config"),
            execution_profile_digest=D("execution-profile"),
            service_source_sha256=D("service-source"),
            provider_home="/tmp/fabric-inert-provider-home",
            binary_sha256=self.binary_sha,
            permission_profile_sha256=D('{"permissions":{"allow":["Read(...)"]}}'),
            bridge_uid=bridge_uid)
        self.pin = CONTRACT.BinaryAttestation(
            path="/opt/inert/bin/claude", real_path="/opt/inert/bin/claude",
            version="inert-1.0.0", sha256=self.binary_sha,
            team_identifier=None, size=123456, device=7, inode=4242,
            mode=0o100755, uid=0, gid=0, mtime_ns=1700000000000000000)
        self.image = {
            "pid": 424242, "parent_pid": os.getpid(), "pgid": 424242,
            "session_id": 424242, "boot_id": "inert-boot-scope",
            "start_identity": "999888777666",
            "effective_uid": self.euid, "effective_gid": self.egid,
            "real_uid": self.euid, "real_gid": self.egid,
            "sha256": self.binary_sha, "device": 7, "inode": 4242,
            "mode": 0o100755, "uid": 0, "gid": 0,
            "size": 123456, "mtime_ns": 1700000000000000000,
            "ctime_ns": 1700000000000000001,
        }
        self.descriptor = Descriptor(
            schema="mastermind.fabric_attended_claude_launch/v1",
            contract_name="fabric.attended.claude.bounded.v1",
            run_id=self.run_id,
            argv=(self.pin.real_path, "--safe-mode", "-p",
                  "--output-format", "json", "--model", "inert-model-1",
                  "--settings", '{"permissions":{"allow":["Read(...)"]}}',
                  "--json-schema", "{}"),
            stdin_text=PROMPT,
            environment=MappingProxyType({
                "HOME": run_dir + "/home", "TMPDIR": run_dir + "/tmp",
                "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                "ANTHROPIC_MODEL": "inert-model-1",
                "ANTHROPIC_BASE_URL": "https://inert.example.invalid",
            }),
            workspace_path=WORKSPACE, run_dir=run_dir,
            provider_home=run_dir + "/home", provider_tmp=run_dir + "/tmp",
            model="inert-model-1", settings_sha256=D('{"permissions":{"allow":["Read(...)"]}}'),
            result_schema_json='{"type":"object"}',
            preparation_only=True, start_authorized=False)
        self.owner = OwnerFixture(self)
        self.owner.inert_image = dict(self.image)
        self.owner._original_preparation = self.descriptor
        self.binding = {
            "root_id": "root-inert-00000001", "job_id": JOB_ID,
            "attempt_id": self.run_id,
            "effective_grant_digest": D("grant"),
            "commission_sha256": D("commission"),
        }
        self.canary = {
            "schema_version": "mastermind.executive_secret_canary/v2",
            "passed": True,
            "checks": _canary_checks(),
            "receipt_sha256": D("canary-receipt"),
            "control_environment_probe_sha256": D("canary-probe"),
            "observed_at": "2026-10-12T00:00:00Z",
            "worker_auth_exception": "ASSIGNED_CLAUDE_PROVIDER_REALM_ONLY",
            "realm_binding": {
                "execution_profile_id": "fabric.attended.claude.bounded.v1",
                "harness_binding_id": "minimax-token-plan.claude-code-anthropic",
                "run_id": self.run_id, "job_id": JOB_ID, "worker_id": WORKER_ID,
                "physical_binding_sha256": self.physical.digest,
                "provider_home": self.physical.provider_home,
            },
        }
        self.spec = {
            "run_id": self.run_id, "job_id": JOB_ID, "worker_id": WORKER_ID,
            "prompt": PROMPT, "workspace_path": WORKSPACE, "run_dir": run_dir,
            "result_schema_path": run_dir + "/input/schema.json",
            "authorities": ["READ"], "authority": None,
            "model": "inert-model-1", "reasoning_effort": "xhigh",
            "timeout_seconds": 1800.0, "cancel_grace_seconds": 10.0,
            "worker_user": self.worker_user,
            "expected_base_sha": D("base")[:40],
            "allowed_artifact_paths": [], "isolation_roots": [],
            "isolation_denied_paths": [], "isolation_manifest": {},
            "isolation_manifest_sha256": D("isolation"),
            "forbidden_paths": [], "max_artifacts": 32,
            "max_artifact_bytes": 8 * 1024 * 1024,
            "max_artifact_total_bytes": 32 * 1024 * 1024,
            "expected_worker_uid": self.euid, "expected_worker_gid": self.egid,
            "shared_run_gid": None,
            "secret_canary_verdict": self.canary,
            "require_secret_canary": True,
            "subscription_canary_claim": {},
        }
        self.material = {
            "binding": dict(self.binding),
            "physical_binding_sha256": self.physical.digest,
            "launch_spec": dict(self.spec), "validation_commands": [],
        }
        self.original = {
            **self.material,
            "start_request_sha256": BRIDGE.start_request_sha256(self.material),
        }
        self.evidence = {
            "realm_enrollment": {"evidence_sha256": D("realm"),
                                 "source": "inert:realm-owner"},
            "attendance": {"evidence_sha256": D("attendance"),
                           "source": "inert:attendance-owner"},
            "capacity": {"evidence_sha256": D("capacity"),
                         "source": "inert:capacity-owner"},
            "isolation": {"evidence_sha256": D("isolation-evidence"),
                          "source": "inert:isolation-owner",
                          "isolation_manifest_sha256": D("isolation")},
            "assignment": {"evidence_sha256": D("assignment"),
                           "source": "inert:assignment-owner"},
            "finite_home_tmp": {"evidence_sha256": D("home-tmp"),
                                "source": "inert:filesystem-owner",
                                "home_path": run_dir + "/home",
                                "tmp_path": run_dir + "/tmp"},
        }
        self.capture = {
            "stdout_path": run_dir + "/logs/stdout.json",
            "stderr_path": run_dir + "/logs/stderr.log",
            "result_path": run_dir + "/output/result.json",
        }
        self.workspace_identity = {
            "path": WORKSPACE, "device": 7, "inode": 99, "uid": self.euid,
            "gid": self.egid, "mode": 0o40755,
            "mtime_ns": 1700000000000000000, "git_head": D("base")[:40],
        }
        self.provider_home_identity = {
            "path": run_dir + "/home", "device": 7, "inode": 100,
            "uid": self.euid, "gid": self.egid, "mode": 0o40700,
            "mtime_ns": 1700000000000000000,
        }
        self.records: list[bytes] = []
        self.retained = 0

    def retain(self, blob: bytes) -> None:
        self.records.append(blob)
        self.retained += 1

    def with_spec(self, **changes) -> "World":
        self.spec = {**self.spec, **changes}
        self.material = {**self.material, "launch_spec": self.spec}
        self.original = {
            **self.material,
            "start_request_sha256": BRIDGE.start_request_sha256(self.material),
        }
        return self

    def kwargs(self) -> dict:
        return dict(
            original=self.original, owner=self.owner,
            authority=None,
            physical=self.physical, binary_pin=self.pin,
            capture_paths=self.capture,
            qualified_evidence=self.evidence,
            workspace_identity=self.workspace_identity,
            provider_home_identity=self.provider_home_identity)


@pytest.fixture
def world(lr, tmp_path, monkeypatch):
    global LANE
    LANE = lr
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    value = World(str(run_dir))
    owner = value.owner
    owner._invocation = dict(command=list(value.descriptor.argv),
        cwd=value.descriptor.workspace_path, shell=False,
        environment_keys=sorted(value.descriptor.environment),
        environment_projection_sha256=lr._nonsecret_environment_sha256(value.descriptor.environment),
        prompt_sha256=hashlib.sha256(value.descriptor.stdin_text.encode()).hexdigest())
    owner._original_start_context = dict(binding=value.binding,
        request_sha256=BRIDGE.start_request_sha256(value.material),
        physical_binding_sha256=value.physical.digest)
    owner._original_start_receipt_path = tmp_path / 'original.start.json'
    monkeypatch.setattr(lr, '_EXECUTION_OWNER', owner)
    owner._capture_reservation = lr._OwnedCaptureReservation.create(str(run_dir),
        result_schema_json=value.descriptor.result_schema_json, limit_bytes=1024 * 1024)
    owner._original_capture_paths = lr.owned_capture_paths(owner)
    assert owner._original_capture_paths == value.capture
    value.holds = []
    owner._original_lease = SimpleNamespace(hold_for_reconciliation=value.holds.append)
    value.finisher = object()
    owner._finisher = value.finisher
    monkeypatch.setattr(lr, '_EXECUTION_OWNER', owner)
    monkeypatch.setitem(__import__('sys').modules, 'lane_runtime', lr)
    monkeypatch.setitem(__import__('sys').modules, 'integrations.session_bridge.bound_launch_capture.runtime.lane_runtime', lr)
    monkeypatch.setattr(__import__('integrations.session_bridge.bound_launch_capture.runtime',fromlist=['lane_runtime']), 'lane_runtime', lr, raising=False)
    monkeypatch.setattr(lr.sys, 'platform', 'linux')
    from control_plane import linux_process_identity
    value.observations = []
    def inspect(pid):
        value.observations.append(pid)
        return {k: v for k, v in value.image.items() if k != 'pid'}
    monkeypatch.setattr(linux_process_identity, 'inspect_linux_process_image', inspect)
    value.authority_checks = []
    def inert_authority(authority, material):
        value.authority_checks.append(material)
    monkeypatch.setattr(producer, '_require_control_authority', inert_authority)
    yield value
    # Actual private FD reservation is tested; kernel/issuer remain inert.
    reservation = owner._capture_reservation
    if reservation is not None and not reservation._closed:
        reservation.close_fds_only()
    monkeypatch.setattr(lr, '_EXECUTION_OWNER', None)


def test_real_validators_original_observer_and_retainer_join(world, monkeypatch):
    monkeypatch.setattr(producer, '_utc_now', lambda: '2026-10-13T00:00:00Z')
    published = producer.publish_owned_start(**world.kwargs())
    result = dict(published.start_result)
    ref, _ = ADAPTER.validate_start_result(result, payload=world.material, physical=world.physical)
    BRIDGE._complete_start_result(result, world.binding, result['request_sha256'], world.spec)
    assert ref.started_at == world.owner.started_at != '2026-10-13T00:00:00Z'
    assert ref.launch_nonce == world.owner.launch_nonce
    record = world.owner._original_start_receipt_path.read_bytes()
    assert hashlib.sha256(record).hexdigest() == published.start_record_sha256
    assert json.loads(record)['start_result'] == result
    assert world.observations == [world.owner.process.pid] * 2
    assert len(world.authority_checks) == 3
    assert world.owner.result is None and world.owner.failure is None
    assert world.owner._finisher is world.finisher and world.holds == []
    with pytest.raises(producer.OwnedStartRefused, match='already_attempted'):
        producer.publish_owned_start(**world.kwargs())


@pytest.mark.parametrize('field', ['sha256', 'inode', 'size', 'mtime_ns', 'mode'])
def test_wrong_independent_image_pin_refuses_before_retention(world, field):
    value = getattr(world.pin, field)
    world.pin = dataclasses.replace(world.pin, **{field: value + 1 if isinstance(value, int) else '0' * 64})
    with pytest.raises(producer.OwnedStartRefused, match='pinned_binary'):
        producer.publish_owned_start(**world.kwargs())
    assert not world.owner._original_start_receipt_path.exists()
    assert world.owner._finisher is world.finisher


@pytest.mark.parametrize('field', ['start_identity', 'boot_id', 'pgid', 'session_id', 'real_uid', 'effective_gid'])
def test_changed_original_generation_or_principal_refuses(world, field):
    value = world.image[field]
    world.image[field] = value + 1 if isinstance(value, int) else value + '-changed'
    with pytest.raises(producer.OwnedStartRefused, match='owned_image_unqualified'):
        producer.publish_owned_start(**world.kwargs())
    assert not world.owner._original_start_receipt_path.exists()


def test_changed_image_between_validation_and_publication_refuses(world, monkeypatch):
    from control_plane import linux_process_identity
    original = linux_process_identity.inspect_linux_process_image
    count = []
    def changes(pid):
        result = original(pid); count.append(pid)
        if len(count) == 2: result['ctime_ns'] += 1
        return result
    monkeypatch.setattr(linux_process_identity, 'inspect_linux_process_image', changes)
    with pytest.raises(producer.OwnedStartRefused, match='changed_before_publication'):
        producer.publish_owned_start(**world.kwargs())
    assert not world.owner._original_start_receipt_path.exists()


@pytest.mark.parametrize('field', ['command', 'cwd', 'shell', 'prompt_sha256', 'environment_projection_sha256'])
def test_actual_invocation_cannot_be_reconstructed_from_descriptor(world, field):
    world.owner._invocation[field] = 'changed'
    with pytest.raises(producer.OwnedStartRefused, match='original_invocation_changed'):
        producer.publish_owned_start(**world.kwargs())


@pytest.mark.parametrize('fact', sorted(producer._EVIDENCE_KEYS))
def test_named_qualification_inputs_are_required_not_fabricated(world, fact):
    world.evidence.pop(fact)
    with pytest.raises(producer.OwnedStartRefused, match='qualified_evidence_required'):
        producer.publish_owned_start(**world.kwargs())


def test_caller_filenames_do_not_supply_missing_original_capture_producer(world):
    del world.owner._original_capture_paths
    with pytest.raises(producer.OwnedStartRefused, match='original_capture_binding_required'):
        producer.publish_owned_start(**world.kwargs())


def test_expired_command_after_observation_prevents_publication(world, monkeypatch):
    count = []
    def expires(authority, material):
        count.append(material)
        if len(count) == 3: raise producer.OwnedStartRefused('expired_original_command')
    monkeypatch.setattr(producer, '_require_control_authority', expires)
    with pytest.raises(producer.OwnedStartRefused, match='expired_original_command'):
        producer.publish_owned_start(**world.kwargs())
    assert not world.owner._original_start_receipt_path.exists()


def test_durability_failure_keeps_finisher_lease_and_once_only_boundary(world, monkeypatch):
    def failed(fd): raise OSError('inert fsync failure')
    with monkeypatch.context() as scope:
        scope.setattr(LANE.os, 'fsync', failed)
        with pytest.raises(producer.OwnedStartRefused, match='start_retention_failed'):
            producer.publish_owned_start(**world.kwargs())
    assert world.owner._finisher is world.finisher
    assert world.holds == ['owned_start_publication_unconfirmed']
    assert world.owner._start_record_sha256 is None
    with pytest.raises(producer.OwnedStartRefused, match='already_attempted'):
        producer.publish_owned_start(**world.kwargs())


def test_real_authority_guard_does_not_accept_fixture_evidence(world, monkeypatch):
    from control_plane.fabric_control_start import ControlStartAuthority
    assert type(world.kwargs()['authority']) is not ControlStartAuthority
    monkeypatch.setattr(producer, '_require_control_authority', ORIGINAL_AUTHORITY_GUARD)
    with pytest.raises(producer.OwnedStartRefused, match='authenticated_original_owner_required'):
        producer.publish_owned_start(**world.kwargs())
    assert world.observations == []
    assert world.holds == ['owned_start_validation_unconfirmed']


def test_cancelled_publication_preserves_original_exception_owner_and_lease(world, monkeypatch):
    import asyncio
    def cancelled(authority, material): raise asyncio.CancelledError()
    monkeypatch.setattr(producer, '_require_control_authority', cancelled)
    with pytest.raises(asyncio.CancelledError): producer.publish_owned_start(**world.kwargs())
    assert world.holds == ['owned_start_validation_unconfirmed']
    assert world.owner._finisher is world.finisher and world.owner.failure is None
    assert world.owner.result is None and world.owner.process.poll() is None


@pytest.mark.parametrize('field', ['physical_binding_sha256', 'binding', 'launch_spec'])
def test_rewritten_original_request_refuses_before_observation(world, field):
    world.original = copy.deepcopy(world.original)
    if field == 'physical_binding_sha256': world.original[field] = '0' * 64
    elif field == 'binding': world.original[field]['job_id'] = 'different-job'
    else: world.original[field]['prompt'] = 'rewritten prompt'
    with pytest.raises(producer.OwnedStartRefused, match='reserved_request_changed'):
        producer.publish_owned_start(**world.kwargs())
    assert world.observations == [] and world.holds


def test_existing_receipt_is_not_reconstructed_into_start_authority(world):
    world.owner._original_start_receipt_path.write_text('unknown prior retention')
    with pytest.raises(producer.OwnedStartRefused, match='start_retention_failed'):
        producer.publish_owned_start(**world.kwargs())
    assert world.owner._original_start_receipt_path.read_text() == 'unknown prior retention'
    assert world.holds == ['owned_start_publication_unconfirmed']


@pytest.mark.parametrize('base', ['a' * 64, 'a' * 39, 'unknown'])
def test_git_base_is_not_a_generic_sha256_evidence_digest(world, base):
    world.with_spec(expected_base_sha=base)
    world.workspace_identity['git_head'] = base
    with pytest.raises(producer.OwnedStartRefused, match='spec.expected_base_sha'):
        producer.publish_owned_start(**world.kwargs())


@pytest.mark.parametrize('condition', ['missing_preparation', 'dead_child'])
def test_unretained_preparation_and_dead_child_never_publish(world, condition):
    if condition == 'missing_preparation':
        world.owner._original_preparation = None
        reason = 'prepared_descriptor_invalid'
    else:
        world.owner.process._returncode = 0
        reason = 'owned_image_unqualified'
    with pytest.raises(producer.OwnedStartRefused, match=reason):
        producer.publish_owned_start(**world.kwargs())


def test_default_public_path_stays_closed():
    assert producer.main() != 0


def test_plausible_paths_without_original_pinned_capture_files_refuse(world):
    world.owner._capture_reservation.close_fds_only()
    # The inert issuer/image fixture is intentionally otherwise valid. A dict
    # attached to the live owner is still not the original file producer.
    assert world.owner._original_capture_paths == world.capture
    with pytest.raises(producer.OwnedStartRefused, match='capture'):
        producer.publish_owned_start(**world.kwargs())
    assert not world.owner._original_start_receipt_path.exists()
    assert world.owner._finisher is world.finisher
    assert world.owner.process.poll() is None


ORIGINAL_AUTHORITY_GUARD = producer._require_control_authority


