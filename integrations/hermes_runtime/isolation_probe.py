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

* A missing listener or a refused connection is NOT denial proof. The port
  cases require a current owned PID/start/socket-inode witness before and after
  the attempt plus the same-target pre-Landlock positive. Same-cgroup listeners
  cannot supply an external cgroup-policy positive; copied peer reports cannot
  establish current fixture existence behind an inaccessible parent.
* A denial is only attributable to a control when the other control is known
  to permit the same target. Landlock restricts TCP *ports*; the unit's
  cgroup policy restricts *addresses*. The probe therefore records, per case,
  the layer that denies it and the facts that support that attribution.

``--external-address-fixtures`` is one closed boolean for one bounded case:
the operator supplies the fixture for the two address-denial cases from
outside the role cgroup, so the probe omits its internal listeners for exactly
those two cases and still attempts the same derived targets. It supplies no
host, port, path, command or authority, and it never turns an unwitnessed
attempt into a denial proof: the outside-cgroup pre/post bracket remains
separate evidence.

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
import math
import os
from pathlib import Path
import pwd
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
import uuid
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any
from types import CodeType

from .constants import CONFIG_EXIT, IO_EXIT, POLICY_EXIT
from .egress import ROLE_PROXY_HOST, ROLE_PROXY_PORT
from .errors import RuntimeRefusal
from .profile import RuntimeProfile, load_profile
from .role_isolation import ROLE_ACCOUNTS, assert_role_credential_isolation
from .system_service import assert_role_network_profile, assert_root_service_cgroup
from .tcp_sandbox import enforce_role_tcp_ports, role_tcp_ports

SCHEMA = "mastermind.hermes_role_isolation_qualification.v2"

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
LISTENER_LIFETIME = 600.0
MAX_PEER_AGE = 900.0
GUARD_ORDER = ("assert_root_service_cgroup", "assert_role_network_profile",
               "assert_role_credential_isolation", "enforce_role_tcp_ports")

# The two address-denial cases whose fixture listener may be owned outside the
# role cgroup. Their case identifiers, targets, fixed ports and expectations are
# unchanged: only the owner of the fixture differs. --external-address-fixtures
# therefore omits the internal listener for exactly these two listener keys and
# still attempts the same derived targets through the ordinary bounded connect
# path. The probe cannot witness or bracket a fixture in another cgroup, so an
# attempt here is an observation only; the operator's separate outside-cgroup
# pre/post bracket remains the final acceptance evidence.
EXTERNAL_ADDRESS_CASES = {
    "tcp.sibling_alias.gateway_port": "sibling_gateway",
    "tcp.shared_loopback.gateway_port": "shared_loopback_gateway",
}
EXTERNAL_ADDRESS_LISTENERS = frozenset(EXTERNAL_ADDRESS_CASES.values())

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
        _Case('bind.own_alias.gateway_port', 'bind',
              'fixed gateway bind succeeds after Landlock', OBSERVED_ALLOWED, listener='own_gateway'),
        _Case('bind.own_alias.backend_port', 'bind',
              'fixed backend bind succeeds after Landlock', OBSERVED_ALLOWED, listener='own_backend'),
        _Case('bind.own_alias.ephemeral_port', 'bind',
              'ephemeral bind is refused after Landlock', OBSERVED_REFUSED),
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
            "own role alias on an unrelated owned listener port that Landlock "
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
        'bind.own_alias.gateway_port': (own_alias, gateway_port),
        'bind.own_alias.backend_port': (own_alias, backend_port),
        'bind.own_alias.ephemeral_port': (own_alias, 0),
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
        if outcome.observed == OBSERVED_ALLOWED:
            return STATUS_PASS if outcome.witness.get('sufficient') is True else STATUS_UNAVAILABLE
        return STATUS_FAIL
    if outcome.observed == OBSERVED_REFUSED:
        # A refusal is only denial proof when the positive witness exists.
        return STATUS_PASS if outcome.witness.get("sufficient") is True else STATUS_UNAVAILABLE
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



