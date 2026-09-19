# Mastermind Portfolio V3 S0 Decision Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Portfolio V3 vertical: one immutable, bounded, correction-safe, point-in-time Decision Snapshot for the active US `autonomous` paper book, with a read-only API and operator inspector, while producing zero model, allocation, settlement, or V2 behavior effects.

**Architecture:** Add a pure closed-contract layer, a fixed allowlisted source-capture adapter over existing Portfolio and Macro artifacts, and a content-addressed immutable store under the existing `data/shadow/` root. The only writer is an explicit operator CLI that receives its clocks as arguments; the web API and UI are read-only projections over already-materialized snapshots. Sector/rotation remains an explicit partial dependency until Mastermind PR #548 is accepted; S0 records that gap and does not duplicate its reader.

**Tech Stack:** Python 3.12+, stdlib dataclasses/hashlib/json/os/pathlib, existing YAML artifact registry, FastAPI/JSONResponse, the existing single-file dashboard SPA, pytest, current Mastermind deployment workflow.

**Spec:** `docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md`

## Global Constraints

- This plan was reconciled against protected `Mastermind@36f74c02edc938f7f5c41f38743f93ee34be2b2b` with `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1. Execution must re-pin protected `master` again at action time.
- Mastermind PR #658 is the records-only architecture-and-plan carrier. It must never carry S0 implementation source, tests, installation, or runtime evidence.
- After PR #658 is accepted and protected, S0 starts as the separate operation `mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001` in a separately acquired `mmx-workspace` and a separate Draft/HOLD implementation PR.
- The first vertical is `V3-S0 Decision Snapshot` only. No Claim, PM View, constructor, alpha tilt, target, shadow account, learning policy, or execution logic enters this plan.
- `autonomous` remains the sole active US managed book. Do not add a V3 registry row or a second active book.
- S0 is read-only with respect to all existing Portfolio state. It may create files only below `data/shadow/decision_snapshots/autonomous/`.
- Do not call a model, provider, web search, quote network, scheduler, or worker runtime from snapshot code.
- Do not call `portfolio.paper_account._load_account()`: that function may recover a transaction and mutate state. Read canonical files through fixed paths without recovery.
- Do not write or clear `_pending_decision.json`, `pending_target.json`, `pending_orders.json`, account, fills, NAV, decisions, positions, post-sell, or settlement receipts.
- Do not add a mutable `latest.json`, index, cursor database, correction ledger, queue, or daemon. Discover snapshots by verifying immutable content-addressed files.
- Every clock used for truth or cutoff eligibility is supplied by the caller, declared by the source, or—only for canonical first-party Portfolio state—proven by a stable file read and labeled `FILE_MTIME_FIRST_PARTY_STATE`. External Macro filesystem mtime may be recorded only as `filesystem_observed_at`; it never becomes market `known_at`.
- Contract/composer modules may not call `datetime.now`, `date.today`, `time.time`, network, subprocess, environment mutation, or random/UUID identity generation.
- Snapshot identity is `sha256:<64 lowercase hex>` over canonical JSON without the `snapshot_id` field.
- Root snapshot payload maximum: 262,144 UTF-8 bytes. Section response maximum: 65,536 UTF-8 bytes. Raw source file maximum: 8,388,608 bytes. JSONL tail maximum: 100 rows. Section page maximum: 100 rows.
- Source paths are closed constants or checked-in contract keys. No caller-supplied path, URL, repository root, or filename may reach a filesystem expression.
- A missing source is not an empty complete source. A stale source is not calm. An unknown clock remains unknown.
- External source content with a qualified `known_at` after the decision cutoff is excluded as `FUTURE_AT_CUTOFF`.
- The snapshot carries `write_permitted=false`, `execution_authority=false`, and `numeric_target_authority=false`.
- `COMPLETE`, `PARTIAL`, `BLOCKED`, `INVALID`, and `CORRECTED_GENERATION_AVAILABLE` remain distinct.
- PR #548 owns native IDs, bounded paging, coverage, and correction-safe retrieval for Sector Central. S0 captures its raw artifact receipt only and marks the market-structure section partial until that owner is protected and consumed.
- PR #398 is an open Outcome Learning candidate. S0 neither imports it nor recreates its contracts.
- Existing `portfolio/shadow_books.py` remains the counterfactual book owner. S0 adds immutable evidence under the same `data/shadow/` estate but does not alter policy books, accounts, NAV, or leaderboard behavior.
- Existing paper-account, pending-target, settlement, fill, mark, and NAV modules remain the only portfolio mutation owners.
- Source merge, deployment, snapshot composition, API readback, and browser proof are separate gates.
- Every task uses tests first, focused GREEN, mutation or negative proof where named, a clean diff, and a small commit.
- If a task proves that a frozen owner boundary is insufficient, stop with the exact failing contract. Do not broaden the wave by convenience.

## File Structure and Responsibility Map

### New focused modules

- `portfolio/decision_snapshot_contracts.py`
  - Pure schemas, vocabularies, UTC parsing, digesting, sealing, and validation.
  - Reuses `control_plane.wake_events.canonical_json_bytes`; no second canonical serializer. No filesystem, clock, network, model, or Portfolio-state imports.

- `portfolio/decision_snapshot_sources.py`
  - Fixed allowlist of internal and external source slots.
  - Bounded reads, explicit clock extraction, source receipts, bounded section projections, and gap reporting.
  - No persistence and no model/provider access.

- `portfolio/decision_snapshot.py`
  - Compose one closed snapshot from a capture bundle.
  - Derive coverage/correction state.
  - Create-only content-addressed persistence.
  - Verified list/load/status/section-page reads.

- `scripts/portfolio_decision_snapshot.py`
  - Explicit operator CLI with `compose`, `status`, and `show`.
  - `compose` is the only S0 writer and requires explicit UTC `decision_cutoff` and `recorded_at`.

- `docs/runbooks/portfolio-v3-decision-snapshot.md`
  - Operator composition, readback, correction, rollback, and no-effect verification.

### New tests

- `tests/test_decision_snapshot_contracts.py`
- `tests/test_decision_snapshot_sources.py`
- `tests/test_decision_snapshot.py`
- `tests/test_decision_snapshot_cli.py`
- `tests/test_decision_snapshot_api.py`
- `tests/test_decision_snapshot_ui.py`
- `tests/test_decision_snapshot_no_effect.py`

### Existing files modified

- `config/contracts.yml`
  - Register the fixed Macro artifacts newly consumed by S0.

- `tests/test_contracts.py`
  - Pin those checked-in artifact contracts.

- `app/web.py`
  - Add one read-only `GET /api/decision-snapshot` route.

- `app/static/index.html`
  - Add the US-V3-only evidence inspector and bounded renderer.

### Files explicitly not modified in S0

- `brain/portfolio_intelligence.py`
- `brain/autonomous_mcp.py`
- `tests/test_portfolio_intelligence.py`
- `tests/test_portfolio_intelligence_mcp.py`
- `bot/autonomous.py`
- `brain/decision_submission.py`
- `portfolio/paper_account.py`
- `portfolio/registry.py`
- `portfolio/shadow_books.py`
- `portfolio/forward_evaluation.py`
- every settlement, fill, account, provider, scheduler, and model file

---

### Task 0: Protect the Records-Only Design and Open a Separate S0 Carrier

**Files:**
- Read only: `docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md`
- Read only: `docs/superpowers/plans/2026-09-15-mastermind-portfolio-v3-s0-decision-snapshot.md`
- Read only: Mastermind PR #658
- Read only: Mastermind PR #548
- Read only: Mastermind PR #398
- Read only: current protected `master`
- No implementation source file changes on PR #658

**Interfaces:**
- Consumes: protected Skillpack `mastermind.sol_skillpack.v1` from the exact action-time protected commit.
- Produces:
  - terminal acceptance/protection disposition for the records-only architecture-and-plan carrier #658;
  - operation `mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001`;
  - one separately managed implementation workspace and branch;
  - one later Draft/HOLD implementation PR after the first scoped source commit.

- [ ] **Step 1: Re-pin protected source and verify the records-only workspace**

Run:

```bash
git fetch origin master
git status --short --branch
git rev-parse HEAD
git rev-parse origin/master
```

Expected:

- the architecture/plan workspace is clean;
- branch identity is the existing PR #658 records carrier;
- protected `master` is recorded before any release or implementation action;
- PR #658 contains only the architecture spec and this implementation plan relative to protected master.

- [ ] **Step 2: Re-read the architecture and dependency carriers**

Use canonical GitHub reads for PR #658, PR #548, and PR #398.

Record exactly:

```text
#658: records-only architecture/plan carrier, exact head/base, review/check state
#548: non-lossy rotation-reader owner, exact changed paths, RED/GREEN/review state
#398: Outcome Learning candidate, exact open/merged state, protected capability or not
```

Expected:

- #548 remains the owner of `brain/portfolio_intelligence.py`, `brain/autonomous_mcp.py`, and their rotation-reader tests unless current protected source proves otherwise;
- #398 does not become an S0 dependency merely because it contains useful concepts;
- no retrieved PR prose grants START or merge authority by itself.

- [ ] **Step 3: Run an open-PR changed-path collision census**

Check these exact planned implementation paths against every open Mastermind PR:

```text
config/contracts.yml
tests/test_contracts.py
portfolio/decision_snapshot_contracts.py
portfolio/decision_snapshot_sources.py
portfolio/decision_snapshot.py
scripts/portfolio_decision_snapshot.py
docs/runbooks/portfolio-v3-decision-snapshot.md
tests/test_decision_snapshot_contracts.py
tests/test_decision_snapshot_sources.py
tests/test_decision_snapshot.py
tests/test_decision_snapshot_cli.py
tests/test_decision_snapshot_api.py
tests/test_decision_snapshot_ui.py
tests/test_decision_snapshot_no_effect.py
app/web.py
app/static/index.html
```

Expected:

- no unreconciled writer owns a planned path;
- if `app/web.py`, `app/static/index.html`, `config/contracts.yml`, or `tests/test_contracts.py` is currently owned, sequence S0 behind that exact carrier rather than racing it;
- do not infer path ownership from PR titles.

- [ ] **Step 4: Verify current owner invariants**

Run:

```bash
git grep -n "DASHBOARD_DEFAULT_ID = \"autonomous\"" portfolio/registry.py
git grep -n "The reasoning model selects names and expresses ordinal intent" brain/decision_submission.py
git grep -n "Parallel forward shadow books" portfolio/shadow_books.py
git grep -n "Bounded forward evaluation" portfolio/forward_evaluation.py
git grep -n "def canonical_json_bytes" control_plane/wake_events.py
```

Expected: all five canonical owners remain present.

- [ ] **Step 5: Accept and protect PR #658 as records-only design law**

Before protection, require:

```text
architecture status: APPROVED
plan status: APPROVED
changed paths: exactly the architecture spec and S0 plan
implementation capability: NOT_BUILT
production effect: NONE
```

Obtain applicable exact-head/current-base checks and independent source review. Merge through the normal protected path. Read back the actual protected SHA and confirm the two records are present. Do not place implementation files on #658.

- [ ] **Step 6: Acquire the separate S0 implementation workspace**

From a trusted attended host with the canonical launcher:

```bash
base_sha=$(git -C /Users/chriswong/Documents/GitHub/Mastermind rev-parse origin/master)
/Users/chriswong/.local/bin/mmx-workspace acquire \
  --operation-id mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001 \
  --base-sha "$base_sha" \
  --lane sol
