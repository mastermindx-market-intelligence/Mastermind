"""Inert regressions for local collection failures and native watch classification."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts import install_ci_wait_guidance as installer


ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT/'integrations/session_bridge/original_validator_compat'


def guard(tmp_path):
    source = (ROOT/'research/execution_friction_20261011/fixtures/installed_routing_guard.py').read_text()
    ns = {'__name__': 'inert_guard'}
    exec(compile(installer.render('guard', source), '<guard>', 'exec'), ns)
    ns['POLL_STATE_DIR'] = str(tmp_path)
    return ns


def call_guard(ns, payload, command, **extra):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        ns['guard_bash'](payload, {'command': command, **extra})
    return json.loads(out.getvalue())['hookSpecificOutput']


def payload(**changes):
    return dict(session_id='inert-root', turn_id='inert-turn',
                cwd='/Users/chriswong/Documents/Cluade/Mastermind',
                transcript_path='/inert/rollout.jsonl', **changes)


def test_codex_transcript_does_not_make_a_claude_foreground_call(tmp_path):
    result = call_guard(guard(tmp_path), payload(), 'gh run watch 42 --interval 300 --exit-status')
    assert 'permissionDecision' not in result
    assert 'launch is NOT yet verified' in result['additionalContext']


@pytest.mark.parametrize('turn', [None, '', '  ', True, 12, [], {}])
def test_missing_or_malformed_native_turn_is_not_native(tmp_path, turn):
    p = payload(); p['turn_id'] = turn
    result = call_guard(guard(tmp_path), p, 'gh run watch 42 --interval 300')
    assert result['permissionDecision'] == 'deny'


@pytest.mark.parametrize('command', [
    'gh run watch 42 --interval 3',
    'gh run watch 42',
    'gh run watch 42 --interval 300; gh pr merge 12 --squash',
    'sleep 300; gh run view 42',
])
def test_native_transcript_preserves_other_refusals(tmp_path, command):
    assert call_guard(guard(tmp_path), payload(), command)['permissionDecision'] == 'deny'


def test_native_watch_preserves_same_run_cooldown(tmp_path):
    ns = guard(tmp_path)
    call_guard(ns, payload(), 'gh run watch 42 --interval 300')
    result = call_guard(ns, payload(), 'gh run view 42 --json status')
    assert result['permissionDecision'] == 'deny'
    assert 'READ_COOLDOWN_ONLY' in result['permissionDecisionReason']


def test_claude_background_watch_still_supported(tmp_path):
    p = payload(); p.pop('turn_id')
    result = call_guard(guard(tmp_path), p, 'gh run watch 42 --interval 300', run_in_background=True)
    assert 'permissionDecision' not in result


@pytest.fixture
def collector(monkeypatch):
    # Existing dependency modules only; no live caller substitution, collection,
    # directory modification or transport. Candidate has no import-time effects.
    monkeypatch.syspath_prepend(str(EXT))
    path = ROOT/'integrations/session_bridge/qwen_plain_recovery/original_delivery_collector.py'
    spec = importlib.util.spec_from_file_location('local_diagnostic_candidate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('error,reason', [
    (ValueError('directory_owner_or_mode'), 'directory_owner_or_mode'),
    (ValueError('directory_chain_changed'), 'directory_chain_changed'),
    (PermissionError('/private/path must not appear'), 'original_binding_unconfirmed'),
])
def test_local_binding_refusal_is_sanitized_and_pretransport(collector, monkeypatch, capsys, error, reason):
    c = collector
    monkeypatch.setattr(c, 'load_binding', Mock(side_effect=error))
    reserve = Mock(side_effect=AssertionError('must not reserve'))
    transport = Mock(side_effect=AssertionError('must not transport'))
    monkeypatch.setattr(c.delivery, 'reserve_destination', reserve)
    monkeypatch.setattr(c.delivery, 'transport', transport)
    rc = c.main(['inert-run', '--root', 'inert-root', '--parent', 'inert-root',
                 '--binding', '/inert/binding', '--destination', '/inert/destination'])
    result = json.loads(capsys.readouterr().out)
    assert rc == 75
    assert result['reason'] == reason
    assert result['failure_phase'] == 'original_local_binding'
    assert result['remote_read_started'] is False
    assert result['destination_reserved'] is False
    assert result['retry_authorized'] is False
    assert result['worker_terminal_proof'] is False
    assert result['delivery_verified'] is False
    assert '/private/path' not in json.dumps(result)
    reserve.assert_not_called(); transport.assert_not_called()


def test_later_failure_does_not_claim_pretransport(collector, monkeypatch, capsys):
    monkeypatch.setattr(collector, 'collect', Mock(side_effect=ValueError('later')))
    assert collector.main(['inert-run', '--root', 'inert-root', '--parent', 'inert-root',
                           '--binding', '/inert/binding', '--destination', '/inert/destination']) == 75
    result = json.loads(capsys.readouterr().out)
    assert result['reason'] == 'original_delivery_unconfirmed'
    assert 'remote_read_started' not in result
    assert result['retry_authorized'] is False
