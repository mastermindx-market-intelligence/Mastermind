"""MAS-115 / P0B-C0 disposable non-seat canary — hostile/mutation tests.

Falsifiers for :mod:`integrations.chairman_surfaces.nonseat_canary` and
:mod:`integrations.chairman_surfaces.nonseat_canary_vendors`, governed by
``DEC:CCR-P0B-AUTOMATION-OWNED-NONSEAT-CANARY-ONLY``. Every test here is
hermetic: only ``tmp_path``, injected fakes, and one bounded loopback
integration test (against a server this test suite starts itself) are ever
touched — never the real network, the real keychain, or a real profile
store.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import io
import json
import os
import pickle
import re
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import chatgpt
from integrations.chairman_surfaces import mas115_multilogin_port_policy as port_policy
from integrations.chairman_surfaces import nonseat_canary as core
from integrations.chairman_surfaces import nonseat_canary_vendors as vendors

PACKAGE_DIR = Path(core.__file__).resolve().parent
CORE_PATH = Path(core.__file__)
VENDORS_PATH = Path(vendors.__file__)

VENDORS = ("gologin", "multilogin")
_NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
_OBSERVED_AT = "2026-08-23T11:00:00Z"


# ---------------------------------------------------------------------------
# small local helpers
# ---------------------------------------------------------------------------


def _valid_provision(vendor: str, **overrides) -> dict:
    if vendor == "gologin":
        doc = {
            "schema": core.PROVISION_SCHEMA,
            "vendor": "gologin",
            "profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "origin_policy": port_policy.ORIGIN_POLICY,
            "benign_origin": port_policy.CANARY_ORIGIN,
            "disposable_ack": core.REQUIRED_ACK,
        }
    else:
        doc = {
            "schema": core.PROVISION_SCHEMA,
            "vendor": "multilogin",
            "profile_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "folder_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "browser_type": "mimic",
            "origin_policy": port_policy.ORIGIN_POLICY,
            "benign_origin": port_policy.CANARY_ORIGIN,
            "disposable_ack": core.REQUIRED_ACK,
        }
    doc.update(overrides)
    return doc


def _write_provision(tmp_path: Path, doc) -> Path:
    path = tmp_path / "provision.json"
    if isinstance(doc, str):
        path.write_text(doc, encoding="utf-8")
    else:
        stored = dict(doc)
        if stored.get("benign_origin") == port_policy.CANARY_ORIGIN:
            stored.pop("benign_origin")
        path.write_text(json.dumps(stored), encoding="utf-8")
    return path


def _stored_provision(doc: dict) -> dict:
    stored = dict(doc)
    stored.pop("benign_origin", None)
    return stored


def _environment_loader_for(provision: dict, *, running=False):
    def _load():
        return {
            "multilogin": [{
                "workspace_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                "profile_id": provision["profile_id"],
                "folder_id": provision["folder_id"],
                "running": running,
            }],
            "gologin": [
                {"profile_id": "111111111111111111111111", "running": True},
                {"profile_id": "222222222222222222222222", "running": True},
                {"profile_id": "333333333333333333333333", "running": True},
            ],
        }
    return _load


def _binding_doc(*, colliding_profile_id=None) -> dict:
    profile_ids = [
        colliding_profile_id or "111111111111111111111111",
        "222222222222222222222222",
        "333333333333333333333333",
    ]
    bindings = []
    for index, profile_id in enumerate(profile_ids, start=1):
        is_multilogin = "-" in profile_id
        locator = {
            "env_manager": "multilogin" if is_multilogin else "gologin",
            "profile_id": profile_id,
            # Schema-valid synthetic exact-chat address. The collision census
            # uses only the managed-profile identity and never reads this URL.
            "url": f"https://chatgpt.com/c/non-private-seat-{index}",
        }
        if is_multilogin:
            locator["folder_id"] = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        bindings.append(sb.new_binding(
            work_ref="WS:CCR",
            role="chairman" if index == 1 else "ceo",
            provider="chatgpt",
            locator_kind="chatgpt_managed_env",
            locator=locator,
            observed_at=_OBSERVED_AT,
            seat_ref=f"chatgpt{index}",
            # Current ChatGPT open is unsupported, so this can lawfully remain
            # null while the fresh observation proves the profile census.
            last_verified_at=None,
        ))
    return {"schema": sb.SCHEMA, "bindings": bindings}


def _no_collision_loader():
    return _binding_doc(), []


def _load_provision(path, *, bindings_loader):
    return core.load_provision(path, bindings_loader=bindings_loader, now=_NOW)


class _CountingNavigator:
    """Wraps a navigator fake and counts calls to its public surface."""

    def __init__(self, inner):
        self._inner = inner
        self.open_url_calls = 0
        self.list_pages_calls = 0

    def open_url(self, port, url):
        self.open_url_calls += 1
        return self._inner.open_url(port, url)

    def list_pages(self, port):
        self.list_pages_calls += 1
        return self._inner.list_pages(port)


class _RecordingVendorFake(core.HermeticVendorFake):
    """Records every lifecycle call's profile_ref; also carries a
    name-based-lookup temptation that must never be touched."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls: list = []
        self._profiles_by_name_reads = 0
        self._unexpected_attr_accesses: list = []

    @property
    def profiles_by_name(self):
        self._profiles_by_name_reads += 1
        return {"chairman-seat": self.profile_id}

    def __getattr__(self, name):
        # Reached only when normal attribute lookup already failed.
        self._unexpected_attr_accesses.append(name)
        raise AttributeError(name)

    def profile_exists(self, profile_ref):
        self.calls.append(("profile_exists", dict(profile_ref) if isinstance(profile_ref, dict) else profile_ref))
        return super().profile_exists(profile_ref)

    def is_running_externally(self, profile_ref):
        self.calls.append(("is_running_externally", dict(profile_ref)))
        return super().is_running_externally(profile_ref)

    def start(self, profile_ref):
        self.calls.append(("start", dict(profile_ref)))
        return super().start(profile_ref)

    def stop(self, profile_ref):
        self.calls.append(("stop", dict(profile_ref)))
        return super().stop(profile_ref)


def _harness(vendor: str, *, vendor_cls=core.HermeticVendorFake, credential=None):
    """Build a hermetic harness like build_hermetic_harness, but with an
    injectable vendor-fake class and credential."""
    harness = core.build_hermetic_harness(vendor)
    if vendor_cls is not core.HermeticVendorFake:
        vendor_fake = vendor_cls(vendor, harness["provision"]["profile_id"], harness["provision"].get("folder_id"))
        navigator_fake = core.HermeticNavigatorFake(vendor_fake, harness["origin_probe"])
        harness["vendor_client"] = vendor_fake
        harness["navigator"] = navigator_fake
        harness["process_probe"] = vendor_fake.process_counts
    if credential is not None:
        harness["credential"] = credential
    return harness


# ---------------------------------------------------------------------------
# 1. hermetic full-matrix PASS for both vendors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_hermetic_full_matrix_pass(vendor):
    receipts = core.run_matrix(**core.build_hermetic_harness(vendor))
    assert receipts["verdict"] == "PASS"
    assert receipts["schema"] == core.RECEIPTS_SCHEMA
    assert receipts["vendor"] == vendor
    row_ids = [row["row"] for row in receipts["rows"]]
    assert row_ids == ["C0", "C1", "C2", "C3", "C4", "C8", "C5", "C6", "C7", "C9", "C10"]
    for row in receipts["rows"]:
        assert row["ok"] is True, row


# ---------------------------------------------------------------------------
# 2. focus never contractual
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_focus_never_contractual(vendor):
    harness_none = core.build_hermetic_harness(vendor)
    receipts_none = core.run_matrix(**harness_none)

    harness_true = core.build_hermetic_harness(vendor)
    receipts_true = core.run_matrix(focus_probe=lambda: True, **harness_true)

    harness_flip = core.build_hermetic_harness(vendor)
    flipped = {"n": 0}

    def _focus_probe():
        flipped["n"] += 1
        return flipped["n"] % 2 == 0

    receipts_flip = core.run_matrix(focus_probe=_focus_probe, **harness_flip)

    assert receipts_none["verdict"] == receipts_true["verdict"] == receipts_flip["verdict"] == "PASS"

    c1_true = next(r for r in receipts_true["rows"] if r["row"] == "C1")
    assert c1_true["focus_observed"] is True
    assert c1_true["observation_only"] is True

    c1_none = next(r for r in receipts_none["rows"] if r["row"] == "C1")
    assert "focus_observed" not in c1_none


# ---------------------------------------------------------------------------
# 3. name-fallback impossible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_name_fallback_impossible(vendor):
    harness = _harness(vendor, vendor_cls=_RecordingVendorFake)
    receipts = core.run_matrix(**harness)
    assert receipts["verdict"] == "PASS"

    fake = harness["vendor_client"]
    assert fake._unexpected_attr_accesses == []
    assert fake._profiles_by_name_reads == 0

    for _, ref in fake.calls:
        assert set(ref.keys()) <= {"profile_id", "folder_id"}


# ---------------------------------------------------------------------------
# 4. identity-echo gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_identity_echo_gate(vendor):
    class _WrongIdentityVendorFake(core.HermeticVendorFake):
        def start(self, profile_ref):
            self.start_calls += 1
            self._running = True
            return {"profile_id": "wrong-profile-id-should-never-be-adopted", "port": 9999}

    provision = _valid_provision(vendor)
    vendor_fake = _WrongIdentityVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    origin_fake = core.HermeticOriginFake("token")
    navigator_fake = core.HermeticNavigatorFake(vendor_fake, origin_fake)
    credential = core.Credential("cred", "stdin")

    actuator = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake, navigator=navigator_fake, provision=provision, credential=credential,
    )
    with pytest.raises(core.CanaryRefusal) as exc_info:
        actuator.acquire()
    assert exc_info.value.code == "VENDOR_ERROR"
    assert actuator.owned is False

    with pytest.raises(core.CanaryRefusal):
        actuator.navigate(provision["benign_origin"] + "/a")
    assert actuator.owned is False


# ---------------------------------------------------------------------------
# 5. cross-profile retry impossible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_cross_profile_retry_impossible(vendor):
    harness = _harness(vendor, vendor_cls=_RecordingVendorFake)
    receipts = core.run_matrix(**harness)
    fake = harness["vendor_client"]

    c6 = next(r for r in receipts["rows"] if r["row"] == "C6")
    assert c6["code"] == "PROFILE_NOT_FOUND"
    assert c6["ok"] is True

    unknown_id = core.UNKNOWN_PROFILE_IDS[vendor]
    unknown_calls = [(op, ref) for op, ref in fake.calls if ref.get("profile_id") == unknown_id]
    assert unknown_calls, "expected the unknown ref to have been probed"
    assert all(op == "profile_exists" for op, _ref in unknown_calls)

    provisioned_id = harness["provision"]["profile_id"]
    all_ids = {ref.get("profile_id") for _op, ref in fake.calls}
    assert all_ids == {provisioned_id, unknown_id}

    if vendor == "multilogin":
        # M8: the multilogin unknown ref must carry the provisioned
        # folder_id — a bare profile_id-only ref can silently under-specify
        # the lookup on a folder-scoped vendor.
        for _op, ref in unknown_calls:
            assert ref.get("folder_id") == harness["provision"]["folder_id"]


# ---------------------------------------------------------------------------
# 6. repeat-start guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_repeat_start_guard(vendor):
    provision = _valid_provision(vendor)
    credential = core.Credential("cred", "stdin")

    # (a) acquire twice -> BUSY_PROFILE, start_calls stays 1.
    vendor_fake = core.HermeticVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    origin_fake = core.HermeticOriginFake("token")
    navigator_fake = core.HermeticNavigatorFake(vendor_fake, origin_fake)
    actuator = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake, navigator=navigator_fake, provision=provision, credential=credential,
    )
    actuator.acquire()
    assert vendor_fake.start_calls == 1
    with pytest.raises(core.CanaryRefusal) as exc_info:
        actuator.acquire()
    assert exc_info.value.code == "BUSY_PROFILE"
    assert vendor_fake.start_calls == 1

    # (b) fresh actuator, vendor reports externally running -> UNOWNED_RUNNING_PROFILE.
    vendor_fake_b = core.HermeticVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    vendor_fake_b._running = True  # simulate an externally-started browser
    navigator_fake_b = core.HermeticNavigatorFake(vendor_fake_b, origin_fake)
    actuator_b = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake_b, navigator=navigator_fake_b, provision=provision, credential=credential,
    )
    with pytest.raises(core.CanaryRefusal) as exc_info_b:
        actuator_b.navigate(provision["benign_origin"] + "/a")
    assert exc_info_b.value.code == "UNOWNED_RUNNING_PROFILE"
    assert vendor_fake_b.start_calls == 0

    # (c) fresh actuator, vendor reports not running -> UNSUPPORTED_SURFACE.
    vendor_fake_c = core.HermeticVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    navigator_fake_c = core.HermeticNavigatorFake(vendor_fake_c, origin_fake)
    actuator_c = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake_c, navigator=navigator_fake_c, provision=provision, credential=credential,
    )
    with pytest.raises(core.CanaryRefusal) as exc_info_c:
        actuator_c.navigate(provision["benign_origin"] + "/a")
    assert exc_info_c.value.code == "UNSUPPORTED_SURFACE"
    assert vendor_fake_c.start_calls == 0


# ---------------------------------------------------------------------------
# 7. owner-loss never auto-restarts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_owner_loss_never_auto_restarts(vendor):
    provision = _valid_provision(vendor)
    credential = core.Credential("cred", "stdin")
    vendor_fake = core.HermeticVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    origin_fake = core.HermeticOriginFake("token")
    navigator_fake = core.HermeticNavigatorFake(vendor_fake, origin_fake)
    actuator = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake, navigator=navigator_fake, provision=provision, credential=credential,
    )
    actuator.acquire()
    assert vendor_fake.start_calls == 1
    assert vendor_fake.stop_calls == 0

    actuator.drop_ownership()

    with pytest.raises(core.CanaryRefusal) as exc_nav:
        actuator.navigate(provision["benign_origin"] + "/a")
    assert exc_nav.value.code == "UNOWNED_RUNNING_PROFILE"
    assert vendor_fake.start_calls == 1
    assert vendor_fake.stop_calls == 0

    with pytest.raises(core.CanaryRefusal) as exc_rel:
        actuator.release()
    assert exc_rel.value.code == "UNSUPPORTED_SURFACE"
    assert vendor_fake.start_calls == 1
    assert vendor_fake.stop_calls == 0


# ---------------------------------------------------------------------------
# 8. credential hygiene
# ---------------------------------------------------------------------------

_SECRET = "hostile-secret-value-123"


def test_hostile_credential_repr_never_leaks():
    cred = core.Credential(_SECRET, "stdin")
    assert _SECRET not in repr(cred)
    assert _SECRET not in str(cred)


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_start_exception_never_leaks_secret(vendor):
    class _BoomVendorFake(core.HermeticVendorFake):
        def start(self, profile_ref):
            raise RuntimeError(_SECRET)

    provision = _valid_provision(vendor)
    vendor_fake = _BoomVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    origin_fake = core.HermeticOriginFake("token")
    navigator_fake = core.HermeticNavigatorFake(vendor_fake, origin_fake)
    credential = core.Credential(_SECRET, "stdin")
    actuator = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake, navigator=navigator_fake, provision=provision, credential=credential,
    )
    with pytest.raises(core.CanaryRefusal) as exc_info:
        actuator.acquire()
    exc = exc_info.value
    assert exc.code == "VENDOR_ERROR"
    assert _SECRET not in str(exc)
    assert _SECRET not in repr(exc)
    assert not any(_SECRET in str(a) for a in exc.args)

    # N10: the exception chain itself must be severed, not merely
    # display-suppressed — `raise ... from None` alone leaves __context__
    # pointing at the laundered original (only __cause__/traceback display
    # are affected by `from None`). Walking __context__/__cause__ must never
    # recover the RuntimeError carrying the secret.
    assert exc.__cause__ is None
    assert exc.__context__ is None
    walked = []
    node = exc
    for _ in range(10):
        node = node.__context__ or node.__cause__
        if node is None:
            break
        walked.append(node)
    assert walked == []


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_full_matrix_receipts_never_leak_secret(vendor):
    harness = core.build_hermetic_harness(vendor)
    harness["credential"] = core.Credential(_SECRET, "stdin")
    receipts = core.run_matrix(**harness)
    dumped = json.dumps(receipts)
    assert _SECRET not in dumped


def test_mutation_keychain_capture_path_is_structurally_absent():
    source = CORE_PATH.read_text(encoding="utf-8") + VENDORS_PATH.read_text(encoding="utf-8")
    assert "run_argv" not in source
    assert '.get("stdout")' not in source
    assert "capture_output" not in source
    assert ".communicate(" not in source
    assert ".stdout.read(" not in source
    assert "keychain_reader" not in inspect.signature(core.resolve_credential).parameters


def test_hostile_keychain_producer_is_fixed_direct_fd_pipe_not_captured_stdout():
    calls = []

    def _spawn(path, argv, env, *, file_actions):
        calls.append((path, list(argv), dict(env), list(file_actions)))
        dup_stdout = next(
            action for action in file_actions
            if action[0] == vendors.os.POSIX_SPAWN_DUP2 and action[2] == 1
        )
        vendors.os.write(dup_stdout[1], (_SECRET + "\n").encode("utf-8"))
        return 4242

    def _waitpid(pid, options):
        assert pid == 4242
        assert options == vendors.os.WNOHANG
        return pid, 0

    def _kill(*args):
        raise AssertionError("completed Keychain producer must not be signalled")

    pipe = vendors._open_keychain_credential_pipe(
        spawn=_spawn, waitpid=_waitpid, kill=_kill,
    )
    try:
        credential = vendors._read_direct_pipe_credential(pipe)
    finally:
        pipe.close()
    assert credential.present is True
    assert _SECRET not in repr(credential)
    assert len(calls) == 1
    path, argv, env, actions = calls[0]
    assert path == vendors._SECURITY_BIN
    assert argv == [
        vendors._SECURITY_BIN, "find-generic-password", "-w",
        "-s", vendors._KEYCHAIN_SERVICE, "-a", vendors._KEYCHAIN_ACCOUNT,
    ]
    assert env == {}
    assert [action[0] for action in actions] == [
        vendors.os.POSIX_SPAWN_OPEN,
        vendors.os.POSIX_SPAWN_DUP2,
        vendors.os.POSIX_SPAWN_OPEN,
        vendors.os.POSIX_SPAWN_CLOSE,
        vendors.os.POSIX_SPAWN_CLOSE,
    ]
    assert actions[0][1:] == (0, vendors.os.devnull, vendors.os.O_RDONLY, 0)
    assert actions[1][2] == 1
    assert actions[2][1:] == (2, vendors.os.devnull, vendors.os.O_WRONLY, 0)


def test_hostile_posix_spawn_file_actions_connect_direct_anonymous_pipe():
    def _benign_spawn(_path, _argv, env, *, file_actions):
        return vendors.os.posix_spawn(
            "/usr/bin/printf",
            ["/usr/bin/printf", "synthetic-direct-pipe"],
            env,
            file_actions=file_actions,
        )

    pipe = vendors._open_keychain_credential_pipe(spawn=_benign_spawn)
    try:
        credential = vendors._read_direct_pipe_credential(pipe)
    finally:
        pipe.close()
    assert credential.present is True
    assert "synthetic-direct-pipe" not in repr(credential)


def test_hostile_direct_pipe_credential_is_bounded_and_redacting():
    cred = vendors._read_direct_pipe_credential(io.StringIO(_SECRET + "\n"))
    assert cred.present is True
    assert cred.source == "stdin"
    assert _SECRET not in repr(cred)
    assert _SECRET not in str(cred)

    oversized = vendors._read_direct_pipe_credential(io.StringIO("x" * (vendors._MAX_STDIN_BYTES + 1)))
    assert oversized.present is False


def test_mutation_keychain_child_cleanup_is_bounded_to_own_pid(monkeypatch):
    monkeypatch.setattr(vendors, "_KEYCHAIN_WAIT_TIMEOUT_SECONDS", 0.0)
    read_fd, write_fd = vendors.os.pipe()
    vendors.os.close(write_fd)
    signals = []

    def _waitpid(pid, options):
        assert pid == 4242
        assert options == vendors.os.WNOHANG
        return 0, 0

    def _kill(pid, signal_number):
        assert pid == 4242
        signals.append(signal_number)

    pipe = vendors._KeychainCredentialPipe(
        read_fd, 4242, waitpid=_waitpid, kill=_kill,
    )
    pipe.close()
    assert signals == [vendors.signal.SIGTERM, vendors.signal.SIGKILL]


def test_hostile_resolve_credential_missing_direct_stdin_is_absent():
    cred = core.resolve_credential(vendor="gologin", stdin_text=None)
    assert cred.present is False
    assert cred.source == "absent"


# ---------------------------------------------------------------------------
# 9. receipt hygiene
# ---------------------------------------------------------------------------


def test_hostile_audit_receipts_flags_forbidden_content():
    clean_rows = [{"row": "C0", "code": "OK", "ok": True, "detail": core.DETAILS["OK"], "ts": "t"}]
    assert core.audit_receipts(clean_rows, ["secret-value"]) is True

    url_rows = [{"row": "C1", "code": "OK", "ok": True, "detail": "https://chatgpt.com/c/x", "ts": "t"}]
    assert core.audit_receipts(url_rows, []) is False

    profile_rows = [{"row": "C1", "code": "OK", "ok": True, "detail": "contains-profile-id-here", "ts": "t"}]
    assert core.audit_receipts(profile_rows, ["profile-id-here"]) is False

    argv_rows = [{"row": "C1", "code": "OK", "ok": True, "detail": "--user-data-dir=/tmp/x", "ts": "t"}]
    assert core.audit_receipts(argv_rows, []) is False


_ALLOWED_ROW_KEYS = {
    "row", "code", "ok", "detail", "ts",
    "url_digest", "process_counts", "provision_digest", "profile_digest",
    "start_calls_delta", "focus_observed", "observation_only",
    "expired_probed", "expired_ok", "predicates",
}

_ALLOWED_CLEANUP_KEYS = {
    "code", "detail", "ok", "attempted", "vendor_code", "process_counts", "predicates",
}


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_hermetic_receipts_pass_hygiene_and_closed_keys(vendor):
    receipts = core.run_matrix(**core.build_hermetic_harness(vendor))
    dumped = json.dumps(receipts)
    assert "://" not in dumped
    for row in receipts["rows"]:
        assert set(row.keys()) <= _ALLOWED_ROW_KEYS
        assert row["detail"] == core.DETAILS[row["code"]]
    assert set(receipts["cleanup"]) == _ALLOWED_CLEANUP_KEYS
    assert receipts["cleanup"]["detail"] == core.DETAILS[receipts["cleanup"]["code"]]


# ---------------------------------------------------------------------------
# 10. URL widening impossible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_url_widening_impossible(vendor):
    provision = _valid_provision(vendor)
    credential = core.Credential("cred", "stdin")
    vendor_fake = core.HermeticVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    origin_fake = core.HermeticOriginFake("token")
    inner_navigator = core.HermeticNavigatorFake(vendor_fake, origin_fake)
    navigator = _CountingNavigator(inner_navigator)
    actuator = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake, navigator=navigator, provision=provision, credential=credential,
    )
    actuator.acquire()

    for bad_url in (
        "https://chatgpt.com/c/anything",
        provision["benign_origin"] + "/etc/passwd",
        provision["benign_origin"] + "/a?x=1",
    ):
        with pytest.raises(core.CanaryRefusal) as exc_info:
            actuator.navigate(bad_url)
        assert exc_info.value.code == "DISALLOWED_TARGET"

    assert navigator.open_url_calls == 0


def test_hostile_allowed_url_exact_match_semantics():
    provision = {
        "origin_policy": port_policy.ORIGIN_POLICY,
        "benign_origin": port_policy.CANARY_ORIGIN,
    }
    assert core.allowed_url(provision, port_policy.CANARY_ORIGIN + "/a") is True
    assert core.allowed_url(provision, port_policy.CANARY_ORIGIN + "/b") is True
    assert core.allowed_url(provision, port_policy.CANARY_ORIGIN + "/a/") is False
    assert core.allowed_url(provision, port_policy.CANARY_ORIGIN + "/a?x=1") is False
    assert core.allowed_url(provision, "http://127.0.0.1:7777/etc/passwd") is False
    assert core.allowed_url(provision, "https://127.0.0.1:7777/a") is False
    assert core.allowed_url(provision, "http://127.0.0.1:7778/a") is False
    assert core.allowed_url(provision, "http://evil.example/a") is False


# ---------------------------------------------------------------------------
# 11. no click/fill/send surface (source-level)
# ---------------------------------------------------------------------------

_CDP_BANNED_PHRASES = (
    "input.dispatch", "runtime.evaluate", "page.evaluate",
    "mouse", "websocket", "send_keys", "elementhandle",
)


def test_falsifier_no_click_fill_send_surface():
    offenders = []
    for path in (CORE_PATH, VENDORS_PATH):
        lowered = path.read_text(encoding="utf-8").lower()
        for phrase in _CDP_BANNED_PHRASES:
            if phrase in lowered:
                offenders.append((path.name, phrase))
    assert offenders == []

    harness = core.build_hermetic_harness("gologin")
    actuator = core.NonSeatCanaryActuator(
        vendor_client=harness["vendor_client"], navigator=harness["navigator"],
        provision=harness["provision"], credential=harness["credential"],
    )
    public = {a for a in dir(actuator) if not a.startswith("_")}
    assert public == {"acquire", "navigate", "release", "drop_ownership", "owned"}

    webdriver_public = {
        a for a in dir(vendors.WebDriverNavigator)
        if not a.startswith("_") and callable(getattr(vendors.WebDriverNavigator, a))
    }
    assert webdriver_public == {"list_pages", "open_url"}

    hermetic_nav_public = {
        a for a in dir(core.HermeticNavigatorFake)
        if not a.startswith("_") and callable(getattr(core.HermeticNavigatorFake, a))
    }
    assert hermetic_nav_public == {"list_pages", "open_url"}


# ---------------------------------------------------------------------------
# 12. no profile-config mutation surface
# ---------------------------------------------------------------------------


def test_falsifier_profile_config_mutation_surface_is_exactly_allowlisted():
    """Catches any mutation path beyond the single fixed-port transaction."""
    core_text = CORE_PATH.read_text(encoding="utf-8").lower()
    vendor_text = VENDORS_PATH.read_text(encoding="utf-8").lower()
    for text in (core_text, vendor_text):
        for phrase in ("httpx.patch", "httpx.delete", "/browser/update", '"profile/update"'):
            assert phrase not in text
    assert "/profile/partial_update" not in core_text
    assert vendor_text.count('"/profile/partial_update"') == 1
    assert tuple(inspect.signature(
        vendors.BoundedHttpClient._mlx_configure_canary_port,
    ).parameters) == ("self", "credential", "profile_id", "snapshot")
    assert tuple(inspect.signature(
        vendors.MultiloginClient.configure_canary_port,
    ).parameters) == ("self", "profile_ref")
    assert tuple(inspect.signature(
        vendors.MultiloginClient.port_policy_snapshot,
    ).parameters) == ("self", "profile_ref")


def test_falsifier_webdriver_endpoint_allowlist():
    vendors_source = VENDORS_PATH.read_text(encoding="utf-8")
    found = set(re.findall(r"/json/\w+", vendors_source))
    assert found == set()
    for exact_path in ('path + "/url"', 'path + "/window"', 'path + "/window/handles"'):
        assert exact_path in vendors_source
    assert "def _webdriver_call" not in vendors_source


@pytest.mark.parametrize(
    "browser_type,browser_name,options_key",
    [("mimic", "chrome", "goog:chromeOptions"), ("stealthfox", "firefox", "moz:firefoxOptions")],
)
def test_webdriver_session_capabilities_are_exact_and_core_aware(browser_type, browser_name, options_key):
    seen = []

    def _handler(request):
        seen.append(json.loads(request.read()))
        return httpx.Response(200, json={"value": {
            "sessionId": "session-1", "capabilities": {"browserName": browser_name},
        }})

    inner = httpx.Client(transport=httpx.MockTransport(_handler), trust_env=False)
    client = vendors.BoundedHttpClient(client=inner)
    try:
        response = client._webdriver_create_session(9222, browser_type)
    finally:
        client.close()
    assert response.status_code == 200
    always = seen[0]["capabilities"]["alwaysMatch"]
    assert always == {
        "acceptInsecureCerts": False,
        "browserName": browser_name,
        "pageLoadStrategy": "normal",
        "unhandledPromptBehavior": "dismiss and notify",
        options_key: {},
    }
    assert seen[0]["capabilities"]["firstMatch"] == [{}]


class _ExactWebDriverTransport:
    def __init__(self, browser_name="chrome"):
        self.browser_name = browser_name
        self.current_url = "about:blank"
        self.calls = []

    def _webdriver_create_session(self, port, browser_type):
        self.calls.append(("create", port, browser_type))
        return vendors._BoundedResponse(200, {"value": {
            "sessionId": "session-1", "capabilities": {"browserName": self.browser_name},
        }})

    def _webdriver_window_handles(self, port, session_id):
        self.calls.append(("handles", port, session_id))
        return vendors._BoundedResponse(200, {"value": ["window-1"]})

    def _webdriver_current_window(self, port, session_id):
        self.calls.append(("current-window", port, session_id))
        return vendors._BoundedResponse(200, {"value": "window-1"})

    def _webdriver_switch_window(self, port, session_id, handle):
        self.calls.append(("switch-window", port, session_id, handle))
        return vendors._BoundedResponse(200, {"value": None})

    def _webdriver_navigate(self, port, session_id, url):
        self.calls.append(("navigate", port, session_id, url))
        self.current_url = url
        return vendors._BoundedResponse(200, {"value": None})

    def _webdriver_current_url(self, port, session_id):
        self.calls.append(("current-url", port, session_id))
        return vendors._BoundedResponse(200, {"value": self.current_url})


@pytest.mark.parametrize(
    "browser_type,browser_name",
    [("mimic", "chrome"), ("stealthfox", "firefox")],
)
def test_webdriver_navigator_supports_exact_navigation_for_both_multilogin_cores(browser_type, browser_name):
    provision = _valid_provision("multilogin", browser_type=browser_type)
    transport = _ExactWebDriverTransport(browser_name)
    navigator = vendors.WebDriverNavigator(transport, provision)
    target = provision["benign_origin"] + "/a"
    assert navigator.open_url(9222, target) is True
    assert navigator.list_pages(9222) == [target]
    assert [call[0] for call in transport.calls].count("create") == 1
    navigator._forget(9222)
    assert navigator.list_pages(9222) == []


@pytest.mark.parametrize("payload", [None, {}, {"value": None}, {"value": {"sessionId": "bad/id", "capabilities": {"browserName": "chrome"}}}])
def test_webdriver_navigator_refuses_malformed_or_changed_session_contract(payload):
    class _BadSessionTransport(_ExactWebDriverTransport):
        def _webdriver_create_session(self, port, browser_type):
            return None if payload is None else vendors._BoundedResponse(200, payload)

    provision = _valid_provision("multilogin")
    navigator = vendors.WebDriverNavigator(_BadSessionTransport(), provision)
    assert navigator.open_url(9222, provision["benign_origin"] + "/a") is False
    assert navigator.list_pages(9222) == []


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_profile_config_byte_identical_across_matrix(vendor):
    harness = core.build_hermetic_harness(vendor)
    fake = harness["vendor_client"]
    before = copy.deepcopy(fake.profile_config)
    core.run_matrix(**harness)
    assert fake.profile_config == before


