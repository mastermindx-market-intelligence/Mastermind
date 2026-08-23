"""integrations.chairman_surfaces.nonseat_canary — MAS-115 / P0B-C0 disposable non-seat canary.

Governed by ``DEC:CCR-P0B-AUTOMATION-OWNED-NONSEAT-CANARY-ONLY``: this module
proves a bounded, disposable, vendor-supported (GoLogin/Multilogin) managed-
browser lifecycle — exact-profile launch, exact benign-URL navigation,
same-owner reuse, state persistence, and every refusal state — while being
structurally INCAPABLE of ever addressing a real Chairman seat.

This module NEVER addresses a Chairman seat. It only ever operates against a
profile explicitly provisioned as disposable (``disposable_ack`` must equal
:data:`REQUIRED_ACK` exactly) and a benign loopback origin; it refuses closed
wherever a supported vendor path is absent, wherever the target is not the
provisioned benign origin, and wherever the provisioned profile collides with
any known ``chatgpt`` seat binding in :mod:`control_plane.surface_bindings`.

Credential law
--------------
A credential's raw value is never placed in argv, an environment variable, a
log line, a receipt, or an exception message. :class:`Credential` exposes it
only via :meth:`Credential.expose`; every other surface of this module —
``repr``/``str``, :class:`CanaryRefusal`, and every receipt row emitted by
:func:`run_matrix` — carries only fixed static detail sentences plus
digests, booleans, counts, and timestamps.

Receipt law
-----------
Receipts carry only fixed static detail sentences (:data:`DETAILS`) plus
digests (:func:`sha256_hex`), booleans, counts, and timestamps — never a raw
URL, profile id, credential value, or vendor payload. :func:`audit_receipts`
is the row that proves this about every row that ran before it.

Foreground/focus law
---------------------
Foreground/focus observation (``focus_probe`` in :func:`run_matrix`) is
OBSERVATION_ONLY. It is recorded for visibility and never contributes to any
row's ``ok`` value or to the overall verdict.

Determinism law
----------------
This module performs no network I/O, imports no ``subprocess``, and reads no
clock inside any library function — only the CLI :func:`main` at the bottom
of this file reads the clock (to build the ``clock`` callable passed into
:func:`run_matrix` for a live run) or touches the network (indirectly, via
:mod:`integrations.chairman_surfaces.nonseat_canary_vendors`, imported lazily
inside ``main`` so this module stays import-clean).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from control_plane import surface_bindings as _surface_bindings

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

RESULT_CODES = frozenset({
    "OK",
    "PROVISION_MISSING",
    "DISALLOWED_TARGET",
    "PROFILE_NOT_FOUND",
    "AUTH_MISSING",
    "AUTH_EXPIRED",
    "BUSY_PROFILE",
    "UNOWNED_RUNNING_PROFILE",
    "UNSUPPORTED_SURFACE",
    "AUTH_REQUIRED_TARGET",
    "LAUNCH_FAILED",
    "NAVIGATION_FAILED",
    "STATE_NOT_PRESERVED",
    "RECEIPT_HYGIENE_FAILED",
    "VENDOR_ERROR",
})

PROVISION_SCHEMA = "mastermind.mas115_nonseat_canary_provision.v1"
DEFAULT_PROVISION_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_canary.json"
REQUIRED_ACK = "disposable-non-chairman-profile"
RECEIPTS_SCHEMA = "mastermind.mas115_nonseat_canary_receipts.v1"

KEYCHAIN_SERVICE_TEMPLATE = "mastermind.mas115.{vendor}.disposable"
KEYCHAIN_ACCOUNT = "mastermind-mas115-canary"
SECURITY_BIN = "/usr/bin/security"

#: The ONLY navigable paths, appended to the provisioned loopback origin.
ALLOWED_PATHS = ("/a", "/b", "/state/set", "/state/check", "/auth")

#: Deliberately-invalid-shaped-but-well-formed ids used only to prove a
#: "not found" refusal without ever touching a real profile.
UNKNOWN_PROFILE_IDS = {
    "gologin": "ffffffffffffffffffffffff",
    "multilogin": "ffffffff-ffff-4fff-8fff-ffffffffffff",
}

#: Fixed static sentence per result code. Receipts and exceptions may only
#: ever carry these exact strings — never an interpolated id, url, port,
#: exception text, or vendor payload.
DETAILS = {
    "OK": "the canary step completed as expected.",
    "PROVISION_MISSING": "no valid disposable non-seat canary provision was found.",
    "DISALLOWED_TARGET": "the requested target is not an allowed loopback benign-origin path.",
    "PROFILE_NOT_FOUND": "the vendor reports no such disposable profile.",
    "AUTH_MISSING": "no disposable canary credential is available.",
    "AUTH_EXPIRED": "the disposable canary credential was rejected as expired or invalid.",
    "BUSY_PROFILE": "the disposable profile is already owned or already running.",
    "UNOWNED_RUNNING_PROFILE": "a running profile exists that this actuator does not own.",
    "UNSUPPORTED_SURFACE": "no supported vendor surface exists for this operation.",
    "AUTH_REQUIRED_TARGET": "the target requires authentication this actuator does not attempt.",
    "LAUNCH_FAILED": "the vendor did not launch the disposable profile as requested.",
    "NAVIGATION_FAILED": "the navigator did not confirm the requested navigation.",
    "STATE_NOT_PRESERVED": "the disposable profile did not preserve state across a close and reopen.",
    "RECEIPT_HYGIENE_FAILED": "a receipt failed the hygiene scan for forbidden content.",
    "VENDOR_ERROR": "the vendor surface returned an unexpected or malformed result.",
}

if set(DETAILS.keys()) != RESULT_CODES:
    # An `assert` here would be stripped by `python -O`; this invariant must
    # hold even in an optimized interpreter.
    raise RuntimeError("nonseat_canary: DETAILS keys must exactly match RESULT_CODES")


# ---------------------------------------------------------------------------
# refusal + credential
# ---------------------------------------------------------------------------


class CanaryRefusal(Exception):
    """A typed, closed-vocabulary refusal. Never carries dynamic text."""

    def __init__(self, code: str):
        if code not in RESULT_CODES:
            raise ValueError(f"unknown canary result code: {code!r}")
        self.code = code
        self.detail = DETAILS[code]
        super().__init__(self.detail)


class Credential:
    """A credential holder that never leaks its value via repr/str.

    ``source`` is one of ``"stdin"``, ``"keychain"``, ``"absent"``.
    """

    __slots__ = ("_value", "source")

    def __init__(self, value, source: str):
        if source not in ("stdin", "keychain", "absent"):
            raise ValueError(f"unknown credential source: {source!r}")
        self._value = value if isinstance(value, str) and value else None
        self.source = source

    @property
    def present(self) -> bool:
        return self._value is not None

    def expose(self):
        """Return the raw credential value, or ``None``. Never logged by this module."""
        return self._value

    def __repr__(self) -> str:
        return f"<mas115-credential source={self.source} present={self.present}>"

    __str__ = __repr__


def resolve_credential(*, vendor: str, stdin_text=None, keychain_reader=None) -> Credential:
    """Resolve a disposable canary credential. Never raises.

    Stripped nonempty ``stdin_text`` wins (source ``"stdin"``); else
    ``keychain_reader()`` (a zero-arg callable returning ``str | None``,
    whose exceptions degrade to ``None`` and are never logged) as source
    ``"keychain"``; else an absent :class:`Credential`.
    """
    del vendor  # scoping is baked into the injected keychain_reader by the caller
    if isinstance(stdin_text, str):
        stripped = stdin_text.strip()
        if stripped:
            return Credential(stripped, "stdin")
    if keychain_reader is not None:
        try:
            value = keychain_reader()
        except Exception:  # noqa: BLE001 — a keychain probe failure must never propagate
            value = None
        if isinstance(value, str) and value:
            return Credential(value, "keychain")
    return Credential(None, "absent")


# ---------------------------------------------------------------------------
# provision
# ---------------------------------------------------------------------------

_PROVISION_ALLOWED_KEYS = frozenset({"schema", "vendor", "profile_id", "folder_id", "benign_origin", "disposable_ack"})
_PROVISION_REQUIRED_KEYS_BASE = frozenset({"schema", "vendor", "profile_id", "benign_origin", "disposable_ack"})
_MAX_PROVISION_BYTES = 64 * 1024
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def load_provision(path=None, *, bindings_loader=None):
    """Load and validate the disposable canary provision file.

    Returns ``(provision_dict, None)`` on success, or ``(None, code)`` where
    ``code`` is one of ``"PROVISION_MISSING"`` / ``"DISALLOWED_TARGET"``.
    Never raises.
    """
    loader = bindings_loader if bindings_loader is not None else _surface_bindings.load_bindings

    target = Path(path).expanduser() if path else Path(DEFAULT_PROVISION_PATH).expanduser()

    try:
        if not target.is_file():
            return None, "PROVISION_MISSING"
        if target.stat().st_size > _MAX_PROVISION_BYTES:
            return None, "PROVISION_MISSING"
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return None, "PROVISION_MISSING"

    try:
        doc = json.loads(raw)
    except ValueError:
        return None, "PROVISION_MISSING"

    if not isinstance(doc, dict):
        return None, "PROVISION_MISSING"
    if set(doc.keys()) - _PROVISION_ALLOWED_KEYS:
        return None, "PROVISION_MISSING"
    if doc.get("schema") != PROVISION_SCHEMA:
        return None, "PROVISION_MISSING"

    vendor = doc.get("vendor")
    if vendor not in ("gologin", "multilogin"):
        return None, "PROVISION_MISSING"

    required = _PROVISION_REQUIRED_KEYS_BASE | ({"folder_id"} if vendor == "multilogin" else set())
    if not required.issubset(doc.keys()):
        return None, "PROVISION_MISSING"

    if vendor == "multilogin":
        folder_id = doc.get("folder_id")
        if not isinstance(folder_id, str) or not _surface_bindings.UUID_RE.match(folder_id):
            return None, "PROVISION_MISSING"
        profile_id = doc.get("profile_id")
        if not isinstance(profile_id, str) or not _surface_bindings.UUID_RE.match(profile_id):
            return None, "PROVISION_MISSING"
        # Canonicalize to lowercase so a case-varied id can never dodge the
        # seat-collision comparison below or downstream vendor lookups.
        profile_id = profile_id.lower()
        folder_id = folder_id.lower()
        doc["profile_id"] = profile_id
        doc["folder_id"] = folder_id
    else:  # gologin
        if "folder_id" in doc:
            return None, "PROVISION_MISSING"
        profile_id = doc.get("profile_id")
        if not isinstance(profile_id, str) or not _surface_bindings.GOLOGIN_PROFILE_ID_RE.match(profile_id):
            return None, "PROVISION_MISSING"

    if doc.get("disposable_ack") != REQUIRED_ACK:
        return None, "PROVISION_MISSING"

    benign_origin = doc.get("benign_origin")
    if not isinstance(benign_origin, str) or not benign_origin:
        return None, "DISALLOWED_TARGET"
    parsed = urlsplit(benign_origin)
    if parsed.scheme not in ("http", "https"):
        return None, "DISALLOWED_TARGET"
    if parsed.username or parsed.password:
        return None, "DISALLOWED_TARGET"
    if parsed.path or parsed.query or parsed.fragment:
        return None, "DISALLOWED_TARGET"
    if (parsed.hostname or "") not in _LOOPBACK_HOSTS:
        return None, "DISALLOWED_TARGET"

    # Seat-collision guard: fail closed if we cannot prove non-collision.
    try:
        collision_doc, problems = loader()
    except Exception:  # noqa: BLE001 — cannot prove non-collision, fail closed
        return None, "DISALLOWED_TARGET"

    if collision_doc is None:
        if problems:
            return None, "DISALLOWED_TARGET"
        # (None, []) — bindings file absent -> no collision possible.
    else:
        for binding in (collision_doc.get("bindings") or []):
            if not isinstance(binding, dict):
                continue
            if binding.get("provider") != "chatgpt":
                continue
            locator = binding.get("locator")
            if not isinstance(locator, dict):
                continue
            bound_profile_id = locator.get("profile_id")
            if isinstance(bound_profile_id, str) and bound_profile_id.lower() == str(profile_id).lower():
                return None, "DISALLOWED_TARGET"

    return doc, None


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_disposable(provision) -> None:
    """Defense-in-depth gate: never trust a caller-supplied ``provision``
    dict at face value. Raises :class:`CanaryRefusal` (``DISALLOWED_TARGET``)
    unless ``provision`` is a dict carrying the exact disposable ack AND a
    benign loopback-only origin (http/https, no credentials, no path/query/
    fragment, hostname in :data:`_LOOPBACK_HOSTS`)."""
    if not isinstance(provision, dict):
        raise CanaryRefusal("DISALLOWED_TARGET")
    if provision.get("disposable_ack") != REQUIRED_ACK:
        raise CanaryRefusal("DISALLOWED_TARGET")
    origin = provision.get("benign_origin")
    if not isinstance(origin, str) or not origin:
        raise CanaryRefusal("DISALLOWED_TARGET")
    parsed = urlsplit(origin)
    if parsed.scheme not in ("http", "https"):
        raise CanaryRefusal("DISALLOWED_TARGET")
    if parsed.username or parsed.password:
        raise CanaryRefusal("DISALLOWED_TARGET")
    if parsed.path or parsed.query or parsed.fragment:
        raise CanaryRefusal("DISALLOWED_TARGET")
    if (parsed.hostname or "") not in _LOOPBACK_HOSTS:
        raise CanaryRefusal("DISALLOWED_TARGET")


def allowed_url(provision: dict, url) -> bool:
    """True iff ``url`` is exactly the provisioned benign origin plus one of
    :data:`ALLOWED_PATHS`, AND that origin's hostname is loopback."""
    origin = provision.get("benign_origin") if isinstance(provision, dict) else None
    if not isinstance(origin, str) or not isinstance(url, str):
        return False
    if (urlsplit(origin).hostname or "") not in _LOOPBACK_HOSTS:
        return False
    return any(url == origin + suffix for suffix in ALLOWED_PATHS)


