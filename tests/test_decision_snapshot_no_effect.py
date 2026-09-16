"""tests/test_decision_snapshot_no_effect.py — Task 7 whole-system negative proof.

Proves that one ``decision_snapshot.create_snapshot(...)`` call creates only its own
immutable shadow artifact and has zero effect on V2 book state, providers, network,
subprocesses, or hidden clocks. All filesystem roots are redirected to ``tmp_path``;
nothing here ever touches the real repository's data.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import stat
import subprocess
from pathlib import Path

import pytest

from portfolio import decision_snapshot as snapshots
from portfolio import decision_snapshot_contracts as c
from portfolio import decision_snapshot_sources as sources

_REPO_ROOT = Path(__file__).resolve().parent.parent

_S0_SOURCE_MODULES = (
    _REPO_ROOT / "portfolio" / "decision_snapshot_contracts.py",
    _REPO_ROOT / "portfolio" / "decision_snapshot_sources.py",
    _REPO_ROOT / "portfolio" / "decision_snapshot.py",
    _REPO_ROOT / "scripts" / "portfolio_decision_snapshot.py",
)

_CLOCK_SCANNED_MODULES = (
    _REPO_ROOT / "portfolio" / "decision_snapshot_contracts.py",
    _REPO_ROOT / "portfolio" / "decision_snapshot_sources.py",
    _REPO_ROOT / "portfolio" / "decision_snapshot.py",
)

_FORBIDDEN_IMPORT_MODULES = (
    "brain.client",
    "brain.provider_waterfall",
    "brain.key_rotor",
    "bot.settle",
    "bot.autonomous",
    "portfolio.paper_account",
    "portfolio.shadow_books",
    "portfolio.forward_evaluation",
)

_ALLOWED_PROJECT_IMPORTS = {
    "portfolio/decision_snapshot_contracts.py": {"control_plane.wake_events"},
    "portfolio/decision_snapshot_sources.py": {
        "control_plane.wake_events",
        "control_plane.contracts",
        "portfolio.decision_snapshot_contracts",
        "portfolio.registry",
    },
    "portfolio/decision_snapshot.py": {
        "control_plane.wake_events",
        "portfolio.decision_snapshot_contracts",
        "portfolio.decision_snapshot_sources",
    },
    "scripts/portfolio_decision_snapshot.py": {
        "control_plane.wake_events",
        "portfolio.decision_snapshot",
        "portfolio.decision_snapshot_contracts",
    },
}
_PROJECT_PACKAGE_ROOTS = (
    "portfolio", "brain", "bot", "control_plane", "app", "scripts", "loop",
    "data_layer", "bridge",
)

_V2_STATE_FILES = {
    "account.json": json.dumps({
        "starting_nav": 1_000_000.0,
        "cash": 812_345.67,
        "benchmark_symbol": "SPY",
        "positions": {
            "AAPL": {
                "shares": 120.0,
                "avg_cost": 178.32,
                "identity_status": "verified_common_stock",
                "holding_mark_source": "live_quote",
                "weight": 0.183,
            },
        },
    }, indent=2),
    "fills.jsonl": "\n".join([
        json.dumps({"ticker": "AAPL", "side": "buy", "shares": 120.0,
                     "price": 178.32, "asof": "2026-09-10T14:31:00Z"}),
        json.dumps({"ticker": "MSFT", "side": "sell", "shares": 40.0,
                     "price": 402.11, "asof": "2026-09-12T15:02:00Z"}),
    ]) + "\n",
    "nav_history.jsonl": "\n".join([
        json.dumps({"asof": "2026-09-14T20:00:00Z", "nav": 1_014_820.55, "cash": 812_345.67}),
        json.dumps({"asof": "2026-09-15T20:00:00Z", "nav": 1_017_204.12, "cash": 812_345.67}),
    ]) + "\n",
    "decisions.jsonl": json.dumps({
        "ticker": "AAPL", "action": "buy", "asof": "2026-09-10T14:30:00Z",
        "rationale": "confirmation",
    }) + "\n",
    "pending_orders.json": json.dumps({"orders": []}, indent=2),
    "pending_target.json": json.dumps({
        "target": {"AAPL": 0.18, "MSFT": 0.05},
        "asof": "2026-09-15T20:00:00Z",
        "queued_at": "2026-09-15T20:00:05Z",
        "portfolio_id": "autonomous",
    }, indent=2),
    "_pending_decision.json": json.dumps({
        "decision_id": "dec-20260915-0001",
        "target_sha256": "a" * 64,
        "decision_log_required": True,
    }, indent=2),
}


# ---------------------------------------------------------------------------
# Fixtures and small helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _hashes(paths) -> dict:
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _tree_fingerprint(root: Path) -> dict:
    """Map every path under ``root`` to a (kind, content-or-target) tuple.

    Catches a new file of any name, a deleted file, changed bytes in an existing
    file, and a directory/symlink type change — not just a ``*.json`` count.
    """
    fingerprint = {}
    if not root.exists():
        return fingerprint
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            fingerprint[rel] = ("symlink", os.readlink(path))
        elif path.is_dir():
            fingerprint[rel] = ("dir", None)
        elif path.is_file():
            fingerprint[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            fingerprint[rel] = ("other", None)
    return fingerprint


@pytest.fixture
def redirected_roots(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    macro = tmp_path / "macro"
    storage = tmp_path / "storage"
    repo.mkdir()
    macro.mkdir()
    storage.mkdir()
    monkeypatch.setattr(sources, "_ROOT", repo)
    monkeypatch.setattr(sources, "_V", macro)
    monkeypatch.setattr(snapshots, "_ROOT", storage)
    return {"repo": repo, "macro": macro, "storage": storage}


def _seed_v2_state(repo_root: Path) -> dict[str, Path]:
    book_dir = repo_root / "data" / "portfolios" / "autonomous"
    paths = {}
    for rel_name, content in _V2_STATE_FILES.items():
        path = book_dir / rel_name
        _write(path, content)
        paths[rel_name] = path
    return paths


# ---------------------------------------------------------------------------
# Step 1: full before/after state-hash + single-artifact proof
# ---------------------------------------------------------------------------

def test_create_snapshot_preserves_v2_state_and_writes_exactly_one_artifact(
    redirected_roots,
):
    book_dir = redirected_roots["repo"] / "data" / "portfolios" / "autonomous"
    state_paths = _seed_v2_state(redirected_roots["repo"])
    before_hashes = _hashes(state_paths.values())
    before_tree = _tree_fingerprint(book_dir)

    receipt = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )

    # All seven canonical V2 files are byte-identical, and nothing else appeared,
    # vanished, or changed type anywhere under the book's data directory.
    assert _hashes(state_paths.values()) == before_hashes
    assert _tree_fingerprint(book_dir) == before_tree

    snapshot_dir = snapshots.snapshot_dir("autonomous")
    created = sorted(snapshot_dir.glob("*.json"))
    assert len(created) == 1
    artifact = created[0]
    mode = artifact.lstat().st_mode
    assert not artifact.is_symlink()
    assert stat.S_ISREG(mode)
    assert artifact.name == receipt["snapshot_id"].split(":", 1)[1] + ".json"
    assert receipt["snapshot_id"] in artifact.read_text(encoding="ascii")

    # Round-trip through the verified reader: canonical bytes, closed schema, and
    # the content digest must all check out, and authority must be hard-false.
    loaded = snapshots.load_snapshot("autonomous", receipt["snapshot_id"])
    assert loaded["snapshot_id"] == receipt["snapshot_id"]
    assert loaded["authority"] == {
        "write_permitted": False,
        "execution_authority": False,
        "numeric_target_authority": False,
    }
    c.verify_snapshot(loaded)


# ---------------------------------------------------------------------------
# Step 2: provider / network / process fuses
# ---------------------------------------------------------------------------

def _forbidden(*_args, **_kwargs):
    raise AssertionError("decision_snapshot.create_snapshot reached a forbidden call")


def test_create_snapshot_never_touches_provider_network_or_process(
    redirected_roots, monkeypatch,
):
    _seed_v2_state(redirected_roots["repo"])

    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)

    from brain import client as brain_client
    from brain import provider_waterfall
    from portfolio import paper_account

    monkeypatch.setattr(brain_client, "available", _forbidden)
    monkeypatch.setattr(brain_client, "call_model", _forbidden)
    monkeypatch.setattr(provider_waterfall, "available", _forbidden)
    # Named verbatim in the Task 7 dispatch; kept as forward-compatible fuses even
    # though this attribute does not exist on the accepted module today.
    monkeypatch.setattr(provider_waterfall, "run", _forbidden, raising=False)
    monkeypatch.setattr(paper_account, "queue_target", _forbidden, raising=False)

    monkeypatch.setattr(paper_account, "_current_price", _forbidden)
    monkeypatch.setattr(paper_account, "_load_account", _forbidden)
    monkeypatch.setattr(paper_account, "rebalance", _forbidden)
    monkeypatch.setattr(paper_account, "queue_orders", _forbidden)
    monkeypatch.setattr(paper_account, "save_pending_target", _forbidden)
    monkeypatch.setattr(paper_account, "settle_target", _forbidden)
    monkeypatch.setattr(paper_account, "mark", _forbidden)
    monkeypatch.setattr(paper_account, "execute_fill", _forbidden)

    receipt = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert receipt["snapshot_id"].startswith("sha256:")
    assert len(list(snapshots.snapshot_dir("autonomous").glob("*.json"))) == 1


# ---------------------------------------------------------------------------
# Step 3: import-boundary proof (AST-based, not substring)
# ---------------------------------------------------------------------------

def _imported_module_forms(source_path: Path) -> set[str]:
    """Every dotted module path this file's ``import``/``from ... import`` statements
    could resolve to, covering both ``import a.b.c`` and ``from a.b import c`` forms."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    forms: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                forms.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            for alias in node.names:
                forms.add(f"{node.module}.{alias.name}")
    return forms