def _kernel_listeners(port: int) -> list[dict[str, Any]]:
    """Bounded IPv4 kernel rows, including the actual socket inode."""
    try:
        with open('/proc/net/tcp', 'rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return []
        rows = []
        for line in raw.decode('ascii').splitlines()[1:]:
            parts = line.split()
            if len(parts) < 10 or parts[3] != LISTEN_STATE:
                continue
            address, hexport = parts[1].split(':')
            host = _hex_to_ipv4(address)
            if int(hexport, 16) == port and host is not None:
                rows.append({'host': host, 'port': port, 'inode': int(parts[9])})
        return rows
    except (OSError, ValueError, UnicodeError):
        return []


def _listening_local_addresses(port: int) -> list[str]:
    return sorted(row['host'] for row in _kernel_listeners(port))


def _process_identity(pid: int) -> dict[str, int] | None:
    try:
        with open(f'/proc/{pid}/stat', 'rb') as stream:
            raw = stream.read(8193)
        if len(raw) > 8192:
            return None
        fields = raw.decode('ascii').rsplit(')', 1)[1].split()
        if fields[0] in {'Z', 'X'}:
            return None
        return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': int(fields[19])}
    except (OSError, ValueError, IndexError, UnicodeError):
        return None


def _listener_current(listener: dict[str, Any], host: str, port: int) -> dict[str, Any]:
    """Join our current child, start identity, socket FD and exact LISTEN row."""
    no = {'kind': 'owned_current_listener', 'sufficient': False}
    pid, inode, start = (listener.get(k) for k in ('pid', 'socket_inode', 'start_ticks'))
    if (listener.get('bound') is not True or any(type(x) is not int or x <= 0 for x in (pid, inode, start))
            or listener.get('bind_host') != host or listener.get('bind_port') != port):
        return {**no, 'reason': 'owned listener identity missing'}
    identity = _process_identity(pid)
    if identity != {'pid': pid, 'ppid': os.getpid(), 'start_ticks': start}:
        return {**no, 'reason': 'owned child missing or changed'}
    channel = listener.get('_witness_channel')
    socket_fd = listener.get('socket_fd')
    if (type(socket_fd) is not int or socket_fd < 0 or type(channel) is not _ListenerChannel
            or channel.parent_pid != os.getpid() or channel.child_pid != pid):
        return {**no, 'reason': 'owned socket witness channel unavailable'}
    # A parent restricted after fork cannot ptrace the older child's FD table.
    # Ask that same finite child for fresh facts over its exclusive pipe writer;
    # never retain a TCP socket in the parent or reuse startup FD facts as proof.
    witnessed = channel.observe()
    expected = {'pid': pid, 'start_ticks': start, 'socket_fd': socket_fd,
                'socket_inode': inode, 'host': host, 'port': port, 'accepting': True}
    if witnessed != expected:
        return {**no, 'reason': 'owned socket current witness unavailable'}
    matches = [row for row in _kernel_listeners(port)
               if row == {'host': host, 'port': port, 'inode': inode}]
    if len(matches) != 1 or _process_identity(pid) != identity:
        return {**no, 'reason': 'exact current kernel listener missing'}
    return {**no, 'sufficient': True, 'pid': pid, 'start_ticks': start,
            'socket_fd': socket_fd, 'socket_inode': inode, 'host': host, 'port': port}


def _same_listener(before, after) -> bool:
    fields = ('pid', 'start_ticks', 'socket_fd', 'socket_inode', 'host', 'port')
    return (before.get('sufficient') is True and after.get('sufficient') is True
            and all(type(before.get(k)) is int and before[k] > 0 for k in ('pid', 'start_ticks', 'socket_inode', 'port'))
            and type(before.get('socket_fd')) is int and before['socket_fd'] >= 0
            and isinstance(before.get('host'), str) and before['host'].startswith('127.')
            and all(before.get(k) == after.get(k) for k in fields))


def _pre_landlock_baseline(listener, host, port, timeout):
    before = _listener_current(listener, host, port)
    if before.get('sufficient') is not True:
        return {'reached': False, 'listener': before, 'target': f'{host}:{port}'}
    code, symptom = _connect(host, port, timeout)
    after = _listener_current(listener, host, port)
    return {'reached': code is None and symptom == 'connected' and _same_listener(before, after),
            'errno': code, 'errno_name': _errno_name(code), 'symptom': symptom,
            'target': f'{host}:{port}', 'listener': after,
            'scope': 'same role cgroup before Landlock; not an external IP-policy witness'}



def _matching_listen_entries(entries: list[str], bind_host: str) -> list[str]:
    """A row on a different address never witnesses this exact listener."""
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



def _read_pipe_frame(fd: int, *, timeout: float) -> dict[str, Any]:
    """One bounded newline frame; an old/extra/partial frame is never a reply."""
    deadline = time.monotonic() + timeout
    raw = bytearray()
    while len(raw) <= 2048:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise ValueError('owned witness timed out')
        part = os.read(fd, 2049 - len(raw))
        if not part:
            raise ValueError('owned witness closed')
        raw.extend(part)
        if b'\n' in raw:
            if len(raw) > 2048 or not raw.endswith(b'\n') or raw.count(b'\n') != 1:
                raise ValueError('owned witness framing differs')
            value = json.loads(raw[:-1].decode('ascii'), object_pairs_hook=_json_unique)
            if type(value) is not dict:
                raise ValueError('owned witness is not an object')
            return value
    raise ValueError('owned witness exceeds bound')


def _write_pipe_frame(fd: int, value: dict[str, Any]) -> None:
    raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
    if len(raw) > 2048 or os.write(fd, raw) != len(raw):
        raise ValueError('owned witness write incomplete')


@dataclass
class _ListenerChannel:
    """Private descriptors of one already-owned finite fixture, not a server."""
    request_fd: int
    response_fd: int
    parent_pid: int
    child_pid: int
    request_identity: tuple[int, int]
    response_identity: tuple[int, int]
    _close_complete: bool = field(default=True, init=False, repr=False)

    def _current(self, fd, identity):
        try:
            info = os.fstat(fd)
            return stat.S_ISFIFO(info.st_mode) and (info.st_dev, info.st_ino) == identity
        except OSError:
            return False

    def observe(self):
        if (self.parent_pid != os.getpid()
                or not self._current(self.request_fd, self.request_identity)
                or not self._current(self.response_fd, self.response_identity)):
            return None
        nonce = uuid.uuid4().hex
        try:
            raw = nonce.encode('ascii') + b'\n'
            if os.write(self.request_fd, raw) != len(raw):
                raise ValueError('owned witness request incomplete')
            reply = _read_pipe_frame(self.response_fd, timeout=LISTENER_TIMEOUT)
            fields = {'nonce', 'pid', 'start_ticks', 'socket_fd', 'socket_inode', 'host', 'port', 'accepting'}
            if (set(reply) != fields or reply['nonce'] != nonce
                    or any(type(reply[k]) is not int for k in ('pid', 'start_ticks', 'socket_fd', 'socket_inode', 'port'))
                    or type(reply['host']) is not str or reply['accepting'] is not True):
                raise ValueError('owned witness response differs')
            return {k: v for k, v in reply.items() if k != 'nonce'}
        except (OSError, ValueError, UnicodeError):
            self.close()
            return None

    def close(self):
        complete = self._close_complete
        for name, identity in (('request_fd', self.request_identity), ('response_fd', self.response_identity)):
            fd = getattr(self, name)
            if fd < 0:
                continue
            if self._current(fd, identity):
                try:
                    os.close(fd)
                except OSError:
                    complete = False
            else:
                # Never close a descriptor that has been replaced by another owner.
                complete = False
            setattr(self, name, -1)
        # A later idempotent close cannot erase an earlier custody/close
        # failure merely because the original descriptor fields are cleared.
        self._close_complete = complete
        return self._close_complete


def _listener_socket_facts(sock):
    fd = sock.fileno()
    identity = _process_identity(os.getpid())
    info = os.fstat(fd)
    host, port = sock.getsockname()
    if (identity is None or not stat.S_ISSOCK(info.st_mode)
            or sock.family != socket.AF_INET or sock.type != socket.SOCK_STREAM
            or sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1):
        raise ValueError('owned listening socket unavailable')
    return {'pid': os.getpid(), 'start_ticks': identity['start_ticks'],
            'socket_fd': fd, 'socket_inode': info.st_ino,
            'host': host, 'port': port, 'accepting': True}


def _listener_child(bind_host, bind_port, request_fd, response_fd, parent_pid):
    """Answer only fresh witness nonces; accept only synthetic loopback traffic."""
    sock = None
    try:
        # Later fixture children must not keep earlier children's control ends.
        # No caller-chosen descriptor or target is accepted by this finite child.
        inherited = os.listdir('/proc/self/fd')
        if len(inherited) > 1024:
            raise ValueError('owned fixture inherited descriptor bound exceeded')
        for value in inherited:
            fd = int(value)
            if fd > 2 and fd not in {request_fd, response_fd}:
                try:
                    os.close(fd)
                except OSError:
                    pass
        os.set_blocking(request_fd, False)
        os.set_blocking(response_fd, False)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(int(LISTENER_LIFETIME) + 1)
        receipt = {'bind_host': bind_host, 'bind_port': bind_port, 'pid': os.getpid()}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((bind_host, bind_port))  # no reuse: collision is unavailable
            sock.listen(16)
            sock.setblocking(False)
            facts = _listener_socket_facts(sock)
            receipt.update(bound=True, listen_port=facts['port'], socket_fd=facts['socket_fd'],
                           socket_inode=facts['socket_inode'], start_ticks=facts['start_ticks'])
        except OSError as exc:
            receipt.update(bound=False, errno=exc.errno or errno.EIO,
                           errno_name=_errno_name(exc.errno or errno.EIO))
        _write_pipe_frame(response_fd, receipt)
        deadline = time.monotonic() + LISTENER_LIFETIME
        while (receipt.get('bound') and sock is not None and time.monotonic() < deadline
                and os.getppid() == parent_pid):
            ready = select.select([request_fd, sock], [], [], min(0.25, max(0, deadline-time.monotonic())))[0]
            if request_fd in ready:
                request = os.read(request_fd, 34)
                if not re.fullmatch(rb'[0-9a-f]{32}\n', request):
                    break  # EOF, malformed, extra or partial requests stop the fixture.
                _write_pipe_frame(response_fd,
                    {'nonce': request[:-1].decode('ascii'), **_listener_socket_facts(sock)})
            if sock in ready:
                try:
                    connection, _ = sock.accept()
                except BlockingIOError:
                    continue
                try:
                    connection.settimeout(0.25)
                    connection.sendall(b'HERMES-ISO-SYNTHETIC\n')
                except OSError:
                    pass
                finally:
                    connection.close()
    except (OSError, ValueError, UnicodeError):
        pass
    finally:
        if sock is not None:
            sock.close()
        for fd in (request_fd, response_fd):
            try:
                os.close(fd)
            except OSError:
                pass
        os._exit(0)


def _spawn_listener(bind_host: str, bind_port: int) -> tuple[int, dict[str, Any]]:
    """The same finite fixture with exclusive request/reply pipes and no shared TCP FD."""
    read_fd, write_fd = os.pipe()
    try:
        request_fd, send_fd = os.pipe()
    except OSError:
        os.close(read_fd)
        os.close(write_fd)
        raise
    parent_pid = os.getpid()
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        pid = os.fork()
    except OSError:
        for fd in (read_fd, write_fd, request_fd, send_fd):
            os.close(fd)
        raise
    if pid == 0:  # pragma: no cover - bounded Linux fixture tests exercise the child
        os.close(read_fd)
        os.close(send_fd)
        _listener_child(bind_host, bind_port, request_fd, write_fd, parent_pid)
    os.close(write_fd)
    os.close(request_fd)
    req, res = os.fstat(send_fd), os.fstat(read_fd)
    channel = _ListenerChannel(send_fd, read_fd, parent_pid, pid,
                               (req.st_dev, req.st_ino), (res.st_dev, res.st_ino))
    receipt = {'bind_host': bind_host, 'bind_port': bind_port, 'pid': pid, 'bound': False,
               '_witness_channel': channel}
    try:
        os.set_blocking(send_fd, False)
        os.set_blocking(read_fd, False)
        decoded = _read_pipe_frame(read_fd, timeout=LISTENER_TIMEOUT)
        if (decoded.get('pid') != pid or decoded.get('bind_host') != bind_host
                or decoded.get('bind_port') != bind_port or '_witness_channel' in decoded):
            raise ValueError('owned fixture startup differs')
        receipt.update(decoded)
    except (OSError, ValueError, UnicodeError):
        channel.close()
    return pid, receipt



def _terminate_children(children: list[dict[str, Any]]) -> bool:
    """Signal only our unreaped children; finite TERM/KILL/reap deadlines."""
    pending = {}
    complete = True
    for child in children:
        channel = child.get('_witness_channel')
        if type(channel) is _ListenerChannel:
            complete = channel.close() and complete
        pid = child.get('pid')
        if type(pid) is not int or pid <= 0:
            complete = False
            continue
        try:
            reaped, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            continue
        if reaped == pid:
            continue
        identity = _process_identity(pid)
        if identity is None:
            try:
                reaped, _ = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                reaped = pid
            if reaped == pid:
                continue
        if (identity is None or identity['ppid'] != os.getpid()
                or (child.get('start_ticks') is not None and identity['start_ticks'] != child['start_ticks'])):
            complete = False
            continue
        pending[pid] = identity
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid, identity in list(pending.items()):
            if _process_identity(pid) != identity:
                # It may have just exited; reap below, never signal a replacement.
                continue
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 2.0
        while pending and time.monotonic() < deadline:
            for pid in list(pending):
                try:
                    reaped, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    reaped = pid
                if reaped == pid:
                    pending.pop(pid)
            if pending:
                time.sleep(0.01)
    return complete and not pending



def _exec_probe(host: str, port: int, timeout: float) -> tuple[str, int | None]:
    try:
        completed = subprocess.run(
            [sys.executable, '-I', '-S', '-c', _EXEC_PROBE, host, str(port), str(timeout)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=EXEC_TIMEOUT, close_fds=True,
            env={'PATH': os.defpath, 'LC_ALL': 'C'},
        )
    except subprocess.TimeoutExpired:
        return 'timeout', None  # process deadline, not a kernel denial
    except OSError:
        return 'error', None
    output = completed.stdout.strip()
    if completed.returncode != 0 or len(output) > 128:
        return 'error', None
    if output == 'OK':
        return 'connected', None
    if output == 'TIMEOUT':
        return 'timed_out', errno.EAGAIN
    if re.fullmatch(r'ERR:[1-9][0-9]{0,3}', output):
        return 'refused_immediately', int(output[4:])
    return 'error', None


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



def _json_unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON key')
        out[key] = value
    return out


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _load_peer_report(path: Path | None, peer_role: str, *, qualification_id=None,
                      provenance=None, expected_profile_sha256=None,
                      expected_report_sha256=None) -> tuple[dict[str, Any] | None, str]:
    """A root-copied earlier observation, never a current existence attestation."""
    if path is None:
        return None, 'no peer report supplied'
    if (not qualification_id or not provenance
            or not isinstance(expected_profile_sha256, str)
            or not re.fullmatch(r'[0-9a-f]{64}', expected_profile_sha256)
            or not isinstance(expected_report_sha256, str)
            or not re.fullmatch(r'[0-9a-f]{64}', expected_report_sha256)):
        return None, 'peer host/run/profile/report binding incomplete'
    try:
        raw, custody = _read_regular(path, MAX_REPORT_BYTES, root_owned=True)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_report_sha256:
            return None, 'peer report digest mismatch'
        report = json.loads(raw.decode('utf-8'), object_pairs_hook=_json_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(report) is not dict or report.get('schema') != SCHEMA or report.get('role') != peer_role:
            return None, 'peer schema or role mismatch'
        if report.get('context_rechecked') is not True or report.get('cleanup_complete') is not True:
            return None, 'peer context or cleanup not qualified'
        generated = datetime.datetime.strptime(report['generated_at_utc'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - generated).total_seconds()
        if not 0 <= age <= MAX_PEER_AGE:
            return None, 'peer report stale or future dated'
        context = report['context']
        peer_provenance = context['provenance']
        if (report.get('qualification_id') != qualification_id
                or peer_provenance['qualification_id'] != qualification_id
                or _canonical(peer_provenance['host']) != _canonical(provenance['host'])
                or _canonical(peer_provenance['sources']) != _canonical(provenance['sources'])
                or peer_provenance['profile_sha256'] != expected_profile_sha256):
            return None, 'peer host/boot/run/source/profile mismatch'
        if report.get('context_fingerprint') != hashlib.sha256(_canonical(
                {'context': context, 'selected': report['selected_matrix']})).hexdigest():
            return None, 'peer context fingerprint mismatch'
        if ([g.get('name') for g in report['guards']] != list(GUARD_ORDER)
                or any(g.get('status') != STATUS_PASS or g.get('code') is not None for g in report['guards'])):
            return None, 'peer production guards unqualified'
        recheck = report['observational_recheck']
        if (any(recheck.get(key) is not True
                for key in ('identity_matched', 'guards_matched', 'provenance_matched'))
                or _canonical(recheck.get('guards')) != _canonical(report['guards'][:3])
                or _canonical(recheck.get('observed_identity')) != _canonical(context['identity'])):
            return None, 'peer final identity/guards unqualified'
        account, group = pwd.getpwnam(ROLE_ACCOUNTS[peer_role]), grp.getgrnam(ROLE_ACCOUNTS[peer_role])
        identity = context['identity']
        expected = {'role': peer_role, 'nss_user': account.pw_name, 'nss_uid': account.pw_uid,
                    'nss_primary_gid': account.pw_gid, 'nss_gid': group.gr_gid, 'nss_home': account.pw_dir,
                    'process_uid': account.pw_uid, 'process_euid': account.pw_uid,
                    'process_gid': group.gr_gid, 'process_egid': group.gr_gid,
                    'uid_is_nss_uid': True, 'gid_is_nss_gid': True,
                    'no_extra_supplementary_groups': True}
        if any(_canonical(identity.get(k)) != _canonical(v) for k, v in expected.items()):
            return None, 'peer actual role identity mismatch'
        cgroup = f'/system.slice/hermes-runtime-{peer_role}.service'
        observed = identity['effective_cgroup_observed']
        if (identity.get('effective_cgroup_expected') != cgroup
                or not isinstance(observed, str)
                or not (observed == cgroup or observed.startswith(cgroup + '/'))
                or context.get('service_name') != f'hermes-runtime-{peer_role}'
                or context.get('expected_cgroup') != cgroup
                or context.get('role') != peer_role
                or any(type(g) is not int or g != group.gr_gid for g in identity['process_groups'])):
            return None, 'peer service/cgroup mismatch'
        own = report['own_file']
        facts = own['facts']
        expected_path = str(Path(context['state_dir']) / 'qualification' / 'synthetic.txt')
        if (own.get('status') != STATUS_PASS or own.get('sha256') != SYNTHETIC_MARKER_SHA256
                or own.get('path') != expected_path or not Path(expected_path).is_absolute()
                or facts.get('mode') != '0o600' or facts.get('uid') != account.pw_uid
                or facts.get('gid') != group.gr_gid or facts.get('nlink') != 1
                or facts.get('size') != len(SYNTHETIC_MARKER)
                or any(type(facts.get(k)) is not int or facts[k] < 0
                       for k in ('device', 'inode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns'))):
            return None, 'peer own synthetic fixture not qualified'
        own_rows = [row for row in report['matrix'] if row.get('case_id') == 'file.own.read']
        if (len(own_rows) != 1 or own_rows[0].get('status') != STATUS_PASS
                or own_rows[0].get('observed') != OBSERVED_ALLOWED
                or own_rows[0].get('target') != {'path': expected_path}
                or _canonical(own_rows[0]['witness'].get('facts')) != _canonical(facts)
                or own_rows[0]['witness'].get('sha256') != SYNTHETIC_MARKER_SHA256):
            return None, 'peer own-file matrix mismatch'
        report['_custody'] = {'qualified': True, 'sha256': digest, 'facts': custody}
        return report, 'root-copied peer observation qualified; current fixture bracket still required'
    except (OSError, RuntimeRefusal, ValueError, UnicodeError, KeyError, TypeError, AttributeError):
        return None, 'peer report unavailable or malformed'


def _loaded_code_fingerprint(code: CodeType) -> str:
    """Stable loaded-code structure, excluding marshal reference-count flags.

    This preserves exposed bytecode and all constructor metadata. It does not
    attest globals/defaults/closure values or mutable interpreter quickening.
    Source and interpreter custody remain separate existing qualifications.
    """
    fields = ('co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals',
              'co_stacksize', 'co_flags', 'co_code', 'co_consts', 'co_names', 'co_varnames',
              'co_freevars', 'co_cellvars', 'co_filename', 'co_name', 'co_qualname',
              'co_firstlineno', 'co_linetable', 'co_exceptiontable')
    remaining, nodes, active = 1024 * 1024, 100_000, set()
    def refuse():
        raise RuntimeRefusal('PROBE_LOADED_CODE_UNAVAILABLE')
    def canonical(value):
        return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    def encode(value, depth=0):
        nonlocal remaining, nodes
        nodes -= 1
        if nodes < 0 or depth > 64:
            refuse()
        kind = type(value)
        if value is None:
            result = ['none']
        elif value is Ellipsis:
            result = ['ellipsis']
        elif kind is bool:
            result = ['bool', value]
        elif kind is int:
            if value.bit_length() > remaining * 4:
                refuse()
            result = ['int', format(value, 'x')]
        elif kind is float:
            result = ['float', struct.pack('>d', value).hex()]
        elif kind is complex:
            result = ['complex', struct.pack('>dd', value.real, value.imag).hex()]
        elif kind in {str, bytes}:
            if len(value) > remaining:
                refuse()
            result = ['str', value] if kind is str else ['bytes', value.hex()]
        elif kind in {CodeType, tuple, frozenset}:
            if id(value) in active:
                refuse()
            active.add(id(value))
            remaining -= 16
            if remaining < 0:
                refuse()
            try:
                if kind is CodeType:
                    result = ['code', [[name, encode(getattr(value, name), depth+1)] for name in fields]]
                else:
                    items = [encode(item, depth+1) for item in value]
                    result = ['tuple', items] if kind is tuple else ['frozenset', sorted(items, key=canonical)]
            except AttributeError:
                refuse()
            finally:
                active.remove(id(value))
            return result
        else:
            refuse()
        remaining -= len(canonical(result))
        if remaining < 0:
            refuse()
        return result
    if type(code) is not CodeType:
        refuse()
    encoded = canonical(['mastermind.loaded_code/cpython-v1', encode(code)])
    if len(encoded) > 1024 * 1024:
        refuse()
    return hashlib.sha256(encoded).hexdigest()


def _capture_provenance(profile_path: Path, qualification_id: str) -> dict[str, Any]:
    # These are non-secret Linux identity and imported source/profile bytes.
    def small_text(path, limit):
        with open(path, 'rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise RuntimeRefusal('PROBE_HOST_IDENTITY_UNAVAILABLE')
        return raw.decode('ascii').strip()
    machine = small_text('/etc/machine-id', 128)
    boot = small_text('/proc/sys/kernel/random/boot_id', 128)
    if not re.fullmatch(r'[0-9a-f]{32}', machine) or not re.fullmatch(r'[0-9a-f-]{36}', boot):
        raise RuntimeRefusal('PROBE_HOST_IDENTITY_UNAVAILABLE')
    ns = os.stat('/proc/self/ns/net')
    names = {__name__, assert_root_service_cgroup.__module__, assert_role_credential_isolation.__module__,
             enforce_role_tcp_ports.__module__, load_profile.__module__}
    sources = {}
    for name in sorted(names):
        module = sys.modules.get(name)
        raw, _ = _read_regular(Path(module.__file__).resolve(strict=True), 1024 * 1024)
        sources[name] = hashlib.sha256(raw).hexdigest()
    for function in (assert_root_service_cgroup, assert_role_network_profile,
                     assert_role_credential_isolation, enforce_role_tcp_ports, load_profile, _run_probe):
        loaded = function.__code__
        sources[function.__module__ + '.' + function.__name__ + ':loaded_code'] = _loaded_code_fingerprint(loaded)
        if function.__code__ is not loaded:
            raise RuntimeRefusal('PROBE_LOADED_CODE_CHANGED')
    resolved = profile_path.resolve(strict=True)
    profile_bytes, facts = _read_regular(resolved, 65536)
    if profile_path.resolve(strict=True) != resolved:
        raise RuntimeRefusal('PROBE_PROFILE_CHANGED')
    return {'qualification_id': qualification_id,
            'host': {'machine_id': machine, 'boot_id': boot, 'netns': [ns.st_dev, ns.st_ino],
                     'kernel': os.uname().release},
            'sources': sources, 'profile_sha256': hashlib.sha256(profile_bytes).hexdigest(),
            'profile_file': facts, 'profile_resolved': str(resolved)}



def _peer_witness(report: dict[str, Any] | None, peer_file: Path) -> dict[str, Any]:
    if (report is None or report.get('_custody', {}).get('qualified') is not True
            or report.get('own_file', {}).get('path') != str(peer_file)):
        return {'kind': 'none', 'sufficient': False, 'artifact_qualified': False,
                'note': 'no bound peer observation for this synthetic fixture'}
    return {'kind': 'root_copied_peer_observation', 'sufficient': False,
            'artifact_qualified': True, 'peer_role': report['role'],
            'peer_file_path': str(peer_file), 'peer_file_sha256': report['own_file']['sha256'],
            'peer_file_facts': report['own_file']['facts'],
            'peer_report_sha256': report['_custody']['sha256'],
            'note': 'an earlier file observation cannot prove current existence behind a denied parent; '
                    'root pre/post fixture bracketing and unchanged report hashes remain required'}


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



def _stat_record(info) -> dict[str, Any]:
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid,
            'gid': info.st_gid, 'mode': oct(stat.S_IMODE(info.st_mode)),
            'nlink': info.st_nlink, 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def _directory_identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
            stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode))


def _open_parent(path: Path, *, root_owned=False):
    """Retain each directory FD; never traverse a symlink by pathname."""
    if path.anchor != '/' or '..' in path.parts or not path.name:
        raise RuntimeRefusal('PROBE_FILE_PATH_INVALID')
    held = []
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        for component in ['/', *path.parent.parts[1:]]:
            fd = os.open(component, flags, dir_fd=held[-1][0] if held else None)
            info = os.fstat(fd)
            held.append((fd, _directory_identity(info)))
            if (not stat.S_ISDIR(info.st_mode)
                    or (root_owned and (info.st_uid != 0 or info.st_mode & 0o022))):
                raise RuntimeRefusal('PROBE_FILE_PARENT_UNQUALIFIED')
        return held
    except BaseException:
        for fd, _ in reversed(held):
            os.close(fd)
        raise


def _recheck_parent(path: Path, held, *, root_owned=False):
    current = _open_parent(path, root_owned=root_owned)
    try:
        expected = [identity for _, identity in held]
        if ([identity for _, identity in current] != expected
                or [_directory_identity(os.fstat(fd)) for fd, _ in held] != expected):
            raise RuntimeRefusal('PROBE_FILE_PARENT_CHANGED')
    finally:
        for fd, _ in reversed(current):
            os.close(fd)


def _read_regular(path: Path, limit: int, *, root_owned=False,
                  uid=None, gid=None, mode=None) -> tuple[bytes, dict[str, Any]]:
    """Read one bounded regular FD, with no symlink/type/replacement fallback."""
    held = _open_parent(path, root_owned=root_owned)
    fd = None
    try:
        dirfd = held[-1][0]
        before = os.stat(path.name, dir_fd=dirfd, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit
                or (root_owned and (before.st_uid != 0 or before.st_mode & 0o022))
                or (uid is not None and before.st_uid != uid)
                or (gid is not None and before.st_gid != gid)
                or (mode is not None and stat.S_IMODE(before.st_mode) != mode)):
            raise RuntimeRefusal('PROBE_FILE_CUSTODY_UNQUALIFIED')
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=dirfd)
        if _stat_record(os.fstat(fd)) != _stat_record(before):
            raise RuntimeRefusal('PROBE_FILE_CHANGED')
        chunks, size = [], 0
        while size <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if (size > limit or _stat_record(os.fstat(fd)) != _stat_record(before)
                or _stat_record(os.stat(path.name, dir_fd=dirfd, follow_symlinks=False)) != _stat_record(before)):
            raise RuntimeRefusal('PROBE_FILE_CHANGED_OR_OVERSIZED')
        _recheck_parent(path, held, root_owned=root_owned)
        return b''.join(chunks), _stat_record(before)
    finally:
        if fd is not None:
            os.close(fd)
        for parent_fd, _ in reversed(held):
            os.close(parent_fd)


def _file_outcome_own(path: Path, state_dir: Path, uid: int, gid: int) -> _Outcome:
    target = {'path': str(path)}
    witness = {'kind': 'bounded_synthetic_fd', 'sufficient': False}
    # Never accept an arbitrary path to a real credential as a fixture.
    if path != state_dir / 'qualification' / 'synthetic.txt':
        return _Outcome(OBSERVED_ERROR, detail='exact synthetic fixture path required',
                        target=target, witness=witness)
    try:
        content, facts = _read_regular(path, len(SYNTHETIC_MARKER), uid=uid, gid=gid, mode=0o600)
    except RuntimeRefusal as exc:
        return _Outcome(OBSERVED_ERROR, detail=exc.code, target=target, witness=witness)
    except OSError as exc:
        code = exc.errno or errno.EIO
        observed = OBSERVED_UNAVAILABLE if code == errno.ENOENT else OBSERVED_REFUSED
        return _Outcome(observed, errno=code, errno_name=_errno_name(code),
                        detail='own synthetic fixture unavailable', target=target, witness=witness)
    digest = hashlib.sha256(content).hexdigest()
    witness.update(path=str(path), facts=facts, sha256=digest,
                   sufficient=content == SYNTHETIC_MARKER)
    return _Outcome(OBSERVED_ALLOWED if witness['sufficient'] else OBSERVED_ERROR,
                    detail='bounded synthetic marker observation', target=target, witness=witness)



def _file_outcome_peer(path: Path, witness: dict[str, Any]) -> _Outcome:
    target = {'path': str(path)}
    stat_outcome, read_outcome = _try_stat(path), _try_read(path)
    # A successful read is a breach even if an earlier stat was denied.
    if read_outcome['readable']:
        return _Outcome(OBSERVED_ALLOWED, detail='sibling synthetic file was readable',
                        target=target, witness=witness)
    code = read_outcome.get('errno')
    if code in {errno.EACCES, errno.EPERM}:
        prior = stat_outcome.get('errno')
        if prior not in {None, errno.EACCES, errno.EPERM}:
            return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                            detail='contradictory fixture observations', target=target,
                            witness={**witness, 'sufficient': False})
        return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                        symptom='refused_immediately', target=target, witness=witness,
                        detail='read denied; current external fixture bracketing remains required')
    if code == errno.ENOENT or stat_outcome.get('errno') in {errno.EACCES, errno.EPERM}:
        return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                        detail='missing or inconsistent sibling fixture', target=target,
                        witness={**witness, 'sufficient': False})
    return _Outcome(OBSERVED_ERROR, errno=code, errno_name=_errno_name(code),
                    detail='unrelated file error is not denial proof', target=target,
                    witness={**witness, 'sufficient': False})



