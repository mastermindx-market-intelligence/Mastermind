from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md"
P = ROOT / "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md"
C = ROOT / "config/wake_session_targets.json"
S = ROOT / "control_plane/session_targets.py"
R = ROOT / "control_plane/executive_runtime.py"
B = ROOT / "control_plane/runtime_binding_projection.py"
W = ROOT / "control_plane/wake_transport.py"
L = ROOT / "control_plane/wake_ledger.py"
A = ROOT / "control_plane/sol_action_target.py"
I = ROOT / "tests/test_codex_sol_identity_conformance.py"
X = ROOT / "tests/test_codex_sol_execution_identity_conformance.py"
DB = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->"
DE = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->"
PB = "<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->"
PE = "<!-- STAGE_B1_CORRECTION_GATE_END -->"
OB = "<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->"
OE = "<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->"
SHA = "cba0424f10ad6a9a917234c6740d92b19b018642"
OP = "stage-b0-r1-no-duplicate-owner-freeze-v4-20260902-sol-001"
TARGET = "EXECUTIVE-CEO-CODEX-A"
RECORDS = ["docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md", "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md", "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"]
SOURCE = ["config/wake_session_targets.json", "control_plane/executive_runtime.py", "control_plane/runtime_binding_projection.py", "control_plane/sol_action_target_assignment.py", "tests/test_autonomy_stage_b_initial_assignment.py", "tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"]
ORDER = ("1. RED_V4_SOURCE_LAW_OWNER_TARGET_NO_ACK", "2. ADD_DISABLED_EXECUTIVE_CEO_CODEX_A_TARGET", "3. RED_ROLE_NULL_CEO_CURRENT_WRITER_PROJECTION", "4. EXTEND_EXISTING_RUNTIME_READ_SEAM_WITHOUT_WEAKENING_ROLEFUL_PATH", "5. RED_COMMAND_REPLAY_CONCURRENCY_AND_ALIAS_SHARING", "6. IMPLEMENT_CLOSED_COMMAND_EVENT_AND_ROOT_FOLD", "7. IMPLEMENT_FULL_MAP_EXACT_GENERATION_PROJECTOR", "8. RED_REAL_STAGE_A_AND_STALE_GENERATION", "9. INTEGRATE_UNCHANGED_STAGE_A_CONSUMER", "10. RUN_ROW_INTEGRITY_FORBIDDEN_FIELD_AND_MUTATION_PROOF", "11. RUN_FOCUSED_ADJACENT_FULL_AND_SECURITY_GATES", "12. INDEPENDENT_IMMUTABLE_HEAD_REVIEW", "13. SOL_EXPECTED_HEAD_SOURCE_RELEASE", "14. SEPARATE_DISPOSABLE_PRODUCTION_CANARY")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block(path: Path, begin: str, end: str) -> tuple[dict[str, Any], str]:
    match = re.search(re.escape(begin) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(end), read(path), re.S)
    assert match
    value = json.loads(match.group(1))
    assert isinstance(value, dict)
    return value, match.group(1)


def text_block(path: Path, begin: str, end: str) -> tuple[str, ...]:
    match = re.search(re.escape(begin) + r"\s*```text\s*(.*?)\s*```\s*" + re.escape(end), read(path), re.S)
    assert match
    return tuple(line.strip() for line in match.group(1).splitlines() if line.strip())


def definition(path: Path, qualname: str) -> str:
    source = read(path)
    nodes: list[ast.AST] = list(ast.parse(source).body)
    node: ast.AST | None = None
    for index, part in enumerate(qualname.split(".")):
        node = next((item for item in nodes if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == part), None)
        assert node is not None, f"missing {qualname}"
        if index < len(qualname.split(".")) - 1:
            assert isinstance(node, ast.ClassDef)
            nodes = list(node.body)
    segment = ast.get_source_segment(source, node)
    assert segment
    return segment


