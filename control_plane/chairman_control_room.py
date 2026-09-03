"""control_plane.chairman_control_room — ``mastermind.chairman_control_room.v1``.

Wave A of the Chairman Control Room P0 (``research/MASTERMIND_CHAIRMAN_CONTROL_
ROOM_P0_ARCHITECTURE_AND_FABLE00_COMMISSION_2026-08-21.md``, §7/§21).  This module
projects a single deterministic, read-only document that makes "what is the
organization doing, what needs a human, and where can I go look" legible from
canonical sources — without becoming a fourth control plane itself.

Two layers, strictly separated
-------------------------------
* :func:`compose_control_room` — a **pure** function.  No file I/O, no
  subprocess, no clock read, no environment read.  Same inputs (including the
  same ``generated_at``) always produce byte-identical
  ``json.dumps(doc, sort_keys=True)`` output.  This is where every join,
  every sort, and every "what counts as degraded" decision lives, so it can be
  unit-tested completely offline against fixtures.
* :func:`build_control_room` — the **gather** layer.  It performs the one
  Agent OS subprocess call (via :func:`control_plane.ceo_boot_packet.
  build_packet`, injected into :func:`control_plane.executive_inbox.
  build_inbox` so a second subprocess is never spawned), reads the active-
  build snapshot Macro already compiles, loads the local navigation bindings,
  and hands everything to :func:`compose_control_room`.  Every source failure
  here becomes a ``None`` input plus a named ``degraded`` entry; this layer
  never raises.

Design laws
-----------
* **No synthetic overall status.**  There is no combined/overall lifecycle
  field anywhere in the output.  Every fact stays attributed to its owning
  source (Agent OS / Executive runtime / GitHub / local bindings); when two
  sources disagree, both raw values are preserved in a card's
  ``disagreements`` list rather than being averaged or voted on.
* **Bindings never create canonical facts.**  A navigation binding can only
  ever attach itself to a work card that already exists from an
  Agent-OS/executive/GitHub source, or land in ``unbound_surfaces``.
  Deleting the whole bindings file changes only ``sources.
  bindings_path_present``, every card's ``bindings``/``unbound_surfaces``/
  ``binding_conflicts`` — never any other field.
* **Exact joins only.**  A GitHub PR joins a work card only via a literal,
  word-boundary ``WS:<KEY>`` token in its title (the compiled
  ``project_active_builds.v1`` snapshot carries no PR body text — see the
  module-level receipt below); a runtime Job joins only via the CEO-intent
  provenance ``workstream`` field being byte-equal to the card's
  ``work_ref``.  No fuzzy or title-similarity matching exists anywhere in
  this module.
* **Upstream key names are never renamed.**  Every field this module reads
  off ``ceo_brief.v1`` / ``mastermind.executive_inbox.v2`` /
  ``project_active_builds.v1`` keeps its upstream name in the composed
  output.  Receipts for the exact keys consumed live in this module's
  helper docstrings, each pinned to the file/line it was read from.

Usage
-----
    from control_plane.chairman_control_room import build_control_room
    doc = build_control_room()
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane import (
    ceo_boot_packet,
    executive_inbox,
    executive_runtime,
    surface_bindings,
)

# CAP-C1 placement selection is an OPTIONAL capability: an extracted
# control-room-remote release stages an exact runtime file allowlist, and
# that allowlist may omit the selector modules or a genuinely optional
# dependency of theirs. This module must therefore boot — and compose a
# complete document — when they are absent. The import is DELIBERATELY
# dynamic, not static: a static import would both crash the extracted boot
# and widen the release's audited import closure.
#
# Genuine optional absence fails SOFT, by name, into the
# "placement_selection: unavailable (module not shipped)" degraded path.
#
# That softness has an exact limit. It applies only to a module the audited
# allowlist can actually omit — one this file does not already require. A
# dependency that is reachable through this module's own MANDATORY imports
# is not optional in any release: its absence raises before the optional
# block below is ever reached, and that hard failure is correct rather than
# a gap to paper over. See _SELECTOR_CONTROL_PLANE_REQUIRES for which
# dependencies fall on which side of that line.


def _optional_control_plane_module(name: str, *, requires: tuple[str, ...] = ()):
    """``None`` when the module is genuinely not shipped; loud otherwise.

    ``find_spec`` distinguishes the two failure classes: a missing file
    yields a ``None`` spec (→ optional capability absent, degrade by name),
    while a module that IS shipped but broken imports without a net so it
    fails loudly instead of masquerading as "not shipped".

    ``requires`` names this module's own STATIC control-plane dependencies,
    and they are resolved BEFORE the import (review 5086941171 BLOCKER 4).
    Resolving only ``name`` was not enough: in a release that ships the
    selector but not the steward, the selector's spec resolves fine, and the
    unguarded ``import_module`` below then raises ``ModuleNotFoundError``
    from the selector's own ``from control_plane.executive_steward import
    ...`` — aborting the import of THIS module entirely instead of degrading
    by name. Checking the dependency's spec turns that asymmetric packaging
    into the same fail-closed "not shipped" answer.

    This deliberately checks SPEC PRESENCE only. A dependency that is
    present but broken still raises from ``import_module``, so a genuine
    fault inside a shipped module keeps failing loudly rather than
    masquerading as absent.
    """
    qualified = f"control_plane.{name}"
    for dependency in (name, *requires):
        try:
            spec = importlib.util.find_spec(f"control_plane.{dependency}")
        except ModuleNotFoundError:
            spec = None
        if spec is None:
            return None
    return importlib.import_module(qualified)


#: Every control-plane module :mod:`control_plane.executive_placement_selection`
#: STATICALLY imports, derived from its own AST by
#: ``tests/test_chairman_control_room.py::
#: test_declared_selector_dependencies_match_its_actual_static_imports`` so
#: the list cannot silently drift if a STATIC import is added later.
#:
#: Scope of that guarantee, stated exactly, because the unqualified version
#: of this sentence was falsifiable: the derivation sees STATIC import forms
#: only. A DYNAMIC import (``importlib.import_module``, ``__import__``, or an
#: attribute reached off a bare ``import control_plane``) is invisible to any
#: AST walk and would leave this list stale while the guard stayed green.
#: Rather than claim a completeness the derivation cannot deliver, the guard
#: additionally REFUSES a dynamic import in the selector — turning that
#: silent gap into a loud one.
#:
#: What this buys, stated exactly — because an earlier pass over-claimed it:
#: declaring a dependency here converts its absence into the documented
#: "not shipped" degrade ONLY IF the dependency is not ALREADY reachable
#: from this module's own mandatory imports. ``executive_steward`` is such a
#: case and genuinely degrades. ``executive_orchestration_principal`` is NOT:
#: the unconditional ``from control_plane import (...)`` above pulls it
#: transitively. The observed traceback runs ``chairman_control_room ->
#: executive_inbox -> executive_runtime -> executive_orchestration_principal``;
#: ``executive_runtime`` is also imported directly here, so BOTH routes are
#: mandatory. Its absence therefore raises long before this optional block
#: is reached. It is listed here because it IS a
#: static import of the selector and the AST guard is the source of truth —
#: but a mandatory transitive dependency cannot be softened from here, and
#: ``test_a_mandatory_transitive_dependency_is_a_hard_failure_not_a_degrade``
#: pins that hard failure as the correct behaviour rather than pretending
#: otherwise.
_SELECTOR_CONTROL_PLANE_REQUIRES: tuple[str, ...] = (
    "executive_orchestration_principal",
    "executive_steward",
)

executive_placement_selection = _optional_control_plane_module(
    "executive_placement_selection", requires=_SELECTOR_CONTROL_PLANE_REQUIRES
)
executive_steward = _optional_control_plane_module("executive_steward")

#: CR1A's autonomy consumer is loaded through the SAME protected mechanism as
#: the selector above, and for the same reason.  A static
#: ``from control_plane import autonomy_control_room_projection`` at the top of
#: this module made ``executive_steward`` MANDATORY — the projection imports it
#: at module scope — which silently converted C1's optional capability into a
#: hard requirement and defeated the degraded-boot contract this file
#: documents.  Measured before the repair: with only ``executive_steward``
#: blocked, importing this module raised ``ModuleNotFoundError`` where master
#: booted with ``executive_steward is None``.  Packaging closure is NOT
#: permission to narrow that contract (Sol ruling, 2026-09-03), so the
#: dependency is declared here and absence degrades by name instead.
autonomy_control_room_projection = _optional_control_plane_module(
    "autonomy_control_room_projection", requires=("executive_steward",)
)

#: Review 5103135217 BLOCKER 1: the canonical, real dispatch-evidence
#: owners for :func:`_gather_dispatch_evidence` below, loaded through the
#: SAME protected optional mechanism and for the SAME reason as the
#: selector/projection above — an extracted release's audited runtime file
#: allowlist may omit any of these, and this module must still boot and
#: compose a complete (degraded) document rather than raise.  ``requires``
#: is each module's own full transitive STATIC control-plane import
#: closure, omitting only :mod:`control_plane.executive_runtime` (already
#: an unconditional mandatory import of THIS module, at the top of the
#: file, so it can never be the thing that is missing here).
wake_persist = _optional_control_plane_module(
    "wake_persist",
    requires=("wake_events", "wake_ledger", "session_targets", "wake_transport"),
)
wake_ledger = _optional_control_plane_module(
    "wake_ledger", requires=("session_targets", "wake_events", "wake_transport")
)
session_targets = _optional_control_plane_module(
    "session_targets", requires=("wake_events", "wake_transport")
)
sol_action_target = _optional_control_plane_module(
    "sol_action_target", requires=("session_targets", "wake_events", "wake_transport")
)
runtime_binding_projection = _optional_control_plane_module(
    "runtime_binding_projection",
    requires=(
        "operator_harness_contract", "session_targets", "wake_events",
        "wake_transport",
    ),
)

#: Schema version of the document this module emits.
SCHEMA = "mastermind.chairman_control_room.v1"

#: The CEO boot packet contract this module reads.  Owned by
#: :mod:`control_plane.ceo_boot_packet`.
BOOT_PACKET_SCHEMA = ceo_boot_packet.SCHEMA

#: The Agent OS brief contract nested inside the boot packet.  Owned by Macro
#: ``scripts/agentos.py`` (``BRIEF_SCHEMA``, pinned SHA
#: ``5ad347240a1a744746e01a472f80d6698e73b413``, line 97).
AGENT_OS_BRIEF_SCHEMA = ceo_boot_packet.BRIEF_SCHEMA

#: The Executive Inbox contract this module reads.  Owned by
#: :mod:`control_plane.executive_inbox`.
EXECUTIVE_INBOX_SCHEMA = executive_inbox.SCHEMA

#: The compiled active-build snapshot contract this module reads.  Owned by
#: Macro ``scripts/build_project_active_build_map.py`` (``SCHEMA``, pinned
#: SHA ``5ad347240a1a744746e01a472f80d6698e73b413``, line 38).  Repeated as a
#: literal rather than imported: Mastermind has no import-time dependency on
#: the Macro checkout, only a runtime file read (see ``_read_active_builds``).
ACTIVE_BUILDS_SCHEMA = "project_active_builds.v1"

#: Relative path, inside a resolved Macro checkout, of the compiled snapshot.
#: Verified against ``scripts/build_project_active_build_map.py`` line 49
#: (``_DEFAULT_JSON_OUT = _REPO_ROOT / "data" / "governance" /
#: "project_active_builds.json"``).
ACTIVE_BUILDS_RELATIVE_PATH = Path("data") / "governance" / "project_active_builds.json"

#: The compiled per-workstream Agent OS artifact this module reads (Wave A.1
#: amendment).  Owned by Macro ``scripts/agentos.py`` (``STATE_SCHEMA``,
#: pinned SHA ``5ad347240a1a744746e01a472f80d6698e73b413``, line 96).  Unlike
#: the ``ceo_brief.v1`` embedded in the boot packet, this artifact DOES carry
#: a flat per-workstream ``key/title/status/program/next_action`` directory
#: (``build_state()`` lines 1778-1811, record shape lines ~1485-1510) — it
#: fills exactly the gap :func:`_agent_os_workstreams` names in its own
#: docstring.
AGENT_OS_STATE_SCHEMA = "agent_os_state.v1"

#: Relative path, inside a resolved Macro checkout, of the compiled artifact.
#: Verified against ``scripts/agentos.py`` line 92
#: (``_STATE_JSON = _ROOT / "data" / "governance" / "agent_os_state.json"``).
AGENT_OS_STATE_RELATIVE_PATH = Path("data") / "governance" / "agent_os_state.json"

#: This Mastermind checkout — same idiom as :mod:`control_plane.ceo_boot_packet`.
_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Wall-clock budget for the one agentos subprocess, shared with
#: :mod:`control_plane.ceo_boot_packet`.
DEFAULT_TIMEOUT = ceo_boot_packet.DEFAULT_TIMEOUT

#: Every seat an attention item can be addressed to.  Mirrors
#: :data:`control_plane.executive_inbox.TARGETS`; repeated so this module's
#: partition never silently drifts from the inbox's own enum if a bucket is
#: renamed there without a corresponding CCR change.
_ATTENTION_TARGETS = ("chairman", "ceo", "coo")

#: Word-boundary ``WS:<key>`` token matcher.  A negative lookbehind on the
#: character immediately before ``WS:`` stops ``AWS:FOO`` from being read as
#: a citation of ``WS:FOO``; the greedy tail is a maximal run of key
#: characters, so ``WS:XY`` is read as ONE token — never as ``WS:X`` plus a
#: dangling ``Y`` — which is what keeps a card for ``WS:X`` from joining a PR
#: that only cites ``WS:XY`` (falsifier: similar-but-different key, no join).
_WS_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])WS:[A-Za-z0-9_.\-]+")

#: Exact workstream-record file path a PR can cite instead of (or in addition
#: to) a title token — Wave A.1 amendment.  Matches literally
#: ``agentos/workstreams/WS-<KEY>.md`` and captures ``<KEY>`` (which may
#: itself contain hyphens, e.g. ``CHAIRMAN-CONTROL-ROOM``) unambiguously: the
#: filename has exactly one ``WS-`` prefix and one ``.md`` suffix, so regex
#: backtracking resolves the greedy capture correctly with no key-boundary
#: guesswork. This — like the title-token join — can MINT a new work card.
_WORKSTREAM_FILE_RE = re.compile(r"^agentos/workstreams/WS-(.+)\.md$")

#: Handoff-file prefix a PR can cite.  Unlike the workstream-file path above,
#: a handoff filename (``agentos/handoffs/<KEY>-<date>.md``) cannot be
#: unambiguously reverse-parsed into a key when the key itself may contain
#: hyphens — ``CHAIRMAN-CONTROL-ROOM-2026-08-21.md`` has no marked boundary
#: between key and date.  So this join is evaluated the OTHER direction: for
#: each candidate key already known from another source, check whether a PR
#: cites ``agentos/handoffs/<KEY>-``.  It can therefore only ATTACH a PR to
#: an existing card, never mint a new one on its own.
_HANDOFF_FILE_PREFIX = "agentos/handoffs/"

#: Binding-summary keys shared by ``unbound_surfaces`` and every work card's
#: ``bindings`` list.  Deliberately excludes ``locator`` — a card projection
#: is navigation summary, not the raw locator payload.
_BINDING_SUMMARY_KEYS = (
    "binding_id", "work_ref", "role", "provider", "seat_ref", "locator_kind",
    "observed_at", "last_verified_at",
)

#: Closed set of top-level output keys.  A test asserts the composed
#: document's keys equal exactly this set — the frozen contract in the
#: architecture doc §7 / commission FROZEN SPEC.
OUTPUT_KEYS = frozenset({
    "schema", "generated_at", "sources", "degraded", "attention", "work",
    "unjoined_open_prs", "unbound_surfaces", "binding_conflicts",
    "placement_selection", "autonomy",
})


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------

def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ws_tokens(text: Any) -> set[str]:
    if not isinstance(text, str) or not text:
        return set()
    return set(_WS_TOKEN_RE.findall(text))


def _pr_ws_tokens(pr: Mapping[str, Any]) -> set[str]:
    """WS: tokens cited by one active-builds PR row.

    Reads ``title`` (the only free-text field the compiled
    ``project_active_builds.v1`` snapshot carries — verified against
    ``scripts/build_project_active_build_map.py`` lines 516-554: the
    compiled ``open_prs`` row has no ``body`` key at all, only ``files``/
    ``dependencies`` derived from it upstream) and defensively also a
    ``body`` key should a future schema add one.  Never returns text from
    either field in the composed output — only whether a token was found.
    """
    tokens = _ws_tokens(pr.get("title"))
    tokens |= _ws_tokens(pr.get("body"))
    return tokens


def _pr_summary(pr: Mapping[str, Any]) -> dict[str, Any]:
    """Project one active-builds PR row down to its navigation-safe summary.

    Keys verified against ``scripts/build_project_active_build_map.py``
    lines 516-542 (open_prs row construction): ``repo``, ``number``, ``url``,
    ``title``, ``branch``, ``draft``, ``merge_state``.  ``files``/
    ``protected_paths``/``dependencies``/``conflict`` are deliberately not
    copied — this module's PR facts are "what is it, can I open it", not a
    dependency graph.
    """
    return {
        "repo": pr.get("repo"),
        "number": pr.get("number"),
        "url": pr.get("url"),
        "title": pr.get("title"),
        "branch": pr.get("branch"),
        "draft": pr.get("draft"),
        "merge_state": pr.get("merge_state"),
    }


def _binding_summary(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {key: binding.get(key) for key in _BINDING_SUMMARY_KEYS}


# ---------------------------------------------------------------------------
# Agent OS brief consumption
# ---------------------------------------------------------------------------

def _agent_os_workstreams(brief: Any) -> dict[str, dict[str, Any]]:
    """Every workstream the ``ceo_brief.v1`` document names, keyed by its bare key.

    The emitted JSON brief does NOT carry a flat ``key/title/status``
    directory of every workstream — that shape exists only in the
    ``--full`` TEXT render, built from ``state["workstreams"]``, which is
    never part of the JSON the CLI emits.  What IS present for every
    workstream is ``readiness.records`` — LIVE-VERIFIED (Wave D production
    defect fix, 2026-08-22): running ``python3 scripts/agentos.py brief
    --json --no-remember`` against a fresh ``origin/main`` Macro checkout
    emits ``doc["readiness"] == {"schema": "agentos.readiness.v1",
    "degraded": [...], "records": [...341 rows live...]}`` — the container
    key is ``records``, NEVER ``items``.  ``items`` was
    ``compute_readiness()``'s internal Python variable name in
    ``scripts/agentos.py``, read off the SOURCE rather than the emitted
    document; the original Wave A fixture encoded that same wrong key, so
    every test passed while production silently composed zero brief
    workstreams (cards minted from ``agent_os_state`` alone; e.g.
    ``WS:CHAIRMAN-CONTROL-ROOM`` never appeared).  Each record — live
    receipt, a real workstream-level row — is exactly ``{"workstream":
    "ACCOUNT-IDENTITY-HARDENING", "wave": null, "state": "blocked",
    "reason_code": "workstream_blocked", "reason": "Authored workstream
    status is blocked.", "depends_on": [], "unmet_dependencies": [],
    "source": "agentos/workstreams/WS-ACCOUNT-IDENTITY-HARDENING.md"}`` —
    one entry per workstream, ``wave: null``, carrying ``workstream``/
    ``state``/``reason_code``/``reason``/``source``/``depends_on``/
    ``unmet_dependencies`` (all source-owned field names, unchanged here)
    plus a ``title`` for whichever workstreams also appear in ``blocked``
    or ``finished`` — both ALSO re-verified live in the same emission
    (unchanged from the original guess, but confirmed against the real
    document rather than source code): a real ``blocked[]`` row is
    ``{"workstream": "CUSTOMER-DATA-BACKUP", "title": "Customer-data backup
    and restore (MMX-001 / GATE-1)", "blocked_by": [...], "record_stale_days":
    7, "source": "agentos/workstreams/WS-CUSTOMER-DATA-BACKUP.md"}`` and a
    real ``finished[]`` row is ``{"workstream": "DEFENSE-PROCUREMENT-V3",
    "wave": "D4", "title": "Company financial truth bridge", "prs": [6123,
    6173, 6192], "done_at": "2026-08-21T12:36:09Z", "source":
    "agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md"}`` — ``workstream``/
    ``title`` land exactly where this function already reads them.  A
    real ``needs_ceo[]`` row (consumed elsewhere, by
    :mod:`control_plane.executive_inbox`'s own ``project_needs_ceo``, not
    here) is ``{"workstream": ..., "question": ..., "options": [...],
    "recommendation": ..., "by_when": ..., "blocks_waves": ..., "source":
    ...}`` — also unchanged from what was already assumed.  A workstream
    that is neither blocked nor finished in the window carries ``title:
    None`` here rather than an invented one.
    """
    if not isinstance(brief, Mapping):
        return {}

    readiness = brief.get("readiness")
    records = readiness.get("records") if isinstance(readiness, Mapping) else None
    result: dict[str, dict[str, Any]] = {}
    if isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
        for item in records:
            if not isinstance(item, Mapping):
                continue
            if item.get("wave") is not None:
                continue  # workstream-level rows only
            key = item.get("workstream")
            if not isinstance(key, str) or not key:
                continue
            result[key] = {
                "workstream": key,
                "state": item.get("state"),
                "reason_code": item.get("reason_code"),
                "reason": item.get("reason"),
                "source": item.get("source"),
                "depends_on": list(item.get("depends_on") or []),
                "unmet_dependencies": list(item.get("unmet_dependencies") or []),
                "title": None,
            }

    for bucket in ("blocked", "finished"):
        rows = brief.get(bucket)
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            key = row.get("workstream")
            title = row.get("title")
            if (
                isinstance(key, str) and key in result
                and isinstance(title, str) and title
                and result[key]["title"] is None
            ):
                result[key]["title"] = title

    return result


def _agent_os_state_workstreams(artifact: Any) -> dict[str, dict[str, Any]]:
    """Every workstream the ``agent_os_state.v1`` artifact names, keyed by its bare key.

    Wave A.1 amendment: this is the flat per-workstream directory the brief's
    ``ceo_brief.v1`` JSON does NOT carry (see :func:`_agent_os_workstreams`).
    Verified against Macro ``scripts/agentos.py`` (pinned SHA
    ``5ad347240a1a744746e01a472f80d6698e73b413``): the artifact's top-level
    ``workstreams`` list (``build_state()`` line 1795, ``"workstreams":
    records``) and each record's exact keys (record construction ~lines
    1485-1510): ``key`` (used as this dict's key, never emitted twice),
    ``title``, ``status``, ``program``, ``next_action``.  Every other record
    field (``owner``, ``class``, ``repos``, ``waves``, ``wave_detail``,
    ``prs``, ``claim``, ``collisions``, ``depends_on``, ``blocked_by``, ...)
    is deliberately NOT copied — only the four fields the commissioned
    WorkCard contract names.
    """
    if not isinstance(artifact, Mapping):
        return {}
    rows = artifact.get("workstreams")
    result: dict[str, dict[str, Any]] = {}
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            key = row.get("key")
            if not isinstance(key, str) or not key:
                continue
            result[key] = {
                "title": row.get("title"),
                "status": row.get("status"),
                "program": row.get("program"),
                "next_action": row.get("next_action"),
            }
    return result


def _merged_agent_os_entry(
    bare_key: str,
    brief_ws: Mapping[str, dict[str, Any]],
    state_ws: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Merge the artifact's per-workstream facts with the brief's live readiness overlay.

    ``agent_os_state.v1`` (:func:`_agent_os_state_workstreams`) is the base:
    ``title``/``status``/``program``/``next_action``, present for every
    workstream it knows about.  ``ceo_brief.v1``'s readiness projection
    (:func:`_agent_os_workstreams`) is layered on top as the LIVE overlay —
    its own ``state``/``reason_code``/``reason``/``source``/``depends_on``/
    ``unmet_dependencies`` fields, unchanged from the original Wave A design.
    Neither layer overwrites the other's fields — both raw values stay
    present so a caller can compare them (see the artifact-vs-brief
    disagreement check in :func:`_disagreements`).  ``title`` falls back to
    the brief's ``blocked``/``finished`` title only when the artifact did not
    know this workstream at all.
    """
    state_entry = state_ws.get(bare_key)
    brief_entry = brief_ws.get(bare_key)
    if state_entry is None and brief_entry is None:
        return None

    entry: dict[str, Any] = {
        "workstream": bare_key,
        "title": state_entry.get("title") if state_entry else None,
        "status": state_entry.get("status") if state_entry else None,
        "program": state_entry.get("program") if state_entry else None,
        "next_action": state_entry.get("next_action") if state_entry else None,
        "state": brief_entry.get("state") if brief_entry else None,
        "reason_code": brief_entry.get("reason_code") if brief_entry else None,
        "reason": brief_entry.get("reason") if brief_entry else None,
        "source": brief_entry.get("source") if brief_entry else None,
        "depends_on": list(brief_entry.get("depends_on") or []) if brief_entry else [],
        "unmet_dependencies": (
            list(brief_entry.get("unmet_dependencies") or []) if brief_entry else []
        ),
    }
    if entry["title"] is None and brief_entry is not None:
        entry["title"] = brief_entry.get("title")
    return entry


# ---------------------------------------------------------------------------
# Executive Inbox consumption
# ---------------------------------------------------------------------------

def _inbox_attention_items(inbox: Any) -> list[dict[str, Any]]:
    if not isinstance(inbox, Mapping):
        return []
    items = inbox.get("attention")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def _executive_jobs_by_workstream(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Runtime jobs grouped by their exact CEO-intent-provenance ``workstream``.

    Each ``mastermind.executive_inbox.v2`` attention item already carries the
    join key verbatim: ``item["job_id"]`` is ``None`` for Agent-OS-sourced
    items (``executive_inbox.py`` line 909) and the runtime job id for
    runtime-sourced items (line 615); ``item["workstream"]`` for a
    runtime item is exactly ``provenance["workstream"]`` (line 616, sourced
    from ``ceo_intent.py``'s ``_provenance`` line 681, itself validated
    against ``_WORKSTREAM_RE = r"^WS:..."`` at ``ceo_intent.py`` line 110) —
    i.e. it is ALREADY the full ``WS:<KEY>`` ref, not a bare key, unlike the
    Agent OS brief's own ``workstream`` fields.  This function only groups;
    it invents no join logic executive_inbox does not already assert.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        job_id = item.get("job_id")
        workstream = item.get("workstream")
        if job_id is None or not isinstance(workstream, str) or not workstream:
            continue
        grouped.setdefault(workstream, []).append({
            "job_id": job_id,
            "status": item.get("status"),
            "workstream": workstream,
        })
    return grouped


def _normalized_workstream_ref(item: Mapping[str, Any]) -> str | None:
    """The item's ``workstream`` as a full ``WS:<KEY>`` ref, regardless of source.

    A genuine cross-source asymmetry, both verified against ``executive_inbox.py``:
    a ``source="runtime"`` item's ``workstream`` is already the full ref (it is
    ``ceo_intent`` provenance, itself validated against
    ``_WORKSTREAM_RE = r"^WS:..."`` — ``ceo_intent.py`` line 110) — see the
    receipt in :func:`_executive_jobs_by_workstream`. A ``source="agent_os"``
    item's ``workstream`` (``executive_inbox.py`` line 910, via
    ``project_needs_ceo`` line 892-893) is copied verbatim from the Agent OS
    brief's own ``needs_ceo[].workstream``, which — like every other
    workstream field the brief emits (see :func:`_agent_os_workstreams`) — is
    the BARE key, with no ``WS:`` prefix.  Without this normalization, an
    agent_os-sourced attention item would group under a different dict key
    than the runtime items and PR/agent_os cards for the very same workstream,
    and its ``attention_id`` would silently never reach that card.
    """
    workstream = item.get("workstream")
    if not isinstance(workstream, str) or not workstream:
        return None
    if item.get("source") == "agent_os":
        return workstream if workstream.startswith("WS:") else f"WS:{workstream}"
    return workstream


def _attention_ids_by_workstream(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        ref = _normalized_workstream_ref(item)
        attention_id = item.get("attention_id")
        if ref is not None and isinstance(attention_id, str):
            grouped.setdefault(ref, []).append(attention_id)
    return grouped


def _group_jobs_by_ref(jobs: Any) -> dict[str, list[dict[str, Any]]]:
    """Group a flat ``[{job_id, status, workstream}, ...]`` list by ``workstream``.

    Wave A.1 amendment: the shape the gather layer's ``_read_runtime_jobs``
    produces is deliberately identical to the entries
    :func:`_executive_jobs_by_workstream` already builds from Executive
    Inbox attention items, so both can be merged with the same downstream
    dedupe-by-``job_id`` logic in :func:`compose_control_room`.  The
    ``workstream`` on each row is expected to already be the full
    ``WS:<KEY>`` ref (``_read_runtime_jobs`` sources it from
    :func:`control_plane.executive_inbox.ceo_intent_provenance`, the exact
    same provenance field :func:`_executive_jobs_by_workstream` reads).
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(jobs, Sequence) or isinstance(jobs, (str, bytes)):
        return grouped
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        workstream = job.get("workstream")
        job_id = job.get("job_id")
        if not isinstance(workstream, str) or not workstream or job_id is None:
            continue
        grouped.setdefault(workstream, []).append({
            "job_id": job_id,
            "status": job.get("status"),
            "workstream": workstream,
        })
    return grouped


# ---------------------------------------------------------------------------
# active-builds consumption
# ---------------------------------------------------------------------------

def _open_prs(active_builds: Any) -> list[dict[str, Any]]:
    if not isinstance(active_builds, Mapping):
        return []
    repositories = active_builds.get("repositories")
    if not isinstance(repositories, Sequence) or isinstance(repositories, (str, bytes)):
        return []
    prs: list[dict[str, Any]] = []
    for repo in repositories:
        if not isinstance(repo, Mapping):
            continue
        open_prs = repo.get("open_prs")
        if not isinstance(open_prs, Sequence) or isinstance(open_prs, (str, bytes)):
            continue
        prs.extend(pr for pr in open_prs if isinstance(pr, Mapping))
    return prs


def _pr_files(pr: Mapping[str, Any]) -> list[str]:
    files = pr.get("files")
    if isinstance(files, Sequence) and not isinstance(files, (str, bytes)):
        return [f for f in files if isinstance(f, str)]
    return []


def _pr_workstream_file_refs(pr: Mapping[str, Any]) -> set[str]:
    """WS: refs cited by an exact ``agentos/workstreams/WS-<KEY>.md`` file path.

    See :data:`_WORKSTREAM_FILE_RE` for the exactness/mint-a-new-card receipt.
    """
    refs: set[str] = set()
    for f in _pr_files(pr):
        match = _WORKSTREAM_FILE_RE.match(f)
        if match:
            refs.add(f"WS:{match.group(1)}")
    return refs


def _pr_cites_handoff_for_key(pr: Mapping[str, Any], bare_key: str) -> bool:
    """Whether one of ``pr``'s files starts with ``agentos/handoffs/<bare_key>-``.

    See :data:`_HANDOFF_FILE_PREFIX` for why this direction (candidate key ->
    prefix check) is the only unambiguous way to evaluate this join.
    """
    prefix = f"{_HANDOFF_FILE_PREFIX}{bare_key}-"
    return any(f.startswith(prefix) for f in _pr_files(pr))


def _prs_by_extractable_ref(open_prs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """PRs grouped by every ref they can MINT a card for on their own.

    Union of title/body ``WS:`` tokens and exact ``agentos/workstreams/
    WS-<KEY>.md`` file citations — both are unambiguous extractions that
    need no pre-existing candidate key list, so (like the original title-
    token join) either can create a brand-new work card.  Handoff-file
    citations are deliberately NOT part of this function; see
    :func:`_pr_cites_handoff_for_key`.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for pr in open_prs:
        refs = _pr_ws_tokens(pr) | _pr_workstream_file_refs(pr)
        for ref in refs:
            grouped.setdefault(ref, []).append(_pr_summary(pr))
    return grouped


def _unjoined_open_prs(
    open_prs: list[dict[str, Any]], joined_pr_identities: set[tuple[Any, Any]]
) -> list[dict[str, Any]]:
    """Open PRs that joined no card by ANY method (title token, workstream-file, or handoff-file)."""
    unjoined = [
        _pr_summary(pr) for pr in open_prs
        if (pr.get("repo"), pr.get("number")) not in joined_pr_identities
    ]
    unjoined.sort(key=lambda pr: (str(pr.get("repo") or ""), pr.get("number") or 0))
    return unjoined


# ---------------------------------------------------------------------------
# disagreements
# ---------------------------------------------------------------------------

def _disagreements(
    agent_os_entry: dict[str, Any] | None,
    jobs: list[dict[str, Any]],
    prs: list[dict[str, Any]],
) -> list[str]:
    """Preserve, never resolve, a conflict between two source-owned facts.

    Two checks compare the Agent OS readiness ``state`` (the closest
    source-owned analog to an authored lifecycle label the JSON brief
    exposes — see :func:`_agent_os_workstreams`) against a DIFFERENT
    source's own raw fact.  A third (Wave A.1 amendment) compares the
    ``agent_os_state.v1`` artifact's own authored ``status`` against that
    same brief readiness ``state`` — the two Agent-OS-family layers
    :func:`_merged_agent_os_entry` merges together can themselves disagree,
    since one is a point-in-time materialized snapshot and the other is
    live. No branch invents or overwrites either source's value; each only
    reports that they disagree.
    """
    out: list[str] = []
    state = agent_os_entry.get("state") if agent_os_entry else None
    status = agent_os_entry.get("status") if agent_os_entry else None

    if state == "done" and prs:
        out.append(
            f"agent_os reports this workstream readiness state=done while github "
            f"lists {len(prs)} open PR(s) citing it"
        )

    if state == "in_progress":
        failed = [job for job in jobs if job.get("status") == "failed"]
        if failed:
            job_ids = ", ".join(sorted(str(job.get("job_id")) for job in failed))
            out.append(
                f"executive reports {len(failed)} failed job(s) ({job_ids}) for this "
                f"workstream while agent_os reports readiness state=in_progress"
            )

    if status in ("done", "killed") and state not in (None, "done"):
        out.append(
            f"agent_os_state reports status={status!r} while agent os readiness "
            f"reports state={state!r} for this workstream"
        )

    return out


# ---------------------------------------------------------------------------
# the pure compositor
# ---------------------------------------------------------------------------

def compose_control_room(
    *,
    inbox: dict[str, Any] | None,
    boot_packet: dict[str, Any] | None,
    active_builds: dict[str, Any] | None,
    agent_os_state: dict[str, Any] | None = None,
    runtime_jobs: list[dict[str, Any]] | None = None,
    bindings: dict[str, Any] | None,
    binding_problems: Sequence[str] = (),
    placement_selection: dict[str, Any] | None = None,
    dispatch_evidence: Sequence[Mapping[str, Any]] | None = None,
    generated_at: str,
) -> dict[str, Any]:
    """Pure, deterministic projection of every already-collected source.

    No I/O, no subprocess, no clock read, no environment read — every value
    the document needs is either an argument or derived from one.  Calling
    this twice with the same arguments (in any list order upstream lists
    happened to arrive in) produces byte-identical
    ``json.dumps(doc, sort_keys=True)`` output, because every list this
    function itself emits is explicitly sorted before being placed in the
    document.
    """
    degraded: list[str] = []

    # --- boot packet / Agent OS brief --------------------------------------
    brief: Mapping[str, Any] | None = None
    mastermind_sha: str | None = None
    mastermind_branch: str | None = None
    macro_root: str | None = None
    macro_sha: str | None = None
    agent_os_brief_schema: str | None = None

    if boot_packet is None:
        degraded.append("boot_packet: unavailable")
    elif not isinstance(boot_packet, Mapping):
        degraded.append(f"boot_packet: expected an object, got {type(boot_packet).__name__}")
    else:
        found_schema = boot_packet.get("schema")
        if found_schema != BOOT_PACKET_SCHEMA:
            degraded.append(
                f"boot_packet: schema is {found_schema!r}, expected {BOOT_PACKET_SCHEMA!r}"
            )
        mm = boot_packet.get("mastermind")
        if isinstance(mm, Mapping):
            mastermind_sha = mm.get("sha")
            mastermind_branch = mm.get("branch")
        macro = boot_packet.get("macro")
        if isinstance(macro, Mapping):
            macro_root = macro.get("root")
            macro_sha = macro.get("sha")
        packet_degraded = boot_packet.get("degraded")
        if isinstance(packet_degraded, Sequence) and not isinstance(packet_degraded, (str, bytes)):
            degraded.extend(f"boot_packet: {entry}" for entry in packet_degraded)

        raw_brief = boot_packet.get("brief")
        if isinstance(raw_brief, Mapping):
            brief = raw_brief
            agent_os_brief_schema = raw_brief.get("schema")
            if agent_os_brief_schema != AGENT_OS_BRIEF_SCHEMA:
                degraded.append(
                    f"boot_packet: agent os brief schema is {agent_os_brief_schema!r}, "
                    f"expected {AGENT_OS_BRIEF_SCHEMA!r}"
                )
        elif raw_brief is not None:
            degraded.append("boot_packet: brief field is present but not an object")
        else:
            degraded.append("boot_packet: no agent os brief available")

    # --- agent os state artifact (Wave A.1 amendment) -----------------------
    agent_os_state_schema: str | None = None
    agent_os_state_generated_at: str | None = None
    agent_os_state_ws: dict[str, dict[str, Any]] = {}

    if agent_os_state is None:
        degraded.append("agent_os_state: unavailable")
    elif not isinstance(agent_os_state, Mapping):
        degraded.append(f"agent_os_state: expected an object, got {type(agent_os_state).__name__}")
    else:
        agent_os_state_schema = agent_os_state.get("schema")
        if agent_os_state_schema != AGENT_OS_STATE_SCHEMA:
            degraded.append(
                f"agent_os_state: schema is {agent_os_state_schema!r}, expected "
                f"{AGENT_OS_STATE_SCHEMA!r}"
            )
        agent_os_state_generated_at = agent_os_state.get("generated_at")
        agent_os_state_ws = _agent_os_state_workstreams(agent_os_state)

    # --- executive inbox -----------------------------------------------------
    attention: dict[str, list[dict[str, Any]]] = {target: [] for target in _ATTENTION_TARGETS}
    executive_inbox_schema: str | None = None
    runtime_db_present: bool | None = None
    raw_attention_items: list[dict[str, Any]] = []

    if inbox is None:
        degraded.append("executive_inbox: unavailable")
    elif not isinstance(inbox, Mapping):
        degraded.append(f"executive_inbox: expected an object, got {type(inbox).__name__}")
    else:
        executive_inbox_schema = inbox.get("schema")
        if executive_inbox_schema != EXECUTIVE_INBOX_SCHEMA:
            degraded.append(
                f"executive_inbox: schema is {executive_inbox_schema!r}, expected "
                f"{EXECUTIVE_INBOX_SCHEMA!r}"
            )
        grounding = inbox.get("grounding")
        if isinstance(grounding, Mapping):
            gm = grounding.get("mastermind")
            if isinstance(gm, Mapping):
                mastermind_sha = gm.get("sha") or mastermind_sha
                mastermind_branch = gm.get("branch") or mastermind_branch
            gmacro = grounding.get("macro")
            if isinstance(gmacro, Mapping):
                macro_root = gmacro.get("root") or macro_root
                macro_sha = gmacro.get("sha") or macro_sha
            runtime_db = grounding.get("runtime_db")
            if isinstance(runtime_db, Mapping):
                runtime_db_present = runtime_db.get("present")

        inbox_degraded = inbox.get("degraded")
        if isinstance(inbox_degraded, Sequence) and not isinstance(inbox_degraded, (str, bytes)):
            degraded.extend(f"executive_inbox: {entry}" for entry in inbox_degraded)

        raw_attention_items = _inbox_attention_items(inbox)
        for item in raw_attention_items:
            target = item.get("target")
            if target in attention:
                attention[target].append(item)

    # --- runtime jobs (Wave A.1 amendment) -----------------------------------
    # Distinct prefix from "executive_inbox:" on purpose: this closes the
    # suppressed-healthy-job blindness (acceptance row 3) that attention-only
    # jobs left — a job that never became an inbox attention item (queued,
    # running, cleanly completed) can still carry CEO-intent provenance and
    # belongs on its card.
    if runtime_jobs is None:
        degraded.append("executive_runtime: unavailable")
    runtime_jobs_by_ref = _group_jobs_by_ref(runtime_jobs) if runtime_jobs is not None else {}

    # --- active builds ---------------------------------------------------
    active_builds_schema: str | None = None
    active_builds_collected_at: str | None = None
    open_prs: list[dict[str, Any]] = []

    if active_builds is None:
        degraded.append("active_builds: unavailable")
    elif not isinstance(active_builds, Mapping):
        degraded.append(f"active_builds: expected an object, got {type(active_builds).__name__}")
    else:
        active_builds_schema = active_builds.get("schema")
        if active_builds_schema != ACTIVE_BUILDS_SCHEMA:
            degraded.append(
                f"active_builds: schema is {active_builds_schema!r}, expected "
                f"{ACTIVE_BUILDS_SCHEMA!r}"
            )
        active_builds_collected_at = active_builds.get("collected_at")
        open_prs = _open_prs(active_builds)

    # --- surface bindings --------------------------------------------------
    for problem in binding_problems:
        degraded.append(f"surface_bindings: {problem}")
    bindings_path_present = isinstance(bindings, Mapping)
    binding_rows: list[Mapping[str, Any]] = []
    if bindings_path_present:
        raw_rows = bindings.get("bindings") if isinstance(bindings, Mapping) else None
        if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)):
            binding_rows = [row for row in raw_rows if isinstance(row, Mapping)]
    binding_conflicts = surface_bindings.find_conflicts(bindings) if bindings_path_present else []

    # --- joins --------------------------------------------------------------
    agent_os_ws = _agent_os_workstreams(brief)
    exec_jobs_by_ref = _executive_jobs_by_workstream(raw_attention_items)
    attention_ids_by_ref = _attention_ids_by_workstream(raw_attention_items)
    prs_by_ref = _prs_by_extractable_ref(open_prs)  # title tokens + workstream-file refs

    # Every "mintable" ref: a card can come into existence from the Agent OS
    # brief, the agent_os_state artifact, an executive job's CEO-intent
    # provenance (attention-derived OR runtime_jobs-derived), or a PR's own
    # title-token/workstream-file citation.  A binding's work_ref and a PR's
    # handoff-file citation can only ATTACH to one of these — never mint one.
    combined_jobs_by_ref: dict[str, list[dict[str, Any]]] = {}
    for ref, job_rows in exec_jobs_by_ref.items():
        combined_jobs_by_ref.setdefault(ref, []).extend(job_rows)
    for ref, job_rows in runtime_jobs_by_ref.items():
        combined_jobs_by_ref.setdefault(ref, []).extend(job_rows)

    card_refs: set[str] = set()
    card_refs.update(f"WS:{key}" for key in agent_os_ws)
    card_refs.update(f"WS:{key}" for key in agent_os_state_ws)
    card_refs.update(combined_jobs_by_ref.keys())
    card_refs.update(prs_by_ref.keys())

    # Handoff-file attachment pass: evaluated against the now-final card_refs
    # only, so it can never mint a card — see `_HANDOFF_FILE_PREFIX`.
    for ref in card_refs:
        bare_key = ref.split(":", 1)[1]
        for pr in open_prs:
            if _pr_cites_handoff_for_key(pr, bare_key):
                prs_by_ref.setdefault(ref, []).append(_pr_summary(pr))

    joined_pr_identities: set[tuple[Any, Any]] = set()
    for pr_rows in prs_by_ref.values():
        for pr_summary in pr_rows:
            joined_pr_identities.add((pr_summary.get("repo"), pr_summary.get("number")))

    bindings_by_ref: dict[str, list[dict[str, Any]]] = {}
    unbound_surfaces: list[dict[str, Any]] = []
    for row in binding_rows:
        summary = _binding_summary(row)
        ref = row.get("work_ref")
        if isinstance(ref, str) and ref in card_refs:
            bindings_by_ref.setdefault(ref, []).append(summary)
        else:
            unbound_surfaces.append(summary)
    unbound_surfaces.sort(
        key=lambda s: (str(s.get("work_ref") or ""), str(s.get("role") or ""), str(s.get("binding_id") or ""))
    )

    work: list[dict[str, Any]] = []
    for ref in sorted(card_refs):
        bare_key = ref.split(":", 1)[1]
        agent_os_entry = _merged_agent_os_entry(bare_key, agent_os_ws, agent_os_state_ws)

        seen_jobs: set[str] = set()
        jobs: list[dict[str, Any]] = []
        for job in sorted(combined_jobs_by_ref.get(ref, []), key=lambda j: str(j["job_id"])):
            if job["job_id"] in seen_jobs:
                continue
            seen_jobs.add(job["job_id"])
            jobs.append(job)
        joined_by = "ceo_intent_provenance" if jobs else None

        seen_prs: set[tuple[Any, Any]] = set()
        prs: list[dict[str, Any]] = []
        for pr in sorted(
            prs_by_ref.get(ref, []),
            key=lambda p: (str(p.get("repo") or ""), p.get("number") or 0),
        ):
            pr_key = (pr.get("repo"), pr.get("number"))
            if pr_key in seen_prs:
                continue
            seen_prs.add(pr_key)
            prs.append(pr)

        attention_ids = sorted(set(attention_ids_by_ref.get(ref, [])))
        card_bindings = sorted(
            bindings_by_ref.get(ref, []),
            key=lambda b: (str(b.get("role") or ""), str(b.get("binding_id") or "")),
        )

        work.append({
            "work_ref": ref,
            "agent_os": agent_os_entry,
            "executive": {"jobs": jobs, "joined_by": joined_by},
            "github": {"prs": prs},
            "attention_ids": attention_ids,
            "bindings": card_bindings,
            "disagreements": _disagreements(agent_os_entry, jobs, prs),
        })

    # --- placement selection (CAP-C1) ---------------------------------------
    # Optional pure input: a wire dict already produced by
    # executive_placement_selection.select_placement().to_dict() (or `None`
    # when no facts document was supplied — the common case). A well-typed
    # `None` renders no section and degrades nothing, matching how every
    # other optional source in this module behaves. A present-but-invalid
    # dict degrades by name, exactly like a malformed boot_packet/inbox/
    # active_builds/agent_os_state input — this function still returns a
    # complete, well-formed document rather than raising.
    placement_selection_out: dict[str, Any] | None = None
    if placement_selection is not None and executive_placement_selection is None:
        degraded.append("placement_selection: unavailable (module not shipped)")
    elif placement_selection is not None:
        try:
            placement_selection_out = executive_placement_selection.validate_placement_selection(
                placement_selection
            )
        except (ValueError, TypeError) as exc:
            degraded.append(f"placement_selection: {exc}")
            placement_selection_out = None

    # --- autonomy responsibility projection ---------------------------------
    # Optional exactly like placement_selection above: a release that does not
    # ship the projection (or its required steward) still composes a complete
    # document.  The closed `autonomy` output key is RETAINED with a
    # non-actionable unavailable value and the absence degrades BY NAME, using
    # the same vocabulary this module already uses for the selector.
    autonomy: dict[str, Any] | None = None
    if autonomy_control_room_projection is None:
        degraded.append("autonomy: unavailable (module not shipped)")
    else:
        # --- autonomy responsibility projection ---------------------------------
        # Additive: control_plane.autonomy_control_room_projection.
        # build_autonomy_snapshot maps these same already-gathered plain-data
        # inputs into an ExecutiveStewardSnapshot, and project_autonomy renders
        # it — this compositor's own generated_at is passed straight through so
        # the whole document stays deterministic and clock-free.  Fix 1
        # (adversarial-review repair packet, 2026-09-01): that same
        # generated_at is now ALSO the reference timestamp every constructed
        # fact's freshness is judged against — threaded into
        # build_autonomy_snapshot and its two mapper siblings below, not just
        # into project_autonomy — so a real, aged Agent OS/inbox/bindings
        # document reads honestly STALE instead of unconditionally CURRENT.
        autonomy_snapshot = autonomy_control_room_projection.build_autonomy_snapshot(
            inbox=inbox,
            boot_packet=boot_packet,
            active_builds=active_builds,
            agent_os_state=agent_os_state,
            runtime_jobs=runtime_jobs,
            bindings=bindings,
            generated_at=generated_at,
        )
        # Agent-OS-declared blockers travel beside the snapshot rather than inside
        # it: the Steward's BlockerFact contract admits only Executive OS / Inbox /
        # Wake owners, so an agent_os-owned blocker cannot lawfully be a BlockerFact
        # and is carried as separately-attributed plain data instead.
        autonomy_declared_blockers = (
            autonomy_control_room_projection.declared_blockers_from_agent_os_state(
                agent_os_state, generated_at
            )
        )
        # Blast-radius repair packet, 2026-09-01: an unrecognized workstream
        # owner is a bounded, per-row mapping gap, never a SourceFailure — see
        # autonomy_control_room_projection.unmapped_responsibilities_from_
        # agent_os_state.  Threaded the same additive way as declared_blockers.
        autonomy_unmapped_responsibilities = (
            autonomy_control_room_projection.unmapped_responsibilities_from_agent_os_state(
                agent_os_state, generated_at
            )
        )
        # Blocker 1 (review 5106453403): the same runtime_jobs already
        # threaded into build_autonomy_snapshot above, grouped by workstream
        # into its full candidate-root set -- threaded the same additive
        # way as declared_blockers/unmapped_responsibilities so a card can
        # render "ambiguous, reconciliation required" distinctly from "no
        # Runtime evidence at all" (both leave root_job_id null).
        autonomy_runtime_root_candidates = (
            autonomy_control_room_projection.runtime_root_candidates_from_runtime_jobs(
                runtime_jobs
            )
        )
        autonomy = autonomy_control_room_projection.project_autonomy(
            autonomy_snapshot,
            generated_at=generated_at,
            declared_blockers=autonomy_declared_blockers,
            unmapped_responsibilities=autonomy_unmapped_responsibilities,
            runtime_root_candidates=autonomy_runtime_root_candidates,
        )
        # Dispatch-consumption is a SECOND pure pass over the cards just
        # produced, joined on the same exact (responsibility_ref, root_job_id)
        # key the projection already owns.  Review 5103135217 BLOCKER 1: the
        # real evidence itself is GATHERED by the I/O layer
        # (:func:`_gather_dispatch_evidence`, called from
        # :func:`build_control_room`) and handed in here as the
        # ``dispatch_evidence`` argument — this pure path only joins it, it
        # never fetches it.  A caller with no evidence to supply (offline
        # tests, an older gather layer) passes ``None`` and every card reads
        # UNKNOWN and non-actionable — ignorance, never a fabricated stage.
        autonomy = autonomy_control_room_projection.attach_dispatch_consumption(
            autonomy,
            autonomy_control_room_projection.project_dispatch_consumption(
                autonomy["responsibilities"],
                generated_at=generated_at,
                dispatch_evidence=dispatch_evidence,
            ),
        )

    doc = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "sources": {
            "mastermind_sha": mastermind_sha,
            "mastermind_branch": mastermind_branch,
            "macro_sha": macro_sha,
            "macro_root": macro_root,
            "executive_inbox_schema": executive_inbox_schema,
            "agent_os_brief_schema": agent_os_brief_schema,
            "agent_os_state_schema": agent_os_state_schema,
            "agent_os_state_generated_at": agent_os_state_generated_at,
            "active_builds_schema": active_builds_schema,
            "active_builds_collected_at": active_builds_collected_at,
            "runtime_db_present": runtime_db_present,
            "bindings_path_present": bindings_path_present,
        },
        "degraded": sorted(degraded),
        "attention": attention,
        "work": work,
        "unjoined_open_prs": _unjoined_open_prs(open_prs, joined_pr_identities),
        "unbound_surfaces": unbound_surfaces,
        "binding_conflicts": binding_conflicts,
        "placement_selection": placement_selection_out,
        "autonomy": autonomy,
    }
    assert set(doc.keys()) == OUTPUT_KEYS  # self-check: no "overall" field, closed set
    return doc


