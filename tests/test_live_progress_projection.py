"""Regression coverage for source-qualified live progress metadata: privacy, grants, rotation, bounds, ordering and cancellation."""
import hashlib
import pytest
from control_plane.visible_turn_projection import MAX_READ_ITEMS, ProjectionError, TurnKey, VisibleTurnProjection
THREAD = 'thread'
OTHER_THREAD = 'other-thread'
NATIVE_TURN = 'native-turn-1'
SECRET_COMMAND = 'SECRET-CMD-7f3a'
SECRET_OUTPUT = 'SECRET-OUT-9b2e'
SECRET_PRIVATE = 'SECRET-PRIV-4d11'
SECRET_REASONING = 'SECRET-REASON-2c55'
PLAN_PROSE = 'PLAN-PROSE-LEAK-6aa9'
TOOL_STARTED_TEXT = 'commandExecution: tool started'
TOOL_COMPLETED_TEXT = 'commandExecution: tool lifecycle completed; outcome unverified'
PLAN_TEXT_PREFIX = 'plan: authored plan (non-executable):'

def _turn_key(attempt='att-1', session_epoch='epoch-1', proc_gen='pgen-1', generation=1, worker='worker-1', local_turn='local-1', native_turn=NATIVE_TURN):
    return TurnKey(attempt, session_epoch, proc_gen, generation, worker, local_turn, native_turn)

def _hashed(item_id):
    """Tool/plan metadata items carry sha256(native id), never the raw id."""
    return 'sha256:' + hashlib.sha256(item_id.encode('utf-8')).hexdigest()

def _tool_item(item_id, extra=None):
    item = {'id': item_id, 'type': 'commandExecution', 'command': SECRET_COMMAND, 'aggregatedOutput': SECRET_OUTPUT}
    if extra:
        item.update(extra)
    return item

def _message_item(item_id, text, sequence):
    return {'id': item_id, 'type': 'agentMessage', 'text': text, 'sequence': sequence}

def _item_event(method, item, key=None, thread=THREAD, turn=None, **extra):
    if turn is None:
        turn = key.native_turn_id if key is not None else NATIVE_TURN
    return {'method': method, 'params': dict({'threadId': thread, 'turnId': turn, 'item': item}, **extra)}

def _plan_event(steps, key=None, thread=THREAD, turn=None, **extra):
    if turn is None:
        turn = key.native_turn_id if key is not None else NATIVE_TURN
    return {'method': 'turn/plan/updated', 'params': dict({'threadId': thread, 'turnId': turn, 'plan': steps}, **extra)}

def _turn_completed(key=None, thread=THREAD, status='interrupted'):
    turn = key.native_turn_id if key is not None else NATIVE_TURN
    return {'method': 'turn/completed', 'params': {'threadId': thread, 'turn': {'id': turn, 'status': status}}}

def _read_all(projection, key, grant, max_items=MAX_READ_ITEMS, limit=200):
    """Bounded cursor walk.

    ``next_cursor`` is always a nonempty string; the walk ends on the first
    settled empty page (no items, returned cursor equal to the one just
    consumed) and fails loudly if it never settles.
    """
    pages = []
    cursor = None
    for _ in range(limit):
        page = projection.read(key, reader_grant=grant, cursor=cursor, max_items=max_items)
        assert isinstance(page.next_cursor, str) and page.next_cursor
        pages.append(page)
        if not page.items and page.next_cursor == cursor:
            return pages
        cursor = page.next_cursor
    raise AssertionError('cursor walk did not settle within %d pages' % limit)

def _all_items(pages):
    return [item for page in pages for item in page.items]

def _all_gaps(pages):
    seen = {}
    for page in pages:
        for gap in page.gaps:
            seen[gap.from_publication_sequence, gap.to_publication_sequence, gap.reason] = gap
    return list(seen.values())

def _blob(pages):
    """Everything a reader can observe, joined for sentinel scans."""
    parts = []
    for item in _all_items(pages):
        parts.extend((item.source_item_id, item.state, item.text))
    for gap in _all_gaps(pages):
        parts.append(gap.reason)
    for page in pages:
        parts.extend(page.retained_scope)
        parts.append(page.publication_epoch)
    return '\n'.join(parts)

