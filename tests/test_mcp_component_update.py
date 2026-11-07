"""Offline invariants for the owned MCP component-update tool.

Source tests only: no installed release, no launchd, no root and no installed file
is read or written. The engine runs against an in-memory FakeHost that models the
gateway (config, plist, launchd registration, the process's running config) and
records every effectful operation, so every crash gap of the happy path can be
exercised and re-entered through ``reconcile``. ``ProductionHost`` is exercised
only through patched ``launchctl`` and temp directories.
"""
from __future__ import annotations

import copy
import dataclasses
import http.client
import itertools
import json
import os
import plistlib

import pytest

from control_plane import executive_installed_peer as installed
from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.metadata import protected_resource_metadata
from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE, load_app_policies
from ops.executive_os import executive_mcp_entry
from ops.executive_os import mcp_component_update as m

ISSUER = "https://issuer.mastermind.example.test"
RESOURCE = "https://executive-app.mastermind.example.test/mcp"
SUBJECT = "chairman-opaque-e1"
OLD_RELEASE = "b" * 40
NEW_RELEASE = "c" * 40
MANIFEST = "a1" * 32
CLOSURE = "b2" * 32
PRIMARY_METADATA_PATH = "/mcp/.well-known/oauth-protected-resource"
PUBLIC_METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
PUBLIC_RESOURCE = "https://mcp.mastermind-x.com/mcp"
PUBLIC_METADATA_URL = "https://mcp.mastermind-x.com/.well-known/oauth-protected-resource/mcp"


# --- fixtures (same shape as tests/test_os_gateway_publication.py) -------------------


def _policy_payload(policy_id, scopes):
    return {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": policy_id,
        "resource": RESOURCE,
        "resource_metadata_url": RESOURCE + "/.well-known/oauth-protected-resource",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/.well-known/jwks.json",
        "required_scopes": list(scopes),
        "allowed_subject_digests": [subject_digest(issuer=ISSUER, subject=SUBJECT)],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 300,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 5,
    }


def _policy(policy_id, scopes):
    return json.loads(json.dumps(
        dataclasses.asdict(load_resource_policy(_policy_payload(policy_id, scopes)))))


def prior_mcp_document(**overrides):
    document = {
        "schema": executive_mcp_entry.CONFIG_SCHEMA,
        "release_sha": OLD_RELEASE,
        "service_uid": 458,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "port": 8443,
        "policies": {
            "read": _policy("gateway-fixture-read", [READ_SCOPE]),
            "submit": _policy("gateway-fixture-submit", sorted([READ_SCOPE, SUBMIT_SCOPE])),
        },
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "executive_mcp_profile": "web_ceo_v3",
    }
    document.update(overrides)
    return document


def prior_plist_document(release=OLD_RELEASE):
    template = copy.deepcopy(installed._EXPECTED_PLIST_PROFILES["gateway"])
    return json.loads(json.dumps(template).replace(
        "{release}", installed._SERVICE_RELEASES + "/" + release))


def mcp_bytes(document):
    return json.dumps(document, sort_keys=True).encode("utf-8") + b"\n"


def plist_bytes(document):
    return plistlib.dumps(document)


PRIOR_CONFIG = mcp_bytes(prior_mcp_document())
PRIOR_PLIST = plist_bytes(prior_plist_document())


def expected_config_after(**overrides):
    """Independent expectation: sorted compact JSON of the prior document with the changes."""
    document = prior_mcp_document(release_sha=NEW_RELEASE, **overrides)
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def expected_plist_after():
    return plistlib.dumps(prior_plist_document(release=NEW_RELEASE))


def digest(raw):
    return m.digest(raw)


# --- FakeHost -----------------------------------------------------------------------


class Crash(BaseException):
    """Process death: BaseException so the engine's ``except Exception`` cannot absorb it."""


class FakeHost:
    EFFECTFUL = ("marker_create", "marker_write", "marker_remove", "preserve", "stage", "replace",
                 "discard_preserved", "discard_staged", "receipt_write", "stop_service",
                 "start_service", "recover_enable")

    def __init__(self, *, config=PRIOR_CONFIG, plist=PRIOR_PLIST):
        self.config = config
        self.plist = plist
        self.running = config  # the config the live process started with
        self.state = "REGISTERED"
        self.marker = None
        self.staged = {}
        self.preserved = {}
        self.receipts = {}
        self.locked = False
        self.lock_busy = False
        self.log = []
        self.violations = []
        self.sleeps = []
        self.root = True
        self.receipts_error = None
        self.release_error = None
        self.closure_error = None
        self.marker_read_error = None
        self.config_read_error = None
        self.manifest = MANIFEST
        self.closure = CLOSURE
        self.crash_at = None
        self.fail_at = {}
        self.fail_after_at = {}
        self.hooks = {}
        self.stop_effective = True
        self.start_effective = True
        self.probe_override = {}
        self.readback_override = {}
        self.readback_error = None
        self.disabled = False
        self.enabled_calls = 0
        self.running_plist = plist  # the plist the live process was launched from
        self.process_error = None  # raised by every launchd observation
        self.process_override = {}  # fields overlaid on the observed process
        self.process_pids = None  # iterator of pids, one per observation (crash loop)
        self.observations = 0
        self.events = []  # read-side trace ("observe" / "probe") plus the start dispatch

    # fault injection ---------------------------------------------------------------

    def arm(self, offset):
        self.crash_at = len(self.log) + offset

    def count(self, name):
        return sum(1 for entry in self.log if entry[0] == name)

    def _effect(self, name, action, detail=None):
        index = len(self.log)
        if self.crash_at is not None and index == self.crash_at:
            raise Crash(name)
        self.log.append((name, detail))
        nth = sum(1 for entry in self.log if entry[0] == name)
        failure = self.fail_at.get((name, nth))
        if failure is not None:
            raise failure
        result = action()
        failure = self.fail_after_at.get((name, nth))
        if failure is not None:
            raise failure
        hook = self.hooks.get((name, nth))
        if hook is not None:
            hook(self)
        return result

    def _dispatched(self, name):
        return self.marker is not None and name in self.marker["dispatched"]

    # read-only host surface --------------------------------------------------------

    def require_root(self):
        if not self.root:
            raise m.UpdateRefused("ROOT_REQUIRED")

    def receipts_ready(self):
        if self.receipts_error is not None:
            raise m.UpdateRefused(self.receipts_error)

    def acquire_lock(self):
        if self.lock_busy:
            raise m.UpdateRefused("LOCK_HELD")
        self.locked = True

    def release_lock(self):
        self.locked = False

    def read_config(self):
        if self.config_read_error is not None:
            raise self.config_read_error
        return self.config

    def read_plist(self):
        return self.plist

    def verify_release(self, release_sha):
        if self.release_error is not None:
            raise m.UpdateRefused(self.release_error)
        return self.manifest

    def verify_closure(self):
        if self.closure_error is not None:
            raise m.UpdateRefused(self.closure_error)
        return self.closure

    def readback(self, release_sha):
        if self.readback_error is not None:
            raise self.readback_error
        value = {
            "schema": "fake.readback",
            "release_sha": release_sha,
            "config_sha256": digest(self.config),
            "release_manifest_sha256": self.manifest,
            "network_closure_sha256": self.closure,
        }
        value.update(self.readback_override)
        return value

    def marker_read(self):
        if self.marker_read_error is not None:
            raise self.marker_read_error
        return copy.deepcopy(self.marker)

    def read_preserved(self, kind, tag):
        return self.preserved.get((kind, tag))

    def staged_digest(self, kind, tag):
        data = self.staged.get((kind, tag))
        return None if data is None else digest(data)

    def receipt_exists(self, name):
        return name in self.receipts

    def service_state(self):
        return self.state

    def service_enabled(self):
        return not self.disabled

    def observe_process(self):
        self.observations += 1
        self.events.append("observe")
        if self.process_error is not None:
            raise self.process_error
        if self.state == "ABSENT":
            raise m.UpdateRefused("PROCESS_OBSERVATION_REFUSED: not running")
        document = plistlib.loads(self.running_plist)
        value = {
            "state": "running",
            "program": document["ProgramArguments"][0],
            "argv": list(document["ProgramArguments"]),
            "working_directory": document["WorkingDirectory"],
            "username": m.GATEWAY_USER,
            "pid": 4242,
        }
        if self.process_pids is not None:
            value["pid"] = next(self.process_pids)
        value.update(self.process_override)
        return value

    def now(self):
        return "2026-10-25T00:00:00Z"

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    # effectful host surface --------------------------------------------------------

    def marker_create(self, marker):
        def action():
            if self.marker is not None:
                raise m.UpdateRefused("TRANSACTION_PRESENT")
            self.marker = copy.deepcopy(marker)
        self._effect("marker_create", action)

    def marker_write(self, marker):
        self._effect("marker_write", lambda: setattr(self, "marker", copy.deepcopy(marker)),
                     detail=(marker["phase"], tuple(marker["dispatched"])))

    def marker_remove(self):
        self._effect("marker_remove", lambda: setattr(self, "marker", None))

    def preserve(self, kind, tag, data):
        self._effect("preserve", lambda: self.preserved.__setitem__((kind, tag), data), detail=kind)

    def stage(self, kind, tag, data):
        self._effect("stage", lambda: self.staged.__setitem__((kind, tag), data), detail=kind)

    def discard_preserved(self, tag):
        def action():
            for kind in m.KINDS:
                self.preserved.pop((kind, tag), None)
        self._effect("discard_preserved", action)

    def discard_staged(self, tag):
        def action():
            for kind in m.KINDS:
                self.staged.pop((kind, tag), None)
        self._effect("discard_staged", action)

    def replace(self, kind, tag):
        def action():
            if self.state != "ABSENT":
                self.violations.append("replace while " + self.state)
            data = self.staged.pop((kind, tag))
            if kind == "config":
                self.config = data
            else:
                self.plist = data
        self._effect("replace", action, detail=kind)

    def receipt_write(self, name, document):
        self._effect("receipt_write", lambda: self.receipts.__setitem__(name, copy.deepcopy(document)),
                     detail=name)

    def stop_service(self):
        def action():
            if not self._dispatched("stop"):
                self.violations.append("stop before recorded dispatch")
            self.disabled = True
            if self.stop_effective:
                self.state = "ABSENT"
        self._effect("stop_service", action)

    def start_service(self):
        def action():
            self.events.append("start")
            if not self._dispatched("start"):
                self.violations.append("start before recorded dispatch")
            if self.state == "REGISTERED":
                self.violations.append("start while REGISTERED")
            self.disabled = False
            if self.start_effective:
                self.state = "REGISTERED"
                self.running = self.config
                self.running_plist = self.plist
        self._effect("start_service", action)

    def recover_enable(self):
        def action():
            if not self._dispatched("recover_enable"):
                self.violations.append("recover_enable before recorded dispatch")
            self.disabled = False
        self._effect("recover_enable", action)

    # the fake gateway --------------------------------------------------------------

    def probe(self, port, probe):
        assert port == 8443
        self.events.append("probe")
        override = self.probe_override.get(probe.name)
        if override is not None:
            if isinstance(override, BaseException):
                raise override
            return override
        if self.state == "ABSENT":
            raise ConnectionRefusedError("gateway down")
        document = json.loads(self.running)
        policies = load_app_policies(document["policies"])
        public = executive_mcp_entry.build_public_policies(
            document, policies, executive_mcp_entry.build_additional_policies(document, policies))
        active = public if public is not None else policies
        metadata_path = PUBLIC_METADATA_PATH if public is not None else PRIMARY_METADATA_PATH
        metadata_url = active.read.resource_metadata_url
        if probe.method == "GET" and probe.path == metadata_path:
            body = json.dumps(protected_resource_metadata(active.submit)).encode("utf-8")
            return m.ProbeResult(200, {"content-type": "application/json"}, body)
        if probe.method == "POST" and probe.path == "/mcp":
            return m.ProbeResult(
                401, {"www-authenticate": 'Bearer error="invalid_token", resource_metadata="' + metadata_url + '"'}, b"")
        return m.ProbeResult(404, {}, b"")


