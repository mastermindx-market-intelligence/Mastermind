"""BR-COMPAT: previous-release admission and per-connection action sets.

Ruling 16: a method that makes running sessions fail is not installed while
other programmes have operators at work. The native host therefore admits
exactly one previous bridge release's transport capability digest alongside
its own, and holds every admitted connection to the action set that digest
describes. Whatever ordering of client upgrade, extension reload and host
respawn the fleet goes through, an old peer keeps its old actions and the new
actions ``read`` and ``menu`` exist only where both ends of the connection
describe them. The accepted previous release is 5aa30969 (0.4.0) — the
release running at BOTH ends when BR2 switches (RULING BR2-R2 class rule);
b640dec1 was only staged and is a skipped release, admitted nowhere.

The previous-release client module is byte-identical to the current one
(verified against release roots), so a client whose protocol module reports
the previous digest is a faithful stand-in for the unmodified old client:
its hello carries that digest and its ack check demands the echo of exactly
that digest.
"""
from __future__ import annotations

import inspect
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from integrations.chairman_surfaces import web_sol_browser_protocol as browser
from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_instance as wsi
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "a" * 64
# The 40 browser actions of release 5aa30969241163b4abb3e025bc9e52123ee4b478
# (0.4.0): the current set minus ``read`` and ``menu`` and nothing else.
PREVIOUS_ACTION_NAMES = frozenset({
    "accessibility", "back", "capture", "cdp", "cdp_attach", "cdp_detach",
    "cdp_status", "click", "close", "diagnostics", "dialog", "dom", "download",
    "downloads", "emulate", "evaluate", "events", "fill", "focus", "forward",
    "frames", "interact", "locate", "navigate", "network", "open", "pdf",
    "press", "reload", "response_body", "result", "route", "screenshot",
    "scroll", "select", "snapshot", "status", "tabs", "upload", "wait",
})
PREVIOUS_DIGEST = (
    "e0216d3d9e9f05edef32ff642cb82a1281b1a9766d5cc35f694c88e0ef0bb0bb"
)
PREVIOUS_COMMIT = "5aa30969241163b4abb3e025bc9e52123ee4b478"
# b640dec1 was staged but never went live as a pin or a loaded extension;
# its digest is a skipped release and is admitted nowhere (RULING BR2-R2).
SKIPPED_DIGEST = (
    "1c40ec98d1086a8f8005151757b040698057019f5e9169cace91e393b6f60d40"
)
UNKNOWN_DIGEST = "ab" * 32


class PreviousReleaseWsp:
    """Delegate everything to the live protocol module except the digest.

    Converts the current client into a stand-in for the previous release's
    unmodified client: the hello it builds carries the previous digest and the
    ack it accepts must echo that digest.
    """

    def __init__(self, digest: str):
        self._digest = digest

    def __getattr__(self, name):
        return getattr(wsp, name)

    def transport_capability_digest(self):
        return self._digest


class ExtensionStandIn(threading.Thread):
    """Extension end of the stdio framing protocol over real pipe fds.

    Performs the extension-role handshake with the digest it was given —
    including the unmodified extension's own ack check that the host must
    echo the presented digest — then answers every forwarded document with a
    receipt and records what it was asked to execute.
    """

    def __init__(self, to_host, from_host, instance_id: str, digest: str):
        super().__init__(daemon=True, name="extension-stand-in")
        self._to_host = to_host
        self._from_host = from_host
        self._instance_id = instance_id
        self._digest = digest
        self.boot_nonce = None
        self.forwarded = []
        self.ready = threading.Event()

    def _hello(self, boot, challenge):
        return wsp.build_transport_hello(
            role="extension",
            adapter_instance_id=self._instance_id,
            client_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
            native_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
            extension_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
            capability_digest=self._digest,
            boot_nonce=boot,
            challenge_nonce=challenge,
        )

    def _ack(self, value, *, challenge):
        accepted = wsp.validate_transport_hello_ack(value)
        assert accepted["role"] == "extension"
        assert accepted["capability_digest"] == self._digest, (
            "the host ack must echo the digest the peer presented"
        )
        assert accepted["challenge_nonce"] == challenge
        return accepted

    def run(self):
        try:
            first_challenge = secrets.token_urlsafe(24)
            native.write_frame(self._to_host, self._hello(None, first_challenge))
            first = self._ack(
                native.read_frame(self._from_host), challenge=first_challenge
            )
            self.boot_nonce = first["boot_nonce"]
            second_challenge = secrets.token_urlsafe(24)
            native.write_frame(
                self._to_host, self._hello(self.boot_nonce, second_challenge)
            )
            self._ack(
                native.read_frame(self._from_host), challenge=second_challenge
            )
            self.ready.set()
            while True:
                document = native.read_frame(self._from_host)
                self.forwarded.append(document)
                native.write_frame(
                    self._to_host,
                    browser.receipt(
                        document,
                        status="OK",
                        effect="APPLIED",
                        data={"stand_in": True},
                    ),
                )
        except Exception:
            # Chrome channel teardown at test end is the normal exit.
            return


