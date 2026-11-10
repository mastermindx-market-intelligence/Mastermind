"""Isolated account ambiguity tests; never launch a Claude GUI or CLI."""

from pathlib import Path

import pytest

from integrations.chairman_surfaces import claude


@pytest.fixture
def mac_platform(monkeypatch):
    monkeypatch.setattr(claude.sys, "platform", "darwin")


def wrapper(root: Path, name: str):
    path = root / (name + ".app")
    path.mkdir()
    return path


def test_other_platform_uses_existing_non_mac_behavior(tmp_path, monkeypatch):
    wrapper(tmp_path, "Claude Default")
    wrapper(tmp_path, "Claude 1")
    monkeypatch.setattr(claude.sys, "platform", "linux")
    assert claude._has_multiple_parall_claude_wrappers(tmp_path) is False


@pytest.mark.parametrize(
    "names,ambiguous",
    [
        ([], False),
        (["Claude"], False),
        (["Claude Default"], False),
        (["Claude 1"], False),
        (["Claude Default", "Claude 1"], True),
        (["Claude", "Claude 1"], True),
        (["Claude Official", "Claude 1"], True),
        (["Claude 1", "Claude 2"], True),
        (["Claude 4 Legacy"], False),
        (["Claude Default", "Claude 4 Legacy"], True),
        (["Claude Default", "Claude 1", "Claude 2"], True),
        (["Claude 1", "ClaudeCode"], False),
    ],
)
def test_distinct_desktop_accounts_only(tmp_path, mac_platform, names, ambiguous):
    for name in names:
        wrapper(tmp_path, name)
    assert claude._has_multiple_parall_claude_wrappers(tmp_path) is ambiguous


def test_default_app_symlink_does_not_duplicate_an_account(tmp_path, mac_platform):
    original = wrapper(tmp_path, "Claude Default")
    (tmp_path / "Claude.app").symlink_to(original, target_is_directory=True)
    assert claude._has_multiple_parall_claude_wrappers(tmp_path) is False
    wrapper(tmp_path, "Claude 6")
    assert claude._has_multiple_parall_claude_wrappers(tmp_path) is True


def test_missing_inventory_fails_closed(tmp_path, mac_platform):
    assert claude._has_multiple_parall_claude_wrappers(tmp_path / "missing") is True


def test_unreadable_inventory_fails_closed(tmp_path, mac_platform, monkeypatch):
    def denied(_path):
        raise PermissionError("access denied")

    monkeypatch.setattr(claude.os, "scandir", denied)
    assert claude._has_multiple_parall_claude_wrappers(tmp_path) is True


def test_invalid_symlink_target_does_not_count_as_second_account(tmp_path, mac_platform):
    wrapper(tmp_path, "Claude 5")
    (tmp_path / "Claude Default.app").symlink_to(
        tmp_path / "missing.app", target_is_directory=True
    )
    assert claude._has_multiple_parall_claude_wrappers(tmp_path) is False



def test_system_plus_user_applications_are_both_scanned(tmp_path, mac_platform):
    system_apps = tmp_path / "system"
    user_apps = tmp_path / "user"
    system_apps.mkdir()
    user_apps.mkdir()
    wrapper(system_apps, "Claude Default")
    wrapper(user_apps, "Claude 1")
    assert claude._has_multiple_parall_claude_wrappers(
        system_apps, user_apps
    ) is True


def test_cross_root_alias_is_one_account(tmp_path, mac_platform):
    system_apps = tmp_path / "system"
    user_apps = tmp_path / "user"
    system_apps.mkdir()
    user_apps.mkdir()
    original = wrapper(system_apps, "Claude Default")
    (user_apps / "Claude.app").symlink_to(
        original, target_is_directory=True
    )
    assert claude._has_multiple_parall_claude_wrappers(
        system_apps, user_apps
    ) is False
    wrapper(user_apps, "Claude 4 Legacy")
    assert claude._has_multiple_parall_claude_wrappers(
        system_apps, user_apps
    ) is True


def test_optional_missing_user_applications_does_not_force_ambiguity(
    tmp_path, mac_platform
):
    system_apps = tmp_path / "system"
    system_apps.mkdir()
    wrapper(system_apps, "Claude 1")
    assert claude._has_multiple_parall_claude_wrappers(
        system_apps, tmp_path / "missing-user"
    ) is False


def test_optional_inaccessible_user_apps_fails_closed(tmp_path, mac_platform, monkeypatch):
    system_apps = tmp_path / "system"
    system_apps.mkdir()
    wrapper(system_apps, "Claude 1")
    real_scandir = claude.os.scandir

    def scoped_scandir(path):
        if path == tmp_path / "denied-user":
            raise PermissionError("access denied")
        return real_scandir(path)

    monkeypatch.setattr(claude.os, "scandir", scoped_scandir)
    assert claude._has_multiple_parall_claude_wrappers(
        system_apps, tmp_path / "denied-user"
    ) is True
