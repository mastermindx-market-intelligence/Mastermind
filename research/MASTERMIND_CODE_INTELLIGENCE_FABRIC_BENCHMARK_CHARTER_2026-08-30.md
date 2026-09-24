# Mastermind Code Intelligence Fabric — Historical Benchmark Charter

**Status:** `SPEC_ONLY / RECORDS_ONLY`  
**Parent architecture:** `research/MASTERMIND_CODE_INTELLIGENCE_FABRIC_F0_ARCHITECTURE_2026-08-30.md`  
**Benchmark operation:** `mastermind-codeintel-fabric-f0-benchmark-20260830-sol-001`  
**Frozen source window:** protected `Mastermind@8f0babf473e6e4e8efce697014bd48c594227d94`, `macro@ca31568272d06f2472f65946d2435517611f31dc`

This charter defines the benchmark corpus, answer-key contract, run conditions, scoring and promotion law. It does not claim that any candidate CodeIntel component exists or that any case has already been run.

## 1. Benchmark job

Measure whether the Fabric changes the quality and economics of real Mastermind architecture recovery, bounded implementation, debugging and adversarial review.

A candidate fails when it only returns results faster while increasing wrong-owner conclusions, stale-current claims, missed consumers, false confidence or context burden.

## 2. Immutable case contract

Each case is materialized as one versioned JSON document under a future C0/Z0 test-fixture directory. Every document must contain:

```json
{
  "schema": "mastermind.codeintel_benchmark_case.v1",
  "case_id": "E1",
  "category": "executive_os",
  "historical_prompt": "verbatim bounded prompt",
  "as_of": "RFC3339 UTC",
  "repositories": [
    {"name": "Mastermind", "ref": "exact commit SHA"}
  ],
  "canonical_owner": ["exact owner names"],
  "critical_files": ["exact paths"],
  "critical_symbols": ["exact qualified names"],
  "important_consumers": ["exact files/symbols"],
  "tests_and_source_law": ["exact paths"],
  "pr_or_commit_evidence": ["exact PR/commit IDs"],
  "known_ambiguities": ["bounded ambiguity statements"],
  "must_not_conclude": ["known wrong-owner/stale conclusions"],
  "answer_key_sha256": "digest of canonical answer-key projection"
}
```

The historical prompt is not rewritten after observing a candidate's performance. Answer keys are prepared from canonical Git/GitHub evidence before candidate runs. A later correction creates a new case revision and preserves the earlier result.

## 3. Initial 24-case manifest

The listed PRs/episodes are corpus seeds, not proof that a PR title alone is the answer key. C0/Z0 must reconstruct exact accepted/merged state and freeze the correct historical commit window before running a model.

### Executive OS and authority — E1–E3

**E1 — Execution capability ownership and attestation**  
Seed: current `ExecutionCapabilityRegistry`, capability config and Operator Adapter at the frozen protected pin.  
Question: Where is exact MCP/tool authority granted and attested, and what must change to add a new read capability without ambient plugin authority?  
Critical distinction: registry policy, App Server observation and Executive lifecycle are separate owners.

**E2 — H0 source transport versus native proof**  
Seed: Mastermind PR #213 and its H0 source-closure lineage.  
Question: Which implementation owns the authenticated source transport, which exact evidence is source-only, and what remains required before native acceptance?  
Critical distinction: merged source transport is not installed-host or CF2-P0 proof.

**E3 — Operator continuation identity and effect boundaries**  
Seed: Mastermind PR #193 continuation-contract episode and current protected consumers.  
Question: Which pure contract identifies a continuation, which runtime owner would persist/deliver it, and what fields are forbidden from caller/model authority?  
Critical distinction: content-addressed contract is not RuntimeBinding, provider execution or lifecycle.

### Operator Harness, continuity and workspace binding — O1–O3

**O1 — Exact Codex workspace identity**  
Seed: current `control_plane/codex_operator_adapter.py` and contract tests.  
Question: How is workspace root, Git HEAD, device/inode and App Server CWD sealed, and which change requires a new Attempt?  
Critical distinction: CodeIntel must attach under the Attempt rather than select a worktree.

**O2 — Claude worker preflight refusal boundary**  
Seed: Mastermind PR #184.  
Question: Which preflight facts are observable without provider work, why does the current estate refuse readiness, and which downstream owner is still missing?  
Critical distinction: binary/auth observation is not provider realm readiness, capacity identity or routing.

**O3 — Tracked symlink materialization regression**  
Seed: Mastermind PR #200.  
Question: Why did a disposable checkout always fail the no-symlink gate, where was the narrow repair made, and which security checks remained unchanged?  
Critical distinction: checkout materialization changed; Git mode/blob truth and privileged host behavior did not.

### Capacity, model routing and worker economics — C1–C3

