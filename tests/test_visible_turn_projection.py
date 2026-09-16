"""Maintenance wave VTP-M1 — RED tests for defects in
``control_plane/visible_turn_projection.py``.

  F1 — upsert + small page strands a retained item (publication order vs storage order).
  F2 — ``mint_grant`` is not atomic across the budget check, the UUID mint, and the
       viewer bookkeeping; concurrent mints can exceed ``MAX_VIEWERS``.
  F3 — ``read()`` re-acquires the lock for the snapshot after ``check_grant`` has
       already released it; a revoke landing in that window is invisible and a
       revoked reader is served text.
  F4 — the replacement branch of ``_append_locked`` skips the byte-budget eviction
       loop, so retention can grow past ``MAX_RETAINED_TURN_BYTES``.
  F5 — the F4 eviction gap is recorded BEYOND ``next_publication_sequence`` so it
       can never be cleared by a subsequent read; the same retention contract as
       the append branch requires the gap to be reachable.
  F6 — ``ReadResult.items`` is now a ``list``, breaking the frozen
       ``tuple[VisibleItem, ...]`` shape declared on the dataclass.
  F7 — render order test must distinguish source order from storage order.
  F8 — render order is independent of publication order, not just storage order.

Each test must finish within its own deterministic budget. No thread or Event in
this file waits more than 2.0 s; the whole file runs in well under 15 s wall-clock
on a hermetic host.
"""
from __future__ import annotations

import base64
from dataclasses import replace
import json
import threading

import pytest

import control_plane.visible_turn_projection as vtp
from control_plane.visible_turn_projection import (
    MAX_ITEM_BYTES,
    MAX_RETAINED_TURN_BYTES,
    MAX_VIEWERS,
    ProjectionError,
    TurnKey,
    VisibleTurnProjection,
)


# ---------------------------------------------------------------------------
# Helpers — hermetic, no identity reads from the host.
# ---------------------------------------------------------------------------


def _make_key(native: str = "native-1") -> TurnKey:
    return TurnKey(
        attempt_id="att-1",
        session_epoch_id="epoch-1",
        process_generation_id="gen-1",
        generation_number=1,
        worker_id="worker-1",
        local_turn_id="local-1",
        native_turn_id=native,
    )


def _publish(proj, key, *, source_id, source_sequence, state, text):
    method = "item/updated" if state == "partial" else "item/completed"
    proj.publish(
        key,
        method=method,
        params={
            "item": {
                "type": "agentMessage",
                "id": source_id,
                "sequence": source_sequence,
                "text": text,
            }
        },
        native_turn_id=key.native_turn_id,
    )


# ===========================================================================
# F1 — upsert + small page strands a retained item
# ===========================================================================


