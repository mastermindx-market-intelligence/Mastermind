"""Focused reconcile and fence proofs for the control content observer.

Covers the accepted repair findings on ``executive_content_observer.py`` /
``executive_worker_broker.py``:

* explicit status/revoke reconcile the exact existing bound grant after the
  Runtime lease expired / the turn ceased and the broker has no active
  operator run, while enroll and every read still refuse on a stale Runtime;
* the run-absent broker path performs an exact existing-registry binding
  lookup (no mint, no guess) and treats a partial tuple match as a conflict;
* the canonical ``worker_quota_classes`` held_attempt_id/fence_counter parity
  and the current fence are part of every live join, the access ticket and the
  before/after page snapshot: a quota mismatch refuses, a fence moved during
  a page refuses that page, and a later fresh read may observe the same turn
  once the reconciled fence is ticketed. Lease tokens are never exposed.

The runtime/broker/projection objects are the real production classes seeded
through the same fixture as ``test_steward_content_integration``.
"""
import asyncio
import json

import pytest

from control_plane.executive_content_observer import (
    ContentRefused,
    ExecutiveContentObserver,
)
from control_plane.executive_worker_broker import BrokerStateError
from control_plane.visible_turn_projection import VisibleTurnProjection
from integrations.executive_content_contract import ACCESS_SCHEMA, PAGE_SCHEMA

from test_steward_content_integration import fixture


class _DirectBroker:
    """In-process client that exercises the real broker dispatch."""

    def __init__(self, broker):
        self._broker = broker

    async def request(self, operation, payload):
        return await self._broker._dispatch(operation, dict(payload))


def _observer(runtime, broker, p, clock):
    return ExecutiveContentObserver(
        runtime=runtime,
        broker_client=_DirectBroker(broker),
        profile_loader=lambda: p,
        now=lambda: clock.value // 1000,
    )


def _terminal_run_absent(broker, adapter):
    """Model the broker state after the operator run went terminal."""
    broker._operator_run = None
    assert broker._observer_projection is adapter.visible_turn_projection


def test_status_and_revoke_reconcile_expired_lease_and_absent_run(tmp_path):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def run():
        observer = _observer(runtime, broker, p, clock)
        enrolled = await observer.enroll()
        assert enrolled["status"] == "ACTIVE"
        assert enrolled["turn_key"]["native_turn_id"] == "NATIVE-G1"
        _terminal_run_absent(broker, adapter)
        clock.advance(3)  # the Runtime lease was 2s
        # Status reconciles the exact existing bound grant on the stale
        # Runtime with no active operator run.
        status = await observer.status()
        assert status["status"] == "ACTIVE"
        assert status["turn_key"] == enrolled["turn_key"]
        # Neither reads nor enrollment reconcile a stale Runtime.
        refused = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert refused == {"ok": False, "error": {"code": "GRANT_INVALIDATED"}}
        with pytest.raises(ContentRefused, match="GRANT_INVALIDATED"):
            await observer.enroll()
        revoked = await observer.revoke()
        assert revoked["status"] == "REVOKED"
        assert revoked["reader_grant"] is None
        # Subsequent reads refuse on the revoked grant.
        again = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert again == {"ok": False, "error": {"code": "GRANT_INVALIDATED"}}

    asyncio.run(run())


def test_run_absent_without_grant_returns_absent_and_never_mints(tmp_path):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def run():
        broker._operator_run = None
        adapter.visible_turn_projection = VisibleTurnProjection()
        broker._observer_projection = adapter.visible_turn_projection
        observer = _observer(runtime, broker, p, clock)
        assert (await observer.status())["status"] == "ABSENT"
        assert (await observer.revoke())["status"] == "ABSENT"
        # With no retained registry at all the answer is still a plain
        # ABSENT status, never a minted or guessed grant.
        broker._observer_projection = None
        absent = await observer.status()
        assert absent == {"status": "ABSENT", "reader_grant": None,
                          "turn_key": None, "grant_generation": None}
        # Enrollment without an active operator run refuses closed.
        with pytest.raises(BrokerStateError, match="UNKNOWN_GENERATION"):
            await observer.enroll()

    asyncio.run(run())


def test_partial_binding_tuple_is_conflict_not_miss(tmp_path):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def run():
        observer = _observer(runtime, broker, p, clock)
        assert (await observer.enroll())["status"] == "ACTIVE"
        _terminal_run_absent(broker, adapter)
        assert (await observer.status())["status"] == "ACTIVE"
        wrong_permission = dict(p.broker_payload(), permission_digest="f" * 64)
        with pytest.raises(BrokerStateError, match="OBSERVER_CONFLICT"):
            await broker._dispatch("ohf-observer-status", wrong_permission)
        wrong_turn = dict(p.broker_payload(), turn="some-other-turn")
        with pytest.raises(BrokerStateError, match="OBSERVER_CONFLICT"):
            await broker._dispatch("ohf-observer-revoke", wrong_turn)
        # The exact full tuple still reconciles after the conflicts.
        assert (await observer.status())["status"] == "ACTIVE"

    asyncio.run(run())