@pytest.fixture()
def projection():
    return VisibleTurnProjection()

def test_explicit_metadata_gate_mixed_grants(projection):
    key = _turn_key(attempt='att-gate')
    meta_grant = projection.mint_grant(key, progress_thread_id=THREAD)
    plain_grant = projection.mint_grant(key)
    projection.publish(key, **_plan_event([{'step': PLAN_PROSE + ' alpha', 'status': 'completed'}, {'step': PLAN_PROSE + ' beta', 'status': 'completed'}], key=key, explanation=PLAN_PROSE + ' explanation'))
    tool = _tool_item('gate-tool-1')
    projection.publish(key, **_item_event('item/started', tool, key=key, startedAtMs=1000))
    projection.publish(key, **_item_event('item/completed', tool, key=key, startedAtMs=1000, completedAtMs=2000))
    projection.publish(key, **_item_event('item/completed', _message_item('gate-msg-1', 'response body', 7), key=key))
    meta_pages = _read_all(projection, key, meta_grant)
    meta_items = _all_items(meta_pages)
    plain_items = _all_items(_read_all(projection, key, plain_grant))
    blob = _blob(meta_pages)
    assert [i.source_item_id for i in plain_items] == ['gate-msg-1']
    assert all((i.progress_metadata is False for i in plain_items))
    assert _hashed('gate-tool-1') in [i.source_item_id for i in meta_items]
    assert 'gate-tool-1' not in blob
    assert any((i.progress_metadata is True for i in meta_items))
    finished = next((i for i in meta_items if i.source_item_id == _hashed('gate-tool-1')))
    assert finished.state == 'completed'
    assert finished.text == TOOL_COMPLETED_TEXT
    assert finished.byte_length == len(TOOL_COMPLETED_TEXT.encode('utf-8'))
    plan_item = next((i for i in meta_items if i.source_item_id == 'authored-plan'))
    assert plan_item.progress_metadata is True
    assert plan_item.text.startswith(PLAN_TEXT_PREFIX)
    assert '0 pending, 0 in progress, 2 completed' in plan_item.text
    assert plan_item.state == 'partial'
    assert PLAN_PROSE not in blob
    assert not any((page.terminal for page in meta_pages))

def test_secret_sentinels_and_native_ids_never_surface(projection):
    key = _turn_key(attempt='att-secret')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    secrets = {'stdout': SECRET_PRIVATE, 'stderr': SECRET_PRIVATE, 'nativeCommandId': SECRET_PRIVATE}
    projection.publish(key, **_item_event('item/started', _tool_item('secret-item-1', extra=secrets), key=key, startedAtMs=10))
    projection.publish(key, **_item_event('item/completed', _tool_item('secret-item-1', extra=secrets), key=key, startedAtMs=10, completedAtMs=20))
    pages = _read_all(projection, key, grant)
    items = _all_items(pages)
    assert [i.source_item_id for i in items] == [_hashed('secret-item-1')]
    blob = _blob(pages)
    for secret in (SECRET_COMMAND, SECRET_OUTPUT, SECRET_PRIVATE, SECRET_REASONING, 'secret-item-1'):
        assert secret not in blob
    finished = items[0]
    assert finished.progress_metadata is True
    assert finished.state == 'completed'
    assert finished.text == TOOL_COMPLETED_TEXT
    assert isinstance(finished.byte_length, int) and finished.byte_length > 0