def _try_stat(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
    except OSError as exc:
        return {'ok': False, 'errno': exc.errno or errno.EIO}
    return {'ok': True, 'errno': None, **_stat_record(info)}



def _try_read(path: Path) -> dict[str, Any]:
    if path.name != 'synthetic.txt' or path.parent.name != 'qualification':
        return {'readable': False, 'errno': None, 'reason': 'synthetic path required'}
    try:
        content, facts = _read_regular(path, len(SYNTHETIC_MARKER))
    except RuntimeRefusal:
        return {'readable': False, 'errno': None, 'reason': 'fixture custody invalid'}
    except OSError as exc:
        return {'readable': False, 'errno': exc.errno or errno.EIO}
    return {'readable': True, 'errno': None,
            'sha256': hashlib.sha256(content).hexdigest(), 'facts': facts}


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
    parser.add_argument('--qualification-id', help='one shared unique identifier for the A/B/A qualification')
    parser.add_argument('--peer-profile-sha256', help='root operator expected digest of the peer profile')
    parser.add_argument('--peer-report-sha256', help='root operator digest of the unchanged copied peer report')
    parser.add_argument("--denied-port", type=int,
                        help="a free unprivileged port outside the role's allowed set")
    parser.add_argument("--report", type=Path, help="write the JSON report here as well")
    parser.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT,
                        help="bounded connect timeout in seconds")
    parser.add_argument("--only", default="",
                        help="comma-separated subset of case ids to select")
    parser.add_argument("--external-address-fixtures", action="store_true",
                        help=("the operator supplies the outside-role-cgroup fixture for the two "
                              "address-denial cases: the internal listeners for exactly those two "
                              "cases are omitted, the same fixed targets are still attempted, and "
                              "no denial is attributed without the separate outside-cgroup bracket"))
    parser.add_argument("--list-cases", action="store_true",
                        help="print the matrix identifiers and exit")
    args = parser.parse_args(argv)
    if args.list_cases:
        return args
    missing = [name for name in ("profile", "role", "own_file", "peer_file", 'qualification_id')
               if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(sorted(missing)))
    if not math.isfinite(args.connect_timeout) or args.connect_timeout <= 0 or args.connect_timeout > 30:
        parser.error("--connect-timeout must be in (0, 30]")
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.qualification_id):
        parser.error('--qualification-id must be a bounded plain identifier')
    for value in (args.peer_profile_sha256, args.peer_report_sha256):
        if value is not None and not re.fullmatch(r'[0-9a-f]{64}', value):
            parser.error('peer digests must be full lowercase SHA-256 values')
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
    raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    if len(raw) > MAX_REPORT_BYTES:
        raise RuntimeRefusal('PROBE_REPORT_TOO_LARGE')
    if path is not None:
        held = _open_parent(path)
        dirfd = held[-1][0]
        temp = '.isolation-' + uuid.uuid4().hex + '.tmp'
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=dirfd)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Atomic no-replace publication. Existing files/symlinks all refuse.
            _recheck_parent(path, held)
            os.link(temp, path.name, src_dir_fd=dirfd, dst_dir_fd=dirfd, follow_symlinks=False)
            os.unlink(temp, dir_fd=dirfd)
            os.fsync(dirfd)
            _recheck_parent(path, held)
            observed, _ = _read_regular(path, MAX_REPORT_BYTES, uid=os.geteuid(), mode=0o600)
            if observed != raw:
                raise RuntimeRefusal('PROBE_REPORT_POSTIMAGE_CHANGED')
        finally:
            try:
                os.unlink(temp, dir_fd=dirfd)
            except FileNotFoundError:
                pass
            for parent_fd, _ in reversed(held):
                os.close(parent_fd)
    sys.stdout.write(raw.decode('utf-8'))



