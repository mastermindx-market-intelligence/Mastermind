# Mastermind Code Intelligence Fabric — F0 Architecture Freeze

**Status:** `SPEC_ONLY / RECORDS_ONLY`  
**Program CEO:** Sol  
**Chairman operation:** `mastermind-codeintel-fabric-20260830-sol-pro-001`  
**Architecture child:** `mastermind-codeintel-fabric-f0-architecture-20260830-sol-001`  
**Frozen against:** protected `Mastermind@8f0babf473e6e4e8efce697014bd48c594227d94` and `macro@ca31568272d06f2472f65946d2435517611f31dc`  
**Skillpack:** `mastermind.sol_skillpack.v1` version `1.0.1`, bootstrap major `1`, atomically loaded from the protected Mastermind pin above

This document freezes product intent, authority boundaries, external component roles, stable model-facing contracts, empirical promotion gates and no-rebuild law. It creates no MCP server, index, process, worker profile, credential, host installation, runtime capability, Agent OS lifecycle, Executive Job, Attempt, Worker, queue, watcher, memory or production deployment.

## 1. Outcome and completion ruler

Mastermind's autonomous Sols, CTOs, Codex/Claude workers and reviewers need to understand a large, rapidly changing multi-repository system without repeatedly spending frontier cognition on implementation archaeology.

The 10/10 journey is:

```text
intent/question
-> fast company-wide discovery
-> precise semantics over the exact current worker worktree
-> exact canonical verification
-> materially better architecture, implementation, debugging and review
```

The Fabric must answer, with explicit freshness and provenance:

- where behavior lives now;
- which implementation is current;
- which symbols call, implement or depend on it;
- which repositories and tests are involved;
- what could break if an interface changes;
- whether a canonical owner already implements the job;
- what changed recently;
- which exact source revision the answer describes;
- whether the current worktree has candidate bytes absent from protected GitHub;
- which current branch, PR or program surface may collide.

Completion is not Serena starting, Zoekt indexing a repository, an MCP returning results, a profile existing or CI turning green. Completion requires real Mastermind tasks to become faster **and** more correct, exact worktree isolation to hold under hostile concurrency, canonical verification to remain separate, and operating ownership to survive a fresh session.

## 2. Current capability ledger

| Capability | F0 classification | Ruling |
|---|---:|---|
| Code Intelligence Fabric overall | `NOT_BUILT` | No canonical implementation or current carrier was found. |
| Durable CodeIntel architecture before this carrier | `NOT_BUILT` | The Chairman handoff is assignment and evidence, not repository source law. |
| Existing `ExecutionCapabilityRegistry` / capability attestation | `BUILT_NOT_PROVEN` / `PRODUCTION_INERT` | Extend it; never create a second capability registry. |
| Existing exact-workspace Codex Operator Adapter seam | `PARTIAL` / `BUILT_NOT_PROVEN` | It already seals `workspace_root`, Git HEAD, device/inode and App Server CWD. CodeIntel attaches below it. |
| Global discovery facade | `NOT_BUILT` | Z0 must falsify quality, freshness and resource assumptions. |
| Exact-worktree semantic facade | `NOT_BUILT` | C0 must choose the backend empirically. |
| Direct upstream Serena as model-facing production MCP | `REJECTED_BY_DESIGN` | Surface drift, project-controlled configuration and unnecessary authority make a direct grant unsafe. |
| Serena as an internal pinned backend behind a Mastermind facade | `NOT_BUILT` / candidate | Competes against direct LSP in C0. |
| Generic local/stdio MCP trust class | `REJECTED_BY_DESIGN` | Only the closed `sealed-stdio-v1` class below may be proposed. |
| Worker-wide GitHub MCP in V1 | `REJECTED_BY_DESIGN` | Existing local Git and accepted GitHub acquisition seams remain canonical verification. |
| Sourcebot, SCIP and ast-grep in V1 | `REJECTED_BY_DESIGN` | Reconsider only against a measured benchmark gap. |

## 3. Architecture freeze — two governed discovery planes plus existing truth

The production target is **not one super-MCP**. It is two narrow read capabilities with different state and trust models, followed by existing canonical verification.

