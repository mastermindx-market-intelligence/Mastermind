"""Record-only ASF-F0 checks; no provider, process, Runtime or auth execution.

The record is documentation, not a runtime policy/configuration API. Paired
mutations check its declared boundaries. AST joins prove named source seams
exist; they do not prove that those seams are installed or production-safe.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ESTATE = "research/PROVIDER_APP_SERVER_ADAPTER_ESTATE_2026-09-06.md"
SPEC = "docs/superpowers/specs/2026-09-06-provider-app-server-adapter-fabric-design.md"
PLAN = "docs/superpowers/plans/2026-09-06-provider-app-server-adapter-fabric.md"
TEST = "tests/test_provider_app_server_adapter_source_law.py"
SOURCE_PATHS = [ESTATE, SPEC, PLAN, TEST]
OWNERS = {
    "lifecycle": "Executive OS",
    "placement": "Existing Model Router and Capacity claim",
    "continuation": "Existing Wake and RuntimeBinding",
    "organizational_memory": "Macro Agent OS",
    "implementation_evidence": "GitHub",
    "transport": "Slack",
    "supervisor_projection": "Existing Control Room and Steward",
}
INTERFACES = {
    "sealed_worker": ("control_plane/worker_adapter.py", "WorkerExecutionAdapter",
                      ["start", "collect_result", "cancel", "run_validation_argv"]),
    "rich_operator": ("control_plane/operator_harness_contract.py", "OperatorHarnessAdapter",
                      ["describe_capabilities", "validate_requested_profile", "start_session",
                       "begin_turn", "read_events", "interrupt_turn",
                       "collect_candidate_result", "graceful_stop", "cancel", "reconcile"]),
}
PORTS = {
    "codex": ("codex-app-server-stdio", "rich_operator", "BUILT_NOT_PROVEN",
              "turn/completed:interrupted", "SOURCE_SUPPORTED_NOT_LIVE_PROVEN"),
    "claude": ("claude-foreground-cli", "sealed_worker", "SPEC_ONLY",
               "closed-profile terminal plus identity-safe cleanup", "NOT_ADMITTED_FIRST_SLICE"),
    "grok": ("acp-stdio", "sealed_worker", "SPEC_ONLY",
             "original session/prompt response:cancelled", "UNVERIFIED"),
}
EFFECTS = {
    "intent_before_dispatch": True,
    "unknown_disposition": "RECONCILE_SAME_OPERATION",
    "retry_unknown": False,
    "provider_failover_unknown": False,
    "account_failover_unknown": False,
    "host_failover_unknown": False,
    "process_exit_proves_remote_cancellation": False,
    "candidate_result_completes_job": False,
}
SUPERVISION = {
    "independent_work": "EXECUTIVE_CHILD_JOB",
    "ephemeral_helpers": "PARENT_GRANT_NO_INDEPENDENT_EFFECT",
    "native_lineage": "OBSERVED_PARENT_ATTEMPT_OR_UNKNOWN",
    "permission_ceiling": "CHILD_SUBSET_OF_PARENT",
    "budgets": "EXISTING_OWNER_UNCHANGED",
    "cost_order": "SUITABILITY_THEN_CAPACITY",
    "gui": "COMPARATOR_NOT_EXECUTION_OWNER",
    "result_target": "EXISTING_RESULT_AND_PARENT_WAKE",
    "unknowns": "EXPLICIT_NOT_IDLE",
    "new_store": False,
}
JOURNEY = ["admitted_job", "atomic_worker_claim", "attested_execution",
           "canonical_result", "independent_review", "parent_consumption",
           "visible_consumer", "terminal_reconciliation"]
FAILURES = ["lost_launch_response", "wrong_realm", "model_mismatch", "schema_drift",
            "late_cancel", "duplicate_result", "stale_parent", "worker_crash",
            "capacity_exhaustion", "host_interruption"]


def _same(actual, expected):
    """JSON comparison deliberately distinguishes true from 1 and null from false."""
    assert json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(
        expected, sort_keys=True, allow_nan=False), (actual, expected)

def _unique(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, "duplicate documentation record key"
        result[key] = value
    return result


def _parse_record(text):
    blocks = re.findall(r"<!-- ASF_SOURCE_RECORD -->\s*```json\s*\n(.*?)\n```", text, re.S)
    assert len(blocks) == 1, "exactly one documentation source record required"
    return json.loads(blocks[0], object_pairs_hook=_unique)


def _load_record():
    path = ROOT / SPEC
    assert path.is_file(), "F0 design source record is missing"
    return _parse_record(path.read_text(encoding="utf-8"))


def _validate(record):
    assert set(record) == {"record_type", "version", "scope", "owners", "interfaces",
                           "providers", "effects", "supervision", "proof"}
    _same(record["record_type"], "DOCUMENTATION_ONLY_SELECTION")
    _same(record["version"], 1)
    _same(record["scope"], {"source_paths": SOURCE_PATHS, "runtime_writes": [],
                            "provider_invocations": 0, "production_armed": False})
    _same(record["owners"], OWNERS)
    assert set(record["interfaces"]) == set(INTERFACES)
    for key, (path, symbol, methods) in INTERFACES.items():
        _same(record["interfaces"][key], {"path": path, "symbol": symbol, "methods": methods})
    assert set(record["providers"]) == set(PORTS)
    for key, (transport, interface, state, terminal, resume) in PORTS.items():
        _same(record["providers"][key], {
            "transport": transport, "interface": interface, "capability_state": state,
            "cancel_completion": terminal, "resume": resume,
            "actual_binary_required": True, "identity": "SAME_WORKER_REALM_REQUIRED",
            "model": "REQUESTED_AND_OBSERVED_SEPARATE",
            "quota": "OPTIONAL_FRESH_REALM_BOUND_OR_UNKNOWN",
            "activation": "SEPARATE_EXISTING_OWNER_GATE",
        })
    _same(record["effects"], EFFECTS)
    _same(record["supervision"], SUPERVISION)
    _same(record["proof"], {
        "record_tests_prove": "DOCUMENT_COHERENCE_AND_SOURCE_SEAM_EXISTENCE_ONLY",
        "required_real_journey": JOURNEY, "failure_cases": FAILURES,
        "executed_by_f0": False, "provider_proof_complete": False,
    })


class ProviderAdapterSourceLawTests(unittest.TestCase):
    def test_all_four_source_records_are_present(self):
        for path in SOURCE_PATHS:
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertFalse((ROOT / path).is_symlink(), path)

    def test_documentation_record_is_closed_and_consistent(self):
        _validate(_load_record())

    def test_both_declared_interfaces_join_actual_source(self):
        record = _load_record()
        _validate(record)
        for interface in record["interfaces"].values():
            tree = ast.parse((ROOT / interface["path"]).read_text(encoding="utf-8"))
            classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
                       and node.name == interface["symbol"]]
            self.assertEqual(len(classes), 1, interface["symbol"])
            methods = {node.name for node in classes[0].body
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            self.assertTrue(set(interface["methods"]) <= methods, interface["symbol"])

    def test_provider_session_field_remains_owner_defined(self):
        tree = ast.parse((ROOT / INTERFACES["rich_operator"][0]).read_text(encoding="utf-8"))
        names = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in {
                    "CANONICAL_SESSION_FIELD", "FORBIDDEN_SESSION_SYNONYM"
                }:
                    names[target.id] = ast.literal_eval(node.value)
        self.assertEqual(names, {"CANONICAL_SESSION_FIELD": "provider_session_id",
                                "FORBIDDEN_SESSION_SYNONYM": "native_session_id"})

    def test_result_and_intent_seams_already_exist(self):
        for path, expected in {
            "control_plane/executive_orchestration_result.py":
                {"validate_envelope", "parse_and_validate_envelope", "_validate_review"},
            "control_plane/operator_harness_orchestrator.py":
                {"begin_operator_session", "bind_operator_session", "record_operator_effect_unknown"},
        }.items():
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
            present = {node.name for node in ast.walk(tree)
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            self.assertTrue(expected <= present, path)

    def test_record_parser_refuses_duplicate_keys(self):
        with self.assertRaisesRegex(AssertionError, "duplicate"):
            _parse_record('<!-- ASF_SOURCE_RECORD -->\n```json\n{"v":1,"v":2}\n```')

    def test_record_parser_requires_exactly_one_record(self):
        with self.assertRaises(AssertionError):
            _parse_record("a prose PASS is not a design record")
        block = '<!-- ASF_SOURCE_RECORD -->\n```json\n{}\n```'
        with self.assertRaises(AssertionError):
            _parse_record(block + "\n" + block)

    def test_record_tests_use_only_stdlib_imports(self):
        tree = ast.parse((ROOT / TEST).read_text(encoding="utf-8"))
        allowed = {"__future__", "ast", "copy", "json", "re", "unittest", "pathlib"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertTrue(imported <= allowed, imported - allowed)


MUTATIONS = {
    "second_lifecycle": (("owners", "lifecycle"), "Provider-local lifecycle"),
    "fifth_source_path": (("scope", "source_paths"), SOURCE_PATHS + ["control_plane/new.py"]),
    "runtime_write": (("scope", "runtime_writes"), ["Executive SQLite"]),
    "provider_probe": (("scope", "provider_invocations"), 1),
    "production_arming": (("scope", "production_armed"), True),
    "boolean_version": (("version",), True),
    "integer_false": (("scope", "production_armed"), 0),
    "claude_app_server_fiction": (("providers", "claude", "transport"), "claude-app-server"),
    "sdk_silent_substitution": (("providers", "claude", "transport"), "sdk-auto-selected-cli"),
    "unbound_binary": (("providers", "claude", "actual_binary_required"), False),
    "unbound_realm": (("providers", "grok", "identity"), "ANY_AUTHENTICATED_ACCOUNT"),
    "invented_quota": (("providers", "grok", "quota"), "UNKNOWN_IS_AVAILABLE"),
    "grok_kill_is_cancel": (("providers", "grok", "cancel_completion"), "child killed"),
    "codex_interrupt_ack_is_terminal": (("providers", "codex", "cancel_completion"), "interrupt ACK"),
    "claude_resume_leak": (("providers", "claude", "resume"), "ENABLED"),
    "candidate_promoted_live": (("providers", "grok", "capability_state"), "PROVEN_LIVE"),
    "dispatch_before_intent": (("effects", "intent_before_dispatch"), False),
    "retry_effect_unknown": (("effects", "retry_unknown"), True),
    "provider_failover": (("effects", "provider_failover_unknown"), True),
    "account_failover": (("effects", "account_failover_unknown"), True),
    "host_failover": (("effects", "host_failover_unknown"), True),
    "exit_proves_remote_cancel": (("effects", "process_exit_proves_remote_cancellation"), True),
    "candidate_self_completion": (("effects", "candidate_result_completes_job"), True),
    "invisible_material_helper": (("supervision", "independent_work"), "NATIVE_HELPER_ONLY"),
    "new_budget_defaults": (("supervision", "budgets"), "UNBOUNDED_FANOUT"),
    "cheapest_before_quality": (("supervision", "cost_order"), "COST_FIRST"),
    "second_observation_store": (("supervision", "new_store"), True),
    "skip_parent_consumption": (("proof", "required_real_journey"), [x for x in JOURNEY if x != "parent_consumption"]),
    "record_tests_are_provider_proof": (("proof", "provider_proof_complete"), True),
}


def _mutation_case(path, replacement):
    def case(self):
        original = _load_record()
        _validate(original)  # Missing or already-invalid records cannot yield a false green.
        mutated = copy.deepcopy(original)
        parent = mutated
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = replacement
        self.assertNotEqual(json.dumps(original, sort_keys=True), json.dumps(mutated, sort_keys=True))
        with self.assertRaises(AssertionError):
            _validate(mutated)
    return case


for _name, (_path, _replacement) in MUTATIONS.items():
    setattr(ProviderAdapterSourceLawTests, "test_reject_" + _name,
            _mutation_case(_path, _replacement))

if __name__ == "__main__":
    unittest.main()