def test_quota_parity_mismatch_refuses_live_read(tmp_path):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def run():
        observer = _observer(runtime, broker, p, clock)
        assert (await observer.enroll())["status"] == "ACTIVE"
        ok = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert ok["ok"] is True
        # The quota class no longer holds this attempt at this fence.
        with runtime.store.transaction() as connection:
            connection.execute(
                "UPDATE worker_quota_classes SET fence_counter=fence_counter+1 "
                "WHERE worker_id=?",
                ("worker-a",),
            )
        mismatched = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert mismatched == {"ok": False, "error": {"code": "GRANT_INVALIDATED"}}
        with runtime.store.transaction() as connection:
            connection.execute(
                "UPDATE worker_quota_classes SET status='AVAILABLE', "
                "held_attempt_id=NULL WHERE worker_id=?",
                ("worker-a",),
            )
        released = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert released == {"ok": False, "error": {"code": "GRANT_INVALIDATED"}}

    asyncio.run(run())


def test_fence_change_mid_page_refuses_then_fresh_read_reconciles(tmp_path):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def run():
        observer = _observer(runtime, broker, p, clock)
        assert (await observer.enroll())["status"] == "ACTIVE"
        from control_plane.visible_turn_projection import TurnKey

        key = TurnKey(**(await observer.status())["turn_key"])
        for n in range(4):
            adapter.visible_turn_projection.publish(
                key,
                method="item/updated",
                params={"item": {"type": "agentMessage", "id": str(n),
                                 "sequence": n, "text": "x" * 12000}},
                native_turn_id="NATIVE-G1",
            )
        before = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert before["ok"] is True
        assert set(before["access"]) == {"ticket_digest", "retained_scope",
                                         "expires_at"}
        ticket = before["access"]["ticket_digest"]
        reply_json = json.dumps(before)
        assert "lease" not in reply_json
        assert "reader_grant" not in reply_json

        refenced = []

        class _MidPageBroker:
            """Advance the whole fence coherently during the page read."""

            def __init__(self, inner):
                self._inner = inner

            async def request(self, operation, payload):
                if operation == "ohf-observe-turn" and not refenced:
                    refenced.append(True)
                    with runtime.store.transaction() as connection:
                        connection.execute(
                            "UPDATE attempts SET fence_generation="
                            "fence_generation+1 WHERE attempt_id=?",
                            (p.attempt_id,),
                        )
                        connection.execute(
                            "UPDATE worker_quota_classes SET fence_counter="
                            "fence_counter+1 WHERE worker_id=?",
                            ("worker-a",),
                        )
                return await self._inner.request(operation, payload)

        observer.broker = _MidPageBroker(observer.broker)
        page = dict(p.frame(PAGE_SCHEMA), access_ticket_digest=ticket,
                    cursor=None, max_items=4)
        refused = await observer.handle_frame(page)
        assert refused == {"ok": False, "error": {"code": "ACCESS_CHANGED"}}
        assert refenced == [True]

        # A later fresh read observes the same turn under the reconciled
        # fence: new ticket, same retained scope, readable page.
        fresh = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert fresh["ok"] is True
        assert fresh["access"]["ticket_digest"] != ticket
        assert fresh["access"]["retained_scope"] == before["access"]["retained_scope"]
        ok_page = await observer.handle_frame(dict(
            p.frame(PAGE_SCHEMA),
            access_ticket_digest=fresh["access"]["ticket_digest"],
            cursor=None,
            max_items=4,
        ))
        assert ok_page["ok"] is True
        assert [item["byte_length"] for item in ok_page["page"]["items"]] == [12000] * 4
        assert "reader_grant" not in json.dumps(ok_page)
        assert "lease" not in json.dumps(ok_page)

    asyncio.run(run())


def test_quarantine_denies_read_but_preserves_explicit_revocation(tmp_path):
    clock, runtime, p, adapter, broker = fixture(tmp_path)

    async def run():
        observer = _observer(runtime, broker, p, clock)
        enrolled = await observer.enroll()
        with runtime.store.transaction() as connection:
            runtime.store.append_event(connection, aggregate_type='worker',
                aggregate_id=enrolled['turn_key']['worker_id'],
                event_type='OHF_RESTORE_INVALIDATED',
                worker_id=enrolled['turn_key']['worker_id'],
                attempt_id=p.attempt_id, payload={'fixture': True})
        assert (await observer.handle_frame(p.frame(ACCESS_SCHEMA)))['ok'] is False
        with pytest.raises(ContentRefused):
            await observer.enroll()
        assert (await observer.status())['status'] == 'ACTIVE'
        assert (await observer.revoke())['status'] == 'REVOKED'

    asyncio.run(run())
