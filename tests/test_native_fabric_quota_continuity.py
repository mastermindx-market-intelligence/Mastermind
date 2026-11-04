"""Run the native recovery qualification through the canonical repository gate.

The native source is not a setuptools package. Separate processes also preserve
the suite's real module identities and isolate its fixture broker environment
from unrelated repository tests.
"""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"


def _qualify(directory, *, timeout_seconds=240):
    from scripts.native_unittest_diagnostics import NativeInvocation,bind_facts,run_native
    invocation=NativeInvocation(directory)
    result,facts=run_native(directory,timeout_seconds=timeout_seconds,root=ROOT,cwd=NATIVE,invocation=invocation)
    if result.returncode != 0 and facts is not None:
        error=AssertionError(result.stdout+result.stderr)
        case='test_native_quota_continuity_owners' if directory=='tests' else 'test_native_generation_and_ingress_rollout'
        bind_facts(error,facts,invocation,'tests/test_native_fabric_quota_continuity.py::'+case)
        raise error
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ran 0 tests" not in result.stderr, "Native qualification discovered no tests"


def test_native_quota_continuity_owners():
    _qualify("tests", timeout_seconds=300)


def test_native_generation_and_ingress_rollout():
    _qualify("rollout")
