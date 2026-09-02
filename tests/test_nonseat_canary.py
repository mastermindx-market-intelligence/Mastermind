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
import inspect
import io
import json
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from control_plane import surface_bindings as sb
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
                "profile_id": provision["profile_id"],
                "folder_id": provision["folder_id"],
                "running": running,
            }],
            "gologin": [],
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
    code = vendors.main(
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
    code = vendors.main(
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
    code = vendors.main(
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
    code = vendors.main(
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
    code = vendors.main(
        ["--vendor", "multilogin", "--provision-path", str(path)],
        stdout=buf, bindings_loader=_no_collision_loader,
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
    code = vendors.main(
        ["--vendor", "multilogin", "--provision-path", str(path)],
        stdout=buf, bindings_loader=lambda: (None, []),
        credential_stream_factory=_credential_stream_factory,
        client_factory=_client_factory, origin_factory=_origin_factory, now=_NOW,
    )
    assert code == 2
    assert json.loads(buf.getvalue())["code"] == "BINDINGS_UNAVAILABLE"
    assert calls == {"keychain_spawn": 0, "client": 0, "origin": 0}


def test_non_mimic_provision_refuses_before_local_census_origin_keychain_or_http(tmp_path):
    """Catches deferring the approved Mimic gate until after secret access."""
    provision = _valid_provision("multilogin", browser_type="stealthfox")
    path = _write_provision(tmp_path, provision)
    calls = []
    boom = lambda *args, **kwargs: calls.append("unexpected")
    out = io.StringIO()
    code = vendors.main(
        ["configure-canary-port", "--vendor", "multilogin", "--provision-path", str(path)],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=boom,
        origin_factory=boom,
        credential_stream_factory=boom,
        client_factory=boom,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == "UNSUPPORTED_PORT_STATE"
    assert calls == []


@pytest.mark.parametrize(
    ("environment", "expected"),
    (
        ({"multilogin": [], "gologin": []}, "PROFILE_NOT_FOUND"),
        ("running", "BUSY_PROFILE"),
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
        environment_loader = lambda: environment

    def unexpected(*args, **kwargs):
        calls.append("unexpected")
        raise AssertionError("local refusal must precede origin, Keychain, and HTTP")

    out = io.StringIO()
    code = vendors.main(
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
    code = vendors.main(
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

_PEER_FOLDER = "peer-folder"
_PEER_ANCHOR = "anchor-profile"


def _peer_name() -> str:
    return vendors.peer_profile_name(_PEER_FOLDER, _PEER_ANCHOR)


_PEER_CREATED_UUID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


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
        return True

    _commit.calls = calls
    return _commit


def _refusing_intent():
    calls = []

    def _commit():
        calls.append(True)
        return False

    _commit.calls = calls
    return _commit


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
    code = vendors.main(
        [operation, "--vendor", "multilogin", "--provision-path", str(path), "--confirmed"],
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
    out = io.StringIO()
    code = vendors.main(
        [operation, "--vendor", "multilogin", "--provision-path", str(path), "--confirmed"],
        stdout=out,
        bindings_loader=_no_collision_loader,
        environment_loader=_environment_loader_for(provision, running=True),
        credential_stream_factory=lambda: (_ for _ in ()).throw(AssertionError("must not read Keychain")),
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not build a vendor client")),
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == "BUSY_PROFILE"


@pytest.mark.parametrize("operation", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_d2_stale_bindings_refuse_before_keychain_or_http(tmp_path, operation):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    out = io.StringIO()
    code = vendors.main(
        [operation, "--vendor", "multilogin", "--provision-path", str(path), "--confirmed"],
        stdout=out,
        bindings_loader=lambda: (None, ["stale"]),
        environment_loader=_environment_loader_for(provision),
        credential_stream_factory=lambda: (_ for _ in ()).throw(AssertionError("must not read Keychain")),
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not build a vendor client")),
        origin_factory=_ReadyOrigin,
        now=_NOW,
    )
    assert code == 2
    assert json.loads(out.getvalue())["code"] == "BINDINGS_UNAVAILABLE"


def test_peer_d2_new_operations_never_bind_or_self_test_loopback_origin(tmp_path):
    """#385-2 (loopback carve-out): these operations never launch a browser,
    so the fixed-port origin must never be bound or self-tested."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, folder_id=provision["folder_id"])])
    transport.create_response = _peer_create_success()

    origin_calls = []

    def _tracking_origin(*args, **kwargs):
        origin_calls.append(1)
        raise AssertionError("create/rollback must never bind the loopback origin")

    out = io.StringIO()
    code = vendors.main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
            "--confirmed",
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

    out = io.StringIO()
    code = vendors.main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
            "--confirmed",
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
            _peer_record(peer_name, id="dup-peer-a"),
            _peer_record(peer_name, id="dup-peer-b"),
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


def test_peer_d11_provision_write_failure_retains_cleanup_lease(tmp_path):
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    peer_name = vendors.peer_profile_name(provision["folder_id"], provision["profile_id"])
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [_peer_record(peer_name, folder_id=provision["folder_id"])])
    transport.create_response = _peer_create_success()
    peer_provision_path = tmp_path / "peer_provision.json"
    # Pre-seed a colliding, non-reconcilable peer provision file so the
    # write-then-reload step is forced to fail.
    peer_provision_path.write_text(json.dumps({"not": "reconcilable"}), encoding="utf-8")

    out = io.StringIO()
    code = vendors.main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
            "--confirmed",
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
    assert code == 3
    assert receipt["verdict"] == "HOLD"
    assert receipt["predicates"]["provision_written"] is False
    assert receipt["predicates"]["cleanup_lease_retained"] is True
    assert [c[0] for c in transport.calls].count("create") == 1
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

    out = io.StringIO()
    code = vendors.main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
            "--confirmed",
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
        [_peer_record(peer_name, id="peer-created-1")], [],
    )
    transport.remove_response = _peer_remove_success()
    client = _peer_client(transport)
    receipt = client.remove_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR, peer_profile_id="peer-created-1",
    )
    assert receipt["verdict"] == "PASS"
    assert receipt["effect"] == "ROLLBACK_VERIFIED"
    assert receipt["predicates"]["removed_absent"] is True
    assert [c[0] for c in transport.calls].count("remove") == 1


# --- REVIEW REPAIRS: gaps found by the non-author adversarial review -------


def _seed_peer_intent(tmp_path, provision):
    """Write the create-intent preimage exactly as a real create would."""
    intent_path = tmp_path / "peer_intent.json"
    assert vendors._commit_peer_intent(
        intent_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=vendors.peer_profile_name(provision["folder_id"], provision["profile_id"]),
    )
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


def _rollback_main(tmp_path, provision, transport, *, intent_path, peer_provision_path, out):
    return vendors.main(
        [
            "rollback-peer-profile", "--vendor", "multilogin",
            "--provision-path", str(_write_provision(tmp_path, provision)), "--confirmed",
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
    peer_provision_path.write_text(
        json.dumps(_peer_provision_doc(provision, _PEER_CREATED_UUID)), encoding="utf-8"
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
    peer_provision_path.write_text(
        json.dumps(_peer_provision_doc(provision, _PEER_CREATED_UUID)), encoding="utf-8"
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
    """An explicit 401 is classified pre-effect by #385-9, so the preimage it
    just wrote describes a creation that provably did not happen.

    Without discarding it, the single most common vendor failure (an expired
    bearer token) would pin every later invocation at CREATE_EFFECT_UNKNOWN
    forever, making the promised capability permanently unreachable.
    """
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    intent_path = tmp_path / "peer_intent.json"
    transport = _PeerTransport()
    transport.set_candidates_sequence([])
    transport.create_response = vendors._BoundedResponse(401, {})

    out = io.StringIO()
    code = vendors.main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path), "--confirmed"],
        peer_intent_path=str(intent_path),
        peer_provision_path=str(tmp_path / "peer_provision.json"),
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
    # The capability is still reachable: no stale preimage was left behind.
    assert not intent_path.exists()


def test_peer_ambiguous_response_keeps_its_preimage(tmp_path):
    """The converse of the pre-effect discard: a LOST response must retain the
    preimage, because a profile may well have been created."""
    provision = _valid_provision("multilogin")
    path = _write_provision(tmp_path, provision)
    intent_path = tmp_path / "peer_intent.json"
    transport = _PeerTransport()
    transport.set_candidates_sequence([], [])
    transport.create_raises = True

    out = io.StringIO()
    vendors.main(
        ["create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path), "--confirmed"],
        peer_intent_path=str(intent_path),
        peer_provision_path=str(tmp_path / "peer_provision.json"),
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
    transport.set_candidates_sequence([], [_peer_record(peer_name, id="census-id-Y")])
    transport.create_response = _peer_create_success(profile_id="acked-id-X")
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=False, commit_intent=lambda: True,
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
        intent_present=False, commit_intent=lambda: True,
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
        _peer_record(peer_name, id="dup-1"), _peer_record(peer_name, id="dup-2"),
    ]
    transport = _PeerTransport()
    transport.set_candidates_sequence(rows)
    client = _peer_client(transport)
    receipt = client.create_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR,
        intent_present=True, commit_intent=lambda: True,
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


# --- #385-13: wrong id / replaced identity / bound / running / unowned ---


@pytest.mark.parametrize(
    "mutation",
    ("wrong_id", "replaced_identity", "folder_mismatch", "still_bound", "running", "unowned"),
)
def test_peer_d13_non_exact_target_emits_zero_remove_requests(mutation):
    peer_name = _peer_name()
    record = _peer_record(peer_name, id="peer-created-1")
    target_id = "peer-created-1"
    status_by_id = {}
    if mutation == "wrong_id":
        target_id = "some-other-id"
    elif mutation == "replaced_identity":
        record["browser_type"] = "stealthfox"
    elif mutation == "folder_mismatch":
        record["folder_id"] = "not-the-anchor-folder"
    elif mutation == "still_bound":
        record["locked_by"] = "other-session"
    elif mutation == "running":
        status_by_id["peer-created-1"] = "browser_running"
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
        [_peer_record(peer_name, id="peer-created-1")], [],
    )
    transport.remove_response = None  # response lost
    client = _peer_client(transport)
    receipt = client.remove_peer_profile(
        folder_id=_PEER_FOLDER, anchor_profile_id=_PEER_ANCHOR, peer_profile_id="peer-created-1",
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
    vendors.main(
        [
            "create-peer-profile", "--vendor", "multilogin", "--provision-path", str(path),
            "--confirmed",
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
