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

import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane import ceo_boot_packet, executive_inbox, surface_bindings

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

    The emitted JSON brief (``scripts/agentos.py`` ``build_brief``, pinned SHA
    ``5ad347240a1a744746e01a472f80d6698e73b413`` lines 2101-2124) does NOT
    carry a flat ``key/title/status`` directory of every workstream — that
    shape exists only in the ``--full`` TEXT render, built from
    ``state["workstreams"]``, which is never part of the JSON the CLI emits.
    What IS present for every workstream is ``readiness.items`` (lines
    1648-1657: one entry per workstream, ``wave: null``, carrying
    ``workstream``/``state``/``reason_code``/``reason``/``source``/
    ``depends_on``/``unmet_dependencies`` — all source-owned field names,
    unchanged here) plus a ``title`` for whichever workstreams also appear in
    ``blocked`` (line 2075-2076) or ``finished`` (lines 2063-2066).  This is
    the honest exact reading of what the brief actually emits; a workstream
    that is neither blocked nor finished in the window carries ``title:
    None`` here rather than an invented one.  See DEVIATIONS in the Wave A
    build packet for the full explanation.
    """
    if not isinstance(brief, Mapping):
        return {}

    readiness = brief.get("readiness")
    items = readiness.get("items") if isinstance(readiness, Mapping) else None
    result: dict[str, dict[str, Any]] = {}
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        for item in items:
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


def _prs_by_ws_token(open_prs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for pr in open_prs:
        for token in _pr_ws_tokens(pr):
            grouped.setdefault(token, []).append(_pr_summary(pr))
    return grouped


def _unjoined_open_prs(open_prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unjoined = [_pr_summary(pr) for pr in open_prs if not _pr_ws_tokens(pr)]
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

    Both checks compare the Agent OS readiness ``state`` (the closest
    source-owned analog to an authored lifecycle label the JSON brief
    exposes — see :func:`_agent_os_workstreams`) against a DIFFERENT
    source's own raw fact.  Neither branch invents or overwrites either
    source's value; it only reports that they disagree.
    """
    out: list[str] = []
    state = agent_os_entry.get("state") if agent_os_entry else None

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

    return out


# ---------------------------------------------------------------------------
# the pure compositor
# ---------------------------------------------------------------------------

def compose_control_room(
    *,
    inbox: dict[str, Any] | None,
    boot_packet: dict[str, Any] | None,
    active_builds: dict[str, Any] | None,
    bindings: dict[str, Any] | None,
    binding_problems: Sequence[str] = (),
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
    prs_by_ref = _prs_by_ws_token(open_prs)

    card_refs: set[str] = set()
    card_refs.update(f"WS:{key}" for key in agent_os_ws)
    card_refs.update(exec_jobs_by_ref.keys())
    card_refs.update(prs_by_ref.keys())

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
        agent_os_entry = dict(agent_os_ws[bare_key]) if bare_key in agent_os_ws else None

        seen_jobs: set[str] = set()
        jobs: list[dict[str, Any]] = []
        for job in sorted(exec_jobs_by_ref.get(ref, []), key=lambda j: str(j["job_id"])):
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
            "active_builds_schema": active_builds_schema,
            "active_builds_collected_at": active_builds_collected_at,
            "runtime_db_present": runtime_db_present,
            "bindings_path_present": bindings_path_present,
        },
        "degraded": sorted(degraded),
        "attention": attention,
        "work": work,
        "unjoined_open_prs": _unjoined_open_prs(open_prs),
        "unbound_surfaces": unbound_surfaces,
        "binding_conflicts": binding_conflicts,
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


def build_control_room(
    *,
    repo_root: Path | None = None,
    macro_root_flag: str | None = None,
    environ: Mapping[str, str] = os.environ,
    now: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    bindings_path: str | Path | None = None,
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

    bindings, binding_problems = surface_bindings.load_bindings(bindings_path)

    doc = compose_control_room(
        inbox=inbox,
        boot_packet=packet,
        active_builds=active_builds,
        bindings=bindings,
        binding_problems=binding_problems,
        generated_at=generated_at,
    )

    extra_degraded: list[str] = []
    if packet_failure:
        extra_degraded.append(f"boot_packet: unavailable — {packet_failure}")
    if inbox_failure:
        extra_degraded.append(f"executive_inbox: unavailable — {inbox_failure}")
    if active_builds_failure:
        extra_degraded.append(f"active_builds: {active_builds_failure}")
    if extra_degraded:
        doc = dict(doc)
        doc["degraded"] = sorted(list(doc["degraded"]) + extra_degraded)

    return doc
