"""GLM through the sealed native generation and the original finite v9 owner.

All Git source commitments, provider files, credentials, accounts and runtime
owners in this module are disposable fixtures. No provider request is made.
"""
from contextlib import redirect_stdout, redirect_stderr
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
sys.path.insert(0, str(NATIVE / "tests"))
from test_go_native_stage import g, installer, loaded_entry, published, unseal
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner
from test_go_service_enrollment import (
    service_owner, prepare, unchanged_ingress,
    reseal_modified_entry_for_disposable_fixtures,
)
from test_go_service_startup import environment, boot
from test_hermes_primary_application_enrollment import select_role, isolated_native_service_imports

PROFILES = ("hermes-attended", "hermes-secretary", "hermes-meta-ceo")
MODELS = ("glm-5.3", "glm-5.3-flash")


@pytest.fixture(scope="module")
def glm_source_stage(tmp_path_factory):
    """A real fixture commit binds captured inputs; no production SHA is invented."""
    work = tmp_path_factory.mktemp("glm-committed-native-source").resolve()
    repo = work / "repository"
    target = repo / "ops/native_fabric"
    target.parent.mkdir(parents=True)
    shutil.copytree(ROOT / "ops/native_fabric", target, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    shutil.copytree(ROOT / "control_plane", repo / "control_plane", symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    shutil.copytree(ROOT / "requirements", repo / "requirements", symlinks=True)
    def git(*args):
        result = subprocess.run(["git", "-C", str(repo), *args],
                                capture_output=True, check=True)
        return result.stdout.decode().strip()
    git("init", "--quiet")
    inputs = [
        "ops/native_fabric/quota_continuity/source/glm_keys.py",
        "ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py",
        "ops/native_fabric/quota_continuity/candidate/application_http_transports.py",
        "ops/native_fabric/quota_continuity/rollout/application_http_realm_projection.py",
    ]
    git("add", "--", *inputs)
    git("-c", "user.name=Native GLM Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
        "commit", "--quiet", "-m", "Capture synthetic GLM source proof")
    commit = git("rev-parse", "HEAD")
    path = target / "quota_continuity/rollout/build_review_stage.py"
    name = "_fixture_committed_glm_stage_builder"
    prior = sys.modules.get(name)
    specification = importlib.util.spec_from_file_location(name, path)
    builder = importlib.util.module_from_spec(specification)
    sys.modules[name] = builder
    try:
        specification.loader.exec_module(builder)
        output = work / "reviewed-stage"
        with mock.patch.object(sys, "argv", [
                "builder", "--output", str(output), "--include-go-application",
                "--include-application-http", "--include-application-glm"]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            builder.main()
        yield SimpleNamespace(root=repo, native=target / "quota_continuity",
                              builder=builder, output=output, commit=commit)
    finally:
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior
        unseal(work)


@pytest.fixture(scope="module")
def native_stage(glm_source_stage):
    return glm_source_stage.output


@pytest.fixture(autouse=True)
def captured_source_owner(glm_source_stage, monkeypatch):
    # Same original installer, with its actual copied and committed source owner.
    monkeypatch.setattr(installer, "stage_builder", glm_source_stage.builder)


def configure_glm_role(case, monkeypatch, profile):
    monkeypatch.delenv("LANE_LEASED", raising=False)
    monkeypatch.delenv("POOL_ACCOUNT", raising=False)
    config = case.root / "glm-provider" / "config.json"
    if not config.exists():
        config.parent.mkdir(mode=0o700)
        config.write_text(json.dumps({
            "api_key": "fixture-legacy-only-for-original-enabled-contract",
            "model": "glm-5.3",
            "openai_base_url": "https://api.z.ai/api/coding/paas/v4",
            "accounts": {
                "account-a": {"api_key": "fixture-glm-account-a"},
                "account-b": {"api_key": "fixture-glm-account-b"},
            },
        }))
        config.chmod(0o600)
    monkeypatch.setenv("GLM_CONFIG", str(config))
    case.glm_config = config
    document = json.loads(case.accounts.read_bytes())
    if "glm" not in document["providers"]:
        document["providers"]["glm"] = copy.deepcopy(document["providers"]["go"])
        document["providers"]["glm"]["enabled"] = "auto"
        case.accounts.write_text(json.dumps(document))
    case.document = document
    select_role(case, profile)
    case.specification["scope"]["route_scope"] = {
        "schema": "mastermind.application_route_scope.v1", "pools": ["glm"]}
    original = case.specification.pop("grant")
    grants, recipes = [], []
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release,
                                verified_metadata=case.published.meta)
        for index, model in enumerate(MODELS):
            recipe = entry.application_http_recipe(startup, model, pool="glm")
            _, digest = startup.broker_module._application_http_recipe(
                recipe, pool="glm", model=model)
            grant = copy.deepcopy(original)
            grant.update(grant_id=original["grant_id"] + "-glm-" + str(index),
                         pool="glm", models=[model], recipe_digest=digest)
            grant.pop("transport_kind", None)
            grants.append(grant)
            recipes.append(recipe)
        projection_sha256 = startup.glm_projection_sha256
    case.specification["grants"] = grants
    case.specification["glm_application_http"] = {
        "pool": "glm", "source_projection_sha256": projection_sha256,
        "recipes": recipes,
        "accounts": sorted({name for grant in grants for name in grant["accounts"]}),
    }
    return case


def inspect(entry, case):
    return entry.inspect(verified_root=case.published.release,
                         verified_metadata=case.published.meta)


def test_glm_stage_has_one_closed_pair_and_a_real_fixture_source_commit(glm_source_stage):
    stage = glm_source_stage.output
    manifest = json.loads((stage / "native-manifest.json").read_bytes())
    builder = glm_source_stage.builder
    assert builder.GLM_HTTP_GENERATION_MEMBERS == g.GLM_HTTP_REQUIRED
    assert (builder.HTTP_GENERATION_MEMBERS | builder.GLM_HTTP_GENERATION_MEMBERS) <= set(manifest)
    raw = (stage / "native-code-stage/ext/application_http_realms.v2.json").read_bytes()
    projection = json.loads(raw)
    assert projection["glm_source_commit"] == glm_source_stage.commit
    assert projection["legacy_projection"] == json.loads(
        (stage / "native-code-stage/ext/application_http_realms.v1.json").read_bytes())
    assert g.digest(raw) == manifest["ext/application_http_realms.v2.json"]
    assert manifest["ext/glm_application_adapter.py"] == (
        "d680789e7a184b7b882a57f6cc7b0337b6bebc4e27069ac8263aeffd456c5fed")
    for missing in builder.GLM_HTTP_GENERATION_MEMBERS | builder.HTTP_GENERATION_MEMBERS:
        partial = dict(manifest)
        del partial[missing]
        with pytest.raises(ValueError, match="HTTP closure"):
            g.manifest_files(partial)


def test_flat_inspection_preserves_external_helper_and_has_no_private_effects(service_owner):
    case = service_owner
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        assert startup.glm_adapter.__name__ == "glm_application_adapter"
        assert startup.glm_keys.__file__ == str(case.published.release / "ext/glm_keys.py")
        assert entry.GLM_HELPER_SHA256 == (
            "020b9ef9c59260d07980a23f2ac277d4e4d7350ff81e010d071fd733cc05b1fc")
        with mock.patch.object(startup.glm_keys, "_load_raw", side_effect=AssertionError("private read")), \
                mock.patch.object(sqlite3, "connect", side_effect=AssertionError("database")), \
                mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network")), \
                mock.patch.object(socket.socket, "bind", side_effect=AssertionError("listener")):
            again = inspect(entry, case)
            assert again.glm_projection == startup.glm_projection
            assert len(again.http_recipes) == 4
            assert sys.modules["glm_shim"] is not again.glm_adapter


@pytest.mark.parametrize("profile", PROFILES)
def test_actual_v9_role_captures_custody_and_starts_the_original_http_pool(
        service_owner, monkeypatch, profile):
    case = configure_glm_role(service_owner, monkeypatch, profile)
    plan = prepare(case)
    original_secret = installer.secrets.token_urlsafe
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_secret) as mint:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert mint.call_count == 1
    private = json.loads(case.binding.read_bytes())
    record = plan["glm_application_http"]
    assert record == private["glm_application_http"] == receipt["glm_application_http"]
    assert record["provider_profile"] == str(case.glm_config)
    assert record["provider_profile_identity"]["ino"] == case.glm_config.stat().st_ino
    assert record["provider_profile_sha256"] == g.digest(case.glm_config.read_bytes())
    assert private["credential"] not in json.dumps([plan, receipt])
    assert len({grant["recipe_digest"] for grant in case.specification["grants"]}) == 2
    assert plan["scope"]["account_profile"] == str(case.profile)
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        completed = entry.load_completed_application_startup(startup, profile)
        assert completed[0][0].principal_id == profile and completed[2] == case.profile
        assert type(completed[3]) is entry.GLMHTTPServiceProjection
        observed = {}
        def original_main(**kwargs):
            observed.update(kwargs)
            assert type(kwargs["application_broker"]) is startup.broker_module.Broker
            assert Path(kwargs["application_broker"].db_path) == case.ext / "broker/leases.sqlite"
            return 73
        with mock.patch.object(startup.handler, "main", side_effect=original_main):
            assert boot(entry, case) == 73
        bindings = observed["application_http_binding"]
        assert set(bindings) == {"glm"}
        binding = bindings["glm"]
        assert type(binding.driver) is startup.glm_adapter.GlmChatCompletionsDriver
        assert binding.credential_loader("account-a") == "fixture-glm-account-a"
        assert binding.recipe("glm-5.3") == record["recipes"][0]
    unchanged_ingress(case)


@pytest.mark.parametrize("fault", ("content", "inode", "owner-path", "endpoint", "accounts"))
def test_provider_custody_change_before_apply_has_no_enrollment_effect(
        service_owner, monkeypatch, fault):
    case = configure_glm_role(service_owner, monkeypatch, "hermes-secretary")
    prepare(case)
    raw = case.glm_config.read_bytes()
    if fault == "content":
        case.glm_config.write_bytes(raw + b"\n")
    elif fault == "inode":
        alternate = case.glm_config.with_name("replacement.json")
        alternate.write_bytes(raw)
        alternate.chmod(0o600)
        os.replace(alternate, case.glm_config)
    elif fault == "owner-path":
        alternate = case.glm_config.with_name("foreign.json")
        alternate.write_bytes(raw)
        alternate.chmod(0o600)
        monkeypatch.setenv("GLM_CONFIG", str(alternate))
    else:
        document = json.loads(raw)
        if fault == "endpoint":
            document["openai_base_url"] = "https://api.z.ai/api/paas/v4"
        else:
            document["accounts"].pop("account-a")
        case.glm_config.write_text(json.dumps(document))
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("minted")):
        with pytest.raises(ValueError):
            installer.apply_go_service_enrollment(case.service_bundle)
    assert not case.intent.exists() and not case.binding.exists() and not case.service_receipt.exists()
    unchanged_ingress(case)


