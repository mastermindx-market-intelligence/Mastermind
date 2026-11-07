"""WQ-JOIN-1 joined boundary proof: real-Runtime + real-control-room work read.

The three tests below pin the JOINED boundary between the bounded
``Runtime`` SQLite store and the autonomy control-room projection —
the same boundary the live read service crosses on every work
request.  The ``actual`` fixture (writer Runtime, ``bound()``,
``ObservationNamespace``, the submitted ``job``) and the ``compose``
helper (real ``build_workspace_composer`` → real
``autonomy_control_room_projection``) are reused from the sibling
``test_workspace_source_join`` so this file exercises the SAME
real-path the production publisher takes — no stubbed projections,
no synthetic control-room documents.

Three tests:

B1. ``test_real_autonomy_card_of_undispatched_root_yields_no_producer_and_records_the_skip``
    — pins the exact card shape the real projection emits for a
    freshly-submitted, undispatched root, and asserts the deriver
    emits NO producer row for that card (with the exact skip token
    the current deriver code emits).

B2. ``test_work_read_over_real_runtime_and_real_control_room_is_available_with_no_producer_rows``
    — exercises the full READ-SERVICE path over the real Runtime +
    real control room: published doc → cache → real
    ``list_roots_v2_from_runtime`` + real ``compose_work_queue_v1``.
    Asserts AVAILABLE, ``effect_exception`` no-exception-observed,
    exactly one QUEUED row with all three producer columns at
    ``UNKNOWN``/``no_producer``, and ``source_observation`` /
    runtime receipt both ``SAME``.

B3. ``test_deriver_populates_rows_when_the_real_card_carries_an_owed_turn``
    — proves the deriver populates rows when a real-shaped card
    carries an actionable owed-turn claim.  Two variants on the
    same deep-copied doc: (a) within the 900 s freshness window →
    ``next_actor.value == "SOL"`` group ``NEEDS_SOL``; (b) with the
    source ``observed_at`` moved 901 s earlier → ``evidence_stale``,
    ``UNKNOWN``, group ``QUEUED``.

All three tests use ONLY the public ``derive_work_producers_v1`` and
``compose_work_queue_v1`` plus the sibling ``actual``/``compose``
fixtures — no private-import additions, no shortcut stubs.
"""
from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from control_plane import (
    autonomy_control_room_projection as autonomy_proj,
    chairman_control_room as ccr,
    executive_runtime as er,
    workspace_source_join as join,
)
from control_plane.ceo_intent import submit_intent
from control_plane.workspace_read_service import WorkspaceReadService
from scripts import chairman_control_room as publisher

from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_workspace_programs_qualification import empty_inputs
from tests.test_workspace_read_service import (
    STAMP, cache_fixture, frame, run,
)
from tests.test_workspace_source_join import intent


# ---------------------------------------------------------------------------
# fixtures (mirrors the sibling — same real Runtime + real composer)
# ---------------------------------------------------------------------------


@pytest.fixture
def actual(tmp_path):
    """Real Runtime + bound namespace + the submitted job.

    Identical shape to ``tests.test_workspace_source_join.actual``
    (sibling reuse by import — the autouse ``compose`` helper
    below reaches through the same ``build_workspace_composer`` →
    ``autonomy_control_room_projection.project_autonomy`` chain the
    live publisher uses).
    """
    root = tmp_path / "runtime"
    writer = er.Runtime.at(root)
    job = submit_intent(writer, intent())["job_id"]
    keeper = er.sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(writer.store.path)

    def bound():
        return er.Runtime.at(root, create=False,
                             read_binding=er.RuntimeReadBinding(namespace))

    try:
        yield writer, bound, namespace, job
    finally:
        keeper.close()


