"""Run real native owner tests within an already prepared, marked private PM home."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--fixture-home", type=Path, required=True)
    args = parser.parse_args()
    source, home = args.native_source.resolve(), args.fixture_home.resolve()
    marker = json.loads((home / ".observational-qualification-home.json").read_text())
    if marker != {"schema": "hermes.observational_fixture.v1", "native_source": str(source)}:
        raise ValueError("explicit fixture ownership is required")
    (home / "profiles").mkdir(exist_ok=True)
    os.environ.update(
        HERMES_HOME=str(home), HERMES_MANAGED_DIR=str(home / "absent-managed"),
        HERMES_CONFIG_BACKEND="file", HERMES_DISABLE_LAZY_INSTALLS="1",
        MMX_HERMES_QUALIFICATION_HOME=str(home), PYTHONDONTWRITEBYTECODE="1")
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(source))
    sys.path.insert(1, str(repo))
    from pm import environments
    environment = environments.committed_venv(source)
    if environment is None or Path(sys.prefix).resolve() != environment.resolve():
        raise ValueError("use the real native-PM-committed fixture interpreter")
    from hermes_cli import _early_recovery, venv_sync
    blocked = []
    def audit(event, arguments):
        if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo"}:
            blocked.append(event)
            raise RuntimeError("native owner qualification cannot contact a provider")
    sys.addaudithook(audit)
    # Explicit qualification-only fences. Actual native agents, plugins,
    # SessionDB, middleware and the cold enrollment checker remain unchanged.
    with ExitStack() as stack:
        for owner, member in (
            (venv_sync, "prepare_launch"), (_early_recovery, "restore_interrupted_pull"),
            (_early_recovery, "recover_if_needed"), (environments, "activate_dependencies"),
        ):
            stack.enter_context(mock.patch.object(owner, member, return_value=None))
        path = Path(__file__).with_name("native_owner_qualification.py")
        spec = importlib.util.spec_from_file_location("_mmx_native_owner_qualification", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        import run_agent
        if Path(run_agent.__file__).resolve() != source / "run_agent.py":
            raise AssertionError("native source attribution mismatch")
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {
        "schema": "mastermind.hermes_native_owner_qualification.v1",
        "native_source": str(source), "fixture_home": str(home),
        "dependency_environment": str(environment), "native_pm_selection_real": True,
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skips": len(result.skipped), "network_attempts": blocked,
        "bootstrap_recovery_and_activation_fenced_in_harness": True,
        "execution_engine_fixture": True, "live_worker_start": False,
    }
    print(json.dumps(receipt, sort_keys=True))
    return 0 if result.wasSuccessful() and not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
