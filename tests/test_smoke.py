"""Phase 0 acceptance test — the live regime recompute matches the published one."""
import json
from pathlib import Path

import pytest

import bot  # noqa: F401  -> vendor/macro bootstrap


def test_engine_imports_and_reproduces_regime():
    from lib import config
    from engine import inputs, regime

    config_yml = Path(config.__file__).resolve().parent.parent / "config.yml"
    if not config_yml.is_file():
        pytest.skip("vendored Macro config.yml absent — hosted CI sparse checkout")
    data_dir = Path(config.data_dir())
    latest_path = data_dir / "regime" / "latest.json"
    if not latest_path.exists():
        pytest.skip("vendored data/regime/latest.json absent — hosted CI sparse checkout")
    latest = json.loads(latest_path.read_text())

    cls = regime.classify(inputs.build_features())
    live_quad = str(cls.iloc[-1]["quad"])

    assert live_quad == latest["quad"], (
        f"live recompute {live_quad} != published {latest['quad']}"
    )
