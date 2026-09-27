"""Real local process death/concurrency over RuntimeStore, synthetic HTTP only."""
from __future__ import annotations
import json
from pathlib import Path
import selectors
import subprocess
import sys
import pytest
from test_github_read_installation_identity import Owner, durable_fence

_CHILD = r'''
import asyncio, dataclasses, json, os, sys
from pathlib import Path
from control_plane.executive_runtime import RuntimeStore
from integrations.mastermind_github_app.read_installation_identity import InstallationCredentialError
from integrations.mastermind_github_app.read_issuance_runtime import CredentialIssuanceAdmission, RuntimeReadIssuanceFence, binding_fingerprint
from test_github_read_installation_identity import Owner, provider
root, log, phase, generation = sys.argv[1:]
owner = Owner()
owner.binding = dataclasses.replace(owner.binding, generation=generation)
store = RuntimeStore(root=root, create=False, existing_writable=True, clock=lambda: owner.now * 1000)
expected_runtime = store._database_file_identity
def admission(binding):
    return CredentialIssuanceAdmission(expected_runtime, binding_fingerprint(binding), "a" * 64, "b" * 64, binding.expires_at * 1000)
fence = RuntimeReadIssuanceFence(store=store, authorize=admission)
owner._issuance_fence = fence
original_request = owner.request
if phase == "crash-after-claim":
    original_claim = fence.claim
    def claim(binding):
        original_claim(binding)
        os._exit(71)
    fence.claim = claim
async def request(**kwargs):
    if kwargs["method"] == "POST":
        with open(log, "a") as stream:
            stream.write("POST\n")
            stream.flush()
            os.fsync(stream.fileno())
        if phase == "crash-after-post":
            os._exit(72)
    result = await original_request(**kwargs)
    if phase == "race" and kwargs["method"] == "GET":
        print("READY", flush=True)
        assert await asyncio.to_thread(sys.stdin.readline) == "go\n"
    return result
owner.request = request
try:
    asyncio.run(provider(owner).installation_token())
    output = {"returned": True, "signs": owner.signs}
except InstallationCredentialError as error:
    output = {"returned": False, "code": error.code, "possible": error.issuance_possible, "signs": owner.signs}
print(json.dumps(output), flush=True)
'''


def _command(root, log, phase, generation="credential:review-one"):
    # Only temporary paths and non-secret synthetic fixture labels enter argv.
    return [sys.executable, "-B", "-c", _CHILD, str(root), str(log), phase, generation]


def _environment():
    import os
    return {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent) + os.pathsep + str(Path.cwd()),
        "PYTHONDONTWRITEBYTECODE": "1"}


@pytest.mark.parametrize("phase,code,posts", [("crash-after-claim", 71, 0), ("crash-after-post", 72, 1)])
def test_hard_process_exit_preserves_original_issuance_fence(tmp_path, phase, code, posts):
    root, log = tmp_path / "runtime", tmp_path / "synthetic-posts.log"
    durable_fence(Owner(), root)  # Test setup only; children open existing schema.
    first = subprocess.run(_command(root, log, phase), env=_environment(), text=True,
        capture_output=True, timeout=25)
    assert first.returncode == code, first.stderr
    for generation in ("credential:review-one", "credential:replacement"):
        second = subprocess.run(_command(root, log, "read-recovery", generation), env=_environment(),
            text=True, capture_output=True, timeout=25)
        assert second.returncode == 0, second.stderr
        result = json.loads(second.stdout)
        assert result == {"returned": False, "code": "ISSUANCE_RECONCILIATION_REQUIRED", "possible": True, "signs": 0}
    assert (log.read_text().count("POST\n") if log.exists() else 0) == posts


def test_two_native_processes_cross_preflight_but_only_one_issues(tmp_path):
    root, log = tmp_path / "runtime", tmp_path / "synthetic-posts.log"
    durable_fence(Owner(), root)
    children = []
    try:
        for _ in range(2):
            children.append(subprocess.Popen(_command(root, log, "race"), env=_environment(),
                text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for child in children:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=20), "native fixture did not reach its bounded preflight barrier"
            assert child.stdout.readline().strip() == "READY"
        # Both observed an empty slot. Only the atomic Event claim can serialize them.
        for child in children:
            child.stdin.write("go\n")
            child.stdin.flush()
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=25)
            assert child.returncode == 0, stderr
            results.append(json.loads(stdout))
        assert sum(r["returned"] for r in results) == 1
        assert [r["code"] for r in results if not r["returned"]] == ["ISSUANCE_RECONCILIATION_REQUIRED"]
        assert log.read_text() == "POST\n"
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.communicate(timeout=5)
