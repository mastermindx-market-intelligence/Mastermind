"""Real disposable Runtime-event storage; no host key provisioning or HTTP."""
import asyncio
import base64
import dataclasses
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane.executive_runtime import Runtime
from integrations.session_bridge import web_reply_subscription_owner as owner

NOW = 1791766800
URL = "https://receiver.example.com/callback_private_token_123"
SECRET = "whsec_" + base64.b64encode(b"a" * 32).decode()
NEW_SECRET = "whsec_" + base64.b64encode(b"b" * 32).decode()


def run(awaitable):
    return asyncio.run(awaitable)


def setup(tmp_path, clock=None):
    from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher, RuntimeReplySubscriptionStore
    runtime = Runtime.at(tmp_path)
    store = RuntimeReplySubscriptionStore(runtime, ExecutiveReplyCipher("fixture-key", b"k" * 32), clock=clock or (lambda: NOW))
    record = owner.StoredReplySubscription(
        subscription_id=owner._subscription_id("a" * 64, "request-001", URL),
        owner_key="a" * 64, request_ref="request-001", read_ref="read-001",
        revision="grant-001", expires_at=NOW + 1000, verified_at=NOW,
        callback_url_digest=hashlib.sha256(URL.encode()).hexdigest(),
        signing_secret_digest=hashlib.sha256(SECRET.encode()).hexdigest(),
    )
    return runtime, store, record


def commit(store, record, secret=SECRET, expected="empty"):
    return run(store.commit(record, secret, callback_url=URL, expected_version=expected))


def remove(store, record, expected):
    return run(store.remove(record.subscription_id, record.owner_key, request_ref=record.request_ref,
                            callback_url_digest=record.callback_url_digest, expected_version=expected))


def test_restart_recovers_sealed_url_and_secrets_without_plaintext(tmp_path):
    from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher, RuntimeReplySubscriptionStore
    runtime, store, record = setup(tmp_path)
    commit(store, record)
    snapshot = run(store.snapshot(record.subscription_id))
    reopened = RuntimeReplySubscriptionStore(Runtime.at(tmp_path), ExecutiveReplyCipher("fixture-key", b"k" * 32), clock=lambda: NOW)
    view = reopened.delivery_view(record.subscription_id, expected_version=snapshot.version,
                                 owner_key=record.owner_key, grant_revision=record.revision)
    assert view.callback_url == URL and view.signing_secrets == (SECRET,)
    assert URL not in repr(view) and SECRET not in repr(view)
    encoded = json.dumps([event.to_dict() for event in runtime.store.list_events()])
    assert URL not in encoded and SECRET not in encoded and "kkkkkkkk" not in encoded
    for path in tmp_path.rglob("*.sqlite*"):
        assert URL.encode() not in path.read_bytes() and SECRET.encode() not in path.read_bytes()


def test_concurrent_cas_one_winner_and_no_late_tombstone_resurrection(tmp_path):
    _, store, record = setup(tmp_path)
    def attempt(expiry):
        try:
            commit(store, dataclasses.replace(record, expires_at=expiry))
            return True
        except owner.SubscriptionConflict:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, [NOW + 900, NOW + 901])) == [False, True]
    prior = run(store.snapshot(record.subscription_id))
    remove(store, record, prior.version)
    revoked = run(store.snapshot(record.subscription_id))
    assert revoked.record is None and revoked.version != "empty"
    with pytest.raises(owner.SubscriptionConflict):
        commit(store, record, expected=prior.version)
    assert run(store.read(record.subscription_id)) is None


def test_virgin_unsubscribe_fences_waiting_first_callback(tmp_path):
    _, store, record = setup(tmp_path)
    remove(store, record, "empty")
    with pytest.raises(owner.SubscriptionConflict):
        commit(store, record)


def test_same_operation_recovery_does_not_append_again(tmp_path):
    runtime, store, record = setup(tmp_path)
    commit(store, record)
    first = runtime.store.list_events()
    assert commit(store, record) == record
    assert runtime.store.list_events() == first