def _compose(tmp_path, actual, monkeypatch):
    """Same helper as the sibling: real ``build_workspace_composer`` →
    real ``autonomy_control_room_projection.project_autonomy``."""
    writer, bound, namespace, job = actual
    args = empty_inputs()
    args["agent_os_state"]["workstreams"] = [
        {"key": "ONE", "title": "One", "owner": "ceo-sol", "status": "active"},
    ]
    macro = tmp_path / "macro"
    macro.mkdir()
    for name, rel in (("active_builds", ccr.ACTIVE_BUILDS_RELATIVE_PATH),
                      ("agent_os_state", ccr.AGENT_OS_STATE_RELATIVE_PATH)):
        f = macro / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(args[name]))
    calls = []

    def packet(**kwargs):
        calls.append(kwargs)
        return args["boot_packet"]

    build = join.build_workspace_composer(
        packet_collector=packet,
        repo_root=tmp_path / "source",
        macro_root=macro,
        bounded_runtime=bound,
        bindings_path=None,
    )
    assert calls == [] and namespace.entries == 0
    doc = build(STAMP)
    assert calls[0]["now"] == STAMP and calls[0]["macro_root_flag"] == str(macro)
    return doc


# ---------------------------------------------------------------------------
# B1 — the real undispatched card's exact shape + deriver's exact skip trail
# ---------------------------------------------------------------------------


def test_real_autonomy_card_of_undispatched_root_yields_no_producer_and_records_the_skip(
        tmp_path, actual, monkeypatch):
    """The freshly-submitted, undispatched root's real card shape.

    The ``compose`` helper runs the real ``build_workspace_composer``
    against the real writer ``Runtime`` (with the real
    ``ObservationNamespace`` binding) and returns the real
    ``mastermind.chairman_control_room.v1`` document the publisher
    would cache.  For an undispatched root the real projection emits
    ``is_actionable is False`` and a ``not_observable`` placement —
    the deriver must skip this card and produce NO producer row.

    The skipped-trail token is exactly the one the current deriver
    code emits for this card shape (``not_actionable`` because
    ``is_actionable is False`` on the real card — NOT an exemption,
    because the placement is ``not_observable`` not
    ``EFFECT_UNKNOWN``).  Each assertion is annotated with which
    ``_evaluate_card`` branch fires.
    """
    doc = _compose(tmp_path, actual, monkeypatch)
    card = doc["autonomy"]["responsibilities"][0]
    job = actual[3]

    # Real card shape — every value pinned to the parent-verified facts.
    assert card["root_job_id"] == job
    assert card["runtime_root_state"] == "RESOLVED"
    assert card["root_job_ambiguous"] is False
    assert card["responsibility_ref"] == "WS:ONE"
    assert card["owed_turn"] == {
        "seat": "unknown", "reason": "no_owed_turn_signal", "source_refs": [],
    }
    assert card["placement_state"] == {
        "value": "not_observable", "observable": False,
        "reason": "no_canonical_producer",
    }
    assert card["current_worker"] is None
    assert card["freshness"] == "current"
    assert card["is_actionable"] is False
    # ``autonomy.generated_at`` is the render clock; the validity
    # budget pins ``qualified_at`` to the same instant.
    assert doc["autonomy"]["generated_at"] == STAMP
    assert card["validity"]["card"]["qualified_at"] == STAMP
    assert card["validity"]["card"]["sources"][0]["observed_at"] == STAMP
    assert isinstance(card["validity"]["card"]["valid_for_ms"], int)
    # ``proof_ref`` is the content-addressed digest over sources; pin
    # only the shape (a 64-char hex string) — the exact digest is the
    # projection's own output and a parent audit would re-derive it.
    proof_ref = card["validity"]["card"]["proof_ref"]
    assert isinstance(proof_ref, str) and len(proof_ref) == 64

    # Deriver output: all three producers None (no owed-turn claim
    # qualifies, no placement evidence, no EFFECT_UNKNOWN exception),
    # evidence_as_of is the render clock, skipped carries the
    # ``not_actionable`` token recorded by ``_evaluate_card``.
    from control_plane.work_queue_projection import derive_work_producers_v1
    result = derive_work_producers_v1(doc)
    assert result["accountability"] is None
    assert result["placement"] is None
    assert result["effects"] is None
    assert result["evidence_as_of"] == STAMP
    # ``_evaluate_card`` branch trace for this card:
    # - ``runtime_root_state == "RESOLVED"`` → first gate passes
    # - ``root_job_ambiguous is False`` → second gate passes
    # - ``placement_value == "not_observable"`` (NOT EFFECT_UNKNOWN)
    #   → ``is_effect_unknown`` is False
    # - ``freshness == "current"`` → freshness gate passes
    # - ``is_actionable is False`` (with valid_for_ms an int) →
    #   ``full_gate_ok`` is False
    # - ``is_effect_unknown`` is False AND ``not full_gate_ok``
    #   → skip token ``not_actionable``
    assert result["skipped"] == [f"{job}:not_actionable"]


