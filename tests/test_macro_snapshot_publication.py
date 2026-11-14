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


def test_mandatory_stage_failure_stops_publication_at_every_entrypoint(tmp_path, monkeypatch):
    from subprocess import CompletedProcess

    from app import scheduler
    from brain import cost_guard
    from scripts import export_macro_snapshot as exporter

    commands = []
    def git(root, *args):
        commands.append(args)
        status = 1 if args == ("add", "-f", exporter._REL_PATH) else 0
        return CompletedProcess(args, status, stdout="main\n", stderr="")

    monkeypatch.setattr(exporter, "_git", git)
    monkeypatch.setattr(exporter, "_macro_root", lambda: tmp_path)
    snapshot = tmp_path / exporter._REL_PATH
    monkeypatch.setattr(exporter.macro_snapshot, "write", lambda dest: snapshot)
    monkeypatch.setattr(cost_guard, "write_cost_summary", lambda dest: None)
    monkeypatch.setattr(exporter, "_write_key_events", lambda root: None)
    monkeypatch.setattr(exporter, "_write_pool_status", lambda root: None)
    statuses = []
    monkeypatch.setattr(scheduler, "_ledger_start", lambda *args, **kwargs: object())
    monkeypatch.setattr(scheduler, "_ledger_end", lambda handle, status: statuses.append(status))

    assert exporter._commit_and_push(tmp_path) is False
    assert exporter.run() is None
    assert exporter.main([]) == 1
    scheduler._snapshot_job()
    assert statuses == ["error"]
    assert commands == [("rev-parse", "--abbrev-ref", "HEAD"),
                        ("add", "-f", exporter._REL_PATH)] * 4

    commands.clear()
    assert exporter.run(no_push=True) == snapshot
    assert exporter.main(["--dest", str(tmp_path / "preview")]) == 0
    assert commands == []


def test_clean_and_changed_snapshot_can_publish(tmp_path, monkeypatch):
    from subprocess import CompletedProcess

    from scripts import export_macro_snapshot as exporter

    monkeypatch.setattr(exporter.macro_snapshot, "build", lambda: {"generated_at": "test"})
    for changed in (False, True):
        calls = []

        def git(root, *args):
            calls.append(args)
            rc = int(changed) if args == ("diff", "--cached", "--quiet") else 0
            return CompletedProcess(args, rc, stdout="main\n", stderr="")

        monkeypatch.setattr(exporter, "_git", git)
        assert exporter._commit_and_push(tmp_path) is True
        assert calls[:3] == [("rev-parse", "--abbrev-ref", "HEAD"),
                             ("add", "-f", exporter._REL_PATH),
                             ("diff", "--cached", "--quiet")]
        if changed:
            assert calls[-1] == ("push",)
        else:
            assert len(calls) == 3