def validate(c: dict[str, Any]) -> None:
    assert c["schema"] == "mastermind.autonomy_stage_b_f0_contract.v4"
    assert c["protected_source_sha"] == SHA and c["architecture_operation"] == OP
    assert c["supersedes"] == ["mastermind.autonomy_stage_b_f0_contract.v1", "mastermind.autonomy_stage_b_f0_contract.v2", "mastermind.autonomy_stage_b_f0_contract.v3"]
    assert c["current_claim"] == "SPEC_ONLY / SOURCE_NOT_BUILT / PRODUCTION_INERT"
    assert c["authorized_next_wave"] == "STAGE-B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL"
    assert c["supported_after_source_wave"] == {"modes": ["INITIAL_ASSIGNMENT"], "surfaces": ["codex"]}
    assert c["held"]["modes"] == ["SAME_ALIAS_GENERATION_SUCCESSION", "CROSS_ALIAS_RESPONSIBILITY_TRANSFER"]
    target = c["canonical_target"]
    assert target == {"session_alias": TARGET, "target_seat": "ceo", "reasoning_surface": "codex", "wake_transport": "codex-app-server", "allowed_transports": ["codex-app-server"], "workstream": "executive", "target_enabled": False, "production_armed": False, "caller_selectable": False}
    root = c["responsibility_root"]
    assert root["owner"] == "Executive Runtime Job plus unique JOB_CREATED Event"
    assert "owner_seat equals ceo" in root["required"] and "status in QUEUED|RUNNING|CHECKPOINTED" in root["required"]
    assert "Wake acknowledgement" in root["not_required"] and "provider identity" in root["not_required"]
    carrier = c["destination_carrier"]
    for item in ("orchestration_role is null", "carrier status in QUEUED|RUNNING|CHECKPOINTED", "active worker provider openai-codex", "exactly one CURRENT epoch", "exactly one matching OHF_LAUNCH_DECISION=ALLOW"):
        assert item in carrier["required"]
    assert "ORCHESTRATION_WORK_ADMITTED" in carrier["does_not_require"]
    actor = c["command_authority"]
    assert actor["source"] == "non-serialized live RuntimeBinding from invoking session boundary"
    assert "actor RuntimeBinding is outside command JSON" in actor["required"]
    assert "actor native_handle, binding_id, binding_generation, and reasoning_surface exactly equal destination current RuntimeBinding" in actor["required"]
    assert actor["caller_may_supply_actor_label"] is False and actor["caller_may_supply_actor_binding_in_command"] is False
    assert actor["event_actor_derivation"] == "ceo from validated destination carrier provenance" and actor["persist_native_handle"] is False
    owner = c["assignment_owner"]
    assert owner["event_type"] == "SOL_ACTION_TARGET_ASSIGNED" and owner["event_schema"] == "mastermind.sol_action_target_assignment/v1"
    assert owner["event_actor"] == "ceo" and owner["first_revision"] == 1
    assert "first immutable Event" in owner["rule"] and "same binding_id and binding_generation" in owner["alias_sharing"]
    assert owner["implicit_generation_advance"] is False
    command = c["command"]
    assert command["caller_may_supply_command_id"] is False and "command_id" not in command["fields"]
    assert command["expected_assignment_revision"] == 0 and command["expected_session_alias"] == TARGET
    assert command["foreign_occupancy"] == "COMMAND_REPLAY_CONFLICT" and "EXPECTED_REVISION_MISMATCH" in command["same_root_race"]
    assert "never retry/failover" in command["effect_unknown"]
    assert "binding_generation" in c["event_required"] and "responsibility_authority_fingerprint" in c["event_required"] and "actor_authority_fingerprint" in c["event_required"]
    for item in ("native_handle", "provider_session_id", "account_label", "pid", "Slack principal", "model output", "caller_actor_label"):
        assert item in c["event_forbidden"]
    assert c["target_fingerprint"]["fields"] == ["session_alias", "target_seat", "reasoning_surface", "wake_transport", "allowed_transports", "workstream"]
    assert "target_enabled" in c["target_fingerprint"]["excludes"] and "root_job_bindings" in c["target_fingerprint"]["excludes"]
    extension = c["runtime_extension"]
    assert extension["read_seam"] == "current_ceo_harness_binding_source" and extension["projection_seam"] == "project_ceo_runtime_binding"
    assert extension["same_connection"] is True and extension["read_only"] is True and extension["roleful_behavior_changed"] is False and extension["new_registry"] is False
    assert c["fold"] == {"root_scoped": True, "revision_start": 1, "contiguous": True, "allowed_events": ["SOL_ACTION_TARGET_ASSIGNED"], "duplicate_gap_or_branch": "ASSIGNMENT_HISTORY_CONFLICT", "unsupported_event": "UNSUPPORTED_ASSIGNMENT_MODE", "newest_event_repair": False}
    assert "verify global alias assignments bind one RuntimeBinding" in c["action_time"]
    assert "require Event binding_id and binding_generation exact match" in c["action_time"]
    assert "copy complete root_job_bindings and replace selected root ceo only" in c["action_time"]
    assert c["transaction"][2] == "BEGIN IMMEDIATE" and "validate live actor binding equals destination current binding" in c["transaction"] and c["transaction"][-1].endswith("same id")
    for failure in ("ROOT_JOB_NOT_CEO_OWNED", "TARGET_CARRIER_ROLE_CONFLICT", "ACTOR_AUTHORITY_INVALID", "ACTOR_BINDING_MISMATCH", "TARGET_ALIAS_ALREADY_BINDS_DIFFERENT_RUNTIME", "EXPECTED_REVISION_MISMATCH", "COMMAND_REPLAY_CONFLICT", "STALE_ASSIGNED_BINDING", "UNSUPPORTED_ASSIGNMENT_MODE"):
        assert failure in c["failures"]
    assert "never elect by recency" in c["time_null_correction"]["timestamps"]
    assert "no reassignment or succession" in c["time_null_correction"]["correction"]
    assert c["time_null_correction"]["automatic_retry"] is False
    assert c["source_paths"] == SOURCE
    n = c["no_rebuild"]
    assert n["tables"] == [] and n["migrations"] == [] and n["registries"] == [] and n["lifecycles"] == []
    assert n["job_attempt_worker_rows_mutated"] is False and n["ohf_rows_mutated"] is False and n["wake_rows_mutated"] is False
    assert n["provider_or_slack_calls_in_transaction"] is False and n["stage_a_signature_changed"] is False and n["production_armed"] is False
    assert c["source_release_claim"] == "BUILT_NOT_PROVEN / INITIAL_ASSIGNMENT_ONLY / PRODUCTION_DISARMED"


