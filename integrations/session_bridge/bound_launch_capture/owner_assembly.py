"""Fixed, owner-injected attended service composition using existing readers.

Only the installation owner supplies these arguments, never RPC/configured
Python or environment selectors. This composes no admission and reads no secret
bytes. The default CLI remains closed. Real root-installed definitions, worker
enrollment, binary and credential custody must already exist on the worker host.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
import re
import threading

from control_plane import codex_provider_realm as realm
from control_plane import executive_fabric_bridge_broker as bridge
from control_plane import fabric_attended_canary as canary
from control_plane.executive_fabric_composition import FabricBindingSource
from control_plane.fabric_attended_claude import (
    MAX_TURNS_LIMIT, _reviewed_binary, _reviewed_binding_and_profile, _reviewed_model,
    finite_read_permission_digest,
)
from control_plane.subscription_catalog import compose_catalog_digest, get_binding
from control_plane.subscription_harness_bindings import load_bindings
from control_plane.subscription_provider_profiles import get_profile, load_profiles
from integrations.session_bridge.bound_launch_capture.fabric_attended_backend import (
    _FixedOwnerResources, create_attended_backend,
)
from scripts.executive_os_phase1c_worker import _broker_policy


def _refuse():
    raise bridge.BridgeProtocolError('OwnerResourceMismatch',
        'Fixed attended resources are unavailable or changed; no automatic retry')


def compose_owner_resources(config, *, config_path, bindings_path, bindings_sha256,
                            realm_config_path, host_ref, worker_id,
                            routing_root_id, routing_parent_run_id, active_dir,
                            model_class, max_turns, verified_release_manifest_sha256, credential_loader, nice=0):
    """Derive static preparation from pinned definitions, not arbitrary kwargs.

    The loader is the actual owner's existing private credential callable. It is
    retained without invocation. Realm enrollment observes custody metadata;
    actual START independently rechecks grant, canary, assignment and catalogue.
    Root/parent here are transport correlation, never identity or budget grants.
    """
    if (threading.current_thread() is not threading.main_thread()
            or type(config) is not bridge.BridgeConfig
            or config._trust is not bridge._TRUSTED_CONFIG
            or not callable(credential_loader)
            or type(max_turns) is not int or not 1 <= max_turns <= MAX_TURNS_LIMIT
            or type(nice) is not int or not 0 <= nice <= 19
            or config.validation_commands):
        _refuse()
    for value in (routing_root_id, routing_parent_run_id):
        if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) is None:
            _refuse()
    active_dir = Path(active_dir)
    if not active_dir.is_absolute() or '..' in active_dir.parts:
        _refuse()
    config_path, realm_config_path = Path(config_path), Path(realm_config_path)
    if bridge.load_config(config_path) != config:
        _refuse()
    source = FabricBindingSource.from_path(bindings_path, bindings_sha256)
    physical = source(host_ref, worker_id)
    # The fixed entry supplies this only AFTER verifying its sealed release.
    # This is service-source identity, distinct from binary/profile digests.
    if (type(verified_release_manifest_sha256) is not str
            or re.fullmatch(r'[0-9a-f]{64}', verified_release_manifest_sha256) is None
            or physical.service_source_sha256 != verified_release_manifest_sha256
            or physical.permission_profile_sha256 != finite_read_permission_digest()):
        _refuse()
    raw = canary.definition(realm_config_path, physical)
    # Use the original worker policy constructor and require its finite
    # assignment seal. Non-isolated supplementary groups remain a refusal.
    policy = dataclasses.replace(_broker_policy(raw), require_assignment_seal=True)
    if (config.bridge_uid != physical.worker_uid or physical.bridge_uid != physical.worker_uid
            or config.control_uid != policy.control_uid
            or policy.worker_uid != physical.worker_uid or policy.worker_gid != physical.worker_gid
            or policy.worker_id != physical.worker_id or policy.provider_home != Path(physical.provider_home)
            or config.socket_path != Path(physical.socket_path)
            or config.workspace_root != policy.workspace_root or config.run_root != policy.run_root):
        _refuse()
    profiles = load_profiles()
    bindings = load_bindings(profiles_document=profiles)
    binding = get_binding(canary.BINDING, document=bindings, profiles_document=profiles)
    profile = get_profile(binding.profile_id, document=profiles)
    _reviewed_binding_and_profile(binding, profile)
    if (binding.implementation_state == 'SPEC_ONLY' or binding.autonomous_allowed
            or profile.autonomous_allowed or binding.provider != physical.provider
            or _reviewed_model(binding, profile, model_class) != physical.model):
        _refuse()
    catalog_sha = compose_catalog_digest(bindings_document=bindings, profiles_document=profiles)
    owner = realm.load_subscription_realm_owner(realm_config_path,
        expected_config_sha256=physical.worker_source_config_digest)
    observation = owner.observe()
    native_enrollment = None
    if 'native_capacity_enrollment' in raw:
        native_enrollment = owner.observe_capacity_enrollment()
        if (native_enrollment['host_ref'] != physical.host_ref
                or native_enrollment['capacity_capability_id'] != raw.get('capacity_capability_id')
                or native_enrollment['realm_generation'] != observation['realm_generation']):
            _refuse()
    if (observation['worker_id'] != physical.worker_id
            or observation['control_uid'] != config.control_uid
            or observation['realm_config_sha256'] != physical.worker_source_config_digest
            or observation['binding_id'] != binding.binding_id
            or observation['profile_id'] != profile.profile_id
            or observation['adapter_id'] != binding.adapter_id
            or observation['catalog_digest'] != catalog_sha):
        _refuse()
    # Reuse the protected attestation validator; keep observe()'s exact eight
    # fields, which are consumed by the retained START contract.
    binary = realm._observe_attended_claude_binary(raw, physical.worker_gid)
    _reviewed_binary(binary)
    if binary.sha256 != physical.binary_sha256:
        _refuse()
    preparation = dict(policy=policy, binary=binary, binding=binding, profile=profile,
        model_class=model_class, max_turns=max_turns, allowed_validation_commands=())
    resources = _FixedOwnerResources(preparation=preparation, physical=physical,
        binary_pin=binary, routing_root_id=routing_root_id,
        routing_parent_run_id=routing_parent_run_id, active_dir=active_dir, nice=nice,
        credential_loader=credential_loader, credential_realm_owner=owner,
        credential_bindings_document=bindings, credential_profiles_document=profiles)
    if (source(host_ref, worker_id) != physical
            or canary.definition(realm_config_path, physical) != raw
            or (native_enrollment is not None and owner.observe_capacity_enrollment() != native_enrollment)
            or owner.observe() != observation
            or realm._observe_attended_claude_binary(raw, physical.worker_gid) != binary
            or compose_catalog_digest() != catalog_sha
            or bridge.load_config(config_path) != config):
        _refuse()
    return resources


def run_owner_bridge(*, config_path, bindings_path, bindings_sha256,
                     realm_config_path, host_ref, worker_id, routing_root_id,
                     routing_parent_run_id, active_dir, model_class, max_turns,
                     verified_release_manifest_sha256, credential_loader, nice=0):
    """Actual fixed caller of existing main; no new listener or event loop owner.

    main supplies the config it just authenticated. Resources are assembled on
    that exact invocation, then existing serve activates the original socket.
    The real per-assignment controller is constructed later on its main loop.
    No callable/module can be selected by command line, JSON or environment.
    """
    from scripts.executive_fabric_bridge import main
    def fixed_factory(config):
        resources = compose_owner_resources(config, config_path=config_path,
            bindings_path=bindings_path, bindings_sha256=bindings_sha256,
            realm_config_path=realm_config_path, host_ref=host_ref, worker_id=worker_id,
            routing_root_id=routing_root_id, routing_parent_run_id=routing_parent_run_id,
            active_dir=active_dir, model_class=model_class, max_turns=max_turns,
            verified_release_manifest_sha256=verified_release_manifest_sha256,
            credential_loader=credential_loader, nice=nice)
        return create_attended_backend(config, owner_resources=resources)
    return main(['serve', '--config', str(config_path)], backend_factory=fixed_factory)


def run_private_owner_bridge(*, config_path, bindings_path, bindings_sha256,
                             realm_config_path, host_ref, worker_id, routing_root_id,
                             routing_parent_run_id, active_dir, model_class, max_turns,
                             verified_release_manifest_sha256, nice=0):
    """Installed fixed caller; bind the existing private loader without reading it.

    The root-owned installation entry supplies only literal data. No configured
    module, callable, credential path or environment variable selects code.
    Existing protected definitions own the worker identity and private HOME.
    """
    source = FabricBindingSource.from_path(bindings_path, bindings_sha256)
    physical = source(host_ref, worker_id)
    raw = canary.definition(realm_config_path, physical)

    def credential_loader():
        # Recheck the original definition before opening the existing private
        # credential at the actual launch boundary, never during assembly.
        if (source(host_ref, worker_id) != physical
                or canary.definition(realm_config_path, physical) != raw):
            _refuse()
        return realm.load_private_provider_credential(Path(raw['provider_home']),
            expected_uid=raw['worker_uid'], expected_gid=raw['worker_gid'])

    return run_owner_bridge(config_path=config_path, bindings_path=bindings_path,
        bindings_sha256=bindings_sha256, realm_config_path=realm_config_path,
        host_ref=host_ref, worker_id=worker_id, routing_root_id=routing_root_id,
        routing_parent_run_id=routing_parent_run_id, active_dir=active_dir,
        model_class=model_class, max_turns=max_turns,
        verified_release_manifest_sha256=verified_release_manifest_sha256,
        credential_loader=credential_loader, nice=nice)
