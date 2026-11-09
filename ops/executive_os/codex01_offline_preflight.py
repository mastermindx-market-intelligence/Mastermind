"""Credential-free macOS Sandbox preflight for CODEX-01 (source only).

This module deliberately cannot launch Codex, access a provider, enroll OAuth,
or change any installed service. It validates an isolated, default-deny
non-network host profile with ONLY fixed, harmless system/local probes.

It is a prerelease diagnostic. A later exact-binary parser qualification still
needs its own independent host/security review and original-owner action.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

SCHEMA = "mastermind.codex01_offline_preflight.v1"
SANDBOX = Path("/usr/bin/sandbox-exec")
TRUE = Path("/usr/bin/true")
PROBE_PYTHON = Path("/opt/homebrew/bin/python3")
SCRATCH_PARENT = Path("/private/tmp")
DENIED_READ_ROOTS = (
    "/Users",
    "/Volumes",
    "/Library/Keychains",
    "/Library/Application Support",
    "/private/var",
    "/private/etc",
    "/private/tmp",
    "/opt/homebrew/etc",
    "/usr/local/etc",
)
# System-only exceptions allow the Homebrew Python baseline on macOS 26.5.
# The remainder of /private/var (including private service state) stays denied.
SYSTEM_READ_EXCEPTIONS = (
    "/private/var/select",
    "/private/var/db/dyld",
)


def _literal(path: str) -> str:
    """A sandbox quoted literal; never embed caller-controlled SBPL source."""
    if not path.startswith("/") or "\x00" in path or "\n" in path:
        raise ValueError("absolute newline-free sandbox path required")
    return json.dumps(path, ensure_ascii=True)


def _strict_fixture_child(candidate: Path, parent: Path) -> bool:
    """Reject lexical traversal and existing aliases even for missing files.

    pathlib.is_relative_to alone is lexical: 'scratch/../outside' can pass.
    A missing leaf can also follow an existing symlinked ancestor; checking
    candidate.exists() before resolve would silently skip that case.
    """
    try:
        if (not isinstance(candidate, Path)
                or not candidate.is_absolute() or candidate == parent
                or ".." in candidate.parts
                or not candidate.is_relative_to(parent)):
            return False
        cursor = candidate
        while cursor != parent:
            if cursor.is_symlink():
                return False
            cursor = cursor.parent
        return candidate.resolve(strict=False).is_relative_to(
            parent.resolve(strict=False)
        )
    except (OSError, RuntimeError, ValueError):
        return False


def policy(scratch: Path, *, deny_fixture: Path | None = None,
           allow_fixture: Path | None = None) -> str:
    """Fixed defensive sandbox. Optional fixture paths are test-only.

    Broad executable/runtime file access is bounded by explicit sensitive-root
    denies; denied real credential locations are NEVER probed for contents.
    No explicit Mach, user-home, network, or additional write grant exists.
    """
    # Never turn the scratch exception into an ambient/home/volume grant.
    # This helper accepts only a direct child of the fixed private temp owner.
    if (not scratch.is_absolute() or scratch.parent != SCRATCH_PARENT
            or not scratch.name.startswith("mmx_codex01_offline_")
            or scratch.is_symlink()
            # No profile may be generated for an unowned future pathname:
            # the real preflight creates its mode-0700 scratch *first*.
            or not scratch.is_dir()
            or scratch.stat().st_uid != os.geteuid()
            or scratch.stat().st_mode & 0o777 != 0o700):
        raise ValueError("private scratch required")
    if deny_fixture is not None and not _strict_fixture_child(deny_fixture, scratch):
        raise ValueError("fixture must remain inside scratch")
    if allow_fixture is not None and (
        deny_fixture is None
        or not _strict_fixture_child(allow_fixture, deny_fixture)
    ):
        raise ValueError("only exact test fixture child can be allowed")
    clauses = [
        "(version 1)", "(deny default)", "(allow process-exec)",
        "(allow file-read*)",
    ]
    clauses.extend(
        f"(deny file-read* (subpath {_literal(root)}))"
        for root in DENIED_READ_ROOTS
    )
    clauses.extend(
        f"(allow file-read* (subpath {_literal(root)}))"
        for root in SYSTEM_READ_EXCEPTIONS
    )
    # Scratch is a noncredential test area. Put broad scratch access BEFORE
    # the fixture exception pair: on macOS SBPL a later general read grant
    # can defeat an earlier specific denial, as the real adversarial probe
    # demonstrated. The final literal permits ONLY its exact test file.
    clauses.extend((
        f"(allow file-read* (subpath {_literal(str(scratch))}))",
        f"(allow file-write* (subpath {_literal(str(scratch))}))",
    ))
    if deny_fixture is not None:
        clauses.append(
            f"(deny file-read* (subpath {_literal(str(deny_fixture))}))"
        )
    if allow_fixture is not None:
        clauses.append(
            f"(allow file-read* (literal {_literal(str(allow_fixture))}))"
        )
    clauses.append("(deny network*)")
    return "\n".join(clauses) + "\n"


def _env(scratch: Path) -> dict[str, str]:
    return {
        "HOME": str(scratch / "home"),
        "CODEX_HOME": str(scratch / "codex-home"),
        "XDG_CONFIG_HOME": str(scratch / "xdg"),
        "TMPDIR": str(scratch / "tmp"),
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _run(profile: Path, scratch: Path, argv: list[str]) -> tuple[int, str]:
    if any(not a or "\x00" in a for a in argv):
        raise ValueError("invalid inert probe argument")
    try:
        completed = subprocess.run(
            [str(SANDBOX), "-f", str(profile), *argv],
            cwd=scratch,
            env=_env(scratch),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    # Never return arbitrary stderr, filesystem details or user data.
    try:
        return completed.returncode, completed.stdout[:256].decode("ascii")
    except UnicodeDecodeError:
        return completed.returncode, ""


def _probe(profile: Path, scratch: Path, code: str) -> bool:
    # -I ignores PYTHONDONTWRITEBYTECODE; suppress cache writes explicitly.
    rc, stdout = _run(
        profile, scratch, [str(PROBE_PYTHON), "-I", "-B", "-S", "-c", code]
    )
    return rc == 0 and stdout.strip() == "DENIED"


def preflight() -> dict[str, object]:
    checks: dict[str, bool] = {}
    if platform.system() != "Darwin" or not (
        SANDBOX.is_file() and TRUE.is_file() and PROBE_PYTHON.is_file()
        and SCRATCH_PARENT.is_dir()
    ):
        return {"schema": SCHEMA, "state": "UNAVAILABLE",
                "checks": checks, "candidate_invoked": False,
                "provider_invoked": False, "installation_changed": False}

    with tempfile.TemporaryDirectory(prefix="mmx_codex01_offline_",
                                     dir=SCRATCH_PARENT) as temp:
        scratch = Path(temp)
        if (scratch.stat().st_mode & 0o777) != 0o700:
            raise RuntimeError("scratch must be user-private")
        for name in ("home", "codex-home", "xdg", "tmp"):
            (scratch / name).mkdir(mode=0o700)
        candidate = scratch / "candidate"
        candidate.write_text("public_test_only", encoding="ascii")
        # All probes stay inert even if the sandbox unexpectedly fails open.
        # A writable open on /dev/null requires write authority, but cannot
        # create a host file or change persistent state; never write to it.
        profile = scratch / "sandbox.sb"
        profile.write_text(policy(scratch), encoding="utf-8")
        profile.chmod(0o600)
        checks["system_binary"] = _run(profile, scratch, [str(TRUE)])[0] == 0
        checks["scratch_read"] = _probe(profile, scratch,
            f"import pathlib; p=pathlib.Path({str(candidate)!r});"
            "print('DENIED' if p.read_text()=='public_test_only' else 'FAIL')")
        for key, root in (
            ("home_read_denied", "/Users"),
            ("volume_read_denied", "/Volumes"),
            ("private_state_read_denied", "/private/var/db"),
            ("keychain_read_denied", "/Library/Keychains"),
            ("library_app_support_denied", "/Library/Application Support"),
            ("host_temp_listing_denied", "/private/tmp"),
            ("system_config_denied", "/private/etc"),
            ("brew_config_denied", "/opt/homebrew/etc"),
        ):
            # A fail-open sandbox must not enumerate sensitive directory
            # names: attempt only a read-capability open, close immediately,
            # and never call listdir/scandir/read on any real location.
            checks[key] = _probe(profile, scratch,
                f"import os,errno; p={root!r};"
                "e=0;"
                "\ntry: fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY);os.close(fd)"
                "\nexcept OSError as x: e=x.errno"
                "\nprint('DENIED' if e==errno.EPERM else 'FAIL')")
        checks["outside_write_denied"] = _probe(profile, scratch,
            "import os,errno; e=0;"
            "\ntry: fd=os.open('/dev/null',os.O_WRONLY);os.close(fd)"
            "\nexcept OSError as x: e=x.errno"
            "\nprint('DENIED' if e==errno.EPERM else 'FAIL')")
        checks["loopback_network_denied"] = _probe(profile, scratch,
            "import socket,errno;"
            "s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);"
            "e=s.connect_ex(('127.0.0.1',9));s.close();"
            "print('DENIED' if e==errno.EPERM else 'FAIL')")
        # AF_UNIX is a separate local-IPC threat boundary. Use ONLY a dummy
        # ephemeral listener in this controlled scratch; no installed socket
        # or privileged Control/Worker endpoint is ever approached.
        socket_path = scratch / "local-socket-only.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(1)
            checks["unix_socket_denied"] = _probe(profile, scratch,
                f"import socket,errno; p={str(socket_path)!r};"
                "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);"
                "e=s.connect_ex(p);s.close();"
                "print('DENIED' if e==errno.EPERM else 'FAIL')")
        # Prove exact literal read exception without reading any real binary
        # or loosening its forbidden sibling directory.
        fixture_root = scratch / "fixture-deny"
        fixture_root.mkdir()
        allowed = fixture_root / "safe"
        forbidden = fixture_root / "sibling"
        allowed.write_text("public_test_only", encoding="ascii")
        forbidden.write_text("dummy_forbidden_test_only", encoding="ascii")
        profile.write_text(
            policy(scratch, deny_fixture=fixture_root, allow_fixture=allowed),
            encoding="utf-8",
        )
        checks["literal_exception"] = _probe(profile, scratch,
            f"import pathlib; p=pathlib.Path({str(allowed)!r});"
            "print('DENIED' if p.read_text()=='public_test_only' else 'FAIL')")
        checks["sibling_stays_denied"] = _probe(profile, scratch,
            f"import os,errno; p={str(forbidden)!r};e=0;"
            "\ntry: os.open(p,os.O_RDONLY)"
            "\nexcept OSError as x: e=x.errno"
            "\nprint('DENIED' if e==errno.EPERM else 'FAIL')")
        alias = scratch / "test-alias"
        alias.symlink_to(forbidden)
        checks["sibling_symlink_stays_denied"] = _probe(profile, scratch,
            f"import os,errno; p={str(alias)!r};e=0;"
            "\ntry: os.open(p,os.O_RDONLY)"
            "\nexcept OSError as x: e=x.errno"
            "\nprint('DENIED' if e==errno.EPERM else 'FAIL')")
    return {
        "schema": SCHEMA,
        "state": "PASS" if checks and all(checks.values()) else "FAIL",
        "checks": checks,
        "candidate_invoked": False,
        "provider_invoked": False,
        "installation_changed": False,
    }


def main() -> int:
    # No generic argv, command execution, token, network, or candidate mode.
    if sys.argv[1:] != ["--preflight"]:
        print("offline benign preflight only: --preflight", file=sys.stderr)
        return 2
    try:
        receipt = preflight()
    except Exception:
        receipt = {"schema": SCHEMA, "state": "FAIL", "checks": {},
                   "candidate_invoked": False, "provider_invoked": False,
                   "installation_changed": False}
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["state"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