def test_v4_contract_and_mutations() -> None:
    c, raw = block(D, DB, DE)
    validate(c)
    assert "chatgpt-web" not in raw
    Mutation = Callable[[dict[str, Any]], None]
    def set_path(path: tuple[str, ...], value: Any) -> Mutation:
        def mutate(item: dict[str, Any]) -> None:
            cursor: Any = item
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
        return mutate
    mutations: dict[str, Mutation] = {
        "predecessor_owner": set_path(("assignment_owner", "rule"), "separate receipt owns assignment"),
        "pre_ack": lambda item: item["responsibility_root"]["not_required"].remove("Wake acknowledgement"),
        "caller_actor_label": set_path(("command_authority", "caller_may_supply_actor_label"), True),
        "caller_actor_binding": set_path(("command_authority", "caller_may_supply_actor_binding_in_command"), True),
        "drop_actor_match": lambda item: item["command_authority"]["required"].remove("actor native_handle, binding_id, binding_generation, and reasoning_surface exactly equal destination current RuntimeBinding"),
        "caller_id": set_path(("command", "caller_may_supply_command_id"), True),
        "caller_alias": set_path(("canonical_target", "caller_selectable"), True),
        "succession": lambda item: item["supported_after_source_wave"]["modes"].append("SAME_ALIAS_GENERATION_SUCCESSION"),
        "chatgpt": lambda item: item["supported_after_source_wave"]["surfaces"].append("chatgpt-sol"),
        "implicit_generation": set_path(("assignment_owner", "implicit_generation_advance"), True),
        "roleful": lambda item: item["destination_carrier"]["required"].remove("orchestration_role is null"),
        "destructive_map": set_path(("action_time",), ["replace selected root only"]),
        "new_table": set_path(("no_rebuild", "tables"), ["sol_targets"]),
        "stage_a_change": set_path(("no_rebuild", "stage_a_signature_changed"), True),
        "arming": set_path(("no_rebuild", "production_armed"), True),
        "path_widen": lambda item: item["source_paths"].append("control_plane/sol_action_target.py"),
    }
    survivors = []
    for name, mutate in mutations.items():
        changed = copy.deepcopy(c)
        mutate(changed)
        try:
            validate(changed)
        except (AssertionError, ValueError):
            continue
        survivors.append(name)
    assert survivors == [], survivors


