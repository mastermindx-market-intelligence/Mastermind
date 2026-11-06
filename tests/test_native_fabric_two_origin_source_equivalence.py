"""Prove two exact published Fabric Broker starting points compose to one candidate.

Uses frozen repository source artifacts and git apply in disposable directories.
The #1512 source is an archived installed-generation *receipt*, never a read of
current M2 installed files. This test makes no broker DB, account, provider,
network, credential, host, lease or runtime change.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "ops/native_fabric/routing_audit_20261013"
FIXTURES = ROOT / "tests/fixtures/native_fabric_protected_20261014"
INSTALLED_RECEIPT_SOURCE = (
    ROOT / "research/fabric_bailian_host_eligibility_20261015"
    / "candidate/lease_broker.py"
)
FROZEN_HISTORIC = FIXTURES / "lease_broker.py.txt"

# Git blobs, not hashes guessed from filenames. If either input changes, the
# correspondence to the actual historic release stops being established.
SOURCE_BLOBS = {
    "historic": "855495a15615787c3c80f9045e6637839ee47384",
    "qwen-installed-receipt": "3c0ae231ad4c3c5cd041661b94140834a8c573ce",
}

# Each patch is applied precisely once.  The installed Qwen source already
# contains #1469's cached GLM quota admission and #1512's Qwen host join.
STAGES = (
    ("native", FIXTURES / "native_admission.patch", True),
    ("expiry", FIXTURES / "glm_expiry.patch", False),
    ("priority", BUNDLE / "protected_composition/logical_priority_after_native.patch", False),
    ("queue", BUNDLE / "queue_priority/queue_priority_isolation.patch", False),
    ("waiter", BUNDLE / "request_waiters/request_waiters.patch", False),
    ("wiring", BUNDLE / "request_waiters/request_waiters_wiring.patch", False),
    ("balance", BUNDLE / "account_balance/normalized_account_balance.patch", False),
    ("quota", FIXTURES / "glm_quota_admission.patch", True),
    ("pin", BUNDLE / "pinned_waiters/pinned_account_eligibility.patch", False),
    ("reclaim", BUNDLE / "pinned_waiters/pinned_account_reclaim.patch", False),
    ("park", BUNDLE / "pinned_waiters/pinned_quota_waiter.patch", False),
    ("memo", BUNDLE / "pinned_waiters/pinned_ready_memo.patch", False),
    ("model", BUNDLE / "model_waiters/model_aware_waiters.patch", False),
    ("qwen", BUNDLE / "qwen_compat/qwen_host_after_model_waiters.patch", False),
)


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _apply(stage: Path, patch: Path, *, directory: bool) -> None:
    assert patch.is_file(), f"missing exact-source patch: {patch}"
    # Some routing patches also amend the shell launcher; this test isolates
    # the Broker source union without mutating or requiring that second file.
    arguments = ["git", "apply", "--include=ext/lease_broker.py"]
    if directory:
        arguments.append("--directory=ext")
    arguments.append(str(patch))
    result = subprocess.run(arguments, cwd=stage, text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0, (
        f"{patch.relative_to(ROOT)}: git apply rc={result.returncode}; "
        f"stderr={result.stderr[:1000]}"
    )


def _compose(tmp_path: Path, name: str, source_file: Path) -> tuple[bytes, tuple[str, ...]]:
    data = source_file.read_bytes()
    assert _git_blob(data) == SOURCE_BLOBS[name], (
        f"{name}: source changed, original installed/baseline witness invalid"
    )
    stage = tmp_path / name
    (stage / "ext").mkdir(parents=True)
    dest = stage / "ext/lease_broker.py"
    dest.write_bytes(data)
    applied: list[str] = []
    for label, patch, directory in STAGES:
        if name == "qwen-installed-receipt" and label in ("quota", "qwen"):
            continue
        _apply(stage, patch, directory=directory)
        applied.append(label)
    return dest.read_bytes(), tuple(applied)


def test_two_published_installed_and_historical_broker_sources_join_identically(tmp_path):
    historical, h_stages = _compose(tmp_path, "historic", FROZEN_HISTORIC)
    installed, i_stages = _compose(tmp_path, "qwen-installed-receipt", INSTALLED_RECEIPT_SOURCE)
    assert len(h_stages) == 14 and len(i_stages) == 12
    assert set(h_stages) - set(i_stages) == {"quota", "qwen"}
    assert historical == installed, (
        "source-only broker union differs by input version; release requires "
        "exact incumbent source/installer reconciliation"
    )
    assert hashlib.sha256(historical).hexdigest() == (
        "59fb2ab4179f3337f54d1796334f7491d038306b8162969407f77a8970408e51"
    )
    text = historical.decode("utf-8")
    parsed = ast.parse(text)
    broker = next(node for node in parsed.body
                  if isinstance(node, ast.ClassDef) and node.name == "Broker")
    acquire = next(node for node in broker.body
                   if isinstance(node, ast.FunctionDef) and node.name == "_try_acquire")
    assert "native_binding" in {arg.arg for arg in acquire.args.args}
    assert "_waiter_pinned_model_full" in text
    assert "_waiter_pinned_quota_parked" in text
    assert "_request_waiter_id" in text
    assert "native_binding" in text
    assert 'ALTER TABLE waiters ADD COLUMN model TEXT NOT NULL DEFAULT' in text
    assert 'mode="glm" if pool == "glm" else "qwen"' in text


def test_declared_qwen_and_quota_changes_not_reapplied_to_installed_source():
    # Version guard for future refactors: one patch for a change already in the
    # installed-source receipt is a release error, not an idempotent operation.
    text = INSTALLED_RECEIPT_SOURCE.read_text()
    assert text.count("from quota_remote import cached_glm_account_parked") == 1
    assert text.count('mode="glm" if pool == "glm" else "qwen"') == 1
    assert 'def _waiter_pinned_model_full' not in text