```

Expected receipt:

```text
operation_id=mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
base_sha=<exact protected SHA containing #658>
branch=sol/mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
reused=false or a canonically matching reusable workspace
```

Use only the returned workspace. Do not create a raw worktree, nested checkout, or replacement branch.

- [ ] **Step 7: Record implementation PRE_START on #658 and the future implementation carrier**

The #658 terminal record states:

```text
architecture/plan: PROTECTED RECORDS
S0 implementation: PRE_START
implementation operation: mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
implementation branch: sol/mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
#548 disposition: current exact state
#398 disposition: current exact state
collisions: none or exact blocker
live Portfolio effect: NONE
```

The separate implementation PR is opened as Draft/HOLD after Task 1 creates the first scoped commit. PR #658 remains terminal records history, not an implementation carrier.

Stop if source ownership, protected design publication, or workspace identity is ambiguous.

### Task 1: Add the Closed Snapshot Contract and Register Its Fixed Macro Sources

**Files:**
- Create: `portfolio/decision_snapshot_contracts.py`
- Create: `tests/test_decision_snapshot_contracts.py`
- Modify: `config/contracts.yml`
- Modify: `tests/test_contracts.py`

**Interfaces:**
- Consumes: `control_plane.wake_events.canonical_json_bytes(value: Any) -> bytes` as the single canonical JSON serializer.
- Produces:
  - `SNAPSHOT_SCHEMA = "mastermind.portfolio_decision_snapshot.v1"`
  - `SOURCE_RECEIPT_SCHEMA = "mastermind.portfolio_source_receipt.v1"`
  - `SECTION_SCHEMA = "mastermind.portfolio_snapshot_section.v1"`
  - `SNAPSHOT_STATES`
  - `COVERAGE_STATES`
  - `SOURCE_STATUSES`
  - `SECTION_IDS`
  - `DecisionSnapshotContractError`
  - `parse_utc_timestamp(value: str, *, field: str) -> str`
  - `content_digest(value: Any) -> str`
  - `validate_source_receipt(receipt: Mapping[str, Any]) -> None`
  - `validate_section(section: Mapping[str, Any]) -> None`
  - `validate_unsealed_snapshot(snapshot: Mapping[str, Any]) -> None`
  - `seal_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]`
  - `validate_snapshot(snapshot: Mapping[str, Any]) -> None`
  - `verify_snapshot(snapshot: Mapping[str, Any]) -> None`
- Consumes no project module other than the canonical serializer owner above.

- [ ] **Step 1: Add RED tests for the closed vocabularies and canonical seal**

Create `tests/test_decision_snapshot_contracts.py` with factories using the exact root shape:

```python
from portfolio import decision_snapshot_contracts as c


def _receipt() -> dict:
    return {
        "schema": c.SOURCE_RECEIPT_SCHEMA,
        "source_id": "book.account",
        "domains": ["book_truth"],
        "producer": "mastermind_portfolio",
        "owner": "portfolio_desk",
        "artifact": "data/portfolios/autonomous/account.json",
        "source_schema": None,
        "schema_version": None,
        "definition_id": None,
        "artifact_digest": "sha256:" + "a" * 64,
        "observed_at": None,
        "known_at": "2026-09-15T20:00:00Z",
        "as_of": "2026-09-15",
        "generated_at": None,
        "filesystem_observed_at": "2026-09-15T20:00:00Z",
        "correction_generation": "sha256:" + "a" * 64,
        "freshness_state": "FRESH",
        "coverage_state": "COMPLETE",
        "rights_class": "FIRST_PARTY_INTERNAL",
        "authority_class": "BOOK_STATE",
        "status": "AVAILABLE",
        "required": True,
        "bytes": 120,
        "rows_total": 1,
        "rows_returned": 1,
        "omitted_rows": 0,
        "clock_basis": "FILE_MTIME_FIRST_PARTY_STATE",
        "error_code": None,
    }


def _section() -> dict:
    return {
        "schema": c.SECTION_SCHEMA,
        "section_id": "book_truth",
        "coverage_state": "COMPLETE",
        "source_ids": ["book.account"],
        "rows_total": 1,
        "rows_returned": 1,
        "omitted_rows": 0,
        "rows": [{"kind": "account", "cash": 1000000.0, "positions": []}],
        "gaps": [],
    }


def _unsealed() -> dict:
    return {
        "schema": c.SNAPSHOT_SCHEMA,
        "book": "autonomous",
        "decision_cutoff": "2026-09-15T20:00:00Z",
        "recorded_at": "2026-09-15T20:01:00Z",
        "state": "COMPLETE",
        "coverage_state": "COMPLETE",
        "summary": {
            "sources_total": 1,
            "sources_available": 1,
            "domains_complete": 1,
            "domains_partial": 0,
            "domains_blocked": 0,
        },
        "source_generation_set": [
            {"source_id": "book.account", "correction_generation": "sha256:" + "a" * 64}
        ],
        "sources": [_receipt()],
        "sections": {"book_truth": _section()},
        "gaps": [],
        "correction": {
            "status": "ORIGINAL",
            "same_cutoff_prior_snapshot_ids": [],
        },
        "authority": {
            "write_permitted": False,
            "execution_authority": False,
            "numeric_target_authority": False,
        },
    }
```

Add these exact tests:

```python
def test_seal_is_key_order_invariant_and_self_verifying():
    left = _unsealed()
    right = dict(reversed(list(left.items())))
    sealed_left = c.seal_snapshot(left)
    sealed_right = c.seal_snapshot(right)
    assert sealed_left["snapshot_id"] == sealed_right["snapshot_id"]
    assert sealed_left["snapshot_id"].startswith("sha256:")
    c.verify_snapshot(sealed_left)


def test_closed_root_rejects_unknown_and_missing_fields():
    extra = {**_unsealed(), "surprise": True}
    with pytest.raises(c.DecisionSnapshotContractError, match="unknown"):
        c.validate_unsealed_snapshot(extra)
    missing = _unsealed()
    missing.pop("decision_cutoff")
    with pytest.raises(c.DecisionSnapshotContractError, match="missing"):
        c.validate_unsealed_snapshot(missing)


def test_contract_requires_timezone_aware_utc_clocks():
    for bad in ("2026-09-15", "2026-09-15T20:00:00", "not-a-time"):
        with pytest.raises(c.DecisionSnapshotContractError):
            c.parse_utc_timestamp(bad, field="decision_cutoff")
    assert c.parse_utc_timestamp(
        "2026-09-15T16:00:00-04:00", field="decision_cutoff"
    ) == "2026-09-15T20:00:00Z"


def test_source_receipt_refuses_unqualified_digest_and_authority_escalation():
    bad_digest = {**_receipt(), "artifact_digest": "abc"}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(bad_digest)
    bad_authority = {**_receipt(), "authority_class": "EXECUTION"}
    with pytest.raises(c.DecisionSnapshotContractError):
        c.validate_source_receipt(bad_authority)


def test_contract_reuses_canonical_json_owner_and_has_no_hidden_io():
    source = Path(c.__file__).read_text(encoding="utf-8")
    assert "from control_plane.wake_events import canonical_json_bytes" in source
    assert "def canonical_json_bytes" not in source
    forbidden = (
        "datetime.now",
        "date.today",
        "time.time",
        "open(",
        "Path(",
        "requests",
        "subprocess",
        "paper_account",
        "portfolio_intelligence",
    )
    assert not [token for token in forbidden if token in source]
```

- [ ] **Step 2: Run RED**

Run:

```bash
python3 -m pytest -q tests/test_decision_snapshot_contracts.py
```

Expected: import failure because `portfolio.decision_snapshot_contracts` does not exist.

- [ ] **Step 3: Implement the pure contract module**

Create `portfolio/decision_snapshot_contracts.py` by reusing the existing canonical serializer:

```python
from control_plane.wake_events import canonical_json_bytes

SNAPSHOT_SCHEMA = "mastermind.portfolio_decision_snapshot.v1"
SOURCE_RECEIPT_SCHEMA = "mastermind.portfolio_source_receipt.v1"
SECTION_SCHEMA = "mastermind.portfolio_snapshot_section.v1"

