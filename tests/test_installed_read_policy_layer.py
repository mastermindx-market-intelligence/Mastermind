"""Private installed OAuth pairing remains exact and is revalidated on use."""
import dataclasses
from types import SimpleNamespace
import pytest
from control_plane.installed_principal_read_binding import trusted_read_pair
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.session_bridge.runtime_return import _trusted_read_pair
from tests import test_mastermind_executive_app_asgi as auth


def policies():
    return AppPolicies(read=auth._read_policy(), submit=auth._submit_policy())


def test_core_pair_uses_the_incumbent_exact_policy_parser_on_demand():
    value = policies()
    assert trusted_read_pair(value) == _trusted_read_pair(value)
    assert trusted_read_pair(None) is None


@pytest.mark.parametrize('damage', ['duck', 'subclass', 'read-replaced', 'validator-replaced', 'mixed-resource'])
def test_unissued_or_changed_pair_never_substitutes_for_actual_installed_policies(damage):
    value = policies()
    if damage == 'duck':
        value = SimpleNamespace(read=value.read, submit=value.submit)
    elif damage == 'subclass':
        class Foreign(AppPolicies):
            pass
        value = Foreign(read=value.read, submit=value.submit)
    elif damage == 'read-replaced':
        object.__setattr__(value, 'read', auth._read_policy())
    elif damage == 'validator-replaced':
        token = dataclasses.replace(value._installed_read_pair, validator=lambda owner: (owner.read, owner.submit))
        object.__setattr__(value, '_installed_read_pair', token)
    else:
        # AppPolicies historically checks scopes at construction; selecting a
        # mismatched pair still fails at the old parser boundary, not earlier.
        value = AppPolicies(read=value.read, submit=dataclasses.replace(value.submit, resource='https://other.invalid/mcp'))
    with pytest.raises((TypeError, ValueError)):
        trusted_read_pair(value)


def test_unissued_owner_attribute_hook_is_not_executed():
    calls = []
    class ForeignOwner:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError('unissued owner callback was reached')
    with pytest.raises(TypeError):
        trusted_read_pair(ForeignOwner())
    assert calls == []
