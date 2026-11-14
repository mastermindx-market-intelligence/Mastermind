"""BR2 fold-ins LOW1 and LOW2: the admitted-set intersection covers EVERY
dispatch family, and one connection presents exactly one capability digest.

LOW1: census and surface-action (wsp) requests were forwarded without the
capability intersection the browser family already had. Both admitted
releases speak census and the same surface actions, so the gate refuses
when either end's digest is absent or unknown — fail closed, never forward.

LOW2: the two handshake hellos were admitted independently; a peer could
present one admitted digest in hello1 and another in hello2. The connection
must present exactly one digest across both hellos.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import os
import secrets
import socket
import threading
import time

import pytest

from integrations.chairman_surfaces import web_sol_browser_protocol as browser
from integrations.chairman_surfaces import web_sol_census_protocol as census
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp
from test_web_sol_transport_compat import (
    ExtensionStandIn, HostHarness, INSTANCE, PREVIOUS_DIGEST, UNKNOWN_DIGEST,
    socket_dir,
)
from test_web_sol_protocol import valid_observation, valid_request

CURRENT_DIGEST = wsp.transport_capability_digest()
BOOT = "boot-nonce-for-gate-tests-0001"


def _zulu(moment):
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def census_request():
    now = datetime.now(timezone.utc)
    return {
        "schema": census.REQUEST_SCHEMA,
        "adapter_instance_id": INSTANCE,
        "operation_key": "census-gate-operation",
        "nonce": secrets.token_hex(24),
        "issued_at": _zulu(now),
        "expires_at": _zulu(now + timedelta(seconds=8)),
    }


def surface_request(action="INSPECT"):
    now = datetime.now(timezone.utc)
    return valid_request(
        action=action,
        issued_at=_zulu(now),
        expires_at=_zulu(now + timedelta(seconds=30)),
        nonce="nonce-" + secrets.token_hex(11),
    )


def census_reply(document):
    return {"schema": census.RECEIPT_SCHEMA,
            **{k: document[k] for k in census.IDENTITY_FIELDS},
            "status": "COLLECTOR_UNAVAILABLE", "snapshot": None}


def surface_reply(document):
    return {"schema": wsp.RECEIPT_SCHEMA,
            **{k: document[k] for k in ("binding_id", "conversation_fingerprint",
                "binding_fingerprint", "action", "operation_key", "nonce")},
            "status": "INSPECTED",
            "observed_at": _zulu(datetime.now(timezone.utc)),
            "observation": valid_observation()}


class GateStandIn(ExtensionStandIn):
    """Extension stand-in that answers each schema with its own receipt."""

    def run(self):
        try:
            first_challenge = secrets.token_urlsafe(24)
            native.write_frame(self._to_host, self._hello(None, first_challenge))
            first = self._ack(native.read_frame(self._from_host), challenge=first_challenge)
            self.boot_nonce = first["boot_nonce"]
            second_challenge = secrets.token_urlsafe(24)
            native.write_frame(self._to_host, self._hello(self.boot_nonce, second_challenge))
            self._ack(native.read_frame(self._from_host), challenge=second_challenge)
            self.ready.set()
            while True:
                document = native.read_frame(self._from_host)
                self.forwarded.append(document)
                if document.get("schema") == census.REQUEST_SCHEMA:
                    reply = census_reply(document)
                elif document.get("schema") == browser.REQUEST_SCHEMA:
                    reply = browser.receipt(document, status="OK", effect="APPLIED",
                                            data={"stand_in": True})
                else:
                    reply = surface_reply(document)
                native.write_frame(self._to_host, reply)
        except Exception:
            return


def gate_harness(tmp_path, monkeypatch, *, extension_digest):
    import test_web_sol_transport_compat as compat
    monkeypatch.setattr(compat, "ExtensionStandIn", GateStandIn)
    return HostHarness(tmp_path, extension_digest=extension_digest)


def _connect():
    # The harness waits for the socket file, which bind creates before
    # listen; retry the narrow race window instead of flaking.
    destination = str(native.wsi.socket_path(INSTANCE))
    for attempt in range(100):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(5.0)
        try:
            connection.connect(destination)
            return connection
        except ConnectionRefusedError:
            connection.close()
            if attempt == 99:
                raise
            time.sleep(0.01)


def _hello(digest, boot, challenge):
    return wsp.build_transport_hello(
        role="client", adapter_instance_id=INSTANCE,
        client_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        native_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        extension_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        capability_digest=digest, boot_nonce=boot, challenge_nonce=challenge)


def _client_handshake(reader, writer, first_digest, second_digest):
    native.write_frame(writer, _hello(first_digest, None, secrets.token_urlsafe(24)))
    first = wsp.validate_transport_hello_ack(native.read_frame(reader))
    native.write_frame(writer, _hello(second_digest, first["boot_nonce"],
                                      secrets.token_urlsafe(24)))
    second = wsp.validate_transport_hello_ack(native.read_frame(reader))
    return second["boot_nonce"]


# --- LOW2: one connection, one digest -------------------------------------

def test_hello_digest_swap_is_refused(socket_dir):
    harness = HostHarness(socket_dir, extension_digest=CURRENT_DIGEST)
    harness.start()
    try:
        connection = _connect()
        with connection:
            reader = connection.makefile("rb", buffering=0)
            writer = connection.makefile("wb", buffering=0)
            native.write_frame(writer, _hello(CURRENT_DIGEST, None, secrets.token_urlsafe(24)))
            first = wsp.validate_transport_hello_ack(native.read_frame(reader))
            native.write_frame(writer, _hello(PREVIOUS_DIGEST, first["boot_nonce"],
                                              secrets.token_urlsafe(24)))
            # Both digests are individually admitted; the swap itself must
            # close the connection instead of completing the handshake.
            with pytest.raises(native.NativeHostError):
                native.read_frame(reader)
        assert harness.extension.forwarded == []
    finally:
        harness.stop()


def test_same_previous_digest_twice_still_completes(socket_dir):
    harness = HostHarness(socket_dir, extension_digest=CURRENT_DIGEST)
    harness.start()
    try:
        connection = _connect()
        with connection:
            reader = connection.makefile("rb", buffering=0)
            writer = connection.makefile("wb", buffering=0)
            boot = _client_handshake(reader, writer, PREVIOUS_DIGEST, PREVIOUS_DIGEST)
            assert boot
        assert harness.extension.forwarded == []
    finally:
        harness.stop()


# --- LOW1: census and surface actions join the intersection ---------------

def test_surface_and_census_helpers_admit_exactly_the_two_releases():
    surface = {a.value for a in wsp.SurfaceAction}
    assert wsp.transport_capability_surface_actions(CURRENT_DIGEST) == surface
    assert wsp.transport_capability_surface_actions(PREVIOUS_DIGEST) == surface
    assert wsp.transport_capability_admits_census(CURRENT_DIGEST) is True
    assert wsp.transport_capability_admits_census(PREVIOUS_DIGEST) is True
    for foreign in (UNKNOWN_DIGEST, "", None):
        assert wsp.transport_capability_surface_actions(foreign) is None
        assert wsp.transport_capability_admits_census(foreign) is False


def serve_once(request_doc, *, extension_digest, extension_actions, reply=None):
    """Drive one real _serve_client over a socketpair; return (forwarded_bytes,
    client_reply_or_None). The chrome reply, when given, is pre-loaded."""
    peer, server = socket.socketpair()
    peer.settimeout(5.0)
    # The reply side must be a real fd: the host selects on it. The forward
    # side only needs write_frame, which tolerates a plain buffer.
    reply_write = None
    if reply is not None:
        read_fd, write_fd = os.pipe()
        chrome_in = os.fdopen(read_fd, "rb", buffering=0)
        reply_write = os.fdopen(write_fd, "wb", buffering=0)
        native.write_frame(reply_write, reply)
    else:
        chrome_in = io.BytesIO()
    chrome_out = io.BytesIO()
    errors = []

    def run():
        try:
            native._serve_client(
                server, chrome_in, chrome_out,
                timeout_seconds=5.0, expected_instance_id=INSTANCE,
                boot_nonce=BOOT, extension_actions=extension_actions,
                extension_digest=extension_digest)
        except BaseException as exc:
            errors.append(exc)
        finally:
            try:
                server.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    received = None
    try:
        reader = peer.makefile("rb", buffering=0)
        writer = peer.makefile("wb", buffering=0)
        _client_handshake(reader, writer, CURRENT_DIGEST, CURRENT_DIGEST)
        native.write_frame(writer, request_doc)
        received = native.read_frame(reader)
    except (native.NativeHostError, OSError):
        received = None
    finally:
        peer.close()
        thread.join(timeout=5.0)
        chrome_in.close()
        if reply_write is not None:
            reply_write.close()
    assert not any(isinstance(exc, TypeError) for exc in errors), errors
    return chrome_out.getvalue(), received


def test_census_flows_between_two_current_ends():
    request = census_request()
    forwarded, received = serve_once(request, extension_digest=CURRENT_DIGEST,
        extension_actions=browser.ACTIONS, reply=census_reply(request))
    assert forwarded, "the census request reached Chrome"
    assert received is not None and received["status"] == "COLLECTOR_UNAVAILABLE"


def test_census_flows_across_the_release_boundary():
    request = census_request()
    forwarded, received = serve_once(request, extension_digest=PREVIOUS_DIGEST,
        extension_actions=browser.PREVIOUS_ACTIONS, reply=census_reply(request))
    assert forwarded and received is not None


def test_census_without_an_extension_digest_is_refused():
    forwarded, received = serve_once(census_request(), extension_digest=None,
        extension_actions=browser.ACTIONS)
    assert forwarded == b"", "nothing may reach Chrome without the extension's digest"
    assert received is None


def test_census_with_an_unknown_extension_digest_is_refused():
    forwarded, received = serve_once(census_request(), extension_digest=UNKNOWN_DIGEST,
        extension_actions=browser.ACTIONS)
    assert forwarded == b"" and received is None


def test_surface_inspect_flows_between_two_current_ends():
    request = surface_request()
    forwarded, received = serve_once(request, extension_digest=CURRENT_DIGEST,
        extension_actions=browser.ACTIONS, reply=surface_reply(request))
    assert forwarded and received is not None and received["status"] == "INSPECTED"


def test_surface_inspect_with_an_unknown_extension_digest_is_refused():
    forwarded, received = serve_once(surface_request(), extension_digest=UNKNOWN_DIGEST,
        extension_actions=browser.ACTIONS)
    assert forwarded == b"" and received is None


def test_surface_inspect_without_an_extension_digest_is_refused():
    forwarded, received = serve_once(surface_request(), extension_digest=None,
        extension_actions=browser.ACTIONS)
    assert forwarded == b"" and received is None


# --- end to end: census and INSPECT across a real host --------------------

def _one_exchange(harness, request_doc, validate):
    connection = _connect()
    with connection:
        reader = connection.makefile("rb", buffering=0)
        writer = connection.makefile("wb", buffering=0)
        _client_handshake(reader, writer, CURRENT_DIGEST, CURRENT_DIGEST)
        native.write_frame(writer, request_doc)
        return validate(native.read_frame(reader))


def test_census_flows_end_to_end(socket_dir, monkeypatch):
    harness = gate_harness(socket_dir, monkeypatch, extension_digest=CURRENT_DIGEST)
    harness.start()
    try:
        received = _one_exchange(harness, census_request(), census.validate_census_receipt)
        assert received["status"] == "COLLECTOR_UNAVAILABLE"
        assert harness.extension.forwarded[0]["schema"] == census.REQUEST_SCHEMA
    finally:
        harness.stop()


def test_surface_inspect_flows_end_to_end(socket_dir, monkeypatch):
    harness = gate_harness(socket_dir, monkeypatch, extension_digest=CURRENT_DIGEST)
    harness.start()
    try:
        received = _one_exchange(harness, surface_request(), wsp.validate_receipt)
        assert received["status"] == "INSPECTED"
        assert harness.extension.forwarded[0]["action"] == "INSPECT"
    finally:
        harness.stop()


def test_old_extension_still_serves_census_to_a_new_client(socket_dir, monkeypatch):
    harness = gate_harness(socket_dir, monkeypatch, extension_digest=PREVIOUS_DIGEST)
    harness.start()
    try:
        connection = _connect()
        with connection:
            reader = connection.makefile("rb", buffering=0)
            writer = connection.makefile("wb", buffering=0)
            _client_handshake(reader, writer, CURRENT_DIGEST, CURRENT_DIGEST)
            native.write_frame(writer, census_request())
            received = census.validate_census_receipt(native.read_frame(reader))
            assert received["status"] == "COLLECTOR_UNAVAILABLE"
        assert harness.extension.forwarded[0]["schema"] == census.REQUEST_SCHEMA
    finally:
        harness.stop()