def _ephemeral_bind(host: str) -> tuple[int | None, int | None]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return None, sock.getsockname()[1]
    except OSError as exc:
        return exc.errno or errno.EIO, None


def _bind_outcome(case, listeners, baseline):
    if case.expected == OBSERVED_ALLOWED:
        listener = listeners.get(case.listener or '', {})
        witness = _listener_current(listener, case.host, case.port)
        witness['sufficient'] = witness.get('sufficient') is True and listener.get('created_after_landlock') is True
        if witness['sufficient']:
            return _Outcome(OBSERVED_ALLOWED, witness=witness, detail='owned fixed listener bound after Landlock')
        code = listener.get('errno')
        observed = OBSERVED_REFUSED if code in LANDLOCK_DENIAL_ERRNOS else OBSERVED_UNAVAILABLE
        return _Outcome(observed, errno=code, errno_name=_errno_name(code), witness=witness,
                        detail='fixed bind refused or fixture unavailable; collision is not policy proof')
    code, port = _ephemeral_bind(case.host)
    witness = {'kind': 'pre_landlock_ephemeral_bind', 'sufficient': baseline.get('bound') is True,
               'baseline': baseline}
    if code is None:
        return _Outcome(OBSERVED_ALLOWED, witness=witness, detail='forbidden ephemeral bind succeeded',
                        target={'host': case.host, 'requested_port': 0, 'assigned_port': port})
    if code not in LANDLOCK_DENIAL_ERRNOS:
        return _Outcome(OBSERVED_ERROR, errno=code, errno_name=_errno_name(code),
                        witness={**witness, 'sufficient': False}, detail='unrelated bind error')
    return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                    symptom='refused_immediately', witness=witness,
                    attribution='LANDLOCK_TCP_PORT' if witness['sufficient'] else 'UNDETERMINED',
                    detail='ephemeral bind denied after production restriction')


