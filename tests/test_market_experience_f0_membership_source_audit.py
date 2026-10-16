from __future__ import annotations

from datetime import date
import hashlib

import pytest

from research import market_experience_f0_membership_source_audit as audit


def git_blob(body: bytes) -> str:
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def bind_fixture(monkeypatch, interval: bytes, snapshot: bytes) -> None:
    monkeypatch.setattr(audit, "INTERVAL_BYTES", len(interval))
    monkeypatch.setattr(audit, "INTERVAL_GIT_BLOB", git_blob(interval))
    monkeypatch.setattr(audit, "SNAPSHOT_BYTES", len(snapshot))
    monkeypatch.setattr(audit, "SNAPSHOT_GIT_BLOB", git_blob(snapshot))


def valid_fixture() -> tuple[bytes, bytes]:
    interval = (
        "ticker,start_date,end_date\n"
        "AAA,2019-01-01,2020-01-01\n"
        "AAA,2021-01-01,\n"
        "BBB,2019-01-01,\n"
        "BRK.B,2019-06-01,\n"
    ).encode()
    snapshot = (
        "date,tickers\n"
        '2019-01-01,"AAA,BBB"\n'
        '2019-06-01,"AAA,BBB,BRK.B"\n'
        '2020-01-01,"BBB,BRK.B"\n'
        '2021-01-01,"AAA,BBB,BRK.B"\n'
        '2024-01-01,"AAA,BBB,BRK.B"\n'
    ).encode()
    return interval, snapshot


def test_valid_source_shapes_and_reentry(monkeypatch):
    interval, snapshot = valid_fixture()
    bind_fixture(monkeypatch, interval, snapshot)
    intervals, interval_stats = audit.load_intervals(interval)
    snapshots, snapshot_stats = audit.load_snapshots(snapshot)
    assert interval_stats["unique_symbols"] == 3
    assert interval_stats["overlaps"] == 0
    assert snapshot_stats["unique_symbols"] == 3
    assert audit._members_from_intervals(
        intervals, date(2020, 1, 1), inclusive_end=False
    ) == frozenset({"BBB", "BRK-B"})
    assert audit._members_from_intervals(
        intervals, date(2020, 1, 1), inclusive_end=True
    ) == frozenset({"AAA", "BBB", "BRK-B"})
    assert audit._members_from_intervals(
        intervals, date(2021, 1, 1), inclusive_end=False
    ) == frozenset({"AAA", "BBB", "BRK-B"})


def test_compare_date_exposes_removal_day_inclusive_error(monkeypatch):
    interval, snapshot = valid_fixture()
    bind_fixture(monkeypatch, interval, snapshot)
    intervals, _ = audit.load_intervals(interval)
    snapshots, _ = audit.load_snapshots(snapshot)
    result = audit.compare_date(intervals, snapshots, date(2020, 1, 1))
    assert result["exclusive"]["extra"] == 0
    assert result["exclusive"]["missing"] == 0
    assert result["inclusive"]["extra"] == 1
    assert result["inclusive"]["extra_sample"] == ["AAA"]


def test_latest_snapshot_is_not_extrapolated_past_source_max(monkeypatch):
    interval, snapshot = valid_fixture()
    bind_fixture(monkeypatch, interval, snapshot)
    intervals, _ = audit.load_intervals(interval)
    snapshots, _ = audit.load_snapshots(snapshot)
    assert audit.compare_date(intervals, snapshots, date(2024, 1, 2)) == {
        "date": "2024-01-02",
        "covered": False,
    }


def test_overlap_fails_closed(monkeypatch):
    interval = (
        "ticker,start_date,end_date\n"
        "AAA,2019-01-01,2020-06-01\n"
        "AAA,2020-05-01,2021-01-01\n"
    ).encode()
    snapshot = 'date,tickers\n2020-05-15,"AAA"\n'.encode()
    bind_fixture(monkeypatch, interval, snapshot)
    with pytest.raises(audit.MembershipAuditError, match="overlapping intervals"):
        audit.load_intervals(interval)


def test_normalization_collision_fails_closed(monkeypatch):
    interval = (
        "ticker,start_date,end_date\n"
        "BRK.B,2019-01-01,2020-01-01\n"
        "BRK-B,2020-01-01,\n"
    ).encode()
    snapshot = 'date,tickers\n2020-01-01,"BRK-B"\n'.encode()
    bind_fixture(monkeypatch, interval, snapshot)
    with pytest.raises(audit.MembershipAuditError, match="normalization collisions"):
        audit.load_intervals(interval)


@pytest.mark.parametrize(
    "row",
    [
        "AAA,2019-02-30,\n",
        "AAA,2020-01-01,2019-12-31\n",
        "AAA,2020-01-01,2020-01-01\n",
    ],
)
def test_invalid_or_inverted_dates_fail_closed(monkeypatch, row):
    interval = ("ticker,start_date,end_date\n" + row).encode()
    snapshot = 'date,tickers\n2020-01-01,"AAA"\n'.encode()
    bind_fixture(monkeypatch, interval, snapshot)
    with pytest.raises(audit.MembershipAuditError):
        audit.load_intervals(interval)


def test_source_identity_is_fenced(monkeypatch):
    interval, _ = valid_fixture()
    monkeypatch.setattr(audit, "INTERVAL_BYTES", len(interval))
    monkeypatch.setattr(audit, "INTERVAL_GIT_BLOB", "0" * 40)
    with pytest.raises(audit.MembershipAuditError, match="source identity mismatch"):
        audit.load_intervals(interval)


def test_full_audit_keeps_rights_and_authority_false(monkeypatch):
    interval, snapshot = valid_fixture()
    bind_fixture(monkeypatch, interval, snapshot)
    receipt = audit.audit(interval, snapshot)
    assert receipt["rights"]["underlying_index_data_rights"] == "UNKNOWN"
    assert receipt["rights"]["training_eligible"] is False
    assert receipt["rights"]["redistribution_eligible"] is False
    assert receipt["authority"] == {
        "stock_pilot_admitted": False,
        "production_data_admitted": False,
        "forecast_trial": False,
        "promotion_eligible": False,
    }


def test_repository_reader_stays_end_exclusive():
    import ast
    from pathlib import Path
    import pandas as pd

    path = Path(__file__).resolve().parents[1] / "loop" / "single_name_panel.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "members_asof"
    )
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {"pd": pd, "set": set}
    exec(compile(module, str(path), "exec"), namespace)
    members_asof = namespace["members_asof"]

    membership = pd.DataFrame(
        [
            {"ticker": "AAA", "start_date": "2019-01-01", "end_date": "2020-01-01"},
            {"ticker": "AAA", "start_date": "2021-01-01", "end_date": None},
        ]
    )
    membership["start_date"] = pd.to_datetime(membership["start_date"])
    membership["end_date"] = pd.to_datetime(membership["end_date"])
    assert members_asof(membership, pd.Timestamp("2019-12-31")) == {"AAA"}
    assert members_asof(membership, pd.Timestamp("2020-01-01")) == set()
    assert members_asof(membership, pd.Timestamp("2021-01-01")) == {"AAA"}
