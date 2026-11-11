"""Declarative launch bindings in the existing per-profile plugin registry."""
from __future__ import annotations

import copy
import os
from contextlib import nullcontext
from contextvars import ContextVar
from pathlib import Path
from threading import RLock

from agent.launch_credential_binding import (
    CAPABILITY, PRIVATE_FIELD, LaunchCredentialError, collect, declaration, digest,
)

REQUIRED_BINDING_ENV = 'HERMES_REQUIRED_LAUNCH_BINDING'
_launch_witness = None
_launch_witness_lock = RLock()
_validating_launch_destinations = ContextVar('validating_launch_destinations', default=False)


def _owned_declaration(manifest, binding_id):
    from hermes_cli.plugins_manifest import manifest_key
    raw = manifest.launch_credentials.get(binding_id)
    if raw is None:
        raise LaunchCredentialError('launch_credentials_declaration_missing')
    parsed = declaration(binding_id, raw)
    # Client and local server must agree on the exact manifest owner as well as its spec.
    parsed['plugin_owner'] = {'key': manifest_key(manifest), 'source': manifest.source,
                              'path': str(Path(manifest.path).resolve()) if manifest.path else ''}
    return parsed


def manifest_declarations(*, home=None):
    """Use the incumbent import-free manifest scanner and enable/disable precedence."""
    from agent.safe_worker_policy import safe_worker_enabled
    from hermes_cli.plugins_discovery import (
        _get_disabled_plugins, _get_enabled_plugins, collect_directory_manifests,
        gate_manifest, resolve_manifest_winners, suppress_plugin_discovery,
    )
    from hermes_cli.plugins_loader import _plugin_home_scope
    from hermes_cli.plugins_manifest import requires_hermes_error
    from utils import env_var_enabled
    if safe_worker_enabled() or env_var_enabled('HERMES_SAFE_MODE'):
        return {}
    with (_plugin_home_scope(home) if home is not None else nullcontext()), suppress_plugin_discovery():
        winners = resolve_manifest_winners(collect_directory_manifests())
        disabled, enabled = _get_disabled_plugins(), _get_enabled_plugins()
        found = {}
        for key, manifest in winners.items():
            if (manifest.kind != 'standalone' or manifest.source not in {'bundled', 'user'}
                    or gate_manifest(manifest, disabled, enabled).action != 'load'
                    or requires_hermes_error(manifest)):
                continue
            for binding_id in manifest.launch_credentials:
                if binding_id in found:
                    raise LaunchCredentialError('ambiguous_launch_credentials_binding')
                found[binding_id] = {'plugin_key': key,
                                     'declaration': _owned_declaration(manifest, binding_id)}
        return found


def _selected_launch_binding(environ=None):
    """Freeze ambient launch metadata, never values, before any child can inherit env."""
    global _launch_witness
    from hermes_constants import get_routing_process_hermes_home
    environment = os.environ if environ is None else environ
    required = environment.get(REQUIRED_BINDING_ENV)
    with _launch_witness_lock:
        previous = _launch_witness if environ is None else None
    if required is None:
        if previous is not None:
            raise LaunchCredentialError('launch_credentials_owner_changed')
        return None
    if not isinstance(required, str):
        raise LaunchCredentialError('launch_credentials_plugin_unavailable')
    home = get_routing_process_hermes_home().resolve()
    entry = manifest_declarations(home=home).get(required)
    if entry is None:
        raise LaunchCredentialError('launch_credentials_plugin_unavailable')
    spec = entry['declaration']
    witness = (str(home), required, digest(spec), _child_secret_names(spec))
    if environ is None:
        with _launch_witness_lock:
            if _launch_witness is not None and _launch_witness != witness:
                raise LaunchCredentialError('launch_credentials_owner_changed')
            _launch_witness = witness
    return entry


def register(context, binding_id, spec=None):
    parsed = _owned_declaration(context.manifest, binding_id)
    expected = manifest_declarations(home=context._manager.home_path).get(binding_id)
    if (expected is None or expected['plugin_key'] != context.plugin_id
            or digest(parsed) != digest(expected['declaration'])):
        raise LaunchCredentialError('launch_credentials_owner_changed')
    if spec is not None:
        supplied = declaration(binding_id, spec)
        supplied['plugin_owner'] = parsed['plugin_owner']
        if digest(supplied) != digest(parsed):
            raise LaunchCredentialError('launch_credentials_declaration_changed')
    manager = context._manager
    if not hasattr(manager, '_launch_credential_bindings'):
        manager._launch_credential_bindings = {}
    current = manager._launch_credential_bindings.get(binding_id)
    if current is not None and current['plugin_key'] != context.plugin_id:
        raise LaunchCredentialError('ambiguous_launch_credentials_binding')
    entry = {'plugin_key': context.plugin_id, 'declaration': parsed}
    return context._register_entry(
        'launch_credentials', binding_id, manager._launch_credential_bindings, entry,
        'Plugin %s registered finite launch binding: %s', binding_id)