def _run_probe(args: argparse.Namespace) -> int:
    try:
        selected = _selected_cases(args.only)
        provenance = _capture_provenance(args.profile, args.qualification_id)
        profile = load_profile(args.profile)
        if _canonical(_capture_provenance(args.profile, args.qualification_id)) != _canonical(provenance):
            raise RuntimeRefusal('PROBE_PROFILE_OR_SOURCE_CHANGED')
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return CONFIG_EXIT
    if profile.role != args.role:
        raise RuntimeRefusal('PROBE_ROLE_PROFILE_MISMATCH')
    role = profile.role
    peer_role = 'mmmeta' if role == 'mmsecretary' else 'mmsecretary'
    own_alias, peer_alias = ROLE_PROXY_HOST[role], ROLE_PROXY_HOST[peer_role]
    if args.own_file != profile.state_dir / 'qualification' / 'synthetic.txt':
        raise RuntimeRefusal('PROBE_SYNTHETIC_PATH_REQUIRED')
    if args.report is not None and (args.report.parent != profile.state_dir / 'qualification'
            or not re.fullmatch(r'report-[A-Za-z0-9_-]{1,128}\.json', args.report.name)
            or args.qualification_id not in args.report.name):
        raise RuntimeRefusal('PROBE_UNIQUE_REPORT_PATH_REQUIRED')
    bind_ports, connect_ports = role_tcp_ports(profile)
    denied_port = args.denied_port or DEFAULT_DENIED_PORT[role]
    if (not 1024 <= denied_port <= 65535 or denied_port in bind_ports | connect_ports
            or denied_port in ROLE_FIXED_PORTS[peer_role].values()):
        raise RuntimeRefusal('PROBE_DENIED_PORT_INVALID_OR_ALLOWED')
    # A closed boolean: it names no host, port, path, command or authority.
    external_address_fixtures = getattr(args, 'external_address_fixtures', False) is True
    identity = _identity_facts(role)
    guards, guards_ok = _run_guards(profile, role)
    guards = [dict(entry) for entry in guards]
    initial_observations = [dict(entry) for entry in guards]
    args._provenance = provenance
    args._context_stable = False
    args._profile_semantic = _profile_values(asdict(profile))
    catalog = _bind_cases(role, profile.gateway_port, profile.backend_port, denied_port)
    records, listeners, pre_landlock, children = {}, {}, {}, []
    exec_baseline = ('not_run', None)
    exec_pre_listener = {}
    ephemeral_baseline = {'bound': False}
    cleanup_complete = True

    def emit(case, outcome):
        records[case.case_id] = _case_record(case, outcome, selected=case.case_id in selected)

    def not_run(case, reason):
        emit(case, _Outcome(OBSERVED_NOT_RUN, detail=reason, witness={'sufficient': False}))

    def listener(key, host, port, *, after=False):
        pid, receipt = _spawn_listener(host, port)
        receipt['pid'] = pid
        receipt['created_after_landlock'] = after
        children.append(receipt)
        listeners[key] = receipt

    network_selected = any(c.case_id in selected and c.dimension in {'bind', 'tcp', 'exec'} for c in catalog)
    try:
        if guards_ok:
            if network_selected:
                # Same-role-cgroup pre-Landlock fixtures are not external IP positives.
                for key, host, port in (
                    ('wildcard_denied', own_alias, denied_port),
                    ('sibling_gateway', peer_alias, profile.gateway_port),
                    ('shared_loopback_gateway', '127.0.0.1', profile.gateway_port),
                ):
                    if external_address_fixtures and key in EXTERNAL_ADDRESS_LISTENERS:
                        # The operator's own outside-role-cgroup fixture owns this
                        # exact target. An internal listener here would collide with
                        # it and would still not be an outside-cgroup positive.
                        continue
                    listener(key, host, port)
                    pre_landlock[key] = _pre_landlock_baseline(listeners[key], host, port, args.connect_timeout)
                exec_pre_listener = _listener_current(listeners['wildcard_denied'], own_alias, denied_port)
                exec_baseline = _exec_probe(own_alias, denied_port, args.connect_timeout)
                after_exec = _listener_current(listeners['wildcard_denied'], own_alias, denied_port)
                if not _same_listener(exec_pre_listener, after_exec):
                    exec_baseline = ('unavailable', None)
                code, port = _ephemeral_bind(own_alias)
                ephemeral_baseline = {'bound': code is None, 'host': own_alias,
                                      'requested_port': 0, 'assigned_port': port, 'errno': code}
            try:
                enforce_role_tcp_ports(profile)
                guards.append({'name': 'enforce_role_tcp_ports', 'status': STATUS_PASS, 'code': None})
            except RuntimeRefusal as exc:
                guards.append({'name': 'enforce_role_tcp_ports', 'status': 'REFUSED', 'code': exc.code})
                guards_ok = False
            if guards_ok and network_selected:
                # These child binds actually inherit the newly applied Landlock restriction.
                listener('own_gateway', own_alias, profile.gateway_port, after=True)
                listener('own_backend', own_alias, profile.backend_port, after=True)
        for case in catalog:
            if not guards_ok or case.case_id not in selected:
                not_run(case, 'guard refused' if not guards_ok else 'not selected')
            elif case.dimension == 'profile':
                emit(case, _profile_ports_outcome(profile, role))
            elif case.dimension == 'bind':
                emit(case, _bind_outcome(case, listeners, ephemeral_baseline))
            elif case.dimension == 'tcp':
                emit(case, _tcp_outcome(case, listeners, pre_landlock, connect_ports, args.connect_timeout,
                                        external_address_fixtures=external_address_fixtures))
            elif case.dimension == 'exec':
                key = 'wildcard_denied' if case.expected == OBSERVED_REFUSED else 'own_gateway'
                emit(case, _exec_outcome(case, exec_baseline, args.connect_timeout,
                                         listeners.get(key), exec_pre_listener))
            elif case.dimension == 'file':
                emit(case, _file_outcome(case, profile, identity['nss_uid'], identity['nss_gid'],
                                         args.own_file, args.peer_file, args.peer_report,
                                         qualification_id=args.qualification_id, provenance=provenance,
                                         peer_profile_sha256=args.peer_profile_sha256,
                                         peer_report_sha256=args.peer_report_sha256))
    finally:
        cleanup_complete = _terminate_children(children)
    args._observational_recheck = {'identity_matched': False, 'guards_matched': False,
                                  'provenance_matched': False}
    try:
        final_identity = _identity_facts(role)
        final_guards, final_guards_ok = _run_guards(profile, role)
        args._observational_recheck = {
            'observed_identity': final_identity, 'guards': final_guards,
            'identity_matched': _canonical(final_identity) == _canonical(identity),
            'guards_matched': final_guards_ok is True and _canonical(final_guards) == _canonical(initial_observations),
            'provenance_matched': _canonical(_capture_provenance(args.profile, args.qualification_id)) == _canonical(provenance),
        }
        args._context_stable = all(args._observational_recheck[key] is True
                                  for key in ('identity_matched', 'guards_matched', 'provenance_matched'))
    except (OSError, RuntimeRefusal, ValueError, UnicodeError):
        args._context_stable = False
    report = _build_report(profile, role, peer_role, identity, guards, records, selected,
                           bind_ports, connect_ports, denied_port, args,
                           witnesses={'pre_landlock': pre_landlock, 'exec_pre_landlock': exec_baseline,
                                      'ephemeral_pre_landlock': ephemeral_baseline,
                                      'cleanup_complete': cleanup_complete}, listeners=listeners)
    _write_report(report, args.report)
    return _exit_code(report)