**C1 — Provider capacity canonical owner**  
Seed: Macro PR #6297 / `WS:EXECUTIVE-CAPACITY-FABRIC`.  
Question: Which repo owns provider availability/quota/cooling evidence, what projection crosses into Mastermind, and where may Executive use it?  
Critical distinction: Capacity ranks already-eligible workers; it does not redefine model suitability or create lifecycle.

**C2 — Manual worker avenue placement law**  
Seed: Mastermind PR #215.  
Question: What does Sol select, who owns routine concrete placement, and when does live delivery become receiver assignment?  
Critical distinction: `WAITING_CAPACITY` is not a precommission and Chairman is not the default quota allocator.

**C3 — Chat-native Meta-CEO cognition economics**  
Seed: Mastermind PR #263.  
Question: Which Sol cognition route is default, what constitutes a metered exception, and what worker routing remains unchanged?  
Critical distinction: cognition surface, worker/model, execution surface and authority are separate.

### Worker Presence, dialogue and Wake — W1–W3

**W1 — Pure turn-attention classifier**  
Seed: Mastermind PR #209.  
Question: Where is a dialogue leaf classified, what inputs determine target attention, and which side effects are explicitly absent?  
Critical distinction: deterministic attention fact is not Wake delivery, polling or lifecycle.

**W2 — Bounded company-dialogue MCP**  
Seed: Mastermind PR #210.  
Question: Which six tools exist, how are actor/context/thread bindings injected, and how does effect-unknown remain reconcilable without resend?  
Critical distinction: dialogue transport cannot create Job/Attempt/Worker state or choose Slack identity.

**W3 — Agent Relay runtime and enrollment split**  
Seed: Mastermind PRs #231 and #238.  
Question: Which code owns long-running AF_UNIX relay behavior, which code owns root-only enrollment, and what remains production-disarmed?  
Critical distinction: credential enrollment, service runtime, canonical parent creation, Wake and Executive execution are separate facts.

### Control Room, project surfaces and frontend — U1–U3

**U1 — Control Room immutable release-root repair**  
Seed: Mastermind PR #198 and source PR #196.  
Question: Why did the installed `current` symlink prevent service startup, what identity is now attested, and what production proof is still owed?  
Critical distinction: source repair is not installed AF_UNIX/browser proof.

**U2 — Linear projector credential host boundary**  
Seed: Mastermind PR #218.  
Question: Where is the fixed root-owned credential boundary, which values remain secret, and which later action owns actual app/OAuth/Linear mutation?  
Critical distinction: host enrollment capability is not a Linear app or projector runtime.

**U3 — Project Workroom federated architecture**  
Seed: Mastermind PR #273.  
Question: Which existing systems own organizational, runtime, implementation, portfolio and transport truth, and what would a Workroom add without becoming another control plane?  
Critical distinction: merged Workroom source law creates no live app, Canvas, Radar or worker.

### Cross-repository Mastermind/Macro — X1–X3

**X1 — Capacity projection consumption boundary**  
Seed: Macro PR #6297 plus Mastermind capacity claim/source-law consumers.  
Question: Trace the real producer, versioned projection, acquisition seam, claim-time consumer and tests across both repositories.  
Critical distinction: no floating import of Macro internals and no duplicate capacity ledger.

**X2 — H0 Macro source archive and Mastermind installer contract**  
Seed: Mastermind PR #213 and referenced Macro source SHA/archive evidence.  
Question: Which repository bytes are authenticated, how are carrier and immutable repair provenance separated, and which host ceremony consumes them?  
Critical distinction: whole-repo provenance is not semantic capacity state and source bundle proof is not native install proof.

**X3 — Agent OS organizational record versus Mastermind implementation**  
Seed: `WS:EXECUTIVE-CAPACITY-FABRIC`, `WS:CHAIRMAN-CONTROL-ROOM` and their referenced Mastermind PRs.  
Question: Recover current organizational wave, current implementation evidence, held dependencies and exact next action without treating either repo as the other's truth store.  
Critical distinction: Agent OS workstream truth and GitHub implementation truth must be composed, not collapsed.

### Regression and root-cause investigation — R1–R3

**R1 — Watcher token-burn and stale-carrier defects**  
Seed: Mastermind PR #205.  
Question: Identify the two distinct incidents, their common source law, cadence/freshness repairs and runtime enforcement gap.  
Critical distinction: watcher cadence and read-before-write freshness are different defects.

**R2 — Control Room mutable alias race**  
Seed: Mastermind PR #198.  
Question: Find the caller/consumer mismatch between installer, systemd unit and low-level verifier, then prove the minimal repair did not relax symlink checks.  
Critical distinction: resolve the alias once to immutable release identity; do not bless a mutable alias as authority.

**R3 — Direct entrypoint import failure masked by the development environment**  
Seed: Mastermind PR #152.  
Question: Why did the documented `python3 scripts/verify_slack_agent_dialogue_metadata.py ...` command fail from a clean checkout while ordinary tests could pass, which wrapper/import boundary was wrong, and what hermetic subprocess test proved the repair?  
Critical distinction: editable installs or `PYTHONPATH` can mask the real operator journey; the wrapper may bootstrap the repository root without changing the credential-safe verifier contract.