def audit_receipts(rows, forbidden_values) -> bool:
    """Return ``True`` iff no receipt string in ``rows`` contains a forbidden
    value or a raw URL / ``--user-data-dir`` token."""
    forbidden = [v for v in forbidden_values if isinstance(v, str) and v]

    def _scan(node) -> bool:
        if isinstance(node, str):
            if "--user-data-dir" in node or "://" in node:
                return True
            return any(bad in node for bad in forbidden)
        if isinstance(node, dict):
            return any(_scan(v) for v in node.values())
        if isinstance(node, list):
            return any(_scan(v) for v in node)
        return False

    return not any(_scan(row) for row in rows)


# ---------------------------------------------------------------------------
# actuator
# ---------------------------------------------------------------------------


class NonSeatCanaryActuator:
    """A one-profile, one-owner disposable non-seat browser actuator.

    Public surface EXACTLY: :meth:`acquire`, :meth:`navigate`,
    :meth:`release`, :meth:`drop_ownership`, and the :attr:`owned` property.
    Everything else is private.
    """

    def __init__(self, *, vendor_client, navigator, provision: dict, credential: Credential):
        assert_disposable(provision)  # never trust the provision dict; verify before storing anything
        self._vendor_client = vendor_client
        self._navigator = navigator
        self._provision = provision
        self._credential = credential
        self._owned = None  # {"profile_key": str, "port": int} | None

        profile_ref = {"profile_id": provision.get("profile_id")}
        if "folder_id" in provision:
            profile_ref["folder_id"] = provision.get("folder_id")
        self._profile_ref = profile_ref

    @property
    def owned(self) -> bool:
        return self._owned is not None

    @property
    def _port(self):
        return self._owned["port"] if self._owned else None

    def acquire(self) -> None:
        if not self._credential.present:
            raise CanaryRefusal("AUTH_MISSING")
        if self._owned is not None:
            raise CanaryRefusal("BUSY_PROFILE")

        vendor_error = False
        result = None
        try:
            exists = self._vendor_client.profile_exists(self._profile_ref)
            if not exists:
                raise CanaryRefusal("PROFILE_NOT_FOUND")
            running = self._vendor_client.is_running_externally(self._profile_ref)
            if running:
                # A browser some other owner started is NEVER adopted.
                raise CanaryRefusal("BUSY_PROFILE")
            result = self._vendor_client.start(self._profile_ref)
        except CanaryRefusal:
            raise
        except Exception:  # noqa: BLE001 — any other vendor exception is laundered
            vendor_error = True
        if vendor_error:
            # Raised OUTSIDE the except block (not `raise ... from exc`/bare
            # re-raise inside the handler) so CPython never auto-chains the
            # laundered exception onto __context__ — `from None` alone only
            # suppresses __cause__/traceback display, not __context__ itself.
            raise CanaryRefusal("VENDOR_ERROR") from None

        if not isinstance(result, dict) or result.get("profile_id") != self._provision.get("profile_id"):
            # Identity-echo gate: a vendor answering with any other profile is
            # refused, never adopted.
            raise CanaryRefusal("VENDOR_ERROR")
        port = result.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
            raise CanaryRefusal("VENDOR_ERROR")

        self._owned = {"profile_key": self._profile_ref.get("profile_id"), "port": port}

    def navigate(self, url: str) -> None:
        if not allowed_url(self._provision, url):
            raise CanaryRefusal("DISALLOWED_TARGET")

        if self._owned is None:
            vendor_error = False
            running = False
            try:
                running = self._vendor_client.is_running_externally(self._profile_ref)
            except CanaryRefusal:
                raise
            except Exception:  # noqa: BLE001
                vendor_error = True
            if vendor_error:
                raise CanaryRefusal("VENDOR_ERROR") from None  # see acquire(): context severed by construction
            if running:
                raise CanaryRefusal("UNOWNED_RUNNING_PROFILE")
            raise CanaryRefusal("UNSUPPORTED_SURFACE")

        vendor_error = False
        ok = False
        try:
            ok = self._navigator.open_url(self._owned["port"], url)
        except CanaryRefusal:
            raise
        except Exception:  # noqa: BLE001
            vendor_error = True
        if vendor_error:
            raise CanaryRefusal("VENDOR_ERROR") from None  # see acquire(): context severed by construction
        if not ok:
            raise CanaryRefusal("NAVIGATION_FAILED")

    def release(self) -> None:
        if self._owned is None:
            raise CanaryRefusal("UNSUPPORTED_SURFACE")
        vendor_error = False
        try:
            self._vendor_client.stop(self._profile_ref)
        except CanaryRefusal:
            raise
        except Exception:  # noqa: BLE001
            vendor_error = True
        if vendor_error:
            raise CanaryRefusal("VENDOR_ERROR") from None  # see acquire(): context severed by construction
        self._owned = None

    def drop_ownership(self) -> None:
        """Disposable-environment-only owner-loss simulation for canary row
        C5. Never a recovery mechanism — it never calls the vendor to
        start/stop anything. It DOES tell the vendor client to forget its own
        local ownership bookkeeping (when the client exposes that lever), so
        the client's ``is_running_externally`` correctly reports the profile
        as no-longer-ours rather than mis-attributing it to us forever."""
        self._owned = None
        forget = getattr(self._vendor_client, "forget_ownership", None)
        if forget is not None:
            forget()


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------

