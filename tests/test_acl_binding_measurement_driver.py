"""The evidence driver requires an explicitly selected unprivileged identity."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


DRIVER = (Path(__file__).parents[1] / "docs/evidence/2026-11-03-acl-binding-reuse"
          / "measure-native.py")


@pytest.fixture
def driver(monkeypatch):
    spec = importlib.util.spec_from_file_location("acl_binding_measurement_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(module, "platform", SimpleNamespace(python_version=lambda: "3.12.10"))
    # Loading source and creating a fixture must remain beyond identity admission.
    module.load = Mock(side_effect=RuntimeError("source loading reached"))
    module.tempfile = SimpleNamespace(TemporaryDirectory=Mock())
    return module


def test_measurement_requires_explicit_uid_before_loading_source(driver, monkeypatch):
    monkeypatch.setattr("sys.argv", [str(DRIVER)])
    with pytest.raises(SystemExit) as error:
        driver.main()
    assert error.value.code == 2
    driver.load.assert_not_called()
    driver.tempfile.TemporaryDirectory.assert_not_called()


@pytest.mark.parametrize("expected,real,effective", [
    (0, 0, 0),
    (-1, -1, -1),
    (1234, 1235, 1234),
    (1234, 1234, 1235),
])
def test_measurement_refuses_root_and_mismatched_uids(
    driver, monkeypatch, expected, real, effective,
):
    monkeypatch.setattr("sys.argv", [str(DRIVER), "--expected-uid", str(expected)])
    driver.os = SimpleNamespace(getuid=lambda: real, geteuid=lambda: effective)
    with pytest.raises(AssertionError):
        driver.main()
    driver.load.assert_not_called()
    driver.tempfile.TemporaryDirectory.assert_not_called()


def test_measurement_matching_explicit_uid_reaches_source_validation(driver, monkeypatch):
    monkeypatch.setattr("sys.argv", [str(DRIVER), "--expected-uid", "1234"])
    driver.os = SimpleNamespace(getuid=lambda: 1234, geteuid=lambda: 1234)
    with pytest.raises(RuntimeError, match="source loading reached"):
        driver.main()
    driver.load.assert_called_once_with("baseline", driver.BASELINE)
    driver.tempfile.TemporaryDirectory.assert_not_called()
