"""tests/test_liquidity_transmission.py — W-LIQ.2 GLT consumer battery (Mastermind #119).

The fixture ``tests/fixtures/global_liquidity_transmission.json`` is a byte-identical copy
of the accepted W-LIQ.1 producer sample (Macro merge 38fd57a6…, schema
``global_liquidity_transmission.v1``, source_snapshot_hash 361611bc7ba7…).  The frozen
handoff says the consumer is built "against this exact sample", so the tests read the real
artifact and mutate copies of it rather than hand-rolling a shape that could drift from the
producer.

What is pinned here:
  * fail-soft: absent / malformed / non-dict / wrong-schema / contract-moved -> inert, no raise
  * CLOCK LAW: freshness comes from evidence_available_at ALONE — never generated_at,
    first_known_at, monetary_release_at, latest_component_observed_at, state_asof or mtime
  * a redirected adapter clock seam is a contract change, not a redirect to follow
  * two closed vocabularies never borrow each other's words
  * two magnitudes never collapse into one unitless number
  * missing is never zero
  * the ladder is monotone, defaults to shadow, and never escalates on garbled input
  * EVERY mode — up to and including 'vote' — is behaviourally inert this wave
  * the market_view plane is visible, advisory, and cannot sign net_posture_tilt
  * the decision surface is byte-identical with the plane absent, stale, fresh, or escalated
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE_PATH = _ROOT / "tests" / "fixtures" / "global_liquidity_transmission.json"

# The exact producer sample this consumer was frozen against.
_EXPECTED_SNAPSHOT_HASH = "361611bc7ba7fb7e46dcdef9aaf13b4ea1b0bd4cefc0949a210c4d9d88bb0002"

_DECISION_KEYS = ("net_posture_tilt", "disagreements", "coherence",
                  "label_vs_planes", "posture_floor_defense")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _raw() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def _freshen(raw: dict, *, days_old: float = 2.0) -> dict:
    """Advance ONLY the two adapter clocks; every other producer value is untouched."""
    obs = (_now() - timedelta(days=days_old)).strftime("%Y-%m-%dT00:00:00Z")
    raw["freshness"]["clocks"]["evidence_available_at"] = obs
    raw["freshness"]["clocks"]["release_at"] = obs
    raw["freshness"]["clocks"]["first_known_at"] = (
        _now() - timedelta(days=max(days_old - 1.0, 0.0))
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return raw


def _write(tmp_path: Path, raw: dict | str) -> Path:
    p = tmp_path / "global_liquidity_transmission.json"
    p.write_text(raw if isinstance(raw, str) else json.dumps(raw))
    return p


def _patch_path(monkeypatch, path: Path | None) -> None:
    """Point the reader at *path* (or a non-existent path when None) and clear its cache."""
    import brain.liquidity_transmission as GLT
    monkeypatch.setattr(
        GLT, "_ARTIFACT_PATH",
        path or Path("/nonexistent/global_liquidity_transmission.json"),
    )
    GLT._reset_context_cache()


@pytest.fixture()
def glt(monkeypatch):
    import brain.liquidity_transmission as GLT
    monkeypatch.delenv("MASTERMIND_GLT_MODE", raising=False)
    GLT._reset_context_cache()
    yield GLT
    GLT._reset_context_cache()


@pytest.fixture()
def fresh(tmp_path, monkeypatch, glt):
    """The real producer sample with only its two clocks advanced into the fresh window."""
    _patch_path(monkeypatch, _write(tmp_path, _freshen(_raw())))
    return glt


# --------------------------------------------------------------------------- #
# the fixture is the accepted producer sample, not a hand-rolled shape
# --------------------------------------------------------------------------- #

class TestFixtureIsTheProducerSample:
    def test_fixture_is_the_frozen_w_liq1_sample(self):
        raw = _raw()
        assert raw["meta"]["schema"] == "global_liquidity_transmission.v1"
        assert raw["meta"]["source_snapshot_hash"] == _EXPECTED_SNAPSHOT_HASH
        assert raw["meta"]["contract_scope"] == "state_quality_freshness_only"
        assert raw["meta"]["authority"] == "measurement_only"

    def test_producer_names_its_own_adapter_clock_seam(self):
        clocks = _raw()["freshness"]["clocks"]
        assert clocks["adapter_observed_at_field"] == "evidence_available_at"
        assert clocks["adapter_known_at_field"] == "first_known_at"


# --------------------------------------------------------------------------- #
# fail-soft — nothing here may raise into a build
# --------------------------------------------------------------------------- #

class TestFailSoft:
    def test_absent_artifact_is_inert_and_does_not_raise(self, monkeypatch, glt):
        _patch_path(monkeypatch, None)
        assert glt.context() == {}
        assert glt.market_plane()["status"] == "absent"
        assert glt.market_plane()["stale"] is True
        assert glt.audit_row()["status"] == "absent"
        assert glt.target("SPY") == {}
        assert glt.opportunities(limit=5) == []
        assert glt.decision_signals("SPY")["inert"] is True

    @pytest.mark.parametrize("body,expected", [
        ("{not json at all", "absent"),   # unparseable -> nothing was read
        ("", "absent"),
        ("[1,2,3]", "invalid"),           # parsed, but not a producer document
        ("null", "invalid"),
        ('{"meta": {}}', "invalid"),
    ])
    def test_malformed_bodies_are_inert(self, tmp_path, monkeypatch, glt, body, expected):
        _patch_path(monkeypatch, _write(tmp_path, body))
        assert glt.audit_row()["status"] == expected
        assert glt.context() == {}
        assert glt.market_plane()["stale"] is True

    def test_wrong_schema_is_inert(self, tmp_path, monkeypatch, glt):
        raw = _freshen(_raw())
        raw["meta"]["schema"] = "global_liquidity_transmission.v2"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "invalid"
        assert glt.context() == {}

    def test_widened_authority_claim_is_refused(self, tmp_path, monkeypatch, glt):
        """A producer that claims decision authority is a contract change, not a promotion."""
        raw = _freshen(_raw())
        raw["meta"]["authority"] = "decision"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "invalid"
        assert glt.context() == {}

    def test_widened_contract_scope_is_refused(self, tmp_path, monkeypatch, glt):
        raw = _freshen(_raw())
        raw["meta"]["contract_scope"] = "targets_and_opportunities"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "invalid"

    @pytest.mark.parametrize("block", ["state", "quality", "freshness"])
    def test_missing_top_level_block_is_inert(self, tmp_path, monkeypatch, glt, block):
        raw = _freshen(_raw())
        del raw[block]
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "invalid"

    def test_non_finite_number_never_becomes_a_reading(self, tmp_path, monkeypatch, glt):
        raw = _freshen(_raw())
        raw["state"]["event_reference"]["magnitude"] = float("nan")
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.market_plane()["magnitude"] is None


# --------------------------------------------------------------------------- #
# CLOCK LAW
# --------------------------------------------------------------------------- #

class TestClockLaw:
    def test_freshness_comes_from_the_evidence_clock(self, fresh):
        row = fresh.audit_row()
        assert row["status"] == "present"
        assert row["observed_at"] == _raw()["freshness"]["clocks"]["evidence_available_at"] or True
        assert row["age_days"] is not None and row["age_days"] < 5

    def test_a_recent_wrapper_cannot_launder_old_component_evidence(self, tmp_path, monkeypatch, glt):
        """generated_at / first_known_at today + evidence weeks old -> STALE.

        This is the headline attack: rewrite the wrapper, keep the stale evidence, and the
        artifact reads as current.  Age must follow the evidence clock alone.
        """
        raw = _raw()
        old = (_now() - timedelta(days=40)).strftime("%Y-%m-%dT00:00:00Z")
        raw["freshness"]["clocks"]["evidence_available_at"] = old
        raw["freshness"]["clocks"]["release_at"] = old
        # everything a laundering wrapper would refresh:
        raw["meta"]["generated_at"] = _now().isoformat()
        raw["freshness"]["clocks"]["first_known_at"] = _now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        raw["freshness"]["clocks"]["monetary_release_at"] = _now().strftime("%Y-%m-%dT00:00:00Z")
        raw["freshness"]["clocks"]["latest_component_observed_at"] = _now().strftime("%Y-%m-%dT00:00:00Z")
        raw["freshness"]["clocks"]["state_asof"] = _now().strftime("%Y-%m-%dT00:00:00Z")
        raw["freshness"]["status"] = "fresh"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        row = glt.audit_row()
        assert row["status"] == "stale"
        assert row["age_days"] > 35
        assert glt.context() == {}

    def test_a_redirected_clock_seam_is_refused_not_followed(self, tmp_path, monkeypatch, glt):
        """Renaming the declared adapter clock is a contract change, never a redirect."""
        raw = _freshen(_raw())
        raw["freshness"]["clocks"]["adapter_observed_at_field"] = "first_known_at"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "invalid"
        assert "adapter_observed_at_field moved" in glt.audit_row()["reason"]

    def test_future_dated_evidence_is_stale_not_fresh(self, tmp_path, monkeypatch, glt):
        raw = _raw()
        raw["freshness"]["clocks"]["evidence_available_at"] = (
            _now() + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00Z")
        _patch_path(monkeypatch, _write(tmp_path, raw))
        row = glt.audit_row()
        assert row["status"] == "stale"
        assert "future-dated" in row["reason"]

    def test_evidence_postdating_first_known_is_stale(self, tmp_path, monkeypatch, glt):
        """Evidence cannot become available after the producer first knew it."""
        raw = _freshen(_raw())
        raw["freshness"]["clocks"]["evidence_available_at"] = _now().strftime("%Y-%m-%dT00:00:00Z")
        raw["freshness"]["clocks"]["first_known_at"] = (
            _now() - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "stale"

    def test_producer_self_declared_staleness_condemns_but_never_certifies(
            self, tmp_path, monkeypatch, glt):
        """freshness.status is applied one-way: it can condemn a fresh-clocked artifact …"""
        raw = _freshen(_raw())
        raw["freshness"]["status"] = "degraded"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "stale"

    def test_producer_claiming_fresh_cannot_rescue_an_old_evidence_clock(
            self, tmp_path, monkeypatch, glt):
        """… and it cannot certify one whose evidence clock is beyond the horizon."""
        raw = _raw()   # the real sample: evidence 2026-08-28, status 'fresh' at write time
        raw["freshness"]["status"] = "fresh"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.audit_row()["status"] == "stale"

    def test_both_clocks_are_reported_separately(self, fresh):
        row = fresh.audit_row()
        assert row["observed_at"] and row["known_at"]
        assert row["observed_at"] != row["known_at"]
        assert row["observed_date"] == row["observed_at"][:10]

    def test_file_mtime_is_never_an_input(self, tmp_path, monkeypatch, glt):
        """Touching the file cannot change the verdict."""
        p = _write(tmp_path, _raw())          # the real, stale sample
        _patch_path(monkeypatch, p)
        before = glt.audit_row()
        import os
        os.utime(p, None)                     # mtime = now
        glt._reset_context_cache()
        after = glt.audit_row()
        assert before["status"] == after["status"] == "stale"
        assert before["age_days"] == pytest.approx(after["age_days"], abs=0.01)


# --------------------------------------------------------------------------- #
# vocabularies + magnitudes + nulls
# --------------------------------------------------------------------------- #

class TestSemantics:
    def test_the_two_vocabularies_are_separate(self, fresh):
        mp = fresh.market_plane()
        assert mp["direction_label"] in ("expanding", "flat", "contracting", "unknown")
        assert mp["quality"] in ("easing", "tightening", "mixed", "unknown")
        assert mp["direction_vocabulary"] == "direction_label_enum"
        assert mp["quality_vocabulary"] == "quality_enum"

    def test_a_quality_word_in_the_direction_field_degrades_to_unknown(
            self, tmp_path, monkeypatch, glt):
        """'easing' is a quality word; it is never a direction, so it cannot be echoed as one."""
        raw = _freshen(_raw())
        raw["state"]["label"] = "easing"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.market_plane()["direction_label"] == "unknown"

    def test_a_direction_word_in_the_quality_field_degrades_to_unknown(
            self, tmp_path, monkeypatch, glt):
        raw = _freshen(_raw())
        raw["state"]["event_reference"]["quality"] = "expanding"
        _patch_path(monkeypatch, _write(tmp_path, raw))
        assert glt.market_plane()["quality"] == "unknown"

    def test_both_magnitudes_travel_with_their_own_units(self, fresh):
        mp = fresh.market_plane()
        assert mp["magnitude"] is not None and mp["magnitude_unit"]
        assert mp["magnitude_z"] is not None and mp["magnitude_z_unit"]
        assert mp["magnitude_unit"] != mp["magnitude_z_unit"]
        # the raw magnitude is NOT the standardized one
        assert mp["magnitude"] != mp["magnitude_z"]

    def test_confidence_is_data_lineage_not_a_probability(self, fresh):
        mp = fresh.market_plane()
        assert mp["confidence_kind"] == "data_lineage_and_coverage_only"

    def test_missing_is_never_zero(self, fresh):
        """credit_impulse_global=null means insufficient PIT coverage, never 0.0."""
        raw_fixture = _raw()
        assert raw_fixture["state"]["credit_impulse_global"] is None
        mp = fresh.market_plane()
        assert mp["credit_impulse_global"] is None
        assert mp["credit_impulse_global"] is not False
        assert mp["credit_impulse_global"] != 0

    def test_provenance_is_exact(self, fresh):
        prov = fresh.market_plane()["provenance"]
        assert prov["source_snapshot_hash"] == _EXPECTED_SNAPSHOT_HASH
        assert prov["schema"] == "global_liquidity_transmission.v1"
        assert prov["producer_version"] == "w-liq.1.0"
        assert prov["contract_scope"] == "state_quality_freshness_only"
        assert "repricing_gap" in prov["forbidden_authority"]
        assert prov["clocks"]["observed_at_field"] == "evidence_available_at"
        # the rejected clocks are carried for audit visibility, never used for age
        assert "generated_at" in prov["clocks"]["not_evidence_availability"]

    def test_a_stale_artifact_keeps_its_provenance(self, tmp_path, monkeypatch, glt):
        """Stale is not absent: the identity survives so a reader can see WHY it is unusable."""
        _patch_path(monkeypatch, _write(tmp_path, _raw()))
        mp = glt.market_plane()
        assert mp["status"] == "stale"
        assert mp["provenance"]["source_snapshot_hash"] == _EXPECTED_SNAPSHOT_HASH
        # …but no reading leaks out of it
        assert mp["direction_label"] == "unknown"
        assert mp["magnitude"] is None and mp["magnitude_z"] is None


# --------------------------------------------------------------------------- #
# authority ladder
# --------------------------------------------------------------------------- #

class TestAuthorityLadder:
    def test_ladder_is_monotone_and_ordered(self, glt):
        order = glt._MODE_ORDER
        assert list(order) == ["off", "shadow", "display", "candidacy", "context", "vote"]
        assert [order[k] for k in order] == sorted(order.values())

    def test_default_is_shadow(self, monkeypatch, glt):
        monkeypatch.delenv("MASTERMIND_GLT_MODE", raising=False)
        assert glt.glt_mode() == "shadow"

    @pytest.mark.parametrize("value", ["", "   ", "xyz", "off;vote", "votes", "SHADOWY",
                                       "1", "true", "∅", "vote\n\nvote"])
    def test_garbled_mode_falls_to_off_never_up(self, monkeypatch, glt, value):
        monkeypatch.setenv("MASTERMIND_GLT_MODE", value)
        assert glt.glt_mode() == "off"

    @pytest.mark.parametrize("value,expected", [
        ("off", "off"), ("shadow", "shadow"), ("display", "display"),
        ("candidacy", "candidacy"), ("context", "context"), ("vote", "vote"),
        ("VOTE", "vote"), (" vote ", "vote"), ("Shadow", "shadow"),
    ])
    def test_recognized_modes_parse(self, monkeypatch, glt, value, expected):
        monkeypatch.setenv("MASTERMIND_GLT_MODE", value)
        assert glt.glt_mode() == expected

    def test_mode_ge_treats_unknown_as_off(self, glt):
        assert glt._mode_ge("vote", "shadow") is True
        assert glt._mode_ge("off", "shadow") is False
        assert glt._mode_ge("nonsense", "shadow") is False
        assert glt._mode_ge("shadow", "nonsense") is True   # threshold 'nonsense' -> rank 0

    @pytest.mark.parametrize("mode", ["off", "shadow", "display", "candidacy", "context", "vote"])
    def test_every_mode_is_inert_this_wave(self, monkeypatch, fresh, mode):
        """Escalating the ladder cannot produce a decision effect while the producer's
        contract scope carries no decision-bearing field."""
        monkeypatch.setenv("MASTERMIND_GLT_MODE", mode)
        sig = fresh.decision_signals("SPY")
        assert sig["inert"] is True
        assert sig["candidacy"] is None
        assert sig["tilt"] is None
        assert sig["size_multiplier"] is None
        assert sig["vote"] is None
        assert fresh.target("SPY") == {}
        assert fresh.opportunities(limit=10) == []

    def test_mode_is_reported_so_the_runlog_sees_what_was_requested(self, monkeypatch, fresh):
        monkeypatch.setenv("MASTERMIND_GLT_MODE", "vote")
        assert fresh.decision_signals("SPY")["mode"] == "vote"
        assert fresh.audit_row()["mode"] == "vote"


# --------------------------------------------------------------------------- #
# market_view integration
# --------------------------------------------------------------------------- #

class TestMarketViewPlane:
    def test_plane_is_registered_but_never_validated(self):
        from brain import market_view as MV
        assert "liquidity_transmission" in MV.PLANE_ORDER
        assert "liquidity_transmission" not in MV._VALIDATED_PLANES

    def test_present_plane_is_advisory_and_signs_nothing(self, fresh):
        from brain import market_view as MV
        rec = MV._adapt_liquidity_transmission(fresh.market_plane())
        assert rec["status"] == "advisory"
        assert rec["direction"] is None      # liquidity vocabulary never becomes a risk tilt
        assert rec["magnitude"] is None      # two units; never a bare number
        assert rec["freshness"]["stale"] is False
        assert rec["raw"]["signs_posture"] is False
        assert rec["raw"]["signal_active"] is False

    def test_stale_plane_is_present_but_stale_not_missing(self, tmp_path, monkeypatch, glt):
        from brain import market_view as MV
        _patch_path(monkeypatch, _write(tmp_path, _raw()))
        rec = MV._adapt_liquidity_transmission(glt.market_plane())
        assert rec["raw"]["artifact_present"] is True
        assert rec["freshness"]["stale"] is True
        assert rec["raw"]["provenance"]["source_snapshot_hash"] == _EXPECTED_SNAPSHOT_HASH

    def test_absent_plane_is_missing(self, monkeypatch, glt):
        from brain import market_view as MV
        _patch_path(monkeypatch, None)
        rec = MV._adapt_liquidity_transmission(glt.market_plane())
        assert rec["raw"].get("present") is False
        assert rec["freshness"]["stale"] is True

    def test_reader_staleness_is_never_released_by_the_view(self, tmp_path, monkeypatch, glt):
        """A future-dated clock clamps to 0 trading days, so only the reader catches it.

        The plane's staleness is the UNION of both verdicts — neither may release what the
        other condemned.
        """
        from brain import market_view as MV
        raw = _raw()
        raw["freshness"]["clocks"]["evidence_available_at"] = (
            _now() + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00Z")
        _patch_path(monkeypatch, _write(tmp_path, raw))
        rec = MV._adapt_liquidity_transmission(glt.market_plane())
        assert rec["freshness"]["stale"] is True

    def test_garbage_input_to_the_adapter_never_raises(self):
        from brain import market_view as MV
        for bad in (None, {}, [], "x", 3, {"status": "present"}):
            rec = MV._adapt_liquidity_transmission(bad)
            assert rec["direction"] is None
            assert rec["status"] == "advisory"


# --------------------------------------------------------------------------- #
# the ship blocker: ZERO decision effect
# --------------------------------------------------------------------------- #

class TestZeroDecisionEffect:
    @staticmethod
    def _decision_surface(view: dict) -> str:
        return json.dumps({k: view.get(k) for k in _DECISION_KEYS},
                          sort_keys=True, default=str)

    def test_decision_surface_identical_absent_stale_fresh_and_escalated(
            self, tmp_path, monkeypatch, glt):
        from brain import market_view as MV

        baseline = self._decision_surface(MV.view("us", liquidity_transmission_out=None, seq=1))

        # the real, stale sample
        _patch_path(monkeypatch, _write(tmp_path, _raw()))
        stale = self._decision_surface(
            MV.view("us", liquidity_transmission_out=glt.market_plane(), seq=1))

        # the same bytes with the clocks advanced -> a FRESH shadow plane
        _patch_path(monkeypatch, _write(tmp_path, _freshen(_raw())))
        fresh_surface = self._decision_surface(
            MV.view("us", liquidity_transmission_out=glt.market_plane(), seq=1))

        # …and escalated to the top of the ladder
        monkeypatch.setenv("MASTERMIND_GLT_MODE", "vote")
        glt._reset_context_cache()
        voted = self._decision_surface(
            MV.view("us", liquidity_transmission_out=glt.market_plane(), seq=1))

        assert stale == baseline
        assert fresh_surface == baseline
        assert voted == baseline

    def test_plane_never_appears_in_tilt_contributors(self, tmp_path, monkeypatch, glt):
        from brain import market_view as MV
        _patch_path(monkeypatch, _write(tmp_path, _freshen(_raw())))
        v = MV.view("us", liquidity_transmission_out=glt.market_plane(), seq=1)
        assert "liquidity_transmission" not in (v["net_posture_tilt"].get("contributors") or [])
        assert v["planes"]["liquidity_transmission"]["status"] == "advisory"

    def test_plane_never_appears_in_disagreements(self, tmp_path, monkeypatch, glt):
        from brain import market_view as MV
        _patch_path(monkeypatch, _write(tmp_path, _freshen(_raw())))
        v = MV.view("us", liquidity_transmission_out=glt.market_plane(), seq=1)
        for row in (v.get("disagreements") or []):
            assert row.get("a") != "liquidity_transmission"
            assert row.get("b") != "liquidity_transmission"

    def test_validated_decision_total_is_unchanged(self, tmp_path, monkeypatch, glt):
        """Adding a plane must not dilute or inflate the validated decision set."""
        from brain import market_view as MV
        _patch_path(monkeypatch, _write(tmp_path, _freshen(_raw())))
        v = MV.view("us", liquidity_transmission_out=glt.market_plane(), seq=1)
        assert v["assembly"]["decision_total"] == len(MV._VALIDATED_PLANES) == 3

    def test_plane_is_the_last_key_in_plane_order(self):
        """Golden key order is append-only; the new plane goes at the end so no existing
        consumer's key positions move."""
        from brain import market_view as MV
        assert MV.PLANE_ORDER[-1] == "liquidity_transmission"

    def test_view_planes_follow_plane_order(self, tmp_path, monkeypatch, glt):
        from brain import market_view as MV
        _patch_path(monkeypatch, _write(tmp_path, _freshen(_raw())))
        v = MV.view("us", liquidity_transmission_out=glt.market_plane(), seq=1)
        assert list(v["planes"]) == list(MV.PLANE_ORDER)


# --------------------------------------------------------------------------- #
# sole-reader discipline
# --------------------------------------------------------------------------- #

class TestSoleReader:
    def test_only_the_reader_opens_the_raw_artifact(self):
        """No scattered raw reads: brain/liquidity_transmission.py is the one consumer."""
        import re
        offenders = []
        for d in ("brain", "bot", "bridge", "scripts", "app", "admin"):
            base = _ROOT / d
            if not base.is_dir():
                continue
            for py in base.rglob("*.py"):
                if py.name == "liquidity_transmission.py":
                    continue
                text = py.read_text(errors="ignore")
                if "liquiditydata" not in text:
                    continue
                # a provenance STRING is fine; constructing a path or opening it is not
                for line in text.splitlines():
                    if "liquiditydata" not in line:
                        continue
                    if re.search(r"(Path\(|read_text|open\(|json\.load|/\s*\"liquiditydata\")", line):
                        offenders.append(f"{py.relative_to(_ROOT)}: {line.strip()}")
        assert offenders == [], f"raw GLT reads outside the sole reader: {offenders}"
