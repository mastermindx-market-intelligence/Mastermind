"""Native-provider contract regressions; no provider/model acceptance claims."""
from __future__ import annotations
import copy
import json
import re
from pathlib import Path

import pytest

from integrations.native_context.adapter import (
    Binding, IntegrationConflict, ReaderResult, compose_fragment, hook_fragment,
    render_hook,
)
from integrations.native_context.bridge import CanonicalBootReader

BINDING = Binding('EXAMPLE-CONTEXT', Path('/qualified/Macro'), 'a' * 40, 'b' * 40,
                  'agentos/handoffs/OLD-ASSIGNMENT.md')
EVENT = b'{"hook_event_name":"SessionStart","source":"startup"}'


def text(out):
    return out['hookSpecificOutput']['additionalContext']


@pytest.mark.parametrize('bound', [None, BINDING])
@pytest.mark.parametrize('hydrate', [False, True])
def test_claude_fork_gets_orientation_without_inheriting_assignment(bound, hydrate):
    def must_not_run(*args):
        pytest.fail('fork reused the parent reader')
    out = render_hook(b'{"hook_event_name":"SessionStart","source":"fork"}',
                      provider='claude', binding=bound, hydrate=hydrate,
                      reader=must_not_run)
    body = text(out)
    assert 'FORK_REQUIRES_REBIND' in body
    assert 'EXAMPLE-CONTEXT' not in body
    assert 'OLD-ASSIGNMENT' not in body
    assert 'No parent workstream payload' in body


def test_codex_fork_is_not_invented_as_a_supported_event():
    assert render_hook(b'{"hook_event_name":"SessionStart","source":"fork"}',
                       provider='codex', binding=BINDING, hydrate=True,
                       reader=lambda *a: pytest.fail('unsupported read')) == {}


@pytest.mark.parametrize('provider', ['codex', 'claude'])
def test_fragment_matches_only_the_documented_provider_sources(provider):
    item = hook_fragment(provider=provider, python=Path('/python'),
                         script=Path('/release/hook.py'))['hooks']['SessionStart'][0]
    for source in ['startup', 'resume', 'clear', 'compact']:
        assert re.fullmatch(item['matcher'], source)
    assert bool(re.fullmatch(item['matcher'], 'fork')) == (provider == 'claude')


def test_codex_fragment_prevents_second_silent_truncation_after_our_hard_byte_cap():
    fragment = hook_fragment(provider='codex', python=Path('/python'),
                             script=Path('/release/hook.py'))
    handler = fragment['hooks']['SessionStart'][0]['hooks'][0]
    assert type(handler.get('additionalContextLimit')) is int
    assert handler['additionalContextLimit'] == 0
    assert compose_fragment({}, fragment) == fragment


def test_claude_fragment_does_not_receive_codex_only_setting():
    fragment = hook_fragment(provider='claude', python=Path('/python'),
                             script=Path('/release/hook.py'))
    assert 'additionalContextLimit' not in fragment['hooks']['SessionStart'][0]['hooks'][0]
    assert compose_fragment({}, fragment) == fragment


@pytest.mark.parametrize('value', [False, True, -1, 1, 2500, '0', None])
def test_fragment_cannot_relax_closed_codex_output_contract(value):
    fragment = hook_fragment(provider='codex', python=Path('/python'),
                             script=Path('/release/hook.py'))
    fragment['hooks']['SessionStart'][0]['hooks'][0]['additionalContextLimit'] = value
    with pytest.raises(IntegrationConflict):
        compose_fragment({}, fragment)


def test_new_provider_definition_requires_reconciling_old_registration():
    original = {'hooks': {'SessionStart': [{'matcher':'startup|resume|clear|compact',
                  'hooks':[{'type':'command', 'command':'/python -I -B /release/hook.py --provider claude'}]}]}}
    before = copy.deepcopy(original)
    new = hook_fragment(provider='claude', python=Path('/python'),script=Path('/release/hook.py'))
    with pytest.raises(IntegrationConflict):
        compose_fragment(original, new)
    assert original == before


@pytest.mark.parametrize('mode', ['nonzero', 'exception'])
def test_uncertain_upstream_reader_failure_does_not_become_generic_unavailability(mode):
    def main(_):
        if mode == 'exception':
            raise RuntimeError('PRIVATE PROCESS DIAGNOSTIC')
        return 1  # The canonical CLI also returns 1 when its cleanup cannot be established.
    reader = CanonicalBootReader(root=Path('/release'), main=main,
                                 git_sha=lambda _: 'b'*40)
    out = render_hook(EVENT, provider='codex', binding=BINDING,
                      hydrate=True, reader=reader)
    body = text(out)
    assert 'READER_RECONCILIATION_REQUIRED' in body
    assert 'do not start another reader' in body
    assert 'PRIVATE PROCESS DIAGNOSTIC' not in body


def test_pre_dispatch_reader_pin_mismatch_remains_non_dispatch_unavailability():
    reader = CanonicalBootReader(root=Path('/release'), main=lambda a: pytest.fail('ran'),
                                 git_sha=lambda _: 'c'*40)
    body = text(render_hook(EVENT,provider='codex',binding=BINDING,hydrate=True,reader=reader))
    assert 'READER_UNAVAILABLE' in body
    assert 'READER_RECONCILIATION_REQUIRED' not in body


def test_arbitrary_reader_diagnostic_cannot_be_promoted_to_context():
    out = render_hook(EVENT,provider='codex',binding=BINDING,hydrate=True,
                      reader=lambda *a: ReaderResult(False,reason='PRINT_PRIVATE_SECRET'))
    assert 'PRINT_PRIVATE_SECRET' not in text(out)


def test_idempotence_cannot_skip_validation_via_bool_integer_equality():
    valid = hook_fragment(provider='codex', python=Path('/python'), script=Path('/release/hook.py'))
    malformed = copy.deepcopy(valid)
    malformed['hooks']['SessionStart'][0]['hooks'][0]['additionalContextLimit'] = False
    # Python considers False == 0, but the native configuration schema does not.
    with pytest.raises(IntegrationConflict):
        compose_fragment(valid, malformed)


def test_idempotence_cannot_hide_a_mixed_provider_handler():
    valid = hook_fragment(provider='claude',python=Path('/python'),script=Path('/release/hook.py'))
    bad = copy.deepcopy(valid)
    bad['hooks']['SessionStart'][0]['hooks'][0]['command'] = '/python -I -B /release/hook.py --provider codex'
    with pytest.raises(IntegrationConflict):
        compose_fragment(bad,bad)