# ---------------------------------------------------------------------------
# the gather layer
# ---------------------------------------------------------------------------

def _read_active_builds(macro_root: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """Read the compiled active-build snapshot; never raises.

    No-write machine seam: this only reads a file Macro's own
    ``scripts/build_project_active_build_map.py`` already produces on its own
    schedule.  This module writes nothing into the Macro checkout, ever.
    """
    if not macro_root:
        return None, "no macro root resolved; active_builds not read"

    path = Path(macro_root) / ACTIVE_BUILDS_RELATIVE_PATH
    try:
        if not path.is_file():
            return None, f"{path}: not found"
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path}: cannot read ({exc})"

    try:
        loaded = json.loads(raw)
    except ValueError as exc:
        return None, f"{path}: invalid JSON ({exc})"

    if not isinstance(loaded, dict):
        return None, f"{path}: not a JSON object"
    return loaded, None


def _read_agent_os_state(macro_root: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """Read the compiled ``agent_os_state.v1`` artifact; never raises.

    Same no-write read pattern as :func:`_read_active_builds`: this only
    reads a file Macro's own ``scripts/agentos.py status`` already produces
    on its own schedule.
    """
    if not macro_root:
        return None, "no macro root resolved; agent_os_state not read"

    path = Path(macro_root) / AGENT_OS_STATE_RELATIVE_PATH
    try:
        if not path.is_file():
            return None, f"{path}: not found"
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path}: cannot read ({exc})"

    try:
        loaded = json.loads(raw)
    except ValueError as exc:
        return None, f"{path}: invalid JSON ({exc})"

    if not isinstance(loaded, dict):
        return None, f"{path}: not a JSON object"
    return loaded, None


