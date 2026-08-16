"""Phase 2b contract: Agent OS readiness annotates the canonical agenda.

The bridge is deliberately additive and fail-open.  Readiness may describe whether
an explicitly-linked workstream/wave can run, but it must never create, remove, or
reorder an Improvement Agenda item.  Existing constructors have no truthful join
keys yet, so they remain explicit N/A rather than guessing from prose.
"""
from __future__ import annotations

import ast
import hashlib
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import bot  # noqa: F401 -- put the pinned Macro engine on sys.path
import pytest
from brain import improvement_agenda as A


ROOT = Path(__file__).resolve().parent.parent
AGENDA_HTML = (ROOT / "app" / "static" / "agenda.html").read_text(encoding="utf-8")
WEB_SOURCE = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
SCHEDULER_SOURCE = (ROOT / "app" / "scheduler.py").read_text(encoding="utf-8")
CI_SOURCE = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _raw_item(item_id: str, score: float, agentos_ref: dict | None) -> dict:
    return {
        "id": item_id,
        "class": A.CLASS_COST,
        "title": item_id,
        "evidence": [f"evidence for {item_id}"],
        "suggested_fix": "fix it",
        "fix_type": A.FIX_CODE,
        "expected_impact": "improves the system",
        "owner": A.OWNER_OPUS,
        "rank_score": score,
        "agentos_ref": agentos_ref,
    }


