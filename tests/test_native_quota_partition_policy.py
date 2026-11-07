"""The native split must preserve every normal owner module exactly once."""
import ast
from pathlib import Path

import pytest

from scripts import native_unittest_diagnostics as native

ROOT = Path(__file__).resolve().parents[1]


def test_current_native_owner_inventory_has_a_total_disjoint_partition():
    inventory = native.owner_inventory(ROOT / "ops/native_fabric/quota_continuity/tests")
    groups = native.verify_owner_partitions(inventory, native.OWNER_SELECTIONS)
    assert len(groups) == 3
    assert {name for group in groups for name in group} == set(inventory)
    assert len(inventory) == sum(len(group) for group in groups)
    assert "test_commission_deadline.py" in groups[0]
    assert "test_macro_result_controller.py" in groups[1]
    assert "test_plain_transport_owner.py" in groups[2]


@pytest.mark.parametrize("unexpected", ["test_7future.py", "test_Future.py", "test__future.py"])
def test_future_uncovered_filename_fails_instead_of_silently_disappearing(unexpected):
    with pytest.raises(AssertionError, match="exactly once"):
        native.verify_owner_partitions(
            ("test_alpha.py", "test_leaf.py", "test_zulu.py", unexpected), native.OWNER_SELECTIONS)


@pytest.mark.parametrize("selections", [
    native.OWNER_SELECTIONS[:2],
    (native.OWNER_SELECTIONS[0], native.OWNER_SELECTIONS[0], *native.OWNER_SELECTIONS[1:]),
    (("tests", "test_*.py"), *native.OWNER_SELECTIONS),
])
def test_dropped_or_duplicate_partition_refuses(selections):
    with pytest.raises(AssertionError, match="exactly once"):
        native.verify_owner_partitions(("test_alpha.py", "test_leaf.py", "test_zulu.py"), selections)


def test_empty_partition_refuses():
    with pytest.raises(AssertionError, match="each discover"):
        native.verify_owner_partitions(("test_alpha.py", "test_leaf.py"), native.OWNER_SELECTIONS)


def test_package_inventory_matches_normal_discovery_and_ignores_nonpackages(tmp_path):
    (tmp_path / "test_alpha.py").write_text("import unittest\n")
    package = tmp_path / "nested";package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "test_leaf.py").write_text("import unittest\n")
    fixtures = tmp_path / "fixtures";fixtures.mkdir()
    (fixtures / "test_unused.py").write_text("raise RuntimeError('not a test package')\n")
    assert native.owner_inventory(tmp_path) == ("nested/test_leaf.py", "test_alpha.py")


def test_source_symlink_cannot_enter_native_partition(tmp_path):
    source = tmp_path / "source.py";source.write_text("")
    (tmp_path / "test_alpha.py").symlink_to(source)
    with pytest.raises(AssertionError, match="regular file"):
        native.owner_inventory(tmp_path)


def test_repository_collects_each_closed_wrapper_once_without_old_monolith():
    found = []
    paths = {node.split("::")[0] for node in native.WRAPPER_SELECTIONS}
    for path in paths:
        module = ast.parse((ROOT / path).read_text())
        found.extend(path + "::" + item.name for item in module.body
            if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"))
    assert all(found.count(node)==1 for node in native.WRAPPER_SELECTIONS)
    owner_wrappers=[node for node in found if node.split('::')[0].startswith('tests/test_native_fabric_quota_continuity')]
    assert sorted(owner_wrappers)==sorted(node for node in native.WRAPPER_SELECTIONS
        if node.split('::')[0].startswith('tests/test_native_fabric_quota_continuity'))
    assert "tests/test_native_fabric_quota_continuity.py::test_native_quota_continuity_owners" not in found
