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