def _registered_entries():
    from hermes_cli.plugins import discover_plugins, get_plugin_manager
    discover_plugins()
    return getattr(get_plugin_manager(), '_launch_credential_bindings', {})


def declarations():
    return {name: copy.deepcopy(entry['declaration']) for name, entry in _registered_entries().items()}


def declaration_for(binding_id):
    expected = manifest_declarations().get(binding_id)
    if expected is None:
        raise LaunchCredentialError('launch_credentials_plugin_unavailable')
    loaded = _registered_entries().get(binding_id)
    if (loaded is None or loaded['plugin_key'] != expected['plugin_key']
            or digest(loaded['declaration']) != digest(expected['declaration'])):
        raise LaunchCredentialError('launch_credentials_plugin_unavailable')
    spec = expected['declaration']
    assert_tool_destinations(spec)
    return spec


def assert_tool_destinations(spec):
    """Use fresh incumbent metadata; run grants cannot replace provider/runtime custody."""
    try:
        from tools.environments import local_env_policy
        from providers import list_providers
        reserved = set(local_env_policy._build_provider_env_blocklist())
        reserved.update(local_env_policy._registered_adapter_secret_env())
        reserved.update(local_env_policy._ALWAYS_STRIP_FOLDED)
        for provider in list_providers():
            reserved.update(provider.env_vars)
            if provider.base_url_env_var:
                reserved.add(provider.base_url_env_var)
        reserved = {name.upper() for name in reserved}
        for name in _child_secret_names(spec):
            if (name.startswith('HERMES_') or name in reserved
                    or local_env_policy._is_hermes_internal_secret(name)):
                raise LaunchCredentialError('launch_credentials_destination_owned')
    except LaunchCredentialError:
        raise
    except Exception:  # health: allow BLE001 -- provider metadata failure must deny ownership without exposing exception values
        raise LaunchCredentialError('launch_credentials_ownership_unavailable') from None


def collect_launch_credentials(environ=None):
    environment = os.environ if environ is None else environ
    entry = _selected_launch_binding(environ)
    if entry is None:
        return None
    spec = entry['declaration']
    _assert_launch_destinations(spec)
    payload = collect(spec, environment)
    if payload is None:
        raise LaunchCredentialError('launch_credentials_context_missing')
    return payload


def launch_parameters(parameters, capabilities, *, environ=None):
    """An old gateway refuses a required binding before any prompt submission."""
    from hermes_cli.gateway_client import GatewayClientError
    try:
        payload = collect_launch_credentials(environ)
        if payload is None:
            return {}
        if PRIVATE_FIELD not in parameters or CAPABILITY not in (capabilities or ()):
            raise LaunchCredentialError('gateway_launch_credentials_unsupported')
        return {PRIVATE_FIELD: payload}
    except LaunchCredentialError as exc:
        raise GatewayClientError(str(exc)) from None


def refuse_launch_resume():
    from hermes_cli.gateway_client import GatewayClientError
    if collect_launch_credentials() is not None:
        raise GatewayClientError('launch_credentials_require_fresh_session')


def verify_required_binding():
    """Run before any gateway connection/autostart, without exposing private values."""
    from hermes_cli.gateway_client import GatewayClientError
    try:
        collect_launch_credentials()
    except LaunchCredentialError as exc:
        raise GatewayClientError(str(exc)) from None


def verify_fresh_launch(continuing):
    verify_required_binding()
    if continuing:
        refuse_launch_resume()


def launch_secret_names(*, environ=None):
    """Freeze the exact removal set without discovering/importing plugin implementations."""
    entry = _selected_launch_binding(environ)
    if entry is None:
        return frozenset()
    _assert_launch_destinations(entry['declaration'])
    return _child_secret_names(entry['declaration'])


def _assert_launch_destinations(spec):
    """Classify at the launch origin; metadata cannot recursively start a child."""
    from hermes_constants import get_routing_process_hermes_home
    from hermes_cli.plugins_discovery import suppress_plugin_discovery
    from hermes_cli.plugins_loader import _plugin_home_scope
    if _validating_launch_destinations.get():
        raise LaunchCredentialError('launch_credentials_ownership_unavailable')
    token = _validating_launch_destinations.set(True)
    try:
        with _plugin_home_scope(get_routing_process_hermes_home()), suppress_plugin_discovery():
            assert_tool_destinations(spec)
    finally:
        _validating_launch_destinations.reset(token)


def _child_secret_names(spec):
    return frozenset(item['env'] for item in spec['credentials']) | frozenset(spec['withheld_env'])


def strip_child_credentials(environment, names):
    """Removal only; keep the incumbent profile/provider environment policy intact."""
    stripped = dict(environment)
    for name in (*names, REQUIRED_BINDING_ENV):
        stripped.pop(name, None)
    return stripped


def strip_daemon_credentials(environment):
    return strip_child_credentials(environment, launch_secret_names(environ=environment))