def _read_runtime_jobs(root: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Runtime jobs whose CEO-intent provenance carries a workstream.

    Uses ONLY existing PUBLIC APIs — :meth:`control_plane.executive_runtime.
    Runtime.at` (``create=False``), :meth:`control_plane.executive_runtime.
    JobRegistry.list_jobs`, and :func:`control_plane.executive_inbox.
    ceo_intent_provenance` — exactly the same three calls
    ``executive_inbox.project_runtime`` itself makes.  No raw SQL; no edits
    to either module.  The existence check BEFORE construction mirrors
    ``executive_inbox.py`` lines 716-726: a bare ``Runtime.at(root)`` call
    defaults ``create=True`` and would manufacture an empty database, then
    report a quiet, job-free company — this never does that.  Distinct
    "executive_runtime:" degraded prefix from "executive_inbox:" so a caller
    can tell which read failed.

    Each row also carries the Job's own ``root_job_id`` (review 5106453403,
    Blocker 1) — the same public ``Job`` field
    :func:`autonomy_control_room_projection.build_autonomy_snapshot` needs
    to resolve ONE unique deduplicated Runtime root per workstream.
    :func:`_group_jobs_by_ref` deliberately reconstructs its OWN
    ``{job_id, status, workstream}`` shape and drops this extra key, so
    adding it here changes nothing about ``work[].executive.jobs``.
    """
    db_path = root / executive_inbox.DB_RELATIVE_PATH
    if not db_path.is_file():
        return None, f"database missing at {db_path}"

    try:
        runtime = executive_runtime.Runtime.at(root, create=False)
    except (executive_runtime.RuntimeProofError, OSError, ValueError, KeyError) as exc:
        return None, f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"

    try:
        jobs = runtime.jobs.list_jobs()
    except (executive_runtime.RuntimeProofError, ValueError, KeyError) as exc:
        return None, (
            f"jobs unreadable: {str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__}"
        )

    result: list[dict[str, Any]] = []
    for job in jobs:
        try:
            provenance, _warning = executive_inbox.ceo_intent_provenance(runtime, job.job_id)
        except (executive_runtime.RuntimeProofError, ValueError, KeyError):
            continue
        if provenance is None:
            continue
        workstream = provenance.get("workstream")
        if not isinstance(workstream, str) or not workstream:
            continue
        status = getattr(job.status, "value", None) or str(job.status)
        result.append({
            "job_id": job.job_id,
            "status": status,
            "workstream": workstream,
            "root_job_id": job.root_job_id,
        })
    return result, None


# ---------------------------------------------------------------------------
# dispatch-consumption evidence gather (review 5103135217 BLOCKER 1) — the
# ONE place this module reads real Executive Runtime / Wake ledger /
# RuntimeBinding facts to answer "was this responsibility actually picked
# up".  Bounded, read-only, never raises.  Builds ZERO new store, event
# type, cursor, watcher registry, or queue: every read goes through an
# existing owner's own public API (``runtime.attempts``/``runtime.events``,
# :class:`control_plane.wake_persist.WakeLedgerRepository` +
# :func:`control_plane.wake_ledger.reconstruct_status`,
# :func:`control_plane.sol_action_target.resolve_sol_action_target`, a
# real-if-available :func:`control_plane.runtime_binding_projection.
# project_runtime_binding`).  A source genuinely absent (module not shipped,
# no session-target registry file, no matching Runtime evidence) renders the
# fixed downstream states (``WATCH_UNPROVEN`` / ``RUNTIME_BINDING_
# RECONCILIATION_REQUIRED`` / ``DELIVERY_UNCONSUMED`` / ``UNKNOWN``) via
# :mod:`control_plane.autonomy_control_room_projection`'s own closed
# classification — this function never fills the gap itself.
#
# No canonical live Dialogue/Observer return-receipt store exists anywhere
# in this codebase today (only ``sol_watcher_contract.py``, a prompt-
# CONTRACT validator, names the closed BLOCKED/DECISION_REQUEST/RESULT
# vocabulary — it owns no runtime receipt log).  This gather therefore
# deliberately leaves every ``watch_*``/``return_*``/``sol_decision*`` field
# unset: a terminal Attempt with no such receipt renders WATCH_UNPROVEN,
# never a fabricated RETURNED — exactly the "admit ignorance rather than
# invent progress" law this whole packet exists to enforce.
# ---------------------------------------------------------------------------

#: Blocker 1: "The gather must be bounded (cap the rows and the per-row
#: work)."  A control room with an unbounded number of responsibility cards
#: must never turn this gather into unbounded per-request Runtime work.
_DISPATCH_EVIDENCE_MAX_CARDS = 200

#: Per-card cap on how many WAKE_REQUESTED events (i.e. candidate wake
#: obligations) this gather will even look at before giving up rather than
#: reading further — a card with a pathological number of wake obligations
#: degrades to "ambiguous-shaped" rather than doing unbounded work.
_DISPATCH_EVIDENCE_MAX_WAKE_REQUESTED = 20


def _dispatch_evidence_newer(current: str | None, candidate: Any) -> str | None:
    """Keep the lexicographically-greatest of two Zulu ISO-8601 strings.

    Every timestamp this module reads is a ``YYYY-MM-DDTHH:MM:SS(.ffffff)?Z``
    wire string (Runtime/Event/WakeLedgerRecord convention throughout this
    codebase), so plain string comparison is a correct, allocation-free
    "most recent" — no parsing, no clock, no timezone arithmetic needed
    here; the projection layer parses it for real freshness comparison.
    """
    if not isinstance(candidate, str) or not candidate:
        return current
    if current is None or candidate > current:
        return candidate
    return current


#: Job statuses that mean the job is finished; a finished descendant must
#: not evict a live ancestor from the executable frontier.
_TERMINAL_JOB_STATUSES = frozenset({"FAILED", "LOST", "COMPLETED", "CANCELLED"})


def _executable_attempt_candidates(tree_jobs: Sequence[Any]) -> list[Any]:
    """Jobs holding a live attempt, minus any that merely aggregate one.

    A job is dropped when another candidate is its strict descendant, so an
    aggregation root never competes with the carrier beneath it.  Ancestry is
    read from ``parent_job_id`` only — no depth arithmetic, no recency, no
    attempt-number comparison, and no title or provider inference.
    """
    candidates = [j for j in tree_jobs if getattr(j, "current_attempt_id", None)]
    if len(candidates) < 2:
        return candidates
    # Only a LIVE descendant may evict an ancestor.  `current_attempt_id` is
    # sticky on both sides: a FAILED/LOST/COMPLETED/CANCELLED child keeps it,
    # and the first version of this rule let such a dead child evict a
    # genuinely RUNNING root — turning a live responsibility into a terminal
    # one on the Chairman's surface, which is worse than the silence it
    # replaced (review follow-up, 2026-09-03).  A finished child does not
    # make its still-working parent finished.
    def _is_live(job: Any) -> bool:
        status = getattr(job, "status", None)
        return str(getattr(status, "value", status)) not in _TERMINAL_JOB_STATUSES

    live = [j for j in candidates if _is_live(j)]
    if live:
        # A finished child beside a still-running parent is an ordinary state,
        # not an ambiguity: the live job IS the answer.  Restricting to live
        # candidates first means a dead descendant neither evicts its live
        # ancestor nor drags the row into a false "cannot tell".
        candidates = live
        if len(candidates) < 2:
            return candidates
    live_ids = {getattr(j, "job_id", None) for j in candidates}
    by_id = {getattr(j, "job_id", None): j for j in tree_jobs}
    candidate_ids = {getattr(j, "job_id", None) for j in candidates}
    aggregating: set[Any] = set()
    for job in candidates:
        seen: set[Any] = set()
        parent = getattr(job, "parent_job_id", None)
        while parent and parent not in seen:
            seen.add(parent)
            if parent in candidate_ids and getattr(job, "job_id", None) in live_ids:
                # a dead descendant never evicts its ancestor
                aggregating.add(parent)
            parent_job = by_id.get(parent)
            parent = getattr(parent_job, "parent_job_id", None) if parent_job else None
    return [j for j in candidates if getattr(j, "job_id", None) not in aggregating]


def _gather_dispatch_evidence(
    root: Path,
    cards: Sequence[Mapping[str, Any]],
    generated_at: str,
) -> list[dict[str, Any]]:
    """Bounded, read-only, never-raising gather of real dispatch evidence.

    One row per ``(responsibility_ref, root_job_id)`` — the exact join key
    :func:`control_plane.autonomy_control_room_projection.
    project_dispatch_consumption` already owns (Law 1: reused, never
    reinvented).  A card is skipped entirely (no row emitted — the
    projection then reads it as absent evidence, ``UNKNOWN``) when its
    ``root_job_id`` is missing/malformed, or when nothing genuine was found
    for it at all — this function never emits a content-free row just to
    claim a happy-path state.

    Review 5106453403, Blockers 2-4 (closing the "40/40 UNKNOWN" defect):
    a card's ``root_job_id`` is often an AGGREGATION root — the whole point
    of Blocker 1 upstream — while the executable Attempt, the source of a
    Wake obligation, and a durable terminal-return receipt all live on a
    CHILD/carrier Job under that same root.  Every read below is therefore
    scoped to the exact Runtime job TREE sharing this card's
    ``root_job_id`` (``Job.root_job_id``, the DB-maintained invariant every
    descendant at every ``Job.parent_job_id``/``Job.depth`` already
    carries) — never to the root job_id alone, and never selected across
    jobs by title, timestamp, or provider.
    """
    try:
        db_path = root / executive_inbox.DB_RELATIVE_PATH
        if not db_path.is_file():
            return []
        try:
            runtime = executive_runtime.Runtime.at(root, create=False)
        except (executive_runtime.RuntimeProofError, OSError, ValueError, KeyError):
            return []

        registry = None
        if session_targets is not None and sol_action_target is not None:
            try:
                registry = session_targets.load_session_targets()
            except Exception:  # noqa: BLE001 — gather layer never raises
                registry = None

        wake_repo = None
        if wake_persist is not None and wake_ledger is not None:
            try:
                wake_repo = wake_persist.WakeLedgerRepository(runtime)
            except Exception:  # noqa: BLE001 — gather layer never raises
                wake_repo = None

        # Blockers 2-3: the whole Runtime job tree, read ONCE (not once per
        # card) and grouped by `root_job_id` — the canonical, DB-maintained
        # tree-membership field every job at every depth already carries.
        # This is what "restrict candidates to the exact root" means in
        # practice: a candidate job for card X can only ever come from
        # `jobs_by_root.get(X's root_job_id)`.
        try:
            all_jobs = runtime.jobs.list_jobs()
        except (executive_runtime.RuntimeProofError, ValueError, KeyError, OSError):
            all_jobs = []
        jobs_by_root: dict[str, list[Any]] = {}
        for job in all_jobs:
            jobs_by_root.setdefault(job.root_job_id, []).append(job)

        rows: list[dict[str, Any]] = []
        seen_keys: set[tuple[Any, Any]] = set()

        for card in list(cards)[:_DISPATCH_EVIDENCE_MAX_CARDS]:
            if not isinstance(card, Mapping):
                continue
            ref = card.get("responsibility_ref")
            root_job_id = card.get("root_job_id")
            if not isinstance(ref, str) or not ref:
                continue
            if not isinstance(root_job_id, str) or not root_job_id:
                continue
            key = (ref, root_job_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            row: dict[str, Any] = {}
            observed_at: str | None = None
            attempt = None
            candidate_job = None
            found_evidence = False

            tree_jobs = jobs_by_root.get(root_job_id, [])

            # --- attempt state: the canonical CURRENT attempt of the ONE
            # viable executable child/carrier Job in this root's tree —
            # never `max(attempt_number)`, never the aggregation root
            # itself unless IT is the (only) job carrying a live attempt.
            # `current_attempt_id` is STICKY in the Runtime schema: a CHECK
            # constraint keeps it non-null for every non-QUEUED state once a
            # job has been claimed.  So an aggregation root that is itself
            # RUNNING or COMPLETED — the normal COO shape — retains its own
            # attempt alongside a live child carrier, which made the count
            # two and dropped the whole attempt dimension: neither the root
            # nor the carrier won (review, real-Runtime probe S1/S2).  The
            # head's own test only passed because it requeued the root first,
            # an artificial step that removes the blocking condition.
            #
            # Resolve it STRUCTURALLY, never by recency, number or title: an
            # ancestor that merely aggregates is not the executable job, so a
            # candidate that is a strict ancestor of another candidate is
            # dropped.  What survives is the deepest executable frontier —
            # exactly one carrier, or a genuine multi-carrier ambiguity.
            attempt_candidates = _executable_attempt_candidates(tree_jobs)
            if len(attempt_candidates) == 1:
                candidate_job = attempt_candidates[0]
                try:
                    attempt = runtime.attempts.get_attempt(candidate_job.current_attempt_id)
                except (executive_runtime.RuntimeProofError, ValueError, KeyError, OSError):
                    attempt = None
                if attempt is not None:
                    status_value = getattr(attempt.status, "value", None)
                    if isinstance(status_value, str) and status_value:
                        row["attempt_state"] = status_value
                        found_evidence = True
                    for ts in (attempt.finished_at, attempt.heartbeat_at, attempt.started_at):
                        observed_at = _dispatch_evidence_newer(observed_at, ts)
            # Zero candidates (no job in the tree has a live current
            # attempt) or MULTIPLE viable candidates (two or more children
            # each carrying one): this dimension is left unset either way —
            # reconciliation-required, never a pick.

            # --- durable terminal-return APPLIED receipt (Blocker 4): the
            # SAME resolved candidate attempt, consulted for a matching
            # EXECUTIVE_TERMINAL_RETURN_APPLIED event.  A terminal Attempt
            # with NO such receipt (and no Dialogue/Observer watch proof)
            # stays WATCH_UNPROVEN downstream — this never fabricates one.
            if attempt is not None and candidate_job is not None:
                try:
                    applied_events = runtime.events.list_events(
                        aggregate_type="terminal_return_projection",
                        aggregate_id=attempt.attempt_id,
                    )
                except Exception:  # noqa: BLE001 — gather layer never raises
                    applied_events = []
                for event in applied_events:
                    payload = getattr(event, "payload", None)
                    if (
                        event.event_type == "EXECUTIVE_TERMINAL_RETURN_APPLIED"
                        and event.job_id == candidate_job.job_id
                        and event.attempt_id == attempt.attempt_id
                        and event.worker_id == attempt.worker_id
                        and isinstance(payload, Mapping)
                        and payload.get("root_job_id") == root_job_id
                    ):
                        row["terminal_return_state"] = "APPLIED"
                        found_evidence = True
                        observed_at = _dispatch_evidence_newer(observed_at, event.created_at)
                        break

            # --- obligation status: WakeLedgerRepository + reconstruct_status.
            # Blocker 3: Wake persistence records the SOURCE job in
            # `Event.job_id` (often a child), while the obligation's OWN
            # persisted envelope separately carries `root_job_id` (the
            # responsibility root) — so every job_id in this root's tree is
            # searched, and each candidate is admitted only when its own
            # parsed envelope's `root_job_id` matches this card's root
            # exactly (never merely "same tree", to guard against a
            # relocated/foreign envelope).
            if wake_repo is not None and wake_persist is not None:
                obligation_ids: set[str] = set()
                seen_event_count = 0
                scan_truncated = False
                for job in sorted(tree_jobs, key=lambda j: j.job_id):
                    if seen_event_count >= _DISPATCH_EVIDENCE_MAX_WAKE_REQUESTED:
                        scan_truncated = True
                        break
                    try:
                        wake_requested_events = runtime.events.list_events(
                            aggregate_type=wake_ledger.WAKE_AGGREGATE_TYPE,
                            job_id=job.job_id,
                        )
                    except Exception:  # noqa: BLE001 — gather layer never raises
                        wake_requested_events = []
                    for event in wake_requested_events:
                        if seen_event_count >= _DISPATCH_EVIDENCE_MAX_WAKE_REQUESTED:
                            scan_truncated = True
                            break
                        seen_event_count += 1
                        if event.event_type != "WAKE_REQUESTED" or not event.aggregate_id:
                            continue
                        try:
                            obligation = wake_persist.parse_obligation(event.payload)
                        except Exception:  # noqa: BLE001 — untrusted envelope
                            continue
                        if obligation.root_job_id != root_job_id:
                            continue
                        obligation_ids.add(event.aggregate_id)
                # More than one candidate obligation under this root: this
                # ROW cannot pick one without guessing (there is no
                # recency/title rule in this codebase for that choice), so
                # it leaves obligation_status unset rather than picking —
                # conservative, never a fabricated single answer.
                # A truncated scan cannot prove a second obligation is
                # absent, so it must read as ambiguity rather than as the
                # first one found.  The budget is spent across the whole tree
                # and counts rejected envelopes too, so exhausting it on an
                # early child previously hid a genuine obligation on a later
                # one and the row asserted a definite status picked by scan
                # order (review, real-Runtime probe: 19 foreign envelopes +
                # two genuine obligations reported one of them).
                if len(obligation_ids) == 1 and not scan_truncated:
                    oid = next(iter(obligation_ids))
                    try:
                        persisted = wake_repo.list_wake_events(aggregate_id=oid)
                        status = wake_ledger.reconstruct_status(
                            oid, tuple(item.record for item in persisted)
                        )
                        status_value = getattr(status, "value", None)
                        if isinstance(status_value, str) and status_value:
                            row["obligation_status"] = status_value
                            found_evidence = True
                        for item in persisted:
                            observed_at = _dispatch_evidence_newer(
                                observed_at, item.event.created_at
                            )
                    except Exception:  # noqa: BLE001 — gather layer never raises
                        pass

            # --- binding resolution: sol_action_target + session_targets ---
            if registry is not None and sol_action_target is not None:
                try:
                    seat_map = registry.root_job_bindings.get(root_job_id)
                    alias = seat_map.get("ceo") if isinstance(seat_map, Mapping) else None
                    target = registry.targets.get(alias) if isinstance(alias, str) else None
                    binding_snapshot = sol_action_target.RuntimeBindingSnapshot.unknown()
                    if (
                        target is not None
                        and attempt is not None
                        and runtime_binding_projection is not None
                    ):
                        try:
                            binding = runtime_binding_projection.project_runtime_binding(
                                runtime, attempt.attempt_id, target
                            )
                            binding_snapshot = sol_action_target.RuntimeBindingSnapshot.current(
                                [binding]
                            )
                        except Exception:  # noqa: BLE001 — gather layer never raises
                            binding_snapshot = sol_action_target.RuntimeBindingSnapshot.unknown()
                    resolution = sol_action_target.resolve_sol_action_target(
                        root_job_id=root_job_id,
                        registry=registry,
                        binding_snapshot=binding_snapshot,
                        actor_binding=None,
                    )
                    row["action_target_state"] = resolution.state.value
                    row["action_target_reason"] = resolution.reason.value
                    row["binding_evidence_state"] = binding_snapshot.state.value
                    found_evidence = True
                except Exception:  # noqa: BLE001 — gather layer never raises
                    pass

            if not found_evidence:
                # Nothing genuine was found for this card at all: emit no
                # row.  The projection then reads this card exactly like
                # any other card with no supplied evidence — UNKNOWN,
                # non-actionable, historical — rather than this function
                # claiming a hollow "WAITING_CAPACITY" it has no basis for.
                continue

            row["responsibility_ref"] = ref
            row["root_job_id"] = root_job_id
            if observed_at is not None:
                row["observed_at"] = observed_at
            rows.append(row)

        return rows
    except Exception:  # noqa: BLE001 — gather layer must never raise
        return []


# ---------------------------------------------------------------------------
# placement selection facts document (CAP-C1) — read + parse + select, never
# raises. This is the ONE gather-layer seam for
# :mod:`control_plane.executive_placement_selection`: a caller-supplied JSON
# document is parsed into the module's own typed, secret-safe facts, handed
# to the pure :func:`control_plane.executive_placement_selection.
# select_placement`, and the resulting decision's closed wire dict is what
# flows into :func:`compose_control_room`. No file is ever written here.
# ---------------------------------------------------------------------------

def _parse_source_ref(raw: Any) -> executive_steward.SourceRef:
    if not isinstance(raw, Mapping):
        raise ValueError("source must be an object")
    return executive_steward.SourceRef(
        owner=executive_steward.SourceOwner(raw["owner"]),
        ref=raw["ref"],
        observed_at=raw.get("observed_at"),
        freshness=executive_steward.Freshness(raw["freshness"]),
    )


def _parse_responsibility_fact(raw: Any) -> executive_steward.ResponsibilityFact:
    if not isinstance(raw, Mapping):
        raise ValueError("responsibility must be an object")
    return executive_steward.ResponsibilityFact(
        responsibility_ref=raw["responsibility_ref"],
        title=raw["title"],
        accountable_seat=executive_steward.Seat(raw["accountable_seat"]),
        state=raw.get("state"),
        root_job_id=raw.get("root_job_id"),
        source=_parse_source_ref(raw["source"]),
    )


def _parse_placement_demand(raw: Any) -> executive_placement_selection.PlacementDemand:
    if not isinstance(raw, Mapping):
        raise ValueError("demand must be an object")
    capabilities = raw["required_capabilities"]
    if not isinstance(capabilities, list):
        raise ValueError("demand.required_capabilities must be a list")
    # Mode wave: allowed_modes is required (no soft default — an omitted
    # or empty set would silently mean "no candidate can ever satisfy
    # this", which PlacementDemand itself already refuses).
    allowed_modes_raw = raw["allowed_modes"]
    if not isinstance(allowed_modes_raw, list):
        raise ValueError("demand.allowed_modes must be a list")
    return executive_placement_selection.PlacementDemand(
        required_capabilities=frozenset(capabilities),
        quota_class=raw["quota_class"],
        provider=raw.get("provider"),
        allowed_modes=frozenset(
            executive_placement_selection.PlacementMode(item) for item in allowed_modes_raw
        ),
    )


def _parse_placement_candidate(raw: Any) -> executive_placement_selection.PlacementCandidateFact:
    if not isinstance(raw, Mapping):
        raise ValueError("candidate must be an object")
    capabilities = raw["capabilities"]
    if not isinstance(capabilities, list):
        raise ValueError("candidate.capabilities must be a list")
    return executive_placement_selection.PlacementCandidateFact(
        worker_id=raw["worker_id"],
        provider=raw["provider"],
        account_label=raw["account_label"],
        quota_class=raw["quota_class"],
        capabilities=frozenset(capabilities),
        observed_at_ms=raw["observed_at_ms"],
        occupancy=executive_placement_selection.OccupancyState(raw["occupancy"]),
        occupancy_source=_parse_source_ref(raw["occupancy_source"]),
        capacity_state=executive_steward.CapacityState(raw["capacity_state"]),
        capacity_source=_parse_source_ref(raw["capacity_source"]),
        host_source_closure_proven=raw["host_source_closure_proven"],
        closure_source=_parse_source_ref(raw["closure_source"]),
        effect_state=executive_steward.EffectState(raw["effect_state"]),
        # Mode wave: mode is required; the two creation bools default to
        # None where absent — the exact shape a reuse candidate's facts
        # document naturally omits them in (PlacementCandidateFact itself
        # still refuses a fresh-lane candidate whose bools were left None).
        mode=executive_placement_selection.PlacementMode(raw["mode"]),
        creation_surface_accessible=raw.get("creation_surface_accessible"),
        session_creation_allowed=raw.get("session_creation_allowed"),
    )


def _read_placement_selection(
    path: str | Path | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read one placement-selection facts document and run ``select_placement``.

    ``path`` is ``None`` in the common case (no ``--placement-selection``
    flag) — that returns ``(None, None)`` with no degraded entry at all,
    exactly like an optional feature that was never asked for. Any other
    failure (missing file, invalid JSON, wrong shape, a typed fact that
    fails its own secret-safe validation, or ``select_placement`` itself
    refusing the input) becomes ``(None, "<reason>")`` — this function never
    raises, matching every other gather-layer reader in this module.

    Reviewer m-7: unlike this module's other gather-layer readers (whose
    ``degraded`` rows may embed ``str(exc)``/a path — an inherited,
    out-of-scope idiom), this ONE reader's failure reason names only the
    exception CLASS, never ``str(exc)`` or ``path`` itself. The facts
    document this reads can carry caller-supplied enum/token values (an
    invalid ``SourceOwner``/``Freshness``/... raises a stdlib ``ValueError``
    whose message echoes the bad value verbatim), and the ``degraded`` list
    is user-visible product surface — it must never become a channel for
    replaying facts-document content or filesystem paths back out.
    """
    if not path:
        return None, None
    if executive_placement_selection is None:
        return None, "unavailable (module not shipped)"
    try:
        raw_text = Path(path).read_text(encoding="utf-8")
        raw = json.loads(raw_text)
        if not isinstance(raw, Mapping):
            raise ValueError("placement selection facts document must be a JSON object")
        responsibility = _parse_responsibility_fact(raw["responsibility"])
        demand = _parse_placement_demand(raw["demand"])
        candidates_raw = raw["candidates"]
        if not isinstance(candidates_raw, list):
            raise ValueError("candidates must be a list")
        candidates = tuple(_parse_placement_candidate(item) for item in candidates_raw)
        accepted_tie_breaker = raw.get("accepted_tie_breaker")
        decision = executive_placement_selection.select_placement(
            responsibility=responsibility,
            demand=demand,
            candidates=candidates,
            accepted_tie_breaker=accepted_tie_breaker,
        )
        return decision.to_dict(), None
    except Exception as exc:  # noqa: BLE001 — gather layer never raises
        # Name only the exception CLASS — never str(exc), never `path` — see
        # the leak-safety note above.
        return None, f"unreadable ({exc.__class__.__name__})"


