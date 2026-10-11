"""Actual enrollment transactions with synthetic Keychain bytes and HTTP only."""
from __future__ import annotations

import concurrent.futures
from contextlib import contextmanager
import json
import multiprocessing
import sys
import threading

import pytest

from ops.codex_fabric import enroll_executive_mcp as enroll
from ops.codex_fabric import executive_mcp_auth as auth

POLICY = auth.ExecutiveAuthPolicy(
    "https://fixture.invalid/", "https://resource.fixture.invalid/",
    ("mastermind.executive.intent.submit", "mastermind.executive.read"), (), "a" * 64,
)
META = enroll.OidcMetadata(
    "https://fixture.invalid/authorize", "https://fixture.invalid/token",
    "https://fixture.invalid/register",
)
ATTEMPT = "b" * 64
V3 = enroll.AbsenceReconciledRegistration(
    ATTEMPT, enroll.CALLBACK_URL, POLICY.policy_digest,
    enroll.CLIENT_NAME + " " + ATTEMPT[:16], "c" * 64,
)


class SyntheticApi:
    def __init__(self):
        self.raw = None
        self.mutex = threading.Lock()
        self.on_read = lambda snapshot: None
        self.on_write = lambda value: None
        self.reads = 0
        self.writes = 0

    def read(self, service, account):
        assert (service, account) == (enroll.KEYCHAIN_SERVICE, enroll.REGISTRATION_ACCOUNT)
        with self.mutex:
            self.reads += 1
            snapshot = self.raw
        self.on_read(snapshot)
        return snapshot

    def upsert(self, service, account, value):
        assert (service, account) == (enroll.KEYCHAIN_SERVICE, enroll.REGISTRATION_ACCOUNT)
        self.on_write(value)
        with self.mutex:
            self.writes += 1
            self.raw = value


def response():
    return {"client_id": "tpc_fixture_only", "redirect_uris": [enroll.CALLBACK_URL],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none"}


def absence_evidence():
    return dict(observed_attempt_ref=ATTEMPT, observed_redirect_uri=enroll.CALLBACK_URL,
        observed_policy_digest=POLICY.policy_digest, marker_created_at_epoch=100,
        attempt_local_outcome_by_epoch=101, audit_window_start_epoch=90,
        audit_window_end_epoch=110, audit_events_total=5, audit_pages_total=1,
        audit_pagination_complete=True, audit_retention_covers_window=True,
        marker_metadata_digest="d" * 64, audit_receipt_digest="e" * 64,
        inventory_receipt_digest="f" * 64, local_outcome_evidence_digest="1" * 64,
        current_client_match_count=0, create_client_match_count=0,
        dynamic_registration_match_count=0, deleted_tpc_client_match_count=0,
        observed_at_epoch=120)


@pytest.fixture
def mutex(tmp_path, monkeypatch):
    # Exercise the existing real flock implementation in an isolated directory.
    root = tmp_path / "mutex"
    factory = lambda: auth._exclusive_refresh_lock(lock_root=root, timeout_seconds=0)
    monkeypatch.setattr(enroll, "_exclusive_refresh_lock", factory, raising=False)
    return factory


def v3_store():
    api = SyntheticApi()
    store = enroll.KeychainRegistrationStore(api=api)
    store.save_absence_reconciled(V3)
    return api, store


def test_concurrent_cli_resumes_are_held_before_any_io(mutex, monkeypatch):
    api, store = v3_store()
    before = (api.raw, api.reads, api.writes)
    ready = threading.Barrier(2)

    def forbidden(*args, **kwargs):
        pytest.fail("held CLI action attempted I/O")

    for name in ("KeychainRegistrationStore", "load_installed_policy", "discover_metadata",
                 "_post_json", "_exclusive_refresh_lock"):
        monkeypatch.setattr(enroll, name, forbidden)

    def call():
        ready.wait(3)
        return enroll.main(["--resume-legacy-after-absence"], registration_store=store)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(call) for _ in range(2)]
        assert [f.result(3) for f in futures] == [2, 2]
    assert (api.raw, api.reads, api.writes) == before


def test_stale_absence_writer_cannot_overwrite_known_client_reconciliation(mutex, monkeypatch):
    api = SyntheticApi()
    api.raw = json.dumps({"schema": enroll.PENDING_REGISTRATION_SCHEMA_V1,
        "attempt_ref": ATTEMPT, "redirect_uri": enroll.CALLBACK_URL,
        "policy_digest": POLICY.policy_digest}).encode()
    store = enroll.KeychainRegistrationStore(api=api)
    paused, release = threading.Event(), threading.Event()
    errors = []

    @contextmanager
    def queued_lock():
        if threading.current_thread().name == "stale":
            paused.set()
            assert release.wait(3)
        with mutex():
            yield

    monkeypatch.setattr(enroll, "_exclusive_refresh_lock", queued_lock)

    def stale():
        try:
            enroll.reconcile_legacy_pending_absence(POLICY, store=store, **absence_evidence())
        except enroll.EnrollmentError as exc:
            errors.append(type(exc).__name__)

    thread = threading.Thread(target=stale, name="stale")
    thread.start()
    try:
        assert paused.wait(3)
        registration, _ = enroll.reconcile_legacy_pending_registration(
            POLICY, store=store, observed_client_id="tpc_fixture",
            observed_attempt_ref=ATTEMPT, observed_client_name=enroll.CLIENT_NAME,
            observed_redirect_uri=enroll.CALLBACK_URL,
            observed_policy_digest=POLICY.policy_digest,
            observed_match_count=1, observed_at_epoch=120)
        retained = api.raw
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert api.raw == retained
    assert store.load_state() == registration
    assert errors == ["EnrollmentError"]