### Adversarial impact review — A1–A3

**A1 — MCP tool-surface widening review**  
Seed: Mastermind PR #210 and current capability-registry tests.  
Question: Starting from changed MCP schemas, find every path that could widen caller authority, configuration, tool registration or downstream message type.  
Success: identify exact fences and either catch or rule out an unapproved tool/field/side effect.

**A2 — Sol action-authority collision review**  
Seed: Mastermind PR #214.  
Question: Starting from organizational continuity amendments, find all current consumers of responsibility, SessionTargetRegistry, RuntimeBinding and dialogue applicability that could accidentally elect two Sols.  
Success: distinguish observer multiplicity from one action-authoritative target per unresolved child turn.

**A3 — Exact workspace identity impact review**  
Seed: current protected `control_plane/codex_operator_adapter.py`, `control_plane/operator_harness_contract.py`, and their tests.  
Question: Starting from a proposal to attach a local semantic child, trace every current owner and consumer of workspace root, Git HEAD/base SHA, device/inode, thread CWD, capability manifest and Attempt replacement. Which exact checks prevent one worker from reading another worktree, and which missing test must C0 add?  
Success: identify the existing Attempt/workspace authority boundary, prove CodeIntel must attach beneath it, and derive the hostile two-worktree falsifier without attributing lifecycle or workspace-selection authority to CodeIntel.

## 4. Run conditions

Every case is run under these conditions:

```text
B0  current baseline tools and ordinary repository reads
D1  codeDiscovery only
S1  codeSemantics only, when an exact worktree exists
F1  full Fabric plus local Git/GitHub canonical verification
```

Backend ablation for semantic cases:

```text
S-SERENA  pinned hardened Serena behind the Mastermind facade
S-LSP     direct LSP backend behind the same facade
```

The same model tier, prompt, time budget and source window are used within a comparison block. Runs are randomized and blind to the answer key. Any human intervention is recorded.

## 5. Evidence captured per run

```json
{
  "schema": "mastermind.codeintel_benchmark_run.v1",
  "case_id": "E1",
  "condition": "F1",
  "model": "exact model identifier",
  "started_at": "RFC3339 UTC",
  "source_manifest_sha256": "digest",
  "tool_transcript_ref": "content-addressed artifact reference",
  "first_authoritative_file_ms": 0,
  "tool_calls": 0,
  "whole_file_reads": 0,
  "input_tokens": 0,
  "output_tokens": 0,
  "latency_ms": 0,
  "peak_rss_bytes": 0,
  "answer_key_scores": {},
  "typed_failures": [],
  "final_answer_sha256": "digest"
}
```

Tool transcripts and model answers are evidence artifacts, not a new organizational memory or lifecycle store. Storage location and retention are decided in C0 before any real run.

## 6. Scoring

### Retrieval and semantic correctness

- critical owner recall;
- critical file recall at K=5 and K=10;
- critical symbol recall;
- reference/implementation/consumer recall;
- false-positive burden;
- explicit freshness/coverage correctness;
- canonical-verification completion.

### Reasoning outcome

- wrong-owner conclusion count;
- stale-current/fabricated-current count;
- missed cross-repo consumer count;
- architecture-boundary violations;
- review defects caught;
- suspected defects safely ruled out with evidence;
- primary task completion quality scored by a blinded independent reviewer.

### Economics

- tool calls and wall time to first authoritative file;
- context/tokens consumed;
- whole-file reads;
- model tier required for non-inferior quality;
- index CPU/RAM/disk and refresh cost;
- semantic startup/steady-state CPU/RAM.

## 7. Promotion law

No aggregate score can hide a hard safety failure. Any of the following blocks promotion:

- cross-worktree read;
- model-selectable project/path/Attempt/Worker/endpoint;
- unauthorized tool or schema drift;
- candidate-tree write;
- wrong protected/current claim caused by stale index evidence;
- fabricated `not_found` under unknown/degraded coverage;
- discovery result treated as canonical without exact verification;
- duplicate lifecycle, identity, workspace, memory, queue, retry or control plane.

Subject to those hard gates, CI5 proposes promotion only when:

- median authoritative-answer tool calls or context fall at least 30%;
- critical owner/file recall is at least 95%;
- cross-repo consumer recall improves at least 20 percentage points on X/A cases;
- wrong-owner and stale/fabricated-current conclusions do not increase;
- at least one real review impact missed by baseline is caught or safely ruled out;
- a lower-tier worker is non-inferior to the current higher-tier baseline on at least 12 of 24 cases;
- C0/Z0 resource ceilings are met.

## 8. Exact next action

C0 and Z0 each materialize only the cases needed for their falsifier subset first. CI5 completes all 24 answer keys only after the backend, tool contracts and source-manifest formats are stable. No case result may be backfilled from model memory or PR prose without exact Git/GitHub verification.