"""Preserved walk-forward authority and run contracts."""
from __future__ import annotations

import hashlib
import json
import os
import pytest
from research import trend_persistence_panel as tpp
from research import trend_persistence_walkforward as wf

from tests.test_trend_persistence_walkforward import (
    _holdout_like,
    _panel,
    _reference,
    pinned,
    staged,
)


def test_nothing_is_scored_without_the_pinned_preregistration(monkeypatch):
    panel, inputs = _panel(seed=9)
    monkeypatch.setattr(wf, "PREREG_SHA256", None)
    with pytest.raises(tpp.PreregDrift):
        wf.compare(panel, inputs, {"tests": {}}, _reference())
    with pytest.raises(tpp.PreregDrift):
        wf.build_reference()
    monkeypatch.setattr(wf, "PREREG_SHA256", "0" * 64)
    with pytest.raises(tpp.PreregDrift):
        wf.compare(panel, inputs, {"tests": {}}, _reference())
    with pytest.raises(tpp.PreregDrift):
        wf.run()

def test_real_data_is_not_scored_without_the_pinned_reference(pinned, monkeypatch, tmp_path):
    monkeypatch.setattr(wf, "REFERENCE_SHA256", None)
    with pytest.raises(tpp.PreregDrift, match="no pinned simulated reference"):
        wf.run()
    ref = tmp_path / "ref.json"

    def write(**body):
        ref.write_text(json.dumps(body))
        monkeypatch.setattr(wf, "REFERENCE_SHA256", wf._sha256(str(ref)))

    write(prereg_sha256=wf.PREREG_SHA256, design={"design": "other"})
    monkeypatch.setattr(wf, "REFERENCE_FILE", str(ref))
    monkeypatch.setattr(wf, "REFERENCE_SHA256", "0" * 64)
    with pytest.raises(tpp.PreregDrift, match="hashes to"):
        wf.pinned_reference()
    write(prereg_sha256=wf.PREREG_SHA256, design={"design": "other"})
    with pytest.raises(tpp.PreregDrift, match="different design"):
        wf.pinned_reference()
    write(prereg_sha256=wf.PREREG_SHA256, design=wf.frozen_design(), code_sha256="0" * 64)
    with pytest.raises(tpp.PreregDrift, match="different code"):
        wf.pinned_reference()
    write(prereg_sha256=wf.PREREG_SHA256, design=wf.frozen_design(),
          code_sha256=wf.code_sha256())
    assert wf.pinned_reference()["design"] == wf.frozen_design()

def test_the_code_hash_covers_the_instrument_and_ignores_only_its_two_pins(monkeypatch, tmp_path):
    here = os.path.dirname(wf.__file__)
    for name in wf.CODE_FILES:
        with open(os.path.join(here, name), "rb") as fh:
            (tmp_path / name).write_bytes(fh.read())
    assert len(wf._PIN_LINE.findall((tmp_path / wf.CODE_FILES[0]).read_bytes())) == 2
    before = wf.code_sha256()
    monkeypatch.setattr(wf, "_HERE", str(tmp_path))
    assert wf.code_sha256() == before and len(before) == 64
    main = tmp_path / wf.CODE_FILES[0]
    body = main.read_text()
    main.write_text(wf._PIN_LINE.sub(rb'\1: str | None = "f00d"', body.encode()).decode())
    assert wf.code_sha256() == before                         # a pin changed: same code
    main.write_text(body.replace("CAPTURE_MIN = 0.010", "CAPTURE_MIN = 0.001"))
    assert body != main.read_text() and wf.code_sha256() != before   # a threshold changed
    main.write_text(body)
    other = tmp_path / wf.CODE_FILES[1]
    other.write_text(other.read_text() + "\n# edited\n")
    assert wf.code_sha256() != before                         # the panel module changed

def test_the_holdout_result_b2_reads_is_the_pinned_file(monkeypatch, tmp_path):
    held = wf.pinned_holdout_result()
    assert len(wf.dev_signs(held)) == 29 and set(wf.dev_signs(held).values()) <= {1, -1}
    other = tmp_path / "held.json"
    other.write_text(json.dumps(held))
    monkeypatch.setattr(wf, "HOLDOUT_RESULT_FILE", str(other))
    with pytest.raises(tpp.PreregDrift, match="hashes to"):
        wf.pinned_holdout_result()

def test_b2_stops_if_v2s_holdout_statistic_does_not_reproduce(pinned):
    panel, inputs = _panel(seed=10)
    held = _holdout_like(panel, inputs)
    key = wf.confirmed_keys()[0]
    held["tests"][key]["mean"] += 1e-6
    with pytest.raises(tpp.PreregDrift, match="does not reproduce"):
        wf.compare(panel, inputs, held, _reference())
    held = _holdout_like(panel, inputs)
    held["tests"][key]["n_dates"] += 1
    with pytest.raises(tpp.PreregDrift, match="does not reproduce"):
        wf.compare(panel, inputs, held, _reference())
    held = _holdout_like(panel, inputs)
    del held["tests"][key]
    with pytest.raises(tpp.PreregDrift, match="not the 29"):
        wf.compare(panel, inputs, held, _reference())

