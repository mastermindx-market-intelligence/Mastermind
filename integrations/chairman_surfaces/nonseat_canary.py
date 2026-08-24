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
This model-visible coordinator never reads macOS Keychain and never receives a
live vendor credential.  The live boundary is the deliberately narrow helper
in :mod:`integrations.chairman_surfaces.nonseat_canary_vendors`: after every
non-secret preflight passes, an operator invocation wires fixed Keychain
stdout directly into that helper through an anonymous OS pipe.  Only that
helper may construct a live :class:`Credential`.  A credential's raw value is never
placed in argv, an environment variable, captured subprocess output, a log
line, a receipt, or an exception message.  Hermetic tests may construct
synthetic credentials in-process.

Receipt law
-----------
Receipts carry only fixed static detail sentences (:data:`DETAILS`) plus
digests (:func:`sha256_hex`), booleans, counts, and timestamps — never a raw
URL, profile id, credential value, or vendor payload. C10 proves this about
every row that ran before it; the outer matrix boundary repeats the same audit
after appending the cleanup proof.

Foreground/focus law
---------------------
Foreground/focus observation (``focus_probe`` in :func:`run_matrix`) is
OBSERVATION_ONLY. It is recorded for visibility and never contributes to any
row's ``ok`` value or to the overall verdict.

Determinism law
---------------
This module performs no network I/O, imports no ``subprocess``, and reads no
clock.  Callers provide the reference time used by the binding-census safety
gate and the ``clock`` callable used by :func:`run_matrix`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from control_plane import surface_bindings as _surface_bindings
from . import mas115_multilogin_port_policy as _port_policy

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

RESULT_CODES = frozenset({
    "OK",
    "PROVISION_MISSING",
    "BINDINGS_UNAVAILABLE",
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
    "CLEANUP_FAILED",
    "RECEIPT_HYGIENE_FAILED",
    "VENDOR_ERROR",
})