def test_foreign_identity_is_ignored_without_metadata_or_gaps(projection):
    key = _turn_key(attempt='att-foreign')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    projection.publish_demultiplexed(None, payload=_item_event('item/started', _tool_item('elsewhere-1'), thread=OTHER_THREAD, turn='other-native-turn', startedAtMs=1))
    pages = _read_all(projection, key, grant)
    assert not _all_items(pages)
    assert not _all_gaps(pages)
    projection.publish_demultiplexed(None, payload=_item_event('item/completed', _tool_item('foreign-tool-1'), key=key, startedAtMs=5, completedAtMs=6))
    pages = _read_all(projection, key, grant)
    assert [i.source_item_id for i in _all_items(pages)] == [_hashed('foreign-tool-1')]
    assert not _all_gaps(pages)
    projection.publish_demultiplexed(None, payload=_item_event('item/started', _tool_item('foreign-thread-item'), thread=OTHER_THREAD, key=key, startedAtMs=7))
    pages = _read_all(projection, key, grant)
    assert [i.source_item_id for i in _all_items(pages)] == [_hashed('foreign-tool-1')]
    assert not _all_gaps(pages)

def test_terminal_item_does_not_reopen_on_late_started(projection):
    key = _turn_key(attempt='att-regress')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    tool = _tool_item('regress-tool-1')
    message = _message_item('regress-msg-1', 'body', 3)
    projection.publish(key, **_item_event('item/started', tool, key=key, startedAtMs=1))
    started = {i.source_item_id: i for i in _all_items(_read_all(projection, key, grant))}
    assert started[_hashed('regress-tool-1')].state == 'partial'
    assert started[_hashed('regress-tool-1')].text == TOOL_STARTED_TEXT
    projection.publish(key, **_item_event('item/completed', tool, key=key, startedAtMs=1, completedAtMs=2))
    projection.publish(key, **_item_event('item/completed', message, key=key))
    pages = _read_all(projection, key, grant)
    before = {i.source_item_id: i for i in _all_items(pages)}
    assert set(before) == {_hashed('regress-tool-1'), 'regress-msg-1'}
    assert before[_hashed('regress-tool-1')].state == 'completed'
    assert not any((page.terminal for page in pages))
    projection.publish(key, **_item_event('item/started', tool, key=key, startedAtMs=1))
    projection.publish(key, **_item_event('item/updated', message, key=key))
    pages = _read_all(projection, key, grant)
    after = {i.source_item_id: i for i in _all_items(pages)}
    assert set(after) == set(before)
    for source_id, item in after.items():
        assert item.state == before[source_id].state
        assert item.text == before[source_id].text
        assert item.publication_sequence == before[source_id].publication_sequence
    assert not _all_gaps(pages)
    assert not any((page.terminal for page in pages))

def test_completed_turn_blocks_late_publication(projection):
    key = _turn_key(attempt='att-cancel')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    projection.publish(key, **_item_event('item/started', _tool_item('cancel-tool-1'), key=key, startedAtMs=7))
    projection.publish_demultiplexed(None, payload=_turn_completed(key=key, thread=OTHER_THREAD))
    assert not _read_all(projection, key, grant)[-1].terminal
    projection.publish_demultiplexed(None, payload=_turn_completed(key=key))
    pages = _read_all(projection, key, grant)
    assert pages[-1].terminal
    before_ids = [i.source_item_id for i in _all_items(pages)]
    projection.publish(key, **_item_event('item/completed', _tool_item('cancel-tool-late'), key=key, startedAtMs=8, completedAtMs=9))
    projection.publish(key, **_item_event('item/started', _tool_item('cancel-tool-1'), key=key, startedAtMs=8))
    projection.publish(key, **_plan_event([{'step': PLAN_PROSE, 'status': 'pending'}], key=key))
    projection.publish_demultiplexed(None, payload=_turn_completed(key=key))
    pages = _read_all(projection, key, grant)
    assert pages[-1].terminal
    assert [i.source_item_id for i in _all_items(pages)] == before_ids
    assert not _all_gaps(pages)
    assert PLAN_PROSE not in _blob(pages)

