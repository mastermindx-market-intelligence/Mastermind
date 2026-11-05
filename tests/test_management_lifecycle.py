"""L-R3 — the read-only manager-cycle lifecycle disposition projection.

Fixtures are REAL record shapes copied from production run_events / decision rows, identities
intact: the CN 2026-10-20 and HK 2026-10-15 missing_submission failures, the US 2026-10-21
accepted-and-queued cycle, the US 2026-10-09 accepted-and-settled no-change cycle, the 2026-10-16
cycle that left no record at all, and the 2026-10-22 autonomous cycle whose decision row was
replaced by a later run. The only file read here is this module's own source, for the inertness
guard; nothing is written, and no network or scheduler is involved.
"""
import ast
import copy
import inspect
import re
from datetime import datetime, timezone

import pytest

from brain import management_lifecycle as ML

KEYS = {
    "schema", "job", "book", "due_at", "state", "reason", "failure_kind", "failure_evidence",
    "label_misleading", "settlement", "scheduler_run_id", "brain_run_id", "packet_id", "asof",
    "decision_row_superseded", "overdue", "started_at", "finished_at", "sources",
}
BOOK_KEYS = {
    "schema", "book", "run_status", "last_decision_at", "last_attempt_at", "next_scheduled_at",
    "failure_reason_code", "halted_by", "basis_due_at",
}

CN_ERROR_TEXT = "Exception('Claude Code returned an error result: success')"


def _now(text):
    return datetime.fromisoformat(text)


def _opp(job, book, due_at, **fields):
    opportunity = {"job": job, "book": book, "due_at": due_at, "enabled": True}
    opportunity.update(fields)
    return opportunity


def _started(job, book, ts, run_id):
    return {"ts": ts, "kind": "run_started", "job": job, "book": book, "step": "start",
            "status": "ok", "actor": "system",
            "extra": {"run_id": run_id, "trigger": "cron", "git_sha": "d31aade9", "flags": {}}}


def _finished(job, book, ts, run_id, status, extra, severity=None):
    event = {"ts": ts, "kind": "run_finished", "job": job, "book": book, "step": "end",
             "status": status, "actor": "system",
             "extra": {"run_id": run_id, "trigger": "cron", "git_sha": "d31aade9",
                       "artifacts": [], **extra}}
    if severity is not None:
        event["severity"] = severity
    return event


def _packet(book, ts, run_id, packet_id, asof):
    return {"ts": ts, "kind": "packet_accepted", "job": "", "book": book,
            "step": "submission_boundary", "status": "ok", "actor": "system",
            "extra": {"mode": "enforce", "run_id": run_id, "packet_id": packet_id, "asof": asof,
                      "risk_direction": "risk_on"}}


def _row(book, asof, run_id, ts, target_status, *, decision_effective, error=None,
         executed_n=0, holdings_n=0, packet_id=None):
    return {"asof": asof, "book": book, "decision_effective": decision_effective, "error": error,
            "executed_n": executed_n, "holdings_n": holdings_n, "packet_id": packet_id,
            "run_id": run_id, "target_status": target_status, "ts": ts}


def _cycle(job, book, run_id, started_ts, status, extra, severity=None):
    """One complete run: a start and its own finish, no boundary record."""
    return [
        _started(job, book, started_ts, run_id),
        _finished(job, book, started_ts, run_id, status, extra, severity=severity),
    ]


# ---------------------------------------------------------------------------
# the real production cycles, as recorded
# ---------------------------------------------------------------------------

CN_RUN = "2026-10-20_08-00-00_dcda4618"
CN_BRAIN_RUN = "2026-10-20T08-00-19-590Z00-00"
CN_OPP = _opp("china_daily", "china", "2026-10-20T08:00:00+00:00")
CN_EVENTS = [
    _started("china_daily", "china", "2026-10-20T08:00:00+00:00", CN_RUN),
    _finished("china_daily", "china", "2026-10-20T08:00:39+00:00", CN_RUN, "error",
              {"reason": "missing_submission", "target_status": "rejected_no_submission",
               "elapsed_s": 39.653}, severity="FREEZE"),
]
CN_ROWS = [
    _row("china", "2026-10-20", CN_BRAIN_RUN, "2026-10-20T08:00:28.656800+00:00",
         "rejected_no_submission", decision_effective=False, error=CN_ERROR_TEXT,
         executed_n=0, holdings_n=0),
]


def test_cn_missing_submission_is_failed_with_a_misleading_label():
    """The 2026-10-20 CN cycle froze at the boundary and its own row claims "success"."""
    row = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "failed"
    assert row["reason"] == "missing_submission"
    assert row["failure_kind"] == "unclassified"
    assert row["failure_evidence"] == "error result: success"
    assert row["label_misleading"] is True
    assert row["settlement"] is None
    assert row["overdue"] is False
    assert row["decision_row_superseded"] is False
    assert row["scheduler_run_id"] == CN_RUN
    assert row["brain_run_id"] == CN_BRAIN_RUN           # carried from the matched row
    assert row["packet_id"] is None                      # the boundary was never reached
    assert row["asof"] == "2026-10-20"
    assert row["due_at"] == "2026-10-20T08:00:00+00:00"
    assert row["sources"] == ["run_started", "run_finished", "decision_row"]


def test_cn_credential_evidence_relabels_the_same_cycle():
    """An operator note about THIS run's 401 replaces the misleading SDK wording."""
    row = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"),
                           evidence_text="API Error: 401 OAuth access token has been revoked")
    assert row["state"] == "failed"
    assert row["failure_kind"] == "credential"
    assert row["failure_evidence"] == "401"
    assert row["label_misleading"] is False