```text
                         +-------------------------------+
                         | GitHub / exact local Git      |
                         | canonical implementation truth |
                         +---------------+---------------+
                                         ^ verify
                                         |
+----------------------+      +----------+-----------+
| codeDiscovery        |      | codeSemantics        |
| fixed self-hosted    |      | Attempt-local sealed |
| HTTPS facade         |      | stdio facade         |
| over Zoekt           |      | over Serena or LSP   |
+----------+-----------+      +----------+-----------+
           ^ global                         ^ exact current
           | indexed refs                   | worker worktree
           +---------------- model ----------+
```

### 3.1 `codeDiscovery`: company-wide indexed search

A fixed self-hosted HTTPS `streamable-http` Mastermind facade owns the model-facing contract. Zoekt is an internal disposable engine and is never exposed directly.

V1 tool surface:

```text
search_code
list_repositories
index_status
```

The facade accepts only bounded query, repository, path, language, branch/ref and result-limit fields. It exposes no repository enrollment, credential, reindex, shard, filesystem, shell, process or service-administration tool.

Every search response carries:

```text
query_id
service_build_digest
repository identity
indexed ref and commit SHA
index generated_at and observed_at
freshness state
coverage state
health state
path and bounded line range
bounded contextual snippet
match kind and truncation state
canonical_verification_required = true
```

A negative search result is not authoritative when the requested repository/ref is omitted, freshness exceeds the reviewed budget, shard/index health is degraded, result evaluation truncated, or the facade cannot prove coverage. The response must say `coverage_unknown`, `stale`, `degraded`, or the exact typed failure rather than returning a plausible empty result.

Initial Z0 repository set:

- protected/default Mastermind source and source law;
- protected/default Mastermind Terminal application source;
- Macro source, tests, workflows, docs, research and Agent OS with strict generated/data exclusions.

Initial Macro policy is include-first for source-bearing paths and exclude-first for `site/**`, most `data/**`, content-addressed archives, rendered artifacts, binaries, caches and vendored dependencies. Z0 may admit a narrow excluded subtree only when a real benchmark task proves it improves authoritative discovery without poisoning quality or cost.

V1 indexes protected/default refs. Active PR branches are not a default global-index obligation. Exact candidate state belongs to the worker's local semantic plane or current GitHub PR evidence. A selected PR-ref tier may be added only if Z0/CI5 proves it materially improves collision or review journeys and can preserve explicit ref/freshness truth.

Index credentials stay outside model arguments and responses. Index storage is rebuildable from Git/GitHub; backup means a reproducible manifest and rebuild runbook, not a new durable truth store.

### 3.2 `codeSemantics`: exact current worktree semantics

The model-facing server is a small Mastermind-owned MCP facade launched as a local stdio child by the existing Codex App Server/operator harness composition. The backend may be pinned Serena or direct LSP, but the stable facade contract does not change with backend choice.

V1 tool surface:

```text
workspace_status
symbol_overview
find_symbol
find_references
find_implementations
diagnostics
```

No tool accepts an arbitrary filesystem root, repository path, worktree path, Attempt ID, Worker ID, session identity, endpoint, language-server command, project selector, executable, environment override or backend configuration.

The process must:

1. inherit the exact App Server/thread CWD already established from the sealed Attempt workspace;
2. require that CWD resolve to the Git worktree root;
3. reject symlink/root/device/inode drift;
4. calculate the exact workspace identity expected by the current Operator Adapter;
5. calculate Git HEAD/base SHA and a deterministic candidate dirty-state fingerprint without uploading full candidate contents in the receipt;
6. keep caches, language-server state and metadata in an Attempt-scoped external scratch directory;
7. perform zero writes inside the candidate worktree;
8. run with network disabled;
9. expose no edit, shell, memory, project-switching, onboarding, prompt, dashboard or backend-administration capability.

Before the first model turn, the trusted adapter starts the thread at the sealed workspace, obtains `mcpServerStatus/list`, then directly invokes `workspace_status` through App Server's host-side `mcpServer/toolCall`. The returned structured binding receipt must exactly match the expected workspace path identity, device/inode, Git HEAD/base SHA, wrapper bundle digest, backend digest, language-server digest set and tool-schema digest. Any mismatch fails closed before model use.

The child process is subordinate to the current App Server/operator harness process. It owns no Job, Attempt, Worker, lease, fence, retry, provider choice, session, workspace registry, queue or lifecycle. A child crash may be restarted only inside the same still-valid Attempt after the full binding/attestation sequence succeeds again. It never causes cross-worker or cross-provider failover.

### 3.3 Backend decision deliberately held for C0

C0 compares:

