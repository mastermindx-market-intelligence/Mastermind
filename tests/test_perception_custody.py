"""Point-in-time custody for the existing risk publication and decision journal."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timezone

import pytest

from brain import journal


def test_date_file_does_not_attest_what_an_intraday_decision_saw(tmp_path, monkeypatch):
    root = tmp_path / "data" / "market_view"
    root.mkdir(parents=True)
    (root / "2026-10-19.json").write_text(json.dumps({
        "asof": "2026-10-19", "built_at": "2026-10-20T01:00:00+00:00", "seq": 99,
        "planes": {"risk_radar": {"direction": "risk_on"}},
    }))
    monkeypatch.setattr(journal, "_ROOT", tmp_path)
    assert journal._planes_at_entry("2026-10-19") is None


def test_historical_resolution_does_not_acquire_later_latest_context(tmp_path, monkeypatch):
    root = tmp_path / "data" / "market_view"
    root.mkdir(parents=True)
    (root / "latest.json").write_text(json.dumps({
        "asof": "2026-10-20",
        "brief": {"posture_implication": "later context cannot describe the earlier resolution"},
    }))
    monkeypatch.setattr(journal, "_ROOT", tmp_path)
    assert journal._regime_context(date(2026, 10, 19)) == ""


def _receipt():
    from brain import perception_receipt as R
    clock = datetime.now(timezone.utc).isoformat()
    projection = {
        "publication": {"asof": "2026-10-19", "built_at": "2026-10-20T00:00:00Z",
                        "seq": 9, "artifact_sha256": "a" * 64},
        "serving_freshness": {"checked_at": clock, "current_confirmation_available": False},
        "plane_summaries": [
            {"name": "risk_radar", "direction": "risk_off", "status": "validated",
             "freshness": {"asof": "2026-10-19", "stale": False}},
            {"name": "expired", "direction": "risk_on", "status": "advisory",
             "freshness": {"asof": "2026-08-07", "stale": True}},
        ],
    }
    rendered = "Current confirmation unavailable; Radar risk_off."
    return R.seal(R.capture_projection(projection, rendered),
                  "Synthetic final prompt\n" + rendered)


def test_receipt_retains_actual_projection_when_source_object_changes():
    from brain import perception_receipt as R
    receipt = _receipt()
    original = copy.deepcopy(receipt)
    changed = copy.deepcopy(receipt["projection"])
    changed["plane_summaries"][0]["direction"] = "risk_on"
    assert receipt == original
    assert R.valid(receipt)
    timestamp = datetime.now(timezone.utc).isoformat()
    assert R.entry_planes(receipt, decision_timestamp=timestamp) == {"risk_radar": "risk_off"}
    assert receipt["projection"]["serving_freshness"]["current_confirmation_available"] is False


def test_receipt_tampering_or_unbound_date_cannot_supply_entry_evidence():
    from brain import perception_receipt as R
    receipt = _receipt()
    assert R.entry_planes(receipt, decision_timestamp=None) is None
    receipt["projection"]["plane_summaries"][0]["direction"] = "risk_on"
    assert not R.valid(receipt)
    assert R.entry_planes(receipt, decision_timestamp=datetime.now(timezone.utc).isoformat()) is None


def test_receipt_captured_after_decision_is_not_historical_evidence():
    from brain import perception_receipt as R
    receipt = _receipt()
    assert not R.valid(receipt, decision_timestamp="2000-01-01T00:00:00+00:00")
    assert R.entry_planes(receipt, decision_timestamp="2000-01-01T00:00:00+00:00") is None


def test_actual_autonomous_runner_seals_input_before_dispatch_and_rejects_model_receipt(monkeypatch):
    from bot import autonomous as A
    from brain import autonomous_mcp, cli_bridge, perception_receipt as R
    from brain import pm_conviction, portfolio_learning, self_mirror, student, risk_lens, posture_decider
    from portfolio import advisor_trade, paper_account
    projection = _receipt()["projection"]
    before = copy.deepcopy(projection)
    monkeypatch.setattr(A, "_read_regime", lambda: {"quad": "Q1", "quad_name": "Goldilocks"})
    monkeypatch.setattr(A, "_regime_dict", lambda: {})
    monkeypatch.setattr(pm_conviction, "_full_regime_slice", lambda raw: {
        "market_view": {
            **copy.deepcopy(projection),
            "label_vs_planes_line": "Current confirmation unavailable.",
            "market_view_brief": {"posture_implication": "Original defensive observation."},
        },
    })
    monkeypatch.setattr(paper_account, "_load_account", lambda *a: {"cash": 100, "positions": {}})
    monkeypatch.setattr(advisor_trade, "prompt_context", lambda **k: "")
    monkeypatch.setattr(portfolio_learning, "prompt_block", lambda *a, **k: "")
    monkeypatch.setattr(risk_lens, "briefing", lambda *a, **k: "")
    monkeypatch.setattr(risk_lens, "govern_persona", lambda text, *a: text)
    monkeypatch.setattr(posture_decider, "render_directive", lambda: "")
    monkeypatch.setattr(student, "inject", lambda text, *a: text)
    monkeypatch.setattr(self_mirror, "inject", lambda text, *a: text)
    monkeypatch.setattr(autonomous_mcp, "build_servers", lambda: {})
    monkeypatch.setattr(autonomous_mcp, "allowed_tools", lambda: [])
    observed = {}
    async def fake_reason(prompt, **kwargs):
        observed["prompt"] = prompt
        # Simulate the publisher advancing during model execution.
        projection["publication"]["seq"] = 10
        projection["plane_summaries"][0]["direction"] = "risk_on"
        return {"ok": True, "run_id": "synthetic-run", "perception_input": {"model_forgery": True}}
    monkeypatch.setattr(cli_bridge, "reason", fake_reason)
    result = A._run_brain("2026-10-19", False)
    receipt = result["perception_input"]
    assert R.valid(receipt)
    assert receipt["projection"]["publication"] == before["publication"]
    assert receipt["projection"]["plane_summaries"] == before["plane_summaries"]
    assert receipt["rendered_context"] in observed["prompt"]
    assert receipt["prompt_sha256"] == hashlib.sha256(observed["prompt"].encode()).hexdigest()
    assert "model_forgery" not in receipt
    assert "Original defensive observation." in receipt["rendered_context"]


def test_existing_decision_log_uses_runner_receipt_without_rereading_latest(tmp_path, monkeypatch):
    from bot import autonomous as A
    from brain import pm_conviction, portfolio_learning
    from portfolio import registry
    receipt = _receipt()
    monkeypatch.setattr(registry, "data_dir", lambda *a: tmp_path / "book")
    monkeypatch.setattr(portfolio_learning, "trace_links", lambda *a, **k: {})
    def forbidden(*args, **kwargs):
        raise AssertionError("decision log reread current publication")
    monkeypatch.setattr(pm_conviction, "_read_market_view", forbidden)
    # Existing locked callback path; no portfolio run, account or settlement is invoked.
    A._append_decision_log("2026-10-19", {"perception_input": {"model_forgery": True}}, [], [],
                           {"run_id": "synthetic-run", "perception_input": receipt},
                           _locked=True)
    row = json.loads((tmp_path / "book" / "decisions.jsonl").read_text().splitlines()[0])
    assert row["perception_input"] == receipt
    assert row["run_id"] == "synthetic-run"
    assert "model_forgery" not in row["perception_input"]


def test_self_mirror_preserves_trusted_input_for_the_existing_journal(monkeypatch):
    from brain import self_mirror as S
    receipt = _receipt()
    timestamp = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(S._calib, "_book_decisions", lambda book: [{
        "asof": "2026-10-19", "ts": timestamp, "decision_id": "existing-decision",
        "holdings": [{"ticker": "SYNTH", "conviction": 0.6}], "perception_input": receipt,
    }])
    monkeypatch.setattr(S._calib, "_elapsed", lambda *a: True)
    monkeypatch.setattr(S._calib, "_label_name", lambda *a, **k: {
        "resolved": True, "rel_return": -0.01,
    })
    rows = S._book_rows("autonomous", "SPY", date(2026, 10, 21))
    assert rows[0]["perception_input"] == receipt
    assert rows[0]["decision_timestamp"] == timestamp
    assert rows[0]["decision_id"] == "existing-decision"


def test_journal_retains_original_receipt_after_later_date_file_replacement(tmp_path, monkeypatch):
    receipt = _receipt()
    timestamp = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(journal, "_JOURNAL", tmp_path / "journal")
    monkeypatch.setattr(journal, "_ROOT", tmp_path)
    latest = tmp_path / "data" / "market_view"
    latest.mkdir(parents=True)
    (latest / "2026-10-19.json").write_text(json.dumps({
        "asof": "2026-10-19", "planes": {"risk_radar": {"direction": "risk_on"}},
    }))
    rows = [{
        "date": "2026-10-19", "ticker": "SYNTH", "outcome": 0, "rel": -0.1,
        "verb": "hold", "perception_input": receipt, "decision_timestamp": timestamp,
        "decision_id": "original-decision",
    }]
    assert journal.draft_resolutions("autonomous", date(2026, 10, 20), rows=rows) == 1
    draft = journal.load_drafts("autonomous")[0]
    assert draft["planes_at_entry"] == {"risk_radar": "risk_off"}
    assert draft["entry_perception"] == receipt
    assert draft["entry_evidence_scope"] == "initial_prompt_projection_only"
    assert draft["entry_decision_id"] == "original-decision"
    assert draft["regime_context"] == ""
    assert draft["regime_context_scope"] == "resolution_time_only"


def test_seal_does_not_attest_a_section_removed_from_the_final_prompt():
    from brain import perception_receipt as R
    projection = _receipt()["projection"]
    receipt = R.seal(R.capture_projection(projection, "Section removed by later injection"),
                     "Final prompt without that section")
    assert receipt["supplied"] is False
    assert R.entry_planes(receipt, decision_timestamp=datetime.now(timezone.utc).isoformat()) is None


@pytest.mark.parametrize("defect", ["publication_shape", "plane_list_shape", "freshness_shape"])
def test_malformed_receipt_shapes_fail_closed_without_crashing_the_journal(defect):
    from brain import perception_receipt as R
    projection = _receipt()["projection"]
    if defect == "publication_shape":
        projection["publication"] = "not a publication object"
    elif defect == "plane_list_shape":
        projection["plane_summaries"] = 7
    else:
        projection["plane_summaries"][0]["freshness"] = ["not a freshness object"]
    rendered = "Synthetic rendered section"
    receipt = R.seal(R.capture_projection(projection, rendered), rendered)
    assert R.entry_planes(receipt, decision_timestamp=datetime.now(timezone.utc).isoformat()) is None


def test_nonfinite_legacy_projection_does_not_abort_receipt_sealing():
    from brain import perception_receipt as R
    projection = _receipt()["projection"]
    projection["plane_summaries"][0]["magnitude"] = float("nan")
    rendered = "Original rendered section remains inspectable"
    receipt = R.seal(R.capture_projection(projection, rendered), rendered)
    assert receipt["rendered_context"] == rendered
    assert receipt.get("projection_status") == "unavailable"
    assert R.entry_planes(receipt, decision_timestamp=datetime.now(timezone.utc).isoformat()) is None
