"""Pure compiler invariants for the OS gateway publication generation.

Offline source tests only: no installed release, no service, no grant and no
publication is claimed or performed. Fixtures are explicit nonprod data; the
only ownership checked is the compiler's own DATA law.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib
import json
import plistlib

import pytest

from control_plane import executive_installed_peer as installed
from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE
from ops.executive_os import executive_mcp_entry, os_gateway_publication as m
from ops.executive_os.executive_mcp_entry import OS_EXECUTIVE_RESOURCE

ISSUER = "https://issuer.mastermind.example.test"
RESOURCE = "https://executive-app.mastermind.example.test/mcp"
SUBJECT = "chairman-opaque-e1"
OLD_RELEASE = "b" * 40
NEW_RELEASE = "c" * 40
BASE_SHA = "d" * 40
STUDIO_PORT = 45025
BUNDLE_DIGEST = "4" * 64
AUTH_HELPER = "2" * 64
FILE_HELPER = "3" * 64


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
            "submit": _policy("gateway-fixture-submit",
                              sorted([READ_SCOPE, SUBMIT_SCOPE])),
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


def derived_os_submit_policy():
    """Independent projection of the law: existing submit policy, OS resource."""
    submit = load_resource_policy(prior_mcp_document()["policies"]["submit"])
    replaced = dataclasses.replace(submit, resource=OS_EXECUTIVE_RESOURCE)
    verified = load_resource_policy(json.loads(json.dumps(dataclasses.asdict(replaced))))
    return json.loads(json.dumps(dataclasses.asdict(verified)))


def grant(scope="1" * 64, **template):
    base = {"workstream": "WS:NOIR", "department": "executive-infrastructure",
            "priority": 5, "execution_profile": "research_only"}
    base.update(template)
    return {"principal_scope": scope, "template": base}


def publication_document(grants=None, **overrides):
    document = {
        "schema": "mastermind.os_commission_publication.v1",
        "release_sha": NEW_RELEASE,
        "studio_uid": 502,
        "studio_account": "atelier",
        "studio_port": STUDIO_PORT,
        "policy": derived_os_submit_policy(),
        "grants": [grant()] if grants is None else grants,
        "base_sha": BASE_SHA,
        "audit_directory": m.AUDIT_DIRECTORY,
        "auth_helper_sha256": AUTH_HELPER,
        "file_helper_sha256": FILE_HELPER,
    }
    document.update(overrides)
    return document


def qualified_inputs(document=None):
    document = publication_document() if document is None else document
    return {"publication_document": document,
            "auth_helper_sha256": document["auth_helper_sha256"],
            "file_helper_sha256": document["file_helper_sha256"]}


def prior_mcp_bytes(document=None):
    return json.dumps(prior_mcp_document() if document is None else document,
                      sort_keys=True).encode("utf-8") + b"\n"


def prior_plist_bytes(document=None):
    return plistlib.dumps(prior_plist_document() if document is None else document)


def compile_candidate(*, mcp_bytes=None, plist_bytes=None, release=NEW_RELEASE,
                      bundle=BUNDLE_DIGEST, inputs=None):
    return m.compile_gateway_candidates(
        prior_mcp_bytes() if mcp_bytes is None else mcp_bytes,
        prior_plist_bytes() if plist_bytes is None else plist_bytes,
        expected_release_sha=release, expected_bundle_digest=bundle,
        qualified_publication_inputs=qualified_inputs() if inputs is None else inputs)


def proposed(candidate, path):
    return candidate.artifact(path)


def test_fixed_targets_are_the_exact_publication_paths():
    assert m.MCP_CONFIG_PATH == ("/Library/Application Support/MastermindExecutive"
                                 "/config/executive-mcp.json")
    assert m.MCP_PLIST_PATH == "/Library/LaunchDaemons/com.mastermind.executive.mcp.plist"
    assert m.COMMISSION_CONFIG_PATH == ("/Library/Application Support/MastermindExecutive"
                                        "/config/os-commission-publication.json")
    assert m.AUDIT_DIRECTORY == ("/Library/Application Support/MastermindExecutive"
                                 "/audit/os-commission-publication")
    assert m.OPERATION == "OS_GATEWAY_PUBLICATION"


class _RecordingEnviron(dict):
    def __init__(self, real, calls):
        self._real, self._calls = real, calls

    def __getitem__(self, key):
        self._calls.append("environ[%r]" % (key,))
        return self._real[key]

    def get(self, key, *default):
        self._calls.append("environ.get(%r)" % (key,))
        return self._real.get(key, *default)

    def __contains__(self, key):
        self._calls.append("environ contains %r" % (key,))
        return key in self._real


def _guard_io(monkeypatch, calls, *, stat_too):
    import builtins
    import os as os_module
    import socket as socket_module
    import subprocess as subprocess_module
    from pathlib import Path

    def record(name, function):
        def wrapped(*args, **kwargs):
            calls.append(name)
            return function(*args, **kwargs)
        return wrapped

    for name in ("open", "read_text", "read_bytes"):
        monkeypatch.setattr(Path, name, record("Path." + name, getattr(Path, name)),
                            raising=False)
    monkeypatch.setattr(builtins, "open", record("builtins.open", builtins.open))
    monkeypatch.setattr(os_module, "open", record("os.open", os_module.open))
    monkeypatch.setattr(socket_module, "socket", record("socket.socket", socket_module.socket))
    monkeypatch.setattr(subprocess_module, "run", record("subprocess.run", subprocess_module.run))
    monkeypatch.setattr(subprocess_module, "Popen", record("subprocess.Popen", subprocess_module.Popen))
    if stat_too:
        monkeypatch.setattr(os_module, "stat", record("os.stat", os_module.stat))
        monkeypatch.setattr(os_module, "listdir", record("os.listdir", os_module.listdir))
    monkeypatch.setattr(os_module, "environ",
                        _RecordingEnviron(os_module.environ, calls))


def test_compile_performs_no_global_io(monkeypatch):
    # Warm every lazily imported owner first: a fresh module import stats
    # import-machinery paths by design. Everything after this point must
    # touch no filesystem, socket, process or environment authority.
    for name in ("integrations.studio_direct_mcp.private_service",
                 "integrations.executive_mcp.schemas",
                 "integrations.business_mcp_auth.contracts",
                 "control_plane.executive_peer_identity"):
        importlib.import_module(name)
    calls = []
    _guard_io(monkeypatch, calls, stat_too=True)
    candidate = compile_candidate()
    classification = m.classify_postimages(
        candidate, {artifact.path: artifact.content for artifact in candidate.artifacts},
        publication_before_bytes=b"{}\n")
    manifest = candidate.operation_manifest()
    assert calls == [], calls
    assert classification["state"] == "MATCHED"
    assert manifest["operation"] == "OS_GATEWAY_PUBLICATION"


def test_fresh_module_import_performs_no_data_io(monkeypatch):
    import sys
    calls = []
    _guard_io(monkeypatch, calls, stat_too=False)
    sys.modules.pop("ops.executive_os.os_gateway_publication", None)
    module = importlib.import_module("ops.executive_os.os_gateway_publication")
    assert module.OPERATION == "OS_GATEWAY_PUBLICATION"
    assert calls == [], calls


def test_compile_holds_exact_before_bytes_and_three_fixed_artifacts():
    mcp_bytes, plist_bytes = prior_mcp_bytes(), prior_plist_bytes()
    candidate = compile_candidate(mcp_bytes=mcp_bytes, plist_bytes=plist_bytes)
    assert candidate.schema == "mastermind.os_gateway_publication.v1"
    assert candidate.operation == "OS_GATEWAY_PUBLICATION"
    assert candidate.before_mcp_bytes == mcp_bytes == type(mcp_bytes)(candidate.before_mcp_bytes)
    assert candidate.before_plist_bytes == plist_bytes
    assert candidate.before_mcp_sha256 == hashlib.sha256(mcp_bytes).hexdigest()
    assert candidate.before_plist_sha256 == hashlib.sha256(plist_bytes).hexdigest()
    assert candidate.expected_release_sha == NEW_RELEASE
    assert candidate.expected_bundle_digest == BUNDLE_DIGEST
    assert [artifact.path for artifact in candidate.artifacts] == [
        m.MCP_CONFIG_PATH, m.MCP_PLIST_PATH, m.COMMISSION_CONFIG_PATH]
    for artifact in candidate.artifacts:
        assert artifact.byte_count == len(artifact.content)
        assert candidate.artifact(artifact.path).sha256 == hashlib.sha256(
            artifact.content).hexdigest()
    with pytest.raises(ValueError, match="unknown gateway publication target"):
        candidate.artifact("/etc/passwd")
    assert candidate.publication_before_sha256 is None


def test_proposed_mcp_differs_only_in_the_closed_os_fields():
    candidate = compile_candidate()
    prior = prior_mcp_document()
    new = candidate.mcp_document()
    changed = {key for key in set(prior) | set(new)
               if prior.get(key) != new.get(key)}
    assert changed == {"release_sha", "os_executive_transport",
                       "os_executive_resource", "os_commission_port"}
    assert new["release_sha"] == NEW_RELEASE
    assert new["os_executive_transport"] is True
    assert new["os_executive_resource"] == OS_EXECUTIVE_RESOURCE
    assert new["os_commission_port"] == STUDIO_PORT
    assert new["executive_mcp_profile"] == "web_ceo_v3"
    assert new["policies"] == prior["policies"]
    assert new["port"] == prior["port"] and new["service_uid"] == 458


def test_proposed_plist_differs_only_in_working_directory_and_release_argument():
    candidate = compile_candidate()
    prior = prior_plist_document()
    new = plistlib.loads(proposed(candidate, m.MCP_PLIST_PATH).content)
    assert set(new) == set(prior)
    for key in set(prior) - {"WorkingDirectory", "ProgramArguments"}:
        assert new[key] == prior[key]
    assert new["Label"] == "com.mastermind.executive.mcp"
    assert new["UserName"] == "_mastermind_executive_mcp"
    assert new["GroupName"] == "_mastermind_executive_mcp"
    assert new["WorkingDirectory"] == installed._SERVICE_RELEASES + "/" + NEW_RELEASE
    assert len(new["ProgramArguments"]) == 6
    assert new["ProgramArguments"][:3] == prior["ProgramArguments"][:3]
    assert new["ProgramArguments"][3] == (installed._SERVICE_RELEASES + "/" + NEW_RELEASE
                                          + "/ops/executive_os/executive_mcp_entry.py")
    assert new["ProgramArguments"][4:] == ["--config", m.MCP_CONFIG_PATH]
    assert prior["ProgramArguments"][3].startswith(
        installed._SERVICE_RELEASES + "/" + OLD_RELEASE)


def test_proposed_artifacts_use_exact_canonical_serializations():
    candidate = compile_candidate()
    mcp_raw = proposed(candidate, m.MCP_CONFIG_PATH).content
    publication_raw = proposed(candidate, m.COMMISSION_CONFIG_PATH).content
    assert mcp_raw.endswith(b"\n") and publication_raw.endswith(b"\n")
    expected_mcp = json.dumps(candidate.mcp_document(), sort_keys=True,
                              separators=(",", ":"), ensure_ascii=False,
                              allow_nan=False).encode("utf-8") + b"\n"
    assert mcp_raw == expected_mcp
    assert publication_raw == json.dumps(
        qualified_inputs()["publication_document"], sort_keys=True,
        separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8") + b"\n"
    plist_raw = proposed(candidate, m.MCP_PLIST_PATH).content
    assert plist_raw == plistlib.dumps(plistlib.loads(plist_raw))
    assert compile_candidate().artifact(m.MCP_PLIST_PATH).content == plist_raw
    assert compile_candidate().artifact(m.MCP_CONFIG_PATH).content == mcp_raw


def test_proposed_publication_policy_joins_derived_os_submit_policy():
    candidate = compile_candidate()
    document = candidate.publication_document()
    assert document["policy"] == derived_os_submit_policy()
    assert document["policy"]["resource"] == OS_EXECUTIVE_RESOURCE
    assert document["policy"]["allowed_algorithms"] == ["RS256"]
    assert document["policy"]["required_scopes"] == [
        "mastermind.executive.intent.submit", "mastermind.executive.read"]
    assert candidate.publication_document()["grants"] == [grant()]
    assert document["studio_port"] == STUDIO_PORT


def test_compile_accepts_prior_document_that_already_carried_os_transport():
    prior = prior_mcp_document(os_executive_transport=True,
                               os_executive_resource=OS_EXECUTIVE_RESOURCE,
                               os_commission_port=46010)
    candidate = compile_candidate(mcp_bytes=prior_mcp_bytes(prior))
    new = candidate.mcp_document()
    assert new["os_commission_port"] == STUDIO_PORT
    assert new["release_sha"] == NEW_RELEASE


def test_compile_does_not_mutate_caller_inputs():
    inputs = qualified_inputs()
    document_copy = copy.deepcopy(inputs)
    mcp_bytes, plist_bytes = prior_mcp_bytes(), prior_plist_bytes()
    compile_candidate(mcp_bytes=mcp_bytes, plist_bytes=plist_bytes, inputs=inputs)
    assert inputs == document_copy
    assert mcp_bytes == prior_mcp_bytes() and plist_bytes == prior_plist_bytes()


def test_candidate_is_immutable_data_and_projection_is_fresh():
    candidate = compile_candidate()
    with pytest.raises(Exception):
        candidate.operation = "OTHER"
    with pytest.raises(Exception):
        candidate.publication_before_sha256 = "5" * 64
    with pytest.raises(ValueError, match="no publication before-image exists"):
        dataclasses.replace(candidate, publication_before_sha256="5" * 64)
    document = candidate.publication_document()
    document["grants"].clear()
    assert candidate.publication_document()["grants"] == [grant()]
    projected = candidate.mcp_document()
    projected["release_sha"] = "f" * 40
    assert candidate.mcp_document()["release_sha"] == NEW_RELEASE


def test_operation_manifest_is_closed_data_without_a_store():
    candidate = compile_candidate()
    manifest = candidate.operation_manifest()
    assert set(manifest) == {"schema", "operation", "expected_release_sha",
                             "expected_bundle_digest", "targets", "before_images",
                             "publication_grant_beforeimage", "authority"}
    assert manifest["operation"] == "OS_GATEWAY_PUBLICATION"
    assert manifest["publication_grant_beforeimage"] == "REQUIRED_UNBOUND"
    assert manifest["authority"] == "DATA_ONLY_compiled_values_grant_nothing"
    assert set(manifest["targets"]) == {m.MCP_CONFIG_PATH, m.MCP_PLIST_PATH,
                                        m.COMMISSION_CONFIG_PATH}
    for path, row in manifest["targets"].items():
        assert set(row) == {"kind", "sha256", "byte_count"}
        assert row["sha256"] == candidate.artifact(path).sha256
        assert row["byte_count"] == candidate.artifact(path).byte_count
    assert manifest["before_images"] == {"executive-mcp-config": candidate.before_mcp_sha256,
                                         "executive-mcp-plist": candidate.before_plist_sha256}


@pytest.mark.parametrize("raw", [
    b"", b"{", b"[]", b" null", '{"schema":1,"schema":2}'.encode(),
    b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}',
    b"\xff\xfe", b'{"a":' + b"1" * 70000 + b"}",
])
def test_prior_mcp_bytes_rejections(raw):
    with pytest.raises(ValueError):
        compile_candidate(mcp_bytes=raw)


@pytest.mark.parametrize("raw", [
    b"", b"not a plist", b"<plist/>", b"<plist><dict><dict/></dict></plist>",
    ('<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>'
     '<key>Label</key><string>a</string><key>Label</key><string>b</string>'
     '</dict></plist>').encode(),
    ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><!DOCTYPE plist [<!ENTITY x SYSTEM "
     "'file:///etc/passwd'>]><plist version=\"1.0\"><dict/></plist>").encode(),
    b"<plist><dict>" + b"<key>a</key><integer>1</integer>" * 3000 + b"</dict></plist>",
    b"<plist><dict>" + b"<key>" + b"a" * 300000 + b"</key></dict></plist>",
])
def test_prior_plist_bytes_rejections(raw):
    with pytest.raises(ValueError):
        compile_candidate(plist_bytes=raw)


@pytest.mark.parametrize("inputs", [
    {}, "x", [],
    {"publication_document": publication_document()},
    {"publication_document": publication_document(), "auth_helper_sha256": AUTH_HELPER},
    dict(qualified_inputs(), extra=1),
    dict(qualified_inputs(), auth_helper_sha256="z" * 64),
    dict(qualified_inputs(), file_helper_sha256="nope"),
])
def test_qualified_inputs_are_closed(inputs):
    with pytest.raises(ValueError):
        compile_candidate(inputs=inputs)


def test_unexpected_document_types_are_refused():
    inputs = {"publication_document": [publication_document()],
              "auth_helper_sha256": AUTH_HELPER, "file_helper_sha256": FILE_HELPER}
    with pytest.raises(ValueError, match="publication document must be an object"):
        compile_candidate(inputs=inputs)
    foreign = {"publication_document": {"schema": "mastermind.os_commission_publication.v1",
                                        "policy": ("tuple",), "grants": []},
               "auth_helper_sha256": AUTH_HELPER, "file_helper_sha256": FILE_HELPER}
    with pytest.raises(ValueError, match="exact JSON types"):
        compile_candidate(inputs=foreign)


@pytest.mark.parametrize("overrides", [
    {"schema": "mastermind.other.v1"},
    {"release_sha": OLD_RELEASE},
    {"release_sha": "z" * 40},
    {"base_sha": "short"},
    {"studio_uid": True},
    {"studio_uid": 0},
    {"studio_uid": -5},
    {"studio_uid": "502"},
    {"studio_port": 8443},
    {"studio_port": 45017},
    {"studio_port": 1023},
    {"studio_port": 65536},
    {"studio_port": True},
    {"studio_port": "45025"},
    {"audit_directory": "/tmp/audit"},
    {"auth_helper_sha256": "2" * 63},
    {"file_helper_sha256": "g" * 64},
])
def test_publication_document_scalars_are_refused(overrides):
    with pytest.raises(ValueError):
        compile_candidate(inputs=qualified_inputs(publication_document(**overrides)))


@pytest.mark.parametrize("label", ["", "Atelier", "atelier boutique", "atelé",
                                   "a" * 65, "-leading", "public", "shared", "default",
                                   "state", "config", "logs", "manifest", "a/b"])
def test_studio_account_label_uses_the_private_studio_law(label):
    with pytest.raises(ValueError):
        compile_candidate(inputs=qualified_inputs(
            publication_document(studio_account=label)))


def test_studio_account_label_accepts_the_existing_shape():
    document = publication_document(studio_account="atelier-1.account_x")
    assert compile_candidate(inputs=qualified_inputs(document))


def test_qualified_helper_digests_must_join_the_document():
    inputs = qualified_inputs()
    inputs["auth_helper_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="helper digest join"):
        compile_candidate(inputs=inputs)
    inputs = qualified_inputs()
    inputs["publication_document"] = dict(
        inputs["publication_document"], file_helper_sha256="8" * 64)
    with pytest.raises(ValueError, match="helper digest join"):
        compile_candidate(inputs=inputs)


def test_release_and_bundle_argument_forms_are_joined():
    with pytest.raises(ValueError, match="expected release SHA"):
        compile_candidate(release="z" * 40)
    with pytest.raises(ValueError, match="expected release SHA"):
        compile_candidate(release=NEW_RELEASE[:-1])
    with pytest.raises(ValueError, match="expected bundle digest"):
        compile_candidate(bundle="5" * 63)
    with pytest.raises(ValueError, match="publication release join"):
        compile_candidate(inputs=qualified_inputs(publication_document(
            release_sha=("e" * 40))))


@pytest.mark.parametrize("grants", [
    [],
    [grant(), grant()],
    [grant(), grant(scope="2" * 64), grant(scope="2" * 64)],
    [{"principal_scope": "1" * 64}],
    [{"template": {"workstream": "WS:NOIR", "department": "executive-infrastructure",
                   "priority": 5, "execution_profile": "research_only"}}],
    [dict(grant(), extra=1)],
    [grant(scope="short")],
    [grant(workstream="NOIR")],
    [grant(department="Executive")],
    [grant(priority=101)],
    [grant(priority=True)],
    [grant(execution_profile="deploy")],
    [grant(allowed_write_paths=["/etc/passwd"])],
    [grant(allowed_write_paths=["../escape"])],
    [grant(attempt_limit=0)],
    [grant(attempt_limit=4)],
    [grant(validation={"shell": "rm -rf /"})],
    [grant(validation={"pytest_targets": [1]})],
    [grant(objective="not a template field")],
    [grant(operation_key="os-not-a-template-field")],
])
def test_grants_follow_the_existing_commission_and_five_tool_laws(grants):
    with pytest.raises(ValueError):
        compile_candidate(inputs=qualified_inputs(publication_document(grants=grants)))


def test_publication_document_keys_are_exactly_the_installed_shape():
    extra = publication_document(extra_field=True)
    with pytest.raises(ValueError, match="publication document fields differ"):
        compile_candidate(inputs=qualified_inputs(extra))
    dropped = publication_document()
    del dropped["base_sha"]
    with pytest.raises(ValueError, match="publication document fields differ"):
        compile_candidate(inputs=qualified_inputs(dropped))


def test_optional_template_fields_are_validated_when_emitted():
    grants = [
        grant(scope="1" * 64, execution_profile="bounded_code_change",
              allowed_write_paths=["ops/executive_os/notes.md"],
              validation={"pytest_targets": ["tests/test_a.py"],
                          "git_diff_check": True}, attempt_limit=2),
        grant(scope="2" * 64, attempt_limit=3),
    ]
    candidate = compile_candidate(inputs=qualified_inputs(publication_document(grants=grants)))
    assert candidate.publication_document()["grants"] == grants


def test_policy_must_equal_the_derived_os_submit_policy_exactly():
    document = publication_document()
    wrong = dict(document["policy"], policy_id="gateway-fixture-submit")
    wrong["resource"] = RESOURCE
    with pytest.raises(ValueError, match="publication policy differs"):
        compile_candidate(inputs=qualified_inputs(
            publication_document(policy=wrong)))
    dropped = {key: value for key, value in document["policy"].items()
               if key != "jwks_cache_ttl_seconds"}
    with pytest.raises(ValueError):
        compile_candidate(inputs=qualified_inputs(publication_document(policy=dropped)))
    unsorted = dict(document["policy"],
                    required_scopes=["mastermind.executive.read",
                                     "mastermind.executive.intent.submit"])
    with pytest.raises(ValueError):
        compile_candidate(inputs=qualified_inputs(publication_document(policy=unsorted)))


def test_prior_mcp_profile_must_already_be_web_ceo_v3():
    for profile in (None, "legacy", "web_ceo_v2", "personal_read", "release_control_v1"):
        prior = prior_mcp_document()
        if profile is None:
            prior.pop("executive_mcp_profile")
        else:
            prior["executive_mcp_profile"] = profile
        with pytest.raises(ValueError, match="web_ceo_v3"):
            compile_candidate(mcp_bytes=prior_mcp_bytes(prior))


@pytest.mark.parametrize("overrides", [
    {"schema": "mastermind.other_install.v1"},
    {"service_uid": 459},
    {"service_uid": True},
    {"release_sha": "short"},
    {"port": 80},
    {"ceo_ingress_socket_path": "/var/run/other.sock"},
    {"audit_root": "/var/log/other"},
    {"unknown_field": True},
])
def test_prior_mcp_document_must_validate(overrides):
    with pytest.raises(ValueError):
        compile_candidate(mcp_bytes=prior_mcp_bytes(prior_mcp_document(**overrides)))


def test_prior_mcp_policies_envelope_must_load():
    prior = prior_mcp_document()
    prior["policies"] = {"read": prior["policies"]["read"]}
    with pytest.raises(ValueError):
        compile_candidate(mcp_bytes=prior_mcp_bytes(prior))
    prior = prior_mcp_document()
    prior["policies"]["submit"]["required_scopes"] = ["mastermind.executive.intent.submit"]
    with pytest.raises(ValueError):
        compile_candidate(mcp_bytes=prior_mcp_bytes(prior))


def test_primary_resource_colliding_with_os_audience_is_refused():
    prior = prior_mcp_document()
    prior["policies"]["read"]["resource"] = OS_EXECUTIVE_RESOURCE
    prior["policies"]["read"]["resource_metadata_url"] = (
        OS_EXECUTIVE_RESOURCE + "/.well-known/oauth-protected-resource")
    with pytest.raises(ValueError, match="duplicated"):
        compile_candidate(mcp_bytes=prior_mcp_bytes(prior))


@pytest.mark.parametrize("mutate", [
    lambda document: document.update(Label="com.mastermind.executive.control"),
    lambda document: document.update(UserName="_mastermind_exec"),
    lambda document: document.update(Extra=1),
    lambda document: document["ProgramArguments"].append("--verbose"),
    lambda document: document["ProgramArguments"].pop(),
    lambda document: document["ProgramArguments"].__setitem__(
        0, "/usr/bin/python3"),
    lambda document: document["EnvironmentVariables"].update(
        {"PYTHONPATH": "/tmp/override"}),
    lambda document: document.update({"Program": "/usr/bin/true"}),
])
def test_prior_plist_must_be_the_closed_gateway_profile(mutate):
    document = prior_plist_document()
    mutate(document)
    with pytest.raises(ValueError):
        compile_candidate(plist_bytes=plistlib.dumps(document))


def test_prior_plist_release_joins_the_prior_mcp_release():
    document = prior_plist_document(release=("e" * 40))
    with pytest.raises(ValueError, match="release join"):
        compile_candidate(plist_bytes=plistlib.dumps(document))


def test_compile_is_deterministic_and_independent_of_call_order():
    first = compile_candidate()
    second = compile_candidate()
    assert first == second
    assert [artifact.content for artifact in first.artifacts] == [
        artifact.content for artifact in second.artifacts]


def observed_of(candidate, **replace):
    observed = {artifact.path: artifact.content for artifact in candidate.artifacts}
    observed.update(replace)
    return observed


def test_postimage_classification_matches_only_exact_postimages():
    candidate = compile_candidate()
    result = m.classify_postimages(candidate, observed_of(candidate))
    assert result == {"schema": "mastermind.os_gateway_postimage.v1",
                      "operation": "OS_GATEWAY_PUBLICATION", "state": "MATCHED",
                      "reason": None,
                      "targets": {path: "PROPOSED" for path in observed_of(candidate)},
                      "replay_authorized": False, "rollback_authorized": False}


def test_postimage_classification_original_requires_bound_publication_beforeimage():
    candidate = compile_candidate()
    proposed_publication = proposed(candidate, m.COMMISSION_CONFIG_PATH).content
    without_binding = m.classify_postimages(
        candidate, observed_of(candidate, **{m.COMMISSION_CONFIG_PATH: None}))
    assert without_binding["state"] == "UNKNOWN"
    assert without_binding["reason"] == "publication_beforeimage_unbound"
    assert without_binding["targets"][m.COMMISSION_CONFIG_PATH] == "UNBOUND"
    unbound_bytes = m.classify_postimages(
        candidate, observed_of(candidate, **{m.COMMISSION_CONFIG_PATH: b"{}"}))
    assert unbound_bytes["state"] == "UNKNOWN"
    # An explicitly qualified before-image is honored only when the owner
    # supplies it; it is never the compiler's own output.
    qualified = proposed_publication[:-1] + b" \n"
    bound = m.classify_postimages(
        candidate, observed_of(candidate, **{m.COMMISSION_CONFIG_PATH: qualified}),
        publication_before_bytes=qualified)
    assert bound["targets"][m.COMMISSION_CONFIG_PATH] == "ORIGINAL"
    assert bound["state"] == "UNKNOWN"
    original = m.classify_postimages(
        candidate, {m.MCP_CONFIG_PATH: candidate.before_mcp_bytes,
                    m.MCP_PLIST_PATH: candidate.before_plist_bytes,
                    m.COMMISSION_CONFIG_PATH: qualified},
        publication_before_bytes=qualified)
    assert original["state"] == "ORIGINAL"
    assert original["targets"] == {m.MCP_CONFIG_PATH: "ORIGINAL",
                                   m.MCP_PLIST_PATH: "ORIGINAL",
                                   m.COMMISSION_CONFIG_PATH: "ORIGINAL"}
    assert original["replay_authorized"] is False and original["rollback_authorized"] is False


def test_postimage_mixed_foreign_and_partial_states_are_unknown():
    candidate = compile_candidate()
    cases = [
        (observed_of(candidate, **{m.MCP_PLIST_PATH: b"<plist><dict/></plist>"}),
         "mixed_or_foreign"),
        (observed_of(candidate, **{m.MCP_CONFIG_PATH: None}), "mixed_or_foreign"),
        (observed_of(candidate, **{m.MCP_CONFIG_PATH: candidate.before_mcp_bytes}),
         "mixed_or_foreign"),
        (observed_of(candidate,
                     **{m.COMMISSION_CONFIG_PATH: candidate.before_mcp_bytes}),
         "publication_beforeimage_unbound"),
    ]
    for observed, reason in cases:
        result = m.classify_postimages(candidate, observed)
        assert result["state"] == "UNKNOWN"
        assert result["reason"] == reason
        assert result["replay_authorized"] is False
        assert result["rollback_authorized"] is False
    bound_foreign = m.classify_postimages(
        candidate,
        observed_of(candidate, **{m.COMMISSION_CONFIG_PATH: candidate.before_mcp_bytes}),
        publication_before_bytes=b"{\n}\n")
    assert bound_foreign["targets"][m.COMMISSION_CONFIG_PATH] == "FOREIGN"
    assert bound_foreign["reason"] == "mixed_or_foreign"


def test_postimage_observations_are_closed_to_the_three_targets():
    candidate = compile_candidate()
    with pytest.raises(ValueError, match="three fixed targets"):
        m.classify_postimages(candidate, {})
    with pytest.raises(ValueError, match="three fixed targets"):
        m.classify_postimages(candidate, dict(observed_of(candidate), extra=b"x"))
    with pytest.raises(ValueError, match="exact bytes or explicit absence"):
        m.classify_postimages(candidate, observed_of(candidate, **{m.MCP_PLIST_PATH: "x"}))
    with pytest.raises(ValueError, match="gateway candidate required"):
        m.classify_postimages(object(), observed_of(candidate))


def test_classification_data_never_authorizes_recovery():
    candidate = compile_candidate()
    for observed in (observed_of(candidate),
                     observed_of(candidate, **{m.MCP_CONFIG_PATH: b"{}"}),
                     observed_of(candidate, **{m.COMMISSION_CONFIG_PATH: None})):
        result = m.classify_postimages(candidate, observed)
        assert result["replay_authorized"] is False
        assert result["rollback_authorized"] is False
