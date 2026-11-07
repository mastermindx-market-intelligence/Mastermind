import pytest

from brain import intake


def _rec(score: float, lean: int = 1) -> dict:
    return {
        "score": score,
        "reason": "test evidence",
        "lean": lean,
        "confidence": None,
        "falsifier": None,
    }


def _only_altdata(monkeypatch) -> None:
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("altdata",))
    monkeypatch.setattr(intake, "_LOADERS", {"altdata": "_from_altdata"})


def test_derived_briefing_does_not_count_as_independent_corroboration(monkeypatch):
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({"AAA": _rec(0.70)}, {}, {}))
    monkeypatch.setattr(intake, "_from_altdata", lambda: {"AAA": _rec(0.60)})
    _only_altdata(monkeypatch)

    candidate = intake.build(limit=5)["candidates"][0]

    assert candidate["sources"] == ["altdata", "briefing"]
    assert candidate["n_observed_sources"] == 2
    assert candidate["n_sources"] == 1
    assert candidate["score"] == 0.70
    assert candidate["candidacy_score"] == 0.60


def test_altdata_source_qualification_survives_to_candidate(monkeypatch):
    artifact = {
        "as_of": "2026-09-18",
        "generated_utc": "2026-09-18T18:40:26+00:00",
        "brain_usable": True,
        "is_context_only": True,
        "article3": {"granted": False, "reason": "insufficient-n"},
        "calibration": {"n_scored": 17, "hit_rate": 0.53, "open": 9},
        "signals": [{
            "ticker": "NVDA",
            "signal_score": 80,
            "action": "WATCH",
            "channels": ["patent_cluster", "github_momentum"],
            "falsifier": {"text": "adoption fades"},
        }],
    }
    monkeypatch.setattr(
        intake,
        "_read",
        lambda rel: artifact if rel == "altdata/mastermind.json" else None,
    )
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    _only_altdata(monkeypatch)

    candidate = intake.build(limit=5)["candidates"][0]
    status = candidate["source_qualification"]["altdata"]

    assert status["as_of"] == "2026-09-18"
    assert status["generated_utc"] == "2026-09-18T18:40:26+00:00"
    assert status["brain_usable"] is True
    assert status["is_context_only"] is True
    assert status["article3_granted"] is False
    assert status["article3_reason"] == "insufficient-n"
    assert status["calibration_n_scored"] == 17
    assert status["calibration_hit_rate"] == 0.53


def test_missing_altdata_qualification_stays_unknown(monkeypatch):
    artifact = {
        "signals": [{
            "ticker": "MU",
            "signal_score": 70,
            "action": "WATCH",
            "channels": ["patent_cluster"],
        }],
    }
    monkeypatch.setattr(
        intake,
        "_read",
        lambda rel: artifact if rel == "altdata/mastermind.json" else None,
    )

    status = intake._from_altdata()["MU"]["qualification"]

    assert status["as_of"] is None
    assert status["brain_usable"] is None
    assert status["is_context_only"] is None
    assert status["article3_granted"] is None
    assert status["calibration_n_scored"] is None


def _alt_artifact(*, granted: bool, brain_usable: bool = True) -> dict:
    return {
        "as_of": "2026-09-18",
        "generated_utc": "2026-09-18T18:40:26+00:00",
        "brain_usable": brain_usable,
        "is_context_only": not granted,
        "article3": {"granted": granted, "reason": None if granted else "insufficient-n"},
        "calibration": {"n_scored": 17 if granted else 0, "hit_rate": 0.53 if granted else None},
        "signals": [{
            "ticker": "NVDA",
            "signal_score": 80,
            "action": "ACCUMULATE",
            "channels": ["patent_cluster", "github_momentum"],
        }],
    }


def test_context_only_altdata_cannot_originate_portfolio_candidacy(monkeypatch):
    artifact = _alt_artifact(granted=False)
    monkeypatch.setattr(
        intake, "_read",
        lambda rel: artifact if rel == "altdata/mastermind.json" else None,
    )
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    _only_altdata(monkeypatch)

    candidate = intake.build(limit=5)["candidates"][0]

    assert candidate["ticker"] == "NVDA"
    assert candidate["sources"] == ["altdata"]
    assert candidate["n_observed_sources"] == 1
    assert candidate["n_sources"] == 0
    assert candidate["score"] == 0.6
    assert candidate["candidacy_score"] == 0.0
    assert intake.tickers(limit=5) == []
    assert "NVDA" not in intake.tickers(limit=5, min_score=0.4)