def snapshot(host):
    return copy.deepcopy(host)


def plan_of(host, *, set_public=False, release=NEW_RELEASE):
    result = m.plan(host, release_sha=release, set_public=set_public)
    return result["plan_sha256"]


def apply_of(host, *, set_public=False, release=NEW_RELEASE, plan_sha256=None):
    if plan_sha256 is None:
        plan_sha256 = plan_of(host, set_public=set_public, release=release)
    return m.apply(host, release_sha=release, set_public=set_public, plan_sha256=plan_sha256)


def reconcile_of(host, release=NEW_RELEASE):
    return m.reconcile(host, release_sha=release)


def tag_of(host, *, set_public=False):
    return plan_of(FakeHost(), set_public=set_public)[:12]


def expect(call, exception, code):
    with pytest.raises(exception) as caught:
        call()
    assert caught.value.code == code
    return caught.value


def assert_no_effect(host):
    assert host.log == []
    assert host.config == PRIOR_CONFIG and host.plist == PRIOR_PLIST
    assert host.state == "REGISTERED"
    assert host.locked is False


def assert_clean_prior(host):
    assert host.config == PRIOR_CONFIG and host.plist == PRIOR_PLIST
    assert host.state == "REGISTERED"
    assert host.marker is None
    assert host.violations == []
    assert host.locked is False


def assert_complete(host, *, set_public=False):
    after = expected_config_after(**({"public_mcp_resource": PUBLIC_RESOURCE} if set_public else {}))
    assert host.config == after
    assert host.plist == expected_plist_after()
    assert host.state == "REGISTERED"
    assert host.running == after
    assert host.marker is None
    assert host.violations == []
    assert host.locked is False
    assert host.disabled is False
    assert len([name for name in host.receipts if name.endswith("-v1.json") and "aborted" not in name]) == 1


# --- compile / pure -----------------------------------------------------------------


def test_release_only_candidate_matches_independent_expectation():
    candidate = m.compile_candidate(PRIOR_CONFIG, PRIOR_PLIST, release_sha=NEW_RELEASE,
                                    set_public_mcp_resource=False)
    assert candidate.config_after == expected_config_after()
    assert candidate.plist_after == expected_plist_after()
    assert candidate.config_before == PRIOR_CONFIG and candidate.plist_before == PRIOR_PLIST
    assert candidate.public_mode_after is False and candidate.port == 8443
    assert candidate.prior_release_sha == OLD_RELEASE and candidate.release_sha == NEW_RELEASE
    assert [probe.name for probe in candidate.probes_before] == ["metadata", "challenge"]
    assert [probe.name for probe in candidate.probes_after] == ["metadata", "challenge"]
    assert json.loads(candidate.config_after)["release_sha"] == NEW_RELEASE
    assert "public_mcp_resource" not in json.loads(candidate.config_after)


def test_set_public_candidate_adds_only_the_public_audience():
    candidate = m.compile_candidate(PRIOR_CONFIG, PRIOR_PLIST, release_sha=NEW_RELEASE,
                                    set_public_mcp_resource=True)
    assert candidate.config_after == expected_config_after(public_mcp_resource=PUBLIC_RESOURCE)
    assert candidate.plist_after == expected_plist_after()
    assert candidate.public_mode_after is True
    assert [probe.name for probe in candidate.probes_before] == ["metadata", "challenge"]
    assert [probe.name for probe in candidate.probes_after] == ["metadata", "challenge", "primary-metadata-absent"]
    before = json.loads(candidate.config_before)
    after = json.loads(candidate.config_after)
    assert {key for key in set(before) | set(after) if before.get(key) != after.get(key)} == {
        "release_sha", "public_mcp_resource"}


def test_probes_use_literal_paths_statuses_and_challenge_url():
    prior = m.build_probes(prior_mcp_document())
    assert [(p.name, p.method, p.path, p.expect_status) for p in prior] == [
        ("metadata", "GET", PRIMARY_METADATA_PATH, 200),
        ("challenge", "POST", "/mcp", 401),
    ]
    assert prior[1].challenge_resource_metadata == RESOURCE + "/.well-known/oauth-protected-resource"
    public = m.build_probes(prior_mcp_document(public_mcp_resource=PUBLIC_RESOURCE))
    assert [(p.name, p.method, p.path, p.expect_status) for p in public] == [
        ("metadata", "GET", PUBLIC_METADATA_PATH, 200),
        ("challenge", "POST", "/mcp", 401),
        ("primary-metadata-absent", "GET", PRIMARY_METADATA_PATH, 404),
    ]
    assert public[1].challenge_resource_metadata == PUBLIC_METADATA_URL
    assert json.loads(m.INITIALIZE_BODY)["method"] == "initialize"
    assert dict(public[1].headers)["content-type"] == "application/json"


def test_metadata_probe_expects_the_submit_policy_metadata():
    policies = load_app_policies(prior_mcp_document()["policies"])
    expected = json.loads(json.dumps(protected_resource_metadata(policies.submit)))
    assert m.build_probes(prior_mcp_document())[0].expect_json == expected


@pytest.mark.parametrize("label,release,set_public,config,plist,fragment", [
    ("same-release", OLD_RELEASE, False, PRIOR_CONFIG, PRIOR_PLIST, "equals the installed release"),
    ("short-sha", "abc", False, PRIOR_CONFIG, PRIOR_PLIST, "target release sha shape"),
    ("upper-sha", "C" * 40, False, PRIOR_CONFIG, PRIOR_PLIST, "target release sha shape"),
    ("public-already", NEW_RELEASE, True,
     mcp_bytes(prior_mcp_document(public_mcp_resource=PUBLIC_RESOURCE)), PRIOR_PLIST, "already configured"),
    ("legacy-profile", NEW_RELEASE, False,
     mcp_bytes({k: v for k, v in prior_mcp_document().items() if k != "executive_mcp_profile"}),
     PRIOR_PLIST, "not web_ceo_v3"),
    ("empty-config", NEW_RELEASE, False, b"", PRIOR_PLIST, "byte budget"),
    ("not-json", NEW_RELEASE, False, b"{nope", PRIOR_PLIST, "JSON refused"),
    ("config-array", NEW_RELEASE, False, b"[]\n", PRIOR_PLIST, "JSON refused"),
    ("empty-plist", NEW_RELEASE, False, PRIOR_CONFIG, b"", "byte budget"),
    ("plist-release-mismatch", NEW_RELEASE, False, PRIOR_CONFIG,
     plist_bytes(prior_plist_document(release="e" * 40)), "release join differs"),
])
def test_candidate_refusals(label, release, set_public, config, plist, fragment):
    with pytest.raises(m.UpdateRefused) as caught:
        m.compile_candidate(config, plist, release_sha=release, set_public_mcp_resource=set_public)
    assert caught.value.code.startswith("CANDIDATE_REFUSED: ")
    assert fragment in caught.value.code


def test_candidate_refuses_plist_off_profile():
    document = prior_plist_document()
    document["RunAtLoad"] = not document.get("RunAtLoad", True)
    with pytest.raises(m.UpdateRefused) as caught:
        m.compile_candidate(PRIOR_CONFIG, plist_bytes(document), release_sha=NEW_RELEASE,
                            set_public_mcp_resource=False)
    assert "closed installed gateway profile" in caught.value.code


def test_candidate_refuses_an_unvalidated_prior_document():
    broken = prior_mcp_document()
    broken["port"] = 80
    with pytest.raises(m.UpdateRefused) as caught:
        m.compile_candidate(mcp_bytes(broken), PRIOR_PLIST, release_sha=NEW_RELEASE,
                            set_public_mcp_resource=False)
    assert caught.value.code.startswith("CANDIDATE_REFUSED: ")


def test_candidate_maps_an_auth_policy_error_to_a_bounded_refusal(monkeypatch):
    # The auth-policy loaders raise AuthError (not ValueError); the tool must still refuse cleanly
    # instead of letting a traceback escape from the root-owned CLI.
    def invalid(document):
        raise AuthError(AuthErrorCode.INVALID_POLICY)

    monkeypatch.setattr(m, "_semantic", invalid)
    with pytest.raises(m.UpdateRefused) as caught:
        m.compile_candidate(PRIOR_CONFIG, PRIOR_PLIST, release_sha=NEW_RELEASE,
                            set_public_mcp_resource=False)
    assert caught.value.code == "CANDIDATE_REFUSED: auth policy invalid_policy"


def test_candidate_never_mutates_its_inputs_or_the_prior_document():
    config = bytes(PRIOR_CONFIG)
    plist = bytes(PRIOR_PLIST)
    m.compile_candidate(config, plist, release_sha=NEW_RELEASE, set_public_mcp_resource=True)
    assert config == PRIOR_CONFIG and plist == PRIOR_PLIST


def test_plan_document_and_digest_are_deterministic_and_flag_sensitive():
    a = m.compile_candidate(PRIOR_CONFIG, PRIOR_PLIST, release_sha=NEW_RELEASE, set_public_mcp_resource=False)
    b = m.compile_candidate(PRIOR_CONFIG, PRIOR_PLIST, release_sha=NEW_RELEASE, set_public_mcp_resource=True)
    pa = m.plan_document(a, manifest_sha256=MANIFEST, closure_sha256=CLOSURE)
    pa2 = m.plan_document(a, manifest_sha256=MANIFEST, closure_sha256=CLOSURE)
    pb = m.plan_document(b, manifest_sha256=MANIFEST, closure_sha256=CLOSURE)
    assert pa == pa2 and m.plan_digest(pa) == m.plan_digest(pa2)
    assert m.plan_digest(pa) != m.plan_digest(pb)
    assert m.plan_digest(pa) != m.plan_digest(m.plan_document(a, manifest_sha256="0" * 64, closure_sha256=CLOSURE))
    assert m.plan_digest(pa) != m.plan_digest(m.plan_document(a, manifest_sha256=MANIFEST, closure_sha256="0" * 64))
    assert pa["schema"] == m.PLAN_SCHEMA and len(pa["effects"]) == 4
    assert pa["config"]["after_sha256"] == digest(expected_config_after())
    assert pa["plist"]["after_sha256"] == digest(expected_plist_after())
    assert pb["public_mode_after"] is True and pa["public_mode_after"] is False


def _probe(name="challenge", **kw):
    base = dict(name=name, method="POST", path="/mcp", headers=(), body=None, expect_status=401)
    base.update(kw)
    return m.Probe(**base)


def test_probe_failure_classification():
    url = PUBLIC_METADATA_URL
    probe = _probe(challenge_resource_metadata=url)
    ok = m.ProbeResult(401, {"www-authenticate": 'Bearer realm="x", resource_metadata="' + url + '"'}, b"")
    assert m.probe_failure(probe, ok) is None
    assert m.probe_failure(probe, m.ProbeResult(200, ok.headers, b"")) == "STATUS"
    assert m.probe_failure(probe, m.ProbeResult(401, {}, b"")) == "CHALLENGE"
    assert m.probe_failure(probe, m.ProbeResult(
        401, {"www-authenticate": 'Basic resource_metadata="' + url + '"'}, b"")) == "CHALLENGE"
    assert m.probe_failure(probe, m.ProbeResult(
        401, {"www-authenticate": 'Bearer resource_metadata="https://other.example/x"'}, b"")) == "CHALLENGE"
    body_probe = _probe("metadata", method="GET", expect_status=200, expect_json={"a": 1})
    assert m.probe_failure(body_probe, m.ProbeResult(200, {}, b'{"a": 1}')) is None
    assert m.probe_failure(body_probe, m.ProbeResult(200, {}, b'{"a": 2}')) == "BODY"
    assert m.probe_failure(body_probe, m.ProbeResult(200, {}, b"<html>")) == "BODY"
    assert m.probe_failure(body_probe, m.ProbeResult(404, {}, b'{"a": 1}')) == "STATUS"