# ---------------------------------------------------------------------------
# 13. ACK-only success impossible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_ack_only_success_impossible_origin_never_saw(vendor):
    harness = core.build_hermetic_harness(vendor)
    harness["origin_probe"].saw = lambda path: False  # type: ignore[method-assign]
    receipts = core.run_matrix(**harness)
    c1 = next(r for r in receipts["rows"] if r["row"] == "C1")
    assert c1["ok"] is False
    assert receipts["verdict"] == "FAIL"


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_ack_only_success_impossible_no_pages(vendor):
    harness = core.build_hermetic_harness(vendor)
    harness["navigator"].list_pages = lambda port: []  # type: ignore[method-assign]
    receipts = core.run_matrix(**harness)
    c1 = next(r for r in receipts["rows"] if r["row"] == "C1")
    assert c1["ok"] is False
    assert receipts["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# 14. provision gates, table-driven
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_provision_gate_missing_file(tmp_path, vendor):
    doc, code = _load_provision(str(tmp_path / "nope.json"), bindings_loader=_no_collision_loader)
    assert doc is None
    assert code == "PROVISION_MISSING"


def test_hostile_provision_gate_bad_json(tmp_path):
    path = _write_provision(tmp_path, "{not json")
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_bad_schema(tmp_path):
    bad = _valid_provision("gologin")
    bad["schema"] = "wrong.schema.v1"
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_unknown_key(tmp_path):
    bad = _valid_provision("gologin")
    bad["extra_key"] = "smuggled"
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_bad_ack(tmp_path):
    bad = _valid_provision("gologin", disposable_ack="not-the-required-ack")
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


@pytest.mark.parametrize(
    "origin",
    [
        "https://chatgpt.com",
        "http://127.0.0.1:7777/some/path",
        "http://evil.example.com:7777",
    ],
)
def test_hostile_provision_gate_rejects_any_persisted_origin_field(tmp_path, origin):
    bad = _valid_provision("gologin", benign_origin=origin)
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_gologin_with_folder_id(tmp_path):
    bad = _valid_provision("gologin")
    bad["folder_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_multilogin_without_folder_id(tmp_path):
    bad = _valid_provision("multilogin")
    del bad["folder_id"]
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


@pytest.mark.parametrize("browser_type", [None, "", "chromium", "firefox", "Mimic"])
def test_hostile_provision_gate_multilogin_requires_exact_browser_core(tmp_path, browser_type):
    bad = _valid_provision("multilogin")
    if browser_type is None:
        bad.pop("browser_type")
    else:
        bad["browser_type"] = browser_type
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_gologin_cannot_smuggle_browser_core(tmp_path):
    bad = _valid_provision("gologin", browser_type="mimic")
    path = _write_provision(tmp_path, bad)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_provision_gate_valid_ok(tmp_path, vendor):
    good = _valid_provision(vendor)
    path = _write_provision(tmp_path, good)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert code is None
    assert doc == _stored_provision(good)


def _chatgpt_binding_doc(profile_id: str) -> dict:
    return _binding_doc(colliding_profile_id=profile_id)


def test_hostile_provision_gate_seat_collision_same_profile_id(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    colliding_doc = _chatgpt_binding_doc(good["profile_id"])
    doc, code = _load_provision(str(path), bindings_loader=lambda: (colliding_doc, []))
    assert doc is None and code == "DISALLOWED_TARGET"


def test_hostile_provision_gate_seat_collision_different_profile_id(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    other_doc = _chatgpt_binding_doc("bbbbbbbbbbbbbbbbbbbbbbbb")
    doc, code = _load_provision(str(path), bindings_loader=lambda: (other_doc, []))
    assert code is None
    assert doc == _stored_provision(good)


def test_hostile_provision_gate_bindings_problems_fails_closed(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    doc, code = _load_provision(str(path), bindings_loader=lambda: (None, ["some problem"]))
    assert doc is None and code == "BINDINGS_UNAVAILABLE"


def test_hostile_provision_gate_bindings_absent_refuses(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    doc, code = _load_provision(str(path), bindings_loader=lambda: (None, []))
    assert doc is None
    assert code == "BINDINGS_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 15. local sweeps
# ---------------------------------------------------------------------------


def test_falsifier_local_no_subprocess_import():
    for path in (CORE_PATH, VENDORS_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "subprocess", path.name
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "subprocess", path.name


_BANNED_GUI_PHRASES = ("keystroke", "key code", "type text", "System Events")


def test_falsifier_local_no_gui_scripting_vocabulary():
    offenders = []
    for path in (CORE_PATH, VENDORS_PATH):
        lowered = path.read_text(encoding="utf-8").lower()
        for phrase in _BANNED_GUI_PHRASES:
            if phrase.lower() in lowered:
                offenders.append((path.name, phrase))
    assert offenders == []


# ---------------------------------------------------------------------------
# 16. determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_determinism(vendor):
    receipts_1 = core.run_matrix(**core.build_hermetic_harness(vendor))
    receipts_2 = core.run_matrix(**core.build_hermetic_harness(vendor))
    assert json.dumps(receipts_1, sort_keys=True) == json.dumps(receipts_2, sort_keys=True)


# ---------------------------------------------------------------------------
# 17. C5 exact evidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c5_exact_evidence(vendor):
    harness = core.build_hermetic_harness(vendor)
    fake = harness["vendor_client"]
    receipts = core.run_matrix(**harness)
    assert receipts["verdict"] == "PASS"
    assert fake.start_calls == 2  # C1 + C4 reopen
    assert fake.stop_calls == 2  # C4 release + fail-safe teardown after C5
    assert receipts["cleanup"]["attempted"] is True
    assert receipts["cleanup"]["ok"] is True
    assert receipts["cleanup"]["process_counts"]["after"]["this_profile"] == 0


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c5_zero_lifecycle_calls_after_drop(vendor):
    provision = _valid_provision(vendor)
    credential = core.Credential("cred", "stdin")
    vendor_fake = core.HermeticVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    origin_fake = core.HermeticOriginFake("token")
    navigator_fake = core.HermeticNavigatorFake(vendor_fake, origin_fake)
    actuator = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake, navigator=navigator_fake, provision=provision, credential=credential,
    )
    actuator.acquire()
    start_before, stop_before = vendor_fake.start_calls, vendor_fake.stop_calls
    actuator.drop_ownership()

    for action in (
        lambda: actuator.navigate(provision["benign_origin"] + "/a"),
        actuator.release,
    ):
        with pytest.raises(core.CanaryRefusal):
            action()

    assert vendor_fake.start_calls == start_before
    assert vendor_fake.stop_calls == stop_before


# ---------------------------------------------------------------------------
# 18. LoopbackBenignOrigin bounded loopback integration test
# ---------------------------------------------------------------------------


def test_hostile_loopback_benign_origin_integration():
    origin = vendors.LoopbackBenignOrigin(token="integration-token")
    try:
        base = origin.base_url
        assert base == port_policy.CANARY_ORIGIN
        assert origin.self_test() is True
        assert origin.saw("/a") is False
        assert origin.saw("/auth") is False

        with httpx.Client(base_url=base) as client:
            resp_a = client.get("/a")
            assert resp_a.status_code == 200
            assert origin.saw("/a")

            resp_set = client.get("/state/set")
            assert resp_set.status_code == 200
            assert "mas115_canary=integration-token" in resp_set.headers.get("set-cookie", "")

            resp_check = client.get("/state/check")
            assert resp_check.status_code == 200
            assert origin.cookie_seen("integration-token")

            resp_auth = client.get("/auth")
            assert resp_auth.status_code == 401

            resp_missing = client.get("/does-not-exist")
            assert resp_missing.status_code == 404
    finally:
        origin.close()


def test_loopback_origin_constructor_has_no_port_parameter():
    """Catches reintroducing caller-selected or fallback port behavior."""
    assert tuple(inspect.signature(vendors.LoopbackBenignOrigin).parameters) == ("token",)


# ---------------------------------------------------------------------------
# 19. B1 — defense-in-depth disposability gate (do not trust the provision dict)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_assert_disposable_blocks_actuator_construction(vendor):
    provision = _valid_provision(vendor, benign_origin="https://chatgpt.com", disposable_ack="not-the-required-ack")
    fake = _RecordingVendorFake(vendor, provision["profile_id"], provision.get("folder_id"))
    origin_fake = core.HermeticOriginFake("token")
    navigator_fake = core.HermeticNavigatorFake(fake, origin_fake)
    credential = core.Credential("cred", "stdin")

    with pytest.raises(core.CanaryRefusal) as exc_info:
        core.NonSeatCanaryActuator(
            vendor_client=fake, navigator=navigator_fake, provision=provision, credential=credential,
        )
    assert exc_info.value.code == "DISALLOWED_TARGET"
    # Construction must fail before the vendor fake is ever touched.
    assert fake.calls == []


def test_hostile_assert_disposable_requires_exact_multilogin_browser_core():
    provision = _valid_provision("multilogin")
    provision.pop("browser_type")
    fake = _RecordingVendorFake("multilogin", provision["profile_id"], provision["folder_id"])
    with pytest.raises(core.CanaryRefusal) as exc_info:
        core.NonSeatCanaryActuator(
            vendor_client=fake,
            navigator=core.HermeticNavigatorFake(fake, core.HermeticOriginFake("token")),
            provision=provision,
            credential=core.Credential("cred", "stdin"),
        )
    assert exc_info.value.code == "DISALLOWED_TARGET"
    assert fake.calls == []


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_assert_disposable_gates_run_matrix(vendor):
    harness = _harness(vendor, vendor_cls=_RecordingVendorFake)
    provision = dict(harness["provision"])
    provision["benign_origin"] = "https://chatgpt.com"
    provision["disposable_ack"] = "not-the-required-ack"
    harness["provision"] = provision

    with pytest.raises(core.CanaryRefusal) as exc_info:
        core.run_matrix(**harness)
    assert exc_info.value.code == "DISALLOWED_TARGET"
    assert harness["vendor_client"].start_calls == 0
    assert harness["vendor_client"].calls == []


def test_hostile_allowed_url_requires_loopback_hostname():
    provision = {"benign_origin": "http://evil.example.com:7777"}
    # Exact ALLOWED_PATHS suffix match, but the host is not loopback.
    assert core.allowed_url(provision, "http://evil.example.com:7777/a") is False


def test_hostile_allowed_url_rejects_dangerous_url_schemes():
    provision = {
        "origin_policy": port_policy.ORIGIN_POLICY,
        "benign_origin": port_policy.CANARY_ORIGIN,
    }
    for bad_url in ("javascript:alert(1)", "data:text/html,hi", "file:///etc/passwd"):
        assert core.allowed_url(provision, bad_url) is False


# ---------------------------------------------------------------------------
# 20. B2 — case-insensitive profile-id collision + canonicalization
# ---------------------------------------------------------------------------


def test_hostile_provision_load_canonicalizes_multilogin_ids_to_lowercase(tmp_path):
    good = _valid_provision("multilogin")
    good["profile_id"] = good["profile_id"].upper()
    good["folder_id"] = good["folder_id"].upper()
    path = _write_provision(tmp_path, good)
    doc, code = _load_provision(str(path), bindings_loader=_no_collision_loader)
    assert code is None
    assert doc["profile_id"] == good["profile_id"].lower()
    assert doc["folder_id"] == good["folder_id"].lower()


def test_hostile_provision_gate_seat_collision_case_insensitive(tmp_path):
    good = _valid_provision("multilogin")
    lower_profile_id = good["profile_id"]
    good["profile_id"] = lower_profile_id.upper()
    path = _write_provision(tmp_path, good)
    colliding_doc = _chatgpt_binding_doc(lower_profile_id)
    doc, code = _load_provision(str(path), bindings_loader=lambda: (colliding_doc, []))
    assert doc is None and code == "DISALLOWED_TARGET"


# ---------------------------------------------------------------------------
# 21. B3 — profile-scoped ownership in the live MultiloginClient/GoLoginClient
# ---------------------------------------------------------------------------


def _success(data, message=""):
    return vendors._BoundedResponse(200, {
        "status": {"error_code": "", "http_code": 200, "message": message},
        "data": data,
    })


def _metas_payload(
    *, profile_id="p1", folder_id="f1", ports=None, auto=False,
    browser_type="mimic", in_use_by="", storage_flag=False,
):
    fingerprint = {} if ports is None else {"ports": list(ports)}
    return {
        "status": {
            "error_code": "",
            "http_code": 200,
            "message": "List of profiles metadata",
        },
        "data": {
            "profiles": [{
                "id": profile_id,
                "folder_id": folder_id,
                "browser_type": browser_type,
                "in_use_by": in_use_by,
                "is_auto_update": auto,
                "parameters": {
                    "flags": {"ports_masking": "mask"},
                    "fingerprint": fingerprint,
                    "storage": {
                        "is_local": False,
                        "save_service_worker": storage_flag,
                    },
                },
                "last_update_at": "synthetic-before",
                "last_updated_by": "synthetic-operator",
            }],
        },
    }


class _ExactMultiloginTransport:
    def __init__(self, browser_type="mimic", profile_id="p1", folder_id="f1"):
        self.calls = []
        self.state = "stopped"
        self.status_response = None
        self.browser_type = browser_type
        self.profile_id = profile_id
        self.folder_id = folder_id
        self.ports = []
        self.auto_update = False
        self.partial_update_response = _success(None, "Profile successfully updated")
        self.apply_update_effect = True
        self.mutate_storage_after_update = False
        self.search_in_use_by = ""
        self.search_locked_by = ""
        self.metas_response = None
        self.metas_mode = "mask"

    def _mlx_profile_search(self, credential, folder_id, *, offset):
        self.calls.append(("search", folder_id, offset))
        return _success({
            "profiles": [{
                "id": self.profile_id, "folder_id": folder_id, "name": "synthetic",
                "browser_type": self.browser_type,
                "in_use_by": self.search_in_use_by,
                "locked_by": self.search_locked_by,
            }],
            "total_count": 1,
        }, "Search profile successfully result")

    def _mlx_profile_status(self, credential, profile_id):
        self.calls.append(("status", profile_id))
        if self.status_response is not None:
            return self.status_response
        return _success({
            "profile_id": profile_id,
            "folder_id": self.folder_id,
            "status": self.state,
            "browser_type": self.browser_type,
            "core_version": 132,
            "in_use_by": "synthetic-owner" if self.state == "browser_running" else "",
            "is_quick": False,
            "last_launched_at": "2026-08-23T00:00:00Z",
            "last_launched_by": "synthetic-operator",
            "last_launched_on": "synthetic-machine",
            "message": "",
            "name": "synthetic",
            "timestamp": 1787472000000,
            "workspace_id": "synthetic-workspace",
        })

    def _mlx_profile_start(self, credential, folder_id, profile_id):
        self.calls.append(("start", folder_id, profile_id))
        self.state = "browser_running"
        return _success({
            "id": profile_id, "port": "9222", "browser_type": self.browser_type,
            "core_version": 132, "is_quick": False,
        }, "Profile started successfully")

    def _mlx_profile_stop(self, credential, profile_id):
        self.calls.append(("stop", profile_id))
        self.state = "stopped"
        return vendors._BoundedResponse(200, {
            "status": {"error_code": "", "http_code": 200, "message": ""},
        })

    def _mlx_profile_metas(self, credential, profile_id):
        self.calls.append(("metas", profile_id))
        if self.metas_response is not None:
            return self.metas_response
        payload = _metas_payload(
            profile_id=profile_id,
            folder_id=self.folder_id,
            ports=self.ports,
            auto=self.auto_update,
            browser_type=self.browser_type,
            storage_flag=self.mutate_storage_after_update and bool(self.ports),
        )
        payload["data"]["profiles"][0]["parameters"]["flags"]["ports_masking"] = self.metas_mode
        return vendors._BoundedResponse(200, payload)

    def _mlx_configure_canary_port(self, credential, profile_id, snapshot):
        self.calls.append(("configure", profile_id, snapshot.auto_update_core))
        if self.apply_update_effect:
            self.ports = [port_policy.CANARY_PORT]
        return self.partial_update_response

    def close(self):
        self.calls.append(("close",))


class _ReadyOrigin:
    base_url = port_policy.CANARY_ORIGIN

    def __init__(self, *, token):
        self.token = token
        self.closed = False

    def self_test(self):
        return True

    def close(self):
        self.closed = True


def test_configure_canary_port_preserves_auto_update_and_reads_back():
    """Catches omitting the vendor auto-update flag or accepting without read-back."""
    transport = _ExactMultiloginTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "CONFIGURED"
    assert receipt["predicates"] == {
        "preservation_unchanged": True,
        "auto_update_unchanged": True,
        "exact_profile_stopped": True,
    }
    assert transport.calls == [
        ("search", "f1", 0), ("status", "p1"), ("metas", "p1"),
        ("configure", "p1", False),
        ("search", "f1", 0), ("status", "p1"), ("metas", "p1"),
    ]


def test_configure_canary_port_is_idempotent_without_update():
    """Catches writing an already exact disposable profile."""
    transport = _ExactMultiloginTransport()
    transport.ports = [port_policy.CANARY_PORT]
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "ALREADY_CONFIGURED"
    assert not any(call[0] == "configure" for call in transport.calls)


@pytest.mark.parametrize(
    ("response", "effect", "expected"),
    (
        (None, False, "EFFECT_UNKNOWN"),
        (vendors._BoundedResponse(200, {"renamed": "response"}), True,
         "CONFIGURED_AFTER_RECONCILIATION"),
        (vendors._BoundedResponse(500, None), False, "EFFECT_UNKNOWN"),
    ),
)
def test_ambiguous_update_never_retries_and_only_reconciles_read_only(response, effect, expected):
    """Catches retrying an ambiguous mutation or skipping its single read-back."""
    transport = _ExactMultiloginTransport()
    transport.partial_update_response = response
    transport.apply_update_effect = effect
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert sum(call[0] == "configure" for call in transport.calls) == 1
    assert receipt["code"] == expected
    assert receipt["reconciled"] is True
    assert [call[0] for call in transport.calls[-3:]] == ["search", "status", "metas"]


def test_post_update_non_target_drift_vetoes_success():
    """Catches reporting PASS when an unrelated profile parameter changed."""
    transport = _ExactMultiloginTransport()
    transport.mutate_storage_after_update = True
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "PRESERVATION_DRIFT"
    assert receipt["verdict"] == "HOLD"


@pytest.mark.parametrize("status_code", (401, 403))
def test_configuration_auth_rejection_has_no_readback_or_retry(status_code):
    """Catches treating explicit auth failure as an ambiguous applied update."""
    transport = _ExactMultiloginTransport()
    transport.partial_update_response = vendors._BoundedResponse(status_code, None)
    transport.apply_update_effect = False
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "AUTH_EXPIRED_NO_PROOF"
    assert [call[0] for call in transport.calls].count("configure") == 1
    assert [call[0] for call in transport.calls].count("metas") == 1


def test_configuration_explicit_rejection_has_no_readback_or_retry():
    """Catches retry/reconciliation after a schema-valid definitive rejection."""
    transport = _ExactMultiloginTransport()
    transport.partial_update_response = vendors._BoundedResponse(400, {
        "status": {"error_code": "INVALID_INPUT", "http_code": 400, "message": "rejected"},
        "data": None,
    })
    transport.apply_update_effect = False
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "REJECTED_NO_PROOF"
    assert [call[0] for call in transport.calls].count("configure") == 1
    assert [call[0] for call in transport.calls].count("metas") == 1


def test_wrong_success_message_requires_read_only_reconciliation():
    """Catches trusting vendor prose drift as a definitive success envelope."""
    transport = _ExactMultiloginTransport()
    transport.partial_update_response = _success(None, "renamed success")
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "CONFIGURED_AFTER_RECONCILIATION"
    assert receipt["reconciled"] is True


@pytest.mark.parametrize(
    ("mutation", "value"),
    (
        ("running", "browser_running"),
        ("owned", "other-session"),
        ("locked", "other-lock"),
        ("browser", "stealthfox"),
        ("mode", "natural"),
    ),
)
def test_configuration_refuses_nonexact_preflight_without_update(mutation, value):
    """Catches configuring a running, owned, locked, non-Mimic, or widened profile."""
    transport = _ExactMultiloginTransport()
    if mutation == "running":
        transport.state = value
    elif mutation == "owned":
        transport.search_in_use_by = value
    elif mutation == "locked":
        transport.search_locked_by = value
    elif mutation == "browser":
        transport.browser_type = value
    else:
        transport.metas_mode = value
    client = vendors.MultiloginClient(
        core.Credential("cred", "stdin"), transport, browser_type=transport.browser_type,
    )
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["verdict"] != "PASS"
    assert not any(call[0] == "configure" for call in transport.calls)


def test_configuration_missing_credential_refuses_before_vendor_calls():
    """Catches a configuration read or write without a present credential."""
    transport = _ExactMultiloginTransport()
    client = vendors.MultiloginClient(core.Credential(None, "absent"), transport)
    receipt = client.configure_canary_port({"profile_id": "p1", "folder_id": "f1"})
    assert receipt["code"] == "VENDOR_ERROR"
    assert transport.calls == []


def test_bounded_transport_serializes_only_the_approved_partial_update():
    """Catches endpoint, method, authorization, or body widening at the HTTP boundary."""
    observed = []

    def handler(request):
        observed.append({
            "method": request.method,
            "url": str(request.url),
            "authorization": request.headers.get("authorization"),
            "body": json.loads(request.content),
        })
        return httpx.Response(200, json={
            "status": {
                "error_code": "",
                "http_code": 200,
                "message": "Profile successfully updated",
            },
            "data": None,
        })

    raw = httpx.Client(
        transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False,
    )
    bounded = vendors.BoundedHttpClient(client=raw)
    snapshot = port_policy.classify_profile_metas(
        _metas_payload(), profile_id="p1", folder_id="f1",
    )
    response = bounded._mlx_configure_canary_port(
        core.Credential("secret-value", "stdin"), "p1", snapshot,
    )
    bounded.close()
    assert response.status_code == 200
    assert observed == [{
        "method": "POST",
        "url": "https://api.multilogin.com/profile/partial_update",
        "authorization": "Bearer secret-value",
        "body": {
            "profile_id": "p1",
            "auto_update_core": False,
            "parameters": {
                "flags": {"ports_masking": "mask"},
                "fingerprint": {"ports": [65535]},
            },
        },
    }]


def test_vendor_configure_operation_emits_only_redacted_configuration_receipt(tmp_path):
    """Catches routing the operator command into the C0-C10 launch path."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    transport = _ExactMultiloginTransport(
        profile_id=provision["profile_id"], folder_id=provision["folder_id"],
    )
    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        [
            "configure-canary-port", "--vendor", "multilogin",
            "--provision-path", str(path),
        ],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    receipt = json.loads(out.getvalue())
    assert code == 0
    assert receipt["code"] == "CONFIGURED"
    assert "p1" not in out.getvalue()
    assert [call[0] for call in transport.calls].count("configure") == 1
    assert not any(call[0] == "start" for call in transport.calls)


def test_vendor_run_refuses_default_policy_without_update_or_start(tmp_path):
    """Catches ordinary run silently mutating or launching an unconfigured profile."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    transport = _ExactMultiloginTransport(
        profile_id=provision["profile_id"], folder_id=provision["folder_id"],
    )
    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["run", "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == "UNSUPPORTED_PORT_STATE"
    assert not any(call[0] in {"configure", "start"} for call in transport.calls)


def test_vendor_run_requires_exact_preflight_and_postflight_without_update(tmp_path, monkeypatch):
    """Catches launching before the exact policy or omitting post-run preservation proof."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    transport = _ExactMultiloginTransport(
        profile_id=provision["profile_id"], folder_id=provision["folder_id"],
    )
    transport.ports = [port_policy.CANARY_PORT]
    matrix_calls = []

    def fake_matrix(**kwargs):
        matrix_calls.append(kwargs["provision"]["benign_origin"])
        return {
            "schema": core.RECEIPTS_SCHEMA,
            "vendor": "multilogin",
            "rows": [{
                "row": "C10", "code": "OK", "ok": True,
                "detail": core.DETAILS["OK"], "ts": "synthetic",
            }],
            "cleanup": {"ok": True},
            "verdict": "PASS",
        }

    monkeypatch.setattr(vendors._core, "run_matrix", fake_matrix)
    monkeypatch.setattr(vendors, "live_process_probe", lambda provision: lambda: {})
    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["run", "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert code == 0
    assert json.loads(out.getvalue())["verdict"] == "PASS"
    assert matrix_calls == [port_policy.CANARY_ORIGIN]
    assert [call[0] for call in transport.calls].count("metas") == 2
    assert not any(call[0] == "configure" for call in transport.calls)


def test_vendor_run_postflight_drift_vetoes_matrix_pass(tmp_path, monkeypatch):
    """Catches returning PASS after the profile policy drifts during C0-C10."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    transport = _ExactMultiloginTransport(
        profile_id=provision["profile_id"], folder_id=provision["folder_id"],
    )
    transport.ports = [port_policy.CANARY_PORT]

    def fake_matrix(**kwargs):
        transport.mutate_storage_after_update = True
        return {
            "schema": core.RECEIPTS_SCHEMA,
            "vendor": "multilogin",
            "rows": [{
                "row": "C10", "code": "OK", "ok": True,
                "detail": core.DETAILS["OK"], "ts": "synthetic",
            }],
            "cleanup": {"ok": True},
            "verdict": "PASS",
        }

    monkeypatch.setattr(vendors._core, "run_matrix", fake_matrix)
    monkeypatch.setattr(vendors, "live_process_probe", lambda provision: lambda: {})
    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["run", "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    receipt = json.loads(out.getvalue())
    assert code == 1
    assert receipt["verdict"] == "FAIL"
    assert receipt["rows"][0]["row"] == "C10"
    assert receipt["rows"][0]["code"] == "UNSUPPORTED_PORT_STATE"
    assert receipt["rows"][0]["ok"] is False
    assert not any(call[0] == "configure" for call in transport.calls)


def test_hostile_multilogin_repeat_start_guard_before_http():
    transport = _ExactMultiloginTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    ref = {"profile_id": "p1", "folder_id": "f1"}

    result = client.start(ref)
    assert result == {"profile_id": "p1", "port": 9222}
    assert [call[0] for call in transport.calls] == ["search", "status", "start"]

    calls_before = list(transport.calls)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start(ref)
    assert exc_info.value.code == "BUSY_PROFILE"
    assert transport.calls == calls_before


def test_hostile_multilogin_cleanup_lease_survives_owner_loss_and_stops_exact_profile_once():
    transport = _ExactMultiloginTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    ref = {"profile_id": "p1", "folder_id": "f1"}
    client.start(ref)
    client.forget_ownership()

    calls_before = list(transport.calls)
    assert client._cleanup_started_profile() is True
    assert transport.calls == calls_before + [("stop", "p1")]
    assert transport.state == "stopped"
    assert client._cleanup_started_profile() is False
    assert transport.calls == calls_before + [("stop", "p1")]


def test_hostile_multilogin_ambiguous_start_response_retains_exact_cleanup_lease():
    class _AmbiguousStartTransport(_ExactMultiloginTransport):
        def _mlx_profile_start(self, credential, folder_id, profile_id):
            self.calls.append(("start", folder_id, profile_id))
            self.state = "browser_running"
            return None

    transport = _AmbiguousStartTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"
    assert client._cleanup_started_profile() is True
    assert transport.calls[-1] == ("stop", "p1")
    assert transport.state == "stopped"


@pytest.mark.parametrize("browser_type", ["mimic", "stealthfox"])
def test_multilogin_exact_core_selenium_launch_contract_accepts_both_documented_cores(browser_type):
    transport = _ExactMultiloginTransport(browser_type)
    client = vendors.MultiloginClient(
        core.Credential("cred", "stdin"), transport, browser_type=browser_type,
    )
    assert client.start({"profile_id": "p1", "folder_id": "f1"}) == {
        "profile_id": "p1", "port": 9222,
    }
    assert [call[0] for call in transport.calls] == ["search", "status", "start"]


def test_hostile_gologin_forget_ownership_is_noop():
    client = vendors.GoLoginClient(core.Credential("cred", "stdin"))
    # Must exist, be a no-op, and require no network / not raise.
    assert client.forget_ownership() is None


# ---------------------------------------------------------------------------
# 22. M4 — owner-loss simulation forgets client ownership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_drop_ownership_forgets_vendor_client_state(vendor):
    harness = core.build_hermetic_harness(vendor)
    vendor_fake = harness["vendor_client"]
    actuator = core.NonSeatCanaryActuator(
        vendor_client=vendor_fake, navigator=harness["navigator"], provision=harness["provision"],
        credential=harness["credential"],
    )
    profile_ref = {"profile_id": harness["provision"]["profile_id"]}
    if "folder_id" in harness["provision"]:
        profile_ref["folder_id"] = harness["provision"]["folder_id"]

    actuator.acquire()
    # While we own it, the vendor fake must never call it "externally running".
    assert vendor_fake.is_running_externally(profile_ref) is False

    actuator.drop_ownership()
    assert vendor_fake.is_running_externally(profile_ref) is True

    start_before, stop_before = vendor_fake.start_calls, vendor_fake.stop_calls
    with pytest.raises(core.CanaryRefusal) as exc_info:
        actuator.navigate(harness["provision"]["benign_origin"] + "/a")
    assert exc_info.value.code == "UNOWNED_RUNNING_PROFILE"
    # drop_ownership()'s vendor_client.forget_ownership() call is itself
    # never a start/stop.
    assert vendor_fake.start_calls == start_before
    assert vendor_fake.stop_calls == stop_before


def test_hostile_drop_ownership_getattr_guard_survives_missing_forget_ownership():
    provision = _valid_provision("gologin")

    class _NoForgetVendor:
        pass

    origin_fake = core.HermeticOriginFake("token")
    navigator_fake = core.HermeticNavigatorFake(
        core.HermeticVendorFake("gologin", provision["profile_id"]), origin_fake,
    )
    actuator = core.NonSeatCanaryActuator(
        vendor_client=_NoForgetVendor(), navigator=navigator_fake, provision=provision,
        credential=core.Credential("cred", "stdin"),
    )
    actuator._owned = {"profile_key": provision["profile_id"], "port": 9222}
    actuator.drop_ownership()  # must not raise despite the vendor lacking forget_ownership
    assert actuator.owned is False


def test_hostile_multilogin_is_running_externally_profile_scoped():
    transport = _ExactMultiloginTransport()
    transport.state = "browser_running"
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)

    ref_p = {"profile_id": "p1", "folder_id": "f1"}
    ref_q = {"profile_id": "q1", "folder_id": "f1"}

    # Before we've started anything, the vendor's "active" is externally owned.
    assert client.is_running_externally(ref_p) is True

    # Simulate having started P (no network — set the profile-scoped state directly).
    client._started_profile_id = "p1"
    assert client.is_running_externally(ref_p) is False
    assert client.is_running_externally(ref_q) is True

    client.forget_ownership()
    assert client.is_running_externally(ref_p) is True


# ---------------------------------------------------------------------------
# 23. M5 — real-launch evidence in the process counts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c1_requires_real_launch_evidence(vendor):
    harness = core.build_hermetic_harness(vendor)
    harness["process_probe"] = lambda: {"this_profile": 0, "other_profiles": 0}
    receipts = core.run_matrix(**harness)
    c1 = next(r for r in receipts["rows"] if r["row"] == "C1")
    assert c1["ok"] is False
    assert c1["code"] == "LAUNCH_FAILED"
    assert c1["predicates"]["exact_profile_process_group_started"] is False
    assert receipts["verdict"] == "FAIL"


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c1_accepts_exact_profile_process_group_and_emits_split_predicates(vendor):
    harness = core.build_hermetic_harness(vendor)
    fake = harness["vendor_client"]

    def _process_group_counts():
        return {"this_profile": 6 if fake._running else 0, "other_profiles": 39}

    harness["process_probe"] = _process_group_counts
    receipts = core.run_matrix(**harness)
    c1 = next(r for r in receipts["rows"] if r["row"] == "C1")
    assert receipts["verdict"] == "PASS"
    assert c1["process_counts"]["before"] == {"this_profile": 0, "other_profiles": 39}
    assert c1["process_counts"]["after"] == {"this_profile": 6, "other_profiles": 39}
    assert c1["predicates"] == {
        "baseline_closed": True,
        "exact_profile_process_group_started": True,
        "other_profiles_unchanged": True,
        "benign_origin_observed": True,
        "navigated_page_membership": True,
    }
    assert receipts["cleanup"]["process_counts"]["after"] == {
        "this_profile": 0,
        "other_profiles": 39,
    }


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c1_navigation_failure_is_distinct_and_still_cleans_up(vendor):
    harness = core.build_hermetic_harness(vendor)
    harness["origin_probe"].saw = lambda _path: False
    receipts = core.run_matrix(**harness)
    c1 = next(r for r in receipts["rows"] if r["row"] == "C1")
    assert c1["code"] == "NAVIGATION_FAILED"
    assert c1["predicates"]["exact_profile_process_group_started"] is True
    assert c1["predicates"]["benign_origin_observed"] is False
    assert receipts["cleanup"]["attempted"] is True
    assert receipts["cleanup"]["ok"] is True
    assert harness["vendor_client"]._running is False


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_cleanup_failure_vetoes_otherwise_complete_matrix(vendor):
    class _CleanupFailVendor(core.HermeticVendorFake):
        def _cleanup_started_profile(self):
            raise core.CanaryRefusal("VENDOR_ERROR")

    harness = _harness(vendor, vendor_cls=_CleanupFailVendor)
    receipts = core.run_matrix(**harness)
    assert all(row["ok"] is True for row in receipts["rows"])
    assert receipts["cleanup"]["code"] == "CLEANUP_FAILED"
    assert receipts["cleanup"]["vendor_code"] == "VENDOR_ERROR"
    assert receipts["cleanup"]["ok"] is False
    assert receipts["verdict"] == "FAIL"


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_unexpected_post_start_exception_still_invokes_cleanup(vendor):
    harness = core.build_hermetic_harness(vendor)
    fake = harness["vendor_client"]
    calls = {"clock": 0}

    def _clock():
        calls["clock"] += 1
        if calls["clock"] == 2:
            raise RuntimeError("synthetic post-start matrix failure")
        return f"2026-01-01T00:00:{calls['clock']:02d}.000000Z"

    harness["clock"] = _clock
    with pytest.raises(RuntimeError, match="synthetic post-start matrix failure"):
        core.run_matrix(**harness)
    assert fake.start_calls == 1
    assert fake.stop_calls == 1
    assert fake._running is False


def test_hostile_live_cleanup_probe_waits_boundedly_for_exact_process_group_exit():
    observations = iter((
        {"this_profile": 6, "other_profiles": 39},
        {"this_profile": 2, "other_profiles": 39},
        {"this_profile": 0, "other_profiles": 39},
    ))
    now = {"value": 0.0}
    sleeps = []

    def _monotonic():
        now["value"] += 0.1
        return now["value"]

    probe = vendors._settled_cleanup_probe(
        lambda: next(observations),
        monotonic=_monotonic,
        sleep=lambda seconds: sleeps.append(seconds),
        timeout_seconds=1.0,
    )
    assert probe() == {"this_profile": 0, "other_profiles": 39}
    assert sleeps == [
        vendors._CLEANUP_PROCESS_POLL_SECONDS,
        vendors._CLEANUP_PROCESS_POLL_SECONDS,
    ]


# ---------------------------------------------------------------------------
# 24. M6 — C7 expiry sub-probe honesty
# ---------------------------------------------------------------------------


class _NoExpiryLeverVendorFake(core.HermeticVendorFake):
    """Models a live vendor client with no expiry lever at all — plain
    ``hasattr(client, 'expired_credential')`` must be False."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        del self.expired_credential

    def _check_expired(self) -> None:
        return None


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c7_expired_probed_true_on_hermetic_fake(vendor):
    receipts = core.run_matrix(**core.build_hermetic_harness(vendor))
    c7 = next(r for r in receipts["rows"] if r["row"] == "C7")
    assert c7["expired_probed"] is True
    assert c7["expired_ok"] is True
    assert c7["ok"] is True


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c7_expired_probed_false_when_no_lever(vendor):
    harness = _harness(vendor, vendor_cls=_NoExpiryLeverVendorFake)
    assert not hasattr(harness["vendor_client"], "expired_credential")
    receipts = core.run_matrix(**harness)
    c7 = next(r for r in receipts["rows"] if r["row"] == "C7")
    assert c7["expired_probed"] is False
    # Missing expiry lever must never fail the row — only auth-missing drives it.
    assert c7["ok"] is True
    assert receipts["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# 25. M7 — CLI vendor/provision agreement
# ---------------------------------------------------------------------------


def test_hostile_helper_vendor_provision_mismatch_refuses_before_keychain_or_client(tmp_path):
    gologin_doc = _valid_provision("gologin")
    path = _write_provision(tmp_path, gologin_doc)

    def _boom_credential_factory():
        raise AssertionError("Keychain must not start on a vendor mismatch")

    class _BoomClient:
        def __init__(self, *a, **kw):
            raise AssertionError("client must never be constructed on a vendor mismatch")

    buf = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["--vendor", "multilogin", "--provision-path", str(path)],
        stdout=buf, bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(_valid_provision("multilogin")),
        credential_stream_factory=_boom_credential_factory,
        client_factory=_BoomClient, now=_NOW,
    )
    assert code == 2
    payload = json.loads(buf.getvalue())
    assert payload["verdict"] == "REFUSED"
    assert payload["code"] == "PROVISION_MISSING"


# ---------------------------------------------------------------------------
# 26. N12 — stronger C1 page evidence (comparison only; nothing stored)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_c1_requires_url_membership_in_list_pages(vendor):
    harness = core.build_hermetic_harness(vendor)
    # Non-empty, but never contains the just-navigated url — a bare
    # truthiness check on `pages` would incorrectly still pass this.
    harness["navigator"].list_pages = lambda port: ["http://127.0.0.1:1/decoy-page-not-navigated"]
    receipts = core.run_matrix(**harness)
    c1 = next(r for r in receipts["rows"] if r["row"] == "C1")
    assert c1["ok"] is False
    assert receipts["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# 27. N11 — refuse-closed on non-HTTPError transport exceptions
# ---------------------------------------------------------------------------


def test_hostile_multilogin_start_refuses_closed_on_non_http_error():
    class _BoomTransport:
        def _mlx_profile_search(self, *args, **kwargs):
            raise RuntimeError("dynamic transport failure carrying private data")

    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), _BoomTransport())
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p", "folder_id": "f"})
    assert exc_info.value.code == "VENDOR_ERROR"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_hostile_gologin_profile_exists_is_unsupported_without_http():
    client = vendors.GoLoginClient(core.Credential("cred", "stdin"))
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.profile_exists({"profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa"})
    assert exc_info.value.code == "UNSUPPORTED_SURFACE"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


class _C6BoomVendorFake(core.HermeticVendorFake):
    """Crashes with a plain (non-CanaryRefusal) exception when C6 probes the
    deliberately-unknown profile id — every other call behaves normally."""

    def profile_exists(self, profile_ref):
        if profile_ref.get("profile_id") == core.UNKNOWN_PROFILE_IDS[self.vendor]:
            raise RuntimeError("simulated vendor crash on unknown-profile probe")
        return super().profile_exists(profile_ref)


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_run_matrix_c6_survives_non_canary_vendor_crash(vendor):
    harness = _harness(vendor, vendor_cls=_C6BoomVendorFake)
    receipts = core.run_matrix(**harness)
    row_ids = [row["row"] for row in receipts["rows"]]
    assert row_ids == list(core._ROW_ORDER)
    c6 = next(r for r in receipts["rows"] if r["row"] == "C6")
    assert c6["code"] == "VENDOR_ERROR"
    assert c6["ok"] is False
    assert receipts["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# 28. N15 — cheap correctness hardening (assert -O stripping, reserved keys)
# ---------------------------------------------------------------------------


def test_falsifier_no_assert_statements_strippable_by_dash_o():
    """`python -O` strips every `assert`; a load-bearing invariant must use
    an explicit `if ...: raise` instead. Scans the WHOLE core module, not
    just the two named invariants, so this also guards against regression."""
    tree = ast.parse(CORE_PATH.read_text(encoding="utf-8"), filename=str(CORE_PATH))
    assert_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    assert assert_nodes == []


def test_hostile_build_row_rejects_reserved_extra_key():
    for reserved in ("row", "code", "ok", "detail", "ts"):
        with pytest.raises(RuntimeError):
            core._build_row("C0", "OK", True, "ts-value", **{reserved: "smuggled"})
    # Sanity: a legitimate extra key still works.
    row = core._build_row("C0", "OK", True, "ts-value", provision_digest="abc")
    assert row["provision_digest"] == "abc"
    assert row["row"] == "C0"


# ---------------------------------------------------------------------------
# 29. SOL blocker 1 — split secret boundary and pre-secret refusals
# ---------------------------------------------------------------------------


def test_hostile_model_visible_coordinator_live_mode_never_preflights_or_reads_secret(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("model-visible live coordinator must not load a provision")

    monkeypatch.setattr(core, "load_provision", _boom)
    buf = io.StringIO()
    code = core.main(["--vendor", "multilogin", "--provision-path", "/private/path"], stdout=buf)
    assert code == 2
    payload = json.loads(buf.getvalue())
    assert payload["code"] == "UNSUPPORTED_SURFACE"


def test_hostile_bindings_unavailable_prevents_keychain_http_origin_and_launch(tmp_path):
    path = _write_provision(tmp_path, _valid_provision("multilogin"))
    calls = {"keychain_spawn": 0, "client": 0, "origin": 0}

    def _credential_stream_factory():
        calls["keychain_spawn"] += 1
        raise AssertionError("binding refusal must precede Keychain spawn")

    def _client_factory():
        calls["client"] += 1
        raise AssertionError("binding refusal must precede HTTP construction")

    def _origin_factory(*args, **kwargs):
        calls["origin"] += 1
        raise AssertionError("binding refusal must precede origin/browser construction")

    buf = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["--vendor", "multilogin", "--provision-path", str(path)],
        stdout=buf, bindings_loader=lambda: (None, []),
        environment_loader=_environment_loader_for(_valid_provision("multilogin")),
        credential_stream_factory=_credential_stream_factory,
        client_factory=_client_factory, origin_factory=_origin_factory, now=_NOW,
    )
    assert code == 2
    assert json.loads(buf.getvalue())["code"] == "BINDINGS_UNAVAILABLE"
    assert calls == {"keychain_spawn": 0, "client": 0, "origin": 0}


def test_non_mimic_provision_refuses_after_census_but_before_origin_keychain_or_http(tmp_path):
    """The trusted census is acquired first, while the Mimic gate still precedes secrets."""
    provision = _valid_provision("multilogin", browser_type="stealthfox")
    path = _write_provision(tmp_path, provision)
    calls = []
    def _environment():
        calls.append("environment")
        return _environment_loader_for(provision)()

    boom = lambda *args, **kwargs: calls.append("unexpected")
    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["configure-canary-port", "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment,
        origin_factory=boom,
        credential_stream_factory=boom,
        client_factory=boom,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == "UNSUPPORTED_PORT_STATE"
    assert calls == ["environment"]


@pytest.mark.parametrize(
    ("environment", "expected"),
    (
        ("missing", "PROFILE_NOT_FOUND"),
        ("running", "BINDINGS_UNAVAILABLE"),
    ),
)
def test_local_disposable_census_refuses_before_origin_keychain_or_http(
    tmp_path, environment, expected,
):
    """Catches reading secrets before the local exact-profile stopped proof."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    calls = []
    if environment == "running":
        environment_loader = _environment_loader_for(provision, running=True)
    else:
        current = _realm1_environment(provision)
        current["multilogin"].clear()
        environment_loader = lambda: current

    def unexpected(*args, **kwargs):
        calls.append("unexpected")
        raise AssertionError("local refusal must precede origin, Keychain, and HTTP")

    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["run", "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=environment_loader,
        origin_factory=unexpected,
        credential_stream_factory=unexpected,
        client_factory=unexpected,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == expected
    assert calls == []


def test_busy_fixed_port_refuses_before_keychain_or_http(tmp_path):
    """Catches secret/vendor access before the fixed loopback port is proven."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    calls = []

    def busy_origin(*, token):
        calls.append("origin")
        raise OSError("synthetic busy port")

    buf = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["--vendor", "multilogin", "--provision-path", str(path)],
        stdout=buf,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        origin_factory=busy_origin,
        credential_stream_factory=lambda: calls.append("keychain"),
        client_factory=lambda: calls.append("client"),
        now=_NOW,
    )
    assert code == 2
    assert json.loads(buf.getvalue())["code"] == "CANARY_PORT_UNAVAILABLE"
    assert calls == ["origin"]


def test_hostile_gologin_helper_refuses_before_any_io():
    buf = io.StringIO()
    code = vendors.main(
        ["--vendor", "gologin", "--provision-path", "/definitely/not/read"],
        stdout=buf,
        bindings_loader=lambda: (_ for _ in ()).throw(AssertionError("must not load bindings")),
        credential_stream_factory=lambda: (_ for _ in ()).throw(AssertionError("must not spawn Keychain")),
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not make HTTP")),
        now=_NOW,
    )
    assert code == 2
    assert json.loads(buf.getvalue())["code"] == "UNSUPPORTED_SURFACE"


# ---------------------------------------------------------------------------
# 30. SOL blocker 2 — one hostile-environment-proof HTTP boundary
# ---------------------------------------------------------------------------


def test_mutation_bounded_client_disables_ambient_proxy_and_redirects(monkeypatch):
    captured = {}
    proxy_recorder = []
    direct_recorder = []

    class _Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @staticmethod
        def iter_bytes():
            return (b"{}",)

    class _ConstructedClient:
        def __init__(self, trust_env):
            self._trust_env = trust_env

        def stream(self, method, url, *, headers=None, **kwargs):
            target = direct_recorder if self._trust_env is False else proxy_recorder
            target.append({"method": method, "url": url, "headers": dict(headers or {})})
            return _Response()

        def close(self):
            return None

    def _factory(**kwargs):
        captured.update(kwargs)
        return _ConstructedClient(kwargs.get("trust_env"))

    poison = "http://127.0.0.1:1/poison-recorder"
    monkeypatch.setenv("HTTPS_PROXY", poison)
    monkeypatch.setenv("HTTP_PROXY", poison)
    monkeypatch.setenv("ALL_PROXY", poison)
    monkeypatch.setattr(vendors.httpx, "Client", _factory)
    client = vendors.BoundedHttpClient()
    try:
        response = client._mlx_profile_status(
            core.Credential("synthetic-proxy-falsifier", "stdin"), "profile",
        )
        assert response is not None
        assert captured["trust_env"] is False
        assert captured["follow_redirects"] is False
        assert isinstance(captured["timeout"], httpx.Timeout)
        assert captured["limits"].max_connections == 1
    finally:
        client.close()
    assert proxy_recorder == []
    assert len(direct_recorder) == 1
    assert direct_recorder[0]["headers"]["Authorization"] == "Bearer synthetic-proxy-falsifier"


def test_hostile_bounded_client_only_emits_frozen_methods_origins_and_paths():
    seen = []

    def _handler(request):
        seen.append((
            request.method,
            str(request.url.copy_with(query=None)),
            request.read(),
        ))
        return httpx.Response(200, json={})

    inner = httpx.Client(
        transport=httpx.MockTransport(_handler), trust_env=False, follow_redirects=False,
    )
    client = vendors.BoundedHttpClient(client=inner)
    credential = core.Credential("synthetic-credential", "stdin")
    try:
        client._mlx_profile_search(credential, "folder", offset=0)
        client._mlx_profile_status(credential, "profile")
        client._mlx_profile_start(credential, "folder", "profile")
        client._mlx_profile_stop(credential, "profile")
        client._webdriver_create_session(9222, "mimic")
        client._webdriver_window_handles(9222, "session-1")
        client._webdriver_current_window(9222, "session-1")
        client._webdriver_switch_window(9222, "session-1", "window-1")
        client._webdriver_navigate(9222, "session-1", "http://127.0.0.1:7777/a")
        client._webdriver_current_url(9222, "session-1")
        # A port-shaped authority injection must refuse before URL parsing;
        # otherwise ``127.0.0.1:9222@evil`` would resolve to a non-loopback host.
        assert client._webdriver_create_session("9222@evil.example", "mimic") is None
    finally:
        client.close()

    assert [(method, url) for method, url, _body in seen] == [
        ("POST", "https://api.multilogin.com/profile/search"),
        ("GET", "https://launcher.mlx.yt:45001/api/v1/profile/status/p/profile"),
        ("GET", "https://launcher.mlx.yt:45001/api/v2/profile/f/folder/p/profile/start"),
        ("GET", "https://launcher.mlx.yt:45001/api/v1/profile/stop/p/profile"),
        ("POST", "http://127.0.0.1:9222/session"),
        ("GET", "http://127.0.0.1:9222/session/session-1/window/handles"),
        ("GET", "http://127.0.0.1:9222/session/session-1/window"),
        ("POST", "http://127.0.0.1:9222/session/session-1/window"),
        ("POST", "http://127.0.0.1:9222/session/session-1/url"),
        ("GET", "http://127.0.0.1:9222/session/session-1/url"),
    ]
    assert json.loads(seen[0][2]) == {
        "folder_id": "folder",
        "is_removed": False,
        "limit": vendors._PROFILE_PAGE_SIZE,
        "offset": 0,
        "order_by": "created_at",
        "search_text": "",
        "sort": "asc",
        "storage_type": "all",
    }
    public = {
        name for name in dir(vendors.BoundedHttpClient)
        if not name.startswith("_") and callable(getattr(vendors.BoundedHttpClient, name))
    }
    assert public == {"close"}

    source = VENDORS_PATH.read_text(encoding="utf-8")
    assert re.search(r"\bhttpx\.(get|put|post|patch|delete|request|stream)\s*\(", source) is None


def test_hostile_bounded_client_caps_body_and_launders_transport_errors():
    oversized = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * (vendors._MAX_RESPONSE_BYTES + 1)),
        ),
        trust_env=False,
    )
    bounded = vendors.BoundedHttpClient(client=oversized)
    try:
        assert bounded._webdriver_create_session(9222, "mimic") is None
    finally:
        bounded.close()

    def _boom(request):
        raise RuntimeError("private response or proxy recorder payload")

    failing = httpx.Client(transport=httpx.MockTransport(_boom), trust_env=False)
    bounded = vendors.BoundedHttpClient(client=failing)
    try:
        result = bounded._webdriver_create_session(9222, "mimic")
    finally:
        bounded.close()
    assert result is None
    assert "private response" not in repr(result)


def test_hostile_multilogin_inventory_paginates_below_transport_response_cap():
    total = 28
    seen = []

    def _handler(request):
        body = json.loads(request.read())
        offset = body["offset"]
        limit = body["limit"]
        seen.append((offset, limit))
        profiles = [
            {
                "id": f"profile-{index}",
                "folder_id": body["folder_id"],
                # Ten rows fit below the independent 64 KiB response cap;
                # one unpaginated 28-row response does not.
                "bounded_metadata": "x" * 4096,
            }
            for index in range(offset, min(offset + limit, total))
        ]
        return httpx.Response(200, json={
            "status": {
                "error_code": "",
                "http_code": 200,
                "message": "Search profile successfully result",
            },
            "data": {"profiles": profiles, "total_count": total},
        })

    inner = httpx.Client(transport=httpx.MockTransport(_handler), trust_env=False)
    bounded = vendors.BoundedHttpClient(client=inner)
    client = vendors.MultiloginClient(core.Credential("synthetic", "stdin"), bounded)
    try:
        assert client.profile_exists({"profile_id": "absent", "folder_id": "folder"}) is False
    finally:
        bounded.close()

    assert seen == [(0, 10), (10, 10), (20, 10)]


def test_hostile_webdriver_rejects_external_url_before_transport():
    class _Recorder:
        def __init__(self):
            self.calls = []

        def _webdriver_create_session(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return vendors._BoundedResponse(200, {})

        def _webdriver_navigate(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return vendors._BoundedResponse(200, {})

    transport = _Recorder()
    provision = _valid_provision("multilogin")
    navigator = vendors.WebDriverNavigator(transport, provision)
    assert navigator.open_url(9222, "https://chatgpt.com/") is False
    assert navigator.open_url(70000, provision["benign_origin"] + "/a") is False
    assert transport.calls == []


# ---------------------------------------------------------------------------
# 31. SOL blocker 3 — exact Multilogin response/state contract
# ---------------------------------------------------------------------------


_MLX_TRANSITIONAL_OR_ERROR_STATES = (
    "download_browser_profile_metadata",
    "download_browser_profile_data",
    "download_browser_core",
    "download_finished",
    "download_meta_error",
    "download_data_error",
    "download_core_error",
    "download_meta_finished",
    "download_data_finished",
    "download_core_finished",
    "validate_proxy",
    "validate_proxy_error",
    "start_browser",
    "start_browser_error",
    "closed",
    "running",
    "already stopped",
    "already running with changed wording",
)


@pytest.mark.parametrize("mutated_state", _MLX_TRANSITIONAL_OR_ERROR_STATES)
def test_mutation_multilogin_nonterminal_or_renamed_state_refuses_before_start(mutated_state):
    transport = _ExactMultiloginTransport()
    transport.status_response = _success({
        "profile_id": "p1", "folder_id": "f1", "status": mutated_state,
    })
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"
    assert not any(call[0] == "start" for call in transport.calls)


@pytest.mark.parametrize(
    "payload,status_code",
    [
        ({"status": {"error_code": "", "http_code": 200, "message": ""},
          "data": {"profile_id": "p1", "folder_id": "f1", "active": False}}, 200),
        ({"status": {"error_code": "", "http_code": 200, "message": ""},
          "data": {"profile_id": "p1", "folder_id": "f1", "profile_status": "stopped"}}, 200),
        ({"status": {"error_code": "", "http_code": 200, "message": ""},
          "data": {"profile_id": "wrong", "folder_id": "f1", "status": "stopped"}}, 200),
        ({"status": {"error_code": "", "http_code": 200, "message": ""},
          "data": {"profile_id": "p1", "folder_id": "wrong", "status": "stopped"}}, 200),
        ({"result": {"profile_id": "p1", "folder_id": "f1", "status": "stopped"}}, 200),
        ({"status": {"error_code": "", "http_code": 200, "message": "", "renamed": True},
          "data": {"profile_id": "p1", "folder_id": "f1", "status": "stopped"}}, 200),
        ({"status": {"error_code": "", "http_code": 200, "message": ""},
          "data": {"profile_id": "p1", "folder_id": "f1", "status": "stopped",
                   "unexpected_state_alias": "closed"}}, 200),
        ({"status": {"error_code": "ERR", "http_code": 200, "message": ""},
          "data": {"profile_id": "p1", "folder_id": "f1", "status": "stopped"}}, 200),
        ({"status": {"error_code": "", "http_code": 200, "message": ""},
          "data": {"profile_id": "p1", "folder_id": "f1", "status": "stopped"}}, 404),
    ],
)
def test_mutation_multilogin_missing_malformed_renamed_or_agent_lost_status_refuses(payload, status_code):
    transport = _ExactMultiloginTransport()
    transport.status_response = vendors._BoundedResponse(status_code, payload)
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"
    assert not any(call[0] == "start" for call in transport.calls)


def test_hostile_multilogin_exact_running_refuses_busy_before_start():
    transport = _ExactMultiloginTransport()
    transport.state = "browser_running"
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "BUSY_PROFILE"
    assert not any(call[0] == "start" for call in transport.calls)


def test_mutation_multilogin_mismatched_stealthfox_refuses_before_selenium_start():
    transport = _ExactMultiloginTransport()
    payload = transport._mlx_profile_status(None, "p1").payload
    payload["data"]["browser_type"] = "stealthfox"
    transport.calls.clear()
    transport.status_response = vendors._BoundedResponse(200, payload)
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"
    assert not any(call[0] == "start" for call in transport.calls)


def test_mutation_multilogin_cloud_stealthfox_refuses_before_status_or_start():
    class _CloudStealthfoxTransport(_ExactMultiloginTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            self.calls.append(("search", folder_id, offset))
            return _success({
                "profiles": [{
                    "id": "p1", "folder_id": folder_id, "name": "synthetic",
                    "browser_type": "stealthfox", "in_use_by": "", "locked_by": "",
                }],
                "total_count": 1,
            }, "Search profile successfully result")

    transport = _CloudStealthfoxTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"
    assert [call[0] for call in transport.calls] == ["search"]


def test_mutation_multilogin_start_prose_cannot_replace_exact_success_contract():
    class _AlreadyTransport(_ExactMultiloginTransport):
        def _mlx_profile_start(self, credential, folder_id, profile_id):
            self.calls.append(("start", folder_id, profile_id))
            return _success({
                "id": profile_id, "port": "9222", "browser_type": "mimic",
                "core_version": 132, "is_quick": False,
            }, "Profile launch accepted")

    transport = _AlreadyTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"


def test_contract_multilogin_search_accepts_success_prose_drift_only():
    class _SearchProseDriftTransport(_ExactMultiloginTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            self.calls.append(("search", folder_id, offset))
            return _success({
                "profiles": [{
                    "id": "p1", "folder_id": folder_id, "name": "synthetic",
                    "browser_type": "mimic", "in_use_by": "", "locked_by": "",
                }],
                "total_count": 1,
            }, "Synthetic changed success prose")

    transport = _SearchProseDriftTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    assert client.profile_exists({"profile_id": "p1", "folder_id": "f1"}) is True
    assert [call[0] for call in transport.calls] == ["search"]


@pytest.mark.parametrize("message", (None, 200, True, []))
def test_mutation_multilogin_search_message_must_remain_a_string(message):
    class _MalformedSearchMessageTransport(_ExactMultiloginTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            response = _success({
                "profiles": [{
                    "id": "p1", "folder_id": folder_id, "name": "synthetic",
                    "browser_type": "mimic", "in_use_by": "", "locked_by": "",
                }],
                "total_count": 1,
            })
            response.payload["status"]["message"] = message
            return response

    client = vendors.MultiloginClient(
        core.Credential("cred", "stdin"), _MalformedSearchMessageTransport(),
    )
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.profile_exists({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"


@pytest.mark.parametrize(
    "error_code,http_code",
    (("ERR", 200), ("", 201), ("", "200"), (None, 200)),
)
def test_mutation_multilogin_search_success_codes_remain_exact(error_code, http_code):
    class _MalformedSearchStatusTransport(_ExactMultiloginTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            response = _success({"profiles": [], "total_count": 0})
            response.payload["status"]["error_code"] = error_code
            response.payload["status"]["http_code"] = http_code
            return response

    client = vendors.MultiloginClient(
        core.Credential("cred", "stdin"), _MalformedSearchStatusTransport(),
    )
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.profile_exists({"profile_id": "absent", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"


@pytest.mark.parametrize(
    "ownership_field,ownership_value,expected_code",
    [
        ("in_use_by", None, "VENDOR_ERROR"),
        ("in_use_by", "other-agent-session", "BUSY_PROFILE"),
        ("locked_by", "other-agent-session", "BUSY_PROFILE"),
    ],
)
def test_mutation_multilogin_ownership_uncertainty_or_conflict_refuses_before_start(
    ownership_field, ownership_value, expected_code,
):
    class _OwnershipTransport(_ExactMultiloginTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            item = {
                "id": "p1", "folder_id": folder_id, "name": "synthetic",
                "browser_type": "mimic", "in_use_by": "", "locked_by": "",
            }
            if ownership_value is None:
                item.pop(ownership_field)
            else:
                item[ownership_field] = ownership_value
            self.calls.append(("search", folder_id, offset))
            return _success(
                {"profiles": [item], "total_count": 1},
                "Search profile successfully result",
            )

    transport = _OwnershipTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p1", "folder_id": "f1"})
    assert exc_info.value.code == expected_code
    assert not any(call[0] in ("status", "start") for call in transport.calls)


def test_hostile_multilogin_absent_profile_requires_complete_bounded_census():
    class _PagingTransport:
        def __init__(self):
            self.offsets = []

        def _mlx_profile_search(self, credential, folder_id, *, offset):
            self.offsets.append(offset)
            page = {
                0: [
                    {"id": "one", "folder_id": folder_id, "in_use_by": ""},
                    {"id": "two", "folder_id": folder_id, "in_use_by": ""},
                ],
                2: [{"id": "three", "folder_id": folder_id, "in_use_by": ""}],
            }[offset]
            return _success(
                {"profiles": page, "total_count": 3},
                "Search profile successfully result",
            )

    transport = _PagingTransport()
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), transport)
    assert client.profile_exists({"profile_id": "absent", "folder_id": "f1"}) is False
    assert transport.offsets == [0, 2]


def test_mutation_multilogin_truncated_census_refuses_not_absent():
    class _TruncatedTransport:
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            return _success(
                {"profiles": [], "total_count": 1},
                "Search profile successfully result",
            )

    client = vendors.MultiloginClient(core.Credential("cred", "stdin"), _TruncatedTransport())
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.profile_exists({"profile_id": "absent", "folder_id": "f1"})
    assert exc_info.value.code == "VENDOR_ERROR"


# ---------------------------------------------------------------------------
# 32. SOL blocker 4 — affirmative current three-seat collision census
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutation", ("one-seat", "stale", "future", "missing-observed", "renamed-seat", "four-seats", "conflict"))
def test_mutation_incomplete_stale_or_conflicting_binding_census_refuses(tmp_path, mutation):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    doc = _binding_doc()
    if mutation == "one-seat":
        doc["bindings"] = doc["bindings"][:1]
    elif mutation == "stale":
        for binding in doc["bindings"]:
            binding["observed_at"] = "2026-08-21T00:00:00Z"
    elif mutation == "future":
        doc["bindings"][0]["observed_at"] = "2026-08-24T00:00:00Z"
    elif mutation == "missing-observed":
        doc["bindings"][0]["observed_at"] = "not-a-timestamp"
    elif mutation == "renamed-seat":
        doc["bindings"][0]["seat_ref"] = "chatgpt-seat-1"
    elif mutation == "four-seats":
        extra = copy.deepcopy(doc["bindings"][0])
        extra["binding_id"] = "synthetic-extra-binding"
        extra["seat_ref"] = "chatgpt4"
        extra["locator"]["profile_id"] = "444444444444444444444444"
        doc["bindings"].append(extra)
    elif mutation == "conflict":
        conflict = copy.deepcopy(doc["bindings"][0])
        conflict["binding_id"] = "synthetic-conflicting-binding"
        conflict["locator"]["profile_id"] = "999999999999999999999999"
        doc["bindings"].append(conflict)

    loaded, code = _load_provision(str(path), bindings_loader=lambda: (doc, []))
    assert loaded is None
    assert code == "BINDINGS_UNAVAILABLE"


def test_hostile_binding_census_safety_window_boundary_is_inclusive(tmp_path):
    path = _write_provision(tmp_path, _valid_provision("multilogin"))
    doc = _binding_doc()
    boundary = "2026-08-22T12:00:00Z"
    for binding in doc["bindings"]:
        binding["observed_at"] = boundary
    loaded, code = _load_provision(str(path), bindings_loader=lambda: (doc, []))
    assert code is None
    assert loaded is not None


def test_falsifier_binding_result_code_is_closed_and_receipt_safe():
    assert "BINDINGS_UNAVAILABLE" in core.RESULT_CODES
    assert set(core.DETAILS) == set(core.RESULT_CODES)
    detail = core.DETAILS["BINDINGS_UNAVAILABLE"]
    assert "://" not in detail
    assert "profile_id" not in detail


# ---------------------------------------------------------------------------
# REALM1-C1 — MAS-115 one-profile Multilogin peer create/reconcile/remove
#
# Discriminators reference Mastermind issue #385. Every test here is
# hermetic: no real network, Keychain, or browser is ever touched.
# ---------------------------------------------------------------------------

_PEER_FOLDER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
_PEER_ANCHOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _peer_name() -> str:
    return vendors.peer_profile_name(_PEER_FOLDER, _PEER_ANCHOR)


_PEER_CREATED_UUID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
_PEER_ALT_UUID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
_PEER_OTHER_UUID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def _peer_record(peer_name, **overrides):
    record = {
        "id": _PEER_CREATED_UUID,
        "folder_id": _PEER_FOLDER,
        "name": peer_name,
        "browser_type": "mimic",
        "os_type": "macos",
        "in_use_by": "",
    }
    record.update(overrides)
    return record


def _peer_create_success(profile_id=_PEER_CREATED_UUID, *, status_code=201):
    return vendors._BoundedResponse(status_code, {
        "status": {"error_code": "", "http_code": status_code, "message": "Profile successfully created"},
        "data": {"ids": [profile_id]},
    })


def _peer_remove_success():
    return vendors._BoundedResponse(200, {
        "status": {"error_code": "", "http_code": 200, "message": "Profile successfully removed"},
        "data": None,
    })


class _PeerTransport:
    """Fake ``BoundedHttpClient`` surface for peer create/remove tests.

    ``set_candidates_sequence`` takes one full-profiles-list per successive
    call to :meth:`MultiloginClient.peer_candidates` (the before-census, the
    after-census, and so on) so a test can express "zero, then one" or
    "one, then zero" without any real pagination server.
    """

    def __init__(self):
        self.calls = []
        self.search_rounds = [[]]
        self._search_round = -1
        self.status_by_id = {}
        # The launcher status envelope is folder-checked by the client, so the
        # fake must answer for the folder actually being censused rather than
        # a hardcoded one -- otherwise a "stopped" proof silently degrades
        # into a folder mismatch and the happy path passes for the wrong
        # reason.
        self.folder_id = _PEER_FOLDER
        self.create_response = None
        self.create_raises = False
        self.remove_response = None
        self.remove_raises = False

    def set_candidates_sequence(self, *rounds):
        self.search_rounds = list(rounds)

    def _mlx_profile_search(self, credential, folder_id, *, offset):
        if offset == 0:
            self._search_round += 1
        profiles = self.search_rounds[min(self._search_round, len(self.search_rounds) - 1)]
        self.folder_id = folder_id
        self.calls.append(("search", folder_id, offset))
        page = profiles[offset:offset + vendors._PROFILE_PAGE_SIZE]
        return vendors._BoundedResponse(200, {
            "status": {"error_code": "", "http_code": 200, "message": "Search profile successfully result"},
            "data": {"profiles": page, "total_count": len(profiles)},
        })

    def _mlx_profile_status(self, credential, profile_id):
        self.calls.append(("status", profile_id))
        state = self.status_by_id.get(profile_id, "stopped")
        if isinstance(state, vendors._BoundedResponse):
            return state
        return vendors._BoundedResponse(200, {
            "status": {"error_code": "", "http_code": 200, "message": ""},
            "data": {
                "profile_id": profile_id, "folder_id": self.folder_id, "status": state,
                "browser_type": "mimic", "core_version": 132,
                "in_use_by": "" if state == "stopped" else "synthetic-owner",
                "is_quick": False, "last_launched_at": "2026-08-23T00:00:00Z",
                "last_launched_by": "op", "last_launched_on": "machine",
                "message": "", "name": "synthetic", "timestamp": 1787472000000,
                "workspace_id": "workspace",
            },
        })

    def _mlx_profile_create(self, credential, folder_id, name):
        self.calls.append(("create", folder_id, name))
        if self.create_raises:
            raise RuntimeError("synthetic create transport failure")
        return self.create_response

    def _mlx_profile_remove(self, credential, profile_id):
        self.calls.append(("remove", profile_id))
        if self.remove_raises:
            raise RuntimeError("synthetic remove transport failure")
        return self.remove_response

    def close(self):
        self.calls.append(("close",))


def _peer_client(transport, *, credential=None):
    return vendors.MultiloginClient(credential or core.Credential("cred", "stdin"), transport)


def _committing_intent():
    """A ``commit_intent`` fake that always succeeds, like a real first commit."""
    calls = []

    def _commit():
        calls.append(True)
        return vendors.CREATED_THIS_CALL

    _commit.calls = calls
    return _commit


def _refusing_intent():
    calls = []

    def _commit():
        calls.append(True)
        return vendors.REFUSED

    _commit.calls = calls
    return _commit


def _authorized_peer_main(argv, **kwargs):
    """Exercise the opaque coordinator seam, never the now-inert public CLI."""
    operation, *rest = argv
    if "peer_intent_path" not in kwargs or "peer_provision_path" not in kwargs:
        anchor_index = rest.index("--provision-path") + 1
        test_parent = Path(rest[anchor_index]).parent
        kwargs.setdefault("peer_intent_path", test_parent / "peer-state.json")
        kwargs.setdefault("peer_provision_path", test_parent / "peer-profile.json")
    if operation == "create-peer-profile":
        return vendors._run_coordinator_peer_create(rest, **kwargs)  # noqa: SLF001
    if operation == "rollback-peer-profile":
        return vendors._run_coordinator_peer_rollback(rest, **kwargs)  # noqa: SLF001
    raise AssertionError(f"not a peer operation: {operation}")


def _prepare_peer_lifecycle(provision, state_path, peer_provision_path):
    outcome = vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=vendors.peer_profile_name(
            provision["folder_id"], provision["profile_id"],
        ),
        peer_provision_path=peer_provision_path,
    )
    assert outcome in (vendors.CREATED_THIS_CALL, vendors.EXISTING_EXACT)


# --- #385-1: the seams exist and are closed --------------------------------


def test_peer_d1_create_remove_seams_are_closed_frozen_calls():
    """#385-1: only fixed folder_id/name (create) or profile_id (remove) ever
    reach the transport; no caller-supplied URL/method/body/count exists."""
    seen = []

    def _handler(request):
        seen.append((
            request.method, str(request.url),
            json.loads(request.read()) if request.content else None,
        ))
        return httpx.Response(200, json={})

    inner = httpx.Client(
        transport=httpx.MockTransport(_handler), trust_env=False, follow_redirects=False,
    )
    client = vendors.BoundedHttpClient(client=inner)
    credential = core.Credential("synthetic-credential", "stdin")
    try:
        client._mlx_profile_create(credential, "folder-x", "name-x")
        client._mlx_profile_remove(credential, "profile-x")
    finally:
        client.close()
    assert [(m, u) for m, u, _ in seen] == [
        ("POST", "https://api.multilogin.com/profile/create"),
        ("POST", "https://api.multilogin.com/profile/remove"),
    ]
    assert seen[0][2] == {
        "name": "name-x",
        "browser_type": "mimic",
        "os_type": "macos",
        "folder_id": "folder-x",
        "times": 1,
        "parameters": {
            "flags": {"ports_masking": "mask", "proxy_masking": "disabled"},
            "storage": {"is_local": True, "save_service_worker": True},
            "fingerprint": {},
        },
    }
    assert seen[1][2] == {"ids": ["profile-x"], "permanently": False}
    public = {
        name for name in dir(vendors.BoundedHttpClient)
        if not name.startswith("_") and callable(getattr(vendors.BoundedHttpClient, name))
    }
    assert public == {"close"}


# --- #385-2: pre-secret failures prove Keychain/HTTP never reached ---------


@pytest.mark.parametrize("operation", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_d2_bad_anchor_provision_refuses_before_keychain_or_http(tmp_path, operation):
    path = tmp_path / "missing-provision.json"
    out = io.StringIO()
    code = _authorized_peer_main(
        [operation, "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=lambda: (_ for _ in ()).throw(
            AssertionError("must not read the local environment before a valid anchor provision"),
        ),
        credential_stream_factory=lambda: (_ for _ in ()).throw(
            AssertionError("must not read Keychain before a valid anchor provision"),
        ),
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not build a vendor client")),
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == "PROVISION_MISSING"


@pytest.mark.parametrize("operation", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_d2_running_anchor_profile_refuses_before_keychain_or_http(tmp_path, operation):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    if operation == "create-peer-profile":
        _prepare_peer_lifecycle(
            provision, tmp_path / "peer-state.json", tmp_path / "peer-profile.json",
        )
    out = io.StringIO()
    code = _authorized_peer_main(
        [operation, "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision, running=True),
        credential_stream_factory=lambda: (_ for _ in ()).throw(AssertionError("must not read Keychain")),
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not build a vendor client")),
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == (
        "BINDINGS_UNAVAILABLE"
        if operation == "create-peer-profile" else "PROVISION_MISSING"
    )


@pytest.mark.parametrize("operation", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_d2_stale_bindings_refuse_before_keychain_or_http(tmp_path, operation):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    if operation == "create-peer-profile":
        _prepare_peer_lifecycle(
            provision, tmp_path / "peer-state.json", tmp_path / "peer-profile.json",
        )
    out = io.StringIO()
    code = _authorized_peer_main(
        [operation, "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=lambda: (None, ["stale"]),
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: (_ for _ in ()).throw(AssertionError("must not read Keychain")),
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not build a vendor client")),
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == (
        "BINDINGS_UNAVAILABLE" if operation == "create-peer-profile" else "PROVISION_MISSING"
    )


def test_peer_d2_new_operations_never_bind_or_self_test_loopback_origin(tmp_path):
    """#385-2 (loopback carve-out): these operations never launch a browser,
    so the fixed-port origin must never be bound or self-tested."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, folder_id=provision["folder_id"])])
    transport.create_response = _peer_create_success()
    _prepare_peer_lifecycle(
        provision, tmp_path / "intent.json", tmp_path / "peer.json",
    )

    origin_calls = []

    def _tracking_origin(*args, **kwargs):
        origin_calls.append(1)
        raise AssertionError("create/rollback must never bind the loopback origin")

    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
        ],
        peer_intent_path=str(tmp_path / "intent.json"),
        peer_provision_path=str(tmp_path / "peer.json"),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_tracking_origin,
        now=_NOW,
    )
    assert origin_calls == []
    assert code == 0
    assert json.loads(out.getvalue())["verdict"] == "PASS"


# --- #385-3: caller cannot widen the create body ---------------------------


def test_peer_d3_create_body_is_frozen_and_times_is_always_one():
    observed = []

    def _handler(request):
        observed.append(json.loads(request.read()))
        return httpx.Response(201, json={
            "status": {"error_code": "", "http_code": 201, "message": "Profile successfully created"},
            "data": {"ids": ["ignored"]},
        })

    inner = httpx.Client(transport=httpx.MockTransport(_handler), trust_env=False, follow_redirects=False)
    bounded = vendors.BoundedHttpClient(client=inner)
    try:
        bounded._mlx_profile_create(core.Credential("secret", "stdin"), "attacker-folder", "attacker-name")
    finally:
        bounded.close()
    assert observed == [{
        "name": "attacker-name",
        "browser_type": "mimic",
        "os_type": "macos",
        "folder_id": "attacker-folder",
        "times": 1,
        "parameters": {
            "flags": {"ports_masking": "mask", "proxy_masking": "disabled"},
            "storage": {"is_local": True, "save_service_worker": True},
            "fingerprint": {},
        },
    }]
    # No proxy, custom_start_urls, notes, tags, or fingerprint values exist
    # anywhere in the emitted body.
    for forbidden in ("proxy", "custom_start_urls", "notes", "tags", "core_version"):
        assert forbidden not in observed[0]
        assert forbidden not in observed[0]["parameters"]


# --- #385-4: zero candidates -> one create -> exact readback -> PASS ------


def test_peer_d4_zero_candidates_creates_reads_back_and_writes_provision(tmp_path):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, folder_id=provision["folder_id"])])
    transport.create_response = _peer_create_success()
    peer_provision_path = tmp_path / "peer_provision.json"
    peer_intent_path = tmp_path / "peer_intent.json"
    _prepare_peer_lifecycle(provision, peer_intent_path, peer_provision_path)

    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
        ],
        peer_intent_path=str(peer_intent_path),
        peer_provision_path=str(peer_provision_path),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    receipt = json.loads(out.getvalue())
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert receipt["effect"] == "PROVISION_WRITTEN"
    # profile_B is only publishable once the read-back positively proved the
    # exact profile stopped; PASS must never be reachable without it.
    assert receipt["predicates"]["stopped_proven"] is True
    assert receipt["predicates"]["exact_readback"] is True
    assert receipt["predicates"]["provision_written"] is True
    assert receipt["predicates"]["cleanup_lease_retained"] is False
    assert [c[0] for c in transport.calls].count("create") == 1
    assert peer_provision_path.exists()
    written = json.loads(peer_provision_path.read_text(encoding="utf-8"))
    assert written["vendor"] == "multilogin"
    assert written["folder_id"] == provision["folder_id"]
    assert peer_intent_path.exists()
    intent_doc = json.loads(peer_intent_path.read_text(encoding="utf-8"))
    assert intent_doc["peer_name"] == peer_name
    assert intent_doc["schema"] == vendors.PEER_INTENT_SCHEMA
    # Both private files are owner-only; neither carries a raw vendor id.
    assert stat.S_IMODE(peer_provision_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(peer_intent_path.stat().st_mode) == 0o600
    assert provision["folder_id"] not in json.dumps(intent_doc)
    assert provision["profile_id"] not in json.dumps(intent_doc)


# --- #385-5: matching committed intent -> read-only, zero create ----------


def test_peer_d5_matching_intent_and_exact_candidate_is_read_only():
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [_peer_record(peer_name)],
        [_peer_record(peer_name)],
    )
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=True, commit_intent=lambda: (_ for _ in ()).throw(
            AssertionError("must not attempt to commit a new intent when one already matches"),
        ),
        intent_reconciliation_ready=True,
    )
    assert receipt["predicates"]["dispatched"] is False
    assert receipt["predicates"]["reconciled"] is True
    assert [c[0] for c in transport.calls].count("create") == 0
    assert receipt["effect"] in ("PROFILE_STOPPED_PROVEN", "CREATE_APPLIED")


