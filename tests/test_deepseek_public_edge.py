"""DSH ingress source proof; synthetic app bytes, no live publication or provider."""
import copy
import json
from pathlib import Path

import pytest

from integrations.deepseek_harness.package_attended import PIN, PUBLICATION_SCHEMA, PUBLICATION_CUSTODY
from ops.executive_os import deepseek_public_edge as planner
from ops.executive_os import os_public_edge_publication as m
from tests.test_os_public_edge_publication import inputs, git  # noqa: F401


def _config():
    return {"admin": {"listen": "127.0.0.1:2019"}, "storage": {"module": "file_system", "root": "/saved"},
            "apps": {"tls": {"automation": {"policies": [{"subjects": ["other.example.invalid"]}]}},
                     "http": {"servers": {"production": {"listen": [":443"], "routes": [
                         {"match": [{"host": [planner.OS_HOST]}], "terminal": True,
                          "handle": [{"handler": "static_response", "body": "unchanged OS fixture"}]},
                         {"match": [{"host": ["other.example.invalid"]}],
                          "handle": [{"handler": "static_response", "body": "unchanged other"}]},
                     ]}}}}}


def test_chat_route_preserves_complete_existing_configuration():
    original = _config()
    before = copy.deepcopy(original)
    candidate = planner.candidate_config(original)
    added = candidate["apps"]["http"]["servers"]["production"]["routes"].pop()
    assert candidate == original == before
    assert added == planner.site_route()
    proxy = added["handle"][0]["routes"][0]["handle"][-1]
    assert proxy["upstreams"] == [{"dial": "127.0.0.1:4181"}]
    assert "flush_interval" not in proxy
    assert added["match"] == [{"host": ["chat.mastermind-x.com"]}]


@pytest.mark.parametrize("mutation", [
    lambda s: s["routes"].append({"match": [{"host": [planner.HOST]}]}),
    lambda s: s["routes"].append({"match": [{"host": ["*.mastermind-x.com"]}]}),
    lambda s: s["routes"].append({"handle": [{"handler": "static_response"}]}),
    lambda s: s.update(listen=[":80"]),
    lambda s: s.update(automatic_https={"disable": True}),
    lambda s: s.update(tls_connection_policies=[{"match": {"sni": [planner.OS_HOST]}}]),
    lambda s: s.update(tls_connection_policies=[{"client_authentication": {"mode": "require_and_verify"}}]),
    lambda s: s.update(tls_connection_policies=[{"certificate_selection": {"any_tag": ["os-only"]}}]),
    lambda s: s.update(tls_connection_policies=[{"fallback_sni": planner.OS_HOST}]),
])
def test_chat_route_refuses_unqualified_or_overlapping_shape(mutation):
    original = _config()
    mutation(original["apps"]["http"]["servers"]["production"])
    with pytest.raises(ValueError):
        planner.candidate_config(original)


class Relay:
    def __init__(self, config, assets):
        self.config = config
        self.etag = '"original"'
        self.assets = assets
        self.posts = 0
        self.fault = None

    def http(self, port, method, path, *, body=None, headers=None, maximum=m.MAX_BYTES):
        assert port == 2019 and path == "/config/"
        if method == "POST":
            assert headers["If-Match"] == self.etag
            self.posts += 1
            self.config = json.loads(body)
            self.etag = '"next"'
            if self.fault == "lost":
                raise OSError("fixture response lost after config applied")
            return 200, {}, b""
        return 200, {"etag": self.etag}, m.canonical(self.config)

    def native(self, path, *, maximum):
        if path == "/":
            return (401, {"cache-control": "no-store", "content-type": "text/plain; charset=utf-8"},
                    b"dsh web authentication required; reopen the URL printed by dsh web.\n")
        raw, mime = self.assets[path]
        if self.fault == "asset":
            raw = raw[:-1]
        return 200, {"content-type": mime}, raw


