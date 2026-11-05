"""Credential-free final-role isolation qualification probe for the Hermes Runtime.

This is a one-shot, bounded *host qualification utility*, not a model tool and
not a runtime component. It is executed by an operator inside one existing
final role service context and it reuses the production guards, in their
production order, so that the operator observes the real OS identity, the
effective cgroup, the qualified private paths and the effective TCP policy of
that context instead of a re-implementation of them:

    assert_root_service_cgroup -> assert_role_network_profile
    -> assert_role_credential_isolation -> enforce_role_tcp_ports

Nothing here is copied, weakened or re-derived; every guard below is imported
from the production module that owns it.

The probe never provisions an account, installs, starts, stops, restarts or
reloads a unit, edits a unit, changes a firewall or an authentication setting,
loads a secret, instantiates ``ServiceRuntime``, runs a canary or a text turn,
or calls a provider, a model or Slack. It binds only synthetic loopback
listeners, reads only synthetic credential-free files, and writes only its own
report. It is inert on import: importing it starts nothing, opens nothing and
reads no environment.

Two facts this module exists to keep honest:

* A missing listener or a refused connection is NOT denial proof. Every
  negative case therefore carries an independent positive witness: a kernel
  ``/proc/net/tcp`` LISTEN entry for the target port, and for the cross-role
  file case a peer-role probe report that proves the sibling file exists.
* A denial is only attributable to a control when the other control is known
  to permit the same target. Landlock restricts TCP *ports*; the unit's
  cgroup policy restricts *addresses*. The probe therefore records, per case,
  the layer that denies it and the facts that support that attribution.

A PASS is bound to the exact observed host identity, role, service context,
effective cgroup and selected matrix through ``context_fingerprint``. It is
never granted on a missing resource: an absent witness yields ``UNAVAILABLE``,
never ``PASS``. See ``docs/hermes/FINAL_ROLE_QUALIFICATION.md``.
"""
from __future__ import annotations

import argparse
import datetime
import errno
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import select
import signal
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass, field, replace
from typing import Any

from .constants import CONFIG_EXIT, IO_EXIT, POLICY_EXIT
from .egress import ROLE_PROXY_HOST, ROLE_PROXY_PORT
from .errors import RuntimeRefusal
from .profile import RuntimeProfile, load_profile
from .role_isolation import ROLE_ACCOUNTS, assert_role_credential_isolation
from .system_service import assert_role_network_profile, assert_root_service_cgroup
from .tcp_sandbox import enforce_role_tcp_ports, role_tcp_ports

SCHEMA = "mastermind.hermes_role_isolation_qualification.v1"

# The synthetic fixture content. It carries no credential and no operator data;
# it exists so that "the file was read" is a checkable fact rather than an
# assumption. Both roles use the same marker so a peer report can be matched.
SYNTHETIC_MARKER = b"mastermind-hermes-role-isolation-qualification-synthetic-v1\n"
SYNTHETIC_MARKER_SHA256 = hashlib.sha256(SYNTHETIC_MARKER).hexdigest()

# The documented fixed ports of the two existing final roles. A profile that
# disagrees is a drift finding, not a quiet pass.
ROLE_FIXED_PORTS = {
    "mmsecretary": {"gateway": 8765, "backend": 8766, "proxy": 18651},
    "mmmeta": {"gateway": 8865, "backend": 8866, "proxy": 18652},
}

# Synthetic ports used for the Landlock-isolation case. They are deliberately
# outside every role's allowed set and are not production ports. The operator
# may override them with any free unprivileged port.
DEFAULT_DENIED_PORT = {"mmsecretary": 45151, "mmmeta": 45152}

LISTEN_STATE = "0A"
MAX_REPORT_BYTES = 256 * 1024
DEFAULT_CONNECT_TIMEOUT = 2.0
LISTENER_TIMEOUT = 10.0
EXEC_TIMEOUT = 15.0

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_NOT_RUN = "NOT_RUN"

OBSERVED_ALLOWED = "ALLOWED"
OBSERVED_REFUSED = "REFUSED"
OBSERVED_UNAVAILABLE = "UNAVAILABLE"
OBSERVED_NOT_RUN = "NOT_RUN"
OBSERVED_ERROR = "ERROR"

# errno values that mean "the connection did not complete" rather than
# "the connection was actively refused". The cgroup IP policy blackholes the
# SYN, so a bounded connect surfaces as EAGAIN/ETIMEDOUT, while Landlock
# refuses the port immediately with EACCES. Keeping them apart is the whole
# point of the matrix.
IP_DENIAL_ERRNOS = frozenset({errno.EPERM, errno.EAGAIN, errno.ETIMEDOUT})
LANDLOCK_DENIAL_ERRNOS = frozenset({errno.EACCES, errno.EPERM})

_EXEC_PROBE = (
    "import socket,sys\n"
    "host=sys.argv[1]; port=int(sys.argv[2]); timeout=float(sys.argv[3])\n"
    "s=socket.socket(); s.settimeout(timeout)\n"
    "try:\n"
    "    s.connect((host,port)); print('OK')\n"
    "except TimeoutError:\n"
    "    print('TIMEOUT')\n"
    "except OSError as exc:\n"
    "    print('ERR:%d' % (exc.errno or 0))\n"
    "finally:\n"
    "    s.close()\n"
)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _errno_name(code: int | None) -> str | None:
    if code is None:
        return None
    return errno.errorcode.get(code, f"E{code}")


@dataclass(frozen=True)
class _Case:
    """One selected matrix case and the outcome it is expected to produce."""

    case_id: str
    dimension: str
    description: str
    expected: str
    host: str | None = None
    port: int | None = None
    listener: str | None = None


@dataclass
class _Outcome:
    """An honest observation. ``witness`` carries the proof the case needs."""

    observed: str
    errno: int | None = None
    errno_name: str | None = None
    symptom: str | None = None
    detail: str = ""
    attribution: str = ""
    basis: str = ""
    target: dict[str, Any] = field(default_factory=dict)
    witness: dict[str, Any] = field(default_factory=dict)


