"""Attempt-owned loopback endpoint for an existing coding harness.

Not a daemon, credential store, account allocator, retry ledger or Worker adapter.
The existing broker supplies the session/account/model, private client capability,
credential loader, request admission and terminal-failure callback. It owns launch,
outer cancellation, durable events and cleanup. This endpoint cannot mint grants.

After any admitted inference fails, this instance permanently stops forwarding.
That local fail-stop latch prevents a client's outer retry loop from duplicating
provider effects while the existing broker terminates/reconciles its Worker.
"""
from __future__ import annotations

import hmac
import json
import socket
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

from control_plane.opencode_go_pooled_transport import (
    AccountChoice, ProviderRequest, OpenCodeGoEffectUnknown,
    OpenCodeGoTransportContractError, _choice, _freeze_request,
)
from control_plane.opencode_go_stream import StreamReceipt, stream_single_account

_MAX_BODY = 1024 * 1024
_PATHS = {'openai-chat': 'chat/completions', 'anthropic': 'messages', 'responses': 'responses'}


class EndpointCloseUncertain(RuntimeError):
    pass


@dataclass(frozen=True)
class HarnessBinding:
    session_id: str
    model_id: str
    protocol: str
    account: AccountChoice
    # Supplied from the existing worker-private boundary, not generated here.
    client_capability: str = field(repr=False)


