"""scripts/chairman_control_room.py — Chairman Control Room P0, Wave C.

A **loopback-only, ephemeral, local presentation process** (architecture doc
``research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_P0_ARCHITECTURE_AND_FABLE00_
COMMISSION_2026-08-21.md`` §8). It composes the read-only
``mastermind.chairman_control_room.v1`` document (Wave A, :mod:`control_plane.
chairman_control_room`), offers one-click navigation to a bound surface (Wave
B, :mod:`integrations.chairman_surfaces`), and lets the Chairman bind/unbind a
navigation-only local surface address (:mod:`control_plane.surface_bindings`).

Everything canonical stays read-only.  The **only** disk write anywhere in
this process is the atomic, ``0600`` surface-bindings save
(:func:`control_plane.surface_bindings.save_bindings`), reached from exactly
two endpoints: ``POST /api/bind`` and ``POST /api/unbind`` (plus one
``last_verified_at`` write-back from a successful ``POST /api/open``, which is
the SAME file, the SAME atomic writer). No canonical Agent OS / Executive OS /
GitHub / Macro state is ever written by this process — see the module-level
design laws in ``control_plane/chairman_control_room.py`` and
``control_plane/surface_bindings.py``, both reused, never re-implemented, here.

Runtime shape (architecture §8.2/§8.3; state caching per the H0 hardening
repair, 2026-08-22)
---------------------------------------
* binds ``127.0.0.1`` ONLY — there is no ``--host`` flag, and the server
  refuses to start (``assert``) if the bound socket is ever not loopback;
* ``GET /api/state`` is served from a process-memory cache, not recomposed
  per request: the server composes ONCE, synchronously, before it starts
  accepting requests, and a stale cache (default TTL 120s) refreshes via at
  most ONE background thread at a time (single-flight) — a request never
  blocks on a fresh composition, and N concurrent requests never spawn N
  compositions. This exists because the real gather-layer cost (Agent OS
  brief, blobless-clone git reads) measured 60-95s+ on the host this
  process actually runs on, well past what a synchronous per-request GET
  can afford; ``ServerConfig.compose_timeout`` (default 240s, CLI
  ``--compose-timeout``) is the timeout given to that OFF-request-path
  composition, deliberately wider than the shared library's own
  ``ceo_boot_packet.DEFAULT_TIMEOUT`` (60s, unchanged — still what
  ``--check`` and any other direct caller gets). All of this is process
  memory only — a restart forgets it, exactly like ``live_cache`` below;
* the one exception, by design (P0 acceptance row 28 — restart-forgets
  proof): a successful ``POST /api/refresh-builds`` stores its live
  ``project_active_builds.v1`` document in **process memory only**
  (``ServerConfig.live_cache``); a process restart forgets it, exactly like
  every other piece of server state;
* every request is loopback + Host-header gated; every mutating (``POST``)
  request, plus the two read ``GET``s that expose full org state
  (``/api/state``, ``/api/discover``), additionally requires the
  ``X-CCR-Token`` header. That token is a **per-process browser-origin
  capability nonce** (cross-site/CSRF defense for the local UI), NOT
  local-process authentication (H1 repair, Sol review 5000983751 Blocker
  1): ``GET /`` is itself unauthenticated and is what DELIVERS the nonce to
  the browser (``_serve_index`` substitutes it into the served HTML), so
  any same-user local process can fetch ``/`` and extract it the same way
  the browser does — that adversary is deliberately OUTSIDE this nonce's
  threat boundary. What it DOES guarantee: a simple cross-site browser
  request cannot set the custom header, and this server implements no
  CORS/preflight response at all, so a browser can never be granted
  cross-origin permission to attach it; when an ``Origin`` header is
  present it must additionally match the server's own origin exactly;
  tokenless or wrong-origin API requests are rejected fast, BEFORE any
  composition/discovery work runs;
* static assets are served from a closed, explicit ``{name: (path, mime)}``
  map — a request path is only ever used as a dict LOOKUP key, never
  concatenated into a filesystem path, so path traversal has no code path to
  reach;
* ``POST /api/open`` accepts only a ``binding_id`` — never a URL, argv, path,
  or profile from the browser; the actual navigation argv is built entirely
  server-side by :mod:`integrations.chairman_surfaces`.

Usage
-----
    python3 scripts/chairman_control_room.py
    python3 scripts/chairman_control_room.py --port 8888 --open
    python3 scripts/chairman_control_room.py --check
"""
from __future__ import annotations

import argparse
import http.server
import ipaddress
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

_REPO_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_REPO_ROOT))

from control_plane import ceo_boot_packet  # noqa: E402  (after sys.path bootstrap)
from control_plane import chairman_control_room as ccr  # noqa: E402
from control_plane import executive_inbox  # noqa: E402
from control_plane import surface_bindings as sb  # noqa: E402
from integrations.chairman_surfaces import capability, chatgpt, contract  # noqa: E402
from integrations.chairman_surfaces import runner as surfaces_runner  # noqa: E402

#: Default static asset directory (Wave C's private, non-public UI).
DEFAULT_STATIC_DIR = _REPO_ROOT / "app" / "static" / "chairman_control"

#: Default ephemeral loopback port.
DEFAULT_PORT = 8787

#: Host is hard-coded, never a flag — see module docstring / architecture §8.2.
HOST = "127.0.0.1"

#: Every Host header value this server accepts (with or without ``:<port>``).
_ALLOWED_HOSTNAMES = ("127.0.0.1", "localhost")

#: Bound applied to a POST JSON body before it is even parsed.
_MAX_BODY_BYTES = 64 * 1024

#: Timeout for the Macro active-builds refresh subprocess (frozen spec).
_REFRESH_BUILDS_TIMEOUT = 180.0

#: Cap applied to both discovery listings (claude_code_sessions, codex_sessions).
_DISCOVER_CAP = 40

#: Content-Security-Policy applied to every HTML response.
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self' data:"
)


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------

def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


#: Default output cap for the cwd-supporting branch of :func:`default_runner`
#: — matches ``integrations.chairman_surfaces.runner``'s own 64 KiB bound
#: (:data:`integrations.chairman_surfaces.runner._MAX_BYTES`) so a caller
#: that does not explicitly widen it (i.e. every adapter-shaped call this
#: branch might ever receive) keeps byte-identical behavior to Wave B.
_DEFAULT_CWD_RUNNER_MAX_BYTES = 65536

#: Output cap for the ONE caller that needs more than 64 KiB: the Macro
#: active-build compiler's ``--json-stdout`` document, which is real
#: organizational data (measured 112,569 bytes in Wave D live proof — see
#: the fix commission) and must never be silently truncated before
#: ``json.loads`` sees it. 4 MiB is a generous multiple of that measured
#: size, not a guess; ``integrations/chairman_surfaces/runner.py`` itself is
#: NOT touched — its 64 KiB cap stays exactly as-is for every adapter call,
#: whose outputs are tiny (osascript/open exit codes and short strings) by
#: design.
_REFRESH_BUILDS_MAX_OUTPUT_BYTES = 4 * 1024 * 1024


