"""Hermetic metadata tests of the real release-origin ancestry qualifier.

The fixture describes filesystem DATA only, never installed Root authority.
Every ancestor is supplied explicitly; no live filesystem read is permitted.
"""
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from ops.executive_os import autonomy_control as control


ADMIN = Path("/Library/Application Support")
RELEASE = ADMIN / "MastermindExecutive/releases" / ("a" * 40)
ANCESTORS = (RELEASE, *RELEASE.parents)


def _walk(monkeypatch, *, changes=None, acl_paths=()):
    metadata = {
        path: {"st_mode": stat.S_IFDIR | 0o755, "st_uid": 0, "st_gid": 0}
        for path in ANCESTORS
    }
    for path, fields in (changes or {}).items():
        metadata[path].update(fields)
    visited = []
    acl_checked = []

    def lstat(path):
        assert path in metadata, "unexpected path must not reach the filesystem"
        visited.append(path)
        return SimpleNamespace(**metadata[path])

    def has_acl(path):
        acl_checked.append(path)
        return path in acl_paths

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", lstat)
        patch.setattr(control, "_has_acl", has_acl)
        control.ProductionGatewayPublicationHost._sealed_origin_chain(RELEASE)
    return visited, acl_checked


@pytest.mark.parametrize("admin_gid", [0, 80])
def test_normal_and_exact_installer_admin_ancestor_walk_to_root(monkeypatch, admin_gid):
    visited, acl_checked = _walk(monkeypatch, changes={ADMIN: {"st_gid": admin_gid}})
    assert visited == list(ANCESTORS)
    assert acl_checked == list(ANCESTORS)


@pytest.mark.parametrize("path,fields", [
    (Path("/Library"), {"st_gid": 80}),
    (ADMIN / "MastermindExecutive", {"st_gid": 80}),
    (RELEASE, {"st_gid": 80}),
    (ADMIN, {"st_gid": 81}),
    (ADMIN, {"st_gid": 80, "st_mode": stat.S_IFDIR | 0o700}),
    (ADMIN, {"st_gid": 80, "st_mode": stat.S_IFDIR | 0o775}),
    (ADMIN, {"st_gid": 80, "st_mode": stat.S_IFDIR | 0o1755}),
    (ADMIN, {"st_gid": 80, "st_uid": 501}),
    (ADMIN, {"st_gid": 80, "st_mode": stat.S_IFLNK | 0o755}),
    (ADMIN, {"st_gid": 80, "st_mode": stat.S_IFREG | 0o755}),
    (Path("/"), {"st_gid": 80}),
    (Path("/Library"), {"st_mode": stat.S_IFDIR | 0o777}),
])
def test_exception_never_relaxes_other_custody_checks(monkeypatch, path, fields):
    changes = {ADMIN: {"st_gid": 80}}
    changes.setdefault(path, {}).update(fields)
    with pytest.raises(control.GatewayPublicationError) as error:
        _walk(monkeypatch, changes=changes)
    assert error.value.code == "gateway_target_invalid"


@pytest.mark.parametrize("path", [ADMIN, Path("/Library"), Path("/")])
def test_acl_refuses_at_and_above_exact_exception(monkeypatch, path):
    with pytest.raises(control.GatewayPublicationError) as error:
        _walk(monkeypatch, changes={ADMIN: {"st_gid": 80}}, acl_paths={path})
    assert error.value.code == "gateway_target_invalid"


def test_gid_zero_incumbent_nonwritable_mode_stays_unchanged(monkeypatch):
    visited, _ = _walk(monkeypatch, changes={ADMIN: {"st_mode": stat.S_IFDIR | 0o700}})
    assert visited == list(ANCESTORS)