class HostHarness:
    """One real ``run_native_host`` over pipes with a select-able chrome fd."""

    def __init__(self, tmp_path: Path, *, extension_digest: str):
        host_read, extension_write = os.pipe()
        extension_read, host_write = os.pipe()
        self.extension = ExtensionStandIn(
            os.fdopen(extension_write, "wb", buffering=0),
            os.fdopen(extension_read, "rb", buffering=0),
            INSTANCE,
            extension_digest,
        )
        self._chrome_in = os.fdopen(host_read, "rb", buffering=0)
        self._chrome_out = os.fdopen(host_write, "wb", buffering=0)
        self.host_error = None
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="native-host")

    def _run(self):
        try:
            native.run_native_host(
                self._chrome_in,
                self._chrome_out,
                caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
                expected_instance_id=INSTANCE,
                socket_root=str(SOCKET_DIR),
                owner_uid=os.getuid(),
                action_timeout_seconds=5.0,
            )
        except BaseException as exc:  # recorded, asserted by stop()
            self.host_error = exc

    def start(self):
        self.extension.start()
        self._thread.start()
        assert self.extension.ready.wait(5.0), "extension handshake never completed"
        # The handshake completing and the server socket binding are two
        # separate moments; clients may only connect once the socket exists.
        destination = wsi.socket_path(INSTANCE)
        for _ in range(500):
            if destination.exists():
                return
            assert not self.host_error, self.host_error
            time.sleep(0.01)
        raise AssertionError(f"server socket never bound: {destination}")

    def stop(self):
        for stream in (self._chrome_in, self._chrome_out):
            try:
                stream.close()
            except OSError:
                pass
        self._thread.join(timeout=5.0)
        assert not self._thread.is_alive(), "native host did not stop"


SOCKET_DIR = None


@pytest.fixture
def socket_dir(monkeypatch):
    # The host binds under an explicit root; the client derives the same path
    # from the module default, so both ends meet in one scratch directory.
    # It must stay short: Darwin caps AF_UNIX paths at 104 bytes and the
    # pytest tmp tree is far deeper than that.
    global SOCKET_DIR
    SOCKET_DIR = Path(f"/tmp/brcompat-wsx-{os.getpid()}-{secrets.token_hex(4)}")
    SOCKET_DIR.mkdir(mode=0o700)
    monkeypatch.setattr(wsi, "DEFAULT_SOCKET_ROOT", str(SOCKET_DIR))
    yield SOCKET_DIR
    for stale in SOCKET_DIR.glob("*.sock"):
        try:
            stale.unlink()
        except OSError:
            pass
    try:
        SOCKET_DIR.rmdir()
    except OSError:
        pass
    SOCKET_DIR = None


def _browser_request(action: str, *, boot: str, **changes):
    from test_web_sol_browser import request as base_request

    value = base_request(action, transport_boot_nonce=boot, **changes)
    return browser.validate_window(value)