def test_probe_failures_report_unreachable_and_retry_with_sleeps():
    host = FakeHost()
    probes = (_probe("one"), _probe("two"))
    host.probe_override = {"one": OSError("down"), "two": http.client.RemoteDisconnected("bye")}
    assert m.probe_failures(host, 8443, probes, attempts=3) == ["one:UNREACHABLE", "two:UNREACHABLE"]
    assert host.sleeps == [1.0, 1.0]

    host = FakeHost()
    calls = []

    def flaky(port, probe):
        calls.append(probe.name)
        if len(calls) < 3:
            raise ConnectionRefusedError()
        return m.ProbeResult(401, {}, b"")

    host.probe = flaky
    assert m.probe_failures(host, 8443, (_probe("one"),), attempts=5) == []
    assert host.sleeps == [1.0, 1.0] and len(calls) == 3


# --- plan ----------------------------------------------------------------------------


def test_plan_is_read_only_and_deterministic():
    host = FakeHost()
    first = m.plan(host, release_sha=NEW_RELEASE, set_public=False)
    second = m.plan(host, release_sha=NEW_RELEASE, set_public=False)
    assert first == second
    assert host.log == [] and host.locked is False
    assert first["outcome"] == "PLANNED" and first["ok"] is True
    assert first["plan_sha256"] == m.plan_digest(first["plan"])
    assert first["warnings"] == list(m.WARNINGS)
    assert first["plan"]["release_manifest_sha256"] == MANIFEST
    assert first["plan"]["network_closure_sha256"] == CLOSURE
    assert m.plan(host, release_sha=NEW_RELEASE, set_public=True)["plan_sha256"] != first["plan_sha256"]


@pytest.mark.parametrize("attribute,value,code", [
    ("root", False, "ROOT_REQUIRED"),
    ("receipts_error", "RECEIPTS_DIR_UNTRUSTED:x", "RECEIPTS_DIR_UNTRUSTED:x"),
    ("release_error", "RELEASE_UNVERIFIED:x", "RELEASE_UNVERIFIED:x"),
    ("closure_error", "CLOSURE_UNVERIFIED:x", "CLOSURE_UNVERIFIED:x"),
])
def test_plan_refusals_have_no_effect(attribute, value, code):
    host = FakeHost()
    setattr(host, attribute, value)
    expect(lambda: m.plan(host, release_sha=NEW_RELEASE, set_public=False), m.UpdateRefused, code)
    assert_no_effect(host)


def test_plan_refuses_a_bad_candidate_before_touching_the_release():
    host = FakeHost()
    host.release_error = "SHOULD_NOT_BE_REACHED"
    error = expect(lambda: m.plan(host, release_sha=OLD_RELEASE, set_public=False), m.UpdateRefused,
                   "CANDIDATE_REFUSED: target release equals the installed release")
    assert error.code != "SHOULD_NOT_BE_REACHED"


# --- apply: happy paths --------------------------------------------------------------

HAPPY_LOG = [
    "marker_create", "preserve", "preserve", "stage", "stage", "marker_write",
    "marker_write", "stop_service", "replace", "replace", "marker_write",
    "marker_write", "start_service", "marker_write", "receipt_write", "marker_remove",
]


def test_apply_happy_path_release_only():
    host = FakeHost()
    result = apply_of(host)
    assert result["ok"] is True and result["outcome"] == "COMPLETE"
    assert [entry[0] for entry in host.log] == HAPPY_LOG
    assert_complete(host)
    tag = result["plan_sha256"][:12]
    assert host.preserved[("config", tag)] == PRIOR_CONFIG
    assert host.preserved[("plist", tag)] == PRIOR_PLIST
    assert host.staged == {}
    (name, receipt), = host.receipts.items()
    # One name per attempt: release, plan, then the attempt's start stamp (FakeHost.now()).
    assert name == "mcp-component-" + NEW_RELEASE[:12] + "-" + tag + "-20261025000000-v1.json"
    assert receipt["schema"] == m.RECEIPT_SCHEMA and receipt["outcome"] == "COMPLETE"
    argv = plistlib.loads(expected_plist_after())["ProgramArguments"]
    assert receipt["process"] == {"pid": 4242, "program": argv[0]}
    assert receipt["dispatched"] == ["stop", "start"]
    assert receipt["config"] == {"before_sha256": digest(PRIOR_CONFIG), "after_sha256": digest(expected_config_after())}
    assert receipt["plist"]["after_sha256"] == digest(expected_plist_after())
    assert receipt["release_manifest_sha256"] == MANIFEST and receipt["network_closure_sha256"] == CLOSURE
    assert receipt["readback"]["config_sha256"] == digest(expected_config_after())
    assert receipt["probes_after"] == ["metadata", "challenge"]
    assert receipt["before_images"] == ["mcp-update-" + tag + ".config.before", "mcp-update-" + tag + ".plist.before"]
    assert host.count("recover_enable") == 0
    # The process proof brackets the probes: a stable run before them, a hold window after them,
    # and one final confirmation observation.
    assert host.observations == m.PROCESS_STABLE_POLLS + m.PROCESS_HOLD_POLLS + 1


def test_apply_happy_path_set_public():
    host = FakeHost()
    result = apply_of(host, set_public=True)
    assert result["outcome"] == "COMPLETE"
    assert_complete(host, set_public=True)
    (receipt,) = host.receipts.values()
    assert receipt["set_public_mcp_resource"] is True
    assert receipt["probes_after"] == ["metadata", "challenge", "primary-metadata-absent"]
    assert json.loads(host.running)["public_mcp_resource"] == PUBLIC_RESOURCE


def test_apply_marker_phases_are_persisted_before_each_launchd_effect():
    host = FakeHost()
    apply_of(host)
    writes = [entry[1] for entry in host.log if entry[0] == "marker_write"]
    assert writes == [
        ("STAGED", ()),
        ("STOP_DISPATCHED", ("stop",)),
        ("REPLACED", ("stop",)),
        ("START_DISPATCHED", ("stop", "start")),
        ("VERIFIED", ("stop", "start")),
    ]
    names = [entry[0] for entry in host.log]
    assert names.index("marker_write", names.index("preserve")) < names.index("stop_service")
    assert max(i for i, n in enumerate(names) if n == "marker_write" and names[:i].count("marker_write") == 3) \
        < names.index("start_service")


def test_apply_waits_for_the_stop_to_settle_before_replacing():
    host = FakeHost()
    real_state = host.service_state
    lagging = {"polls": 0}

    def state():
        # launchd keeps reporting the label for three polls after the stop was dispatched.
        stopped = any(entry[0] == "stop_service" for entry in host.log)
        if stopped and host.state == "ABSENT" and lagging["polls"] < 3:
            lagging["polls"] += 1
            return "REGISTERED"
        return real_state()

    host.service_state = state
    assert apply_of(host)["outcome"] == "COMPLETE"
    assert lagging["polls"] == 3
    assert len(host.sleeps) >= 3
    assert host.violations == []
    assert host.count("stop_service") == 1 and host.count("start_service") == 1


# --- apply: refusals with no effect ---------------------------------------------------


def test_apply_refuses_a_stale_plan_digest():
    host = FakeHost()
    expect(lambda: apply_of(host, plan_sha256="0" * 64), m.UpdateRefused, "PLAN_DIGEST_MISMATCH")
    assert_no_effect(host)


def test_apply_refuses_when_the_sealed_release_changed_after_the_plan():
    host = FakeHost()
    digest_value = plan_of(host)
    host.manifest = "c3" * 32
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "PLAN_DIGEST_MISMATCH")
    assert_no_effect(host)
    host.manifest = MANIFEST
    host.closure = "d4" * 32
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "PLAN_DIGEST_MISMATCH")
    assert_no_effect(host)


def test_apply_refuses_when_the_installed_files_changed_after_the_plan():
    host = FakeHost()
    digest_value = plan_of(host)
    document = prior_mcp_document()
    document["port"] = 8444
    host.config = mcp_bytes(document)
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "PLAN_DIGEST_MISMATCH")
    assert host.log == [] and host.plist == PRIOR_PLIST


def test_apply_refuses_when_the_lock_is_held():
    host = FakeHost()
    digest_value = plan_of(host)
    host.lock_busy = True
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "LOCK_HELD")
    assert_no_effect(host)


def test_apply_refuses_when_not_root():
    host = FakeHost()
    digest_value = plan_of(host)
    host.root = False
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "ROOT_REQUIRED")
    assert_no_effect(host)


def test_apply_refuses_when_a_transaction_is_present():
    host = FakeHost()
    digest_value = plan_of(host)
    host.marker = {"anything": True}
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "TRANSACTION_PRESENT")
    assert host.log == [] and host.locked is False


def test_apply_refuses_leftover_staged_or_preserved_images():
    host = FakeHost()
    digest_value = plan_of(host)
    tag = digest_value[:12]
    host.staged[("plist", tag)] = b"x"
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "STAGED_PRESENT")
    assert host.log == []
    host.staged.clear()
    host.preserved[("config", tag)] = b"x"
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "PRESERVED_PRESENT")
    assert host.log == []


def test_apply_refuses_an_unregistered_service():
    host = FakeHost()
    digest_value = plan_of(host)
    host.state = "ABSENT"
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "SERVICE_NOT_REGISTERED")
    assert host.log == [] and host.locked is False


def test_apply_refuses_a_registered_but_disabled_gateway():
    # An operator kill switch (launchctl disable) on a still-registered label must not be undone
    # by the tool's own start sequence (which enables the label): refuse before any effect.
    host = FakeHost()
    digest_value = plan_of(host)
    host.disabled = True
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "GATEWAY_DISABLED")
    assert host.log == [] and host.locked is False
    assert host.config == PRIOR_CONFIG and host.plist == PRIOR_PLIST and host.state == "REGISTERED"
    assert host.marker is None


@pytest.mark.parametrize("override", [
    {"metadata": m.ProbeResult(500, {}, b"")},
    {"challenge": m.ProbeResult(200, {}, b"")},
    {"metadata": ConnectionRefusedError("x")},
])
def test_apply_refuses_an_unhealthy_prior_gateway(override):
    host = FakeHost()
    digest_value = plan_of(host)
    host.probe_override = override
    expect(lambda: apply_of(host, plan_sha256=digest_value), m.UpdateRefused, "PRIOR_UNHEALTHY")
    assert host.log == [] and host.locked is False


# --- apply: pre-stop discard paths ------------------------------------------------------


def test_stage_failure_discards_without_touching_launchd():
    host = FakeHost()
    host.fail_at[("stage", 2)] = OSError("disk full")
    result = apply_of(host)
    assert result == {"ok": False, "outcome": "DISCARDED_NO_EFFECT", "code": "STAGE_FAILED"}
    assert_clean_prior(host)
    assert host.staged == {} and host.preserved == {}
    assert host.count("stop_service") == 0 and host.count("start_service") == 0


def test_files_changed_before_stop_discards():
    host = FakeHost()

    def drift(h):
        document = prior_mcp_document()
        document["audit_root"] = "/var/log/mastermind-executive/drift"
        h.config = mcp_bytes(document)

    host.hooks[("marker_write", 1)] = drift
    result = apply_of(host)
    assert result["code"] == "FILES_CHANGED_BEFORE_STOP" and result["outcome"] == "DISCARDED_NO_EFFECT"
    assert host.marker is None and host.staged == {} and host.preserved == {}
    assert host.plist == PRIOR_PLIST and host.state == "REGISTERED"
    assert host.count("stop_service") == 0