SNAPSHOT_STATES = frozenset({
    "COMPLETE",
    "PARTIAL",
    "BLOCKED",
    "INVALID",
    "CORRECTED_GENERATION_AVAILABLE",
})
COVERAGE_STATES = frozenset({"COMPLETE", "PARTIAL", "BLOCKED", "UNKNOWN"})
SOURCE_STATUSES = frozenset({
    "AVAILABLE",
    "ABSENT_OPTIONAL",
    "MISSING",
    "MALFORMED",
    "OVERSIZE",
    "FUTURE_AT_CUTOFF",
    "UNQUALIFIED_CLOCK",
    "DEPENDENCY_PARTIAL",
    "RIGHTS_BLOCKED",
    "INVALID",
})
SECTION_IDS = (
    "book_truth",
    "risk_truth",
    "market_structure",
    "independence",
    "factor_risk",
    "candidate_geometry",
    "relationships",
    "fundamental_state",
    "positioning",
    "priceability",
    "event_state",
    "historical_memory",
)
MAX_SNAPSHOT_BYTES = 262_144
MAX_SECTION_RESPONSE_BYTES = 65_536
MAX_SECTION_ROWS = 100
MAX_SOURCE_BYTES = 8_388_608
MAX_JSONL_TAIL_ROWS = 100
```

Use exact-key validation helpers. `parse_utc_timestamp` must normalize any aware timestamp to second-precision UTC `Z`. Booleans are not accepted as numbers. `seal_snapshot` must:

```python
def seal_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_unsealed_snapshot(snapshot)
    sealed = json.loads(canonical_json_bytes(snapshot))
    sealed["snapshot_id"] = content_digest(snapshot)
    validate_snapshot(sealed)
    if len(canonical_json_bytes(sealed)) > MAX_SNAPSHOT_BYTES:
        raise DecisionSnapshotContractError("snapshot exceeds 262144-byte limit")
    return sealed
```

`verify_snapshot` must remove `snapshot_id`, recompute the digest, compare exact identity, and re-run closed validation.

- [ ] **Step 4: Register the six newly consumed Macro artifacts**

Append these exact entries to `config/contracts.yml` under census-declared artifacts:

```yaml
  portfolio-v3-risk-envelope-settled:
    path: site/riskdata/risk_envelope.json
    owner: macro_engine
    schema_hint: json
    freshness_budget_sessions: 1
    tier: display
    allowed_effect: context-only
    degradation_class: SHRINK
    consumer_modules:
      - portfolio/decision_snapshot_sources.py
    declared_by: census

  portfolio-v3-sector-central:
    path: site/sectordata/sector_central.json
    owner: macro_engine
    schema_hint: json
    freshness_budget_sessions: 1
    tier: display
    allowed_effect: context-only
    degradation_class: ADVISORY
    consumer_modules:
      - portfolio/decision_snapshot_sources.py
    declared_by: census

  portfolio-v3-covariance-spine:
    path: data/neuralweb/covariance_spine.json
    owner: macro_engine
    schema_hint: json
    freshness_budget_sessions: 1
    tier: infrastructure
    allowed_effect: context-only
    degradation_class: ADVISORY
    consumer_modules:
      - portfolio/decision_snapshot_sources.py
    declared_by: census

  portfolio-v3-factor-betas:
    path: site/factor_betas.json
    owner: macro_engine
    schema_hint: json
    freshness_budget_sessions: 1
    tier: display
    allowed_effect: context-only
    degradation_class: ADVISORY
    consumer_modules:
      - portfolio/decision_snapshot_sources.py
    declared_by: census

  portfolio-v3-prophet-index:
    path: site/prophet/index.json
    owner: macro_engine
    schema_hint: json
    freshness_budget_sessions: 1
    tier: display
    allowed_effect: display-only
    degradation_class: ADVISORY
    consumer_modules:
      - portfolio/decision_snapshot_sources.py
    declared_by: census

  portfolio-v3-portfolio-context:
    path: site/data/portfolio_ctx.json
    owner: macro_engine
    schema_hint: json
    freshness_budget_sessions: 1
    tier: display
    allowed_effect: context-only
    degradation_class: ADVISORY
    consumer_modules:
      - portfolio/decision_snapshot_sources.py
    declared_by: census
```

Reuse existing keys for:

```text
regime-latest
site-neural-web-mastermind-context
site-intelligence-by-ticker
site-altdata-by-ticker
site-news-by-ticker
```

Do not create aliases for those existing paths.

- [ ] **Step 5: Pin the registry additions in `tests/test_contracts.py`**

Add:

```python
def test_portfolio_v3_snapshot_sources_are_registered_context_only():
    expected = {
        "portfolio-v3-risk-envelope-settled": (
            "site/riskdata/risk_envelope.json", "SHRINK"
        ),
        "portfolio-v3-sector-central": (
            "site/sectordata/sector_central.json", "ADVISORY"
        ),
        "portfolio-v3-covariance-spine": (
            "data/neuralweb/covariance_spine.json", "ADVISORY"
        ),
        "portfolio-v3-factor-betas": (
            "site/factor_betas.json", "ADVISORY"
        ),
        "portfolio-v3-prophet-index": (
            "site/prophet/index.json", "ADVISORY"
        ),
        "portfolio-v3-portfolio-context": (
            "site/data/portfolio_ctx.json", "ADVISORY"
        ),
    }
    for key, (path, degradation) in expected.items():
        row = contracts.contract(key)
        assert row is not None
        assert row["path"] == path
        assert row["allowed_effect"] in {"context-only", "display-only"}
        assert row["degradation_class"] == degradation
        assert row["consumer_modules"] == [
            "portfolio/decision_snapshot_sources.py"
        ]
```

- [ ] **Step 6: Run GREEN and mutation proof**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot_contracts.py \
  tests/test_contracts.py
python3 -m compileall -q portfolio/decision_snapshot_contracts.py
git diff --check
```

Expected: all pass.

Mutation proof:

1. Temporarily permit `EXECUTION` in the authority vocabulary.
2. Run `test_source_receipt_refuses_unqualified_digest_and_authority_escalation`.
3. Confirm it fails.
4. Restore the source and rerun GREEN.

- [ ] **Step 7: Commit**

```bash
git add \
  portfolio/decision_snapshot_contracts.py \
  tests/test_decision_snapshot_contracts.py \
  config/contracts.yml \
  tests/test_contracts.py
git commit -m "feat(portfolio): define V3 decision snapshot contracts"
```

- [ ] **Step 8: Push and open the separate Draft/HOLD implementation PR**

```bash
git push -u origin HEAD
```

Open one Draft PR from:

```text
sol/mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
```

to protected `master`, with:

```text
title: [PORTFOLIO-V3][S0][DRAFT][HOLD] Immutable Decision Snapshot
operation: mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
parent architecture/plan: Mastermind PR #658
capability: BUILT_NOT_PROVEN only after source implementation passes; initially PARTIAL / IN_PROGRESS
production effect: NONE
```

Do not mark Ready, enable auto-merge, deploy, or add implementation commits to PR #658.

---

### Task 2: Build the Fixed, Clock-Honest Source Capture Layer

**Files:**
- Create: `portfolio/decision_snapshot_sources.py`
- Create: `tests/test_decision_snapshot_sources.py`
- Read only: `control_plane/contracts.py`
- Read only: `portfolio/registry.py`
- Read only: `portfolio/paper_account.py`
- Read only: `brain/portfolio_intelligence.py`

**Interfaces:**
- Consumes:
  - contract functions and constants from Task 1;
  - `control_plane.contracts.contract(key)`;
  - `portfolio.registry.data_dir("autonomous")`.
- Produces:
  - `SourceSpec`
  - `EXTERNAL_SOURCE_SPECS`
  - `capture_all(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]`
  - `capture_book_state(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]`
  - `capture_external_sources(*, held_tickers: Sequence[str], decision_cutoff: str, recorded_at: str) -> dict[str, Any]`
  - return shape:
    `{"sources": list[receipt], "sections": dict[section_id, section], "gaps": list[gap]}`

- [ ] **Step 1: Write RED tests for path closure and zero hidden effects**

Create `tests/test_decision_snapshot_sources.py`.

Add a `repo_roots` fixture that monkeypatches only module-owned `_ROOT` and `_V` to `tmp_path / "repo"` and `tmp_path / "macro"`. Create fixed files beneath those roots.

Add:

```python
def test_capture_reads_fixed_sources_without_account_recovery(
    monkeypatch, repo_roots
):
    repo, macro = repo_roots
    _write_json(repo / "data/portfolios/autonomous/account.json", {
        "starting_nav": 1_000_000.0,
        "cash": 800_000.0,
        "positions": {"AAPL": {"shares": 100.0, "avg_cost": 180.0}},
    })
    _write_json(repo / "data/portfolios/autonomous/latest.json", {
        "as_of": "2026-09-15",
        "positions": [{
            "ticker": "AAPL",
            "weight": 0.2,
            "identity_status": "verified_common_stock",
            "holding_mark_source": "live_quote",
        }],
    })
    _write_json(macro / "site/riskdata/risk_envelope.json", {
        "schema": "mastermind.risk_envelope/v1",
        "definition_id": "grey-deer-v1-2026-08-19",
        "generated_at": "2026-09-15T19:55:00Z",
        "as_of": "2026-09-15",
        "data_state": "FRESH",
        "capital_policy": {"posture": "SELECTIVE"},
    })

    from portfolio import paper_account
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda *a, **k: pytest.fail("transaction recovery is forbidden"),
    )

    result = sources.capture_all(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )

    assert result["sections"]["book_truth"]["rows"][0]["cash"] == 800_000.0
    assert result["sections"]["risk_truth"]["rows"][0]["capital_policy"] == {
        "posture": "SELECTIVE"
    }
    assert not any(gap["code"] == "ACCOUNT_RECOVERY_CALLED" for gap in result["gaps"])
```

Add:

```python
def test_internal_state_uses_only_stable_first_party_file_clock(repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    os.utime(path, ns=(1_789_400_000_000_000_000, 1_789_400_000_000_000_000))
    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["clock_basis"] == "FILE_MTIME_FIRST_PARTY_STATE"
    assert receipt["known_at"] == receipt["filesystem_observed_at"]


def test_internal_source_change_during_read_returns_no_rows(monkeypatch, repo_roots):
    repo, _ = repo_roots
    path = repo / "data/portfolios/autonomous/account.json"
    _write_json(path, {"cash": 1_000_000.0, "positions": {}})
    real_fstat = sources.os.fstat
    calls = {"n": 0}

    def changed(fd):
        row = real_fstat(fd)
        calls["n"] += 1
        if calls["n"] == 2:
            return SimpleNamespace(
                st_dev=row.st_dev,
                st_ino=row.st_ino,
                st_size=row.st_size + 1,
                st_mtime_ns=row.st_mtime_ns + 1,
            )
        return row

    monkeypatch.setattr(sources.os, "fstat", changed)
    result = sources.capture_book_state(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["book.account"]
    assert receipt["status"] == "INVALID"
    assert receipt["error_code"] == "SOURCE_CHANGED_DURING_READ"
    assert result["sections"]["book_truth"]["rows"] == []
```