def test_context_only_altdata_cannot_boost_an_eligible_source(monkeypatch):
    artifact = _alt_artifact(granted=False)
    monkeypatch.setattr(
        intake, "_read",
        lambda rel: artifact if rel == "altdata/mastermind.json" else None,
    )
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    monkeypatch.setattr(intake, "_from_radar", lambda: {"NVDA": _rec(0.45)})
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar", "altdata"))
    monkeypatch.setattr(intake, "_LOADERS", {"radar": "_from_radar", "altdata": "_from_altdata"})

    candidate = intake.build(limit=5)["candidates"][0]

    assert candidate["sources"] == ["altdata", "radar"]
    assert candidate["n_observed_sources"] == 2
    assert candidate["n_sources"] == 1
    assert candidate["score"] == 0.68  # research salience may reward distinct observed evidence
    assert candidate["candidacy_score"] == 0.45
    assert candidate["lean"] == 1


def test_article3_granted_altdata_can_enter_candidacy(monkeypatch):
    artifact = _alt_artifact(granted=True)
    monkeypatch.setattr(
        intake, "_read",
        lambda rel: artifact if rel == "altdata/mastermind.json" else None,
    )
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    _only_altdata(monkeypatch)

    candidate = intake.build(limit=5)["candidates"][0]

    assert candidate["n_sources"] == 1
    assert candidate["score"] == 0.6
    assert candidate["candidacy_score"] == 0.6
    assert candidate["lean"] == 1
    assert "NVDA" in intake.tickers(limit=5, min_score=0.4)


def test_article3_grant_with_unusable_brain_still_refuses_candidacy(monkeypatch):
    artifact = _alt_artifact(granted=True, brain_usable=False)
    monkeypatch.setattr(
        intake, "_read",
        lambda rel: artifact if rel == "altdata/mastermind.json" else None,
    )
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    _only_altdata(monkeypatch)

    candidate = intake.build(limit=5)["candidates"][0]

    assert candidate["n_sources"] == 0
    assert candidate["score"] == 0.6
    assert candidate["candidacy_score"] == 0.0
    assert intake.tickers(limit=5) == []
    assert "NVDA" not in intake.tickers(limit=5, min_score=0.4)


def test_context_salience_cannot_crowd_eligible_candidate_out_of_tickers(monkeypatch):
    refused = _alt_artifact(granted=False)
    refused["signals"][0]["ticker"] = "CONTEXT"
    monkeypatch.setattr(
        intake, "_read",
        lambda rel: refused if rel == "altdata/mastermind.json" else None,
    )
    monkeypatch.setattr(
        intake, "_from_briefing",
        lambda: ({"CONTEXT": _rec(0.99), "ELIGIBLE": {**_rec(0.10), "ranking_eligible": False}}, {}, {}),
    )
    monkeypatch.setattr(intake, "_from_radar", lambda: {"ELIGIBLE": _rec(0.45)})
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar", "altdata"))
    monkeypatch.setattr(intake, "_LOADERS", {"radar": "_from_radar", "altdata": "_from_altdata"})

    research = intake.queue(limit=1)
    candidacy = intake.tickers(limit=1, min_score=0.4)

    assert research[0]["ticker"] == "CONTEXT"
    assert research[0]["score"] == 0.99
    assert research[0]["candidacy_score"] == 0.0
    assert candidacy == ["ELIGIBLE"]


def test_derived_briefing_base_does_not_stack_primitive_corroboration_twice(monkeypatch):
    """A fused briefing may set research salience, but primitive evidence cannot be added on top twice."""
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({"AAA": _rec(0.70)}, {}, {}))
    monkeypatch.setattr(intake, "_from_altdata", lambda: {"AAA": _rec(0.60)})
    monkeypatch.setattr(intake, "_from_radar", lambda: {"AAA": _rec(0.50)})
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar", "altdata"))
    monkeypatch.setattr(
        intake, "_LOADERS", {"radar": "_from_radar", "altdata": "_from_altdata"}
    )

    candidate = intake.build(limit=5)["candidates"][0]

    assert candidate["sources"] == ["altdata", "briefing", "radar"]
    assert candidate["n_observed_sources"] == 3
    assert candidate["n_sources"] == 2
    assert candidate["score"] == 0.70
    assert candidate["candidacy_score"] == 0.68