class _Server(HTTPServer):
    """At most one request thread; never accumulate a retry queue."""
    allow_reuse_address = False
    def __init__(self, owner):
        self.owner = owner
        self.slot = threading.Lock()
        self.active = None
        self.active_socket = None
        super().__init__(('127.0.0.1', 0), _Handler)

    def process_request(self, request, client_address):
        # A bounded handoff lets the previous completed response close its socket.
        # It does not retain a request queue or admit concurrent inference.
        if not self.slot.acquire(timeout=0.1):
            self.shutdown_request(request)
            return
        def run():
            try:
                self.finish_request(request, client_address)
            except Exception:
                pass  # Request diagnostics are deliberately not printed.
            finally:
                self.shutdown_request(request)
                self.active_socket = None
                self.slot.release()
        request.settimeout(3.0)
        self.active_socket = request
        self.active = threading.Thread(target=run, name='go-request', daemon=True)
        self.active.start()

    def handle_error(self, request, client_address):
        # Never print request bodies, keys, headers or underlying callback errors.
        pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'Mastermind'
    sys_version = ''

    def log_message(self, *args):
        pass

    def _reply(self, status, code):
        payload = json.dumps({'error': {'type': code, 'message': 'Worker action required.'}}).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_GET(self):
        self._reply(405, 'MMX_METHOD_REFUSED')

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_GET

    def do_POST(self):
        owner = self.server.owner
        self.close_connection = True
        try:
            auth = self.headers.get_all('Authorization', [])
            api_keys = self.headers.get_all('x-api-key', [])
            if owner.binding.protocol == 'anthropic' and len(api_keys) == 1 and not auth:
                supplied = ('Bearer ' + api_keys[0]).encode('utf-8')
            else:
                supplied = auth[0].encode('utf-8') if len(auth) == 1 and not api_keys else b''
            if not hmac.compare_digest(supplied, owner._authorization):
                self._reply(401, 'MMX_CLIENT_REFUSED')
                return
            if owner._poisoned.is_set() or owner._cancel.is_set():
                self._reply(409, 'MMX_WORKER_STOPPED')
                return
            lengths = self.headers.get_all('Content-Length', [])
            if (self.path != '/v1/' + owner._path or self.headers.get('Origin') is not None
                    or self.headers.get('Transfer-Encoding') is not None
                    or len(lengths) != 1 or not lengths[0].isdigit()
                    or not 0 < int(lengths[0]) <= _MAX_BODY
                    or self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json'):
                self._reply(400, 'MMX_REQUEST_REFUSED')
                return
            body = self.rfile.read(int(lengths[0]))
            if len(body) != int(lengths[0]):
                self._reply(400, 'MMX_REQUEST_REFUSED')
                return
            headers = {name: self.headers[name] for name in ('anthropic-version', 'anthropic-beta') if name in self.headers}
            headers['Content-Type'] = 'application/json'
            request = _freeze_request(ProviderRequest(owner._path, owner.binding.session_id, headers, body), replayable=False)
            payload = json.loads(request.body)
            if payload.get('model') != owner.binding.model_id or payload.get('stream') is not True or payload.get('background') is True:
                self._reply(400, 'MMX_BINDING_REFUSED')
                return
        except Exception:
            self._reply(400, 'MMX_REQUEST_REFUSED')
            return

        started = False
        def consume(chunk):
            nonlocal started
            if not isinstance(chunk, bytes) or not chunk:
                raise ValueError('invalid stream chunk')
            if not started:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Transfer-Encoding', 'chunked')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                started = True
            self.wfile.write(('%x\r\n' % len(chunk)).encode() + chunk + b'\r\n')
            self.wfile.flush()

        try:
            result = owner._stream(
                request, choice=owner.binding.account, credential_loader=owner._credential,
                request_check=owner._admit, on_chunk=consume, cancel=owner._cancel,
            )
            if (not isinstance(result, StreamReceipt)
                    or result.account_id != owner.binding.account.account_id
                    or result.pool_generation != owner.binding.account.pool_generation):
                raise OpenCodeGoEffectUnknown(owner.binding.account.account_id, (owner.binding.account.account_id,))
            if result.http_status != 200 or not result.terminal_observed:
                owner._fail('upstream_refused_or_incomplete')
                if not started:
                    self._reply(409, 'MMX_PROVIDER_STOPPED')
                return
            if not started:
                raise OpenCodeGoEffectUnknown(owner.binding.account.account_id, (owner.binding.account.account_id,))
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()
        except OpenCodeGoTransportContractError:
            owner._fail('request_admission_refused')
            if not started:
                self._reply(409, 'MMX_ADMISSION_STOPPED')
        except Exception:
            owner._fail('effect_unknown')
            if not started:
                self._reply(409, 'MMX_EFFECT_UNRESOLVED')
        finally:
            self.close_connection = True


class GoHarnessEndpoint:
    """Context-managed endpoint scoped to ONE existing Worker Attempt/session.

    No automatic restart, model/account changes, credential creation or retry.
    Host binding is always numeric IPv4 loopback and OS-chosen ephemeral port.
    The broker must protect the supplied capability, consume failure events, and
    stop its harness; a callback is not itself evidence of durable consumption.
    Failure callbacks notify the supervisor; they must not synchronously close
    this endpoint from inside its own request thread.
    Constructor dependencies are trusted composition inputs, not web parameters.
    """
    def __init__(self, binding: HarnessBinding, *, credential_loader: Callable,
                 request_check: Callable, on_terminal_failure: Callable,
                 cancel: threading.Event, stream: Callable = stream_single_account):
        if not isinstance(binding, HarnessBinding) or binding.protocol not in _PATHS:
            raise OpenCodeGoTransportContractError('unsupported harness binding')
        if (not isinstance(binding.client_capability, str) or not 32 <= len(binding.client_capability) <= 256
                or not binding.client_capability.isascii() or not binding.client_capability.isalnum()):
            raise OpenCodeGoTransportContractError('private client capability required')
        if not isinstance(cancel, threading.Event) or not all(callable(v) for v in (credential_loader, request_check, on_terminal_failure, stream)):
            raise OpenCodeGoTransportContractError('invalid endpoint dependencies')
        if _choice(binding.account, pool_id=binding.account.pool_id) != binding.account:
            raise OpenCodeGoTransportContractError("account identity must be canonical")
        # Reuse canonical request identity validation without reading a credential.
        _freeze_request(ProviderRequest(_PATHS[binding.protocol], binding.session_id, {},
            json.dumps({'model':binding.model_id,'stream':True}).encode()), replayable=False)
        self.binding = binding
        self._path = _PATHS[binding.protocol]
        self._authorization = ('Bearer ' + binding.client_capability).encode()
        self._credential, self._admit = credential_loader, request_check
        self._failure, self._stream, self._cancel = on_terminal_failure, stream, cancel
        self._poisoned = threading.Event()
        self._notification_failed = threading.Event()
        self._server = self._thread = None
        self._ever_started = False

    def _fail(self, kind):
        if self._poisoned.is_set():
            return
        self._poisoned.set()  # Stop further forwarding BEFORE calling another owner.
        try:
            self._failure(kind)
        except Exception:
            # Failure to record an event is not permission to send more requests.
            self._notification_failed.set()

    @property
    def base_url(self):
        if self._server is None:
            raise OpenCodeGoTransportContractError('endpoint not running')
        return 'http://127.0.0.1:%d/v1' % self._server.server_port

    @property
    def stopped_forwarding(self):
        return self._poisoned.is_set()

    @property
    def failure_notification_failed(self):
        return self._notification_failed.is_set()

    def __enter__(self):
        if self._ever_started:
            raise OpenCodeGoTransportContractError('endpoint cannot restart')
        self._ever_started = True
        self._server = _Server(self)
        self._thread = threading.Thread(target=self._server.serve_forever,
            kwargs={'poll_interval':0.05}, name='go-endpoint', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *error):
        self.close()

    def close(self):
        server = self._server
        if server is None:
            return
        if threading.current_thread() in (self._thread, server.active):
            self._poisoned.set()
            self._cancel.set()
            raise EndpointCloseUncertain('endpoint cleanup requires its existing outer supervisor')
        self._poisoned.set()
        self._cancel.set()
        server.shutdown()
        client = server.active_socket
        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        server.server_close()
        self._thread.join(timeout=1)
        worker = server.active
        if worker is not None:
            worker.join(timeout=1)
        if self._thread.is_alive() or (worker is not None and worker.is_alive()):
            raise EndpointCloseUncertain('existing worker supervisor must reconcile endpoint cleanup')
        self._server = self._thread = None