def test_gateway_disabled_between_stage_and_stop_discards():
    host = FakeHost()
    host.hooks[("marker_write", 1)] = lambda h: setattr(h, "disabled", True)
    result = apply_of(host)
    assert result == {"ok": False, "outcome": "DISCARDED_NO_EFFECT", "code": "GATEWAY_DISABLED"}
    assert host.marker is None and host.staged == {} and host.preserved == {}
    assert host.count("stop_service") == 0 and host.count("start_service") == 0
    assert host.count("recover_enable") == 0
    assert host.config == PRIOR_CONFIG and host.plist == PRIOR_PLIST and host.state == "REGISTERED"
    # The operator's disable is left exactly as found.
    assert host.disabled is True and host.locked is False


def test_service_gone_before_stop_discards():
    host = FakeHost()
    host.hooks[("marker_write", 1)] = lambda h: setattr(h, "state", "ABSENT")
    result = apply_of(host)
    assert result["code"] == "SERVICE_NOT_REGISTERED" and result["outcome"] == "DISCARDED_NO_EFFECT"
    assert host.marker is None and host.count("stop_service") == 0
    assert host.config == PRIOR_CONFIG


def test_staged_image_drift_before_stop_discards():
    host = FakeHost()

    def drift(h):
        for key in list(h.staged):
            h.staged[key] = b"tampered"

    host.hooks[("marker_write", 1)] = drift
    result = apply_of(host)
    assert result["code"] == "STAGED_IMAGE_MISSING_OR_DRIFTED"
    assert host.marker is None and host.count("stop_service") == 0 and host.config == PRIOR_CONFIG


def test_a_read_error_in_the_last_gate_discards_before_the_stop_is_recorded():
    host = FakeHost()
    host.hooks[("marker_write", 1)] = lambda h: setattr(h, "config_read_error", OSError("eio"))
    result = apply_of(host)
    assert result["code"] == "PRE_STOP_GATE_FAILED" and result["outcome"] == "DISCARDED_NO_EFFECT"
    assert host.count("stop_service") == 0 and host.marker is None


def test_a_failed_stop_dispatch_write_is_effect_unknown_and_never_stops():
    host = FakeHost()
    host.fail_at[("marker_write", 2)] = OSError("eio")
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "UNEXPECTED_OSERROR")
    # The dispatch was appended in memory but never persisted: nothing launchd-related ran.
    assert host.count("stop_service") == 0
    assert host.state == "REGISTERED" and host.config == PRIOR_CONFIG and host.plist == PRIOR_PLIST
    assert host.marker is not None and host.marker["dispatched"] == []
    assert host.locked is False
    # Reconcile sees no recorded stop and discards cleanly.
    result = reconcile_of(host)
    assert result["code"] == "RECONCILE_NO_EFFECT"
    assert_clean_prior(host)


# --- apply: outcomes after the stop -----------------------------------------------------


def test_ineffective_stop_aborts_unchanged_and_re_enables():
    host = FakeHost()
    host.stop_effective = False
    result = apply_of(host)
    assert result == {"ok": False, "outcome": "ABORTED_UNCHANGED", "code": "STOP_DID_NOT_TAKE_EFFECT"}
    assert len(host.sleeps) == m.SETTLE_POLLS - 1
    assert host.count("recover_enable") == 1 and host.disabled is False
    assert host.count("replace") == 0 and host.count("start_service") == 0
    assert_clean_prior(host)
    # Both installed files are provably the before-images, so the redundant copies are gone and a
    # later re-apply of the same plan is not refused on a leftover before-image.
    assert host.staged == {} and host.preserved == {}
    assert host.receipts and all(entry["before_images"] == [] for entry in host.receipts.values())
    (name,) = host.receipts
    assert name.endswith("-aborted-v1.json") and host.receipts[name]["outcome"] == "ABORTED_UNCHANGED"
    assert host.receipts[name]["dispatched"] == ["stop", "recover_enable", "recover_enable_done"]


def test_recover_not_proven_when_the_service_is_not_registered_after_enable():
    host = FakeHost()
    host.stop_effective = False
    host.hooks[("recover_enable", 1)] = lambda h: setattr(h, "state", "ABSENT")
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "RECOVER_NOT_PROVEN")
    assert host.marker is not None and host.count("replace") == 0


def test_recover_not_proven_when_the_prior_probes_fail():
    host = FakeHost()
    host.stop_effective = False
    # The prior gateway was healthy when the plan was taken; after the compensating enable its
    # challenge probe fails, so recovery is not proven and the transaction stays open.
    host.hooks[("recover_enable", 1)] = lambda h: h.probe_override.update(
        {"challenge": m.ProbeResult(500, {}, b"")})
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "RECOVER_NOT_PROVEN")
    assert host.marker is not None
    assert host.violations == []


def _recover_left_unproven(monkeypatch):
    """The stop did not take effect; the service drops out of launchd just after the prior probes pass."""
    host = FakeHost()
    host.stop_effective = False
    armed = [True]
    real = m.probe_failures

    def probe_failures(host_, port, probes, *, attempts):
        failures = real(host_, port, probes, attempts=attempts)
        if armed[0] and host_.count("recover_enable") == 1:
            host_.state = "ABSENT"
        return failures

    monkeypatch.setattr(m, "probe_failures", probe_failures)
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "RECOVER_NOT_PROVEN")
    armed[0] = False
    return host


def test_recover_not_proven_when_the_service_leaves_launchd_after_the_prior_probes(monkeypatch):
    host = _recover_left_unproven(monkeypatch)
    assert host.marker is not None and host.receipts == {}
    assert host.marker["dispatched"] == ["stop", "recover_enable", "recover_enable_done"]
    assert host.count("recover_enable") == 1 and host.violations == []
    # Registered again: observation alone closes the abort, and the enable is never replayed.
    host.state = "REGISTERED"
    result = reconcile_of(host)
    assert result["outcome"] == "ABORTED_UNCHANGED"
    assert host.count("recover_enable") == 1
    assert_clean_prior(host)


def test_an_operator_disable_after_the_compensating_enable_is_not_undone(monkeypatch):
    host = _recover_left_unproven(monkeypatch)
    host.state = "REGISTERED"
    host.disabled = True  # the operator throws the kill switch after the tool's own enable
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "GATEWAY_DISABLED_AFTER_RECOVERY")
    assert host.count("recover_enable") == 1 and host.disabled is True
    assert host.marker is not None and host.receipts == {}
    host.disabled = False
    assert reconcile_of(host)["outcome"] == "ABORTED_UNCHANGED"
    assert host.count("recover_enable") == 1
    assert_clean_prior(host)


def test_start_not_observed_then_reconcile_never_starts_twice():
    host = FakeHost()
    host.start_effective = False
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "START_NOT_OBSERVED")
    assert host.count("start_service") == 1
    assert host.marker["dispatched"] == ["stop", "start"]
    assert host.config == expected_config_after() and host.plist == expected_plist_after()
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "START_NOT_PROVEN")
    assert host.count("start_service") == 1
    # The dispatch stays recorded and the phase is never regressed to REPLACED by the re-entry.
    assert host.marker["phase"] == "START_DISPATCHED" and host.marker["dispatched"] == ["stop", "start"]
    # launchd registers it late: observation alone completes the transaction.
    host.state = "REGISTERED"
    host.running = host.config
    host.running_plist = host.plist
    result = reconcile_of(host)
    assert result["outcome"] == "COMPLETE"
    assert host.count("start_service") == 1
    assert_complete(host)


@pytest.mark.parametrize("failure,code", [
    (m.UpdateRefused("LAUNCHCTL_BOOTSTRAP_FAILED"), "REFUSED_AFTER_DISPATCH:LAUNCHCTL_BOOTSTRAP_FAILED"),
    (m.UpdateRefused("LAUNCHCTL_ENABLE_FAILED"), "REFUSED_AFTER_DISPATCH:LAUNCHCTL_ENABLE_FAILED"),
])
def test_launchctl_refusal_on_start_is_effect_unknown_and_not_replayed(failure, code):
    host = FakeHost()
    host.fail_at[("start_service", 1)] = failure
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    assert host.count("start_service") == 1 and host.marker is not None
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "START_NOT_PROVEN")
    assert host.count("start_service") == 1


def test_launchctl_refusal_on_stop_disable_then_reconcile_aborts_unchanged():
    host = FakeHost()
    host.fail_at[("stop_service", 1)] = m.UpdateRefused("LAUNCHCTL_DISABLE_FAILED")
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "REFUSED_AFTER_DISPATCH:LAUNCHCTL_DISABLE_FAILED")
    assert host.config == PRIOR_CONFIG and host.state == "REGISTERED"
    result = reconcile_of(host)
    assert result["outcome"] == "ABORTED_UNCHANGED"
    assert host.count("stop_service") == 1 and host.count("recover_enable") == 1
    assert_clean_prior(host)


def test_unexpected_error_on_replace_then_reconcile_completes():
    host = FakeHost()
    host.fail_at[("replace", 1)] = OSError("rename failed")
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "UNEXPECTED_OSERROR")
    assert host.state == "ABSENT" and host.config == PRIOR_CONFIG
    assert host.count("stop_service") == 1
    result = reconcile_of(host)
    assert result["outcome"] == "COMPLETE"
    assert host.count("stop_service") == 1 and host.count("start_service") == 1
    assert_complete(host)


def test_foreign_installed_image_is_effect_unknown():
    host = FakeHost()
    host.hooks[("stop_service", 1)] = lambda h: setattr(h, "config", b"{}\n")
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "FOREIGN_IMAGE")
    assert host.count("replace") == 0 and host.count("start_service") == 0
    assert host.marker is not None


def test_mixed_image_while_registered_is_effect_unknown():
    host = FakeHost()
    host.stop_effective = False

    def mix(h):
        h.config = expected_config_after()

    host.hooks[("stop_service", 1)] = mix
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "MIXED_IMAGE_WHILE_REGISTERED")
    assert host.count("start_service") == 0 and host.count("recover_enable") == 0


def test_verify_failure_keeps_the_new_images_and_reconcile_completes_after_the_fault_clears():
    host = FakeHost()
    host.probe_override = {}
    host.hooks[("start_service", 1)] = lambda h: h.probe_override.update(
        {"challenge": m.ProbeResult(200, {}, b"")})
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "VERIFY_FAILED")
    assert host.config == expected_config_after() and host.plist == expected_plist_after()
    assert host.marker["last_verify"] == ["challenge:STATUS"]
    assert host.sleeps.count(1.0) >= m.VERIFY_ATTEMPTS - 1
    assert host.count("start_service") == 1 and host.count("replace") == 2
    host.probe_override = {}
    result = reconcile_of(host)
    assert result["outcome"] == "COMPLETE"
    assert host.count("start_service") == 1 and host.count("stop_service") == 1
    assert_complete(host)


def test_verify_failure_when_unreachable_records_the_reason():
    host = FakeHost()
    host.hooks[("start_service", 1)] = lambda h: h.probe_override.update({"metadata": ConnectionResetError("x")})
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "VERIFY_FAILED")
    assert host.marker["last_verify"] == ["metadata:UNREACHABLE"]


@pytest.mark.parametrize("key", ["release_sha", "config_sha256", "release_manifest_sha256",
                                 "network_closure_sha256"])
def test_readback_join_failure_is_effect_unknown(key):
    host = FakeHost()
    host.readback_override = {key: "f" * (40 if key == "release_sha" else 64)}
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "READBACK_JOIN_FAILED")
    assert host.config == expected_config_after() and host.count("start_service") == 1
    assert host.marker is not None and host.receipts == {}