def _case_catalog() -> list[_Case]:
    """The full matrix. Identifiers are stable and are part of the contract."""
    return [
        _Case(
            "profile.fixed_ports",
            "profile",
            "the loaded profile carries this role's documented fixed gateway, "
            "backend and proxy ports",
            OBSERVED_ALLOWED,
        ),
        _Case(
            "tcp.own_alias.gateway_port",
            "tcp",
            "own role alias on the Landlock-allowed gateway port must be reachable",
            OBSERVED_ALLOWED,
            listener="own_gateway",
        ),
        _Case(
            "tcp.own_alias.backend_port",
            "tcp",
            "own role alias on the Landlock-allowed backend port must be reachable",
            OBSERVED_ALLOWED,
            listener="own_backend",
        ),
        _Case(
            "tcp.sibling_alias.gateway_port",
            "tcp",
            "sibling role alias on a Landlock-ALLOWED port: Landlock permits the "
            "port, so any denial is attributable to the cgroup IP policy",
            OBSERVED_REFUSED,
            listener="sibling_gateway",
        ),
        _Case(
            "tcp.shared_loopback.gateway_port",
            "tcp",
            "127.0.0.1 on a Landlock-ALLOWED port: Landlock permits the port, so "
            "any denial is attributable to the cgroup IP policy",
            OBSERVED_REFUSED,
            listener="shared_loopback_gateway",
        ),
        _Case(
            "tcp.own_alias.denied_port",
            "tcp",
            "own role alias on an unrelated wildcard listener port that Landlock "
            "does not allow: the IP policy permits the address, so any denial is "
            "attributable to Landlock",
            OBSERVED_REFUSED,
            listener="wildcard_denied",
        ),
        _Case(
            "file.own.read",
            "file",
            "this role's own synthetic credential-free file is readable here",
            OBSERVED_ALLOWED,
        ),
        _Case(
            "file.peer.read",
            "file",
            "the sibling role's synthetic file is denied to this role",
            OBSERVED_REFUSED,
        ),
        _Case(
            "exec.own_alias.denied_port",
            "exec",
            "an exec'd descendant still inherits the Landlock port denial",
            OBSERVED_REFUSED,
        ),
        _Case(
            "exec.own_alias.gateway_port",
            "exec",
            "an exec'd descendant retains the Landlock-allowed gateway port, so "
            "the inherited denial is port-specific and not a blanket refusal",
            OBSERVED_ALLOWED,
        ),
    ]


def _bind_cases(role: str, gateway_port: int, backend_port: int,
                denied_port: int) -> list[_Case]:
    """Bind the static matrix to the profile's actual ports and aliases.

    The matrix is a contract of case identifiers; the addresses and ports it
    exercises are properties of the observed profile, not constants of the
    tool.
    """
    own_alias = ROLE_PROXY_HOST[role]
    peer_role = "mmmeta" if role == "mmsecretary" else "mmsecretary"
    peer_alias = ROLE_PROXY_HOST[peer_role]
    targets = {
        "tcp.own_alias.gateway_port": (own_alias, gateway_port),
        "tcp.own_alias.backend_port": (own_alias, backend_port),
        "tcp.sibling_alias.gateway_port": (peer_alias, gateway_port),
        "tcp.shared_loopback.gateway_port": ("127.0.0.1", gateway_port),
        "tcp.own_alias.denied_port": (own_alias, denied_port),
        "exec.own_alias.denied_port": (own_alias, denied_port),
        "exec.own_alias.gateway_port": (own_alias, gateway_port),
    }
    return [replace(case, host=host, port=port)
            for case, (host, port) in
            ((case, targets.get(case.case_id, (None, None)))
             for case in _case_catalog())]


def _status_for(case: _Case, outcome: _Outcome) -> str:
    if outcome.observed == OBSERVED_NOT_RUN:
        return STATUS_NOT_RUN
    if outcome.observed == OBSERVED_UNAVAILABLE:
        return STATUS_UNAVAILABLE
    if outcome.observed == OBSERVED_ERROR:
        return STATUS_FAIL
    if case.expected == OBSERVED_ALLOWED:
        return STATUS_PASS if outcome.observed == OBSERVED_ALLOWED else STATUS_FAIL
    if outcome.observed == OBSERVED_REFUSED:
        # A refusal is only denial proof when the positive witness exists.
        return STATUS_PASS if outcome.witness.get("sufficient") else STATUS_UNAVAILABLE
    return STATUS_FAIL


def _case_record(case: _Case, outcome: _Outcome, *, selected: bool) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "dimension": case.dimension,
        "description": case.description,
        "selected": selected,
        "expected": case.expected,
        "observed": outcome.observed,
        "status": _status_for(case, outcome),
        "errno": outcome.errno,
        "errno_name": outcome.errno_name,
        "symptom": outcome.symptom,
        "attribution": outcome.attribution,
        "attribution_basis": outcome.basis,
        "witness": outcome.witness,
        "detail": outcome.detail,
        "target": outcome.target or {"host": case.host, "port": case.port},
    }


def _hex_to_ipv4(hex_address: str) -> str | None:
    """Convert a /proc/net/tcp local address into a dotted quad."""
    try:
        raw = bytes.fromhex(hex_address)
    except ValueError:
        return None
    if len(raw) != 4:
        return None
    return ".".join(str(byte) for byte in reversed(raw))


def _listening_local_addresses(port: int) -> list[str]:
    """Kernel LISTEN evidence for a port, independent of any probe self-report."""
    found: list[str] = []
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        path = Path(table)
        try:
            if not path.exists():
                continue
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 4 or parts[3] != LISTEN_STATE:
                continue
            hex_address, _, hexport = parts[1].partition(":")
            try:
                if int(hexport, 16) != port:
                    continue
            except ValueError:
                continue
            address = _hex_to_ipv4(hex_address)
            if address is not None:
                found.append(address)
    return sorted(found)


