"""Exact-M2 guard reconciliation candidate, pure/source-only.

Never write the active M2 guard here. The incumbent provider-policy owner must
review and deploy any change through its existing authority and readback.
"""
from __future__ import annotations

from hashlib import sha256

EXPECTED_PREIMAGE = "d1fabbcb39bfd7bfd1552d79acc5ada346f0ac47c887802fb6b021afe84a3840"
EXPECTED_CANDIDATE = "9c70114886c6ce80fdd1916ece254e6e3fc018d9dbfbd220a191f395f29a0633"
ANCHOR = '    if tool not in ("Agent", "Task"):\n        return\n    model = str(ti.get("model") or "").strip()\n'
INSERT = (
    '    # Cursor delivers a different Task hook shape from Claude. A Cursor env\n'
    '    # variable alone must NEVER select this branch (Claude can inherit it).\n'
    '    if tool == "Task" and "cursor_version" in payload:\n'
    '        project_dir = os.environ.get("CURSOR_PROJECT_DIR", "")\n'
    '        in_scope = is_mastermind_scope(payload) or (\n'
    '            bool(project_dir) and os.path.isabs(project_dir)\n'
    '            and is_mastermind_scope({"cwd": project_dir})\n'
    '        )\n'
    '        if in_scope:\n'
    '            try:\n'
    '                from cursor_native_child_policy import evaluate_cursor_task\n'
    '            except ImportError:\n'
    '                deny("Mastermind Cursor Task policy companion unavailable")\n'
    '            observed = evaluate_cursor_task(payload, os.environ)\n'
    '            if not observed.admitted:\n'
    '                deny("Mastermind Cursor Task refused: " + observed.code)\n'
    '            allow_context(\n'
    '                "Reviewed read-only Cursor role declaration: "\n'
    '                + str(observed.declared_model)\n'
    '                + ". Actual model selection UNVERIFIED. No Fabric worker authority."\n'
    '            )\n'
    '            return\n'
    '\n'
)


class StaleHostGuardError(ValueError):
    pass


def compose_installed_guard(original: bytes) -> bytes:
    """Return reviewed proposal bytes; performs no filesystem modifications."""
    if sha256(original).hexdigest() != EXPECTED_PREIMAGE:
        raise StaleHostGuardError("installed M2 guard preimage changed; refuse overlay")
    text = original.decode("utf-8")
    if text.count(ANCHOR) != 1:
        raise StaleHostGuardError("M2 guard Cursor insertion anchor drifted")
    candidate = (text.replace(ANCHOR, INSERT + ANCHOR)).encode("utf-8")
    if sha256(candidate).hexdigest() != EXPECTED_CANDIDATE:
        raise StaleHostGuardError("M2 host overlay digest mismatch")
    return candidate