def test_current_projection_target_transport_and_ack_source() -> None:
    config = json.loads(read(C))
    assert config["root_job_bindings"] == {} and "Git stays empty" in config["notes"] and "tests overlay exact bindings" in config["notes"]
    assert not any(t["target_seat"] == "ceo" and t["reasoning_surface"] == "codex" for t in config["targets"].values())
    assert config["targets"]["EXECUTIVE-CEO-A"]["reasoning_surface"] == "chatgpt-sol" and config["production_armed"] is False
    digest = definition(S, "SessionTargetRegistry.policy_digest")
    assert "root_job_bindings" not in digest
    overlay = definition(S, "SessionTargetRegistry.with_root_job_bindings")
    assert "root_job_bindings=resolved" in overlay and "self.root_job_bindings" not in overlay
    assert '"chatgpt-sol"' in read(S) and '"codex"' in read(S) and "chatgpt-web" not in read(S)
    assert '"codex-app-server"' in read(W) and "CodexAppServerWakeTransport" in read(W)
    assert "class WakeAcknowledgement" in read(L) and 'return f"{oid}:ACK"' in read(L)
    assert "consumed_turn_reference" not in read(L) and "acknowledgement_token" not in read(L)


def test_current_ceo_ohf_gap_and_existing_stage_a_are_exact() -> None:
    runtime = read(R)
    assert "def _has_executive_provenance" in runtime
    assert 'owner_seat != "coo" and not _has_executive_provenance' in runtime
    assert 'escalation_target != "coo" and not _has_executive_provenance' in runtime
    current = definition(R, "Runtime.current_harness_binding_source")
    assert "ORCHESTRATION_WORK_ADMITTED" in current and "JOB_CREATED" not in current and "_has_executive_provenance" not in current
    seal = definition(R, "OperatorHarnessRegistry.seal_attestation")
    assert "OHF_LAUNCH_DECISION" in seal
    assert "orchestration_role is None and principal_observation is not None" in seal
    assert "orchestration_role is not None and comparison.decision is LaunchDecision.ALLOW" in seal
    assert "ORCHESTRATION_WORK_ADMITTED" in seal
    binding = read(B)
    assert '_PROVIDER_TO_REASONING_SURFACE = {"openai-codex": "codex"}' in binding
    assert "runtime.current_harness_binding_source" in binding and "connection=connection" in binding and "runtime_binding_id_for" in binding and "persists nothing" in binding
    stage_a = read(A)
    assert "Storeless Stage-A resolution" in stage_a and "seat/workstream defaults are never consulted" in stage_a
    assert "is evidence, not a reusable authority" in stage_a and "def require_sol_action_authority" in stage_a
    assert "_binding_identity(actor) == _binding_identity(target)" in stage_a
    assert "test_ceo_accountability_requires_typed_provenance_not_codex_identity" in read(I)
    assert 'owner_seat="ceo"' in read(I) and "owner_seat" in read(X) and "provider" in read(X)


def test_plan_gate_paths_and_order() -> None:
    g, raw = block(P, PB, PE)
    assert g["schema"] == "mastermind.autonomy_stage_b1_correction_gate.v4" and g["protected_source_sha"] == SHA and g["architecture_operation"] == OP
    assert g["carrier"]["pull_request"] == 368 and g["records_paths"] == RECORDS
    assert g["records_only"] is True and g["runtime_effect"] is False and g["provider_effect"] is False and g["production_armed"] is False
    assert g["authorized_next_wave"] == "STAGE-B1_CEO_CODEX_INITIAL_ASSIGNMENT_VERTICAL" and g["authorized_mode"] == "INITIAL_ASSIGNMENT" and g["authorized_surface"] == "codex"
    assert g["canonical_target_alias"] == TARGET and g["separate_root_binding_owner_required"] is False and g["pre_assignment_wake_ack_required"] is False
    assert g["requires_exact_current_actor_binding"] is True and g["caller_actor_label_authoritative"] is False
    assert g["requires_exact_binding_generation_fence"] is True and g["requires_full_map_preservation"] is True and g["requires_unchanged_stage_a"] is True and g["requires_separate_production_canary"] is True
    assert "chatgpt-web" not in raw and text_block(P, OB, OE) == ORDER
    plan = read(P)
    for path in RECORDS + SOURCE:
        assert path in plan
    assert "No seventh path is authorized" in plan and "Do not modify `control_plane/sol_action_target.py`" in plan