Add:

```python
def test_external_known_after_cutoff_is_excluded_not_read_as_current(repo_roots):
    _, macro = repo_roots
    _write_json(macro / "site/riskdata/risk_envelope.json", {
        "schema": "mastermind.risk_envelope/v1",
        "generated_at": "2026-09-15T20:05:00Z",
        "as_of": "2026-09-15",
        "capital_policy": {"posture": "NORMAL"},
    })
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:06:00Z",
    )
    receipt = _by_id(result["sources"])["macro.risk_envelope"]
    assert receipt["status"] == "FUTURE_AT_CUTOFF"
    assert receipt["coverage_state"] == "BLOCKED"
    assert result["sections"]["risk_truth"]["rows"] == []
```

Add:

```python
def test_missing_risk_is_unknown_protective_not_calm(repo_roots):
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    risk = result["sections"]["risk_truth"]
    assert risk["coverage_state"] == "PARTIAL"
    assert risk["rows"] == [{
        "market_risk_state": "UNKNOWN_PROTECTIVE",
        "reason": "macro.risk_envelope:MISSING",
    }]
```

Add:

```python
def test_rotation_is_receipt_only_until_pr548_contract_is_available(
    repo_roots,
):
    _, macro = repo_roots
    _write_json(macro / "site/sectordata/sector_central.json", {
        "as_of": "2026-09-15",
        "sectors": [{"id": "technology", "ticker": "XLK"}],
        "baskets": [{"id": "memory-hbm", "ticker": "SMH"}],
    })
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.sector_rotation"]
    assert receipt["status"] == "DEPENDENCY_PARTIAL"
    section = result["sections"]["market_structure"]
    assert section["coverage_state"] == "PARTIAL"
    assert not any("sectors" in row or "baskets" in row for row in section["rows"])
    assert any(gap["owner"] == "Mastermind PR #548" for gap in section["gaps"])
```

Add:

```python
def test_external_mtime_is_never_promoted_to_market_known_at(repo_roots):
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    _write_json(path, {"schema": "factor_betas.v1", "betas": {}})
    os.utime(path, (1_789_400_000, 1_789_400_000))
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.factor_betas"]
    assert receipt["known_at"] is None
    assert receipt["filesystem_observed_at"] is not None
    assert receipt["clock_basis"] == "UNQUALIFIED_EXTERNAL_CLOCK"
    assert receipt["status"] == "UNQUALIFIED_CLOCK"
```

Add path/size tests:

```python
def test_no_public_function_accepts_a_path_or_root_argument():
    for fn in (
        sources.capture_all,
        sources.capture_book_state,
        sources.capture_external_sources,
    ):
        assert not {"path", "root", "url", "filename"} & set(
            inspect.signature(fn).parameters
        )


def test_oversize_source_is_partial_without_parsing(repo_roots):
    _, macro = repo_roots
    path = macro / "site/factor_betas.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{" + b"x" * (c.MAX_SOURCE_BYTES + 1))
    result = sources.capture_external_sources(
        held_tickers=[],
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    receipt = _by_id(result["sources"])["macro.factor_betas"]
    assert receipt["status"] == "OVERSIZE"
    assert receipt["coverage_state"] == "PARTIAL"
```

- [ ] **Step 2: Run RED**

Run:

```bash
python3 -m pytest -q tests/test_decision_snapshot_sources.py
```

Expected: import failure because `portfolio.decision_snapshot_sources` does not exist.

- [ ] **Step 3: Implement the closed source registry**

Create:

```python
@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    contract_key: str
    domains: tuple[str, ...]
    required: bool
    authority_class: str
    rights_class: str
    projection: str
    known_at_fields: tuple[str, ...] = ()
    observed_at_fields: tuple[str, ...] = ()
    as_of_fields: tuple[str, ...] = ()
    generated_at_fields: tuple[str, ...] = ()
    schema_fields: tuple[str, ...] = ("schema",)
    definition_fields: tuple[str, ...] = ("definition_id",)
```

Define exactly these external slots:

```python
EXTERNAL_SOURCE_SPECS = (
    SourceSpec(
        "macro.risk_envelope",
        "portfolio-v3-risk-envelope-settled",
        ("risk_truth",),
        True,
        "MARKET_RISK_CONTEXT",
        "FIRST_PARTY_INTERNAL",
        "risk_envelope",
        known_at_fields=("known_at", "available_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at", "produced_at"),
    ),
    SourceSpec(
        "macro.regime",
        "regime-latest",
        ("market_structure",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "regime",
        known_at_fields=("known_at", "available_at", "generated_at"),
        as_of_fields=("as_of", "asof", "date"),
        generated_at_fields=("generated_at", "produced_at"),
    ),
    SourceSpec(
        "macro.sector_rotation",
        "portfolio-v3-sector-central",
        ("market_structure",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "receipt_only_pr548",
        as_of_fields=("as_of",),
    ),
    SourceSpec(
        "macro.r_orth",
        "portfolio-v3-covariance-spine",
        ("independence",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "covariance_spine",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of",),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.factor_betas",
        "portfolio-v3-factor-betas",
        ("factor_risk",),
        False,
        "MEASUREMENT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "factor_betas",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.prophet",
        "portfolio-v3-prophet-index",
        ("candidate_geometry",),
        False,
        "DISPLAY_ONLY",
        "FIRST_PARTY_INTERNAL",
        "prophet",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.neural_web",
        "site-neural-web-mastermind-context",
        ("relationships",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "neural_web",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of",),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.portfolio_context",
        "portfolio-v3-portfolio-context",
        ("fundamental_state", "positioning", "event_state", "priceability"),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "portfolio_context",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.intelligence",
        "site-intelligence-by-ticker",
        ("fundamental_state", "positioning", "event_state"),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.altdata",
        "site-altdata-by-ticker",
        ("positioning",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.news",
        "site-news-by-ticker",
        ("event_state",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
)
```

The registry must resolve paths through `control_plane.contracts.contract(spec.contract_key)`. If a contract is absent or path-like input appears anywhere, emit `INVALID` and no read.

- [ ] **Step 4: Implement bounded fixed-path readers**

Implement:

```python
def _read_json_file(path: Path) -> tuple[bytes | None, Any | None, str | None]:
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        return None, None, "OVERSIZE"
    raw = path.read_bytes()
    try:
        return raw, json.loads(raw), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw, None, "MALFORMED"
```

Implement a JSONL tail reader that reads no more than 8 MiB and returns at most the last 100 valid object rows. Invalid rows must increment `omitted_rows`; they may not vanish from coverage.

Internal book source paths are exact literals beneath `registry.data_dir("autonomous")`:

```text
account.json                 required
latest.json                  optional
pending_orders.json          optional known absence
pending_target.json          optional known absence
decisions.jsonl              optional history
fills.jsonl                  optional history
positions_ledger.json        optional history
settlement_receipts/*.json   optional, sorted, metadata-bounded
```

For internal canonical Portfolio files only, use a stable first-party read:

1. open the fixed path without following a caller-selected path;
2. `fstat` before reading;
3. read at most the declared bound;
4. `fstat` again;
5. require the same device, inode, size, and nanosecond mtime before/after;
6. otherwise emit `INVALID` / `SOURCE_CHANGED_DURING_READ` and no rows.

For a stable internal read set:

```text
known_at = filesystem mtime normalized to UTC
filesystem_observed_at = the same explicit file-write clock
clock_basis = FILE_MTIME_FIRST_PARTY_STATE
```

This is lawful only because Portfolio owns both the canonical state writer and file. External Macro mtime never becomes `known_at`.

For external Macro files:

```text
clock_basis = DECLARED_SOURCE_FIELD
```

only when the exact field declared by `SourceSpec` is present. Otherwise:

```text
known_at = null
clock_basis = UNQUALIFIED_EXTERNAL_CLOCK
status = UNQUALIFIED_CLOCK
```

- [ ] **Step 5: Implement bounded projections**

Projection rules:

- `risk_envelope`: carry only schema/definition/clocks/data_state/measured_state/hazard_summary/capital_policy/coherence/authority.
- `regime`: carry only declared state/quad/liquidity/cycle/transition and source-native contradictions.
- `sector_rotation`: receipt and gap only; carry no sector/basket rows.
- `covariance_spine`: carry schema/as_of/data_state, rates/factors/dispersion/lobes summary, coverage, missing inputs, and authority.
- `factor_betas`: carry top-level factor metadata and only held-ticker beta rows.
- `prophet`: select all held-ticker plans up to 50 held names, then the first 50 non-held plans in producer-authored order; preserve original relative order among every selected row; cap the section at 100 rows; report exact omitted counts; never rerank.
- `neural_web`: carry authority declaration/effective hard-false fence, market summary, and held-ticker candidate rows only.
- `portfolio_context`: carry metadata and held-ticker rows only, split into fundamental/positioning/event/priceability sections.
- `intelligence`, `altdata`, and `news`: reuse their existing contracts; carry metadata plus held-ticker rows only into fundamental/positioning/event sections; preserve producer order and report omitted counts.
- internal decisions/fills: last 100 rows, preserve source order.
- account/latest: carry cash, position identity, shares/cost/weight, and published mark/identity fields; never request a fresh quote.

Every projection returns rows plus exact `rows_total`, `rows_returned`, and `omitted_rows`.

- [ ] **Step 6: Implement source receipt generation**

`artifact_digest` is the SHA-256 of raw bytes. `correction_generation` is:

1. a declared `revision`, `bundle_id`, or `content_generation` when present and scalar;
2. otherwise the artifact digest.

A source with `known_at > decision_cutoff` receives `FUTURE_AT_CUTOFF` and contributes no rows.

A source with no qualified external clock receives `UNQUALIFIED_CLOCK`, contributes only its receipt/digest and zero decision rows, and makes every dependent domain `PARTIAL`. It cannot make a snapshot `COMPLETE` or leak post-cutoff content into the PM information set.

