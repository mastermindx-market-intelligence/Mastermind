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
import io
import json
import re
from pathlib import Path

import httpx
import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import nonseat_canary as core
from integrations.chairman_surfaces import nonseat_canary_vendors as vendors

PACKAGE_DIR = Path(core.__file__).resolve().parent
CORE_PATH = Path(core.__file__)
VENDORS_PATH = Path(vendors.__file__)

VENDORS = ("gologin", "multilogin")


# ---------------------------------------------------------------------------
# small local helpers
# ---------------------------------------------------------------------------


def _valid_provision(vendor: str, **overrides) -> dict:
    if vendor == "gologin":
        doc = {
            "schema": core.PROVISION_SCHEMA,
            "vendor": "gologin",
            "profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "benign_origin": "http://127.0.0.1:7777",
            "disposable_ack": core.REQUIRED_ACK,
        }
    else:
        doc = {
            "schema": core.PROVISION_SCHEMA,
            "vendor": "multilogin",
            "profile_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "folder_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "benign_origin": "http://127.0.0.1:7777",
            "disposable_ack": core.REQUIRED_ACK,
        }
    doc.update(overrides)
    return doc


def _write_provision(tmp_path: Path, doc) -> Path:
    path = tmp_path / "provision.json"
    if isinstance(doc, str):
        path.write_text(doc, encoding="utf-8")
    else:
        path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _no_collision_loader():
    return None, []


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


def test_hostile_keychain_reader_argv_excludes_secret():
    captured = {}

    def _fake_run(argv, *, timeout=20.0):
        captured["argv"] = list(argv)
        captured["timeout"] = timeout
        return {"code": 0, "stdout": _SECRET, "stderr": "", "timed_out": False}

    reader = vendors.keychain_credential_reader("gologin", run=_fake_run)
    value = reader()
    assert value == _SECRET
    assert _SECRET not in captured["argv"]
    assert captured["argv"] == [
        core.SECURITY_BIN, "find-generic-password", "-w",
        "-s", core.KEYCHAIN_SERVICE_TEMPLATE.format(vendor="gologin"),
        "-a", core.KEYCHAIN_ACCOUNT,
    ]


def test_hostile_resolve_credential_keychain_exception_degrades_to_absent():
    def _boom():
        raise RuntimeError("keychain exploded")

    cred = core.resolve_credential(vendor="gologin", stdin_text=None, keychain_reader=_boom)
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
    "expired_probed", "expired_ok",
}


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_hermetic_receipts_pass_hygiene_and_closed_keys(vendor):
    receipts = core.run_matrix(**core.build_hermetic_harness(vendor))
    dumped = json.dumps(receipts)
    assert "://" not in dumped
    for row in receipts["rows"]:
        assert set(row.keys()) <= _ALLOWED_ROW_KEYS
        assert row["detail"] == core.DETAILS[row["code"]]


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
    provision = {"benign_origin": "http://127.0.0.1:7777"}
    assert core.allowed_url(provision, "http://127.0.0.1:7777/a") is True
    assert core.allowed_url(provision, "http://127.0.0.1:7777/b") is True
    assert core.allowed_url(provision, "http://127.0.0.1:7777/a/") is False
    assert core.allowed_url(provision, "http://127.0.0.1:7777/a?x=1") is False
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

    dev_nav_public = {a for a in dir(vendors.DevToolsNavigator) if not a.startswith("_") and callable(getattr(vendors.DevToolsNavigator, a))}
    assert dev_nav_public == {"list_pages", "open_url"}

    hermetic_nav_public = {
        a for a in dir(core.HermeticNavigatorFake)
        if not a.startswith("_") and callable(getattr(core.HermeticNavigatorFake, a))
    }
    assert hermetic_nav_public == {"list_pages", "open_url"}


# ---------------------------------------------------------------------------
# 12. no profile-config mutation surface
# ---------------------------------------------------------------------------