def _profile_values(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(_profile_values(v) for v in value)
    if isinstance(value, dict):
        return {k: _profile_values(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_profile_values(v) for v in value]
    return value



def _tcp_external_address_outcome(case: _Case, landlock_connect: frozenset[int],
                                  timeout: float) -> _Outcome:
    """One bounded attempt against an operator-supplied outside-cgroup fixture.

    The required fixture is outside the role cgroup, but this context does
    not observe its existence or ownership and cannot bracket it before and
    after the attempt. The attempt is therefore an observation only: it never
    supplies the external positive, a refusal here stays unattributed, and the
    case stays UNAVAILABLE. The operator's separate outside-cgroup pre/post
    connection bracket is the final acceptance evidence.
    """
    host = case.host or ''
    port = case.port or 0
    target = {'host': host, 'port': port}
    witness = {
        'kind': 'external_address_fixture',
        'sufficient': False,
        'external_positive_required': True,
        'external_bracket_required': True,
        'fixture_owner_expected': 'outside_role_cgroup',
        'note': ('an external fixture is expected but not observed by this process; this probe can '
                 'neither witness nor bracket it; the outside-cgroup pre/post connection bracket '
                 'remains separate acceptance evidence'),
    }
    code, symptom = _connect(host, port, timeout)
    if code is None and symptom == 'connected':
        # A forbidden target that answers is a real failure, not an unavailable one.
        return _Outcome(OBSERVED_ALLOWED, symptom=symptom, target=target, witness=witness,
                        attribution='NONE',
                        basis='the forbidden external-address target completed the connection',
                        detail='forbidden external-address target accepted the connection')
    if code == errno.ECONNREFUSED:
        return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                        symptom=symptom, target=target, witness=witness,
                        attribution='UNDETERMINED',
                        basis='nothing answered at this target; a refused connection is not policy proof',
                        detail='no external fixture answered; a refused connection is not policy proof')
    denial_shaped = ((symptom == 'timed_out' and code in {errno.EAGAIN, errno.ETIMEDOUT})
                     or (symptom == 'refused_immediately' and code == errno.EPERM))
    if not denial_shaped:
        return _Outcome(OBSERVED_ERROR, errno=code, errno_name=_errno_name(code),
                        symptom=symptom, target=target, witness=witness,
                        attribution='UNDETERMINED',
                        basis='an unrelated errno or symptom is not IP-policy denial proof',
                        detail='unrelated error remains an error, not unavailable denial evidence')
    if port in landlock_connect:
        attribution = 'UNVERIFIED_CGROUP_IP_POLICY'
        basis = ("the target port is inside the role's Landlock connect set, so Landlock permits "
                 'it; the refusal shape is consistent with the cgroup address policy, but no '
                 'outside-cgroup witness was observed here')
    else:
        attribution = 'UNDETERMINED'
        basis = ("the target port is outside the role's Landlock connect set, so Landlock refuses "
                 'it independently of the address policy; no outside-cgroup witness was observed here')
    return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code), symptom=symptom,
                    target=target, witness=witness, attribution=attribution, basis=basis,
                    detail='external current positive witness required')


