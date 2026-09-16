import hashlib
import json
import os
from pathlib import Path

import pytest

from portfolio import decision_snapshot as snapshots
from portfolio import decision_snapshot_sources as sources
from scripts import portfolio_decision_snapshot as cli

_RUNBOOK_PATH = Path(__file__).resolve().parent.parent / "docs" / "runbooks" / "portfolio-v3-decision-snapshot.md"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _tree_fingerprint(root):
    """Map every path under ``root`` to a (kind, content-or-target) tuple.

    Unlike a bare ``*.json`` count, this catches a new mutable file of any
    name (``latest.json``, an index, a cache), a deleted file, changed bytes
    in an existing file, and a directory/symlink type change.
    """
    fingerprint = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            fingerprint[rel] = ("symlink", os.readlink(path))
        elif path.is_dir():
            fingerprint[rel] = ("dir", None)
        elif path.is_file():
            fingerprint[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            fingerprint[rel] = ("other", None)
    return fingerprint

@pytest.fixture
def snapshot_root(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    macro = tmp_path / "macro"
    storage = tmp_path / "storage"
    repo.mkdir()
    macro.mkdir()
    storage.mkdir()
    monkeypatch.setattr(sources, "_ROOT", repo)
    monkeypatch.setattr(sources, "_V", macro)
    monkeypatch.setattr(snapshots, "_ROOT", storage)
    return storage


def _forbid_create_snapshot(monkeypatch):
    monkeypatch.setattr(
        cli.decision_snapshot,
        "create_snapshot",
        lambda *a, **k: pytest.fail("must not run"),
    )


def _fake_sealed_snapshot(**overrides):
    base = {
        "schema": "mastermind.portfolio_decision_snapshot.v1",
        "book": "autonomous",
        "snapshot_id": "sha256:" + "b" * 64,
        "decision_cutoff": "2026-09-15T20:00:00Z",
        "recorded_at": "2026-09-15T20:01:00Z",
        "state": "PARTIAL",
        "coverage_state": "PARTIAL",
        "summary": {
            "sources_total": 1,
            "sources_available": 0,
            "domains_complete": 0,
            "domains_partial": 1,
            "domains_blocked": 0,
        },
        "source_generation_set": [],
        "sources": [{"source_id": "fake"}],
        "sections": {
            "risk_truth": {
                "schema": "mastermind.portfolio_snapshot_section.v1",
                "section_id": "risk_truth",
                "coverage_state": "PARTIAL",
                "source_ids": ["fake"],
                "rows_total": 1,
                "rows_returned": 1,
                "omitted_rows": 0,
                "rows": [{"value": 1}],
                "gaps": [],
            }
        },
        "gaps": [],
        "correction": {"status": "ORIGINAL", "same_cutoff_prior_snapshot_ids": []},
        "authority": {
            "write_permitted": False,
            "execution_authority": False,
            "numeric_target_authority": False,
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# compose: explicit clocks, single writer, bounded receipt
# ---------------------------------------------------------------------------

def test_compose_requires_both_explicit_clocks(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.decision_snapshot,
        "create_snapshot",
        lambda *a, **k: pytest.fail("must not run"),
    )
    assert cli.main(["compose", "--book", "autonomous"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "invalid_request"
    assert "decision-cutoff" in error["error"]
    assert "recorded-at" in error["error"]


def test_compose_missing_recorded_at_only_still_reports_it(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)
    rc = cli.main([
        "compose", "--book", "autonomous",
        "--decision-cutoff", "2026-09-15T20:00:00Z",
    ])
    assert rc == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "invalid_request"
    assert "recorded-at" in error["error"]


def test_compose_calls_writer_once_and_prints_bounded_receipt(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        cli.decision_snapshot,
        "create_snapshot",
        lambda book, decision_cutoff, recorded_at: seen.append(
            (book, decision_cutoff, recorded_at)
        ) or {
            "snapshot_id": "sha256:" + "a" * 64,
            "state": "PARTIAL",
            "coverage_state": "PARTIAL",
        },
    )
    rc = cli.main([
        "compose",
        "--book", "autonomous",
        "--decision-cutoff", "2026-09-15T20:00:00Z",
        "--recorded-at", "2026-09-15T20:01:00Z",
    ])
    assert rc == 0
    assert seen == [(
        "autonomous",
        "2026-09-15T20:00:00Z",
        "2026-09-15T20:01:00Z",
    )]
    assert json.loads(capsys.readouterr().out)["snapshot_id"] == (
        "sha256:" + "a" * 64
    )


def test_compose_receipt_is_bounded_and_excludes_snapshot_bulk(monkeypatch, capsys):
    full_snapshot = _fake_sealed_snapshot()
    full_snapshot["created"] = True
    monkeypatch.setattr(
        cli.decision_snapshot, "create_snapshot", lambda *a, **k: full_snapshot,
    )
    rc = cli.main([
        "compose", "--book", "autonomous",
        "--decision-cutoff", "2026-09-15T20:00:00Z",
        "--recorded-at", "2026-09-15T20:01:00Z",
    ])
    assert rc == 0
    receipt = json.loads(capsys.readouterr().out)
    assert set(receipt.keys()) == {
        "schema", "book", "snapshot_id", "state", "coverage_state",
        "write_root", "write_permitted_outside_shadow", "execution_authority",
    }
    assert receipt["write_root"] == "data/shadow/decision_snapshots/autonomous"
    assert receipt["write_permitted_outside_shadow"] is False
    assert receipt["execution_authority"] is False
    assert "sources" not in receipt
    assert "sections" not in receipt
    assert "gaps" not in receipt


# ---------------------------------------------------------------------------
# status: read-only, compact manifest, typed NO_SNAPSHOT
# ---------------------------------------------------------------------------

def test_status_no_snapshot_prints_typed_object_without_writing(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)
    monkeypatch.setattr(cli.decision_snapshot, "latest_snapshot", lambda book: None)
    rc = cli.main(["status", "--book", "autonomous"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "NO_SNAPSHOT"
    assert out["book"] == "autonomous"


def test_status_prints_compact_manifest_without_bulk_fields(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)
    fake = _fake_sealed_snapshot()
    monkeypatch.setattr(cli.decision_snapshot, "latest_snapshot", lambda book: fake)
    rc = cli.main(["status", "--book", "autonomous"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "OK"
    manifest = out["manifest"]
    assert manifest["snapshot_id"] == fake["snapshot_id"]
    assert manifest["state"] == "PARTIAL"
    for bulky in ("sources", "sections", "gaps", "source_generation_set"):
        assert bulky not in manifest


# ---------------------------------------------------------------------------
# show: read-only, compact manifest by default, bounded section page
# ---------------------------------------------------------------------------

def test_show_no_snapshot_prints_typed_object_without_writing(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)
    monkeypatch.setattr(cli.decision_snapshot, "latest_snapshot", lambda book: None)
    rc = cli.main(["show", "--book", "autonomous"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "NO_SNAPSHOT"


def test_show_without_section_prints_compact_manifest(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)
    fake = _fake_sealed_snapshot()
    monkeypatch.setattr(cli.decision_snapshot, "latest_snapshot", lambda book: fake)
    rc = cli.main(["show", "--book", "autonomous"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    manifest = out["manifest"]
    assert manifest["snapshot_id"] == fake["snapshot_id"]
    for bulky in ("sources", "sections", "gaps", "source_generation_set"):
        assert bulky not in manifest


def test_show_with_explicit_snapshot_id_uses_load_snapshot(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)
    fake = _fake_sealed_snapshot()
    seen = []
    monkeypatch.setattr(
        cli.decision_snapshot,
        "load_snapshot",
        lambda book, snapshot_id: seen.append((book, snapshot_id)) or fake,
    )
    monkeypatch.setattr(
        cli.decision_snapshot,
        "latest_snapshot",
        lambda book: pytest.fail("must not run when --snapshot-id is given"),
    )
    rc = cli.main(["show", "--book", "autonomous", "--snapshot-id", fake["snapshot_id"]])
    assert rc == 0
    assert seen == [("autonomous", fake["snapshot_id"])]


def test_show_with_section_calls_accepted_section_page(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)
    fake = _fake_sealed_snapshot()
    monkeypatch.setattr(cli.decision_snapshot, "latest_snapshot", lambda book: fake)
    seen = []

    def fake_section_page(snapshot, section_id, *, offset, limit):
        seen.append((snapshot["snapshot_id"], section_id, offset, limit))
        return {
            "schema": "mastermind.portfolio_snapshot_section.v1",
            "section_id": section_id,
            "coverage_state": "PARTIAL",
            "source_ids": [],
            "rows_total": 0,
            "rows_returned": 0,
            "omitted_rows": 0,
            "gaps": [],
            "rows": [],
            "next_offset": None,
        }

    monkeypatch.setattr(cli.decision_snapshot, "section_page", fake_section_page)
    rc = cli.main([
        "show", "--book", "autonomous",
        "--section", "risk_truth", "--offset", "3", "--limit", "7",
    ])
    assert rc == 0
    assert seen == [(fake["snapshot_id"], "risk_truth", 3, 7)]
    out = json.loads(capsys.readouterr().out)
    assert out["section"]["section_id"] == "risk_truth"
    assert out["snapshot_id"] == fake["snapshot_id"]


def test_show_not_found_snapshot_id_is_typed_error_without_leak(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)

    def raise_not_found(book, snapshot_id):
        raise cli.decision_snapshot.SnapshotNotFound(
            "/very/secret/internal/path snapshot missing"
        )

    monkeypatch.setattr(cli.decision_snapshot, "load_snapshot", raise_not_found)
    rc = cli.main(["show", "--book", "autonomous", "--snapshot-id", "sha256:" + "c" * 64])
    assert rc == 1
    err_text = capsys.readouterr().err
    error = json.loads(err_text)
    assert error["status"] == "not_found"
    assert "/very/secret/internal/path" not in err_text


def test_show_corrupt_snapshot_is_typed_error_without_leak(monkeypatch, capsys):
    _forbid_create_snapshot(monkeypatch)

    def raise_corrupt(book, snapshot_id):
        raise cli.decision_snapshot.SnapshotCorrupt(
            "/very/secret/internal/path is not a regular file"
        )

    monkeypatch.setattr(cli.decision_snapshot, "load_snapshot", raise_corrupt)
    rc = cli.main(["show", "--book", "autonomous", "--snapshot-id", "sha256:" + "d" * 64])
    assert rc == 1
    err_text = capsys.readouterr().err
    error = json.loads(err_text)
    assert error["status"] == "corrupt_snapshot"
    assert "/very/secret/internal/path" not in err_text


# ---------------------------------------------------------------------------
# Closed vocabulary: book, no path/root/url/output overrides, parser errors
# ---------------------------------------------------------------------------

def test_cli_has_no_path_root_url_or_output_override():
    parser = cli.build_parser()
    help_text = parser.format_help()
    for forbidden in ("--path", "--root", "--url", "--output"):
        assert forbidden not in help_text


@pytest.mark.parametrize("command", ["compose", "status", "show"])
def test_unsupported_book_is_rejected_before_any_call(monkeypatch, capsys, command):
    _forbid_create_snapshot(monkeypatch)
    monkeypatch.setattr(
        cli.decision_snapshot, "latest_snapshot",
        lambda book: pytest.fail("must not run"),
    )
    monkeypatch.setattr(
        cli.decision_snapshot, "load_snapshot",
        lambda book, snapshot_id: pytest.fail("must not run"),
    )
    argv = [command, "--book", "NOT_A_BOOK"]
    if command == "compose":
        argv += ["--decision-cutoff", "2026-09-15T20:00:00Z", "--recorded-at", "2026-09-15T20:01:00Z"]
    rc = cli.main(argv)
    assert rc == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "invalid_request"


def test_missing_command_is_closed_json_parser_error(capsys):
    rc = cli.main([])
    assert rc == 2
    err_text = capsys.readouterr().err
    error = json.loads(err_text)
    assert error["status"] == "invalid_request"
    assert "usage:" not in err_text.lower().split("\n")[0]


def test_unknown_command_is_closed_json_parser_error(capsys):
    rc = cli.main(["bogus"])
    assert rc == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "invalid_request"


def test_show_bad_offset_type_is_closed_json_parser_error(capsys):
    rc = cli.main(["show", "--book", "autonomous", "--section", "risk_truth", "--offset", "nope"])
    assert rc == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "invalid_request"


# ---------------------------------------------------------------------------
# Real round trip against the accepted decision_snapshot/sources modules
# ---------------------------------------------------------------------------

def test_compose_then_status_then_show_round_trip(snapshot_root, capsys):
    rc = cli.main([
        "compose", "--book", "autonomous",
        "--decision-cutoff", "2026-09-15T20:00:00Z",
        "--recorded-at", "2026-09-15T20:01:00Z",
    ])
    assert rc == 0
    compose_out = json.loads(capsys.readouterr().out)
    snapshot_id = compose_out["snapshot_id"]
    assert len(list(snapshots.snapshot_dir("autonomous").glob("*.json"))) == 1

    rc = cli.main(["compose", "--book", "autonomous",
                    "--decision-cutoff", "2026-09-15T20:00:00Z",
                    "--recorded-at", "2026-09-15T20:05:00Z"])
    assert rc == 0
    second_out = json.loads(capsys.readouterr().out)
    assert second_out["snapshot_id"] == snapshot_id
    assert len(list(snapshots.snapshot_dir("autonomous").glob("*.json"))) == 1

    # Captured after both composes, before any read-only command: the strengthened
    # discriminator for Important-2 (status/show must not touch this tree at all).
    tree_before_reads = _tree_fingerprint(snapshot_root)

    rc = cli.main(["status", "--book", "autonomous"])
    assert rc == 0
    status_out = json.loads(capsys.readouterr().out)
    assert status_out["status"] == "OK"
    assert status_out["manifest"]["snapshot_id"] == snapshot_id
    assert _tree_fingerprint(snapshot_root) == tree_before_reads

    rc = cli.main(["show", "--book", "autonomous"])
    assert rc == 0
    show_out = json.loads(capsys.readouterr().out)
    assert show_out["manifest"]["snapshot_id"] == snapshot_id
    assert _tree_fingerprint(snapshot_root) == tree_before_reads

    rc = cli.main([
        "show", "--book", "autonomous",
        "--section", "risk_truth", "--offset", "0", "--limit", "10",
    ])
    assert rc == 0
    section_out = json.loads(capsys.readouterr().out)
    assert section_out["snapshot_id"] == snapshot_id
    assert section_out["section"]["section_id"] == "risk_truth"
    assert isinstance(section_out["section"]["rows"], list)
    assert _tree_fingerprint(snapshot_root) == tree_before_reads


# ---------------------------------------------------------------------------
# Runbook content locks: corrupt-sibling reconciliation must stay terminal,
# and the bounded scan's truncation limit must stay non-probative.
# ---------------------------------------------------------------------------

def _runbook_normalized_text() -> str:
    """Whitespace-collapsed, lowercased runbook text, so line-wrap and case never
    affect these content-lock substring checks."""
    return " ".join(_RUNBOOK_PATH.read_text().split()).lower()


def test_runbook_corrupt_sibling_procedure_is_terminal_not_loopback():
    text = _runbook_normalized_text()
    assert "the same as step 2" not in text
    assert "reconcile which cutoff the corrupt file was for before deciding" not in text
    for required in (
        "do not loop back to step 2",
        "fail closed together",
        "escalate to the immutable snapshot-store owner",
        "independently authorized store-repair operation",
        "raw/unverified json bytes directly",
        "delete, quarantine, or rewrite it",
        "re-run `compose`",
        "move the operation to a different carrier or session",
        "newer, unrelated snapshot",
    ):
        assert required in text


def test_runbook_truncated_scan_is_documented_as_non_probative():
    text = _runbook_normalized_text()
    assert "source generation set — never before" not in text
    for required in (
        "hard clamp, not a page size",
        "non-probative",
        "never expose a source generation set",
    ):
        assert required in text