def test_upsert_then_small_page_never_strands_a_retained_item():
    proj = VisibleTurnProjection()
    key = _make_key()
    grant = proj.mint_grant(key)

    # Step 1 — publish A as a partial.
    _publish(proj, key, source_id="A", source_sequence=0, state="partial", text="A-partial")

    # Step 2 — read with cursor=None, max_items=1; capture the post-first-page cursor.
    first = proj.read(key, reader_grant=grant, cursor=None, max_items=1)
    assert len(first.items) == 1
    assert first.items[0].source_item_id == "A"
    assert first.items[0].state == "partial"
    cursor_after_first = first.next_cursor

    # Step 3 — publish B as completed.
    _publish(proj, key, source_id="B", source_sequence=1, state="completed", text="B-completed")

    # Step 4 — publish A as completed (this UPSERTS A in place to a NEW publication sequence).
    _publish(proj, key, source_id="A", source_sequence=0, state="completed", text="A-completed")

    # Assertion (1) — drain one page at a time. Both source ids must appear, and A's
    # text must include the COMPLETED version. On the pinned module B is stranded,
    # so seen_ids is missing "B".
    seen = []
    cursor = None
    for _ in range(8):
        result = proj.read(key, reader_grant=grant, cursor=cursor, max_items=1)
        if not result.items:
            break
        seen.extend(result.items)
        cursor = result.next_cursor
    seen_ids = {it.source_item_id for it in seen}
    assert seen_ids == {"A", "B"}, (
        f"drain missed an id — pinned module strands retained content: seen {seen_ids}"
    )
    a_texts = [it.text for it in seen if it.source_item_id == "A"]
    assert "A-completed" in a_texts, (
        f"A's completed text is not in the drain — last-write-wins broken: {a_texts}"
    )

    # Assertion (2) — anti-skip invariant. After the first post-upsert page, decode the
    # issued next_cursor and assert that EVERY retained item NOT in that page has
    # publication_sequence strictly greater than the cursor's "s". On the pinned
    # module the cursor lands at A's new publication sequence (3), and B (pub_seq 2)
    # is stranded below it.
    first_post_upsert = proj.read(
        key, reader_grant=grant, cursor=cursor_after_first, max_items=1
    )
    decoded = base64.urlsafe_b64decode(first_post_upsert.next_cursor.encode("ascii"))
    cursor_payload = json.loads(decoded)
    s = cursor_payload["s"]
    served_ids = {it.source_item_id for it in first_post_upsert.items}
    record = proj._turns[key.native_turn_id]
    unserved = [it for it in record.items if it.source_item_id not in served_ids]
    bad = [it for it in unserved if it.publication_sequence <= s]
    assert not bad, (
        f"anti-skip violated: cursor s={s} but retained items have publication_sequence "
        f"<= s: {[(it.source_item_id, it.publication_sequence) for it in bad]}"
    )


def test_page_renders_in_source_order_not_publication_order():
    proj = VisibleTurnProjection()
    key = _make_key()
    grant = proj.mint_grant(key)

    # Discriminating scenario: publish A FIRST with source_sequence=1, then B with
    # source_sequence=0. Storage order is (A, B); independent source order is
    # (B, A). A render that respects source order renders [B, A]; a render that
    # respects storage order renders [A, B].
    _publish(proj, key, source_id="A", source_sequence=1, state="partial", text="A-partial")
    _publish(proj, key, source_id="B", source_sequence=0, state="completed", text="B-completed")
    _publish(proj, key, source_id="A", source_sequence=1, state="completed", text="A-completed")

    result = proj.read(key, reader_grant=grant, cursor=None, max_items=8)
    assert len(result.items) == 2, f"expected 2 items, got {len(result.items)}"
    # Source order: B (sequence 0) then A (sequence 1).
    assert result.items[0].source_item_id == "B", (
        f"expected B first (source_sequence=0), got {result.items[0].source_item_id!r}; "
        f"the page rendered storage order instead of source order"
    )
    assert result.items[1].source_item_id == "A", (
        f"expected A second (source_sequence=1), got {result.items[1].source_item_id!r}"
    )
    assert result.items[0].source_sequence == 0
    assert result.items[1].source_sequence == 1
    # Last-write-wins: A's state is the completed one.
    assert result.items[1].state == "completed"
    assert result.items[1].text == "A-completed"
    # F6 — ReadResult.items is the frozen ``tuple[VisibleItem, ...]`` shape, never a list.
    assert isinstance(result.items, tuple), (
        f"ReadResult.items must be a tuple, got {type(result.items).__name__}"
    )