def test_readback_exception_is_effect_unknown_without_a_receipt():
    host = FakeHost()
    host.readback_error = m.UpdateRefused("READBACK_UNAVAILABLE")
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "REFUSED_AFTER_DISPATCH:READBACK_UNAVAILABLE")
    host.readback_error = RuntimeError("boom")
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "UNEXPECTED_RUNTIMEERROR")
    assert host.receipts == {} and host.marker is not None


# --- reconcile ----------------------------------------------------------------------


def _interrupted_after_stop(host=None):
    host = host or FakeHost()
    host.stop_effective = False
    host.fail_at[("stop_service", 1)] = m.UpdateRefused("LAUNCHCTL_DISABLE_FAILED")
    with pytest.raises(m.TransactionEffectUnknown):
        apply_of(host)
    host.fail_at.clear()
    host.stop_effective = True
    return host


def test_reconcile_without_a_transaction_refuses():
    host = FakeHost()
    expect(lambda: reconcile_of(host), m.UpdateRefused, "NO_TRANSACTION")
    assert host.log == []


def test_reconcile_refuses_a_different_release():
    host = _interrupted_after_stop()
    expect(lambda: reconcile_of(host, release="d" * 40), m.UpdateRefused, "RELEASE_DIFFERS_FROM_TRANSACTION")
    assert host.marker is not None


def test_reconcile_requires_root_and_the_lock():
    host = _interrupted_after_stop()
    host.root = False
    expect(lambda: reconcile_of(host), m.UpdateRefused, "ROOT_REQUIRED")
    host.root = True
    host.lock_busy = True
    expect(lambda: reconcile_of(host), m.UpdateRefused, "LOCK_HELD")
    assert host.marker is not None


def test_reconcile_unreadable_marker_is_effect_unknown():
    host = _interrupted_after_stop()
    host.marker_read_error = OSError("eio")
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "MARKER_UNREADABLE")
    assert host.locked is False


@pytest.mark.parametrize("corruption", [
    lambda mk: mk.pop("last_verify"),
    lambda mk: mk.update(extra=1),
    lambda mk: mk.update(schema="other"),
    lambda mk: mk.update(plan_sha256="zz"),
    lambda mk: mk.update(release_sha="abc"),
    lambda mk: mk.update(phase="NOPE"),
    lambda mk: mk.update(dispatched=["stop", "stop"]),
    lambda mk: mk.update(dispatched=["format-disk"]),
    lambda mk: mk.update(dispatched=["stop", "recover_enable_done"]),
    lambda mk: mk.update(dispatched=["stop", "recover_enable_done", "recover_enable"]),
    lambda mk: mk.update(dispatched=["stop", "recover_enable", "recover_enable"]),
    lambda mk: mk.update(dispatched="stop"),
    lambda mk: mk.update(set_public_mcp_resource=1),
    lambda mk: mk.update(last_verify="x"),
])
def test_reconcile_malformed_marker_is_effect_unknown(corruption):
    host = _interrupted_after_stop()
    corruption(host.marker)
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "MARKER_MALFORMED")
    assert host.count("start_service") == 0 and host.count("replace") == 0


def test_reconcile_missing_or_drifted_before_images_are_effect_unknown():
    host = _interrupted_after_stop()
    tag = host.marker["plan_sha256"][:12]
    saved = dict(host.preserved)
    del host.preserved[("config", tag)]
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "BEFORE_IMAGE_MISSING")
    host.preserved = dict(saved)
    host.preserved[("plist", tag)] = b"changed"
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "BEFORE_IMAGE_DRIFTED")


def test_reconcile_after_image_drift_is_effect_unknown():
    host = _interrupted_after_stop()
    host.marker["config_after_sha256"] = "0" * 64
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "AFTER_IMAGE_DRIFTED")


def test_reconcile_unrecompilable_before_image_is_effect_unknown():
    host = _interrupted_after_stop()
    tag = host.marker["plan_sha256"][:12]
    garbage = b"not json at all"
    host.preserved[("config", tag)] = garbage
    host.marker["config_before_sha256"] = digest(garbage)
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "CANDIDATE_UNAVAILABLE_UPDATEREFUSED")


# --- process identity: a probe answer alone does not prove the new release is running ------


def _identity_failure_state(host, code):
    """After a process-identity failure: new images stay, one start, no receipt, reason recorded."""
    assert host.config == expected_config_after() and host.plist == expected_plist_after()
    assert host.state == "REGISTERED" and host.violations == [] and host.locked is False
    assert host.count("stop_service") == 1 and host.count("start_service") == 1
    assert host.count("replace") == 2 and host.count("recover_enable") == 0
    assert host.marker is not None and host.marker["last_verify"] == [code]
    assert host.receipts == {}


def test_a_crash_looping_new_release_is_effect_unknown_and_never_rolled_back():
    baseline = FakeHost()
    apply_of(baseline)
    # Settling sleeps only: the baseline's stage-A gaps and hold-window sleeps are the identity proof.
    other_sleeps = len(baseline.sleeps) - (m.PROCESS_STABLE_POLLS - 1) - m.PROCESS_HOLD_POLLS
    host = FakeHost()
    host.process_pids = iter(range(1000, 1000 + 10 * m.PROCESS_POLLS))  # a new pid on every poll
    code = "PROCESS_IDENTITY_NOT_PROVEN:PID_CHANGED"
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    _identity_failure_state(host, code)
    assert host.observations == m.PROCESS_POLLS
    assert len(host.sleeps) == other_sleeps + m.PROCESS_POLLS - 1
    assert all(seconds == 1.0 for seconds in host.sleeps)
    # The fault clears: the read-only re-verification completes without a second stop or start.
    host.process_pids = None
    result = reconcile_of(host)
    assert result["outcome"] == "COMPLETE"
    assert host.count("stop_service") == 1 and host.count("start_service") == 1
    assert_complete(host)
    (receipt,) = host.receipts.values()
    assert receipt["process"]["pid"] == 4242


@pytest.mark.parametrize("override,reasons", [
    ({"argv": ["/bin/other"]}, "ARGV"),
    ({"program": "/bin/other"}, "ARGV"),
    ({"working_directory": "/tmp"}, "WORKING_DIRECTORY"),
    ({"username": "root"}, "USER"),
    ({"state": "waiting"}, "STATE"),
    ({"pid": 0}, "PID"),
    ({"pid": "4242"}, "PID"),
    ({"pid": True}, "PID"),
    ({"state": "waiting", "username": "root"}, "STATE,USER"),
    ({"argv": ["/bin/other"], "working_directory": "/tmp", "username": "root", "pid": -1},
     "ARGV,WORKING_DIRECTORY,USER,PID"),
])
def test_a_process_that_is_not_the_after_image_gateway_is_effect_unknown(override, reasons):
    host = FakeHost()
    host.process_override = dict(override)
    code = "PROCESS_IDENTITY_NOT_PROVEN:" + reasons
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    _identity_failure_state(host, code)
    assert host.observations == m.PROCESS_POLLS
    host.process_override = {}
    assert reconcile_of(host)["outcome"] == "COMPLETE"
    assert host.count("stop_service") == 1 and host.count("start_service") == 1
    assert_complete(host)


def test_a_process_still_running_the_before_image_plist_is_not_the_new_release():
    host = FakeHost()
    # The start was dispatched and the label registered, but launchd still reports the old program.
    host.hooks[("start_service", 1)] = lambda h: setattr(h, "running_plist", PRIOR_PLIST)
    code = "PROCESS_IDENTITY_NOT_PROVEN:ARGV,WORKING_DIRECTORY"
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    _identity_failure_state(host, code)
    host.running_plist = host.plist
    assert reconcile_of(host)["outcome"] == "COMPLETE"
    assert host.count("start_service") == 1
    assert_complete(host)


def test_an_unobservable_process_is_effect_unknown_with_the_observation_reason():
    host = FakeHost()
    host.process_error = m.UpdateRefused("LAUNCHD_DOWN")
    code = "PROCESS_IDENTITY_NOT_PROVEN:OBSERVATION:LAUNCHD_DOWN"
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    _identity_failure_state(host, code)
    assert host.observations == m.PROCESS_POLLS


def test_a_transient_launchd_observation_refusal_is_retried_within_the_bound():
    host = FakeHost()
    host.process_error = m.UpdateRefused("LAUNCHD_BUSY")
    real_sleep = host.sleep

    def sleep(seconds):
        real_sleep(seconds)
        if len(host.sleeps) >= 2:
            host.process_error = None

    host.sleep = sleep
    assert apply_of(host)["outcome"] == "COMPLETE"
    # Failed stage-A observations cost extra polls, bounded by the stage-A budget, then the hold
    # window and the final observation.
    clean = m.PROCESS_STABLE_POLLS + m.PROCESS_HOLD_POLLS + 1
    assert clean < host.observations < m.PROCESS_POLLS + m.PROCESS_HOLD_POLLS + 1
    assert_complete(host)


def test_one_pid_change_while_the_new_release_settles_is_tolerated():
    host = FakeHost()
    # A first launch replaced once, then stable; the stable pid is the one held after the probes.
    host.process_pids = itertools.chain([5000, 5001, 5001, 5001], itertools.repeat(5001))
    assert apply_of(host)["outcome"] == "COMPLETE"
    assert host.observations == 4 + m.PROCESS_HOLD_POLLS + 1
    (receipt,) = host.receipts.values()
    assert receipt["process"]["pid"] == 5001
    assert_complete(host)


def test_a_flapping_pid_never_accumulates_a_stable_run_across_a_change():
    host = FakeHost()
    # Two matching polls, a change, two matching polls: no run reaches the stable count.
    pids = [7000, 7000, 7001, 7001] * 4
    host.process_pids = iter(pids)
    code = "PROCESS_IDENTITY_NOT_PROVEN:PID_CHANGED"
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    _identity_failure_state(host, code)


# --- process identity brackets the probes ------------------------------------------------------


def _runs(events):
    """Collapse consecutive duplicates: ["a", "a", "b"] -> [("a", 2), ("b", 1)]."""
    runs = []
    for event in events:
        if runs and runs[-1][0] == event:
            runs[-1][1] += 1
        else:
            runs.append([event, 1])
    return [tuple(run) for run in runs]


def _after_start(host):
    return host.events[host.events.index("start") + 1:]


def _degrade_after(host, clean, **overlay):
    """From the (clean + 1)th launchd observation on, the observed process carries ``overlay``."""
    real = host.observe_process

    def observe():
        value = real()
        if host.observations > clean:
            value.update(overlay)
        return value

    host.observe_process = observe


def _unobservable_after(host, clean, error):
    """From the (clean + 1)th launchd observation on, every observation is refused with ``error``."""
    real = host.observe_process

    def observe():
        if host.observations >= clean:
            host.process_error = error
        return real()

    host.observe_process = observe


def _heal(host):
    host.__dict__.pop("observe_process", None)
    host.__dict__.pop("probe", None)
    host.process_error = None


# Observations are counted from the start dispatch: STABLE before the first probe pass, HOLD after it,
# then one final observation after the second probe pass.
HOLD_START = m.PROCESS_STABLE_POLLS
HOLD_END = m.PROCESS_STABLE_POLLS + m.PROCESS_HOLD_POLLS
CLEAN_BEFORE_FAILURE = [
    pytest.param(HOLD_START, id="first-hold-poll"),
    pytest.param(HOLD_START + 5, id="mid-hold"),
    pytest.param(HOLD_END - 1, id="last-hold-poll"),
    pytest.param(HOLD_END, id="final-observation-only"),
]


