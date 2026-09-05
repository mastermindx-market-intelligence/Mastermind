"""control_plane.ceo_boot_packet — read-only CEO boot packet assembled from Agent OS.

Agent OS is the organization's durable KNOWLEDGE plane: the ``agentos/`` record store
plus ``scripts/agentos.py`` in the **Macro** repository (merged as Macro PR #5472,
merge SHA ``431fb2b846b693c13fb6654901f0747e79f82534``).  Executive OS — this
repository — is the EXECUTION plane.  This module is the one-way bridge between them.
It projects a single deterministic packet the AI CEO seat boots from: what the company
is trying to do, what is running, what is blocked, and what needs a ruling from Chris.
Priority remains in the canonical Improvement Agenda; Agent OS readiness reaches it as
an annotation rather than becoming a second queue in this packet.

Design laws
-----------
* **Read-only, one direction.**  Executive OS READS Agent OS.  It never writes into
  the Macro checkout.  The only contact is one ``subprocess`` call to
  ``scripts/agentos.py brief --json --no-remember`` plus directory listings and
  ``git rev-parse``.  ``--no-remember`` is not a nicety: without it the Macro-side
  brief records a check-in marker at ``data/governance/.ceo_brief_last`` *inside the
  Macro checkout*, which would make this reader a writer.  ``tests/
  test_ceo_boot_packet.py`` snapshots the whole fixture tree around a CLI run and
  fails on any byte that moves.
* **No runtime coupling.**  Nothing here schedules, dispatches, leases, arms, or
  executes anything, and this module imports no module that does — not
  :mod:`control_plane.worker_runtime`, not :mod:`control_plane.executive_runtime`.
  This is the same law :mod:`control_plane.strategic_state` states, for the same
  reason: an execution path hung off organizational state would be the second control
  plane ``constraints.duplicate_control_planes`` prohibits.
* **Fail open.**  The deliberate inverse of :mod:`control_plane.strategic_state`'s
  fail-loud contract.  A missing, stale, or broken Macro checkout is an *orientation*
  gap, not a control-plane fault: the packet degrades with explicit warnings, names
  the repair in ``next_recommended_act``, and still exits 0.  A CEO who cannot read
  the org must still be told *that*, loudly, rather than handed a traceback.
* **Agent OS stays canonical.**  The ``ceo_brief.v1`` document is embedded verbatim
  and never re-derived, re-sorted, or re-scored here.  Its own ``inputs.degraded`` and
  ``warnings`` stay nested inside it; ``packet["degraded"]`` carries only bridge-level
  problems.  One generator, many renderers — the projection logic belongs to Macro.
* **Import-time stdlib only.**  Importing this module pulls in no third-party code.
  :mod:`control_plane.strategic_state` is itself import-time stdlib only (its PyYAML
  import is lazy), so importing it here preserves the property.

Usage
-----
    from control_plane.ceo_boot_packet import build_packet, render_packet
    packet = build_packet()
    print(render_packet(packet))
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane.strategic_state import StrategicStateError, load_strategic_state

#: Schema version of the packet this module emits.  A bump means a migration.
SCHEMA = "mastermind.ceo_boot_packet.v1"

#: Schema version of the Agent OS document embedded under ``packet["brief"]``.  That
#: contract is owned by Macro ``scripts/agentos.py``; a mismatch is reported, never
#: repaired here.
BRIEF_SCHEMA = "ceo_brief.v1"

#: Environment override for the Macro checkout to read Agent OS from.
ENV_MACRO_ROOT = "MASTERMIND_MACRO_ROOT"

#: How many handoff records the packet carries.  The boot packet is orientation, not
#: an archive; the store itself is the archive.
HANDOFF_LIMIT = 5

#: Wall-clock budget for the Agent OS brief subprocess.  It scans a git store and
#: worktrees, so it is seconds-to-tens-of-seconds on a warm workstation.
DEFAULT_TIMEOUT = 60

# The remote Control Room supplies one group-owning bounded runner and this cap.
# Other existing callers retain the historical stdlib subprocess path unless they
# explicitly opt into that runner contract.
DEFAULT_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
Runner = Callable[..., Mapping[str, Any]]

#: Budget for the two ``git rev-parse`` probes.  A hung git is a degraded packet, not
#: a hung CEO.
_GIT_TIMEOUT = 10

#: This Mastermind checkout — same idiom as :mod:`control_plane.strategic_state`.
_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Render width for the text form.
_WIDTH = 78

#: Column the labelled Agent OS rows hang from in the text form.
_LABEL_COL = 22

#: How many items of each Agent OS list the text form shows before "(+n more)".
_RENDER_TOP_N = 3


# ---------------------------------------------------------------------------
# Macro checkout resolution
# ---------------------------------------------------------------------------

def _macro_root_problem(path: Path) -> str | None:
    """Why `path` cannot serve as an Agent OS read root, or None when it can."""
    if not path.is_dir():
        return "missing"
    if not (path / "scripts" / "agentos.py").is_file():
        return "no scripts/agentos.py"
    if not (path / "agentos").is_dir():
        return "no agentos/ store"
    return None


def resolve_macro_root(
    explicit: str | None,
    environ: Mapping[str, str],
    repo_root: Path,
) -> tuple[Path | None, str | None, list[dict[str, Any]]]:
    """Locate a Macro checkout to read Agent OS from.

    Returns ``(resolved_path, resolved_via, candidates_tried)``.  A non-null explicit
    flag is authoritative and never falls through when unusable.  Without a flag, the
    discovery ladder is ``MASTERMIND_MACRO_ROOT -> sibling ../Macro Dashboard ->
    vendor/macro`` and the first *usable* candidate wins; a candidate is usable only
    when the directory exists and carries both ``scripts/agentos.py`` and an
    ``agentos/`` store.

    The sibling checkout deliberately outranks ``vendor/macro``.  The vendor pin exists
    so app code can import a *fixed* Macro engine revision and is therefore stale by
    design — that is its whole job.  Organizational STATE must be fresh, so a live
    sibling working copy beats a pinned engine mirror every time.  ``vendor/macro``
    remains last so a machine with no sibling still has a chance of answering.

    Every candidate tried is recorded (path + why it was rejected) so an unresolved
    packet can be diagnosed without re-running anything.
    """
    if explicit is not None:
        sources: list[tuple[str, Path | None]] = [("flag", Path(explicit))]
    else:
        sources = [
            ("env", Path(environ[ENV_MACRO_ROOT]) if environ.get(ENV_MACRO_ROOT) else None),
            ("sibling", repo_root.parent / "Macro Dashboard"),
            # `vendor/macro` is a tracked symlink; resolve it so the recorded path names
            # the real target rather than the link.
            ("vendor", (repo_root / "vendor" / "macro").resolve()),
        ]

    candidates: list[dict[str, Any]] = []
    for via, path in sources:
        if path is None:
            continue
        reason = _macro_root_problem(path)
        candidates.append({
            "via": via,
            "path": os.fspath(path),
            "usable": reason is None,
            "reason": reason,
        })
        if reason is None:
            return path, via, candidates

    return None, None, candidates


# ---------------------------------------------------------------------------
# Agent OS brief
# ---------------------------------------------------------------------------

def collect_brief(
    macro_root: Path,
    *,
    timeout: float,
    since: str | None,
    now: str | None,
    runner: Runner | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Run the Agent OS brief in `macro_root` and return ``(brief, warnings)``.

    Never raises: every failure mode returns ``(None, [warning])`` so the caller can
    degrade (see the fail-open design law).
    """
    script = macro_root / "scripts" / "agentos.py"
    # `--no-remember` is LOAD-BEARING, not cosmetic.  Without it `cmd_brief` writes a
    # `data/governance/.ceo_brief_last` check-in marker into the MACRO checkout, which
    # would turn this read-only bridge into a writer and break the boundary this whole
    # module exists to hold.  Never drop it.
    cmd = [sys.executable, os.fspath(script), "brief", "--json", "--no-remember"]
    if since:
        cmd += ["--since", since]
    if now:
        cmd += ["--now", now]

    if runner is None:
        try:
            proc = subprocess.run(
                cmd,
                cwd=os.fspath(macro_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, [f"agentos brief timed out after {timeout:g}s"]
        except OSError as exc:
            return None, [f"agentos brief could not be launched: {exc}"]

        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[-200:]
            return None, [
                f"agentos brief exited {proc.returncode}: {tail or '<no stderr>'}"
            ]
        stdout = proc.stdout
    else:
        try:
            result = runner(
                cmd,
                cwd=macro_root,
                timeout=timeout,
                max_bytes=max_output_bytes,
            )
        except Exception:  # noqa: BLE001 - stable, non-secret boundary reason
            return None, ["agentos brief bounded runner unavailable"]
        if not isinstance(result, Mapping):
            return None, ["agentos brief bounded runner invalid"]
        if result.get("timed_out") is True:
            return None, [f"agentos brief timed out after {timeout:g}s"]
        if result.get("limit_exceeded") is True:
            return None, ["agentos brief output exceeded hard limit"]
        if result.get("invalid_utf8") is True:
            return None, ["agentos brief emitted invalid UTF-8"]
        if result.get("code") != 0:
            return None, ["agentos brief command failed"]
        stdout = result.get("stdout")
        if type(stdout) is not str:
            return None, ["agentos brief bounded runner invalid"]

    try:
        brief = json.loads(stdout)
    except (ValueError, TypeError):
        head = (stdout or "").strip()[:200]
        return None, [f"agentos brief emitted unparseable output: {head or '<empty>'}"]

    if not isinstance(brief, dict):
        head = str(brief)[:200]
        return None, [f"agentos brief emitted unparseable output: {head}"]

    warnings: list[str] = []
    found = brief.get("schema")
    if found != BRIEF_SCHEMA:
        # Report and embed as-is.  Agent OS owns this contract; silently reshaping a
        # document we do not own would be worse than showing the CEO the mismatch.
        warnings.append(
            f"agentos brief schema is {found!r}, expected {BRIEF_SCHEMA!r} "
            f"— embedded as-is"
        )
    return brief, warnings


def collect_handoffs(macro_root: Path) -> tuple[list[dict[str, str]], str | None]:
    """Latest ``HANDOFF_LIMIT`` handoff records, newest first, plus a warning or None.

    Ordered by FILENAME descending, never by mtime.  Handoff filenames embed their
    date, and file mtimes in this organization are observer-stamped — a status sweep,
    a Finder walk, or a sparse-checkout materialization restamps whole trees, so an
    mtime sort silently reports whichever file was last *looked at*.
    """
    handoff_dir = macro_root / "agentos" / "handoffs"
    if not handoff_dir.is_dir():
        return [], f"no agentos/handoffs/ directory at {handoff_dir}"

    try:
        files = [p for p in handoff_dir.glob("*.md") if p.is_file()]
    except OSError as exc:
        return [], f"agentos/handoffs/ unreadable: {exc}"

    files.sort(key=lambda p: p.name, reverse=True)
    return [
        {"name": p.stem, "path": p.relative_to(macro_root).as_posix()}
        for p in files[:HANDOFF_LIMIT]
    ], None


# ---------------------------------------------------------------------------
# Local repository facts
# ---------------------------------------------------------------------------

def _git(path: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", os.fspath(path), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = (proc.stdout or "").strip()
    return value or None


def _bounded_git(
    path: Path,
    *args: str,
    runner: Runner,
    max_output_bytes: int,
) -> str | None:
    """Read one git fact through the caller's bounded process owner."""
    try:
        result = runner(
            ["git", *args],
            cwd=path,
            timeout=_GIT_TIMEOUT,
            max_bytes=min(max_output_bytes, 64 * 1024),
        )
    except Exception:  # noqa: BLE001 - degraded read-only boundary
        return None
    if not isinstance(result, Mapping):
        return None
    if any(
        result.get(flag) is True
        for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
    ):
        return None
    if result.get("code") != 0 or type(result.get("stdout")) is not str:
        return None
    value = result["stdout"].strip()
    return value or None


def _git_sha(path: Path) -> str | None:
    """HEAD commit sha of the checkout at `path`, or None if it cannot be read."""
    return _git(path, "rev-parse", "HEAD")


def _git_branch(path: Path) -> str | None:
    """Current branch name at `path` ('HEAD' when detached), or None."""
    return _git(path, "rev-parse", "--abbrev-ref", "HEAD")


def git_sha(path: Path) -> str | None:
    """Public name for :func:`_git_sha`, for sibling read-only projections.

    A WRAPPER, not an alias.  An alias would bind the function object at import
    time, so the house idiom of patching ``_git_sha`` in a test would silently
    fail to move it; this delegates on every call, so patching either name works.
    """
    return _git_sha(path)


def git_branch(path: Path) -> str | None:
    """Public name for :func:`_git_branch`.  A wrapper, for the reason above."""
    return _git_branch(path)


def load_strategic_summary() -> tuple[dict[str, Any] | None, str | None]:
    """Project ``config/strategic_state.yml`` down to the boot-packet summary.

    Returns ``(summary, error)``.  The reader itself fails loud by design; the packet
    catches that and degrades, because "the company has no readable objective set" is
    exactly the thing a booting CEO must be TOLD rather than crash on.
    """
    try:
        state = load_strategic_state()
    except StrategicStateError as exc:
        return None, str(exc).splitlines()[0]

    summary = {
        "schema": state["schema"],
        "company_phase": state["company_phase"],
        "north_star": list(state["north_star"]),
        "p0": [
            {
                "id": obj["id"],
                "department": obj["department"],
                "objective": " ".join(str(obj["objective"]).split()),
                "status": obj["status"],
            }
            for obj in state["p0"]
        ],
        # `constraints` is already a flat {name: level} mapping in the validated state
        # (levels drawn from the declared `constraint_levels` vocabulary).
        "constraints": {name: str(level) for name, level in state["constraints"].items()},
    }
    return summary, None


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------

def next_recommended_act(
    strategic: dict[str, Any] | None,
    strategic_err: str | None,
    brief: dict[str, Any] | None,
    degraded: Sequence[str],
) -> str:
    """The one thing the CEO should do next, by fixed precedence.

    Deterministic and explainable on purpose: the same packet always yields the same
    act, and the rung that produced it is readable off the sentence.  Repairs outrank
    rulings, rulings outrank unblocking; after those, the canonical Improvement Agenda
    owns priority.  Legacy ``brief.unblocked`` data is deliberately ignored here.
    """
    # 1. A company with no readable objective set cannot correctly prioritize anything
    #    else — every downstream judgment would be made against invented strategy.
    if strategic is None:
        return (
            f"Repair config/strategic_state.yml — {strategic_err or 'unreadable'}. "
            f"The company is running without a declared objective set."
        )

    # 2. No organizational state at all.  Nothing below this rung has any input.
    if brief is None:
        first = degraded[0] if degraded else "Agent OS store unreachable"
        return (
            f"Restore the Agent OS read path — {first}. "
            f"Sol has no organizational state until then."
        )

    needs = brief.get("needs_ceo") or []
    if needs:
        top = needs[0] if isinstance(needs[0], dict) else {}
        return (
            f"Rule on {len(needs)} pending CEO decision(s). "
            f"First: WS:{top.get('workstream', '?')} — "
            f"{top.get('question') or 'question not recorded'}"
        )

    blocked = brief.get("blocked") or []
    if blocked:
        top = blocked[0] if isinstance(blocked[0], dict) else {}
        by = ", ".join(str(b) for b in (top.get("blocked_by") or [])) or "unspecified"
        return (
            f"Clear {len(blocked)} blocked workstream(s). "
            f"First: WS:{top.get('workstream', '?')} (blocked by: {by})"
        )

    return (
        "Consult the canonical Improvement Agenda for the highest-priority next work."
    )


# ---------------------------------------------------------------------------
# Packet assembly
# ---------------------------------------------------------------------------

def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def build_packet(
    *,
    repo_root: Path | None = None,
    macro_root_flag: str | None = None,
    environ: Mapping[str, str] = os.environ,
    since: str | None = None,
    now: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    runner: Runner | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    mastermind_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the ``mastermind.ceo_boot_packet.v1`` document.

    Never raises on a degraded environment: an unresolved Macro checkout, a failing
    brief, an unreadable strategic state, or a missing handoffs directory each land as
    a string in ``packet["degraded"]`` and the packet is still returned whole.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    degraded: list[str] = []

    macro_root, resolved_via, candidates = resolve_macro_root(
        macro_root_flag, environ, root
    )

    brief: dict[str, Any] | None = None
    handoffs: list[dict[str, str]] = []
    macro_sha: str | None = None

    if macro_root is None:
        tried = "; ".join(
            f"{c['via']}={c['path']} ({c['reason']})" for c in candidates
        ) or "no candidates"
        degraded.append(
            f"no Agent OS store resolved — set {ENV_MACRO_ROOT} or pass --macro-root; "
            f"tried: {tried}"
        )
    else:
        brief, brief_warnings = collect_brief(
            macro_root,
            timeout=timeout,
            since=since,
            now=now,
            runner=runner,
            max_output_bytes=max_output_bytes,
        )
        degraded.extend(brief_warnings)

        handoffs, handoff_warning = collect_handoffs(macro_root)
        if handoff_warning:
            degraded.append(handoff_warning)

        macro_sha = (
            _git_sha(macro_root)
            if runner is None
            else _bounded_git(
                macro_root,
                "rev-parse",
                "HEAD",
                runner=runner,
                max_output_bytes=max_output_bytes,
            )
        )
        if macro_sha is None:
            degraded.append(f"macro git sha unreadable at {macro_root}")

    if mastermind_identity is None:
        mastermind_sha = _git_sha(root)
        if mastermind_sha is None:
            degraded.append(f"mastermind git sha unreadable at {root}")
        mastermind_branch = _git_branch(root)
    else:
        mastermind_sha = mastermind_identity.get("sha")
        mastermind_branch = mastermind_identity.get("branch")

    strategic, strategic_err = load_strategic_summary()
    if strategic_err:
        degraded.append(f"strategic state unreadable: {strategic_err}")

    return {
        "schema": SCHEMA,
        "generated_at": now or _utc_now_z(),
        "mastermind": {
            "root": os.fspath(root),
            "sha": mastermind_sha,
            "branch": mastermind_branch,
        },
        "macro": {
            "root": os.fspath(macro_root) if macro_root is not None else None,
            "sha": macro_sha,
            "resolved_via": resolved_via,
            "candidates_tried": candidates,
        },
        "strategic_state": strategic,
        # Embedded verbatim.  Its own inputs.degraded / warnings stay NESTED: Agent OS
        # is canonical and this packet displays it, never re-derives it.
        "brief": brief,
        "handoffs": handoffs,
        "degraded": degraded,
        "next_recommended_act": next_recommended_act(
            strategic, strategic_err, brief, degraded
        ),
    }


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def _wrap(text: str, width: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


def _labeled(label: str, entries: Sequence[str]) -> list[str]:
    """`label` in the left column, `entries` hanging at ``_LABEL_COL``."""
    head = f"  {label}".ljust(_LABEL_COL)
    hang = " " * _LABEL_COL
    body = list(entries) or ["none"]
    lines: list[str] = []
    for entry in body:
        for segment in _wrap(entry, _WIDTH - _LABEL_COL):
            prefix = head if not lines else hang
            lines.append((prefix + segment).rstrip())
    return lines


def _top_n(items: Sequence[Any], render) -> list[str]:
    shown = [render(i, item) for i, item in enumerate(items[:_RENDER_TOP_N], start=1)]
    if len(items) > _RENDER_TOP_N:
        shown.append(f"(+{len(items) - _RENDER_TOP_N} more)")
    return shown


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "?"


def render_packet(packet: dict[str, Any]) -> str:
    """Human-readable form of a boot packet.

    Every section is always present and DEGRADED is never suppressed: a boot packet
    that quietly omits what it could not read would be worse than no packet at all.
    """
    macro = packet.get("macro") or {}
    mastermind = packet.get("mastermind") or {}
    brief = packet.get("brief")
    strategic = packet.get("strategic_state")

    macro_sha = macro.get("sha")
    macro_cell = _short(macro_sha) if macro.get("root") else "UNRESOLVED"

    out: list[str] = [
        f"CEO BOOT PACKET — {packet.get('generated_at', '?')}",
        f"mastermind {_short(mastermind.get('sha'))} "
        f"({mastermind.get('branch') or '?'}) · macro {macro_cell}",
        f"schema {packet.get('schema', '?')}",
        "",
    ]

    # --- STRATEGY -----------------------------------------------------------
    if strategic is None:
        out.append("STRATEGY")
        out.append("  ⚠ strategic state unreadable")
    else:
        out.append(f"STRATEGY — {strategic.get('company_phase', '?')}")
        out.extend(_labeled("north star:", list(strategic.get("north_star") or [])))
        for obj in strategic.get("p0") or []:
            entry = (
                f"P0 {obj.get('id', '?')} [{obj.get('status', '?')}] — "
                f"{obj.get('objective', '')}"
            )
            for i, segment in enumerate(_wrap(entry, _WIDTH - 5)):
                out.append(("  " if i == 0 else "     ") + segment)
    out.append("")

    # --- DEGRADED -----------------------------------------------------------
    packet_degraded = list(packet.get("degraded") or [])
    brief_degraded = list(((brief or {}).get("inputs") or {}).get("degraded") or [])
    if packet_degraded or brief_degraded:
        out.append(f"⚠ DEGRADED ({len(packet_degraded) + len(brief_degraded)})")
        for entry in packet_degraded:
            for i, segment in enumerate(_wrap(entry, _WIDTH - 4)):
                out.append(("  - " if i == 0 else "    ") + segment)
        for entry in brief_degraded:
            for i, segment in enumerate(_wrap(f"brief: {entry}", _WIDTH - 4)):
                out.append(("  - " if i == 0 else "    ") + segment)
        out.append("")

    # --- AGENT OS -----------------------------------------------------------
    if brief is None:
        out.append("AGENT OS")
        out.append("  no Agent OS state — see DEGRADED")
    else:
        out.append(
            f"AGENT OS — {brief.get('schema', '?')} @ "
            f"{brief.get('generated_at', '?')}, since {brief.get('since_label', '?')}"
        )
        counts = brief.get("counts") or {}
        out.append(
            f"  {counts.get('total', 0)} workstreams: "
            f"{counts.get('active', 0)} active · "
            f"{counts.get('awaiting_ci', 0)} awaiting CI · "
            f"{counts.get('blocked', 0)} blocked · "
            f"{counts.get('done_in_window', 0)} done in window"
        )

        needs = list(brief.get("needs_ceo") or [])
        out.extend(_labeled(
            f"NEEDS CEO ({len(needs)}):",
            _top_n(needs, lambda i, n: (
                f"{i}. WS:{n.get('workstream', '?')} — "
                f"{n.get('question') or 'question not recorded'}"
            )),
        ))

        blocked = list(brief.get("blocked") or [])
        out.extend(_labeled(
            f"BLOCKED ({len(blocked)}):",
            _top_n(blocked, lambda _i, b: (
                f"WS:{b.get('workstream', '?')} ← "
                f"{', '.join(str(x) for x in (b.get('blocked_by') or [])) or 'unspecified'}"
            )),
        ))

    out.append("")

    # --- HANDOFFS -----------------------------------------------------------
    handoffs = list(packet.get("handoffs") or [])
    out.append(f"HANDOFFS (latest {len(handoffs)})")
    if handoffs:
        for row in handoffs:
            entry = f"{row.get('name', '?')} — {row.get('path', '?')}"
            for i, segment in enumerate(_wrap(entry, _WIDTH - 4)):
                out.append(("  " if i == 0 else "    ") + segment)
    else:
        out.append("  none on file")
    out.append("")

    # --- NEXT ---------------------------------------------------------------
    out.append("NEXT RECOMMENDED ACT")
    for segment in _wrap(packet.get("next_recommended_act", ""), _WIDTH - 2):
        out.append("  " + segment)

    return "\n".join(out) + "\n"