- **Candidate S:** Serena `v1.7.0` at `949a27ef1e5fda1a6e7b561e777bcece345c6ffd`, hidden behind the facade;
- **Candidate L:** direct language-server orchestration behind the same facade.

Candidate S must ignore repository `.serena` configuration, prompts, modes, language-server commands and project metadata. Dashboard, memory, editing, shell, onboarding and project activation/switching remain disabled. Backend metadata must live outside the candidate tree. The exact advertised and callable facade tool census—not upstream claims—governs.

Serena wins only if it materially improves semantic recall, latency, language coverage or implementation cost **and** passes every security/worktree falsifier. Direct LSP wins when equivalent useful semantics can be delivered with a smaller, more deterministic authority surface.

### 3.4 Canonical verification remains separate

Discovery is never implementation truth.

- Exact local candidate bytes, Git HEAD, dirty diff and ancestry are verified through existing local Git behavior inside the sealed workspace.
- Protected/default SHA, exact remote file at ref, PR/diff, changed-file census, commit history, CI/status and merge evidence are verified through the accepted GitHub acquisition seam.
- A CodeIntel result never authorizes a modification, merge, release, lifecycle transition, owner decision or factual claim about protected current source without the relevant exact local/GitHub check.

No broad GitHub MCP is included in V1 merely for symmetry. CI5 may propose a tiny read facade only if the benchmark proves that an essential worker journey cannot be completed reliably through local Git plus the existing GitHub seam.

## 4. Capability-registry evolution

Current registry v3 supports reviewed HTTPS `streamable-http`. CI1 may propose schema v4 with one additional **closed transport class**:

```text
transport = sealed-stdio-v1
binary_identity = reviewed logical ID
binary_bundle_digest = exact SHA-256
argv = fixed token array; no shell
cwd_policy = inherit_attempt_workspace
configured_cwd = forbidden
environment = empty or exact closed allowlist
network_policy = disabled
model_supplied_arguments = forbidden
server_identity/version = exact
enabled_tools = exact closed list
tool_schema_digest = exact
workspace_binding_receipt = required before first model turn
```

This is not generic stdio support. The registry parser must refuse unrecognized command fields, arbitrary executable paths, configured CWD, shell strings, mutable package launchers such as `uvx ...@latest`, dynamic environment values, ambient PATH resolution, secret-bearing variables and omitted digests.

At Attempt composition time the existing harness resolves the reviewed binary from an immutable installed bundle, rejects symlinks, verifies owner/mode/digest, compiles the exact App Server configuration and includes its security-relevant projection in the current capability manifest/attestation. The adapter rechecks the executable/bundle before launch and verifies the thread-specific binding receipt after launch.

Existing failure families remain owners. Use the current equivalents of capability-attestation failure, workspace mismatch, MCP/tool transport failure and process crash. Do not create a CodeIntel lifecycle database to remember them.

## 5. Authority and no-rebuild law

The governing composition is:

```text
Executive selects/claims Worker and Attempt
-> Operator Harness establishes exact workspace and capability profile
-> CodeIntel read capabilities attach to that already-bound Attempt
-> model discovers and reasons
-> local Git/GitHub verify conclusions
```

Never invert it into:

```text
CodeIntel selects repo/worktree/worker/session
-> execution follows that selection
```

Code Intelligence Fabric owns retrieval contracts, freshness, worktree semantic binding and benchmark evidence only. It owns none of:

- Executive Job/Attempt/Worker/Event lifecycle;
- Worker identity, claim, lease or fence;
- provider/account/host placement;
- workspace creation or registry;
- retry/failover;
- organizational memory;
- Agent OS workstreams/decisions;
- GitHub implementation truth;
- Slack transport state;
- Linear portfolio state;
- source-code modification or merge authority.

HF1 in Executive Capacity Fabric remains the owner of future provider-neutral harness generalization. CI1 may extend only the current exact capability/attestation seam required by this program; it may not absorb HF1 or introduce a CodeIntel broker/scheduler/provider adapter.

## 6. Product journeys

### Fresh Sol architecture recovery

1. `codeDiscovery.search_code` finds current source law, implementations, consumers and tests across repos with indexed SHA/freshness.
2. Sol narrows to the relevant exact repository/worktree and uses `codeSemantics` for symbols/references.
3. Sol verifies protected current source, recent PRs and exact files through GitHub.
4. Output distinguishes canonical owner, candidate implementation, historical/dead paths and unresolved gaps.

### Bounded worker feature implementation

