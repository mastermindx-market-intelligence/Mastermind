"""Work-queue reads through source join over a REAL bound Runtime.

Proves that ``WorkspaceReadService._read_work`` drives the production
``list_roots_v2_from_runtime`` acquirer through a real
``RuntimeReadBinding(ObservationNamespace(...))`` over an actual SQLite
``Runtime``, and that the resulting body matches every bullet of the
parent diagnosis (exact values, not just truthiness).

PATH HAZARD (documented here, not changed in production): the namespace
capability compares the exact database path; on macOS a ``/var/...``
temp dir must be ``.resolve()``d (``/private/var/...``) or the bound
read refuses ``bound read custody unavailable``. ``pytest tmp_path``
is already resolved, so the fixture in
``test_workspace_source_join.actual`` is safe.
"""
from control_plane import executive_runtime as er
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_workspace_source_join import intent, actual  # noqa: F401  (pytest fixture, resolved from module globals)
from tests.test_workspace_read_service import cache_fixture, frame, run
import pytest
import re  # noqa: E402  (kept here so the events-guard regex stays near its use site)


def _service(cache, writer, bound, *, armed=None, runtime_identity=None):
    """Build a WorkspaceReadService that resolves the real work-queue
    producer (``list_roots_v2_from_runtime``) through the bounded
    Runtime returned by ``bound()``.
    """
    return WorkspaceReadService(
        cache=cache,
        runtime=writer,
        authorize=lambda p: True,
        armed=armed if armed is not None else {"ceo_submit_armed": False,
                                                "source": "control.json"},
        runtime_identity=runtime_identity if runtime_identity is not None else {
            "root": None, "db_present": True, "identity": None},
        bounded_runtime=lambda r: bound() if r is writer else pytest.fail(
            "bounded_runtime received the wrong runtime"),
    )


def test_work_read_over_actual_bound_runtime_is_available(actual, tmp_path):
    """Parent diagnosis bullet 1: every exact value, not just truthiness."""
    from control_plane.fabric_job_view import (
        _ROOT_ENUMERATION_NOTE, _UNARMED_ENTRY_V2,
    )
    from control_plane.work_queue_projection import WORK_QUEUE_SCHEMA
    writer, bound, namespace, job = actual
    _, _, cache = cache_fixture(tmp_path / "cache")
    service = _service(cache, writer, bound)
    response = run(service, frame("work"))
    # Envelope shape.
    assert response["ok"] is True
    body = response["result"]
    # Schema and projection.
    assert body["schema"] == WORK_QUEUE_SCHEMA
    assert body["availability"] == "AVAILABLE"
    assert body["lifecycle_source"]["schema"] == "mastermind.fabric_job_root_list.v2"
    # Coverage: PARTIAL (the producer surfaces PARTIAL provenance — the
    # bounded enumeration is unjoined without exact-root acquisition).
    assert body["coverage"] == {"count": 1, "total": 1, "truncated": False,
                                "completeness": "PARTIAL"}
    assert body["reason_codes"] == []
    # Queue-level effect_exception: NONE, no exception observed.
    assert body["effect_exception"] == {
        "value": "NONE", "scope": "RUNTIME_CURRENT_WORKER",
        "observable": False, "reason": "no_exception_observed",
    }
    # Source observation: SAME on both halves of the receipt.
    assert body["source_observation"]["state"] == "SAME"
    assert body["source_observation"]["runtime"]["state"] == "SAME"
    # Lifecycle source: degraded list is sorted by the producer
    # (``sorted(set(notes))`` in ``_root_list_v2_document``).
    assert body["lifecycle_source"]["degraded"] == [_UNARMED_ENTRY_V2,
                                                    _ROOT_ENUMERATION_NOTE]
    # Acquisition provenance: PARTIAL with the submitted job unjoined.
    provenance = body["lifecycle_source"]["runtime"]["acquisition"]["provenance"]
    assert provenance == {"state": "PARTIAL", "unjoined_job_ids": [job]}
    # Exactly one QUEUED row, lifecycle shape closed.
    queued = body["groups"]["QUEUED"]
    assert len(queued) == 1
    row = queued[0]
    assert row["root_job_id"] == job
    assert row["lifecycle"] == {"status": "QUEUED", "source": "EXECUTIVE_RUNTIME",
                                "orchestration_role": "aggregation", "depth": 0}
    # next_actor / capacity / effect: no producer -> UNKNOWN, no_producer.
    for column in ("next_actor", "capacity", "effect"):
        assert row[column] == {"value": "UNKNOWN", "source": None,
                                "reason": "no_producer",
                                "evidence_ref": None, "observed_at": None}, column
    # Acceptance: NOT_PROJECTED for a QUEUED row (no producer in this projection).
    assert row["acceptance"]["state"] == "NOT_PROJECTED"
    # Namespace custody: one enter, one exit, never left active.
    assert namespace.entries == namespace.exits == 1
    assert namespace.active is False