def test_revoke_regrant_rotation_and_attempt_binding(projection):
    key = _turn_key(attempt='att-revoke', native_turn='revoke-turn')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    projection.publish(key, **_item_event('item/completed', _tool_item('revoke-tool-1'), key=key, completedAtMs=4))
    assert len(_all_items(_read_all(projection, key, grant))) == 1
    epoch_before = _read_all(projection, key, grant)[-1].publication_epoch
    projection.revoke_grant(grant)
    with pytest.raises(ProjectionError):
        projection.read(key, reader_grant=grant, cursor=None, max_items=MAX_READ_ITEMS)
    fresh = projection.mint_grant(key, progress_thread_id=THREAD)
    pages = _read_all(projection, key, fresh)
    assert not _all_items(pages)
    assert not _all_gaps(pages)
    assert isinstance(pages[-1].publication_epoch, str)
    assert pages[-1].publication_epoch
    assert pages[-1].publication_epoch != epoch_before
    with pytest.raises(ProjectionError):
        projection.read(key, reader_grant=grant, cursor=None, max_items=MAX_READ_ITEMS)
    rotate_key = _turn_key(attempt='att-rotate', proc_gen='pgen-1', native_turn='rotate-turn')
    rotate_grant = projection.mint_grant(rotate_key, progress_thread_id=THREAD)
    projection.publish(rotate_key, **_item_event('item/completed', _tool_item('rotate-tool-1'), key=rotate_key, completedAtMs=2))
    assert len(_all_items(_read_all(projection, rotate_key, rotate_grant))) == 1
    projection.invalidate_generation(rotate_key)
    with pytest.raises(ProjectionError):
        projection.read(rotate_key, reader_grant=rotate_grant, cursor=None, max_items=MAX_READ_ITEMS)
    fresh_key = _turn_key(attempt='att-rotate', proc_gen='pgen-2', generation=2, native_turn='rotate-turn')
    fresh_rotate_grant = projection.mint_grant(fresh_key, progress_thread_id=THREAD)
    projection.publish(fresh_key, **_item_event('item/completed', _tool_item('rotate-tool-2'), key=fresh_key, completedAtMs=3))
    assert [i.source_item_id for i in _all_items(_read_all(projection, fresh_key, fresh_rotate_grant))] == [_hashed('rotate-tool-2')]
    third_key = _turn_key(attempt='att-other', native_turn='third-turn')
    projection.mint_grant(third_key, progress_thread_id=THREAD)
    with pytest.raises(ProjectionError):
        projection.read(third_key, reader_grant=fresh_rotate_grant, cursor=None, max_items=MAX_READ_ITEMS)
    with pytest.raises(ProjectionError):
        projection.read(fresh_key, reader_grant=None, cursor=None, max_items=MAX_READ_ITEMS)
    with pytest.raises(ProjectionError):
        projection.read(fresh_key, reader_grant=fresh_rotate_grant, cursor=None, max_items=0)

def test_plan_step_bound_and_unknown_private_fields(projection):
    key = _turn_key(attempt='att-bounds')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    projection.publish(key, **_item_event('item/started', {'id': 'ghost-reasoning', 'type': 'reasoning', 'text': SECRET_REASONING, 'summary': [{'type': 'summary_text', 'text': SECRET_REASONING}]}, key=key, startedAtMs=1))
    projection.publish(key, **_item_event('item/completed', {'id': 'ghost-future', 'type': 'vendorFutureTool', 'payload': SECRET_REASONING}, key=key, startedAtMs=2, completedAtMs=3))
    projection.publish(key, **_item_event('item/completed', _tool_item('known-tool-1', extra={'vendorPrivate': SECRET_PRIVATE}), key=key, startedAtMs=4, completedAtMs=5))
    pages = _read_all(projection, key, grant)
    assert [i.source_item_id for i in _all_items(pages)] == [_hashed('known-tool-1')]
    assert not _all_gaps(pages)
    blob = _blob(pages)
    assert SECRET_REASONING not in blob
    assert SECRET_PRIVATE not in blob
    projection.publish(key, **_plan_event([{'step': '%s-%d' % (PLAN_PROSE, n), 'status': 'pending'} for n in range(129)], key=key))
    pages = _read_all(projection, key, grant)
    assert [gap.reason for gap in _all_gaps(pages)] == ['parser_failure']
    assert PLAN_PROSE not in _blob(pages)
    assert not [i for i in _all_items(pages) if i.source_item_id == 'authored-plan']
    projection.publish(key, **_plan_event([{'step': '%s-%d' % (PLAN_PROSE, n), 'status': 'completed'} for n in range(128)], key=key))
    pages = _read_all(projection, key, grant)
    plan_items = [i for i in _all_items(pages) if i.source_item_id == 'authored-plan']
    assert len(plan_items) == 1
    assert plan_items[0].progress_metadata is True
    assert plan_items[0].state == 'partial'
    assert '0 pending, 0 in progress, 128 completed' in plan_items[0].text
    assert PLAN_PROSE not in _blob(pages)
    assert len(_all_gaps(pages)) == 1
    assert not any((page.terminal for page in pages))

