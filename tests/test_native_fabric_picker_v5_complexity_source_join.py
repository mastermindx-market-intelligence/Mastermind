"""Verify V5 nonblocking quota and native complexity patches share one picker.

Use exact immutable repository source blobs and native git apply in temp dirs.
This is archived #1512 Qwen picker source, not a current installed M2 read.
No quota, credentials, network, host, live broker, account or worker is touched.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
QWEN_PICKER = (ROOT / "research/fabric_bailian_host_eligibility_20261015"
               / "candidate/pick.py")
AUDIT_PATCH = ROOT / "ops/native_fabric/routing_audit_20261013/complexity_invariants.patch"
V5_PATCH = ROOT / "tests/fixtures/native_fabric_protected_20261014/pick_quota_cacheonly_v5_section.patch"

BLOBS = {
    "source": "75437a62ccf716489aaad8ed293e56dacad04dac",
    "complexity": "2f473ee0727a2b53a3ebaf912bb7f08b226473aa",
    "V5": "554941d686ce8415992aba4d7e71c9f23aca61f5",
}


def _blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _apply(directory: Path, patch: Path) -> None:
    command = ["git", "apply", "--include=ext/pick.py", str(patch)]
    # The V5 patch also contains quota, ledger and unrelated tests. Never
    # promote those source files to this exact picker-only verification.
    for preflight in (True, False):
        args = command[:2] + (["--check"] if preflight else []) + command[2:]
        result = subprocess.run(
            args, cwd=directory, check=False, capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"{patch.relative_to(ROOT)}: git apply "
            f"{'--check ' if preflight else ''}refused: {result.stderr[:900]}"
        )


def _stage(tmp_path: Path, name: str, order: tuple[Path, Path]) -> bytes:
    folder = tmp_path / name
    (folder / "ext").mkdir(parents=True)
    target = folder / "ext/pick.py"
    target.write_bytes(QWEN_PICKER.read_bytes())
    for patch in order:
        _apply(folder, patch)
    # Complete source is one file, no extra publication/installer was created.
    assert sorted(x.name for x in (folder / "ext").iterdir()) == ["pick.py"]
    return target.read_bytes()


def test_current_published_qwen_picker_v5_and_complexity_source_commute(tmp_path):
    assert _blob(QWEN_PICKER.read_bytes()) == BLOBS["source"]
    assert _blob(AUDIT_PATCH.read_bytes()) == BLOBS["complexity"]
    assert _blob(V5_PATCH.read_bytes()) == BLOBS["V5"]

    first = _stage(tmp_path, "complexity-first", (AUDIT_PATCH, V5_PATCH))
    second = _stage(tmp_path, "quota-first", (V5_PATCH, AUDIT_PATCH))
    assert first == second, (
        "unreviewed picker preimage conflict: preserve both source owners "
        "and do not install/replay either patch"
    )

    source = first.decode("utf-8")
    ast.parse(source)
    assert source.count("frontier_witness_required") == 2
    assert source.count("bounded_complexity_requires_escalation") == 2
    assert 'quota_remote.read_provider("minimax", allow_remote=False)' in source
    assert 'quota_remote.glm_accounts_state(allow_remote=False)' in source
    assert 'quota_remote.read_provider("glm", allow_remote=False)' in source
    assert 'pool_ledger.glm_burn(read_remote=False, write_state=False)' in source
    assert 'if normalized_mode not in {"minimax", "grok"' in source

    # The archived Qwen picker already enforced these GLM-specific branches;
    # the new routing amendment adds a separate cross-provider policy layer.
    assert 'if is_glm_mode and normalized_complexity == "C3_FRONTIER_JUDGMENT":' in source
    assert 'if is_glm_mode and normalized_complexity in BOUNDED_TASK_COMPLEXITIES:' in source

    # Four existing V5 picker hunks plus two original complexity hunks;
    # all original account/host grant authority remains outside this test.
    assert len(source.splitlines()) > 2600


# Frozen *picker-only* slice of the exact #1441 V5 patch; source blob
# d34b6b15bf7ab074d911d3d05128e2cbf1f74100 remains owned by #1441.
# CI must not require an unmerged sibling PR's file tree to run this test.


def test_frozen_v5_picker_section_preserves_source_boundary():
    patch = V5_PATCH.read_text()
    assert patch.startswith("--- a/ext/pick.py\\n+++ b/ext/pick.py\\n".replace("\\n", "\n"))
    assert patch.count("@@ -") == 4
    assert "quota_remote.py" not in patch.splitlines()[0:2]
    assert "b/ext/quota_remote.py" not in patch
    assert "b/ext/pool_ledger.py" not in patch
    assert _blob(V5_PATCH.read_bytes()) == BLOBS["V5"]


def test_historical_picker_does_not_claim_an_installed_V5_source():
    raw = QWEN_PICKER.read_text()
    assert _blob(QWEN_PICKER.read_bytes()) == BLOBS["source"]
    assert raw.count("frontier_witness_required") == 1
    assert raw.count("bounded_complexity_requires_escalation") == 1
    assert 'quota_remote.read_provider("minimax", allow_remote=False)' not in raw
