"""One original request has one disposition, including across caller surfaces."""
from concurrent.futures import ThreadPoolExecutor
import dataclasses
import threading

import pytest

from tests.test_company_dialogue_principal_runtime_fence import (
    Resolver, binding, intent, owner, principal_message, runtime_child,
)
from integrations.mastermind_company_principal_runtime_fence import (
    PRINCIPAL_RUNTIME_EVENT_TYPE, PrincipalRuntimeFenceError,
)


def other_intent(bound, key="b"):
    # The existing owner receives the canonical message digest from its gateway.
    return dataclasses.replace(intent(bound, principal_message(bound)),
        message_key="asd-principal-" + key * 32, message_fingerprint=key * 64)


@pytest.mark.parametrize("changed_caller", [False, True])
def test_new_message_key_cannot_reanswer_the_original_request(tmp_path, changed_caller):
    runtime, root, child, attempt = runtime_child(tmp_path)
    first = binding(root, child, attempt)
    owner(runtime, Resolver(first)).before_commit(intent(first, principal_message(first)))
    second = first
    if changed_caller:
        second = dataclasses.replace(first, actor_ref={**first.actor_ref,
            "reasoning_surface": "other-authenticated-surface",
            "principal_binding_digest": "3" * 64,
            "authority_generation_digest": "4" * 64})
    with pytest.raises(PrincipalRuntimeFenceError, match="request already has a COMMIT"):
        owner(runtime, Resolver(second)).before_commit(other_intent(second))
    assert len([e for e in runtime.events.list_events()
                if e.event_type == PRINCIPAL_RUNTIME_EVENT_TYPE]) == 1


def test_distinct_original_request_still_accepts_one_new_disposition(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    first = binding(root, child, attempt)
    owner(runtime, Resolver(first)).before_commit(intent(first, principal_message(first)))
    next_request = dataclasses.replace(first, reply_to_message_key="asd-result-next00001")
    receipt = owner(runtime, Resolver(next_request)).before_commit(other_intent(next_request))
    assert receipt.durable_ref.startswith("runtime-event:")


def test_concurrent_surfaces_serialize_on_the_original_request(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    start = threading.Barrier(2)
    def commit(key):
        subject = owner(runtime, Resolver(bound))
        start.wait(timeout=5)
        try:
            subject.before_commit(other_intent(bound, key))
            return "committed"
        except PrincipalRuntimeFenceError:
            return "refused"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, ["b", "c"]))
    assert sorted(results) == ["committed", "refused"]
    assert len([e for e in runtime.events.list_events()
                if e.event_type == PRINCIPAL_RUNTIME_EVENT_TYPE]) == 1