_ROW_ORDER = ("C0", "C1", "C2", "C3", "C4", "C8", "C5", "C6", "C7", "C9", "C10")

#: Keys every row already carries — an ``emit(..., **extra)`` caller must
#: never be able to shadow one of these via a colliding extra-field name.
_RESERVED_ROW_KEYS = frozenset({"row", "code", "ok", "detail", "ts"})


def _build_row(row_id, code, ok, ts, /, **extra) -> dict:
    """Build one receipts row. ``row_id``/``code``/``ok``/``ts`` are
    positional-only so a reserved key smuggled into ``extra`` can never
    dodge the check below by colliding with a same-named parameter instead —
    raises ``RuntimeError`` (not silently overwritten) if ``extra`` collides
    with a reserved row key."""
    if _RESERVED_ROW_KEYS & set(extra.keys()):
        raise RuntimeError("nonseat_canary: emit() extra keys collide with reserved row keys")
    rec = {"row": row_id, "code": code, "ok": bool(ok), "detail": DETAILS[code], "ts": ts}
    rec.update(extra)
    return rec


def run_matrix(
    *, vendor_client, navigator, provision: dict, credential: Credential,
    process_probe, origin_probe, clock, canary_token: str, focus_probe=None,
) -> dict:
    """Run the full C0..C10 canary matrix and return a receipts document."""
    assert_disposable(provision)  # never trust the provision dict; verify before anything else runs

    vendor = provision.get("vendor")
    origin = provision.get("benign_origin")
    profile_id = provision.get("profile_id")

    actuator = NonSeatCanaryActuator(
        vendor_client=vendor_client, navigator=navigator, provision=provision, credential=credential,
    )

    rows: list[dict] = []
    broken = False
    after_c1_this_profile = None

    def emit(row_id: str, code: str, ok: bool, **extra) -> None:
        rows.append(_build_row(row_id, code, ok, clock(), **extra))

    # ---- C0: baseline ----
    provision_digest = sha256_hex(json.dumps(provision, sort_keys=True))
    profile_digest = sha256_hex(str(profile_id))
    emit(
        "C0", "OK", True,
        provision_digest=provision_digest, profile_digest=profile_digest,
        process_counts=process_probe(),
    )

    # ---- C1: closed -> launch ----
    if broken:
        emit("C1", "UNSUPPORTED_SURFACE", False)
    else:
        try:
            p0 = process_probe()
            actuator.acquire()
            navigated_url = origin + "/a"
            actuator.navigate(navigated_url)
            p1 = process_probe()
            after_c1_this_profile = p1.get("this_profile")
            saw = origin_probe.saw("/a")
            same_others = p1.get("other_profiles") == p0.get("other_profiles")
            # Real-launch evidence: the process probe must show exactly one
            # more "this_profile" process than before acquire() — not merely
            # an unrelated truthy count.
            launch_evidence = p1.get("this_profile") == (p0.get("this_profile") or 0) + 1
            pages = navigator.list_pages(actuator._port)
            page_membership = isinstance(pages, list) and navigated_url in pages
            ok = bool(saw) and bool(same_others) and bool(launch_evidence) and page_membership
            extra = {
                "process_counts": {"before": p0, "after": p1},
                "url_digest": sha256_hex(origin + "/a"),
            }
            if focus_probe is not None:
                extra["focus_observed"] = bool(focus_probe())
                extra["observation_only"] = True
            emit("C1", "OK" if ok else "NAVIGATION_FAILED", ok, **extra)
            if not ok:
                broken = True
        except CanaryRefusal as exc:
            broken = True
            emit("C1", exc.code, False)

    # ---- C2: same-owner reuse ----
    if broken:
        emit("C2", "UNSUPPORTED_SURFACE", False)
    else:
        start_calls_before = getattr(vendor_client, "start_calls", None)
        try:
            actuator.navigate(origin + "/b")
            saw = origin_probe.saw("/b")
            this_after = process_probe().get("this_profile")
            unchanged = this_after == after_c1_this_profile
            real_process_evidence = isinstance(this_after, int) and this_after >= 1
            extra = {"url_digest": sha256_hex(origin + "/b")}
            no_new_start = True
            if start_calls_before is not None:
                delta = vendor_client.start_calls - start_calls_before
                extra["start_calls_delta"] = delta
                no_new_start = delta == 0
            ok = bool(saw) and bool(unchanged) and no_new_start and real_process_evidence
            emit("C2", "OK" if ok else "NAVIGATION_FAILED", ok, **extra)
            if not ok:
                broken = True
        except CanaryRefusal as exc:
            broken = True
            emit("C2", exc.code, False)

    # ---- C3: conflict / duplicate acquire ----
    if broken:
        emit("C3", "UNSUPPORTED_SURFACE", False)
    else:
        start_calls_before = getattr(vendor_client, "start_calls", None)
        try:
            actuator.acquire()
        except CanaryRefusal as exc:
            extra = {}
            no_new_start = True
            if start_calls_before is not None:
                delta = vendor_client.start_calls - start_calls_before
                extra["start_calls_delta"] = delta
                no_new_start = delta == 0
            ok = (exc.code == "BUSY_PROFILE") and no_new_start
            emit("C3", exc.code, ok, **extra)
            if not ok:
                broken = True
        else:
            broken = True
            emit("C3", "OK", False)

    # ---- C4: persistence ----
    if broken:
        emit("C4", "UNSUPPORTED_SURFACE", False)
    else:
        try:
            actuator.navigate(origin + "/state/set")
            actuator.release()
            actuator.acquire()
            actuator.navigate(origin + "/state/check")
            ok = bool(origin_probe.cookie_seen(canary_token))
            emit(
                "C4", "OK" if ok else "STATE_NOT_PRESERVED", ok,
                url_digest=sha256_hex(origin + "/state/check"),
            )
            if not ok:
                broken = True
        except CanaryRefusal as exc:
            broken = True
            emit("C4", exc.code, False)

    # ---- C8: logged-out target (still owned) ----
    if broken:
        emit("C8", "UNSUPPORTED_SURFACE", False)
    else:
        try:
            actuator.navigate(origin + "/auth")
            ok = bool(origin_probe.saw("/auth"))
            emit("C8", "AUTH_REQUIRED_TARGET", ok, url_digest=sha256_hex(origin + "/auth"))
        except CanaryRefusal as exc:
            broken = True
            emit("C8", exc.code, False)

    # ---- C5: owner loss ----
    if broken:
        emit("C5", "UNSUPPORTED_SURFACE", False)
    else:
        start_calls_before = getattr(vendor_client, "start_calls", None)
        stop_calls_before = getattr(vendor_client, "stop_calls", None)
        actuator.drop_ownership()
        try:
            actuator.navigate(origin + "/b")
        except CanaryRefusal as exc:
            no_calls = True
            extra = {}
            if start_calls_before is not None:
                extra["start_calls_delta"] = vendor_client.start_calls - start_calls_before
                no_calls = no_calls and vendor_client.start_calls == start_calls_before
            if stop_calls_before is not None:
                no_calls = no_calls and vendor_client.stop_calls == stop_calls_before
            ok = (exc.code == "UNOWNED_RUNNING_PROFILE") and no_calls
            emit("C5", exc.code, ok, **extra)
            if not ok:
                broken = True
        else:
            broken = True
            emit("C5", "OK", False)

    # ---- C6: not found ----
    unknown_ref = {"profile_id": UNKNOWN_PROFILE_IDS.get(vendor)}
    if vendor == "multilogin":
        unknown_ref["folder_id"] = provision.get("folder_id")
    start_calls_before = getattr(vendor_client, "start_calls", None)
    try:
        exists = vendor_client.profile_exists(unknown_ref)
        no_new_start = True
        if start_calls_before is not None:
            no_new_start = vendor_client.start_calls == start_calls_before
        ok = (not exists) and no_new_start
        emit("C6", "PROFILE_NOT_FOUND", ok)
    except CanaryRefusal as exc:
        no_new_start = True
        if start_calls_before is not None:
            no_new_start = vendor_client.start_calls == start_calls_before
        ok = (exc.code == "PROFILE_NOT_FOUND") and no_new_start
        emit("C6", exc.code, ok)
    except Exception:  # noqa: BLE001 — an unmapped vendor crash must still emit a receipt, never abort the matrix
        emit("C6", "VENDOR_ERROR", False)

    # ---- C7: auth missing (+ auth expired, when the fake exposes it) ----
    absent_actuator = NonSeatCanaryActuator(
        vendor_client=vendor_client, navigator=navigator, provision=provision,
        credential=Credential(None, "absent"),
    )
    start_calls_before = getattr(vendor_client, "start_calls", None)
    try:
        absent_actuator.acquire()
        auth_missing_ok = False
        row_code = "OK"
    except CanaryRefusal as exc:
        no_calls = True
        if start_calls_before is not None:
            no_calls = vendor_client.start_calls == start_calls_before
        auth_missing_ok = (exc.code == "AUTH_MISSING") and no_calls
        row_code = exc.code

    expired_probed = hasattr(vendor_client, "expired_credential")
    expired_ok = True
    if expired_probed:
        prior_flag = vendor_client.expired_credential
        vendor_client.expired_credential = True
        try:
            expired_actuator = NonSeatCanaryActuator(
                vendor_client=vendor_client, navigator=navigator, provision=provision, credential=credential,
            )
            try:
                expired_actuator.acquire()
                expired_ok = False
            except CanaryRefusal as exc2:
                expired_ok = exc2.code == "AUTH_EXPIRED"
        finally:
            vendor_client.expired_credential = prior_flag

    # When the client exposes no expiry lever (every live client today), a
    # missing expiry probe must NEVER fail the row — only auth_missing_ok
    # drives it; `expired_probed=False` records that honestly rather than
    # silently claiming the sub-probe ran.
    row_ok = auth_missing_ok and (expired_ok if expired_probed else True)
    emit("C7", row_code, row_ok, expired_probed=expired_probed, expired_ok=expired_ok)

    # ---- C9: authority-negative (closed public surface) ----
    actuator_public = {a for a in dir(actuator) if not a.startswith("_")}
    expected_actuator_public = {"acquire", "navigate", "release", "drop_ownership", "owned"}
    nav_public = {
        a for a in dir(navigator)
        if not a.startswith("_") and callable(getattr(navigator, a, None))
    }
    allowed_nav = {"list_pages", "open_url"}
    c9_ok = (actuator_public == expected_actuator_public) and nav_public.issubset(allowed_nav)
    emit("C9", "OK", c9_ok)

    # ---- C10: receipt hygiene ----
    forbidden_values = [provision.get("benign_origin"), profile_id, canary_token]
    cred_value = credential.expose()
    if cred_value:
        forbidden_values.append(cred_value)
    clean = audit_receipts(rows, forbidden_values)
    emit("C10", "OK" if clean else "RECEIPT_HYGIENE_FAILED", clean)

    verdict = "PASS" if all(row["ok"] is True for row in rows) else "FAIL"
    if tuple(row["row"] for row in rows) != _ROW_ORDER:
        # An `assert` here would be stripped by `python -O`; this invariant
        # must hold even in an optimized interpreter.
        raise RuntimeError("nonseat_canary: row emission order diverged from _ROW_ORDER")

    return {"schema": RECEIPTS_SCHEMA, "vendor": vendor, "rows": rows, "verdict": verdict}