def _only_items(monkeypatch, rows: list[dict]) -> None:
    """Make build() deterministic with only the supplied synthetic source rows."""
    source_names = (
        "_from_journal", "_from_benchmark", "_from_book_lifecycle",
        "_from_validation", "_from_cost_guard", "_from_deploy_lag",
        "_from_model_drift", "_from_nw_reflection", "_from_experiment_registry",
        "_from_experiment_tristate",
    )
    for name in source_names:
        monkeypatch.setattr(A, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(A, "_from_calibration", lambda *args, **kwargs: [
        {**row, "agentos_ref": (
            dict(row["agentos_ref"]) if isinstance(row.get("agentos_ref"), dict)
            else row.get("agentos_ref")
        )}
        for row in rows
    ])
    monkeypatch.setattr(A, "_from_shadow", lambda *args, **kwargs: [])
    monkeypatch.setattr(A, "_from_accruing_experiments", lambda *args, **kwargs: [])
    monkeypatch.setattr(A, "_prior_agenda", lambda *args, **kwargs: {})


def _bridge(monkeypatch, brief: dict | None, warnings: list[str] | None = None) -> None:
    macro_root = ROOT.parent / "macro-fixture"
    monkeypatch.setattr(
        A,
        "_agentos_bridge",
        lambda: SimpleNamespace(
            DEFAULT_TIMEOUT=60,
            resolve_macro_root=lambda explicit, environ, repo_root: (
                macro_root,
                "flag",
                [{"via": "flag", "path": str(macro_root), "usable": True, "reason": None}],
            ),
            collect_brief=lambda root, **kwargs: (brief, list(warnings or [])),
            _git_sha=lambda root: "a" * 40,
        ),
    )


def _envelope(records: list[dict], *, degraded: list[str] | None = None) -> dict:
    return {
        "schema": "agentos.readiness.v1",
        "records": records,
        "degraded": list(degraded or []),
        # Additive producer fields must not break an older tolerant consumer.
        "future_addition": {"ignored": True},
    }


def _record(
    workstream: str,
    wave: str | None,
    state: str,
    *,
    reason_code: str = "dependencies_satisfied",
) -> dict:
    return {
        "workstream": workstream,
        "wave": wave,
        "state": state,
        "reason_code": reason_code,
        "reason": f"{workstream} {wave or 'workstream'} is {state}",
        "depends_on": ["WS:FOUNDATION"],
        "unmet_dependencies": [] if state == "ready" else ["WS:FOUNDATION"],
        "source": f"agentos/workstreams/WS-{workstream}.md",
        "future_record_field": "ignored",
    }


def _rank_receipt(agenda: dict) -> list[tuple]:
    return [
        (it["id"], it["rank"], it["rank_score"], it["first_seen"], it["age_weeks"])
        for it in agenda["items"]
    ]


def test_item_constructor_is_explicitly_unmapped_and_structured_na() -> None:
    item = A._item(
        "cost:test", A.CLASS_COST, "test", evidence=["receipt"],
        suggested_fix="fix", fix_type=A.FIX_CODE, expected_impact="impact",
        owner=A.OWNER_OPUS,
    )

    assert item["agentos_ref"] is None
    assert item["readiness"] == {
        "state": "not_applicable",
        "reason_code": "no_agentos_ref",
        "reason": "No explicit Agent OS reference; readiness is not applicable.",
        "depends_on": [],
        "unmet_dependencies": [],
    }


def test_valid_readiness_annotates_after_ranking_without_changing_rank_receipt(
    monkeypatch,
) -> None:
    rows = [
        _raw_item("cost:linked", 49.0, {"workstream": "AGENT-OS", "wave": "W2B"}),
        _raw_item("cost:unmapped", 48.0, None),
    ]
    _only_items(monkeypatch, rows)

    _bridge(monkeypatch, {"schema": "ceo_brief.v1"})
    without_readiness = A.build(date(2026, 8, 14), cio_rep={})

    readiness = _envelope([
        _record("AGENT-OS", None, "in_progress", reason_code="status_in_progress"),
        _record("AGENT-OS", "W2B", "ready"),
    ])
    _bridge(monkeypatch, {"schema": "ceo_brief.v1", "readiness": readiness})
    with_readiness = A.build(date(2026, 8, 14), cio_rep={})

    assert _rank_receipt(with_readiness) == _rank_receipt(without_readiness)
    linked, unmapped = with_readiness["items"]
    assert linked["readiness"] == {
        "state": "ready",
        "reason_code": "dependencies_satisfied",
        "reason": "AGENT-OS W2B is ready",
        "depends_on": ["WS:FOUNDATION"],
        "unmet_dependencies": [],
    }
    assert unmapped["agentos_ref"] is None
    assert unmapped["readiness"]["state"] == "not_applicable"
    assert with_readiness["readiness_input"] == {
        "schema": "agentos.readiness.v1",
        "available": True,
        "macro_root": "macro-fixture",
        "macro_sha": "a" * 40,
        "resolved_via": "flag",
        "degraded": [],
    }


def test_current_constructors_do_not_fabricate_prose_mappings(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(A, "_ROOT", tmp_path)
    monkeypatch.setattr(A, "_OUT", tmp_path / "agenda")
    monkeypatch.setattr(A, "_VALIDATION_DIR", tmp_path / "validation")
    item = A._from_calibration(date(2026, 8, 14), {
        "per_seat": [{
            "seat": "gate", "label": "GATE", "reputation": "overconfident",
            "multiplier": 0.6, "n_resolved": 30, "reliability": 0.4,
            "kpis": {"significant": True}, "recommendation": "tighten the gate",
        }],
    })[0]

    assert item["agentos_ref"] is None
    assert item["readiness"]["state"] == "not_applicable"
    assert item["readiness"]["reason_code"] == "no_agentos_ref"
    source_tree = ast.parse(Path(A.__file__).read_text(encoding="utf-8"))
    constructor_calls = [
        node for node in ast.walk(source_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_item"
    ]
    assert len(constructor_calls) >= 10
    assert all(
        not any(keyword.arg == "agentos_ref" for keyword in call.keywords)
        for call in constructor_calls
    ), "current constructors must not fabricate Agent OS mappings from prose"


def test_old_brief_without_readiness_fails_open(monkeypatch) -> None:
    _only_items(monkeypatch, [
        _raw_item("cost:linked", 40.0, {"workstream": "AGENT-OS", "wave": "W2B"}),
    ])
    _bridge(monkeypatch, {
        "schema": "ceo_brief.v1",
        "unblocked": [{"workstream": "AGENT-OS", "wave": "W2B"}],
    })

    agenda = A.build(date(2026, 8, 14), cio_rep={})

    assert agenda["n_items"] == 1
    assert agenda["readiness_input"]["available"] is False
    assert agenda["readiness_input"]["schema"] is None
    assert any("brief.readiness is absent" in row
               for row in agenda["readiness_input"]["degraded"])
    assert agenda["items"][0]["readiness"]["state"] == "unknown"
    assert agenda["items"][0]["readiness"]["reason_code"] == "macro_unavailable"


def test_valid_payload_with_no_exact_join_is_explicitly_unmapped(monkeypatch) -> None:
    _only_items(monkeypatch, [
        _raw_item("cost:linked", 40.0, {"workstream": "AGENT-OS", "wave": "W9"}),
    ])
    _bridge(monkeypatch, {
        "schema": "ceo_brief.v1",
        "readiness": _envelope(
            [_record("AGENT-OS", "W2B", "ready")],
            degraded=["one workstream record could not be projected"],
        ),
    }, warnings=["brief provenance is stale"])

    agenda = A.build(date(2026, 8, 14), cio_rep={})

    assert agenda["readiness_input"]["available"] is True
    assert agenda["readiness_input"]["degraded"] == [
        "brief provenance is stale",
        "one workstream record could not be projected",
    ]
    assert agenda["items"][0]["readiness"] == {
        "state": "unknown",
        "reason_code": "unmapped_ref",
        "reason": "No readiness record matched Agent OS reference AGENT-OS#W9.",
        "depends_on": [],
        "unmet_dependencies": [],
    }


def test_malformed_nonnull_item_reference_is_unknown_not_na(monkeypatch) -> None:
    _only_items(monkeypatch, [])
    monkeypatch.setattr(A, "_from_calibration", lambda *args, **kwargs: [
        A._item(
            "cost:bad-ref", A.CLASS_COST, "bad ref", evidence=["receipt"],
            suggested_fix="fix", fix_type=A.FIX_CODE, expected_impact="impact",
            owner=A.OWNER_OPUS, agentos_ref={"workstream": "", "wave": "W2B"},
        ),
        A._item(
            "cost:whitespace-ref", A.CLASS_COST, "bad ref", evidence=["receipt"],
            suggested_fix="fix", fix_type=A.FIX_CODE, expected_impact="impact",
            owner=A.OWNER_OPUS,
            agentos_ref={"workstream": " AGENT-OS", "wave": "W2B"},
        ),
    ])
    _bridge(monkeypatch, {
        "schema": "ceo_brief.v1",
        "readiness": _envelope([_record("AGENT-OS", "W2B", "ready")]),
    })

    agenda = A.build(date(2026, 8, 14), cio_rep={})

    assert agenda["n_items"] == 2, "a malformed optional ref must not drop its source rows"
    for item in agenda["items"]:
        assert item["agentos_ref"] is None
        assert item["readiness"]["state"] == "unknown"
        assert item["readiness"]["reason_code"] == "malformed_ref"


def test_rank_invariant_fails_open_and_retains_original_priority(monkeypatch) -> None:
    _only_items(monkeypatch, [
        _raw_item("cost:first", 42.0, {"workstream": "AGENT-OS", "wave": "W2B"}),
        _raw_item("cost:second", 41.0, None),
    ])
    _bridge(monkeypatch, {
        "schema": "ceo_brief.v1",
        "readiness": _envelope([_record("AGENT-OS", "W2B", "ready")]),
    })

    def corrupt_rank(items, index, failure_code):
        items.reverse()
        items[0]["rank"] = 999
        return items

    monkeypatch.setattr(A, "_annotate_readiness", corrupt_rank)

    agenda = A.build(date(2026, 8, 14), cio_rep={})

    assert [(row["id"], row["rank"]) for row in agenda["items"]] == [
        ("cost:first", 1),
        ("cost:second", 2),
    ]
    assert all(row["readiness"]["reason_code"] == "invariant_violation"
               for row in agenda["items"])
    assert agenda["readiness_input"]["available"] is False
    assert any("frozen rank invariant" in row
               for row in agenda["readiness_input"]["degraded"])


def test_missing_macro_root_fails_open(monkeypatch) -> None:
    _only_items(monkeypatch, [
        _raw_item("cost:linked", 41.0, {"workstream": "AGENT-OS", "wave": "W2B"}),
        _raw_item("cost:unmapped", 40.0, None),
    ])
    monkeypatch.setattr(
        A,
        "_agentos_bridge",
        lambda: SimpleNamespace(
            DEFAULT_TIMEOUT=60,
            resolve_macro_root=lambda explicit, environ, repo_root: (
                None,
                None,
                [{"via": "sibling", "path": "/missing", "usable": False, "reason": "missing"}],
            ),
        ),
    )

    agenda = A.build(date(2026, 8, 14), cio_rep={})

    assert agenda["n_items"] == 2
    assert agenda["readiness_input"]["available"] is False
    assert agenda["readiness_input"]["macro_root"] is None
    by_id = {row["id"]: row for row in agenda["items"]}
    assert by_id["cost:linked"]["readiness"]["state"] == "unknown"
    assert by_id["cost:linked"]["readiness"]["reason_code"] == "macro_unavailable"
    assert by_id["cost:unmapped"]["readiness"]["state"] == "not_applicable"


def test_public_readiness_provenance_redacts_absolute_paths(monkeypatch, tmp_path) -> None:
    macro = tmp_path / "private-macro-checkout"
    warning = f"agentos brief could not be launched: {macro}/scripts/agentos.py"
    monkeypatch.setattr(
        A,
        "_agentos_bridge",
        lambda: SimpleNamespace(
            DEFAULT_TIMEOUT=60,
            resolve_macro_root=lambda explicit, environ, repo_root: (
                macro,
                "env",
                [{"via": "env", "path": str(macro), "usable": True, "reason": None}],
            ),
            collect_brief=lambda root, **kwargs: (None, [warning]),
            _git_sha=lambda root: None,
        ),
    )

    _, readiness_input, failure = A._load_agentos_readiness()
    serialized = json.dumps(readiness_input, sort_keys=True)

    assert failure == "macro_unavailable"
    assert readiness_input["macro_root"] == "private-macro-checkout"
    assert readiness_input["resolved_via"] == "env"
    assert str(macro) not in serialized
    assert str(tmp_path) not in serialized
    assert "env" in serialized
    assert "could not be launched" in serialized


def test_malformed_and_duplicate_readiness_payloads_fail_open(monkeypatch) -> None:
    _only_items(monkeypatch, [
        _raw_item("cost:linked", 40.0, {"workstream": "AGENT-OS", "wave": "W2B"}),
    ])
    bad_payloads = [
        {"schema": "agentos.readiness.v0", "records": [], "degraded": []},
        {"schema": "agentos.readiness.v1", "records": "not-a-list", "degraded": []},
        _envelope([{"workstream": "AGENT-OS", "wave": "W2B"}]),
        _envelope([
            _record("AGENT-OS", "W2B", "ready"),
            _record("AGENT-OS", "W2B", "blocked", reason_code="unmet_dependencies"),
        ]),
    ]

    for payload in bad_payloads:
        _bridge(monkeypatch, {"schema": "ceo_brief.v1", "readiness": payload})
        agenda = A.build(date(2026, 8, 14), cio_rep={})
        assert agenda["n_items"] == 1
        assert agenda["readiness_input"]["available"] is False
        assert agenda["readiness_input"]["degraded"]
        assert agenda["items"][0]["readiness"]["state"] == "unknown"
        assert agenda["items"][0]["readiness"]["reason_code"] == "malformed_payload"


def test_api_agenda_returns_readiness_contract_verbatim(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.web import router

    artifact = {
        "schema_version": "improvement_agenda.v1",
        "as_of": "2026-08-14",
        "n_items": 1,
        "class_counts": {"cost-guard": 1},
        "owners": {"opus-session": 1},
        "readiness_input": {
            "schema": "agentos.readiness.v1",
            "available": True,
            "macro_root": "macro",
            "macro_sha": "b" * 40,
            "resolved_via": "env",
            "degraded": [],
        },
        "items": [{
            "id": "cost:linked",
            "rank": 1,
            "agentos_ref": {"workstream": "AGENT-OS", "wave": "W2B"},
            "readiness": {
                "state": "blocked",
                "reason_code": "unmet_dependencies",
                "reason": "W2B waits on W2A",
                "depends_on": ["WS:AGENT-OS#W2A"],
                "unmet_dependencies": ["WS:AGENT-OS#W2A"],
            },
        }],
    }
    monkeypatch.setattr(A, "latest", lambda: artifact)
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app, raise_server_exceptions=True).get("/api/agenda")

    assert response.status_code == 200
    assert response.json() == artifact
    assert "/srv/macro" not in response.text


def test_markdown_renders_non_ranked_readiness_provenance_health_and_item_parity() -> None:
    agenda = {
        "schema_version": "improvement_agenda.v1",
        "as_of": "2026-08-14",
        "n_items": 2,
        "class_counts": {"cost-guard": 2},
        "owners": {A.OWNER_SELF: 0, A.OWNER_OPUS: 2, A.OWNER_FABLE: 0},
        "readiness_input": {
            "schema": "agentos.readiness.v1",
            "available": True,
            "macro_root": "macro",
            "macro_sha": "b" * 40,
            "resolved_via": "env",
            "degraded": ["active-build join is stale", "P0 join is unavailable"],
        },
        "items": [
            {
                **_raw_item(
                    "cost:first", 42.0,
                    {"workstream": "AGENT-OS", "wave": "W2B"},
                ),
                "rank": 1,
                "first_seen": "2026-08-01",
                "age_weeks": 1,
                "readiness": {
                    "state": "blocked",
                    "reason_code": "unmet_dependencies",
                    "reason": "W2B waits on W2",
                    "depends_on": ["WS:AGENT-OS#W2"],
                    "unmet_dependencies": ["WS:AGENT-OS#W2"],
                },
            },
            {
                **_raw_item("cost:second", 41.0, None),
                "rank": 2,
                "first_seen": "2026-08-14",
                "age_weeks": 0,
                "readiness": A._not_applicable_readiness(),
            },
        ],
    }
    before = _rank_receipt(agenda)

    markdown = A._md(agenda)

    assert "## Agent OS readiness input (non-ranked)" in markdown
    assert "**Health.** DEGRADED" in markdown
    assert "**Available.** yes" in markdown
    assert "**Schema.** `agentos.readiness.v1`" in markdown
    assert "**Macro root.** `macro`" in markdown
    assert f"**Macro SHA.** `{'b' * 40}`" in markdown
    assert "**Resolved via.** `env`" in markdown
    assert "- active-build join is stale" in markdown
    assert "- P0 join is unavailable" in markdown
    assert "**Agent OS reference.** `AGENT-OS#W2B`" in markdown
    assert "**Agent OS reference.** N/A" in markdown
    assert "**Dependencies.** WS:AGENT-OS#W2" in markdown
    assert "**Unmet dependencies.** WS:AGENT-OS#W2" in markdown
    assert markdown.index("## 1. cost:first") < markdown.index("## 2. cost:second")
    assert _rank_receipt(agenda) == before


def test_run_cio_reuses_prebuilt_agenda_and_performs_one_read(monkeypatch, tmp_path) -> None:
    from scripts import run_cio

    monkeypatch.setattr(A, "_OUT", tmp_path / "agenda")
    cio_review = {"as_of": "2026-08-14", "per_seat": []}
    monkeypatch.setattr(
        run_cio.cio,
        "write",
        lambda asof, narrate=True: {"ok": True, "review": cio_review},
    )
    artifact = {
        "schema_version": "improvement_agenda.v1",
        "as_of": "2026-08-14",
        "n_items": 0,
        "class_counts": {},
        "owners": {},
        "items": [],
        "readiness_input": {
            "schema": "agentos.readiness.v1",
            "available": True,
            "macro_root": "macro",
            "macro_sha": "c" * 40,
            "resolved_via": "env",
            "degraded": [],
        },
        "note": "advisory only",
    }
    build_calls: list[tuple] = []

    def fake_build(asof, *, cio_rep=None):
        build_calls.append((asof, cio_rep))
        return artifact

    monkeypatch.setattr(A, "build", fake_build)

    result = run_cio.run(date(2026, 8, 14), with_agenda=True, narrate=False)

    assert build_calls == [(date(2026, 8, 14), cio_review)]
    assert result["agenda"]["ok"] is True
    assert result["agenda"]["n_items"] == 0
    persisted = (tmp_path / "agenda" / "2026-08-14.json").read_text(encoding="utf-8")
    assert '"macro_sha": "' + ("c" * 40) + '"' in persisted


def test_real_bridge_read_is_no_remember_and_writes_nothing(monkeypatch, tmp_path) -> None:
    """Exercise the real PR #44 collector, including its load-bearing write trap."""
    macro = tmp_path / "macro"
    (macro / "agentos").mkdir(parents=True)
    scripts = macro / "scripts"
    scripts.mkdir()
    (scripts / "agentos.py").write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if "--no-remember" not in sys.argv[1:]:
    marker = root / "data" / "governance" / ".ceo_brief_last"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("agenda wrote here\\n", encoding="utf-8")

print(json.dumps({
    "schema": "ceo_brief.v1",
    "readiness": {
        "schema": "agentos.readiness.v1",
        "records": [{
            "workstream": "AGENT-OS",
            "wave": "W2B",
            "state": "ready",
            "reason_code": "dependencies_satisfied",
            "reason": "all declared dependencies are satisfied",
            "depends_on": [],
            "unmet_dependencies": [],
            "source": "agentos/workstreams/WS-AGENT-OS.md"
        }],
        "degraded": []
    }
}, sort_keys=True))
""",
        encoding="utf-8",
    )

    def snapshot() -> dict[str, str]:
        return {
            path.relative_to(macro).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(macro.rglob("*")) if path.is_file()
        }

    monkeypatch.setenv("MASTERMIND_MACRO_ROOT", str(macro))
    before = snapshot()

    index, readiness_input, failure = A._load_agentos_readiness()

    assert failure is None
    assert index[("AGENT-OS", "W2B")]["state"] == "ready"
    assert readiness_input["available"] is True
    assert readiness_input["resolved_via"] == "env"
    assert readiness_input["macro_root"] == "macro"
    assert str(macro) not in str(readiness_input)
    assert snapshot() == before
    assert not (macro / "data" / "governance" / ".ceo_brief_last").exists()


def test_agenda_read_bridge_has_no_network_or_execution_plane_imports() -> None:
    source = Path(A.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)

    network_roots = {"requests", "httpx", "urllib", "socket"}
    assert not {
        name for name in imports if name.split(".", 1)[0] in network_roots
    }
    execution_modules = {
        name for name in imports
        if name.startswith("control_plane.")
        and name != "control_plane.ceo_boot_packet"
    }
    assert not execution_modules
    assert "subprocess" not in imports, "agenda must delegate subprocess policy to PR #44"


def test_agenda_ui_api_scheduler_docs_and_ci_expose_native_readiness() -> None:
    assert 'class="pill readiness-' in AGENDA_HTML
    assert "Readiness" in AGENDA_HTML
    assert "not_applicable" in AGENDA_HTML
    assert "unmet_dependencies" in AGENDA_HTML
    assert "readiness.depends_on" in AGENDA_HTML
    assert "readiness_input" in AGENDA_HTML
    assert "items.sort(" not in AGENDA_HTML
    assert 'readinessState === "ready"' not in AGENDA_HTML
    assert 'hasOwnProperty.call(it, "readiness")' in AGENDA_HTML
    assert 'reason_code: "legacy_artifact"' in AGENDA_HTML
    assert "Rebuild required" in AGENDA_HTML
    render_path = AGENDA_HTML.split("function renderItem", 1)[1].split("fetch(", 1)[0]
    assert ".sort(" not in render_path
    assert "Agent OS readiness" in WEB_SOURCE
    assert "Agent OS readiness" in SCHEDULER_SOURCE
    assert "scripts/ci_pytest.py" in CI_SOURCE
    assert "Run repository test gate" in CI_SOURCE
    discovered = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests").rglob("test_*.py")
        if path.is_file()
    }
    assert "tests/test_agentos_readiness_agenda.py" in discovered
