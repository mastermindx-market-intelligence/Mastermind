"""Truthful reverse-publication behavior for the Macro dashboard snapshot."""
from __future__ import annotations


def test_default_publish_refuses_a_missing_macro_owner_checkout(monkeypatch) -> None:
    """The authoritative VPS must not create a local vendor tree and call it published."""
    from scripts import export_macro_snapshot as exporter

    monkeypatch.setattr(exporter, "_macro_root", lambda: None)

    writes: list[object] = []

    def _record_write(*args, **kwargs):
        writes.append((args, kwargs))
        return exporter._ROOT / "vendor" / "macro" / "site" / "mastermind" / "mastermind_snapshot.json"

    monkeypatch.setattr(exporter.macro_snapshot, "write", _record_write)

    assert exporter.run() is None
    assert writes == [], "a missing owner checkout must fail before creating local-only bytes"


def test_scheduler_records_error_when_snapshot_was_not_published(monkeypatch) -> None:
    """A no-publication result must be visible in /api/scheduler, never reported as ok."""
    from app import scheduler
    from scripts import export_macro_snapshot as exporter

    statuses: list[str] = []
    monkeypatch.setattr(exporter, "run", lambda: None)
    monkeypatch.setattr(scheduler, "_ledger_start", lambda *args, **kwargs: object())
    monkeypatch.setattr(scheduler, "_ledger_end", lambda handle, status: statuses.append(status))

    scheduler._snapshot_job()

    assert statuses == ["error"]
