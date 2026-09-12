# Fresh-Sol Evaluation Harness F0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one production-inert OHF runner that can launch genuinely fresh `gpt-5.6-sol` App Server contexts against immutable Sol Skillpack bytes and emit verbatim, identity-bound behavioral evidence for MAS-136.

**Architecture:** Extend the existing `scripts/ohf/**` live-laboratory substrate only. Each sample materializes exact Git-backed procedure bytes into a fresh isolated workspace, starts a new contained Codex App Server process, attests the effective model/capability surface before `thread/start`, runs exactly one scenario turn in one brand-new native thread, reads the canonical thread result, proves cleanup, and emits a create-only evidence artifact. The runner owns no Executive lifecycle, scheduling, retry, grading, or authority.

**Tech Stack:** Python 3.12+, stdlib (`argparse`, `dataclasses`, `hashlib`, `json`, `pathlib`, `subprocess`, `tempfile`, `uuid`), PyYAML already present in repository, existing `scripts.ohf.laboratory.AppServerClient`, `scripts.ohf.protocol`, `scripts.ohf.redaction`, `scripts.ohf.p1a_capability_policy`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-fresh-sol-evaluation-harness-f0-design.md`

## Global Constraints

- Protected implementation pickup is `acc7ebc4bf44a4857168f481a745b2e57d5be585`; re-pin protected `master` before final return and report any material collision.
- Do not modify `control_plane/**`, `docs/sol_skills/**`, `scripts/sol_commission_lint.py`, #147 procedure/evidence files, Agent OS, Linear, Slack, Executive configuration, or production state.
- Extend existing OHF primitives; do not add a database, daemon, scheduler, queue, session registry, credential store, retry plane, or provider router.
- No network fetches for Skillpack materialization. Required Git objects must already exist locally.
- Control arm is exactly `51f9942733b86e550bb9169d2a43462bd28e774f` / Skillpack 1.0.0. Amended arm is exactly `8209e1f31da15f8effc23a9899a5c5a02d30cab4` / Skillpack 1.1.0.
- Release-required MAS-136 scenarios are exactly `S2`, `S6`, `S7`, `S8`; scenario wording comes only from the supplied #147 protocol file, never hard-coded into Python.
- Every valid sample uses a unique temporary workspace, a new App Server process/private process group, exactly one `thread/start`, no resume/fork, exactly one scenario turn, canonical thread read, and proven cleanup.
- Requested and served model must both be exactly `gpt-5.6-sol`; approval `never`; sandbox `read-only`; no model-visible MCP/plugins/skills/helpers. Ambiguous ambient capability invalidates the run.
- Require an explicit non-default independently authenticated `--codex-home`; never read/copy/hash/serialize credential contents and never perform login/logout/reauthorization.
- Exact prompt and exact final model output are evidence. The model cannot grade itself, mark PASS, merge, dispatch, or modify company state.
- An effect-unknown turn is never automatically retried/resumed. An existing evidence artifact is never overwritten.
- Builder owes one live control + one live amended F0 proof only. Builder must NOT run the 16-sample constitutional corpus.
- Keep the implementation PR DRAFT / HOLD-FOR-SOL and stop for Sol final F0 review.

---

## File Structure

- `scripts/ohf/fresh_sol_eval.py` — all F0 contracts, Git/protocol materialization, fresh-run orchestration, evidence serialization, CLI `run-one` / `run-matrix` / `check-corpus`.
- `tests/test_fresh_sol_eval.py` — pure/fake-client tests and all required mutation/falsifier cases. No provider credentials or live provider calls in CI.
- Existing `scripts/ohf/laboratory.py`, `scripts/ohf/protocol.py`, `scripts/ohf/redaction.py`, `scripts/ohf/p1a_capability_policy.py` — reuse as dependencies; modify only if a concrete missing observation primitive is proven, with a separate focused regression.
- No persistent live evidence file is committed by the F0 builder. The live two-run receipt is sanitized into the PR discussion.

---

### Task 1: Immutable Skillpack + Protocol Materialization

**Files:**
- Create: `scripts/ohf/fresh_sol_eval.py`
- Create: `tests/test_fresh_sol_eval.py`

**Interfaces:**
- Produces `SkillpackArm`, `ProcedureBundle`, `ScenarioPacket`, `FreshSolEvalError`.
- Produces `materialize_skillpack(repo_root: Path, arm: SkillpackArm) -> ProcedureBundle`.
- Produces `parse_protocol(path: Path) -> dict[str, ScenarioPacket]`.
- Produces `build_eval_agents_md(bundle: ProcedureBundle) -> bytes`.
- Later tasks consume these exact names; do not rename without updating plan consumers and tests in the same commit.

- [ ] **Step 1: Add the RED contract tests for immutable arm identity.**

Add tests with these literal expectations:

```python
from scripts.ohf.fresh_sol_eval import MAS136_ARMS, MAS136_SCENARIOS


def test_mas136_arm_identity_is_frozen():
    assert MAS136_ARMS["control-1.0.0"].commit_sha == "51f9942733b86e550bb9169d2a43462bd28e774f"
    assert MAS136_ARMS["control-1.0.0"].skillpack_version == "1.0.0"
    assert MAS136_ARMS["amended-1.1.0"].commit_sha == "8209e1f31da15f8effc23a9899a5c5a02d30cab4"
    assert MAS136_ARMS["amended-1.1.0"].skillpack_version == "1.1.0"
    assert MAS136_SCENARIOS == ("S2", "S6", "S7", "S8")
```

Run:

```bash
python3 -m pytest -q tests/test_fresh_sol_eval.py::test_mas136_arm_identity_is_frozen
```

Expected: FAIL because module/constants do not exist.

- [ ] **Step 2: Implement the immutable arm/value types and closed failure vocabulary.**

Add these public contracts:

```python
RUN_SCHEMA = "mastermind.fresh_sol_eval_run/v1"
MAS136_SCENARIOS = ("S2", "S6", "S7", "S8")

@dataclass(frozen=True)
class SkillpackArm:
    name: str
    commit_sha: str
    skillpack_version: str

MAS136_ARMS = {
    "control-1.0.0": SkillpackArm("control-1.0.0", "51f9942733b86e550bb9169d2a43462bd28e774f", "1.0.0"),
    "amended-1.1.0": SkillpackArm("amended-1.1.0", "8209e1f31da15f8effc23a9899a5c5a02d30cab4", "1.1.0"),
}

FAILURE_CODES = frozenset({
    "SOURCE_COMMIT_UNAVAILABLE",
    "SKILLPACK_IDENTITY_MISMATCH",
    "PROCEDURE_SOURCE_UNAVAILABLE",
    "PROTOCOL_INVALID",
    "AUTH_REALM_INVALID",
    "HARNESS_BINARY_UNAVAILABLE",
    "HARNESS_INITIALIZE_FAILED",
    "CAPABILITY_ATTESTATION_INVALID",
    "SERVED_MODEL_MISMATCH",
    "THREAD_START_FAILED",
    "TURN_EFFECT_UNKNOWN",
    "THREAD_READ_FAILED",
    "EVIDENCE_SECRET_SHAPE_REFUSED",
    "CLEANUP_UNPROVEN",
    "EVIDENCE_COLLISION",
})

class FreshSolEvalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        if code not in FAILURE_CODES:
            raise ValueError("unknown fresh-Sol failure code")
        super().__init__(message)
        self.code = code
```

- [ ] **Step 3: Add RED tests proving source bytes come from immutable Git objects, not the working tree.**

Use a temporary Git repository fixture with two commits whose `docs/sol_skills/INDEX.md` and one sibling skill have different bytes. Dirty the working-tree file after committing. Assert `materialize_skillpack()` returns the committed bytes, records sorted paths + Git blob SHAs, and produces a stable aggregate SHA-256 from exact ordered path/bytes pairs.

Also add failures for:

```text
unknown commit -> SOURCE_COMMIT_UNAVAILABLE
missing INDEX or unreadable skill path -> PROCEDURE_SOURCE_UNAVAILABLE
wrong schema/version/bootstrap -> SKILLPACK_IDENTITY_MISMATCH
```

Run the named tests against the unimplemented functions and preserve RED output in the builder return.

- [ ] **Step 4: Implement Git-object materialization with zero network.**

Use only fixed argv subprocesses, never shell strings:

```python
def _git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    ...
```

Required mechanics:

```text
git cat-file -e <commit>^{commit}
git ls-tree -r --name-only <commit> -- docs/sol_skills
git rev-parse <commit>:<path>
git show <commit>:<path>
```

Filter only `.md`, require `docs/sol_skills/INDEX.md`, sort paths lexicographically, parse INDEX with `yaml.safe_load`, require schema `mastermind.sol_skillpack.v1`, exact expected `skillpack_version`, and `minimum_bootstrap_major <= 1` with a positive integer value. Do not read the checkout copy of any skill.

Define:

```python
@dataclass(frozen=True)
class ProcedureSource:
    path: str
    blob_sha: str
    content: bytes

@dataclass(frozen=True)
class ProcedureBundle:
    arm: SkillpackArm
    sources: tuple[ProcedureSource, ...]
    context_sha256: str
```

Aggregate digest input is deterministic:

```python
hasher.update(path.encode("utf-8"))
hasher.update(b"\0")
hasher.update(blob_sha.encode("ascii"))
hasher.update(b"\0")
hasher.update(content)
hasher.update(b"\0")
```

- [ ] **Step 5: Add RED protocol-parser tests with exact S2/S6/S7/S8 extraction.**

Build a small protocol fixture in the test using the same Markdown shape as #147:

```markdown
## Shared scenario preamble

> PREAMBLE LINE

## S2 — repaired-then-stale organizational state

> S2 BODY

PASS requires: S2 RULE
```

Require exactly one shared preamble and exactly one S2/S6/S7/S8 section. Missing/duplicate sections, duplicate shared preamble, missing `PASS requires`, or malformed headings must raise `PROTOCOL_INVALID`. Assert scenario prompt is the shared block plus scenario quoted block and does not contain `PASS requires` grading text.

- [ ] **Step 6: Implement the protocol parser and neutral procedure wrapper.**

Define:

```python
@dataclass(frozen=True)
class ScenarioPacket:
    scenario_id: str
    prompt: str
    pass_requires: str

EVAL_WRAPPER_VERSION = "mastermind.fresh_sol_eval_wrapper/v1"
```

The wrapper must be arm-neutral. It must NOT name Continuation Delta behavior, scenario outcome, control/amended expectation, or `PASS requires`. It may state only:

```text
This is a read-only evaluation of Sol procedure.
The exact procedure bundle appended below governs this isolated run.
Do not modify external systems.
Answer only the supplied scenario in the user turn.
```

`build_eval_agents_md()` concatenates the fixed wrapper plus each exact skill file with deterministic markers:

```text
----- BEGIN <path> @ <blob_sha> -----
<exact decoded UTF-8 source>
----- END <path> -----
```

Reject non-UTF-8 procedure bytes as `PROCEDURE_SOURCE_UNAVAILABLE`.

- [ ] **Step 7: Run Task 1 tests and commit.**

Run:

```bash
python3 -m pytest -q tests/test_fresh_sol_eval.py -k 'arm_identity or materialize or protocol or agents_md'
python3 -m compileall -q scripts/ohf/fresh_sol_eval.py
git diff --check
```

Expected: all selected tests PASS.

Commit only Task 1 files:

```bash
git add scripts/ohf/fresh_sol_eval.py tests/test_fresh_sol_eval.py
git commit -m "feat(ohf): materialize immutable fresh-Sol inputs"
```

---

### Task 2: Fresh Process/Thread Execution + Capability Attestation

**Files:**
- Modify: `scripts/ohf/fresh_sol_eval.py`
- Modify: `tests/test_fresh_sol_eval.py`
- Optional only if proven necessary: a narrow helper in `scripts/ohf/laboratory.py` plus its existing test module

**Interfaces:**
- Consumes `ProcedureBundle` / `ScenarioPacket` from Task 1.
- Produces `CapabilityReceipt`, `CleanupReceipt`, `RunObservation`.
- Produces `run_one(...) -> RunObservation`.

- [ ] **Step 1: Add an injectable App Server client protocol and RED fresh-session tests.**

Inside `fresh_sol_eval.py` define a narrow structural Protocol (or dataclass-compatible fake seam) covering only methods already exposed by `AppServerClient`:

```python
class EvalClient(Protocol):
    pid: int | None
    cwd: Path
    notifications: list[dict[str, object]]
    def start(self) -> None: ...
    def request(self, method: str, params: dict[str, object] | None = None, timeout: float = ...) -> dict[str, object]: ...
    def notify(self, method: str, params: dict[str, object]) -> None: ...
    def wait_notification(self, method: str, *, timeout: float) -> dict[str, object]: ...
    def terminate(self) -> object: ...
```

The test fake must record every RPC method and synthesize deterministic process/thread IDs. Add RED tests asserting two calls to `run_one()` yield distinct run IDs, client PIDs, workspace paths, and native thread IDs; each client sees exactly one `thread/start`, zero `thread/resume`, zero `thread/fork`, and one `turn/start`.

- [ ] **Step 2: Add RED capability-attestation tests.**

Fake these pre-thread observations:

```text
initialize -> userAgent
account/read -> chatgpt / pro / requires_openai_auth=true
config/read -> model=gpt-5.6-sol, approval_policy=never, sandbox_mode=read-only, no configured MCP/plugins
skills/list -> empty model-visible skill set
MCP status/list surface -> empty observed MCP set where the installed protocol exposes it
```

Tests must reject before `thread/start` when any of the following is injected:

```text
served model != gpt-5.6-sol -> SERVED_MODEL_MISMATCH
approval != never -> CAPABILITY_ATTESTATION_INVALID
sandbox != read-only -> CAPABILITY_ATTESTATION_INVALID
one MCP configured/observed -> CAPABILITY_ATTESTATION_INVALID
one plugin configured -> CAPABILITY_ATTESTATION_INVALID
one skill/native helper/unclassified capability visible -> CAPABILITY_ATTESTATION_INVALID
capability observation unavailable/ambiguous -> CAPABILITY_ATTESTATION_INVALID
```

Reuse `scripts.ohf.protocol` parsers and `scripts.ohf.p1a_capability_policy.classify_observed/launch_decision`; do not implement a second classification system.

- [ ] **Step 3: Implement isolated workspace/config preparation.**

Every `run_one` invocation creates a unique temporary root containing only:

```text
workspace/AGENTS.md
workspace/.git/   # do NOT create; workspace is intentionally not a repo
home/
config/config.toml
```

Write the minimal config using current repository-supported keys:

```toml
model = "gpt-5.6-sol"
approval_policy = "never"
sandbox_mode = "read-only"

[features]
apps = false

[skills.bundled]
enabled = false
```

Do not configure MCP. Do not install `.agents/skills`. Keep provider transport available only as required by Codex itself; model shell/tool network remains unavailable by the read-only + approval-never contract.

Do not mutate the dedicated `--codex-home` config permanently. Use App Server `--strict-config` / `-c` overrides if current existing OHF paths already support exact ephemeral overrides; otherwise construct a temporary config layer through an existing laboratory primitive. If the only path would overwrite the authenticated realm's persistent config, STOP and return to Sol rather than broadening credential/config custody.

- [ ] **Step 4: Implement dedicated auth-realm validation without credential reads.**

Reuse `scripts.ohf.laboratory.validate_live_codex_home` where possible. Add an explicit assertion in the test that no code calls `Path.read_bytes/read_text/open` on `<codex-home>/auth.json`.

The evidence-safe auth observation comes only from `account/read`. The runner may record:

```text
auth_type
plan_type
requires_openai_auth
codex_home_is_default = false
```

It must not record credential file content, digest, size-derived token properties, email, access token, refresh token, id token, cookie, or workspace credential bytes.

- [ ] **Step 5: Implement process/thread/turn lifecycle.**

Use `AppServerClient(..., start_new_session=True)` so every process owns a private process group. The load-bearing sequence is exactly:

```text
client.start()
initialize
initialized notification
account/config/capability observations
thread/start(model=gpt-5.6-sol, cwd=workspace, approvalPolicy=never, sandbox=read-only)
turn/start(threadId=<new>, input=[scenario prompt], cwd=workspace, approvalPolicy=never)
wait turn/completed
thread/read(includeTurns=true) or existing canonical list/read fallback that proves the same exact thread
extract final assistant output from canonical thread state
client.terminate()
prove process group empty
```

There is no call to `thread/resume` or `thread/fork`. If `turn/start` times out/disconnects after dispatch, raise `TURN_EFFECT_UNKNOWN`, terminate/contain the process, and never retry that run ID/thread.

If canonical thread read cannot produce one unambiguous final assistant text, raise `THREAD_READ_FAILED`; do not concatenate notification fragments into a synthetic answer.

- [ ] **Step 6: Implement typed observations.**

Use these shapes:

```python
@dataclass(frozen=True)
class CapabilityReceipt:
    requested_model: str
    served_model: str
    approval_policy: str
    sandbox_mode: str
    mcp_names: tuple[str, ...]
    plugin_names: tuple[str, ...]
    skill_names: tuple[str, ...]
    auth_type: str
    plan_type: str
    requires_openai_auth: bool | None
    harness_version: str

@dataclass(frozen=True)
class CleanupReceipt:
    controller_returncode: int | None
    private_group_id: int | None
    private_group_empty: bool
    termination_outcome: str

@dataclass(frozen=True)
class RunObservation:
    run_id: str
    arm: str
    scenario_id: str
    workspace: Path
    process_pid: int
    process_pgid: int
    process_start_identity: str
    native_thread_id: str
    prompt: str
    output: str
    started_at: str
    completed_at: str
    capability: CapabilityReceipt
    cleanup: CleanupReceipt
```

Do not put secrets or authority verdicts in these types.

- [ ] **Step 7: Run Task 2 tests and commit.**

Run:

```bash
python3 -m pytest -q tests/test_fresh_sol_eval.py -k 'fresh or capability or model or thread or cleanup or auth'
python3 -m compileall -q scripts/ohf/fresh_sol_eval.py
git diff --check
```

Commit:

```bash
git add scripts/ohf/fresh_sol_eval.py tests/test_fresh_sol_eval.py
git commit -m "feat(ohf): run isolated fresh-Sol App Server samples"
```

---

### Task 3: Create-Only Evidence + CLI + MAS-136 Matrix

**Files:**
- Modify: `scripts/ohf/fresh_sol_eval.py`
- Modify: `tests/test_fresh_sol_eval.py`

**Interfaces:**
- Consumes Task 1/2 contracts.
- Produces `write_run_artifact`, `run_matrix`, `check_corpus`, `main` CLI.

- [ ] **Step 1: Add RED evidence schema and exact-output tests.**

Require a Markdown artifact containing a YAML front matter or deterministic metadata block with every field from the spec, followed by fenced sections:

```markdown
## Exact prompt

```text
<verbatim prompt>
```

## Exact model output

```text
<verbatim output>
```
```

Required metadata includes:

```text
schema
scenario_id
arm
run_id
procedure_commit_sha
expected_skillpack_version
procedure_source_blobs
procedure_context_sha256
protocol_sha256
prompt_sha256
model_requested
model_served
harness_kind
harness_version
harness_binary_sha256
provider_auth_type
provider_plan_type
requires_openai_auth
process_pid
process_pgid
process_start_identity
native_thread_id
started_at
completed_at
cleanup_proof
manual_classification: PENDING_SOL_REVIEW
```

Assert exact prompt/output bytes round-trip unchanged except Markdown fencing; do not redact normal model text after it has passed the secret-shape gate.

- [ ] **Step 2: Add RED create-only, secret-shape, and collision tests.**

Reuse `scripts.ohf.redaction.evidence_contains_secret`. Tests:

```text
existing target path -> EVIDENCE_COLLISION and original bytes unchanged
prompt contains secret-shape -> EVIDENCE_SECRET_SHAPE_REFUSED and no artifact
output contains secret-shape -> EVIDENCE_SECRET_SHAPE_REFUSED and no artifact
normal output -> artifact created exactly once
```

No secret-shaped fixture value should be a real credential; use synthetic detector-triggering strings already used by existing OHF redaction tests.

- [ ] **Step 3: Implement deterministic evidence paths and atomic corpus manifest.**

Artifact path:

```python
root / "runs" / arm / scenario_id / f"{run_id}.md"
```

Use exclusive create (`open("x", encoding="utf-8", newline="\n")`) after parent creation. Do not overwrite.

Maintain `MANIFEST.json` as evidence bookkeeping only. It is an atomically replaced canonical list of artifacts with:

```text
schema = mastermind.fresh_sol_eval_manifest/v1
entries = sorted [{run_id, arm, scenario_id, relative_path, artifact_sha256}]
```

No status machine, retry count, owner, lease, queue, timestamps-as-scheduling, or lifecycle fields.

- [ ] **Step 4: Add RED matrix cardinality and resume-manifest tests.**

`run_matrix` for `mode="mas-136"` must create this logical sample plan in this exact deterministic order:

```python
[("control-1.0.0", "S2", 1),
 ("amended-1.1.0", "S2", 1),
 ("amended-1.1.0", "S2", 2),
 ("amended-1.1.0", "S2", 3),
 ... same for S6, S7, S8 ...]
```

There must be 4 control + 12 amended planned samples = 16.

A run ID is freshly generated immediately before each sample. Failure/invalidity stops the matrix. The only skip path is `--resume-manifest <path>` and only for entries whose artifact exists and SHA-256 still equals the manifest; mismatched/missing bytes refuse as `EVIDENCE_COLLISION` rather than silently rerunning.

- [ ] **Step 5: Implement CLI.**

Required commands:

```bash
python3 scripts/ohf/fresh_sol_eval.py run-one \
  --repo-root <local Mastermind clone> \
  --protocol-path <PR147 PRESSURE_TEST_PROTOCOL.md> \
  --codex-home <dedicated non-default realm> \
  --evidence-root <directory> \
  --arm control-1.0.0 \
  --scenario S8

python3 scripts/ohf/fresh_sol_eval.py run-matrix \
  --repo-root <local Mastermind clone> \
  --protocol-path <PR147 PRESSURE_TEST_PROTOCOL.md> \
  --codex-home <dedicated non-default realm> \
  --evidence-root <directory> \
  --mode mas-136

python3 scripts/ohf/fresh_sol_eval.py check-corpus \
  --evidence-root <directory> \
  --mode mas-136
```

`check-corpus` verifies only identity/cardinality/digest/cleanup completeness; it does not behavioral-grade outputs. It returns nonzero if fewer/more than 16 valid MAS-136 samples are present or any artifact/manifest digest is inconsistent.

Do not add a network fetch, GitHub API, Slack API, Linear API, Executive API, or merge command to the CLI.

- [ ] **Step 6: Run Task 3 tests and commit.**

Run:

```bash
python3 -m pytest -q tests/test_fresh_sol_eval.py -k 'evidence or secret or collision or matrix or corpus or cli'
python3 -m compileall -q scripts/ohf/fresh_sol_eval.py
git diff --check
```

Commit:

```bash
git add scripts/ohf/fresh_sol_eval.py tests/test_fresh_sol_eval.py
git commit -m "feat(ohf): emit bounded fresh-Sol evidence corpus"
```

---

### Task 4: Complete the 16 Required Falsifiers and Repository Regression Gate

**Files:**
- Modify: `tests/test_fresh_sol_eval.py`
- Modify `scripts/ohf/fresh_sol_eval.py` only for the smallest fixes exposed by RED tests

**Interfaces:**
- No new production interface unless a falsifier exposes a real missing contract.

- [ ] **Step 1: Add a named test for every spec mutation.**

The final test file must contain distinct tests whose names make the killed mutant obvious:

```text
test_second_sample_never_reuses_native_thread
test_resume_and_fork_are_never_called
test_skillpack_comes_from_exact_git_commit_not_dirty_worktree
test_wrapper_is_byte_identical_between_arms_except_skill_sources
test_missing_or_wrong_commit_skill_file_refuses
test_protocol_has_no_hardcoded_scenario_fallback
test_served_model_mismatch_refuses_before_thread_start
test_ambient_mcp_plugin_skill_or_unclassified_capability_refuses
test_default_codex_home_refuses
test_auth_json_contents_are_never_read_copied_or_serialized
test_notification_fragments_cannot_replace_canonical_thread_read
test_existing_run_artifact_is_never_overwritten
test_effect_unknown_turn_is_never_retried_or_resumed
test_unproven_process_group_cleanup_invalidates_run
test_secret_shaped_output_is_not_persisted
test_mas136_matrix_is_exactly_four_control_twelve_amended
```

These are not aliases for one generic parametrized smoke test. Parametrization is fine within a named failure family, but each of the sixteen laws must have an independently readable failure point.

- [ ] **Step 2: Prove each test discriminates the law.**

For each of the sixteen, either:

1. preserve a RED receipt from before the implementation/fix that the test required, or
2. locally introduce a one-line test-only monkeypatch/mutant that violates the named law and record that the test fails, then remove the mutant.

The return packet must summarize the 16/16 discrimination evidence. Do not commit mutants.

- [ ] **Step 3: Run the full focused OHF regression set.**

Run at minimum:

```bash
python3 -m pytest -q \
  tests/test_fresh_sol_eval.py \
  tests/test_ohf_protocol_fidelity.py \
  tests/test_ohf_auth_isolation.py \
  tests/test_ohf_probe_inertness.py \
  tests/test_ohf_p1a_operator_harness_contract.py \
  tests/test_codex_operator_adapter.py
```

If an exact filename above has moved on current protected master, locate the current equivalent test rather than deleting the gate. Do not edit CI exclusion policy.

- [ ] **Step 4: Run repository-level static/full gates.**

Run:

```bash
python3 -m compileall -q scripts/ohf
python3 scripts/ci_pytest.py --plan-only
python3 scripts/ci_pytest.py
git diff --check
```

`ci_pytest.py` must report zero new exclusions. If a fresh worktree has a known vendored-Macro setup prerequisite, follow the repository's current documented CI-equivalent setup; do not weaken tests or add exclusions.

- [ ] **Step 5: Commit only bounded repair/tests from this task.**

```bash
git add scripts/ohf/fresh_sol_eval.py tests/test_fresh_sol_eval.py
git commit -m "test(ohf): falsify fresh-Sol isolation and evidence escapes"
```

If no code change is needed and the tests were already added in prior task commits, do not manufacture an empty commit; record Task 4 as verification-only in the return packet.

---

### Task 5: Draft PR, Hosted Proof, and One Control + One Amended Live F0 Canary

**Files:**
- No required implementation file change.
- PR discussion receives sanitized proof receipts; raw live evidence remains ephemeral and must not be committed to #147.

**Interfaces:**
- Consumes final F0 CLI.
- Produces exact-head CI/CodeQL + live F0 acceptance receipts for Sol.

- [ ] **Step 1: Re-pin and reconcile before push/PR.**

Record:

```bash
git rev-parse HEAD
git fetch origin master
git rev-parse origin/master
git diff --name-only <protected-pickup>...HEAD
```

Confirm the branch still changes only:

```text
docs/superpowers/specs/2026-08-26-fresh-sol-evaluation-harness-f0-design.md
docs/superpowers/plans/2026-08-26-fresh-sol-evaluation-harness-f0.md
scripts/ohf/fresh_sol_eval.py
tests/test_fresh_sol_eval.py
```

plus at most one narrowly justified existing `scripts/ohf/**` helper/test pair if Task 2 proved it necessary. Any `control_plane/**`, `docs/sol_skills/**`, #147, Agent OS, workflow, dependency, config, or production path is a STOP/return-to-Sol condition.

- [ ] **Step 2: Push the existing carrier and keep/create one draft PR.**

Use branch `sol/mas-136-fresh-sol-eval-f0-20260826`. Do not create a second implementation branch. PR title:

```text
HOLD-FOR-SOL: OHF fresh-Sol evaluation harness F0 for MAS-136
```

PR body must state `BUILT_NOT_PROVEN` until the live two-run proof passes and must repeat that the 16-run constitutional corpus is not builder scope.

- [ ] **Step 3: Wait for exact-head hosted CI and CodeQL and classify honestly.**

Required final head checks:

```text
CI/test = success
CodeQL aggregate = success
Analyze(actions) = success
Analyze(javascript-typescript) = success
Analyze(python) = success
```

If branch concurrency cancels an intermediate run, only the final exact-head run counts. Do not claim a cancelled run green.

- [ ] **Step 4: Run the live two-sample F0 proof using a dedicated non-default ChatGPT Pro Codex realm.**

Use **S8** because it is harmless/read-only and tests the over-hardening boundary without needing live organizational mutation.

Create a temporary checkout of #147's protocol carrier at the exact evidence-protocol commit containing the bounded matrix (currently `92a17f057c25575197debc79faa78261962b622d`, unless Sol has recorded a newer evidence-only protocol commit without procedure-byte movement). Do not run from an unpinned working-tree protocol.

Run exactly:

```bash
rm -rf /tmp/mmx-fresh-sol-f0-live
mkdir -p /tmp/mmx-fresh-sol-f0-live/control /tmp/mmx-fresh-sol-f0-live/amended

python3 scripts/ohf/fresh_sol_eval.py run-one \
  --repo-root "$PWD" \
  --protocol-path <PINNED_147_CHECKOUT>/review_evidence/continuation_delta/PRESSURE_TEST_PROTOCOL.md \
  --codex-home <DEDICATED_NONDEFAULT_PRO_REALM> \
  --evidence-root /tmp/mmx-fresh-sol-f0-live/control \
  --arm control-1.0.0 \
  --scenario S8

python3 scripts/ohf/fresh_sol_eval.py run-one \
  --repo-root "$PWD" \
  --protocol-path <PINNED_147_CHECKOUT>/review_evidence/continuation_delta/PRESSURE_TEST_PROTOCOL.md \
  --codex-home <DEDICATED_NONDEFAULT_PRO_REALM> \
  --evidence-root /tmp/mmx-fresh-sol-f0-live/amended \
  --arm amended-1.1.0 \
  --scenario S8
```

The `<...>` values above are operator-supplied host paths, not code placeholders: the builder must resolve them from the actual dedicated realm and exact pinned #147 worktree at execution time and report the resolved **non-secret** paths/commit identities without exposing credential contents.

- [ ] **Step 5: Prove live F0 acceptance from the two artifacts.**

Both runs must show:

```text
distinct run IDs
distinct App Server PIDs/process-start identities
distinct native thread IDs
requested model = served model = gpt-5.6-sol
control procedure = 51f9942733... / 1.0.0
amended procedure = 8209e1f31d... / 1.1.0
capability gate valid with empty MCP/plugins/skills/helpers
exact prompt captured
exact output captured
private process group cleanup proven
default ~/.codex realm not used or modified
manual_classification = PENDING_SOL_REVIEW
```

Do not grade whether the answers are behaviorally correct for #147. This task proves F0 isolation/evidence mechanics only.

- [ ] **Step 6: Scan the ephemeral live evidence for secret shapes and publish only a sanitized receipt.**

Do not paste exact model outputs into Slack/Linear unless Sol asks; raw ephemeral output may contain user/model text not needed for F0 mechanics review. PR comment should include only identities/digests/cleanup/capability facts and SHA-256 of each raw artifact.

- [ ] **Step 7: Return to Sol and STOP.**

Return exactly:

```text
final immutable head SHA
changed-file list
commit sequence
16/16 falsifier discrimination summary
targeted test count/result
full repository CI-equivalent result
hosted CI + CodeQL exact-head receipts
live control run safe receipt
live amended run safe receipt
whether installed Codex exposed any ambient capability that blocked F0
confirmation protected paths and external systems were untouched
exact next action = SOL FINAL F0 REVIEW
```

Do not merge F0. Do not run the 16 MAS-136 samples. Do not modify #147. Do not propagate the kernel. Do not start R3C.
