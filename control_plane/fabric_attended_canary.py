"""Fixed per-Attempt probe composition; no admission, process start or lifecycle.

The current environment producer is Darwin/same-host only. A remote Mac PID
cannot be used as an Ubuntu process identity. Missing definitions fail closed.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import sys

from control_plane.executive_canary import AttendedCanaryBinding, SecretCanaryConfig
from control_plane.executive_worker_broker import BrokerStateError

OPERATION = 'attended-secret-canary'
PROFILE = 'fabric.attended.claude.bounded.v1'
BINDING = 'minimax-token-plan.claude-code-anthropic'
PRESET = {'schema_version': 'mastermind.attended_secret_canary_definition/v1',
          'environment_probe': 'darwin-same-host/v1'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _refuse():
    raise BrokerStateError('finite attended probe definition or current owner is unavailable')


def definition(path, physical):
    from control_plane.codex_provider_realm import _native_read_config
    from scripts.executive_os_phase1c_worker import _load_config
    raw = _native_read_config(Path(path), physical.worker_source_config_digest)
    checked = _load_config(Path(path), require_root_owner=True)
    if (checked != raw or raw != _native_read_config(Path(path), physical.worker_source_config_digest)
            or raw.get('attended_secret_canary') != PRESET
            or raw.get('harness_binding_id') != BINDING
            or raw.get('worker_id') != physical.worker_id
            or raw.get('worker_uid') != physical.worker_uid
            or raw.get('worker_gid') != physical.worker_gid
            or raw.get('provider_home') != physical.provider_home
            or physical.provider != 'minimax'):
        _refuse()
    return raw


def binding(spec, physical):
    if (spec.worker_id != physical.worker_id or spec.model != physical.model
            or spec.expected_worker_uid != physical.worker_uid
            or spec.expected_worker_gid != physical.worker_gid
            or spec.require_secret_canary is not True):
        _refuse()
    return AttendedCanaryBinding(spec, PROFILE, BINDING, physical.digest,
                                Path(physical.provider_home))


def host_root(raw):
    """Finite assignments live separately; canary sentinels stay on the real host."""
    home = Path(raw['provider_home'])
    host = home.parents[2]
    jobs = host/'workers'/raw['worker_id']/'jobs'
    if (Path(raw['workspace_root']) != jobs/'workspaces' or Path(raw['run_root']) != jobs/'runs'
            or home != host/'workers'/raw['worker_id']/'provider-home'
            or any('..' in Path(raw[key]).parts or not Path(raw[key]).is_absolute()
                   for key in ('workspace_root', 'run_root', 'provider_home'))):
        _refuse()
    return host


def probe_config(raw, *, release_sha, probe_sha256, control_gid):
    host = host_root(raw)
    home = Path(raw['provider_home'])
    if raw.get('control_gid') != control_gid:
        _refuse()
    return SecretCanaryConfig(expected_worker_uid=raw['worker_uid'],
        expected_worker_gid=raw['worker_gid'], control_uid=raw['control_uid'],
        control_gid=control_gid, control_environment_sentinel='EXECUTIVE_CONTROL_CANARY_VALUE',
        control_environment_probe_sha256=probe_sha256,
        administrative_checkout_sentinel=host/'control/admin-checkout'/release_sha/'.git/executive-secret-canary',
        executive_database=host/'control/db/data/control_plane/executive.sqlite3',
        other_worker_home_sentinel=host/'canary-fixtures/other-worker-home/sentinel',
        forbidden_production_sentinel=host/'canary-fixtures/production-like/sentinel', codex_home=home)


def produce(resources, payload):
    """Use the existing actual environment probe and new open-only V2 producer."""
    from control_plane.codex_provider_realm import SubscriptionRealmOwner
    from control_plane.executive_worker_broker import _launch_spec_from_wire
    from control_plane.executive_canary import run_attended_secret_canary
    from scripts.executive_os_phase1c_worker import _build_autonomy_canary_factory, _ROOT
    from scripts.executive_os_phase1c import _validate_canary_envelope
    if sys.platform != 'darwin':
        _refuse()
    owner = resources.credential_realm_owner
    if (type(owner) is not SubscriptionRealmOwner
            or owner._config_sha256 != resources.physical.worker_source_config_digest
            or payload['physical_binding_sha256'] != resources.physical.digest):
        _refuse()
    raw = definition(owner._config_path, resources.physical)
    observed = owner.observe()
    if observed['realm_config_sha256'] != resources.physical.worker_source_config_digest:
        _refuse()
    spec = _launch_spec_from_wire(payload['launch_spec'], resources.preparation['policy'])
    assigned = binding(spec, resources.physical)
    attestation = payload['control_environment_attestation']
    if (attestation.get('process_identity', {}).get('effective_gid') != raw['control_gid']
            or attestation.get('process_identity', {}).get('real_gid') != raw['control_gid']):
        _refuse()
    # This callback is a closed lexical call to the actual producer. No payload
    # or configuration selects code, command arguments, paths or probe results.
    issue = _build_autonomy_canary_factory(raw, release_root=_ROOT,
        secret_canary_runner=lambda config: run_attended_secret_canary(config, assigned, realm_owner=owner))
    envelope = dict(issue({'control_environment_attestation': attestation}))
    if definition(owner._config_path, resources.physical) != raw or owner.observe() != observed:
        _refuse()
    expected = probe_config(raw, release_sha=_ROOT.name,
        probe_sha256=envelope['control_environment_probe_sha256'], control_gid=raw['control_gid'])
    # Validate all actual environment checks before sending any positive result.
    host = host_root(raw)
    control = dict(raw, runtime_root=str(host/'control/db'),
        proof_source_repository=str(host/'control/admin-checkout'/_ROOT.name),
        worker_provider_home=raw['provider_home'])
    _validate_canary_envelope(envelope, raw=control, control_attestation=attestation,
        attended_config=expected, attended_binding=assigned)
    return dict(adapter_id='attended-fabric', binding=payload['binding'],
        physical_binding_sha256=resources.physical.digest,
        probe_request_sha256=digest(payload), envelope=envelope)


@dataclasses.dataclass(frozen=True)
class AttendedControlProbeSource:
    """One existing root Control definition, reread through its current owner."""
    config_path: Path
    config_sha256: str
    control_attestation_sha256: str
    definition_sha256: str

    @classmethod
    def from_startup(cls, config_path, raw, control_attestation):
        from scripts.executive_os_phase1c import _jsonable
        return cls(Path(config_path), control_attestation['config_sha256'],
                   digest(control_attestation), digest(_jsonable(raw)))

    def require_definition(self, raw):
        from scripts.executive_os_phase1c import _jsonable
        if digest(_jsonable(raw)) != self.definition_sha256:
            _refuse()

    def configuration(self, physical):
        from scripts.executive_os_phase1c import load_control_config, _load_control_environment_attestation
        if sys.platform != 'darwin':
            _refuse()
        raw = load_control_config(self.config_path)
        self.require_definition(raw)
        stanza = raw.get('fabric_attended_probe')
        if type(stanza) is not dict or set(stanza) != {'worker_config_path'}:
            _refuse()
        worker = definition(stanza['worker_config_path'], physical)
        attestation = _load_control_environment_attestation(
            Path(raw['control_environment_attestation_path']), config_path=self.config_path,
            expected_release_sha=raw['proof_base_sha'])
        if (attestation.get('config_sha256') != self.config_sha256
                or digest(attestation) != self.control_attestation_sha256):
            _refuse()
        host_root(worker)
        return raw, worker, attestation

    def snapshot(self, physical, spec):
        raw, worker, attestation = self.configuration(physical)
        # Control's local schema/commission group is not the remote broker's
        # execution principal. Derive only these two fields from the protected
        # worker definition before the probe, launch pin or recovery seal.
        username = worker.get('worker_user')
        if type(username) is not str or not username or any(c.isspace() for c in username):
            _refuse()
        assigned = binding(dataclasses.replace(spec, worker_user=username,
            shared_run_gid=physical.worker_gid), physical)
        return raw, worker, attestation, assigned

    async def native_observation(self, physical):
        """Acquire one fixed, current same-host source observation; never admit.

        No request fields select identity, source, clock, endpoint or callback.
        The incumbent root socket namespace and kernel peer UID bind transport;
        the current root Control/Worker definitions and source pin bind expected
        coordinates. The JSON/hash alone grants no authenticity or availability.
        """
        import secrets
        import time
        from datetime import datetime
        from control_plane.executive_capacity_observation import OBSERVATION_LIFETIME_MS, CLOCK_SKEW_MS
        from control_plane.executive_fabric_adapter import _fixed_client
        from ops.executive_os.capacity_source_contract import (
            acquire_control_native_registration, validate_native_identity_observation,
        )
        from ops.executive_os.host_capacity_probe import current_boot_reference

        snapshot = self.configuration(physical)
        raw, worker, _attestation = snapshot
        stanza = worker.get('native_capacity_enrollment')
        if type(stanza) is not dict:
            _refuse()
        registration = acquire_control_native_registration(self, physical)
        boot = current_boot_reference()
        started_wall = time.time_ns() // 1_000_000
        started_mono = time.monotonic_ns()
        nonce = secrets.token_hex(16)
        # No retry or cache: a failed/ambiguous read remains unavailable.
        result = await _fixed_client(physical).request('native-capacity-observation', {'nonce': nonce})
        finished_wall = time.time_ns() // 1_000_000
        elapsed_ms = (time.monotonic_ns() - started_mono) // 1_000_000
        if (type(result) is not dict or set(result) != {'nonce', 'observation'}
                or result['nonce'] != nonce or not 0 <= elapsed_ms <= OBSERVATION_LIFETIME_MS
                or abs((finished_wall - started_wall) - elapsed_ms) > CLOCK_SKEW_MS):
            _refuse()
        value = validate_native_identity_observation(result['observation'])
        observed_ms = int(datetime.fromisoformat(value['observed_at'].replace('Z', '+00:00')).timestamp()*1000)
        expected = dict(capacity_capability_id=registration['capacity_capability_id'],
            capability_generation=registration['capability_generation'], host_ref=physical.host_ref,
            boot_ref=boot, realm_generation=worker['subscription_realm_enrollment']['generation'],
            source_receipt_digest=registration['source_receipt_digest'])
        enrollment = dict(schema='mastermind.provider_realm_enrollment/v2',
            capacity_capability_id=registration['capacity_capability_id'],
            capability_generation=registration['capability_generation'],
            realm_generation=expected['realm_generation'], provider_family='minimax',
            product='claude-code', execution_surface='native_cli', auth_family='minimax_subscription_api_key',
            **{key: stanza[key] for key in ('host_ref', 'os_principal_ref', 'config_custody_ref', 'enrollment_state')},
            registration_receipt_digest=registration['registration_receipt_digest'],
            source_receipt_digest=registration['source_receipt_digest'],
            receipt_id='realm-'+hashlib.sha256((physical.worker_source_config_digest+
                registration['registration_receipt_digest']).encode()).hexdigest())
        expected['enrollment_receipt_digest'] = digest(enrollment)
        if (any(value[key] != expected_value for key, expected_value in expected.items())
                or not finished_wall-OBSERVATION_LIFETIME_MS-CLOCK_SKEW_MS <= observed_ms <= finished_wall+CLOCK_SKEW_MS
                or value['host_ref'] != stanza['host_ref']
                or acquire_control_native_registration(self, physical) != registration
                or self.configuration(physical) != snapshot or current_boot_reference() != boot):
            _refuse()
        # Owner revalidation itself may block. Do not return a once-fresh read
        # after its complete acquisition interval has expired or its clock moved.
        final_wall = time.time_ns() // 1_000_000
        total_ms = (time.monotonic_ns()-started_mono) // 1_000_000
        if (not 0 <= total_ms <= OBSERVATION_LIFETIME_MS
                or abs((final_wall-started_wall)-total_ms) > CLOCK_SKEW_MS
                or not final_wall-OBSERVATION_LIFETIME_MS-CLOCK_SKEW_MS <= observed_ms <= final_wall+CLOCK_SKEW_MS):
            _refuse()
        return value

    def validate(self, snapshot, result):
        from scripts.executive_os_phase1c import _validate_canary_envelope
        raw, worker, attestation, assigned = snapshot
        expected = probe_config(worker, release_sha=attestation['release_commit_sha'],
            probe_sha256=result['envelope']['control_environment_probe_sha256'],
            control_gid=attestation['process_identity']['effective_gid'])
        return _validate_canary_envelope(result['envelope'], raw=raw,
            control_attestation=attestation, attended_config=expected, attended_binding=assigned)