def _matching_listen_entries(entries: list[str], bind_host: str) -> list[str]:
    """The LISTEN entries that actually cover the address under test.

    A wildcard listener covers every address, so every entry on the port
    matches it. A listener bound to one alias only matches that alias, which
    keeps a sibling's listener from being mistaken for this target's witness.
    """
    if bind_host in ("0.0.0.0", ""):
        return list(entries)
    return [entry for entry in entries if entry == bind_host]


def _connect(host: str, port: int, timeout: float) -> tuple[int | None, str]:
    """Attempt one bounded TCP connect.

    Returns ``(errno, symptom)``. ``errno`` is ``None`` when the connection
    was established. A timeout is reported as ``EAGAIN`` because that is how a
    bounded connect surfaces a blackholed SYN; it is kept distinct from an
    immediate refusal.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            try:
                sock.settimeout(timeout)
                sock.recv(64)
            except OSError:
                pass
        return None, "connected"
    except TimeoutError:
        return errno.EAGAIN, "timed_out"
    except OSError as exc:
        code = exc.errno if isinstance(exc.errno, int) else errno.EIO
        return code, "refused_immediately"


def _spawn_listener(bind_host: str, bind_port: int) -> tuple[int, dict[str, Any]]:
    """Fork a child that binds and listens on one synthetic address.

    The child is forked *before* the Landlock restriction is applied, because
    the wildcard witness must bind a port that Landlock will later refuse to
    bind. The child reports the kernel's own bind result, which is the
    positive witness that a listener exists on that exact address and port.
    """
    read_fd, write_fd = os.pipe()
    sys.stdout.flush()
    sys.stderr.flush()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - child process
        os.close(read_fd)
        receipt: dict[str, Any] = {"bind_host": bind_host, "bind_port": bind_port}
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # No SO_REUSEADDR/SO_REUSEPORT: an occupied port must fail rather
            # than be stolen from the service that legitimately owns it.
            sock.bind((bind_host, bind_port))
            sock.listen(16)
            receipt["bound"] = True
            receipt["listen_port"] = sock.getsockname()[1]
        except OSError as exc:
            receipt["bound"] = False
            receipt["errno"] = exc.errno if isinstance(exc.errno, int) else errno.EIO
            receipt["errno_name"] = _errno_name(receipt["errno"])
        try:
            os.write(write_fd, json.dumps(receipt).encode("utf-8") + b"\n")
        except OSError:
            pass
        os.close(write_fd)
        if receipt.get("bound") and sock is not None:
            while True:
                try:
                    connection, _ = sock.accept()
                except OSError:
                    break
                try:
                    connection.sendall(b"HELMES-ISO-PROBE\n")
                except OSError:
                    pass
                finally:
                    connection.close()
        os._exit(0)
    os.close(write_fd)
    receipt = {"bind_host": bind_host, "bind_port": bind_port}
    try:
        ready, _, _ = select.select([read_fd], [], [], LISTENER_TIMEOUT)
        if ready:
            raw = os.read(read_fd, 65536)
            if raw:
                receipt.update(json.loads(raw.decode("utf-8")))
        else:
            receipt["bound"] = False
            receipt["detail"] = "listener receipt timed out"
    except (OSError, ValueError, UnicodeError):
        receipt.setdefault("bound", False)
        receipt["detail"] = "listener receipt unreadable"
    finally:
        os.close(read_fd)
    return pid, receipt


def _terminate_children(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for pid in pids:
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass


def _exec_probe(host: str, port: int, timeout: float) -> tuple[str, int | None]:
    """Run the connect probe in an exec'd descendant.

    Landlock restrictions are inherited across fork and exec, so this is how
    the matrix proves that a descendant cannot escape the confinement.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _EXEC_PROBE, host, str(port), str(timeout)],
            capture_output=True, text=True, timeout=EXEC_TIMEOUT, close_fds=True,
            env={"PATH": os.defpath, "LC_ALL": "C"},
        )
    except subprocess.TimeoutExpired:
        return "timeout", None
    except OSError:
        return "error", None
    output = completed.stdout.strip()
    if completed.returncode != 0:
        return "error", None
    if output == "OK":
        return "connected", None
    if output == "TIMEOUT":
        return "timed_out", errno.EAGAIN
    if output.startswith("ERR:"):
        try:
            code = int(output[4:])
        except ValueError:
            return "error", None
        return "refused_immediately", code
    return "error", None


def _identity_facts(role: str) -> dict[str, Any]:
    """Actual NSS identity and effective cgroup of the running context."""
    try:
        account = pwd.getpwnam(ROLE_ACCOUNTS[role])
        group = grp.getgrnam(ROLE_ACCOUNTS[role])
    except (KeyError, OSError):
        # The production guard reports the same condition; the probe must not
        # fail with an unhandled lookup error before the guard runs.
        raise RuntimeRefusal("ROLE_OS_ACCOUNT_UNAVAILABLE") from None
    try:
        cgroup_raw = Path("/proc/self/cgroup").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        cgroup_raw = ""
    expected = f"/system.slice/hermes-runtime-{role}.service"
    effective = None
    for line in cgroup_raw.splitlines():
        if line.startswith("0::"):
            value = line[3:]
            if value == expected or value.startswith(expected + "/"):
                effective = value
                break
    return {
        "role": role,
        "nss_user": account.pw_name,
        "nss_uid": account.pw_uid,
        "nss_primary_gid": account.pw_gid,
        "nss_gid": group.gr_gid,
        "nss_home": account.pw_dir,
        "process_uid": os.getuid(),
        "process_euid": os.geteuid(),
        "process_gid": os.getgid(),
        "process_egid": os.getegid(),
        "process_groups": sorted(os.getgroups()),
        "uid_is_nss_uid": os.getuid() == account.pw_uid == os.geteuid(),
        "gid_is_nss_gid": os.getgid() == group.gr_gid == os.getegid(),
        "no_extra_supplementary_groups": set(os.getgroups()) <= {group.gr_gid},
        "effective_cgroup_expected": expected,
        "effective_cgroup_observed": effective,
        "effective_cgroup_raw": cgroup_raw.strip().splitlines(),
    }


