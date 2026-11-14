"""BR-COMPATFIX MED-2: the runbook carries a truthful rollback window table.

The BR-COMPAT review (MED-2) showed the rollback as written — a bare pin
(``rollback OLD = 5aa30969…``) with no procedure — strands every profile
reloaded at step 3: after the reload the extensions present the NEW digest,
and nothing proved the OLD host's single-digest-strict admission accepts it.
A truthful rollback names the reverse reload (the old loaded folders survive
untouched, so the bytes exist to reload from) and states, per step: what is
live, how to undo it, and until when that undo is the right one.

Fails first on 72de0bab3: that runbook has per-step rollback prose but no
rollback window table.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "integrations/hermes_harness" / "mcp_bridge_install.md"


def _table_rows(section: str):
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell != ""):
            continue
        rows.append(cells)
    return rows


def test_runbook_has_a_per_step_rollback_window_table():
    text = RUNBOOK.read_text()
    assert "## Rollback window" in text, \
        "the runbook must carry a 'Rollback window' section (MED-2)"
    section = text.split("## Rollback window", 1)[1]
    rows = _table_rows(section)
    assert rows, "the rollback window section carries no table"
    header, *body = rows
    assert [cell.lower() for cell in header] == ["step", "what is live", "how to undo", "until when"], \
        f"unexpected rollback table header: {header}"
    assert len(body) >= 5, "the table must cover every install step"
    steps = [row[0] for row in body]
    for number in ("1", "2", "3", "4", "5"):
        assert any(cell.startswith(number) for cell in steps), \
            f"rollback table has no row for step {number}"
    for row in body:
        assert len(row) == 4 and all(cell for cell in row), \
            f"every rollback row needs four non-empty cells: {row}"


def test_rollback_rows_are_truthful_about_the_reverse_reload_and_the_backups():
    text = RUNBOOK.read_text()
    section = text.split("## Rollback window", 1)[1]
    _, *body = _table_rows(section)
    rows = {row[0][0]: row for row in body}
    # Step 2's undo is the installer's own backup mechanism, not a rerun.
    undo2 = rows["2"][2].lower()
    assert ".previous" in undo2, "step 2's undo must restore the installer's .previous backups"
    # Step 3's undo names the reverse reload from the untouched old folder —
    # the exact gap MED-2 found (a pin-only rollback strands reloaded profiles).
    undo3 = rows["3"][2].lower()
    assert "load unpacked" in undo3, "step 3's undo must name the reverse Load unpacked"
    # BR2's untouched old staging folder is b640dec1's (release 3's was 0.5.0).
    assert "0.6.0-b640dec1" in undo3, "step 3's undo must name the untouched old staging folder"
    # Step 4's undo is the same atomic repoint back; running sessions never need it.
    undo4 = rows["4"][2].lower()
    assert ("repoint" in undo4 or "switch" in undo4) and "old" in undo4, \
        "step 4's undo must name the atomic repoint back to the old pin"