def test_item_bound_retention_and_gap_accounting(projection):
    key = _turn_key(attempt='att-overflow')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    total = 300
    for n in range(total):
        projection.publish(key, **_item_event('item/completed', _tool_item('overflow-tool-%04d' % n), key=key, completedAtMs=n + 1))
    pages = _read_all(projection, key, grant)
    items = _all_items(pages)
    assert 1 <= len(items) <= 256
    ids = [i.source_item_id for i in items]
    assert len(set(ids)) == len(ids)
    assert _hashed('overflow-tool-%04d' % (total - 1)) in ids
    gaps = _all_gaps(pages)
    assert total - len(items) <= len(gaps) <= 256
    assert all((gap.reason in {'turn_item_overflow', 'turn_byte_overflow', 'retained_gap'} for gap in gaps))
    assert any((page.resync_required for page in pages))
    for page in pages:
        assert len(page.items) <= MAX_READ_ITEMS
        ordering = [(i.source_sequence, i.publication_sequence) for i in page.items]
        assert ordering == sorted(ordering)

def test_cursor_walk_exact_once_in_display_order(projection):
    key = _turn_key(attempt='att-pages')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    tools = ['page-tool-%d' % n for n in range(4)]
    for n, tool_id in enumerate(tools):
        projection.publish(key, **_item_event('item/completed', _tool_item(tool_id), key=key, completedAtMs=n + 1))
    projection.publish(key, **_item_event('item/completed', _message_item('page-msg-a', 'message-a-body', 30), key=key))
    projection.publish(key, **_item_event('item/completed', _message_item('page-msg-b', 'message-b-body', 10), key=key))
    pages = _read_all(projection, key, grant, max_items=3)
    assert len(pages) >= 3
    seen = _all_items(pages)
    assert [i.source_item_id for i in seen] == [*(_hashed(t) for t in tools), 'page-msg-b', 'page-msg-a']
    assert len({(i.source_item_id, i.publication_sequence) for i in seen}) == len(seen)
    assert seen[-1].publication_sequence < seen[-2].publication_sequence
    for page in pages:
        assert len(page.items) <= 3
        ordering = [(i.source_sequence, i.publication_sequence) for i in page.items]
        assert ordering == sorted(ordering)
    assert not any((page.terminal for page in pages))
    assert 'message-a-body' in _blob(pages)

def test_malformed_payloads_record_parser_failure_gaps(projection):
    key = _turn_key(attempt='att-malformed')
    grant = projection.mint_grant(key, progress_thread_id=THREAD)
    projection.publish_demultiplexed(None, payload=_plan_event(PLAN_PROSE, key=key))
    projection.publish_demultiplexed(None, payload=_item_event('item/completed', 'not-an-object', key=key, completedAtMs=5))
    projection.publish_demultiplexed(None, payload=_item_event('item/started', _tool_item('missing-ts-1'), key=key))
    projection.publish_demultiplexed(None, payload=_plan_event([{'step': 'x', 'status': 'done'}], key=key))
    pages = _read_all(projection, key, grant)
    assert [gap.reason for gap in _all_gaps(pages)] == ['parser_failure'] * 4
    assert not _all_items(pages)
    assert PLAN_PROSE not in _blob(pages)
    projection.publish_demultiplexed(None, payload=_item_event('item/completed', _tool_item('post-malformed-1'), key=key, startedAtMs=6, completedAtMs=7))
    pages = _read_all(projection, key, grant)
    assert [i.source_item_id for i in _all_items(pages)] == [_hashed('post-malformed-1')]
    assert len(_all_gaps(pages)) == 4