def _path_facts(path: Path) -> dict[str, Any]:
    """Ownership/mode facts for one path and every ancestor of it.

    Recorded so a reviewer can see *why* the production private-path guard
    accepted the path. The guard itself decides; this only observes. An
    ordinary writable ``/tmp`` ancestor shows up here as an ancestor that is
    not root- or role-owned, or that carries a group/other write bit, which is
    exactly the condition the production guard refuses.
    """
    facts: dict[str, Any] = {"path": str(path)}
    ancestors = []
    for parent in path.parents:
        entry: dict[str, Any] = {"path": str(parent)}
        try:
            item = parent.lstat()
        except OSError as exc:
            entry["available"] = False
            entry["errno_name"] = _errno_name(
                exc.errno if isinstance(exc.errno, int) else errno.EIO
            )
            ancestors.append(entry)
            continue
        entry["available"] = True
        entry["mode"] = oct(stat.S_IMODE(item.st_mode))
        entry["uid"] = item.st_uid
        entry["gid"] = item.st_gid
        entry["is_directory"] = stat.S_ISDIR(item.st_mode)
        entry["group_or_other_writable"] = bool(stat.S_IMODE(item.st_mode) & 0o022)
        ancestors.append(entry)
    facts["ancestors"] = ancestors
    try:
        info = path.lstat()
    except OSError as exc:
        facts["available"] = False
        facts["errno"] = exc.errno if isinstance(exc.errno, int) else errno.EIO
        facts["errno_name"] = _errno_name(facts["errno"])
        return facts
    facts["available"] = True
    facts["is_directory"] = stat.S_ISDIR(info.st_mode)
    facts["is_regular"] = stat.S_ISREG(info.st_mode)
    facts["mode"] = oct(stat.S_IMODE(info.st_mode))
    facts["uid"] = info.st_uid
    facts["gid"] = info.st_gid
    facts["nlink"] = info.st_nlink
    return facts


def _load_peer_report(path: Path | None, peer_role: str) -> tuple[dict[str, Any] | None, str]:
    """Load and validate the sibling role's probe report.

    The peer report is the independent existence witness for the sibling's
    synthetic file: only the sibling role itself can prove that the file is
    readable in its own private directory. An operator assertion is not a
    witness and does not unlock a PASS.
    """
    if path is None:
        return None, "no peer report supplied"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"peer report unreadable: {_errno_name(exc.errno)}"
    if len(raw) > MAX_REPORT_BYTES:
        return None, "peer report too large"
    try:
        report = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        return None, "peer report is not valid JSON"
    if not isinstance(report, dict):
        return None, "peer report is not an object"
    if report.get("schema") != SCHEMA:
        return None, "peer report schema mismatch"
    if report.get("role") != peer_role:
        return None, "peer report is for a different role"
    own_file = report.get("own_file")
    if not isinstance(own_file, dict):
        return None, "peer report carries no own_file record"
    if own_file.get("status") != STATUS_PASS:
        return None, "peer role did not prove its own file readable"
    if own_file.get("sha256") != SYNTHETIC_MARKER_SHA256:
        return None, "peer file digest is not the synthetic marker"
    file_path = own_file.get("path")
    if not isinstance(file_path, str) or not file_path.startswith("/"):
        return None, "peer report own_file path is not absolute"
    return report, "peer probe report accepted"


def _peer_witness(report: dict[str, Any] | None, peer_file: Path) -> dict[str, Any]:
    """Match the supplied peer file against the peer report's own file."""
    if report is None:
        return {"kind": "none", "sufficient": False,
                "note": "no independent witness for the sibling file"}
    own_file = report.get("own_file") or {}
    recorded = str(own_file.get("path", ""))
    if recorded != str(peer_file):
        return {"kind": "peer_probe_report", "sufficient": False,
                "note": "peer report records a different sibling file path"}
    return {
        "kind": "peer_probe_report",
        "sufficient": True,
        "note": "sibling role proved its own file readable in its private directory",
        "peer_role": report.get("role"),
        "peer_file_path": recorded,
        "peer_file_sha256": own_file.get("sha256"),
    }


def _run_guards(profile: RuntimeProfile, role: str) -> tuple[list[dict[str, Any]], bool]:
    """Run the production guards in their production order.

    The first three are pure observations. The fourth irreversibly restricts
    this process, so it is run only after the witnesses are in place and only
    when the first three all passed.
    """
    results: list[dict[str, Any]] = []

    def guard(name: str, call) -> bool:
        try:
            call()
        except RuntimeRefusal as exc:
            results.append({"name": name, "status": "REFUSED", "code": exc.code})
            return False
        results.append({"name": name, "status": STATUS_PASS, "code": None})
        return True

    ok = guard("assert_root_service_cgroup", lambda: assert_root_service_cgroup(role))
    if ok:
        ok = guard("assert_role_network_profile", lambda: assert_role_network_profile(profile))
    if ok:
        ok = guard("assert_role_credential_isolation",
                   lambda: assert_role_credential_isolation(profile))
    return results, ok


def _profile_ports_outcome(profile: RuntimeProfile, role: str) -> _Outcome:
    expected = ROLE_FIXED_PORTS.get(role)
    observed = {
        "gateway": profile.gateway_port,
        "backend": profile.backend_port,
        "proxy": ROLE_PROXY_PORT.get(role),
    }
    if expected is None:
        return _Outcome(OBSERVED_ERROR, detail="unknown role")
    if observed == expected:
        return _Outcome(OBSERVED_ALLOWED, detail="profile ports match the fixed role ports",
                        witness={"kind": "profile", "sufficient": True})
    return _Outcome(OBSERVED_ERROR,
                    detail=f"profile ports {observed} differ from the fixed role ports {expected}",
                    witness={"kind": "profile", "sufficient": True})