HK_RUN = "2026-10-15_09-00-00_a385895c"
HK_BRAIN_RUN = "2026-10-15T09-00-08-208Z00-00"
HK_OPP = _opp("hk_daily", "hk", "2026-10-15T09:00:00+00:00")
HK_EVENTS = [
    _started("hk_daily", "hk", "2026-10-15T09:00:00+00:00", HK_RUN),
    _finished("hk_daily", "hk", "2026-10-15T09:00:31+00:00", HK_RUN, "error",
              {"reason": "missing_submission", "target_status": "rejected_no_submission",
               "elapsed_s": 31.235}, severity="FREEZE"),
]
HK_ROWS = [
    _row("hk", "2026-10-15", HK_BRAIN_RUN, "2026-10-15T09:00:17.762658+00:00",
         "rejected_no_submission", decision_effective=False, error=CN_ERROR_TEXT),
]


def test_hk_quota_failure_is_labelled_from_the_operator_note():
    row = ML.project_cycle(HK_OPP, HK_EVENTS, HK_ROWS, now=_now("2026-10-15T12:00:00+00:00"),
                           evidence_text="You've hit your weekly limit · resets Oct 18, 7pm (UTC)")
    assert row["state"] == "failed"
    assert row["failure_kind"] == "quota"
    assert row["failure_evidence"] == "weekly limit"
    assert row["scheduler_run_id"] == HK_RUN
    assert row["brain_run_id"] == HK_BRAIN_RUN
    assert row["asof"] == "2026-10-15"
    assert row["sources"] == ["run_started", "run_finished", "decision_row"]


US_RUN = "2026-10-21_23-10-00_0b07978c"
US_BRAIN_RUN = "2026-10-21T23-10-44-493Z00-00"
US_PACKET = "74797d0d21985a73"
US_OPP = _opp("autonomous_daily", "autonomous", "2026-10-21T23:10:00+00:00")
US_EVENTS = [
    _started("autonomous_daily", "autonomous", "2026-10-21T23:10:00+00:00", US_RUN),
    _packet("autonomous", "2026-10-21T23:16:43+00:00", US_BRAIN_RUN, US_PACKET, "2026-10-21"),
    _finished("autonomous_daily", "autonomous", "2026-10-21T23:17:08+00:00", US_RUN, "ok",
              {"target_status": "queued", "elapsed_s": 427.854}),
]
US_ROWS = [
    _row("autonomous", "2026-10-21", US_BRAIN_RUN, "2026-10-21T23:16:44.958859+00:00", "queued",
         decision_effective=True, executed_n=0, holdings_n=6, packet_id=US_PACKET),
]


def test_us_queued_target_is_accepted_change_still_pending():
    """Queued means a target waits for the next session — never "no change", never settled."""
    row = ML.project_cycle(US_OPP, US_EVENTS, US_ROWS, now=_now("2026-10-21T23:30:00+00:00"))
    assert row["state"] == "accepted_change"
    assert row["settlement"] == "pending"
    assert row["reason"] is None
    assert row["scheduler_run_id"] == US_RUN
    assert row["brain_run_id"] == US_BRAIN_RUN
    assert row["packet_id"] == US_PACKET
    assert row["scheduler_run_id"] != row["brain_run_id"]    # two distinct identity namespaces
    assert row["asof"] == "2026-10-21"
    assert row["decision_row_superseded"] is False
    assert row["sources"] == ["run_started", "run_finished", "packet_accepted", "decision_row"]


def test_us_queued_target_with_no_row_is_still_pending():
    """No decision row means settlement has not spoken: a queued ledger target stays pending."""
    row = ML.project_cycle(US_OPP, US_EVENTS, [], now=_now("2026-10-21T23:30:00+00:00"))
    assert row["state"] == "accepted_change"
    assert row["settlement"] == "pending"
    assert row["decision_row_superseded"] is False
    assert row["sources"] == ["run_started", "run_finished", "packet_accepted"]


def test_us_settled_with_zero_fills_is_accepted_no_change():
    run, brain_run = "2026-10-09_23-10-00_5acbb577", "2026-10-09T23-10-09-296Z00-00"
    events = [
        _started("autonomous_daily", "autonomous", "2026-10-09T23:10:00+00:00", run),
        _packet("autonomous", "2026-10-09T23:13:46+00:00", brain_run, "e1c73675fa814c68",
                "2026-10-09"),
        _finished("autonomous_daily", "autonomous", "2026-10-09T23:14:04+00:00", run, "ok",
                  {"target_status": "queued", "elapsed_s": 244.623}),
    ]
    rows = [
        _row("autonomous", "2026-10-09", brain_run, "2026-10-09T23:13:48.513977+00:00",
             "executed", decision_effective=True, executed_n=0, holdings_n=4,
             packet_id="e1c73675fa814c68"),
    ]
    row = ML.project_cycle(_opp("autonomous_daily", "autonomous", "2026-10-09T23:10:00+00:00"),
                           events, rows, now=_now("2026-10-10T12:00:00+00:00"))
    assert row["state"] == "accepted_no_change"
    assert row["settlement"] == "settled"
    assert row["packet_id"] == "e1c73675fa814c68"
    assert row["overdue"] is False


def test_us_settled_with_fills_is_accepted_change():
    rows = [
        _row("autonomous", "2026-10-21", US_BRAIN_RUN, "2026-10-21T23:40:00+00:00", "executed",
             decision_effective=True, executed_n=3, holdings_n=6, packet_id=US_PACKET),
    ]
    row = ML.project_cycle(US_OPP, US_EVENTS, rows, now=_now("2026-10-22T12:00:00+00:00"))
    assert row["state"] == "accepted_change"
    assert row["settlement"] == "settled"


def test_executed_row_without_a_fill_count_never_claims_no_change():
    rows = [
        _row("autonomous", "2026-10-21", US_BRAIN_RUN, "2026-10-21T23:40:00+00:00", "executed",
             decision_effective=True, executed_n=None, packet_id=US_PACKET),
    ]
    row = ML.project_cycle(US_OPP, US_EVENTS, rows, now=_now("2026-10-22T12:00:00+00:00"))
    assert row["state"] == "accepted_change"
    assert row["settlement"] == "settled"