def test_s0_source_modules_import_no_forbidden_owner_module_ast_based():
    violations = []
    for path in _S0_SOURCE_MODULES:
        forms = _imported_module_forms(path)
        for forbidden in _FORBIDDEN_IMPORT_MODULES:
            if forbidden in forms:
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {forbidden}")
    assert violations == []


def _project_import_violations(source_path: Path, allowed: set[str]) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in _PROJECT_PACKAGE_ROOTS and alias.name not in allowed:
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            root = node.module.split(".", 1)[0]
            if root not in _PROJECT_PACKAGE_ROOTS:
                continue
            for alias in node.names:
                combined = f"{node.module}.{alias.name}"
                if node.module in allowed or combined in allowed:
                    continue
                violations.append(combined)
    return violations


def test_s0_source_modules_import_only_their_declared_project_owners():
    violations = {}
    for path in _S0_SOURCE_MODULES:
        key = str(path.relative_to(_REPO_ROOT))
        found = _project_import_violations(path, _ALLOWED_PROJECT_IMPORTS[key])
        if found:
            violations[key] = found
    assert violations == {}


# ---------------------------------------------------------------------------
# Step 4: no-hidden-clock proof (AST-based, semantic not textual)
# ---------------------------------------------------------------------------

_BANNED_CLOCK_ATTRS = {"now", "utcnow", "today"}