def _tcp_outcome(case: _Case, listeners: dict[str, dict[str, Any]],
                 unconfined: dict[str, dict[str, Any]],
                 landlock_connect: frozenset[int], timeout: float,
                 *, external_address_fixtures: bool = False) -> _Outcome:
    if external_address_fixtures and case.case_id in EXTERNAL_ADDRESS_CASES:
        return _tcp_external_address_outcome(case, landlock_connect, timeout)
    listener = listeners.get(case.listener or '', {})
    before = _listener_current(listener, case.host or '', case.port or 0)
    if before.get('sufficient') is not True:
        return _Outcome(OBSERVED_UNAVAILABLE, detail='current owned listener unavailable', witness=before)
    code, symptom = _connect(case.host or '', case.port or 0, timeout)
    after = _listener_current(listener, case.host or '', case.port or 0)
    baseline = unconfined.get(case.listener or '', {})
    same_baseline = (baseline.get('reached') is True
                     and baseline.get('target') == f'{case.host}:{case.port}'
                     and _same_listener(baseline.get('listener', {}), before))
    witness = {'kind': 'bracketed_owned_listener', 'sufficient': _same_listener(before, after),
               'before': before, 'after': after, 'pre_landlock_reached': same_baseline}
    if code is None and symptom == 'connected':
        if case.expected == OBSERVED_ALLOWED and not witness['sufficient']:
            return _Outcome(OBSERVED_UNAVAILABLE, symptom=symptom, witness=witness,
                            detail='allowed connection outlived its owned listener witness')
        return _Outcome(OBSERVED_ALLOWED, symptom=symptom, witness=witness,
                        attribution='NONE', detail='TCP connection completed')
    if case.expected == OBSERVED_ALLOWED:
        return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                        symptom=symptom, witness=witness, attribution='UNDETERMINED',
                        detail='own allowed target was not reachable')
    if code == errno.ECONNREFUSED:
        return _Outcome(OBSERVED_UNAVAILABLE, errno=code, errno_name=_errno_name(code),
                        symptom=symptom, witness={**witness, 'sufficient': False},
                        detail='connection refusal is not policy proof')
    if case.port in landlock_connect:
        # These fixture children inherit this role's IP cgroup. Their prior
        # connects cannot prove an outside-cgroup positive. External root
        # before/after evidence is a separate final acceptance requirement.
        candidate = ((symptom == 'timed_out' and code in {errno.EAGAIN, errno.ETIMEDOUT})
                     or (symptom == 'refused_immediately' and code == errno.EPERM))
        return _Outcome(OBSERVED_REFUSED if candidate else OBSERVED_ERROR,
                        errno=code, errno_name=_errno_name(code), symptom=symptom,
                        attribution='UNVERIFIED_CGROUP_IP_POLICY' if candidate else 'UNDETERMINED',
                        detail='external current positive witness required',
                        witness={**witness, 'sufficient': False, 'external_positive_required': True})
    expected_denial = symptom == 'refused_immediately' and code in LANDLOCK_DENIAL_ERRNOS
    if not expected_denial:
        return _Outcome(OBSERVED_ERROR, errno=code, errno_name=_errno_name(code),
                        symptom=symptom, witness={**witness, 'sufficient': False},
                        detail='unrelated error or timeout is not Landlock proof')
    witness['sufficient'] = witness['sufficient'] and same_baseline
    return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                    symptom=symptom, witness=witness,
                    attribution='LANDLOCK_TCP_PORT' if witness['sufficient'] else 'UNDETERMINED',
                    detail='immediate denial; same-target positive and current listener required')