def _cap_text(data: bytes | str | None, limit: int = _DEFAULT_CWD_RUNNER_MAX_BYTES) -> str:
    """Bound captured subprocess text to ``limit`` bytes, mirroring ``surfaces_runner._cap``."""
    if not data:
        return ""
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > limit:
        return encoded[:limit].decode("utf-8", errors="ignore")
    return text


def default_runner(
    argv: list[str], *, timeout: float = 20.0, cwd: str | None = None, max_bytes: int | None = None
) -> dict:
    """The server's default subprocess runner.

    Every provider-adapter navigation call dispatched through
    :func:`integrations.chairman_surfaces.contract.open_binding` (i.e. every
    call this function receives WITHOUT a ``cwd``) delegates straight to
    :func:`integrations.chairman_surfaces.runner.run_argv` — the ONE
    subprocess boundary that package's own tests pin — so ``/api/open``'s
    subprocess behavior is byte-identical to Wave B's. ``max_bytes`` is
    PASSED THROUGH on this branch (``run_argv`` has carried its own
    ``max_bytes`` parameter since 98c8834; this seam simply forwards the
    caller's value, or ``run_argv``'s own 64 KiB default when the caller
    passes ``None``) — those small adapter outputs stay at the 64 KiB
    default in every live call today; this only matters if a future caller
    ever needs to widen it on this branch too.

    Only ``/api/refresh-builds`` (invoking Macro's active-build compiler
    script) needs a working directory, and ``run_argv`` has no ``cwd``
    parameter — that module is outside this packet's edit scope (see the
    build commission's OWNED FILES). This branch reuses ``run_argv``'s own
    argv-validation gate (:func:`integrations.chairman_surfaces.runner.
    _validate_argv`) and reproduces its exact safety properties (``shell=
    False``, never raising on subprocess failure), but takes an explicit
    ``max_bytes`` output cap (default matches ``run_argv``'s own 64 KiB;
    ``/api/refresh-builds`` widens it to 4 MiB — Wave D live proof found the
    real ``project_active_builds.v1`` document, 112,569 bytes, silently
    truncated below valid JSON at the old fixed 64 KiB bound).
    """
    if cwd is None:
        return surfaces_runner.run_argv(argv, timeout=timeout, max_bytes=max_bytes)

    limit = max_bytes if max_bytes is not None else _DEFAULT_CWD_RUNNER_MAX_BYTES
    validated = surfaces_runner._validate_argv(argv)  # reuse, not duplicate, the gate
    try:
        completed = subprocess.run(
            validated, shell=False, capture_output=True, timeout=timeout, cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "code": None, "stdout": _cap_text(exc.stdout, limit), "stderr": _cap_text(exc.stderr, limit),
            "timed_out": True,
        }
    except OSError as exc:
        return {"code": None, "stdout": "", "stderr": _cap_text(str(exc), limit), "timed_out": False}
    return {
        "code": completed.returncode,
        "stdout": _cap_text(completed.stdout, limit),
        "stderr": _cap_text(completed.stderr, limit),
        "timed_out": False,
    }