@pytest.mark.parametrize("entrypoint", ["ensure", "pending", "legacy", "absence", "resume"])
def test_every_mutating_entrypoint_refuses_contention_before_read(mutex, entrypoint):
    api, store = v3_store()
    posts = []
    actions = {
        "ensure": lambda: enroll.ensure_client_registration(
            POLICY, META, store=store, post_json=lambda *a: posts.append(a) or response()),
        "pending": lambda: enroll.reconcile_pending_registration(
            POLICY, store=store, observed_client_id="tpc_fixture", observed_attempt_ref=ATTEMPT,
            observed_client_name=V3.client_name),
        "legacy": lambda: enroll.reconcile_legacy_pending_registration(
            POLICY, store=store, observed_client_id="tpc_fixture", observed_attempt_ref=ATTEMPT,
            observed_client_name=enroll.CLIENT_NAME, observed_redirect_uri=enroll.CALLBACK_URL,
            observed_policy_digest=POLICY.policy_digest, observed_match_count=1, observed_at_epoch=120),
        "absence": lambda: enroll.reconcile_legacy_pending_absence(
            POLICY, store=store, **absence_evidence()),
        "resume": lambda: enroll.resume_legacy_registration_after_absence(
            POLICY, META, store=store, post_json=lambda *a: posts.append(a) or response()),
    }
    raw, reads, writes = api.raw, api.reads, api.writes
    with mutex(), pytest.raises(enroll.EnrollmentError):
        actions[entrypoint]()
    assert (api.raw, api.reads, api.writes, posts) == (raw, reads, writes, [])


@pytest.mark.parametrize("outcome", [response(), OSError("lost"), {}])
def test_enabled_registration_settlement_and_restart_never_post_twice(mutex, outcome):
    api = SyntheticApi()
    store = enroll.KeychainRegistrationStore(api=api)
    posts = []

    def post(url, body):
        assert isinstance(store.load_state(), enroll.PendingRegistration)
        posts.append(body)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    if outcome == response():
        registration = enroll.ensure_client_registration(POLICY, META, store=store, post_json=post)
    else:
        with pytest.raises(enroll.EnrollmentEffectUnknown):
            enroll.ensure_client_registration(POLICY, META, store=store, post_json=post)
    retained = api.raw
    restarted = enroll.KeychainRegistrationStore(api=api)
    if outcome == response():
        assert enroll.ensure_client_registration(POLICY, META, store=restarted, post_json=post) == registration
    else:
        with pytest.raises(enroll.EnrollmentEffectUnknown):
            enroll.ensure_client_registration(POLICY, META, store=restarted, post_json=post)
    assert api.raw == retained
    assert len(posts) == 1
    assert restarted.load_state().policy_digest == POLICY.policy_digest


def test_crash_after_marker_persistence_before_http_retains_fence(mutex):
    api = SyntheticApi()
    store = enroll.KeychainRegistrationStore(api=api)
    posts = []

    def interrupt(snapshot):
        if snapshot is not None and json.loads(snapshot)["schema"] == enroll.PENDING_REGISTRATION_SCHEMA:
            raise KeyboardInterrupt("synthetic interruption before HTTP")

    api.on_read = interrupt
    with pytest.raises(KeyboardInterrupt):
        enroll.ensure_client_registration(
            POLICY, META, store=store, post_json=lambda *a: posts.append(a))
    retained = api.raw
    api.on_read = lambda snapshot: None
    with pytest.raises(enroll.EnrollmentError):
        enroll.ensure_client_registration(POLICY, META,
            store=enroll.KeychainRegistrationStore(api=api), post_json=lambda *a: posts.append(a))
    assert isinstance(store.load_state(), enroll.PendingRegistration)
    assert api.raw == retained
    assert posts == []


