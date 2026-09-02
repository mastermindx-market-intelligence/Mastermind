# Agent Evaluation EVAL-OHF2 — OHF-to-R0 Bridge

Operation `mastermind-agent-evaluation-ohf2-integration-20260901-fable-001`.
Base: `origin/master` at `e255fdd2` (>= `d2da7053`, carrying F0's records,
R0's evidence core, C0's governed corpus, S1's scorers, and the scoped
inertness fence). B4 of the Chairman-delegated agent-evaluation-fabric
program.

Controlling records (read in full before this one; this record never
restates their law, only cites and extends it):

- `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`
  (design) — §7.4/7.5 run draft and run receipt contracts, §7.6
  deterministic validity, §8.3/8.4 safe paths and create-only publication,
  §9.1/9.2 native-core-first and "OHF is the sole fresh runner."
- `docs/superpowers/plans/2026-08-31-agent-evaluation-r0.md` (R0 plan) —
  Task 4 (`finalize_run_receipt`), Task 6 (`ArtifactStore`), §5.6
  resolver boundary / complete-enumeration law.
- `docs/superpowers/specs/2026-09-01-agent-evaluation-r0-environment-free-secret-safety-amendment.md`
  — the environment-free law this wave inherits unchanged (no network/
  process/environment/credential access anywhere in `ohf_bridge.py`).
- `docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md` (S1
  plan) — `technical_integrity` scorer and `summarize_experiment`, reused
  unmodified against bridged runs.
- Mastermind PR #162 branch head `478ca1f5` (unmerged, read-only source
  for this record): `scripts/ohf/fresh_sol_eval.py` — the OHF F0 runner's
  evidence-artifact and manifest formats this bridge adapts. **Not
  imported and not modified.**

## 0. Why this wave exists

