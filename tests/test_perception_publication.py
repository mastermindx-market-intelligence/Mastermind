"""Synthetic proof of one source capture, one commit point and no evidence refresh by timer."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import subprocess

import pytest

from brain import decision_context as DC
from brain import market_view as MV
from brain import perception_publication as P
from brain import regime_frame as RF

NOW = datetime(2026, 10, 21, 5, tzinfo=timezone.utc)
FRESH = "2026-10-19"


def _sources():
    return {
        "regime": {
            "date": FRESH, "quad": "Q1", "quad_name": "Goldilocks", "confidence": 0.8,
            "risk_radar": {"asof": FRESH, "state": "caution", "top_score": 80},
            "mtf_signals": {"asof": FRESH, "signals": [{"state": "short-bias"}]},
        },
        "cycles": {"meta": {"asOf": FRESH}, "sectors": [
            {"ticker": "XLK", "now": {"phase": "Markup", "pos": 20, "osc_slope": 1}},
        ]},
        "rrg": None, "group_flow": None,
    }


def _capture(sources=None, *, revision="a" * 40, at=NOW):
    sources = copy.deepcopy(sources if sources is not None else _sources())
    manifest = {}
    for name, (path, required) in P._SOURCE_PATHS.items():
        row = {"path": path, "required": required}
        value = sources[name]
        row.update({"status": "absent"} if value is None else {
            "status": "present", "sha256": P._sha(P._json_bytes(value)),
        })
        manifest[name] = row
    return {
        "contract": P._CONTRACT, "source_revision": revision,
        "captured_at": at.isoformat(), "sources": sources,
        "source_manifest": manifest, "source_identity": P._source_identity(sources),
        "excluded": list(P._EXCLUDED),
    }


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    mv_dir = tmp_path / "market_view"
    dc_dir = tmp_path / "decision_context"
    monkeypatch.setattr(MV, "_ARTIFACT_DIR", mv_dir)
    monkeypatch.setattr(MV, "_LATEST_PATH", mv_dir / "latest.json")
    monkeypatch.setattr(DC, "_ARTIFACT_DIR", dc_dir)
    monkeypatch.setattr(DC, "_LATEST_PATH", dc_dir / "latest.json")
    monkeypatch.setattr(DC, "_MARKET_VIEW_PATH", mv_dir / "latest.json")
    doctrine = tmp_path / "doctrine.yml"
    doctrine.write_text("{}\n")
    monkeypatch.setattr(P, "_DOCTRINE_PATH", doctrine)
    monkeypatch.setattr(RF, "_DOCTRINE_PATH", doctrine)
    # Captured assembly may not acquire a second regime, auxiliary organ or budget.
    def forbidden(*args, **kwargs):
        raise AssertionError("uncaptured market/policy read")
    monkeypatch.setattr(RF, "_read_raw", forbidden)
    monkeypatch.setattr(RF, "budget", forbidden)
    monkeypatch.setattr(MV, "_adapt_rotation_tensor", forbidden)
    monkeypatch.setattr(MV, "_adapt_anticipation", forbidden)


def _latest():
    return json.loads(MV._LATEST_PATH.read_bytes())


def test_publish_same_capture_once_despite_timer_or_unrelated_revision():
    capture = _capture()
    first = P.publish_capture(capture, now=NOW)
    original = MV._LATEST_PATH.read_bytes()
    capture["source_revision"] = "b" * 40
    capture["captured_at"] = (NOW + timedelta(hours=3)).isoformat()
    second = P.publish_capture(capture, now=NOW + timedelta(hours=3))
    assert first["status"] == "published"
    assert second["status"] == "unchanged"
    assert first["seq"] == second["seq"] == 1
    assert MV._LATEST_PATH.read_bytes() == original
    typed = DC.for_publication(_latest())
    assert typed["seq"] == 1
    assert typed["publication"]["publication_id"] == first["publication_id"]
    assert typed["market_asof"] == FRESH
    assert _latest()["budget_ref"] == {"lead_budget": None, "inputs": None}
    absent = _latest()["planes"]["distribution_tells"]
    assert absent["reading"] is None and absent["direction"] is None
    assert absent["status"] != "validated"


def test_generated_timestamp_does_not_create_source_observation():
    left = _sources()
    right = copy.deepcopy(left)
    left["regime"]["built_at"] = "2026-10-20T01:00:00Z"
    right["regime"]["built_at"] = "2026-10-21T01:00:00Z"
    assert P._source_identity(left) == P._source_identity(right)


def test_same_day_correction_keeps_original_immutable_pair():
    P.publish_capture(_capture(), now=NOW)
    before = {p: p.read_bytes() for p in MV._ARTIFACT_DIR.glob("*.json")}
    old = _latest()
    old_typed = DC.for_publication(old)
    corrected = _sources()
    corrected["regime"]["risk_radar"]["state"] = "calm"
    corrected["regime"]["mtf_signals"]["signals"] = [{"state": "long-bias"}]
    result = P.publish_capture(_capture(corrected, at=NOW + timedelta(minutes=3)),
                               now=NOW + timedelta(minutes=3))
    assert result["status"] == "published" and result["seq"] == 2
    assert _latest()["asof"] == old["asof"]
    for path, payload in before.items():
        if path.name != "latest.json":
            assert path.read_bytes() == payload
    assert DC.for_publication(old) == old_typed
    assert _latest()["publication"]["source_identity"] != old["publication"]["source_identity"]


@pytest.mark.parametrize("defect", ["missing", "old", "future", "malformed", "cycles_missing"])
def test_incomplete_required_sources_preserve_last_complete_pair(defect):
    P.publish_capture(_capture(), now=NOW)
    before = MV._LATEST_PATH.read_bytes()
    typed_before = DC.for_publication(_latest())
    sources = _sources()
    if defect == "missing":
        del sources["regime"]["risk_radar"]
    elif defect == "cycles_missing":
        sources["cycles"] = None
    else:
        sources["regime"]["risk_radar"]["asof"] = {
            "old": "2026-08-07", "future": "2026-10-22", "malformed": "not-a-date",
        }[defect]
    with pytest.raises(P.PublicationRefused, match="required_voter"):
        P.publish_capture(_capture(sources), now=NOW)
    assert MV._LATEST_PATH.read_bytes() == before
    assert DC.for_publication(_latest()) == typed_before


def test_advisory_update_cannot_republish_positive_survivors_after_dissent_expires():
    sources = _sources()
    sources["regime"]["mtf_signals"]["signals"] = [{"state": "long-bias"}]
    P.publish_capture(_capture(sources), now=NOW)
    original = MV._LATEST_PATH.read_bytes()
    sources["regime"]["risk_radar"]["asof"] = "2026-08-07"
    sources["rrg"] = {"asof": FRESH, "sectors": [{"key": "Tech", "quadrant": "leading"}]}
    with pytest.raises(P.PublicationRefused, match="required_voter_ineligible:risk_radar"):
        P.publish_capture(_capture(sources), now=NOW)
    assert MV._LATEST_PATH.read_bytes() == original


def test_prepare_failure_never_changes_committed_pair(monkeypatch):
    P.publish_capture(_capture(), now=NOW)
    original = MV._LATEST_PATH.read_bytes()
    typed = DC.for_publication(_latest())
    def fail(*args):
        raise OSError("synthetic disk failure")
    monkeypatch.setattr(P, "_immutable_write", fail)
    changed = _sources()
    changed["regime"]["risk_radar"]["top_score"] = 81
    with pytest.raises(OSError):
        P.publish_capture(_capture(changed, at=NOW + timedelta(seconds=1)),
                          now=NOW + timedelta(seconds=1))
    assert MV._LATEST_PATH.read_bytes() == original
    assert DC.for_publication(_latest()) == typed


def test_commit_failure_keeps_old_pair_despite_orphan_prepared_copies(monkeypatch):
    P.publish_capture(_capture(), now=NOW)
    original = MV._LATEST_PATH.read_bytes()
    typed = DC.for_publication(_latest())
    def fail(*args):
        raise OSError("synthetic rename refusal")
    monkeypatch.setattr(P, "_atomic_replace", fail)
    changed = _sources()
    changed["regime"]["risk_radar"]["top_score"] = 81
    with pytest.raises(P.PublicationRefused, match="commit_failed_before_publication"):
        P.publish_capture(_capture(changed, at=NOW + timedelta(seconds=1)),
                          now=NOW + timedelta(seconds=1))
    assert MV._LATEST_PATH.read_bytes() == original
    assert DC.for_publication(_latest()) == typed


def test_lost_post_commit_reply_is_unknown_and_reconciles_without_duplicate(monkeypatch):
    real = P._atomic_replace
    def commit_then_fail(path, payload):
        real(path, payload)
        raise OSError("synthetic lost acknowledgement")
    monkeypatch.setattr(P, "_atomic_replace", commit_then_fail)
    result = P.publish_capture(_capture(), now=NOW)
    assert result["status"] == "effect_unknown"
    assert DC.for_publication(_latest())["seq"] == 1
    monkeypatch.setattr(P, "_atomic_replace", real)
    assert P.publish_capture(_capture(), now=NOW)["status"] == "unchanged"
    assert _latest()["seq"] == 1


def test_typed_reference_corruption_cannot_fall_back_to_compatibility_latest():
    P.publish_capture(_capture(), now=NOW)
    published = _latest()
    assert DC._LATEST_PATH.is_file()
    path = DC._ARTIFACT_DIR / published["publication"]["decision_context"]["file"]
    path.write_text("{}")
    assert DC.for_publication(published) == {}
    assert DC.prompt_summary(now=NOW)["serving_freshness"]["current_assessment_available"] is False


def test_reference_path_cannot_escape_existing_typed_directory():
    P.publish_capture(_capture(), now=NOW)
    published = _latest()
    published["publication"]["decision_context"]["file"] = "../latest.json"
    assert DC.for_publication(published) == {}


def test_concurrent_triggers_commit_one_observation():
    capture = _capture()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: P.publish_capture(capture, now=NOW), range(2)))
    assert sorted(r["status"] for r in results) == ["published", "unchanged"]
    assert _latest()["seq"] == 1


@pytest.mark.parametrize("info", [
    {}, {"stale": False}, {"refresh_mode": "owned", "refresh_succeeded": False},
])
def test_unknown_or_failed_refresh_never_captures(info, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("capture attempted after failed refresh")
    monkeypatch.setattr(P, "capture_sources", forbidden)
    assert P.publish_after_refresh(info, now=NOW)["status"] == "refused"
    assert not MV._LATEST_PATH.exists()


def test_external_refresh_none_is_not_owned_refresh_failure(monkeypatch):
    monkeypatch.setattr(P, "capture_sources", lambda **kwargs: _capture())
    result = P.publish_after_refresh({
        "refresh_mode": "external", "refreshed_to": None,
        "refresh_succeeded": None, "stale": False,
    }, now=NOW)
    assert result["status"] == "published"


def test_false_stale_flag_does_not_prove_source_capture(monkeypatch):
    def fail(**kwargs):
        raise P.PublicationRefused("required_source_missing")
    monkeypatch.setattr(P, "capture_sources", fail)
    result = P.publish_after_refresh({"refresh_mode": "external", "stale": False}, now=NOW)
    assert result == {"status": "refused", "reason": "required_source_missing"}


def _git_repo(tmp_path, monkeypatch):
    repo = tmp_path / "macro"
    repo.mkdir()
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=Synthetic Test",
             "-c", "user.email=synthetic@example.invalid", *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    git("init")
    for name, value in _sources().items():
        if value is None:
            continue
        path = repo / P._SOURCE_PATHS[name][0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    git("add", ".")
    git("commit", "-m", "Synthetic captured market sources")
    monkeypatch.setattr(P, "_MACRO_ROOT", repo)
    return repo, git


def test_capture_uses_exact_committed_objects_and_preserves_own_dates(tmp_path, monkeypatch):
    repo, git = _git_repo(tmp_path, monkeypatch)
    first = P.capture_sources(now=NOW)
    assert first["source_revision"] == git("rev-parse", "HEAD")
    assert first["sources"]["regime"]["risk_radar"]["asof"] == FRESH
    assert first["source_manifest"]["rrg"]["status"] == "absent"
    (repo / "unrelated.txt").write_text("unrelated repository change")
    git("add", "unrelated.txt")
    git("commit", "-m", "Synthetic unrelated change")
    second = P.capture_sources(now=NOW)
    assert second["source_revision"] != first["source_revision"]
    assert second["source_identity"] == first["source_identity"]


def test_partial_working_tree_is_not_accepted_as_complete_capture(tmp_path, monkeypatch):
    repo, _ = _git_repo(tmp_path, monkeypatch)
    (repo / P._SOURCE_PATHS["regime"][0]).write_text("{}")
    with pytest.raises(P.PublicationRefused, match="working_source_not_at_revision:regime"):
        P.capture_sources(now=NOW)


def test_precommit_directory_sync_failure_preserves_committed_pair(monkeypatch):
    P.publish_capture(_capture(), now=NOW)
    original = MV._LATEST_PATH.read_bytes()
    typed = DC.for_publication(_latest())
    changed = _sources()
    changed["regime"]["risk_radar"]["top_score"] = 81
    def fail(path):
        raise OSError("synthetic directory sync failure before commit")
    monkeypatch.setattr(P, "_sync_directory", fail)
    with pytest.raises(OSError):
        P.publish_capture(_capture(changed, at=NOW + timedelta(seconds=1)),
                          now=NOW + timedelta(seconds=1))
    assert MV._LATEST_PATH.read_bytes() == original
    assert DC.for_publication(_latest()) == typed


def test_postcommit_directory_sync_failure_is_unknown_then_reconciles(monkeypatch):
    real = P._sync_directory
    def fail_after_commit(path):
        if path == MV._ARTIFACT_DIR and MV._LATEST_PATH.exists():
            raise OSError("synthetic lost durability acknowledgement")
        real(path)
    monkeypatch.setattr(P, "_sync_directory", fail_after_commit)
    result = P.publish_capture(_capture(), now=NOW)
    assert result["status"] == "effect_unknown"
    assert DC.for_publication(_latest())["seq"] == 1
    monkeypatch.setattr(P, "_sync_directory", real)
    assert P.publish_capture(_capture(), now=NOW)["status"] == "unchanged"
    assert _latest()["seq"] == 1


def test_unreadable_commit_effect_is_unknown_not_refused(monkeypatch):
    real_replace = P._atomic_replace
    real_read = P.Path.read_bytes
    committed = []
    def replace(path, payload):
        real_replace(path, payload)
        if path == MV._LATEST_PATH:
            committed.append(True)
    def read(path):
        if committed and path == MV._LATEST_PATH:
            raise OSError("synthetic lost post-commit read access")
        return real_read(path)
    monkeypatch.setattr(P, "_atomic_replace", replace)
    monkeypatch.setattr(P.Path, "read_bytes", read)
    result = P.publish_capture(_capture(), now=NOW)
    assert result["status"] == "effect_unknown"
    monkeypatch.setattr(P.Path, "read_bytes", real_read)
    assert DC.for_publication(_latest())["seq"] == 1


def test_changed_commit_preimage_is_not_overwritten(monkeypatch):
    P.publish_capture(_capture(), now=NOW)
    competing = copy.deepcopy(_latest())
    competing["seq"] = 20
    competing_bytes = P._json_bytes(competing)
    real = P._immutable_write
    def interleave(path, payload):
        real(path, payload)
        if path.parent == MV._ARTIFACT_DIR:
            MV._LATEST_PATH.write_bytes(competing_bytes)
    monkeypatch.setattr(P, "_immutable_write", interleave)
    changed = _sources()
    changed["regime"]["risk_radar"]["top_score"] = 81
    with pytest.raises(P.PublicationRefused, match="publication_changed_before_commit"):
        P.publish_capture(_capture(changed, at=NOW + timedelta(seconds=1)),
                          now=NOW + timedelta(seconds=1))
    assert MV._LATEST_PATH.read_bytes() == competing_bytes


@pytest.mark.parametrize("info", [
    {"refresh_mode": "owned", "refresh_succeeded": True},
    {"refresh_mode": "owned", "refresh_succeeded": True, "refreshed_to": None},
    {"refresh_mode": "owned", "refresh_succeeded": True, "refreshed_to": ""},
])
def test_contradictory_owned_refresh_result_never_captures(info, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("capture attempted without successful owned refresh")
    monkeypatch.setattr(P, "capture_sources", forbidden)
    assert P.publish_after_refresh(info, now=NOW)["reason"] == "owned_refresh_failed"


@pytest.mark.parametrize("publication_status,expected", [
    ("published", "ok"), ("unchanged", "ok"),
    ("refused", "error"), ("effect_unknown", "error"),
])
def test_existing_refresh_owner_passes_result_once_and_records_publication_outcome(
        monkeypatch, publication_status, expected):
    from app import scheduler
    from data_layer import macro_refresh
    events = []
    info = {"refresh_mode": "external", "refreshed_to": None, "stale": False}
    def refresh():
        events.append("refresh")
        return info
    def publish(received):
        assert received is info
        events.append("publish")
        return {"status": publication_status, "seq": 1, "reason": "synthetic"}
    monkeypatch.setattr(macro_refresh, "refresh_and_check", refresh)
    monkeypatch.setattr(P, "publish_after_refresh", publish)
    monkeypatch.setattr(scheduler, "_ledger_start",
                        lambda *a, **k: events.append("start") or "synthetic-handle")
    monkeypatch.setattr(scheduler, "_ledger_end",
                        lambda handle, status: events.append((handle, status)))
    scheduler._macro_refresh_job()
    assert events == ["start", "refresh", "publish", ("synthetic-handle", expected)]


def test_current_consumer_binds_actual_view_bytes_even_when_clocks_are_reused(monkeypatch):
    from brain import pm_conviction
    P.publish_capture(_capture(), now=NOW)
    monkeypatch.setattr(pm_conviction, "_MARKET_VIEW_PATH", MV._LATEST_PATH)
    projection = pm_conviction._market_view_enrichment(pm_conviction._read_market_view(now=NOW))
    expected = projection["publication"]
    assert expected["artifact_sha256"] == P._sha(MV._LATEST_PATH.read_bytes())
    accepted = DC.prompt_summary(now=NOW, expected_publication=expected)
    assert accepted["serving_freshness"]["current_assessment_available"] is True
    changed = _latest()
    changed["unrelated_note"] = "different bytes with identical asof, built_at and sequence"
    MV._LATEST_PATH.write_bytes(P._json_bytes(changed))
    refused = DC.prompt_summary(now=NOW, expected_publication=expected)
    assert refused["serving_freshness"]["current_assessment_available"] is False
    assert "consumer_publication_bytes_changed_during_read" in refused["serving_freshness"]["reasons"]


def test_compatibility_latest_cannot_supersede_committed_typed_reference():
    P.publish_capture(_capture(), now=NOW)
    selected = DC.latest()
    DC._LATEST_PATH.write_text(json.dumps({"seq": 999, "governor": {"confirmed": True}}))
    assert DC.latest() == selected
    current = DC.prompt_summary(now=NOW)
    assert current["publication"]["seq"] == 1
    assert current["serving_freshness"]["current_assessment_available"] is True


def test_delayed_capture_cannot_replace_a_newer_committed_observation():
    earlier = _capture()
    newer_sources = _sources()
    newer_sources["regime"]["risk_radar"]["top_score"] = 81
    newer = _capture(newer_sources, revision="b" * 40)
    newer["captured_at"] = (NOW + timedelta(minutes=1)).isoformat()
    P.publish_capture(newer, now=NOW + timedelta(minutes=1))
    committed = MV._LATEST_PATH.read_bytes()
    typed = DC.for_publication(_latest())
    with pytest.raises(P.PublicationRefused, match="capture_precedes_committed_observation"):
        P.publish_capture(earlier, now=NOW + timedelta(minutes=2))
    assert MV._LATEST_PATH.read_bytes() == committed
    assert DC.for_publication(_latest()) == typed
    assert _latest()["seq"] == 1


@pytest.mark.parametrize("captured_at", [None, "bad-clock", "2026-10-21T05:00:00",
                                         "2026-10-22T05:00:00+00:00"])
def test_invalid_capture_clock_cannot_establish_new_observation(captured_at):
    capture = _capture()
    capture["captured_at"] = captured_at
    with pytest.raises(P.PublicationRefused, match="capture_clock_invalid"):
        P.publish_capture(capture, now=NOW)
    assert not MV._LATEST_PATH.exists()


def test_distinct_capture_with_equal_clock_has_no_proven_order():
    P.publish_capture(_capture(), now=NOW)
    committed = MV._LATEST_PATH.read_bytes()
    changed = _sources()
    changed["regime"]["risk_radar"]["top_score"] = 81
    with pytest.raises(P.PublicationRefused, match="capture_precedes_committed_observation"):
        P.publish_capture(_capture(changed), now=NOW)
    assert MV._LATEST_PATH.read_bytes() == committed



def test_first_publication_makes_new_directory_links_durable_before_commit(tmp_path, monkeypatch):
    mv_dir = tmp_path / "new-view-parent" / "new-data" / "market_view"
    dc_dir = tmp_path / "new-typed-parent" / "new-data" / "decision_context"
    monkeypatch.setattr(MV, "_ARTIFACT_DIR", mv_dir)
    monkeypatch.setattr(MV, "_LATEST_PATH", mv_dir / "latest.json")
    monkeypatch.setattr(DC, "_ARTIFACT_DIR", dc_dir)
    monkeypatch.setattr(DC, "_LATEST_PATH", dc_dir / "latest.json")
    monkeypatch.setattr(DC, "_MARKET_VIEW_PATH", mv_dir / "latest.json")
    synced = set()
    real_sync = P._sync_directory
    real_replace = P._atomic_replace
    def sync(path):
        real_sync(path)
        synced.add(path)
    def commit(path, payload):
        if path == MV._LATEST_PATH:
            for directory in (mv_dir, dc_dir):
                assert directory in synced
                assert directory.parent in synced
                assert directory.parent.parent in synced
                assert tmp_path in synced
        real_replace(path, payload)
    monkeypatch.setattr(P, "_sync_directory", sync)
    monkeypatch.setattr(P, "_atomic_replace", commit)
    assert P.publish_capture(_capture(), now=NOW)["status"] == "published"


def test_parent_directory_sync_failure_cannot_acknowledge_first_publication(tmp_path, monkeypatch):
    real_sync = P._sync_directory
    def fail_parent(path):
        if path == tmp_path:
            raise OSError("synthetic parent-link durability failure")
        real_sync(path)
    monkeypatch.setattr(P, "_sync_directory", fail_parent)
    with pytest.raises(OSError, match="parent-link durability"):
        P.publish_capture(_capture(), now=NOW)
    assert not MV._LATEST_PATH.exists()



def _fresh_mixed_market_dates():
    sources = _sources()
    sources["regime"]["risk_radar"]["state"] = "calm"
    sources["regime"]["mtf_signals"] = {
        "asof": "2026-10-20", "signals": [{"state": "long-bias"}],
    }
    return sources


def test_typed_voter_ineligible_relative_to_regime_cannot_publish_confirmation():
    capture = _capture(_fresh_mixed_market_dates())
    with pytest.raises(P.PublicationRefused, match="typed_governor_membership_inconsistent"):
        P.publish_capture(capture, now=NOW)
    assert not MV._LATEST_PATH.exists()


def test_legacy_pair_cannot_confirm_when_typed_voter_is_not_eligible():
    sources = _fresh_mixed_market_dates()
    view = MV.captured_view(sources, now=NOW, prev_view=None, seq=1)
    view = json.loads(P._json_bytes(view))
    typed = DC.assemble(sources["regime"], view, neural_web={}, seq=1,
                        built_at=view["built_at"])
    assert view["label_vs_planes"]["confirmed"] is True
    assert view["net_posture_tilt"]["n_validated"] == 3
    mtf = next(row for row in typed["signals"] if row["name"] == "mtf_signals")
    assert mtf["allowed_effect"] == "shrink_only"
    assert mtf["freshness"]["stale"] is True
    for path, value in ((MV._LATEST_PATH, view), (DC._LATEST_PATH, typed)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(P._json_bytes(value))
    result = DC.prompt_summary(now=NOW)
    assert result["serving_freshness"]["current_assessment_available"] is False
    assert "typed_governor_membership_inconsistent" in result["serving_freshness"]["reasons"]
    assert result["governor"]["confirmed"] is False



def test_retry_synchronizes_complete_orphan_file_before_publication(monkeypatch):
    import os
    import stat
    real_sync = P.os.fsync
    orphan_inode = []
    def fail_first_file(descriptor):
        info = os.fstat(descriptor)
        if stat.S_ISREG(info.st_mode) and not orphan_inode:
            orphan_inode.append((info.st_dev, info.st_ino))
            raise OSError("synthetic interrupted immutable-file sync")
        real_sync(descriptor)
    monkeypatch.setattr(P.os, "fsync", fail_first_file)
    with pytest.raises(OSError, match="interrupted immutable-file"):
        P.publish_capture(_capture(), now=NOW)
    assert not MV._LATEST_PATH.exists()
    assert len(list(DC._ARTIFACT_DIR.glob("*.json"))) == 1
    synced_files = set()
    def record_sync(descriptor):
        info = os.fstat(descriptor)
        real_sync(descriptor)
        if stat.S_ISREG(info.st_mode):
            synced_files.add((info.st_dev, info.st_ino))
    real_replace = P._atomic_replace
    def commit(path, payload):
        if path == MV._LATEST_PATH:
            assert orphan_inode[0] in synced_files
        real_replace(path, payload)
    monkeypatch.setattr(P.os, "fsync", record_sync)
    monkeypatch.setattr(P, "_atomic_replace", commit)
    assert P.publish_capture(_capture(), now=NOW)["status"] == "published"