# ---------------------------------------------------------------------------
# absence of evidence is a result, not a silence
# ---------------------------------------------------------------------------

def test_2026_10_16_vanished_cycle_is_overdue():
    row = ML.project_cycle(_opp("china_daily", "china", "2026-10-16T08:00:00+00:00"),
                           [], [], now=_now("2026-10-16T12:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "no_start_record"
    assert row["overdue"] is True
    assert row["sources"] == []


def test_2026_10_16_inside_the_grace_window_is_only_awaiting_start():
    row = ML.project_cycle(_opp("china_daily", "china", "2026-10-16T08:00:00+00:00"),
                           [], [], now=_now("2026-10-16T08:30:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "awaiting_start"
    assert row["overdue"] is False


def test_disabled_beats_every_other_state():
    opportunity = _opp("china_daily", "china", "2026-10-20T08:00:00+00:00", enabled=False)
    row = ML.project_cycle(opportunity, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "disabled"
    assert row["reason"] is None
    assert row["sources"] == []


def test_not_due_before_the_cron_instant():
    row = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T07:30:00+00:00"))
    assert row["state"] == "not_due"
    assert row["reason"] is None
    assert row["sources"] == []


def test_started_but_not_finished_inside_the_deadline():
    events = [_started("china_daily", "china", "2026-10-20T08:00:00+00:00", CN_RUN)]
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T09:30:00+00:00"))
    assert row["state"] == "started"
    assert row["scheduler_run_id"] == CN_RUN
    assert row["overdue"] is False
    assert row["sources"] == ["run_started"]


def test_started_but_never_finished_is_overdue_uncertain():
    events = [_started("china_daily", "china", "2026-10-20T08:00:00+00:00", CN_RUN)]
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T11:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "no_finish_record"
    assert row["overdue"] is True
    assert row["sources"] == ["run_started"]


def test_lock_held_skip_with_no_start_is_uncertain():
    events = [{"ts": "2026-10-20T08:00:01+00:00", "kind": "run_skipped", "job": "china_daily",
               "book": "china", "step": "acquire", "status": "lock_held",
               "severity": "ADVISORY_ONLY", "actor": "system"}]
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "skipped_lock_held"
    assert row["sources"] == ["run_skipped"]


def test_an_archived_book_skip_is_not_a_lock_held():
    events = [{"ts": "2026-10-20T08:00:01+00:00", "kind": "run_skipped", "job": "etf_daily",
               "book": "etf", "step": "archive_policy", "status": "portfolio_archived",
               "severity": "ADVISORY_ONLY", "actor": "system",
               "extra": {"superseded_by": "autonomous"}}]
    row = ML.project_cycle(_opp("etf_daily", "etf", "2026-10-20T08:00:00+00:00"), events, [],
                           now=_now("2026-10-20T12:00:00+00:00"))
    assert row["reason"] == "no_start_record"
    assert row["sources"] == []


@pytest.mark.parametrize("reason", ["market_closed", "nothing_queued",
                                    "legacy_etf_migration_pending"])
def test_legitimate_ledger_skips_read_as_not_due(reason):
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "skip",
                    {"reason": reason, "target_status": None, "elapsed_s": 4.1},
                    severity="ADVISORY_ONLY")
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "not_due"
    assert row["reason"] == reason
    assert row["settlement"] is None


def test_cost_capped_is_a_rejection_not_a_failure():
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "skip",
                    {"reason": "cost_capped", "target_status": None, "elapsed_s": 9.4},
                    severity="ADVISORY_ONLY")
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "rejected"
    assert row["reason"] == "cost_capped"


def test_gate_rejection_warn_uses_the_target_status_as_reason():
    events = _cycle("autonomous_daily", "autonomous", US_RUN, "2026-10-21T23:10:00+00:00",
                    "warn",
                    {"reason": "rejected_lesson_citations",
                     "target_status": "rejected_lesson_citations", "elapsed_s": 240.0},
                    severity="FREEZE")
    row = ML.project_cycle(US_OPP, events, [], now=_now("2026-10-22T12:00:00+00:00"))
    assert row["state"] == "rejected"
    assert row["reason"] == "rejected_lesson_citations"
    assert row["settlement"] is None
    assert row["failure_kind"] is None


def test_frozen_target_warn_is_rejected():
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "warn",
                    {"reason": "frozen_boundary", "target_status": "frozen_boundary",
                     "elapsed_s": 300.0}, severity="FREEZE")
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "rejected"
    assert row["reason"] == "frozen_boundary"


@pytest.mark.parametrize("reason", ["rejected_execution_error", "runner_failed", "invalid_result",
                                   "inconsistent_result"])
def test_application_failures(reason):
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "error",
                    {"reason": reason, "target_status": None, "elapsed_s": 300.0},
                    severity="FREEZE")
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "failed"
    assert row["reason"] == reason
    assert row["failure_kind"] == "application"
    assert row["failure_evidence"] is None
    assert row["label_misleading"] is False


def test_swallowed_exception_path_carries_no_reason_at_all():
    """``_ledger_end(handle, "error")`` writes no reason and no target_status."""
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "error",
                    {"elapsed_s": 120.0})
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "failed"
    assert row["reason"] is None
    assert row["failure_kind"] == "application"


@pytest.mark.parametrize("reason", ["projection_failed", "settlement_finalization_incomplete"])
def test_unfinished_projections_are_uncertain_not_failed(reason):
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "error",
                    {"reason": reason, "target_status": "rejected_no_submission", "elapsed_s": 5.0},
                    severity="FREEZE")
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == reason


def test_unknown_ledger_vocabulary_degrades_to_uncertain():
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "weird",
                    {"reason": "brand_new_reason", "target_status": "brand_new", "elapsed_s": 5.0})
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "unrecognized_outcome"


def test_ok_ledger_without_a_target_status_is_not_a_success():
    events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "ok",
                    {"target_status": None, "elapsed_s": 5.0})
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "unrecognized_outcome"