A missing optional internal file receives `ABSENT_OPTIONAL` and `coverage_state=COMPLETE`; a missing external context source receives `MISSING` and `coverage_state=PARTIAL`.

- [ ] **Step 7: Run GREEN and mutation proofs**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot_sources.py \
  tests/test_decision_snapshot_contracts.py \
  tests/test_contracts.py
python3 -m compileall -q \
  portfolio/decision_snapshot_contracts.py \
  portfolio/decision_snapshot_sources.py
git diff --check
```

Mutation proofs:

1. Replace `UNQUALIFIED_EXTERNAL_CLOCK` behavior with file-mtime promotion; require `test_external_mtime_is_never_promoted_to_market_known_at` to fail.
2. Call `paper_account._load_account()` in book capture; require `test_capture_reads_fixed_sources_without_account_recovery` to fail.
3. Project rotation rows; require the #548 dependency test to fail.
4. Remove the second internal-file `fstat`; require `test_internal_source_change_during_read_returns_no_rows` to fail.

Restore and rerun GREEN.

- [ ] **Step 8: Commit**

```bash
git add \
  portfolio/decision_snapshot_sources.py \
  tests/test_decision_snapshot_sources.py
git commit -m "feat(portfolio): capture bounded V3 decision evidence"
```

---

### Task 3: Compose and Persist Immutable Correction-Safe Snapshots

**Files:**
- Create: `portfolio/decision_snapshot.py`
- Create: `tests/test_decision_snapshot.py`
- Read only: `portfolio/decision_snapshot_contracts.py`
- Read only: `portfolio/decision_snapshot_sources.py`

**Interfaces:**
- Consumes:
  - `capture_all(...) -> capture bundle`;
  - Task 1 contract/seal functions.
- Produces:
  - `DecisionSnapshotError`
  - `SnapshotNotFound`
  - `SnapshotCorrupt`
  - `SnapshotInvalidRequest`
  - `snapshot_dir(book: str) -> Path`
  - `compose_snapshot(book: str, *, decision_cutoff: str, recorded_at: str, capture: Mapping[str, Any], same_cutoff_prior_snapshot_ids: Sequence[str]) -> dict[str, Any]`
  - `create_snapshot(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]`
  - `persist_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]`
  - `load_snapshot(book: str, snapshot_id: str) -> dict[str, Any]`
  - `list_snapshots(book: str, *, limit: int = 20) -> list[dict[str, Any]]`
  - `latest_snapshot(book: str) -> dict[str, Any] | None`
  - `section_page(snapshot: Mapping[str, Any], section_id: str, *, offset: int, limit: int) -> dict[str, Any]`
  - `read_projection(book: str, *, snapshot_id: str | None, section_id: str | None, offset: int, limit: int) -> dict[str, Any]`

- [ ] **Step 1: Write RED tests for deterministic composition**

Create a fixed capture fixture with all 12 sections.

Add:

```python
def test_same_capture_and_clocks_produce_same_snapshot_id():
    first = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(),
        same_cutoff_prior_snapshot_ids=[],
    )
    second = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(),
        same_cutoff_prior_snapshot_ids=[],
    )
    assert first == second
    assert first["snapshot_id"] == second["snapshot_id"]
```

Add:

```python
def test_state_is_partial_when_any_required_domain_is_unqualified():
    capture = _capture()
    capture["sections"]["risk_truth"]["coverage_state"] = "PARTIAL"
    capture["gaps"].append({
        "code": "UNQUALIFIED_CLOCK",
        "source_id": "macro.risk_envelope",
        "owner": "macro",
        "detail": "known_at unavailable",
    })
    result = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=capture,
        same_cutoff_prior_snapshot_ids=[],
    )
    assert result["state"] == "PARTIAL"
    assert result["coverage_state"] == "PARTIAL"
```

Add:

```python
def test_same_cutoff_same_generation_reuses_existing_snapshot_despite_later_recorded_at(
    snapshot_root,
):
    first = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
    )
    second = snapshots.create_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
    )
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["created"] is False
    assert len(list(snapshots.snapshot_dir("autonomous").glob("*.json"))) == 1


def test_same_cutoff_new_generation_is_explicit_correction():
    original = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:01:00Z",
        capture=_capture(generation="sha256:" + "a" * 64),
        same_cutoff_prior_snapshot_ids=[],
    )
    corrected = snapshots.compose_snapshot(
        "autonomous",
        decision_cutoff="2026-09-15T20:00:00Z",
        recorded_at="2026-09-15T20:10:00Z",
        capture=_capture(generation="sha256:" + "b" * 64),
        same_cutoff_prior_snapshot_ids=[original["snapshot_id"]],
    )
    assert corrected["state"] == "CORRECTED_GENERATION_AVAILABLE"
    assert corrected["coverage_state"] == "COMPLETE"
    assert corrected["correction"] == {
        "status": "CORRECTED_GENERATION_AVAILABLE",
        "same_cutoff_prior_snapshot_ids": [original["snapshot_id"]],
    }
    assert corrected["snapshot_id"] != original["snapshot_id"]
```

- [ ] **Step 2: Write RED tests for immutable persistence**

Use a fixture that monkeypatches `snapshots._ROOT` to `tmp_path`.

Add:

```python
def test_persist_is_create_once_and_exact_retry_is_noop(snapshot_root):
    payload = _sealed_snapshot()
    first = snapshots.persist_snapshot(payload)
    before = Path(first["path"]).read_bytes()
    second = snapshots.persist_snapshot(payload)
    assert second["created"] is False
    assert Path(second["path"]).read_bytes() == before


