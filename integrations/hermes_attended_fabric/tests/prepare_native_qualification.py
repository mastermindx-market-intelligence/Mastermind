"""Prepare an explicit private native-PM home for offline Hermes qualification.

This calls the existing PM with its declared MCP feature. It never bootstraps a
Hermes agent, publishes launchers, configures a provider, or fabricates PM facts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--fixture-home", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path,
                        help="optional existing native PM tool store")
    args = parser.parse_args()
    source = args.native_source.resolve(strict=True)
    home = args.fixture_home.absolute()
    home.mkdir()  # exclusive: reconcile a prior preparation before retrying
    (home / "config.yaml").write_text('{"plugins":{"enabled":[]}}\n')
    os.environ.update(
        HERMES_HOME=str(home), HERMES_MANAGED_DIR=str(home / "absent-managed"),
        HERMES_CONFIG_BACKEND="file", PYTHONDONTWRITEBYTECODE="1")
    if args.runtime_dir is not None:
        os.environ["HERMES_RUNTIME_DIR"] = str(args.runtime_dir.resolve(strict=True))
    sys.path.insert(0, str(source))
    from pm.client import sync_venv
    from pm.plugin_inputs import Members
    from pm.environments import committed_venv, runtime_facts_path
    sync_venv(["mcp"], explicit=True, plugins=Members([]), project_root=source)
    environment = committed_venv(source)
    if environment is None:
        raise RuntimeError("native PM did not commit a dependency selection")
    marker = {"schema": "hermes.observational_fixture.v1", "native_source": str(source)}
    with (home / ".observational-qualification-home.json").open("x") as stream:
        json.dump(marker, stream, sort_keys=True)
    print(json.dumps({
        "fixture_home": str(home.resolve()), "native_source": str(source),
        "dependency_environment": str(environment), "native_feature": "mcp",
        "dependency_facts_sha256": hashlib.sha256(runtime_facts_path(source).read_bytes()).hexdigest(),
        "native_pm_selection_real": True, "live_installation": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