# ---------------------------------------------------------------------------
# identity: never borrow another cycle's evidence
# ---------------------------------------------------------------------------

def test_a_row_from_a_later_run_does_not_speak_for_this_cycle():
    """autonomous 2026-10-22: the 02:20 cycle's own row was replaced by the 06:20 run."""
    early_run, early_brain = "2026-10-22_02-20-05_11111111", "2026-10-22T02-20-43-426Z00-00"
    late_brain = "2026-10-22T06-20-17-535Z00-00"
    events = [
        _started("autonomous_daily", "autonomous", "2026-10-22T02:20:05+00:00", early_run),
        _packet("autonomous", "2026-10-22T02:23:26+00:00", early_brain, "aaaaaaaaaaaaaaaa",
                "2026-10-22"),
        _finished("autonomous_daily", "autonomous", "2026-10-22T02:24:00+00:00", early_run, "ok",
                  {"target_status": "queued", "elapsed_s": 235.0}),
    ]
    rows = [
        _row("autonomous", "2026-10-22", late_brain, "2026-10-22T06:23:03.763904+00:00",
             "executed", decision_effective=True, executed_n=2, holdings_n=6,
             packet_id="bbbbbbbbbbbbbbbb"),
    ]
    row = ML.project_cycle(_opp("autonomous_daily", "autonomous", "2026-10-22T02:20:00+00:00"),
                           events, rows, now=_now("2026-10-22T12:00:00+00:00"))
    assert row["decision_row_superseded"] is True
    assert row["state"] == "accepted_change"     # the ledger's own queued claim, nothing more
    assert row["settlement"] == "pending"        # NOT the later row's executed status
    assert row["packet_id"] == "aaaaaaaaaaaaaaaa"    # NOT the later row's packet
    assert row["brain_run_id"] == early_brain
    assert row["sources"] == ["run_started", "run_finished", "packet_accepted"]


def test_the_superseded_flag_needs_a_same_date_row_of_another_run():
    """A row for another date is simply not this cycle's row; nothing was superseded."""
    events = _cycle("autonomous_daily", "autonomous", US_RUN, "2026-10-21T23:10:00+00:00", "ok",
                    {"target_status": "queued", "elapsed_s": 427.854}) + [
        _packet("autonomous", "2026-10-21T23:16:43+00:00", US_BRAIN_RUN, US_PACKET, "2026-10-21")]
    rows = [
        _row("autonomous", "2026-10-20", "other-run", "2026-10-20T23:12:00+00:00", "executed",
             decision_effective=True, executed_n=4),
    ]
    row = ML.project_cycle(US_OPP, events, rows, now=_now("2026-10-22T12:00:00+00:00"))
    assert row["decision_row_superseded"] is False
    assert row["state"] == "accepted_change"
    assert row["settlement"] == "pending"


def test_other_books_and_other_days_are_never_matched():
    row = ML.project_cycle(CN_OPP, HK_EVENTS, HK_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "no_start_record"
    assert row["overdue"] is True
    assert row["scheduler_run_id"] is None
    assert row["brain_run_id"] is None
    assert row["asof"] is None
    assert row["sources"] == []


def test_a_start_outside_the_grace_window_is_not_this_cycle():
    late_start = [_started("china_daily", "china", "2026-10-20T11:00:00+00:00", CN_RUN)]
    row = ML.project_cycle(CN_OPP, late_start, [], now=_now("2026-10-20T12:00:00+00:00"))
    assert row["reason"] == "no_start_record"
    assert row["overdue"] is True
    assert row["scheduler_run_id"] is None
    # ... while a start stamped a little BEFORE the cron instant still belongs to the cycle.
    early_start = [_started("china_daily", "china", "2026-10-20T07:59:30+00:00", CN_RUN)]
    row = ML.project_cycle(CN_OPP, early_start, [], now=_now("2026-10-20T08:30:00+00:00"))
    assert row["scheduler_run_id"] == CN_RUN
    assert row["state"] == "started"


def test_the_opportunity_can_narrow_the_scheduler_defaults():
    late_start = [_started("china_daily", "china", "2026-10-20T08:20:00+00:00", CN_RUN)]
    tight = _opp("china_daily", "china", "2026-10-20T08:00:00+00:00", start_grace_s=600)
    assert ML.project_cycle(tight, late_start, [],
                            now=_now("2026-10-20T12:00:00+00:00"))["reason"] == "no_start_record"
    assert ML.project_cycle(CN_OPP, late_start, [],
                            now=_now("2026-10-20T12:00:00+00:00"))["scheduler_run_id"] == CN_RUN


def test_only_the_earliest_start_and_the_latest_boundary_are_used():
    first, second = "2026-10-20_08-00-00_aaaaaaaa", "2026-10-20_08-00-30_bbbbbbbb"
    events = [
        _started("china_daily", "china", "2026-10-20T08:00:00+00:00", first),
        _started("china_daily", "china", "2026-10-20T08:00:30+00:00", second),
        _packet("china", "2026-10-20T08:01:00+00:00", "brain-one", "packet-one", "2026-10-20"),
        _packet("china", "2026-10-20T08:02:00+00:00", "brain-two", "packet-two", "2026-10-20"),
    ]
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T09:00:00+00:00"))
    assert row["scheduler_run_id"] == first
    assert row["brain_run_id"] == "brain-two"
    assert row["packet_id"] == "packet-two"
    assert row["state"] == "started"                     # no run_finished for the matched start


def test_a_boundary_record_after_the_finish_is_outside_the_cycle():
    events = US_EVENTS + [
        _packet("autonomous", "2026-10-22T01:00:00+00:00", "brain-later", "packet-later",
                "2026-10-21")]
    row = ML.project_cycle(US_OPP, events, US_ROWS, now=_now("2026-10-22T12:00:00+00:00"))
    assert row["brain_run_id"] == US_BRAIN_RUN
    assert row["packet_id"] == US_PACKET


def test_a_finished_record_from_another_run_id_is_not_adopted():
    events = [
        _started("china_daily", "china", "2026-10-20T08:00:00+00:00", CN_RUN),
        _finished("china_daily", "china", "2026-10-20T08:00:39+00:00", "2026-10-20_09-00-00_cccccc",
                  "error", {"reason": "missing_submission", "elapsed_s": 1.0}, severity="FREEZE"),
    ]
    row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T09:00:00+00:00"))
    assert row["state"] == "started"
    assert row["sources"] == ["run_started"]


# ---------------------------------------------------------------------------
# classify_failure_text — display only
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind,evidence", [
    ("API Error: 401 OAuth access token has been revoked", "credential", "401"),
    ("authentication_failed for the pool key", "credential", "authentication_failed"),
    ("Invalid API key supplied", "credential", "invalid api key"),
    ("request Unauthorized", "credential", "unauthorized"),
    ("token was revoked yesterday", "credential", "revoked"),
    ("You've hit your weekly limit · resets Oct 18, 7pm (UTC)", "quota", "weekly limit"),
    ("You've hit your session limit", "quota", "session limit"),
    ("usage limit reached", "quota", "usage limit"),
    ("rate_limit exceeded", "quota", "rate_limit"),
    ("HTTP 429 Too Many Requests", "quota", "429"),
    ("all pool keys cooling", "availability", "all pool keys cooling"),
    ("ALL POOL KEYS DEAD", "availability", "all pool keys dead"),
    ("provider overloaded right now", "availability", "overloaded"),
    ("529 overload", "availability", "529"),
    ("request timeout after 120s", "transport", "timeout"),
    ("connection reset by peer", "transport", "connection reset"),
    ("CliConnectionError: bridge died", "transport", "cliconnectionerror"),
])
def test_classify_failure_text_labels(text, kind, evidence):
    labelled = ML.classify_failure_text(text)
    assert labelled["kind"] == kind
    assert labelled["evidence"] == evidence
    assert labelled["label_misleading"] is False