@pytest.mark.parametrize("fault", ("shared-model-digest", "extra-custody-claim", "recipe-digest", "legacy-schema"))
def test_semantic_specification_cannot_assert_custody_or_cross_schema(
        service_owner, monkeypatch, fault):
    case = configure_glm_role(service_owner, monkeypatch, "hermes-secretary")
    if fault == "shared-model-digest":
        case.specification["grants"][0]["models"] = list(MODELS)
    elif fault == "extra-custody-claim":
        case.specification["glm_application_http"]["provider_profile"] = str(case.glm_config)
    elif fault == "recipe-digest":
        case.specification["grants"][1]["recipe_digest"] = case.specification["grants"][0]["recipe_digest"]
    else:
        case.specification["schema"] = "native-go-service-enrollment-specification.v1"
    with pytest.raises(ValueError):
        prepare(case)
    assert not case.service_bundle.exists()
    assert not case.intent.exists() and not case.binding.exists()


def test_completed_enrollment_recovers_after_provider_removal_but_fresh_key_refuses(
        service_owner, monkeypatch):
    case = configure_glm_role(service_owner, monkeypatch, "hermes-meta-ceo")
    prepare(case)
    receipt = installer.apply_go_service_enrollment(case.service_bundle)
    case.glm_config.unlink()
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("remint")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed write")):
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        completed = entry.load_completed_application_startup(startup, "hermes-meta-ceo")
        binding = entry._application_http_binding(startup, completed[3])
        with pytest.raises((OSError, ValueError)):
            binding.credential_loader("account-a")
        assert entry.load_completed_application_startup(startup, "hermes-meta-ceo") == completed