def test_a_panel_off_the_v2_design_is_refused(pinned):
    panel, inputs = _panel(seed=10)
    held = _holdout_like(panel, inputs)
    panel["observed_mask"] = False
    with pytest.raises(ValueError):
        wf.compare(panel, inputs, held, _reference())

def test_the_run_refuses_an_uncommitted_tree_and_any_other_panel(staged):
    staged["clean"] = False
    with pytest.raises(tpp.PreregDrift, match="uncommitted"):
        wf.run()
    assert not staged["attempt"].exists()                     # nothing was read: no attempt
    staged["clean"] = True
    with pytest.raises(tpp.PreregDrift, match="not the one V2"):
        wf.run()
    assert not staged["result"].exists()
    attempts = json.loads(staged["attempt"].read_text())["attempts"]
    assert len(attempts) == 1 and attempts[0]["retry_reason"] is None
    assert attempts[0]["git_head"] == "a" * 40 and attempts[0]["code_sha256"] == wf.code_sha256()

def test_an_attempt_that_left_no_result_needs_a_stated_reason(staged):
    with pytest.raises(tpp.PreregDrift, match="not the one V2"):
        wf.run()
    for reason in (None, "", "   "):
        with pytest.raises(tpp.HoldoutLocked, match="needs a stated reason"):
            wf.run(retry_reason=reason)
    with pytest.raises(tpp.PreregDrift, match="not the one V2"):
        wf.run(retry_reason="the loader pointed at the wrong store")
    attempts = json.loads(staged["attempt"].read_text())["attempts"]
    assert [a["retry_reason"] for a in attempts] == [None, "the loader pointed at the wrong store"]

def test_the_run_writes_one_result_and_is_never_made_again(staged, monkeypatch):
    monkeypatch.setattr(wf, "V2_PANEL_SHA256", "synthetic")
    out = wf.run()
    assert out["status"] == "scored" and out["decision"]["outcome"] == "eligible_calibrated_profile"
    written = json.loads(staged["result"].read_text())
    assert written["decision"] == out["decision"] and written["git_head"] == "a" * 40
    assert written["code_sha256"] == wf.code_sha256() and len(written["attempts"]) == 1
    assert written["holdout_result_sha256"] == wf.HOLDOUT_RESULT_SHA256
    assert not os.path.exists(str(staged["result"]) + ".tmp")
    for kwargs in ({}, {"retry_reason": "again"}):
        with pytest.raises(tpp.HoldoutLocked, match="not run again"):
            wf.run(**kwargs)
    assert len(json.loads(staged["attempt"].read_text())["attempts"]) == 1

def test_the_real_run_takes_no_output_path(capsys):
    with pytest.raises(SystemExit):
        wf.main(["--out", "elsewhere.json"])
    assert "fixed path" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        wf.main(["--reference"])
    assert "--out is required" in capsys.readouterr().err
    assert os.path.dirname(wf.RESULT_FILE) == os.path.dirname(wf.ATTEMPT_FILE) == "data"

def test_the_committed_result_was_produced_once_under_the_pinned_files():
    here = os.path.dirname(wf.__file__)
    with open(os.path.join(here, wf.RESULT_FILE)) as fh:
        out = json.load(fh)
    with open(os.path.join(here, wf.ATTEMPT_FILE)) as fh:
        attempts = json.load(fh)["attempts"]
    assert out["prereg_sha256"] == wf.PREREG_SHA256
    # The run pinned the reference as `--reference` wrote it: on one line. The committed file
    # holds the same value with one member per line (readout §7), and the pin follows the file.
    # Written on one line again, it must hash to what the run recorded.
    ref_path = os.path.join(here, wf.REFERENCE_FILE)
    with open(ref_path) as fh:
        one_line = json.dumps(json.load(fh), sort_keys=True, separators=(",", ":")) + "\n"
    assert out["reference_sha256"] == hashlib.sha256(one_line.encode()).hexdigest()
    assert (out["reference_sha256"][:8], out["reference_sha256"][-4:]) == ("e2caf7e8", "20f3")
    assert wf.REFERENCE_SHA256 == wf._sha256(ref_path)
    assert out["code_sha256"] == wf.code_sha256()
    assert out["holdout_result_sha256"] == wf.HOLDOUT_RESULT_SHA256
    assert out["panel_sha256"] == wf.V2_PANEL_SHA256
    assert out["attempts"] == attempts and len(attempts) == 1
    assert attempts[0]["retry_reason"] is None and attempts[0]["git_head"] == out["git_head"]
    # what the readout reports (§11): no gated horizon passes, three tests carry the label
    assert out["status"] == "scored" and out["decision"]["outcome"] == "no_model_value"
    assert out["decision"]["advances"] is False and out["decision"]["horizons"] == []
    assert not any(out["horizons"][h]["gates"]["passed"] for h in ("20", "60"))
    assert sum(s["beyond_simulated_volatility"] for s in out["q2"].values()) == 3