def test_classify_failure_text_precedence_is_credential_then_quota_then_availability():
    """First match wins across the whole table, not per category."""
    assert ML.classify_failure_text("529 after 401 on the same call")["kind"] == "credential"
    assert ML.classify_failure_text("overloaded: 429 returned")["kind"] == "quota"
    assert ML.classify_failure_text("timeout, then all pool keys cooling")["kind"] == "availability"


def test_classify_failure_text_flags_the_success_worded_error():
    assert ML.classify_failure_text(CN_ERROR_TEXT) == {
        "kind": "unclassified", "evidence": "error result: success", "label_misleading": True}


@pytest.mark.parametrize("text", [None, "", "   ", "a provider said something new entirely", 7])
def test_classify_failure_text_unclassified_never_claims_success(text):
    labelled = ML.classify_failure_text(text)
    assert labelled["kind"] == "unclassified"
    assert labelled["label_misleading"] is False


def test_classify_failure_text_evidence_is_a_needle_not_the_text():
    text = ("Claude Code returned an error result: success while replaying a provider payload "
            + "x" * 300)
    labelled = ML.classify_failure_text(text)
    assert labelled["evidence"] == "error result: success"
    assert len(labelled["evidence"]) <= 80
    assert labelled["evidence"] in text
    assert text not in labelled["evidence"]


@pytest.mark.parametrize("text", ["401", "429", "overloaded", "timeout", CN_ERROR_TEXT])
def test_a_failure_label_never_changes_the_state(text):
    """classify_failure_text labels a failed run; it never creates or upgrades one."""
    baseline = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    labelled = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS,
                                now=_now("2026-10-20T12:00:00+00:00"), evidence_text=text)
    assert labelled["state"] == baseline["state"] == "failed"
    assert labelled["reason"] == baseline["reason"]


def test_a_clean_cycle_carries_no_failure_label():
    row = ML.project_cycle(US_OPP, US_EVENTS, US_ROWS, now=_now("2026-10-22T12:00:00+00:00"),
                           evidence_text="401 revoked")
    assert row["state"] == "accepted_change"
    assert row["failure_kind"] is None
    assert row["failure_evidence"] is None
    assert row["label_misleading"] is False


# ---------------------------------------------------------------------------
# project_cycles
# ---------------------------------------------------------------------------

def test_project_cycles_returns_one_disposition_per_opportunity_in_order():
    opportunities = [
        CN_OPP,
        HK_OPP,
        US_OPP,
        _opp("china_daily", "china", "2026-10-16T08:00:00+00:00"),
        _opp("etf_daily", "etf", "2026-10-21T08:00:00+00:00", enabled=False),
    ]
    events = CN_EVENTS + HK_EVENTS + US_EVENTS
    rows = CN_ROWS + HK_ROWS + US_ROWS
    projected = ML.project_cycles(opportunities, events, rows,
                                  now=_now("2026-10-22T12:00:00+00:00"))
    assert len(projected) == len(opportunities)
    assert [row["job"] for row in projected] == [
        "china_daily", "hk_daily", "autonomous_daily", "china_daily", "etf_daily"]
    assert [row["state"] for row in projected] == [
        "failed", "failed", "accepted_change", "incomplete_uncertain", "disabled"]
    for row in projected:
        assert set(row) == KEYS
        assert row["schema"] == ML.SCHEMA
        assert row["state"] in ML.STATES