# --- #385-6: candidate exists WITHOUT matching intent -> conflict ---------


def test_peer_d6_colliding_name_without_intent_is_conflict_never_adopted():
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence([_peer_record(peer_name)])
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False,
        commit_intent=lambda: (_ for _ in ()).throw(
            AssertionError("a name collision without intent must never attempt a commit"),
        ),
    )
    assert receipt["verdict"] == "REFUSED"
    assert receipt["effect"] == "NONE"
    assert receipt["code"] == "BUSY_PROFILE"
    assert receipt["predicates"]["candidates_before"] == 1
    assert [c[0] for c in transport.calls].count("create") == 0


# --- #385-7: create response lost, exact one candidate on readback -------


def test_peer_d7_lost_create_response_with_one_readback_candidate_reconciles():
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name)])
    transport.create_response = None  # transport returns None: response lost
    client = _peer_client(transport)
    commit = _committing_intent()
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=commit,
    )
    assert receipt["effect"] in ("CREATE_APPLIED", "PROFILE_STOPPED_PROVEN")
    assert receipt["predicates"]["reconciled"] is True
    assert receipt["predicates"]["dispatched"] is True
    assert [c[0] for c in transport.calls].count("create") == 1


# --- #385-8: create response lost + zero/multiple readback candidates ----


