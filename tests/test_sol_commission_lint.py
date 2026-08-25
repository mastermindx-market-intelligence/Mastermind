"""Mutation battery for scripts/sol_commission_lint.py (Continuation Delta contract).

Every hard finding in docs/sol_skills/CONTINUATION_DELTA_CONTRACT.md has at
least one mutation here that was observed RED before the linter existed
(RED-first evidence lives in the PR body). The committed green corpus under
tests/fixtures/sol_commission_delta/ must pass.

The linter validates a derivation artifact only. It authorizes nothing, reads
nothing from the network, and owns no lifecycle.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.sol_commission_lint import lint_file, main

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "sol_commission_delta"


# ---------------------------------------------------------------- helpers


def _extract_yaml(md_path: Path) -> dict:
    """Pull the manifest mapping out of a fenced yaml block in a .md fixture."""
    text = md_path.read_text(encoding="utf-8")
    inside, buf = False, []
    for line in text.splitlines():
        if line.strip().startswith("```yaml"):
            inside = True
            continue
        if inside and line.strip().startswith("```"):
            break
        if inside:
            buf.append(line)
    data = yaml.safe_load("\n".join(buf))
    assert isinstance(data, dict) and data.get("schema") == "mastermind.sol_commission.v1"
    return data


def _base() -> dict:
    return copy.deepcopy(_extract_yaml(FIX / "base_continuation.md"))


def _lint_dict(tmp_path: Path, manifest: dict, context: Path | None = None):
    p = tmp_path / "manifest.yml"
    p.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return lint_file(p, context_path=context)


def _hard(findings) -> set[str]:
    return {f.name for f in findings if f.severity == "hard"}


def _warn(findings) -> set[str]:
    return {f.name for f in findings if f.severity == "warning"}


# ---------------------------------------------------------------- green corpus


def test_green_base_continuation_has_no_hard_findings():
    findings = lint_file(FIX / "base_continuation.md")
    assert _hard(findings) == set()


def test_green_base_without_bundle_warns_dnr_coverage_unproven():
    findings = lint_file(FIX / "base_continuation.md")
    assert "DNR_COVERAGE_UNPROVEN" in _warn(findings)


def test_green_base_with_covering_bundle_is_fully_clean():
    findings = lint_file(FIX / "base_continuation.md", context_path=FIX / "context_bundle.json")
    assert _hard(findings) == set()
    assert "DNR_COVERAGE_UNPROVEN" not in _warn(findings)


def test_green_new_wave_passes():
    findings = lint_file(FIX / "new_wave.md")
    assert _hard(findings) == set()


def test_case_k_repeated_context_is_not_replay():
    """Completed effects described as context, executable surface only open work."""
    findings = lint_file(FIX / "case_k_context_not_replay.md")
    assert _hard(findings) == set()


# ---------------------------------------------------------------- replay findings


def test_case_a_done_work_in_ordered_is_replay_collision(tmp_path):
    m = _base()
    m["execution"]["ordered"].append("DUR-01")
    assert "HANDOFF_REPLAY_COLLISION" in _hard(_lint_dict(tmp_path, m))


def test_done_work_in_parallel_is_replay_collision(tmp_path):
    m = _base()
    m["execution"]["parallel"] = ["DUR-01"]
    assert "HANDOFF_REPLAY_COLLISION" in _hard(_lint_dict(tmp_path, m))


def test_superseded_work_reopened(tmp_path):
    m = _base()
    m["execution"]["ordered"].append("DUR-02")
    assert "SUPERSEDED_WORK_REOPENED" in _hard(_lint_dict(tmp_path, m))


def test_rejected_work_reopened(tmp_path):
    m = _base()
    for ob in m["obligations"]:
        if ob["id"] == "DUR-02":
            ob["disposition"] = "REJECTED"
    m["execution"]["ordered"].append("DUR-02")
    assert "REJECTED_WORK_REOPENED" in _hard(_lint_dict(tmp_path, m))


# ---------------------------------------------------------------- revalidation


def test_case_c_revalidation_without_invalidator_is_unjustified(tmp_path):
    m = _base()
    for ob in m["obligations"]:
        if ob["id"] == "APP-R1":
            ob.pop("invalidated_by")
    assert "UNJUSTIFIED_REVALIDATION" in _hard(_lint_dict(tmp_path, m))


def test_revalidation_without_prior_evidence_is_unjustified(tmp_path):
    m = _base()
    for ob in m["obligations"]:
        if ob["id"] == "APP-R1":
            ob.pop("prior_evidence")
    assert "UNJUSTIFIED_REVALIDATION" in _hard(_lint_dict(tmp_path, m))


def test_case_b_justified_revalidation_passes():
    findings = lint_file(FIX / "base_continuation.md")
    assert "UNJUSTIFIED_REVALIDATION" not in _hard(findings)


# ---------------------------------------------------------------- binding / identity


def test_unbound_continuation_missing_pickup_sha(tmp_path):
    m = _base()
    del m["identity"]["carrier"]["pickup_sha"]
    assert "UNBOUND_CONTINUATION" in _hard(_lint_dict(tmp_path, m))


def test_unbound_continuation_short_sha(tmp_path):
    m = _base()
    m["identity"]["carrier"]["pickup_sha"] = "abc123"
    assert "UNBOUND_CONTINUATION" in _hard(_lint_dict(tmp_path, m))


def test_case_j_same_id_two_states_is_collision(tmp_path):
    m = _base()
    m["obligations"].append({"id": "APP-01", "statement": "duplicate", "disposition": "REJECTED"})
    assert "OBLIGATION_STATE_COLLISION" in _hard(_lint_dict(tmp_path, m))


def test_case_i_execution_references_undeclared_id(tmp_path):
    m = _base()
    m["execution"]["ordered"].append("GHOST-9")
    assert "UNDECLARED_EXECUTION" in _hard(_lint_dict(tmp_path, m))


def test_held_references_undeclared_id(tmp_path):
    """C3 resolution: held is a validated surface too."""
    m = _base()
    m["execution"]["held"].append("GHOST-8")
    assert "UNDECLARED_EXECUTION" in _hard(_lint_dict(tmp_path, m))


# ---------------------------------------------------------------- disposition legality


def test_blocked_work_in_ordered_is_illegal(tmp_path):
    m = _base()
    m["execution"]["ordered"].append("SUCC-01")
    assert "EXECUTION_DISPOSITION_ILLEGAL" in _hard(_lint_dict(tmp_path, m))


def test_done_work_in_held_is_illegal(tmp_path):
    m = _base()
    m["execution"]["held"].append("DUR-01")
    assert "HELD_DISPOSITION_ILLEGAL" in _hard(_lint_dict(tmp_path, m))


def test_open_work_in_held_without_hold_reason_is_illegal(tmp_path):
    m = _base()
    m["execution"]["ordered"].remove("APP-01")
    m["execution"]["held"].append("APP-01")
    assert "HELD_DISPOSITION_ILLEGAL" in _hard(_lint_dict(tmp_path, m))


def test_open_work_in_held_with_hold_reason_is_lawful(tmp_path):
    m = _base()
    m["execution"]["ordered"].remove("APP-01")
    m["execution"]["held"].append("APP-01")
    for ob in m["obligations"]:
        if ob["id"] == "APP-01":
            ob["hold_reason"] = "waiting on the F2 ruling before this becomes executable"
    findings = _lint_dict(tmp_path, m)
    assert "HELD_DISPOSITION_ILLEGAL" not in _hard(findings)
    assert "DARK_OPEN_WORK" not in _hard(findings)


# ---------------------------------------------------------------- dark work / empty delta


def test_case_h_dark_open_work(tmp_path):
    m = _base()
    m["obligations"].append({"id": "APP-04", "statement": "forgotten", "disposition": "OPEN"})
    assert "DARK_OPEN_WORK" in _hard(_lint_dict(tmp_path, m))


def test_dark_open_work_escaped_by_deferred_to(tmp_path):
    """C4 resolution: the independent-parallel-wave exemption is a declared field."""
    m = _base()
    m["obligations"].append(
        {
            "id": "APP-04",
            "statement": "owned by an independent wave",
            "disposition": "OPEN",
            "deferred_to": "WS:OTHER-PROGRAM",
        }
    )
    assert "DARK_OPEN_WORK" not in _hard(_lint_dict(tmp_path, m))


def test_case_g_nothing_to_commission(tmp_path):
    m = _base()
    for ob in m["obligations"]:
        if ob["disposition"] in {"OPEN", "REVALIDATE_REQUIRED"}:
            ob["disposition"] = "DONE"
            ob.pop("prior_evidence", None)
            ob.pop("invalidated_by", None)
            ob["evidence"] = ["completed on the prior carrier"]
    m["execution"]["ordered"] = []
    m["execution"]["parallel"] = []
    assert "NOTHING_TO_COMMISSION" in _hard(_lint_dict(tmp_path, m))


# ---------------------------------------------------------------- do-not-redo


def test_case_e_dnr_reopened_without_refutation(tmp_path):
    m = _base()
    m["do_not_redo_reconciliation"][0]["reopens"] = ["APP-01"]
    assert "DNR_REOPEN_WITHOUT_REFUTATION" in _hard(_lint_dict(tmp_path, m))


def test_refuted_without_refuted_by_is_unlawful(tmp_path):
    m = _base()
    m["do_not_redo_reconciliation"][0]["disposition"] = "REFUTED"
    assert "DNR_REOPEN_WITHOUT_REFUTATION" in _hard(_lint_dict(tmp_path, m))


def test_case_f_lawful_dnr_refutation(tmp_path):
    m = _base()
    entry = m["do_not_redo_reconciliation"][0]
    entry["disposition"] = "REFUTED"
    entry["refuted_by"] = ["the archived critic receipt is proven byte-corrupt (sha mismatch vs merge)"]
    entry["reopens"] = ["APP-01"]
    assert "DNR_REOPEN_WITHOUT_REFUTATION" not in _hard(_lint_dict(tmp_path, m))


def test_uncovered_bundle_statement_is_hard_coverage_missing(tmp_path):
    m = _base()
    findings = _lint_dict(tmp_path, m, context=FIX / "context_bundle_uncovered.json")
    assert "DNR_COVERAGE_MISSING" in _hard(findings)


def test_coverage_match_is_whitespace_and_case_insensitive(tmp_path):
    m = _base()
    m["do_not_redo_reconciliation"][0]["statement"] = (
        "  do not RE-DERIVE the six-lane archaeology;   extend, don't re-census. "
    )
    findings = _lint_dict(tmp_path, m, context=FIX / "context_bundle.json")
    assert "DNR_COVERAGE_MISSING" not in _hard(findings)


# ---------------------------------------------------------------- organizational sources


def test_missing_workstream_source_is_not_reconciled(tmp_path):
    m = _base()
    del m["sources"]["agentos_workstream"]
    assert "ORGANIZATIONAL_STATE_NOT_RECONCILED" in _hard(_lint_dict(tmp_path, m))


def test_declared_unavailable_workstream_source_is_lawful(tmp_path):
    m = _base()
    m["sources"]["agentos_workstream"] = {
        "status": "unavailable",
        "reason": "protected Git read outage; investigation-only continuation",
    }
    assert "ORGANIZATIONAL_STATE_NOT_RECONCILED" not in _hard(_lint_dict(tmp_path, m))


def test_bad_observed_sha_grammar_is_malformed(tmp_path):
    """C4 resolution: blob-proof grammar is exact — 40-hex or blob:<40-hex>."""
    m = _base()
    m["sources"]["agentos_workstream"]["observed_sha"] = "blob:short"
    assert "MALFORMED_MANIFEST" in _hard(_lint_dict(tmp_path, m))


# ---------------------------------------------------------------- warnings


def test_possible_stale_org_state_when_recorded_next_wave_already_completed(tmp_path):
    m = _base()
    m["sources"]["agentos_workstream"]["recorded_next_wave"] = "W2"
    assert "POSSIBLE_STALE_ORG_STATE" in _warn(_lint_dict(tmp_path, m))


def test_new_wave_with_existing_carrier_warns(tmp_path):
    m = _base()
    m["handoff_mode"] = "NEW_WAVE"
    assert "NEW_WAVE_WITH_EXISTING_CARRIER" in _warn(_lint_dict(tmp_path, m))


# ---------------------------------------------------------------- malformed / CLI


def test_missing_schema_is_malformed(tmp_path):
    m = _base()
    del m["schema"]
    assert "MALFORMED_MANIFEST" in _hard(_lint_dict(tmp_path, m))


def test_unknown_disposition_is_malformed(tmp_path):
    m = _base()
    m["obligations"][0]["disposition"] = "KINDA_DONE"
    assert "MALFORMED_MANIFEST" in _hard(_lint_dict(tmp_path, m))


def test_unknown_handoff_mode_is_malformed(tmp_path):
    m = _base()
    m["handoff_mode"] = "SORT_OF_CONTINUING"
    assert "MALFORMED_MANIFEST" in _hard(_lint_dict(tmp_path, m))


def test_cli_exit_codes_and_determinism(tmp_path):
    clean = FIX / "base_continuation.md"
    assert main([str(clean), "--agentos-context", str(FIX / "context_bundle.json")]) == 0

    m = _base()
    m["execution"]["ordered"].append("DUR-01")
    dirty = tmp_path / "dirty.yml"
    dirty.write_text(yaml.safe_dump(m, sort_keys=False), encoding="utf-8")
    assert main([str(dirty)]) == 1

    assert main([str(tmp_path / "does-not-exist.yml")]) == 2

    # Deterministic: identical invocations produce byte-identical JSON reports.
    cmd = [sys.executable, "scripts/sol_commission_lint.py", str(dirty), "--json"]
    r1 = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    r2 = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r1.returncode == 1 and r1.stdout == r2.stdout
    parsed = json.loads(r1.stdout)
    assert any(f["name"] == "HANDOFF_REPLAY_COLLISION" for f in parsed["findings"])