def _clock_violations(source_path: Path) -> list[str]:
    """Flag ``X.now()``/``X.utcnow()``/``date.today()``/``time.time()`` calls.

    ``datetime.fromtimestamp`` is a distinct attribute name and is never scanned —
    it is the allowed fixed-file-metadata conversion, not a banned current-clock read.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        attr = node.func.attr
        base = node.func.value
        base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
        if attr in _BANNED_CLOCK_ATTRS:
            violations.append(f"{source_path.name}:{node.lineno}:{base_name}.{attr}()")
        elif attr == "time" and base_name == "time":
            violations.append(f"{source_path.name}:{node.lineno}:time.time()")
    return violations


def test_s0_state_and_source_modules_call_no_hidden_current_clock():
    violations = []
    for path in _CLOCK_SCANNED_MODULES:
        violations.extend(_clock_violations(path))
    assert violations == []


# ---------------------------------------------------------------------------
# Clock-law proof: first-party file mtime vs. external Macro mtime
# ---------------------------------------------------------------------------

def _by_id(receipts) -> dict:
    return {r["source_id"]: r for r in receipts}


def test_clock_law_distinguishes_first_party_mtime_from_external_mtime(
    redirected_roots,
):
    state_paths = _seed_v2_state(redirected_roots["repo"])
    account_path = state_paths["account.json"]
    os.utime(account_path, ns=(1_789_400_000_000_000_000, 1_789_400_000_000_000_000))

    external_path = redirected_roots["macro"] / "site" / "factor_betas.json"
    _write(external_path, json.dumps({"schema": "factor_betas.v1", "betas": {}}))
    os.utime(external_path, (1_789_400_000, 1_789_400_000))

    capture = sources.capture_all(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipts = _by_id(capture["sources"])

    account_receipt = receipts["book.account"]
    assert account_receipt["clock_basis"] == "FILE_MTIME_FIRST_PARTY_STATE"
    assert account_receipt["known_at"] == account_receipt["filesystem_observed_at"]
    assert account_receipt["known_at"] is not None

    external_receipt = receipts["macro.factor_betas"]
    assert external_receipt["known_at"] is None
    assert external_receipt["filesystem_observed_at"] is not None
    assert external_receipt["clock_basis"] == "UNQUALIFIED_EXTERNAL_CLOCK"
    assert external_receipt["status"] == "UNQUALIFIED_CLOCK"