def _resolve_macro_root_simple(
    flag: str | None, environ: Mapping[str, str], repo_root: Path
) -> str | None:
    """Locate a Macro checkout directory for THIS server's own direct reads.

    Deliberately NOT :func:`control_plane.ceo_boot_packet.resolve_macro_root`
    — that ladder additionally requires ``scripts/agentos.py`` AND an
    ``agentos/`` store to consider a candidate "usable", which is a Agent-OS
    -specific concern unrelated to whether a Macro checkout carries
    ``scripts/build_project_active_build_map.py`` (the ONLY thing
    ``/api/refresh-builds`` and the live-active-builds override path need).
    Same candidate ORDER (flag -> env -> sibling "../Macro Dashboard" ->
    vendor/macro), existence-only test.
    """
    candidates = [
        flag,
        environ.get("MASTERMIND_MACRO_ROOT"),
        os.fspath(repo_root.parent / "Macro Dashboard"),
        os.fspath((repo_root / "vendor" / "macro").resolve()),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return candidate
    return None


def _unknown_key(data: dict, allowed: set) -> str | None:
    for key in data.keys():
        if key not in allowed:
            return key
    return None


# ---------------------------------------------------------------------------
# server configuration (injection seams)
# ---------------------------------------------------------------------------

@dataclass
class ServerConfig:
    """Everything a request handler needs, injected so tests never touch the
    real filesystem/subprocess/clock beyond what they explicitly opt into.
    """

    repo_root: Path
    macro_root: str | None
    bindings_path: str | Path | None
    #: per-process browser-origin capability nonce — cross-site defense, NOT
    #: local-process auth; see _api_auth_ok
    token: str
    origin: str
    port: int
    static_dir: Path = DEFAULT_STATIC_DIR
    runner: Callable[..., dict] = default_runner
    now_fn: Callable[[], str] = _utc_now_z
    open_binding_fn: Callable[..., dict] = contract.open_binding
    #: Overrides for the ``claude_code``/``codex`` native-existence-gate
    #: session-store roots (Sol review 5000169412 blocker 2) — ``None`` (the
    #: production default) means each adapter uses its own real default
    #: (``~/.claude/projects`` / ``~/.codex/sessions``). Tests inject a
    #: ``tmp_path`` here instead.
    claude_projects_dir: str | None = None
    codex_sessions_dir: str | None = None
    #: CAP-C1: optional path to a placement-selection facts document,
    #: passed straight through to ``ccr.build_control_room``'s own
    #: ``placement_selection_path`` parameter. ``None`` (the default) means
    #: no ``placement_selection`` section is composed at all — see
    #: ``control_plane.chairman_control_room._read_placement_selection``.
    placement_selection_path: str | Path | None = None
    #: Overrides for the ``chatgpt`` adapter's managed-browser environment
    #: store roots (Sol architecture correction, MAS-113, 2026-08-22) —
    #: ``None`` (the production default) means the adapter's own real default
    #: (``~/mlx/profiles`` / ``~/Library/Caches/GoLogin/profiles``). Tests
    #: inject a ``tmp_path`` here instead.
    mlx_profiles_root: str | None = None
    gologin_profiles_root: str | None = None
    #: Process-memory-only live active-builds cache — see module docstring.
    #: A fresh ``ServerConfig`` (i.e. a process restart) always starts empty.
    live_cache: dict[str, Any] = field(default_factory=dict)
    #: H0 hardening (2026-08-22): process-memory-only cache for the composed
    #: ``/api/state`` document + capability census, keyed "doc" / "capabilities"
    #: / "composed_at" (wall-clock ISO, ``config.now_fn`` at composition time)
    #: / "composed_monotonic" (``time.monotonic()`` at composition time — the
    #: TTL clock; wall clock is display-only and never drives staleness). A
    #: fresh ``ServerConfig`` (process restart) always starts empty — nothing
    #: here is durable, exactly like ``live_cache`` above.
    state_cache: dict[str, Any] = field(default_factory=dict)
    #: Guards ``state_cache`` plus the bookkeeping fields below across the
    #: serving threads (``ThreadingHTTPServer``) and any background/explicit
    #: recompose in flight.
    state_lock: threading.Lock = field(default_factory=threading.Lock)
    #: H1 repair (Sol review 5000983751 Blocker 2): monotonic reservation
    #: counter — EVERY composition attempt (startup pre-compose, background
    #: refresh, explicit refresh-builds) reserves the next value, via
    #: :func:`_reserve_composition` (or its exact inline equivalent — see
    #: :func:`_maybe_start_background_refresh`), before composing. Read and
    #: written only under ``state_lock``.
    state_compose_seq: int = 0
    #: Generation currently published in ``state_cache``. Read and written
    #: only under ``state_lock``.
    state_published_seq: int = 0
    #: Highest generation reserved by an EXPLICIT recomposition (an
    #: authenticated ``POST /api/refresh-builds``). A generation strictly
    #: below this floor may never publish OR record error metadata — this is
    #: what stops a stale background composition from overwriting a newer
    #: explicit recomposition that already finished (the race Sol's review
    #: named). Read and written only under ``state_lock``.
    state_explicit_floor: int = 0
    #: Count of composition attempts currently running. Read and written
    #: only under ``state_lock``. Replaces a prior ``state_refresh_in_flight:
    #: bool`` (H1 repair): an explicit recompose may now lawfully run
    #: concurrently with one background refresh, and with a bool the first
    #: of the two to exit would clear the flag while the other was still
    #: running — both lying to the snapshot and re-opening the single-flight
    #: gate early. The envelope's ``refresh_in_flight`` key stays a bool,
    #: derived as ``count > 0`` in :func:`_cached_state_snapshot`.
    state_refreshes_in_flight: int = 0
    #: Cache max-age (seconds, monotonic clock) before a GET kicks a
    #: background recompose. CLI flag ``--state-ttl``.
    state_ttl: float = 120.0
    #: Timeout handed to the gather layer (``build_control_room`` /
    #: ``build_packet`` / ``build_inbox``) for a cache-populating
    #: composition — startup pre-compose and every background recompose.
    #: Deliberately wider than ``ceo_boot_packet.DEFAULT_TIMEOUT`` (60s, kept
    #: UNCHANGED — shared machinery, still used by ``--check`` and any other
    #: direct caller) because this cost now runs off the request path: the
    #: 240s default covers the measured 94-206s real-host brief cost with
    #: headroom, where 60s always timed out (F1). CLI flag
    #: ``--compose-timeout``.
    compose_timeout: float = 240.0
    #: Static reason string for the LAST FAILED background recompose, or
    #: ``None``. Cleared on the next successful recompose. Never raised into
    #: a serving thread — surfaced only in the ``/api/state`` envelope.
    state_refresh_error: str | None = None


# ---------------------------------------------------------------------------
# state composition — reuses build_control_room/compose_control_room
# ---------------------------------------------------------------------------

def _compose_state_doc(
    config: ServerConfig, *, timeout: float = ceo_boot_packet.DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Fresh ``mastermind.chairman_control_room.v1`` document for ``/api/state``.

    No live-active-builds cache -> a plain, un-duplicated call to
    :func:`control_plane.chairman_control_room.build_control_room` (the
    common case; zero gather-layer duplication).

    A live cache present (from a prior ``/api/refresh-builds``) -> hand it to
    :func:`control_plane.chairman_control_room.compose_control_room` IN PLACE
    of a fresh active-builds file read (frozen spec: "passes it INTO the
    composition in place of the artifact read"). ``build_control_room``
    exposes no injection point for this (and ``chairman_control_room.py`` is
    out of this packet's edit scope), so :func:`_compose_with_live_active_builds`
    replicates that function's own gather-layer sequencing for this one path.

    ``timeout`` defaults to ``ceo_boot_packet.DEFAULT_TIMEOUT`` (60s) — the
    library default, unchanged, and exactly what every existing caller
    (``run_check``/``--check``) still gets with no argument. The H0
    cache-populating callers (startup pre-compose, background recompose)
    pass ``config.compose_timeout`` (default 240s) explicitly instead — this
    cost now runs off the request path, so it can afford to wait out the
    real host's measured 94-206s brief cost rather than the 60s bound that
    always timed out on the request path (F1/F2).
    """
    generated_at = config.now_fn()
    live_active_builds = config.live_cache.get("active_builds")
    if live_active_builds is None:
        return ccr.build_control_room(
            repo_root=config.repo_root,
            macro_root_flag=config.macro_root,
            environ=os.environ,
            now=generated_at,
            timeout=timeout,
            bindings_path=config.bindings_path,
            placement_selection_path=config.placement_selection_path,
        )
    return _compose_with_live_active_builds(config, live_active_builds, generated_at, timeout=timeout)


def _compose_with_live_active_builds(
    config: ServerConfig,
    live_active_builds: dict[str, Any],
    generated_at: str,
    *,
    timeout: float = ceo_boot_packet.DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    root = config.repo_root

    packet: dict[str, Any] | None = None
    packet_failure: str | None = None
    try:
        packet = ceo_boot_packet.build_packet(
            repo_root=root, macro_root_flag=config.macro_root, environ=os.environ,
            now=generated_at, timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — gather layer never raises
        packet_failure = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"

    inbox: dict[str, Any] | None = None
    inbox_failure: str | None = None
    try:
        inbox = executive_inbox.build_inbox(
            repo_root=root, boot_packet=packet, environ=os.environ,
            now=generated_at, timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — gather layer never raises
        inbox_failure = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"

    # Same macro-root preference ccr.build_control_room itself uses: reuse the
    # packet's own reported root first, fall back to Macro's own ladder
    # function only when the packet gave us nothing (receipt: chairman_
    # control_room.py build_control_room(), "Resolve the Macro root exactly
    # like the packet does").
    macro_root_resolved: str | None = None
    if isinstance(packet, dict):
        macro = packet.get("macro")
        if isinstance(macro, dict):
            macro_root_resolved = macro.get("root")
    if not macro_root_resolved:
        resolved, _via, _candidates = ceo_boot_packet.resolve_macro_root(
            config.macro_root, os.environ, root
        )
        if resolved is not None:
            macro_root_resolved = os.fspath(resolved)

    agent_os_state, agent_os_state_failure = ccr._read_agent_os_state(macro_root_resolved)
    runtime_jobs, runtime_jobs_failure = ccr._read_runtime_jobs(root)
    bindings, binding_problems = sb.load_bindings(config.bindings_path)

    doc = ccr.compose_control_room(
        inbox=inbox,
        boot_packet=packet,
        active_builds=live_active_builds,
        agent_os_state=agent_os_state,
        runtime_jobs=runtime_jobs,
        bindings=bindings,
        binding_problems=binding_problems,
        generated_at=generated_at,
    )

    extra_degraded: list[str] = []
    if packet_failure:
        extra_degraded.append(f"boot_packet: unavailable — {packet_failure}")
    if inbox_failure:
        extra_degraded.append(f"executive_inbox: unavailable — {inbox_failure}")
    if agent_os_state_failure:
        extra_degraded.append(f"agent_os_state: {agent_os_state_failure}")
    if runtime_jobs_failure:
        extra_degraded.append(f"executive_runtime: {runtime_jobs_failure}")
    if extra_degraded:
        doc = dict(doc)
        doc["degraded"] = sorted(list(doc["degraded"]) + extra_degraded)
    return doc


# ---------------------------------------------------------------------------
# state cache — cached, single-flight background composition (H0 hardening,
# 2026-08-22). Everything below is process memory only; a restart forgets
# it, exactly like ``live_cache`` above. The pure compositor
# (``compose_control_room``) and the gather layer (``build_control_room`` /
# ``build_packet`` / ``build_inbox``) are UNTOUCHED — this section only ever
# calls them, through the existing ``_compose_state_doc`` seam.
# ---------------------------------------------------------------------------

def _reserve_composition(config: ServerConfig, *, explicit: bool = False) -> int:
    """Reserve the next composition generation, under ``state_lock``, and
    count one more composition as in flight (H1 repair, Sol review
    5000983751 Blocker 2).

    EVERY composition attempt — startup pre-compose, a background refresh,
    or an explicit ``POST /api/refresh-builds`` recompose — must reserve a
    generation this way (or via the exact inline equivalent under an
    already-held lock — see :func:`_maybe_start_background_refresh`)
    BEFORE composing, so :func:`_refresh_state_cache` can tell an older
    generation from a newer one when it finishes. ``explicit=True`` also
    raises :attr:`ServerConfig.state_explicit_floor` to this generation —
    the floor a background composition may never publish (or record an
    error) below.
    """
    with config.state_lock:
        config.state_compose_seq += 1
        gen = config.state_compose_seq
        if explicit:
            config.state_explicit_floor = gen
        config.state_refreshes_in_flight += 1
        return gen


def _refresh_state_cache(
    config: ServerConfig, *, timeout: float, generation: int, include_capabilities: bool = True
) -> None:
    """Compose a fresh doc (+ capability census, when requested) for
    ``generation`` and, unless a newer generation has already published,
    atomically swap the cache.

    Never raises into the caller (startup pre-compose runs this inline on
    the main thread; every other call runs on a daemon background thread or
    the POST-handling thread) — a composition failure keeps the last good
    cached doc and records a static :attr:`ServerConfig.state_refresh_error`
    instead, UNLESS this generation is superseded (see below), in which case
    even the failure is discarded. On a non-superseded success the error is
    cleared. The caller (or :func:`_reserve_composition`) is responsible for
    incrementing :attr:`ServerConfig.state_refreshes_in_flight` before
    calling this; this function always decrements it on the way out.

    Superseded gating (H1 repair, Sol review 5000983751 Blocker 2): a
    generation is superseded when it is strictly below
    :attr:`ServerConfig.state_explicit_floor` (an explicit recompose was
    reserved after this one started) OR at/below
    :attr:`ServerConfig.state_published_seq` (a newer generation — explicit
    or background — has already published). A superseded composition's
    result is discarded ENTIRELY: no cache write, no error write/clear, no
    ``composed_at``/``composed_monotonic`` touch. This is what stops a
    stale background composition from overwriting a newer explicit
    recomposition that already finished.

    ``include_capabilities=False`` is the constructor-time startup path
    ONLY — see :func:`_ensure_capabilities_cached` for why census is kept
    out of it. Every other caller (background refresh, explicit refresh)
    recomposes doc + census together, "alongside" each other in the same
    cache entry, per the frozen spec.
    """
    try:
        doc = _compose_state_doc(config, timeout=timeout)
        capabilities = capability.census(runner=config.runner) if include_capabilities else None
    except Exception as exc:  # noqa: BLE001 — never raise into a serving thread
        detail = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
        with config.state_lock:
            config.state_refreshes_in_flight -= 1
            superseded = (
                generation < config.state_explicit_floor or generation <= config.state_published_seq
            )
            if not superseded:
                config.state_refresh_error = "state refresh failed; serving last good composition"
            published = config.state_published_seq
            floor = config.state_explicit_floor
        if superseded:
            print(
                f"superseded state refresh failure discarded: generation={generation} "
                f"published={published} explicit_floor={floor}: {detail}",
                flush=True,
            )
        else:
            print(f"state refresh failed: {detail}", flush=True)
        return

    composed_at = config.now_fn()
    with config.state_lock:
        config.state_refreshes_in_flight -= 1
        superseded = generation < config.state_explicit_floor or generation <= config.state_published_seq
        published = config.state_published_seq
        floor = config.state_explicit_floor
        if not superseded:
            config.state_cache["doc"] = doc
            if include_capabilities:
                config.state_cache["capabilities"] = capabilities
            config.state_cache["composed_at"] = composed_at
            config.state_cache["composed_monotonic"] = time.monotonic()
            config.state_published_seq = generation
            config.state_refresh_error = None
    if superseded:
        print(
            f"superseded composition discarded (generation={generation} published={published} "
            f"explicit_floor={floor})",
            flush=True,
        )


def _precompose_initial_state(config: ServerConfig) -> None:
    """Startup pre-compose (run/main only, NOT ``--check``) — composes once,
    synchronously, before the server accepts any request, so the first
    ``GET /api/state`` is always served from cache rather than stalling on a
    fresh composition (F1).

    Deliberately composes the DOC only, not the capability census — see
    :func:`_ensure_capabilities_cached`.
    """
    print("composing initial state…", flush=True)
    started = time.monotonic()
    gen = _reserve_composition(config)
    _refresh_state_cache(config, timeout=config.compose_timeout, generation=gen, include_capabilities=False)
    elapsed = time.monotonic() - started
    print(f"state composed in {elapsed:.1f}s", flush=True)


def _maybe_start_background_refresh(config: ServerConfig) -> None:
    """If the cache is stale and no composition is already running, start
    exactly ONE daemon background recompose thread (single-flight — F5:
    without this, N concurrent stale GETs would each spawn a full
    composition). Never blocks the calling (serving) thread. Recomposes
    doc + census together (``include_capabilities=True``) — by the time
    the cache can go stale, an authenticated GET has already run
    :func:`_ensure_capabilities_cached` at least once.

    Reserves the generation INLINE under the same lock hold as the
    staleness/in-flight check (not via :func:`_reserve_composition`, which
    would re-take the lock) so the check-and-reserve is atomic.
    """
    with config.state_lock:
        composed_monotonic = config.state_cache.get("composed_monotonic")
        age = None if composed_monotonic is None else time.monotonic() - composed_monotonic
        is_stale = age is None or age > config.state_ttl
        if not is_stale or config.state_refreshes_in_flight:
            return
        config.state_compose_seq += 1
        gen = config.state_compose_seq
        config.state_refreshes_in_flight += 1
    thread = threading.Thread(
        target=_refresh_state_cache,
        kwargs={
            "config": config, "timeout": config.compose_timeout, "generation": gen,
            "include_capabilities": True,
        },
        daemon=True,
    )
    thread.start()


def _ensure_capabilities_cached(config: ServerConfig) -> None:
    """Populate the capability census once, synchronously, on first demand.

    Kept OUT of the unconditional constructor-time pre-compose on purpose:
    ``capability.census`` is the ONE piece of this cache that touches
    ``config.runner`` (its optional ``--version`` probe of whichever of
    claude/codex/cursor-agent are found on ``PATH``) — every OTHER
    composition step (``build_control_room`` / ``build_packet`` /
    ``build_inbox``) never calls ``config.runner`` at all. Folding census
    into the mandatory startup pre-compose would mean EVERY server
    construction — including the many existing tests that never call
    ``/api/state`` — records calls against that test's own narrowly-scoped
    ``FakeRunner`` (real hosts have claude/codex/cursor-agent installed,
    confirmed via ``shutil.which`` on this checkout's host), silently
    breaking ``runner.calls == []``-style assertions that predate H0 and are
    about an unrelated endpoint. Deferred to first actual demand instead:
    the first authenticated ``/api/state`` call blocks briefly for this
    (matching pre-H0 per-request behavior exactly, once, for that one
    call); every call after reads the cache, and every later background
    refresh recomputes doc + census together as one unit (frozen spec:
    "composed alongside the doc").
    """
    with config.state_lock:
        if "capabilities" in config.state_cache:
            return
    try:
        capabilities = capability.census(runner=config.runner)
    except Exception:  # noqa: BLE001 — never raise into a serving thread
        capabilities = {}
    with config.state_lock:
        config.state_cache.setdefault("capabilities", capabilities)


def _cached_state_snapshot(config: ServerConfig) -> dict[str, Any]:
    """Read the current cache + bookkeeping fields under one lock acquisition
    so a response envelope never mixes fields from two different compositions.

    ``refresh_in_flight`` stays a bool in the envelope (H1 repair, Sol
    review 5000983751 Blocker 2): derived as
    ``state_refreshes_in_flight > 0`` — a background refresh and an
    explicit recompose may now lawfully run concurrently, so the envelope
    reports "something is composing", not a count.
    """
    with config.state_lock:
        return {
            "doc": config.state_cache.get("doc"),
            "capabilities": config.state_cache.get("capabilities") or {},
            "composed_at": config.state_cache.get("composed_at"),
            "refresh_in_flight": config.state_refreshes_in_flight > 0,
            "state_refresh_error": config.state_refresh_error,
        }


# ---------------------------------------------------------------------------
# discovery — candidate surfaces, zero ownership conferred
# ---------------------------------------------------------------------------

def _decode_claude_project_slug(slug: str) -> str:
    """Best-effort reverse of Claude Code's ``/`` -> ``-`` project-dir slug.

    Only trusted when the reconstructed path actually exists on disk;
    otherwise the raw slug is returned unchanged (frozen spec: "decode the
    slug to a path only if trivially derivable, else return the slug").
    """
    if slug.startswith("-"):
        candidate = slug.replace("-", "/")
        if Path(candidate).is_dir():
            return candidate
    return slug


def _claude_code_sessions() -> list[dict[str, Any]]:
    root = Path("~/.claude/projects").expanduser()
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    try:
        project_dirs = list(root.iterdir())
    except OSError:
        return []
    for project_dir in project_dirs:
        if not project_dir.is_dir():
            continue
        decoded = _decode_claude_project_slug(project_dir.name)
        try:
            jsonl_files = list(project_dir.glob("*.jsonl"))
        except OSError:
            continue
        for jsonl_file in jsonl_files:
            try:
                mtime = jsonl_file.stat().st_mtime
            except OSError:
                continue
            entries.append({
                "project_dir": decoded, "session_id": jsonl_file.stem, "mtime": mtime,
            })
    entries.sort(key=lambda e: e["mtime"], reverse=True)
    return entries[:_DISCOVER_CAP]


def _codex_sessions() -> list[dict[str, Any]]:
    root = Path("~/.codex/sessions").expanduser()
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    try:
        year_dirs = sorted((d for d in root.iterdir() if d.is_dir()), reverse=True)
    except OSError:
        return []
    for year_dir in year_dirs:
        try:
            month_dirs = sorted((d for d in year_dir.iterdir() if d.is_dir()), reverse=True)
        except OSError:
            continue
        for month_dir in month_dirs:
            try:
                day_dirs = sorted((d for d in month_dir.iterdir() if d.is_dir()), reverse=True)
            except OSError:
                continue
            for day_dir in day_dirs:
                date_str = f"{year_dir.name}-{month_dir.name}-{day_dir.name}"
                try:
                    files = sorted(day_dir.iterdir())
                except OSError:
                    continue
                for f in files:
                    if f.is_file():
                        entries.append({"session_id": f.stem, "date": date_str})
            if len(entries) >= _DISCOVER_CAP:
                break
        if len(entries) >= _DISCOVER_CAP:
            break
    return entries[:_DISCOVER_CAP]


def _discover_document(config: ServerConfig) -> dict[str, Any]:
    """Zero-write candidate-surface census. Confers zero ownership/binding."""
    return {
        "chatgpt_environments": chatgpt.list_local_environments(
            mlx_profiles_root=config.mlx_profiles_root, gologin_profiles_root=config.gologin_profiles_root,
        ),
        "claude_code_sessions": _claude_code_sessions(),
        "codex_sessions": _codex_sessions(),
        "cursor": {
            "supported": False,
            "note": (
                "Cursor native thread discovery is not built in P0 (architecture "
                "§6.3/§21 Wave B); locate the thread in Cursor's own UI, then bind "
                "it manually."
            ),
        },
    }


# ---------------------------------------------------------------------------
# static assets — explicit closed map, never a filesystem path built from
# request input
# ---------------------------------------------------------------------------

def _static_assets(static_dir: Path) -> dict[str, tuple[Path, str]]:
    return {
        "index.html": (static_dir / "index.html", "text/html; charset=utf-8"),
        "control_room.js": (static_dir / "control_room.js", "application/javascript; charset=utf-8"),
        "control_room.css": (static_dir / "control_room.css", "text/css; charset=utf-8"),
    }


#: Fixed request-path -> static-asset-name map. A request path that is not a
#: literal key here NEVER reaches the filesystem via this route.
_STATIC_NAME_BY_PATH = {
    "/": "index.html",
    "/static/control_room.js": "control_room.js",
    "/static/control_room.css": "control_room.css",
}


# ---------------------------------------------------------------------------
# security gates
# ---------------------------------------------------------------------------

def _client_is_loopback(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def _host_allowed(host_header: str | None, port: int) -> bool:
    if not host_header:
        return False
    parsed = urlsplit("//" + host_header)
    hostname = (parsed.hostname or "").lower()
    if hostname not in _ALLOWED_HOSTNAMES:
        return False
    if parsed.port is not None and parsed.port != port:
        return False
    return True


# ---------------------------------------------------------------------------
# request handler
# ---------------------------------------------------------------------------

class ChairmanControlRoomHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ChairmanControlRoom/1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # local single-operator tool; keep stdout to the one startup line

    # -- shared response helpers -------------------------------------------------

    def _common_headers(self, *, content_type: str, length: int, csp: bool = False, no_store: bool = False) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        if csp:
            self.send_header("Content-Security-Policy", _CSP)
        if no_store:
            self.send_header("Cache-Control", "no-store")

    def _write(self, status: int, body: bytes, *, content_type: str, csp: bool = False, no_store: bool = False) -> None:
        try:
            self.send_response(status)
            self._common_headers(content_type=content_type, length=len(body), csp=csp, no_store=no_store)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, status: int, payload: Any, *, no_store: bool = False) -> None:
        self._write(status, json.dumps(payload).encode("utf-8"), content_type="application/json", no_store=no_store)

    def _forbidden(self, detail: str) -> None:
        self._send_json(403, {"error": "forbidden", "detail": detail}, no_store=True)

    def _not_found(self) -> None:
        self._send_json(404, {"error": "not_found"}, no_store=True)

    def _bad_request(self, detail: str) -> None:
        self._send_json(400, {"error": "bad_request", "detail": detail}, no_store=True)

    # -- security ------------------------------------------------------------

    def _loopback_and_host_ok(self) -> bool:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        if not _client_is_loopback(self.client_address[0]):
            self._forbidden("client address is not loopback")
            return False
        if not _host_allowed(self.headers.get("Host"), config.port):
            self._forbidden("Host header not allowed")
            return False
        return True

    def _api_auth_ok(self) -> bool:
        """Browser-origin nonce check shared by every mutating POST and by
        the two read GET endpoints that expose full org state
        (``/api/state``, ``/api/discover`` — F4/H0 hardening, 2026-08-22).
        ``X-CCR-Token`` is a per-process browser-origin capability nonce —
        cross-site/CSRF defense, NOT local-process authentication (H1
        repair, Sol review 5000983751 Blocker 1; see the module docstring
        for the full threat-boundary statement). Static assets and the
        index page stay token-free (the index page is what DELIVERS the
        token to the browser in the first place) — this method is never
        called on that path.
        """
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        token = self.headers.get("X-CCR-Token")
        if token != config.token:
            self._forbidden("missing or invalid X-CCR-Token")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != config.origin:
            self._forbidden("Origin header does not match this server's own origin")
            return False
        return True

    def _read_json_body(self) -> tuple[dict | None, str | None]:
        length_header = self.headers.get("Content-Length")
        try:
            length = int(length_header) if length_header is not None else 0
        except ValueError:
            return None, "invalid Content-Length"
        if length < 0 or length > _MAX_BODY_BYTES:
            return None, "request body exceeds 64 KiB"
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}, None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, "request body is not valid JSON"
        if not isinstance(data, dict):
            return None, "request body must be a JSON object"
        return data, None

    # -- GET -------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if not self._loopback_and_host_ok():
            return
        path = urlsplit(self.path).path

        static_name = _STATIC_NAME_BY_PATH.get(path)
        if static_name == "index.html":
            return self._serve_index()
        if static_name is not None:
            return self._serve_static(static_name)
        if path == "/favicon.ico":
            self.send_response(204)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return
        if path == "/api/state":
            if not self._api_auth_ok():
                return
            return self._handle_state()
        if path == "/api/discover":
            if not self._api_auth_ok():
                return
            return self._handle_discover()
        self._not_found()

    def _serve_index(self) -> None:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        file_path, _mime = _static_assets(config.static_dir)["index.html"]
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            return self._not_found()
        body = content.replace("__CCR_TOKEN__", config.token).encode("utf-8")
        self._write(200, body, content_type="text/html; charset=utf-8", csp=True)

    def _serve_static(self, name: str) -> None:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        file_path, mime = _static_assets(config.static_dir)[name]
        try:
            body = file_path.read_bytes()
        except OSError:
            return self._not_found()
        self._write(200, body, content_type=mime)

    def _handle_state(self) -> None:
        """Serve the cached composition immediately (H0 hardening, 2026-08-22
        — F1/F5). A stale cache kicks at most one background recompose
        (single-flight) and this request still returns the last good doc —
        it never blocks on a fresh composition. ``capability.census`` moved
        into the cached composition work, so an authenticated GET against a
        warm cache does zero subprocess work. ``live_builds_active`` is
        computed live off ``config.live_cache`` (unchanged semantics — a
        cheap dict lookup, not part of the composition cache).
        """
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        _ensure_capabilities_cached(config)
        _maybe_start_background_refresh(config)
        snapshot = _cached_state_snapshot(config)
        body = {
            "control_room": snapshot["doc"],
            "capabilities": snapshot["capabilities"],
            "live_builds_active": config.live_cache.get("active_builds") is not None,
            "composed_at": snapshot["composed_at"],
            "refresh_in_flight": snapshot["refresh_in_flight"],
            "state_refresh_error": snapshot["state_refresh_error"],
        }
        self._send_json(200, body, no_store=True)

    def _handle_discover(self) -> None:
        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        self._send_json(200, _discover_document(config), no_store=True)

    # -- POST ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        if not self._loopback_and_host_ok():
            return
        if not self._api_auth_ok():
            return
        path = urlsplit(self.path).path
        if path == "/api/open":
            return self._handle_open()
        if path == "/api/bind":
            return self._handle_bind()
        if path == "/api/unbind":
            return self._handle_unbind()
        if path == "/api/refresh-builds":
            return self._handle_refresh_builds()
        self._not_found()

    def _handle_open(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, {"binding_id"})
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")
        binding_id = data.get("binding_id")
        if not isinstance(binding_id, str) or not binding_id:
            return self._bad_request("binding_id: required (non-empty string)")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        doc, problems = sb.load_bindings(config.bindings_path)
        if doc is None:
            if problems:
                outcome = contract.refused(
                    "unknown", binding_id, "invalid_binding", "the bindings file failed validation"
                )
            else:
                outcome = contract.refused(
                    "unknown", binding_id, "not_found", "no bindings file is present"
                )
            return self._send_json(200, outcome, no_store=True)

        binding = next(
            (row for row in doc.get("bindings", []) if isinstance(row, dict) and row.get("binding_id") == binding_id),
            None,
        )
        if binding is None:
            outcome = contract.refused("unknown", binding_id, "not_found", "no binding with this id exists")
            return self._send_json(200, outcome, no_store=True)

        outcome = config.open_binding_fn(
            binding, config.runner,
            claude_projects_dir=config.claude_projects_dir,
            codex_sessions_dir=config.codex_sessions_dir,
            mlx_profiles_root=config.mlx_profiles_root,
            gologin_profiles_root=config.gologin_profiles_root,
        )
        # last_verified_at / VERIFIED_OPENABLE law (Sol review 5000169412,
        # blocker 2): a mere Terminal-launch ACK must never advance this —
        # only an outcome that PROVED the provider-native session/tab exists
        # (contract.OpenOutcome.verified=True) may. `ok=True, verified=False`
        # (chatgpt / claude_desktop / cursor_agent — no proven local read
        # surface) stays BOUND_UNVERIFIED and leaves the bindings file
        # byte-unchanged.
        if outcome.get("ok") and outcome.get("verified"):
            now = config.now_fn()
            for row in doc["bindings"]:
                if isinstance(row, dict) and row.get("binding_id") == binding_id:
                    row["last_verified_at"] = now
            sb.save_bindings(doc, config.bindings_path)
        self._send_json(200, outcome, no_store=True)

    _BIND_ALLOWED_KEYS = frozenset({"work_ref", "role", "provider", "seat_ref", "locator"})

    def _handle_bind(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, self._BIND_ALLOWED_KEYS)
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")

        work_ref = data.get("work_ref")
        role = data.get("role")
        provider = data.get("provider")
        seat_ref = data.get("seat_ref")
        locator = data.get("locator")

        if not isinstance(work_ref, str) or not isinstance(role, str) or not isinstance(provider, str):
            return self._bad_request("work_ref, role, and provider must be strings")
        if not isinstance(locator, dict):
            return self._bad_request("locator must be an object")
        if seat_ref is not None and not isinstance(seat_ref, str):
            return self._bad_request("seat_ref must be a string or null")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        # sb._PROVIDER_LOCATOR_KIND is the same module's own provider->kind
        # map — reused, not re-derived, so a new provider added there never
        # needs a matching edit here. An unknown provider maps to itself,
        # which validate_bindings_document then names as a "must be one of"
        # problem — never a crash.
        locator_kind = sb._PROVIDER_LOCATOR_KIND.get(provider, provider)
        binding = sb.new_binding(
            work_ref=work_ref, role=role, provider=provider, locator_kind=locator_kind,
            locator=locator, observed_at=config.now_fn(), seat_ref=seat_ref,
        )

        existing_doc, load_problems = sb.load_bindings(config.bindings_path)
        if existing_doc is None and load_problems:
            return self._send_json(200, {"ok": False, "problems": load_problems}, no_store=True)
        if existing_doc is None:
            existing_doc = {"schema": sb.SCHEMA, "bindings": []}

        new_doc = {
            "schema": existing_doc.get("schema", sb.SCHEMA),
            "bindings": list(existing_doc.get("bindings", [])) + [binding],
        }
        problems = sb.validate_bindings_document(new_doc)
        if problems:
            return self._send_json(200, {"ok": False, "problems": problems}, no_store=True)

        sb.save_bindings(new_doc, config.bindings_path)
        self._send_json(200, {"ok": True, "binding_id": binding["binding_id"]}, no_store=True)

    def _handle_unbind(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, {"binding_id"})
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")
        binding_id = data.get("binding_id")
        if not isinstance(binding_id, str) or not binding_id:
            return self._bad_request("binding_id: required (non-empty string)")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        doc, _problems = sb.load_bindings(config.bindings_path)
        if doc is None:
            return self._send_json(200, {"ok": False}, no_store=True)

        rows = doc.get("bindings", [])
        remaining = [r for r in rows if not (isinstance(r, dict) and r.get("binding_id") == binding_id)]
        if len(remaining) == len(rows):
            return self._send_json(200, {"ok": False}, no_store=True)

        new_doc = {"schema": doc.get("schema", sb.SCHEMA), "bindings": remaining}
        sb.save_bindings(new_doc, config.bindings_path)
        self._send_json(200, {"ok": True}, no_store=True)

    def _handle_refresh_builds(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._bad_request(err)
        unknown = _unknown_key(data, set())
        if unknown is not None:
            return self._bad_request(f"unknown key: {unknown!r}")

        config: ServerConfig = self.server.config  # type: ignore[attr-defined]
        macro_root = config.macro_root
        if not macro_root:
            return self._send_json(200, {"ok": False, "detail": "no macro root resolved"}, no_store=True)

        script_path = Path(macro_root) / "scripts" / "build_project_active_build_map.py"
        if not script_path.is_file():
            return self._send_json(
                200,
                {"ok": False, "detail": "--json-stdout seam not present at macro root"},
                no_store=True,
            )

        argv = [sys.executable, str(script_path), "--json-stdout"]
        # 4 MiB, not the runner's default 64 KiB — the real project_active_
        # builds.v1 document is real organizational data (Wave D live proof:
        # 112,569 bytes) and must never be silently truncated below valid
        # JSON. See _REFRESH_BUILDS_MAX_OUTPUT_BYTES's docstring.
        result = config.runner(
            argv, timeout=_REFRESH_BUILDS_TIMEOUT, cwd=macro_root, max_bytes=_REFRESH_BUILDS_MAX_OUTPUT_BYTES
        )

        if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
            stderr_tail = ""
            if isinstance(result, dict):
                stderr_tail = (result.get("stderr") or "")[-2000:]
            detail = f"build_project_active_build_map.py failed: {stderr_tail}".rstrip(": ")
            return self._send_json(200, {"ok": False, "detail": detail}, no_store=True)

        stdout = result.get("stdout") or ""
        try:
            parsed = json.loads(stdout)
        except ValueError:
            return self._send_json(200, {"ok": False, "detail": "stdout was not valid JSON"}, no_store=True)
        if not isinstance(parsed, dict) or parsed.get("schema") != "project_active_builds.v1":
            return self._send_json(
                200, {"ok": False, "detail": "stdout schema was not project_active_builds.v1"}, no_store=True
            )

        config.live_cache["active_builds"] = parsed
        # H0 hardening (2026-08-22): GET /api/state now serves a cache, not
        # a fresh composition per request — but this ONE write path (a live
        # active-builds refresh) must still be visible on the very next GET,
        # not eventually-consistent up to state_ttl. Recompose synchronously
        # here, once, rather than leaving the cache stamped with whatever
        # was true before this refresh. refresh-builds is already an
        # explicit, infrequent, user-initiated action with its own 180s
        # subprocess timeout; this costs the same gather-layer time GET
        # /api/state used to pay on every request, but only for this action.
        # H1 repair (Sol review 5000983751 Blocker 2): reserve this as an
        # EXPLICIT generation — it raises state_explicit_floor, so an older
        # background recompose that finishes after this one may never
        # overwrite it.
        gen = _reserve_composition(config, explicit=True)
        _refresh_state_cache(config, timeout=config.compose_timeout, generation=gen, include_capabilities=True)
        self._send_json(200, {"ok": True, "collected_at": parsed.get("collected_at")}, no_store=True)


class ControlRoomServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler_cls: type, config: ServerConfig) -> None:
        self.config = config
        super().__init__(server_address, handler_cls)
        # H0 hardening (2026-08-22, F1): compose once, synchronously, before
        # this constructor returns — i.e. before any caller can start
        # accepting requests via serve_forever(). Never reached from
        # --check (run_check never constructs this class).
        _precompose_initial_state(config)


# ---------------------------------------------------------------------------
# --check mode
# ---------------------------------------------------------------------------

def run_check(config: ServerConfig) -> int:
    """Build one control-room document + capability census; print a compact
    summary (schema, counts, degraded list, capability states) with NO
    urls/session ids anywhere in the output. Always exits 0 — this is the
    operator smoke command, not a correctness gate.
    """
    doc = _compose_state_doc(config)
    capabilities = capability.census(runner=config.runner)

    print(f"schema: {doc['schema']}")
    print(f"generated_at: {doc['generated_at']}")
    print(f"work cards: {len(doc['work'])}")
    print(f"unjoined_open_prs: {len(doc['unjoined_open_prs'])}")
    print(f"unbound_surfaces: {len(doc['unbound_surfaces'])}")
    print(f"binding_conflicts: {len(doc['binding_conflicts'])}")
    attention = doc["attention"]
    print(
        "attention: chairman={0} ceo={1} coo={2}".format(
            len(attention.get("chairman", [])), len(attention.get("ceo", [])), len(attention.get("coo", []))
        )
    )
    # CAP-C1 (reviewer m-9): one line when a placement_selection section is
    # actually present; a degraded marker when the flag was given but the
    # section came back None (the failure detail itself lives in the
    # `degraded` list printed below, never repeated here). No line at all
    # when the flag was never given — this stays exactly as quiet as every
    # other never-asked-for optional feature.
    placement_selection = doc.get("placement_selection")
    if placement_selection is not None:
        selected = placement_selection.get("selected")
        tied = placement_selection.get("tied_worker_ids") or []
        if selected is not None:
            detail = f"selected={selected.get('worker_id')}"
        elif tied:
            detail = f"abstained, tied={len(tied)}"
        else:
            detail = "no selection"
        print(f"placement_selection: state={placement_selection.get('state')} {detail}")
    elif config.placement_selection_path:
        print("placement_selection: degraded (see degraded list)")
    if doc["degraded"]:
        print("degraded:")
        for entry in doc["degraded"]:
            print(f"  - {entry}")
    else:
        print("degraded: none")
    print("capabilities:")
    for name in sorted(capabilities):
        print(f"  {name}: {capabilities[name].get('state')}")
    return 0


# ---------------------------------------------------------------------------
# CLI / process lifecycle
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Chairman Control Room P0 — loopback-only local presentation "
            "process. No canonical writes; the only disk write anywhere in "
            "this process is the atomic surface-bindings save."
        ),
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    parser.add_argument("--repo-root", default=None, help="Mastermind checkout root (default: this repo)")
    parser.add_argument("--macro-root", default=None, help="Macro checkout root (default: auto-resolved)")
    parser.add_argument("--bindings-path", default=None, help="surface_bindings.json path (default: platform default)")
    parser.add_argument(
        "--placement-selection", default=None,
        help="CAP-C1: path to a placement-selection facts document (default: no placement_selection "
             "section composed)",
    )
    parser.add_argument("--open", action="store_true", help="open the Control Room URL after startup")
    parser.add_argument("--check", action="store_true", help="build one document + capability census, print, exit 0")
    parser.add_argument(
        "--compose-timeout", type=float, default=240.0,
        help="timeout (seconds) for a cache-populating composition — startup pre-compose and every "
             "background recompose (default 240; --check is unaffected, it always uses the library's "
             "own 60s default)",
    )
    parser.add_argument(
        "--state-ttl", type=float, default=120.0,
        help="cache max-age (seconds) before a GET /api/state kicks a background recompose (default 120)",
    )
    return parser


def _build_config(args: argparse.Namespace) -> ServerConfig:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else _REPO_ROOT
    macro_root = _resolve_macro_root_simple(args.macro_root, os.environ, repo_root)
    bindings_path = Path(args.bindings_path).expanduser() if args.bindings_path else None
    placement_selection_path = (
        Path(args.placement_selection).expanduser() if args.placement_selection else None
    )
    token = secrets.token_urlsafe(32)
    return ServerConfig(
        repo_root=repo_root,
        macro_root=macro_root,
        bindings_path=bindings_path,
        placement_selection_path=placement_selection_path,
        token=token,
        origin=f"http://{HOST}:{args.port}",
        port=args.port,
        static_dir=DEFAULT_STATIC_DIR,
        compose_timeout=args.compose_timeout,
        state_ttl=args.state_ttl,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = _build_config(args)

    if args.check:
        return run_check(config)

    httpd = ControlRoomServer((HOST, args.port), ChairmanControlRoomHandler, config)
    bound_ip, bound_port = httpd.server_address[0], httpd.server_address[1]
    assert ipaddress.ip_address(bound_ip).is_loopback, "refusing to serve on a non-loopback bind"

    config.port = bound_port
    config.origin = f"http://{HOST}:{bound_port}"
    url = f"http://{HOST}:{bound_port}/"
    print(f"{url} — loopback-only; no canonical writes; Ctrl-C to stop.")

    if args.open:
        try:
            subprocess.run(["/usr/bin/open", url], check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _sigint_handler(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
