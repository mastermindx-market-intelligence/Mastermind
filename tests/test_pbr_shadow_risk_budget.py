"""PBR L-S5 — evidence-conditioned shadow risk budget (spec §5.3, rulings Q2/Q3/CR-R7/SR-1).

Baseline tests pass on master and document the gap (sizing is purely
categorical).  Contract tests import the new module inside the test body, so
on code without ``brain/shadow_risk_budget.py`` they FAIL with
ModuleNotFoundError.  No network, no live data; the config is read, never
modified.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
from pathlib import Path

import pytest
import yaml

from brain import decision_submission

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "pbr" / "decision_cases"
CONFIG = ROOT / "config" / "pbr_shadow_risk_budget.yml"

MU_ENTRY = "mu_2026-10-02_entry.json"
MU_AMENDMENT = "mu_2026-10-05_amendment.json"
CN_SIZING = "cn_688062_2026-08-12_sizing.json"
XOM_CONTROL = "xom_2026-08-12_positive_control.json"
PLANLESS = "mu_2026-10-22_planless_summary.json"

NEW_MODULE_RELS = ("brain/facts.py", "brain/thesis_store.py", "brain/shadow_risk_budget.py")
NEW_MODULE_NAMES = ("brain.facts", "brain.thesis_store", "brain.shadow_risk_budget")
SHADOW_LEAF_NAMES = ("facts", "thesis_store", "shadow_risk_budget")
SCAN_ROOTS = ("brain", "bot", "portfolio", "app", "loop", "data_layer", "bridge")

# CR-R7: the pinned schema/version constants.
EXPECTED_CONSTANTS = {
    "brain.facts": {"SCHEMA_VERSION": "pbr.fact.v1", "REFERENCE_MARK_SCHEMA": "pbr.reference_mark.v1"},
    "brain.thesis_store": {
        "SCHEMA_VERSION": "pbr.thesis.v1",
        "AMENDMENT_SCHEMA_VERSION": "pbr.thesis_amendment.v1",
        "OBSERVATION_SCHEMA_VERSION": "pbr.thesis_observation.v1",
    },
    "brain.shadow_risk_budget": {"PARAMS_SCHEMA": "pbr.shadow_risk_budget_params.v1"},
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _record_by_line(fix: dict, line: int) -> dict:
    for record in fix["records"]:
        if record["line_index_0based"] == line:
            return record
    raise AssertionError(f"line {line} not among records")


def _scan(node, needles):
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found |= _scan(key, needles)
            found |= _scan(value, needles)
    elif isinstance(node, (list, tuple)):
        for value in node:
            found |= _scan(value, needles)
    elif isinstance(node, str):
        for needle in needles:
            if needle in node:
                found.add(needle)
    return found


def _config_raw() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


# Declared per-case shadow-budget inputs.  Evidence-quality inputs are typed
# test data (spec §5 test rules: facts are hand-built from fixture fields under
# SR-1 rules (2)/(3); no prose parser this wave).  The 688062.SS single-family
# and degraded-coverage declaration follows the recorded `single-source` /
# `starter` digest terms and the case record; the XOM multi-family declaration
# follows its six-entry recorded source_provenance.
CASE_INPUTS = {
    MU_ENTRY: dict(action="add", position_role="starter", categorical_cap=0.10,
                   cap_source="autonomous deterministic_conviction_allocator.v2 conviction_caps.medium (recorded add weight 0.10)",
                   source_families=2, primary_mix="mixed", technical_coverage="ok"),
    MU_AMENDMENT: dict(action="hold", position_role="established", categorical_cap=0.15,
                       cap_source="autonomous deterministic_conviction_allocator.v2 conviction_caps.high (recorded hold conviction high)",
                       source_families=2, primary_mix="mixed", technical_coverage="ok"),
    PLANLESS: dict(action="exit", position_role="risk_reduction", categorical_cap=0.15,
                   cap_source="autonomous deterministic_conviction_allocator.v2 conviction_caps.high (conviction in force at the exit)",
                   source_families=1, primary_mix="derived_only", technical_coverage="degraded"),
    CN_SIZING: dict(action="add", position_role="starter", categorical_cap=0.12,
                    cap_source="regional deterministic_incremental_regional_allocator.v1 conviction_caps.medium (cap_reference line 450; recorded weight 0.12)",
                    source_families=1, primary_mix="derived_only", technical_coverage="degraded"),
    XOM_CONTROL: dict(action="add", position_role="starter", categorical_cap=0.10,
                      cap_source="autonomous deterministic_conviction_allocator.v2 conviction_caps.medium (recorded row-38 weight 0.10)",
                      source_families=3, primary_mix="primary_dominant", technical_coverage="ok"),
}


def _inputs(case: str, ticker: str, book: str, **overrides) -> dict:
    inputs = {
        "book": book,
        "ticker": ticker,
        **CASE_INPUTS[case],
    }
    inputs.update(overrides)
    return inputs


# ───────────────────────────── baseline (master) ─────────────────────────────


def test_baseline_master_sizing_is_purely_categorical():
    for name, line, book, policy in (
        (CN_SIZING, 35, "china", "deterministic_incremental_regional_allocator.v1"),
        (MU_ENTRY, 75, "autonomous", "deterministic_conviction_allocator.v2"),
    ):
        fix = _load(name)
        holding = _record_by_line(fix, line)["case_holding"]
        row = {
            "ticker": holding["ticker"],
            "conviction": holding["conviction"],
            "action_effective": "add",
            "_protected_weight": 0.0,
        }
        sizing = decision_submission._allocate_deterministically(book, [row], "caution")
        assert row["weight"] == holding["weight"], (
            f"{name}: categorical sizing must reproduce the recorded weight"
        )
        assert row["weight_source"] == policy
        assert sizing["policy"] == policy
        assert sizing["conviction_caps"]["medium"] == holding["weight"]
        # The audit vocabulary carries no evidence term at all.
        assert set(sizing) == {
            "policy",
            "posture_target_gross",
            "max_single_weight",
            "conviction_caps",
            "protected_gross",
            "model_weight_is_advisory_only",
            "no_forced_marginal_names",
        }
        assert (
            _scan(
                sizing,
                [
                    "evidence",
                    "eligible_weight",
                    "risk_budget",
                    "role_budget",
                    "concentration",
                    "fact_verification",
                ],
            )
            == set()
        )


# ────────────────────────────── contract tests ───────────────────────────────


def test_waterfall_fully_explained_for_all_cases():
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    cases = {
        MU_ENTRY: ("MU", "autonomous"),
        MU_AMENDMENT: ("MU", "autonomous"),
        PLANLESS: ("MU", "autonomous"),
        CN_SIZING: ("688062.SS", "china"),
        XOM_CONTROL: ("XOM", "autonomous"),
    }
    for name, (ticker, book) in cases.items():
        assessment = shadow_risk_budget.assess(_inputs(name, ticker, book), cfg)
        assert assessment["schema"] == "pbr.shadow_risk_budget_assessment.v1", name
        assert assessment["live"] is False
        assert assessment["config_version"] == cfg["version"]
        waterfall = assessment["waterfall"]
        assert [step["step"] for step in waterfall] == [
            "categorical_cap",
            "role_budget",
            "evidence_haircut",
            "concentration_limit",
            "eligible_weight",
        ], name
        for step in waterfall:
            assert isinstance(step["value"], (int, float)), (name, step["step"])
            assert isinstance(step.get("explanation"), str) and step["explanation"].strip()
        eligible = assessment["eligible_weight"]
        for step in waterfall[:4]:
            assert eligible <= step["value"] + 1e-9, (name, step["step"])
        assert eligible == pytest.approx(min(step["value"] for step in waterfall[:4]))
        assert assessment["assumptions"] is not None


def test_starter_single_source_budget_below_categorical_cap():
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    assessment = shadow_risk_budget.assess(
        _inputs(CN_SIZING, "688062.SS", "china"), cfg
    )
    # Spec §4.3 audit mechanism 2: strict inequality only — never a number.
    assert assessment["eligible_weight"] < 0.12


def test_uncalibrated_probability_has_zero_influence():
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    without = shadow_risk_budget.assess(_inputs(CN_SIZING, "688062.SS", "china"), cfg)
    with_prob = shadow_risk_budget.assess(
        _inputs(
            CN_SIZING,
            "688062.SS",
            "china",
            stated_probability={"value": 0.62, "calibration_status": "uncalibrated"},
        ),
        cfg,
    )
    assert with_prob["eligible_weight"] == without["eligible_weight"]
    assert with_prob["waterfall"] == without["waterfall"]
    codes = {a["code"] for a in with_prob["assumptions"]}
    assert "stated_probability_zero_influence" in codes
    assert "stated_probability_zero_influence" not in {a["code"] for a in without["assumptions"]}
    # Even a calibrated status is not wired to sizing in this wave (law 11).
    calibrated = shadow_risk_budget.assess(
        _inputs(
            CN_SIZING,
            "688062.SS",
            "china",
            stated_probability={"value": 0.62, "calibration_status": "calibrated"},
        ),
        cfg,
    )
    assert calibrated["eligible_weight"] == without["eligible_weight"]


def test_xom_positive_control_remains_eligible():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    assessment = shadow_risk_budget.assess(_inputs(XOM_CONTROL, "XOM", "autonomous"), cfg)
    assert assessment["eligible_weight"] > 0
    for step in assessment["waterfall"][:4]:
        assert step["value"] > 0, step["step"]

    # Perturbation: the price levels pushed outside the band without a bridge →
    # BASIS_UNRECONCILED propagates into the haircut; the machinery is
    # conditional on the recorded evidence, never on the name.  15.83 is a
    # synthetic perturbation value (a tenth of the mark), not a fixture value.
    fix = _load(XOM_CONTROL)
    record = _record_by_line(fix, 38)
    digest = record["case_holding"]["falsifier"]
    claim = "<redacted synthetic perturbation: level a tenth of the qualified mark, no bridge>"
    instrument = {"ticker": "XOM", "book": "autonomous", "venue": None,
                  "identity_status": record["case_holding"]["identity_status"]}
    fact = {
        "fact_id": facts.fact_id_for(claim, instrument, "price_level", "synthetic-perturbation"),
        "claim_text": claim,
        "kind": "price_level",
        "instrument": instrument,
        "value": 15.83,
        "unit": "price_per_share",
        "currency": "USD",
        "period": None,
        "published_at": None,
        "available_at": None,
        "observed_at": None,
        "basis": {"adjustment": "unadjusted_close", "split_assumption": "current_shares", "currency": "USD"},
        "source_class": "model_interpretation",
        "source_family": "decision_package",
        "source_ref": "synthetic-perturbation",
        "decision_asof": record["row"]["asof"],
    }
    mark = {
        "schema": facts.REFERENCE_MARK_SCHEMA,
        "value": 158.03,
        "currency": "USD",
        "basis": {"adjustment": "unadjusted_close", "split_assumption": "current_shares"},
        "symbol": "XOM",
        "asof": record["row"]["asof"],
        "source": facts.MARK_SOURCE_ECON_UNION_MARK,
        "store_ref": "test-double",
        "mark_source": "test-double",
    }
    outcome = facts.verify_fact(fact, reference_mark=mark, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.BASIS_UNRECONCILED
    perturbed = shadow_risk_budget.assess(
        _inputs(XOM_CONTROL, "XOM", "autonomous", fact_outcomes=[outcome]), cfg
    )
    assert perturbed["eligible_weight"] == 0.0
    evidence_step = perturbed["waterfall"][2]
    assert evidence_step["drivers"]["fact_factor"] == 0.0
    assert facts.VerificationOutcome.BASIS_UNRECONCILED in evidence_step["drivers"]["blocking_verdicts"]


def test_config_frozen_ex_ante_and_versioned(tmp_path):
    import brain.shadow_risk_budget as shadow_risk_budget

    raw = _config_raw()
    assert raw["schema"] == "pbr.shadow_risk_budget_params.v1"
    assert isinstance(raw["version"], int) and raw["version"] >= 1
    assert raw["frozen_at"]
    assert raw["freeze_owner"] == "pbr-seat"  # seat ruling Q3
    # load_params accepts the real file...
    cfg = shadow_risk_budget.load_params(CONFIG)
    assert cfg["schema"] == raw["schema"]
    # ...and refuses a missing/late frozen_at.
    mutated = copy.deepcopy(raw)
    mutated.pop("frozen_at")
    path = tmp_path / "missing_frozen_at.yml"
    path.write_text(yaml.safe_dump(mutated), encoding="utf-8")
    with pytest.raises(shadow_risk_budget.ParamsError):
        shadow_risk_budget.load_params(path)
    # ...and a bare justification on any parameter.
    mutated = copy.deepcopy(raw)
    mutated["role_loss_budgets"]["starter"]["max_adverse_nav_fraction"]["justification"] = ""
    path = tmp_path / "bare_justification.yml"
    path.write_text(yaml.safe_dump(mutated), encoding="utf-8")
    with pytest.raises(shadow_risk_budget.ParamsError):
        shadow_risk_budget.load_params(path)
    mutated = copy.deepcopy(raw)
    mutated["evidence_multiplier"]["multiplier_floor"].pop("justification")
    path = tmp_path / "missing_justification.yml"
    path.write_text(yaml.safe_dump(mutated), encoding="utf-8")
    with pytest.raises(shadow_risk_budget.ParamsError):
        shadow_risk_budget.load_params(path)


def test_config_names_no_case_ticker():
    text = CONFIG.read_text(encoding="utf-8")
    for needle in ("688062", "Micron", "XOM", "Exxon", "22196"):
        assert needle not in text, needle
    assert re.search(r"\bMU\b", text) is None


def test_new_modules_have_no_live_write_path(tmp_path):
    import brain.facts
    import brain.shadow_risk_budget
    import brain.thesis_store

    stdlib_allowed = {
        "__future__", "annotations", "hashlib", "json", "math", "re", "datetime",
        "pathlib", "typing", "ast", "yaml", "collections", "dataclasses", "enum",
        "functools", "itertools", "os", "sys",
    }
    forbidden_roots = (
        "brain.decision_submission", "brain.ledger", "portfolio", "bot", "app",
        "loop", "data_layer", "bridge",
        "requests", "httpx", "urllib", "socket", "http", "aiohttp", "websockets",
        "ftplib", "telnetlib", "smtplib", "xmlrpc", "subprocess",
    )
    seen_roots = set()
    for rel in NEW_MODULE_RELS:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = ("brain." * node.level) + (node.module or "")
                modules = [base] if node.module else []
                if node.module in (None, "", "brain"):
                    modules += [f"brain.{alias.name}" for alias in node.names]
                elif node.level:
                    modules += [f"{base}.{alias.name}" for alias in node.names]
            for module in modules:
                top = module.split(".")[0]
                seen_roots.add(top)
                for forbidden in forbidden_roots:
                    assert module != forbidden and not module.startswith(forbidden + "."), (
                        rel, module
                    )
    unexpected = seen_roots - stdlib_allowed - {"brain"}
    assert unexpected == set(), unexpected

    # No module-level data path: no Path constant, no slash-carrying constant.
    for module in (brain.facts, brain.thesis_store, brain.shadow_risk_budget):
        for name, value in vars(module).items():
            if not name.isupper():
                continue
            assert not isinstance(value, Path), (module.__name__, name)
            if isinstance(value, str):
                assert "/" not in value, (module.__name__, name, value)
                assert not value.startswith("data"), (module.__name__, name, value)

    # A full shadow round trip creates files ONLY under the caller's store_dir.
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    thesis = thesis_store.record_thesis(
        store,
        {
            "book": "autonomous",
            "ticker": "TEST",
            "episode_open_date": "2026-10-05",
            "entry_fill_ids": ["fill-1"],
            "why_now": "<redacted sha256=abc len=3 dates=none periods=none terms=none>",
            "fact_ids": [],
            "horizon": None,
            "falsifiers": ["<redacted sha256=def len=3 dates=none periods=none terms=none>"],
            "exit_conditions": ["<redacted sha256=012 len=3 dates=none periods=none terms=none>"],
            "position_role": "starter",
            "originating_decision_id": "decision.v1.test000000000000000",
            "created_at": "2026-10-05T00:00:00+00:00",
        },
    )
    thesis_store.record_amendment(
        store,
        {
            "thesis_id": thesis["thesis_id"],
            "changes": {"falsifier": {"old": "old", "new": "new"}},
            "reason_code": "SUPERSEDED",
            "evidence_refs": ["decision.v1.test000000000000000"],
            "effective_at": "2026-10-06",
            "recorded_at": "2026-10-06T00:00:00+00:00",
            "accountable_decision_id": "decision.v1.test000000000000001",
        },
        originating_decision_asof="2026-10-05",
    )
    prior_row = {"book": "autonomous", "ticker": "TEST", "decision_id": "d1", "asof": "2026-10-05",
                 "conviction": "medium"}
    new_row = dict(prior_row, decision_id="d2", asof="2026-10-06", conviction="high")
    verdict = thesis_store.check_continuity(store, prior_row, new_row)
    assert verdict["status"] == "ACCEPTED_NO_WATCHED_CHANGE"
    # The round trip created the three named append-only files under the
    # caller's store_dir — and nothing else anywhere (tmp_path/_experiments is
    # the conftest's own registry isolation fixture, not ours).
    assert sorted(p.name for p in store.iterdir()) == [
        "amendments.jsonl",
        "observations.jsonl",
        "theses.jsonl",
    ]
    ours = sorted(
        str(p.relative_to(tmp_path))
        for p in tmp_path.rglob("*")
        if p.is_file() and "_experiments" not in p.relative_to(tmp_path).parts
    )
    assert ours == [
        "store/amendments.jsonl",
        "store/observations.jsonl",
        "store/theses.jsonl",
    ]


def test_no_sizing_or_decision_path_imports_shadow_modules():
    violations = []
    scanned = 0
    for root in SCAN_ROOTS:
        for path in sorted((ROOT / root).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel in NEW_MODULE_RELS:
                continue
            scanned += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                candidates = []
                if isinstance(node, ast.Import):
                    candidates = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0:
                        if node.module:
                            candidates.append(node.module)
                        if node.module == "brain":
                            candidates += [f"brain.{alias.name}" for alias in node.names]
                    else:
                        # Relative imports resolve inside their package.
                        if node.module in SHADOW_LEAF_NAMES:
                            violations.append((rel, f"relative:{node.module}"))
                        candidates += [
                            f"{node.module}.{alias.name}"
                            for alias in node.names
                            if alias.name in SHADOW_LEAF_NAMES
                        ]
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # importlib.import_module("brain.facts") and friends.
                    if node.value in NEW_MODULE_NAMES:
                        violations.append((rel, node.value))
                for candidate in candidates:
                    if any(
                        candidate == name or candidate.startswith(name + ".")
                        for name in NEW_MODULE_NAMES
                    ):
                        violations.append((rel, candidate))
    assert scanned > 50
    assert violations == [], violations


def test_schema_constants_pinned():
    import brain.facts
    import brain.shadow_risk_budget
    import brain.thesis_store

    pins = {
        "brain.facts": brain.facts,
        "brain.thesis_store": brain.thesis_store,
        "brain.shadow_risk_budget": brain.shadow_risk_budget,
    }
    for module_name, expected in EXPECTED_CONSTANTS.items():
        module = pins[module_name]
        for attr, literal in expected.items():
            assert getattr(module, attr) == literal, (module_name, attr)
    assert brain.facts.MARK_SOURCE_ECON_UNION_MARK == "ECON_UNION_MARK"
    assert brain.facts.MARK_SOURCE_CALLER_SUPPLIED == "CALLER_SUPPLIED"
    assert brain.thesis_store.AMENDMENT_REASON_CODES == (
        "FALSIFIED",
        "TIME_STOP",
        "EXIT_PLAN_HIT",
        "SUPERSEDED",
        "MANUAL",
    )
    # The config's schema equals the params constant (CR-R7).
    assert _config_raw()["schema"] == brain.shadow_risk_budget.PARAMS_SCHEMA


def test_new_files_carry_no_original_prose():
    """ENV-GATED (SR-1): no original PM prose string — nor any 30-character span
    of one — occurs in the three new modules, the three new test files or the
    config.  Skips with an SR-1 reason when ``PBR_DECISION_CASE_INPUT_DIR`` is
    unset or its files are absent."""
    input_dir = Path(os.environ.get("PBR_DECISION_CASE_INPUT_DIR", "/nonexistent/pbr-decision-case-inputs"))
    inputs = (input_dir / "case_rows.jsonl", input_dir / "case_fills.jsonl")
    if not all(path.exists() for path in inputs):
        pytest.skip(
            f"SR-1: original capture extracts not present at {input_dir} "
            "(set PBR_DECISION_CASE_INPUT_DIR); production prose stays outside the repository"
        )

    def _leaves(node):
        if isinstance(node, dict):
            for value in node.values():
                yield from _leaves(value)
        elif isinstance(node, list):
            for value in node:
                yield from _leaves(value)
        elif isinstance(node, str):
            yield node

    originals = set()
    for path in inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for leaf in _leaves(json.loads(line)["row"]):
                if not any(ch.isspace() for ch in leaf):
                    continue
                for text in [leaf] + [part.strip() for part in leaf.split(". ")]:
                    if len(text) >= 30:
                        originals.add(text)

    targets = [ROOT / rel for rel in NEW_MODULE_RELS]
    targets += [
        ROOT / "tests" / "test_pbr_facts.py",
        ROOT / "tests" / "test_pbr_thesis_store.py",
        Path(__file__),
        CONFIG,
    ]
    corpus = "\n".join(target.read_text(encoding="utf-8") for target in targets)

    leaked = set()
    for text in originals:
        if text in corpus:
            leaked.add(text[:40])
        for start in range(len(text) - 30 + 1):
            span = text[start : start + 30]
            if span in corpus:
                leaked.add(span)
    assert leaked == set(), sorted(leaked)[:5]