def test_the_process_proof_brackets_the_probes_in_order():
    host = FakeHost()
    assert apply_of(host)["outcome"] == "COMPLETE"
    runs = _runs(_after_start(host))
    assert [kind for kind, _ in runs] == ["observe", "probe", "observe", "probe", "observe"]
    counts = [count for _, count in runs]
    assert counts[0] == m.PROCESS_STABLE_POLLS
    assert counts[2] == m.PROCESS_HOLD_POLLS
    assert counts[4] == 1
    assert counts[1] == counts[3] >= 1
    assert host.observations == HOLD_END + 1


def test_no_probe_runs_while_the_process_identity_is_unproven():
    host = FakeHost()
    host.process_override = {"username": "root"}
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "PROCESS_IDENTITY_NOT_PROVEN:USER")
    assert "probe" not in _after_start(host)


@pytest.mark.parametrize("clean", CLEAN_BEFORE_FAILURE)
@pytest.mark.parametrize("overlay,reason", [
    ({"pid": 9999}, "PID_CHANGED"),
    ({"state": "waiting"}, "STATE"),
    ({"username": "root"}, "USER"),
])
def test_a_release_that_changes_after_the_probes_answered_is_effect_unknown(clean, overlay, reason):
    baseline = FakeHost()
    apply_of(baseline)
    per_pass = _runs(_after_start(baseline))[1][1]
    host = FakeHost()
    _degrade_after(host, clean, **overlay)
    code = "PROCESS_IDENTITY_NOT_PROVEN:AFTER_PROBES:" + reason
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    _identity_failure_state(host, code)
    assert host.observations == clean + 1
    # The probes had answered healthy: only the process observation after them caught the change.
    passes = 2 if clean == HOLD_END else 1
    assert _after_start(host).count("probe") == per_pass * passes
    # The fault clears: read-only re-verification completes without a second stop or start.
    _heal(host)
    assert reconcile_of(host)["outcome"] == "COMPLETE"
    assert host.count("stop_service") == 1 and host.count("start_service") == 1
    assert_complete(host)
    (receipt,) = host.receipts.values()
    assert receipt["process"]["pid"] == 4242


@pytest.mark.parametrize("clean", CLEAN_BEFORE_FAILURE)
def test_launchd_losing_the_process_after_the_probes_is_effect_unknown(clean):
    host = FakeHost()
    _unobservable_after(host, clean, m.UpdateRefused("LAUNCHD_GONE"))
    code = "PROCESS_IDENTITY_NOT_PROVEN:AFTER_PROBES:OBSERVATION:LAUNCHD_GONE"
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, code)
    _identity_failure_state(host, code)
    assert host.observations == clean + 1
    _heal(host)
    assert reconcile_of(host)["outcome"] == "COMPLETE"
    assert host.count("stop_service") == 1 and host.count("start_service") == 1
    assert_complete(host)


def test_a_probe_failure_after_the_hold_window_is_verify_failed_with_a_short_recheck():
    baseline = FakeHost()
    apply_of(baseline)
    per_pass = _runs(_after_start(baseline))[1][1]
    host = FakeHost()
    real = host.probe
    failing = []

    def probe(port, spec):
        if host.observations >= HOLD_END:
            failing.append(spec.name)
            return m.ProbeResult(500, {}, b"")
        return real(port, spec)

    host.probe = probe
    expect(lambda: apply_of(host), m.TransactionEffectUnknown, "VERIFY_FAILED")
    # The recheck is bounded by its own, shorter attempt count and ran after the hold window.
    assert len(failing) == per_pass * m.PROBE_RECHECK_ATTEMPTS
    assert host.observations == HOLD_END
    assert host.marker is not None and host.marker["last_verify"]
    assert not any(entry.startswith("PROCESS_IDENTITY") for entry in host.marker["last_verify"])
    assert host.config == expected_config_after() and host.receipts == {}
    assert host.count("stop_service") == 1 and host.count("start_service") == 1
    _heal(host)
    assert reconcile_of(host)["outcome"] == "COMPLETE"
    assert_complete(host)


# --- aborts: re-apply, re-entry and cleanup --------------------------------------------


def test_reapplying_the_same_plan_after_an_abort_writes_a_distinct_receipt():
    host = FakeHost()
    digest_value = plan_of(host)
    host.stop_effective = False
    assert apply_of(host, plan_sha256=digest_value)["outcome"] == "ABORTED_UNCHANGED"
    (aborted,) = host.receipts
    assert aborted.endswith("-20261025000000-aborted-v1.json")
    host.stop_effective = True
    host.now = lambda: "2026-10-25T01:00:00Z"
    result = apply_of(host, plan_sha256=digest_value)
    assert result["outcome"] == "COMPLETE" and host.violations == []
    assert_complete(host)
    assert aborted in host.receipts and len(host.receipts) == 2
    (complete,) = [name for name in host.receipts if "aborted" not in name]
    assert complete.endswith("-20261025010000-v1.json")
    assert host.receipts[aborted]["outcome"] == "ABORTED_UNCHANGED"
    assert host.receipts[complete]["outcome"] == "COMPLETE"


def _abort_crashed_after_the_before_images_were_removed():
    host = FakeHost()
    host.stop_effective = False
    host.fail_after_at[("discard_preserved", 1)] = Crash("died after the before-images were removed")
    with pytest.raises(Crash):
        apply_of(host)
    host.locked = False  # the lock dies with the process
    host.fail_after_at.clear()
    return host


def test_an_abort_that_died_after_removing_the_before_images_closes_on_reentry():
    host = _abort_crashed_after_the_before_images_were_removed()
    # The copies are gone but the marker and the aborted receipt are not: the old re-entry path
    # would have demanded a before-image that no longer exists.
    assert host.preserved == {} and host.marker is not None
    assert any(name.endswith("-aborted-v1.json") for name in host.receipts)
    result = reconcile_of(host)
    assert result == {"ok": False, "outcome": "ABORTED_UNCHANGED", "code": "STOP_DID_NOT_TAKE_EFFECT"}
    assert host.count("stop_service") == 1 and host.count("start_service") == 0
    assert host.count("recover_enable") == 1 and host.count("replace") == 0
    assert_clean_prior(host)
    assert host.staged == {} and host.preserved == {}
    assert _reconcile_outcome(host)[0] == "NO_TRANSACTION"


@pytest.mark.parametrize("change", [
    lambda h: setattr(h, "state", "ABSENT"),
    lambda h: setattr(h, "config", expected_config_after()),
    lambda h: setattr(h, "plist", expected_plist_after()),
], ids=["service-gone", "config-replaced", "plist-replaced"])
def test_an_abort_reentry_refuses_when_the_installed_state_is_no_longer_the_before_image(change):
    host = _abort_crashed_after_the_before_images_were_removed()
    change(host)
    log = list(host.log)
    expect(lambda: reconcile_of(host), m.TransactionEffectUnknown, "ABORT_STATE_CHANGED")
    assert host.log == log and host.marker is not None and host.locked is False


def test_every_crash_gap_of_the_ineffective_stop_abort_closes_without_a_second_launchd_effect():
    probe = FakeHost()
    probe.stop_effective = False
    apply_of(probe)
    names = [entry[0] for entry in probe.log]
    assert names[-3:] == ["discard_staged", "discard_preserved", "marker_remove"]
    for gap in range(len(names)):
        host = FakeHost()
        host.stop_effective = False
        digest_value = plan_of(host)
        host.arm(gap)
        with pytest.raises(Crash):
            apply_of(host, plan_sha256=digest_value)
        assert len(host.log) == gap
        host.locked = False
        host.crash_at = None
        outcome, _ = _reconcile_outcome(host)
        if gap == 0:
            expected = "NO_TRANSACTION"
        elif gap < names.index("stop_service"):
            expected = "DISCARDED_NO_EFFECT"
        else:
            expected = "ABORTED_UNCHANGED"
        assert outcome == expected, (gap, outcome, host.log)
        _assert_invariants(host, outcome)
        assert host.staged == {} and host.preserved == {}, gap
        assert host.count("replace") == 0 and host.count("start_service") == 0, gap
        if outcome == "ABORTED_UNCHANGED":
            assert _reconcile_outcome(host)[0] == "NO_TRANSACTION"


# --- the crash matrix ----------------------------------------------------------------


def _assert_invariants(host, outcome, *, set_public=False):
    assert host.violations == []
    assert host.locked is False
    assert host.count("stop_service") <= 1, host.log
    assert host.count("start_service") <= 1, host.log
    if outcome == "COMPLETE":
        assert_complete(host, set_public=set_public)
    elif outcome == "ABORTED_UNCHANGED":
        assert_clean_prior(host)
        assert host.count("recover_enable") >= 1
        assert host.disabled is False
        assert any(name.endswith("-aborted-v1.json") for name in host.receipts)
    elif outcome in ("DISCARDED_NO_EFFECT", "NO_TRANSACTION"):
        assert_clean_prior(host)
        assert host.staged == {} and host.preserved == {}
    elif outcome == "EFFECT_UNKNOWN":
        assert host.marker is not None
        tag = host.marker["plan_sha256"][:12]
        assert host.preserved[("config", tag)] == PRIOR_CONFIG
        assert host.preserved[("plist", tag)] == PRIOR_PLIST
    else:  # pragma: no cover
        raise AssertionError(outcome)


def _reconcile_outcome(host, release=NEW_RELEASE):
    try:
        result = reconcile_of(host, release)
    except m.UpdateRefused as error:
        assert error.code == "NO_TRANSACTION", error.code
        return "NO_TRANSACTION", error.code
    except m.TransactionEffectUnknown as error:
        return "EFFECT_UNKNOWN", error.code
    return result["outcome"], result.get("code")


EXPECTED_GAPS = {
    0: ("NO_TRANSACTION", "NO_TRANSACTION"),
    1: ("DISCARDED_NO_EFFECT", "RECONCILE_NO_EFFECT"),
    2: ("DISCARDED_NO_EFFECT", "RECONCILE_NO_EFFECT"),
    3: ("DISCARDED_NO_EFFECT", "RECONCILE_NO_EFFECT"),
    4: ("DISCARDED_NO_EFFECT", "RECONCILE_NO_EFFECT"),
    5: ("DISCARDED_NO_EFFECT", "RECONCILE_NO_EFFECT"),
    6: ("DISCARDED_NO_EFFECT", "RECONCILE_NO_EFFECT"),
    7: ("ABORTED_UNCHANGED", "STOP_DID_NOT_TAKE_EFFECT"),
    8: ("COMPLETE", None),
    9: ("COMPLETE", None),
    10: ("COMPLETE", None),
    11: ("COMPLETE", None),
    12: ("EFFECT_UNKNOWN", "START_NOT_PROVEN"),
    13: ("COMPLETE", None),
    14: ("COMPLETE", None),
    15: ("COMPLETE", None),
}


@pytest.mark.parametrize("gap", sorted(EXPECTED_GAPS))
@pytest.mark.parametrize("set_public", [False, True])
def test_every_crash_gap_of_the_happy_path_reconciles_safely(gap, set_public):
    host = FakeHost()
    digest_value = plan_of(host, set_public=set_public)
    host.arm(gap)
    with pytest.raises(Crash):
        apply_of(host, set_public=set_public, plan_sha256=digest_value)
    assert len(host.log) == gap
    host.locked = False  # the lock dies with the process
    host.crash_at = None
    outcome, code = _reconcile_outcome(host)
    expected_outcome, expected_code = EXPECTED_GAPS[gap]
    assert outcome == expected_outcome
    if expected_code is not None:
        assert code == expected_code
    _assert_invariants(host, outcome, set_public=set_public)
    if outcome == "COMPLETE":
        # A completed transaction reconciles to nothing further.
        assert _reconcile_outcome(host)[0] == "NO_TRANSACTION"
        _assert_invariants(host, "COMPLETE", set_public=set_public)


