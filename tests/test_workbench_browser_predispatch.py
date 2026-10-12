"""Actual signed-reference/real-store regression; no browser or relay process."""
from __future__ import annotations
import os
from types import SimpleNamespace
import pytest
from control_plane.codex_worker import ProcessIdentityError
from integrations.workbench_browser_mcp import browser_port as browser_module
from tests.test_workbench_browser_port import _fixture

@pytest.mark.parametrize('failure', ['binding_revoked', 'relay_identity_lost', 'resource_expired'])
def test_claimed_but_never_dispatched_action_has_terminal_not_applied(tmp_path, monkeypatch, failure):
    relay_calls = []
    def relay(*args, **kwargs):
        relay_calls.append((args, kwargs))
        raise AssertionError('No relay dispatch is allowed in this regression')
    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(caller, browser_ref, 'browser_click', {'target': 'button'})
        browser, binding, _socket, prepared = port._decode_action(caller, browser_ref, action_ref)
        identity = port._action_identity(browser, binding, prepared)
        original_claim = browser_module.claim_action
        def claim_then_invalidate(*args, **kwargs):
            outcome = original_claim(*args, **kwargs)
            if outcome.created:
                if failure == 'binding_revoked':
                    monkeypatch.setattr(port, '_resolve_binding', lambda *_args: None)
                elif failure == 'relay_identity_lost':
                    def missing(_pid):
                        raise ProcessIdentityError('synthetic process disappeared')
                    monkeypatch.setattr(port, '_inspector', SimpleNamespace(inspect=missing))
                else:
                    monkeypatch.setattr(port, '_clock_ms', lambda: 9000)
            return outcome
        monkeypatch.setattr(browser_module, 'claim_action', claim_then_invalidate)
        observed_error = None
        try:
            result = port.run_action(caller, browser_ref, action_ref)
        except browser_module.BrowserPortRefused as exc:
            observed_error = exc.code
        classified = browser_module.classify_action(port._store, identity)
        assert relay_calls == [], (failure, observed_error)
        assert classified.evidence_status == 'qualified', (failure, observed_error, classified)
        assert classified.effect_state == 'NOT_APPLIED', (failure, observed_error, classified)
        assert observed_error is None
        assert result['effect_state'] == 'NOT_APPLIED'
        assert result['reconciled'] is False
        assert classified.result.details == {'reason': 'binding_refused_before_dispatch'}
    finally:
        os.close(fd)


def _prepared(caller, port, browser_ref):
    action_ref = port.prepare_action(caller, browser_ref, 'browser_click', {'target': 'button'})
    browser, binding, _socket, prepared = port._decode_action(caller, browser_ref, action_ref)
    return action_ref, port._action_identity(browser, binding, prepared)


def test_initial_refusal_creates_no_claim(tmp_path, monkeypatch):
    def no_relay(*args, **kwargs):
        pytest.fail('relay must not be called')
    fd, caller, port, browser_ref = _fixture(tmp_path, no_relay)
    try:
        action_ref, identity = _prepared(caller, port, browser_ref)
        monkeypatch.setattr(port, '_resolve_binding', lambda *_: None)
        with pytest.raises(browser_module.BrowserPortRefused, match='BROWSER_BINDING_CHANGED'):
            port.run_action(caller, browser_ref, action_ref)
        classified = browser_module.classify_action(port._store, identity)
        assert classified.evidence_status == 'absent'
        assert classified.claim is None and classified.result is None
    finally:
        os.close(fd)


@pytest.mark.parametrize('failure', ['untyped_resource', 'finalizer', 'clock'])
def test_unqualified_predispatch_failures_are_not_finalized(tmp_path, monkeypatch, failure):
    def no_relay(*args, **kwargs):
        pytest.fail('relay must not be called')
    fd, caller, port, browser_ref = _fixture(tmp_path, no_relay)
    try:
        action_ref, identity = _prepared(caller, port, browser_ref)
        original_claim = browser_module.claim_action
        def unavailable(*args, **kwargs):
            raise OSError('synthetic unavailable')
        def typed_refusal(*args, **kwargs):
            if failure == 'clock':
                monkeypatch.setattr(port, '_clock_ms', unavailable)
            raise browser_module.BrowserPortRefused('BROWSER_BINDING_CHANGED')
        def claim_then_fail(*args, **kwargs):
            outcome = original_claim(*args, **kwargs)
            assert outcome.created
            monkeypatch.setattr(port, '_resource', unavailable if failure == 'untyped_resource' else typed_refusal)
            if failure == 'finalizer':
                monkeypatch.setattr(browser_module, 'finalize_action', unavailable)
            return outcome
        monkeypatch.setattr(browser_module, 'claim_action', claim_then_fail)
        with pytest.raises(OSError, match='synthetic unavailable'):
            port.run_action(caller, browser_ref, action_ref)
        classified = browser_module.classify_action(port._store, identity)
        assert classified.evidence_status == 'pending'
        assert classified.effect_state == 'EFFECT_UNKNOWN'
        assert classified.claim is not None and classified.result is None
    finally:
        os.close(fd)


def test_typed_error_after_relay_entry_stays_unknown_and_cannot_replay(tmp_path):
    calls = []
    def relay(*args, **kwargs):
        calls.append(args)
        raise browser_module.BrowserPortRefused('synthetic post-dispatch error')
    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref, identity = _prepared(caller, port, browser_ref)
        with pytest.raises(browser_module.BrowserPortRefused, match='post-dispatch'):
            port.run_action(caller, browser_ref, action_ref)
        classified = browser_module.classify_action(port._store, identity)
        assert classified.evidence_status == 'pending'
        assert classified.effect_state == 'EFFECT_UNKNOWN'
        assert classified.result is None
        repeated = port.run_action(caller, browser_ref, action_ref)
        assert repeated['effect_state'] == 'EFFECT_UNKNOWN'
        assert repeated['reconciled'] is True
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_existing_claim_is_not_finalized_by_another_invocation(tmp_path, monkeypatch):
    def no_relay(*args, **kwargs):
        pytest.fail('relay must not be called')
    fd, caller, port, browser_ref = _fixture(tmp_path, no_relay)
    try:
        action_ref, identity = _prepared(caller, port, browser_ref)
        with browser_module.acquire_store_writer(port._store):
            outcome = browser_module.claim_action(port._store, identity, claimed_at_ms=2000)
            assert outcome.created
        def no_finalize(*args, **kwargs):
            pytest.fail('existing claim must not be finalized')
        monkeypatch.setattr(browser_module, 'finalize_action', no_finalize)
        result = port.run_action(caller, browser_ref, action_ref)
        assert result['effect_state'] == 'EFFECT_UNKNOWN'
        assert result['reconciled'] is True
        classified = browser_module.classify_action(port._store, identity)
        assert classified.claim == outcome.claim
        assert classified.result is None
    finally:
        os.close(fd)