def _stage(inputs, monkeypatch):
    accepted_path = "integrations/deepseek_harness/attended-build.json"
    accepted_raw = (Path(__file__).resolve().parents[1] / accepted_path).read_bytes()
    accepted = json.loads(accepted_raw)
    destination = inputs["source_repo"] / accepted_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(accepted_raw)
    git(inputs["source_repo"], "add", accepted_path)
    git(inputs["source_repo"], "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "accepted build fixture")
    inputs["new_sha"] = git(inputs["source_repo"], "rev-parse", "HEAD")
    inputs["new_tree"] = git(inputs["source_repo"], "rev-parse", "HEAD^{tree}")
    git(inputs["source_repo"], "update-ref", "refs/remotes/origin/master", inputs["new_sha"])
    artifact = inputs["out"].parent / "native-export"
    m._new_directory(artifact)
    assets, rows = {}, []
    with m.private(artifact) as area:
        for suffix, mime, raw in (("js", "text/javascript", b"console.log('native fixture');"),
                                  ("css", "text/css", b"body{background:#111}")):
            url, name = "/assets/index-fixture." + suffix, "client." + suffix + ".blob"
            assets[url] = (raw, mime)
            rows.append({"url": url, "mime": mime, "bytes": len(raw),
                         "sha256": m.digest(raw), "capture": name})
            area.write(name, raw)
        record = {"schema": PUBLICATION_SCHEMA, "custody": PUBLICATION_CUSTODY,
                  "source": {"sha": inputs["new_sha"], "tree": inputs["new_tree"]}, "donor_sha": PIN,
                  "host": planner.HOST, "native_port": 4180, "relay_port": 4181,
                  "package_manifest_sha256": accepted["package_manifest_sha256"], "package_entries": 12,
                  "build_qualification_sha256": m.digest(accepted_raw),
                  "app_config_sha256": accepted["app_config_sha256"],
                  "company_client_sha256": accepted["company_client_sha256"],
                  "company_patch_sha256": "4" * 64,
                  "native_client_build_sha256": accepted["native_client_build_sha256"],
                  "assets": rows, "installed": False, "public_route_qualified": False, "provider_calls": 0}
        raw = m.canonical(record)
        area.write("artifact-receipt.json", raw)
    relay = Relay(_config(), assets)
    monkeypatch.setattr(m, "_http", relay.http)
    monkeypatch.setattr(m, "_dsh_http", relay.native)
    monkeypatch.setattr(m, "_listener", lambda port, pid: m.require(port == 4181 and pid == 4242, "listener"))
    monkeypatch.setattr(m, "_validate_file", lambda stage, name, candidate:
                        m.require(m.decode(stage.read(name)) == candidate, "candidate"))
    result = m.stage_dsh(artifact_path=artifact, artifact_digest=m.digest(raw),
                         source_repo=inputs["source_repo"], source_sha=inputs["new_sha"],
                         source_tree=inputs["new_tree"], out=inputs["out"])
    request = {"stage_path": inputs["out"], "stage_digest": result["stage_digest"], "listener_pid": 4242}
    return relay, request


def test_native_ingress_uses_one_existing_publication_transaction(inputs, monkeypatch):
    relay, request = _stage(inputs, monkeypatch)
    result = m.publish_dsh(**request)
    assert result["state"] == "PUBLISHED" and relay.posts == 1
    with pytest.raises(ValueError, match="no replay"):
        m.publish_dsh(**request)
    assert relay.posts == 1


def test_native_ingress_lost_ack_retains_original_effect(inputs, monkeypatch):
    relay, request = _stage(inputs, monkeypatch)
    relay.fault = "lost"
    with pytest.raises(OSError, match="response lost"):
        m.publish_dsh(**request)
    journal = Path(request["stage_path"]) / m.OPERATION
    assert (journal / "dsh-intent.json").exists()
    assert (journal / "dsh-reconciliation.json").exists()
    assert not (journal / "dsh-receipt.json").exists()
    with pytest.raises(ValueError, match="no replay"):
        m.publish_dsh(**request)
    assert relay.posts == 1


@pytest.mark.parametrize("fault", ["etag", "asset", "capture"])
def test_native_ingress_refuses_drift_before_any_post(inputs, monkeypatch, fault):
    relay, request = _stage(inputs, monkeypatch)
    if fault == "etag":
        relay.etag = '"changed"'
    elif fault == "asset":
        relay.fault = "asset"
    else:
        (Path(request["stage_path"]) / "client.js.blob").write_bytes(b"altered")
    with pytest.raises(ValueError):
        m.publish_dsh(**request)
    assert relay.posts == 0
    assert not (Path(request["stage_path"]) / m.OPERATION).exists()


def test_chat_refuses_applicable_private_certificate_authority():
    config = _config()
    config["apps"]["tls"]["automation"]["policies"].append({"issuers": [{"module": "internal"}]})
    with pytest.raises(ValueError, match="issuance authority"):
        planner.candidate_config(config)


def test_chat_retains_unrelated_certificate_authority():
    config = _config()
    config["apps"]["tls"]["automation"]["policies"][0]["issuers"] = [{"module": "internal"}]
    candidate = planner.candidate_config(config)
    assert candidate["apps"]["tls"] == config["apps"]["tls"]


def test_native_ingress_rejects_rehashed_candidate_with_changed_json_type(inputs, monkeypatch):
    relay, request = _stage(inputs, monkeypatch)
    stage_path = Path(request["stage_path"])
    candidate = json.loads((stage_path / "candidate.json").read_bytes())
    candidate["apps"]["http"]["servers"]["production"]["routes"][-1]["terminal"] = 1
    raw = m.canonical(candidate)
    descriptor = json.loads((stage_path / m.DESCRIPTOR).read_bytes())
    descriptor["files"]["candidate.json"] = {"sha256": m.digest(raw), "bytes": len(raw)}
    descriptor_raw = m.canonical(descriptor)
    (stage_path / "candidate.json").write_bytes(raw)
    (stage_path / m.DESCRIPTOR).write_bytes(descriptor_raw)
    with pytest.raises(ValueError, match="native candidate differs"):
        m.publish_dsh(**{**request, "stage_digest": m.digest(descriptor_raw)})
    assert relay.posts == 0
    assert not (stage_path / m.OPERATION).exists()


def test_native_ingress_numeric_readback_cannot_publish_a_false_success(inputs, monkeypatch):
    relay, request = _stage(inputs, monkeypatch)
    original_http = relay.http
    def changed_readback(port, method, path, **kwargs):
        result = original_http(port, method, path, **kwargs)
        if method == "POST":
            relay.config["apps"]["http"]["servers"]["production"]["routes"][-1]["terminal"] = 1
        return result
    monkeypatch.setattr(m, "_http", changed_readback)
    with pytest.raises(ValueError, match="publication readback differs"):
        m.publish_dsh(**request)
    journal = Path(request["stage_path"]) / m.OPERATION
    assert (journal / "dsh-intent.json").exists()
    assert (journal / "dsh-reconciliation.json").exists()
    assert not (journal / "dsh-receipt.json").exists()
    with pytest.raises(ValueError, match="no replay"):
        m.publish_dsh(**request)
    assert relay.posts == 1