def test_page_render_order_is_independent_of_publication_order():
    """F8 — render order is INDEPENDENT of publication order.

    Discriminating scenario with NO upsert: publish A (source_sequence=1) as
    a partial FIRST, then B (source_sequence=0) as completed. Publication
    order is then [A@1, B@2] and independent source order is [B(0), A(1)]
    — the two DISAGREE, and storage order [A, B] disagrees with source
    order too, so this test discriminates on BOTH axes.
    """
    proj = VisibleTurnProjection()
    key = _make_key()
    grant = proj.mint_grant(key)

    _publish(proj, key, source_id="A", source_sequence=1, state="partial", text="A-partial")
    _publish(proj, key, source_id="B", source_sequence=0, state="completed", text="B-completed")

    result = proj.read(key, reader_grant=grant, cursor=None, max_items=8)
    assert len(result.items) == 2, f"expected 2 items, got {len(result.items)}"

    # Source order: B (sequence 0) then A (sequence 1).
    assert result.items[0].source_item_id == "B", (
        f"expected B first (source_sequence=0), got {result.items[0].source_item_id!r}; "
        f"the page rendered publication/storage order instead of independent source order"
    )
    assert result.items[1].source_item_id == "A", (
        f"expected A second (source_sequence=1), got {result.items[1].source_item_id!r}"
    )
    assert result.items[0].source_sequence == 0
    assert result.items[1].source_sequence == 1

    # Pin that publication order really IS the opposite of the rendered order:
    # A was published first (publication_sequence < B's). A publication-order
    # render would put A first; source order puts B first, so this assertion
    # cannot be satisfied by a publication-order render.
    a_pub_seq = result.items[1].publication_sequence
    b_pub_seq = result.items[0].publication_sequence
    assert a_pub_seq < b_pub_seq, (
        f"expected A.publication_sequence < B.publication_sequence to pin that "
        f"publication order is opposite of rendered order, got A={a_pub_seq}, B={b_pub_seq}"
    )

    # F6 — ReadResult.items is the frozen ``tuple[VisibleItem, ...]`` shape.
    assert isinstance(result.items, tuple), (
        f"ReadResult.items must be a tuple, got {type(result.items).__name__}"
    )


# ===========================================================================
# F2 — mint_grant is not atomic across the budget check + UUID + bookkeeping
# ===========================================================================


class _UuidShim:
    """Seam: delegates to real ``uuid.uuid4`` but, while armed, makes the FIRST
    arriving caller wait on a ``threading.Event`` (timeout 2.0 s) that the SECOND
    arriving caller sets."""

    def __init__(self, real_module):
        self._real = real_module
        self._armed = False
        self._lock = threading.Lock()
        self._first_waiting = False
        self._gate = threading.Event()

    def uuid4(self):
        if not self._armed:
            return self._real.uuid4()
        with self._lock:
            if not self._first_waiting:
                self._first_waiting = True
                first = True
            else:
                self._gate.set()
                first = False
        if first:
            self._gate.wait(timeout=2.0)
        return self._real.uuid4()


@pytest.fixture
def uuid_shim(monkeypatch):
    real_uuid = vtp.uuid
    shim = _UuidShim(real_uuid)
    monkeypatch.setattr(vtp, "uuid", shim)
    return shim


def test_concurrent_mint_cannot_exceed_viewer_budget(uuid_shim):
    proj = VisibleTurnProjection()
    key = _make_key()

    # Establish one existing viewer with the shim NOT armed so no gate contention.
    uuid_shim._armed = False
    existing = proj.mint_grant(key)
    assert existing in proj._grants

    # Arm the shim. Two threads each call mint_grant for the same key.
    uuid_shim._armed = True

    results: dict = {}
    errors: dict = {}

    def worker(name: str):
        try:
            results[name] = proj.mint_grant(key)
        except ProjectionError as exc:
            errors[name] = exc

    t1 = threading.Thread(target=worker, args=("t1",))
    t2 = threading.Thread(target=worker, args=("t2",))
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)
    assert not t1.is_alive(), "thread t1 did not finish within 5s"
    assert not t2.is_alive(), "thread t2 did not finish within 5s"

    over_budget = [
        e for e in errors.values()
        if isinstance(e, ProjectionError) and e.code == "OVER_BUDGET"
    ]
    assert len(over_budget) == 1, (
        f"expected exactly 1 OVER_BUDGET, got {len(over_budget)}; errors={list(errors.values())}"
    )
    assert MAX_VIEWERS == 2, f"MAX_VIEWERS raised: got {MAX_VIEWERS}, expected 2"
    assert len(proj._viewers_by_turn[key]) == MAX_VIEWERS, (
        f"expected exactly {MAX_VIEWERS} viewers, got {len(proj._viewers_by_turn[key])} "
        f"({sorted(proj._viewers_by_turn[key])!r})"
    )
    live_grants = list(proj._grants.keys())
    assert len(live_grants) == MAX_VIEWERS, (
        f"expected exactly {MAX_VIEWERS} live grants, got {len(live_grants)}"
    )
    for grant in live_grants:
        assert proj.check_grant(grant) is not None, (
            f"grant {grant!r} does not resolve through check_grant"
        )

    # No thread raised any exception other than OVER_BUDGET.
    for name, exc in errors.items():
        assert exc.code == "OVER_BUDGET", (
            f"{name} raised a non-OVER_BUDGET error: code={exc.code!r}"
        )


