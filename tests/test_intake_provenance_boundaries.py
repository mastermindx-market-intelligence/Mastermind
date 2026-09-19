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
