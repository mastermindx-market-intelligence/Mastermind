"""Native learning outlives foreground credentials without acquiring their authority."""
import json
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar, copy_context

import pytest

from agent import launch_credential_binding as binding

SECRET = 'qualification-auxiliary-token-91cba80e'
PROVIDER_SECRET = 'provider-owned-fixture-value-70e2'


@contextmanager
def foreground():
    lease = binding.CredentialLease('fixture-profile', 'fixture-principal', 'parent', 'fixture', 1,
        {'credential_fingerprints': {'TEST_RUN_TOKEN': 'fixture-digest'}, 'expires_at': time.time() + 3600},
        {'TEST_RUN_TOKEN': SECRET}, {'TEST_RUN_ID': 'fixture-run'})
    claim = lease.claim(profile_id='fixture-profile', principal_id='fixture-principal', session_id='parent',
                        instance_id='fixture', owner_epoch=1, admission_id='admission', generation=1, finite=True)
    with binding.execution_scope(lease, claim, transcript_check=lambda sid: sid == 'parent'):
        yield lease


@pytest.mark.parametrize('retire_parent', [False, True])
@pytest.mark.parametrize('secret_in_prefix', [False, True])
def test_native_review_constructor_and_real_tool_survive_parent_retirement(tmp_path, monkeypatch,
                                                                         retire_parent, secret_in_prefix):
    import agent.background_review as bg
    import model_tools
    import run_agent
    from hermes_constants import get_hermes_home
    from tools.thread_context import propagate_context_to_thread

    # The real constructor, native review worker and real dispatcher are exercised;
    # only model generation is replaced, so no network or paid calls are made.
    parent = run_agent.AIAgent(model='gpt-4.1-mini', provider='openai', api_key=PROVIDER_SECRET,
        base_url='http://127.0.0.1:9/v1', platform='cli', session_id='parent', quiet_mode=True,
        skip_memory=True, skip_context_files=True, enabled_toolsets=['file'], save_trajectories=False)
    parent._cached_system_prompt = 'native parent prefix' + (' ' + SECRET if secret_in_prefix else '')
    parent.ephemeral_system_prompt = 'native ephemeral context' + (' ' + SECRET if secret_in_prefix else '')
    if secret_in_prefix:
        assert parent.tools
        parent.tools[0]['function']['description'] += ' ' + SECRET
    original_tools = json.dumps(parent.tools, sort_keys=True)
    proof = tmp_path / 'read-proof.txt'
    proof.write_text('native-review-read-succeeded ' + SECRET)
    messages = [{'role': 'user', 'content': 'prior context ' + SECRET}]
    prompt = 'review instruction ' + SECRET
    expected_home = get_hermes_home()
    owner_context = ContextVar('review_fixture_owner', default=None)
    owner_token = owner_context.set('original-owner')
    seen, errors = [], []

    def generation(fork, **kwargs):
        assert binding.bound_credentials() is None
        assert binding.tool_environment() == {}
        assert get_hermes_home() == expected_home
        assert owner_context.get() == 'original-owner'
        assert fork.api_key == PROVIDER_SECRET
        assert fork.session_id == parent.session_id
        assert fork._persist_disabled and fork._session_db is None
        assert SECRET not in fork._cached_system_prompt
        assert SECRET not in (fork.ephemeral_system_prompt or '')
        assert SECRET not in json.dumps(kwargs)
        assert SECRET not in json.dumps(fork.tools)
        assert 'TEST_RUN_TOKEN' in binding.snapshot_exclusion_names()
        if not secret_in_prefix:
            assert fork._cached_system_prompt == parent._cached_system_prompt
            assert fork.ephemeral_system_prompt == parent.ephemeral_system_prompt
            assert fork.tools == parent.tools
        result = model_tools.handle_function_call('read_file', {'path': str(proof)}, session_id='parent',
            skip_pre_tool_call_hook=True, skip_tool_request_middleware=True)
        assert 'native-review-read-succeeded' in result
        assert SECRET not in result
        seen.append({'result': result, 'home': str(get_hermes_home())})
        return {'messages': [], 'final_response': 'qualification review complete'}

    monkeypatch.setattr(run_agent.AIAgent, 'run_conversation', generation)
    try:
        with foreground():
            with binding.tool_dispatch_scope('parent', 'execute_code', {}):
                # Match native copy_context propagation, including a subsequently
                # retired tool scope; the review must not revive either scope.
                def target():
                    try:
                        bg._run_review_in_thread(parent, messages, prompt, review_memory=False)
                    except BaseException as exc:
                        errors.append(type(exc).__name__)
                delayed = propagate_context_to_thread(target)
            if not retire_parent:
                thread = threading.Thread(target=delayed)
                thread.start()
                thread.join(timeout=30)
                assert not thread.is_alive()
                with binding.tool_dispatch_scope('parent', 'terminal', {}):
                    assert binding.tool_environment()['TEST_RUN_TOKEN'] == SECRET
        if retire_parent:
            thread = threading.Thread(target=delayed)
            thread.start()
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not errors
        assert len(seen) == 1
        assert messages[0]['content'].endswith(SECRET)
        assert parent._cached_system_prompt.endswith(SECRET) is secret_in_prefix
        assert json.dumps(parent.tools, sort_keys=True) == original_tools
        assert binding.bound_credentials() is None
        assert binding.tool_environment() == {}
        assert binding.snapshot_exclusion_names() == set()
    finally:
        owner_context.reset(owner_token)
        parent.close()


