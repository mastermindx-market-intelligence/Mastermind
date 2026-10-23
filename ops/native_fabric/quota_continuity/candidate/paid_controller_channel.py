"""Private original-controller framing. Transport alone grants no authority.

Only a controller-side owner retaining the authenticated Control command may
answer this channel. A nonce, descriptor, PID or successful exchange is never a
Runtime grant or proof of provider execution. This module opens no listener,
reads no credential/lease, starts no process and implements no retry.
"""
from __future__ import annotations

import json
import fcntl
import stat
import threading
import os
import re
import socket
import struct
import sys

REQUEST_SCHEMA = 'mastermind.paid_controller_lease_request/v1'
RESPONSE_SCHEMA = 'mastermind.paid_controller_lease_response/v1'
MAX_REQUEST = 1024
MAX_RESPONSE = 32768
_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_NONCE = re.compile(r'[0-9a-f]{64}\Z')


class ChannelRefused(ValueError):
    """Closed diagnostic only; never exposes input or capability material."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ChannelRefused('private_channel_json_refused')
        result[key] = value
    return result


def _constant(_):
    raise ChannelRefused('private_channel_json_refused')


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('ascii')
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ChannelRefused('private_channel_json_refused') from None


def _exact(sock, size):
    chunks = []
    while size:
        chunk = sock.recv(size)
        if not chunk:
            raise ChannelRefused('private_channel_incomplete')
        chunks.append(chunk)
        size -= len(chunk)
    return b''.join(chunks)


def _socket(sock):
    if (type(sock) is not socket.socket or sock.family != socket.AF_UNIX
            or sock.type & 0xf != socket.SOCK_STREAM):
        raise ChannelRefused('private_channel_socket_refused')


def receive(sock, *, limit):
    _socket(sock)
    size = struct.unpack('!I', _exact(sock, 4))[0]
    if not 1 <= size <= limit:
        raise ChannelRefused('private_channel_frame_refused')
    try:
        value = json.loads(_exact(sock, size).decode('utf-8'),
                           object_pairs_hook=_pairs, parse_constant=_constant)
        canonical(value)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ChannelRefused('private_channel_json_refused') from None
    if type(value) is not dict:
        raise ChannelRefused('private_channel_json_refused')
    return value


def send(sock, value, *, limit):
    _socket(sock)
    raw = canonical(value)
    if not 1 <= len(raw) <= limit:
        raise ChannelRefused('private_channel_frame_refused')
    sock.sendall(struct.pack('!I', len(raw)) + raw)


def _identity(run_id, lease_id, nonce):
    if (any(type(v) is not str or not _IDENTIFIER.fullmatch(v)
            for v in (run_id, lease_id))
            or type(nonce) is not str or not _NONCE.fullmatch(nonce)):
        raise ChannelRefused('private_channel_binding_refused')


def request_lease(sock, *, run_id, lease_id, nonce):
    """One exchange, closed before returning; caller never retains this FD."""
    try:
        _identity(run_id, lease_id, nonce)
        send(sock, dict(schema=REQUEST_SCHEMA, run_id=run_id,
                        lease_id=lease_id, nonce=nonce), limit=MAX_REQUEST)
        value = receive(sock, limit=MAX_RESPONSE)
        if (set(value) != {'schema', 'run_id', 'lease_id', 'nonce', 'capsule'}
                or value['schema'] != RESPONSE_SCHEMA
                or any(value[k] != v for k, v in
                       (('run_id', run_id), ('lease_id', lease_id), ('nonce', nonce)))
                or type(value['capsule']) is not dict):
            raise ChannelRefused('private_channel_response_refused')
        # Scope/signature are validated by the actual capability consumer. A
        # JSON dictionary on a private transport is never a minting authority.
        return value['capsule']
    finally:
        sock.close()


def receive_lease(sock, *, run_id, nonce):
    """Parse correlation only. The actual owner must independently qualify it."""
    value = receive(sock, limit=MAX_REQUEST)
    if set(value) != {'schema', 'run_id', 'lease_id', 'nonce'}:
        raise ChannelRefused('private_channel_request_refused')
    _identity(value['run_id'], value['lease_id'], value['nonce'])
    if (value['schema'] != REQUEST_SCHEMA or value['run_id'] != run_id
            or value['nonce'] != nonce):
        raise ChannelRefused('private_channel_request_refused')
    return value['lease_id']


def answer_lease(sock, *, run_id, lease_id, nonce, capsule):
    _identity(run_id, lease_id, nonce)
    if type(capsule) is not dict:
        raise ChannelRefused('private_channel_response_refused')
    send(sock, dict(schema=RESPONSE_SCHEMA, run_id=run_id, lease_id=lease_id,
                    nonce=nonce, capsule=capsule), limit=MAX_RESPONSE)


class ProviderIntent:
    """One actual original owner's sink, never an admission or public issuer.

    The paid backend constructs exactly one instance from its pinned original
    controller log after authenticating and reserving that operation. This IO
    primitive cannot qualify that caller. It never reconstructs an owner from
    a path or grants replay after a partial/unknown write.
    """
    def __init__(self, log_fd, *, payload_sha256):
        if (type(log_fd) is not int or log_fd < 0 or type(payload_sha256) is not str
                or not _NONCE.fullmatch(payload_sha256)):
            raise ChannelRefused('provider_intent_sink_refused')
        self._fd = os.dup(log_fd)
        os.set_inheritable(self._fd, False)
        try:
            self._identity = self._stat()
        except BaseException:
            os.close(self._fd)
            self._fd = None
            raise
        self._payload = payload_sha256
        self._lock = threading.Lock()
        self._attempted = False

    def _stat(self):
        info = os.fstat(self._fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ChannelRefused('provider_intent_sink_refused')
        return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_nlink)

    def consume(self):
        with self._lock:
            if self._attempted:
                raise ChannelRefused('provider_intent_already_attempted')
            # This remains true even if flock/read/write/fsync fails. No second
            # HTTP request can reinterpret an unknown sink outcome as absence.
            self._attempted = True
            locked = False
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                if self._stat() != self._identity:
                    raise ChannelRefused('provider_intent_sink_changed')
                info = os.fstat(self._fd)
                if not 1 <= info.st_size <= 1024 * 1024:
                    raise ChannelRefused('provider_intent_sink_refused')
                raw = os.pread(self._fd, info.st_size + 1, 0)
                prefix = ('CANONICAL_PAID_REQUIRED schema=1 payload_sha256='
                          + self._payload + '\n').encode('ascii')
                if (len(raw) != info.st_size or not raw.startswith(prefix)
                        or b'CANONICAL_PAID_PROVIDER_INTENT' in raw):
                    raise ChannelRefused('provider_intent_original_record_refused')
                marker = ('CANONICAL_PAID_PROVIDER_INTENT schema=1 payload_sha256='
                          + self._payload + '\n').encode('ascii')
                os.lseek(self._fd, 0, os.SEEK_END)
                if os.write(self._fd, marker) != len(marker):
                    raise ChannelRefused('provider_intent_write_unknown')
                os.fsync(self._fd)
                if self._stat() != self._identity:
                    raise ChannelRefused('provider_intent_sink_changed')
            except (OSError, ValueError):
                raise ChannelRefused('provider_intent_unknown') from None
            finally:
                if locked:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)

    def close(self):
        with self._lock:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    sock = None
    try:
        if (len(args) != 4 or not args[0].isdigit()
                or not 3 <= int(args[0]) <= 1024):
            raise ChannelRefused('private_channel_arguments_refused')
        fd = int(args[0])
        os.set_inheritable(fd, False)
        sock = socket.socket(fileno=fd)
        _socket(sock)
        sock.settimeout(30)
        result = request_lease(sock, run_id=args[1], lease_id=args[2], nonce=args[3])
        sys.stdout.buffer.write(canonical(result))
        return 0
    except (ChannelRefused, OSError, ValueError, UnicodeError):
        print('CANONICAL_PAID_PRIVATE_CHANNEL_REFUSED before_provider=1', file=sys.stderr)
        return 78
    finally:
        if sock is not None:
            sock.close()


if __name__ == '__main__':
    raise SystemExit(main())
