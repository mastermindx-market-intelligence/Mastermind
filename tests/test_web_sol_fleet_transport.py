from __future__ import annotations

import inspect
import json
import os
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_instance as instance
from integrations.chairman_surfaces import web_sol_native_host as native


MULTILOGIN_FOLDER = "11111111-1111-4111-8111-111111111111"
MULTILOGIN_PROFILE = "22222222-2222-4222-8222-222222222222"
GOLOGIN_PROFILE = "aaaaaaaaaaaaaaaaaaaaaaaa"
SHORT_TEST_ROOT = Path("/tmp/w")


def managed_binding(
    *,
    manager: str = "multilogin",
    folder_id: str = MULTILOGIN_FOLDER,
    profile_id: str = MULTILOGIN_PROFILE,
    url: str = "https://chatgpt.com/c/session-alpha",
    work_ref: str = "WS:CCR",
    seat_ref: str = "chatgpt1",
    binding_id: str = "33333333-3333-4333-8333-333333333333",
) -> dict:
    locator = {"env_manager": manager, "profile_id": profile_id, "url": url}
    if manager == "multilogin":
        locator["folder_id"] = folder_id
    return sb.new_binding(
        work_ref=work_ref,
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator=locator,
        observed_at="2026-08-30T07:00:00Z",
        seat_ref=seat_ref,
        binding_id=binding_id,
    )


def test_instance_identity_uses_only_the_canonical_managed_environment_coordinate():
    first = managed_binding()
    second = managed_binding(
        url="https://chatgpt.com/c/session-beta",
        work_ref="WS:OTHER",
        seat_ref="chatgpt2",
        binding_id="44444444-4444-4444-8444-444444444444",
    )

    assert instance.adapter_instance_id(first) == instance.adapter_instance_id(second)


def test_distinct_multilogin_profiles_and_folders_have_distinct_instances_and_sockets():
    original = managed_binding()
    changed_profile = managed_binding(profile_id="55555555-5555-4555-8555-555555555555")
    changed_folder = managed_binding(folder_id="66666666-6666-4666-8666-666666666666")

    identities = {
        instance.adapter_instance_id(original),
        instance.adapter_instance_id(changed_profile),
        instance.adapter_instance_id(changed_folder),
    }
    assert len(identities) == 3
    assert len({instance.socket_path(value, root=SHORT_TEST_ROOT) for value in identities}) == 3


def test_gologin_instance_uses_profile_without_inventing_a_folder_coordinate():
    first = managed_binding(manager="gologin", profile_id=GOLOGIN_PROFILE)
    second = managed_binding(
        manager="gologin",
        profile_id=GOLOGIN_PROFILE,
        url="https://chatgpt.com/c/session-beta",
        work_ref="WS:OTHER",
    )

    assert instance.adapter_instance_id(first) == instance.adapter_instance_id(second)


def test_instance_derivatives_are_opaque_and_bounded():
    row = managed_binding()
    value = instance.adapter_instance_id(row)
    leaf = instance.socket_leaf(value)
    host_name = instance.native_host_name(value)
    destination = instance.socket_path(value, root=SHORT_TEST_ROOT)
    serialized = json.dumps(
        {"instance": value, "leaf": leaf, "host": host_name, "path": str(destination)},
        sort_keys=True,
    )

    assert len(value) == 64
    assert value == value.lower()
    assert row["locator"]["folder_id"] not in serialized
    assert row["locator"]["profile_id"] not in serialized
    assert leaf == f"wsx-{value[:instance.SOCKET_LEAF_HEX]}.sock"
    assert host_name == f"com.mastermind.web_sol_surface.{value[:instance.NATIVE_HOST_LEAF_HEX]}"


def test_invalid_binding_instance_and_overlong_explicit_socket_path_fail_closed(tmp_path):
    with pytest.raises(instance.WebSolInstanceError, match="invalid_binding"):
        instance.adapter_instance_id({"provider": "codex"})
    with pytest.raises(instance.WebSolInstanceError, match="invalid_instance_id"):
        instance.socket_path("not-a-digest", root=SHORT_TEST_ROOT)
    with pytest.raises(instance.WebSolInstanceError, match="socket_path_too_long"):
        instance.socket_path("a" * 64, root=tmp_path / ("x" * 120))


def test_default_socket_path_prefers_application_support_when_it_fits(monkeypatch):
    home = Path("/Users/wsx")
    monkeypatch.setenv("HOME", str(home))
    destination = instance.socket_path("a" * 64)

    assert destination.parent == home / "Library" / "Application Support" / "Mastermind" / "wsx"
    assert len(os.fsencode(destination)) < instance.DARWIN_SUN_PATH_BYTES


def test_default_socket_path_uses_deterministic_uid_scoped_short_root_when_home_is_too_long(monkeypatch):
    monkeypatch.setenv("HOME", f"/tmp/{'h' * 80}")
    monkeypatch.setattr(instance.os, "getuid", lambda: 501)

    destination = instance.socket_path("a" * 64)

    assert destination.parent == Path("/tmp/mmx-wsx-501")
    assert destination.name == instance.socket_leaf("a" * 64)
    assert len(os.fsencode(destination)) < instance.DARWIN_SUN_PATH_BYTES


def test_public_web_sol_actions_do_not_accept_socket_or_instance_overrides():
    for function in (client.inspect_via_extension, client.foreground_via_extension):
        parameters = inspect.signature(function).parameters
        for forbidden in (
            "socket_path",
            "socket_root",
            "instance_id",
            "native_host",
            "profile_id",
            "folder_id",
        ):
            assert forbidden not in parameters


def test_client_routes_one_action_to_the_socket_derived_from_its_binding(monkeypatch):
    row = managed_binding(manager="gologin", profile_id=GOLOGIN_PROFILE)
    seen: list[tuple[dict, Path]] = []

    def exchange(request: dict, *, path: Path):
        seen.append((request, path))
        raise client.WebSolExtensionError("fixture_stop")

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    with pytest.raises(client.WebSolExtensionError, match="fixture_stop"):
        client.inspect_via_extension(
            row,
            operation_key="web-sol-fleet-routing-test",
            issued_at="2026-08-30T07:00:00Z",
            expires_at="2026-08-30T07:00:30Z",
            nonce="fixture-nonce-0123456789",
        )

    expected_instance = instance.adapter_instance_id(row)
    assert len(seen) == 1
    assert seen[0][1] == instance.socket_path(expected_instance)


def test_native_host_requires_a_wrapper_fixed_instance_and_has_no_global_production_socket():
    signature = inspect.signature(native.run_native_host)
    assert "expected_instance_id" in signature.parameters
    assert "socket_root" in signature.parameters
    assert "socket_path" not in signature.parameters
    assert not hasattr(native, "SOCKET_PATH")
