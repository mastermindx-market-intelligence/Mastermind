"""r13 documented limits — REVIEW9 re-check #9 MINORs #1 and #2, pinned.

These tests PIN CURRENT BEHAVIOUR (documented limits of guard r13), not a
desired property: integrations/mmos/REVIEW9_GUARD_R13_OPUS_20261110.md
ACCEPTED r13 under these limits and the guard module docstring documents
them ("Documented limits (r13, REVIEW9 re-check #9)"). An assertion here
moves only together with an accepted guard change that re-documents the
limit; never weaken one to make a new guard revision pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.executive_os import provider_orchestrator_guard as guard
from tests.test_provider_orchestrator_policy import (
    _r11_sealed_shells,
    _r7_both,
    shared_placement,
)

# --- REVIEW9 MINOR #1: env -S decodes its own escapes -------------------------

#: macOS ``env -S`` decodes its ``-S`` value itself (backslash-backslash to
#: one backslash, backslash-n to a newline), so a value holding ``po`` +
#: three literal backslashes + ``nol run glm a /tmp glm-5.3`` hands bash the
#: body ``po\⏎ol`` and bash joins the continuation into ``pool`` (a bare
#: launch of the wrapper, marker ``pool-``). The RAW command bytes hold no
#: newline byte, no shell construct and no literal wrapper name, so the
#: armed parse never runs — the same arbitrary-process class as the pinned
#: printf-computed name. The double-quoted variant needs FIVE literal
#: backslashes: the outer double quotes collapse backslash-backslash to one
#: backslash before env -S ever sees the value (sealed zsh AND bash launch
#: the fake wrapper for exactly these two spellings; three backslashes
#: double-quoted does NOT launch — measured on this machine).
_R13_ENV_S_LIMIT_SHAPES = (
    "env -S 'bash -c po" + "\\" * 3 + "nol run glm a /tmp glm-5.3'",
    'env -S "bash -c po' + "\\" * 5 + 'nol run glm a /tmp glm-5.3"',
)


def test_r13_limit_env_s_escape_decoding_is_pinned(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PINS A KNOWN LIMIT (REVIEW9 #1), not a desired property: sealed zsh
    AND bash really launch the (fake) wrapper through env -S escape decoding
    while an armed session allows the command unjudged, gate unreached."""
    (tmp_path / "sealed").mkdir()
    run = _r11_sealed_shells(tmp_path / "sealed")
    for command in _R13_ENV_S_LIMIT_SHAPES:
        # (i) the limit is real: each sealed shell launches the fake wrapper
        for shell in ("zsh", "bash"):
            markers = run(command, shell)
            assert markers, (command, shell)
            assert any(name.startswith("pool") for name in markers), (
                command, shell, markers
            )
        # (ii) armed bound AND unbound: allow, the gate is never reached
        (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
            guard, shared_placement, monkeypatch, tmp_path, capsys, command
        )
        assert (bound, bound_gate) == ("allow", False), (command, bound_reason)
        assert (nobind, nobind_gate) == ("allow", False), (command, nobind_reason)
        # (iii) construct-free and literally unnamed on the raw bytes
        assert guard.r12_constructs(command) == [], command
        assert not guard.r12_armed_in_scope(command), command
    # (iv) the guard already knows env -S is not a transparent prefix: the
    # NAMED form is refused with R6_PREFIX_FORM, bound and unbound.
    named = "env -S 'pool run glm a /tmp glm-5.3'"
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, named
    )
    assert (bound, nobind, bound_gate, nobind_gate) == ("deny", "deny", False, False), (
        bound_reason, nobind_reason
    )
    assert "R6_PREFIX_FORM" in bound_reason, bound_reason
    assert "R6_PREFIX_FORM" in nobind_reason, nobind_reason


# --- REVIEW9 MINOR #2: escaped quote before a newline is over-refused ---------

#: The six REVIEW9 §C shapes (its own byte spellings; every ``\\`` pair below
#: is one backslash in the command, every ``\\n`` a real newline byte). None
#: is a launch; r12 allowed all six and r13 refuses them structurally — the
#: accepted availability cost, documented in the guard module docstring.
_R13_OVER_REFUSAL_SHAPES = (
    # an escaped quote immediately before a newline inside a multi-line
    # double-quoted argument; the head is not an admitted read form
    # (the standalone "\n" pieces below are REAL newline bytes; each \\" is
    # one backslash + quote inside the double-quoted body)
    'gh pr create --title t --body "Fixes \\"x\\"' + "\n\n" + 'More text"',
    'python3 tools/report.py --msg "He said \\"hi\\"' + "\n" + 'next line"',
    # a quoted trailing backslash (printf format / single-quoted path) and a
    # double-quoted trailing escaped backslash, each immediately before a
    # newline (REVIEW9 §C "the pinned shape (variant)")
    "printf '%s\\\\n' 'C:\\\\dir\\\\'\nls",
    'echo "C:\\\\temp\\\\"\necho b',
    # the already-accepted pinned over-refusal (policy module), for completeness
    "echo 'a\\'\necho b",
    # an in-scope two-command list whose first command ends in \"…\"
    'git commit -m "say \\"hi\\""\ngit log -1',
)


def test_r13_limit_escaped_quote_before_newline_over_refusal_is_pinned(
    shared_placement: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """PINS AN ACCEPTED OVER-REFUSAL (REVIEW9 #2): every honest multi-line
    shape below is denied structurally (gate unreached) because the
    quote-deleted view reads a ``\\⏎`` continuation where an escaped quote
    or trailing backslash sits immediately before a newline; the remedy is a
    one-line rewrite or ``--body-file`` / ``-F FILE``."""
    for command in _R13_OVER_REFUSAL_SHAPES:
        assert guard._R13_ASSEMBLED_CONTINUATION in guard.r12_constructs(command), command
        (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
            guard, shared_placement, monkeypatch, tmp_path, capsys, command
        )
        assert (bound, bound_gate) == ("deny", False), (command, bound_reason)
        assert (nobind, nobind_gate) == ("deny", False), (command, nobind_reason)
        assert "R12_SHELL_CONSTRUCT" in bound_reason, (command, bound_reason)
    # The honest form the guard does NOT flag (REVIEW9 §C last line,
    # measured): an admitted read form may hold the multi-line quoted body.
    honest = 'git commit -m "Fix \\"quoted\\"' + "\n\n" + 'Body"'
    (bound, bound_reason, bound_gate), (nobind, nobind_reason, nobind_gate) = _r7_both(
        guard, shared_placement, monkeypatch, tmp_path, capsys, honest
    )
    assert (bound, bound_gate) == ("allow", False), bound_reason
    assert (nobind, nobind_gate) == ("allow", False), nobind_reason
