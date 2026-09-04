"""integrations.chairman_surfaces.chatgpt — ChatGPT (managed-browser seat).

Managed-environment seat law (Sol architecture correction, MAS-113,
2026-08-22 — supersedes the Chrome-profile law of review 5000169412)
--------------------------------------------------------------------------
The Chairman's three Personal-Pro ChatGPT seats canonically live in
persistent GoLogin/Multilogin managed-browser environments, never an
ordinary Chrome profile. A GoLogin or Multilogin environment is identified
by an exact local identity — a GoLogin ``profile_id`` or a Multilogin
``folder_id`` + ``profile_id`` — plus the exact conversation URL; that pair
is the durable address :mod:`control_plane.surface_bindings` stores for this
provider (locator kind ``chatgpt_managed_env``).

Only an OFFICIAL, DOCUMENTED vendor surface may ever address one of these
environments. A deliberate investigation on the real machine plus a sweep of
both vendors' official documentation (multilogin.com/help "API basics — key
terms & concepts", "How to use headless mode", "Learn CLI commands", "Learn
CLI command flags", "Start working with CLI"; gologin.com/docs quickstart +
"Local Agent Browser CLI"; api.gologin.com/docs-json OpenAPI enumeration)
found that neither vendor documents a surface that can open a URL in, focus,
or attach automation to an environment that is ALREADY RUNNING as a
GUI-started profile:

* **Multilogin** — the local launcher API exposes only auth-gated
  start/stop; there is no documented focus or open-url verb, no documented
  start-URL parameter, and a GUI-started profile exposes no CDP port to
  attach to. The CLI requires an interactive credential login no session may
  perform.
* **GoLogin** — no local desktop control API is documented at all; the
  official SDK/CLI spawn a FRESH browser process rather than attaching to
  one already running, and (like Multilogin) require cloud authentication
  this module may never perform.

Because no documented surface exists for "act on an already-open managed
profile", :func:`open_surface` REFUSES CLOSED on every path — it never
falls back to an unofficial mechanism (no Chrome, no GUI-scripting, no
vendor binary execution, no HTTP call to a launcher/cloud API). This module's role
for ``chatgpt`` is durable exact addressing (:func:`env_exists`) plus a
best-effort LOCAL existence/liveness read (:func:`env_running`), never
launch, never focus, never a simulated key press.

Zero-message / no-config-mutation law
--------------------------------------
This module never simulates typing or sends any input event, never starts,
stops, or edits a managed-browser environment, and never reads or writes
proxy, fingerprint, or cookie configuration. It only stats directory names
under the vendors' own LOCAL profile-store paths and, for a running check,
reads (never mutates) the local process list.

GoLogin store law (operator veto)
------------------------------------
``~/Library/Caches/GoLogin`` and every other GoLogin-owned path are under a
standing operator no-delete veto ("GoLogin data is never deletable"). This
module only ever ``stat``s directory names inside that store — it never
writes, deletes, or renames anything there, and every test exercising this
module points its roots at a ``tmp_path`` fixture, never the real store.

ARGV-PRIVACY LAW
-----------------
A managed-browser process's command line (``ps`` output) carries live proxy
credentials in its ``--proxy-server``/authentication arguments. The raw
process-argument strings this module reads (:func:`env_running`'s
``process_args_reader``) are NEVER logged, returned, stored, or embedded in
any outcome or exception anywhere in this module — every function that
touches them returns ONLY a bool or an id already known from a directory
name, and every :class:`OpenOutcome` detail string in this module is a
fixed, static sentence carrying no locator or process content whatsoever.
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from control_plane import surface_bindings as sb

from . import contract
from . import runner as _runner_module

#: Default on-disk root of Multilogin's local profile store (macOS). Layout:
#: ``<root>/<workspace_id>/<folder_id>/<profile_id>/`` — the workspace id is
#: not part of the stored locator, so :func:`env_exists`/:func:`env_running`
#: search across whichever workspace directories exist locally.
MLX_PROFILES_ROOT = "~/mlx/profiles"

#: Default on-disk root of GoLogin's local profile cache (macOS). Layout:
#: ``<root>/<profile_id>/``.
GOLOGIN_PROFILES_ROOT = "~/Library/Caches/GoLogin/profiles"

#: Hard cap on how many environment identities :func:`list_local_environments`
#: ever reports per manager — this is a local discovery convenience, never an
#: inventory system, and a runaway store must not turn into an unbounded scan.
_DISCOVER_CAP = 200

#: Matches a ``--user-data-dir=<path>`` token inside one process command
#: line. The captured value is inspected only for its trailing path
#: component(s) — never logged or returned (see the module docstring's
#: ARGV-PRIVACY LAW).
_USER_DATA_DIR_RE = re.compile(r"--user-data-dir=(\S+)")


# ---------------------------------------------------------------------------
# process observation (read-only; never the outcome `runner`)
# ---------------------------------------------------------------------------

#: Explicit stdout cap for the full process-table snapshot.  The runner's
#: 64 KiB default silently DROPPED every managed-browser line on the real
#: machine (each Mimic/Orbita argv is kilobytes long and the host's table
#: exceeds 64 KiB), so a running seat read as stopped — measured live
#: 2026-08-22.  4 MiB comfortably holds any real process table.
_PS_SNAPSHOT_MAX_BYTES = 4 * 1024 * 1024

_STRICT_INVENTORY_MAX_IDENTITIES = 1000
_STRICT_INVENTORY_REFUSAL = "strict local environment inventory unavailable"
_HEX24_SHAPE_RE = re.compile(r"^[0-9a-fA-F]{24}$")
_STRICT_USER_DATA_DIR_RE = re.compile(r"(?:^|\s)--user-data-dir=(\S+)")


class _StrictInventoryRefusal(Exception):
    """Internal marker whose details never cross the strict producer seam."""


class _StrictInventoryUnavailable(RuntimeError):
    """Fixed, detail-free refusal exposed only by the private producer."""


def _strict_refuse():
    raise _StrictInventoryRefusal


def _same_file_identity(left, right) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _strict_open_root(root: str):
    """Open one root without following links; a never-present root is empty."""
    try:
        observed = os.lstat(root)
    except FileNotFoundError:
        return None
    except OSError:
        _strict_refuse()
    if not stat.S_ISDIR(observed.st_mode):
        _strict_refuse()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(root, flags)
    except OSError:
        _strict_refuse()
    try:
        opened = os.fstat(fd)
        current = os.lstat(root)
        if not _same_file_identity(observed, opened) or not _same_file_identity(opened, current):
            _strict_refuse()
    except Exception:
        os.close(fd)
        raise
    return fd, opened


def _strict_open_child(parent_fd: int, name: str, observed):
    if not stat.S_ISDIR(observed.st_mode):
        _strict_refuse()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
        opened = os.fstat(fd)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        _strict_refuse()
    if not _same_file_identity(observed, opened) or not _same_file_identity(opened, current):
        os.close(fd)
        _strict_refuse()
    return fd, opened


def _strict_entries(fd: int):
    try:
        with os.scandir(fd) as iterator:
            return sorted(iterator, key=lambda entry: entry.name)
    except OSError:
        _strict_refuse()


def _strict_revalidate_root(root: str, fd: int, opened) -> None:
    try:
        current = os.lstat(root)
        held = os.fstat(fd)
    except OSError:
        _strict_refuse()
    if not _same_file_identity(opened, held) or not _same_file_identity(held, current):
        _strict_refuse()


def _strict_revalidate_child(parent_fd: int, name: str, fd: int, opened) -> None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        held = os.fstat(fd)
    except OSError:
        _strict_refuse()
    if not _same_file_identity(opened, held) or not _same_file_identity(held, current):
        _strict_refuse()


def _strict_entry_stat(entry):
    try:
        return entry.stat(follow_symlinks=False)
    except OSError:
        _strict_refuse()


def _strict_count_identity(counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > _STRICT_INVENTORY_MAX_IDENTITIES:
        _strict_refuse()


def _strict_scan_multilogin(root: str, counter: list[int]) -> list[dict]:
    opened_root = _strict_open_root(root)
    if opened_root is None:
        return []
    root_fd, root_identity = opened_root
    rows = []
    authority_identities = set()
    try:
        for workspace_entry in _strict_entries(root_fd):
            if not sb.UUID_RE.fullmatch(workspace_entry.name):
                continue
            workspace_stat = _strict_entry_stat(workspace_entry)
            workspace_fd, workspace_identity = _strict_open_child(
                root_fd, workspace_entry.name, workspace_stat,
            )
            try:
                for folder_entry in _strict_entries(workspace_fd):
                    if not sb.UUID_RE.fullmatch(folder_entry.name):
                        continue
                    folder_stat = _strict_entry_stat(folder_entry)
                    folder_fd, folder_identity = _strict_open_child(
                        workspace_fd, folder_entry.name, folder_stat,
                    )
                    try:
                        for profile_entry in _strict_entries(folder_fd):
                            if not sb.UUID_RE.fullmatch(profile_entry.name):
                                continue
                            profile_stat = _strict_entry_stat(profile_entry)
                            profile_fd, profile_identity = _strict_open_child(
                                folder_fd, profile_entry.name, profile_stat,
                            )
                            try:
                                _strict_revalidate_child(
                                    folder_fd, profile_entry.name, profile_fd, profile_identity,
                                )
                            finally:
                                os.close(profile_fd)
                            workspace_id = workspace_entry.name.lower()
                            folder_id = folder_entry.name.lower()
                            profile_id = profile_entry.name.lower()
                            authority_identity = (folder_id, profile_id)
                            if authority_identity in authority_identities:
                                _strict_refuse()
                            authority_identities.add(authority_identity)
                            _strict_count_identity(counter)
                            rows.append({
                                "workspace_id": workspace_id,
                                "folder_id": folder_id,
                                "profile_id": profile_id,
                                "running": False,
                            })
                        _strict_revalidate_child(
                            workspace_fd, folder_entry.name, folder_fd, folder_identity,
                        )
                    finally:
                        os.close(folder_fd)
                _strict_revalidate_child(
                    root_fd, workspace_entry.name, workspace_fd, workspace_identity,
                )
            finally:
                os.close(workspace_fd)
        _strict_revalidate_root(root, root_fd, root_identity)
    finally:
        os.close(root_fd)
    return rows


def _strict_scan_gologin(root: str, counter: list[int]) -> list[dict]:
    opened_root = _strict_open_root(root)
    if opened_root is None:
        return []
    root_fd, root_identity = opened_root
    rows = []
    try:
        for profile_entry in _strict_entries(root_fd):
            if _HEX24_SHAPE_RE.fullmatch(profile_entry.name) and not sb.GOLOGIN_PROFILE_ID_RE.fullmatch(
                profile_entry.name
            ):
                _strict_refuse()
            if not sb.GOLOGIN_PROFILE_ID_RE.fullmatch(profile_entry.name):
                continue
            profile_stat = _strict_entry_stat(profile_entry)
            profile_fd, profile_identity = _strict_open_child(
                root_fd, profile_entry.name, profile_stat,
            )
            try:
                _strict_revalidate_child(
                    root_fd, profile_entry.name, profile_fd, profile_identity,
                )
            finally:
                os.close(profile_fd)
            _strict_count_identity(counter)
            rows.append({"profile_id": profile_entry.name, "running": False})
        _strict_revalidate_root(root, root_fd, root_identity)
    finally:
        os.close(root_fd)
    return rows


def _strict_managed_identity(value: str, mlx_root: str, gologin_root: str):
    if not os.path.isabs(value) or os.path.normpath(value) != value:
        for root in (mlx_root, gologin_root):
            if root in value:
                _strict_refuse()
        return None
    for manager, root in (("multilogin", mlx_root), ("gologin", gologin_root)):
        try:
            inside = os.path.commonpath((value, root)) == root
        except ValueError:
            inside = False
        if not inside:
            continue
        relative = os.path.relpath(value, root)
        parts = relative.split(os.sep)
        if manager == "gologin":
            if len(parts) != 1 or not sb.GOLOGIN_PROFILE_ID_RE.fullmatch(parts[0]):
                _strict_refuse()
            return manager, parts[0]
        if len(parts) != 3 or not all(sb.UUID_RE.fullmatch(part) for part in parts):
            _strict_refuse()
        return manager, parts[0].lower(), parts[1].lower(), parts[2].lower()
    return None


def _strict_reconcile_processes(stdout: str, mlx_root: str, gologin_root: str, rows: dict) -> None:
    known = {
        ("multilogin", row["workspace_id"], row["folder_id"], row["profile_id"])
        for row in rows["multilogin"]
    }
    known.update(("gologin", row["profile_id"]) for row in rows["gologin"])
    running = set()
    for line in stdout.splitlines():
        matches = list(_STRICT_USER_DATA_DIR_RE.finditer(line))
        recognized_spans = {match.span() for match in matches}
        for occurrence in re.finditer(r"(?:^|\s)--user-data-dir(?:=\S*)?", line):
            if occurrence.span() not in recognized_spans and (
                mlx_root in line or gologin_root in line
            ):
                _strict_refuse()
        managed = []
        for match in matches:
            identity = _strict_managed_identity(match.group(1), mlx_root, gologin_root)
            if identity is not None:
                managed.append(identity)
        if len(managed) > 1:
            _strict_refuse()
        if not managed:
            continue
        identity = managed[0]
        if identity not in known:
            _strict_refuse()
        running.add(identity)
    for row in rows["multilogin"]:
        row["running"] = (
            "multilogin", row["workspace_id"], row["folder_id"], row["profile_id"],
        ) in running
    for row in rows["gologin"]:
        row["running"] = ("gologin", row["profile_id"]) in running


def _strict_list_local_environments_impl(
    *, mlx_profiles_root=None, gologin_profiles_root=None, process_runner=None,
) -> dict:
    runner = process_runner or _runner_module.run_argv
    result = runner(
        ["/bin/ps", "-axo", "args="],
        timeout=5.0,
        max_bytes=_PS_SNAPSHOT_MAX_BYTES + 4,
    )
    if (
        not isinstance(result, dict)
        or set(result) != {"code", "stdout", "stderr", "timed_out"}
        or type(result["code"]) is not int
        or result["code"] != 0
        or type(result["stdout"]) is not str
        or type(result["stderr"]) is not str
        or type(result["timed_out"]) is not bool
        or result["timed_out"] is not False
        or "\ufffd" in result["stdout"]
        or "\ufffd" in result["stderr"]
        or len(result["stdout"].encode("utf-8")) > _PS_SNAPSHOT_MAX_BYTES
    ):
        _strict_refuse()
    mlx_root = os.path.abspath(os.path.expanduser(
        mlx_profiles_root if mlx_profiles_root is not None else MLX_PROFILES_ROOT
    ))
    gologin_root = os.path.abspath(os.path.expanduser(
        gologin_profiles_root if gologin_profiles_root is not None else GOLOGIN_PROFILES_ROOT
    ))
    try:
        roots_overlap = os.path.commonpath((mlx_root, gologin_root)) in (mlx_root, gologin_root)
    except ValueError:
        roots_overlap = True
    if roots_overlap:
        _strict_refuse()
    identity_count = [0]
    rows = {
        "multilogin": _strict_scan_multilogin(mlx_root, identity_count),
        "gologin": _strict_scan_gologin(gologin_root, identity_count),
    }
    _strict_reconcile_processes(result["stdout"], mlx_root, gologin_root, rows)
    return rows


def _strict_list_local_environments(
    *, mlx_profiles_root=None, gologin_profiles_root=None, process_runner=None,
) -> dict:
    """Return one complete, reconciled census or one fixed private refusal.

    Unlike :func:`list_local_environments`, this private producer is an
    all-or-nothing authority input for secret-capable callers.  Production
    callers cannot forward roots or a runner; those seams exist only for
    hermetic tests.
    """
    try:
        return _strict_list_local_environments_impl(
            mlx_profiles_root=mlx_profiles_root,
            gologin_profiles_root=gologin_profiles_root,
            process_runner=process_runner,
        )
    except Exception:  # noqa: BLE001 — collapse every probe detail
        pass
    raise _StrictInventoryUnavailable(_STRICT_INVENTORY_REFUSAL) from None


def _default_process_args_reader() -> list[str]:
    """Best-effort local process command-line snapshot via ``/bin/ps``.

    This is process OBSERVATION, not navigation — it goes through
    :func:`integrations.chairman_surfaces.runner.run_argv` (the package's one
    permitted subprocess boundary) directly, NEVER through the ``runner``
    callable a caller injects into :func:`open_surface` for navigation
    outcomes. Those are deliberately different code paths: a fake runner
    injected to prove "navigation never happened" must see zero calls even
    when this reader runs for real underneath it.

    Never raises; a failed/timed-out probe degrades to ``[]``.
    """
    result = _runner_module.run_argv(
        ["/bin/ps", "-axo", "args="], timeout=5.0, max_bytes=_PS_SNAPSHOT_MAX_BYTES
    )
    if not isinstance(result, dict) or result.get("timed_out") or result.get("code") != 0:
        return []
    stdout = result.get("stdout") or ""
    return stdout.splitlines()


def _lines_show_running(lines: list, manager: str, folder_id: str | None, profile_id: str) -> bool:
    """True iff some process line's ``--user-data-dir=`` value matches.

    multilogin: the value's LAST TWO path components must equal
    ``(folder_id, profile_id)`` exactly — an exact path-component match, not
    a substring check, so a profile id that happens to be a substring of a
    longer id never false-matches. gologin: any path component must equal
    ``profile_id`` exactly.

    Returns only a bool — the line content itself never leaves this
    function (ARGV-PRIVACY LAW, module docstring).
    """
    for line in lines:
        if not isinstance(line, str):
            continue
        match = _USER_DATA_DIR_RE.search(line)
        if not match:
            continue
        parts = [part for part in match.group(1).split("/") if part]
        if manager == "multilogin":
            if len(parts) >= 2 and parts[-2] == folder_id and parts[-1] == profile_id:
                return True
        elif manager == "gologin":
            if profile_id in parts:
                return True
    return False


# ---------------------------------------------------------------------------
# read-only local existence / liveness
# ---------------------------------------------------------------------------

def env_exists(locator: dict, *, mlx_profiles_root: str | None = None, gologin_profiles_root: str | None = None) -> bool:
    """True iff the locator's environment identity exists in the local store.

    Read-only ``stat``s only; tolerant of a missing/unreadable root (``False``,
    never raises). multilogin: some ``<root>/<workspace>/<folder_id>/
    <profile_id>`` directory exists, where ``<workspace>`` iterates the
    root's immediate UUID-shaped subdirectories (a non-UUID sibling, e.g. the
    real store's ``branding`` directory, is skipped). Bounded to three fixed
    levels — no unbounded recursion. gologin: ``<root>/<profile_id>`` is a
    directory.
    """
    if not isinstance(locator, dict):
        return False
    manager = locator.get("env_manager")

    if manager == "multilogin":
        folder_id = locator.get("folder_id")
        profile_id = locator.get("profile_id")
        if not isinstance(folder_id, str) or not isinstance(profile_id, str):
            return False
        root = Path(mlx_profiles_root).expanduser() if mlx_profiles_root else Path(MLX_PROFILES_ROOT).expanduser()
        try:
            workspace_entries = list(os.scandir(root))
        except OSError:
            return False
        for workspace_entry in workspace_entries:
            if not workspace_entry.is_dir(follow_symlinks=False):
                continue
            if not sb.UUID_RE.match(workspace_entry.name):
                continue
            candidate = Path(workspace_entry.path) / folder_id / profile_id
            try:
                if candidate.is_dir():
                    return True
            except OSError:
                continue
        return False

    if manager == "gologin":
        profile_id = locator.get("profile_id")
        if not isinstance(profile_id, str):
            return False
        root = Path(gologin_profiles_root).expanduser() if gologin_profiles_root else Path(GOLOGIN_PROFILES_ROOT).expanduser()
        candidate = root / profile_id
        try:
            return candidate.is_dir()
        except OSError:
            return False

    return False


def env_running(locator: dict, *, process_args_reader=None) -> bool:
    """Best-effort, read-only: is this environment's browser process alive.

    ``process_args_reader`` (default :func:`_default_process_args_reader`)
    returns the full local process command-line list; see the module
    docstring's ARGV-PRIVACY LAW — those strings never leave this module.
    Never raises; a failed reader degrades to ``False``.
    """
    if not isinstance(locator, dict):
        return False
    manager = locator.get("env_manager")
    reader = process_args_reader or _default_process_args_reader
    try:
        lines = reader()
    except Exception:  # noqa: BLE001 — a probe failure must never propagate
        return False
    if not isinstance(lines, list):
        return False

    if manager == "multilogin":
        folder_id = locator.get("folder_id")
        profile_id = locator.get("profile_id")
        if not isinstance(folder_id, str) or not isinstance(profile_id, str):
            return False
        return _lines_show_running(lines, "multilogin", folder_id, profile_id)

    if manager == "gologin":
        profile_id = locator.get("profile_id")
        if not isinstance(profile_id, str):
            return False
        return _lines_show_running(lines, "gologin", None, profile_id)

    return False


# ---------------------------------------------------------------------------
# navigation — refuses closed on every path (see module docstring)
# ---------------------------------------------------------------------------

def open_surface(
    binding: dict,
    runner,
    *,
    mlx_profiles_root: str | None = None,
    gologin_profiles_root: str | None = None,
    process_args_reader=None,
) -> dict:
    """Refuse closed. ``runner`` is accepted for uniform dispatch shape with
    every other adapter but is NEVER invoked — see the module docstring's
    managed-environment seat law for why no navigation primitive exists.
    """
    locator = binding.get("locator") if isinstance(binding, dict) else None
    locator = locator if isinstance(locator, dict) else {}
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    binding_id = binding_id if isinstance(binding_id, str) else None

    manager = locator.get("env_manager")
    if manager not in sb.ENV_MANAGERS:
        return contract.refused(
            "chatgpt", binding_id, "invalid_binding",
            f"the bound environment manager must be one of {sorted(sb.ENV_MANAGERS)}",
        )

    if manager == "multilogin":
        folder_id = locator.get("folder_id")
        profile_id = locator.get("profile_id")
        if not isinstance(folder_id, str) or not sb.UUID_RE.match(folder_id):
            return contract.refused("chatgpt", binding_id, "unsafe_token", "the bound folder id failed the safety check")
        if not isinstance(profile_id, str) or not sb.UUID_RE.match(profile_id):
            return contract.refused("chatgpt", binding_id, "unsafe_token", "the bound profile id failed the safety check")
    else:  # manager == "gologin"
        if "folder_id" in locator:
            return contract.refused(
                "chatgpt", binding_id, "invalid_binding",
                "gologin environments are addressed by profile_id only; folder_id is not part of the durable address",
            )
        profile_id = locator.get("profile_id")
        if not isinstance(profile_id, str) or not sb.GOLOGIN_PROFILE_ID_RE.match(profile_id):
            return contract.refused("chatgpt", binding_id, "unsafe_token", "the bound profile id failed the safety check")

    url = locator.get("url")
    if not isinstance(url, str) or not url:
        return contract.refused("chatgpt", binding_id, "invalid_binding", "the bound URL is missing")

    if not env_exists(locator, mlx_profiles_root=mlx_profiles_root, gologin_profiles_root=gologin_profiles_root):
        return contract.refused(
            "chatgpt", binding_id, "not_found",
            "the bound managed environment was not found in the local profile store",
        )

    if env_running(locator, process_args_reader=process_args_reader):
        return contract.refused(
            "chatgpt", binding_id, "unsupported_surface",
            "the bound environment is running, but the installed managed-browser surface "
            "documents no way to open a URL in, focus, or attach to a running profile; "
            "seat navigation is held rather than using an unofficial mechanism",
        )

    return contract.refused(
        "chatgpt", binding_id, "unsupported_surface",
        "the bound environment is not running; starting it requires cloud authentication "
        "and an undocumented restart path that could disrupt the persistent seat; "
        "navigation is held",
    )


# ---------------------------------------------------------------------------
# discovery — read-only local environment identities, zero ownership
# ---------------------------------------------------------------------------

def _scan_multilogin(root: Path, lines: list) -> list[dict]:
    entries: list[dict] = []
    try:
        workspace_dirs = sorted(
            (e for e in os.scandir(root) if e.is_dir(follow_symlinks=False)), key=lambda e: e.name,
        )
    except OSError:
        return entries
    for workspace_entry in workspace_dirs:
        if not sb.UUID_RE.match(workspace_entry.name):
            continue
        try:
            folder_dirs = sorted(
                (e for e in os.scandir(workspace_entry.path) if e.is_dir(follow_symlinks=False)), key=lambda e: e.name,
            )
        except OSError:
            continue
        for folder_entry in folder_dirs:
            if not sb.UUID_RE.match(folder_entry.name):
                continue
            try:
                profile_dirs = sorted(
                    (e for e in os.scandir(folder_entry.path) if e.is_dir(follow_symlinks=False)), key=lambda e: e.name,
                )
            except OSError:
                continue
            for profile_entry in profile_dirs:
                if not sb.UUID_RE.match(profile_entry.name):
                    continue
                entries.append({
                    "workspace_id": workspace_entry.name,
                    "folder_id": folder_entry.name,
                    "profile_id": profile_entry.name,
                    "running": _lines_show_running(lines, "multilogin", folder_entry.name, profile_entry.name),
                })
                if len(entries) >= _DISCOVER_CAP:
                    return entries
    return entries


def _scan_gologin(root: Path, lines: list) -> list[dict]:
    entries: list[dict] = []
    try:
        profile_dirs = sorted(
            (e for e in os.scandir(root) if e.is_dir(follow_symlinks=False)), key=lambda e: e.name,
        )
    except OSError:
        return entries
    for profile_entry in profile_dirs:
        if not sb.GOLOGIN_PROFILE_ID_RE.match(profile_entry.name):
            continue
        entries.append({
            "profile_id": profile_entry.name,
            "running": _lines_show_running(lines, "gologin", None, profile_entry.name),
        })
        if len(entries) >= _DISCOVER_CAP:
            return entries
    return entries


def list_local_environments(
    *, mlx_profiles_root: str | None = None, gologin_profiles_root: str | None = None, process_args_reader=None,
) -> dict:
    """Read-only census of local managed-browser environment identities.

    Returns ``{"multilogin": [{"workspace_id", "folder_id", "profile_id",
    "running"}, ...], "gologin": [{"profile_id", "running"}, ...]}``. IDs are
    harvested from directory names only (never from any cloud/vendor API —
    a display NAME requires cloud authentication no session may perform, so
    only ids are ever reported); each list is sorted lexicographically and
    capped at :data:`_DISCOVER_CAP` per manager. Tolerant of a missing root
    (empty list). Confers zero ownership/binding by itself.

    Takes exactly ONE process snapshot (via ``process_args_reader``, default
    :func:`_default_process_args_reader`) and reuses it for every entry's
    ``running`` flag — never forks a probe per profile.
    """
    reader = process_args_reader or _default_process_args_reader
    try:
        lines = reader()
    except Exception:  # noqa: BLE001 — a probe failure must never propagate
        lines = []
    if not isinstance(lines, list):
        lines = []

    mlx_root = Path(mlx_profiles_root).expanduser() if mlx_profiles_root else Path(MLX_PROFILES_ROOT).expanduser()
    gologin_root = Path(gologin_profiles_root).expanduser() if gologin_profiles_root else Path(GOLOGIN_PROFILES_ROOT).expanduser()

    return {
        "multilogin": _scan_multilogin(mlx_root, lines),
        "gologin": _scan_gologin(gologin_root, lines),
    }
