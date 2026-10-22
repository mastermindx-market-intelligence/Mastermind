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

# Fixed, pre-cutoff epoch (2026-09-15T19:00:00Z) so every seeded V2 fixture's mtime never
# depends on the host wall clock landing before the "2026-09-15T20:00:00Z" decision_cutoff
# the tests below use — otherwise a run on or after 2026-09-16 would see every internal
# first-party source as FUTURE_AT_CUTOFF and this file's whole-system negative proof would
# silently stop exercising a populated book.
_PRE_CUTOFF_EPOCH = 1_789_498_800


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.utime(path, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))


def _hashes(paths) -> dict:
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _tree_fingerprint(root: Path) -> dict:
    """Map every path under ``root`` to a (kind, mode, mtime_ns, size, content) tuple.

    Catches a new file of any name, a deleted file, changed bytes in an existing
    file, and a directory/symlink type change — not just a ``*.json`` count. ``mtime_ns``
    is part of the tuple because file mtime is *evidentiary state* in this system: a
    first-party mtime becomes a receipt's ``known_at``, so an ``os.utime`` touch that
    leaves every byte alone is still a real effect on the V2 book.
    """
    fingerprint = {}
    if not root.exists():
        return fingerprint
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        info = path.lstat()
        common = (oct(stat.S_IMODE(info.st_mode)), info.st_mtime_ns)
        if path.is_symlink():
            fingerprint[rel] = ("symlink", *common, 0, os.readlink(path))
        elif path.is_dir():
            fingerprint[rel] = ("dir", *common, 0, None)
        elif stat.S_ISREG(info.st_mode):
            fingerprint[rel] = (
                "file", *common, info.st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        else:
            fingerprint[rel] = ("other", *common, 0, None)
    return fingerprint


def _non_directory_paths(root: Path) -> set:
    """Every non-directory path anywhere below ``root``, relative and normalized.

    The single-artifact proof must be a census of the *whole* redirected storage root, not
    a ``*.json`` glob of one leaf directory: an out-of-leaf ``latest.json``, an extensionless
    ``INDEX`` sidecar, and a nested second store all escape the glob.
    """
    return {rel for rel, entry in _tree_fingerprint(root).items() if entry[0] != "dir"}


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

    # The zero-effect proof must exercise an actually populated, eligible capture — not
    # merely succeed vacuously because every internal source came back FUTURE_AT_CUTOFF.
    account_receipt = next(r for r in receipt["sources"] if r["source_id"] == "book.account")
    assert account_receipt["status"] == "AVAILABLE"
    assert account_receipt["coverage_state"] == "COMPLETE"
    assert receipt["sections"]["book_truth"]["coverage_state"] == "COMPLETE"
    assert receipt["sections"]["book_truth"]["rows"] != []

    # Not a reused same-generation read: this fresh isolated root must have *created*
    # the artifact, or every assertion below would hold vacuously.
    assert receipt["created"] is True

    snapshot_dir = snapshots.snapshot_dir("autonomous")
    created = sorted(snapshot_dir.glob("*.json"))
    assert len(created) == 1
    artifact = created[0]

    # Whole-storage-root census: the content-addressed snapshot is the *only* non-directory
    # artifact anywhere under the redirected storage root — no out-of-leaf mutable index,
    # no non-JSON sidecar, no nested second store.
    storage_root = redirected_roots["storage"]
    assert _non_directory_paths(storage_root) == {
        str(artifact.relative_to(storage_root))
    }
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

class _ForbiddenCall(BaseException):
    """Unswallowable by construction.

    A fuse that raised ``AssertionError`` could be absorbed by any ``except Exception``
    on the call path (the CLI has one at ``scripts/portfolio_decision_snapshot.py``), which
    would turn a proven live-book effect into a quiet ``internal_error``. ``BaseException``
    cannot be caught by an ``except Exception`` handler.
    """


def _forbidden(*_args, **_kwargs):
    raise _ForbiddenCall("decision_snapshot.create_snapshot reached a forbidden call")


# Every paper-account entrypoint that mutates, recovers, prices, or stages live book state.
_FUSED_PAPER_ACCOUNT_ENTRYPOINTS = (
    "_current_price",
    "_load_account",
    "rebalance",
    "queue_orders",
    "save_pending_target",
    "settle_target",
    "mark",
    "execute_fill",
    # Account recovery is a named capability item: ``bot/settle.py`` calls
    # ``recover_paper_transaction`` directly in four places, so the direct form is the
    # idiomatic one in this codebase and must be fused alongside the unlocked inner form.
    "recover_paper_transaction",
    "_recover_paper_transaction_unlocked",
)


def _install_forbidden_call_fuses(monkeypatch):
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

    for name in _FUSED_PAPER_ACCOUNT_ENTRYPOINTS:
        monkeypatch.setattr(paper_account, name, _forbidden)
    return paper_account


def test_create_snapshot_never_touches_provider_network_or_process(
    redirected_roots, monkeypatch,
):
    _seed_v2_state(redirected_roots["repo"])
    _install_forbidden_call_fuses(monkeypatch)

    receipt = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    assert receipt["snapshot_id"].startswith("sha256:")
    assert len(list(snapshots.snapshot_dir("autonomous").glob("*.json"))) == 1


# The capability sentence names these explicitly. Asserting the required set separately from
# the fuse loop keeps the proof non-circular: shrinking _FUSED_PAPER_ACCOUNT_ENTRYPOINTS
# would otherwise shrink the test along with it.
_REQUIRED_FUSED_ENTRYPOINTS = frozenset({
    "_current_price", "_load_account", "rebalance", "queue_orders", "save_pending_target",
    "settle_target", "mark", "execute_fill",
    "recover_paper_transaction", "_recover_paper_transaction_unlocked",
})


def test_every_live_book_entrypoint_including_recovery_is_actually_fused(monkeypatch):
    """Discriminator for the fuse set itself: each named entrypoint must, once fused, raise
    the dedicated unswallowable error — and that error must survive an ``except Exception``
    exactly like the one the CLI wraps its command dispatch in."""
    assert _REQUIRED_FUSED_ENTRYPOINTS <= set(_FUSED_PAPER_ACCOUNT_ENTRYPOINTS)
    paper_account = _install_forbidden_call_fuses(monkeypatch)
    for name in _FUSED_PAPER_ACCOUNT_ENTRYPOINTS:
        with pytest.raises(_ForbiddenCall):
            getattr(paper_account, name)("autonomous")

    swallowed = False
    try:
        try:
            paper_account.recover_paper_transaction("autonomous")
        except Exception:  # noqa: BLE001 - deliberately mirrors the CLI's broad handler
            swallowed = True
    except _ForbiddenCall:
        pass
    assert swallowed is False


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


def _matches_forbidden(form: str, forbidden: str) -> bool:
    """``from portfolio.paper_account import _load_account`` resolves to the form
    ``portfolio.paper_account._load_account``, which never equals the forbidden module name.
    A forbidden module must therefore match its own name *or any descendant form*."""
    return form == forbidden or form.startswith(forbidden + ".")


def _forbidden_import_violations(source_path: Path) -> list[str]:
    forms = _imported_module_forms(source_path)
    return [
        forbidden for forbidden in _FORBIDDEN_IMPORT_MODULES
        if any(_matches_forbidden(form, forbidden) for form in forms)
    ]


def test_s0_source_modules_import_no_forbidden_owner_module_ast_based():
    violations = []
    for path in _S0_SOURCE_MODULES:
        for forbidden in _forbidden_import_violations(path):
            violations.append(f"{path.relative_to(_REPO_ROOT)} imports {forbidden}")
    assert violations == []


def test_forbidden_import_matcher_catches_the_from_import_member_form(tmp_path):
    """Discriminator: the exact-equality matcher this replaces passed a module that did
    ``from portfolio.paper_account import _load_account``."""
    original = (_REPO_ROOT / "portfolio" / "decision_snapshot_sources.py").read_text(
        encoding="utf-8"
    )
    mutated = tmp_path / "mutated_sources.py"
    mutated.write_text(
        "from portfolio.paper_account import _load_account\n" + original, encoding="utf-8"
    )
    assert _forbidden_import_violations(mutated) == ["portfolio.paper_account"]
    # The unmutated original is still clean under the widened matcher.
    assert _forbidden_import_violations(
        _REPO_ROOT / "portfolio" / "decision_snapshot_sources.py"
    ) == []


_DYNAMIC_IMPORT_CALLS = {"import_module", "__import__"}


def _dynamic_import_violations(source_path: Path) -> list[str]:
    """Flag ``importlib.import_module(...)``, a bare ``import_module(...)``, and
    ``__import__(...)``.

    Static import allowlists and per-owner fuses are both bypassed by a dynamic import, so
    S0 modules must not contain one at all — that is the mechanism by which a mutation can
    reach ``paper_account.recover_paper_transaction`` with no import statement to catch.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib" or alias.name.startswith("importlib."):
                    violations.append(f"{source_path.name}:{node.lineno}:import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".", 1)[0] == "importlib":
                violations.append(f"{source_path.name}:{node.lineno}:from {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None
            )
            if name in _DYNAMIC_IMPORT_CALLS:
                violations.append(f"{source_path.name}:{node.lineno}:{name}()")
    return violations


def test_s0_source_modules_contain_no_dynamic_import_escape_hatch():
    violations = []
    for path in _S0_SOURCE_MODULES:
        violations.extend(_dynamic_import_violations(path))
    assert violations == []


@pytest.mark.parametrize("body", [
    "import importlib\n",
    "from importlib import import_module\n",
    "def f(b):\n    return importlib.import_module('portfolio.paper_account')\n",
    "def f(b):\n    return import_module('portfolio.paper_account')\n",
    "def f(b):\n    return __import__('portfolio.paper_account')\n",
])
def test_dynamic_import_scan_catches_every_bypass_form(tmp_path, body):
    probe = tmp_path / "probe.py"
    probe.write_text(body, encoding="utf-8")
    assert _dynamic_import_violations(probe) != []


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

_BANNED_CLOCK_ATTRS = {
    "now", "utcnow", "today",
    # A hidden clock does not have to be wall-clock-shaped to poison determinism.
    "time", "time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns",
}
_NONDETERMINISTIC_IDENTITY_MODULES = {"random", "uuid"}


def _clock_violations(source_path: Path) -> list[str]:
    """Flag every current-clock read and every non-deterministic identity source.

    Covers dotted forms (``datetime.now()``, ``time.time_ns()``, ``dt.datetime.utcnow()``),
    bare from-import aliases (``from time import monotonic as m; m()``), and ``random``/
    ``uuid`` imports or calls — snapshot identity is a content digest, never a draw.

    ``datetime.fromtimestamp`` is a distinct attribute name and is never scanned — it is the
    allowed fixed-file-metadata conversion, not a banned current-clock read.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = []
    clock_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in _NONDETERMINISTIC_IDENTITY_MODULES:
                    violations.append(f"{source_path.name}:{node.lineno}:import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in _NONDETERMINISTIC_IDENTITY_MODULES:
                violations.append(f"{source_path.name}:{node.lineno}:from {node.module}")
            for alias in node.names:
                if alias.name in _BANNED_CLOCK_ATTRS:
                    clock_aliases[alias.asname or alias.name] = alias.name

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            base = func.value
            base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
            if func.attr in _BANNED_CLOCK_ATTRS:
                violations.append(f"{source_path.name}:{node.lineno}:{base_name}.{func.attr}()")
            elif base_name in _NONDETERMINISTIC_IDENTITY_MODULES:
                violations.append(f"{source_path.name}:{node.lineno}:{base_name}.{func.attr}()")
        elif isinstance(func, ast.Name) and func.id in clock_aliases:
            violations.append(
                f"{source_path.name}:{node.lineno}:{func.id}() [{clock_aliases[func.id]}]"
            )
    return violations


def test_s0_state_and_source_modules_call_no_hidden_current_clock():
    violations = []
    for path in _S0_SOURCE_MODULES:
        violations.extend(_clock_violations(path))
    assert violations == []


@pytest.mark.parametrize("body", [
    "import datetime\nx = datetime.datetime.now()\n",
    "import time\nx = time.time()\n",
    "import time\nx = time.time_ns()\n",
    "import time\nx = time.monotonic()\n",
    "import time\nx = time.perf_counter()\n",
    "from time import time as _t\nx = _t()\n",
    "from time import monotonic\nx = monotonic()\n",
    "import random\n",
    "import uuid\nx = uuid.uuid4()\n",
    "from uuid import uuid4\n",
    "from random import choice\n",
])
def test_clock_and_identity_scan_catches_every_hidden_form(tmp_path, body):
    probe = tmp_path / "probe.py"
    probe.write_text(body, encoding="utf-8")
    assert _clock_violations(probe) != []


def test_clock_scan_still_permits_proven_file_metadata_conversion(tmp_path):
    """``datetime.fromtimestamp`` over a proven file mtime is the one lawful conversion;
    banning it would outlaw the first-party clock law itself."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from datetime import datetime, timezone\n"
        "def f(ns):\n"
        "    return datetime.fromtimestamp(ns // 1_000_000_000, tz=timezone.utc)\n",
        encoding="utf-8",
    )
    assert _clock_violations(probe) == []


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


# ---------------------------------------------------------------------------
# Task 8 repair R6 — meta-proofs that the strengthened guards actually discriminate
# ---------------------------------------------------------------------------

def _isolated(tmp_path: Path) -> Path:
    """A subdirectory of ``tmp_path`` this file owns outright.

    ``tmp_path`` itself is shared with repository-wide autouse fixtures that seed their own
    files into it, which would make a whole-root census non-deterministic.
    """
    root = tmp_path / "fingerprint_probe"
    root.mkdir()
    return root


def test_tree_fingerprint_detects_an_mtime_only_touch(tmp_path):
    """A bytes-preserving ``os.utime`` is a real effect on V2 state: a first-party mtime
    becomes a receipt's ``known_at``. A content-only fingerprint would call this unchanged."""
    tmp_path = _isolated(tmp_path)
    target = tmp_path / "account.json"
    target.write_text("{}", encoding="utf-8")
    os.utime(target, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    before = _tree_fingerprint(tmp_path)

    os.utime(target, (_PRE_CUTOFF_EPOCH + 1, _PRE_CUTOFF_EPOCH + 1))
    assert target.read_text(encoding="utf-8") == "{}"
    assert _tree_fingerprint(tmp_path) != before


def test_tree_fingerprint_detects_a_mode_only_change(tmp_path):
    tmp_path = _isolated(tmp_path)
    target = tmp_path / "account.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o600)
    os.utime(target, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    before = _tree_fingerprint(tmp_path)

    os.chmod(target, 0o644)
    os.utime(target, (_PRE_CUTOFF_EPOCH, _PRE_CUTOFF_EPOCH))
    assert _tree_fingerprint(tmp_path) != before


def test_storage_census_catches_out_of_leaf_and_non_json_sidecars(tmp_path):
    """Discriminator for the whole-root census: the ``*.json``-glob proof it replaces saw
    none of these — an out-of-leaf mutable index, an extensionless cursor inside the leaf,
    or a nested second store."""
    tmp_path = _isolated(tmp_path)
    leaf = tmp_path / "data" / "shadow" / "decision_snapshots" / "autonomous"
    leaf.mkdir(parents=True)
    artifact = leaf / ("a" * 64 + ".json")
    artifact.write_text("{}", encoding="utf-8")
    assert _non_directory_paths(tmp_path) == {str(artifact.relative_to(tmp_path))}

    (leaf.parent / "latest.json").write_text("{}", encoding="utf-8")
    (leaf / "INDEX").write_text("cursor", encoding="utf-8")
    (leaf / "nested").mkdir()
    (leaf / "nested" / "second_store.db").write_text("x", encoding="utf-8")

    census = _non_directory_paths(tmp_path)
    assert str(artifact.relative_to(tmp_path)) in census
    assert len(census) == 4
    # The old proof's instrument sees only one of the four.
    assert len(sorted(leaf.glob("*.json"))) == 1


def test_recovery_reached_by_dynamic_import_still_trips_the_fuse(monkeypatch):
    """The exact bypass the import allowlist cannot see. A mutation inside
    ``capture_book_state`` of the shape
    ``importlib.import_module("portfolio.paper_account").recover_paper_transaction(book)``
    has no import statement to catch and no ``_load_account`` hop to borrow a fuse from, so
    the recovery entrypoints must be fused as callables in their own right."""
    import importlib

    _install_forbidden_call_fuses(monkeypatch)
    module = importlib.import_module("portfolio.paper_account")
    with pytest.raises(_ForbiddenCall):
        module.recover_paper_transaction("autonomous")
    with pytest.raises(_ForbiddenCall):
        module._recover_paper_transaction_unlocked("autonomous")
