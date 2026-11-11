"""Initial publication cannot invent a replacement for an incumbent identity."""
from copy import deepcopy

import pytest

from ops.executive_os.finite_reference_assignment import (
    FiniteReferenceError, require_initial_reference_context,
)


def context():
    # Explicit pure fixtures; not a host enrollment or installed configuration.
    return ({'proof_base_sha': 'a' * 40}, {'operator_harness_armed': False},
            {'canonical_runtime': {'host_id': None}, 'qualification': 'UNQUALIFIED',
             'production_armed': False, 'host_qualifications': []})


def test_empty_initial_context_is_inert_and_unchanged():
    values = context()
    before = deepcopy(values)
    assert require_initial_reference_context(*values) is None
    assert values == before


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('field', [
    'host_ref', 'os_principal_ref', 'config_custody_ref', 'native_realm_enrollment',
    'native_capacity_enrollment', 'fabric_bindings_path', 'fabric_attended_probe',
])
def test_even_unresolved_incumbent_fields_refuse_initial_assignment(index, field):
    values = context()
    values[index][field] = None
    with pytest.raises(FiniteReferenceError):
        require_initial_reference_context(*values)


@pytest.mark.parametrize('change', [
    {'canonical_runtime': {'host_id': 'host-' + 'a' * 64}},
    {'canonical_runtime': {}}, {'canonical_runtime': None},
    {'qualification': 'QUALIFIED'}, {'qualification': None},
    {'production_armed': True}, {'production_armed': 0},
    {'host_qualifications': [{'host_id': 'host-' + 'b' * 64}]},
    {'host_qualifications': None},
])
def test_existing_or_unqualified_policy_context_cannot_mint_replacement(change):
    control, primary, policy = context()
    policy.update(change)
    with pytest.raises(FiniteReferenceError):
        require_initial_reference_context(control, primary, policy)


@pytest.mark.parametrize('index', [0, 1, 2])
@pytest.mark.parametrize('bad', [None, [], True])
def test_nonmapping_context_refuses(index, bad):
    values = list(context())
    values[index] = bad
    with pytest.raises(FiniteReferenceError):
        require_initial_reference_context(*values)