PROVISION_SCHEMA = "mastermind.mas115_nonseat_canary_provision.v3"
DEFAULT_PROVISION_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_canary.json"
REQUIRED_ACK = "disposable-non-chairman-profile"
RECEIPTS_SCHEMA = "mastermind.mas115_nonseat_canary_receipts.v2"

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
    "BINDINGS_UNAVAILABLE": "a current affirmative Chairman-seat binding census is unavailable.",
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
    "CLEANUP_FAILED": "the exact disposable profile could not be proven stopped during canary cleanup.",
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

    ``source`` is one of ``"stdin"`` or ``"absent"``.  ``"stdin"`` means
    either a synthetic hermetic value or the narrow live helper's direct
    stdin boundary; this coordinator never creates a live instance.
    """

    __slots__ = ("_value", "source")

    def __init__(self, value, source: str):
        if source not in ("stdin", "absent"):
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


def resolve_credential(*, vendor: str, stdin_text=None) -> Credential:
    """Build a synthetic/direct-stdin credential or an absent credential.

    This function has no Keychain reader and no subprocess path.  The live
    helper performs its own bounded anonymous-pipe read only after all non-seat
    preflights pass; the model-visible coordinator never calls this function
    with live input.
    """
    del vendor
    if isinstance(stdin_text, str):
        stripped = stdin_text.strip()
        if stripped:
            return Credential(stripped, "stdin")
    return Credential(None, "absent")


# ---------------------------------------------------------------------------
# provision
# ---------------------------------------------------------------------------

_PROVISION_ALLOWED_KEYS = frozenset({
    "schema", "vendor", "profile_id", "folder_id", "browser_type",
    "origin_policy", "disposable_ack",
})
_PROVISION_REQUIRED_KEYS_BASE = frozenset({
    "schema", "vendor", "profile_id", "origin_policy", "disposable_ack",
})
_MAX_PROVISION_BYTES = 64 * 1024
CHAIRMAN_SEAT_REFS = frozenset({"chatgpt1", "chatgpt2", "chatgpt3"})
BINDINGS_CENSUS_MAX_AGE_SECONDS = 24 * 60 * 60


def _parse_utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _current_chairman_profile_census(doc, *, now, candidate_profile_id: str):
    """Return ``"clear"``, ``"collision"``, or ``"unavailable"``.

    ``surface_bindings`` remains a navigation cache, not a new authority
    plane.  For this one hazardous live preflight, however, absence or an
    incomplete/stale cache cannot prove non-collision.  We therefore require
    the three named Personal-Pro seat references to have one consistent
    managed-environment identity and at least one observation inside the fixed
    safety window.  ``last_verified_at`` is deliberately not used: current
    ChatGPT opens are unsupported and therefore cannot advance it.  Duplicate
    workstream bindings for the same seat are allowed only when they agree on
    that identity.
    """
    if not isinstance(doc, dict) or doc.get("schema") != _surface_bindings.SCHEMA:
        return "unavailable"
    if _surface_bindings.validate_bindings_document(doc):
        return "unavailable"
    if not isinstance(now, datetime) or now.tzinfo is None:
        return "unavailable"

    identities: dict[str, tuple] = {}
    observed: dict[str, datetime] = {}
    candidate_lower = candidate_profile_id.lower()
    collision = False

    for binding in doc.get("bindings") or []:
        if not isinstance(binding, dict) or binding.get("provider") != "chatgpt":
            continue
        locator = binding.get("locator")
        if not isinstance(locator, dict):
            return "unavailable"
        bound_profile_id = locator.get("profile_id")
        if isinstance(bound_profile_id, str) and bound_profile_id.lower() == candidate_lower:
            collision = True

        seat_ref = binding.get("seat_ref")
        manager = locator.get("env_manager")
        folder_id = locator.get("folder_id")
        if seat_ref not in CHAIRMAN_SEAT_REFS:
            return "unavailable"
        if manager not in ("gologin", "multilogin") or not isinstance(bound_profile_id, str):
            return "unavailable"
        identity = (manager, folder_id if manager == "multilogin" else None, bound_profile_id.lower())
        prior = identities.get(seat_ref)
        if prior is not None and prior != identity:
            return "unavailable"
        identities[seat_ref] = identity

        observed_at = _parse_utc(binding.get("observed_at"))
        if observed_at is None:
            return "unavailable"
        prior_observed = observed.get(seat_ref)
        if prior_observed is None or observed_at > prior_observed:
            observed[seat_ref] = observed_at

    if set(identities) != CHAIRMAN_SEAT_REFS or set(observed) != CHAIRMAN_SEAT_REFS:
        return "unavailable"
    for observed_at in observed.values():
        age = (now - observed_at).total_seconds()
        if age < 0 or age > BINDINGS_CENSUS_MAX_AGE_SECONDS:
            return "unavailable"
    return "collision" if collision else "clear"


def _read_provision_document(target: Path):
    try:
        if not target.is_file():
            return None
        if target.stat().st_size > _MAX_PROVISION_BYTES:
            return None
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        doc = json.loads(raw)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def _validate_provision_document(doc, *, bindings_loader=None, now=None):
    loader = bindings_loader if bindings_loader is not None else _surface_bindings.load_bindings

    if not isinstance(doc, dict):
        return None, "PROVISION_MISSING"
    if set(doc.keys()) - _PROVISION_ALLOWED_KEYS:
        return None, "PROVISION_MISSING"
    if doc.get("schema") != PROVISION_SCHEMA:
        return None, "PROVISION_MISSING"

    doc = dict(doc)

    vendor = doc.get("vendor")
    if vendor not in ("gologin", "multilogin"):
        return None, "PROVISION_MISSING"

    required = _PROVISION_REQUIRED_KEYS_BASE | (
        {"folder_id", "browser_type"} if vendor == "multilogin" else set()
    )
    if not required.issubset(doc.keys()):
        return None, "PROVISION_MISSING"

    if vendor == "multilogin":
        if doc.get("browser_type") not in ("mimic", "stealthfox"):
            return None, "PROVISION_MISSING"
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
        if "folder_id" in doc or "browser_type" in doc:
            return None, "PROVISION_MISSING"
        profile_id = doc.get("profile_id")
        if not isinstance(profile_id, str) or not _surface_bindings.GOLOGIN_PROFILE_ID_RE.match(profile_id):
            return None, "PROVISION_MISSING"

    if doc.get("disposable_ack") != REQUIRED_ACK:
        return None, "PROVISION_MISSING"
    if doc.get("origin_policy") != _port_policy.ORIGIN_POLICY:
        return None, "DISALLOWED_TARGET"

    # Seat-collision guard: only a present, valid, fresh affirmative census
    # can prove non-collision.  Missing navigation state is never evidence
    # that no Chairman seat exists.
    try:
        collision_doc, problems = loader()
    except Exception:  # noqa: BLE001 — cannot prove non-collision, fail closed
        return None, "BINDINGS_UNAVAILABLE"

    if problems:
        return None, "BINDINGS_UNAVAILABLE"
    census = _current_chairman_profile_census(
        collision_doc, now=now, candidate_profile_id=str(profile_id),
    )
    if census == "collision":
        return None, "DISALLOWED_TARGET"
    if census != "clear":
        return None, "BINDINGS_UNAVAILABLE"

    return doc, None


def load_provision(path=None, *, bindings_loader=None, now=None):
    """Load and validate the fixed-policy disposable canary provision.

    Returns ``(provision_dict, None)`` on success, or ``(None, code)`` where
    ``code`` is one of ``"PROVISION_MISSING"`` / ``"DISALLOWED_TARGET"`` /
    ``"BINDINGS_UNAVAILABLE"``. Never raises and never migrates.
    """
    target = Path(path).expanduser() if path else Path(DEFAULT_PROVISION_PATH).expanduser()
    doc = _read_provision_document(target)
    if doc is None:
        return None, "PROVISION_MISSING"
    return _validate_provision_document(
        doc, bindings_loader=bindings_loader, now=now,
    )


def load_legacy_provision_for_migration(
    path=None, *, bindings_loader=None, now=None,
):
    """Validate and transform only the exact historical v2 provision."""

    target = Path(path).expanduser() if path else Path(DEFAULT_PROVISION_PATH).expanduser()
    doc = _read_provision_document(target)
    if doc is None:
        return None, "PROVISION_MISSING"
    vendor = doc.get("vendor")
    expected_keys = set(_PROVISION_REQUIRED_KEYS_BASE)
    expected_keys.remove("origin_policy")
    expected_keys.add("benign_origin")
    if vendor == "multilogin":
        expected_keys.update({"folder_id", "browser_type"})
    if set(doc) != expected_keys:
        return None, "PROVISION_MISSING"
    if (
        doc.get("schema") != _port_policy.LEGACY_PROVISION_SCHEMA
        or doc.get("benign_origin") != _port_policy.LEGACY_BENIGN_ORIGIN
    ):
        return None, "DISALLOWED_TARGET"
    candidate = {key: value for key, value in doc.items() if key != "benign_origin"}
    candidate["schema"] = PROVISION_SCHEMA
    candidate["origin_policy"] = _port_policy.ORIGIN_POLICY
    return _validate_provision_document(
        candidate, bindings_loader=bindings_loader, now=now,
    )


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_disposable(provision) -> None:
    """Defense-in-depth gate: never trust a caller-supplied ``provision``
    dict at face value. Raises :class:`CanaryRefusal` (``DISALLOWED_TARGET``)
    unless ``provision`` is a dict carrying the exact disposable ack AND a
    the fixed origin policy and its runtime-derived exact loopback origin."""
    if not isinstance(provision, dict):
        raise CanaryRefusal("DISALLOWED_TARGET")
    if provision.get("disposable_ack") != REQUIRED_ACK:
        raise CanaryRefusal("DISALLOWED_TARGET")
    vendor = provision.get("vendor")
    if vendor not in ("gologin", "multilogin"):
        raise CanaryRefusal("DISALLOWED_TARGET")
    if vendor == "multilogin" and provision.get("browser_type") not in ("mimic", "stealthfox"):
        raise CanaryRefusal("DISALLOWED_TARGET")
    if vendor == "gologin" and "browser_type" in provision:
        raise CanaryRefusal("DISALLOWED_TARGET")
    if provision.get("origin_policy") != _port_policy.ORIGIN_POLICY:
        raise CanaryRefusal("DISALLOWED_TARGET")
    if provision.get("benign_origin") != _port_policy.CANARY_ORIGIN:
        raise CanaryRefusal("DISALLOWED_TARGET")


def allowed_url(provision: dict, url) -> bool:
    """True iff ``url`` is exactly the provisioned benign origin plus one of
    :data:`ALLOWED_PATHS`, AND that origin's hostname is loopback."""
    if not isinstance(provision, dict) or not isinstance(url, str):
        return False
    if provision.get("origin_policy") != _port_policy.ORIGIN_POLICY:
        return False
    if provision.get("benign_origin") != _port_policy.CANARY_ORIGIN:
        return False
    return any(url == _port_policy.CANARY_ORIGIN + suffix for suffix in ALLOWED_PATHS)


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
        owned_port = self._owned["port"]
        vendor_error = False
        try:
            self._vendor_client.stop(self._profile_ref)
        except CanaryRefusal:
            raise
        except Exception:  # noqa: BLE001
            vendor_error = True
        if vendor_error:
            raise CanaryRefusal("VENDOR_ERROR") from None  # see acquire(): context severed by construction
        # A supported vendor stop invalidates the WebDriver session. Forget
        # only this actuator-owned loopback session so a same-port allocation
        # after the persistence restart can create a fresh W3C session. This
        # is local bookkeeping only; it sends no browser/vendor command.
        forget = getattr(self._navigator, "_forget", None)
        if forget is not None:
            try:
                forget(owned_port)
            except Exception:  # noqa: BLE001 — stop already succeeded; cleanup cannot widen the result
                pass
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