def test_falsifier_no_profile_config_mutation_surface():
    for path in (CORE_PATH, VENDORS_PATH):
        lowered = path.read_text(encoding="utf-8").lower()
        for phrase in ("httpx.patch", "httpx.delete"):
            assert phrase not in lowered, f"{path.name} contains forbidden mutation call {phrase!r}"
        for token in ("patch", "delete"):
            assert token not in lowered, f"{path.name} contains forbidden mutation token {token!r}"
        for phrase in ("/browser/update", "profile/update", "fingerprint"):
            assert phrase not in lowered, f"{path.name} contains forbidden mutation phrase {phrase!r}"


def test_falsifier_devtools_endpoint_allowlist():
    vendors_source = VENDORS_PATH.read_text(encoding="utf-8")
    found = set(re.findall(r"/json/\w+", vendors_source))
    assert found <= {"/json/list", "/json/new", "/json/version"}


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
    doc, code = core.load_provision(str(tmp_path / "nope.json"), bindings_loader=_no_collision_loader)
    assert doc is None
    assert code == "PROVISION_MISSING"


def test_hostile_provision_gate_bad_json(tmp_path):
    path = _write_provision(tmp_path, "{not json")
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_bad_schema(tmp_path):
    bad = _valid_provision("gologin")
    bad["schema"] = "wrong.schema.v1"
    path = _write_provision(tmp_path, bad)
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_unknown_key(tmp_path):
    bad = _valid_provision("gologin")
    bad["extra_key"] = "smuggled"
    path = _write_provision(tmp_path, bad)
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_bad_ack(tmp_path):
    bad = _valid_provision("gologin", disposable_ack="not-the-required-ack")
    path = _write_provision(tmp_path, bad)
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


@pytest.mark.parametrize(
    "origin",
    [
        "https://chatgpt.com",
        "http://127.0.0.1:7777/some/path",
        "http://evil.example.com:7777",
    ],
)
def test_hostile_provision_gate_disallowed_origin(tmp_path, origin):
    bad = _valid_provision("gologin", benign_origin=origin)
    path = _write_provision(tmp_path, bad)
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "DISALLOWED_TARGET"