def test_existing_content_address_with_wrong_bytes_freezes(snapshot_root):
    payload = _sealed_snapshot()
    path = snapshots._snapshot_path("autonomous", payload["snapshot_id"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{}")
    with pytest.raises(snapshots.SnapshotCorrupt):
        snapshots.persist_snapshot(payload)
    assert path.read_bytes() == b"{}"


def test_old_snapshot_remains_byte_identical_after_correction(snapshot_root):
    original = _sealed_snapshot(generation="a")
    corrected = _sealed_snapshot(generation="b", prior=[original["snapshot_id"]])
    snapshots.persist_snapshot(original)
    old_path = snapshots._snapshot_path("autonomous", original["snapshot_id"])
    old_bytes = old_path.read_bytes()
    snapshots.persist_snapshot(corrected)
    assert old_path.read_bytes() == old_bytes
    assert snapshots.load_snapshot(
        "autonomous", original["snapshot_id"]
    ) == original
```

Add path rejection:

```python
@pytest.mark.parametrize(
    "book,snapshot_id",
    [
        ("../autonomous", "sha256:" + "a" * 64),
        ("AUTONOMOUS", "sha256:" + "a" * 64),
        ("autonomous", "../../secret"),
        ("autonomous", "sha256:" + "g" * 64),
    ],
)
def test_storage_identity_rejects_path_control(book, snapshot_id):
    with pytest.raises(snapshots.SnapshotInvalidRequest):
        snapshots.load_snapshot(book, snapshot_id)
```

- [ ] **Step 3: Run RED**

Run:

```bash
python3 -m pytest -q tests/test_decision_snapshot.py
```

Expected: import failure because `portfolio.decision_snapshot` does not exist.

- [ ] **Step 4: Implement state derivation and composition**

State law:

```python
def _coverage_state(sections: Mapping[str, Mapping[str, Any]]) -> str:
    values = {row["coverage_state"] for row in sections.values()}
    if "BLOCKED" in values:
        return "BLOCKED"
    if values == {"COMPLETE"}:
        return "COMPLETE"
    return "PARTIAL"
```

`compose_snapshot` must:

1. normalize `decision_cutoff` and `recorded_at`;
2. reject `recorded_at < decision_cutoff`;
3. require exactly the 12 `SECTION_IDS`;
4. sort sources by `source_id`;
5. sort generation-set rows by `source_id`;
6. sort gaps by `(code, source_id, owner, detail)`;
7. derive coverage summary;
8. set correction status;
9. seal and verify;
10. refuse any payload above 262,144 bytes.

The root authority is fixed:

```python
"authority": {
    "write_permitted": False,
    "execution_authority": False,
    "numeric_target_authority": False,
}
```

- [ ] **Step 5: Implement create-only storage**

Use:

```text
data/shadow/decision_snapshots/autonomous/<64hex>.json
```

No cutoff folder, latest pointer, mutable index, or separate correction file.

`_snapshot_path` must accept only:

```text
book == "autonomous"
snapshot_id matches ^sha256:[0-9a-f]{64}$
```

Write canonical bytes with `os.open(path, O_WRONLY | O_CREAT | O_EXCL, 0o600)`, `fsync`, and directory `fsync`. If the path already exists, read and verify exact canonical bytes. Never replace.

- [ ] **Step 6: Implement listing and section paging**

`list_snapshots`:

- scans only `*.json` directly under the fixed book directory;
- refuses symlinks and non-regular files;
- verifies every returned snapshot;
- sorts by `(decision_cutoff, recorded_at, snapshot_id)` descending;
- caps `limit` to 1..100;
- returns compact manifest rows, not full sections.

`section_page`:

- accepts only `SECTION_IDS`;
- accepts integer, non-Boolean `offset >= 0`;
- accepts integer, non-Boolean `1 <= limit <= 100`;
- returns source section metadata plus the selected rows;
- includes `next_offset` or `None`;
- refuses a response above 65,536 bytes.

- [ ] **Step 7: Implement correction discovery in `create_snapshot`**

`create_snapshot` must:

1. list verified same-cutoff prior snapshots;
2. capture current sources;
3. compare the sorted `source_generation_set`;
4. exact same generation + same clocks -> exact retry/no new identity;
5. same cutoff plus the same sorted `source_generation_set` -> return the existing verified snapshot even when the new operator `recorded_at` is later; do not mint a duplicate identity;
6. changed generation at the same cutoff -> include all prior same-cutoff IDs and produce `CORRECTED_GENERATION_AVAILABLE`;
7. persist only the genuinely new sealed snapshot.

Do not rewrite the original.

- [ ] **Step 8: Run GREEN and mutation proofs**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot.py \
  tests/test_decision_snapshot_contracts.py \
  tests/test_decision_snapshot_sources.py
python3 -m compileall -q \
  portfolio/decision_snapshot.py \
  portfolio/decision_snapshot_contracts.py \
  portfolio/decision_snapshot_sources.py
git diff --check
```

Mutation proofs:

1. Change persistence from `O_EXCL` to replace; require the corrupt-existing-file test to fail.
2. Drop prior IDs from corrected snapshots; require correction test to fail.
3. Return rows without verifying snapshot digest; add a byte mutation and require load to raise.

Restore and rerun GREEN.

- [ ] **Step 9: Commit**

```bash
git add \
  portfolio/decision_snapshot.py \
  tests/test_decision_snapshot.py
git commit -m "feat(portfolio): persist immutable V3 decision snapshots"
```

---

### Task 4: Add the Explicit Operator CLI and Runbook

**Files:**
- Create: `scripts/portfolio_decision_snapshot.py`
- Create: `tests/test_decision_snapshot_cli.py`
- Create: `docs/runbooks/portfolio-v3-decision-snapshot.md`

**Interfaces:**
- Consumes:
  - `decision_snapshot.create_snapshot`
  - `decision_snapshot.latest_snapshot`
  - `decision_snapshot.load_snapshot`
  - `decision_snapshot.section_page`
- Produces CLI:
  - `compose --book autonomous --decision-cutoff <UTC> --recorded-at <UTC>`
  - `status --book autonomous`
  - `show --book autonomous [--snapshot-id <id>] [--section <id>] [--offset N] [--limit N]`

- [ ] **Step 1: Write RED CLI tests**

Create `tests/test_decision_snapshot_cli.py` with subprocess-free direct `main(argv)` tests.

Add:

```python
def test_compose_requires_both_explicit_clocks(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.decision_snapshot,
        "create_snapshot",
        lambda *a, **k: pytest.fail("must not run"),
    )
    assert cli.main(["compose", "--book", "autonomous"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "invalid_request"
    assert "decision-cutoff" in error["error"]
    assert "recorded-at" in error["error"]
```

Add:

```python
def test_compose_calls_writer_once_and_prints_bounded_receipt(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        cli.decision_snapshot,
        "create_snapshot",
        lambda book, decision_cutoff, recorded_at: seen.append(
            (book, decision_cutoff, recorded_at)
        ) or {
            "snapshot_id": "sha256:" + "a" * 64,
            "state": "PARTIAL",
            "coverage_state": "PARTIAL",
        },
    )
    rc = cli.main([
        "compose",
        "--book", "autonomous",
        "--decision-cutoff", "2026-09-15T20:00:00Z",
        "--recorded-at", "2026-09-15T20:01:00Z",
    ])
    assert rc == 0
    assert seen == [(
        "autonomous",
        "2026-09-15T20:00:00Z",
        "2026-09-15T20:01:00Z",
    )]
    assert json.loads(capsys.readouterr().out)["snapshot_id"] == (
        "sha256:" + "a" * 64
    )
```

Add:

```python
def test_cli_has_no_path_root_url_or_output_override():
    parser = cli.build_parser()
    help_text = parser.format_help()
    for forbidden in ("--path", "--root", "--url", "--output"):
        assert forbidden not in help_text
```

Add status/show no-write tests by monkeypatching `create_snapshot` to fail and verifying those commands call only read functions.

- [ ] **Step 2: Run RED**

Run:

```bash
python3 -m pytest -q tests/test_decision_snapshot_cli.py
```

Expected: import failure because the CLI does not exist.

- [ ] **Step 3: Implement the CLI**

Use `argparse` with required subcommands. JSON is written to stdout; errors are closed JSON on stderr with nonzero exit.

Do not default either clock.

`compose` prints only:

```json
{
  "schema": "mastermind.portfolio_decision_snapshot.compose_receipt.v1",
  "book": "autonomous",
  "snapshot_id": "sha256:...",
  "state": "PARTIAL",
  "coverage_state": "PARTIAL",
  "write_root": "data/shadow/decision_snapshots/autonomous",
  "write_permitted_outside_shadow": false,
  "execution_authority": false
}
```

`status` prints the latest compact manifest or `NO_SNAPSHOT`.

`show` prints the verified manifest or a bounded section page.

- [ ] **Step 4: Write the runbook**

The runbook must include exact commands:

```bash
python3 scripts/portfolio_decision_snapshot.py compose \
  --book autonomous \
  --decision-cutoff 2026-09-15T20:00:00Z \
  --recorded-at 2026-09-15T20:01:00Z

python3 scripts/portfolio_decision_snapshot.py status \
  --book autonomous

python3 scripts/portfolio_decision_snapshot.py show \
  --book autonomous \
  --section risk_truth \
  --offset 0 \
  --limit 50
```

It must explain:

- `PARTIAL` is a valid honest result;
- #548 keeps rotation partial;
- a correction creates another immutable file;
- no command retries an ambiguous write blindly;
- rollback is removal of the S0 source release plus preservation of already-written immutable evidence;
- immutable snapshots are evidence, not executable targets;
- exact before/after V2-state hash procedure from Task 8.

- [ ] **Step 5: Run GREEN**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot_cli.py \
  tests/test_decision_snapshot.py
python3 -m compileall -q \
  scripts/portfolio_decision_snapshot.py \
  portfolio/decision_snapshot.py
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add \
  scripts/portfolio_decision_snapshot.py \
  tests/test_decision_snapshot_cli.py \
  docs/runbooks/portfolio-v3-decision-snapshot.md
git commit -m "feat(portfolio): add decision snapshot operator workflow"
```

---

### Task 5: Add the Read-Only Snapshot API

**Files:**
- Modify: `app/web.py` near `api_forward_evaluation`
- Create: `tests/test_decision_snapshot_api.py`
- Read only: `portfolio/decision_snapshot.py`

**Interfaces:**
- Consumes:
  - `decision_snapshot.read_projection(...)`
- Produces:
  - `GET /api/decision-snapshot`
  - query parameters:
    - `book: str = "autonomous"`
    - `snapshot_id: str | None = None`
    - `section: str | None = None`
    - `offset: int = 0`
    - `limit: int = 50`

- [ ] **Step 1: Write RED API tests**

Use `TestClient` without scheduler startup.

Add:

```python
def test_api_is_read_only_and_never_composes(monkeypatch):
    from portfolio import decision_snapshot
    monkeypatch.setattr(
        decision_snapshot,
        "create_snapshot",
        lambda *a, **k: pytest.fail("GET must not compose"),
    )
    monkeypatch.setattr(
        decision_snapshot,
        "read_projection",
        lambda **kwargs: {
            "schema": "mastermind.portfolio_decision_snapshot.status.v1",
            "book": "autonomous",
            "status": "NO_SNAPSHOT",
            "write_permitted": False,
            "execution_authority": False,
        },
    )
    response = _client().get("/api/decision-snapshot")
    assert response.status_code == 200
    assert response.json()["status"] == "NO_SNAPSHOT"
```

Add:

```python
@pytest.mark.parametrize("book", [
    "flagship",
    "AUTONOMOUS",
    "../autonomous",
    "not-a-book",
])
def test_api_rejects_non_s0_book_before_storage_read(monkeypatch, book):
    from portfolio import decision_snapshot
    monkeypatch.setattr(
        decision_snapshot,
        "read_projection",
        lambda **kwargs: pytest.fail("invalid book reached storage"),
    )
    response = _client().get(
        "/api/decision-snapshot", params={"book": book}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "unsupported_snapshot_book"
```

Add:

```python
@pytest.mark.parametrize("params", [
    {"snapshot_id": "../../secret"},
    {"section": "../../secret"},
    {"offset": -1},
    {"offset": True},
    {"limit": 0},
    {"limit": 101},
])
def test_api_invalid_request_is_4xx_and_never_writes(params, monkeypatch):
    from portfolio import decision_snapshot
    monkeypatch.setattr(
        decision_snapshot,
        "create_snapshot",
        lambda *a, **k: pytest.fail("must not write"),
    )
    response = _client().get("/api/decision-snapshot", params=params)
    assert response.status_code in {400, 404, 422}
```

Add explicit snapshot and section-response tests. Assert:

```text
Cache-Control: no-store
write_permitted=false
execution_authority=false
UTF-8 response <= 65536 for a section page
```

- [ ] **Step 2: Run RED**

Run:

```bash
python3 -m pytest -q tests/test_decision_snapshot_api.py
```

Expected: 404 because route does not exist.

- [ ] **Step 3: Implement the route**

Add near `/api/forward-evaluation`:

```python
@router.get("/api/decision-snapshot")
def api_decision_snapshot(
    book: str = "autonomous",
    snapshot_id: str | None = None,
    section: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> JSONResponse:
    from portfolio import decision_snapshot

    if book != "autonomous":
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unsupported_snapshot_book",
                "book": book,
                "allowed": ["autonomous"],
            },
        )
    try:
        payload = decision_snapshot.read_projection(
            book=book,
            snapshot_id=snapshot_id,
            section_id=section,
            offset=offset,
            limit=limit,
        )
    except decision_snapshot.SnapshotInvalidRequest as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_request", "message": str(exc)},
        ) from exc
    except decision_snapshot.SnapshotNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "snapshot_not_found", "message": str(exc)},
        ) from exc
    except decision_snapshot.SnapshotCorrupt as exc:
        return JSONResponse(
            {
                "schema": "mastermind.portfolio_decision_snapshot.status.v1",
                "book": book,
                "status": "INVALID",
                "error": str(exc),
                "write_permitted": False,
                "execution_authority": False,
            },
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        payload,
        headers={"Cache-Control": "no-store"},
    )
```

The route may not import source capture, CLI, model, paper account, or settlement modules.

- [ ] **Step 4: Run GREEN and route-neighbor tests**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot_api.py \
  tests/test_web.py \
  tests/test_forward_evaluation.py
python3 -m compileall -q app/web.py
git diff --check
```

Expected: all pass.

Mutation proof: make the GET route call `create_snapshot`; require `test_api_is_read_only_and_never_composes` to fail. Restore and rerun.

- [ ] **Step 5: Commit**

```bash
git add app/web.py tests/test_decision_snapshot_api.py
git commit -m "feat(web): expose read-only V3 decision snapshot status"
```

