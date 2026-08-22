"""control_plane.surface_bindings — ``mastermind.surface_bindings.v1`` navigation store.

This module owns a single local, private JSON file that maps a work reference
(``WS:...`` / ``JOB:...`` / ``PR:...``) plus a seat role to *where a human or
agent seat already is* on some external chat/session surface — a ChatGPT tab,
a Claude Code session, a Cursor thread, a Codex thread.  It exists so the
Chairman Control Room compositor (:mod:`control_plane.chairman_control_room`)
can offer "open this surface" navigation without inventing a second lifecycle
or identity plane.

Design laws (frozen by ``research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_P0_
ARCHITECTURE_AND_FABLE00_COMMISSION_2026-08-21.md`` §5)
-----------------------------------------------------------------------------
* **Navigation only, never authority.**  The store may not contain job/
  workstream/attempt status, priority, rank, next action, completion state,
  queue position, lease/claim, authority/permission grants, executive
  attention targets, result verdicts, or provider credentials/tokens/prompts/
  transcripts.  Deleting this file must never change any canonical program,
  runtime, or attention fact — only navigation convenience.
* **``binding_id`` is a local-only handle, not an identity plane.**  It is a
  random ``uuid4`` minted so a human (or the unbind/conflict UI) has a short,
  stable string to reference *this row* by when there are several bindings
  for the same ``(work_ref, role)``.  It grants nothing, proves nothing about
  provenance, and is never joined against any canonical Agent OS / Executive
  OS / GitHub identity.  Treat it exactly like a spreadsheet row number.
* **Closed schema, everywhere.**  Every dict in the document — the document
  itself, each binding, and each binding's ``locator`` — has an exact,
  closed key set.  An unknown key anywhere is a validation problem naming its
  path.  This is deliberately stricter than most Mastermind contracts because
  this file is the one place a "just one more field" edit could quietly turn
  a navigation cache into a second control plane.
* **Fail closed on write, fail open on read.**  ``save_bindings`` validates
  before writing and refuses a non-conforming document outright.
  ``load_bindings`` never raises: a missing file is not an error (P0 §10 —
  "surface binding file absent -> all navigation unbound, canonical state
  unaffected"), and a malformed one degrades to ``(None, [problems])`` so a
  caller can render "bindings unavailable" instead of crashing.
* **Atomic, private writes.**  ``save_bindings`` creates parent directories
  ``0700``, writes through a same-directory temp file made ``0600`` before
  any content is written, ``fsync``s it, and ``os.replace``s it into place —
  never a partial or world-readable file is observable.
* **No clock reads inside the library.**  Every function that needs "now"
  (``new_binding``) takes it as a parameter.  The one caller-visible
  ``datetime.now()`` in the whole binding path belongs to whatever UI/CLI
  eventually calls this module, never to the module itself — the same
  determinism law :mod:`control_plane.chairman_control_room` depends on.

Usage
-----
    from control_plane.surface_bindings import load_bindings, save_bindings, new_binding

    doc, problems = load_bindings()
    if doc is None and problems:
        ...  # surface the problems; treat as "no bindings" for navigation
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

#: Schema version of the document this module reads/writes.
SCHEMA = "mastermind.surface_bindings.v1"

#: Default on-disk location (macOS).  Always expanded at call time so a
#: patched ``HOME`` (tests) is honored; never resolved once at import time.
DEFAULT_PATH = "~/Library/Application Support/Mastermind/control-room/surface_bindings.json"

#: Hard ceiling on the bindings file.  This is a small local navigation
#: cache, never a data store — a file that grew past this is a sign
#: something is putting the wrong kind of data in it.
_MAX_BYTES = 1024 * 1024  # 1 MiB

#: Allowed seat roles.
ROLES = ("chairman", "ceo", "coo", "worker")

#: Allowed providers, and the exact ``locator_kind`` each one is required to
#: carry.  ``aionui`` is deliberately absent in v1 (architecture §6.5) —
#: later waves project it as ``UNSUPPORTED``; it is never stored here.
PROVIDERS = ("chatgpt", "claude_code", "claude_desktop", "cursor_agent", "codex")

_PROVIDER_LOCATOR_KIND: dict[str, str] = {
    "chatgpt": "chatgpt_managed_env",
    "claude_code": "claude_code_session",
    "claude_desktop": "claude_desktop_url",
    "cursor_agent": "cursor_agent_thread",
    "codex": "codex_session",
}

#: Closed key set for each locator kind.
_LOCATOR_ALLOWED_KEYS: dict[str, frozenset[str]] = {
    "chatgpt_managed_env": frozenset({"env_manager", "folder_id", "profile_id", "url"}),
    "claude_code_session": frozenset({"project_dir", "session_id"}),
    "claude_desktop_url": frozenset({"url"}),
    "cursor_agent_thread": frozenset({"chat_id", "workspace_dir"}),
    "codex_session": frozenset({"session_id", "cwd"}),
}

#: Managed-browser environment vendors a ``chatgpt`` seat may be addressed
#: in (Sol architecture correction, MAS-113, 2026-08-22). ChatGPT seats live
#: in persistent GoLogin/Multilogin environments, never an ordinary Chrome
#: profile — see :mod:`integrations.chairman_surfaces.chatgpt` for the full
#: law and the falsifier evidence behind it.
ENV_MANAGERS = ("gologin", "multilogin")

#: GoLogin's on-disk profile id shape: a 24-character lowercase hex string
#: (matches the real local ``~/Library/Caches/GoLogin/profiles/<id>`` store —
#: lowercase only, never validated case-insensitively).
_GOLOGIN_PROFILE_ID_RE = re.compile(r"^[0-9a-f]{24}$")

#: Public aliases for the two id-shape regexes a caller outside this module
#: (currently :mod:`integrations.chairman_surfaces.chatgpt`) needs to reuse
#: rather than duplicate. The private names above remain this module's own
#: canonical definitions; these are read-only re-exports of the same compiled
#: pattern objects, never a second definition to drift out of sync.
GOLOGIN_PROFILE_ID_RE = _GOLOGIN_PROFILE_ID_RE

#: Closed key set for a Binding.
_BINDING_ALLOWED_KEYS = frozenset({
    "binding_id", "work_ref", "role", "seat_ref", "provider", "locator_kind",
    "locator", "observed_at", "last_verified_at",
})

#: Fields a Binding must always carry.  ``seat_ref`` is conditionally
#: required (only when ``provider == "chatgpt"``, checked separately) and
#: ``last_verified_at`` is optional (may be ``null``), so neither is here.
_BINDING_REQUIRED_KEYS = frozenset({
    "binding_id", "work_ref", "role", "provider", "locator_kind", "locator",
    "observed_at",
})

#: Closed key set for the top-level document.
_DOCUMENT_ALLOWED_KEYS = frozenset({"schema", "bindings"})

#: Lowercased key names that would smuggle lifecycle/authority/credential
#: semantics into a navigation-only store.  Checked against EVERY dict in the
#: document, at every depth — the document itself, each binding, and each
#: locator — not just the Binding's own closed key set.  This is a belt, not
#: a replacement for the closed-key check: it exists so the refusal is
#: precisely diagnosable ("key X carries lifecycle/authority semantics")
#: rather than only "key X is unknown here".
#:
#: The proxy/IP/fingerprint/cookie/credential/token entries exist specifically
#: for the managed-browser (GoLogin/Multilogin) chatgpt locator (Sol
#: architecture correction, MAS-113, 2026-08-22): those environments carry
#: live proxy and fingerprint configuration in the vendor's own store, and
#: this belt keeps that material from ever being copied into a navigation-only
#: cache alongside the seat's durable address — the address is an
#: environment/profile ID plus a conversation URL, never the environment's
#: network or fingerprint material.
FORBIDDEN_SEMANTIC_KEYS = frozenset({
    "status", "state", "lifecycle", "priority", "rank", "next_action",
    "completion", "complete", "done", "queue", "queue_position", "lease",
    "claim", "authority", "permission", "attention", "target", "result",
    "verdict", "review", "token", "cookie", "credential", "secret",
    "password", "prompt", "transcript", "message",
    "proxy", "proxy_server", "proxy_username", "proxy_password", "proxies",
    "ip", "ip_address", "fingerprint", "fingerprints", "cookies",
    "user_agent", "api_key", "apikey", "access_token", "refresh_token",
})

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

#: Public re-export of :data:`_UUID_RE` — see :data:`GOLOGIN_PROFILE_ID_RE`'s
#: comment; one definition, reused rather than duplicated by callers outside
#: this module.
UUID_RE = _UUID_RE

_WORK_REF_RE = re.compile(r"^(WS|JOB|PR):\S+$")

_CHATGPT_HOSTS = frozenset({"chatgpt.com", "chat.openai.com"})
_CLAUDE_DESKTOP_HOST = "claude.ai"


class SurfaceBindingError(ValueError):
    """A surface bindings document failed validation."""


class SurfaceBindingViolation(SurfaceBindingError):
    """A surface bindings document tried to carry forbidden semantics.

    Raised specifically (rather than the base :class:`SurfaceBindingError`)
    when at least one problem came from the :data:`FORBIDDEN_SEMANTIC_KEYS`
    belt, so a caller/test can distinguish "this document tried to become a
    second lifecycle plane" from an ordinary shape mistake.
    """


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def _check_closed(node: dict, allowed: frozenset[str], path: str, problems: list[str]) -> None:
    for key in node.keys():
        if not isinstance(key, str):
            problems.append(f"{path}: non-string key {key!r}")
            continue
        if key not in allowed:
            problems.append(f"{path}.{key}: unknown key")


def _walk_forbidden(node: Any, path: str, problems: list[str], forbidden: list[str]) -> None:
    """Recursively flag any dict key matching :data:`FORBIDDEN_SEMANTIC_KEYS`.

    Walks every dict/list in the document regardless of where the closed-key
    checks already looked — a forbidden key nested somewhere the closed-key
    walk does not visit (e.g. inside an otherwise-unknown nested object) must
    still be caught by name.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            key_path = f"{path}.{key}" if isinstance(key, str) else f"{path}.<non-str-key>"
            if isinstance(key, str) and key.lower() in FORBIDDEN_SEMANTIC_KEYS:
                msg = (
                    f"{key_path}: forbidden key {key!r} — surface_bindings is a "
                    f"navigation-only store and may not carry lifecycle, priority, "
                    f"authority, or credential semantics"
                )
                problems.append(msg)
                forbidden.append(msg)
            _walk_forbidden(value, key_path, problems, forbidden)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_forbidden(item, f"{path}[{index}]", problems, forbidden)