def test_sequential_third_viewer_is_still_refused():
    """Contract pin: the sequential budget enforcement keeps working after the F2 fix."""
    proj = VisibleTurnProjection()
    key = _make_key()
    proj.mint_grant(key)
    proj.mint_grant(key)
    with pytest.raises(ProjectionError) as exc:
        proj.mint_grant(key)
    assert exc.value.code == "OVER_BUDGET"
    assert exc.value.message == "turn viewer budget is full"
    assert MAX_VIEWERS == 2
    assert len(proj._viewers_by_turn[key]) == MAX_VIEWERS


# ===========================================================================
# F3 — revoke between check_grant and the snapshot lock is invisible
# ===========================================================================


def test_revoke_between_check_and_snapshot_refuses_the_read():
    proj = VisibleTurnProjection()
    key = _make_key()
    grant_a = proj.mint_grant(key)
    grant_b = proj.mint_grant(key)

    _publish(proj, key, source_id="X", source_sequence=0, state="partial", text="hello")

    # Wrap check_grant: call the original, revoke A, then return the original result.
    # This simulates a revoke that lands between the unlocked check and the
    # snapshot-lock acquisition.
    original_check = proj.check_grant

    def wrapped_check(reader_grant):
        result = original_check(reader_grant)
        if reader_grant == grant_a:
            proj.revoke_grant(grant_a)
        return result

    proj.check_grant = wrapped_check

    with pytest.raises(ProjectionError) as exc:
        proj.read(key, reader_grant=grant_a, cursor=None, max_items=8)
    assert exc.value.code == "READER_REVOKED", (
        f"expected READER_REVOKED, got {exc.value.code!r}"
    )

    receipts = proj.refusal_receipts()
    assert any(code == "READER_REVOKED" for _, code, _ in receipts), (
        f"no READER_REVOKED refusal receipt recorded; got {receipts}"
    )


def test_read_completed_before_revocation_keeps_its_bytes():
    """Contract pin: bytes released by a read that already validated under the snapshot
    lock BEFORE the revoke are legitimate and are never retroactively invalidated."""
    proj = VisibleTurnProjection()
    key = _make_key()
    grant_a = proj.mint_grant(key)
    grant_b = proj.mint_grant(key)

    _publish(proj, key, source_id="X", source_sequence=0, state="partial", text="hello")

    result_before = proj.read(key, reader_grant=grant_a, cursor=None, max_items=8)
    assert len(result_before.items) == 1
    assert result_before.items[0].text == "hello"

    proj.revoke_grant(grant_a)

    # The ReadResult is a frozen dataclass; the bytes it already released are still held.
    assert len(result_before.items) == 1
    assert result_before.items[0].text == "hello"

    # B's subsequent read succeeds.
    result_b = proj.read(key, reader_grant=grant_b, cursor=None, max_items=8)
    assert len(result_b.items) == 1
    assert result_b.items[0].text == "hello"