---

### Task 6: Add the US-V3-Only Evidence Inspector

**Files:**
- Modify: `app/static/index.html`
- Create: `tests/test_decision_snapshot_ui.py`
- Read only: `app/web.py`

**Interfaces:**
- Consumes:
  - `GET /api/decision-snapshot?book=autonomous`
- Produces:
  - collapsed panel `#decision-snapshot`
  - `_decisionSnapshot`
  - `renderDecisionSnapshot()`
  - US-only scope list `PF_US_V3_ONLY`

- [ ] **Step 1: Write RED structural UI tests**

Create:

```python
HTML = Path("app/static/index.html").read_text(encoding="utf-8")


def test_snapshot_panel_is_us_v3_scoped_and_bilingual():
    assert 'id="decision-snapshot"' in HTML
    assert "V3 Decision Snapshot" in HTML
    assert "V3 决策快照" in HTML
    assert "PF_US_V3_ONLY" in HTML
    assert "'decision-snapshot'" in HTML


def test_snapshot_fetch_is_read_only_and_singleton_hydrated():
    assert "fetch('/api/decision-snapshot?book=autonomous')" in HTML
    assert "renderDecisionSnapshot()" in HTML
    assert "/api/decision-snapshot" not in _write_methods(HTML)


def test_snapshot_renderer_escapes_server_text():
    block = _function_block(HTML, "renderDecisionSnapshot")
    for field in ("snapshot_id", "source_id", "status", "error_code"):
        assert f"esc(" in block
    assert "innerHTML = d." not in block


def test_non_us_books_hide_snapshot_panel():
    block = _function_block(HTML, "applyPortfolioScope")
    assert "var usV3 = _portfolio === 'autonomous'" in block
    assert "PF_US_V3_ONLY.forEach" in block
```

`_write_methods` must scan fetch blocks and return any POST/PUT/PATCH/DELETE use for the target URL. `_function_block` must use brace counting, not a fragile one-line regular expression.

- [ ] **Step 2: Run RED**

Run:

```bash
python3 -m pytest -q tests/test_decision_snapshot_ui.py
```

Expected: failures because panel, fetch, and renderer are absent.

- [ ] **Step 3: Add the collapsed panel near Shadow Books**

Insert before `#shadow-books`:

```html
<!-- V3-S0 DECISION SNAPSHOT — read-only evidence available to the future PM -->
<div class="mm-section">
  <div class="panel span12 mm-collapsible mm-collapsed"
       id="decision-snapshot" style="grid-column:span 12">
    <div class="mm-empty">
      <span class="mm-empty-icon">⊙</span>
      <span class="l-en">Loading V3 decision evidence…</span>
      <span class="l-zh">加载 V3 决策证据中…</span>
    </div>
  </div>
</div>
```

Add `decision-snapshot` to `_collapsed`, collapse initialization, and the final `applyColl` calls.

- [ ] **Step 4: Add US-only scope behavior**

Define:

```javascript
var PF_US_V3_ONLY = ['decision-snapshot'];
```

In `applyPortfolioScope()`:

```javascript
var usV3 = _portfolio === 'autonomous';
PF_US_V3_ONLY.forEach(function(id) {
  var p = E(id); if (!p) return;
  var s = p.closest('.mm-section');
  if (s) s.style.display = usV3 ? '' : 'none';
});
```

Do not add the panel to `PF_AUTO_ONLY`; that list includes CN/HK/archived Brain books.

- [ ] **Step 5: Hydrate once and render from cached data**

Add:

```javascript
var _decisionSnapshot = null;
```

Add one request to `_hydrateShared()`:

```javascript
fetch('/api/decision-snapshot?book=autonomous')
  .then(function(r) { return r.ok ? r.json() : null; })
  .catch(function() { return null; })
```

Update settled-result indexing exactly once and call `renderDecisionSnapshot()` from `_renderAll()`.

- [ ] **Step 6: Implement the bounded renderer**

The panel must show:

- state chip;
- coverage chip;
- cutoff;
- recorded time;
- first 16 snapshot-ID hex characters;
- source counts;
- per-domain coverage table;
- source/gap table;
- explicit #548 partial dependency when present;
- `write_permitted=false`;
- no return forecast, ranking, recommendation, or execution language.

State colors:

```text
COMPLETE -> var(--up)
PARTIAL / CORRECTED_GENERATION_AVAILABLE -> var(--warn)
BLOCKED / INVALID -> var(--down)
NO_SNAPSHOT / unavailable -> var(--muted)
```

The renderer must use `esc()` for every server string and cap displayed sources/gaps to 40 rows even if the API contract regresses.

- [ ] **Step 7: Run GREEN and UI neighbors**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot_ui.py \
  tests/test_web.py \
  tests/test_decision_snapshot_api.py
git diff --check
```

Expected: all pass.

Mutation proof: remove the `usV3` scope check and require `test_non_us_books_hide_snapshot_panel` to fail. Restore and rerun.

- [ ] **Step 8: Commit**

```bash
git add app/static/index.html tests/test_decision_snapshot_ui.py
git commit -m "feat(ui): add V3 decision evidence inspector"
```

---

### Task 7: Prove Zero V2, Provider, and Settlement Effects

**Files:**
- Create: `tests/test_decision_snapshot_no_effect.py`
- Read only: all S0 source modules
- Read only: `portfolio/paper_account.py`
- Read only: `brain/provider_waterfall.py`
- Read only: `brain/client.py`

**Interfaces:**
- Consumes: `decision_snapshot.create_snapshot`
- Produces: regression proof that S0 creates only one immutable shadow artifact and no existing state/provider effect.

- [ ] **Step 1: Write a full before/after state-hash test**

Create fixed fixture bytes for:

```text
data/portfolios/autonomous/account.json
data/portfolios/autonomous/fills.jsonl
data/portfolios/autonomous/nav_history.jsonl
data/portfolios/autonomous/decisions.jsonl
data/portfolios/autonomous/pending_orders.json
data/portfolios/autonomous/pending_target.json
data/portfolios/autonomous/_pending_decision.json
```

Hash all seven before the call.

Call:

```python
receipt = decision_snapshot.create_snapshot(
    "autonomous",
    decision_cutoff="2026-09-15T20:00:00Z",
    recorded_at="2026-09-15T20:01:00Z",
)
```

Assert:

```python
assert _hashes(state_paths) == before
created = list(
    (root / "data/shadow/decision_snapshots/autonomous").glob("*.json")
)
assert len(created) == 1
assert receipt["snapshot_id"] in created[0].read_text()
```

- [ ] **Step 2: Add provider/network/process fuses**

Before import/call, monkeypatch:

```python
socket.socket.connect = fail
subprocess.run = fail
subprocess.Popen = fail
brain.client.available = fail
brain.provider_waterfall.run = fail
paper_account._current_price = fail
paper_account._load_account = fail
paper_account.queue_target = fail
paper_account.rebalance = fail
```

The snapshot call must still succeed from fixed local artifacts.

- [ ] **Step 3: Add import-boundary proof**

Parse S0 modules with `ast` and reject imports from:

```text
brain.client
brain.provider_waterfall
brain.key_rotor
bot.settle
bot.autonomous
portfolio.paper_account
portfolio.shadow_books
portfolio.forward_evaluation
```

`decision_snapshot_sources.py` may import `portfolio.registry` and `control_plane.contracts` only from current project owners.

- [ ] **Step 4: Add no-hidden-clock proof**

Scan:

```text
portfolio/decision_snapshot_contracts.py
portfolio/decision_snapshot_sources.py
portfolio/decision_snapshot.py
```

Reject:

```text
datetime.now
date.today
time.time
utcnow
```

`datetime.fromtimestamp` is allowed only for fixed file metadata. It may populate `known_at` only for a stable first-party Portfolio-state read labeled `FILE_MTIME_FIRST_PARTY_STATE`; external Macro mtime may populate only `filesystem_observed_at`.

- [ ] **Step 5: Run the owning regression set**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot_contracts.py \
  tests/test_decision_snapshot_sources.py \
  tests/test_decision_snapshot.py \
  tests/test_decision_snapshot_cli.py \
  tests/test_decision_snapshot_api.py \
  tests/test_decision_snapshot_ui.py \
  tests/test_decision_snapshot_no_effect.py \
  tests/test_contracts.py \
  tests/test_web.py \
  tests/test_forward_evaluation.py \
  tests/test_shadow_books.py \
  tests/test_portfolio_intelligence.py
```

If `claude_agent_sdk` is available, also run:

```bash
python3 -m pytest -q tests/test_portfolio_intelligence_mcp.py
```

Expected: green with no provider/network access.

- [ ] **Step 6: Run mutation controls**

Perform and restore each mutation:

1. Replace direct account-file read with `_load_account`; no-effect test must fail.
2. Write a mutable `latest.json`; path-ceiling/no-effect test must fail.
3. Remove `FUTURE_AT_CUTOFF` exclusion; source test must fail.
4. Use file mtime as external `known_at`; source test must fail.
5. Make API compose when no snapshot exists; API test must fail.
6. Show the S0 panel for CN/HK; UI test must fail.

Record exact failing test names in the PR body.

- [ ] **Step 7: Commit**

```bash
git add tests/test_decision_snapshot_no_effect.py
git commit -m "test(portfolio): prove S0 has no live book effects"
```

---

### Task 8: Current-Base Integration, Independent Review, and S0 Source Release

**Files:**
- Modify only when needed to resolve a demonstrated current-base conflict.
- No feature broadening.
- PR #658 remains untouched except for a cross-reference to the separate implementation PR.

**Interfaces:**
- Consumes: Tasks 1-7 exact commits on operation `mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001`.
- Produces: reviewed and protected S0 source in the separate implementation PR. It does not itself create a real snapshot.

- [ ] **Step 1: Confirm the separate implementation carrier identity**

Record:

```text
operation: mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
branch: sol/mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001
implementation PR: <exact separate PR number>
architecture/plan parent: Mastermind PR #658
workspace: exact mmx-workspace receipt
```

Refuse if implementation commits landed on #658 or any other carrier.

- [ ] **Step 2: Reconcile protected movement**