1. Before editing, the worker discovers producer, consumers, tests and sibling contracts.
2. The semantic facade reads only the exact candidate worktree attached to the current Attempt.
3. After edits, the same facade sees uncommitted candidate state; local Git proves the dirty diff.
4. The worker returns exact changed symbols, consumers considered, tests and canonical verification evidence.

### Adversarial PR review

1. Reviewer begins from changed files/symbols.
2. Global discovery finds cross-repo owners and textual consumers; exact semantics finds local references/implementations.
3. GitHub confirms PR/head/protected bytes and CI.
4. Review either catches a real impact or records why a suspected impact is ruled out.

### Crash/session recovery

A fresh Sol/worker reads the durable handoff, uses global discovery to recover the owning surfaces, binds semantics only to the new exact Attempt/worktree, and verifies current GitHub rather than trusting stale prior-session conclusions.

### Cross-repository collision detection

Before commission, Sol uses discovery to identify current source-law and implementation paths, then checks open/current PR evidence through GitHub. CodeIntel supplies evidence; existing program/authority law decides whether paths truly collide.

## 7. Data, time, null and correction behavior

- Every indexed result names the exact indexed commit/ref and observation times.
- `unknown`, `omitted`, `stale`, `degraded`, `truncated` and `not_found_on_healthy_covered_ref` are distinct states.
- No clock wrapper may refresh stale source evidence.
- Index correction creates a new observation; historical benchmark evidence remains immutable.
- Worktree identity includes exact sealed path identity and Git state. A moved/deleted/replaced worktree invalidates the binding.
- Candidate dirty state is local truth for the current Attempt and must never be silently described as remote/protected source.
- Backend-generated summaries or ranking have zero authority. V1 results are deterministic retrieval/semantic facts plus bounded engine scoring; model synthesis remains outside the capability contract.

## 8. Mandatory failure design

C0/Z0/CI1 tests must cover at least:

- semantic server or language server unavailable;
- unsupported/wrong language-server version;
- wrapper, backend, binary, bundle, server identity, tool or schema drift;
- worktree moved, deleted, symlinked or identity-replaced;
- stale binding and attempted project switch;
- two concurrent Attempts/worktrees cross-read probe;
- repository configuration attempting to change prompt, tool or executable behavior;
- analyzer writes into the candidate tree;
- process crash before and during a model turn;
- restart under the same Attempt and attempted restart under another Attempt;
- Zoekt/index stale, failed, omitted repository/ref, malformed/corrupt shard, duplicate repository name collision, partial coverage and plausible-empty-result failure;
- oversized query/result and explicit truncation;
- GitHub unavailable, credential failure or exact SHA unavailable;
- local candidate differs from remote;
- index/semantic result references a symbol absent from canonical bytes;
- component upgrade changes schema or semantics;
- cleanup failure.

Missing CodeIntel is explicit degradation. It never permits fabrication, authority widening, cross-carrier retry, project switching or hidden use of an ambient tool.

## 9. Empirical benchmark program

CI5 uses 24 real completed Mastermind tasks, stratified as follows:

- 3 Executive OS lifecycle/authority tasks;
- 3 Operator Harness/continuity tasks;
- 3 Capacity/model-routing tasks;
- 3 Worker Presence/Wake/dialogue tasks;
- 3 Control Room/frontend tasks;
- 3 cross-repository Mastermind/Macro tasks;
- 3 regression/root-cause investigations;
- 3 adversarial PR reviews.

Each case freezes a historical prompt and exact repository/ref window, then records an answer key containing canonical owner, repositories, critical files, important symbols, consumers, tests/source law, relevant PR evidence and known ambiguities.

Conditions:

1. current baseline retrieval path;
2. `codeDiscovery` only;
3. `codeSemantics` only where applicable;
4. full Fabric plus canonical verification;
5. backend ablation: hardened Serena versus direct LSP; optional structural engine only when a measured gap exists.

Measurements:

- time and tool calls to first authoritative file;
- relevant-file recall at bounded K;
- symbol/reference/implementation/consumer recall;
- false-positive search burden;
- context/tokens and whole-file reads;
- missed cross-repo consumers;
- wrong-owner and stale-current conclusions;
- review defects caught or safely ruled out;
- architecture mistakes and worker completion quality;
- model tier required;
- latency, CPU, RAM, index size and semantic startup cost.

Proposed minimum promotion gates, adjustable only from real C0/Z0 evidence:

- at least 30% lower median tool calls or context to the authoritative answer;
- at least 95% recall of critical answer-key owner/files;
- at least 20 percentage-point improvement in cross-repo consumer recall on applicable cases;
- zero increase in wrong-owner, stale-current or fabricated-current conclusions;
- at least one historical review impact caught or safely ruled out that the baseline missed;
- a lower-tier worker is non-inferior to the current higher-tier baseline on at least half of bounded cases;
- resource and startup ceilings are frozen after C0/Z0 measurement and then met in CI5.

## 10. Program waves and gates

### F0 — this architecture and benchmark freeze

Records/source law only. No runtime paths or host state.

### C0 — semantic backend falsifier

Disposable exact worktrees compare hardened Serena and direct LSP under the stable facade contract. Proves usefulness, tool census, zero candidate writes, exact binding, configuration injection resistance, concurrent isolation, startup, crash and cleanup. A working spike is not production.

### Z0 — global discovery falsifier

Disposable Zoekt at pinned `sourcegraph/zoekt@5f833dde1bc4b1a8f99007617b4b721e44506c4f` indexes a curated real subset, exercises explicit freshness/coverage/health, tests corrupt/duplicate-shard failure and measures search quality/resource cost. A working index is not production.

C0 and Z0 may run in parallel only on disjoint branches/paths and with no shared runtime/harness edit.

### CI1 — production-inert capability boundary

After C0 backend selection, implement `sealed-stdio-v1`, strict config projection/digests, host-side pre-turn binding call and mutation/falsifier tests. No production profile or installation.

### CI2 — exact worktree isolation

Prove simultaneous worktrees cannot cross-read or switch; prove dirty-state semantics, restart and cleanup under real Operator Adapter composition.

### CI3 — global discovery facade

Implement the fixed HTTPS facade, repository/ref manifest, bounded result contract, health/freshness semantics and rebuild runbook.

### CI4 — reviewed worker capability profile

Add exact CodeIntel grants to the existing registry/harness profile path. Remain canary/inert until full attestation and current collision reconciliation.

### CI5 — A/B benchmark and live bounded canary

Run the 24-case benchmark, one real bounded implementation journey and one real adversarial review with independent review of the evidence.

### CI6 — staged production rollout

Promote only after gates pass; record usage doctrine, monitoring, rollback, operating ownership, economic outcome and durable closeout.

Every wave is an independent operation/carrier and one independently reviewable capability. No wave inherits START, watcher state, runtime binding or modification authority from another wave.

## 11. Rejected alternatives

- **Direct Serena grant:** rejected because upstream read-only advertisement is not the grant, project-controlled configuration can influence behavior, and the surface is wider than Mastermind needs.
- **Generic trusted local MCP:** rejected because it turns a narrow need into ambient executable authority.
- **Central HTTPS semantic router:** rejected because mapping tokens/Attempts to mutable worktrees risks a second workspace/session registry.
- **One dynamic HTTPS sidecar per worker:** rejected for V1 because ports, TLS identities, endpoint routing and cleanup add machinery already avoided by inherited-CWD stdio.
- **One super-MCP combining index, semantics, GitHub and administration:** rejected because the components have different freshness, state and authority and would blur canonical verification.
- **Sourcebot/SCIP/ast-grep bundle:** rejected until a benchmark names a specific missing job. Sourcebot may later serve a distinct human browsing journey; SCIP may later serve persistent cross-repo semantics; ast-grep may later serve syntax-aware structural queries.

## 12. F0 acceptance and exact next action

F0 passes when this architecture and the companion benchmark/implementation plan are current-base reviewed, CI is green, and the PR is explicitly accepted as `SPEC_ONLY / RECORDS_ONLY`. F0 does not prove CodeIntel capability.

After F0 acceptance:

1. create/update the owning Macro Agent OS workstream and decision with the exact accepted source-law SHA;
2. commission C0 through `PREFERRED_AVENUE: CTO Sol` because it is a difficult but bounded security/semantic falsifier;
3. commission Z0 through `PREFERRED_AVENUE: Terra` because it is bounded infrastructure/research work;
4. record `WHY NOT FABLE`: the product, authority and experiment boundaries are frozen; sustained principal ambiguity is not required;
5. give each child its own operation key, carrier, pickup/START and reciprocal continuation cycle.

Until then, hold all edits to `control_plane/**`, `config/executive_agent_capabilities.json`, Operator Harness/runtime paths, MCP configuration, hosts, Slack/Linear projections and production services.