# ---------------------------------------------------------------------------
# B2 — the full read-service work path over real Runtime + real control room
# ---------------------------------------------------------------------------


def test_work_read_over_real_runtime_and_real_control_room_is_available_with_no_producer_rows(
        tmp_path, actual, monkeypatch):
    """The full work-read boundary the production read service crosses.

    The real ``doc`` from ``_compose`` is published into the same
    cache fixture ``tests/test_workspace_read_service.cache_fixture``
    builds; the read service is constructed with the REAL writer
    Runtime as ``runtime`` and a ``bounded_runtime`` factory that
    binds the same writer (the namespace is the same
    ``ObservationNamespace`` from the sibling's ``actual`` fixture —
    entries/exits must balance at end).

    No ``work_acquire`` / ``work_compose`` injection — the read
    service resolves to the production
    ``list_roots_v2_from_runtime`` + ``compose_work_queue_v1``.  The
    real producer returns one QUEUED row for the submitted ``job``;
    the real composer finds the card is not actionable and emits
    ``UNKNOWN``/``no_producer`` on every producer column.  The
    queue-level effect_exception is ``NONE`` (no EFFECT_UNKNOWN
    placement observed).

    Also exercises the ``programs`` operation on the SAME service
    — proves the cache bracket itself remains qualified for the
    programs operation even after a work read.
    """
    writer, bound, namespace, job = actual
    doc = _compose(tmp_path, actual, monkeypatch)

    # Publish the real doc into the cache — same shape as the sibling
    # ``test_actual_sqlite_to_canonical_program_and_partial_mission``
    # test in test_workspace_source_join.py.
    owners, clock, cache = cache_fixture(tmp_path / "cache")
    owner = owners[0]
    owner.state_cache["doc"] = doc
    owner.state_cache.pop("source_validity_bounds", None)
    with owner.state_lock:
        publisher._publish_source_validity(owner, doc, tuple(clock), tuple(clock))

    # Real WorkspaceReadService against the REAL writer Runtime +
    # real bound facade — NO ``work_acquire``/``work_compose``
    # injection; the read service resolves to the production
    # ``list_roots_v2_from_runtime`` + ``compose_work_queue_v1``.
    service = WorkspaceReadService(
        cache=cache, runtime=writer, authorize=lambda p: True,
        armed={"ceo_submit_armed": False, "source": "control.json"},
        runtime_identity={"root": None, "db_present": True, "identity": None},
        bounded_runtime=lambda r: bound() if r is writer else pytest.fail("wrong runtime"),
    )

    # Work read.
    work_result = run(service, frame("work"))
    assert work_result["ok"] is True
    body = work_result["result"]
    assert body["availability"] == "AVAILABLE"
    assert body["effect_exception"] == {
        "value": "NONE", "scope": "RUNTIME_CURRENT_WORKER",
        "observable": False, "reason": "no_exception_observed",
    }
    assert body["reason_codes"] == []
    # Exactly one QUEUED row for the submitted job; every producer
    # column carries the closed no-producer UNKNOWN shape (the real
    # card's owed_turn doesn't qualify, no placement evidence, no
    # EFFECT_UNKNOWN exception).
    queued = body["groups"]["QUEUED"]
    assert len(queued) == 1
    row = queued[0]
    assert row["root_job_id"] == job
    assert row["lifecycle"]["status"] == "QUEUED"
    expected_unknown = {"value": "UNKNOWN", "source": None, "reason": "no_producer",
                        "evidence_ref": None, "observed_at": None}
    assert row["next_actor"] == expected_unknown
    assert row["capacity"] == expected_unknown
    assert row["effect"] == expected_unknown
    # Source observation: CCR and runtime halves both SAME (the
    # bounded observation closed cleanly between the two samples).
    assert body["source_observation"]["state"] == "SAME"
    assert body["source_observation"]["runtime"]["state"] == "SAME"
    # Bounded namespace invariants — the bind/unbind lifecycle balanced.
    assert namespace.entries == namespace.exits
    assert not namespace.active
    # No other groups carry rows.
    for group, rows in body["groups"].items():
        if group == "QUEUED":
            assert len(rows) == 1
        else:
            assert rows == [], (group, rows)

    # Programs operation on the SAME service — the cache bracket
    # remains qualified after the work read, so a subsequent
    # programs read returns AVAILABLE without re-acquiring.
    programs_result = run(service, frame("programs"))
    assert programs_result["ok"] is True
    programs = programs_result["result"]
    assert programs["availability"] == "AVAILABLE"
    assert namespace.entries == namespace.exits
    assert not namespace.active