def test_crash_exploration_two_levels_deep():
    """Crash anywhere in apply, crash again anywhere in the first reconcile, then finish."""
    explored = 0
    for first in range(len(HAPPY_LOG)):
        base = FakeHost()
        digest_value = plan_of(base)
        base.arm(first)
        with pytest.raises(Crash):
            apply_of(base, plan_sha256=digest_value)
        base.locked = False
        base.crash_at = None
        j = 0
        while True:
            host = snapshot(base)
            host.arm(j)
            try:
                outcome, _ = _reconcile_outcome(host)
            except Crash:
                host.locked = False
                host.crash_at = None
                explored += 1
                assert host.violations == []
                assert host.count("stop_service") <= 1 and host.count("start_service") <= 1
                outcome, _ = _reconcile_outcome(host)
                _assert_invariants(host, outcome)
                j += 1
                continue
            _assert_invariants(host, outcome)
            break
    assert explored > 0


def test_a_completed_apply_has_nothing_left_to_reconcile():
    host = FakeHost()
    apply_of(host)
    assert _reconcile_outcome(host)[0] == "NO_TRANSACTION"
    assert_complete(host)


def test_a_second_apply_of_the_same_release_is_refused_after_completion():
    host = FakeHost()
    apply_of(host)
    with pytest.raises(m.UpdateRefused) as caught:
        m.plan(host, release_sha=NEW_RELEASE, set_public=False)
    assert "equals the installed release" in caught.value.code


# --- command line --------------------------------------------------------------------


def test_parse_arguments_accepts_the_closed_grammar():
    sha = "1" * 40
    plan_sha = "2" * 64
    assert m.parse_arguments(["plan", "--release-sha", sha]) == ("plan", {"--release-sha": sha})
    assert m.parse_arguments(["plan", "--release-sha", sha, "--set-public-mcp-resource"]) == (
        "plan", {"--release-sha": sha, "--set-public-mcp-resource": True})
    assert m.parse_arguments(["apply", "--release-sha", sha, "--plan-sha256", plan_sha]) == (
        "apply", {"--release-sha": sha, "--plan-sha256": plan_sha})
    assert m.parse_arguments(["reconcile", "--release-sha", sha]) == ("reconcile", {"--release-sha": sha})


@pytest.mark.parametrize("argv", [
    [],
    ["destroy", "--release-sha", "1" * 40],
    ["plan"],
    ["plan", "--release-sha"],
    ["plan", "--release-sha", "short"],
    ["plan", "--release-sha", "1" * 40, "--release-sha", "2" * 40],
    ["plan", "--release-sha", "1" * 40, "--set-public-mcp-resource", "--set-public-mcp-resource"],
    ["plan", "--release-sha", "1" * 40, "--plan-sha256", "2" * 64],
    ["plan", "--release-sha", "1" * 40, "--unknown"],
    ["plan", "--release-sha", "A" * 40],
    ["apply", "--release-sha", "1" * 40],
    ["apply", "--release-sha", "1" * 40, "--plan-sha256", "nope"],
    ["reconcile", "--release-sha", "1" * 40, "--set-public-mcp-resource"],
    ["reconcile", "--release-sha", "1" * 40, "--plan-sha256", "2" * 64],
    ["plan", "positional"],
])
def test_parse_arguments_rejects_everything_else(argv):
    with pytest.raises(m.UsageError):
        m.parse_arguments(argv)


def _run_main(argv, host, capsys):
    code = m.main(argv, host=host)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_main_plan_then_apply_exit_codes(capsys):
    host = FakeHost()
    code, out, err = _run_main(["plan", "--release-sha", NEW_RELEASE], host, capsys)
    assert code == 0 and err == ""
    planned = json.loads(out)
    assert planned["outcome"] == "PLANNED"
    code, out, err = _run_main(
        ["apply", "--release-sha", NEW_RELEASE, "--plan-sha256", planned["plan_sha256"]], host, capsys)
    assert code == 0 and json.loads(out)["outcome"] == "COMPLETE"
    assert out.endswith("\n") and out == json.dumps(json.loads(out), sort_keys=True, separators=(",", ":")) + "\n"


def test_main_refusal_effect_unknown_and_aborted_exit_codes(capsys):
    host = FakeHost()
    code, out, _ = _run_main(["apply", "--release-sha", NEW_RELEASE, "--plan-sha256", "0" * 64], host, capsys)
    assert code == 1 and json.loads(out) == {"code": "PLAN_DIGEST_MISMATCH", "ok": False, "outcome": "REFUSED"}

    host = FakeHost()
    host.start_effective = False
    plan_sha = plan_of(host)
    code, out, _ = _run_main(["apply", "--release-sha", NEW_RELEASE, "--plan-sha256", plan_sha], host, capsys)
    parsed = json.loads(out)
    assert code == 2 and parsed["outcome"] == "EFFECT_UNKNOWN" and parsed["code"] == "START_NOT_OBSERVED"
    assert "note" in parsed

    host = FakeHost()
    host.stop_effective = False
    plan_sha = plan_of(host)
    code, out, _ = _run_main(["apply", "--release-sha", NEW_RELEASE, "--plan-sha256", plan_sha], host, capsys)
    assert code == 3 and json.loads(out)["outcome"] == "ABORTED_UNCHANGED"


def test_main_usage_and_unexpected_errors(capsys):
    host = FakeHost()
    code, out, err = _run_main(["plan"], host, capsys)
    assert code == 64 and out == "" and err.startswith("usage:")
    host.release_error = None
    host.read_config = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    code, out, err = _run_main(["plan", "--release-sha", NEW_RELEASE], host, capsys)
    assert code == 1 and json.loads(out)["code"] == "UNEXPECTED_RUNTIMEERROR"
    assert "boom" not in out


# --- ProductionHost (patched launchctl and temp directories only) ----------------------


class Launchctl:
    def __init__(self, returncodes=None):
        self.calls = []
        self.kwargs = []
        self.returncodes = returncodes or {}
        self.stdout = b""
        self.raises = None

    def __call__(self, argv, **kwargs):
        self.calls.append(tuple(argv))
        self.kwargs.append(kwargs)
        assert kwargs["stdin"] is not None and kwargs["check"] is False and kwargs["timeout"] == 10
        assert kwargs["env"] == {"PATH": "/usr/bin:/bin"}
        if self.raises is not None:
            raise self.raises
        code = self.returncodes.get(argv[1], 0)
        if isinstance(code, list):
            code = code.pop(0)
        return type("Completed", (), {"returncode": code, "stdout": self.stdout})()


@pytest.fixture
def launchctl(monkeypatch):
    recorder = Launchctl()
    monkeypatch.setattr(m.subprocess, "run", recorder)
    return recorder


def test_production_stop_disables_before_bootout(launchctl):
    m.ProductionHost().stop_service()
    assert launchctl.calls == [(m.LAUNCHCTL, "disable", m.LAUNCHD_ROOT), (m.LAUNCHCTL, "bootout", m.LAUNCHD_ROOT)]


def test_production_stop_refuses_when_disable_fails_and_never_boots_out(launchctl):
    launchctl.returncodes = {"disable": 1}
    with pytest.raises(m.UpdateRefused) as caught:
        m.ProductionHost().stop_service()
    assert caught.value.code == "LAUNCHCTL_DISABLE_FAILED"
    assert [call[1] for call in launchctl.calls] == ["disable"]


def test_production_start_enables_then_bootstraps_the_installed_plist(launchctl):
    m.ProductionHost().start_service()
    assert launchctl.calls == [(m.LAUNCHCTL, "enable", m.LAUNCHD_ROOT),
                               (m.LAUNCHCTL, "bootstrap", "system", m.PLIST_PATH)]


@pytest.mark.parametrize("failing,code", [("enable", "LAUNCHCTL_ENABLE_FAILED"),
                                          ("bootstrap", "LAUNCHCTL_BOOTSTRAP_FAILED")])
def test_production_start_refusals(launchctl, failing, code):
    launchctl.returncodes = {failing: 5}
    with pytest.raises(m.UpdateRefused) as caught:
        m.ProductionHost().start_service()
    assert caught.value.code == code


def test_production_recover_enable_only_enables(launchctl):
    m.ProductionHost().recover_enable()
    assert launchctl.calls == [(m.LAUNCHCTL, "enable", m.LAUNCHD_ROOT)]
    launchctl.returncodes = {"enable": 1}
    with pytest.raises(m.UpdateRefused) as caught:
        m.ProductionHost().recover_enable()
    assert caught.value.code == "LAUNCHCTL_ENABLE_FAILED"


@pytest.mark.parametrize("returncode,expected", [(0, "REGISTERED"), (113, "ABSENT")])
def test_production_service_state_mapping(launchctl, returncode, expected):
    launchctl.returncodes = {"print": returncode}
    assert m.ProductionHost().service_state() == expected
    assert launchctl.calls == [(m.LAUNCHCTL, "print", m.LAUNCHD_ROOT)]


def test_production_service_state_unexpected_code_refuses(launchctl):
    launchctl.returncodes = {"print": 2}
    with pytest.raises(m.UpdateRefused) as caught:
        m.ProductionHost().service_state()
    assert caught.value.code == "LAUNCHCTL_PRINT_UNEXPECTED"


def _disabled_listing(*lines):
    return ("disabled services = {\n" + "".join("\t" + line + "\n" for line in lines) + "}\n").encode()


@pytest.mark.parametrize("listing,expected", [
    (_disabled_listing('"com.mastermind.executive.mcp" => disabled'), False),
    (_disabled_listing('"com.mastermind.executive.mcp" => true'), False),
    (_disabled_listing('"com.mastermind.executive.mcp" => enabled'), True),
    (_disabled_listing('"com.mastermind.executive.mcp" => false'), True),
    # No override for the label (or only other labels, or a longer label) means not disabled.
    (_disabled_listing('"com.apple.other" => disabled'), True),
    (_disabled_listing('"com.mastermind.executive.mcp.other" => disabled'), True),
    # A structurally complete table with no row for the label is "no override": enabled.
    (_disabled_listing(), True),
], ids=["disabled", "true", "enabled", "false", "other-label", "longer-label", "empty-set"])
def test_production_service_enabled_reads_the_launchd_disabled_override(launchctl, listing, expected):
    launchctl.stdout = listing
    assert m.ProductionHost().service_enabled() is expected
    assert launchctl.calls == [(m.LAUNCHCTL, "print-disabled", "system")]
    assert launchctl.kwargs[0]["stdout"] == m.subprocess.PIPE