@pytest.mark.parametrize("scenario", ("zero", "multiple"))
def test_peer_d8_lost_create_response_with_zero_or_many_candidates_is_unknown(scenario):
    peer_name = _peer_name()
    if scenario == "zero":
        after_round = []
    else:
        # Two distinct vendor records that both happen to carry the exact
        # deterministic peer name — a vendor-side collision, not something
        # this actuator could ever cause by construction.
        after_round = [
            _peer_record(peer_name, id=_PEER_ALT_UUID),
            _peer_record(peer_name, id=_PEER_OTHER_UUID),
        ]
    transport = _PeerTransport()
    transport.set_candidates_sequence([], after_round)
    transport.create_response = None
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=_committing_intent(),
    )
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert [c[0] for c in transport.calls].count("create") == 1


# --- #385-9: explicit 401/403 -> typed auth failure, zero pre-dispatch create -


@pytest.mark.parametrize("status_code", (401, 403))
def test_peer_d9_auth_rejection_during_dispatch_is_typed_and_pre_effect(status_code):
    transport = _PeerTransport()
    transport.set_candidates_sequence([])
    transport.create_response = vendors._BoundedResponse(status_code, None)
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=_committing_intent(),
    )
    assert receipt["verdict"] == "REFUSED"
    assert receipt["effect"] == "NONE"
    assert receipt["code"] == "AUTH_EXPIRED"
    assert [c[0] for c in transport.calls].count("create") == 1


@pytest.mark.parametrize("status_code", (401, 403))
def test_peer_d9_auth_rejection_during_pre_dispatch_census_emits_zero_creates(status_code):
    class _AuthBoomTransport(_PeerTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            self.calls.append(("search", folder_id, offset))
            return vendors._BoundedResponse(status_code, None)

    transport = _AuthBoomTransport()
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False,
        commit_intent=lambda: (_ for _ in ()).throw(
            AssertionError("a census auth failure must never reach commit_intent"),
        ),
    )
    assert receipt["verdict"] == "REFUSED"
    assert receipt["effect"] == "NONE"
    assert receipt["code"] == "AUTH_EXPIRED"
    assert [c[0] for c in transport.calls].count("create") == 0


# --- #385-10: hostile leak scan --------------------------------------------


def test_peer_d10_hostile_leak_scan_create_and_remove(tmp_path):
    secret_folder = "the-secret-folder-id"
    secret_profile = "the-secret-profile-id"
    peer_name = vendors.peer_profile_name(secret_folder, _PEER_ANCHOR)
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [], [_peer_record(peer_name, id=secret_profile, folder_id=secret_folder)],
    )
    transport.create_response = _peer_create_success(profile_id=secret_profile)
    client = _peer_client(transport, credential=core.Credential(_SECRET, "stdin"))
    create_receipt = client.create_peer_profile(
        folder_id=secret_folder, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=_committing_intent(),
    )
    dumped_create = json.dumps(create_receipt)
    for forbidden in (_SECRET, secret_profile, secret_folder, peer_name):
        assert forbidden not in dumped_create

    transport2 = _PeerTransport()
    transport2.set_candidates_sequence(
        [_peer_record(peer_name, id=secret_profile, folder_id=secret_folder)], [],
    )
    transport2.remove_response = _peer_remove_success()
    client2 = _peer_client(transport2, credential=core.Credential(_SECRET, "stdin"))
    remove_receipt = client2.remove_peer_profile(
        folder_id=secret_folder, anchor_profile_id=_PEER_ANCHOR,
        peer_profile_id=secret_profile,
        claim_remove=lambda: vendors.CREATED_THIS_CALL,
    )
    dumped_remove = json.dumps(remove_receipt)
    for forbidden in (_SECRET, secret_profile, secret_folder, peer_name):
        assert forbidden not in dumped_remove


def test_peer_d10_hostile_leak_scan_vendor_error_body_never_escapes():
    class _LeakyTransport(_PeerTransport):
        def _mlx_profile_create(self, credential, folder_id, name):
            self.calls.append(("create", folder_id, name))
            raise RuntimeError(_SECRET)

    transport = _LeakyTransport()
    transport.set_candidates_sequence([])
    client = _peer_client(transport, credential=core.Credential(_SECRET, "stdin"))
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=_committing_intent(),
    )
    assert _SECRET not in json.dumps(receipt)


# --- #385-11: provision-write failure after a known create ----------------


def test_peer_d11_foreign_provision_refuses_before_secret_or_create(tmp_path):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, folder_id=provision["folder_id"])])
    transport.create_response = _peer_create_success()
    peer_provision_path = tmp_path / "peer_provision.json"
    # A foreign provision collision must stop before Keychain or vendor I/O.
    peer_provision_path.write_text(json.dumps({"not": "reconcilable"}), encoding="utf-8")
    peer_provision_path.chmod(0o600)

    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
        ],
        peer_intent_path=str(tmp_path / "peer_intent.json"),
        peer_provision_path=str(peer_provision_path),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    receipt = json.loads(out.getvalue())
    assert code == 2
    assert receipt["verdict"] == "REFUSED"
    assert receipt["code"] == "PROVISION_MISSING"
    assert transport.calls == []
    # The pre-seeded foreign file must not have been silently overwritten.
    assert json.loads(peer_provision_path.read_text(encoding="utf-8")) == {"not": "reconcilable"}


def test_peer_d11_unstopped_create_never_writes_a_peer_provision(tmp_path):
    """A create whose read-back cannot prove the profile stopped must NOT
    publish profile_B and must NOT report PASS.

    This is the mutation that turns a HOLD into a false PASS: the search
    record looks unowned, but the launcher reports the profile running. The
    provision file must stay absent and the cleanup lease must be retained.
    """
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, folder_id=provision["folder_id"])])
    transport.create_response = _peer_create_success()
    transport.status_by_id = {_PEER_CREATED_UUID: "browser_running"}
    peer_provision_path = tmp_path / "peer_provision.json"
    peer_intent_path = tmp_path / "peer_intent.json"
    _prepare_peer_lifecycle(provision, peer_intent_path, peer_provision_path)

    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
        ],
        peer_intent_path=str(peer_intent_path),
        peer_provision_path=str(peer_provision_path),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "CREATE_APPLIED"
    assert receipt["predicates"]["stopped_proven"] is False
    assert receipt["predicates"]["provision_written"] is False
    assert receipt["predicates"]["cleanup_lease_retained"] is True
    # The load-bearing assertion: no profile_B binding was published.
    assert not peer_provision_path.exists()
    assert [c[0] for c in transport.calls].count("create") == 1


# --- #385-12: remove exact stopped operation-created peer -> ROLLBACK_VERIFIED -


def test_peer_d12_remove_exact_stopped_peer_verifies_absence():
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [_peer_record(peer_name, id=_PEER_CREATED_UUID)], [],
    )
    transport.remove_response = _peer_remove_success()
    client = _peer_client(transport)
    receipt = client.remove_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR, peer_profile_id=_PEER_CREATED_UUID,
        claim_remove=lambda: vendors.CREATED_THIS_CALL,
    )
    assert receipt["verdict"] == "PASS"
    assert receipt["effect"] == "ROLLBACK_VERIFIED"
    assert receipt["predicates"]["removed_absent"] is True
    assert [c[0] for c in transport.calls].count("remove") == 1


# --- REVIEW REPAIRS: gaps found by the non-author adversarial review -------


def _seed_peer_intent(tmp_path, provision):
    """Write the create-intent preimage exactly as a real create would."""
    intent_path = tmp_path / "peer_intent.json"
    assert vendors.initialize_peer_lifecycle_state(
        intent_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=vendors.peer_profile_name(provision["folder_id"], provision["profile_id"]),
        peer_provision_path=tmp_path / "peer_provision.json",
    ) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        intent_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=vendors.peer_profile_name(provision["folder_id"], provision["profile_id"]),
        peer_provision_path=tmp_path / "peer_provision.json",
    ) == vendors.CREATED_THIS_CALL
    return intent_path


def _peer_provision_doc(provision, profile_id):
    return {
        "schema": core.PROVISION_SCHEMA,
        "vendor": "multilogin",
        "profile_id": profile_id,
        "folder_id": provision["folder_id"],
        "browser_type": "mimic",
        "origin_policy": port_policy.ORIGIN_POLICY,
        "disposable_ack": core.REQUIRED_ACK,
    }


def _peer_ownership_receipt(state, provision_snapshot, **overrides):
    document = {
        "schema": vendors.PEER_OWNERSHIP_FACT_SCHEMA,
        "peer_operation": vendors.PEER_OPERATION_KEY,
        "source_generation": vendors.PEER_SOURCE_GENERATION,
        "lifecycle_generation": state.document["generation"],
        "peer_profile_digest": state.document["peer_profile_digest"],
        "peer_provision_digest": provision_snapshot.sha256,
        "peer_provision_dev": provision_snapshot.st_dev,
        "peer_provision_ino": provision_snapshot.st_ino,
        "pf1_operation": vendors.PF1_OPERATION_KEY,
        "pf1_active": False,
        "install1_operation": vendors.INSTALL1_OPERATION_KEY,
        "install1_active": False,
        "observed_at": "2026-08-23T11:59:00Z",
        "valid_until": "2026-08-23T12:01:00Z",
        "release_nonce_digest": "9" * 64,
    }
    document.update(overrides)
    return document


def _seed_peer_provision_committed(tmp_path, *, profile_id=_PEER_CREATED_UUID):
    """Materialize the exact durable state left by one successful create."""
    provision = _valid_provision("multilogin")
    anchor_path = _write_provision(tmp_path, provision)
    state_path = tmp_path / "peer-state.json"
    peer_provision_path = tmp_path / "peer-provision.json"
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    assert vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=peer_name,
        peer_provision_path=peer_provision_path,
    ) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=peer_name,
        peer_provision_path=peer_provision_path,
    ) == vendors.CREATED_THIS_CALL
    state = vendors._peer_intent_snapshot(state_path)
    state = vendors._transition_peer_intent(
        state_path,
        expected=state,
        phase=vendors.PEER_PHASE_PROFILE_STOPPED,
        peer_profile_id=profile_id,
    )
    assert state is not None
    vendors.atomic_private_json(
        _peer_provision_doc(provision, profile_id), peer_provision_path,
    )
    peer_provision = vendors._peer_provision_snapshot(peer_provision_path)
    state = vendors._transition_peer_intent(
        state_path,
        expected=state,
        phase=vendors.PEER_PHASE_PROVISION_COMMITTED,
        peer_profile_id=profile_id,
        peer_provision_snapshot=peer_provision,
    )
    assert state is not None
    return provision, anchor_path, state_path, peer_provision_path, state, peer_provision


def _rollback_main(tmp_path, provision, transport, *, intent_path, peer_provision_path, out):
    ownership_fact = None
    state = vendors._peer_intent_snapshot(intent_path)
    peer_snapshot = vendors._peer_provision_snapshot(peer_provision_path)
    if state is not None and peer_snapshot is not None:
        if state.document["phase"] == vendors.PEER_PHASE_CREATE_CLAIMED:
            state = vendors._transition_peer_intent(
                intent_path,
                expected=state,
                phase=vendors.PEER_PHASE_PROFILE_STOPPED,
                peer_profile_id=peer_snapshot.document["profile_id"],
            )
            state = vendors._transition_peer_intent(
                intent_path,
                expected=state,
                phase=vendors.PEER_PHASE_PROVISION_COMMITTED,
                peer_profile_id=peer_snapshot.document["profile_id"],
                peer_provision_snapshot=peer_snapshot,
            )
        if state is not None:
            ownership_fact = _peer_ownership_receipt(state, peer_snapshot)
    return _authorized_peer_main(
        [
            "rollback-peer-profile", "--vendor", "multilogin",
            "--provision-path", str(_write_provision(tmp_path, provision)),
        ],
        peer_intent_path=str(intent_path),
        peer_provision_path=str(peer_provision_path),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
        ownership_receipt_loader=lambda: ownership_fact,
    )


def test_peer_rollback_without_create_intent_receipt_refuses_before_any_remove(tmp_path):
    """A peer provision ALONE must not authorize a removal.

    #385 requires the exact operation-created provision AND the create-intent
    receipt to match. Without this gate a hand-authored or stale provision is
    enough to delete a profile this operation never created -- precisely the
    state #385-6 calls a conflict on the create side.
    """
    provision = _valid_provision("multilogin")
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    peer_provision_path = tmp_path / "peer_provision.json"
    vendors.atomic_private_json(
        _peer_provision_doc(provision, _PEER_CREATED_UUID), peer_provision_path,
    )
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [_peer_record(peer_name, folder_id=provision["folder_id"], id=_PEER_CREATED_UUID)], [],
    )
    transport.remove_response = _peer_remove_success()

    out = io.StringIO()
    code = _rollback_main(
        tmp_path, provision, transport,
        intent_path=tmp_path / "absent_intent.json",
        peer_provision_path=peer_provision_path, out=out,
    )
    assert code == 2
    # The load-bearing assertion: nothing was dispatched at all.
    assert [c[0] for c in transport.calls].count("remove") == 0


def test_peer_rollback_with_matching_intent_receipt_verifies_absence(tmp_path):
    """The same flow WITH the operation's own preimage completes end to end."""
    provision = _valid_provision("multilogin")
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    intent_path = _seed_peer_intent(tmp_path, provision)
    peer_provision_path = tmp_path / "peer_provision.json"
    vendors.atomic_private_json(
        _peer_provision_doc(provision, _PEER_CREATED_UUID), peer_provision_path,
    )
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [_peer_record(peer_name, folder_id=provision["folder_id"], id=_PEER_CREATED_UUID)], [],
    )
    transport.remove_response = _peer_remove_success()

    out = io.StringIO()
    code = _rollback_main(
        tmp_path, provision, transport,
        intent_path=intent_path, peer_provision_path=peer_provision_path, out=out,
    )
    receipt = json.loads(out.getvalue())
    assert code == 0
    assert receipt["effect"] == "ROLLBACK_VERIFIED"
    assert receipt["predicates"]["removed_absent"] is True
    assert [c[0] for c in transport.calls].count("remove") == 1


def test_peer_pre_effect_auth_rejection_does_not_wedge_the_capability(tmp_path):
    """A 401 becomes an exact CAS-rearmable tombstone, never a path unlink."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    intent_path = tmp_path / "peer_intent.json"
    transport = _PeerTransport()
    transport.set_candidates_sequence([])
    transport.create_response = vendors._BoundedResponse(401, {})
    peer_provision_path = tmp_path / "peer_provision.json"
    _prepare_peer_lifecycle(provision, intent_path, peer_provision_path)

    out = io.StringIO()
    code = _authorized_peer_main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path)],
        peer_intent_path=str(intent_path),
        peer_provision_path=str(peer_provision_path),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    receipt = json.loads(out.getvalue())
    assert code == 2
    assert receipt["effect"] == "NONE"
    assert receipt["code"] == "AUTH_EXPIRED"
    assert [c[0] for c in transport.calls].count("create") == 1
    rejected = vendors._peer_intent_snapshot(intent_path)
    assert rejected.document["phase"] == vendors.PEER_PHASE_CREATE_AUTH_REJECTED

    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    recovered_transport = _PeerTransport()
    recovered_transport.set_candidates_sequence(
        [], [_peer_record(peer_name, folder_id=provision["folder_id"])],
    )
    recovered_transport.create_response = _peer_create_success()
    recovered_out = io.StringIO()
    recovered_code = _authorized_peer_main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path)],
        peer_intent_path=str(intent_path),
        peer_provision_path=str(peer_provision_path),
        stdout=recovered_out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"fresh-cred"),
        client_factory=lambda: recovered_transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert recovered_code == 0
    assert [c[0] for c in recovered_transport.calls].count("create") == 1


def test_peer_ambiguous_response_keeps_its_preimage(tmp_path):
    """The converse of the pre-effect discard: a LOST response must retain the
    preimage, because a profile may well have been created."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    intent_path = tmp_path / "peer_intent.json"
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [])
    transport.create_raises = True
    peer_provision_path = tmp_path / "peer_provision.json"
    _prepare_peer_lifecycle(provision, intent_path, peer_provision_path)

    out = io.StringIO()
    _authorized_peer_main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path)],
        peer_intent_path=str(intent_path),
        peer_provision_path=str(peer_provision_path),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    receipt = json.loads(out.getvalue())
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert intent_path.exists()


def test_peer_acknowledged_id_must_match_the_read_back_record():
    """The vendor named one id and the census returned another.

    Adopting the census row would strand the acknowledged profile in the
    approved folder: untracked, unreachable by rollback, and fatal to every
    later create (which would then see multiple candidates).
    """
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, id=_PEER_OTHER_UUID)])
    transport.create_response = _peer_create_success(profile_id=_PEER_ALT_UUID)
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=lambda: vendors.CREATED_THIS_CALL,
    )
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["predicates"]["exact_readback"] is False
    assert receipt["digests"]["peer_profile"] is None
    assert client._peer_profile_id is None
    assert [c[0] for c in transport.calls].count("create") == 1


def test_peer_read_back_record_must_be_unowned():
    """Pins ``require_unowned=True`` on the create read-back.

    A census row claiming an owner is not a publishable profile even when the
    launcher reports it stopped; without this the wave's "stopped AND unowned"
    claim would be prose only.
    """
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [], [_peer_record(peer_name, in_use_by="someone@example.com")],
    )
    transport.create_response = _peer_create_success()
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=lambda: vendors.CREATED_THIS_CALL,
    )
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["predicates"]["exact_readback"] is False
    assert client._peer_profile_id is None


@pytest.mark.parametrize("status_code", (202, 204, 500))
def test_peer_create_success_status_set_is_exactly_200_and_201(status_code):
    """Pins the deliberate two-source decision.

    The help article's prose says 200 and the Postman collection's example
    shows 201, so both are accepted as *dispatch acknowledged*. Any other code
    is ambiguous, never exact -- widening this set must fail a test.
    """
    ok = vendors._BoundedResponse(status_code, {
        "status": {"error_code": "", "http_code": status_code, "message": "Profile successfully created"},
        "data": {"ids": [_PEER_CREATED_UUID]},
    })
    assert vendors._is_exact_profile_create_success(ok) is False
    for accepted in (200, 201):
        assert vendors._is_exact_profile_create_success(_peer_create_success(status_code=accepted)) is True


@pytest.mark.parametrize("after_rows", ("zero", "multiple"))
def test_peer_committed_intent_with_wrong_candidate_count_never_dispatches(after_rows):
    """#385-8's committed-intent half: a preimage on disk plus zero or many
    candidates is uncertainty, and uncertainty is never permission to create."""
    peer_name = _peer_name()
    rows = [] if after_rows == "zero" else [
        _peer_record(peer_name, id=_PEER_ALT_UUID),
        _peer_record(peer_name, id=_PEER_OTHER_UUID),
    ]
    transport = _PeerTransport()
    transport.set_candidates_sequence(rows)
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=True, commit_intent=lambda: vendors.CREATED_THIS_CALL,
    )
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["verdict"] == "HOLD"
    assert receipt["predicates"]["dispatched"] is False
    assert [c[0] for c in transport.calls].count("create") == 0


def test_peer_paths_are_not_caller_suppliable_on_the_cli():
    """#385 requires a FIXED private peer destination, so the argument parser
    must expose no flag that could redirect the provision or the preimage."""
    source = inspect.getsource(vendors.main)
    assert "--peer-provision-path" not in source
    assert "--peer-intent-path" not in source


# --- SOL POST-START CLARIFICATION: trash is not permanent deletion ---------