def _valid_iso8601_z(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        from datetime import datetime
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _check_chatgpt_url(url: Any) -> str | None:
    if not isinstance(url, str) or not url:
        return "must be a non-empty string"
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        return "must use https"
    if parsed.username or parsed.password:
        return "must not embed a username/password"
    if parsed.port is not None:
        return "must not specify a port"
    if (parsed.hostname or "").lower() not in _CHATGPT_HOSTS:
        return f"host must be one of {sorted(_CHATGPT_HOSTS)}"
    return None


def _check_claude_desktop_url(url: Any) -> str | None:
    if not isinstance(url, str) or not url:
        return "must be a non-empty string"
    parsed = urlsplit(url)
    if parsed.scheme == "claude":
        return None
    if parsed.scheme != "https":
        return "must use https or the claude:// scheme"
    if parsed.username or parsed.password:
        return "must not embed a username/password"
    if parsed.port is not None:
        return "must not specify a port"
    if (parsed.hostname or "").lower() != _CLAUDE_DESKTOP_HOST:
        return f"host must be {_CLAUDE_DESKTOP_HOST!r} or use the claude:// scheme"
    return None


def _is_absolute_path_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and Path(value).is_absolute()


def _is_nonempty_no_whitespace(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and not any(c.isspace() for c in value)


def _validate_locator(provider: str, locator: Any, path: str, problems: list[str]) -> None:
    if not isinstance(locator, dict):
        problems.append(f"{path}: must be an object")
        return
    kind = _PROVIDER_LOCATOR_KIND[provider]
    _check_closed(locator, _LOCATOR_ALLOWED_KEYS[kind], path, problems)

    if kind == "chatgpt_managed_env":
        manager = locator.get("env_manager")
        if manager not in ENV_MANAGERS:
            problems.append(f"{path}.env_manager: must be one of {sorted(ENV_MANAGERS)}")
        elif manager == "multilogin":
            folder_id = locator.get("folder_id")
            if not isinstance(folder_id, str) or not _UUID_RE.match(folder_id):
                problems.append(f"{path}.folder_id: must be a uuid string")
            profile_id = locator.get("profile_id")
            if not isinstance(profile_id, str) or not _UUID_RE.match(profile_id):
                problems.append(f"{path}.profile_id: must be a uuid string")
        elif manager == "gologin":
            if "folder_id" in locator:
                problems.append(
                    f"{path}.folder_id: gologin environments are addressed by "
                    f"profile_id only; folder_id is not part of the durable address"
                )
            profile_id = locator.get("profile_id")
            if not isinstance(profile_id, str) or not _GOLOGIN_PROFILE_ID_RE.match(profile_id):
                problems.append(f"{path}.profile_id: must be a 24-character lowercase hex string")
        err = _check_chatgpt_url(locator.get("url"))
        if err:
            problems.append(f"{path}.url: {err}")
    elif kind == "claude_code_session":
        if not _is_absolute_path_str(locator.get("project_dir")):
            problems.append(f"{path}.project_dir: must be an absolute path string")
        session_id = locator.get("session_id")
        if not isinstance(session_id, str) or not _UUID_RE.match(session_id):
            problems.append(f"{path}.session_id: must be a uuid string")
    elif kind == "claude_desktop_url":
        err = _check_claude_desktop_url(locator.get("url"))
        if err:
            problems.append(f"{path}.url: {err}")
    elif kind == "cursor_agent_thread":
        if not _is_nonempty_no_whitespace(locator.get("chat_id")):
            problems.append(f"{path}.chat_id: must be a non-empty string with no whitespace")
        workspace_dir = locator.get("workspace_dir")
        if workspace_dir is not None and not _is_absolute_path_str(workspace_dir):
            problems.append(f"{path}.workspace_dir: must be an absolute path string or null")
    elif kind == "codex_session":
        if not _is_nonempty_no_whitespace(locator.get("session_id")):
            problems.append(f"{path}.session_id: must be a non-empty string with no whitespace")
        cwd = locator.get("cwd")
        if cwd is not None and not _is_absolute_path_str(cwd):
            problems.append(f"{path}.cwd: must be an absolute path string or null")


def _validate_binding(binding: Any, path: str, problems: list[str]) -> None:
    if not isinstance(binding, dict):
        problems.append(f"{path}: must be an object")
        return

    _check_closed(binding, _BINDING_ALLOWED_KEYS, path, problems)
    for required in sorted(_BINDING_REQUIRED_KEYS):
        if required not in binding:
            problems.append(f"{path}.{required}: required")

    if "binding_id" in binding:
        value = binding["binding_id"]
        if not isinstance(value, str) or not _UUID_RE.match(value):
            problems.append(f"{path}.binding_id: must be a uuid4 string")

    if "work_ref" in binding:
        value = binding["work_ref"]
        if not isinstance(value, str) or not _WORK_REF_RE.match(value):
            problems.append(f"{path}.work_ref: must match ^(WS|JOB|PR):\\S+$")

    if "role" in binding:
        value = binding["role"]
        if value not in ROLES:
            problems.append(f"{path}.role: must be one of {sorted(ROLES)}")

    provider = binding.get("provider")
    provider_valid = provider in PROVIDERS
    if "provider" in binding and not provider_valid:
        problems.append(f"{path}.provider: must be one of {sorted(PROVIDERS)}")

    seat_ref = binding.get("seat_ref", None)
    if "seat_ref" in binding and seat_ref is not None and not isinstance(seat_ref, str):
        problems.append(f"{path}.seat_ref: must be a string or null")
    if provider_valid and provider == "chatgpt":
        if not isinstance(seat_ref, str) or not seat_ref.strip():
            problems.append(f"{path}.seat_ref: required (non-empty string) when provider is chatgpt")

    if provider_valid:
        expected_kind = _PROVIDER_LOCATOR_KIND[provider]
        if "locator_kind" in binding and binding["locator_kind"] != expected_kind:
            problems.append(
                f"{path}.locator_kind: must equal {expected_kind!r} for provider {provider!r}"
            )
        if "locator" in binding:
            _validate_locator(provider, binding["locator"], f"{path}.locator", problems)

    for field in ("observed_at", "last_verified_at"):
        if field not in binding:
            continue
        value = binding[field]
        if field == "last_verified_at" and value is None:
            continue
        if not _valid_iso8601_z(value):
            problems.append(f"{path}.{field}: must be an ISO-8601 UTC 'Z' timestamp")


def _collect_problems(doc: object) -> tuple[list[str], list[str]]:
    """Return ``(all_problems, forbidden_semantics_problems)``."""
    problems: list[str] = []
    forbidden: list[str] = []

    if not isinstance(doc, dict):
        problems.append("$: document must be an object")
        return problems, forbidden

    _check_closed(doc, _DOCUMENT_ALLOWED_KEYS, "$", problems)

    if doc.get("schema") != SCHEMA:
        problems.append(f"$.schema: expected {SCHEMA!r}, got {doc.get('schema')!r}")

    bindings = doc.get("bindings")
    if not isinstance(bindings, list):
        problems.append("$.bindings: must be a list")
        bindings = []
    else:
        for index, binding in enumerate(bindings):
            _validate_binding(binding, f"$.bindings[{index}]", problems)

    # The forbidden-semantics belt walks the WHOLE document independently of
    # the structural checks above — it is deliberately redundant with the
    # closed-key checks so the refusal is named precisely.
    _walk_forbidden(doc, "$", problems, forbidden)

    return problems, forbidden


def validate_bindings_document(doc: object) -> list[str]:
    """Return every validation problem with ``doc``, or ``[]`` when valid.

    Never raises.  A problem string names its path inside the document
    (``$.bindings[0].locator.url: ...``) so a caller can report precisely
    what is wrong without re-deriving the walk.
    """
    problems, _forbidden = _collect_problems(doc)
    return problems


def _validate_or_raise(doc: object) -> None:
    problems, forbidden = _collect_problems(doc)
    if forbidden:
        raise SurfaceBindingViolation("; ".join(forbidden))
    if problems:
        raise SurfaceBindingError("; ".join(problems))


# ---------------------------------------------------------------------------
# load / save
# ---------------------------------------------------------------------------

def _resolve_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    return Path(DEFAULT_PATH).expanduser()


def load_bindings(path: str | Path | None = None) -> tuple[dict | None, list[str]]:
    """Read and validate the bindings document at ``path`` (default location if None).

    Returns ``(document, problems)``:

    * Missing file -> ``(None, [])`` — absence is not an error (P0 §10).
    * Non-regular file, oversize, unparseable JSON, or a document that fails
      :func:`validate_bindings_document` -> ``(None, [problems])``.
    * A valid document whose file mode grants group/other access is still
      returned, with a "permissions" warning appended -> ``(doc, warnings)``.

    Never raises.
    """
    target = _resolve_path(path)

    try:
        exists = target.exists()
    except OSError:
        exists = False
    if not exists:
        return None, []

    try:
        info = target.stat()
    except OSError as exc:
        return None, [f"{target}: cannot stat ({exc})"]

    if not stat.S_ISREG(info.st_mode):
        return None, [f"{target}: not a regular file"]

    if info.st_size > _MAX_BYTES:
        return None, [f"{target}: {info.st_size} bytes exceeds {_MAX_BYTES} byte limit"]

    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [f"{target}: cannot read ({exc})"]

    try:
        doc = json.loads(raw)
    except ValueError as exc:
        return None, [f"{target}: invalid JSON ({exc})"]

    problems = validate_bindings_document(doc)
    if problems:
        return None, problems

    warnings: list[str] = []
    mode = stat.S_IMODE(info.st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        warnings.append(
            f"{target}: file permissions {oct(mode)} grant group/other access "
            f"(expected 0600) — permissions warning"
        )
    return doc, warnings


def save_bindings(doc: dict, path: str | Path | None = None) -> None:
    """Validate and atomically write ``doc`` to ``path`` (default location if None).

    Raises :class:`SurfaceBindingError` (or the more specific
    :class:`SurfaceBindingViolation`) listing every problem when ``doc`` does
    not validate; writes nothing in that case.  On success, the file is
    written ``0600`` inside a ``0700`` parent, atomically (temp file in the
    same directory, ``fsync``ed, then ``os.replace``d into place), with
    deterministic serialization (``sort_keys=True``).
    """
    _validate_or_raise(doc)

    target = _resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    content = (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")

    tmp = tempfile.NamedTemporaryFile(
        dir=os.fspath(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        os.fchmod(tmp.fileno(), 0o600)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, target)


# ---------------------------------------------------------------------------
# conflicts + construction helper
# ---------------------------------------------------------------------------

def find_conflicts(doc: dict) -> list[dict]:
    """Groups of >1 binding sharing ``(work_ref, role)``.

    Returns ``[{"work_ref", "role", "binding_ids": [sorted]}, ...]`` sorted by
    ``(work_ref, role)``.  Never picks a winner — that judgment belongs to a
    human via explicit unbind, never to this module.
    """
    bindings = (doc or {}).get("bindings") or []
    groups: dict[tuple[str, str], list[str]] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        work_ref = binding.get("work_ref")
        role = binding.get("role")
        binding_id = binding.get("binding_id")
        if not isinstance(work_ref, str) or not isinstance(role, str) or not isinstance(binding_id, str):
            continue
        groups.setdefault((work_ref, role), []).append(binding_id)

    result = [
        {"work_ref": work_ref, "role": role, "binding_ids": sorted(ids)}
        for (work_ref, role), ids in groups.items()
        if len(ids) > 1
    ]
    result.sort(key=lambda group: (group["work_ref"], group["role"]))
    return result


def new_binding(
    *,
    work_ref: str,
    role: str,
    provider: str,
    locator_kind: str,
    locator: dict,
    observed_at: str,
    seat_ref: str | None = None,
    last_verified_at: str | None = None,
    binding_id: str | None = None,
) -> dict:
    """Construct one valid Binding dict.

    ``observed_at`` (and ``last_verified_at`` if given) are caller-supplied —
    this function never reads the clock, so callers stay deterministic and
    testable.  ``binding_id`` defaults to a fresh ``uuid4``; pass one only to
    reconstruct a specific row (e.g. in a test fixture).
    """
    return {
        "binding_id": binding_id or str(uuid.uuid4()),
        "work_ref": work_ref,
        "role": role,
        "seat_ref": seat_ref,
        "provider": provider,
        "locator_kind": locator_kind,
        "locator": dict(locator),
        "observed_at": observed_at,
        "last_verified_at": last_verified_at,
    }