def _raw_connect(digest: str):
    """Hand-build the client handshake with an arbitrary digest.

    This is the 'whatever the client sends' probe: it lets a connection
    admitted on one digest carry a request for an action outside that
    digest's set, exactly as a modified or foreign client could.
    """
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(5.0)
    connection.connect(str(wsi.socket_path(INSTANCE)))
    reader = connection.makefile("rb", buffering=0)
    writer = connection.makefile("wb", buffering=0)

    def hello(boot, challenge):
        return wsp.build_transport_hello(
            role="client",
            adapter_instance_id=INSTANCE,
            client_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
            native_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
            extension_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
            capability_digest=digest,
            boot_nonce=boot,
            challenge_nonce=challenge,
        )

    native.write_frame(writer, hello(None, secrets.token_urlsafe(24)))
    first = wsp.validate_transport_hello_ack(native.read_frame(reader))
    assert first["capability_digest"] == digest, "ack must echo presented digest"
    native.write_frame(writer, hello(first["boot_nonce"], secrets.token_urlsafe(24)))
    second = wsp.validate_transport_hello_ack(native.read_frame(reader))
    assert second["capability_digest"] == digest
    return connection, reader, writer, second["boot_nonce"]


def test_previous_release_constants_name_exactly_one_admitted_digest():
    assert wsp.PREVIOUS_TRANSPORT_CAPABILITY_DIGEST == PREVIOUS_DIGEST
    assert wsp.PREVIOUS_TRANSPORT_CAPABILITY_RELEASE_COMMIT == PREVIOUS_COMMIT
    assert PREVIOUS_DIGEST != wsp.transport_capability_digest()
    assert len(PREVIOUS_DIGEST) == 64
    assert all(c in "0123456789abcdef" for c in PREVIOUS_DIGEST)


def test_previous_action_set_is_the_old_forty_without_read_and_menu():
    assert browser.PREVIOUS_ACTIONS == PREVIOUS_ACTION_NAMES
    assert browser.PREVIOUS_ACTIONS == browser.ACTIONS - {"read", "menu"}
    assert len(browser.PREVIOUS_ACTIONS) == 40
    assert "menu" not in browser.PREVIOUS_ACTIONS
    assert "read" not in browser.PREVIOUS_ACTIONS
    assert "status" in browser.PREVIOUS_ACTIONS


def test_action_set_lookup_admits_current_and_previous_only():
    current = wsp.transport_capability_digest()
    assert wsp.transport_capability_action_set(current) == browser.ACTIONS
    admitted = wsp.transport_capability_action_set(PREVIOUS_DIGEST)
    assert admitted == browser.PREVIOUS_ACTIONS
    for foreign in (UNKNOWN_DIGEST, SKIPPED_DIGEST, "", None, PREVIOUS_DIGEST.upper()):
        assert wsp.transport_capability_action_set(foreign) is None


def test_old_client_connects_and_read_and_menu_are_refused_without_forwarding(socket_dir):
    harness = HostHarness(socket_dir, extension_digest=wsp.transport_capability_digest())
    harness.start()
    try:
        connection, reader, writer, boot = _raw_connect(PREVIOUS_DIGEST)
        with connection:
            native.write_frame(
                writer, _browser_request(
                    "menu", boot=boot, params={"path": ["Thinking", "Extra High"]}
                )
            )
            refused = browser.validate_receipt(native.read_frame(reader))
            assert refused["action"] == "menu"
            assert refused["effect"] == "NOT_APPLIED"
            assert refused["status"] == "ACTION_UNAVAILABLE"
            assert refused["data"]["reason"] == "transport_capability_mismatch"
        assert [doc.get("action") for doc in harness.extension.forwarded] == []
        # Each request is its own connection; the refusal closed that one,
        # not the session. A fresh old-digest connection asks for `read`.
        connection, reader, writer, boot = _raw_connect(PREVIOUS_DIGEST)
        with connection:
            native.write_frame(
                writer, _browser_request("read", boot=boot, params={"offset": 0})
            )
            refused = browser.validate_receipt(native.read_frame(reader))
            assert refused["action"] == "read"
            assert refused["effect"] == "NOT_APPLIED"
            assert refused["status"] == "ACTION_UNAVAILABLE"
            assert refused["data"]["reason"] == "transport_capability_mismatch"
        assert [doc.get("action") for doc in harness.extension.forwarded] == []
        # The refusal poisoned nothing: a fresh old-digest connection still
        # serves an action inside the old set.
        connection, reader, writer, boot = _raw_connect(PREVIOUS_DIGEST)
        with connection:
            native.write_frame(writer, _browser_request("status", boot=boot))
            served = browser.validate_receipt(native.read_frame(reader))
            assert served["status"] == "OK" and served["action"] == "status"
        assert [doc.get("action") for doc in harness.extension.forwarded] == ["status"]
    finally:
        harness.stop()