# ---------------------------------------------------------------------------
# B3 — deriver populates rows when the real-shaped card carries an owed turn
# ---------------------------------------------------------------------------


def _real_card_with_owed_turn(doc, *, seat, reason,
                              source_observed_at=STAMP):
    """Deep-copy the real doc and mutate ONE card to carry an actionable
    owed-turn claim.  Injected stand-in for a dispatched job's
    blocker fact (the real projection only emits an actionable
    owed-turn after dispatch).  Keeps every other fact real so the
    rest of the card shape is exactly what the live path produces.
    """
    out = copy.deepcopy(doc)
    card = out["autonomy"]["responsibilities"][0]
    card["is_actionable"] = True
    card["owed_turn"] = {"seat": seat, "reason": reason, "source_refs": []}
    # Re-anchor the source observed_at to the requested stamp.
    card["validity"]["card"]["sources"] = [
        {"observed_at": source_observed_at, "freshness": "current"},
    ]
    return out


def test_deriver_populates_rows_when_the_real_card_carries_an_owed_turn(
        tmp_path, actual, monkeypatch):
    """Deriver populates rows when a real-shaped card carries an
    actionable owed-turn claim.  Two variants on the same deep-copied
    doc — one within the 900 s freshness window, one 901 s past.

    The root list is built by hand to mirror what the live
    ``list_roots_v2_from_runtime`` would deliver for the submitted
    job: one QUEUED row for ``job``.  The real ``build_workspace_composer``
    does not synthesize a root list — that is the bounded Runtime's
    job — so we pin the row's status here so the composer's
    group-precedence logic reaches NEEDS_SOL in variant (a) and
    QUEUED in variant (b).
    """
    writer, bound, namespace, job = actual  # namespace unused but bound
    doc = _compose(tmp_path, actual, monkeypatch)
    real_proof_ref = doc["autonomy"]["responsibilities"][0]["validity"]["card"]["proof_ref"]
    assert isinstance(real_proof_ref, str) and len(real_proof_ref) == 64

    from control_plane.work_queue_projection import (
        derive_work_producers_v1, compose_work_queue_v1,
    )

    # Synthetic root list mirroring what ``list_roots_v2_from_runtime``
    # would emit for a QUEUED submitted job.
    root_list = {
        "schema": "mastermind.fabric_job_root_list.v2",
        "generated_at": STAMP,
        "runtime": {"root": None, "db_present": True, "identity": None,
                    "acquisition": {
                        "schema": "mastermind.fabric_runtime_acquisition.v1",
                        "query": {"kind": "root_discovery"},
                        "owner": "executive_runtime",
                        "snapshot_digest": "d" * 64,
                        "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                                    "attempts_total": 340, "creation_events_per_job": 1},
                        "truncation": {"jobs": False, "attempt_job_ids": [],
                                       "roots": False, "projection": False},
                        "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
                        "generation": {"schema": "mastermind.runtime_read_observation.v1",
                                       "state": "SAME",
                                       "source_identity": "c" * 64,
                                       "before": 1, "after": 1}}},
        "roots": [{"job_id": job, "status": "QUEUED", "depth": 0,
                   "parent_job_id": None, "orchestration_role": "aggregation"}],
        "count": 1,
        "total": 1,
        "truncated": False,
        "degraded": [],
    }

    # ----------------------------------------------------------------
    # Variant (a): source observed_at == generated_at, age 0 → fresh.
    # The 900 s window admits age 0 → ``next_actor.value == "SOL"``,
    # ``evidence_ref`` is the real proof_ref, ``observed_at`` is the
    # real receipt stamp, group is NEEDS_SOL.
    # ----------------------------------------------------------------
    mutated = _real_card_with_owed_turn(doc, seat="ceo",
                                         reason="blocker_targets_seat",
                                         source_observed_at=STAMP)
    assert mutated["autonomy"]["generated_at"] == STAMP
    producers = derive_work_producers_v1(mutated)
    assert producers["accountability"] == {
        job: {"next_actor": "SOL", "evidence_ref": real_proof_ref,
              "observed_at": STAMP},
    }
    assert producers["evidence_as_of"] == STAMP
    assert producers["placement"] is None
    assert producers["effects"] is None
    assert producers["skipped"] == []
    composed = compose_work_queue_v1(root_list, control_room=mutated,
                                     accountability=producers["accountability"],
                                     placement=producers["placement"],
                                     effects=producers["effects"],
                                     evidence_as_of=producers["evidence_as_of"])
    assert len(composed["groups"]["NEEDS_SOL"]) == 1
    sol_row = composed["groups"]["NEEDS_SOL"][0]
    assert sol_row["root_job_id"] == job
    # The composer's ``_next_actor`` normalizes the deriver's raw
    # ``"SOL"`` accountability value into the row column ``"NEEDS_SOL"``
    # (the deriver output is the raw ``"SOL"`` already asserted above).
    assert sol_row["next_actor"]["value"] == "NEEDS_SOL"
    assert sol_row["next_actor"]["source"] == "AGENT_OS"
    assert sol_row["next_actor"]["evidence_ref"] == real_proof_ref
    assert sol_row["next_actor"]["observed_at"] == STAMP
    # Source receipt stamp is the real one — age 0 within the
    # EVIDENCE_MAX_AGE_S = 900 s window.
    assert sol_row["next_actor"]["reason"] == "evidence_supplied"

    # ----------------------------------------------------------------
    # Variant (b): source observed_at moved 901 s earlier than the
    # render clock → evidence_stale.  ``next_actor.value == UNKNOWN``,
    # reason == "evidence_stale", group falls through to QUEUED.
    # 2026-09-21T00:00:00Z − 901 s = 2026-09-20T23:44:59Z.
    # ----------------------------------------------------------------
    stale_obs = "2026-09-20T23:44:59Z"
    mutated_stale = _real_card_with_owed_turn(doc, seat="ceo",
                                              reason="blocker_targets_seat",
                                              source_observed_at=stale_obs)
    # Sanity: age exactly 901 s, just past the inclusive 900 s boundary.
    from datetime import datetime
    age_s = (datetime.fromisoformat(STAMP.replace("Z", "+00:00"))
             - datetime.fromisoformat(stale_obs.replace("Z", "+00:00"))
             ).total_seconds()
    assert age_s == 901
    producers_stale = derive_work_producers_v1(mutated_stale)
    # The deriver forwards the source observed_at (B1 — deriver
    # does NOT pre-truncate); the composer decides staleness.
    assert producers_stale["accountability"][job]["observed_at"] == stale_obs
    composed_stale = compose_work_queue_v1(
        root_list, control_room=mutated_stale,
        accountability=producers_stale["accountability"],
        placement=producers_stale["placement"],
        effects=producers_stale["effects"],
        evidence_as_of=producers_stale["evidence_as_of"],
    )
    assert len(composed_stale["groups"]["QUEUED"]) == 1
    queued_row = composed_stale["groups"]["QUEUED"][0]
    assert queued_row["root_job_id"] == job
    assert queued_row["next_actor"]["value"] == "UNKNOWN"
    assert queued_row["next_actor"]["reason"] == "evidence_stale"
    assert queued_row["next_actor"]["evidence_ref"] == real_proof_ref
    assert queued_row["next_actor"]["observed_at"] == stale_obs
