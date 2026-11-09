# Fresh-Sol Evaluation Harness F0 Design

**Date:** 2026-08-26  
**Owner:** Sol, AI CEO  
**Parent gate:** Linear MAS-136 / Mastermind PR #147  
**Status:** DESIGN FROZEN IN CHAT / WRITTEN SPEC CHECKPOINT  
**Protected Mastermind basis:** `acc7ebc4bf44a4857168f481a745b2e57d5be585`  
**Protected Skillpack:** `mastermind.sol_skillpack.v1` 1.0.0 / bootstrap major 1  
**Implementation carrier:** `sol/mas-136-fresh-sol-eval-f0-20260826`

## 1. Outcome

Unlock MAS-136 by adding one production-relevant, evaluation-only harness that can execute genuinely fresh `gpt-5.6-sol` contexts against immutable control and amended Sol Skillpack bytes, preserve per-run isolation, and return verbatim evidence with exact runtime/session identity.

This capability exists only to produce behavioral release evidence for constitutional Sol procedure changes. It does not become a general session launcher, scheduler, worker broker, or second lifecycle plane.

### Completion capability

After F0 is accepted and available on a host with one independently authenticated dedicated ChatGPT Pro Codex realm, an operator can run the MAS-136 matrix without manually opening chats:

```text
immutable protocol + immutable Skillpack arm
  -> fresh isolated Codex App Server process
  -> brand-new native thread
  -> one scenario turn
  -> verbatim answer + exact identity/evidence receipt
  -> deterministic cleanup
```

The first consumer is the frozen #147 release matrix: S2, S6, S7, S8; three amended runs plus one control run per scenario, sixteen valid primary-Sol runs total.

## 2. Current truth and why this is the next dependency

MAS-136 is not blocked on #147 deterministic implementation. The deterministic Continuation Delta implementation is already PASS / `COMPLETED_DO_NOT_REPEAT` on procedure head `8209e1f31da15f8effc23a9899a5c5a02d30cab4`.

The existing Slack behavioral-evidence carrier was delivered and ACKed, but ChatGPT3 returned `EXTERNAL_CAPABILITY_BLOCKED` with 0/16 valid runs because that surface cannot spawn genuinely independent fresh primary-Sol contexts after reading the protocol.

Mastermind already has the lower-level execution substrate needed for the missing capability:

- `scripts/ohf/laboratory.py` provides a production-inert live Codex App Server laboratory using an explicit dedicated `CODEX_HOME` and isolated workspace;
- `scripts/ohf/codex_app_server_probe.py` already proves fresh `thread/start`, turn execution, model/config/account observation, and process cleanup without Executive lifecycle mutation;
- `scripts/ohf/p1a_capability_policy.py` freezes the minimal-surface Codex config (`apps=false`, bundled skills disabled, read-only sandbox, approval never) and fail-closed capability classification;
- the durable OHF live acceptance proved an independently authenticated ChatGPT Pro realm and requested/served `gpt-5.6-sol` on the App Server path.

Therefore F0 extends the existing OHF laboratory/test substrate. It does not introduce a new runtime.

## 3. Authority and no-duplicate-system boundaries

Canonical ownership remains unchanged:

- Executive OS owns production Job / Attempt / Worker / Event and runtime session lifecycle.
- Agent OS owns organizational workstreams, decisions, discoveries, and handoffs.
- GitHub owns exact implementation and evidence bytes.
- Linear MAS-136 is a release-gate projection.
- Slack remains transport only.

F0 run IDs, process IDs, and native thread IDs are **evaluation evidence identities**, not production lifecycle records. They must never be inserted into Executive SQLite or treated as a substitute for Executive Attempts.

The harness must not add or modify:

- Executive Runtime schema or Job/Attempt/Worker/Event behavior;
- worker broker, supervisor, routing, Capacity Fabric, Wake, CeoIngress, SOL_STATE, Slack transport, Agent OS, Linear runtime, or Control Room;
- credential storage, credential copying, provider-login automation, retry queues, session registries, databases, daemons, launchd services, or schedulers;
- #147 Skillpack/linter procedure bytes.

## 4. Runtime choice

### Accepted approach: OHF live laboratory + Codex App Server

Use the existing production-inert OHF laboratory directly. Every evaluation run creates a new local App Server process and calls `thread/start` exactly once to obtain a brand-new native thread.

This is preferred over two rejected alternatives:

1. **Canonical Executive Jobs for all test samples** — rejected for F0 because it would couple constitutional behavioral proof to unrelated unfinished host-arming/autonomy gates and turn an evaluation primitive into production orchestration work.
2. **Automated ChatGPT web chats** — rejected because it introduces browser/login/Chairman-seat machinery into a procedure test and provides worse process/session identity evidence than the existing App Server substrate.