def build_control_room(
    *,
    repo_root: Path | None = None,
    macro_root_flag: str | None = None,
    environ: Mapping[str, str] = os.environ,
    now: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    bindings_path: str | Path | None = None,
    placement_selection_path: str | Path | None = None,
) -> dict[str, Any]:
    """Collect every source and hand them to :func:`compose_control_room`.

    Exactly ONE Agent OS subprocess: :func:`control_plane.ceo_boot_packet.
    build_packet` runs it, and the resulting packet is INJECTED into
    :func:`control_plane.executive_inbox.build_inbox` via its
    ``boot_packet=`` parameter (verified at ``executive_inbox.py`` lines
    959-968 / 1000-1001) so the inbox never re-collects it.

    Every source failure degrades rather than raising: a missing/unreadable
    Macro checkout, a failing Agent OS brief, an absent Executive runtime
    database, a missing/invalid active-builds snapshot, or an absent/
    malformed bindings file each become a ``None`` input handed to
    :func:`compose_control_room`, which names the gap.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    generated_at = now or _utc_now_z()

    packet: dict[str, Any] | None = None
    packet_failure: str | None = None
    try:
        packet = ceo_boot_packet.build_packet(
            repo_root=root,
            macro_root_flag=macro_root_flag,
            environ=environ,
            now=now,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — gather layer never raises
        packet_failure = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"

    inbox: dict[str, Any] | None = None
    inbox_failure: str | None = None
    try:
        inbox = executive_inbox.build_inbox(
            repo_root=root,
            boot_packet=packet,
            environ=environ,
            now=now,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — gather layer never raises
        inbox_failure = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"

    # Resolve the Macro root exactly like the packet does: reuse its own
    # reported root first (never re-walk the ladder against a fresher clock),
    # and only fall back to `resolve_macro_root` — Macro's OWN ladder
    # function, never a reimplementation of it — when the packet gave us
    # nothing to reuse (e.g. `build_packet` itself raised).
    macro_root: str | None = None
    if isinstance(packet, dict):
        macro = packet.get("macro")
        if isinstance(macro, dict):
            macro_root = macro.get("root")
    if not macro_root:
        resolved, _via, _candidates = ceo_boot_packet.resolve_macro_root(
            macro_root_flag, environ, root
        )
        if resolved is not None:
            macro_root = os.fspath(resolved)

    active_builds, active_builds_failure = _read_active_builds(macro_root)
    agent_os_state, agent_os_state_failure = _read_agent_os_state(macro_root)
    runtime_jobs, runtime_jobs_failure = _read_runtime_jobs(root)

    bindings, binding_problems = surface_bindings.load_bindings(bindings_path)

    placement_selection, placement_selection_failure = _read_placement_selection(
        placement_selection_path
    )

    # Review 5103135217 BLOCKER 1: real dispatch evidence is gathered here
    # (the I/O layer), never inside the pure `compose_control_room`.  The
    # exact (responsibility_ref, root_job_id) join keys the gather needs to
    # target aren't known until the Autonomy responsibility cards are
    # projected — which `compose_control_room` itself does, purely, from
    # the sources already collected above.  Rather than duplicate that pure
    # join logic here, this calls the pure composer ONCE with no dispatch
    # evidence to learn the card list (byte-identical, deterministic,
    # zero I/O — cheap to redo), runs the bounded real gather against it,
    # then composes the FINAL document with the real evidence attached.
    dispatch_evidence: list[dict[str, Any]] | None = None
    if autonomy_control_room_projection is not None:
        try:
            precursor = compose_control_room(
                inbox=inbox,
                boot_packet=packet,
                active_builds=active_builds,
                agent_os_state=agent_os_state,
                runtime_jobs=runtime_jobs,
                bindings=bindings,
                binding_problems=binding_problems,
                placement_selection=placement_selection,
                generated_at=generated_at,
            )
            precursor_autonomy = precursor.get("autonomy")
            if isinstance(precursor_autonomy, Mapping):
                precursor_cards = precursor_autonomy.get("responsibilities")
                if isinstance(precursor_cards, Sequence) and not isinstance(
                    precursor_cards, (str, bytes)
                ):
                    dispatch_evidence = _gather_dispatch_evidence(
                        root, precursor_cards, generated_at
                    )
        except Exception:  # noqa: BLE001 — gather layer never raises
            dispatch_evidence = None

    doc = compose_control_room(
        inbox=inbox,
        boot_packet=packet,
        active_builds=active_builds,
        agent_os_state=agent_os_state,
        runtime_jobs=runtime_jobs,
        bindings=bindings,
        binding_problems=binding_problems,
        placement_selection=placement_selection,
        dispatch_evidence=dispatch_evidence,
        generated_at=generated_at,
    )

    extra_degraded: list[str] = []
    if packet_failure:
        extra_degraded.append(f"boot_packet: unavailable — {packet_failure}")
    if inbox_failure:
        extra_degraded.append(f"executive_inbox: unavailable — {inbox_failure}")
    if active_builds_failure:
        extra_degraded.append(f"active_builds: {active_builds_failure}")
    if agent_os_state_failure:
        extra_degraded.append(f"agent_os_state: {agent_os_state_failure}")
    if runtime_jobs_failure:
        extra_degraded.append(f"executive_runtime: {runtime_jobs_failure}")
    if placement_selection_failure:
        extra_degraded.append(f"placement_selection: {placement_selection_failure}")
    if extra_degraded:
        doc = dict(doc)
        doc["degraded"] = sorted(list(doc["degraded"]) + extra_degraded)

    return doc
