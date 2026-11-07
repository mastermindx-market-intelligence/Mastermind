"""Bounded read-only native enrollment/evidence check for the existing facade."""
from __future__ import annotations

import importlib
import importlib.util
import json
import site
import sys
from pathlib import Path


def main() -> int:
    try:
        if len(sys.argv) != 5:
            raise ValueError()
        source, home = (Path(value) for value in sys.argv[1:3])
        revision, package_sha256 = sys.argv[3:5]
        installed = home.resolve() / "plugins" / "mastermind-fabric-worker"
        if (not source.is_absolute() or not home.is_absolute()
                or not source.is_dir() or not home.is_dir()
                or installed.is_symlink() or installed.parent.is_symlink()
                or Path(__file__).resolve().parent != installed):
            raise ValueError()
        # Read the already committed dependency selection; do not invoke
        # native bootstrap, recovery, install, reload or provider resolution.
        sys.path.insert(0, str(source))
        from pm.environments import committed_venv, site_packages
        environment = committed_venv(source)
        if environment is None:
            raise ValueError()
        site.addsitedir(str(site_packages(environment)))
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        # Native subdirectory installs do not contain a repository-level
        # integrations package. Load only this fixed installed package, without
        # invoking its register() entry point or ambient package discovery.
        name = "_mmx_attended_fabric_evidence"
        spec = importlib.util.spec_from_file_location(
            name, installed / "__init__.py",
            submodule_search_locations=[str(installed)])
        if spec is None or spec.loader is None:
            raise ValueError()
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        spec.loader.exec_module(package)
        evidence = importlib.import_module(name + ".native_evidence")
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        request = json.loads(raw)
        if type(request) is not dict or set(request) != {"action", "arguments"}:
            raise ValueError()
        token = set_hermes_home_override(str(home))
        try:
            contract = evidence.read_enrollment(home)
            if (contract["source_revision"] != revision
                    or contract["package_sha256"] != package_sha256):
                raise ValueError()
            if request["action"] != "fabric_capabilities":
                evidence.verify_origin(home, request["action"], request["arguments"], contract)
            # Profile, package and native source pin also govern result release.
            if evidence.read_enrollment(home) != contract:
                raise ValueError()
        finally:
            reset_hermes_home_override(token)
        print(json.dumps({"schema": "mastermind.hermes_origin_check.v1",
                          "authorized": True, "contract": contract},
                         separators=(",", ":")))
        return 0
    except Exception:
        # No exception text, file paths, packets, history, tokens or stderr.
        print('{"schema":"mastermind.hermes_origin_check.v1","authorized":false}')
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