def test_project_cycles_attaches_each_cycle_own_evidence_note():
    evidence = {CN_RUN: "API Error: 401 OAuth access token has been revoked",
                HK_BRAIN_RUN: "You've hit your session limit"}
    projected = ML.project_cycles([CN_OPP, HK_OPP], CN_EVENTS + HK_EVENTS, CN_ROWS + HK_ROWS,
                                  now=_now("2026-10-22T12:00:00+00:00"),
                                  evidence_by_run_id=evidence)
    assert [row["failure_kind"] for row in projected] == ["credential", "quota"]
    assert [row["failure_evidence"] for row in projected] == ["401", "session limit"]
    other = ML.project_cycles([HK_OPP, CN_OPP], CN_EVENTS + HK_EVENTS, CN_ROWS + HK_ROWS,
                              now=_now("2026-10-22T12:00:00+00:00"),
                              evidence_by_run_id={US_RUN: "429"})
    assert [row["failure_kind"] for row in other] == ["unclassified", "unclassified"]


def test_project_cycles_survives_junk_records():
    """One row per opportunity even when a schedule entry or a record is malformed."""
    projected = ML.project_cycles(
        [CN_OPP, "not-an-opportunity", None],
        [None, {"kind": "run_started", "job": "china_daily"}, CN_EVENTS[0]],
        [{"ts": "nonsense"}, CN_ROWS[0]],
        now=_now("2026-10-20T08:30:00+00:00"))
    assert len(projected) == 3
    assert [row["state"] for row in projected][1:] == ["incomplete_uncertain",
                                                      "incomplete_uncertain"]
    assert [row["reason"] for row in projected][1:] == ["missing_due_at", "missing_due_at"]
    assert projected[0]["state"] == "started"        # no run_finished for the matched start
    assert projected[0]["sources"] == ["run_started", "decision_row"]
    assert projected[0]["scheduler_run_id"] == CN_RUN


def test_unparseable_due_at_is_uncertain_not_a_crash():
    row = ML.project_cycle(_opp("china_daily", "china", "yesterday-ish"), CN_EVENTS, CN_ROWS,
                           now=_now("2026-10-20T12:00:00+00:00"))
    assert row["state"] == "incomplete_uncertain"
    assert row["reason"] == "missing_due_at"
    assert row["due_at"] is None


def test_naive_and_Z_stamps_are_read_as_utc():
    events = [
        _started("china_daily", "china", "2026-10-20T08:00:00Z", CN_RUN),
        _finished("china_daily", "china", "2026-10-20T08:00:39", CN_RUN, "error",
                  {"reason": "missing_submission", "elapsed_s": 39.653}, severity="FREEZE"),
    ]
    row = ML.project_cycle(_opp("china_daily", "china", "2026-10-20T08:00:00Z"), events, [],
                           now=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc))
    assert row["state"] == "failed"
    assert row["reason"] == "missing_submission"
    assert row["due_at"] == "2026-10-20T08:00:00+00:00"


def test_missing_now_falls_back_to_the_evidence_clock():
    """An unusable clock degrades to the freshest record stamp — never to a wall-clock read."""
    row = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now="not-a-time")
    assert row["state"] == "failed"
    assert row["due_at"] == "2026-10-20T08:00:00+00:00"


# ---------------------------------------------------------------------------
# purity + inertness: this is a projection, not a second state machine
# ---------------------------------------------------------------------------

def test_inputs_are_never_mutated():
    opportunities = [CN_OPP, US_OPP, _opp("china_daily", "china", "2026-10-16T08:00:00+00:00")]
    events = copy.deepcopy(CN_EVENTS + US_EVENTS)
    rows = copy.deepcopy(CN_ROWS + US_ROWS)
    before = copy.deepcopy([opportunities, events, rows])
    ML.project_cycles(opportunities, events, rows, now=_now("2026-10-22T12:00:00+00:00"))
    ML.project_cycle(CN_OPP, events, rows, now=_now("2026-10-22T12:00:00+00:00"),
                     evidence_text="401")
    assert [opportunities, events, rows] == before


def test_projection_is_deterministic_and_hands_back_fresh_containers():
    first = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    second = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    assert first == second
    assert first["sources"] is not second["sources"]
    first["sources"] = ["tampered"]
    third = ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    assert third["sources"] == ["run_started", "run_finished", "decision_row"]


def test_module_keeps_no_state_between_calls():
    ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    quiet = ML.project_cycle(CN_OPP, [], [], now=_now("2026-10-20T12:00:00+00:00"))
    assert quiet["sources"] == []
    assert quiet["scheduler_run_id"] is None
    leftovers = [name for name, value in vars(ML).items()
                 if isinstance(value, (list, dict, set)) and not name.startswith("_")]
    assert leftovers == []