def test_revoking_one_viewer_leaves_the_other_valid():
    """Contract pin: revoking one viewer does not affect a second viewer's reads."""
    proj = VisibleTurnProjection()
    key = _make_key()
    grant_a = proj.mint_grant(key)
    grant_b = proj.mint_grant(key)

    _publish(proj, key, source_id="X", source_sequence=0, state="partial", text="hello")

    proj.revoke_grant(grant_a)

    result_b = proj.read(key, reader_grant=grant_b, cursor=None, max_items=8)
    assert len(result_b.items) == 1
    assert result_b.items[0].text == "hello"

    with pytest.raises(ProjectionError) as exc:
        proj.read(key, reader_grant=grant_a, cursor=None, max_items=8)
    assert exc.value.code == "READER_REVOKED"


# ===========================================================================
# F4 — replacement-byte growth skips the eviction loop
# ===========================================================================


def test_replacement_enforces_the_same_retention_contract_as_append():
    proj = VisibleTurnProjection()
    key = _make_key()
    proj.mint_grant(key)

    # Publish 65 distinct small partials, each 1 byte of text.
    for i in range(65):
        _publish(proj, key, source_id=f"i{i}", source_sequence=i, state="partial", text="a")

    # Replace each with a `item/completed` carrying exactly 16_384 bytes of text.
    big = "x" * 16_384
    for i in range(65):
        _publish(
            proj, key,
            source_id=f"i{i}", source_sequence=i, state="completed", text=big,
        )

    record = proj._turns[key.native_turn_id]

    # The bounds were not raised.
    assert MAX_RETAINED_TURN_BYTES == 1024 * 1024, (
        f"MAX_RETAINED_TURN_BYTES raised: got {MAX_RETAINED_TURN_BYTES}, expected 1048576"
    )
    assert MAX_ITEM_BYTES == 16_384, (
        f"MAX_ITEM_BYTES raised: got {MAX_ITEM_BYTES}, expected 16384"
    )

    # Both the retained-bytes counter AND the true sum of retained item byte_lengths
    # are bounded. A counter-only clamp cannot pass this — we assert the real sum.
    assert record.retained_bytes <= MAX_RETAINED_TURN_BYTES, (
        f"retained_bytes {record.retained_bytes} > MAX_RETAINED_TURN_BYTES "
        f"{MAX_RETAINED_TURN_BYTES}"
    )
    true_sum = sum(it.byte_length for it in record.items)
    assert true_sum <= MAX_RETAINED_TURN_BYTES, (
        f"true sum of retained item.byte_length {true_sum} > "
        f"MAX_RETAINED_TURN_BYTES {MAX_RETAINED_TURN_BYTES}"
    )

    # The item just written by the LAST replacement is still retained.
    assert record.items[-1].source_item_id == "i64", (
        f"last item id {record.items[-1].source_item_id!r}, expected 'i64'"
    )
    assert record.items[-1].state == "completed"
    assert record.items[-1].byte_length == 16_384

    # Eviction was not silent — at least one gap records the byte overflow.
    reasons = [g.reason for g in record.gaps]
    assert "turn_byte_overflow" in reasons, (
        f"no turn_byte_overflow gap recorded; got {reasons}"
    )


# ===========================================================================
# F5 — replacement-eviction gap is unreachable when the eviction is last
# ===========================================================================