# ---------------------------------------------------------------------------
# hermetic fakes (pure python, no I/O — reused by CLI --hermetic and tests)
# ---------------------------------------------------------------------------


class HermeticVendorFake:
    """Pure-python hermetic vendor client fake. Knows exactly one profile."""

    def __init__(self, vendor: str, profile_id: str, folder_id=None):
        self.vendor = vendor
        self.profile_id = profile_id
        self.folder_id = folder_id
        self.start_calls = 0
        self.stop_calls = 0
        self.expired_credential = False
        self._running = False
        self._started_by_us = False
        self._live_cookies: dict = {}
        self._persisted_cookies: dict = {}
        #: byte-identical across a full matrix per the frozen spec's falsifier 12.
        self.profile_config = {"vendor": vendor, "profile_id": profile_id, "folder_id": folder_id}

    def _matches(self, profile_ref) -> bool:
        if not isinstance(profile_ref, dict):
            return False
        if profile_ref.get("profile_id") != self.profile_id:
            return False
        if self.folder_id is not None and profile_ref.get("folder_id") != self.folder_id:
            return False
        return True

    def _check_expired(self) -> None:
        if self.expired_credential:
            raise CanaryRefusal("AUTH_EXPIRED")

    def profile_exists(self, profile_ref) -> bool:
        self._check_expired()
        return self._matches(profile_ref)

    def is_running_externally(self, profile_ref) -> bool:
        self._check_expired()
        if not self._matches(profile_ref):
            return False
        # Profile-scoped ownership: running-but-started-by-us is NOT
        # "externally running" — only a profile we never started (or have
        # since forgotten via drop_ownership()) counts.
        return self._running and not self._started_by_us

    def start(self, profile_ref) -> dict:
        self._check_expired()
        if self._running:
            raise CanaryRefusal("BUSY_PROFILE")
        self.start_calls += 1
        self._running = True
        self._started_by_us = True
        self._live_cookies = dict(self._persisted_cookies)
        return {"profile_id": self.profile_id, "port": 9222}

    def stop(self, profile_ref) -> None:
        self._check_expired()
        self.stop_calls += 1
        self._persisted_cookies = dict(self._live_cookies)
        self._running = False
        self._started_by_us = False

    def forget_ownership(self) -> None:
        """Mirror of the live clients' ``forget_ownership`` — clears only
        the started-by-us bookkeeping. No counter changes, no vendor call."""
        self._started_by_us = False

    def external_shutdown(self) -> None:
        """Simulate an out-of-band close (e.g. an operator closed the window)."""
        self._running = False
        self._started_by_us = False

    def process_counts(self) -> dict:
        return {"this_profile": 1 if self._running else 0, "other_profiles": 0}