F0 is production-relevant because the provider realm is an independently authenticated ChatGPT Pro Codex realm and the served model must be exactly `gpt-5.6-sol`. It is evaluation-only because it is not registered with Executive worker routing and can perform no canonical business mutation.

## 5. Exact implementation surface

Expected implementation is intentionally small:

- create `scripts/ohf/fresh_sol_eval.py` — CLI + pure orchestration for source materialization, isolated run execution, evidence emission, and fixed MAS-136 matrix execution;
- create `tests/test_fresh_sol_eval.py` — deterministic fake-backend/falsifier coverage;
- optionally create a narrow fixture under `tests/fixtures/fresh_sol_eval/` only if the existing fake App Server cannot express a discriminating failure without widening production code;
- reuse `scripts/ohf/laboratory.py`, `scripts/ohf/protocol.py`, `scripts/ohf/redaction.py`, and `scripts/ohf/p1a_capability_policy.py` without changing their authority semantics;
- do not modify `control_plane/**`, `docs/sol_skills/**`, `scripts/sol_commission_lint.py`, Executive configuration, or #147 evidence/procedure files in the implementation PR.

A small refactor to an existing `scripts/ohf/**` helper is permitted only if required to expose already-existing process/thread/config evidence to the new runner. It must remain production-inert and receive its own regression test.

## 6. Immutable procedure input contract

F0 receives immutable Git identities; it does not trust working-tree copies as procedure truth.

For MAS-136 the exact arms are:

```text
control:
  commit = 51f9942733b86e550bb9169d2a43462bd28e774f
  expected Skillpack = 1.0.0

amended:
  commit = 8209e1f31da15f8effc23a9899a5c5a02d30cab4
  expected Skillpack = 1.1.0
```

Before a run, the runner must:

1. verify both commits exist in the supplied local Mastermind Git object database;
2. read `docs/sol_skills/INDEX.md` from the exact selected commit;
3. verify schema `mastermind.sol_skillpack.v1`, expected version, and bootstrap-major compatibility;
4. materialize **all** `docs/sol_skills/*.md` files from that exact commit, sorted by repository path;
5. record every source path and Git blob SHA plus one aggregate SHA-256 over the exact ordered source bytes;
6. refuse if the commit, expected version, file census, or any source read is unavailable.

The runner performs no network fetch. If the required immutable Git objects are absent, it returns a fixed pre-run refusal and the operator must prepare the local clone separately.

### Procedure injection

Each isolated workspace receives one generated root `AGENTS.md`. The wrapper text is fixed and byte-identical between control and amended arms. It states only that this is a read-only Sol evaluation, names the exact local procedure bundle as governing procedure, prohibits external modification, and asks the model to answer the supplied scenario.

After that neutral wrapper, `AGENTS.md` concatenates the exact materialized `docs/sol_skills/*.md` source bytes in deterministic path order with fixed file-boundary markers. No Continuation Delta semantics are added by the wrapper itself.

The evidence receipt records:

- wrapper version/digest;
- ordered source paths/blob SHAs;
- aggregate procedure-context SHA-256;
- source commit and expected Skillpack version.

This guarantees the arm difference comes from immutable Skillpack bytes rather than from an informed orchestrating chat.

## 7. Scenario input contract

The scenario contract remains owned by #147. F0 must not duplicate scenario wording in Python constants.

The CLI receives an explicit `--protocol-path` pointing at `review_evidence/continuation_delta/PRESSURE_TEST_PROTOCOL.md` from a checkout of the #147 evidence carrier. The parser must fail closed unless it can find exactly one shared preamble and exactly one section for each release-required scenario `S2`, `S6`, `S7`, and `S8` with their `PASS requires` boundaries.

The exact scenario prompt sent to the model is:

```text
<shared preamble verbatim>

<scenario packet verbatim>
```

The runner records the protocol file SHA-256 and exact prompt SHA-256 in every run. It never silently reconstructs missing wording from built-in defaults.

## 8. Per-run isolation law

A valid run must satisfy every item below.

### Fresh workspace

- unique temporary root and workspace;
- no repository checkout except the generated procedure bundle and fixed evaluation files;
- no previous run output, scorecard, PR discussion, Agent OS record, Slack thread, or opposite-arm material;
- unique run UUID generated by the harness.

### Fresh provider process/session

- new Codex App Server OS process;
- private process group using the existing containment mechanism;
- `initialize` succeeds;
- exactly one `thread/start` for the run;
- no `thread/resume`;
- no `thread/fork`;
- exactly one scenario turn;
- after evidence capture, graceful termination plus process-group-dead proof.

Any reuse/resume/fork or ambiguous cleanup makes the run invalid.

### No model-accessible side capabilities

Use the existing minimal-surface config floor:

```toml
model = "gpt-5.6-sol"
approval_policy = "never"
sandbox_mode = "read-only"

[features]
apps = false

[skills.bundled]
enabled = false
```