def test_rotation_grace_is_bounded_and_refresh_does_not_extend_it(tmp_path):
    clock = [NOW]
    _, store, record = setup(tmp_path, clock=lambda: clock[0])
    commit(store, record)
    first = run(store.snapshot(record.subscription_id))
    rotated = dataclasses.replace(record, signing_secret_digest=hashlib.sha256(NEW_SECRET.encode()).hexdigest())
    commit(store, rotated, NEW_SECRET, first.version)
    after = run(store.snapshot(record.subscription_id))
    clock[0] += 200
    commit(store, dataclasses.replace(rotated, expires_at=NOW + 1200), NEW_SECRET, after.version)
    current = run(store.snapshot(record.subscription_id))
    view = store.delivery_view(record.subscription_id, expected_version=current.version, owner_key=record.owner_key, grant_revision=record.revision)
    assert view.signing_secrets == (NEW_SECRET, SECRET)
    clock[0] = NOW + 301
    assert store.delivery_view(record.subscription_id, expected_version=current.version, owner_key=record.owner_key, grant_revision=record.revision).signing_secrets == (NEW_SECRET,)
    with pytest.raises(owner.SubscriptionConflict):
        commit(store, record, expected=first.version)


def test_wrong_key_binding_and_digest_refuse(tmp_path):
    from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher, RuntimeReplySubscriptionStore
    runtime, store, record = setup(tmp_path)
    with pytest.raises(ValueError):
        commit(store, dataclasses.replace(record, signing_secret_digest="b" * 64))
    commit(store, record)
    version = run(store.snapshot(record.subscription_id)).version
    wrong = RuntimeReplySubscriptionStore(runtime, ExecutiveReplyCipher("other-key", b"z" * 32), clock=lambda: NOW)
    with pytest.raises(ValueError):
        run(wrong.snapshot(record.subscription_id))
    with pytest.raises(ValueError):
        wrong.delivery_view(record.subscription_id, expected_version=version, owner_key=record.owner_key, grant_revision=record.revision)
    with pytest.raises(ValueError):
        store.delivery_view(record.subscription_id, expected_version=version, owner_key="b" * 64, grant_revision=record.revision)


def test_delivery_reservation_restart_never_resends_and_revoke_can_settle(tmp_path):
    runtime, store, record = setup(tmp_path)
    commit(store, record)
    version = run(store.snapshot(record.subscription_id)).version
    args = dict(subscription_id=record.subscription_id, expected_version=version, owner_key=record.owner_key,
                grant_revision=record.revision, event_id="evt-" + "a" * 64)
    first = run(store.reserve_delivery(**args))
    assert first.fresh is True
    second = run(store.reserve_delivery(**args))
    assert second.fresh is False and second.state == "EFFECT_UNKNOWN"
    remove(store, record, version)
    run(store.settle_delivery(first.delivery_ref, outcome="RECEIVED", http_status=200))
    assert run(store.delivery_status(first.delivery_ref))["parent_consumed"] is False
    with pytest.raises(ValueError):
        run(store.settle_delivery(first.delivery_ref, outcome="REFUSED", http_status=403))
    with pytest.raises((ValueError, owner.SubscriptionConflict)):
        run(store.reserve_delivery(**{**args, "event_id": "evt-" + "b" * 64}))


def test_delivery_identity_survives_subscription_refresh(tmp_path):
    _, store, record = setup(tmp_path)
    commit(store, record)
    version = run(store.snapshot(record.subscription_id)).version
    args = dict(subscription_id=record.subscription_id, expected_version=version,
                owner_key=record.owner_key, grant_revision=record.revision, event_id="evt-" + "c" * 64)
    first = run(store.reserve_delivery(**args))
    commit(store, dataclasses.replace(record, expires_at=NOW + 1200), expected=version)
    newer = run(store.snapshot(record.subscription_id)).version
    again = run(store.reserve_delivery(**{**args, "expected_version": newer}))
    assert again.delivery_ref == first.delivery_ref and again.fresh is False
    assert again.state == "EFFECT_UNKNOWN"


