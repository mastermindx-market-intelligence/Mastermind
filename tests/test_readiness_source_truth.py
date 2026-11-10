from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from portfolio import readiness as r
    from portfolio import predictions as p
    monkeypatch.setattr(r, "_ROOT", tmp_path)
    monkeypatch.setattr(r, "_STATE", tmp_path / "data" / "shadow" / "readiness_state.json")
    monkeypatch.setattr(r, "_ALERTS", tmp_path / "data" / "shadow" / "readiness_alerts.jsonl")
    monkeypatch.setattr(p, "_LEDGER", tmp_path / "data" / "shadow" / "predictions" / "ledger.jsonl")
    return r, p


def test_missing_sources_remain_legitimate_not_ready(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    payload = r.status()

    assert payload["flags"]["calibration_forge"] is False
    assert payload["flags"]["calibration_sentinel"] is False
    assert payload["flags"]["prediction_xsec"] is False
    assert payload["flags"]["shadow_forward"] is False
    assert "read_status" not in payload
    assert "failed_sources" not in payload


def test_corrupt_calibration_is_unknown_not_cold_start(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    path = tmp_path / "data" / "brain" / "calibration.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken calibration evidence\n", encoding="utf-8")

    payload = r.status()

    assert payload["flags"]["calibration_forge"] is None
    assert payload["flags"]["calibration_sentinel"] is None
    assert payload["detail"]["calibration_forge"]["n"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["calibration"]


def test_prediction_ledger_failure_is_unknown_not_below_threshold(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)

    calls = []

    def explode(*, strict=False):
        calls.append(strict)
        raise RuntimeError("secret prediction ledger failure")

    monkeypatch.setattr(p, "_load_ledger", explode)
    payload = r.status()

    assert payload["flags"]["prediction_xsec"] is None
    assert payload["detail"]["prediction_xsec"]["independent_clusters"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["prediction_xsec"]

    assert calls == [True]


def test_corrupt_shadow_leaderboard_is_unknown_not_zero_resolved(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    path = tmp_path / "data" / "shadow" / "leaderboard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[\"wrong-shape\"]", encoding="utf-8")

    payload = r.status()

    assert payload["flags"]["shadow_forward"] is None
    assert payload["detail"]["shadow_forward"]["max_resolved"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["shadow_forward"]


def test_all_readiness_sources_failed_is_typed_unavailable(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    cal = tmp_path / "data" / "brain" / "calibration.json"
    cal.parent.mkdir(parents=True, exist_ok=True)
    cal.write_text("{broken\n", encoding="utf-8")
    lb = tmp_path / "data" / "shadow" / "leaderboard.json"
    lb.parent.mkdir(parents=True, exist_ok=True)
    lb.write_text("{broken\n", encoding="utf-8")
    calls = []

    def unavailable(*, strict=False):
        calls.append(strict)
        raise RuntimeError("no ledger")

    monkeypatch.setattr(p, "_load_ledger", unavailable)

    payload = r.status()

    assert payload["read_status"] == "unavailable"
    assert payload["failed_sources"] == ["calibration", "prediction_xsec", "shadow_forward"]
    assert all(value is None for value in payload["flags"].values())

    assert calls == [True]


def test_unknown_source_cannot_mint_readiness_crossing(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(r, "status", lambda: {
        "flags": {"prediction_xsec": None, "shadow_forward": True},
        "detail": {},
        "read_status": "partial",
        "failed_sources": ["prediction_xsec"],
    })

    result = r.check_and_record("2026-09-18")

    assert result["new"] == ["shadow_forward"]
    rows = r.alerts()
    assert [row["flag"] for row in rows] == ["shadow_forward"]


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _source_path(root, family):
    return root / "data" / (
        "brain/calibration.json" if family == "calibration" else "shadow/leaderboard.json"
    )


def _assert_unknown(payload, family):
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == [family]
    if family == "calibration":
        for who in ("forge", "sentinel"):
            assert payload["flags"][f"calibration_{who}"] is None
            assert payload["detail"][f"calibration_{who}"]["n"] is None
    elif family == "prediction_xsec":
        assert payload["flags"][family] is None
        assert payload["detail"][family]["independent_clusters"] is None
    else:
        assert payload["flags"][family] is None
        assert payload["detail"][family]["max_resolved"] is None


def test_fractional_threshold_keeps_the_actual_boundary_and_api_value(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    _write(_source_path(tmp_path, "calibration"), {
        "min_n": 12.5, "agents": {"forge": {"n": 12}, "sentinel": {"n": 13}},
    })

    payload = r.status()
    assert payload["flags"]["calibration_forge"] is False
    assert payload["flags"]["calibration_sentinel"] is True
    assert payload["detail"]["calibration_forge"] == {"n": 12, "need": 12.5}
    assert payload["detail"]["calibration_sentinel"] == {"n": 13, "need": 12.5}
    assert "read_status" not in payload

    from app import web
    response = json.loads(web.api_readiness().body)
    assert response == {"status": payload, "alerts": []}


@pytest.mark.parametrize("threshold", [
    pytest.param(True, id="boolean"),
    pytest.param("12", id="string"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
])
def test_invalid_thresholds_remain_unknown_and_json_safe(tmp_path, monkeypatch, threshold):
    r, _ = _wire(tmp_path, monkeypatch)
    _write(_source_path(tmp_path, "calibration"), {
        "min_n": threshold, "agents": {"forge": {"n": 12}},
    })

    payload = r.status()
    _assert_unknown(payload, "calibration")
    json.dumps(payload, allow_nan=False)

    from app import web
    response = json.loads(web.api_readiness().body)
    assert response["status"] == payload
    assert response["alerts"] == []


@pytest.mark.parametrize(("family", "value"), [
    pytest.param("calibration", {"agents": []}, id="agents-list"),
    pytest.param("calibration", {"agents": {"forge": False}}, id="agent-row-false"),
    pytest.param("shadow_forward", {"books": 0}, id="books-zero"),
])
def test_falsy_present_containers_are_not_healthy_empty_sources(tmp_path, monkeypatch, family, value):
    r, _ = _wire(tmp_path, monkeypatch)
    _write(_source_path(tmp_path, family), value)

    _assert_unknown(r.status(), family)


def test_explicit_none_containers_keep_existing_missing_compatibility(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    _write(_source_path(tmp_path, "calibration"), {"agents": None})
    _write(_source_path(tmp_path, "shadow_forward"), {"books": None})

    payload = r.status()
    assert all(value is False for value in payload["flags"].values())
    assert "failed_sources" not in payload
    assert "read_status" not in payload


@pytest.mark.parametrize("family", ["calibration", "shadow_forward"])
def test_dangling_optional_source_is_unknown_not_missing(tmp_path, monkeypatch, family):
    r, _ = _wire(tmp_path, monkeypatch)
    path = _source_path(tmp_path, family)
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = tmp_path / "missing-source.json"
    path.symlink_to(missing)

    _assert_unknown(r.status(), family)
    assert path.is_symlink()
    assert path.readlink() == missing
    assert not missing.exists()


def test_dangling_optional_source_ancestor_is_unknown(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    data = tmp_path / "data"
    data.mkdir()
    missing = tmp_path / "missing-brain"
    (data / "brain").symlink_to(missing, target_is_directory=True)

    _assert_unknown(r.status(), "calibration")
    assert (data / "brain").is_symlink()
    assert not missing.exists()


def test_failed_optional_source_absence_probe_is_unknown(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    path = _source_path(tmp_path, "calibration")
    real_lstat = Path.lstat

    def fail_target(self, *args, **kwargs):
        if self == path:
            raise PermissionError("private calibration absence probe")
        return real_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fail_target)
    _assert_unknown(r.status(), "calibration")
    assert not path.exists()


def test_optional_source_appearing_after_failed_read_is_not_missing(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    path = _source_path(tmp_path, "calibration")
    real_read = Path.read_text
    reads = []

    def fail_then_publish(self, *args, **kwargs):
        if self == path:
            reads.append("calibration")
            _write(path, {"agents": {"forge": {"n": 30}}})
            raise FileNotFoundError("read did not observe the appeared source")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_then_publish)
    _assert_unknown(r.status(), "calibration")
    assert reads == ["calibration"]
    assert b'"n": 30' in path.read_bytes()


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="requires non-root POSIX permissions")
@pytest.mark.parametrize("family", ["calibration", "shadow_forward"])
def test_inaccessible_optional_source_is_unknown(tmp_path, monkeypatch, family):
    r, _ = _wire(tmp_path, monkeypatch)
    path = _source_path(tmp_path, family)
    path.parent.mkdir(parents=True, exist_ok=True)
    hidden = tmp_path / "private-source"
    hidden.mkdir()
    target = hidden / "source.json"
    prior = '{"agents": {"forge": {"n": 30}}}' if family == "calibration" else '{"books": {"prod": {"n_resolved": 5}}}'
    target.write_text(prior, encoding="utf-8")
    path.symlink_to(target)
    mode = stat.S_IMODE(hidden.stat().st_mode)
    try:
        hidden.chmod(0)
        _assert_unknown(r.status(), family)
        assert path.is_symlink()
        assert path.readlink() == target
    finally:
        hidden.chmod(mode)

    assert target.read_text(encoding="utf-8") == prior


@pytest.mark.parametrize(("raw", "legacy"), [
    pytest.param(b"{broken secret token=not-public\n", [], id="malformed-json"),
    pytest.param(b"\xff\n", [], id="invalid-utf8"),
    pytest.param(b"[]\n", [[]], id="nonmapping-row"),
])
def test_real_prediction_failure_is_unknown_and_nonstrict_reader_stays_compatible(
    tmp_path, monkeypatch, raw, legacy,
):
    r, p = _wire(tmp_path, monkeypatch)
    p._LEDGER.parent.mkdir(parents=True, exist_ok=True)
    p._LEDGER.write_bytes(raw)

    # #812 made the owned reader strict by default (crash-safe writes must fail closed).
    # The legacy compatibility read is still available, but only when asked for explicitly.
    assert p._load_ledger(strict=False) == legacy
    with pytest.raises((ValueError, UnicodeDecodeError)):
        p._load_ledger(strict=True)
    payload = r.status()
    _assert_unknown(payload, "prediction_xsec")
    assert payload["detail"]["prediction_xsec"]["need"] == p._MIN_DATES
    assert p._LEDGER.read_bytes() == raw

    from app import web
    response = json.loads(web.api_readiness().body)
    assert response == {"status": payload, "alerts": []}
    assert "secret" not in json.dumps(response)


def test_real_dangling_prediction_ledger_is_unknown(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    p._LEDGER.parent.mkdir(parents=True, exist_ok=True)
    missing = tmp_path / "missing-predictions.jsonl"
    p._LEDGER.symlink_to(missing)

    assert p._load_ledger(strict=False) == []
    with pytest.raises(FileNotFoundError):
        p._load_ledger(strict=True)
    _assert_unknown(r.status(), "prediction_xsec")
    assert p._LEDGER.is_symlink()
    assert p._LEDGER.readlink() == missing
    assert not missing.exists()


def test_real_dangling_prediction_ancestor_is_unknown(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    missing = tmp_path / "missing-prediction-store"
    linked = tmp_path / "linked-prediction-store"
    linked.symlink_to(missing, target_is_directory=True)
    monkeypatch.setattr(p, "_LEDGER", linked / "ledger.jsonl")

    with pytest.raises(OSError):
        p._load_ledger(strict=True)
    _assert_unknown(r.status(), "prediction_xsec")
    assert linked.is_symlink()
    assert not missing.exists()


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="requires non-root POSIX permissions")
def test_real_inaccessible_prediction_ledger_is_unknown(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    p._LEDGER.parent.mkdir(parents=True, exist_ok=True)
    hidden = tmp_path / "private-predictions"
    hidden.mkdir()
    target = hidden / "ledger.jsonl"
    prior = '{"status": "resolved", "asof": "2026-09-18"}\n'
    target.write_text(prior, encoding="utf-8")
    p._LEDGER.symlink_to(target)
    mode = stat.S_IMODE(hidden.stat().st_mode)
    try:
        hidden.chmod(0)
        assert p._load_ledger(strict=False) == []
        with pytest.raises(PermissionError):
            p._load_ledger(strict=True)
        _assert_unknown(r.status(), "prediction_xsec")
        assert p._LEDGER.is_symlink()
    finally:
        hidden.chmod(mode)

    assert target.read_text(encoding="utf-8") == prior


def test_failed_prediction_absence_probe_is_unknown(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    real_lstat = Path.lstat

    def fail_target(self, *args, **kwargs):
        if self == p._LEDGER:
            raise PermissionError("private prediction absence probe")
        return real_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fail_target)
    with pytest.raises(PermissionError):
        p._load_ledger(strict=True)
    _assert_unknown(r.status(), "prediction_xsec")


@pytest.mark.parametrize("existing", [False, True], ids=["missing", "empty"])
def test_real_missing_and_empty_prediction_ledgers_remain_known(tmp_path, monkeypatch, existing):
    r, p = _wire(tmp_path, monkeypatch)
    if existing:
        p._LEDGER.parent.mkdir(parents=True, exist_ok=True)
        p._LEDGER.write_text("\n \n", encoding="utf-8")

    assert p._load_ledger(strict=True) == []
    assert p._load_ledger() == []
    payload = r.status()
    assert payload["flags"]["prediction_xsec"] is False
    assert payload["detail"]["prediction_xsec"]["independent_clusters"] == 0
    assert "read_status" not in payload
    assert "failed_sources" not in payload


def test_readable_source_links_keep_existing_compatibility(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    targets = tmp_path / "source-targets"
    targets.mkdir()
    for path, name, raw in (
        (_source_path(tmp_path, "calibration"), "calibration.json", '{"agents": {}}'),
        (_source_path(tmp_path, "shadow_forward"), "leaderboard.json", '{"books": {}}'),
        (p._LEDGER, "predictions.jsonl", ""),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        target = targets / name
        target.write_text(raw, encoding="utf-8")
        path.symlink_to(target)

    payload = r.status()
    assert all(value is False for value in payload["flags"].values())
    assert "failed_sources" not in payload
    assert p._load_ledger(strict=True) == []


def test_actual_unknown_family_cannot_mint_alerts_while_healthy_families_cross_once(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    _write(_source_path(tmp_path, "calibration"), {"agents": {"forge": {"n": 20}}})
    _write(_source_path(tmp_path, "shadow_forward"), {"books": {"prod": {"n_resolved": 5}}})
    p._LEDGER.parent.mkdir(parents=True, exist_ok=True)
    p._LEDGER.write_text("{broken prediction evidence\n", encoding="utf-8")

    payload = r.status()
    _assert_unknown(payload, "prediction_xsec")
    assert payload["flags"]["calibration_forge"] is True
    assert payload["flags"]["shadow_forward"] is True
    first = r.check_and_record("2026-09-18")
    assert first["new"] == ["calibration_forge", "shadow_forward"]
    assert first["flags"]["prediction_xsec"] is None
    rows = r.alerts()
    assert [row["flag"] for row in rows] == first["new"]
    second = r.check_and_record("2026-09-19")
    assert second["new"] == []
    assert r.alerts() == rows

    from app import web
    response = json.loads(web.api_readiness().body)
    assert response == {"status": payload, "alerts": rows}


def test_actual_three_source_failures_reach_api_without_erasing_alerts(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    for path in (_source_path(tmp_path, "calibration"), _source_path(tmp_path, "shadow_forward"), p._LEDGER):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken secret source evidence\n", encoding="utf-8")
    prior = [{"date": "2026-09-17", "flag": "calibration_forge", "message": "already recorded"}]
    raw = "".join(json.dumps(row) + "\n" for row in prior)
    r._ALERTS.write_text(raw, encoding="utf-8")

    from app import web
    response = json.loads(web.api_readiness().body)
    payload = response["status"]
    assert payload["read_status"] == "unavailable"
    assert payload["failed_sources"] == ["calibration", "prediction_xsec", "shadow_forward"]
    assert all(value is None for value in payload["flags"].values())
    assert response["alerts"] == prior
    assert "secret" not in json.dumps(response)
    assert r._ALERTS.read_text(encoding="utf-8") == raw