def test_divergence_bonus_is_applied_exactly_once(monkeypatch):
    """The derived divergence flag has one explicit salience lift, not a base score plus the same lift."""
    monkeypatch.setattr(
        intake,
        "_from_briefing",
        lambda: ({}, {"AAA": _rec(intake._DIVERGENCE_BONUS)}, {}),
    )
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ())
    monkeypatch.setattr(intake, "_LOADERS", {})

    candidate = intake.build(limit=5)["candidates"][0]

    assert candidate["sources"] == ["divergence"]
    assert candidate["n_observed_sources"] == 1
    assert candidate["n_sources"] == 0
    assert candidate["score"] == intake._DIVERGENCE_BONUS
    assert candidate["candidacy_score"] == 0.0



@pytest.mark.parametrize("context_source", ["altdata", "briefing", "divergence"])
def test_context_only_evidence_cannot_break_candidacy_tie(monkeypatch, context_source):
    """Research attention cannot decide which equally eligible name crosses a cutoff."""
    artifacts = {}
    monkeypatch.setattr(intake, "_read", lambda rel: artifacts.get(rel))
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar", "altdata"))
    monkeypatch.setattr(intake, "_LOADERS", {"radar": "_from_radar", "altdata": "_from_altdata"})
    monkeypatch.setattr(intake, "_from_radar", lambda: {"AAA": _rec(0.45), "ZZZ": _rec(0.45)})
    before = {c["ticker"]: c for c in intake.build(limit=None)["candidates"]}
    selected_before = intake.tickers(limit=1, min_score=0.4)
    assert selected_before == ["AAA"]
    if context_source == "altdata":
        artifact = _alt_artifact(granted=False)
        artifact["signals"][0]["ticker"] = "ZZZ"
        artifact["signals"][0]["signal_score"] = 99
        artifacts["altdata/mastermind.json"] = artifact
    elif context_source == "briefing":
        artifacts["intelligence/briefing.json"] = {
            "priority_queue": [{"ticker": "ZZZ", "priority": 0.99, "lean": 1}]
        }
    else:
        artifacts["intelligence/briefing.json"] = {
            "divergences": [{"ticker": "ZZZ", "lean": 1}]
        }
    after = {c["ticker"]: c for c in intake.build(limit=None)["candidates"]}
    assert after["ZZZ"]["score"] > before["ZZZ"]["score"]
    assert after["ZZZ"]["candidacy_score"] == before["ZZZ"]["candidacy_score"]
    assert after["ZZZ"]["n_sources"] == before["ZZZ"]["n_sources"]
    assert intake.tickers(limit=1, min_score=0.4) == selected_before
    assert intake.tickers(limit=2, min_score=0.4) == ["AAA", "ZZZ"]


def test_equal_candidacy_is_stable_under_source_row_order(monkeypatch):
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar",))
    monkeypatch.setattr(intake, "_LOADERS", {"radar": "_from_radar"})
    monkeypatch.setattr(intake, "_from_radar", lambda: {"ZZZ": _rec(0.45), "AAA": _rec(0.45)})
    assert intake.tickers(limit=1, min_score=0.4) == ["AAA"]


def test_higher_candidacy_still_outranks_lexical_tiebreak(monkeypatch):
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({"AAA": _rec(0.99)}, {}, {}))
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar",))
    monkeypatch.setattr(intake, "_LOADERS", {"radar": "_from_radar"})
    monkeypatch.setattr(intake, "_from_radar", lambda: {"AAA": _rec(0.45), "ZZZ": _rec(0.50)})
    assert intake.queue(limit=1)[0]["ticker"] == "AAA"
    assert intake.tickers(limit=1, min_score=0.4) == ["ZZZ"]


@pytest.mark.parametrize("limit", [-1, 0, 1, 5, 99])
@pytest.mark.parametrize("min_score", [0.0, 0.3, 0.31])
def test_no_evidence_seed_order_and_filter_compatibility(monkeypatch, limit, min_score):
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ())
    monkeypatch.setattr(intake, "_LOADERS", {})
    expected = intake._SEED[:max(0, limit)] if min_score <= 0.3 else []
    assert intake.tickers(limit=limit, min_score=min_score) == expected