def _tcp_attribution(case: _Case, outcome_errno: int | None,
                     landlock_connect: frozenset[int]) -> tuple[str, str]:
    """Attribute a denial to the control that actually refused it.

    Landlock's TCP rule is port-scoped, so a port inside the role's connect
    set is permitted by Landlock and any denial of it comes from the cgroup
    address policy. A port outside the set is refused by Landlock, and the
    address policy is separately exercised by the own-alias cases.
    """
    port = case.port
    if outcome_errno is None:
        return ("NONE", "the connect completed; neither control refused it")
    if port is not None and port in landlock_connect:
        return ("CGROUP_IP_POLICY",
                "the target port is inside the role's Landlock connect set, so "
                "Landlock permits it; the address is outside the unit's single "
                "IPAddressAllow /32")
    return ("LANDLOCK_TCP_PORT",
            "the target port is outside the role's Landlock connect set, so "
            "Landlock refuses it independently of the address policy")


def _file_outcome_own(path: Path, state_dir: Path, uid: int, gid: int) -> _Outcome:
    """This role's own synthetic file must be readable and be the marker."""
    target = {"path": str(path)}
    witness: dict[str, Any] = {"kind": "kernel_stat", "sufficient": False}
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return _Outcome(OBSERVED_UNAVAILABLE, detail="own synthetic file is not present",
                        target=target, witness=witness)
    if resolved != path:
        return _Outcome(OBSERVED_ERROR, detail="own synthetic file is not a real path",
                        target=target, witness=witness)
    try:
        state_resolved = state_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return _Outcome(OBSERVED_UNAVAILABLE, detail="state directory is not present",
                        target=target, witness=witness)
    if state_resolved not in resolved.parents:
        return _Outcome(OBSERVED_ERROR,
                        detail="own synthetic file is not inside this role's state directory",
                        target=target, witness=witness)
    try:
        info = path.lstat()
    except OSError as exc:
        code = exc.errno if isinstance(exc.errno, int) else errno.EIO
        return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                        detail="own synthetic file could not be inspected",
                        target=target, witness=witness)
    witness.update({"path": str(path), "uid": info.st_uid, "gid": info.st_gid,
                    "mode": oct(stat.S_IMODE(info.st_mode)), "nlink": info.st_nlink})
    if not stat.S_ISREG(info.st_mode):
        return _Outcome(OBSERVED_ERROR, detail="own synthetic file is not a regular file",
                        target=target, witness=witness)
    if info.st_uid != uid or info.st_gid != gid:
        return _Outcome(OBSERVED_ERROR, detail="own synthetic file is not role-owned",
                        target=target, witness=witness)
    if stat.S_IMODE(info.st_mode) != 0o600:
        return _Outcome(OBSERVED_ERROR, detail="own synthetic file is not mode 0600",
                        target=target, witness=witness)
    try:
        content = path.read_bytes()
    except OSError as exc:
        code = exc.errno if isinstance(exc.errno, int) else errno.EIO
        return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                        symptom="refused_immediately",
                        detail="own synthetic file could not be read",
                        target=target, witness=witness)
    digest = hashlib.sha256(content).hexdigest()
    witness.update({"sha256": digest, "sufficient": True})
    if digest != SYNTHETIC_MARKER_SHA256:
        return _Outcome(OBSERVED_ERROR,
                        detail="own synthetic file is not the credential-free marker",
                        target=target, witness=witness)
    return _Outcome(OBSERVED_ALLOWED, detail="own synthetic file read; content is the marker",
                    target=target, witness=witness)


def _file_outcome_peer(path: Path, witness: dict[str, Any]) -> _Outcome:
    """The sibling role's synthetic file must be denied to this role."""
    target = {"path": str(path)}
    stat_outcome = _try_stat(path)
    read_outcome = _try_read(path)
    denied_errno = None
    denied_at = None
    for label, result in (("directory_traversal", stat_outcome),
                          ("file_mode", read_outcome)):
        if result["errno"] in (errno.EACCES, errno.EPERM):
            denied_errno = result["errno"]
            denied_at = label
            break
    if denied_errno is None:
        if read_outcome["readable"]:
            return _Outcome(OBSERVED_ALLOWED,
                            detail="the sibling role's synthetic file was readable here",
                            target=target, witness=witness)
        code = read_outcome.get("errno")
        if code == errno.ENOENT:
            # A missing sibling fixture is a missing resource, never a
            # denial and never a breach.
            return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                            detail="the sibling role's synthetic file is not present",
                            target=target, witness=witness)
        return _Outcome(OBSERVED_ERROR, errno=code, errno_name=_errno_name(code),
                        detail="the sibling file was neither readable nor cleanly refused",
                        target=target, witness=witness)
    detail = f"sibling file denied at {denied_at}"
    if not witness.get("sufficient"):
        detail += "; no independent witness that the sibling file exists"
    return _Outcome(OBSERVED_REFUSED, errno=denied_errno, errno_name=_errno_name(denied_errno),
                    symptom="refused_immediately", detail=detail, target=target,
                    witness=witness)


def _try_stat(path: Path) -> dict[str, Any]:
    try:
        info = path.stat()
    except OSError as exc:
        code = exc.errno if isinstance(exc.errno, int) else errno.EIO
        return {"ok": False, "errno": code, "errno_name": _errno_name(code)}
    return {"ok": True, "errno": None, "errno_name": None, "mode": oct(stat.S_IMODE(info.st_mode)),
            "uid": info.st_uid, "gid": info.st_gid}


def _try_read(path: Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            content = handle.read(4096)
    except OSError as exc:
        code = exc.errno if isinstance(exc.errno, int) else errno.EIO
        return {"readable": False, "errno": code, "errno_name": _errno_name(code)}
    return {"readable": True, "errno": None, "errno_name": None,
            "sha256": hashlib.sha256(content).hexdigest()}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hermes-role-isolation-qualification-probe",
        description=(
            "One-shot, credential-free final-role isolation qualification probe. "
            "It must run inside the role's own service cgroup, as the role account."
        ),
    )
    parser.add_argument("--profile", type=Path,
                        help="the role's installed profile.yaml (never a secret)")
    parser.add_argument("--role", choices=sorted(ROLE_ACCOUNTS),
                        help="the final role whose service context is being qualified")
    parser.add_argument("--own-file", type=Path,
                        help="this role's synthetic credential-free fixture file")
    parser.add_argument("--peer-file", type=Path,
                        help="the sibling role's synthetic credential-free fixture file")
    parser.add_argument("--peer-report", type=Path,
                        help="the sibling role's probe report (the file existence witness)")
    parser.add_argument("--denied-port", type=int,
                        help="a free unprivileged port outside the role's allowed set")
    parser.add_argument("--report", type=Path, help="write the JSON report here as well")
    parser.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT,
                        help="bounded connect timeout in seconds")
    parser.add_argument("--only", default="",
                        help="comma-separated subset of case ids to select")
    parser.add_argument("--list-cases", action="store_true",
                        help="print the matrix identifiers and exit")
    args = parser.parse_args(argv)
    if args.list_cases:
        return args
    missing = [name for name in ("profile", "role", "own_file", "peer_file")
               if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(sorted(missing)))
    if args.connect_timeout <= 0 or args.connect_timeout > 30:
        parser.error("--connect-timeout must be in (0, 30]")
    return args


