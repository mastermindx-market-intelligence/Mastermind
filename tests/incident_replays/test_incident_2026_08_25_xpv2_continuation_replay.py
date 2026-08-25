"""Incident replay — 2026-08-25 XPV2 continuation replay (Continuation Delta founding incident).

The hard property pinned here: the replay guard survives not merely a stale
old handoff, but the harder state in which a NEWER workstream reconciliation
(#6388) itself became stale hours later when the canonical carrier (#6337)
completed and merged. See fixtures/2026-08-25-xpv2-continuation-replay/README.md.

This is a commission-lint incident, not a trading-stack incident; the
canonical shapes are lint findings, not dwell/severity/firm/cycle gates.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.sol_commission_lint import lint_file, main

FIX = Path(__file__).resolve().parent / "fixtures" / "2026-08-25-xpv2-continuation-replay"
BUNDLE = FIX / "current_context_bundle.json"


def _hard(findings) -> set[str]:
    return {f.name for f in findings if f.severity == "hard"}


def test_truth_fixture_matches_incident_identity():
    truth = json.loads((FIX / "github_truth.json").read_text(encoding="utf-8"))
    carrier = truth["carrier"]
    assert carrier["pr"] == 6337 and carrier["state"] == "MERGED"
    assert carrier["merge_sha"] == "8b303a58e8c0b807ef34d1913c4cacf5bb346e2d"
    assert carrier["verdict"] == "APPROVE_WITH_CONDITIONS"
    assert len(carrier["carried_conditions"]) == 5
    # The staleness that makes this the harder incident: the repaired-then-stale
    # workstream still recorded the pre-merge head.
    assert truth["stale_at_freeze"]["workstream_recorded_head"] == carrier["stale_recorded_head"]


def test_naive_copied_commission_stays_red_forever():
    """Failure shape 1: prior commission copied forward wholesale."""
    findings = lint_file(FIX / "naive_copied_commission.md", context_path=BUNDLE)
    hard = _hard(findings)
    assert "HANDOFF_REPLAY_COLLISION" in hard
    assert "SUPERSEDED_WORK_REOPENED" in hard


def test_naive_stale_derived_commission_stays_red_forever():
    """Failure shape 2 (the C2' shape): a commission lawfully derived from the
    stale-but-recently-repaired records. Internally consistent — only the
    repaired organizational do_not_redo set exposes it."""
    findings = lint_file(FIX / "naive_stale_derived_commission.md", context_path=BUNDLE)
    assert "DNR_COVERAGE_MISSING" in _hard(findings)


def test_naive_stale_derived_commission_is_internally_consistent_without_bundle():
    """Documents WHY the deterministic guard needs the organizational bundle:
    without it, shape 2 carries no self-contradiction the linter can see, and
    only DNR_COVERAGE_UNPROVEN warns that coverage was never proven. The
    procedural half (DURABLE_STATE_STALE in COLD_START/COMMISSION_WAVE) owns
    that judgment — the linter never fakes it."""
    findings = lint_file(FIX / "naive_stale_derived_commission.md")
    assert "DNR_COVERAGE_MISSING" not in _hard(findings)
    assert "DNR_COVERAGE_UNPROVEN" in {f.name for f in findings if f.severity == "warning"}


def test_lawful_continuation_lints_clean_with_current_bundle():
    findings = lint_file(FIX / "lawful_continuation.md", context_path=BUNDLE)
    assert _hard(findings) == set()
    assert main([str(FIX / "lawful_continuation.md"), "--agentos-context", str(BUNDLE)]) == 0


def test_r3c_conditions_exist_but_are_not_open_executable_work():
    """No R3C execution may become OPEN merely because five R3C-owned
    conditions exist: the lawful manifest holds them BLOCKED, and moving any
    of them into executable scope is disposition-illegal."""
    import copy

    import yaml

    text = (FIX / "lawful_continuation.md").read_text(encoding="utf-8")
    inside, buf = False, []
    for line in text.splitlines():
        if line.strip().startswith("```yaml"):
            inside = True
            continue
        if inside and line.strip().startswith("```"):
            break
        if inside:
            buf.append(line)
    manifest = yaml.safe_load("\n".join(buf))

    mutated = copy.deepcopy(manifest)
    mutated["execution"]["held"].remove("R3C-COND-01")
    mutated["execution"]["ordered"].append("R3C-COND-01")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "mutated.yml"
        p.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")
        assert "EXECUTION_DISPOSITION_ILLEGAL" in _hard(lint_file(p, context_path=BUNDLE))
