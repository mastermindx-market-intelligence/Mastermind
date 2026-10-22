"""Inert reference preparation for the existing fixed finite root publisher.

The root configuration owner, not a realm probe or request, owns publication.
These candidate bytes establish no identity until that owner publishes them in
the existing immutable Worker.json and matching Fabric binding. There is no
store, host discovery, credential read, enrollment grant or Runtime effect here.
"""
from __future__ import annotations

import re
import secrets

from ops.executive_os.capacity_source_contract import (
    validate_native_subscription_capacity_enrollment,
)

_REFS = {'host_ref': 'host', 'os_principal_ref': 'principal',
         'config_custody_ref': 'custody'}
_WORKER = 'minimax-finite-01'
_HOME = '/private/var/db/mastermind-executive/workers/' + _WORKER + '/provider-home'
_BINDING = 'minimax-token-plan.claude-code-anthropic'


class FiniteReferenceError(ValueError):
    pass


def _refuse():
    raise FiniteReferenceError('FINITE_REFERENCE_ASSIGNMENT_UNAVAILABLE')


def _reference(value, prefix):
    if type(value) is not str or re.fullmatch(prefix + r'-[0-9a-f]{64}', value) is None:
        _refuse()
    return value


def _new_reference(prefix):
    value = secrets.token_hex(32)
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        _refuse()
    return prefix + '-' + value


def require_initial_reference_context(control, primary, physical_policy):
    """Refuse an incumbent coordinate; never overwrite it with initial refs.

    The root publisher supplies its actual protected config reads and the
    existing validated physical policy. This is not their authentication step.
    The host's ordinary primary and Control definitions remain unchanged.
    """
    if any(type(value) is not dict for value in (control, primary, physical_policy)):
        _refuse()
    reserved = {*_REFS, 'native_realm_enrollment', 'native_capacity_enrollment',
                'fabric_bindings_path', 'fabric_attended_probe'}
    if any(reserved.intersection(value) for value in (control, primary)):
        _refuse()
    runtime = physical_policy.get('canonical_runtime')
    if (type(runtime) is not dict or 'host_id' not in runtime or runtime['host_id'] is not None
            or physical_policy.get('qualification') != 'UNQUALIFIED'
            or physical_policy.get('production_armed') is not False
            or physical_policy.get('host_qualifications', []) != []):
        _refuse()


def prepare_finite_reference_stanza(*, registration_source, realm_generation,
        previous_worker=None, existing_host_ref=None):
    """Prepare the fixed publisher's initial or retained *unenrolled* stanza.

    The invoking root publisher must first qualify the actual installed source,
    same physical host, dedicated principal, private HOME and current disarm.
    For initial publication it must prove its fixed destination absent and
    reconcile all existing selected host coordinates. ``existing_host_ref`` is
    that owner's admitted coordinate, never a label or a discovery fallback.

    If there is no incumbent coordinate, only the fixed first-publication path
    may use this constructor. Its exclusive directory/file publication makes
    the retained Worker.json the reference anchor. Every later generation must
    supply that protected predecessor; absence after publication is an unknown
    effect to reconcile, not permission to enter the initial branch again.

    ``previous_worker`` must be acquired through the existing protected reader
    and exact physical/config-digest binding. This pure function cannot qualify
    caller dictionaries. It retains coordinates across a same or next realm
    generation and never upgrades provider enrollment, even from an enrolled
    predecessor. Existing publisher custody and no-replay rules remain intact.
    """
    if type(realm_generation) is not int or not 1 <= realm_generation < 2**63:
        _refuse()
    if existing_host_ref is not None:
        _reference(existing_host_ref, 'host')
    if previous_worker is None:
        if realm_generation != 1:
            _refuse()
        references = {key: (existing_host_ref if key == 'host_ref' and existing_host_ref is not None
                           else _new_reference(prefix))
                      for key, prefix in _REFS.items()}
    else:
        if type(previous_worker) is not dict:
            _refuse()
        expected = {
            'schema_version': 'mastermind.executive_worker_broker_config/v5',
            'worker_id': _WORKER, 'worker_user': '_mastermind_minimax',
            'worker_uid': 470, 'worker_gid': 470, 'control_uid': 450,
            'control_gid': 450, 'provider_home': _HOME,
            'harness_binding_id': _BINDING,
        }
        if any(type(previous_worker.get(key)) is not type(value)
               or previous_worker[key] != value for key, value in expected.items()):
            _refuse()
        generation = previous_worker.get('subscription_realm_enrollment')
        if (type(generation) is not dict or set(generation) != {'generation', 'binding_id'}
                or generation['binding_id'] != _BINDING
                or type(generation['generation']) is not int
                or not 1 <= generation['generation'] < 2**63
                or realm_generation not in (generation['generation'], generation['generation'] + 1)):
            _refuse()
        try:
            prior = validate_native_subscription_capacity_enrollment(
                previous_worker.get('native_capacity_enrollment'))
        except ValueError:
            _refuse()
        references = {key: prior[key] for key in _REFS}
        if existing_host_ref is not None and references['host_ref'] != existing_host_ref:
            _refuse()
    for key, prefix in _REFS.items():
        _reference(references[key], prefix)
    # A broken randomness source must not silently alias the three coordinates.
    if len({value.split('-', 1)[1] for value in references.values()}) != len(_REFS):
        _refuse()
    try:
        return validate_native_subscription_capacity_enrollment({
            'schema_version': 'mastermind.native_subscription_capacity_enrollment/v1',
            **references, 'enrollment_state': 'unenrolled',
            'registration_source': registration_source,
        })
    except ValueError:
        _refuse()