def _file_outcome(case: _Case, profile: RuntimeProfile, uid: int, gid: int,
                  own_file: Path, peer_file: Path, peer_report_path: Path | None,
                  *, qualification_id=None, provenance=None, peer_profile_sha256=None,
                  peer_report_sha256=None) -> _Outcome:
    if case.case_id == 'file.own.read':
        return _file_outcome_own(own_file, profile.state_dir, uid, gid)
    peer_role = 'mmmeta' if profile.role == 'mmsecretary' else 'mmsecretary'
    report, reason = _load_peer_report(peer_report_path, peer_role,
                                      qualification_id=qualification_id, provenance=provenance,
                                      expected_profile_sha256=peer_profile_sha256,
                                      expected_report_sha256=peer_report_sha256)
    witness = _peer_witness(report, peer_file)
    witness['source'] = reason
    if not witness['artifact_qualified']:
        return _Outcome(OBSERVED_UNAVAILABLE, detail='qualified synthetic peer path required before read',
                        target={'path': str(peer_file)}, witness=witness)
    return _file_outcome_peer(peer_file, witness)



def _exec_outcome(case: _Case, exec_unconfined: tuple[str, int | None],
                  timeout: float, listener: dict[str, Any] | None = None,
                  pre_listener: dict[str, Any] | None = None) -> _Outcome:
    before = _listener_current(listener or {}, case.host or '', case.port or 0)
    if before.get('sufficient') is not True:
        return _Outcome(OBSERVED_UNAVAILABLE, detail='current exec target witness unavailable', witness=before)
    symptom, code = _exec_probe(case.host or '', case.port or 0, timeout)
    after = _listener_current(listener or {}, case.host or '', case.port or 0)
    witness = {'kind': 'bracketed_exec_target', 'sufficient': _same_listener(before, after),
               'before': before, 'after': after, 'pre_landlock_exec': list(exec_unconfined)}
    if symptom == 'connected' and code is None:
        observed = (OBSERVED_UNAVAILABLE if case.expected == OBSERVED_ALLOWED and not witness['sufficient']
                    else OBSERVED_ALLOWED)
        return _Outcome(observed, symptom=symptom, witness=witness, detail='exec descendant connected')
    if symptom in {'error', 'timeout'} or code not in LANDLOCK_DENIAL_ERRNOS or symptom != 'refused_immediately':
        observed = OBSERVED_UNAVAILABLE if code == errno.ECONNREFUSED else OBSERVED_ERROR
        return _Outcome(observed, errno=code, errno_name=_errno_name(code), symptom=symptom,
                        detail='child/protocol/deadline/unrelated failure is not policy denial',
                        witness={**witness, 'sufficient': False})
    if case.expected == OBSERVED_ALLOWED:
        return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code),
                        symptom=symptom, witness=witness, detail='exec descendant lost an allowed port')
    witness['sufficient'] = (witness['sufficient'] and exec_unconfined == ('connected', None)
                             and _same_listener(pre_listener or {}, before))
    return _Outcome(OBSERVED_REFUSED, errno=code, errno_name=_errno_name(code), symptom=symptom,
                    attribution='LANDLOCK_TCP_PORT' if witness['sufficient'] else 'UNDETERMINED',
                    witness=witness, detail='immediate inherited denial with the same current target')


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

    provenance = getattr(args, '_provenance', {})
    external_address_fixtures = getattr(args, 'external_address_fixtures', False) is True
    guard_proven = ([entry.get('name') for entry in guards] == list(GUARD_ORDER)
                    and all(entry.get('status') == STATUS_PASS and entry.get('code') is None for entry in guards))
    complete_matrix = (selected == {case.case_id for case in _case_catalog()}
                       and set(records) == {case.case_id for case in _case_catalog()})
    stable = getattr(args, '_context_stable', False) is True
    cleanup_complete = witnesses.get('cleanup_complete') is True
    if status == 'PASS' and not (guard_proven and complete_matrix and stable and cleanup_complete and provenance):
        status = 'INCOMPLETE'

    context = {
        'provenance': provenance,
        'profile_semantic': getattr(args, '_profile_semantic', {}),
        "role": role,
        "peer_role": peer_role,
        "service_name": profile.service_name,
        "expected_cgroup": f"/system.slice/{profile.service_name}.service",
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
        "external_address_fixtures": external_address_fixtures,
    }
    fingerprint = hashlib.sha256(
        json.dumps({"context": context, "selected": sorted(selected)},
                   sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    limitations = [
        'Same-cgroup listener fixtures cannot qualify cgroup IP denial; current external positive bracketing is required.',
        'A copied peer report is an earlier observation. Root pre/post fixture identities and unchanged report hashes are separate acceptance evidence.',
        "The proxy port is deliberately out of scope: a synthetic listener "
        "would not be the incumbent hermes-egress.service and cannot stand "
        "in for final proxy proof.",
        "The matrix records observations of the selected cgroup and Landlock "
        "controls; external address-denial proof remains separate. It is not proof of effective BPF "
        "enforcement on every kernel, of UDP or Unix-domain isolation, or "
        "of vendor CONNECT ACLs.",
        "An absent witness yields UNAVAILABLE and never PASS; a missing "
        "listener, a refused connection or a skipped case is not denial proof.",
        "A PASS is bound to context_fingerprint. A different host identity, "
        "role, cgroup, profile or selected matrix is a different result.",
    ]
    if external_address_fixtures:
        limitations.append(
            "External-address fixture mode was selected. Any selected address case "
            "requires an outside-role-cgroup fixture that this probe cannot witness or bracket; "
            "the separate outside-cgroup pre/post connection bracket remains required and "
            "this report qualifies neither case."
        )

    return {
        "schema": SCHEMA,
        'qualification_id': getattr(args, 'qualification_id', None),
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
        'context_rechecked': stable,
        'observational_recheck': getattr(args, '_observational_recheck', {}),
        'cleanup_complete': cleanup_complete,
        'full_matrix_selected': complete_matrix,
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
        "listeners": {name: {key: value for key, value in receipt.items() if not key.startswith('_')}
                      for name, receipt in listeners.items()},
        "witnesses": witnesses,
        "matrix": matrix,
        "counts": counts,
        "own_file": {
            "path": str(args.own_file),
            'sha256': ((records.get('file.own.read') or {}).get('witness') or {}).get('sha256'),
            'facts': ((records.get('file.own.read') or {}).get('witness') or {}).get('facts'),
            "status": (records.get("file.own.read") or {}).get("status"),
        },
        "scope": {
            "prepared_fixture": True,
            "final_production_configuration": False,
            "statement": (
                "This report records partial evidence for the isolation controls of one observed "
                "final role service context using synthetic, credential-free "
                "fixtures. It does not qualify the production endpoints, the "
                "incumbent hermes-egress.service proxy, any credential, any "
                "provider, TLS, billing, Slack or a cutover."
            ),
        },
        "limitations": limitations,
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