class HermeticOriginFake:
    def __init__(self, canary_token: str):
        self.token = canary_token
        self._seen_paths: set = set()
        self._cookie_seen = False

    def _record(self, path: str) -> None:
        self._seen_paths.add(path)

    def _mark_cookie_seen(self) -> None:
        self._cookie_seen = True

    def saw(self, path: str) -> bool:
        return path in self._seen_paths

    def cookie_seen(self, token: str) -> bool:
        return self._cookie_seen and token == self.token


class HermeticNavigatorFake:
    """Public surface: list_pages, open_url — mirrors DevToolsNavigator."""

    def __init__(self, vendor_fake: HermeticVendorFake, origin_fake: HermeticOriginFake):
        self._vendor_fake = vendor_fake
        self._origin_fake = origin_fake
        self._opened_urls: list = []

    def open_url(self, port, url: str) -> bool:
        if not self._vendor_fake._running:
            return False
        self._opened_urls.append(url)
        path = url
        for known_path in ALLOWED_PATHS:
            if url.endswith(known_path):
                path = known_path
                break
        self._origin_fake._record(path)
        if path == "/state/set":
            self._vendor_fake._live_cookies["mas115_canary"] = self._origin_fake.token
        elif path == "/state/check":
            seen = self._vendor_fake._live_cookies.get("mas115_canary") == self._origin_fake.token
            if seen:
                self._origin_fake._mark_cookie_seen()
        return True

    def list_pages(self, port) -> list:
        if self._vendor_fake._running:
            return list(self._opened_urls)
        return []