def test_repeated_revocation_does_not_append_and_atomic_failure_rolls_back(tmp_path, monkeypatch):
    runtime, store, record = setup(tmp_path)
    remove(store, record, "empty")
    first = runtime.store.list_events()
    remove(store, record, run(store.snapshot(record.subscription_id)).version)
    assert runtime.store.list_events() == first
    current = run(store.snapshot(record.subscription_id)).version
    append = runtime.store.append_event
    def fail_after_append(*args, **kwargs):
        append(*args, **kwargs)
        raise RuntimeError("fixture transaction failure")
    monkeypatch.setattr(runtime.store, "append_event", fail_after_append)
    with pytest.raises(RuntimeError):
        commit(store, record, expected=current)
    assert runtime.store.list_events() == first
    monkeypatch.setattr(runtime.store, "append_event", append)
    assert commit(store, record, expected=current) == record


def test_lost_commit_ack_reconciles_exact_same_operation(tmp_path, monkeypatch):
    from contextlib import contextmanager
    runtime, store, record = setup(tmp_path)
    transaction = runtime.store.transaction
    @contextmanager
    def lost_ack():
        with transaction() as connection:
            yield connection
        raise RuntimeError("fixture lost ack AFTER COMMIT")
    monkeypatch.setattr(runtime.store, "transaction", lost_ack)
    with pytest.raises(RuntimeError):
        commit(store, record)
    events = runtime.store.list_events()
    assert len(events) == 1
    monkeypatch.setattr(runtime.store, "transaction", transaction)
    assert commit(store, record) == record
    assert runtime.store.list_events() == events


def test_ciphertext_tamper_and_unknown_event_cannot_yield_delivery_view(tmp_path, monkeypatch):
    runtime, store, record = setup(tmp_path)
    commit(store, record)
    version = run(store.snapshot(record.subscription_id)).version
    events = runtime.store.list_events
    def tampered(*args, **kwargs):
        rows = events(*args, **kwargs)
        if kwargs.get("aggregate_type")=="reply_subscription" and rows:
            payload = dict(rows[0].payload)
            payload["envelope"] = dict(payload["envelope"], ciphertext=base64.b64encode(b"x" * 64).decode())
            rows[0] = dataclasses.replace(rows[0], payload=payload)
        return rows
    monkeypatch.setattr(runtime.store, "list_events", tampered)
    with pytest.raises(ValueError):
        store.delivery_view(record.subscription_id, expected_version=version, owner_key=record.owner_key, grant_revision=record.revision)
    monkeypatch.setattr(runtime.store, "list_events", events)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type="reply_subscription", aggregate_id=record.subscription_id,
                                   event_type="FOREIGN_EVENT", payload={})
    with pytest.raises(ValueError):
        run(store.snapshot(record.subscription_id))


def test_rotation_keeps_only_latest_two_and_expiry_rechecked_after_decrypt(tmp_path, monkeypatch):
    clock=[NOW]
    _, store, record=setup(tmp_path,clock=lambda:clock[0])
    commit(store,record)
    version=run(store.snapshot(record.subscription_id)).version
    rotated=dataclasses.replace(record,signing_secret_digest=hashlib.sha256(NEW_SECRET.encode()).hexdigest())
    commit(store,rotated,NEW_SECRET,version)
    third="whsec_"+base64.b64encode(b"c"*32).decode()
    version=run(store.snapshot(record.subscription_id)).version
    latest=dataclasses.replace(record,signing_secret_digest=hashlib.sha256(third.encode()).hexdigest())
    commit(store,latest,third,version)
    version=run(store.snapshot(record.subscription_id)).version
    args=dict(expected_version=version,owner_key=record.owner_key,grant_revision=record.revision)
    assert store.delivery_view(record.subscription_id,**args).signing_secrets==(third,NEW_SECRET)
    opening=store._cipher.open
    def expire_during_open(*args):
        value=opening(*args)
        clock[0]=record.expires_at
        return value
    monkeypatch.setattr(store._cipher,"open",expire_during_open)
    with pytest.raises(ValueError):
        store.delivery_view(record.subscription_id,**args)
