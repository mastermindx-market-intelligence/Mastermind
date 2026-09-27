"""Original-call terminality through real gateway, synthetic owner and GitHub."""
import dataclasses
import pytest
from test_mastermind_github_app import (
    FakeGithub, _source, _gateway, _prepare, _token, _effect_digest, _run,
    COMMIT_TOOL, RECONCILE_TOOL, OPERATION, EffectState,
)


@pytest.mark.parametrize("reconstruct", [False, True], ids=["same-gateway", "new-gateway-same-owner"])
@pytest.mark.parametrize("owner_state", ["current", "unavailable", "moved"])
def test_negative_read_cannot_settle_possible_send_before_original_finishes(reconstruct, owner_state):
    github = FakeGithub(_source())
    github.commit_mode = "ambiguous_delayed"
    gateway, clock, authority = _gateway(github)
    prepared = _prepare(gateway, github)
    token, digest = _token(prepared), _effect_digest(prepared)
    initial = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert initial["data"]["effect_state"] == EffectState.EFFECT_UNKNOWN.value
    assert github.commit_calls == 1 and authority.attempt_claimed
    assert digest in github.pending
    if reconstruct:
        replacement, _, _ = _gateway(github, clock=clock, target=authority.target)
        replacement._authority_resolver = authority
        gateway = replacement
    if owner_state == "unavailable":
        authority.fail = True
    elif owner_state == "moved":
        authority.target = dataclasses.replace(authority.target, branch="sol/different-owner-target")
    calls_before = authority.calls
    unresolved = _run(gateway.call(RECONCILE_TOOL, {
        "operation_key": OPERATION, "normalized_effect_digest": digest, "prepared_token": token,
    }))
    # Only the first request settles, after sampling the still-negative read.
    github.settle_pending(digest)
    later = _run(gateway.call(RECONCILE_TOOL, {
        "operation_key": OPERATION, "normalized_effect_digest": digest, "prepared_token": token,
    }))
    assert later["data"]["effect_state"] == EffectState.APPLIED.value
    assert github.commit_calls == 1 and authority.calls == calls_before
    assert unresolved["data"]["effect_state"] == EffectState.EFFECT_UNKNOWN.value
    assert unresolved["data"]["reconciled"] is False
    assert unresolved["data"]["native_request_attempts"] == 0


def test_expired_execution_token_can_reconcile_unknown_then_applied_without_writes():
    github = FakeGithub(_source()); github.commit_mode = "ambiguous_delayed"
    gateway, clock, authority = _gateway(github)
    prepared = _prepare(gateway, github)
    token, digest = _token(prepared), _effect_digest(prepared)
    _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    clock.value += 301
    request = {"operation_key": OPERATION, "normalized_effect_digest": digest, "prepared_token": token}
    before = _run(gateway.call(RECONCILE_TOOL, request))
    github.settle_pending(digest)
    after = _run(gateway.call(RECONCILE_TOOL, request))
    assert after["data"]["effect_state"] == "APPLIED" and github.commit_calls == 1
    assert before["data"]["effect_state"] == "EFFECT_UNKNOWN"
    assert before["data"]["reconciled"] is False