R0/C0/S1 give Mastermind a canonical, graph-verified evaluation-artifact
tree, but nothing yet turns one *live* OHF fresh-Sol run into an R0 run
receipt. OHF1 (PR #162) is the sole fresh runner (design §9.2) and is
`BUILT_NOT_PROVEN` — its live canary is parked pending a human go/no-go —
but its *output format* (the evidence Markdown artifact + `MANIFEST.json`)
is already frozen on that branch head. This wave builds the adapter that
consumes that frozen format and drives the existing R0 finalizer/store,
proven end-to-end against synthetic (fake-client) OHF artifacts, so that
the moment the OHF1 canary is approved, the OHF -> R0 pipeline is already
live with zero further integration work.

## 1. Scope and non-goals

**In scope:** `scripts/agent_eval/ohf_bridge.py` (stdlib-only, additive),
its tests, this plan record, and the inertness-fence ratchet line for the
three new files.

**Hard non-goals:**

- No second runner. OHF (PR #162) remains the sole fresh runner (design
  §9.2); this bridge only *consumes* its output shape.
- No live provider call, process launch, network access, or credential
  read anywhere in `ohf_bridge.py` — same environment-free law as R0/S1
  (amendment §3.2/§4.5), verified by the SAME AST/subprocess inertness
  fence R0 already runs (`tests/test_agent_eval_inertness.py`), which
  parametrizes over every `scripts/agent_eval/*.py` file automatically.
- No modification to `scripts/ohf/**` or PR #162's branch. This bridge
  imports nothing from `scripts.ohf.*`.
- No corpus content changes, no E1 preregistration, no merge/ready/label
  action, no Slack/Linear.
- No canonical R0 scenario document for the OHF1 MAS-136 `S2/S6/S7/S8`
  family. That scenario-authoring work is out of scope here (§5).

## 2. Frozen OHF F0 artifact/manifest format (as data, from PR #162 @ `478ca1f5`)

Read directly from `scripts/ohf/fresh_sol_eval.py` on the PR #162 branch,
never imported. Two frozen constants copied here as literal data (§6
explains why literal copy, not import):

**Manifest** (`MANIFEST.json`, schema `mastermind.fresh_sol_eval_manifest/v1`):

```json
{"schema": "mastermind.fresh_sol_eval_manifest/v1",
 "entries": [{"run_id": "...", "arm": "...", "scenario_id": "...",
              "relative_path": "runs/<arm>/<scenario_id>/<run_id>.md",
              "artifact_sha256": "<64-hex, sha256 of the artifact's own bytes>"}]}
```

**Run artifact** (`runs/<arm>/<scenario_id>/<run_id>.md`, schema
`mastermind.fresh_sol_eval_run/v1`): a YAML frontmatter block (26 closed
fields, `fresh_sol_eval.py::_EVIDENCE_METADATA_KEYS`) followed by two
fenced Markdown sections, `## Exact prompt` and `## Exact model output`,
each wrapped in a backtick fence at least one character longer than the
longest backtick run inside the fenced text (`_fence_for`, so the fenced
content can never forge its own closing fence).

Frontmatter fields: `schema, scenario_id, arm, run_id,
procedure_commit_sha, expected_skillpack_version, procedure_source_blobs
(list), procedure_context_sha256, protocol_sha256, prompt_sha256,
model_requested, model_served, harness_kind, harness_version,
harness_binary_sha256, provider_auth_type, provider_plan_type,
requires_openai_auth (bool|null), process_pid (int), process_pgid
(int|null), process_start_identity, native_thread_id, started_at,
completed_at (both `%Y-%m-%dT%H:%M:%S.%fZ`, fractional seconds),
cleanup_proof (string `"<termination_outcome>/private_group_empty=<bool>"`),
manual_classification`.

The two frozen Skillpack arms (`fresh_sol_eval.py::MAS136_ARMS`), copied
here as literal data (§6):

| OHF arm name | commit_sha | skillpack_version |
|---|---|---|
| `control-1.0.0` | `51f9942733b86e550bb9169d2a43462bd28e774f` | `1.0.0` |
| `amended-1.1.0` | `8209e1f31da15f8effc23a9899a5c5a02d30cab4` | `1.1.0` |

## 3. Structural invariants this bridge relies on (not literal fields)

OHF F0's *code* (not its persisted artifact) guarantees several things the
artifact never states as an explicit boolean. This bridge treats them as
**documented inferences**, named individually so a future OHF wave that
starts emitting a literal field can replace the inference without anyone
having to rediscover why the value was assumed:

- **Freshness.** `_prepare_run_root` refuses if the run root already
  exists, and a fresh App Server process/thread is started per run — so
  every persisted OHF artifact implies `fresh_process_observed =
  fresh_workspace_observed = fresh_session_observed = True` and
  `resume_used = False`. OHF F0 has no checkpoint/resume path.
- **Cleanup.** `_terminate_and_prove` *raises* `CLEANUP_UNPROVEN` before
  `write_run_artifact` is ever reached if the private process group is
  not proven empty — so a persisted artifact's cleanup was structurally
  proven. This bridge does **not** trust that inference blindly: it
  parses the literal `private_group_empty=` boolean back out of the
  `cleanup_proof` string and fails closed (`OHF_CLEANUP_PROOF_NOT_EMPTY`)
  if it is not exactly `True`, rather than assuming PROVEN from the mere
  fact that the file exists.
- **Completion.** OHF F0 has no partial/failed-run persistence path today
  (a `FreshSolEvalError` aborts before `write_run_artifact`), so every
  bridged run maps to `completion_status = COMPLETED`,
  `termination_reason = COMPLETED_NORMALLY`. A future OHF wave that
  persists partial/failed runs needs this bridge extended, not silently
  reinterpreted.

## 4. Exact mapping table

`OHF -> R0` unless marked. "Caller-supplied" fields are ones OHF's
persisted artifact does not carry at all; the bridge requires them
explicitly rather than inventing a value.

| R0 field | Source | Note |
|---|---|---|
| `run_id` | `run:<canonical dashed str of frontmatter.run_id>` | **Review repair BLOCKER-1 (post-merge correction):** the real harness emits `uuid.uuid4().hex` -- 32 lower-case hex characters, NO dashes -- never the dashed canonical string form this record originally assumed. Accepted shape is exactly `^[0-9a-f]{32}$`; normalized via `uuid.UUID(hex=...)`, version required `== 4`; the canonical **dashed** `str()` of that UUID is what R0's own `run_id` grammar expects and is what this bridge uses downstream (digest inputs, the `run:<uuid>` field). Fails closed (`OHF_RUN_ID_NOT_UUID4`) on any other shape, including a syntactically dashed uuid string (OHF F0 never emits one) or a valid-looking 32-hex value whose version nibble isn't 4. Confirmed against a real harness-written fixture (§9/MAJOR-2): its `run_id` is `1cdaa1b19b584d50ba012dc3910637eb`. |
| `scenario.*` | caller-supplied `scenario` document | Bridge asserts `frontmatter.scenario_id == expected_ohf_scenario_code` when the caller passes that check value (§5). |
| `configuration.*` | caller-supplied `configuration` document | Built via `build_ohf_arm_configuration_fields` (§4.1) or supplied directly. |
| `comparison.arm_id` | `slugify(frontmatter.arm)` | `.` -> `-` (R0 `arm_id` grammar forbids `.`; `control-1.0.0` -> `control-1-0-0`). Caller still names the experiment/arm/pair/replicate explicitly — the bridge does not invent experiment membership. |
| `execution.runner_id` | constant `mastermind.eval_ohf_bridge.v1` | |
| `execution.runner_code_ref` | caller-supplied | The bridge cannot know its own future merge SHA; caller supplies the source-qualified ref (§6 seam). |
| `execution.execution_surface`, `execution_surface_version`, `provider`, `model_requested`, `reasoning_effort` | copied from `configuration.execution` | OHF's frontmatter does not independently re-report these; copying from configuration matches how `procedure`/`context`/`randomness` are required to equal configuration verbatim (validity §7.6 `CONFIGURATION_FIELD_MISMATCH`). |
| `execution.model_served` | `frontmatter.model_served` | Genuinely observed; a real mismatch against `configuration.execution.model_requested` correctly produces `MODEL_SERVED_MISMATCH` through the existing finalizer, unmodified. |
| `execution.auth_realm_class` | `frontmatter.provider_auth_type` uppercased | Genuinely observed (not copied), so a real drift from the configured realm correctly flows into `CONFIGURATION_FIELD_MISMATCH`. Fails closed (`OHF_AUTH_REALM_UNMAPPABLE`) if the uppercased value doesn't match the closed auth-realm-class shape. |
| `execution.process_fingerprint` | `digest_value({process_pid, process_pgid, process_start_identity})` | |
| `execution.native_session_fingerprint` | `digest_value({native_thread_id, run_id})` | |
| `execution.completion_status`, `termination_reason` | constants (§3) | |
| `execution.fresh_*_observed`, `resume_used` | constants (§3) | |
| `procedure.*` | copied verbatim from `configuration.procedure` | Required equal to configuration by validity law regardless. Bridge additionally cross-checks `configuration.procedure.instruction_bundle.digest == digest_value({procedure_source_blobs, procedure_context_sha256})` before proceeding — a real mismatch here means the configuration document does not actually describe what OHF ran, so it fails closed (`OHF_PROCEDURE_BINDING_MISMATCH`) rather than silently publishing a run bound to the wrong configuration. |
| `context.*` | copied verbatim from `configuration.context` | Same equality law as `procedure`. |
| `context.source_policy_digest` | `digest_value(scenario.source_policy)` | Computed the same way the finalizer itself expects (matches `validity._gather_reason_codes`'s own recomputation). |
| `observations.observed_sources` | **caller-supplied, required** | **Genuine gap (§5.1).** OHF F0's persisted artifact records no file-level "what did the model read" evidence stream at all. **Review repair MAJOR-3:** an EMPTY `observed_sources` now requires the caller to pass `observations_are_absent=True` -- `build_run_draft_from_ohf` refuses (`OHF_OBSERVATION_FIELD_REQUIRED`) otherwise. Acknowledging records `OHF_NO_SOURCE_OBSERVATION_DEGRADATION` (`"OHF_F0_NO_SOURCE_OBSERVATION_STREAM"`) in `observations.dependency_degradations`, so the absence lives ON the artifact rather than silently and invisibly satisfying R0's leakage checks. See §5.3 for the resulting-state report. |
| `observations.observed_capability_ids`, `observed_tool_schema_digests` | **caller-supplied, required** | **Genuine gap (§5.1):** `CapabilityReceipt.mcp_names/plugin_names/skill_names` exist only transiently during the OHF run and are never written into `_EVIDENCE_METADATA_KEYS`. Default `()` is explicit, never silent. |
| `observations.observed_network_destinations` | `()` (structural default) | OHF F0's capability policy structurally asserts zero MCP/plugin names (`_assert_empty_capability_surface`) before any turn runs, so no externally-callable network surface exists to observe from. Documented inference, not a literal field; overridable by the caller. |
| `observations.dependency_degradations` | `()` (structural default) | OHF F0 has no degradation-reporting path. Overridable by the caller. |
| `capabilities.profile_id`, `profile_digest`, `sandbox_digest`, `network_policy_digest`, `environment_digest` | copied from `configuration.capabilities` | Required equal to configuration by validity law. |
| `capabilities.workspace_digest` | `digest_value({run_id, process_start_identity})` | Per-run, no drift check against configuration (by design — every run gets a fresh workspace). |
| `randomness.*` | copied verbatim from `configuration.randomness` | |
| `effect.state` | `NO_EFFECT` (constant) | OHF F0's scenario/capability policy is read-only/no-effect by construction for MAS-136; `operation_ref`/`reconciliation_ref` null. |
| `cleanup.status` | `PROVEN` iff parsed `private_group_empty == True` | See §3; fails closed otherwise. |
| `cleanup.proof` | `{artifact_ref: "<ohf_artifact_ref>#cleanup_proof", digest: digest_value(cleanup_proof string)}` | |
| `evidence.output` | `{artifact_ref: ohf_artifact_ref, digest: sha256:<sha256 of the parsed output text>}` | Independently recomputed from the fenced "Exact model output" section, not trusted from any stored digest (OHF does not persist an output digest). |
| `evidence.tool_events` | **placeholder, documented (§5.2)** | `{artifact_ref: "<ohf_artifact_ref>#capability_attestation", digest: digest_value({ohf_f0_tool_events_not_emitted: true, run_id})}`. **Not real observed evidence** — OHF F0 persists no distinct tool-call event log. Flagged loudly, not hidden. |
| `evidence.trace` | `None` | OHF F0 persists no trace stream. |
| `evidence.artifacts` | `[]` | |
| `resources.*` | `input_tokens/output_tokens/tool_calls/provider_usage_ref/estimated_marginal_cost/cost_currency = None`; `elapsed_ms` = computed duration | OHF F0's frontmatter carries none of the token/cost fields; explicit null, never fabricated zero (design §8.1). |
| `timing.started_at`/`completed_at` | `frontmatter.started_at`/`completed_at` truncated to whole seconds | R0's `v_timestamp` requires strict whole-second `...SSZ`; OHF emits fractional-second timestamps. Truncated (never rounded) for determinism; the precise fractional delta is preserved in `monotonic_duration_ms`/`resources.elapsed_ms` before truncation. **Review repair NB-6:** for a sub-second-duration run, truncation can collapse `started_at == completed_at` in the stored R0 document even though `monotonic_duration_ms`/`resources.elapsed_ms` are nonzero (computed from the untruncated fractional values) -- this is not a validation defect (R0's own time-order check only requires `started_at <= completed_at`, and the duration/elapsed-ms cross-check compares those two fields to each other, not to the truncated boundary timestamps), but a reader should not infer "zero duration" from equal whole-second boundaries; the nonzero `monotonic_duration_ms` is the accurate signal. |
| `timing.monotonic_duration_ms` | `round((completed - started).total_seconds() * 1000)` computed from the **fractional** timestamps | Set equal to `resources.elapsed_ms` so the cross-field `DURATION_ELAPSED_MISMATCH` check is trivially satisfied. |

Fields with no R0 home (observed but genuinely unmapped, dropped from the
R0 document, not silently discarded from this record):
`protocol_sha256`, `harness_kind`, `harness_version`,
`harness_binary_sha256`, `provider_plan_type`, `requires_openai_auth`,
`manual_classification`. None of these have a corresponding closed R0
field; a future R0 amendment could add one.

### 4.1 Configuration builder for the two frozen arms

`build_ohf_arm_configuration_fields(arm_name, *, configuration_id,
instruction_bundle, context_packet, ..., created_at)` fills
`procedure.skillpack_source_ref`/`skillpack_version` from the frozen table
in §2 and leaves everything else (execution surface/provider/reasoning
effort, capability declarations, randomness, authorship) to the caller —
a configuration is scenario/experiment-specific input, not something this
bridge can synthesize from the arm name alone (design §7.2: "Configuration
cannot assert capacity, route suitability, policy, authority...").

## 5. Scenario binding and known gaps

### 5.1 Scenario-agnostic by design

OHF1's MAS-136 family (`S2`, `S6`, `S7`, `S8`) has **no** canonical R0
scenario document yet — it is a distinct family from C0's three `TC*`
classes, and authoring MAS-136 scenario documents (source allowlists,
capability policy, effect policy, scoring policy) is real scenario-design
work, not adapter work. `build_run_draft_from_ohf` therefore takes the R0
`scenario`/`configuration`/`experiment` documents as **required
parameters** — it never derives or invents a scenario from an OHF
`scenario_id` string. When the caller wants a hard binding check (e.g. "I
expect this artifact to be OHF's `S2`"), it passes
`expected_ohf_scenario_code`, and the bridge fails closed
(`OHF_SCENARIO_CODE_MISMATCH`) on any other value. This wave proves the
whole pipeline with one synthetic scenario document (`tests/`); a later
wave (or the C0 corpus mechanism) is the right place to author real
MAS-136 scenario documents.

### 5.2 The `evidence.tool_events` placeholder is a real, disclosed gap

R0's `evidence.tool_events` field is required (not optional — only
`trace` is optional in the run schema). OHF F0 has no tool-call event
stream in its persisted artifact. Rather than reuse the output digest
under a misleading label, or block the whole bridge on inventing evidence
that does not exist, the bridge writes an explicitly self-describing
placeholder value (`ohf_f0_tool_events_not_emitted: true`) with an
`artifact_ref` suffix (`#capability_attestation`) that names what part of
the OHF artifact it actually corresponds to. This is disclosed here, in
the module docstring, and in `KNOWN_LIMITATIONS`; it is **not** claimed as
observed tool-call evidence anywhere in code or documentation. A future
OHF wave that persists a real tool-events log should replace this
placeholder wholesale — it is a single named constant/function.

### 5.3 `observed_sources` absence must be acknowledged, not silently vacuous (review repair MAJOR-3)

Because `observations.observed_sources` has no OHF-native source, R0's
leakage reasons (`UNAUTHORIZED_SOURCE`, `SOURCE_DIGEST_MISMATCH`,
`HIDDEN_SOLUTION_SOURCE`) would be **vacuously satisfied** for a bridged
run with an empty `observed_sources` -- the review's finding was that this
produced an *unearned* `source_integrity` `PASS` from S1's
`technical_integrity` scorer with no real observation behind it.

**Repair:** `build_run_draft_from_ohf` now REFUSES
(`OHF_OBSERVATION_FIELD_REQUIRED`) an empty `observed_sources` unless the
caller passes `observations_are_absent=True`. Acknowledging records
`OHF_NO_SOURCE_OBSERVATION_DEGRADATION`
(`"OHF_F0_NO_SOURCE_OBSERVATION_STREAM"`) in the run's own
`observations.dependency_degradations` -- the gap lives ON the artifact,
visible to every downstream reader (scorer, evidence-ref summary, tree
verification), rather than silently and invisibly satisfying the leakage
checks.

**Resulting state, reported honestly (not special-cased):** whichever
technical-validity status R0's own unmodified validity engine computes is
the outcome this bridge accepts. Tested (`tests/test_agent_eval_ohf_bridge.py::
test_major3_resulting_state_is_degraded_dependency_not_special_cased`)
against a scenario that explicitly allows the degradation: the result is
`DEGRADED_DEPENDENCY` (not `VALID` -- the run correctly stays OUT of the
`VALID` bucket), and the run remains fully visible in evidence-ref
denominators (`degraded_count`, never folded into `valid_count`). A
scenario that does NOT allow the degradation would instead correctly
produce `INVALID_CONFIGURATION`/`DEGRADATION_NOT_ALLOWED` -- also not
special-cased, just not the path this record's own test scenario
exercises.

**A narrower, disclosed limit inside this fix:** the technical_integrity
scorer's `source_integrity` dimension (owned by EVAL-S1, `scoring.py`,
NOT modified by this wave) derives its PASS/FAIL purely from the run's
`validity.reason_codes`, and `DEGRADED_DEPENDENCY` alone adds no
LEAKAGE-bucket reason code -- so `source_integrity` still evaluates
`PASS` even on a `DEGRADED_DEPENDENCY` run with an empty
`observed_sources`. This is reported explicitly, pinned by the same test
above, not hidden: the RUN's own technical-validity status is no longer
unearned (that was the review's actual finding), but S1's existing
scorer dimension is a separate, narrower gap this wave does not own and
does not silently patch. `observed_capability_ids`/
`observed_tool_schema_digests` still default to empty with no separate
acknowledgment gate -- that narrower gap was out of scope for this
repair wave.

## 6. The #162-merge-gated seam

`ohf_bridge.py` imports nothing from `scripts.ohf.*` (verified by the
same AST fence R0 already runs, §7). The two facts this bridge needs from
OHF F0 — the frozen Skillpack arm table (§2) and the exact frontmatter
field set/artifact layout — are copied here as **literal data** with a
comment at each copy site naming the exact source (`fresh_sol_eval.py`
line reference at time of writing, PR #162 @ `478ca1f5`) and stating: once
#162 merges, a follow-up wave should replace the literal
`OHF_SKILLPACK_ARMS` table with `from scripts.ohf.fresh_sol_eval import
MAS136_ARMS` (converting the `SkillpackArm` dataclass tuples into this
module's own tuple shape) to eliminate drift risk between the two copies.
That follow-up is intentionally **not** done here — importing an unmerged
module is out of scope (OUT OF SCOPE, packet) and would break the moment
#162's branch is rebased or the shas change during its own review.

## 7. Test-driven implementation (`tests/test_agent_eval_ohf_bridge.py`)

RED-first, in this order:

1. **Frontmatter/section parsing** — a synthetic OHF artifact string
   (built to the exact §2 shape) parses to the expected frontmatter dict,
   prompt text, and output text; a malformed/missing field fails closed
   with a typed `OhfBridgeError`.
2. **Manifest tamper detection** — a manifest entry whose
   `artifact_sha256` does not match the actual artifact bytes is refused
   (`OHF_ARTIFACT_DIGEST_TAMPERED`) before any parsing happens; a missing
   manifest entry for the requested `run_id` is refused
   (`OHF_MANIFEST_ENTRY_MISSING`).
3. **Full fake journey** — synthetic OHF artifact + manifest -> bridge ->
   `finalize_run_receipt` -> a real `ArtifactStore.create()` -> readback
   -> `VALID`. Both arms represented; two-arm experiment; append the
   `technical_integrity` scorer pass per run; `scoring.summarize_experiment`
   + `store.create()` publishes an evidence ref; `store.verify_tree_graph()`
   reports zero defects.
4. **Served-model mismatch** — a second synthetic artifact with
   `model_served != configuration.execution.model_requested` bridges to
   `INVALID_CONFIGURATION` / `MODEL_SERVED_MISMATCH`, preserved (not
   dropped) through finalize + store + evidence-ref summarization.
5. **Fail-closed paths** — tampered digest (2); cleanup not proven
   (`private_group_empty=False` in the artifact text); unparseable
   `run_id`; scenario-code mismatch; auth-realm shape violation;
   procedure-binding digest mismatch. One test per named `OhfBridgeError`
   code.
6. **Scorer pass appends without run mutation** — reuses S1's
   `build_technical_integrity_scorer_pass` unmodified against a bridged
   run; run bytes are unchanged after appending.
7. Full suite: `pytest -q tests/test_agent_eval_*.py
   tests/test_agent_eval_ohf_bridge.py`; `python -m compileall
   scripts/agent_eval`; corpus-verify still `CONSISTENT`.

## 8. Fence ratchet

Adds exactly three paths to `tests/test_agent_eval_inertness.py`'s
`ALLOWED_PATHS` (principal-authorized under this operation key):

```text
docs/superpowers/plans/2026-09-01-agent-evaluation-ohf2-integration.md
scripts/agent_eval/ohf_bridge.py
tests/test_agent_eval_ohf_bridge.py
```

**Review repair MAJOR-2 addition:** the harness-written real-bytes fixture
(§9) adds three more exact paths to the same ratchet, under the same
operation key:

```text
tests/fixtures/agent_eval_ohf_bridge/README.md
tests/fixtures/agent_eval_ohf_bridge/MANIFEST.json
tests/fixtures/agent_eval_ohf_bridge/runs/control-1.0.0/S2/1cdaa1b19b584d50ba012dc3910637eb.md
```

`scripts/agent_eval/ohf_bridge.py` also falls under the existing
`scripts/agent_eval/` AST-fence parametrization automatically (no fence
edit needed there) — it is swept by
`test_production_module_imports_no_forbidden_module` /
`test_production_module_never_accesses_forbidden_attribute` /
`test_importing_production_module_has_no_observable_side_effect` the
moment the file exists on disk.

## 9. Honest capability claim

`BUILT_SYNTHETIC_PROVEN / PRODUCTION_INERT / RUNNER_SEAM_HELD_ON_162`:

- **BUILT_SYNTHETIC_PROVEN** — the adapter is fully implemented and the
  complete OHF-artifact -> R0-run-receipt -> store -> scorer -> evidence-ref
  pipeline is proven end-to-end, including every fail-closed path this
  record names. Proven against BOTH: (a) synthetic, hand-rendered OHF
  artifacts built to the exact §2 documented format (the majority of
  `tests/test_agent_eval_ohf_bridge.py`), used because they let each
  fail-closed path be tested with one deliberately-broken field in
  isolation; and (b) **review repair MAJOR-2** — one REAL harness-written
  artifact + manifest, produced by calling PR #162's own
  `write_run_artifact()` directly (real `yaml.safe_dump`, real backtick
  fencing, real manifest bookkeeping; no live App Server or provider
  call), committed verbatim under
  `tests/fixtures/agent_eval_ohf_bridge/` and bridged end-to-end by
  `test_bridges_harness_written_real_bytes_fixture_end_to_end`. The
  hand-rendered fixtures remain supplementary evidence for the isolated
  fail-closed paths; they are no longer the ONLY evidence the parser
  matches the harness's real byte shape.
- **PRODUCTION_INERT** — `ohf_bridge.py` performs no network, process,
  provider, or credential operation; verified by the same AST/subprocess
  inertness fence R0 already runs (§8). It has never run against a real
  OHF live-canary artifact (a genuine fresh-Sol turn) because none exists
  yet (OHF1's canary is parked pending a human go/no-go) — MAJOR-2's
  fixture proves the SERIALIZATION format, not a live model turn.
  - The frontmatter parser IS now cross-checked against one real
    `yaml.safe_dump` byte stream (MAJOR-2's fixture) — this record no
    longer makes a "byte-for-byte, never checked against real output"
    claim. What remains open: that ONE fixture does not exercise every
    possible value shape PyYAML could quote/fold across the full field
    set (e.g. a `harness_version` PyYAML would need to quote as a
    float-ambiguous string); the closest such case found during this
    repair — a long, space-containing `procedure_source_blobs` value
    that PyYAML line-folds past its default 80-column width — was tested
    directly against real `yaml.safe_dump` output too (§7 item 7a
    regression) and confirmed to fail closed correctly, but a follow-up
    wave should still feed a WIDER range of real (or OHF-team-produced)
    artifact shapes through the parser before the pipeline is trusted
    unconditionally against live output.
- **RUNNER_SEAM_HELD_ON_162** — the bridge cannot be exercised against a
  real fresh-Sol run until PR #162 merges and its canary is approved. The
  seam (§6) is the only work remaining once that happens.

## 10. Non-goals (repeated for the PR body)

No live turns. No modification to PR #162 or `scripts/ohf/**`. No second
runner. No E1 preregistration. No corpus content changes. No merge/ready/
label action. No Slack/Linear posting.

## 11. Review repair log (principal adjudication, 2026-09-01)

A review of the first PR revision found one blocker, two majors, and
several minor/nit items, all addressed in a follow-up commit on the same
branch (`EVAL-OHF2: review repair —` prefix). Summary (detail lives at
each item's own section above):

| Item | Fix | Where |
|---|---|---|
| BLOCKER-1 | Accept the real harness's `uuid.uuid4().hex` (32-hex, no dashes) `run_id` shape, not dashed-only | §4 `run_id` row |
| MAJOR-2 | Committed one REAL harness-written artifact+manifest fixture; bridged end-to-end | §9, `tests/fixtures/agent_eval_ohf_bridge/` |
| MAJOR-3 | `observed_sources` absence now requires explicit acknowledgment, recorded as a dependency degradation on the run itself | §5.3 |
| NB-4 | Duplicate frontmatter keys, inline `[]` list form, and a second injected output section all fail closed; `build_run_draft_from_ohf`/`finalize_and_publish_ohf_run` take `artifact_bytes`+`manifest` directly (structural tamper check, not a separate conventional step) | `ohf_bridge.py` parsing + function signatures |
| NB-5 | Manifest entry identity (`run_id`/`arm`/`scenario_id`) cross-checked against the artifact's own frontmatter, reusing `OHF_ARTIFACT_DIGEST_TAMPERED` | `ohf_bridge._verify_manifest_frontmatter_identity` |
| NB-6 | Disclosed that whole-second timestamp truncation can collapse `started_at == completed_at` alongside nonzero `monotonic_duration_ms` | §4 timing row |
| 7a | Confirmed (with real `yaml.safe_dump`) that a YAML-folded long `procedure_source_blobs` item already fails closed; pinned as a regression | `tests/test_agent_eval_ohf_bridge.py::test_yaml_folded_list_item_fails_closed_regression` |
| 7b | Inline empty-list form (`key: []`) now refused rather than misread as a literal string | `ohf_bridge._parse_ohf_frontmatter` |
