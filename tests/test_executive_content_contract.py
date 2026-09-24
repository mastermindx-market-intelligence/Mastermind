"""The integration import remains a same-object view of the shared contract."""
import importlib


def test_integration_contract_reexports_shared_objects():
    shared = importlib.import_module("common.executive_content_contract")
    compatibility = importlib.import_module("integrations.executive_content_contract")
    for name, value in vars(shared).items():
        if not name.startswith("__"):
            assert getattr(compatibility, name) is value, name


def test_profiles_cross_the_compatibility_boundary_without_type_conversion():
    shared = importlib.import_module("common.executive_content_contract")
    compatibility = importlib.import_module("integrations.executive_content_contract")
    profiles = compatibility.ContentObserverProfiles(
        web=compatibility.ProfileSlot(False, None),
        mac=shared.ProfileSlot(False, None),
    )
    parsed = shared.load_content_profiles(profiles)
    assert type(parsed) is compatibility.ContentObserverProfiles
    assert parsed.to_mapping() == profiles.to_mapping()
    assert compatibility.canonical(parsed.to_mapping()) == shared.canonical(profiles.to_mapping())


def test_workspace_contract_reexports_private_and_public_shared_objects():
    shared = importlib.import_module("common.executive_workspace_contract")
    compatibility = importlib.import_module("integrations.mastermind_workspace_app.contract")
    for name, value in vars(shared).items():
        if not name.startswith("__"):
            assert getattr(compatibility, name) is value, name
    # Authentication remains an integration responsibility.
    for name in ("principal_frame", "validate_workspace_bindings", "workspace_authorizers"):
        assert not hasattr(shared, name)
        assert getattr(compatibility, name).__module__ == compatibility.__name__
