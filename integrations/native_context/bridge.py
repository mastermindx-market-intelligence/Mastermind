"""Thin, in-process adapter to the incumbent #1273 CEO boot entrypoint.

No nested child-process runner is introduced. The canonical entrypoint remains
responsible for its process group, timeout, source checks and reader cleanup.
This adapter must be composed with released, source-qualified Mastermind code.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable

from .adapter import Binding, MAX_READER_BYTES, ReaderResult, canonical_argv


class _BoundedText(io.TextIOBase):
    def __init__(self, ceiling: int) -> None:
        self._ceiling = ceiling
        self._bytes = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        data = value.encode("utf-8", errors="strict")
        if len(self._bytes) + len(data) > self._ceiling:
            raise ValueError("reader_output_ceiling")
        self._bytes.extend(data)
        return len(value)

    def bytes(self) -> bytes:
        return bytes(self._bytes)


def _classify_typed(outcome: Any, code: Any) -> str | None:
    """Map a closed per-call state; malformed outcomes always remain held."""
    if type(code) is not int:
        return "canonical_reader_unavailable_reconcile"
    state = getattr(outcome, "state", None)
    if type(state) is not str:
        return "canonical_reader_unavailable_reconcile"
    if state == "SETTLED":
        return None if code == 0 else "canonical_read_settled_failure"
    if state == "NOT_STARTED":
        return "canonical_read_not_started"
    return "canonical_reader_unavailable_reconcile"


class CanonicalBootReader:
    """Dependency injection is for tests/embedding, not a user-selectable CLI module."""
    def __init__(self, *, root: Path, main: Callable[[list[str]], int],
                 git_sha: Callable[[Path], str | None],
                 typed_main: Callable[[list[str]], tuple[int, Any]] | None = None) -> None:
        self.root = root
        self.main = main
        self.git_sha = git_sha
        self.typed_main = typed_main

    def __call__(self, binding: Binding, budget: int, timeout: float) -> ReaderResult:
        try:
            if self.git_sha(self.root) != binding.expected_reader_sha:
                return ReaderResult(False, reason="reader_source_pin_mismatch")
            # Macro exact root/pin/record provenance and reader settlement are owned by #1273.
            args = canonical_argv(binding, compiler_budget=budget, timeout=timeout)
            output = _BoundedText(MAX_READER_BYTES + 1)
            errors = _BoundedText(32768)
            try:
                with redirect_stdout(output), redirect_stderr(errors):
                    result = (self.typed_main(args) if self.typed_main is not None
                              else self.main(args))
            except SystemExit:
                # An older, uncomposed CLI rejects --workstream; do not call its global mode.
                return ReaderResult(False, reason="canonical_cli_incompatible")
            if self.typed_main is not None:
                if type(result) is not tuple or len(result) != 2:
                    return ReaderResult(False, reason="canonical_reader_unavailable_reconcile")
                code, outcome = result
                classified = _classify_typed(outcome, code)
                if classified is not None:
                    return ReaderResult(False, reason=classified)
            elif type(result) is not int or result != 0:
                return ReaderResult(False, reason="canonical_read_failed")
            if self.git_sha(self.root) != binding.expected_reader_sha:
                return ReaderResult(False, reason="reader_source_drift")
            raw = output.bytes()
            if len(raw) > MAX_READER_BYTES:
                return ReaderResult(False, reason="canonical_output_ceiling")
            return ReaderResult(True, raw)
        except Exception:
            # Do not expose diagnostics or retry an unknown reader cleanup condition.
            return ReaderResult(False, reason="canonical_reader_unavailable_reconcile")


def installed_reader(root: Path) -> CanonicalBootReader:
    """Import only incumbent modules from this installation, not from event input.

    The installation owner must source-qualify this release and its dependencies.
    Local HEAD equality is a drift observation, not an integrity or custody seal.
    """
    # Import-time logs are diagnostics too; never mix them into hook stdout.
    diagnostics = _BoundedText(32768)
    with redirect_stdout(diagnostics), redirect_stderr(diagnostics):
        from control_plane.ceo_boot_packet import git_sha
        from scripts.ceo_boot_packet import main
        try:
            from scripts.ceo_boot_packet import main_with_outcome
        except ImportError:
            main_with_outcome = None
    return CanonicalBootReader(root=root, main=main, git_sha=git_sha,
                               typed_main=main_with_outcome)