def test_real_evidence_for_seed_symbols_uses_identity_ties(monkeypatch):
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar",))
    monkeypatch.setattr(intake, "_LOADERS", {"radar": "_from_radar"})
    monkeypatch.setattr(intake, "_from_radar", lambda: {"NVDA": _rec(0.45), "AMD": _rec(0.45)})
    assert intake.tickers(limit=2, min_score=0.4) == ["AMD", "NVDA"]



def _transitive_inputs(monkeypatch, *, parent, source="signal"):
    files = {"basketdata/radar_ticker.json": {
        "schema": "radar_ticker.v1", "is_context_only": True, "as_of": "2026-09-19",
        "tickers": [{"ticker": "PROBE", "source": source,
                     "state": "POSITIVE_DIVERGENCE", "edge_score": 52}],
    }}
    if parent is not None:
        files["altdata/mastermind.json"] = parent
    monkeypatch.setattr(intake, "_read", lambda rel: files.get(rel))
    monkeypatch.setattr(intake, "_from_briefing", lambda: ({}, {}, {}))
    monkeypatch.setattr(intake, "_SIMPLE_SOURCES", ("radar", "altdata"))
    monkeypatch.setattr(intake, "_LOADERS", {"radar": "_from_radar", "altdata": "_from_altdata"})


def _transitive_parent(granted):
    return {"brain_usable": True, "is_context_only": not granted,
            "article3": {"granted": granted},
            "signals": [{"ticker": "PROBE", "signal_score": 90,
                         "action": "ACCUMULATE", "channels": ["patent_cluster"]}]}


def test_refused_altdata_cannot_reenter_through_signal_radar(monkeypatch):
    _transitive_inputs(monkeypatch, parent=_transitive_parent(False))
    row = intake.queue(limit=1)[0]
    assert row["sources"] == ["altdata", "radar"]
    assert row["candidacy_score"] == 0.0
    assert row["n_sources"] == 0
    assert row["score"] == 0.8
    assert intake.tickers(limit=5, min_score=0.4) == []


def test_granted_altdata_and_its_radar_derivative_count_once(monkeypatch):
    _transitive_inputs(monkeypatch, parent=_transitive_parent(True))
    row = intake.queue(limit=1)[0]
    assert row["n_observed_sources"] == 2
    assert row["n_sources"] == 1
    assert row["candidacy_score"] == 0.8
    assert row["score"] == 0.8
    assert intake.tickers(limit=5, min_score=0.4) == ["PROBE"]


def test_signal_radar_without_parent_stays_research_visible(monkeypatch):
    _transitive_inputs(monkeypatch, parent=None)
    row = intake.queue(limit=1)[0]
    assert row["ticker"] == "PROBE" and row["score"] == 0.52
    assert row["candidacy_score"] == 0.0
    assert intake.tickers(limit=5) == []
    q = row["source_qualification"]["radar"]
    assert q["source_kind"] == "signal"
    assert q["derived_from"] == ["altdata"]
    assert q["independent_evidence"] is False


def test_signal_radar_cannot_borrow_unrelated_parent_grant(monkeypatch):
    parent = _transitive_parent(True)
    parent["signals"] = []
    _transitive_inputs(monkeypatch, parent=parent)
    assert intake.queue(limit=1)[0]["score"] == 0.52
    assert intake.tickers(limit=5) == []


def test_basket_attributed_radar_behavior_is_not_changed(monkeypatch):
    _transitive_inputs(monkeypatch, parent=None, source="basket_attributed")
    row = intake.queue(limit=1)[0]
    assert row["score"] == row["candidacy_score"] == 0.52
    assert row["n_sources"] == 1
    assert intake.tickers(limit=5, min_score=0.4) == ["PROBE"]


def test_transitive_refusal_reaches_actual_conviction_consumer(monkeypatch):
    from brain import ledger
    from portfolio import conviction, prophet_feed

    _transitive_inputs(monkeypatch, parent=_transitive_parent(False))
    monkeypatch.setattr(conviction, "regime_seed", lambda: [])
    monkeypatch.setattr(conviction, "universe", lambda: [])
    monkeypatch.setattr(conviction, "nw_universe_scan", lambda: [])
    monkeypatch.setattr(ledger, "all_theses", lambda: [])
    monkeypatch.setattr(prophet_feed, "candidate_tickers", lambda: [])
    assert intake.queue(limit=1)[0]["ticker"] == "PROBE"
    assert conviction.candidates() == []
