"""Actual installed enrollment command with qualified disposable dependencies.

The CLI, profile serializer, native configuration validator and enrollment
receipt decoder are real. Linux custody and native RPC owners are explicit
doubles; no installed role, provider call or live enrollment is claimed.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from integrations.hermes_harness.native_byok import expected_native_config
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_harness.tests.test_native_executive_consumer import (
    _installation, publication_document,
)
from integrations.hermes_runtime import cli, native_gateway_entry, native_session_control
from integrations.hermes_runtime import role_isolation, system_service, tcp_sandbox
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA, conversation_contract
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import dump_profile
from ops.executive_os import hermes_role_metadata_observer as observer
from ops.executive_os.release_manifest import validate_hermes_runtime_installation

SHA = "a" * 40
BOOT = "fixture-original-boot"


@pytest.fixture
def enrollment_command(tmp_path, monkeypatch):
    def build(version=3, role="mmsecretary", *, primary_application=None):
        publication = publication_document() if version == 3 else None
        document = _installation(consumer=publication, role=role)
        row = next(item for item in document["roles"] if item["role"] == role)
        row["native_gateway"]["session_enrollment"]["schema"] = conversation_contract(role).enrollment_schema
        if publication is not None:
            publication["session"].update(role=role, principal_id=f"uid:{row['uid']}")
            row["native_gateway"]["executive_consumer"] = publication
        installation = validate_hermes_runtime_installation(document)
        row = next(item for item in installation["roles"] if item["role"] == role)
        recipe = deepcopy(row["native_gateway"])
        state_dir = tmp_path / ("v" + str(version)) / "state"
        home = state_dir / "current/hermes-home"
        profile = replace(
            compose_profile(role, state_dir=state_dir,
                            secrets_file=state_dir / "role.env", hermes_home=home),
            gateway_backend="native-session-authority",
            native_provider_id=("byteplus-modelark.glm-5.3-flash" if role == "mmsecretary" else "zai.glm-5.3"),
            tool_allowlist=frozenset({"clarify"}))
        if primary_application is not None:
            from integrations.hermes_application_fabric.publication import (
                PROVIDER, expected_native_config as application_config,
            )
            primary = deepcopy(primary_application)
            primary["enrollment_request_id"] = recipe["session_enrollment"]["request_id"]
            primary["principal_id"] = f"uid:{row['uid']}"
            recipe["primary_application"] = primary
            recipe["schema"] = "mastermind.hermes_native_gateway_installation/v4"
            profile = replace(profile, model_provider=PROVIDER,
                              model_default=primary["model"], native_provider_id=None)
        profile_path = state_dir / "current/profile.yaml"
        native_config = home / "profiles" / role / "config.yaml"
        native_config.parent.mkdir(parents=True)
        config_text = (
            application_config(profile, recipe["primary_application"], publication)
            if primary_application is not None else expected_native_config(profile, publication)
        )
        native_config.write_text(config_text, encoding="utf-8")
        native_config.chmod(0o600)
        profile_path.write_text(dump_profile(profile), encoding="utf-8")
        hermes_bin = state_dir / "current/bin/hermes"
        actual_home = native_config.parent.resolve()
        state = SimpleNamespace(
            inspections=0, creations=0, qualifications=0, changed=False,
            inspect_status="ABSENT", lose_after_create=False,
            change_after_read=False, change_after_create=False,
            prepares=0, checks=0)
        target = dict(profile_id=str(actual_home), session_id="original-native-session",
                      principal_id=f"uid:{row['uid']}", instance_id="original-native-owner",
                      authority_epoch=7, revision=0, execution_generation=0)
        endpoint = SimpleNamespace(
            profile_id=str(actual_home), instance_id=target["instance_id"],
            authority_epoch=target["authority_epoch"], code_sha=PINNED_UPSTREAM_SHA,
            runtime_protocol=1, supervisor="external",
            api_origin=f"http://{profile.gateway_host}:{profile.backend_port}",
            capabilities=native_gateway_entry._CAPABILITIES)

        def qualify(current, binary):
            state.qualifications += 1
            assert dump_profile(current) == dump_profile(profile) and binary == hermes_bin
            if state.changed:
                raise RuntimeRefusal("NATIVE_ENROLLMENT_OWNER_CHANGED")

        def check():
            state.checks += 1
            if state.changed:
                raise RuntimeRefusal("NATIVE_ENROLLMENT_OWNER_CHANGED")

        def observe_child(pid):
            assert pid == 200
            return dict(parent_pid=100, boot_id=BOOT, start_identity="original-start")

        launch = SimpleNamespace(
            recipe=recipe, owner=SimpleNamespace(root=Path("/held") / SHA),
            row=row, qualify=qualify, check=check, observe_child=observe_child)

        class Held:
            def __init__(self, implementation):
                assert implementation == SHA

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def check(self):
                check()

            def role_facts(self, role, properties, boot):
                assert role == profile.role and boot == BOOT and properties == {"Id": "original"}
                return dict(main_pid=100, boot_id=BOOT, gateway_listener="qualified")

        class Client:
            def __init__(self, directory, *, expected_pid, role="mmsecretary"):
                assert directory == actual_home and expected_pid == 200 and role == profile.role

            def inspect_enrollment(self, implementation, request):
                assert implementation == SHA and request == recipe["session_enrollment"]["request_id"]
                state.inspections += 1
                if state.change_after_read:
                    state.changed = True
                return native_session_control.enrollment_result(
                    implementation, request, state.inspect_status,
                    target if state.inspect_status == "ENROLLED" else None, role=profile.role)

            def enroll_session(self, implementation, request):
                assert implementation == SHA and request == recipe["session_enrollment"]["request_id"]
                state.creations += 1
                if state.change_after_create:
                    state.changed = True
                if state.lose_after_create:
                    raise TimeoutError("original native reply lost")
                state.inspect_status = "ENROLLED"
                return native_session_control.enrollment_result(
                    implementation, request, "ENROLLED", target, role=profile.role)

        async def query(*, role):
            assert role == profile.role
            return [dict(role=role, unit_properties={"Id": "original"})]

        def prepare(path):
            assert str(path) == recipe["vendor_root"]
            state.prepares += 1

        def add_module(name, **members):
            value = ModuleType(name)
            value.__dict__.update(members)
            monkeypatch.setitem(sys.modules, name, value)
            return value

        parent = add_module("hermes_cli")
        parent.__path__ = []
        add_module("hermes_cli.gateway_runtime_discovery",
                   query_identify=lambda home, **kwargs: dict(pid=200, hermes_home=str(home)))
        add_module("hermes_cli.gateway_runtime",
                   _endpoint=lambda payload, home: SimpleNamespace(state="ready", endpoint=endpoint))
        monkeypatch.setattr(native_gateway_entry, "prepare_vendor", prepare)
        monkeypatch.setattr(native_session_control, "NativeSecretaryClient", Client)
        monkeypatch.setattr(observer, "_HeldRoleQualification", Held)
        monkeypatch.setattr(observer, "_query_fixed_pid1", query)
        monkeypatch.setattr(observer, "_boot_id", lambda: BOOT)
        monkeypatch.setattr(system_service, "assert_root_service_cgroup",
                            lambda role: None if role == profile.role else pytest.fail("foreign role"))
        monkeypatch.setattr(system_service, "assert_role_network_profile", lambda current: None)
        monkeypatch.setattr(role_isolation, "assert_role_credential_isolation", lambda current: None)
        monkeypatch.setattr(tcp_sandbox, "enforce_role_tcp_ports", lambda current: None)
        return SimpleNamespace(state=state, launch=launch, profile=profile,
                               path=profile_path, binary=hermes_bin, config=native_config,
                               target=target)
    return build


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_actual_command_enrolls_original_once_and_reopens_existing(enrollment_command, capsys, version, role):
    world = enrollment_command(version, role)
    command = "enroll-secretary-session" if role == "mmsecretary" else "enroll-meta-session"
    argv = [command, "--profile", str(world.path),
            "--hermes-bin", str(world.binary)]
    for _ in range(2):
        assert cli.main(argv, native_launch=world.launch) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "ENROLLED" and result["target"] == world.target
    assert world.state.inspections == 2 and world.state.creations == 1
    assert world.state.qualifications >= 7 and world.state.checks > 0


@pytest.mark.parametrize("version", [1, 5])
def test_disarmed_or_unknown_recipe_refuses_before_native_import(enrollment_command, version):
    world = enrollment_command()
    world.launch.recipe["schema"] = f"mastermind.hermes_native_gateway_installation/v{version}"
    with pytest.raises(RuntimeRefusal, match="NATIVE_ENROLLMENT_INSTALLATION_REQUIRED"):
        cli._enroll_secretary_session(world.path, world.binary, native_launch=world.launch)
    assert world.state.prepares == world.state.inspections == world.state.creations == 0


@pytest.mark.parametrize("status", ["REFUSED", "UNAVAILABLE", "EFFECT_UNKNOWN"])
def test_nonabsence_never_creates_replacement(enrollment_command, capsys, status):
    world = enrollment_command()
    world.state.inspect_status = status
    code = cli._enroll_secretary_session(world.path, world.binary, native_launch=world.launch)
    assert code == (3 if status == "EFFECT_UNKNOWN" else 2)
    assert json.loads(capsys.readouterr().out)["status"] == status
    assert world.state.inspections == 1 and world.state.creations == 0


@pytest.mark.parametrize("change", ["lose_after_create", "change_after_create"])
def test_uncertain_original_create_is_retained_without_retry(enrollment_command, capsys, change):
    world = enrollment_command()
    setattr(world.state, change, True)
    assert cli._enroll_secretary_session(world.path, world.binary, native_launch=world.launch) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "EFFECT_UNKNOWN" and result["target"] is None
    assert world.state.inspections == world.state.creations == 1


def test_owner_change_before_create_remains_nonmodifying(enrollment_command, capsys):
    world = enrollment_command()
    world.state.change_after_read = True
    assert cli._enroll_secretary_session(world.path, world.binary, native_launch=world.launch) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "UNAVAILABLE"
    assert world.state.inspections == 1 and world.state.creations == 0


def test_v3_config_drift_refuses_before_native_import(enrollment_command):
    world = enrollment_command()
    world.config.write_bytes(world.config.read_bytes() + b"\nforeign: true\n")
    with pytest.raises(RuntimeRefusal, match="RUNTIME_NATIVE_CONFIG_DRIFT"):
        cli._enroll_secretary_session(world.path, world.binary, native_launch=world.launch)
    assert world.state.prepares == world.state.inspections == world.state.creations == 0


def test_consumer_config_requires_the_original_held_publication(enrollment_command):
    world = enrollment_command()
    world.launch.recipe.pop("executive_consumer")
    with pytest.raises(RuntimeRefusal, match="RUNTIME_NATIVE_CONFIG_DRIFT"):
        cli._enroll_secretary_session(world.path, world.binary, native_launch=world.launch)
    assert world.state.prepares == world.state.inspections == world.state.creations == 0


def test_no_held_launch_refuses_without_an_enrollment_effect(enrollment_command):
    world = enrollment_command()
    with pytest.raises(RuntimeRefusal, match="NATIVE_ENROLLMENT_HELD_LAUNCH_REQUIRED"):
        cli._enroll_secretary_session(world.path, world.binary)
    assert world.state.prepares == world.state.inspections == world.state.creations == 0


def test_v3_preserves_disabled_steward_and_credential_free_executive(enrollment_command):
    from integrations.hermes_steward.config_guard import _load_unique_yaml
    world = enrollment_command()
    config = _load_unique_yaml(world.config.read_bytes())
    base = _load_unique_yaml(expected_native_config(world.profile).encode("utf-8"))
    assert {key: value for key, value in config.items() if key not in {"mcp_servers", "plugins"}} == {
        key: value for key, value in base.items() if key != "mcp_servers"}
    steward = config["mcp_servers"]["mastermind_steward"]
    assert steward == base["mcp_servers"]["mastermind_steward"]
    assert steward["enabled"] is False
    assert steward["headers"]["Authorization"] == "Bearer " + "$" + "{MASTERMIND_STEWARD_ACCESS_TOKEN}"
    consumer = world.launch.recipe["executive_consumer"]
    executive = config["mcp_servers"][consumer["mcp"]["server"]]
    assert executive["auth"] == "oauth" and executive["tools"]["include"] == []
    assert "headers" not in executive and "client_secret" not in executive["oauth"]
    assert "bearer " not in json.dumps(executive).lower()


def test_v3_refuses_bearer_material_in_new_connection(enrollment_command):
    world = enrollment_command()
    publication = deepcopy(world.launch.recipe["executive_consumer"])
    publication["mcp"]["client_id"] = "Bearer synthetic-publication-sentinel"
    with pytest.raises(RuntimeRefusal):
        expected_native_config(world.profile, publication)


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_command_cannot_enroll_the_other_role(enrollment_command, role):
    world = enrollment_command(role=role)
    operation = cli._enroll_meta_session if role == "mmsecretary" else cli._enroll_secretary_session
    with pytest.raises(RuntimeRefusal, match="NATIVE_ENROLLMENT_INSTALLATION_REQUIRED"):
        operation(world.path, world.binary, native_launch=world.launch)
    assert world.state.qualifications == world.state.inspections == world.state.creations == 0

