"""B6 — an enforceable launch contract for candidate backends.

A closed environment is not a disabled network. This module supplies the real
boundary or refuses to pretend:

* **network denial** is enforced by a host launcher (`sandbox-exec` with a
  deny-network profile on Darwin) and *attested by a live canary*, never assumed;
* **CPU, address space, open files and processes** are bounded with `setrlimit`
  in the child before `exec`;
* the child **leads its own process group**, so descendants can be reaped and
  proven dead rather than leaked.

If the host cannot supply an enforceable launcher, `build_sandbox` raises
`SandboxUnavailable`. The caller must record the typed blocker; it may not
relabel a closed environment as a disabled network.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "DEFAULT_LIMITS",
    "sandbox_launcher_available",
    "LaunchLimits",
    "SandboxContract",
    "SandboxUnavailable",
    "build_sandbox",
]

# A deny-network profile that otherwise leaves the child able to read the sealed
# tree. `allow default` keeps the profile minimal and auditable; the one thing it
# removes is exactly the thing C0 must prove absent.
_DENY_NETWORK_PROFILE = """(version 1)
(allow default)
(deny network*)
"""

_NETWORK_CANARY = (
    "import json,socket\n"
    "socket.setdefaulttimeout(6)\n"
    "notes = []\n"
    "dns_ok = tcp_ok = False\n"
    "try:\n"
    "    socket.getaddrinfo('pypi.org', 443); dns_ok = True\n"
    "except Exception as exc:\n"
    "    notes.append('dns ' + type(exc).__name__ + ': ' + str(exc)[:90])\n"
    "try:\n"
    "    s = socket.create_connection(('1.1.1.1', 443), timeout=6); s.close(); tcp_ok = True\n"
    "except Exception as exc:\n"
    "    notes.append('tcp ' + type(exc).__name__ + ': ' + str(exc)[:90])\n"
    "print(json.dumps({'reachable': dns_ok or tcp_ok, 'dns': dns_ok, 'tcp': tcp_ok,"
    " 'detail': '; '.join(notes) or 'both probes succeeded'}))\n"
)


class SandboxUnavailable(Exception):
    """The required boundary cannot be enforced on this host. Fail closed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class LaunchLimits:
    cpu_seconds: int
    address_space_bytes: int
    max_open_files: int
    max_processes: int


DEFAULT_LIMITS = LaunchLimits(
    cpu_seconds=120,
    address_space_bytes=2 * 1024 * 1024 * 1024,
    max_open_files=256,
    # NOTE: on Darwin RLIMIT_NPROC counts processes for the whole USER, not for
    # this process group. A tight value therefore starves unrelated work by the
    # same user rather than bounding the candidate — measured: it broke the
    # network canary in both sandboxed and unsandboxed runs and made the
    # attestation vacuous. Kept generous, and named as a limitation.
    max_processes=2048,
)


def _launcher_path() -> str | None:
    """The host-supplied network-denying launcher, if this platform has one."""
    return shutil.which("sandbox-exec")