def build_hermetic_harness(vendor: str) -> dict:
    """Wire up hermetic fakes + a synthetic provision for ``--hermetic``/tests."""
    if vendor == "gologin":
        profile_id = "aaaaaaaaaaaaaaaaaaaaaaaa"
        folder_id = None
        provision = {
            "schema": PROVISION_SCHEMA,
            "vendor": "gologin",
            "profile_id": profile_id,
            "benign_origin": "http://127.0.0.1:7777",
            "disposable_ack": REQUIRED_ACK,
        }
    elif vendor == "multilogin":
        profile_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        folder_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        provision = {
            "schema": PROVISION_SCHEMA,
            "vendor": "multilogin",
            "profile_id": profile_id,
            "folder_id": folder_id,
            "benign_origin": "http://127.0.0.1:7777",
            "disposable_ack": REQUIRED_ACK,
        }
    else:
        raise ValueError(f"unknown vendor: {vendor!r}")

    vendor_fake = HermeticVendorFake(vendor, profile_id, folder_id)
    origin_fake = HermeticOriginFake("canary-token-hermetic")
    navigator_fake = HermeticNavigatorFake(vendor_fake, origin_fake)
    credential = Credential("hermetic-synthetic-credential", "stdin")

    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-01-01T00:00:{n:02d}.000000Z"

    return {
        "vendor_client": vendor_fake,
        "navigator": navigator_fake,
        "provision": provision,
        "credential": credential,
        "process_probe": vendor_fake.process_counts,
        "origin_probe": origin_fake,
        "clock": clock,
        "canary_token": "canary-token-hermetic",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _refused_payload(vendor: str, code: str) -> dict:
    return {
        "schema": RECEIPTS_SCHEMA, "vendor": vendor, "rows": [],
        "verdict": "REFUSED", "code": code, "detail": DETAILS[code],
    }


def main(argv=None, *, stdout=None) -> int:
    parser = argparse.ArgumentParser(prog="nonseat_canary")
    parser.add_argument("--vendor", required=True, choices=("gologin", "multilogin"))
    parser.add_argument("--hermetic", action="store_true")
    parser.add_argument("--provision-path", default=None)
    args = parser.parse_args(argv)

    out = stdout if stdout is not None else sys.stdout

    if args.hermetic:
        receipts = run_matrix(**build_hermetic_harness(args.vendor))
        print(json.dumps(receipts, indent=2, sort_keys=True), file=out)
        return 0 if receipts["verdict"] == "PASS" else 1

    provision, code = load_provision(args.provision_path)
    if provision is None:
        print(json.dumps(_refused_payload(args.vendor, code), indent=2, sort_keys=True), file=out)
        return 2

    if provision.get("vendor") != args.vendor:
        # A provision file for one vendor must never be run against another
        # vendor's client — refuse BEFORE importing the live vendor shells,
        # constructing any client, or touching the keychain.
        print(
            json.dumps(_refused_payload(args.vendor, "PROVISION_MISSING"), indent=2, sort_keys=True),
            file=out,
        )
        return 2

    # Deferred import: keeps this module import-clean of the live network shells.
    from . import nonseat_canary_vendors as _vendors

    credential = resolve_credential(
        vendor=args.vendor, stdin_text=None,
        keychain_reader=_vendors.keychain_credential_reader(args.vendor),
    )
    if not credential.present:
        print(json.dumps(_refused_payload(args.vendor, "AUTH_MISSING"), indent=2, sort_keys=True), file=out)
        return 2

    if args.vendor == "multilogin":
        vendor_client = _vendors.MultiloginClient(credential)
    else:
        vendor_client = _vendors.GoLoginClient(credential)

    canary_token = f"mas115-live-{uuid.uuid4().hex}"
    navigator = _vendors.DevToolsNavigator()
    origin_server = _vendors.LoopbackBenignOrigin(token=canary_token)
    try:
        # The provisioned benign_origin only proves loopback SHAPE at
        # load_provision time — the actual origin this run serves is the
        # freshly bound loopback port above, so navigation targets it.
        live_provision = dict(provision)
        live_provision["benign_origin"] = origin_server.base_url

        def _clock() -> str:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        receipts = run_matrix(
            vendor_client=vendor_client,
            navigator=navigator,
            provision=live_provision,
            credential=credential,
            process_probe=_vendors.live_process_probe(live_provision),
            origin_probe=origin_server,
            clock=_clock,
            canary_token=canary_token,
        )
    finally:
        origin_server.close()

    print(json.dumps(receipts, indent=2, sort_keys=True), file=out)
    return 0 if receipts["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