def test_peer_active_search_absence_never_proves_permanent_deletion(tmp_path):
    """Absence from ``Profile Search(is_removed=False)`` proves the profile left
    the ACTIVE folder -- nothing more.

    Multilogin deletion is two-stage: an ordinary remove moves the profile to
    the Trash, where it stays restorable and may still consume a plan slot;
    permanent deletion is a separate irreversible action from inside the Trash.
    So a ROLLBACK_VERIFIED receipt built from active-census absence must NOT be
    readable as permanent deletion or capacity release.
    """
    provision = _valid_provision("multilogin")
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    intent_path = _seed_peer_intent(tmp_path, provision)
    peer_provision_path = tmp_path / "peer_provision.json"
    vendors.atomic_private_json(
        _peer_provision_doc(provision, _PEER_CREATED_UUID), peer_provision_path,
    )
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [_peer_record(peer_name, folder_id=provision["folder_id"], id=_PEER_CREATED_UUID)], [],
    )
    transport.remove_response = _peer_remove_success()

    out = io.StringIO()
    code = _rollback_main(
        tmp_path, provision, transport,
        intent_path=intent_path, peer_provision_path=peer_provision_path, out=out,
    )
    receipt = json.loads(out.getvalue())
    assert code == 0
    assert receipt["effect"] == "ROLLBACK_VERIFIED"
    assert receipt["predicates"]["removed_absent"] is True

    # The disposition must be carried explicitly, not left to the reader.
    assert receipt["removal_disposition"] == "TRASHED_RESTORABLE"
    detail = receipt["removal_disposition_detail"].lower()
    assert "restorable" in detail
    assert "may still consume a plan slot" in detail
    assert "not permanent deletion" in detail
    assert "no capacity" in detail

    # No effect sentence anywhere may assert permanence or capacity release.
    vocabulary = " ".join(vendors.PEER_EFFECT_DETAILS.values()).lower()
    for forbidden in ("permanently deleted", "permanent deletion", "capacity released", "slot freed"):
        assert forbidden not in vocabulary

    # And the request that produced the absence asked for the reversible form.
    assert vendors._PEER_REMOVE_PERMANENTLY is False


def test_peer_refused_removal_carries_no_removal_disposition():
    """A refusal that dispatched nothing must not imply a trash move either."""
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence([])
    client = _peer_client(transport)
    receipt = client.remove_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR, peer_profile_id=_PEER_CREATED_UUID,
        claim_remove=lambda: vendors.CREATED_THIS_CALL,
    )
    assert receipt["verdict"] == "REFUSED"
    assert receipt["predicates"]["dispatched"] is False
    assert receipt["removal_disposition"] == "NOT_APPLICABLE"
    assert [c[0] for c in transport.calls].count("remove") == 0


def test_peer_permanent_delete_is_structurally_unauthorized():
    """#385 authorizes ONE exact remove request, not an irreversible purge.

    Permanent deletion IS reachable on the same documented endpoint via
    ``permanently: true``, so the boundary cannot rest on prose. Flipping the
    constant must stop the module from importing at all, forcing a
    DECISION_REQUEST / PERMANENT_DELETE_BOUNDARY ruling first.
    """
    source = Path(vendors.__file__).read_text(encoding="utf-8")
    assert "_PEER_REMOVE_PERMANENTLY = False" in source
    mutated = source.replace("_PEER_REMOVE_PERMANENTLY = False", "_PEER_REMOVE_PERMANENTLY = True", 1)
    namespace = {
        "__name__": "mutated_nonseat_canary_vendors",
        "__file__": vendors.__file__,
        "__package__": "integrations.chairman_surfaces",
    }
    with pytest.raises(RuntimeError) as raised:
        exec(compile(mutated, vendors.__file__, "exec"), namespace)  # noqa: S102 — boundary probe
    assert "permanent profile deletion is not authorized" in str(raised.value)
    assert "PERMANENT_DELETE_BOUNDARY" in str(raised.value)


# --- #385-13: wrong id / replaced identity / bound / running / unowned ---


@pytest.mark.parametrize(
    "mutation",
    ("wrong_id", "replaced_identity", "folder_mismatch", "still_bound", "running", "unowned"),
)
def test_peer_d13_non_exact_target_emits_zero_remove_requests(mutation):
    peer_name = _peer_name()
    record = _peer_record(peer_name, id=_PEER_CREATED_UUID)
    target_id = _PEER_CREATED_UUID
    status_by_id = {}
    if mutation == "wrong_id":
        target_id = _PEER_ALT_UUID
    elif mutation == "replaced_identity":
        record["browser_type"] = "stealthfox"
    elif mutation == "folder_mismatch":
        record["folder_id"] = "not-the-anchor-folder"
    elif mutation == "still_bound":
        record["locked_by"] = "other-session"
    elif mutation == "running":
        status_by_id[_PEER_CREATED_UUID] = "browser_running"
    elif mutation == "unowned":
        record["in_use_by"] = "someone-else"

    transport = _PeerTransport()
    transport.set_candidates_sequence([record])
    transport.status_by_id = status_by_id
    client = _peer_client(transport)
    receipt = client.remove_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR, peer_profile_id=target_id,
    )
    assert receipt["verdict"] == "REFUSED"
    assert receipt["effect"] == "NONE"
    assert [c[0] for c in transport.calls].count("remove") == 0


# --- #385-14: remove response lost -> one reconciliation, one remove call -


def test_peer_d14_lost_remove_response_reconciles_once():
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence(
        [_peer_record(peer_name, id=_PEER_CREATED_UUID)], [],
    )
    transport.remove_response = None  # response lost
    client = _peer_client(transport)
    receipt = client.remove_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR, peer_profile_id=_PEER_CREATED_UUID,
        claim_remove=lambda: vendors.CREATED_THIS_CALL,
    )
    assert receipt["effect"] in ("ROLLBACK_VERIFIED", "REMOVE_EFFECT_UNKNOWN")
    assert [c[0] for c in transport.calls].count("remove") == 1
    assert [c[0] for c in transport.calls].count("search") == 2


# --- #385-15: profile_A and Chairman profiles/bindings are untouched ------


def test_peer_d15_anchor_profile_and_bindings_are_never_targeted_or_mutated(tmp_path):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    before_bytes = path.read_bytes()
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, folder_id=provision["folder_id"])])
    transport.create_response = _peer_create_success()

    out = io.StringIO()
    _authorized_peer_main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
        ],
        peer_intent_path=str(tmp_path / "peer_intent.json"),
        peer_provision_path=str(tmp_path / "peer_provision.json"),
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert path.read_bytes() == before_bytes
    for call in transport.calls:
        if call[0] == "create":
            assert call[2] != provision["profile_id"]
        elif call[0] in ("remove", "status"):
            assert call[1] != provision["profile_id"]


# --- #385-16: GoLogin/quick-profile stay unsupported; no new bare httpx ---


def test_peer_d16_no_new_generic_endpoint_and_gologin_stays_unsupported():
    source = VENDORS_PATH.read_text(encoding="utf-8")
    assert re.search(r"\bhttpx\.(get|put|post|patch|delete|request|stream)\s*\(", source) is None
    public = {
        name for name in dir(vendors.BoundedHttpClient)
        if not name.startswith("_") and callable(getattr(vendors.BoundedHttpClient, name))
    }
    assert public == {"close"}
    # The peer create/remove capability must exist on MultiloginClient...
    multilogin = vendors.MultiloginClient(core.Credential("x", "stdin"), _PeerTransport())
    assert callable(getattr(multilogin, "create_peer_profile", None))
    assert callable(getattr(multilogin, "remove_peer_profile", None))
    # ...and must never be extended to GoLogin, which stays a hard refusal.
    gologin = vendors.GoLoginClient(core.Credential("x", "stdin"))
    with pytest.raises(core.CanaryRefusal) as exc_info:
        gologin.profile_exists({"profile_id": "x"})
    assert exc_info.value.code == "UNSUPPORTED_SURFACE"
    assert not hasattr(gologin, "create_peer_profile")
    assert not hasattr(gologin, "remove_peer_profile")


# --- REALM1-C1 reconstruction: accepted eight-blocker RED matrix -----------


def _initialize_peer_state(
    state_path, provision_path, *, generation=vendors.PEER_SOURCE_GENERATION,
):
    return vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation=generation,
    )


def test_peer_r2_genesis_witness_is_bound_to_the_exact_initialized_state(tmp_path):
    """Normal setup leaves one mutually inode-bound witness/state genesis."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(state_path, provision_path) == vendors.CREATED_THIS_CALL

    state = vendors._peer_intent_snapshot(state_path)
    witness_path = vendors._peer_genesis_witness_path(state_path)
    witness = vendors._peer_genesis_witness_snapshot(witness_path)
    assert state is not None
    assert witness is not None
    assert witness.document["phase"] == vendors._PEER_GENESIS_WITNESS_BOUND
    assert (witness.document["witness_dev"], witness.document["witness_ino"]) == (
        witness.st_dev,
        witness.st_ino,
    )
    assert (witness.document["state_dev"], witness.document["state_ino"]) == (
        state.st_dev,
        state.st_ino,
    )
    assert (state.document["genesis_witness_dev"], state.document["genesis_witness_ino"]) == (
        witness.st_dev,
        witness.st_ino,
    )
    checked_state, checked_provision = vendors._preflight_peer_paths(
        operation="create-peer-profile",
        state_path=state_path,
        provision_path=provision_path,
    )
    assert vendors._same_snapshot(checked_state, state)
    assert checked_provision is None


@pytest.mark.parametrize("crash_point", ("before_state", "before_witness_bind"))
def test_peer_r2_pending_witness_recovers_only_the_two_setup_crash_windows(
    tmp_path, monkeypatch, crash_point,
):
    """Setup resumes only an exact PENDING witness, never a runtime phase."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    witness_path = vendors._peer_genesis_witness_path(state_path)
    real_create = vendors._create_self_bound_private_record
    real_rewrite = vendors._rewrite_private_record_in_parent

    if crash_point == "before_state":
        def _fail_state_create(target, *args, **kwargs):
            if Path(target) == state_path:
                return None
            return real_create(target, *args, **kwargs)

        monkeypatch.setattr(vendors, "_create_self_bound_private_record", _fail_state_create)
    else:
        def _fail_witness_bind(target, *args, **kwargs):
            if (
                Path(target) == witness_path
                and kwargs.get("next_document", {}).get("phase")
                == vendors._PEER_GENESIS_WITNESS_BOUND
            ):
                return None
            return real_rewrite(target, *args, **kwargs)

        monkeypatch.setattr(vendors, "_rewrite_private_record_in_parent", _fail_witness_bind)

    assert _initialize_peer_state(state_path, provision_path) == vendors.REFUSED
    pending = vendors._peer_genesis_witness_snapshot(witness_path)
    assert pending is not None
    assert pending.document["phase"] == vendors._PEER_GENESIS_WITNESS_PENDING
    assert state_path.exists() is (crash_point == "before_witness_bind")

    monkeypatch.setattr(vendors, "_create_self_bound_private_record", real_create)
    monkeypatch.setattr(vendors, "_rewrite_private_record_in_parent", real_rewrite)
    recovered = _initialize_peer_state(state_path, provision_path)
    expected = (
        vendors.CREATED_THIS_CALL
        if crash_point == "before_state" else vendors.EXISTING_EXACT
    )
    assert recovered == expected
    state, peer = vendors._preflight_peer_paths(
        operation="create-peer-profile",
        state_path=state_path,
        provision_path=provision_path,
    )
    bound = vendors._peer_genesis_witness_snapshot(witness_path)
    assert state is not None and peer is None and bound is not None
    assert bound.document["phase"] == vendors._PEER_GENESIS_WITNESS_BOUND


@pytest.mark.parametrize(
    "target_name,mutation",
    (
        ("state", "unlink"),
        ("witness", "unlink"),
        ("state", "replace"),
        ("witness", "replace"),
    ),
)
def test_peer_r2_genesis_loss_or_replacement_never_rearms(
    tmp_path, target_name, mutation,
):
    """Either half of the bound genesis is mandatory and inode-specific."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(state_path, provision_path) == vendors.CREATED_THIS_CALL
    witness_path = vendors._peer_genesis_witness_path(state_path)
    target = state_path if target_name == "state" else witness_path

    if mutation == "unlink":
        target.unlink()
    else:
        replacement = tmp_path / f"foreign-{target.name}"
        replacement.write_bytes(target.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, target)

    with pytest.raises(vendors._PeerStateRefusal):
        vendors._preflight_peer_paths(
            operation="create-peer-profile",
            state_path=state_path,
            provision_path=provision_path,
        )
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
    ) == vendors.REFUSED
    assert _initialize_peer_state(state_path, provision_path) == vendors.REFUSED


def test_peer_r2_create_claim_is_exclusive_and_full_authority_bearing(tmp_path):
    """Only the process that creates the durable lifecycle state may dispatch.

    The state is deliberately strict: a same-name file with a changed
    generation, anchor, coordinate, phase, profile, or response identity is
    never an interchangeable intent receipt.
    """
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(
        state_path, provision_path, generation="a" * 32,
    ) == vendors.CREATED_THIS_CALL
    barrier = threading.Barrier(2)
    outcomes = []

    def _claim():
        barrier.wait()
        outcomes.append(vendors._commit_peer_intent(
            state_path,
            folder_id=_PEER_FOLDER,
            anchor_profile_id=_PEER_ANCHOR,
            peer_name=_peer_name(),
            peer_provision_path=provision_path,
            generation="a" * 32,
        ))

    threads = [threading.Thread(target=_claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(outcomes) == sorted([
        vendors.CREATED_THIS_CALL,
        vendors.EXISTING_EXACT,
    ])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(state) == {
        "schema", "operation", "generation", "folder_digest",
        "anchor_profile_digest", "browser_type", "os_type", "peer_name",
        "state_dev", "state_ino", "genesis_witness_coordinate_digest",
        "genesis_witness_dev", "genesis_witness_ino",
        "peer_profile_digest", "peer_provision_coordinate_digest",
        "peer_provision_digest", "peer_provision_dev", "peer_provision_ino",
        "phase", "response_profile_digest", "ownership_fact_digest",
        "ownership_observed_at",
    }
    state_stat = state_path.stat()
    assert state["state_dev"] == state_stat.st_dev
    assert state["state_ino"] == state_stat.st_ino
    assert state["phase"] == vendors.PEER_PHASE_CREATE_CLAIMED
    assert state["generation"] == "a" * 32
    assert state["peer_profile_digest"] is None
    assert state["response_profile_digest"] is None
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert state_path.stat().st_nlink == 1


def test_peer_r2_unsafe_fixed_path_refuses_before_anchor_environment_secret_or_client(tmp_path):
    """The fixed peer paths are the first input inspected after authority."""
    victim = tmp_path / "victim.json"
    victim.write_text("{}", encoding="utf-8")
    victim.chmod(0o600)
    state_path = tmp_path / "peer-state.json"
    state_path.symlink_to(victim)
    anchor_path = _write_provision(tmp_path, _valid_provision("multilogin"))
    before = (victim.read_bytes(), victim.stat().st_ino)
    calls = []

    def _bomb(label):
        def _raise(*_args, **_kwargs):
            calls.append(label)
            raise AssertionError(f"unsafe peer state reached {label}")
        return _raise

    out = io.StringIO()
    code = vendors._run_coordinator_peer_create(  # noqa: SLF001
        ["--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=tmp_path / "peer-provision.json",
        stdout=out,
        bindings_loader=_bomb("anchor/bindings"),
        environment_loader=_bomb("environment"),
        credential_stream_factory=_bomb("credential"),
        client_factory=_bomb("client"),
        now=_NOW,
    )
    assert code == 2
    assert calls == []
    assert state_path.is_symlink()
    assert (victim.read_bytes(), victim.stat().st_ino) == before


@pytest.mark.parametrize("status_code", (200, 201, 202, 299))
def test_peer_r2_ambiguous_response_id_still_binds_readback(status_code):
    """Usable response identity is evidence even when success prose drifts."""
    response = vendors._BoundedResponse(status_code, {
        "status": {
            "error_code": "",
            "http_code": status_code,
            "message": "Created; rollout advisory attached",
            "advisory": "synthetic",
        },
        "data": {"ids": [_PEER_ALT_UUID], "notice": "synthetic"},
        "meta": {"request": "synthetic"},
    })
    assert vendors._exact_profile_create_id(response) is None
    assert vendors._observed_profile_create_id(response) == _PEER_ALT_UUID

    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(_peer_name(), id=_PEER_OTHER_UUID)])
    transport.create_response = response
    receipt = _peer_client(transport).create_peer_profile(
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        intent_present=False,
        commit_intent=lambda: vendors.CREATED_THIS_CALL,
    )
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["verdict"] == "HOLD"
    assert receipt["predicates"]["exact_readback"] is False
    assert [call[0] for call in transport.calls].count("create") == 1


def test_peer_r2_create_claim_refuses_if_created_inode_becomes_hardlinked(
    tmp_path, monkeypatch,
):
    """The exclusive creator cannot dispatch after its private inode gains an alias."""
    state_path = tmp_path / "peer-state.json"
    alias_path = tmp_path / "foreign-alias.json"
    provision_path = tmp_path / "peer-provision.json"
    real_fsync = vendors.os.fsync
    injected = False

    def _hardlink_after_leaf_fsync(fd):
        nonlocal injected
        real_fsync(fd)
        if not injected and state_path.exists():
            os.link(state_path, alias_path)
            injected = True

    monkeypatch.setattr(vendors.os, "fsync", _hardlink_after_leaf_fsync)
    outcome = vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation="d" * 32,
    )

    assert injected is True
    assert outcome == vendors.REFUSED
    assert state_path.stat().st_nlink == 2
    assert alias_path.samefile(state_path)


def test_peer_r2_create_claim_refuses_parent_swap_during_lock(tmp_path, monkeypatch):
    """A lock on a renamed directory cannot authorize a claim at the fixed path."""
    private_parent = tmp_path / "private"
    moved_parent = tmp_path / "moved-private"
    private_parent.mkdir(mode=0o700)
    state_path = private_parent / "peer-state.json"
    provision_path = private_parent / "peer-provision.json"
    real_flock = vendors.fcntl.flock
    injected = False

    def _swap_parent_during_flock(fd, operation):
        nonlocal injected
        real_flock(fd, operation)
        if not injected:
            private_parent.rename(moved_parent)
            private_parent.mkdir(mode=0o700)
            injected = True

    monkeypatch.setattr(vendors.fcntl, "flock", _swap_parent_during_flock)
    outcome = vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation="4" * 32,
    )

    assert injected is True
    assert outcome == vendors.REFUSED
    assert not state_path.exists()
    assert not (moved_parent / state_path.name).exists()


def test_peer_r2_peer_provision_refuses_byte_identical_foreign_replacement(
    tmp_path, monkeypatch,
):
    """A post-write path replacement is not our operation-created provision."""
    provision_path = tmp_path / "peer-provision.json"
    replacement_path = tmp_path / "foreign-replacement.json"
    real_fsync = vendors.os.fsync
    created_inode = None
    replacement_inode = None
    injected = False
    binding_calls = []

    def _replace_after_leaf_fsync(fd):
        nonlocal created_inode, replacement_inode, injected
        real_fsync(fd)
        if not injected and provision_path.exists():
            created_inode = provision_path.stat().st_ino
            replacement_path.write_bytes(provision_path.read_bytes())
            replacement_path.chmod(0o600)
            replacement_inode = replacement_path.stat().st_ino
            os.replace(replacement_path, provision_path)
            injected = True

    monkeypatch.setattr(vendors.os, "fsync", _replace_after_leaf_fsync)
    current_environment_snapshot = _seal_realm1_environment(_realm1_environment())
    assert current_environment_snapshot is not None
    written, loaded = vendors._write_peer_provision(
        provision_path,
        profile_id=_PEER_CREATED_UUID,
        folder_id=_PEER_FOLDER,
        bindings_loader=lambda: binding_calls.append(True),
        now=_NOW,
        current_environment_snapshot=current_environment_snapshot,
    )

    assert injected is True
    assert created_inode != replacement_inode
    assert provision_path.stat().st_ino == replacement_inode
    assert (written, loaded) == (False, None)
    assert binding_calls == []


def test_peer_r2_remove_claim_refuses_replacement_during_directory_fsync(
    tmp_path, monkeypatch,
):
    """The remove fence is not acquired if its fixed-path inode is replaced."""
    (
        _provision,
        _anchor_path,
        state_path,
        _provision_path,
        state,
        provision_snapshot,
    ) = _seed_peer_provision_committed(tmp_path)
    ownership_fact = _peer_ownership_receipt(state, provision_snapshot)
    replacement_path = tmp_path / "foreign-state.json"
    replacement_path.write_bytes(state.raw)
    replacement_path.chmod(0o600)
    foreign_inode = replacement_path.stat().st_ino
    real_fsync = vendors.os.fsync
    injected = False

    def _replace_during_parent_fsync(fd):
        nonlocal injected
        real_fsync(fd)
        if not injected and stat.S_ISDIR(os.fstat(fd).st_mode):
            os.replace(replacement_path, state_path)
            injected = True

    monkeypatch.setattr(vendors.os, "fsync", _replace_during_parent_fsync)
    outcome = vendors._claim_peer_remove(
        state_path,
        expected=state,
        peer_profile_id=_PEER_CREATED_UUID,
        provision_snapshot=provision_snapshot,
        ownership_fact=ownership_fact,
        now=_NOW,
    )

    assert injected is True
    assert outcome == vendors.REFUSED
    assert state_path.stat().st_ino == foreign_inode
    # The replacement bytes survive untouched, but their embedded inode
    # authority no longer matches the fixed path and therefore cannot be
    # loaded as lifecycle state on this or any later invocation.
    assert vendors._peer_intent_snapshot(state_path) is None
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == (
        vendors.PEER_PHASE_PROVISION_COMMITTED
    )


def test_peer_r2_ambiguous_response_id_is_durable_across_rerun(tmp_path):
    """A drifted response id survives the process and constrains every rerun."""
    provision = _valid_provision("multilogin")
    anchor_path = _write_provision(tmp_path, provision)
    state_path = tmp_path / "peer-state.json"
    peer_provision_path = tmp_path / "peer-provision.json"
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    response_id = _PEER_ALT_UUID
    census_id = _PEER_OTHER_UUID
    response = vendors._BoundedResponse(201, {
        "status": {
            "error_code": "",
            "http_code": 201,
            "message": "Created with advisory prose",
            "advisory": "synthetic",
        },
        "data": {"ids": [response_id], "notice": "synthetic"},
    })
    first_transport = _PeerTransport()
    first_transport.set_candidates_sequence(
        [], [_peer_record(peer_name, id=census_id, folder_id=provision["folder_id"])],
    )
    first_transport.create_response = response
    _prepare_peer_lifecycle(provision, state_path, peer_provision_path)
    first_out = io.StringIO()
    first_code = _authorized_peer_main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=first_out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: first_transport,
        now=_NOW,
    )
    assert first_code == 3
    state = vendors._peer_intent_snapshot(state_path)
    assert state.document["phase"] == vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED
    assert state.document["response_profile_digest"] == core.sha256_hex(response_id)
    assert not peer_provision_path.exists()

    second_transport = _PeerTransport()
    second_transport.set_candidates_sequence([
        _peer_record(peer_name, id=census_id, folder_id=provision["folder_id"]),
    ])
    second_out = io.StringIO()
    second_code = _authorized_peer_main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=second_out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: second_transport,
        now=_NOW,
    )
    assert second_code == 3
    assert json.loads(second_out.getvalue())["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert [call[0] for call in second_transport.calls].count("create") == 0


def test_peer_r2_unsettled_create_claim_cannot_adopt_concurrent_census_id():
    """A loser cannot provision Y while the owner is still recording response X."""
    transport = _PeerTransport()
    transport.set_candidates_sequence([
        _peer_record(_peer_name(), id=_PEER_OTHER_UUID),
    ])
    receipt = _peer_client(transport).create_peer_profile(
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        intent_present=True,
        commit_intent=lambda: (_ for _ in ()).throw(
            AssertionError("an existing in-flight claim must not be recommitted")
        ),
        observed_profile_digest=None,
        intent_reconciliation_ready=False,
    )

    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["verdict"] == "HOLD"
    assert receipt["predicates"]["dispatched"] is False
    assert [call[0] for call in transport.calls].count("create") == 0


def test_peer_r2_concurrent_create_has_one_dispatch_and_one_reconciliation_loser(tmp_path):
    """Two zero-census callers share one durable winner and one read-only loser."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(
        state_path, provision_path, generation="2" * 32,
    ) == vendors.CREATED_THIS_CALL
    claim_barrier = threading.Barrier(2)
    create_lock = threading.Lock()
    create_calls = []
    receipts = []

    class _ConcurrentCreateTransport(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([], [_peer_record(_peer_name())])

        def _mlx_profile_create(self, credential, folder_id, name):
            with create_lock:
                create_calls.append((folder_id, name))
            return _peer_create_success()

    def _run():
        transport = _ConcurrentCreateTransport()

        def _claim():
            claim_barrier.wait(timeout=5)
            return vendors._commit_peer_intent(
                state_path,
                folder_id=_PEER_FOLDER,
                anchor_profile_id=_PEER_ANCHOR,
                peer_name=_peer_name(),
                peer_provision_path=provision_path,
                generation="2" * 32,
            )

        receipts.append(_peer_client(transport).create_peer_profile(
            folder_id=_PEER_FOLDER,
            anchor_profile_id=_PEER_ANCHOR,
            intent_present=False,
            commit_intent=_claim,
        ))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert len(create_calls) == 1
    assert len(receipts) == 2
    assert {receipt["effect"] for receipt in receipts} == {
        "PROFILE_STOPPED_PROVEN",
        "CREATE_EFFECT_UNKNOWN",
    }
    assert sorted(receipt["predicates"]["dispatched"] for receipt in receipts) == [False, True]


@pytest.mark.parametrize("census_result", ("busy", "transport_error"))
def test_peer_r2_phase_advance_during_first_census_never_returns_false_none(
    tmp_path, census_result,
):
    """A concurrent effect-bearing claim cannot be hidden by stale intent=False."""
    provision = _valid_provision("multilogin")
    anchor_path = _write_provision(tmp_path, provision)
    state_path = tmp_path / "peer-state.json"
    peer_provision_path = tmp_path / "peer-provision.json"
    peer_name = vendors.peer_profile_name(
        provision["folder_id"], provision["profile_id"],
    )
    _prepare_peer_lifecycle(provision, state_path, peer_provision_path)

    class _AdvanceDuringFirstCensus(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.advanced = False
            self.set_candidates_sequence([
                _peer_record(
                    peer_name,
                    id=_PEER_CREATED_UUID,
                    folder_id=provision["folder_id"],
                ),
            ])

        def _mlx_profile_search(self, credential, folder_id, *, offset):
            if offset == 0 and not self.advanced:
                initialized = vendors._peer_intent_snapshot(state_path)
                claimed = vendors._transition_peer_intent(
                    state_path,
                    expected=initialized,
                    phase=vendors.PEER_PHASE_CREATE_CLAIMED,
                )
                assert claimed is not None
                observed = vendors._transition_peer_intent(
                    state_path,
                    expected=claimed,
                    phase=vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED,
                    response_profile_id=_PEER_CREATED_UUID,
                )
                assert observed is not None
                self.advanced = True
                if census_result == "transport_error":
                    raise RuntimeError("synthetic first-census transport loss")
            return super()._mlx_profile_search(
                credential, folder_id, offset=offset,
            )

    transport = _AdvanceDuringFirstCensus()
    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile",
            "--vendor",
            "multilogin",
            "--provision-path",
            str(anchor_path),
        ],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"credential"),
        client_factory=lambda: transport,
        now=_NOW,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["predicates"]["intent_committed"] is True
    assert receipt["predicates"]["dispatched"] is False
    assert receipt["predicates"]["reconciled"] is True
    assert sum(call[0] == "create" for call in transport.calls) == 0
    assert vendors._peer_intent_snapshot(state_path).document["phase"] == (
        vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED
    )


@pytest.mark.parametrize(
    "phase,census_result",
    (
        (vendors.PEER_PHASE_CREATE_CLAIMED, "transport_error"),
        (vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED, "transport_error"),
        (vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED, "wrong_identity"),
    ),
)
def test_peer_r2_effect_bearing_create_reentry_never_returns_false_none(
    tmp_path, phase, census_result,
):
    """A persisted create claim makes every failed census effect-unknown."""
    provision = _valid_provision("multilogin")
    anchor_path = _write_provision(tmp_path, provision)
    state_path = tmp_path / "peer-state.json"
    peer_provision_path = tmp_path / "peer-provision.json"
    peer_name = vendors.peer_profile_name(
        provision["folder_id"], provision["profile_id"],
    )
    _prepare_peer_lifecycle(provision, state_path, peer_provision_path)
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=peer_name,
        peer_provision_path=peer_provision_path,
    ) == vendors.CREATED_THIS_CALL
    if phase == vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED:
        claimed = vendors._peer_intent_snapshot(state_path)
        assert vendors._transition_peer_intent(
            state_path,
            expected=claimed,
            phase=vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED,
            response_profile_id=_PEER_CREATED_UUID,
        ) is not None

    class _FailedReentryCensus(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([
                _peer_record(
                    peer_name,
                    id=_PEER_CREATED_UUID,
                    folder_id=provision["folder_id"],
                    browser_type="stealthfox",
                ),
            ])

        def _mlx_profile_search(self, credential, folder_id, *, offset):
            if census_result == "transport_error":
                raise RuntimeError("synthetic re-entry census loss")
            return super()._mlx_profile_search(
                credential, folder_id, offset=offset,
            )

    transport = _FailedReentryCensus()
    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile",
            "--vendor",
            "multilogin",
            "--provision-path",
            str(anchor_path),
        ],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"credential"),
        client_factory=lambda: transport,
        now=_NOW,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["predicates"]["intent_committed"] is True
    assert receipt["predicates"]["dispatched"] is False
    assert receipt["predicates"]["reconciled"] is True
    assert sum(call[0] == "create" for call in transport.calls) == 0
    assert vendors._peer_intent_snapshot(state_path).document["phase"] == phase