def test_lost_glm_binding_rename_ack_keeps_original_credential_and_record(
        service_owner, monkeypatch):
    case = configure_glm_role(service_owner, monkeypatch, "hermes-secretary")
    plan = prepare(case)
    replace, mint = installer.os.replace, installer.secrets.token_urlsafe
    renamed = []
    def lost_ack(source, target):
        replace(source, target)
        if Path(target) == case.binding and not renamed:
            renamed.append(case.binding.stat().st_ino)
            raise OSError("fixture lost original binding rename acknowledgement")
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=mint) as generated:
        with mock.patch.object(installer.os, "replace", side_effect=lost_ack):
            with pytest.raises(OSError, match="original binding"):
                installer.apply_go_service_enrollment(case.service_bundle)
        assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "partial"
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert generated.call_count == 1 and case.binding.stat().st_ino == renamed[0]
    assert receipt["glm_application_http"] == plan["glm_application_http"]
    assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt


def test_three_roles_share_one_verified_provider_projection_without_rewriting_peers(
        service_owner, monkeypatch):
    case = service_owner
    original = copy.deepcopy(case.specification)
    retained = {}
    for profile in PROFILES:
        case.specification = copy.deepcopy(original)
        configure_glm_role(case, monkeypatch, profile)
        prepare(case)
        installer.apply_go_service_enrollment(case.service_bundle)
        for path, (raw, inode) in retained.items():
            assert path.read_bytes() == raw and path.stat().st_ino == inode
        retained[case.binding] = case.binding.read_bytes(), case.binding.stat().st_ino
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        services, _, account_profile, projections = entry.load_all_completed_application_startup(startup)
        assert {service.principal_id for service in services} == set(PROFILES)
        assert account_profile == case.profile and set(projections) == {"glm"}
        assert len(projections["glm"].recipes_json) == 2
        assert set(entry._application_http_bindings(startup, projections)) == {"glm"}