No MCP server is configured. No evaluator skill is installed. No plugin is requested. Native helpers/subagents are not enabled.

The runner must query effective config and observable capability surfaces before the scenario turn. A run is valid only if:

- served model is exactly `gpt-5.6-sol`;
- approval is exactly `never`;
- sandbox is exactly `read-only`;
- configured/observed MCP set is empty;
- plugin set is empty;
- no forbidden or unclassified model-visible capability is observed under the existing P1A capability-classification semantics.

If the installed Codex version exposes unavoidable ambient capabilities that cannot be classified as absent without ambiguity, the run is invalid and F0 returns a capability-attestation blocker rather than weakening the gate.

Provider transport required for Codex to reach the OpenAI service is allowed. Model tool/shell network authority remains disabled.

## 9. Authentication and credential boundary

F0 requires an explicit `--codex-home` pointing at one independently authenticated non-default Codex realm.

Reuse the existing live-laboratory safety law:

- refuse implicit `~/.codex`;
- require a real dedicated directory and a private independently authenticated `auth.json` marker;
- never open, copy, symlink, print, serialize, hash, or commit credential contents;
- do not perform login, logout, device authorization, token refresh ceremony, or credential repair;
- no credential value enters argv, scenario prompt, evidence, environment additions, or repository bytes.

The evidence may record only safe classification/identity facts such as auth type, plan type, `requires_openai_auth`, non-default-realm boolean, and a non-secret harness-generated realm identity digest that cannot reconstruct credential contents.

## 10. Verbatim output and evidence schema

After `turn/completed`, F0 reads the completed native thread through the App Server read/list surface and extracts the final assistant text exactly once. Notification fragments are not reconstructed into a synthetic answer if the canonical thread read is unavailable.

The run artifact is Markdown suitable for direct persistence beneath #147 and contains at minimum:

```text
schema: mastermind.fresh_sol_eval_run/v1
scenario_id
arm: control-1.0.0 | amended-1.1.0
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
exact_prompt
exact_model_output
manual_classification: PENDING_SOL_REVIEW
```

The file path is deterministic from `arm / scenario_id / run_id` and uses create-only semantics. An existing run artifact is never overwritten.

The runner also writes/updates a machine-readable manifest of completed run IDs using atomic replace, but that manifest is evidence bookkeeping only. It carries no scheduling, lifecycle, retry, or authority semantics.

### Secret/error hygiene

Because exact output is required, a run whose prompt or model output trips the existing repository secret-shape detector is not persisted as a valid raw artifact. The runner emits a fixed local refusal identifying only the run ID and `EVIDENCE_SECRET_SHAPE_REFUSED`; the sample must be rerun fresh.

Exceptions, paths, provider errors, and credential metadata are laundered through existing OHF redaction/fixed failure vocabulary. A failed sample never masquerades as behavioral PASS evidence.

## 11. Matrix execution

`run-matrix` is a convenience wrapper around the same `run-one` primitive; it is not a scheduler.

For MAS-136 it executes exactly:

```text
S2: control x1, amended x3
S6: control x1, amended x3
S7: control x1, amended x3
S8: control x1, amended x3
```

Total required valid samples: 16.

Each sample receives a new workspace, process, and native thread. A failed/invalid sample stops the matrix by default. The operator may explicitly restart the matrix command later; already-created valid evidence files are detected and skipped by exact run identity only when the operator passes an explicit resume manifest. The runner never retries an effect-unknown provider turn automatically.

No behavioral grading is automated. Sol remains the reviewer. F0 outputs `PENDING_SOL_REVIEW`; after the corpus exists, Sol classifies the exact raw outputs against #147's `PASS requires` text and produces the aggregate scorecard.

## 12. Failure vocabulary

At minimum F0 must distinguish these pre-run/run outcomes without leaking provider detail:

- `SOURCE_COMMIT_UNAVAILABLE`
- `SKILLPACK_IDENTITY_MISMATCH`
- `PROCEDURE_SOURCE_UNAVAILABLE`
- `PROTOCOL_INVALID`
- `AUTH_REALM_INVALID`
- `HARNESS_BINARY_UNAVAILABLE`
- `HARNESS_INITIALIZE_FAILED`
- `CAPABILITY_ATTESTATION_INVALID`
- `SERVED_MODEL_MISMATCH`
- `THREAD_START_FAILED`
- `TURN_EFFECT_UNKNOWN`
- `THREAD_READ_FAILED`
- `EVIDENCE_SECRET_SHAPE_REFUSED`
- `CLEANUP_UNPROVEN`
- `EVIDENCE_COLLISION`

A failure before provider dispatch may be retried only as a newly identified run. A timeout/disconnect after turn dispatch is effect-unknown for that run and may not reuse or resume the same native thread.