def test_peer_r2_remove_claim_is_monotonic_and_single_winner(tmp_path):
    """A durable remove phase is a one-total-dispatch fence, not a retry bit."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(
        state_path, provision_path, generation="b" * 32,
    ) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation="b" * 32,
    ) == vendors.CREATED_THIS_CALL
    snapshot = vendors._peer_intent_snapshot(state_path)
    vendors.atomic_private_json(
        _peer_provision_doc(
            {"folder_id": _PEER_FOLDER},
            _PEER_CREATED_UUID,
        ),
        provision_path,
    )
    provision_snapshot = vendors._peer_provision_snapshot(provision_path)
    snapshot = vendors._transition_peer_intent(
        state_path,
        expected=snapshot,
        phase=vendors.PEER_PHASE_PROFILE_STOPPED,
        peer_profile_id=_PEER_CREATED_UUID,
    )
    snapshot = vendors._transition_peer_intent(
        state_path,
        expected=snapshot,
        phase=vendors.PEER_PHASE_PROVISION_COMMITTED,
        peer_profile_id=_PEER_CREATED_UUID,
        peer_provision_snapshot=provision_snapshot,
    )
    ownership_fact = _peer_ownership_receipt(snapshot, provision_snapshot)
    first = vendors._claim_peer_remove(
        state_path,
        expected=snapshot,
        peer_profile_id=_PEER_CREATED_UUID,
        provision_snapshot=provision_snapshot,
        ownership_fact=ownership_fact,
        now=_NOW,
    )
    second_snapshot = vendors._peer_intent_snapshot(state_path)
    second = vendors._claim_peer_remove(
        state_path,
        expected=second_snapshot,
        peer_profile_id=_PEER_CREATED_UUID,
        provision_snapshot=provision_snapshot,
        ownership_fact=ownership_fact,
        now=_NOW,
    )
    assert first == vendors.CREATED_THIS_CALL
    assert second == vendors.EXISTING_EXACT
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == vendors.PEER_PHASE_REMOVE_DISPATCHED


def test_peer_r2_remove_phase_advance_during_first_census_never_returns_false_none(
    tmp_path,
):
    """A concurrent remove fence cannot be hidden by a stale pre-census phase."""
    (
        provision,
        _anchor_path,
        state_path,
        peer_provision_path,
        state,
        peer_snapshot,
    ) = _seed_peer_provision_committed(tmp_path)
    ownership_fact = _peer_ownership_receipt(state, peer_snapshot)

    class _AdvanceRemoveDuringFirstCensus(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.advanced = False
            self.set_candidates_sequence([])

        def _mlx_profile_search(self, credential, folder_id, *, offset):
            if offset == 0 and not self.advanced:
                current = vendors._peer_intent_snapshot(state_path)
                advanced = vendors._transition_peer_intent(
                    state_path,
                    expected=current,
                    phase=vendors.PEER_PHASE_REMOVE_DISPATCHED,
                    peer_profile_id=_PEER_CREATED_UUID,
                    ownership_fact=ownership_fact,
                )
                assert advanced is not None
                self.advanced = True
            return super()._mlx_profile_search(
                credential, folder_id, offset=offset,
            )

    transport = _AdvanceRemoveDuringFirstCensus()
    out = io.StringIO()
    code = _rollback_main(
        tmp_path,
        provision,
        transport,
        intent_path=state_path,
        peer_provision_path=peer_provision_path,
        out=out,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "REMOVE_EFFECT_UNKNOWN"
    assert receipt["predicates"]["intent_committed"] is True
    assert receipt["predicates"]["dispatched"] is False
    assert receipt["predicates"]["reconciled"] is True
    assert sum(call[0] == "remove" for call in transport.calls) == 0
    assert vendors._peer_intent_snapshot(state_path).document["phase"] == (
        vendors.PEER_PHASE_REMOVE_DISPATCHED
    )


def test_peer_r2_remove_dispatched_reentry_census_error_never_returns_false_none(
    tmp_path,
):
    """A persisted remove fence remains effect-unknown when census is lost."""
    (
        provision,
        _anchor_path,
        state_path,
        peer_provision_path,
        state,
        peer_snapshot,
    ) = _seed_peer_provision_committed(tmp_path)
    ownership_fact = _peer_ownership_receipt(state, peer_snapshot)
    dispatched = vendors._transition_peer_intent(
        state_path,
        expected=state,
        phase=vendors.PEER_PHASE_REMOVE_DISPATCHED,
        peer_profile_id=_PEER_CREATED_UUID,
        ownership_fact=ownership_fact,
    )
    assert dispatched is not None

    class _LostReentryCensus(_PeerTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            raise RuntimeError("synthetic remove re-entry census loss")

    transport = _LostReentryCensus()
    out = io.StringIO()
    code = _rollback_main(
        tmp_path,
        provision,
        transport,
        intent_path=state_path,
        peer_provision_path=peer_provision_path,
        out=out,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "REMOVE_EFFECT_UNKNOWN"
    assert receipt["predicates"]["intent_committed"] is True
    assert receipt["predicates"]["dispatched"] is False
    assert receipt["predicates"]["reconciled"] is True
    assert sum(call[0] == "remove" for call in transport.calls) == 0
    assert vendors._peer_intent_snapshot(state_path).document["phase"] == (
        vendors.PEER_PHASE_REMOVE_DISPATCHED
    )


def test_peer_r2_remove_claim_requires_fresh_negative_ownership_fact(tmp_path):
    """No private helper path may bypass the PF-1/INSTALL1 exclusion."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(
        state_path, provision_path, generation="e" * 32,
    ) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation="e" * 32,
    ) == vendors.CREATED_THIS_CALL
    snapshot = vendors._peer_intent_snapshot(state_path)
    vendors.atomic_private_json(
        _peer_provision_doc({"folder_id": _PEER_FOLDER}, _PEER_CREATED_UUID),
        provision_path,
    )
    provision_snapshot = vendors._peer_provision_snapshot(provision_path)
    snapshot = vendors._transition_peer_intent(
        state_path,
        expected=snapshot,
        phase=vendors.PEER_PHASE_PROFILE_STOPPED,
        peer_profile_id=_PEER_CREATED_UUID,
    )
    snapshot = vendors._transition_peer_intent(
        state_path,
        expected=snapshot,
        phase=vendors.PEER_PHASE_PROVISION_COMMITTED,
        peer_profile_id=_PEER_CREATED_UUID,
        peer_provision_snapshot=provision_snapshot,
    )

    assert vendors._claim_peer_remove(
        state_path,
        expected=snapshot,
        peer_profile_id=_PEER_CREATED_UUID,
        provision_snapshot=provision_snapshot,
        ownership_fact=None,
        now=_NOW,
    ) == vendors.REFUSED
    assert vendors._peer_intent_snapshot(state_path).document["phase"] == vendors.PEER_PHASE_PROVISION_COMMITTED


def test_peer_r2_stale_concurrent_remove_claim_reconciles_to_existing(tmp_path):
    """A CAS loser observes the winner's exact remove fence, never a retry cue."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(
        state_path, provision_path, generation="f" * 32,
    ) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation="f" * 32,
    ) == vendors.CREATED_THIS_CALL
    stale = vendors._peer_intent_snapshot(state_path)
    vendors.atomic_private_json(
        _peer_provision_doc({"folder_id": _PEER_FOLDER}, _PEER_CREATED_UUID),
        provision_path,
    )
    provision_snapshot = vendors._peer_provision_snapshot(provision_path)
    stale = vendors._transition_peer_intent(
        state_path,
        expected=stale,
        phase=vendors.PEER_PHASE_PROFILE_STOPPED,
        peer_profile_id=_PEER_CREATED_UUID,
    )
    stale = vendors._transition_peer_intent(
        state_path,
        expected=stale,
        phase=vendors.PEER_PHASE_PROVISION_COMMITTED,
        peer_profile_id=_PEER_CREATED_UUID,
        peer_provision_snapshot=provision_snapshot,
    )
    ownership_fact = _peer_ownership_receipt(stale, provision_snapshot)

    first = vendors._claim_peer_remove(
        state_path,
        expected=stale,
        peer_profile_id=_PEER_CREATED_UUID,
        provision_snapshot=provision_snapshot,
        ownership_fact=ownership_fact,
        now=_NOW,
    )
    second = vendors._claim_peer_remove(
        state_path,
        expected=stale,
        peer_profile_id=_PEER_CREATED_UUID,
        provision_snapshot=provision_snapshot,
        ownership_fact=ownership_fact,
        now=_NOW,
    )
    assert first == vendors.CREATED_THIS_CALL
    assert second == vendors.EXISTING_EXACT


def test_peer_r2_phase_shape_and_transitions_cannot_skip_required_proofs(tmp_path):
    """Phase labels cannot manufacture evidence missing from earlier phases."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(
        state_path, provision_path, generation="1" * 32,
    ) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation="1" * 32,
    ) == vendors.CREATED_THIS_CALL
    claimed = vendors._peer_intent_snapshot(state_path)
    malformed = dict(claimed.document)
    malformed["phase"] = vendors.PEER_PHASE_CREATE_RESPONSE_OBSERVED
    assert vendors._peer_state_shape_exact(malformed) is False

    vendors.atomic_private_json(
        _peer_provision_doc({"folder_id": _PEER_FOLDER}, _PEER_CREATED_UUID),
        provision_path,
    )
    provision_snapshot = vendors._peer_provision_snapshot(provision_path)
    assert vendors._transition_peer_intent(
        state_path,
        expected=claimed,
        phase=vendors.PEER_PHASE_PROVISION_COMMITTED,
        peer_profile_id=_PEER_CREATED_UUID,
        peer_provision_snapshot=provision_snapshot,
    ) is None


def test_peer_r2_stale_snapshot_cannot_transition_replacement(tmp_path):
    """A byte-identical replacement inode is never rewritten as our state."""
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(
        state_path, provision_path, generation="c" * 32,
    ) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
        generation="c" * 32,
    ) == vendors.CREATED_THIS_CALL
    stale = vendors._peer_intent_snapshot(state_path)
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(stale.raw)
    replacement.chmod(0o600)
    replacement_bytes = replacement.read_bytes()
    replacement_ino = replacement.stat().st_ino
    os.replace(replacement, state_path)

    assert vendors._transition_peer_intent(
        state_path,
        expected=stale,
        phase=vendors.PEER_PHASE_CREATE_AUTH_REJECTED,
    ) is None
    assert state_path.read_bytes() == replacement_bytes
    assert state_path.stat().st_ino == replacement_ino


def test_peer_r2_public_confirm_flag_cannot_authorize_peer_effects(tmp_path):
    """Serialized CLI input cannot manufacture either operation capability."""
    with pytest.raises(SystemExit) as exc_info:
        vendors.main([
            "create-peer-profile", "--vendor", "multilogin",
            "--provision-path", str(tmp_path / "anchor.json"), "--confirmed",
        ])
    assert exc_info.value.code == 2

    calls = []
    out = io.StringIO()
    code = vendors.main(
        [
            "create-peer-profile", "--vendor", "multilogin",
            "--provision-path", str(tmp_path / "anchor.json"),
        ],
        stdout=out,
        bindings_loader=lambda: calls.append("bindings"),
        credential_stream_factory=lambda: calls.append("credential"),
        client_factory=lambda: calls.append("client"),
    )
    assert code == 2
    assert calls == []
    assert vendors.CREATE_PEER_AUTHORIZATION is not vendors.ROLLBACK_PEER_AUTHORIZATION
    assert not isinstance(vendors.CREATE_PEER_AUTHORIZATION, (bool, str, int, bytes))
    assert not isinstance(vendors.ROLLBACK_PEER_AUTHORIZATION, (bool, str, int, bytes))


def test_peer_r2_downstream_ownership_fact_is_exact_current_and_negative(tmp_path):
    profile_id = _PEER_CREATED_UUID
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    assert _initialize_peer_state(state_path, provision_path) == vendors.CREATED_THIS_CALL
    assert vendors._commit_peer_intent(
        state_path,
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        peer_name=_peer_name(),
        peer_provision_path=provision_path,
    ) == vendors.CREATED_THIS_CALL
    state = vendors._peer_intent_snapshot(state_path)
    state = vendors._transition_peer_intent(
        state_path,
        expected=state,
        phase=vendors.PEER_PHASE_PROFILE_STOPPED,
        peer_profile_id=profile_id,
    )
    vendors.atomic_private_json(
        _peer_provision_doc({"folder_id": _PEER_FOLDER}, profile_id), provision_path,
    )
    provision_snapshot = vendors._peer_provision_snapshot(provision_path)
    state = vendors._transition_peer_intent(
        state_path,
        expected=state,
        phase=vendors.PEER_PHASE_PROVISION_COMMITTED,
        peer_profile_id=profile_id,
        peer_provision_snapshot=provision_snapshot,
    )
    base = _peer_ownership_receipt(state, provision_snapshot)
    assert vendors._validate_peer_ownership_fact(
        base,
        generation=state.document["generation"],
        peer_profile_id=profile_id,
        provision_snapshot=provision_snapshot,
        now=_NOW,
    ) is True
    for mutation in (
        {"pf1_active": True},
        {"install1_active": True},
        {"valid_until": "2026-08-23T11:59:59Z"},
        {"observed_at": "2026-08-23T12:00:01Z"},
        {"valid_until": "2026-08-23T12:10:00Z"},
        {"lifecycle_generation": "f" * 64},
        {"source_generation": "f" * 64},
        {"pf1_operation": "wrong"},
        {"peer_provision_ino": provision_snapshot.st_ino + 1},
        {"extra": False},
    ):
        candidate = dict(base)
        candidate.update(mutation)
        assert vendors._validate_peer_ownership_fact(
            candidate,
            generation=state.document["generation"],
            peer_profile_id=profile_id,
            provision_snapshot=provision_snapshot,
            now=_NOW,
        ) is False


def test_peer_r2_completed_create_rerun_is_idempotent_without_second_dispatch(tmp_path):
    """A committed provision is a completed create, not a new transition request."""
    (
        provision,
        anchor_path,
        state_path,
        peer_provision_path,
        before_state,
        before_provision,
    ) = _seed_peer_provision_committed(tmp_path)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    exact_peer = _peer_record(
        peer_name,
        id=_PEER_CREATED_UUID,
        folder_id=provision["folder_id"],
    )
    transport.set_candidates_sequence([exact_peer], [exact_peer])
    out = io.StringIO()

    code = _authorized_peer_main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        now=_NOW,
    )

    receipt = json.loads(out.getvalue())
    assert code == 0
    assert receipt["verdict"] == "PASS"
    assert receipt["effect"] == "PROVISION_WRITTEN"
    assert receipt["predicates"]["dispatched"] is False
    assert receipt["predicates"]["reconciled"] is True
    assert [call[0] for call in transport.calls].count("create") == 0
    assert vendors._same_snapshot(vendors._peer_intent_snapshot(state_path), before_state)
    assert vendors._same_snapshot(
        vendors._peer_provision_snapshot(peer_provision_path), before_provision,
    )


def test_peer_r2_lost_remove_response_rerun_reconciles_without_second_dispatch(tmp_path):
    """REMOVE_DISPATCHED is a durable one-shot fence across coordinator restarts."""
    (
        provision,
        _anchor_path,
        state_path,
        peer_provision_path,
        _state,
        _peer_provision,
    ) = _seed_peer_provision_committed(tmp_path)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    exact_peer = _peer_record(
        peer_name,
        id=_PEER_CREATED_UUID,
        folder_id=provision["folder_id"],
    )

    first_transport = _PeerTransport()
    first_transport.set_candidates_sequence([exact_peer], [exact_peer])
    first_transport.remove_response = None
    first_out = io.StringIO()
    first_code = _rollback_main(
        tmp_path,
        provision,
        first_transport,
        intent_path=state_path,
        peer_provision_path=peer_provision_path,
        out=first_out,
    )
    assert first_code == 3
    assert json.loads(first_out.getvalue())["effect"] == "REMOVE_EFFECT_UNKNOWN"
    assert [call[0] for call in first_transport.calls].count("remove") == 1
    assert (
        vendors._peer_intent_snapshot(state_path).document["phase"]
        == vendors.PEER_PHASE_REMOVE_DISPATCHED
    )

    second_transport = _PeerTransport()
    second_transport.set_candidates_sequence([exact_peer], [])
    second_transport.remove_response = _peer_remove_success()
    second_out = io.StringIO()
    second_code = _rollback_main(
        tmp_path,
        provision,
        second_transport,
        intent_path=state_path,
        peer_provision_path=peer_provision_path,
        out=second_out,
    )
    second_receipt = json.loads(second_out.getvalue())
    assert second_code == 0
    assert second_receipt["effect"] == "ROLLBACK_VERIFIED"
    assert second_receipt["predicates"]["dispatched"] is False
    assert second_receipt["predicates"]["reconciled"] is True
    assert [call[0] for call in second_transport.calls].count("remove") == 0
    assert (
        vendors._peer_intent_snapshot(state_path).document["phase"]
        == vendors.PEER_PHASE_ROLLBACK_VERIFIED
    )


@pytest.mark.parametrize(
    ("response_id", "census_id"),
    (
        (_PEER_CREATED_UUID.upper(), _PEER_CREATED_UUID),
        (_PEER_CREATED_UUID, _PEER_CREATED_UUID.upper()),
    ),
)
def test_peer_r2_uuid_case_variants_collapse_to_one_canonical_identity(response_id, census_id):
    """UUID casing cannot create a response/census contradiction or a second identity."""
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(_peer_name(), id=census_id)])
    transport.create_response = _peer_create_success(profile_id=response_id)
    client = _peer_client(transport)

    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER,
        anchor_profile_id=_PEER_ANCHOR,
        intent_present=False,
        commit_intent=lambda: vendors.CREATED_THIS_CALL,
    )

    assert receipt["effect"] == "PROFILE_STOPPED_PROVEN"
    assert receipt["predicates"]["exact_readback"] is True
    assert client._peer_profile_id == _PEER_CREATED_UUID
    assert receipt["digests"]["peer_profile"] == core.sha256_hex(_PEER_CREATED_UUID)
    assert [call[0] for call in transport.calls].count("create") == 1


@pytest.mark.parametrize(
    ("case", "mutation"),
    (
        ("wrong_source_generation", {"source_generation": "f" * 64}),
        ("wrong_lifecycle_generation", {"lifecycle_generation": "e" * 64}),
        ("pf1_active", {"pf1_active": True}),
        ("install1_active", {"install1_active": True}),
        ("expired", {"valid_until": "2026-08-23T11:59:59Z"}),
        ("future_observation", {"observed_at": "2026-08-23T12:00:01Z"}),
    ),
)
def test_peer_r2_invalid_ownership_receipt_refuses_before_secret_or_vendor(
    tmp_path, case, mutation,
):
    """Every stale, positive, or misbound release receipt fails at the first gate."""
    (
        provision,
        anchor_path,
        state_path,
        peer_provision_path,
        state,
        peer_provision,
    ) = _seed_peer_provision_committed(tmp_path)
    invalid_receipt = _peer_ownership_receipt(state, peer_provision, **mutation)
    calls = []

    def _unexpected(label):
        def _call(*_args, **_kwargs):
            calls.append(label)
            raise AssertionError(f"{case} receipt reached {label}")
        return _call

    out = io.StringIO()
    code = vendors._run_coordinator_peer_rollback(  # noqa: SLF001
        ["--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=out,
        ownership_receipt_loader=lambda: invalid_receipt,
        bindings_loader=_unexpected("anchor/bindings"),
        environment_loader=_unexpected("environment"),
        credential_stream_factory=_unexpected("credential"),
        client_factory=_unexpected("client"),
        now=_NOW,
    )

    receipt = json.loads(out.getvalue())
    assert code == 2
    assert receipt["verdict"] == "REFUSED"
    assert receipt["code"] == "BINDINGS_UNAVAILABLE"
    assert calls == []
    assert vendors._peer_intent_snapshot(state_path).document["phase"] == (
        vendors.PEER_PHASE_PROVISION_COMMITTED
    )


@pytest.mark.parametrize("second_fact", ("expired", "revoked"))
def test_peer_r2_rollback_reloads_fresh_ownership_receipt_before_remove(
    tmp_path, second_fact,
):
    """A pre-secret receipt cannot authorize a later remove after expiry/revocation."""
    (
        provision,
        anchor_path,
        state_path,
        peer_provision_path,
        state,
        peer_provision,
    ) = _seed_peer_provision_committed(tmp_path)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    exact_peer = _peer_record(
        peer_name,
        id=_PEER_CREATED_UUID,
        folder_id=provision["folder_id"],
    )
    transport = _PeerTransport()
    transport.set_candidates_sequence([exact_peer])
    transport.remove_response = _peer_remove_success()
    valid = _peer_ownership_receipt(state, peer_provision)
    refreshed = (
        dict(valid, pf1_active=True)
        if second_fact == "revoked"
        else valid
    )
    receipts = iter((valid, refreshed))
    receipt_calls = []

    def _load_receipt():
        receipt_calls.append(True)
        return next(receipts)

    times = iter((
        _NOW,
        datetime(2026, 8, 23, 12, 2, tzinfo=timezone.utc)
        if second_fact == "expired"
        else _NOW,
    ))
    out = io.StringIO()
    code = vendors._run_coordinator_peer_rollback(  # noqa: SLF001
        ["--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=out,
        ownership_receipt_loader=_load_receipt,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"cred"),
        client_factory=lambda: transport,
        clock=lambda: next(times),
    )

    receipt = json.loads(out.getvalue())
    assert code == 2
    assert receipt["verdict"] == "REFUSED"
    assert receipt["effect"] == "NONE"
    assert receipt["code"] == "PROVISION_MISSING"
    assert len(receipt_calls) == 2
    assert [call[0] for call in transport.calls].count("remove") == 0
    assert vendors._peer_intent_snapshot(state_path).document["phase"] == (
        vendors.PEER_PHASE_PROVISION_COMMITTED
    )


@pytest.mark.parametrize(
    ("operation", "authorization_kwargs"),
    (
        ("create-peer-profile", {"create_authorization": vendors.ROLLBACK_PEER_AUTHORIZATION}),
        ("rollback-peer-profile", {"rollback_authorization": vendors.CREATE_PEER_AUTHORIZATION}),
        ("create-peer-profile", {"create_authorization": vendors._PeerAuthorization()}),
        ("rollback-peer-profile", {"rollback_authorization": vendors._PeerAuthorization()}),
        (
            "create-peer-profile",
            {
                "create_authorization": vendors.CREATE_PEER_AUTHORIZATION,
                "rollback_authorization": vendors.ROLLBACK_PEER_AUTHORIZATION,
            },
        ),
        (
            "rollback-peer-profile",
            {
                "create_authorization": vendors.CREATE_PEER_AUTHORIZATION,
                "rollback_authorization": vendors.ROLLBACK_PEER_AUTHORIZATION,
            },
        ),
    ),
)
def test_peer_r2_wrong_forged_or_cross_operation_authorization_is_inert(
    tmp_path, operation, authorization_kwargs,
):
    """Only the exact one-operation capability may cross the coordinator boundary."""
    calls = []

    def _unexpected(label):
        def _call(*_args, **_kwargs):
            calls.append(label)
            raise AssertionError(f"bad authorization reached {label}")
        return _call

    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — authorization seam under test
        [operation, "--vendor", "multilogin", "--provision-path", str(tmp_path / "anchor.json")],
        peer_intent_path=tmp_path / "peer-state.json",
        peer_provision_path=tmp_path / "peer-provision.json",
        stdout=out,
        bindings_loader=_unexpected("anchor/bindings"),
        environment_loader=_unexpected("environment"),
        credential_stream_factory=_unexpected("credential"),
        client_factory=_unexpected("client"),
        now=_NOW,
        **authorization_kwargs,
    )

    receipt = json.loads(out.getvalue())
    assert code == 2
    assert receipt["verdict"] == "REFUSED"
    assert receipt["code"] == "DISALLOWED_TARGET"
    assert calls == []
    assert not (tmp_path / "peer-state.json").exists()
    assert not (tmp_path / "peer-provision.json").exists()