def _imported_modules(source):
    """Every module the projection imports, resolved from its own syntax tree."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative import escapes from the read plane"
            names.add(str(node.module))
    return names


def test_module_source_is_pure_and_inert():
    """No I/O, no scheduling, no settlement, no execution-plane import edge: it only projects."""
    source = inspect.getsource(ML)
    for forbidden in ("open(", ".write(", "json.dump", "append(", "import app.scheduler",
                      "apscheduler", "APScheduler", "paper_account", "subprocess", "threading",
                      "socket", "requests", "os.system", "os.environ", "eval(", "exec("):
        assert forbidden not in source, forbidden
    assert re.search(r"\bsettle\b|settle_|\.settle", source) is None
    assert "brain.decision_submission" in source      # named in prose ...
    assert "decision_submission" not in str(_imported_modules(source))   # ... never imported
    assert _imported_modules(source) == {"__future__", "datetime", "typing"}


def test_every_documented_key_is_always_present():
    cases = [
        ML.project_cycle(CN_OPP, CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00")),
        ML.project_cycle(CN_OPP, [], [], now=_now("2026-10-16T08:30:00+00:00")),
        ML.project_cycle(US_OPP, US_EVENTS, US_ROWS, now=_now("2026-10-22T12:00:00+00:00")),
        ML.project_cycle(_opp("china_daily", "china", "2026-10-20T08:00:00+00:00", enabled=False),
                         [], [], now=_now("2026-10-20T12:00:00+00:00")),
        ML.project_cycle(_opp("etf_daily", "etf", "2026-10-20T08:00:00+00:00"), [], [],
                         now=_now("2026-10-20T07:00:00+00:00")),
    ]
    for row in cases:
        assert set(row) == KEYS
        assert row["schema"] == ML.SCHEMA
        assert row["state"] in ML.STATES
        assert isinstance(row["overdue"], bool)
        assert isinstance(row["decision_row_superseded"], bool)
        assert isinstance(row["label_misleading"], bool)
        assert isinstance(row["sources"], list)
        assert row["settlement"] in (None, "settled", "pending")


def test_all_eight_states_are_reachable_from_real_records():
    seen = set()
    scenarios = [
        (CN_OPP, CN_EVENTS, CN_ROWS, "2026-10-20T12:00:00+00:00"),
        (_opp("china_daily", "china", "2026-10-20T08:00:00+00:00", enabled=False), [], [],
         "2026-10-20T12:00:00+00:00"),
        (CN_OPP, [_started("china_daily", "china", "2026-10-20T08:00:00+00:00", CN_RUN)], [],
         "2026-10-20T08:30:00+00:00"),
        (US_OPP, US_EVENTS, [US_ROWS[0]], "2026-10-22T12:00:00+00:00"),
        (CN_OPP, _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "skip",
                         {"reason": "market_closed", "target_status": None}), [],
         "2026-10-20T12:00:00+00:00"),
        (CN_OPP, _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00", "warn",
                         {"reason": "frozen_gate", "target_status": "frozen_gate"}), [],
         "2026-10-20T12:00:00+00:00"),
        (_opp("china_daily", "china", "2026-10-16T08:00:00+00:00"), [], [],
         "2026-10-16T12:00:00+00:00"),
    ]
    for opportunity, events, rows, moment in scenarios:
        seen.add(ML.project_cycle(opportunity, events, rows, now=_now(moment))["state"])
    settled = ML.project_cycle(US_OPP, US_EVENTS, [
        _row("autonomous", "2026-10-21", US_BRAIN_RUN, "2026-10-21T23:40:00+00:00", "executed",
             decision_effective=True, executed_n=0, packet_id=US_PACKET)],
        now=_now("2026-10-22T12:00:00+00:00"))
    seen.add(settled["state"])
    assert seen == set(ML.STATES)


# ---------------------------------------------------------------------------
# the vocabulary this projection is allowed to know
# ---------------------------------------------------------------------------

def test_accepted_target_status_vocabulary_has_not_drifted():
    """brain.decision_submission owns the accepted set; this module mirrors it without importing."""
    from brain import decision_submission

    assert {"executed", "queued"} == set(decision_submission.ACCEPTED_TARGET_STATUSES)
    assert set(ML.ACCEPTED_TARGETS) == {"executed", "queued"}


def test_states_are_the_documented_closed_set():
    assert ML.STATES == ("not_due", "disabled", "started", "accepted_no_change",
                         "accepted_change", "rejected", "failed", "incomplete_uncertain")
    assert ML.SCHEMA == "mastermind.bot.management_cycle_disposition.v1"


def test_display_labels_are_a_closed_set():
    assert set(ML.DISPLAY_ONLY_FAILURE_KINDS) == {"credential", "quota", "availability",
                                                 "transport", "application", "unclassified"}
    assert ML.classify_failure_text("anything")["kind"] in ML.DISPLAY_ONLY_FAILURE_KINDS


def test_scheduler_ledger_reason_vocabulary_is_covered():
    """Every reason app/scheduler._brain_job_outcome can write has a documented disposition."""
    ledger_reasons = {
        "invalid_result", "projection_failed", "cost_capped", "legacy_etf_migration_pending",
        "market_closed", "nothing_queued", "runner_failed", "settlement_finalization_incomplete",
        "inconsistent_result", "missing_submission", "rejected_execution_error",
    }
    handled = (ML.LEDGER_SKIP_REASONS | ML.LEDGER_FAILURE_REASONS | ML.LEDGER_UNCERTAIN_REASONS
               | {"cost_capped", "missing_submission"})
    assert ledger_reasons == handled
    for reason in sorted(ledger_reasons):
        events = _cycle("china_daily", "china", CN_RUN, "2026-10-20T08:00:00+00:00",
                        "skip" if reason in ML.LEDGER_SKIP_REASONS or reason == "cost_capped"
                        else "error",
                        {"reason": reason, "target_status": None})
        row = ML.project_cycle(CN_OPP, events, [], now=_now("2026-10-20T12:00:00+00:00"))
        assert row["state"] in ML.STATES, reason
        assert row["reason"] == reason or row["reason"] is None, reason


# ---------------------------------------------------------------------------
# PRODUCT contract R1: the per-book run-status fold
# ---------------------------------------------------------------------------

def _book(rows, book, **kw):
    return ML.book_status(rows, book=book, **kw)


def test_cycle_stamps_are_the_matched_ledger_records():
    row = ML.project_cycle(US_OPP, US_EVENTS, US_ROWS, now=_now("2026-10-21T23:30:00+00:00"))
    assert row["started_at"] == "2026-10-21T23:10:00+00:00"
    assert row["finished_at"] == "2026-10-21T23:17:08+00:00"
    vanished = ML.project_cycle(_opp("china_daily", "china", "2026-10-16T08:00:00+00:00"),
                                [], [], now=_now("2026-10-16T12:00:00+00:00"))
    assert vanished["started_at"] is None and vanished["finished_at"] is None
    in_flight = ML.project_cycle(CN_OPP, CN_EVENTS[:1], [], now=_now("2026-10-20T08:30:00+00:00"))
    assert in_flight["started_at"] == "2026-10-20T08:00:00+00:00"
    assert in_flight["finished_at"] is None


def test_book_status_cn_missing_submission_is_failed_with_its_ledger_reason():
    rows = ML.project_cycles([CN_OPP], CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    status = _book(rows, "china")
    assert status["run_status"] == "failed"
    assert status["failure_reason_code"] == "missing_submission"
    assert status["last_attempt_at"] == "2026-10-20T08:00:00+00:00"
    assert status["last_decision_at"] is None          # nothing was ever accepted
    assert status["basis_due_at"] == "2026-10-20T08:00:00+00:00"
    assert status["halted_by"] is None


def test_book_status_us_queued_cycle_is_ok_with_its_decision_stamp():
    rows = ML.project_cycles([US_OPP], US_EVENTS, US_ROWS, now=_now("2026-10-21T23:30:00+00:00"))
    status = _book(rows, "autonomous")
    assert status["run_status"] == "ok"
    assert status["last_decision_at"] == "2026-10-21T23:17:08+00:00"
    assert status["failure_reason_code"] is None


def test_book_status_latest_outcome_wins_and_keeps_the_older_decision_stamp():
    ok_day = _opp("china_daily", "china", "2026-10-19T08:00:00+00:00")
    ok_run = "2026-10-19_08-00-00_aaaaaaaa"
    ok_events = _cycle("china_daily", "china", ok_run, "2026-10-19T08:00:00+00:00", "ok",
                       {"target_status": "queued"})
    rows = ML.project_cycles([ok_day, CN_OPP], ok_events + CN_EVENTS, CN_ROWS,
                             now=_now("2026-10-20T12:00:00+00:00"))
    status = _book(rows, "china")
    assert [row["state"] for row in rows] == ["accepted_change", "failed"]
    assert status["run_status"] == "failed"
    assert status["last_decision_at"] == "2026-10-19T08:00:00+00:00"
    assert status["last_attempt_at"] == "2026-10-20T08:00:00+00:00"
    # Caller order does not matter: the latest DUE cycle decides.
    assert _book(list(reversed(rows)), "china") == status


def test_book_status_vanished_cycle_is_degraded_not_ok():
    rows = ML.project_cycles([_opp("china_daily", "china", "2026-10-16T08:00:00+00:00")], [], [],
                             now=_now("2026-10-16T12:00:00+00:00"))
    status = _book(rows, "china")
    assert status["run_status"] == "degraded"
    assert status["failure_reason_code"] == "no_start_record"
    assert status["last_attempt_at"] is None


def test_book_status_in_flight_skipped_and_future_cycles_never_decide_the_status():
    future = _opp("china_daily", "china", "2026-10-21T08:00:00+00:00")
    skipped = _opp("china_daily", "china", "2026-10-18T08:00:00+00:00")
    skip_run = "2026-10-18_08-00-00_bbbbbbbb"
    skip_events = _cycle("china_daily", "china", skip_run, "2026-10-18T08:00:00+00:00", "skip",
                         {"reason": "market_closed", "target_status": None})
    rows = ML.project_cycles([skipped, CN_OPP, future], skip_events + CN_EVENTS[:1], [],
                             now=_now("2026-10-20T08:30:00+00:00"))
    assert [row["state"] for row in rows] == ["not_due", "started", "not_due"]
    status = _book(rows, "china")
    assert status["run_status"] == "unavailable"       # no cycle has an outcome yet
    assert status["basis_due_at"] is None
    assert status["next_scheduled_at"] == "2026-10-21T08:00:00+00:00"
    assert status["last_attempt_at"] == "2026-10-20T08:00:00+00:00"
    awaiting = ML.project_cycles([CN_OPP], [], [], now=_now("2026-10-20T08:30:00+00:00"))
    assert awaiting[0]["reason"] == "awaiting_start"
    assert _book(awaiting, "china")["run_status"] == "unavailable"


def test_book_status_disabled_book_is_not_scheduled():
    rows = ML.project_cycles(
        [_opp("china_daily", "china", "2026-10-20T08:00:00+00:00", enabled=False)], [], [],
        now=_now("2026-10-20T12:00:00+00:00"))
    assert _book(rows, "china")["run_status"] == "not_scheduled"
    assert _book(rows, "china")["failure_reason_code"] is None


def test_book_status_without_a_projection_is_unavailable_and_all_null():
    rows = ML.project_cycles([CN_OPP], CN_EVENTS, CN_ROWS, now=_now("2026-10-20T12:00:00+00:00"))
    for status in (_book([], "china"), _book(None, "china"), _book(rows, "hk"),
                   _book(rows, ""), _book(["junk", 3, None], "china")):
        assert set(status) == BOOK_KEYS
        assert status["run_status"] == "unavailable"
        assert all(status[key] is None for key in BOOK_KEYS
                   - {"schema", "book", "run_status"})


def test_book_status_halt_evidence_is_the_callers_and_says_halted():
    rows = ML.project_cycles([US_OPP], US_EVENTS, US_ROWS, now=_now("2026-10-21T23:30:00+00:00"))
    status = _book(rows, "autonomous", halted_by="safety.json:kill_switch")
    assert status["run_status"] == "halted"
    assert status["halted_by"] == "safety.json:kill_switch"
    assert status["last_decision_at"] == "2026-10-21T23:17:08+00:00"
    assert _book(rows, "autonomous", halted_by="x" * 500)["halted_by"] == "x" * ML.EVIDENCE_MAX_CHARS
    assert _book(rows, "autonomous", halted_by="  ")["run_status"] == "ok"


def test_book_status_shape_vocabulary_and_inputs_are_stable():
    rows = ML.project_cycles([CN_OPP, US_OPP], CN_EVENTS + US_EVENTS, CN_ROWS + US_ROWS,
                             now=_now("2026-10-22T12:00:00+00:00"))
    snapshot = copy.deepcopy(rows)
    for book in ("china", "autonomous", "hk"):
        status = _book(rows, book)
        assert set(status) == BOOK_KEYS
        assert status["schema"] == ML.BOOK_STATUS_SCHEMA == "mastermind.bot.book_run_status.v1"
        assert status["run_status"] in ML.RUN_STATUSES
    assert rows == snapshot
    assert ML.RUN_STATUSES == ("ok", "degraded", "failed", "halted", "not_scheduled",
                               "unavailable")