def test_unmodified_old_client_accepts_the_new_host_answer(socket_dir, monkeypatch):
    # web_sol_client.py is byte-identical between the two releases, so the
    # current client with the previous digest reports exactly what the
    # unmodified old client reports: its own checks — ack echo, versions,
    # instance, challenge and boot — all pass against the new host.
    monkeypatch.setattr(client, "wsp", PreviousReleaseWsp(PREVIOUS_DIGEST))
    harness = HostHarness(socket_dir, extension_digest=wsp.transport_capability_digest())
    harness.start()
    try:
        served = client.browser_via_extension(
            INSTANCE, session_id="b" * 64, operation_key="status-operation",
            action="status",
        )
        assert served["status"] == "OK"
        assert served["transport_boot_nonce"] == harness.extension.boot_nonce
        assert served["data"]["stand_in"] is True
    finally:
        harness.stop()


def test_new_client_connects_and_menu_is_admitted(socket_dir):
    harness = HostHarness(socket_dir, extension_digest=wsp.transport_capability_digest())
    harness.start()
    try:
        status = client.browser_via_extension(
            INSTANCE, session_id="b" * 64, operation_key="status-operation",
            action="status",
        )
        connection_id = status["transport_boot_nonce"]
        menu = client.browser_via_extension(
            INSTANCE, session_id="b" * 64, operation_key="menu-operation",
            action="menu", connection_id=connection_id, tab_id=17,
            url_fingerprint="c" * 64, snapshot_id="snapshot-observation-001",
            ref="e1", params={"path": ["Thinking", "Extra High"]},
        )
        assert menu["status"] == "OK" and menu["action"] == "menu"
        assert [doc.get("action") for doc in harness.extension.forwarded] == [
            "status", "menu",
        ]
    finally:
        harness.stop()


def test_third_digest_is_refused_at_the_handshake(socket_dir):
    harness = HostHarness(socket_dir, extension_digest=wsp.transport_capability_digest())
    harness.start()
    try:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(5.0)
        connection.connect(str(wsi.socket_path(INSTANCE)))
        with connection:
            writer = connection.makefile("wb", buffering=0)
            reader = connection.makefile("rb", buffering=0)
            native.write_frame(
                writer,
                wsp.build_transport_hello(
                    role="client",
                    adapter_instance_id=INSTANCE,
                    client_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
                    native_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
                    extension_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
                    capability_digest=UNKNOWN_DIGEST,
                    boot_nonce=None,
                    challenge_nonce=secrets.token_urlsafe(24),
                ),
            )
            with pytest.raises(native.NativeHostError):
                native.read_frame(reader)
        assert harness.extension.forwarded == []
    finally:
        harness.stop()


def test_skipped_release_digest_is_refused_at_the_handshake(socket_dir):
    # b640dec1 (1c40ec98...) was staged but never live at either end. Under
    # RULING BR2-R2 it is a skipped release: the host must refuse its digest
    # exactly like any unknown one, not admit it as a second previous.
    harness = HostHarness(socket_dir, extension_digest=wsp.transport_capability_digest())
    harness.start()
    try:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(5.0)
        connection.connect(str(wsi.socket_path(INSTANCE)))
        with connection:
            writer = connection.makefile("wb", buffering=0)
            reader = connection.makefile("rb", buffering=0)
            native.write_frame(
                writer,
                wsp.build_transport_hello(
                    role="client",
                    adapter_instance_id=INSTANCE,
                    client_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
                    native_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
                    extension_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
                    capability_digest=SKIPPED_DIGEST,
                    boot_nonce=None,
                    challenge_nonce=secrets.token_urlsafe(24),
                ),
            )
            with pytest.raises(native.NativeHostError):
                native.read_frame(reader)
        assert harness.extension.forwarded == []
    finally:
        harness.stop()