def test_captured_projection_verification_is_exact_and_never_requalifies_git(glm_source_stage):
    builder = glm_source_stage.builder
    raw = (glm_source_stage.output /
           "native-code-stage/ext/application_http_realms.v2.json").read_bytes()
    expected = g.digest(raw)
    with mock.patch.object(subprocess, "run", side_effect=AssertionError("installer attempted Git")):
        sources = builder.application_http_sources(
            glm_source_stage.native, include_glm=True,
            captured_projection=raw, captured_projection_sha256=expected)
        assert sources["ext/application_http_realms.v2.json"][0] == raw
        assert set(sources) == builder.HTTP_GENERATION_MEMBERS | builder.GLM_HTTP_GENERATION_MEMBERS
        with pytest.raises(ValueError):
            builder.application_http_sources(
                glm_source_stage.native, include_glm=True,
                captured_projection=raw + b"\n", captured_projection_sha256=expected)
        with pytest.raises(ValueError):
            builder.application_http_sources(
                glm_source_stage.native, include_glm=True, captured_projection=raw)
        with pytest.raises(ValueError):
            builder.application_http_sources(
                glm_source_stage.native, captured_projection=raw,
                captured_projection_sha256=expected)


def test_changed_projection_cannot_enter_the_original_installer(
        glm_source_stage, tmp_path):
    output = tmp_path / "changed-projection"
    shutil.copytree(glm_source_stage.output, output)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    component = json.loads((output / "external-go-component/component.json").read_bytes())
    projection = output / "native-code-stage/ext/application_http_realms.v2.json"
    projection.write_bytes(projection.read_bytes() + b"\n")
    with mock.patch.object(subprocess, "run", side_effect=AssertionError("installer attempted Git")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("minted")):
        with pytest.raises(ValueError):
            installer._go_component(
                output / "external-go-component", Path(component["stable_ext"]), manifest)