def test_work_read_is_bounded_and_never_reads_creation_events(actual, tmp_path,
                                                              monkeypatch):
    """Bullet 2: the read never falls back to unbounded jobs/attempts
    registries AND never issues a ``FROM events`` statement on the
    root-enumeration path.  At least one statement reads ``FROM jobs``.
    """
    writer, bound, namespace, job = actual
    _, _, cache = cache_fixture(tmp_path / "cache")
    # Mirror the sibling test's unbounded-fallback fail-monkeypatches.
    monkeypatch.setattr(er.JobRegistry, "list_jobs",
                        lambda *a, **k: pytest.fail("unbounded jobs"))
    monkeypatch.setattr(er.AttemptRegistry, "list_attempts",
                        lambda *a, **k: pytest.fail("unbounded attempts"))
    # Install a sqlite trace callback so we can observe every statement
    # the bounded read emits — same pattern as the sibling test.
    traces = []
    original = er.sqlite3.connect

    def connection(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.set_trace_callback(traces.append)
        return conn

    monkeypatch.setattr(er.sqlite3, "connect", connection)
    service = _service(cache, writer, bound)
    response = run(service, frame("work"))
    body = response["result"]
    # The bounded read still succeeds on the real producer path.
    assert response["ok"] is True
    assert body["availability"] == "AVAILABLE"
    # No unbounded Event/creation reads (the enumeration path excludes them
    # by design — see ``list_roots_v2_from_runtime`` docstring). Match
    # case-insensitively and on a word boundary so an ``ORDER BY`` or
    # column-alias leak doesn't slip through the substring check.
    assert not any(re.search(r"\bevents\b", s, re.IGNORECASE) for s in traces)
    # The bounded read DID read from the jobs registry (case-insensitive).
    assert any(re.search(r"\bFROM jobs\b", s, re.IGNORECASE) for s in traces)


def test_work_read_refuses_when_binding_invalidated(tmp_path, monkeypatch):
    """Bullet 3: a ``RuntimeReadBinding`` that has been ``invalidate()``d
    BEFORE the read refuses the work read with the typed code
    ``runtime_observation_not_same`` and the effect-exception reason
    ``read_refused`` — the producer falls into the bounded-unavailable
    branch (``_BOUNDED_UNAVAILABLE_NOTE`` + UNKNOWN generation), which
    the read-service runtime gate translates into the typed refusal.
    """
    from tests.test_executive_runtime_bounded_read import ObservationNamespace
    from control_plane.ceo_intent import submit_intent
    # Build a real bounded Runtime with a real ``RuntimeReadBinding``.
    root = tmp_path / "runtime"
    writer = er.Runtime.at(root)
    submit_intent(writer, intent())
    # Keep WAL/SHM stable across opens so the namespace identity check
    # doesn't flap (the sibling test fixture follows the same pattern).
    keeper = er.sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(writer.store.path)
    binding = er.RuntimeReadBinding(namespace)
    try:
        bound_runtime = er.Runtime.at(root, create=False, read_binding=binding)
        # Invalidate the binding BEFORE the read — the next ``_validate``
        # in the bounded read's ``physical_read`` scope raises
        # ``RuntimeReadUnavailable("bound read invalidated or not acquired")``,
        # which the producer's ``RuntimeProofError`` guard catches and
        # converts to a SAME-bounded-acquisition with UNKNOWN generation
        # and ``_BOUNDED_UNAVAILABLE_NOTE`` in ``degraded``.
        binding.invalidate()
        _, _, cache = cache_fixture(tmp_path / "cache")
        service = WorkspaceReadService(
            cache=cache, runtime=writer, authorize=lambda p: True,
            armed={"ceo_submit_armed": False, "source": "control.json"},
            runtime_identity={"root": None, "db_present": True, "identity": None},
            bounded_runtime=lambda r: bound_runtime,
        )
        response = run(service, frame("work"))
        assert response["ok"] is True
        body = response["result"]
        assert body["availability"] == "UNAVAILABLE"
        assert body["reason_codes"] == ["runtime_observation_not_same"]
        assert body["effect_exception"]["reason"] == "read_refused"
        # No rows landed — the refusal happened at the gate, BEFORE the
        # composer produced a body with groups.
        for group, rows in body["groups"].items():
            assert rows == [], group
        # The producer's bounded-unavailable note never reaches the
        # read-service typed envelope (the gate fires FIRST) — the
        # namespace counter confirms the read NEVER opened the namespace
        # at all: ``physical_read`` rejects on the FIRST ``_invalid``
        # check (inside the state lock) BEFORE the namespace context
        # manager is entered, so the read gate fails closed without
        # touching the namespace.
        assert namespace.entries == namespace.exits == 0
        assert namespace.active is False
    finally:
        keeper.close()


def test_work_read_two_roots_are_sorted_and_counted(actual, tmp_path):
    """Bullet 4: two submitted intents surface as two QUEUED rows, sorted
    by ``root_job_id``, with PARTIAL provenance listing both jobs."""
    from control_plane.work_queue_projection import WORK_QUEUE_SCHEMA
    writer, bound, namespace, first = actual
    from control_plane.ceo_intent import submit_intent
    second = submit_intent(writer, intent(2, workstream="WS:TWO"))["job_id"]
    _, _, cache = cache_fixture(tmp_path / "cache")
    service = _service(cache, writer, bound)
    response = run(service, frame("work"))
    assert response["ok"] is True
    body = response["result"]
    assert body["schema"] == WORK_QUEUE_SCHEMA
    assert body["availability"] == "AVAILABLE"
    assert body["coverage"]["count"] == 2
    assert body["coverage"]["total"] == 2
    assert body["coverage"]["truncated"] is False
    assert body["coverage"]["completeness"] == "PARTIAL"
    queued = body["groups"]["QUEUED"]
    assert len(queued) == 2
    # Sorted by root_job_id.
    ids = [row["root_job_id"] for row in queued]
    assert ids == sorted(ids)
    assert set(ids) == {first, second}
    # Unjoined_job_ids sorted by the producer (``sorted(included)`` in
    # ``_root_list_v2_document``); the workstream on the second intent
    # differs but does not affect the root enumeration path.
    provenance = body["lifecycle_source"]["runtime"]["acquisition"]["provenance"]
    assert provenance["state"] == "PARTIAL"
    assert provenance["unjoined_job_ids"] == sorted([first, second])
    # Namespace custody closed.
    assert namespace.entries == namespace.exits == 1
    assert namespace.active is False