def test_native_cancel_preserves_review_identity_and_parent_lease(monkeypatch):
    import agent.background_review as bg
    from types import SimpleNamespace
    cancelled = threading.Event()
    cancelled.set()
    review = SimpleNamespace(cancel_requested=cancelled)
    parent, finished = object(), []
    monkeypatch.setattr(bg, 'finish_background_review_run', lambda agent, run: finished.append((agent, run)))
    with foreground(), binding.tool_dispatch_scope('parent', 'terminal', {}):
        original = binding.bound_credentials()
        bg._run_review_in_thread(parent, [], 'cancelled review', review_run=review)
        assert finished == [(parent, review)]
        assert binding.bound_credentials() is original
        assert binding.tool_environment()['TEST_RUN_TOKEN'] == SECRET


def test_auxiliary_exception_restores_scopes_and_nested_scrubbing():
    @binding.credential_free_auxiliary_review
    def inner():
        assert binding.bound_credentials() is None
        assert binding.tool_environment() == {}
        return SECRET

    @binding.credential_free_auxiliary_review
    def outer():
        assert SECRET not in inner()
        assert SECRET not in binding.redact({'value': SECRET})['value']
        raise RuntimeError('qualification exception')

    with foreground(), binding.tool_dispatch_scope('parent', 'terminal', {}):
        original = binding.bound_credentials()
        with pytest.raises(RuntimeError, match='qualification exception'):
            outer()
        assert binding.bound_credentials() is original
        assert binding.tool_environment()['TEST_RUN_TOKEN'] == SECRET
    assert binding.snapshot_exclusion_names() == set()
    assert binding.redact(SECRET) == SECRET


def test_auxiliary_logs_remain_scrubbed_after_parent_retirement():
    @binding.credential_free_auxiliary_review
    def review():
        try:
            raise ValueError(SECRET)
        except ValueError:
            import sys
            record = logging.LogRecord('qualification.review', logging.ERROR, '', 0, 'review %s',
                                       (SECRET,), sys.exc_info())
        record.extra = {'nested': [SECRET]}
        binding.sanitize_log_record(record)
        assert SECRET not in record.getMessage()
        assert SECRET not in (record.exc_text or '')
        assert SECRET not in json.dumps(record.extra)
        assert record.exc_info is None
        assert binding.tool_environment() == {}

    with foreground():
        delayed = copy_context()
    delayed.run(review)