@functools.lru_cache(maxsize=1)
def _linux_launcher() -> tuple[str, ...] | None:
    """A network-denying launcher prefix on Linux, verified to actually exec.

    `bwrap --unshare-net` is preferred; `unshare -r -n` is the fallback where
    user namespaces are permitted. Both are PROBED here — a launcher that cannot
    run is treated as absent, never as enforcement.
    """
    candidates: list[tuple[str, ...]] = []
    bwrap = shutil.which("bwrap")
    if bwrap:
        candidates.append((bwrap, "--unshare-net", "--dev-bind", "/", "/", "--"))
    unshare = shutil.which("unshare")
    if unshare:
        candidates.append((unshare, "-r", "-n", "--"))
    for prefix in candidates:
        try:
            probe = subprocess.run(
                [*prefix, "/bin/sh", "-c", "exit 0"],
                capture_output=True, timeout=30, shell=False,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode != 0:
            continue
        # Exec-ing is not enforcing. A launcher that runs but leaves the network
        # reachable is treated as ABSENT, so "available" can never mean less than
        # "actually denies".
        try:
            verdict = subprocess.run(
                [*prefix, str(Path(sys.executable).resolve()), "-c", _NETWORK_CANARY],
                capture_output=True, text=True, timeout=60, shell=False,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
            observed = json.loads(verdict.stdout.strip().splitlines()[-1])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            continue
        if not observed.get("reachable"):
            return prefix
    return None


_LIMIT_PROBE = (
    "import json,resource\n"
    "want = json.loads(__import__('sys').argv[1])\n"
    "out = {}\n"
    "for name, value in want.items():\n"
    "    r = getattr(resource, name)\n"
    "    try:\n"
    "        resource.setrlimit(r, (value, value)); out[name] = True\n"
    "    except Exception:\n"
    "        out[name] = False\n"
    "print(json.dumps(out))\n"
)

_LIMIT_FIELDS = {
    "RLIMIT_CPU": "cpu_seconds",
    "RLIMIT_AS": "address_space_bytes",
    "RLIMIT_NOFILE": "max_open_files",
    "RLIMIT_NPROC": "max_processes",
}


@dataclass(frozen=True, slots=True)
class SandboxContract:
    network_denied: bool
    launcher_argv: tuple[str, ...]
    profile_path: Path | None
    profile_digest: str
    limits: LaunchLimits
    #: Limits this host was measured to actually apply, and those it cannot.
    #: Nothing here is assumed: both sets come from a live probe at build time.
    enforced_limits: tuple[str, ...] = ()
    unenforced_limits: tuple[str, ...] = ()

    # ------------------------------------------------------------------ launch

    def wrap(self, argv: Sequence[str]) -> list[str]:
        """Prefix a command with the enforcing launcher."""
        return [*self.launcher_argv, *argv]

    def preexec(self):
        """Return a preexec callable applying limits and a new process group."""
        limits = self.limits

        def _apply() -> None:  # pragma: no cover - runs in the forked child
            os.setsid()
            for name, field in _LIMIT_FIELDS.items():
                value = getattr(limits, field)
                try:
                    resource.setrlimit(getattr(resource, name), (value, value))
                except (ValueError, OSError):
                    # Darwin rejects RLIMIT_AS outright. Unenforceable limits are
                    # reported by `unenforced_limits`, never silently claimed.
                    continue

        return _apply

    def child_env(self, scratch: Path) -> dict[str, str]:
        return {
            "PATH": "/usr/bin:/bin",
            "HOME": str(scratch),
            "TMPDIR": str(scratch),
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    # ----------------------------------------------------------------- probing

    def run_probe(
        self, executable: Path, args: Sequence[str], *, timeout: int = 60
    ) -> Any:
        """Run a short JSON-emitting probe under this contract."""
        completed = subprocess.run(
            self.wrap([str(executable), *args]),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            preexec_fn=self.preexec(),
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
        if completed.returncode != 0:
            raise SandboxUnavailable(
                "SANDBOX_PROBE_FAILED",
                f"rc={completed.returncode} {completed.stderr.strip()[:200]}",
            )
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def attest_no_network(self, *, timeout: int = 40) -> dict[str, Any]:
        """Live canary: prove the child cannot reach the network."""
        import sys

        completed = subprocess.run(
            self.wrap([str(Path(sys.executable).resolve()), "-c", _NETWORK_CANARY]),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            preexec_fn=self.preexec(),
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
        try:
            observed = json.loads(completed.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            # A child that could not even report is treated as unattested.
            return {
                "network_denied": False,
                "probe": "tcp+dns",
                "dns": None,
                "tcp": None,
                "detail": f"canary produced no verdict: {completed.stderr[:160]}",
            }
        return {
            "network_denied": not observed["reachable"],
            "probe": "tcp+dns",
            "dns": observed.get("dns"),
            "tcp": observed.get("tcp"),
            "detail": observed["detail"],
        }


def _measure_enforceable_limits(
    limits: LaunchLimits,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Measure which rlimits this host actually applies. Never assume."""
    import sys

    want = {name: getattr(limits, field) for name, field in _LIMIT_FIELDS.items()}
    completed = subprocess.run(
        [str(Path(sys.executable).resolve()), "-c", _LIMIT_PROBE, json.dumps(want)],
        capture_output=True, text=True, timeout=60, shell=False,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    if completed.returncode != 0:
        return (), tuple(sorted(want))
    observed = json.loads(completed.stdout.strip().splitlines()[-1])
    enforced = tuple(sorted(k for k, ok in observed.items() if ok))
    unenforced = tuple(sorted(k for k, ok in observed.items() if not ok))
    return enforced, unenforced


def build_sandbox(
    *,
    scratch: Path,
    limits: LaunchLimits = DEFAULT_LIMITS,
    require_network_denial: bool = True,
) -> SandboxContract:
    """Build an enforcing contract, or fail closed with a typed blocker."""
    launcher = None
    linux_prefix: tuple[str, ...] | None = None
    if require_network_denial:
        launcher = _launcher_path()
        if launcher is None:
            linux_prefix = _linux_launcher()

    if linux_prefix is not None:
        enforced, unenforced = _measure_enforceable_limits(limits)
        return SandboxContract(
            network_denied=True,
            launcher_argv=linux_prefix,
            profile_path=None,
            profile_digest=hashlib.sha256(
                " ".join(linux_prefix).encode("utf-8")
            ).hexdigest(),
            limits=limits,
            enforced_limits=enforced,
            unenforced_limits=unenforced,
        )

    if launcher is None:
        if require_network_denial:
            raise SandboxUnavailable(
                "SANDBOX_NETWORK_DENIAL_UNAVAILABLE",
                "no host launcher can deny network on this platform; a closed "
                "environment is not a disabled network",
            )
        enforced, unenforced = _measure_enforceable_limits(limits)
        return SandboxContract(
            network_denied=False,
            launcher_argv=(),
            profile_path=None,
            profile_digest=hashlib.sha256(b"").hexdigest(),
            limits=limits,
            enforced_limits=enforced,
            unenforced_limits=unenforced,
        )

    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    profile_path = scratch / "codeintel-c0-deny-network.sb"
    profile_path.write_text(_DENY_NETWORK_PROFILE, encoding="utf-8")
    enforced, unenforced = _measure_enforceable_limits(limits)
    return SandboxContract(
        network_denied=True,
        launcher_argv=(launcher, "-f", str(profile_path)),
        profile_path=profile_path,
        profile_digest=hashlib.sha256(
            _DENY_NETWORK_PROFILE.encode("utf-8")
        ).hexdigest(),
        limits=limits,
        enforced_limits=enforced,
        unenforced_limits=unenforced,
    )


def kill_process_group(
    pid: int | None = None,
    *,
    pgid: int | None = None,
    reap: Any = None,
    grace: float = 3.0,
) -> dict[str, Any]:
    """Terminate a child's whole group and receipt whether it actually died.

    ``reap`` must be a callable that reaps the direct child (``Popen.poll`` does).
    It is called between signal and liveness check because a terminated but
    UNREAPED child is a zombie, and a zombie keeps its process group alive — so
    without reaping, ``killpg(pgid, 0)`` reports a survivor that is really just
    an unclaimed exit status. That is a real Linux behaviour, not a race.
    """
    import time

    if pgid is None:
        if pid is None:
            return {"group_signalled": False, "descendants_alive": 0,
                    "detail": "no process to signal"}
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError):
            return {"group_signalled": False, "descendants_alive": 0,
                    "detail": "already gone"}

    def _reap() -> None:
        if reap is not None:
            try:
                reap()
            except Exception:  # pragma: no cover - defensive
                pass

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            _reap()
            return {"group_signalled": True, "descendants_alive": 0,
                    "detail": "group already gone"}
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            _reap()
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError):
                return {"group_signalled": True, "descendants_alive": 0,
                        "detail": f"died on {sig.name}"}
            time.sleep(0.05)

    _reap()
    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError):
        return {"group_signalled": True, "descendants_alive": 0, "detail": "died"}
    return {"group_signalled": True, "descendants_alive": 1, "detail": "group still alive"}


def sandbox_launcher_available() -> bool:
    """True when this host can actually deny network to a child process."""
    return _launcher_path() is not None or _linux_launcher() is not None
