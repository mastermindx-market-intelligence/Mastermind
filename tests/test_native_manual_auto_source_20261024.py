"""F1: real native preview/request AUTO contract from SHA-sealed source only.

No real provider, host, token, lease, state directory, live process, or release
selection is accessed. Source is recreated in a disposable isolated review stage.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
PATCH = ROOT / "ops/native_fabric/patches/native_generation_manual_preview_20261022.patch"
FIXTURE = ROOT / "ops/native_fabric/qualification/native_manual_preview_fixture.py"
SOURCE = {
    "ext/fabric_task.py": ("fabric_task.py", "3ceba9777a475fb1cfc568f13035b4c23ae15c7bd54316c4cb006335557a545b"),
    "ext/pick.py": ("pick.py", "a3c3a9822779e244f4140dc1223c4a2617243ed35c12c0358527d637fc1fc1ee"),
    "pool": ("pool_launcher.sh", "4026eb128fe803e575151bbeec49a4d8f5838408db1177feedd64ad24f4f2059"),
}
AFTER = {
    "ext/fabric_task.py": "48699864fdc9e96d12f51ff22fef74bd438a2fcd500f25c836e6fab2dea728d7",
    "ext/pick.py": "9bbb96c8da84e38bbd802fdd373a0e8ba386395abc5a80bc8628b49d5afd8174",
    "pool": "12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679",
}
COMPOSED_PICK = "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b"


def _inverse_manual_member(value: bytes, member: str) -> bytes:
    """Undo only SHA-bound reviewed F1 hunks in disposable source bytes."""
    blob = PATCH.read_bytes()
    heading = ("diff --git a/" + member + " b/" + member + "\n").encode()
    assert blob.count(heading) == 1
    section = blob.split(heading, 1)[1].split(b"\ndiff --git ", 1)[0]
    groups = []
    group = None
    for line in section.splitlines(keepends=True):
        if line.startswith(b"@@ "):
            group = []
            groups.append(group)
        elif group is not None and line[:1] in (b" ", b"+", b"-"):
            group.append(line)
    assert groups
    for group in reversed(groups):
        newer = b"".join(x[1:] for x in group if x[:1] in (b" ", b"+"))
        older = b"".join(x[1:] for x in group if x[:1] in (b" ", b"-"))
        assert value.count(newer) == 1
        value = value.replace(newer, older, 1)
    return value


def _inverse_judgment(value: bytes) -> bytes:
    """Preserve R28 review routing in release while testing its pre-F1 base."""
    pairs = (
        (b'"operator", "reviewer", "review", "adjudicate", "decompose", "audit", "repair",',
         b'"operator", "reviewer", "adjudicate", "decompose", "audit", "repair",'),
        (b'    # Independent review/audit remain judgment even when legacy execute_classes includes them.\n'
         b'    # Preserve explicit-pool gates above; do not score implicit reviewers into Qwen.\n'
         b'    if tc not in {"review", "audit"} and (is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30):\n',
         b'    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:\n'),
    )
    for newer, older in pairs:
        assert value.count(newer) == 1
        value = value.replace(newer, older, 1)
    assert hashlib.sha256(value).hexdigest() == AFTER["ext/pick.py"]
    return value


def sha(path: Path) -> str:
    assert path.is_file() and not path.is_symlink()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_native_auto_pre_effect_source_contract(tmp_path):
    """Reproduce the full native release source's F1 fix without a live install."""
    assert sha(PATCH) == "6b1dade16fe58b732064d66e0645396dd6dd02fc255c3befbf0d03e105b23e6b"
    assert sha(FIXTURE) == "75edb2345e90f2f5a758020acef494aa9090b4c97e020bbafb6f3ee5be63c794"
    builder = NATIVE / "rollout/build_review_stage.py"
    built = tmp_path / "built"
    proc = subprocess.run([sys.executable, str(builder), "--output", str(built)],
                          cwd=ROOT, capture_output=True, text=True, timeout=55)
    assert proc.returncode == 0, proc.stderr[-2500:]
    stage = built / "native-code-stage"
    for relative, (name, original_sha) in SOURCE.items():
        source = NATIVE / "candidate" / name
        # Current 97-member release is ALREADY composed. Do not require
        # its source to match a historical 95-member preimage.
        current = source.read_bytes()
        if relative == "ext/pick.py":
            assert sha(source) == COMPOSED_PICK
            current = _inverse_judgment(current)
        else:
            assert sha(source) == AFTER[relative]
        historical = _inverse_manual_member(current, relative)
        assert hashlib.sha256(historical).hexdigest() == original_sha
        (stage / relative).write_bytes(historical)
    for action in ("--check", None):
        args = ["git", "apply"] + ([action] if action else []) + [str(PATCH)]
        proc = subprocess.run(args, cwd=stage, capture_output=True, text=True, timeout=18)
        assert proc.returncode == 0, proc.stderr[-1800:]
    assert all(sha(stage / name) == digest for name, digest in AFTER.items())
    env = {k: v for k, v in os.environ.items() if not (
        k.startswith(("OPENAI_", "CODEX_", "ANTHROPIC_", "GITHUB_"))
        or k in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
    )}
    env.update(MMX_NATIVE_PREVIEW_CANDIDATE=str(stage), PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=os.pathsep.join((str(stage / "ext"), str(NATIVE / "source"))))
    proc = subprocess.run([sys.executable, str(FIXTURE), "-q"], cwd=stage,
                          env=env, capture_output=True, text=True, timeout=35)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-3800:]
    assert re.search(r"Ran 14 tests", proc.stderr) and "\nOK\n" in proc.stderr
    # The historical F1 regression is preserved; independently verify R28
    # judgment routing stays present in the CURRENT composed native source.
    assert all(sha(stage / name) == digest for name, digest in AFTER.items())
    assert sha(NATIVE / "candidate/pick.py") == COMPOSED_PICK
    assert b'if tc not in {"review", "audit"}' in (
        NATIVE / "candidate/pick.py").read_bytes()
    # Neither stage nor source is published/selected by this test.