def test_replacement_eviction_gap_is_reachable_like_append():
    """When the LAST publication triggers an eviction, the gap it records must be
    REACHABLE by a subsequent drain — the same retention contract as the append
    branch. Concretely: 65 small partials (1 byte each), then EXACTLY 64
    replacements with 16_384-byte text. The 64th replacement is the final
    publication; it triggers an eviction that must record a gap AT its own
    publication sequence, with ``next_publication_sequence`` advanced to that
    same sequence. A drain that advances the cursor past every retained item
    must end with ``resync_required is False`` and ``gaps == ()``.
    """
    proj = VisibleTurnProjection()
    key = _make_key()
    grant = proj.mint_grant(key)

    # Step 1 — 65 small partials (1 byte each).
    for i in range(65):
        _publish(proj, key, source_id=f"i{i}", source_sequence=i, state="partial", text="a")

    # Step 2 — EXACTLY 64 replacements of i0..i63 with 16_384-byte text. i64 is
    # NOT replaced, so the final retained item is i64 (1 byte). The 64th
    # replacement is the final publication and triggers an eviction.
    big = "x" * 16_384
    for i in range(64):
        _publish(
            proj, key,
            source_id=f"i{i}", source_sequence=i, state="completed", text=big,
        )

    record = proj._turns[key.native_turn_id]

    # Eviction was not silent — at least one gap carries reason "turn_byte_overflow".
    overflow_gaps = [g for g in record.gaps if g.reason == "turn_byte_overflow"]
    assert overflow_gaps, (
        f"no turn_byte_overflow gap recorded; got reasons={[g.reason for g in record.gaps]}"
    )

    # Step 3 — drain with successive cursors (max_items=64, at most 8 iterations).
    cursor = None
    final = None
    for _ in range(8):
        result = proj.read(key, reader_grant=grant, cursor=cursor, max_items=64)
        final = result
        if not result.items:
            break
        cursor = result.next_cursor

    assert final is not None

    # The FINAL read is empty (no retained items past the cursor) AND its gap
    # filter has cleared the eviction gap because the gap's ``to_publication_sequence``
    # is reachable — i.e. it is NOT strictly greater than the cursor's "s".
    assert final.items == (), (
        f"final read items not empty: {[(it.source_item_id, it.publication_sequence) for it in final.items]}"
    )
    assert final.gaps == (), (
        f"final read gaps not empty: {[(g.from_publication_sequence, g.to_publication_sequence, g.reason) for g in final.gaps]}"
    )
    assert final.resync_required is False, (
        f"resync_required still True on final read; the eviction gap is unreachable: "
        f"gaps={final.gaps} cursor s={final.next_cursor!r}"
    )


# Generation cleanup must use full TurnKey, never a reused native ID alone.
def _setup_reused_native_turn_generations():
    projection = VisibleTurnProjection()
    old = TurnKey(attempt_id="attempt-old", session_epoch_id="epoch-old",
                  process_generation_id="generation-old", generation_number=1,
                  worker_id="worker", local_turn_id="local-old", native_turn_id="turn-1")
    current = replace(old, attempt_id="attempt-current", session_epoch_id="epoch-current",
                      process_generation_id="generation-current", generation_number=2,
                      local_turn_id="local-current")
    old_grant = projection.mint_grant(old)
    current_grant = projection.mint_grant(current)
    projection.publish(current, method="item/completed", native_turn_id="turn-1",
                       params={"item": {"type": "agentMessage", "id": "answer",
                                        "sequence": 0, "text": "current generation result"}})
    projection.arm_prebind(7)
    return projection, old, current, old_grant, current_grant


def _current_generation_text(projection, current, grant):
    return projection.read(current, reader_grant=grant, cursor=None, max_items=1).items[0].text


@pytest.mark.parametrize("cleanup", ["revoke_old_grant", "invalidate_old_generation"])
def test_old_generation_cleanup_preserves_current_projection(cleanup):
    projection, old, current, old_grant, current_grant = _setup_reused_native_turn_generations()
    assert _current_generation_text(projection, current, current_grant) == "current generation result"
    if cleanup == "revoke_old_grant":
        projection.revoke_grant(old_grant)
    else:
        projection.invalidate_generation(old)
    assert _current_generation_text(projection, current, current_grant) == "current generation result"
    assert projection.active_prebind_request_id() == 7


@pytest.mark.parametrize("cleanup", ["revoke_current_grant", "invalidate_current_generation"])
def test_current_generation_cleanup_still_removes_its_projection(cleanup):
    projection, old, current, old_grant, current_grant = _setup_reused_native_turn_generations()
    if cleanup == "revoke_current_grant":
        projection.revoke_grant(current_grant)
    else:
        projection.invalidate_generation(current)
    with pytest.raises(ProjectionError) as error:
        _current_generation_text(projection, current, current_grant)
    expected = "READER_REVOKED" if cleanup == "revoke_current_grant" else "TURN_NOT_BOUND"
    assert error.value.code == expected
    assert projection.active_prebind_request_id() is None