def _run_matrix_rows(
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
            baseline_count = p0.get("this_profile")
            before_other_count = p0.get("other_profiles")
            after_other_count = p1.get("other_profiles")
            baseline_closed = (
                isinstance(baseline_count, int)
                and not isinstance(baseline_count, bool)
                and baseline_count == 0
            )
            same_others = (
                isinstance(before_other_count, int)
                and not isinstance(before_other_count, bool)
                and before_other_count >= 0
                and isinstance(after_other_count, int)
                and not isinstance(after_other_count, bool)
                and after_other_count == before_other_count
            )
            # Multilogin launches a browser process group, not one process.
            # The exact-profile probe already binds each counted row to the
            # provisioned user-data directory, so positive evidence is one or
            # more exact-profile processes from a zero baseline.
            launch_evidence = (
                isinstance(p1.get("this_profile"), int)
                and not isinstance(p1.get("this_profile"), bool)
                and p1.get("this_profile") >= 1
            )
            pages = navigator.list_pages(actuator._port)
            page_membership = isinstance(pages, list) and navigated_url in pages
            navigation_ok = bool(saw) and bool(page_membership)
            launch_ok = bool(baseline_closed) and bool(same_others) and bool(launch_evidence)
            ok = launch_ok and navigation_ok
            extra = {
                "process_counts": {"before": p0, "after": p1},
                "url_digest": sha256_hex(origin + "/a"),
                "predicates": {
                    "baseline_closed": bool(baseline_closed),
                    "exact_profile_process_group_started": bool(launch_evidence),
                    "other_profiles_unchanged": bool(same_others),
                    "benign_origin_observed": bool(saw),
                    "navigated_page_membership": bool(page_membership),
                },
            }
            if focus_probe is not None:
                extra["focus_observed"] = bool(focus_probe())
                extra["observation_only"] = True
            code = "OK" if ok else ("LAUNCH_FAILED" if not launch_ok else "NAVIGATION_FAILED")
            emit("C1", code, ok, **extra)
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


def _reduced_process_counts(process_probe) -> dict:
    """Return only validated non-negative counts; dynamic probe errors close."""
    try:
        observed = process_probe()
    except Exception:  # noqa: BLE001 — cleanup receipts never carry dynamic probe errors
        observed = None
    if not isinstance(observed, dict):
        return {"this_profile": None, "other_profiles": None}
    reduced = {}
    for key in ("this_profile", "other_profiles"):
        value = observed.get(key)
        reduced[key] = (
            value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
        )
    return reduced


def _cleanup_after_matrix(vendor_client, process_probe, cleanup_probe=None) -> dict:
    """Attempt one exact-profile teardown through the client's private lease.

    The lease is minted only when this process sends its one preflighted
    exact-profile start request and survives ambiguous responses plus C5's
    simulated operational owner loss. No profile identity is supplied here
    and none is emitted: the client can stop only that exact requested profile.
    """
    before = _reduced_process_counts(process_probe)
    cleanup = getattr(vendor_client, "_cleanup_started_profile", None)
    attempted = False
    acknowledged = False
    vendor_code = "OK"
    if callable(cleanup):
        try:
            attempted = bool(cleanup())
            acknowledged = True
        except CanaryRefusal as refusal:
            vendor_code = refusal.code
        except Exception:  # noqa: BLE001 — no dynamic cleanup error crosses the receipt boundary
            vendor_code = "VENDOR_ERROR"
    elif before.get("this_profile") == 0:
        acknowledged = True

    after = _reduced_process_counts(cleanup_probe or process_probe)
    exact_profile_stopped = after.get("this_profile") == 0
    other_profiles_unchanged = (
        before.get("other_profiles") is not None
        and after.get("other_profiles") == before.get("other_profiles")
    )
    ok = acknowledged and exact_profile_stopped and other_profiles_unchanged
    code = "OK" if ok else "CLEANUP_FAILED"
    return {
        "code": code,
        "detail": DETAILS[code],
        "ok": bool(ok),
        "attempted": bool(attempted),
        "vendor_code": vendor_code,
        "process_counts": {"before": before, "after": after},
        "predicates": {
            "stop_acknowledged_or_not_needed": bool(acknowledged),
            "exact_profile_stopped": bool(exact_profile_stopped),
            "other_profiles_unchanged": bool(other_profiles_unchanged),
        },
    }


def run_matrix(
    *, vendor_client, navigator, provision: dict, credential: Credential,
    process_probe, origin_probe, clock, canary_token: str, focus_probe=None,
    cleanup_probe=None,
) -> dict:
    """Run C0..C10 and always close an exact profile started by this run."""
    # Preserve the defense-in-depth gate before even a cleanup/process probe.
    assert_disposable(provision)
    try:
        receipts = _run_matrix_rows(
            vendor_client=vendor_client,
            navigator=navigator,
            provision=provision,
            credential=credential,
            process_probe=process_probe,
            origin_probe=origin_probe,
            clock=clock,
            canary_token=canary_token,
            focus_probe=focus_probe,
        )
    except BaseException:
        # A dynamic matrix failure still owes one exact-profile teardown. The
        # original failure is re-raised; no retry or cross-profile fallback is
        # attempted if teardown itself cannot be proven.
        _cleanup_after_matrix(vendor_client, process_probe, cleanup_probe)
        raise

    cleanup = _cleanup_after_matrix(vendor_client, process_probe, cleanup_probe)
    receipts["cleanup"] = cleanup

    forbidden_values = [provision.get("benign_origin"), provision.get("profile_id"), canary_token]
    credential_value = credential.expose()
    if credential_value:
        forbidden_values.append(credential_value)
    hygienic = audit_receipts(receipts["rows"] + [cleanup], forbidden_values)
    c10 = next(row for row in receipts["rows"] if row.get("row") == "C10")
    if not hygienic:
        c10.update({
            "code": "RECEIPT_HYGIENE_FAILED",
            "detail": DETAILS["RECEIPT_HYGIENE_FAILED"],
            "ok": False,
        })
    receipts["verdict"] = (
        "PASS"
        if cleanup["ok"] is True and all(row.get("ok") is True for row in receipts["rows"])
        else "FAIL"
    )
    return receipts


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
        self._cleanup_started = False
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
        self._cleanup_started = True
        self._live_cookies = dict(self._persisted_cookies)
        return {"profile_id": self.profile_id, "port": 9222}

    def stop(self, profile_ref) -> None:
        self._check_expired()
        self.stop_calls += 1
        self._persisted_cookies = dict(self._live_cookies)
        self._running = False
        self._started_by_us = False
        self._cleanup_started = False

    def forget_ownership(self) -> None:
        """Mirror of the live clients' ``forget_ownership`` — clears only
        the started-by-us bookkeeping. No counter changes, no vendor call."""
        self._started_by_us = False

    def _cleanup_started_profile(self) -> bool:
        """Teardown lease retained independently from C5 owner loss."""
        if not self._cleanup_started:
            return False
        profile_ref = {"profile_id": self.profile_id}
        if self.folder_id is not None:
            profile_ref["folder_id"] = self.folder_id
        self.stop(profile_ref)
        return True

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
    """Public surface: list_pages, open_url — mirrors WebDriverNavigator."""

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
            "origin_policy": _port_policy.ORIGIN_POLICY,
            "benign_origin": _port_policy.CANARY_ORIGIN,
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
            "browser_type": "mimic",
            "origin_policy": _port_policy.ORIGIN_POLICY,
            "benign_origin": _port_policy.CANARY_ORIGIN,
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

    # Live credentials must never cross this model-visible coordinator.  The
    # operator-only helper performs provision/binding preflights, then wires
    # fixed Keychain stdout directly to its secret-owning input through an
    # anonymous pipe.  Refuse here even if this process has readable stdin.
    del args.provision_path
    print(json.dumps(_refused_payload(args.vendor, "UNSUPPORTED_SURFACE"), indent=2, sort_keys=True), file=out)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