def test_hostile_provision_gate_gologin_with_folder_id(tmp_path):
    bad = _valid_provision("gologin")
    bad["folder_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    path = _write_provision(tmp_path, bad)
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


def test_hostile_provision_gate_multilogin_without_folder_id(tmp_path):
    bad = _valid_provision("multilogin")
    del bad["folder_id"]
    path = _write_provision(tmp_path, bad)
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert doc is None and code == "PROVISION_MISSING"


@pytest.mark.parametrize("vendor", VENDORS)
def test_hostile_provision_gate_valid_ok(tmp_path, vendor):
    good = _valid_provision(vendor)
    path = _write_provision(tmp_path, good)
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert code is None
    assert doc == good


def _chatgpt_binding_doc(profile_id: str) -> dict:
    binding = sb.new_binding(
        work_ref="WS:CCR",
        role="chairman",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={"env_manager": "gologin", "profile_id": profile_id, "url": "https://chatgpt.com/c/session-alpha"},
        observed_at="2026-08-22T00:00:00Z",
        seat_ref="chatgpt-seat-1",
    )
    return {"schema": sb.SCHEMA, "bindings": [binding]}


def test_hostile_provision_gate_seat_collision_same_profile_id(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    colliding_doc = _chatgpt_binding_doc(good["profile_id"])
    doc, code = core.load_provision(str(path), bindings_loader=lambda: (colliding_doc, []))
    assert doc is None and code == "DISALLOWED_TARGET"


def test_hostile_provision_gate_seat_collision_different_profile_id(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    other_doc = _chatgpt_binding_doc("bbbbbbbbbbbbbbbbbbbbbbbb")
    doc, code = core.load_provision(str(path), bindings_loader=lambda: (other_doc, []))
    assert code is None
    assert doc == good


def test_hostile_provision_gate_bindings_problems_fails_closed(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    doc, code = core.load_provision(str(path), bindings_loader=lambda: (None, ["some problem"]))
    assert doc is None and code == "DISALLOWED_TARGET"


def test_hostile_provision_gate_bindings_absent_is_ok(tmp_path):
    good = _valid_provision("gologin")
    path = _write_provision(tmp_path, good)
    doc, code = core.load_provision(str(path), bindings_loader=lambda: (None, []))
    assert code is None
    assert doc == good


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
    assert fake.stop_calls == 1  # C4 release


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
        assert base.startswith("http://127.0.0.1:")

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
    provision = {"benign_origin": "http://127.0.0.1:7777"}
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
    doc, code = core.load_provision(str(path), bindings_loader=_no_collision_loader)
    assert code is None
    assert doc["profile_id"] == good["profile_id"].lower()
    assert doc["folder_id"] == good["folder_id"].lower()


def test_hostile_provision_gate_seat_collision_case_insensitive(tmp_path):
    good = _valid_provision("multilogin")
    lower_profile_id = good["profile_id"]
    good["profile_id"] = lower_profile_id.upper()
    path = _write_provision(tmp_path, good)
    colliding_doc = _chatgpt_binding_doc(lower_profile_id)
    doc, code = core.load_provision(str(path), bindings_loader=lambda: (colliding_doc, []))
    assert doc is None and code == "DISALLOWED_TARGET"


# ---------------------------------------------------------------------------
# 21. B3 — profile-scoped ownership in the live MultiloginClient/GoLoginClient
# ---------------------------------------------------------------------------


def test_hostile_multilogin_repeat_start_guard_before_http(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        def json(self):
            return {"port": 9222}

    def _fake_get(url, **kwargs):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(vendors.httpx, "get", _fake_get)
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"))
    ref = {"profile_id": "p1", "folder_id": "f1"}

    result = client.start(ref)
    assert result == {"profile_id": "p1", "port": 9222}
    assert calls["n"] == 1

    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start(ref)
    assert exc_info.value.code == "BUSY_PROFILE"
    # The second call must never reach HTTP at all.
    assert calls["n"] == 1


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


def test_hostile_multilogin_is_running_externally_profile_scoped(monkeypatch):
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"))

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    monkeypatch.setattr(client, "_status", lambda profile_ref: _Resp(200, {"active": True}))

    ref_p = {"profile_id": "P", "folder_id": "F"}
    ref_q = {"profile_id": "Q", "folder_id": "F"}

    # Before we've started anything, the vendor's "active" is externally owned.
    assert client.is_running_externally(ref_p) is True

    # Simulate having started P (no network — set the profile-scoped state directly).
    client._started_profile_id = "P"
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
    assert receipts["verdict"] == "FAIL"


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


def test_hostile_main_vendor_provision_mismatch_refuses_before_keychain(tmp_path, monkeypatch):
    gologin_doc = _valid_provision("gologin")
    path = _write_provision(tmp_path, gologin_doc)

    def _boom_reader(vendor, run=None):
        raise AssertionError("keychain reader must never be constructed on a vendor mismatch")

    class _BoomClient:
        def __init__(self, *a, **kw):
            raise AssertionError("client must never be constructed on a vendor mismatch")

    monkeypatch.setattr(vendors, "keychain_credential_reader", _boom_reader)
    monkeypatch.setattr(vendors, "MultiloginClient", _BoomClient)
    monkeypatch.setattr(vendors, "GoLoginClient", _BoomClient)

    buf = io.StringIO()
    code = core.main(["--vendor", "multilogin", "--provision-path", str(path)], stdout=buf)
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


def test_hostile_multilogin_start_refuses_closed_on_non_http_error(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("dns failure — not an httpx.HTTPError subclass")

    monkeypatch.setattr(vendors.httpx, "get", _boom)
    client = vendors.MultiloginClient(core.Credential("cred", "stdin"))
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.start({"profile_id": "p", "folder_id": "f"})
    assert exc_info.value.code == "VENDOR_ERROR"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_hostile_gologin_profile_exists_refuses_closed_on_non_http_error(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("dns failure — not an httpx.HTTPError subclass")

    monkeypatch.setattr(vendors.httpx, "get", _boom)
    client = vendors.GoLoginClient(core.Credential("cred", "stdin"))
    with pytest.raises(core.CanaryRefusal) as exc_info:
        client.profile_exists({"profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa"})
    assert exc_info.value.code == "VENDOR_ERROR"
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