Run:

```bash
git fetch origin master
git diff --name-status HEAD..origin/master
git diff --name-only origin/master...HEAD
git status --short
```

Classify movement using current `RECONCILE_STATE.md`:

- disjoint, material source unchanged -> compose current base and reuse semantic review when lawful;
- owned path or governing contract changed -> repair minimally and require fresh review;
- ambiguous -> hold.

Do not create an ancestry-only commit merely to become zero-behind.

- [ ] **Step 3: Run focused and full repository gates**

Run:

```bash
python3 -m pytest -q \
  tests/test_decision_snapshot_contracts.py \
  tests/test_decision_snapshot_sources.py \
  tests/test_decision_snapshot.py \
  tests/test_decision_snapshot_cli.py \
  tests/test_decision_snapshot_api.py \
  tests/test_decision_snapshot_ui.py \
  tests/test_decision_snapshot_no_effect.py \
  tests/test_contracts.py \
  tests/test_web.py \
  tests/test_forward_evaluation.py \
  tests/test_shadow_books.py \
  tests/test_portfolio_intelligence.py

python3 scripts/ci_pytest.py --plan-only
git diff --check
```

Then run the repository-required hosted `test` and security checks on the exact implementation PR head.

- [ ] **Step 4: Obtain independent exact-head review**

The reviewer must verify:

- implementation paths match the plan ceiling;
- PR #658 contains no implementation source;
- no #548 duplication;
- canonical JSON serialization is reused from `control_plane.wake_events`;
- no hidden clock;
- no external mtime promoted to market knowledge;
- internal first-party mtime is used only after a stable read and is labeled distinctly from external market knowledge;
- no account recovery;
- no mutable index or second store;
- no model/provider/network path;
- no active-book or settlement path;
- same-generation retry reuses the existing snapshot;
- correction preserves original bytes;
- API is read-only;
- UI distinguishes partial/blocked/corrected;
- capability remains `BUILT_NOT_PROVEN` before installed proof.

- [ ] **Step 5: Update the separate implementation PR accurately**

Its body must state:

```text
PARENT ARCHITECTURE/PLAN: protected PR #658
S0 SOURCE: exact state from evidence
V3 OVERALL: PARTIAL / downstream capabilities NOT_BUILT
LIVE PORTFOLIO EFFECT: NONE
```

Include:

- exact protected base;
- exact semantic head;
- exact changed paths;
- focused test counts;
- mutation receipts;
- current-base integration identity;
- independent review;
- hosted checks;
- held production-canary gate.

Add only a cross-reference comment to #658 naming the separate implementation PR; do not turn #658 into a mutable implementation tracker.

- [ ] **Step 6: Protect S0 source through the normal merge path**

After approval and required checks:

- mark the separate implementation PR Ready only through the authorized release owner;
- merge without bypassing protection;
- read back the actual protected merge SHA;
- verify the merged tree contains exactly the accepted S0 bytes.

Source merge yields:

```text
S0 source: BUILT_NOT_PROVEN
installation: NONE
real snapshot: NONE
V3 live allocator: NONE
```

Release the S0 workspace only after source custody and any pending effect are reconciled.

### Task 9: Deploy the Exact Merge and Prove One Real Current Snapshot

**Files:**
- Runtime evidence only under `data/shadow/decision_snapshots/autonomous/`.
- No Git-tracked source changes unless a real defect requires a separate repair cycle.

**Interfaces:**
- Consumes: exact protected S0 merge.
- Produces:
  - one real immutable snapshot;
  - read-only API readback;
  - visible operator inspector;
  - no-effect hashes;
  - rollback receipt.

- [ ] **Step 1: Deploy the exact protected merge**

On the canonical VPS release path:

```bash
git fetch origin master
merge_sha=$(git rev-parse origin/master)
./scripts/deploy_from_git.sh "$merge_sha"
curl -fsS http://127.0.0.1:8001/health
```

Require HTTP 200 and exact deployed SHA in health.

- [ ] **Step 2: Capture the no-effect baseline**

Run this exact bounded Python receipt on the canonical runtime data root:

```bash
python3 - <<'PY' > /tmp/v3-s0-before.sha256
from pathlib import Path
import hashlib

paths = (
    Path("data/portfolios/autonomous/account.json"),
    Path("data/portfolios/autonomous/fills.jsonl"),
    Path("data/portfolios/autonomous/nav_history.jsonl"),
    Path("data/portfolios/autonomous/decisions.jsonl"),
    Path("data/portfolios/autonomous/pending_orders.json"),
    Path("data/portfolios/autonomous/pending_target.json"),
    Path("data/portfolios/autonomous/_pending_decision.json"),
)
for path in paths:
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "ABSENT"
    print(f"{path.as_posix()} {digest}")
PY
```

The receipt records missing optional files as `ABSENT` without creating them or causing the command to fail.

- [ ] **Step 3: Compose exactly one real snapshot with explicit clocks**

Use operator-resolved UTC values:

```bash
decision_cutoff=$(date -u +%Y-%m-%dT%H:%M:%SZ)
recorded_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

python3 scripts/portfolio_decision_snapshot.py compose \
  --book autonomous \
  --decision-cutoff "$decision_cutoff" \
  --recorded-at "$recorded_at" \
  | tee /tmp/v3-s0-compose-receipt.json
```

Expected honest first result:

- `PARTIAL` is acceptable;
- rotation is partial while #548 is unresolved;
- unknown source clocks remain visible;
- snapshot exists only under the shadow root.

- [ ] **Step 4: Verify immutable CLI and API readback**

Run:

```bash
python3 scripts/portfolio_decision_snapshot.py status \
  --book autonomous \
  | tee /tmp/v3-s0-status.json

curl -fsS \
  'http://127.0.0.1:8001/api/decision-snapshot?book=autonomous' \
  | tee /tmp/v3-s0-api.json

curl -fsS \
  'http://127.0.0.1:8001/api/decision-snapshot?book=autonomous&section=risk_truth&offset=0&limit=50' \
  | tee /tmp/v3-s0-risk-section.json
```

Require identical snapshot IDs across compose/status/API and `write_permitted=false`.

- [ ] **Step 5: Prove no V2 state changed**

Re-run the exact bounded Python receipt from Step 2 to `/tmp/v3-s0-after.sha256` and compare:

```bash
diff -u /tmp/v3-s0-before.sha256 /tmp/v3-s0-after.sha256
```

Expected: no diff.

Also require:

```bash
find data/shadow/decision_snapshots/autonomous \
  -maxdepth 1 -type f -name '*.json' -print
```

to show the new content-addressed file and no mutable index.

- [ ] **Step 6: Prove exact retry and correction behavior**

Exact retry uses the same cutoff but a later observation timestamp:

```bash
retry_recorded_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python3 scripts/portfolio_decision_snapshot.py compose \
  --book autonomous \
  --decision-cutoff "$decision_cutoff" \
  --recorded-at "$retry_recorded_at"
```

Require the same snapshot ID and no second file because the sorted source-generation set is unchanged.

Correction canary uses a controlled non-market fixture only in the test/runtime staging namespace, not production market artifacts:

- copy the accepted fixture source generation;
- change the declared generation while preserving the same cutoff;
- compose in the isolated test root;
- prove a second immutable ID, prior bytes unchanged, and corrected status.

Do not alter live Macro artifacts merely to demonstrate correction.

- [ ] **Step 7: Prove the operator journey in a real browser**

At 1440x900, 820x1180, and 390x844:

1. open the deployed Portfolio dashboard;
2. select `US Brain`;
3. expand `V3 Decision Snapshot`;
4. verify state, cutoff, snapshot ID, source/domain coverage, and gaps render;
5. switch to CN and HK and verify the panel is absent;
6. toggle dark/light and EN/ZH;
7. require zero page errors, zero console errors, and no failed `/api/decision-snapshot` request;
8. retain screenshots and network/console receipts.

A fixture-only render is not installed proof.

- [ ] **Step 8: Record capability state and continuation**

If all source, deployment, snapshot, API, no-effect, and browser evidence passes:

```text
V3-S0 Decision Snapshot: PROVEN_LIVE
V3 root PM: NOT_BUILT
V3 constructor: NOT_BUILT
V3 shadow portfolio: NOT_BUILT
V3 overall: PARTIAL
live V2 behavior: unchanged
```

Update durable Agent OS/architecture continuity with:

- exact protected SHA;
- exact snapshot ID;
- source-generation set digest;
- honest state and gaps;
- no-effect hash receipt;
- browser evidence;
- #548 dependency;
- exact next action: V3-S1 Claim and PM View design/plan, not allocator work.

If any no-effect hash changes, classify the release `BROKEN`, stop, reconcile the owning writer, and do not proceed to S1.

---

## Plan Self-Review Result

### Spec coverage

The plan maps every S0 requirement to an implementation task:

- separate design and implementation carriers -> Tasks 0 and 8;
- immutable, content-addressed snapshot -> Tasks 1 and 3;
- canonical JSON owner reuse -> Task 1;
- explicit point-in-time clocks -> Tasks 1 and 2;
- book/risk/opportunity/source coverage -> Task 2;
- complete/partial/blocked/corrected states -> Tasks 1 and 3;
- same-date correction without rewrite -> Task 3;
- bounded closed payloads and pages -> Tasks 1, 2, 3, and 5;
- no arbitrary file read -> Tasks 2, 3, and 5;
- no model/provider/settlement effect -> Task 7;
- #548 no-duplication -> Tasks 0 and 2;
- visible source/coverage inspector -> Task 6;
- real current-data proof -> Task 9;
- durable continuation -> Task 9.

### Type and name consistency

The plan consistently uses:

```text
decision_snapshot_contracts
decision_snapshot_sources
decision_snapshot
decision_cutoff
recorded_at
snapshot_id
section_id
coverage_state
correction_generation
canonical_json_bytes (imported from control_plane.wake_events)
read_projection
```

No later task refers to an interface absent from an earlier task.

### Scope conclusion

This plan delivers one independently useful read-only vertical on a separate implementation carrier after the records-only architecture/plan is protected. It does not include the PM, research agents, portfolio constructor, execution staging, or promotion logic. Those remain separate plans after S0 is proven.
