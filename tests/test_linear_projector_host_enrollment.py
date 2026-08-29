from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest


MODULE = "ops.linear_projector.host_enrollment"


def _load():
    spec = importlib.util.find_spec(MODULE)
    assert spec is not None, "CRED0 host_enrollment module is not built yet"
    return importlib.import_module(MODULE)


def test_linear_projector_host_enrollment_module_exists() -> None:
    assert importlib.util.find_spec(MODULE) is not None


def test_production_coordinates_and_identity_are_fixed() -> None:
    mod = _load()
    assert mod.ROOT == Path("/Library/Application Support/MastermindPortfolioProjector")
    assert mod.CONFIG_DIR == mod.ROOT / "config"
    assert mod.CONFIG_PATH == mod.CONFIG_DIR / "projector.json"
    assert mod.SECRET_PATH == mod.CONFIG_DIR / "oauth-client-secret"
    assert mod.WORKSPACE_ID == "93bfb3d6-93f1-48a8-9720-aa653cba4335"
    assert mod.TEAM_ID == "26b5bb87-2482-4f8f-a42f-955250bd9eaf"
    assert mod.TEAM_KEY == "MAS"
    assert mod.APP_NAME == "Mastermind Portfolio Projector"
    assert mod.CONFIG_SCHEMA == "mastermind.linear_projector_host.v1"

    joined = "\n".join(
        map(str, (mod.ROOT, mod.CONFIG_DIR, mod.CONFIG_PATH, mod.SECRET_PATH))
    )
    assert "MastermindExecutive" not in joined
    assert "multilogin" not in joined.lower()


def test_cli_surface_is_closed_to_fixed_prepare_enroll_verify_commands() -> None:
    mod = _load()
    parser = mod.build_parser()

    assert parser.parse_args(["prepare"]).command == "prepare"
    assert parser.parse_args(["enroll", "--client-id", "abc123"]).client_id == "abc123"
    assert (
        parser.parse_args(["verify", "--expected-client-id", "abc123"]).expected_client_id
        == "abc123"
    )

    with pytest.raises(mod.ProjectorHostError) as exc:
        parser.parse_args(["enroll", "--path", "/tmp/x", "--client-id", "abc123"])
    assert exc.value.code == "PROJECTOR_HOST_ARGUMENTS_REFUSED"

    with pytest.raises(mod.ProjectorHostError) as exc:
        parser.parse_args(["rotate", "--client-id", "abc123"])
    assert exc.value.code == "PROJECTOR_HOST_ARGUMENTS_REFUSED"


def test_secret_shaped_argv_or_environment_refuses_opaquely() -> None:
    mod = _load()

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.assert_secret_surfaces_clean(
            argv=["enroll", "--client-id", "abc123", "lin_api_example_secret"],
            environ={},
        )
    assert exc.value.code == "PROJECTOR_HOST_SECRET_SURFACE_REFUSED"
    assert "lin_api_example_secret" not in str(exc.value)

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.assert_secret_surfaces_clean(
            argv=["enroll", "--client-id", "abc123"],
            environ={"LINEAR_CLIENT_SECRET": "not-for-output"},
        )
    assert exc.value.code == "PROJECTOR_HOST_SECRET_SURFACE_REFUSED"
    assert "not-for-output" not in str(exc.value)
