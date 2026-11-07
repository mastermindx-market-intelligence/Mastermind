"""Disposition of one Chris-Dot channel subscription on disposable Executive Runtime.

No real OAuth, Slack, webhook, external network or host enrollment.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane.executive_runtime import Runtime
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher
from integrations.session_bridge.runtime_dot_canary_subscriptions import (
    CanaryRecord, RuntimeCanarySubscriptionStore, subscription_id,
)

NOW = 1794017601
URL = "https://receiver.example.com/mcp-events/callback_123"
KEY = "whsec_" + base64.b64encode(b"s" * 32).decode("ascii")
ROTATED = "whsec_" + base64.b64encode(b"t" * 32).decode("ascii")
OWNER = hashlib.sha256(b"chris-dot").hexdigest()
CHANNEL = "C0BSBM78V1N"


def run(coroutine):
    return asyncio.run(coroutine)


def make_case(tmp_path, *, now=NOW):
    state = Runtime.at(tmp_path)
    store = RuntimeCanarySubscriptionStore(state, ExecutiveReplyCipher("existing-key", b"k"*32), clock=lambda: now)
    record = CanaryRecord(
        subscription_id=subscription_id(OWNER, CHANNEL, URL),
        owner_key=OWNER, channel_id=CHANNEL,
        callback_url_digest=hashlib.sha256(URL.encode()).hexdigest(),
        signing_secret_digest=hashlib.sha256(KEY.encode()).hexdigest(),
        source_policy_sha256="a"*64,
        verified_at=now, expires_at=now+300, authorized_until=now+600,
    )
    auth = {"principal":{"subject_digest":"b"*64}, "owner_key":OWNER,
            "channel_id":CHANNEL,"source_policy_sha256":"a"*64,
            "authorized_until":now+600}
    return state, store, record, auth


def commit(store, record, auth, *, secret=KEY, expected="empty"):
    return run(store.commit(record, secret, callback_url=URL,
                            authorization=auth, expected_version=expected))


def test_sealed_subscription_survives_restart_and_hides_all_secrets(tmp_path):
    runtime, store, record, auth = make_case(tmp_path)
    assert commit(store,record,auth) == record
    snapshot = run(store.snapshot(record.subscription_id))
    assert snapshot.record == record
    restored = RuntimeCanarySubscriptionStore(Runtime.at(tmp_path),
        ExecutiveReplyCipher("existing-key",b"k"*32),clock=lambda:NOW)
    view = restored.delivery_view(record.subscription_id,
         expected_version=snapshot.version,owner_key=OWNER)
    assert view.callback_url == URL and view.signing_secrets == (KEY,)
    assert view.authorization == auth
    assert KEY not in repr(view) and URL not in repr(view)
    raw=json.dumps([e.to_dict() for e in runtime.store.list_events()])
    assert KEY not in raw and URL not in raw
    assert str(auth["principal"]["subject_digest"]) not in raw
    for path in tmp_path.rglob("*.sqlite*"):
        assert KEY.encode() not in path.read_bytes()


def test_conflicting_cas_and_idempotent_original_reconciliation(tmp_path):
    runtime, store, record, auth=make_case(tmp_path)
    assert commit(store,record,auth)==record
    before=runtime.store.list_events()
    assert commit(store,record,auth)==record
    assert runtime.store.list_events()==before
    first=run(store.snapshot(record.subscription_id))
    with pytest.raises(Exception):
        commit(store,dataclasses.replace(record,expires_at=NOW+301),auth)
    assert run(store.snapshot(record.subscription_id))==first


def test_cas_concurrent_writers_one_wins(tmp_path):
    runtime, store, record, auth=make_case(tmp_path)
    def write(extra):
        try:
            commit(store,dataclasses.replace(record,expires_at=NOW+extra),auth)
            return "accepted"
        except Exception:
            return "refused"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(write,[250,275]))==["accepted","refused"]
    assert len(runtime.store.list_events(aggregate_type="reply_subscription"))==1


def test_revocation_fences_delayed_commit_and_remains_idempotent(tmp_path):
    runtime, store, record, auth=make_case(tmp_path)
    run(store.remove(record.subscription_id,owner_key=OWNER,channel_id=CHANNEL,
        callback_url_digest=record.callback_url_digest,expected_version="empty"))
    snap=run(store.snapshot(record.subscription_id))
    assert snap.record is None and snap.binding==(OWNER,CHANNEL,record.callback_url_digest)
    run(store.remove(record.subscription_id,owner_key=OWNER,channel_id=CHANNEL,
        callback_url_digest=record.callback_url_digest,expected_version=snap.version))
    with pytest.raises(Exception):
        commit(store,record,auth)
    assert run(store.read(record.subscription_id)) is None


def test_approved_key_rotation_has_grace_window(tmp_path):
    runtime, store, record, auth=make_case(tmp_path)
    commit(store,record,auth)
    first=run(store.snapshot(record.subscription_id))
    current=dataclasses.replace(record,
        signing_secret_digest=hashlib.sha256(ROTATED.encode()).hexdigest())
    commit(store,current,auth,secret=ROTATED,expected=first.version)
    view=store.delivery_view(current.subscription_id,
        expected_version=run(store.snapshot(current.subscription_id)).version,
        owner_key=OWNER)
    assert view.signing_secrets == (ROTATED,KEY)


def test_canary_audience_no_foreign_native_reply_and_expiry(tmp_path):
    runtime, store, record, auth=make_case(tmp_path)
    assert store.subscriptions_for_channel(CHANNEL)==()
    commit(store,record,auth)
    assert store.subscriptions_for_channel(CHANNEL)==(record.subscription_id,)
    assert store.subscriptions_for_channel("C0BRFC9JXK8")==()
    assert runtime.store.list_events(aggregate_type="reply_subscription")[0].event_type=="CANARY_SUBSCRIPTION_COMMITTED"


def test_delivery_exactly_once_even_after_restart_unknown_result(tmp_path):
    runtime,store,record,auth=make_case(tmp_path)
    commit(store,record,auth)
    ver=run(store.snapshot(record.subscription_id)).version
    kwargs=dict(ident=record.subscription_id,version=ver,
                owner_key=OWNER,event_id="evt-"+"f"*64)
    first=run(store.reserve_delivery(**kwargs))
    assert first.fresh and first.state=="STARTED"
    assert store.delivery_status(first.delivery_ref)=="EFFECT_UNKNOWN"
    recovered=RuntimeCanarySubscriptionStore(Runtime.at(tmp_path),
        ExecutiveReplyCipher("existing-key",b"k"*32),clock=lambda:NOW)
    second=run(recovered.reserve_delivery(**kwargs))
    assert second.delivery_ref==first.delivery_ref
    assert second.fresh is False and second.state=="EFFECT_UNKNOWN"
    run(recovered.settle_delivery(first.delivery_ref,outcome="RECEIVED",status=202))
    assert recovered.delivery_status(first.delivery_ref)=="RECEIVED"
    with pytest.raises(Exception):
        run(recovered.settle_delivery(first.delivery_ref,outcome="REFUSED",status=403))


def test_revocation_after_reservation_blocks_later_new_event(tmp_path):
    _,store,record,auth=make_case(tmp_path)
    commit(store,record,auth)
    current=run(store.snapshot(record.subscription_id))
    first=run(store.reserve_delivery(
        ident=record.subscription_id,version=current.version,owner_key=OWNER,
        event_id="evt-"+"c"*64))
    run(store.remove(record.subscription_id,owner_key=OWNER,
        channel_id=CHANNEL,callback_url_digest=record.callback_url_digest,
        expected_version=current.version))
    run(store.settle_delivery(first.delivery_ref,outcome="REFUSED",status=410))
    assert store.delivery_status(first.delivery_ref)=="REFUSED"
    with pytest.raises(Exception):
        run(store.reserve_delivery(
            ident=record.subscription_id,version=current.version,owner_key=OWNER,
            event_id="evt-"+"e"*64))


@pytest.mark.parametrize("changes",[
    {"owner_key":"b"*64},{"channel_id":"C0BRFC9JXK8"},
    {"expires_at":NOW-1},{"authorized_until":NOW+100},
    {"source_policy_sha256":"bad"},{"verified_at":NOW+1000},
    {"signing_secret_digest":"c"*64},
])
def test_invalid_or_forged_record_cannot_commit(tmp_path,changes):
    _,store,record,auth=make_case(tmp_path)
    with pytest.raises(ValueError):
        commit(store,dataclasses.replace(record,**changes),auth)


def test_wrong_key_cannot_decrypt_existing_grant(tmp_path):
    runtime,store,record,auth=make_case(tmp_path)
    commit(store,record,auth)
    bad=RuntimeCanarySubscriptionStore(runtime,
        ExecutiveReplyCipher("wrong-key",b"z"*32),clock=lambda:NOW)
    with pytest.raises(ValueError):
        run(bad.snapshot(record.subscription_id))


def test_distinct_accounts_have_distinct_subscription_ids():
    a=subscription_id(OWNER,CHANNEL,URL)
    b=subscription_id("b"*64,CHANNEL,URL)
    assert a!=b
    assert subscription_id(OWNER,CHANNEL,URL)==a
