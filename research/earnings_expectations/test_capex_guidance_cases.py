"""Alphabet forward capital spending is issuer guidance, not an analyst estimate."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from replay_casebook import CAPEX, PACKETS, build_report, markdown


def _source():
    return json.loads(CAPEX.read_text())


def _modify(tmp_path, change):
    doc = deepcopy(_source())
    change(doc)
    path = tmp_path / "modified.json"
    path.write_text(json.dumps(doc))
    return path


def test_capex_three_chronological_guidance_observations_share_one_budget_target():
    report = build_report()
    rows = report["capex_guidance_sequence"]
    assert len(rows) == 3
    assert report["capex_guidance_status"] == "COMPANY_GUIDANCE_ONLY_NOT_ANALYST_CONSENSUS"
    assert [r["midpoint_billion"] for r in rows] == [180.0, 185.0, 200.0]
    assert [(r["range_low_billion"], r["range_high_billion"]) for r in rows] == [
        (175.0,185.0),(180.0,190.0),(195.0,205.0),
    ]
    assert [r["midpoint_change_billion"] for r in rows] == [None,5.0,15.0]
    assert all(r["fiscal_target"] == "FY2026" for r in rows)
    assert all("NOT_SELL_SIDE_CONSENSUS" in r["source_type"] for r in rows)


def test_unchanged_good_operating_growth_does_not_force_repricing_direction():
    r = build_report()["capex_guidance_sequence"]
    moves = [x["observed_stock_reaction_pct"] for x in r]
    assert moves[0] < 0
    assert moves[1] > 9
    assert moves[2] < -7
    assert r[1]["midpoint_change_pct"] == 2.7778
    assert r[2]["midpoint_change_pct"] == 8.1081
    assert "Intersect" in r[1]["company_reason"]
    assert "capacity" in r[2]["company_reason"].lower()


def test_capex_report_renders_source_links_and_not_a_buy_signal():
    s = markdown(build_report())
    assert "Alphabet FY2026 capital expenditure guidance changes" in s
    assert "$175–$185B" in s
    assert "$195–$205B" in s
    assert "+15.0B" in s
    assert "Company CapEx guidance may be disclosed during the post-close earnings call" in s


def test_missing_capex_file_uses_explicit_unavailable_status(tmp_path):
    report = build_report(capex_path=tmp_path/"missing.json")
    assert report["capex_guidance_status"] == "COMPANY_CAPEX_GUIDANCE_UNAVAILABLE"
    assert report["capex_guidance_sequence"] == []
    assert report["sample_size"] == 9


@pytest.mark.parametrize("mod,expected",[
    (lambda x:x.update(source_type="ANALYST_CONSENSUS"),"CAPEX_GUIDANCE_SOURCE_BASIS_INVALID"),
    (lambda x:x.update(fiscal_target="FY2027"),"CAPEX_GUIDANCE_SOURCE_BASIS_INVALID"),
    (lambda x:x["updates"][1].update(observed_fiscal_target="2026Q1"),"CAPEX_GUIDANCE_FISCAL_TARGET_MISMATCH"),
    (lambda x:x["updates"][2].update(source_type="INFERRED_MARKET_BELIEF"),"CAPEX_GUIDANCE_SOURCE_TYPE_INVALID"),
    (lambda x:x["updates"][0].update(source_ref="http://private"),"CAPEX_GUIDANCE_SOURCE_LINK_REQUIRED"),
    (lambda x:x["updates"][1].update(statement_date="2026-01-01"),"CAPEX_GUIDANCE_RELEASE_ORDER_INVALID"),
    (lambda x:x["updates"][1].update(low=200,high=190),"CAPEX_GUIDANCE_RANGE_INVALID"),
    (lambda x:x["updates"][2].update(same_day_publication_clock_status="PRE_EVENT_AVAILABLE"),"CAPEX_GUIDANCE_UNSUPPORTED_CLOCK_STATUS"),
    (lambda x:x["updates"][0].update(event_ref="earnings:CIK:1018724:2025Q4"),"CAPEX_GUIDANCE_EVENT_IDENTITY_MISMATCH"),
    (lambda x:x["updates"][1].update(statement_date="2026-04-30"),"CAPEX_GUIDANCE_EVENT_IDENTITY_MISMATCH"),
    (lambda x:x["updates"].append(dict(x["updates"][1])),"DUPLICATE_CAPEX_GUIDANCE_EVENT"),
])
def test_capex_adversarial_sources_cannot_override_semantics(tmp_path,mod,expected):
    with pytest.raises(ValueError,match=expected):
        build_report(capex_path=_modify(tmp_path,mod))


def test_calendar_date_not_belief_availability():
    row = build_report()["capex_guidance_sequence"][2]
    assert row["clock_quality"] == "CALL_DISCLOSURE_NOT_PRE_RELEASE"
    assert "source_ref" in row