@pytest.mark.parametrize("listing", [
    _disabled_listing('"com.mastermind.executive.mcp" => disabled', '"com.mastermind.executive.mcp" => enabled'),
    _disabled_listing('"com.mastermind.executive.mcp" => maybe'),
    _disabled_listing('"com.mastermind.executive.mcp" =>'),
    b"x" * (m.MAX_LAUNCHCTL_OUTPUT_BYTES + 1),
    # Fail closed on output that is not exactly one header, rows and one footer: an empty, truncated
    # or reshaped listing must never read as "no override".
    b"",
    b"\n\n",
    b'\t"com.mastermind.executive.mcp" => enabled\n',
    b'disabled services = {\n\t"com.mastermind.executive.mcp" => enabled\n',
    b"disabled services = {\n}\ndisabled services = {\n}\n",
    b"disabled services = {\ndisabled services = {\n}\n",
    b"disabled services = {\n\tsomething unexpected\n}\n",
    b"unexpected banner\n" + _disabled_listing(),
    _disabled_listing() + b'\t"com.mastermind.executive.mcp" => disabled\n',
    _disabled_listing() + b"}\n",
    # A row in any shape the shell parser rejects is refused, never skipped: a skipped row would
    # leave the gateway's own disable invisible and read as "enabled".
    _disabled_listing("com.mastermind.executive.mcp => disabled"),
    _disabled_listing("'com.mastermind.executive.mcp' => disabled"),
    _disabled_listing('"com.mastermind.executive.mcp"  =>  disabled  extra'),
    _disabled_listing('"com.mastermind.executive.mcp"=>disabled'),
    _disabled_listing('"com.mastermind.executive.mcp" => disabled,'),
    _disabled_listing('"com.mastermind.executive.mcp" -> disabled'),
    _disabled_listing('"com.apple.other" => disabled', '"com.apple.other" => disabled'),
    _disabled_listing('"com apple" => disabled'),
    _disabled_listing('"com.mastermind.executive.mcp" == disabled'),
], ids=["conflicting", "unknown-verdict", "no-verdict", "oversized", "empty-output", "blank-lines",
        "rows-without-header", "missing-footer", "duplicate-table", "duplicate-header", "junk-row",
        "banner-before-header", "row-after-footer", "second-footer", "unquoted-label",
        "single-quoted-label", "extra-field", "no-spaces", "trailing-comma", "wrong-arrow",
        "duplicate-other-label", "label-with-space", "wrong-operator"])
def test_production_service_enabled_refuses_ambiguous_output(launchctl, listing):
    launchctl.stdout = listing
    with pytest.raises(m.UpdateRefused) as caught:
        m.ProductionHost().service_enabled()
    assert caught.value.code == "LAUNCHCTL_PRINT_DISABLED_UNEXPECTED"


def test_production_service_enabled_refuses_a_failed_print_disabled(launchctl):
    launchctl.returncodes = {"print-disabled": 1}
    launchctl.stdout = _disabled_listing('"com.mastermind.executive.mcp" => enabled')
    with pytest.raises(m.UpdateRefused) as caught:
        m.ProductionHost().service_enabled()
    assert caught.value.code == "LAUNCHCTL_PRINT_DISABLED_UNEXPECTED"


@pytest.mark.parametrize("failure", [m.subprocess.TimeoutExpired(cmd="launchctl", timeout=10), OSError("gone")],
                         ids=["timeout", "oserror"])
@pytest.mark.parametrize("call", [
    lambda host: host.service_state(),
    lambda host: host.service_enabled(),
    lambda host: host.stop_service(),
    lambda host: host.start_service(),
    lambda host: host.recover_enable(),
], ids=["state", "enabled", "stop", "start", "recover"])
def test_a_launchctl_that_hangs_or_is_missing_is_a_bounded_refusal(launchctl, failure, call):
    launchctl.raises = failure
    with pytest.raises(m.UpdateRefused) as caught:
        call(m.ProductionHost())
    assert caught.value.code == "LAUNCHCTL_UNAVAILABLE"
    assert len(launchctl.calls) == 1  # no further launchctl effect after the first failure


def _observation(**overrides):
    fields = {"service_label": m.LABEL, "plist_path": m.PLIST_PATH, "state": "running",
              "program": "/runtime/bin/python", "argv": ("/runtime/bin/python", "-I"),
              "working_directory": "/releases/" + NEW_RELEASE, "username": m.GATEWAY_USER,
              "group": "_grp", "pid": 4242}
    fields.update(overrides)
    return installed._LaunchdObservation(**fields)


def test_production_observe_process_reports_only_the_identity_fields(monkeypatch):
    seen = []
    monkeypatch.setattr(installed, "_observe_launchd_service", lambda role, **kw: seen.append(role) or _observation())
    value = m.ProductionHost().observe_process()
    assert seen == ["gateway"]
    assert value == {"state": "running", "program": "/runtime/bin/python",
                     "argv": ["/runtime/bin/python", "-I"], "working_directory": "/releases/" + NEW_RELEASE,
                     "username": m.GATEWAY_USER, "pid": 4242}
    assert type(value["argv"]) is list


def test_production_observe_process_maps_a_peer_identity_error_to_a_bounded_refusal(monkeypatch):
    def refuse(role, **kw):
        raise m.PeerIdentityError("LAUNCHD_NOT_RUNNING" + "x" * 300)

    monkeypatch.setattr(installed, "_observe_launchd_service", refuse)
    with pytest.raises(m.UpdateRefused) as caught:
        m.ProductionHost().observe_process()
    code = caught.value.code
    assert code.startswith("PROCESS_OBSERVATION_REFUSED: LAUNCHD_NOT_RUNNING")
    assert len(code) == len("PROCESS_OBSERVATION_REFUSED: ") + 120


def test_production_require_root_branches(monkeypatch):
    host = m.ProductionHost()
    monkeypatch.setattr(m.sys, "platform", "linux")
    with pytest.raises(m.UpdateRefused) as caught:
        host.require_root()
    assert caught.value.code == "PLATFORM_UNSUPPORTED"
    monkeypatch.setattr(m.sys, "platform", "darwin")
    monkeypatch.setattr(m.os, "geteuid", lambda: 501)
    with pytest.raises(m.UpdateRefused) as caught:
        host.require_root()
    assert caught.value.code == "ROOT_REQUIRED"
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    host.require_root()


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    receipts = tmp_path / "installation-receipts"
    config_dir = tmp_path / "config"
    plist_dir = tmp_path / "daemons"
    for directory in (receipts, config_dir, plist_dir):
        directory.mkdir()
    config = config_dir / "executive-mcp.json"
    plist = plist_dir / "com.mastermind.executive.mcp.plist"
    config.write_bytes(PRIOR_CONFIG)
    plist.write_bytes(PRIOR_PLIST)
    monkeypatch.setattr(m, "RECEIPTS_DIR", str(receipts))
    monkeypatch.setattr(m, "CONFIG_PATH", str(config))
    monkeypatch.setattr(m, "PLIST_PATH", str(plist))
    monkeypatch.setattr(m.os, "fchown", lambda fd, uid, gid: None)
    host = m.ProductionHost()
    # The trusted-read path needs uid 0; the unit under test here is the file protocol.
    monkeypatch.setattr(host, "_trusted", lambda path, maximum, mode: open(path, "rb").read(), raising=False)
    return host, receipts, config, plist


def test_production_marker_lifecycle(sandbox):
    host, receipts, _, _ = sandbox
    marker = {"a": 1}
    host.marker_create(marker)
    path = receipts / m.MARKER_NAME
    assert path.exists() and oct(path.stat().st_mode & 0o777) == "0o600"
    with pytest.raises(m.UpdateRefused) as caught:
        host.marker_create(marker)
    assert caught.value.code == "TRANSACTION_PRESENT"
    host.marker_write({"a": 2})
    assert json.loads(path.read_bytes()) == {"a": 2}
    assert not list(receipts.glob("*.tmp"))
    assert host.marker_read() == {"a": 2}
    host.marker_remove()
    assert not path.exists()
    assert host.marker_read() is None
    host.marker_remove()  # idempotent


def test_production_before_images_stage_and_replace(sandbox):
    host, receipts, config, plist = sandbox
    tag = "abcdef123456"
    host.preserve("config", tag, b"cfg-before")
    host.preserve("plist", tag, b"plist-before")
    assert (receipts / ("mcp-update-" + tag + ".config.before")).read_bytes() == b"cfg-before"
    assert oct((receipts / ("mcp-update-" + tag + ".config.before")).stat().st_mode & 0o777) == "0o600"
    assert host.read_preserved("config", tag) == b"cfg-before"
    assert host.read_preserved("plist", "000000000000") is None

    assert host.staged_digest("config", tag) is None
    host.stage("config", tag, b"cfg-after")
    host.stage("plist", tag, b"plist-after")
    assert host.staged_digest("config", tag) == digest(b"cfg-after")
    staged = [entry.name for entry in config.parent.iterdir() if entry.name.endswith(".new")]
    # Dot-prefixed so no directory scan that matches *.plist / *.json can ever pick the staged copy up.
    assert staged == [".executive-mcp.json.mcp-component-" + tag + ".new"]
    assert oct((config.parent / staged[0]).stat().st_mode & 0o777) == "0o644"

    host.replace("config", tag)
    host.replace("plist", tag)
    assert config.read_bytes() == b"cfg-after" and plist.read_bytes() == b"plist-after"
    assert host.staged_digest("config", tag) is None
    host.stage("config", tag, b"again")
    host.discard_staged(tag)
    assert host.staged_digest("config", tag) is None
    host.discard_preserved(tag)
    assert host.read_preserved("config", tag) is None and host.read_preserved("plist", tag) is None
    host.discard_staged(tag)  # idempotent
    host.discard_preserved(tag)


def test_production_stage_never_overwrites_an_existing_staged_file(sandbox):
    host, _, config, _ = sandbox
    host.stage("config", "abcdef123456", b"one")
    with pytest.raises(FileExistsError):
        host.stage("config", "abcdef123456", b"two")


def test_production_receipts_are_write_once(sandbox):
    host, receipts, _, _ = sandbox
    name = "mcp-component-x-v1.json"
    assert host.receipt_exists(name) is False
    host.receipt_write(name, {"v": 1})
    assert host.receipt_exists(name) is True
    host.receipt_write(name, {"v": 2})
    assert json.loads((receipts / name).read_bytes()) == {"v": 1}
    assert not list(receipts.glob("*.tmp"))


def test_production_lock_is_exclusive(sandbox):
    host, receipts, _, _ = sandbox
    other = m.ProductionHost()
    host.acquire_lock()
    with pytest.raises(m.UpdateRefused) as caught:
        other.acquire_lock()
    assert caught.value.code == "LOCK_HELD"
    host.release_lock()
    other.acquire_lock()
    other.release_lock()


def test_production_probe_speaks_plain_http_to_loopback(monkeypatch):
    seen = {}

    class Response:
        status = 401

        def getheaders(self):
            return [("WWW-Authenticate", "Bearer a"), ("www-authenticate", "Bearer b"), ("X", "y")]

        def read(self, amount):
            seen["read"] = amount
            return b"body"

    class Connection:
        def __init__(self, host, port, timeout):
            seen["target"] = (host, port, timeout)

        def request(self, method, path, body=None, headers=None):
            seen["request"] = (method, path, body, headers)

        def getresponse(self):
            return Response()

        def close(self):
            seen["closed"] = True

    monkeypatch.setattr(m.http.client, "HTTPConnection", Connection)
    result = m.ProductionHost().probe(8443, _probe(headers=(("accept", "x"),), body=b"{}"))
    assert seen["target"] == ("127.0.0.1", 8443, 5)
    assert seen["request"] == ("POST", "/mcp", b"{}", {"accept": "x"})
    assert seen["read"] == 65537 and seen["closed"] is True
    assert result.status == 401 and result.body == b"body"
    assert result.headers["www-authenticate"] == "Bearer a, Bearer b" and result.headers["x"] == "y"


def test_receipts_directory_and_constants_are_the_installed_ones():
    assert m.RECEIPTS_DIR == installed._SERVICE_ROOT + "/installation-receipts"
    assert m.CONFIG_PATH == installed._GATEWAY_CONFIG_PATH
    assert m.PLIST_PATH.endswith("com.mastermind.executive.mcp.plist")
    assert m.LAUNCHD_ROOT == "system/" + m.LABEL


def test_module_never_shells_out_beyond_launchctl():
    source = open(m.__file__, encoding="utf-8").read()
    # Exactly two call sites: the status-only launchctl runner and the one that captures print-disabled.
    assert source.count("subprocess.run(") == 2
    assert source.count("(LAUNCHCTL, *argv)") == 2
    assert 'LAUNCHCTL = "/bin/launchctl"' in source
    assert "shell=True" not in source and "os.system" not in source
    assert "service-control" not in source.replace("service-control.sh`", "")