@pytest.mark.parametrize("failure", ["storage", "unavailable", "mismatch"])
def test_unknown_fence_blocks_http(mutex, failure):
    api = SyntheticApi()
    store = enroll.KeychainRegistrationStore(api=api)
    posts = []

    def fail_write(value):
        raise OSError("synthetic persistence failure")

    def read(snapshot):
        if snapshot is not None and json.loads(snapshot)["schema"] == enroll.PENDING_REGISTRATION_SCHEMA:
            if failure == "unavailable":
                raise OSError("synthetic readback unavailable")
            api.raw = json.dumps({"schema": enroll.PENDING_REGISTRATION_SCHEMA,
                "attempt_ref": "e" * 64, "client_name": enroll.CLIENT_NAME + " " + "e" * 16,
                "redirect_uri": enroll.CALLBACK_URL, "policy_digest": POLICY.policy_digest}).encode()

    if failure == "storage":
        api.on_write = fail_write
    elif failure == "unavailable":
        api.on_read = read
    else:
        original_read = api.read

        def mismatch_read(service, account):
            snapshot = original_read(service, account)
            read(snapshot)
            return api.raw

        api.read = mismatch_read
    with pytest.raises(enroll.EnrollmentEffectUnknown):
        enroll.ensure_client_registration(
            POLICY, META, store=store, post_json=lambda *a: posts.append(a))
    assert posts == []


@pytest.mark.parametrize("phase", ["factory", "enter"])
def test_mutex_unavailable_never_reads_or_posts(mutex, monkeypatch, phase):
    api, store = v3_store()
    raw, reads, writes = api.raw, api.reads, api.writes

    @contextmanager
    def denied():
        raise auth.ExecutiveAuthError("synthetic lock refusal")
        yield

    def factory():
        if phase == "factory":
            raise auth.ExecutiveAuthError("synthetic lock unavailable")
        return denied()

    monkeypatch.setattr(enroll, "_exclusive_refresh_lock", factory)
    with pytest.raises(enroll.EnrollmentError):
        enroll.resume_legacy_registration_after_absence(POLICY, META, store=store,
            post_json=lambda *a: pytest.fail("HTTP after mutex refusal"))
    assert (api.raw, api.reads, api.writes) == (raw, reads, writes)


@pytest.mark.parametrize("failure", ["storage", "unavailable", "mismatch"])
def test_completed_registration_requires_verified_settlement(mutex, failure):
    api = SyntheticApi()
    store = enroll.KeychainRegistrationStore(api=api)
    posts = []

    def post(url, body):
        posts.append(body)
        if failure == "storage":
            def unavailable_write(value):
                raise OSError("synthetic settlement unavailable")
            api.on_write = unavailable_write
        elif failure == "unavailable":
            def unavailable_read(snapshot):
                raise OSError("synthetic settlement read unavailable")
            api.on_read = unavailable_read
        else:
            # A dropped completion write must not return a successful registration.
            api.upsert = lambda *a: None
        return response()

    with pytest.raises(enroll.EnrollmentEffectUnknown):
        enroll.ensure_client_registration(POLICY, META, store=store, post_json=post)
    assert len(posts) == 1
    with pytest.raises(enroll.EnrollmentError):
        enroll.ensure_client_registration(POLICY, META, store=store,
            post_json=lambda *a: pytest.fail("unsettled operation posted again"))


def _process_ensure(raw, lock_root, sender, http_gate):
    def forbid_live(event, args):
        if event in {"socket.connect", "socket.connect_ex", "socket.bind",
                     "subprocess.Popen", "os.system", "ctypes.dlopen", "ctypes.dlsym"}:
            raise RuntimeError("synthetic process prohibits live I/O: " + event)

    sys.addaudithook(forbid_live)
    api = SyntheticApi()
    api.raw = raw
    store = enroll.KeychainRegistrationStore(api=api)
    enroll._exclusive_refresh_lock = lambda: auth._exclusive_refresh_lock(
        lock_root=lock_root, timeout_seconds=0)
    posts = []

    def post(url, body):
        posts.append(body)
        sender.send("post")
        assert http_gate.wait(3)
        return response()

    try:
        enroll.ensure_client_registration(POLICY, META, store=store, post_json=post)
        result = "success"
    except enroll.EnrollmentError:
        result = "refused"
    sender.send((result, len(posts)))
    sender.close()


def test_existing_mutex_excludes_another_process_through_http(tmp_path):
    # Both children start with the same stale bytes; only real cross-process
    # exclusion can prevent the contender's synthetic POST while the winner holds it.
    api = SyntheticApi()
    context = multiprocessing.get_context("spawn")
    gate = context.Event()
    root = tmp_path / "process-mutex"
    reader1, writer1 = context.Pipe(duplex=False)
    reader2, writer2 = context.Pipe(duplex=False)
    first = context.Process(target=_process_ensure, args=(api.raw, root, writer1, gate))
    second = context.Process(target=_process_ensure, args=(api.raw, root, writer2, gate))
    first.start()
    try:
        assert reader1.poll(3)
        assert reader1.recv() == "post"
        second.start()
        assert reader2.poll(3)
        assert reader2.recv() == ("refused", 0)
    finally:
        gate.set()
        first.join(3)
        if second.pid is not None:
            second.join(3)
    assert not first.is_alive() and not second.is_alive()
    assert reader1.recv() == ("success", 1)
    assert first.exitcode == second.exitcode == 0