def _selected_cases(selection: str) -> set[str]:
    if not selection.strip():
        return {case.case_id for case in _case_catalog()}
    wanted = {item.strip() for item in selection.split(",") if item.strip()}
    known = {case.case_id for case in _case_catalog()}
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError("unknown case ids: " + ", ".join(unknown))
    return wanted


def _write_report(report: dict[str, Any], path: Path | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if path is not None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    sys.stdout.write(text)


def _run_probe(args: argparse.Namespace) -> int:
    try:
        selected = _selected_cases(args.only)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return CONFIG_EXIT

    try:
        profile = load_profile(args.profile)
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return CONFIG_EXIT
    except OSError:
        print("PROFILE_UNREADABLE", file=sys.stderr)
        return IO_EXIT

    if profile.role != args.role:
        print("PROBE_ROLE_PROFILE_MISMATCH", file=sys.stderr)
        return CONFIG_EXIT

    role = profile.role
    peer_role = "mmmeta" if role == "mmsecretary" else "mmsecretary"
    own_alias = ROLE_PROXY_HOST[role]
    peer_alias = ROLE_PROXY_HOST[peer_role]
    gateway_port = profile.gateway_port
    backend_port = profile.backend_port

    bind_ports, connect_ports = role_tcp_ports(profile)
    denied_port = args.denied_port or DEFAULT_DENIED_PORT[role]
    if not 1024 <= denied_port <= 65535:
        print("PROBE_DENIED_PORT_INVALID", file=sys.stderr)
        return CONFIG_EXIT
    if denied_port in (bind_ports | connect_ports):
        print("PROBE_DENIED_PORT_ALLOWED", file=sys.stderr)
        return CONFIG_EXIT
    if denied_port in ROLE_FIXED_PORTS[peer_role].values():
        print("PROBE_DENIED_PORT_PEER_COLLISION", file=sys.stderr)
        return CONFIG_EXIT

    identity = _identity_facts(role)
    uid = identity["nss_uid"]
    gid = identity["nss_gid"]

    guards, guards_ok = _run_guards(profile, role)

    def not_run(case: _Case, reason: str) -> _Outcome:
        return _Outcome(OBSERVED_NOT_RUN, detail=reason, witness={"kind": "none", "sufficient": False})

    catalog = _bind_cases(role, gateway_port, backend_port, denied_port)
    records: dict[str, dict[str, Any]] = {}

    def emit(case: _Case, outcome: _Outcome) -> None:
        records[case.case_id] = _case_record(case, outcome,
                                              selected=case.case_id in selected)

    if not guards_ok:
        for case in catalog:
            emit(case, not_run(case, "a production guard refused before the matrix ran"))
        report = _build_report(profile, role, peer_role, identity, guards, records,
                               selected, bind_ports, connect_ports, denied_port,
                               args, witnesses={}, listeners={})
        _write_report(report, args.report)
        return CONFIG_EXIT

    # ---- witnesses -------------------------------------------------------
    # Every listener is bound before the Landlock restriction, because the
    # wildcard witness must occupy a port that Landlock will refuse to bind.
    listener_specs = [
        ("own_gateway", own_alias, gateway_port, own_alias),
        ("own_backend", own_alias, backend_port, own_alias),
        ("sibling_gateway", peer_alias, gateway_port, peer_alias),
        ("shared_loopback_gateway", "127.0.0.1", gateway_port, "127.0.0.1"),
        ("wildcard_denied", "0.0.0.0", denied_port, own_alias),
    ]
    listeners: dict[str, dict[str, Any]] = {}
    unconfined: dict[str, dict[str, Any]] = {}
    exec_unconfined: tuple[str, int | None] = ("not_run", None)
    child_pids: list[int] = []
    try:
        for key, bind_host, bind_port, serve_host in listener_specs:
            pid, receipt = _spawn_listener(bind_host, bind_port)
            child_pids.append(pid)
            receipt["serve_host"] = serve_host
            entries = _listening_local_addresses(bind_port)
            receipt["kernel_listen_entries"] = entries
            receipt["kernel_matching_entries"] = _matching_listen_entries(entries, bind_host)
            receipt["kernel_listening"] = bool(receipt["kernel_matching_entries"])
            listeners[key] = receipt

        # Unconfined positive witnesses. The own-alias and wildcard targets are
        # reachable from this context when no port restriction applies, so a
        # later refusal of the same target is attributable to the restriction
        # that was applied in between.
        for key, bind_host, bind_port, serve_host in listener_specs:
            receipt = listeners[key]
            if not receipt.get("bound"):
                unconfined[key] = {"reached": False, "reason": "listener did not bind"}
                continue
            code, symptom = _connect(serve_host, bind_port, args.connect_timeout)
            unconfined[key] = {
                "reached": code is None,
                "errno": code,
                "errno_name": _errno_name(code),
                "symptom": symptom,
                "target": f"{serve_host}:{bind_port}",
            }

        # An exec'd descendant must be able to reach the wildcard witness
        # before the restriction, otherwise a later refusal proves nothing.
        exec_unconfined = _exec_probe(own_alias, denied_port, args.connect_timeout)

        # ---- the irreversible production restriction -----------------------
        try:
            enforce_role_tcp_ports(profile)
        except RuntimeRefusal as exc:
            guards.append({"name": "enforce_role_tcp_ports", "status": "REFUSED",
                           "code": exc.code})
            for case in catalog:
                emit(case, not_run(case, "the TCP port policy could not be applied"))
            report = _build_report(profile, role, peer_role, identity, guards, records,
                                   selected, bind_ports, connect_ports, denied_port,
                                   args, witnesses={"unconfined": unconfined,
                                                    "exec_unconfined": exec_unconfined},
                                   listeners=listeners)
            _write_report(report, args.report)
            return CONFIG_EXIT
        guards.append({"name": "enforce_role_tcp_ports", "status": STATUS_PASS, "code": None})

        # ---- the confined matrix ------------------------------------------
        # This runs while the synthetic listeners are still alive: a listener
        # that is gone makes every connect to it meaningless.
        for case in catalog:
            if case.case_id not in selected:
                emit(case, not_run(case, "not selected for this run"))
                continue
            if case.dimension == "profile":
                emit(case, _profile_ports_outcome(profile, role))
            elif case.dimension == "tcp":
                emit(case, _tcp_outcome(case, listeners, unconfined, connect_ports,
                                        args.connect_timeout))
            elif case.dimension == "file":
                emit(case, _file_outcome(case, profile, uid, gid, args.own_file,
                                         args.peer_file, args.peer_report))
            elif case.dimension == "exec":
                emit(case, _exec_outcome(case, exec_unconfined, args.connect_timeout))
            else:  # pragma: no cover - the catalog is closed
                emit(case, not_run(case, "unknown dimension"))
    finally:
        _terminate_children(child_pids)

    report = _build_report(profile, role, peer_role, identity, guards, records,
                           selected, bind_ports, connect_ports, denied_port, args,
                           witnesses={"unconfined": unconfined,
                                      "exec_unconfined": exec_unconfined},
                           listeners=listeners)
    _write_report(report, args.report)
    return _exit_code(report)


def _tcp_outcome(case: _Case, listeners: dict[str, dict[str, Any]],
                 unconfined: dict[str, dict[str, Any]],
                 landlock_connect: frozenset[int], timeout: float) -> _Outcome:
    listener = listeners.get(case.listener or "", {})
    if not listener.get("bound"):
        code = listener.get("errno")
        return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                        detail=f"the synthetic listener for this case did not bind "
                               f"({_errno_name(code)})",
                        witness={"kind": "bind_receipt", "sufficient": False,
                                 "note": "no listener exists, so no refusal can be proof"})
    kernel_listening = bool(listener.get("kernel_listening"))
    baseline = unconfined.get(case.listener or "", {})
    code, symptom = _connect(case.host or "", case.port or 0, timeout)
    attribution, basis = _tcp_attribution(case, code, landlock_connect)

    if case.expected == OBSERVED_ALLOWED:
        witness = {
            "kind": "kernel_listen_entry",
            "sufficient": kernel_listening,
            "kernel_listen_entries": listener.get("kernel_matching_entries", []),
            "unconfined_reached": baseline.get("reached"),
        }
        if code is None:
            return _Outcome(OBSERVED_ALLOWED, symptom=symptom,
                            detail="connect completed on the role's own alias",
                            attribution="NONE", basis="neither control refused it",
                            witness=witness)
        return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                        symptom=symptom,
                        detail="the role's own allowed port was not reachable",
                        attribution="UNDETERMINED",
                        basis="the own alias is permitted by the address policy and "
                              "the port is permitted by Landlock, so neither refusal "
                              "is attributable to either control",
                        witness=witness)

    # Expected refusal.
    witness = {
        "kind": "kernel_listen_entry",
        "sufficient": kernel_listening,
        "kernel_listen_entries": listener.get("kernel_matching_entries", []),
        "unconfined_reached": baseline.get("reached"),
        "unconfined_errno_name": baseline.get("errno_name"),
        "note": "a refusal counts as denial proof only because the kernel "
                "reports a LISTEN socket on the target address and port",
    }
    if code is None:
        return _Outcome(OBSERVED_ALLOWED, symptom=symptom,
                        detail="a target that must be denied was reachable",
                        attribution="NONE", basis="neither control refused it",
                        witness=witness)
    if code == errno.ECONNREFUSED:
        return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                        symptom=symptom,
                        detail="connection refused; a refused connection is not denial proof",
                        attribution="UNDETERMINED", basis="no control established a refusal",
                        witness={"kind": "bind_receipt", "sufficient": False,
                                 "note": "ECONNREFUSED is never counted as a denial"})
    return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                    symptom=symptom, detail="connect was denied as required",
                    attribution=attribution, basis=basis, witness=witness)