@pytest.mark.parametrize("coordinate", ("state", "provision"))
@pytest.mark.parametrize("alias_kind", ("symlink", "hardlink"))
def test_peer_r2_path_aliases_refuse_before_anchor_secret_or_vendor(
    tmp_path, coordinate, alias_kind,
):
    """Neither lifecycle coordinate may begin as a symlink or multiply-linked inode."""
    state_path = tmp_path / "peer-state.json"
    peer_provision_path = tmp_path / "peer-provision.json"
    selected = state_path if coordinate == "state" else peer_provision_path
    victim = tmp_path / f"{coordinate}-victim.json"
    victim.write_text("{}\n", encoding="utf-8")
    victim.chmod(0o600)
    before = (victim.read_bytes(), victim.stat().st_ino)
    if alias_kind == "symlink":
        selected.symlink_to(victim)
    else:
        os.link(victim, selected)
    anchor_path = _write_provision(tmp_path, _valid_provision("multilogin"))
    calls = []

    def _unexpected(label):
        def _call(*_args, **_kwargs):
            calls.append(label)
            raise AssertionError(f"{coordinate} {alias_kind} reached {label}")
        return _call

    out = io.StringIO()
    code = vendors._run_coordinator_peer_create(  # noqa: SLF001
        ["--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=out,
        bindings_loader=_unexpected("anchor/bindings"),
        environment_loader=_unexpected("environment"),
        credential_stream_factory=_unexpected("credential"),
        client_factory=_unexpected("client"),
        now=_NOW,
    )

    assert code == 2
    assert json.loads(out.getvalue())["code"] == "PROVISION_MISSING"
    assert calls == []
    assert (victim.read_bytes(), victim.stat().st_ino) == before


@pytest.mark.parametrize("coordinate", ("state", "provision"))
def test_peer_r2_foreign_inode_replacement_between_preflights_refuses_presecret(
    tmp_path, coordinate,
):
    """A same-byte path swap after environment census never inherits authority."""
    (
        provision,
        anchor_path,
        state_path,
        peer_provision_path,
        _state,
        _peer_provision,
    ) = _seed_peer_provision_committed(tmp_path)
    selected = state_path if coordinate == "state" else peer_provision_path
    old_inode = selected.stat().st_ino
    replacement_inode = {"value": None}
    calls = []
    base_environment_loader = _environment_loader_for(provision)

    def _replace_during_environment():
        calls.append("environment")
        replacement = tmp_path / f"foreign-{coordinate}.json"
        replacement.write_bytes(selected.read_bytes())
        replacement.chmod(0o600)
        replacement_inode["value"] = replacement.stat().st_ino
        os.replace(replacement, selected)
        return base_environment_loader()

    def _unexpected(label):
        def _call(*_args, **_kwargs):
            calls.append(label)
            raise AssertionError(f"foreign {coordinate} replacement reached {label}")
        return _call

    out = io.StringIO()
    code = vendors._run_coordinator_peer_create(  # noqa: SLF001
        ["--vendor", "multilogin", "--provision-path", str(anchor_path)],
        peer_intent_path=state_path,
        peer_provision_path=peer_provision_path,
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_replace_during_environment,
        credential_stream_factory=_unexpected("credential"),
        client_factory=_unexpected("client"),
        now=_NOW,
    )

    assert code == 2
    assert json.loads(out.getvalue())["code"] == "PROVISION_MISSING"
    assert calls == ["environment"]
    assert selected.stat().st_ino == replacement_inode["value"]
    assert selected.stat().st_ino != old_inode


def test_peer_r2_remove_fence_replacement_never_allows_second_dispatch(tmp_path):
    """A path rollback after the durable remove claim cannot erase its fence."""
    provision, _anchor, state_path, peer_path, _state, _peer = (
        _seed_peer_provision_committed(tmp_path)
    )
    preclaim_raw = state_path.read_bytes()
    peer_name = vendors.peer_profile_name(
        provision["folder_id"], provision["profile_id"]
    )
    exact = _peer_record(
        peer_name,
        id=_PEER_CREATED_UUID,
        folder_id=provision["folder_id"],
    )

    class ReplaceAfterClaimTransport(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([exact], [exact])
            self.remove_response = None

        def _mlx_profile_remove(self, credential, profile_id):
            replacement = tmp_path / "foreign-preclaim.json"
            replacement.write_bytes(preclaim_raw)
            replacement.chmod(0o600)
            os.replace(replacement, state_path)
            return super()._mlx_profile_remove(credential, profile_id)

    first_transport = ReplaceAfterClaimTransport()
    first_out = io.StringIO()
    assert _rollback_main(
        tmp_path,
        provision,
        first_transport,
        intent_path=state_path,
        peer_provision_path=peer_path,
        out=first_out,
    ) == 3
    assert sum(call[0] == "remove" for call in first_transport.calls) == 1

    second_transport = _PeerTransport()
    second_transport.set_candidates_sequence([exact], [exact])
    second_transport.remove_response = None
    second_out = io.StringIO()
    assert _rollback_main(
        tmp_path,
        provision,
        second_transport,
        intent_path=state_path,
        peer_provision_path=peer_path,
        out=second_out,
    ) != 0
    assert sum(call[0] == "remove" for call in second_transport.calls) == 0


def test_peer_r2_create_claim_replacement_never_allows_second_dispatch(tmp_path):
    """A foreign tombstone cannot replace a dispatched create claim and re-arm."""
    provision = _valid_provision("multilogin")
    anchor = _write_provision(tmp_path, provision)
    state_path = tmp_path / "peer-state.json"
    peer_path = tmp_path / "peer-provision.json"
    _prepare_peer_lifecycle(provision, state_path, peer_path)

    class ReplaceAfterClaimTransport(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([], [])
            self.create_response = None

        def _mlx_profile_create(self, credential, folder_id, name):
            claimed = vendors._peer_intent_snapshot(state_path)
            tombstone = dict(claimed.document)
            tombstone["phase"] = vendors.PEER_PHASE_CREATE_AUTH_REJECTED
            replacement = tmp_path / "foreign-tombstone.json"
            replacement.write_bytes(vendors._canonical_private_bytes(tombstone))
            replacement.chmod(0o600)
            os.replace(replacement, state_path)
            return super()._mlx_profile_create(credential, folder_id, name)

    def _run(transport):
        out = io.StringIO()
        rc = _authorized_peer_main(
            [
                "create-peer-profile",
                "--vendor",
                "multilogin",
                "--provision-path",
                str(anchor),
            ],
            peer_intent_path=state_path,
            peer_provision_path=peer_path,
            stdout=out,
            bindings_loader=_no_collision_loader,
            environment_loader=_environment_loader_for(provision),
            credential_stream_factory=lambda: io.BytesIO(b"credential"),
            client_factory=lambda: transport,
            now=_NOW,
        )
        return rc, json.loads(out.getvalue())

    first_transport = ReplaceAfterClaimTransport()
    assert _run(first_transport)[0] == 3
    assert sum(call[0] == "create" for call in first_transport.calls) == 1

    second_transport = _PeerTransport()
    second_transport.set_candidates_sequence([], [])
    second_transport.create_response = None
    assert _run(second_transport)[0] != 0
    assert sum(call[0] == "create" for call in second_transport.calls) == 0


def test_peer_r2_refused_provision_replacement_is_never_reaccepted(
    tmp_path, monkeypatch,
):
    """A byte-identical foreign provision remains foreign on every later run."""
    path = tmp_path / "peer-provision.json"
    replacement = tmp_path / "foreign-provision.json"
    real_fsync = os.fsync
    injected = {"value": False}

    def _replace_at_durability_boundary(fd):
        real_fsync(fd)
        if not injected["value"] and path.exists():
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, path)
            injected["value"] = True

    monkeypatch.setattr(vendors.os, "fsync", _replace_at_durability_boundary)
    current_environment_snapshot = _seal_realm1_environment(_realm1_environment())
    assert current_environment_snapshot is not None
    first = vendors._write_peer_provision(
        path,
        profile_id=_PEER_CREATED_UUID,
        folder_id=_PEER_FOLDER,
        bindings_loader=_no_collision_loader,
        now=_NOW,
        current_environment_snapshot=current_environment_snapshot,
    )
    assert first[0] is False

    monkeypatch.setattr(vendors.os, "fsync", real_fsync)
    second = vendors._write_peer_provision(
        path,
        profile_id=_PEER_CREATED_UUID,
        folder_id=_PEER_FOLDER,
        bindings_loader=_no_collision_loader,
        now=_NOW,
        current_environment_snapshot=current_environment_snapshot,
    )
    assert second[0] is False


def test_peer_r2_deleted_create_claim_never_allows_second_dispatch(tmp_path):
    """Deleting the dispatched claim cannot recreate a virgin namespace."""
    provision = _valid_provision("multilogin")
    anchor = _write_provision(tmp_path, provision)
    state_path = tmp_path / "peer-state.json"
    peer_path = tmp_path / "peer-provision.json"
    assert vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=vendors.peer_profile_name(
            provision["folder_id"], provision["profile_id"]
        ),
        peer_provision_path=peer_path,
    ) == vendors.CREATED_THIS_CALL

    class UnlinkAfterClaimTransport(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([], [])
            self.create_response = None

        def _mlx_profile_create(self, credential, folder_id, name):
            claimed = vendors._peer_intent_snapshot(state_path)
            assert claimed is not None
            assert claimed.document["phase"] == vendors.PEER_PHASE_CREATE_CLAIMED
            state_path.unlink()
            return super()._mlx_profile_create(credential, folder_id, name)

    def _run(transport):
        out = io.StringIO()
        code = _authorized_peer_main(
            [
                "create-peer-profile",
                "--vendor",
                "multilogin",
                "--provision-path",
                str(anchor),
            ],
            peer_intent_path=state_path,
            peer_provision_path=peer_path,
            stdout=out,
            bindings_loader=_no_collision_loader,
            environment_loader=_environment_loader_for(provision),
            credential_stream_factory=lambda: io.BytesIO(b"credential"),
            client_factory=lambda: transport,
            now=_NOW,
        )
        return code, json.loads(out.getvalue())

    first = UnlinkAfterClaimTransport()
    assert _run(first)[0] == 3
    assert sum(call[0] == "create" for call in first.calls) == 1
    assert not state_path.exists()

    second = _PeerTransport()
    second.set_candidates_sequence([], [])
    second.create_response = None
    assert _run(second)[0] != 0
    assert sum(call[0] == "create" for call in second.calls) == 0


def test_peer_r2_completed_create_refuses_stale_state_after_census(tmp_path):
    """A completed rerun cannot PASS after its lifecycle path is replaced."""
    provision, anchor, state_path, peer_path, before_state, _peer = (
        _seed_peer_provision_committed(tmp_path)
    )
    peer_name = vendors.peer_profile_name(
        provision["folder_id"], provision["profile_id"]
    )
    exact = _peer_record(
        peer_name,
        id=_PEER_CREATED_UUID,
        folder_id=provision["folder_id"],
    )

    class ReplaceDuringCensus(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([exact], [exact])
            self.replaced = False

        def _mlx_profile_search(self, credential, folder_id, *, offset):
            if offset == 0 and not self.replaced:
                replacement = tmp_path / "foreign-completed-state.json"
                replacement.write_bytes(state_path.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, state_path)
                self.replaced = True
            return super()._mlx_profile_search(credential, folder_id, offset=offset)

    transport = ReplaceDuringCensus()
    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile",
            "--vendor",
            "multilogin",
            "--provision-path",
            str(anchor),
        ],
        peer_intent_path=state_path,
        peer_provision_path=peer_path,
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"credential"),
        client_factory=lambda: transport,
        now=_NOW,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert sum(call[0] == "create" for call in transport.calls) == 0
    assert state_path.stat().st_ino != before_state.st_ino
    assert vendors._peer_intent_snapshot(state_path) is None


def test_peer_r2_completed_create_holds_if_genesis_witness_vanishes_during_census(
    tmp_path,
):
    """A completed create cannot PASS after losing its cross-bound witness."""
    provision, anchor, state_path, peer_path, _state, _peer = (
        _seed_peer_provision_committed(tmp_path)
    )
    witness_path = vendors._peer_genesis_witness_path(state_path)
    peer_name = vendors.peer_profile_name(
        provision["folder_id"], provision["profile_id"],
    )
    exact = _peer_record(
        peer_name,
        id=_PEER_CREATED_UUID,
        folder_id=provision["folder_id"],
    )

    class _UnlinkWitnessDuringCensus(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([exact], [exact])
            self.unlinked = False

        def _mlx_profile_search(self, credential, folder_id, *, offset):
            response = super()._mlx_profile_search(
                credential, folder_id, offset=offset,
            )
            if offset == 0 and not self.unlinked:
                witness_path.unlink()
                self.unlinked = True
            return response

    transport = _UnlinkWitnessDuringCensus()
    out = io.StringIO()
    code = _authorized_peer_main(
        [
            "create-peer-profile",
            "--vendor",
            "multilogin",
            "--provision-path",
            str(anchor),
        ],
        peer_intent_path=state_path,
        peer_provision_path=peer_path,
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: io.BytesIO(b"credential"),
        client_factory=lambda: transport,
        now=_NOW,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert sum(call[0] == "create" for call in transport.calls) == 0
    assert not witness_path.exists()


def test_peer_r2_rollback_holds_if_genesis_witness_vanishes_after_dispatch(
    tmp_path,
):
    """Witness loss after remove dispatch prevents a false final PASS."""
    provision, _anchor, state_path, peer_path, _state, _peer = (
        _seed_peer_provision_committed(tmp_path)
    )
    witness_path = vendors._peer_genesis_witness_path(state_path)
    peer_name = vendors.peer_profile_name(
        provision["folder_id"], provision["profile_id"],
    )
    exact = _peer_record(
        peer_name,
        id=_PEER_CREATED_UUID,
        folder_id=provision["folder_id"],
    )

    class _UnlinkWitnessAfterRemoveDispatch(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([exact], [])
            self.remove_response = _peer_remove_success()

        def _mlx_profile_remove(self, credential, profile_id):
            response = super()._mlx_profile_remove(credential, profile_id)
            witness_path.unlink()
            return response

    transport = _UnlinkWitnessAfterRemoveDispatch()
    out = io.StringIO()
    code = _rollback_main(
        tmp_path,
        provision,
        transport,
        intent_path=state_path,
        peer_provision_path=peer_path,
        out=out,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "REMOVE_EFFECT_UNKNOWN"
    assert sum(call[0] == "remove" for call in transport.calls) == 1
    assert not witness_path.exists()


def test_peer_r2_completed_rollback_refuses_stale_state_after_census(tmp_path):
    """An idempotent rollback cannot PASS from a replaced lifecycle inode."""
    provision, _anchor, state_path, peer_path, state, peer = (
        _seed_peer_provision_committed(tmp_path)
    )
    ownership = _peer_ownership_receipt(state, peer)
    dispatched = vendors._transition_peer_intent(
        state_path,
        expected=state,
        phase=vendors.PEER_PHASE_REMOVE_DISPATCHED,
        peer_profile_id=_PEER_CREATED_UUID,
        ownership_fact=ownership,
    )
    rolled_back = vendors._transition_peer_intent(
        state_path,
        expected=dispatched,
        phase=vendors.PEER_PHASE_ROLLBACK_VERIFIED,
        peer_profile_id=_PEER_CREATED_UUID,
    )
    assert rolled_back is not None

    class ReplaceDuringCensus(_PeerTransport):
        def __init__(self):
            super().__init__()
            self.set_candidates_sequence([])
            self.replaced = False

        def _mlx_profile_search(self, credential, folder_id, *, offset):
            if offset == 0 and not self.replaced:
                replacement = tmp_path / "foreign-rollback-state.json"
                replacement.write_bytes(state_path.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, state_path)
                self.replaced = True
            return super()._mlx_profile_search(credential, folder_id, offset=offset)

    transport = ReplaceDuringCensus()
    out = io.StringIO()
    code = _rollback_main(
        tmp_path,
        provision,
        transport,
        intent_path=state_path,
        peer_provision_path=peer_path,
        out=out,
    )

    receipt = json.loads(out.getvalue())
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["effect"] == "REMOVE_EFFECT_UNKNOWN"
    assert sum(call[0] == "remove" for call in transport.calls) == 0
    assert state_path.stat().st_ino != rolled_back.st_ino
    assert vendors._peer_intent_snapshot(state_path) is None


# --- REALM1-C1 first-rollout existing-v3-anchor bootstrap -----------------


def _peer_bootstrap_preimage(tmp_path):
    """Seed the real first-rollout shape: exact v3 anchor, no peer records."""
    anchor_path = tmp_path / "anchor.json"
    state_path = tmp_path / "peer-state.json"
    provision_path = tmp_path / "peer-provision.json"
    fence_path = tmp_path / "peer-bootstrap.json"
    provision = _stored_provision(_valid_provision("multilogin"))
    outcome, anchor = vendors._exclusive_private_json(  # noqa: SLF001
        anchor_path, provision,
    )
    assert outcome == vendors.CREATED_THIS_CALL
    assert anchor is not None
    return provision, anchor_path, state_path, provision_path, fence_path, anchor


_DEFAULT_BOOTSTRAP_AUTHORIZATION = object()


def _peer_bootstrap_census(provision, *, running=False):
    return {
        "multilogin": [{
            "workspace_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            "profile_id": provision["profile_id"],
            "folder_id": provision["folder_id"],
            "running": running,
        }],
        "gologin": [
            {"profile_id": "111111111111111111111111", "running": True},
            {"profile_id": "222222222222222222222222", "running": True},
            {"profile_id": "333333333333333333333333", "running": True},
        ],
    }


def _peer_bootstrap_bindings_path(anchor_path):
    path = Path(anchor_path).with_name("surface-bindings.json")
    if not path.exists():
        path.write_bytes(vendors._canonical_private_bytes(_binding_doc()))  # noqa: SLF001
        path.chmod(0o600)
    return path


def _mint_peer_bootstrap_authorization(
    provision, anchor_path, *, bindings_path=None, census_loader=None,
):
    bindings_path = bindings_path or _peer_bootstrap_bindings_path(anchor_path)
    census_loader = census_loader or (
        lambda: _peer_bootstrap_census(provision)
    )
    mint = getattr(vendors, "_mint_peer_bootstrap_evidence", None)
    assert callable(mint), "the evidence-bound bootstrap mint is missing"
    authorization = mint(
        operation=vendors.PEER_BOOTSTRAP_OPERATION_KEY,
        anchor_path=anchor_path,
        bindings_path=bindings_path,
        census_loader=census_loader,
        now=_NOW,
    )
    assert authorization is not None, "the exact bootstrap evidence did not mint"
    return authorization, bindings_path, census_loader


def _bootstrap_existing_peer(
    anchor_path, state_path, provision_path, fence_path,
    *, authorization=_DEFAULT_BOOTSTRAP_AUTHORIZATION, bindings_path=None,
    census_loader=None,
):
    bootstrap = getattr(
        vendors, "_bootstrap_peer_lifecycle_for_existing_anchor", None,
    )
    assert callable(bootstrap), "the explicit existing-v3 bootstrap is missing"
    if authorization is _DEFAULT_BOOTSTRAP_AUTHORIZATION:
        provision = json.loads(Path(anchor_path).read_text(encoding="utf-8"))
        authorization, bindings_path, census_loader = (
            _mint_peer_bootstrap_authorization(
                provision,
                anchor_path,
                bindings_path=bindings_path,
                census_loader=census_loader,
            )
        )
    else:
        bindings_path = bindings_path or _peer_bootstrap_bindings_path(anchor_path)
        census_loader = census_loader or (
            lambda: _peer_bootstrap_census(
                json.loads(Path(anchor_path).read_text(encoding="utf-8")),
            )
        )
    return bootstrap(
        authorization=authorization,
        anchor_path=anchor_path,
        bindings_path=bindings_path,
        census_loader=census_loader,
        now=_NOW,
        state_path=state_path,
        peer_provision_path=provision_path,
        bootstrap_fence_path=fence_path,
    )


@pytest.mark.parametrize("target_name", ("anchor", "bindings"))
def test_peer_bootstrap_capability_refuses_same_byte_path_replacement(
    tmp_path, target_name,
):
    """Held descriptors make same-byte unlink/recreate a different identity."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    target = anchor_path if target_name == "anchor" else bindings_path
    original = target.read_bytes()
    target.unlink()
    target.write_bytes(original)
    target.chmod(0o600)

    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.REFUSED
    assert not fence_path.exists()
    assert not state_path.exists()


@pytest.mark.parametrize("target_name", ("anchor", "bindings"))
def test_peer_bootstrap_capability_refuses_valid_changed_source_after_mint(
    tmp_path, target_name,
):
    """A different valid anchor or bindings document is still unauthorized."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    if target_name == "anchor":
        replacement_document = dict(provision)
        replacement_document["profile_id"] = _PEER_ALT_UUID
        replacement_document["folder_id"] = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        target = anchor_path
    else:
        replacement_document = _binding_doc()
        replacement_document["bindings"][0]["locator"]["url"] = (
            "https://chatgpt.com/c/replacement-binding"
        )
        assert sb.validate_bindings_document(replacement_document) == []
        target = bindings_path
    replacement = tmp_path / f"replacement-{target_name}.json"
    replacement.write_bytes(vendors._canonical_private_bytes(replacement_document))  # noqa: SLF001
    replacement.chmod(0o600)
    os.replace(replacement, target)

    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.REFUSED
    assert not fence_path.exists()
    assert not state_path.exists()


def test_peer_bootstrap_capability_refuses_reduced_census_change_after_mint(tmp_path):
    """A fresh helper-side census must equal the exact coordinator evidence."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    current = [_peer_bootstrap_census(provision)]
    census_loader = lambda: current[0]
    authorization, bindings_path, _loader = _mint_peer_bootstrap_authorization(
        provision, anchor_path, census_loader=census_loader,
    )
    current[0] = _peer_bootstrap_census(provision, running=True)

    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.REFUSED
    assert not fence_path.exists()


def test_peer_bootstrap_capability_closes_held_fds_when_census_probe_raises(tmp_path):
    """An unexpected helper-side probe failure cannot leak reusable evidence."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, _census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    held_fds = (authorization._anchor_fd, authorization._bindings_fd)  # noqa: SLF001

    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=lambda: (_ for _ in ()).throw(RuntimeError("probe failed")),
    ) == vendors.REFUSED
    for held_fd in held_fds:
        with pytest.raises(OSError):
            os.fstat(held_fd)
    assert not fence_path.exists()


def test_peer_bootstrap_capability_is_one_use_after_success_and_refusal(tmp_path):
    """Consumption is monotonic regardless of the first call's outcome."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    kwargs = {
        "authorization": authorization,
        "bindings_path": bindings_path,
        "census_loader": census_loader,
    }
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path, **kwargs,
    ) == vendors.CREATED_THIS_CALL
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path, **kwargs,
    ) == vendors.REFUSED

    refusal_root = tmp_path / "refusal"
    refusal_root.mkdir(mode=0o700)
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(refusal_root)
    )
    current = [_peer_bootstrap_census(provision)]
    census_loader = lambda: current[0]
    refusal_authorization, bindings_path, _loader = (
        _mint_peer_bootstrap_authorization(
            provision, anchor_path, census_loader=census_loader,
        )
    )
    current[0] = _peer_bootstrap_census(provision, running=True)
    refusal_kwargs = {
        "authorization": refusal_authorization,
        "bindings_path": bindings_path,
        "census_loader": census_loader,
    }
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path, **refusal_kwargs,
    ) == vendors.REFUSED
    current[0] = _peer_bootstrap_census(provision)
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path, **refusal_kwargs,
    ) == vendors.REFUSED
    assert not fence_path.exists()
    assert not state_path.exists()


def test_peer_bootstrap_capability_same_instance_has_one_atomic_consumer(tmp_path):
    """Two callers racing one capability cannot both pass its consume edge."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    barrier = threading.Barrier(2)
    outcomes = []

    def _run():
        barrier.wait()
        outcomes.append(_bootstrap_existing_peer(
            anchor_path,
            state_path,
            peer_path,
            fence_path,
            authorization=authorization,
            bindings_path=bindings_path,
            census_loader=census_loader,
        ))

    workers = [threading.Thread(target=_run) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()

    assert outcomes.count(vendors.CREATED_THIS_CALL) == 1
    assert outcomes.count(vendors.REFUSED) == 1
    _assert_completed_bootstrap(
        provision, anchor_path, state_path, peer_path, fence_path,
    )


@pytest.mark.parametrize("mutation", ("operation", "generation", "pid", "cross_anchor"))
def test_peer_bootstrap_capability_refuses_wrong_binding(tmp_path, mutation):
    """Operation, generation, process and anchor bindings are not transferable."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    if mutation == "operation":
        authorization._operation = "wrong-operation"  # noqa: SLF001
    elif mutation == "generation":
        authorization._generation = "f" * 64  # noqa: SLF001
    elif mutation == "pid":
        authorization._mint_pid = os.getpid() + 1  # noqa: SLF001
    else:
        replacement = tmp_path / "other-anchor.json"
        replacement.write_bytes(anchor_path.read_bytes())
        replacement.chmod(0o600)
        anchor_path = replacement

    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.REFUSED
    assert not fence_path.exists()


def test_peer_bootstrap_capability_is_noncopyable_and_closes_held_fds_once(tmp_path):
    """The evidence is process-private and releases both kernel identities."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    held_fds = (authorization._anchor_fd, authorization._bindings_fd)  # noqa: SLF001
    with pytest.raises(TypeError):
        copy.copy(authorization)
    with pytest.raises(TypeError):
        pickle.dumps(authorization)
    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.CREATED_THIS_CALL
    for held_fd in held_fds:
        with pytest.raises(OSError):
            os.fstat(held_fd)
    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.REFUSED


def _assert_completed_bootstrap(
    provision, anchor_path, state_path, provision_path, fence_path,
):
    fence_reader = getattr(vendors, "_peer_bootstrap_fence_snapshot", None)
    assert callable(fence_reader), "the bootstrap fence reader is missing"
    fence = fence_reader(fence_path)
    state = vendors._peer_intent_snapshot(state_path)
    witness = vendors._peer_genesis_witness_snapshot(
        vendors._peer_genesis_witness_path(state_path),
    )
    anchor = vendors._optional_private_json_snapshot(anchor_path)
    assert fence is not None and state is not None and witness is not None
    assert anchor is not None
    assert fence.document["phase"] == vendors.PEER_BOOTSTRAP_PHASE_COMPLETE
    assert fence.document["anchor_document_digest"] == anchor.sha256
    assert (fence.document["anchor_dev"], fence.document["anchor_ino"]) == (
        anchor.st_dev, anchor.st_ino,
    )
    assert fence.document["state_document_digest"] == state.sha256
    assert (fence.document["state_dev"], fence.document["state_ino"]) == (
        state.st_dev, state.st_ino,
    )
    assert fence.document["witness_document_digest"] == witness.sha256
    assert (fence.document["witness_dev"], fence.document["witness_ino"]) == (
        witness.st_dev, witness.st_ino,
    )
    assert state.document["phase"] == vendors.PEER_PHASE_INITIALIZED
    checked_state, checked_provision = vendors._preflight_peer_paths(
        operation="create-peer-profile",
        state_path=state_path,
        provision_path=provision_path,
    )
    assert vendors._same_snapshot(checked_state, state)
    assert checked_provision is None
    return fence, state, witness, anchor


def test_peer_bootstrap_red_actual_existing_v3_preimage_reaches_genesis_without_secret_or_vendor(
    tmp_path, monkeypatch,
):
    """The exact old-estate v3 anchor is upgraded only by the new local seam."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    with pytest.raises(vendors._PeerStateRefusal):
        vendors._preflight_peer_paths(
            operation="create-peer-profile",
            state_path=state_path,
            provision_path=peer_path,
        )

    monkeypatch.setattr(
        vendors,
        "_open_keychain_credential_pipe",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("bootstrap must not open Keychain"),
        ),
    )
    monkeypatch.setattr(
        vendors,
        "BoundedHttpClient",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("bootstrap must not construct vendor HTTP"),
        ),
    )

    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.CREATED_THIS_CALL
    _assert_completed_bootstrap(
        provision, anchor_path, state_path, peer_path, fence_path,
    )


def test_peer_bootstrap_complete_replay_is_read_only_and_inode_exact(tmp_path):
    """A COMPLETE fence reconciles without rewriting any durable record."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.CREATED_THIS_CALL
    first = _assert_completed_bootstrap(
        provision, anchor_path, state_path, peer_path, fence_path,
    )
    before = tuple((item.st_dev, item.st_ino, item.sha256) for item in first)

    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.EXISTING_EXACT
    second = _assert_completed_bootstrap(
        provision, anchor_path, state_path, peer_path, fence_path,
    )
    assert tuple((item.st_dev, item.st_ino, item.sha256) for item in second) == before


@pytest.mark.parametrize(
    "crash_point",
    (
        "after_fence",
        "after_witness",
        "after_state",
        "before_fence_complete",
        "after_fence_complete",
    ),
)
def test_peer_bootstrap_pending_recovers_each_declared_crash_window(
    tmp_path, monkeypatch, crash_point,
):
    """Every exact PENDING prefix finishes once; no alternate genesis appears."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    witness_path = vendors._peer_genesis_witness_path(state_path)
    real_create = vendors._create_self_bound_private_record
    real_rewrite = vendors._rewrite_private_record_in_parent

    def _create(target, *args, **kwargs):
        target = Path(target)
        blocked = (
            crash_point == "after_fence" and target == witness_path
        ) or (
            crash_point == "after_witness" and target == state_path
        )
        return None if blocked else real_create(target, *args, **kwargs)

    def _rewrite(target, *args, **kwargs):
        target = Path(target)
        phase = kwargs.get("next_document", {}).get("phase")
        if (
            crash_point == "after_state"
            and target == witness_path
            and phase == vendors._PEER_GENESIS_WITNESS_BOUND
        ):
            return None
        if (
            crash_point in ("before_fence_complete", "after_fence_complete")
            and target == fence_path
            and phase == vendors.PEER_BOOTSTRAP_PHASE_COMPLETE
        ):
            if crash_point == "before_fence_complete":
                return None
            real_rewrite(target, *args, **kwargs)
            return None
        return real_rewrite(target, *args, **kwargs)

    monkeypatch.setattr(vendors, "_create_self_bound_private_record", _create)
    monkeypatch.setattr(vendors, "_rewrite_private_record_in_parent", _rewrite)
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.REFUSED

    monkeypatch.setattr(vendors, "_create_self_bound_private_record", real_create)
    monkeypatch.setattr(vendors, "_rewrite_private_record_in_parent", real_rewrite)
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.EXISTING_EXACT
    _assert_completed_bootstrap(
        provision, anchor_path, state_path, peer_path, fence_path,
    )


def test_peer_bootstrap_concurrent_invocations_leave_one_fence_and_one_genesis(tmp_path):
    """Concurrent ceremonies converge on one exact durable installation epoch."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    barrier = threading.Barrier(2)
    outcomes = []

    def _run():
        barrier.wait()
        outcomes.append(_bootstrap_existing_peer(
            anchor_path, state_path, peer_path, fence_path,
        ))

    workers = [threading.Thread(target=_run) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()

    assert outcomes.count(vendors.CREATED_THIS_CALL) == 1
    assert set(outcomes) <= {
        vendors.CREATED_THIS_CALL, vendors.EXISTING_EXACT, vendors.REFUSED,
    }
    _assert_completed_bootstrap(
        provision, anchor_path, state_path, peer_path, fence_path,
    )


@pytest.mark.parametrize(
    "target_name,mutation",
    (
        ("state", "unlink"),
        ("witness", "unlink"),
        ("state", "replace"),
        ("witness", "replace"),
        ("state", "hardlink"),
        ("witness", "symlink"),
    ),
)
def test_peer_bootstrap_complete_never_rearms_missing_or_foreign_genesis(
    tmp_path, target_name, mutation,
):
    """COMPLETE is the surviving no-rearm fact for every genesis mutation."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.CREATED_THIS_CALL
    fence_before = fence_path.read_bytes()
    witness_path = vendors._peer_genesis_witness_path(state_path)
    target = state_path if target_name == "state" else witness_path
    original = target.read_bytes()
    # Keep the unlinked inode alive while constructing the replacement. Linux
    # may otherwise immediately reuse the same inode number, accidentally
    # recreating the exact (dev, ino, digest) tuple this test means to falsify.
    held_fd = os.open(target, os.O_RDONLY)
    try:
        target.unlink()
        if mutation == "replace":
            target.write_bytes(original)
            target.chmod(0o600)
        elif mutation == "hardlink":
            source = tmp_path / "foreign-hardlink.json"
            source.write_bytes(original)
            source.chmod(0o600)
            os.link(source, target)
        elif mutation == "symlink":
            source = tmp_path / "foreign-symlink.json"
            source.write_bytes(original)
            source.chmod(0o600)
            target.symlink_to(source)

        assert _bootstrap_existing_peer(
            anchor_path, state_path, peer_path, fence_path,
        ) == vendors.REFUSED
        assert fence_path.read_bytes() == fence_before
        if mutation == "unlink":
            assert not target.exists()
    finally:
        os.close(held_fd)


@pytest.mark.parametrize("mutation", ("replace", "rewrite", "generation"))
def test_peer_bootstrap_binds_exact_anchor_inode_digest_and_source_generation(
    tmp_path, monkeypatch, mutation,
):
    """Changed anchor or source generation never inherits installation authority."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.CREATED_THIS_CALL
    fence_before = fence_path.read_bytes()
    if mutation == "replace":
        replacement = tmp_path / "replacement-anchor.json"
        replacement.write_bytes(anchor_path.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, anchor_path)
    elif mutation == "rewrite":
        changed = dict(provision)
        changed["folder_id"] = _PEER_ALT_UUID
        anchor_path.write_bytes(vendors._canonical_private_bytes(changed))
    else:
        monkeypatch.setattr(vendors, "PEER_SOURCE_GENERATION", "f" * 64)

    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.REFUSED
    assert fence_path.read_bytes() == fence_before


@pytest.mark.parametrize(
    "authorization_name",
    ("none", "create", "rollback", "fresh_object"),
)
def test_peer_bootstrap_only_distinct_coordinator_authorization_can_create_fence(
    tmp_path, authorization_name,
):
    """No generic object or existing create/rollback capability can bootstrap."""
    _provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization = {
        "none": None,
        "create": vendors.CREATE_PEER_AUTHORIZATION,
        "rollback": vendors.ROLLBACK_PEER_AUTHORIZATION,
        "fresh_object": object(),
    }[authorization_name]
    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
    ) == vendors.REFUSED
    assert not fence_path.exists()
    assert not state_path.exists()
    assert not vendors._peer_genesis_witness_path(state_path).exists()


def test_peer_bootstrap_fence_is_closed_and_contains_no_raw_identity_or_path(tmp_path):
    """The installation fence exposes only closed phases, digests and inode facts."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.CREATED_THIS_CALL
    fence = vendors._peer_bootstrap_fence_snapshot(fence_path)
    assert fence is not None
    assert set(fence.document) == vendors._PEER_BOOTSTRAP_FENCE_KEYS
    assert fence.document["schema"] == vendors.PEER_BOOTSTRAP_FENCE_SCHEMA
    assert fence.document["operation"] == vendors.PEER_BOOTSTRAP_OPERATION_KEY
    assert fence.document["peer_operation"] == vendors.PEER_OPERATION_KEY
    serialized = fence.raw.decode("utf-8")
    for forbidden in (
        provision["profile_id"], provision["folder_id"],
        os.fspath(anchor_path), os.fspath(state_path), os.fspath(peer_path),
        "credential", "account", "vendor response",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "mutation",
    ("missing", "wrong_schema", "gologin", "stealthfox", "noncanonical_id"),
)
def test_peer_bootstrap_absent_fence_requires_exact_canonical_v3_mimic_anchor(
    tmp_path, mutation,
):
    """ABSENT is not a migration surface for any approximate anchor shape."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    authorization, bindings_path, census_loader = (
        _mint_peer_bootstrap_authorization(provision, anchor_path)
    )
    if mutation == "missing":
        anchor_path.unlink()
    else:
        document = json.loads(anchor_path.read_text(encoding="utf-8"))
        if mutation == "wrong_schema":
            document["schema"] = "mastermind.mas115_nonseat_canary_provision.v2"
        elif mutation == "gologin":
            document["vendor"] = "gologin"
        elif mutation == "stealthfox":
            document["browser_type"] = "stealthfox"
        else:
            document["profile_id"] = document["profile_id"].upper()
        anchor_path.write_bytes(vendors._canonical_private_bytes(document))

    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.REFUSED
    assert not fence_path.exists()
    assert not state_path.exists()
    assert not vendors._peer_genesis_witness_path(state_path).exists()


@pytest.mark.parametrize("foreign_coordinate", ("state", "witness", "provision"))
def test_peer_bootstrap_absent_fence_refuses_any_preexisting_peer_coordinate(
    tmp_path, foreign_coordinate,
):
    """No pre-fence bytes can be adopted as a bootstrap crash prefix."""
    _provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    target = {
        "state": state_path,
        "witness": vendors._peer_genesis_witness_path(state_path),
        "provision": peer_path,
    }[foreign_coordinate]
    target.write_text("{}\n", encoding="utf-8")
    target.chmod(0o600)

    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.REFUSED
    assert not fence_path.exists()
    assert target.exists()


@pytest.mark.parametrize(
    "mutation", ("unlink", "replace", "malformed", "hardlink", "symlink"),
)
def test_peer_bootstrap_complete_fence_itself_is_never_recreated_or_adopted(
    tmp_path, mutation,
):
    """A consumed fence coordinate cannot be replaced or treated as ABSENT."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.CREATED_THIS_CALL
    _assert_completed_bootstrap(
        provision, anchor_path, state_path, peer_path, fence_path,
    )
    original = fence_path.read_bytes()
    held_fd = os.open(fence_path, os.O_RDONLY)
    try:
        fence_path.unlink()
        if mutation == "replace":
            fence_path.write_bytes(original)
            fence_path.chmod(0o600)
        elif mutation == "malformed":
            fence_path.write_text("{}\n", encoding="utf-8")
            fence_path.chmod(0o600)
        elif mutation == "hardlink":
            source = tmp_path / "foreign-fence-hardlink.json"
            source.write_bytes(original)
            source.chmod(0o600)
            os.link(source, fence_path)
        elif mutation == "symlink":
            source = tmp_path / "foreign-fence-symlink.json"
            source.write_bytes(original)
            source.chmod(0o600)
            fence_path.symlink_to(source)

        assert _bootstrap_existing_peer(
            anchor_path, state_path, peer_path, fence_path,
        ) == vendors.REFUSED
        if mutation == "unlink":
            assert not fence_path.exists()
    finally:
        os.close(held_fd)


def test_peer_bootstrap_holds_one_parent_lock_without_reentry(tmp_path, monkeypatch):
    """The nested genesis helper consumes the already-held bootstrap lock."""
    _provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    real_open = vendors._open_private_parent
    calls = []

    def _open(*args, **kwargs):
        calls.append((args, kwargs))
        return real_open(*args, **kwargs)

    monkeypatch.setattr(vendors, "_open_private_parent", _open)
    assert _bootstrap_existing_peer(
        anchor_path, state_path, peer_path, fence_path,
    ) == vendors.CREATED_THIS_CALL
    assert len(calls) == 2
    assert calls[0][1] == {}
    assert calls[1][1] == {"exclusive": True}


# --- mutation-kill discipline ----------------------------------------------


def test_mutation_kill_create_dispatch_must_follow_intent_commit():
    """FAILS if the create dispatch is moved before the intent commit."""
    transport = _PeerTransport()
    transport.set_candidates_sequence([])
    transport.create_response = _peer_create_success()
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=_refusing_intent(),
    )
    assert receipt["verdict"] == "REFUSED"
    assert receipt["code"] == "PROVISION_MISSING"
    assert [c[0] for c in transport.calls].count("create") == 0


def test_mutation_kill_ambiguous_response_never_dispatches_a_second_create():
    """FAILS if the ambiguous-response branch is allowed to dispatch twice."""
    peer_name = _peer_name()
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name)])
    transport.create_response = None
    client = _peer_client(transport)
    client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=_committing_intent(),
    )
    assert [c[0] for c in transport.calls].count("create") == 1


def test_mutation_kill_readback_alone_decides_never_the_response():
    """FAILS if a "successful" create response alone is trusted without the
    read-back census actually proving the profile exists."""
    transport = _PeerTransport()
    # Vendor claims success, but the read-back census still shows nothing.
    transport.set_candidates_sequence([], [])
    transport.create_response = _peer_create_success()
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=_committing_intent(),
    )
    assert receipt["effect"] == "CREATE_EFFECT_UNKNOWN"
    assert receipt["effect"] not in ("CREATE_APPLIED", "PROFILE_STOPPED_PROVEN", "PROVISION_WRITTEN")


def test_mutation_kill_os_type_must_be_sent_explicitly():
    """FAILS if os_type is dropped from the create body (vendor default is
    "windows"; MAS-115 profiles must always be explicitly "macos")."""
    observed = []

    def _handler(request):
        observed.append(json.loads(request.read()))
        return httpx.Response(201, json={
            "status": {"error_code": "", "http_code": 201, "message": "Profile successfully created"},
            "data": {"ids": ["x"]},
        })

    inner = httpx.Client(transport=httpx.MockTransport(_handler), trust_env=False, follow_redirects=False)
    bounded = vendors.BoundedHttpClient(client=inner)
    try:
        bounded._mlx_profile_create(core.Credential("secret", "stdin"), "folder", "name")
    finally:
        bounded.close()
    assert observed[0].get("os_type") == "macos"
    assert observed[0].get("os_type") != "windows"


def test_mutation_kill_canary_refusal_exception_chain_stays_severed():
    """FAILS if CanaryRefusal's severed ``from None`` is replaced by a bare
    ``raise`` anywhere on the create/remove path."""
    class _LeakyTransport(_PeerTransport):
        def _mlx_profile_search(self, credential, folder_id, *, offset):
            self.calls.append(("search", folder_id, offset))
            raise RuntimeError(_SECRET)

    transport = _LeakyTransport()
    client = _peer_client(transport, credential=core.Credential(_SECRET, "stdin"))
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.peer_candidates(folder_id=_PEER_FOLDER, peer_name=_peer_name())
    exc = exc_info.value
    assert exc.code == "VENDOR_ERROR"
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert _SECRET not in str(exc)
    assert _SECRET not in repr(exc)


# ---------------------------------------------------------------------------
# REALM1 live-seat census snapshot gate repair (Mastermind #432)
# ---------------------------------------------------------------------------


_REALM1_WORKSPACE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
_REALM1_OLD_GENERATION = "c39dac9ab0c51047b442ac5e8bb2683f2780dd6045c5489b79560b4ce6b131a8"
_REALM1_GENERATION = "4b4c77c81a19dafdd6c0ecbed58f14025a41eea77efb2ec070a537e52c999f49"


def _strict_inventory_roots(tmp_path):
    mlx_root = tmp_path / "mlx"
    gologin_root = tmp_path / "gologin"
    mlx_root.mkdir()
    gologin_root.mkdir()
    return mlx_root, gologin_root


def _strict_ps(stdout=""):
    return {
        "code": 0,
        "stdout": stdout,
        "stderr": "",
        "timed_out": False,
    }


def test_realm1_strict_producer_returns_row_201_that_legacy_drops_and_gate_refuses_it(tmp_path):
    """The trusted census cannot inherit the public discovery helper's 200-row truncation."""
    mlx_root, gologin_root = _strict_inventory_roots(tmp_path)
    workspace = mlx_root / _REALM1_WORKSPACE
    candidate_folder = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    candidate_profile = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    (workspace / candidate_folder / candidate_profile).mkdir(parents=True)
    seats = [
        "111111111111111111111111",
        "222222222222222222222222",
        "333333333333333333333333",
    ]
    extra = "f" * 24
    ids = sorted([f"{index:024x}" for index in range(197)] + seats + [extra])
    for profile_id in ids:
        (gologin_root / profile_id).mkdir()
    running = seats + [extra]
    stdout = "\n".join(
        f"browser --user-data-dir={gologin_root / profile_id}"
        for profile_id in running
    )

    legacy = chatgpt.list_local_environments(
        mlx_profiles_root=os.fspath(mlx_root),
        gologin_profiles_root=os.fspath(gologin_root),
        process_args_reader=lambda: stdout.splitlines(),
    )
    strict = chatgpt._strict_list_local_environments(  # noqa: SLF001
        mlx_profiles_root=os.fspath(mlx_root),
        gologin_profiles_root=os.fspath(gologin_root),
        process_runner=lambda *_args, **_kwargs: _strict_ps(stdout),
    )
    assert len(legacy["gologin"]) == 200
    assert extra not in {row["profile_id"] for row in legacy["gologin"]}
    assert len(strict["gologin"]) == 201
    assert strict["gologin"][-1] == {"profile_id": extra, "running": True}

    snapshot = _seal_realm1_environment(strict)
    assert snapshot is not None
    provision = _stored_provision(_valid_provision("multilogin"))
    provision_path = _write_provision(tmp_path, provision)
    loaded, code = core.load_provision(
        provision_path,
        bindings_loader=lambda: (_stale_realm1_bindings(), []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    assert loaded is None and code == "BINDINGS_UNAVAILABLE"


def test_realm1_strict_producer_samples_once_before_traversal_and_uses_plus_four_cap(tmp_path):
    """The one process epoch precedes inventory traversal and preserves a split UTF-8 sentinel."""
    mlx_root = tmp_path / "mlx"
    gologin_root = tmp_path / "gologin"
    calls = []

    def _runner(argv, *, timeout, max_bytes):
        calls.append((argv, timeout, max_bytes))
        mlx_root.mkdir()
        gologin_root.mkdir()
        raw = (
            "x" * chatgpt._PS_SNAPSHOT_MAX_BYTES + "\N{EURO SIGN}"
        ).encode("utf-8")
        # Model runner._cap exactly: a +1 margin drops the split scalar and
        # falsely looks complete, while +4 preserves bytes beyond the limit.
        capped = raw[:max_bytes].decode("utf-8", errors="ignore")
        return _strict_ps(capped)

    with pytest.raises(RuntimeError, match="^strict local environment inventory unavailable$"):
        chatgpt._strict_list_local_environments(  # noqa: SLF001
            mlx_profiles_root=os.fspath(mlx_root),
            gologin_profiles_root=os.fspath(gologin_root),
            process_runner=_runner,
        )
    assert calls == [
        (["/bin/ps", "-axo", "args="], 5.0, chatgpt._PS_SNAPSHOT_MAX_BYTES + 4),
    ]


@pytest.mark.parametrize(
    "result",
    (
        None,
        {},
        {"code": True, "stdout": "", "stderr": "", "timed_out": False},
        {"code": 1, "stdout": "", "stderr": "secret", "timed_out": False},
        {"code": None, "stdout": "", "stderr": "", "timed_out": True},
        {"code": 0, "stdout": b"", "stderr": "", "timed_out": False},
        {"code": 0, "stdout": "\ufffd", "stderr": "", "timed_out": False},
        {"code": 0, "stdout": "", "stderr": "\ufffd", "timed_out": False},
    ),
)
def test_realm1_strict_producer_refuses_malformed_process_envelopes_without_leakage(tmp_path, result):
    mlx_root, gologin_root = _strict_inventory_roots(tmp_path)
    with pytest.raises(RuntimeError) as exc_info:
        chatgpt._strict_list_local_environments(  # noqa: SLF001
            mlx_profiles_root=os.fspath(mlx_root),
            gologin_profiles_root=os.fspath(gologin_root),
            process_runner=lambda *_args, **_kwargs: result,
        )
    assert str(exc_info.value) == "strict local environment inventory unavailable"
    assert exc_info.value.__cause__ is None
    assert "secret" not in repr(exc_info.value)


def test_realm1_strict_producer_refuses_runner_exception_without_raw_context(tmp_path):
    mlx_root, gologin_root = _strict_inventory_roots(tmp_path)

    def _raise(*_args, **_kwargs):
        raise OSError("SECRET /private/profile/path")

    with pytest.raises(RuntimeError) as exc_info:
        chatgpt._strict_list_local_environments(  # noqa: SLF001
            mlx_profiles_root=os.fspath(mlx_root),
            gologin_profiles_root=os.fspath(gologin_root),
            process_runner=_raise,
        )
    assert str(exc_info.value) == "strict local environment inventory unavailable"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "SECRET" not in repr(exc_info.value)


def test_realm1_strict_producer_accepts_exactly_1000_and_refuses_1001(tmp_path):
    mlx_root, gologin_root = _strict_inventory_roots(tmp_path)
    for index in range(1001):
        (gologin_root / f"{index:024x}").mkdir()
    kwargs = {
        "mlx_profiles_root": os.fspath(mlx_root),
        "gologin_profiles_root": os.fspath(gologin_root),
        "process_runner": lambda *_args, **_kwargs: _strict_ps(),
    }
    with pytest.raises(RuntimeError, match="^strict local environment inventory unavailable$"):
        chatgpt._strict_list_local_environments(**kwargs)  # noqa: SLF001
    (gologin_root / f"{1000:024x}").rmdir()
    assert len(chatgpt._strict_list_local_environments(**kwargs)["gologin"]) == 1000  # noqa: SLF001


@pytest.mark.parametrize("bad_kind", ("root_symlink", "identity_symlink", "uppercase_gologin"))
def test_realm1_strict_producer_refuses_ambiguous_filesystem_identities(tmp_path, bad_kind):
    mlx_root, gologin_root = _strict_inventory_roots(tmp_path)
    if bad_kind == "root_symlink":
        mlx_root.rmdir()
        target = tmp_path / "real-mlx"
        target.mkdir()
        mlx_root.symlink_to(target, target_is_directory=True)
    elif bad_kind == "identity_symlink":
        target = tmp_path / "real-profile"
        target.mkdir()
        (gologin_root / ("a" * 24)).symlink_to(target, target_is_directory=True)
    else:
        (gologin_root / ("A" * 24)).mkdir()
    with pytest.raises(RuntimeError, match="^strict local environment inventory unavailable$"):
        chatgpt._strict_list_local_environments(  # noqa: SLF001
            mlx_profiles_root=os.fspath(mlx_root),
            gologin_profiles_root=os.fspath(gologin_root),
            process_runner=lambda *_args, **_kwargs: _strict_ps(),
        )


def test_realm1_strict_producer_refuses_cross_workspace_authority_duplicate(tmp_path):
    mlx_root, gologin_root = _strict_inventory_roots(tmp_path)
    folder = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    profile = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    for workspace in (
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    ):
        (mlx_root / workspace / folder / profile).mkdir(parents=True)
    with pytest.raises(RuntimeError, match="^strict local environment inventory unavailable$"):
        chatgpt._strict_list_local_environments(  # noqa: SLF001
            mlx_profiles_root=os.fspath(mlx_root),
            gologin_profiles_root=os.fspath(gologin_root),
            process_runner=lambda *_args, **_kwargs: _strict_ps(),
        )


@pytest.mark.parametrize(
    "mutation", ("unmatched", "wrong_depth", "multiple", "quoted", "double_slash"),
)
def test_realm1_strict_producer_refuses_managed_process_ambiguity(tmp_path, mutation):
    mlx_root, gologin_root = _strict_inventory_roots(tmp_path)
    profile = "a" * 24
    (gologin_root / profile).mkdir()
    if mutation == "unmatched":
        line = f"browser --user-data-dir={gologin_root / ('b' * 24)}"
    elif mutation == "wrong_depth":
        line = f"browser --user-data-dir={gologin_root / profile / 'nested'}"
    elif mutation == "multiple":
        line = (
            f"browser --user-data-dir={gologin_root / profile} "
            f"--user-data-dir={gologin_root / profile}"
        )
    elif mutation == "quoted":
        line = f'browser --user-data-dir="{gologin_root / profile}"'
    else:
        line = f"browser --user-data-dir=/{gologin_root / profile}"
    with pytest.raises(RuntimeError, match="^strict local environment inventory unavailable$"):
        chatgpt._strict_list_local_environments(  # noqa: SLF001
            mlx_profiles_root=os.fspath(mlx_root),
            gologin_profiles_root=os.fspath(gologin_root),
            process_runner=lambda *_args, **_kwargs: _strict_ps(line),
        )


def test_realm1_strict_producer_ignores_unrelated_browser_process_and_missing_roots(tmp_path):
    missing_mlx = tmp_path / "missing-mlx"
    missing_gologin = tmp_path / "missing-gologin"
    result = chatgpt._strict_list_local_environments(  # noqa: SLF001
        mlx_profiles_root=os.fspath(missing_mlx),
        gologin_profiles_root=os.fspath(missing_gologin),
        process_runner=lambda *_args, **_kwargs: _strict_ps(
            "chrome --user-data-dir=/tmp/ordinary-chrome"
        ),
    )
    assert result == {"multilogin": [], "gologin": []}


def test_realm1_vendor_live_census_uses_only_the_strict_private_producer(monkeypatch):
    strict = _realm1_environment()
    monkeypatch.setattr(chatgpt, "_strict_list_local_environments", lambda: strict, raising=False)
    monkeypatch.setattr(
        chatgpt,
        "list_local_environments",
        lambda: (_ for _ in ()).throw(AssertionError("legacy discovery is not trusted")),
    )
    assert vendors._coordinator_local_census() is strict  # noqa: SLF001


def _realm1_environment(provision=None) -> dict:
    provision = provision or _stored_provision(_valid_provision("multilogin"))
    return {
        "gologin": [
            {"profile_id": "111111111111111111111111", "running": True},
            {"profile_id": "222222222222222222222222", "running": True},
            {"profile_id": "333333333333333333333333", "running": True},
        ],
        "multilogin": [{
            "workspace_id": _REALM1_WORKSPACE,
            "folder_id": provision["folder_id"],
            "profile_id": provision["profile_id"],
            "running": False,
        }],
    }


def _seal_realm1_environment(raw):
    seal = getattr(core, "_seal_current_environment_snapshot", None)
    assert callable(seal), "the private current-environment snapshot sealer is missing"
    return seal(raw)


def test_realm1_live_snapshot_accepts_only_exact_rows_normalizes_uuids_and_detaches_aliases():
    """Catches permissive row reduction, mutable aliases, and noncanonical UUIDs."""
    raw = _realm1_environment()
    for key in ("workspace_id", "folder_id", "profile_id"):
        raw["multilogin"][0][key] = raw["multilogin"][0][key].upper()
    snapshot = _seal_realm1_environment(raw)
    assert snapshot is not None
    assert core._is_current_environment_snapshot(snapshot) is True  # noqa: SLF001

    rows = tuple(dict(row) for row in snapshot.rows)
    candidate = next(row for row in rows if row["env_manager"] == "multilogin")
    assert candidate == {
        "env_manager": "multilogin",
        "workspace_id": _REALM1_WORKSPACE,
        "folder_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "profile_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "running": False,
    }
    assert re.fullmatch(r"[0-9a-f]{64}", snapshot.digest)

    frozen_rows = rows
    frozen_digest = snapshot.digest
    raw["multilogin"][0]["running"] = True
    raw["multilogin"].clear()
    raw["gologin"][0]["profile_id"] = "f" * 24
    assert tuple(dict(row) for row in snapshot.rows) == frozen_rows
    assert snapshot.digest == frozen_digest
    with pytest.raises(TypeError):
        snapshot.rows[0]["running"] = False
    with pytest.raises((AttributeError, TypeError)):
        snapshot.digest = "0" * 64

    class _Lookalike:
        rows = snapshot.rows
        digest = snapshot.digest

    assert core._is_current_environment_snapshot(_realm1_environment()) is False  # noqa: SLF001
    assert core._is_current_environment_snapshot(_Lookalike()) is False  # noqa: SLF001


def test_realm1_live_snapshot_has_an_exact_total_cardinality_ceiling():
    """The authority snapshot is bounded before any downstream decision."""
    raw = _realm1_environment()
    raw["gologin"].extend(
        {"profile_id": f"{index:024x}", "running": False}
        for index in range(996)
    )
    assert len(raw["gologin"]) + len(raw["multilogin"]) == 1000
    assert _seal_realm1_environment(raw) is not None
    raw["gologin"].append({"profile_id": f"{996:024x}", "running": False})
    assert _seal_realm1_environment(raw) is None


def test_realm1_snapshot_order_and_digest_are_canonical_over_closed_rows():
    """Input order cannot change authority, and the digest covers canonical rows."""
    first_raw = _realm1_environment()
    first_raw["gologin"].reverse()
    first = _seal_realm1_environment(first_raw)
    second = _seal_realm1_environment(_realm1_environment())
    assert first is not None and second is not None
    assert tuple(dict(row) for row in first.rows) == tuple(
        dict(row) for row in second.rows
    )
    canonical = json.dumps(
        [dict(row) for row in first.rows],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert first.digest == hashlib.sha256(canonical).hexdigest()
    assert first.digest == second.digest

    changed_raw = _realm1_environment()
    changed_raw["multilogin"][0]["workspace_id"] = (
        "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    )
    changed = _seal_realm1_environment(changed_raw)
    assert changed is not None
    assert changed.digest != first.digest


def test_realm1_snapshot_digest_is_revalidated_by_every_consumer(tmp_path):
    """Forced corruption cannot turn a once-valid object into freshness authority."""
    provision = _stored_provision(_valid_provision("multilogin"))
    path = _write_provision(tmp_path, provision)
    snapshot = _seal_realm1_environment(_realm1_environment(provision))
    assert snapshot is not None
    object.__setattr__(snapshot, "digest", "0" * 64)
    assert core._is_current_environment_snapshot(snapshot) is False  # noqa: SLF001
    loaded, code = core.load_provision(
        path,
        bindings_loader=lambda: (_stale_realm1_bindings(), []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    assert loaded is None and code == "BINDINGS_UNAVAILABLE"
    assert vendors._local_disposable_preflight(  # noqa: SLF001
        provision, current_environment_snapshot=snapshot,
    ) == "BINDINGS_UNAVAILABLE"


def test_realm1_raw_or_lookalike_snapshot_never_activates_live_freshness(tmp_path):
    """Only the private sealed value can bypass stale navigation timestamps."""
    provision = _stored_provision(_valid_provision("multilogin"))
    path = _write_provision(tmp_path, provision)
    snapshot = _seal_realm1_environment(_realm1_environment(provision))
    assert snapshot is not None

    class _Lookalike:
        rows = snapshot.rows
        digest = snapshot.digest

    for untrusted in (_realm1_environment(provision), _Lookalike()):
        loaded, code = core.load_provision(
            path,
            bindings_loader=lambda: (_stale_realm1_bindings(), []),
            current_environment_snapshot=untrusted,
            now=_NOW,
        )
        assert loaded is None and code == "BINDINGS_UNAVAILABLE"


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown_top", "missing_top", "nonlist", "nondict_row",
        "unknown_row", "missing_row", "nonstring", "nonbool", "malformed",
        "uppercase_gologin", "duplicate", "contradictory", "cross_workspace",
    ),
)
def test_realm1_live_snapshot_rejects_every_ambiguous_or_malformed_shape(mutation):
    """Each mutation can otherwise forge a partial or contradictory live census."""
    raw = _realm1_environment()
    row = raw["multilogin"][0]
    if mutation == "unknown_top":
        raw["shadow"] = []
    elif mutation == "missing_top":
        raw.pop("gologin")
    elif mutation == "nonlist":
        raw["gologin"] = {}
    elif mutation == "nondict_row":
        raw["gologin"][0] = "not-a-row"
    elif mutation == "unknown_row":
        row["name"] = "ignored-by-old-reducer"
    elif mutation == "missing_row":
        row.pop("workspace_id")
    elif mutation == "nonstring":
        row["folder_id"] = None
    elif mutation == "nonbool":
        row["running"] = 1
    elif mutation == "malformed":
        row["profile_id"] = "not-a-uuid"
    elif mutation == "uppercase_gologin":
        raw["gologin"][0]["profile_id"] = "A" * 24
    elif mutation == "duplicate":
        raw["multilogin"].append(dict(row))
    elif mutation == "contradictory":
        changed = dict(row)
        changed["running"] = True
        raw["multilogin"].append(changed)
    else:
        changed = dict(row)
        changed["workspace_id"] = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        raw["multilogin"].append(changed)
    assert _seal_realm1_environment(raw) is None


def _stale_realm1_bindings() -> dict:
    document = _binding_doc()
    for binding in document["bindings"]:
        binding["observed_at"] = "2026-08-01T00:00:00Z"
    return document


def test_realm1_stale_bindings_pass_only_with_sealed_exact_live_seats_and_candidate(tmp_path):
    """The live snapshot supplements stale navigation timestamps without rewriting them."""
    provision = _stored_provision(_valid_provision("multilogin"))
    path = _write_provision(tmp_path, provision)
    bindings = _stale_realm1_bindings()
    agreeing = copy.deepcopy(bindings["bindings"][0])
    agreeing["binding_id"] = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    agreeing["work_ref"] = "WS:ANOTHER-CHAT"
    bindings["bindings"].append(agreeing)
    before = copy.deepcopy(bindings)

    loaded, code = core.load_provision(
        path, bindings_loader=lambda: (bindings, []), now=_NOW,
    )
    assert loaded is None and code == "BINDINGS_UNAVAILABLE"

    snapshot = _seal_realm1_environment(_realm1_environment(provision))
    assert snapshot is not None
    loaded, code = core.load_provision(
        path,
        bindings_loader=lambda: (bindings, []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    assert code is None
    assert loaded == provision
    assert bindings == before


def test_realm1_candidate_collision_uses_exact_manager_folder_profile_identity(tmp_path):
    """A shared UUID in another folder is distinct; the exact seat identity is forbidden."""
    candidate = _stored_provision(_valid_provision("multilogin"))
    path = _write_provision(tmp_path, candidate)
    bindings = _binding_doc(colliding_profile_id=candidate["profile_id"])
    for binding in bindings["bindings"]:
        binding["observed_at"] = "2026-08-01T00:00:00Z"
    seat_folder = bindings["bindings"][0]["locator"]["folder_id"]
    raw = {
        "gologin": [
            {"profile_id": "222222222222222222222222", "running": True},
            {"profile_id": "333333333333333333333333", "running": True},
        ],
        "multilogin": [
            {
                "workspace_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                "folder_id": seat_folder,
                "profile_id": candidate["profile_id"],
                "running": True,
            },
            {
                "workspace_id": _REALM1_WORKSPACE,
                "folder_id": candidate["folder_id"],
                "profile_id": candidate["profile_id"],
                "running": False,
            },
        ],
    }
    snapshot = _seal_realm1_environment(raw)
    assert snapshot is not None
    loaded, code = core.load_provision(
        path,
        bindings_loader=lambda: (bindings, []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    assert code is None and loaded == candidate

    exact = dict(candidate, folder_id=seat_folder)
    exact_path = _write_provision(tmp_path, exact)
    loaded, code = core.load_provision(
        exact_path,
        bindings_loader=lambda: (bindings, []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    assert loaded is None and code == "DISALLOWED_TARGET"


@pytest.mark.parametrize(
    "mutation",
    (
        "seat_missing", "seat_stopped", "extra_running",
        "binding_disagrees", "seat_identity_reused",
    ),
)
def test_realm1_live_gate_refuses_running_set_and_binding_mutations(tmp_path, mutation):
    """Catches any relaxation of exact three-seat equality or binding identity."""
    provision = _stored_provision(_valid_provision("multilogin"))
    path = _write_provision(tmp_path, provision)
    raw = _realm1_environment(provision)
    bindings = _stale_realm1_bindings()
    if mutation == "seat_missing":
        raw["gologin"].pop(0)
    elif mutation == "seat_stopped":
        raw["gologin"][0]["running"] = False
    elif mutation == "extra_running":
        raw["gologin"].append({"profile_id": "444444444444444444444444", "running": True})
    elif mutation == "binding_disagrees":
        conflict = copy.deepcopy(bindings["bindings"][0])
        conflict["binding_id"] = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
        conflict["work_ref"] = "WS:ANOTHER-CHAT"
        conflict["locator"]["profile_id"] = "444444444444444444444444"
        bindings["bindings"].append(conflict)
    else:
        bindings["bindings"][1]["locator"]["profile_id"] = (
            bindings["bindings"][0]["locator"]["profile_id"]
        )
    snapshot = _seal_realm1_environment(raw)
    assert snapshot is not None
    loaded, code = core.load_provision(
        path,
        bindings_loader=lambda: (bindings, []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    assert loaded is None
    assert code == "BINDINGS_UNAVAILABLE"


def test_realm1_multilogin_seat_requires_exact_folder_identity(tmp_path):
    """A running Multilogin row in another folder cannot satisfy a bound seat."""
    provision = _stored_provision(_valid_provision("multilogin"))
    path = _write_provision(tmp_path, provision)
    seat_profile = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    bindings = _binding_doc(colliding_profile_id=seat_profile)
    for binding in bindings["bindings"]:
        binding["observed_at"] = "2026-08-01T00:00:00Z"
    seat_folder = bindings["bindings"][0]["locator"]["folder_id"]
    raw = {
        "gologin": [
            {"profile_id": "222222222222222222222222", "running": True},
            {"profile_id": "333333333333333333333333", "running": True},
        ],
        "multilogin": [
            {
                "workspace_id": _REALM1_WORKSPACE,
                "folder_id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
                "profile_id": seat_profile,
                "running": True,
            },
            {
                "workspace_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                "folder_id": provision["folder_id"],
                "profile_id": provision["profile_id"],
                "running": False,
            },
        ],
    }
    assert raw["multilogin"][0]["folder_id"] != seat_folder
    snapshot = _seal_realm1_environment(raw)
    assert snapshot is not None
    loaded, code = core.load_provision(
        path,
        bindings_loader=lambda: (bindings, []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    assert loaded is None and code == "BINDINGS_UNAVAILABLE"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("candidate_running", "BUSY_PROFILE"),
        ("candidate_missing", "PROFILE_NOT_FOUND"),
        ("candidate_wrong_folder", "VENDOR_ERROR"),
    ),
)
def test_realm1_local_gate_requires_exact_distinct_stopped_candidate(
    tmp_path, mutation, expected,
):
    """The separate local gate owns candidate presence and stopped-state proof."""
    provision = _stored_provision(_valid_provision("multilogin"))
    path = _write_provision(tmp_path, provision)
    raw = _realm1_environment(provision)
    if mutation == "candidate_running":
        raw["multilogin"][0]["running"] = True
    elif mutation == "candidate_missing":
        raw["multilogin"].clear()
    else:
        raw["multilogin"][0]["folder_id"] = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    snapshot = _seal_realm1_environment(raw)
    assert snapshot is not None
    loaded, code = core.load_provision(
        path,
        bindings_loader=lambda: (_stale_realm1_bindings(), []),
        current_environment_snapshot=snapshot,
        now=_NOW,
    )
    if mutation == "candidate_running":
        # The seat gate sees this as the forbidden fourth running identity;
        # the local candidate gate independently retains its BUSY result.
        assert loaded is None and code == "BINDINGS_UNAVAILABLE"
    else:
        assert code is None and loaded == provision
    assert vendors._local_disposable_preflight(  # noqa: SLF001
        provision, current_environment_snapshot=snapshot,
    ) == expected


def test_realm1_public_vendor_entrypoints_cannot_accept_inventory_injection():
    """Only the private hermetic seam may replace the trusted census owner."""
    forbidden = {
        "census_loader", "environment_loader",
        "current_environment_snapshot", "raw_rows",
    }
    for entrypoint in (
        vendors.main,
        vendors.run_coordinator_peer_create,
        vendors.run_coordinator_peer_rollback,
        vendors.mint_coordinator_peer_bootstrap_evidence,
        vendors.run_coordinator_peer_bootstrap,
    ):
        signature = inspect.signature(entrypoint)
        assert not any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        assert forbidden.isdisjoint(signature.parameters)
    private_main = getattr(vendors, "_main", None)
    assert callable(private_main), "the hermetic-only vendor entry seam is missing"

    with pytest.raises(TypeError):
        vendors.main([], environment_loader=lambda: _realm1_environment())
    for coordinator in (
        vendors.run_coordinator_peer_create,
        vendors.run_coordinator_peer_rollback,
    ):
        with pytest.raises(TypeError):
            coordinator([], environment_loader=lambda: _realm1_environment())
    with pytest.raises(TypeError):
        vendors.mint_coordinator_peer_bootstrap_evidence(
            census_loader=lambda: _realm1_environment(),
        )
    with pytest.raises(TypeError):
        vendors.run_coordinator_peer_bootstrap(
            authorization=object(),
            census_loader=lambda: _realm1_environment(),
        )


@pytest.mark.parametrize("loader_result", ("raises", "malformed"))
def test_realm1_inventory_failure_refuses_before_core_origin_secret_or_client(
    loader_result,
):
    """No downstream owner is reached unless one strict snapshot was sealed."""
    calls = []

    def _inventory():
        calls.append("inventory")
        if loader_result == "raises":
            raise RuntimeError("synthetic census failure")
        return {"gologin": [], "multilogin": [], "unknown": []}

    def _unexpected(*_args, **_kwargs):
        calls.append("unexpected")
        raise AssertionError("invalid inventory must refuse before downstream work")

    out = io.StringIO()
    code = vendors._main(  # noqa: SLF001 — hermetic dependency seam
        ["run", "--vendor", "multilogin", "--provision-path", "/unused.json"],
        stdout=out,
        environment_loader=_inventory,
        bindings_loader=_unexpected,
        origin_factory=_unexpected,
        credential_stream_factory=_unexpected,
        client_factory=_unexpected,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == "BINDINGS_UNAVAILABLE"
    assert calls == ["inventory"]


def test_realm1_all_peer_revalidation_sites_thread_the_current_snapshot():
    """Every nested peer-provision gate must remain bound to the same epoch."""
    tree = ast.parse(VENDORS_PATH.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for function_name in (
        "_write_peer_provision",
        "_create_peer_profile_cli",
        "_main",
    ):
        calls = [
            node for node in ast.walk(functions[function_name])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_validate_provision_document"
        ]
        assert len(calls) == 1
        snapshot_keyword = next(
            keyword for keyword in calls[0].keywords
            if keyword.arg == "current_environment_snapshot"
        )
        assert isinstance(snapshot_keyword.value, ast.Name)
        assert snapshot_keyword.value.id == "current_environment_snapshot"

    create_calls = [
        node for node in ast.walk(functions["_main"])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_create_peer_profile_cli"
    ]
    assert len(create_calls) == 1
    snapshot_keyword = next(
        keyword for keyword in create_calls[0].keywords
        if keyword.arg == "current_environment_snapshot"
    )
    assert isinstance(snapshot_keyword.value, ast.Name)
    assert snapshot_keyword.value.id == "current_environment_snapshot"


def test_realm1_private_vendor_seam_samples_once_and_threads_one_snapshot_presecret(monkeypatch):
    """Dropping, rebuilding, or resampling the snapshot opens a TOCTOU gap."""
    private_main = getattr(vendors, "_main", None)
    assert callable(private_main), "the hermetic-only vendor entry seam is missing"
    provision = _stored_provision(_valid_provision("multilogin"))
    raw = _realm1_environment(provision)
    calls = []

    def _inventory():
        calls.append(("inventory", None))
        return raw

    def _load(_path, **kwargs):
        snapshot = kwargs.get("current_environment_snapshot")
        assert core._is_current_environment_snapshot(snapshot) is True  # noqa: SLF001
        calls.append(("load", snapshot))
        return provision, None

    def _local(_provision, **kwargs):
        snapshot = kwargs.get("current_environment_snapshot")
        assert core._is_current_environment_snapshot(snapshot) is True  # noqa: SLF001
        calls.append(("local", snapshot))
        return None

    def _secret():
        calls.append(("secret", None))
        return io.BytesIO(b"")

    monkeypatch.setattr(vendors._core, "load_provision", _load)
    monkeypatch.setattr(vendors, "_local_disposable_preflight", _local)
    out = io.StringIO()
    code = private_main(
        ["run", "--vendor", "multilogin", "--provision-path", "/hermetic/provision.json"],
        stdout=out,
        environment_loader=_inventory,
        credential_stream_factory=_secret,
        origin_factory=_ReadyOrigin,
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("empty credential must precede client")),
        now=_NOW,
    )
    assert code == 2
    assert [name for name, _value in calls] == ["inventory", "load", "local", "secret"]
    snapshots = [value for name, value in calls if name in ("load", "local")]
    assert len(snapshots) == 2 and snapshots[0] is snapshots[1]


def test_realm1_peer_provision_post_effect_validation_reuses_snapshot_without_persisting_it(
    tmp_path, monkeypatch,
):
    """The post-create provision gate cannot fall back to stale timestamps."""
    snapshot = _seal_realm1_environment(_realm1_environment())
    assert snapshot is not None
    observed = []

    def _validate(document, **kwargs):
        observed.append(kwargs.get("current_environment_snapshot"))
        return dict(document), None

    monkeypatch.setattr(vendors._core, "_validate_provision_document", _validate)
    path = tmp_path / "peer-provision.json"
    written, loaded = vendors._write_peer_provision(  # noqa: SLF001
        path,
        profile_id=_PEER_CREATED_UUID,
        folder_id=_PEER_FOLDER,
        bindings_loader=_no_collision_loader,
        now=_NOW,
        current_environment_snapshot=snapshot,
    )
    assert written is True and loaded is not None
    assert observed == [snapshot]
    serialized = path.read_text(encoding="utf-8")
    assert snapshot.digest not in serialized
    assert "current_environment_snapshot" not in serialized


def test_realm1_bootstrap_digest_rejects_shape_old_reducer_ignored(tmp_path):
    """Mint and consume must independently seal the entire strict census shape."""
    provision, anchor_path, state_path, peer_path, fence_path, _anchor = (
        _peer_bootstrap_preimage(tmp_path)
    )
    current = [_peer_bootstrap_census(provision)]
    census_calls = []

    def census_loader():
        census_calls.append("sample")
        return current[0]

    authorization, bindings_path, _loader = _mint_peer_bootstrap_authorization(
        provision, anchor_path, census_loader=census_loader,
    )
    assert census_calls == ["sample"]
    current[0] = copy.deepcopy(current[0])
    current[0]["ignored-by-old-reducer"] = []
    assert _bootstrap_existing_peer(
        anchor_path,
        state_path,
        peer_path,
        fence_path,
        authorization=authorization,
        bindings_path=bindings_path,
        census_loader=census_loader,
    ) == vendors.REFUSED
    assert census_calls == ["sample", "sample"]
    assert not fence_path.exists()


def test_realm1_bootstrap_one_validation_uses_one_snapshot_for_both_predicates(
    monkeypatch,
):
    """Bootstrap cannot mix candidate state from one observation with seats from another."""
    provision = _stored_provision(_valid_provision("multilogin"))
    raw = _realm1_environment(provision)
    observed = []

    def _local(_provision, **kwargs):
        observed.append(kwargs.get("current_environment_snapshot"))
        return None

    def _seats(*_args, **kwargs):
        observed.append(kwargs.get("current_environment_snapshot"))
        return "clear"

    monkeypatch.setattr(vendors, "_local_disposable_preflight", _local)
    monkeypatch.setattr(vendors._core, "_current_chairman_profile_census", _seats)
    digest = vendors._validate_peer_bootstrap_evidence_documents(  # noqa: SLF001
        provision,
        _stale_realm1_bindings(),
        raw,
        now=_NOW,
    )
    assert len(observed) == 2 and observed[0] is observed[1]
    assert core._is_current_environment_snapshot(observed[0]) is True  # noqa: SLF001
    assert digest == observed[0].digest


def test_realm1_peer_generation_is_frozen_and_old_generation_is_not_current(tmp_path):
    """Old lifecycle bytes cannot inherit authority after the census contract changes."""
    assert vendors.PEER_SOURCE_GENERATION == _REALM1_GENERATION
    state_path = tmp_path / "peer-state.json"
    peer_path = tmp_path / "peer-provision.json"
    outcome = vendors.initialize_peer_lifecycle_state(
        state_path,
        folder_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        anchor_profile_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        peer_name=vendors.peer_profile_name(
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        ),
        peer_provision_path=peer_path,
        generation=_REALM1_OLD_GENERATION,
    )
    assert outcome == vendors.CREATED_THIS_CALL
    with pytest.raises(vendors._PeerStateRefusal):  # noqa: SLF001
        vendors._preflight_peer_paths(  # noqa: SLF001
            operation="create-peer-profile",
            state_path=state_path,
            provision_path=peer_path,
            generation=_REALM1_GENERATION,
        )