def test_old_extension_holds_read_and_menu_back_from_a_new_client(socket_dir):
    # The host-respawn window: the extension still runs the previous release
    # (0.4.0) while a new-session client presents the new digest. The
    # connection is admitted on both digests, but `read` and `menu` do not
    # exist in the extension's set, so the host refuses them instead of
    # forwarding them to a worker that cannot execute them. Old actions keep
    # flowing.
    harness = HostHarness(socket_dir, extension_digest=PREVIOUS_DIGEST)
    harness.start()
    try:
        status = client.browser_via_extension(
            INSTANCE, session_id="b" * 64, operation_key="status-operation",
            action="status",
        )
        assert status["status"] == "OK"
        refused = client.browser_via_extension(
            INSTANCE, session_id="b" * 64, operation_key="menu-operation",
            action="menu", connection_id=status["transport_boot_nonce"],
            tab_id=17, url_fingerprint="c" * 64,
            snapshot_id="snapshot-observation-001", ref="e1",
            params={"path": ["Thinking", "Extra High"]},
        )
        assert refused["action"] == "menu"
        assert refused["effect"] == "NOT_APPLIED"
        assert refused["status"] == "ACTION_UNAVAILABLE"
        assert refused["data"]["reason"] == "transport_capability_mismatch"
        refused_read = client.browser_via_extension(
            INSTANCE, session_id="b" * 64, operation_key="read-operation",
            action="read", connection_id=status["transport_boot_nonce"],
            tab_id=17, url_fingerprint="c" * 64,
            snapshot_id="snapshot-observation-001", ref="e1",
            params={"offset": 0},
        )
        assert refused_read["action"] == "read"
        assert refused_read["effect"] == "NOT_APPLIED"
        assert refused_read["status"] == "ACTION_UNAVAILABLE"
        assert refused_read["data"]["reason"] == "transport_capability_mismatch"
        assert [doc.get("action") for doc in harness.extension.forwarded] == ["status"]
    finally:
        harness.stop()


def test_extension_with_unknown_digest_is_refused_at_startup(socket_dir):
    harness = HostHarness(socket_dir, extension_digest=UNKNOWN_DIGEST)
    harness.extension.start()
    with pytest.raises(native.NativeHostError, match="transport_capability_mismatch"):
        native.run_native_host(
            harness._chrome_in, harness._chrome_out,
            caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
            expected_instance_id=INSTANCE,
            socket_root=str(socket_dir), owner_uid=os.getuid(),
            action_timeout_seconds=5.0,
        )
    for stream in (harness._chrome_in, harness._chrome_out):
        try:
            stream.close()
        except OSError:
            pass


def test_extension_source_pins_the_current_digest_and_a_stable_id():
    # A rendered bundle is only coherent when the frozen source constant
    # matches the digest the deployment renders into instance_config.js;
    # a mismatch leaves INSTANCE_CONFIG null and the extension inert.
    extension = ROOT / "integrations/chairman_surfaces/web_sol_extension"
    background = (extension / "background.js").read_text()
    assert (
        f'EXPECTED_CAPABILITY_DIGEST = "{wsp.transport_capability_digest()}"'
        in background
    )
    assert PREVIOUS_DIGEST not in background
    assert SKIPPED_DIGEST not in background
    manifest = __import__("json").loads((extension / "manifest.json").read_text())
    # The key keeps the extension id (and therefore the native host manifests'
    # allowed_origins) stable across staging folders, so a reload can move to
    # a new folder without touching host registrations.
    assert isinstance(manifest.get("key"), str) and len(manifest["key"]) > 100


def test_installer_keeps_loaded_folders_untouched_by_default():
    from integrations.hermes_harness import install_browser

    parameters = inspect.signature(install_browser.install_profiles).parameters
    assert parameters["staging_root"].default is None
    assert parameters["update_loaded"].default is False
    completed = subprocess.run(
        [sys.executable, "-m", "integrations.hermes_harness.install_browser", "--help"],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--staging-root" in completed.stdout
    assert "--update-loaded" in completed.stdout