## 13. Deterministic vs model-generated behavior

Deterministic first-party code owns:

- Git source verification/materialization;
- procedure/prompt digests;
- workspace/process/thread lifecycle mechanics;
- model/config/capability attestation;
- run/evidence identity;
- cleanup proof;
- secret-shape refusal;
- matrix cardinality and corpus completeness checks.

The only model-generated field with behavioral meaning is `exact_model_output`. It has **zero authority** to mark itself PASS, authorize a merge, alter company state, or dispatch work.

## 14. TDD and falsifier requirements

Implementation must be RED-first. The deterministic fake-backend suite must kill at least these mutations:

1. second sample reuses the first native thread;
2. runner uses `thread/resume` or `thread/fork`;
3. working-tree Skillpack bytes substitute for exact Git-commit bytes;
4. control/amended wrapper differs beyond source bytes/declared arm identity;
5. one source file is missing or sourced from the wrong commit;
6. protocol parser silently falls back to hard-coded scenario text;
7. served model differs from `gpt-5.6-sol`;
8. MCP/plugin/unclassified ambient capability is present;
9. default `~/.codex` is accepted;
10. credential content is read/copied/serialized;
11. notification fragments are accepted when canonical thread read is unavailable;
12. output artifact overwrites an existing run;
13. effect-unknown turn is automatically retried/resumed;
14. process-group cleanup is not proven;
15. secret-shaped raw output is persisted;
16. matrix cardinality is anything other than 4 control + 12 amended valid samples for the frozen MAS-136 mode.

The fake tests must not call a provider or require credentials.

## 15. Live F0 proof before merge

Repository CI alone is not acceptance. The implementation carrier must return one bounded live proof using an independently authenticated dedicated ChatGPT Pro Codex realm:

1. one control run and one amended run against a harmless MAS-136 scenario packet;
2. two distinct App Server PIDs/process identities;
3. two distinct native thread IDs;
4. both requested and served model exactly `gpt-5.6-sol`;
5. expected Skillpack identity/digests match the two immutable commits;
6. ambient capability gate passes;
7. exact raw outputs are captured;
8. cleanup is proven for both processes;
9. default Chairman Codex realm is untouched;
10. no Executive/Agent OS/Linear/Slack/production mutation occurs.

The live proof may use ephemeral local evidence and a sanitized receipt in the implementation PR. It must not prematurely populate the #147 16-run release corpus unless Sol explicitly releases corpus execution after accepting F0.

Capability state after code+CI but before live proof: `BUILT_NOT_PROVEN`.

Capability state after accepted live two-run F0 proof: `PROVEN_LIVE` **for isolated fresh-Sol behavioral evaluation only**.

## 16. Post-F0 MAS-136 execution

After F0 is accepted, resume the existing MAS-136 evidence operation; do not create another behavioral-evidence carrier.

Run the sixteen samples against the frozen #147 protocol and persist them under #147's existing `review_evidence/continuation_delta/` path. Then:

1. Sol reviews every raw answer against the scenario-specific `PASS requires` text;
2. at least one control must reproduce the target continuation/replay failure family;
3. all twelve amended runs must PASS;
4. commit the evidence + scorecard on the existing #147 carrier;
5. rerun exact-head #147 hosted CI;
6. re-pin protected Mastermind current master;
7. only then adjudicate #147 merge and later Shared Project kernel propagation.

Any amended behavioral failure returns the exact output/rationalization for the smallest procedure correction and affected fresh rerun. F0 itself is not modified unless the harness/evidence mechanism failed.

## 17. Explicit non-goals

F0 does not:

- merge or modify #147;
- change the Continuation Delta law;
- authorize R3C;
- create production Executive Jobs;
- become a provider router or capacity consumer;
- add parallel model providers;
- automate ChatGPT browser sessions;
- provision or rotate provider credentials;
- add a service/daemon/scheduler;
- become a general benchmark framework;
- grade behavioral correctness automatically;
- use control failures as implementation defects;
- claim the full Autonomy V1 path is live.

## 18. Stop condition and return packet

The F0 builder stops after one draft implementation PR returns all of:

- immutable final head SHA;
- exact changed-file list;
- RED mutation/falsifier receipts;
- targeted and full hosted CI/CodeQL receipts;
- live two-run F0 proof with safe identity/digest/cleanup receipts;
- confirmation that `control_plane/**`, `docs/sol_skills/**`, `scripts/sol_commission_lint.py`, #147, Agent OS, Linear, Slack, and production state were untouched;
- any installed-Codex capability that prevented a clean minimal surface;
- exact next action: Sol final F0 review, not MAS-136 corpus execution by the builder.

The builder must not self-merge F0, run the sixteen-sample constitutional corpus, merge #147, propagate the kernel, start R3C, or absorb adjacent Autonomy V1 work.
