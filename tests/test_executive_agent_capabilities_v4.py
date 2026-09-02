"""RED-first tests for opt-in V4 capability-package support in the registry.

Covers (per the CAP-S1 package-identity amendment and the frozen build
commission):

  (a) source-snapshot independence: the real `plugins/mastermind-operator`
      files are re-hashed with LOCAL helper code (never the production
      digest functions) and compared against the frozen fixture rows/digests;
  (b) V4 happy-path load through the real registry loader with source
      verification against the repository root;
  (c) exact Skill-capability profile resolution;
  (d) hostile V4 profile refusals;
  (e) the compiled OHF capability manifest for a Skill-capability profile;
  (f) the `skills.bundled.enabled=false` App Server config projection/override
      law for grant-bearing profiles only;
  (g) the corrected acyclic digest cascade under source mutation;
  (h) revocation semantics;
  (i) duplicate-JSON-key refusal at every object depth, plus runtime-name
      collision and payload-drift sensitivity;
  (j) static no-migration proof for the protected default config and the
      routing/autonomy surfaces.

This module never imports the private digest-construction helpers from
`control_plane.executive_capability_packages` for the snapshot-independence
check in (a); it recomputes the canonical projections locally so a shared
implementation bug in the production digest functions cannot make both sides
agree falsely.  Later sections (fixture mutation, generation-digest cascade)
do reuse the module's own building blocks, because those tests are about the
registry's *use* of already-proven package identity, not about re-proving the
package module's own digest law (that is `tests/test_executive_capability_packages.py`).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat as stat_module
from pathlib import Path

import pytest

from control_plane.executive_capability_packages import (
    build_capability_package_generation,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "plugins" / "mastermind-operator"
V4_FIXTURE = (
    REPO_ROOT / "scripts" / "ohf" / "fixtures" / "executive_agent_capabilities_v4_mastermind_operator.json"
)
PACKAGE_CAPABILITY_ID = "mastermind-operator.p1"
FIXTURE_PROFILE_ID = "operator.appserver.readonly.mastermind-operator.v1"

FROZEN_PACKAGE_CONTENT_DIGEST = "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306"
FROZEN_SKILL_CONTENT_DIGESTS = {
    "escalate-decision": "ca621a8cc034bf607460d81085c8d466000e38d0f4b6afa8245001374d6cc2ad",
    "finish-operation": "3e689aeaa2b1579781832a854d7256c6ad8ee2ef55521b45f3af8dbe9660675e",
    "receive-commission": "d7953504035c797b30f434f1fdc72e864a7074179abffe7c247f1afc9c0a162c",
    "return-progress": "510be1ed3036f0bc1ed5f709875792ca042c350198a48e1128b4ce8ae46a6552",
}
REQUIRED_SKILL_CAPABILITY_IDS = (
    "mastermind-operator.escalate-decision.v1",
    "mastermind-operator.finish-operation.v1",
    "mastermind-operator.receive-commission.v1",
    "mastermind-operator.return-progress.v1",
)


def _load_v4_fixture_raw() -> dict:
    return json.loads(V4_FIXTURE.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: dict, name: str = "capabilities_v4.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Local, spec-derived canonical-JSON helpers (independent of production code)
# ---------------------------------------------------------------------------

_LOCAL_PACKAGE_CONTENT_SCHEMA = "mastermind.capability_package_content/v1"
_LOCAL_SKILL_CLOSURE_SCHEMA = "mastermind.effective_skill_closure/v1"


def _local_canon(obj: object) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _local_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local_file_row(relative_path: str) -> dict:
    path = PACKAGE_ROOT / relative_path
    data = path.read_bytes()
    st = os.stat(path)
    executable = bool(st.st_mode & (stat_module.S_IXUSR | stat_module.S_IXGRP | stat_module.S_IXOTH))
    return {
        "relative_path": relative_path,
        "sha256": _local_sha256_hex(data),
        "byte_length": len(data),
        "executable": executable,
    }


_REAL_RELATIVE_PATHS = (
    ".codex-plugin/plugin.json",
    "references/app-bindings.template.json",
    "references/dialogue-boundary.md",
    "skills/escalate-decision/SKILL.md",
    "skills/finish-operation/SKILL.md",
    "skills/receive-commission/SKILL.md",
    "skills/return-progress/SKILL.md",
)


def _local_package_content_digest(rows: list[dict]) -> str:
    ordered = sorted(rows, key=lambda r: r["relative_path"])
    projection = {
        "schema_version": _LOCAL_PACKAGE_CONTENT_SCHEMA,
        "files": ordered,
    }
    return _local_sha256_hex(_local_canon(projection))


def _local_skill_closure_digest(*, runtime_name: str, entrypoint_path: str, closure_rows: list[dict]) -> str:
    ordered = sorted(closure_rows, key=lambda r: r["relative_path"])
    projection = {
        "schema_version": _LOCAL_SKILL_CLOSURE_SCHEMA,
        "skill_name": runtime_name,
        "entrypoint_path": entrypoint_path,
        "files": ordered,
    }
    return _local_sha256_hex(_local_canon(projection))


# ---------------------------------------------------------------------------
# (a) Source-snapshot independence
# ---------------------------------------------------------------------------


def test_fixture_file_rows_match_real_repository_bytes_independently():
    fixture_raw = _load_v4_fixture_raw()
    package_raw = fixture_raw["capability_packages"][PACKAGE_CAPABILITY_ID]

    local_rows = [_local_file_row(p) for p in _REAL_RELATIVE_PATHS]
    local_rows_by_path = {row["relative_path"]: row for row in local_rows}

    fixture_rows_by_path = {row["relative_path"]: row for row in package_raw["files"]}
    assert set(fixture_rows_by_path) == set(local_rows_by_path)
    for relative_path, local_row in local_rows_by_path.items():
        assert fixture_rows_by_path[relative_path] == local_row

    local_content_digest = _local_package_content_digest(local_rows)
    assert local_content_digest == FROZEN_PACKAGE_CONTENT_DIGEST
    assert package_raw["package_content_digest"] == FROZEN_PACKAGE_CONTENT_DIGEST


@pytest.mark.parametrize(
    "runtime_name",
    ["escalate-decision", "finish-operation", "receive-commission", "return-progress"],
)
def test_fixture_skill_closure_digests_match_real_repository_bytes_independently(runtime_name):
    fixture_raw = _load_v4_fixture_raw()
    package_raw = fixture_raw["capability_packages"][PACKAGE_CAPABILITY_ID]
    capability_id = f"mastermind-operator.{runtime_name}.v1"
    skill_raw = package_raw["skills"][capability_id]

    entrypoint_path = f"skills/{runtime_name}/SKILL.md"
    closure_paths = sorted(["references/dialogue-boundary.md", entrypoint_path])
    assert skill_raw["closure_paths"] == closure_paths
    assert skill_raw["entrypoint_path"] == entrypoint_path
    assert skill_raw["runtime_name"] == runtime_name

    closure_rows = [_local_file_row(p) for p in closure_paths]
    local_digest = _local_skill_closure_digest(
        runtime_name=runtime_name,
        entrypoint_path=entrypoint_path,
        closure_rows=closure_rows,
    )
    assert local_digest == FROZEN_SKILL_CONTENT_DIGESTS[runtime_name]
    assert skill_raw["skill_content_digest"] == FROZEN_SKILL_CONTENT_DIGESTS[runtime_name]


def test_fixture_package_generation_builds_and_verifies_through_production_module():
    """Sanity seam: the fixture is consumable by the phase-2 module itself.

    This does not prove registry v4 dispatch (that is section (b)); it only
    proves the fixture's own package entry is well-formed and its declared
    digests match its declared rows against real bytes on disk.
    """
    fixture_raw = _load_v4_fixture_raw()
    package_raw = fixture_raw["capability_packages"][PACKAGE_CAPABILITY_ID]
    generation = build_capability_package_generation(
        capability_id=PACKAGE_CAPABILITY_ID, raw=package_raw
    )
    assert generation.package_content_digest == FROZEN_PACKAGE_CONTENT_DIGEST
    assert {grant.runtime_name: grant.skill_content_digest for grant in generation.skills} == (
        FROZEN_SKILL_CONTENT_DIGESTS
    )