def _file_outcome(case: _Case, profile: RuntimeProfile, uid: int, gid: int,
                  own_file: Path, peer_file: Path,
                  peer_report_path: Path | None) -> _Outcome:
    if case.case_id == "file.own.read":
        return _file_outcome_own(own_file, profile.state_dir, uid, gid)
    peer_role = "mmmeta" if profile.role == "mmsecretary" else "mmsecretary"
    report, reason = _load_peer_report(peer_report_path, peer_role)
    witness = _peer_witness(report, peer_file)
    witness["source"] = reason
    return _file_outcome_peer(peer_file, witness)


def _exec_outcome(case: _Case, exec_unconfined: tuple[str, int | None],
                  timeout: float) -> _Outcome:
    """An exec'd descendant must inherit the restriction, and only it."""
    baseline_symptom, baseline_errno = exec_unconfined
    witness = {
        "kind": "exec_descendant",
        "sufficient": baseline_symptom == "connected",
        "unconfined_exec_symptom": baseline_symptom,
        "unconfined_exec_errno_name": _errno_name(baseline_errno),
        "note": "the same exec probe reached the target before the restriction",
    }
    if case.case_id == "exec.own_alias.gateway_port":
        symptom, code = _exec_probe(case.host or "", case.port or 0, timeout)
        if symptom == "connected":
            return _Outcome(OBSERVED_ALLOWED, symptom=symptom,
                            detail="the exec'd descendant retained the allowed port",
                            witness={**witness, "sufficient": True})
        return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                        symptom=symptom,
                        detail="the exec'd descendant lost an allowed port",
                        attribution="LANDLOCK_TCP_PORT",
                        basis="the port is inside the role's connect set",
                        witness={**witness, "sufficient": True})
    if baseline_symptom != "connected":
        return _Outcome(OBSERVED_UNAVAILABLE,
                        detail="the exec probe never reached the target before the "
                               "restriction, so the inherited denial is not proven",
                        witness=witness)
    symptom, code = _exec_probe(case.host or "", case.port or 0, timeout)
    if symptom == "connected":
        return _Outcome(OBSERVED_ALLOWED, symptom=symptom,
                        detail="the exec'd descendant escaped the port denial",
                        witness={**witness, "sufficient": True})
    if code == errno.ECONNREFUSED:
        return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                        symptom=symptom,
                        detail="connection refused; a refused connection is not denial proof",
                        witness={**witness, "sufficient": False})
    return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                    symptom=symptom,
                    detail="the exec'd descendant inherited the port denial",
                    attribution="LANDLOCK_TCP_PORT",
                    basis="the port is outside the role's connect set and the "
                          "denial is inherited across exec",
                    witness={**witness, "sufficient": True})


