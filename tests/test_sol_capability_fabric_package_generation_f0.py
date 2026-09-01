from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-generation-design.md"
CORRECTION = ROOT / "docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-content-digest-correction.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-01-sol-capability-fabric-package-generation.md"
PACKAGE_ROOT = ROOT / "plugins/mastermind-operator"
DEFAULT_POLICY = ROOT / "config/executive_agent_capabilities.json"
ROUTES = ROOT / "config/executive_worker_routes.json"
AUTONOMY = ROOT / "control_plane/executive_autonomy.py"

PACKAGE_SCHEMA = "mastermind.capability_package_content/v1"
CLOSURE_SCHEMA = "mastermind.effective_skill_closure/v1"
CORRECT_PACKAGE_DIGEST = (
    "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306"
)
INCORRECT_SUPERSEDED_DIGEST = (
    "a82a274a82ed84c6e82a1c34b67c1f2f0a70cc465c26d0fcf64f648ac295cf16"
)

EXPECTED_FILES = {
    ".codex-plugin/plugin.json": (
        796,
        "0373afdf8950226466383dff091359b81e78ea2732b5ce0ca51afad9c5d8a396",
        False,
    ),
    "references/app-bindings.template.json": (
        388,
        "a4e3e7219fa162063913aadf8cfb6c8b8d1e8ba27bfd7fead1fe007c617dea35",
        False,
    ),
    "references/dialogue-boundary.md": (
        881,
        "e2270c7a324f817b3d0307a2dc9f103615c807102ff35e1a15b8b07f63d7b1c9",
        False,
    ),
    "skills/escalate-decision/SKILL.md": (
        1636,
        "1dbe6a296a96eb60c60b587816dec492d258797e42736ffd8901ecd2a81b5286",
        False,
    ),
    "skills/finish-operation/SKILL.md": (
        1816,
        "f6a91874cf4c41a7655ae31755744646fb3220185f290f118b5d3e8e92a27685",
        False,
    ),
    "skills/receive-commission/SKILL.md": (
        1695,
        "212f5253c812ca47174ca9aac92977d5f649891da28c12b6948c4e0284422c4d",
        False,
    ),
    "skills/return-progress/SKILL.md": (
        1435,
        "6e569a972075f18a5595891a3b7178520a04d0ff732cc7dcffce910c2d097d30",
        False,
    ),
}

EXPECTED_CLOSURES = {
    "escalate-decision": (
        "ca621a8cc034bf607460d81085c8d466000e38d0f4b6afa8245001374d6cc2ad"
    ),
    "finish-operation": (
        "3e689aeaa2b1579781832a854d7256c6ad8ee2ef55521b45f3af8dbe9660675e"
    ),
    "receive-commission": (
        "d7953504035c797b30f434f1fdc72e864a7074179abffe7c247f1afc9c0a162c"
    ),
    "return-progress": (
        "510be1ed3036f0bc1ed5f709875792ca042c350198a48e1128b4ce8ae46a6552"
    ),
}


def _read(path: Path) -> str:
    payload = path.read_bytes()
    assert payload
    assert b"\x00" not in payload
    assert payload.endswith(b"\n")
    return payload.decode("utf-8")


def _prose(path: Path) -> str:
    return " ".join(_read(path).split())


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _actual_file_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(PACKAGE_ROOT.rglob("*")):
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        observed = path.lstat()
        assert not stat.S_ISLNK(observed.st_mode), relative
        if path.is_dir():
            continue
        assert stat.S_ISREG(observed.st_mode), relative
        payload = path.read_bytes()
        rows.append(
            {
                "relative_path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "byte_length": len(payload),
                "executable": bool(stat.S_IMODE(observed.st_mode) & 0o111),
            }
        )
    return rows


def test_records_are_complete_owner_correct_and_production_inert() -> None:
    spec = _read(SPEC)
    correction = _read(CORRECTION)
    plan = _read(PLAN)
    combined = "\n".join((spec, correction, plan)).replace("_", " ")

    for token in (
        "ExecutionCapabilityRegistry",
        "Sol Capability Fabric",
        "BSC-P1",
        "BSC-U1",
        "Professional Practice Fabric",
        "Operator Harness",
        "Executive OS",
        "PRODUCTION INERT",
        "SCF-PKG1",
        "CAP-S1",
    ):
        assert token in combined

    for forbidden in ("TODO", "TBD"):
        assert forbidden not in plan

    spec_prose = _prose(SPEC)
    plan_prose = _prose(PLAN)
    assert "WHY NOT FABLE" in plan
    assert "config/executive_agent_capabilities.json" in spec
    assert "current v3 policy digest remains unchanged" in spec_prose
    assert "No provider process" in plan_prose
    assert "builds no model-facing tool" in spec_prose
    assert "does not yield a live provider capability" in spec_prose
    assert "must not create `PluginRegistry`" in spec_prose
    assert "`PackageStore`" in spec


