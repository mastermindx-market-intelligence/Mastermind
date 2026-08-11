"""Filesystem-boundary security invariants for the portfolio registry."""
from pathlib import Path

import pytest

from portfolio import registry


def test_every_registered_id_resolves_from_literal_allowlist(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_ROOT", tmp_path)

    assert registry.data_dir(None) == tmp_path / "data" / "portfolio"
    assert registry.data_dir("flagship") == tmp_path / "data" / "portfolio"
    for portfolio_id in registry.ids():
        assert registry.canonical_id(portfolio_id) == portfolio_id
        path = registry.data_dir(portfolio_id)
        assert path.is_relative_to(tmp_path)
        if portfolio_id != "flagship":
            assert path == tmp_path / "data" / "portfolios" / portfolio_id

    assert registry.data_dir("flagship_judgment") == (
        tmp_path / "data" / "portfolios" / "flagship_judgment"
    )
    with pytest.raises(ValueError, match="unknown portfolio id"):
        registry.canonical_id("flagship_judgment")


@pytest.mark.parametrize(
    "portfolio_id",
    [
        "",
        ".",
        "..",
        "../../etc/passwd",
        "/etc/passwd",
        "autonomous/../../escape",
        "autonomous\\..\\escape",
        " autonomous",
        "autonomous ",
        "AUTONOMOUS",
        "unknown",
        Path("autonomous"),
        b"autonomous",
        0,
    ],
)
def test_unknown_or_path_like_ids_fail_closed(monkeypatch, tmp_path, portfolio_id):
    monkeypatch.setattr(registry, "_ROOT", tmp_path)

    with pytest.raises(ValueError, match="unknown portfolio id"):
        registry.canonical_id(portfolio_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown portfolio id"):
        registry.data_dir(portfolio_id)  # type: ignore[arg-type]

    assert not (tmp_path / "data").exists()