def _build_report(profile: RuntimeProfile, role: str, peer_role: str,
                  identity: dict[str, Any], guards: list[dict[str, Any]],
                  records: dict[str, dict[str, Any]], selected: set[str],
                  bind_ports: frozenset[int], connect_ports: frozenset[int],
                  denied_port: int, args: argparse.Namespace,
                  witnesses: dict[str, Any], listeners: dict[str, Any]) -> dict[str, Any]:
    matrix = [records[key] for key in sorted(records)]
    counts = {"pass": 0, "fail": 0, "unavailable": 0, "not_run": 0}
    for record in matrix:
        if not record["selected"]:
            counts["not_run"] += 1
            continue
        status = record["status"]
        if status == STATUS_PASS:
            counts["pass"] += 1
        elif status == STATUS_FAIL:
            counts["fail"] += 1
        elif status == STATUS_UNAVAILABLE:
            counts["unavailable"] += 1
        else:
            counts["not_run"] += 1
    if counts["fail"]:
        status = "FAIL"
    elif counts["unavailable"] or counts["not_run"]:
        status = "INCOMPLETE"
    else:
        status = "PASS"

    context = {
        "role": role,
        "peer_role": peer_role,
        "service_name": profile.service_name,
        "expected_cgroup": f"/system.slice/{profile.service_name}",
        "identity": identity,
        "gateway_host": profile.gateway_host,
        "gateway_port": profile.gateway_port,
        "backend_port": profile.backend_port,
        "proxy_host": ROLE_PROXY_HOST[role],
        "proxy_port": ROLE_PROXY_PORT[role],
        "state_dir": str(profile.state_dir),
        "secrets_file": str(profile.secrets_file),
        "landlock_bind_ports": sorted(bind_ports),
        "landlock_connect_ports": sorted(connect_ports),
        "denied_port": denied_port,
    }
    fingerprint = hashlib.sha256(
        json.dumps({"context": context, "selected": sorted(selected)},
                   sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return {
        "schema": SCHEMA,
        "tool": {
            "module": "integrations.hermes_runtime.isolation_probe",
            "kind": "one-shot host qualification utility",
            "model_tool": False,
            "controller": False,
        },
        "generated_at_utc": _utc_now(),
        "role": role,
        "peer_role": peer_role,
        "status": status,
        "qualified": status == "PASS",
        "context_fingerprint": fingerprint,
        "selected_matrix": sorted(selected),
        "context": context,
        "guards": guards,
        "guard_order": [entry["name"] for entry in guards],
        "private_paths": {
            "state_dir": _path_facts(profile.state_dir),
            "secrets_parent": _path_facts(profile.secrets_file.parent),
            "secrets_file": _path_facts(profile.secrets_file),
        },
        "listeners": listeners,
        "witnesses": witnesses,
        "matrix": matrix,
        "counts": counts,
        "own_file": {
            "path": str(args.own_file),
            "sha256": SYNTHETIC_MARKER_SHA256,
            "status": (records.get("file.own.read") or {}).get("status"),
        },
        "scope": {
            "prepared_fixture": True,
            "final_production_configuration": False,
            "statement": (
                "This report qualifies the isolation controls of one observed "
                "final role service context using synthetic, credential-free "
                "fixtures. It does not qualify the production endpoints, the "
                "incumbent hermes-egress.service proxy, any credential, any "
                "provider, TLS, billing, Slack or a cutover."
            ),
        },
        "limitations": [
            "The proxy port is deliberately out of scope: a synthetic listener "
            "would not be the incumbent hermes-egress.service and cannot stand "
            "in for final proxy proof.",
            "The matrix proves the address and port controls of the observed "
            "cgroup and Landlock policy. It is not proof of effective BPF "
            "enforcement on every kernel, of UDP or Unix-domain isolation, or "
            "of vendor CONNECT ACLs.",
            "An absent witness yields UNAVAILABLE and never PASS; a missing "
            "listener, a refused connection or a skipped case is not denial proof.",
            "A PASS is bound to context_fingerprint. A different host identity, "
            "role, cgroup, profile or selected matrix is a different result.",
        ],
    }


def _exit_code(report: dict[str, Any]) -> int:
    status = report["status"]
    if status == "PASS":
        return 0
    if status == "FAIL":
        return POLICY_EXIT
    return CONFIG_EXIT


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.list_cases:
        print(json.dumps({"schema": SCHEMA,
                          "cases": [case.case_id for case in _case_catalog()]},
                         indent=2))
        return 0
    try:
        return _run_probe(args)
    except RuntimeRefusal as exc:
        print(exc.code, file=sys.stderr)
        return CONFIG_EXIT
    except OSError as exc:
        code = exc.errno if isinstance(exc.errno, int) else errno.EIO
        print(f"PROBE_IO_ERROR:{_errno_name(code)}", file=sys.stderr)
        return IO_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