def test_default_policy_routes_and_autonomy_remain_v3_without_package_grants() -> None:
    raw = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "mastermind.executive_agent_capabilities/v3"
    assert raw["plugins"] == {}
    assert "operator.appserver.readonly.mastermind-operator.v1" not in raw["profiles"]

    protected_text = ROUTES.read_text(encoding="utf-8") + AUTONOMY.read_text(
        encoding="utf-8"
    )
    assert "mastermind-operator.p1" not in protected_text
    assert "mastermind-operator.receive-commission.v1" not in protected_text
    assert "2026-09-01.mastermind-operator-p1-fixture" not in protected_text


def test_exact_protected_package_inventory_matches_the_frozen_seven_rows() -> None:
    actual = _actual_file_rows()
    assert [row["relative_path"] for row in actual] == sorted(EXPECTED_FILES)
    assert len(actual) == 7

    for row in actual:
        expected_bytes, expected_sha256, expected_executable = EXPECTED_FILES[
            str(row["relative_path"])
        ]
        assert row["byte_length"] == expected_bytes
        assert row["sha256"] == expected_sha256
        assert row["executable"] is expected_executable


def test_corrected_package_content_digest_is_recomputed_from_real_files() -> None:
    rows = _actual_file_rows()
    actual = _digest({"schema_version": PACKAGE_SCHEMA, "files": rows})
    assert actual == CORRECT_PACKAGE_DIGEST
    assert actual != INCORRECT_SUPERSEDED_DIGEST

    correction = _read(CORRECTION)
    plan = _read(PLAN)
    assert INCORRECT_SUPERSEDED_DIGEST in correction
    assert CORRECT_PACKAGE_DIGEST in correction
    assert CORRECT_PACKAGE_DIGEST in plan
    assert INCORRECT_SUPERSEDED_DIGEST not in plan
    assert "supersedes" in correction


def test_each_operator_skill_closure_includes_the_shared_dialogue_reference() -> None:
    rows = _actual_file_rows()
    by_path = {str(row["relative_path"]): row for row in rows}
    shared = "references/dialogue-boundary.md"

    for name, expected_digest in EXPECTED_CLOSURES.items():
        entrypoint = f"skills/{name}/SKILL.md"
        skill_text = (PACKAGE_ROOT / entrypoint).read_text(encoding="utf-8")
        assert "../../references/dialogue-boundary.md" in skill_text

        closure_rows = tuple(by_path[path] for path in sorted((shared, entrypoint)))
        actual = _digest(
            {
                "schema_version": CLOSURE_SCHEMA,
                "skill_name": name,
                "entrypoint_path": entrypoint,
                "files": closure_rows,
            }
        )
        assert actual == expected_digest


def test_package_and_effective_skill_closure_identities_stay_distinct() -> None:
    spec = _prose(SPEC)
    plan = _prose(PLAN)

    assert "A package generation and a Skill closure are distinct identities" in spec
    assert "unrelated app-binding" in plan
    assert "all four closure digests stable" in plan
    assert "shared dialogue reference change" in plan
    assert "all four closures change" in plan


def test_v4_is_opt_in_and_runtime_plugin_authority_remains_unavailable() -> None:
    spec = _prose(SPEC)
    spec_lower = spec.lower()
    plan = _prose(PLAN)

    assert "CAPABILITY_POLICY_SCHEMA_V3 = mastermind.executive_agent_capabilities/v3" in spec
    assert "CAPABILITY_POLICY_SCHEMA_V4 = mastermind.executive_agent_capabilities/v4" in spec
    assert "`CAPABILITY_POLICY_SCHEMA` remains the current default v3 compatibility alias" in spec
    assert "v3 non-empty plugin registry still refuses" in spec_lower
    assert "full runtime plugin grants remain unavailable" in spec_lower
    assert "Default `config/executive_agent_capabilities.json` remains schema v3" in plan
    assert "Do not start CAP-S1" in plan


def test_implementation_scope_preserves_all_no_edit_surfaces() -> None:
    plan = _read(PLAN)
    for path in (
        "config/executive_agent_capabilities.json",
        "config/executive_worker_routes.json",
        "control_plane/executive_autonomy.py",
        "control_plane/operator_harness_contract.py",
        "control_plane/codex_operator_adapter.py",
        "scripts/executive_os_phase1c_worker.py",
    ):
        assert path in plan

    assert "Protected no-edit files" in plan
    assert "SCF-PKG1 = BUILT_NOT_PROVEN / PRODUCTION_INERT" in plan
    assert "No source merge creates host `CONFIG_DRIFT`" in _prose(SPEC)


def test_next_wave_is_bounded_codex_engineering_not_principal_program_work() -> None:
    plan = _prose(PLAN)
    assert "ROUTE: Codex engineering worker / CTO Sol-compatible execution surface" in plan
    assert "WHY NOT FABLE" in plan
    assert "single-repository" in plan
    assert "no remaining product/organizational ambiguity" in plan
    assert "Do not migrate the default policy" in plan
    assert "Do not start CAP-S1" in plan
