**REQUEST_CHANGES — three P2 findings on the frozen source.**

HEAD remains `b9a70ff85ea122f330675ad7fd3f80a2391c133b`. All three supplied SHA-256 digests matched at the beginning and end of this review. Findings below concern those working-tree bytes, not a newly committed or installed release.

1. **[P2] Attended physical-identity checks are skipped for actual SQLite rows.**
   [control_plane/executive_runtime.py:1181](./control_plane/executive_runtime.py:1181)

   `row_key in row` tests **values**, not column names, for `sqlite3.Row`. Consequently, the new attended checks normally skip every physical field. A read-only probe using the exact matcher definitions and genuine SQLite `SELECT` rows returned `True` after independently changing `worker_provider` to `codex` and `worker_type` to `codex-cli`, while retaining the synthetic attended route.

   The surrounding filters check quota provider/model/effort/cost, but do not check worker type; worker/quota-provider agreement is additionally checked only for orchestration Jobs. Thus the physical mismatch can survive capacity selection, with the legacy role-null claim path also lacking that provider cross-check. Downstream launch protections do not repair the incorrect claim decision.

   **Repair:** require all six physical columns and compare them unconditionally, refusing missing keys. Merely changing this to `row_key in row.keys()` would still silently accept missing columns. Cover real SQLite rows, independently mismatched worker and quota providers, wrong worker type, and missing physical fields.

2. **[P2] The new CLI policy argument breaks six existing subcommands.**
   [scripts/executive_os_phase1b.py:267](./scripts/executive_os_phase1b.py:267)

   `Runtime.at(..., routing_policy_path=args.routing_policy)` executes for every command except `route`, but `workers`, `jobs`, `attempts`, `events`, `run-once`, and `reconcile` never define that attribute. A parser-only probe confirmed `hasattr(args, "routing_policy") == False` for all six. Each therefore raises an uncaught `AttributeError` before opening the runtime or performing its intended operation.

   This also means the CLI currently provides no working custom-policy claim path: `run-once` neither defines nor accepts `--routing-policy`.

   **Repair:** supply a common default for commands without policy selection, and expose the host policy option on the command that actually claims work. Verify the existing inspection commands and custom-policy create/register → `run-once` argument plumbing.

3. **[P2] The attended early return bypasses existing quota-metadata closure.**
   [control_plane/executive_runtime.py:1185](./control_plane/executive_runtime.py:1185)

   The attended branch validates the nested `metadata["attended_route"]` and Job constraints, then returns before checking the quota’s outer alias, routing version, and execution-profile metadata. Independent read-only probes retained a matching nested route while changing outer `execution_profile_digest`, `model_alias`, `routing_policy_version`, or `adapter_id`; every case returned `True`.

   This is separate from finding 1: it persists after fixing physical-column access. A contradictory profile can pass claim selection and then fail the supervisor’s existing metadata validation at [executive_supervisor.py:1833](./control_plane/executive_supervisor.py:1833), unnecessarily consuming an attempt. A contradictory outer alias also feeds the claim’s `selected_model_alias` receipt.

   **Repair:** preserve alias, routing-version, and complete profile/policy agreement before the attended return. Apply the intended optional-redundancy rule to provider/adapter metadata: omission may be accepted where the producer contract permits it, but present contradictory values must refuse.

The prior four P2 areas are therefore **partially resolved**. Runtime/Store construction now carries the host-selected routing path, but the CLI integration regresses. Attended positive matching uses the incumbent normalizer, but physical and metadata checks remain defective. The autonomous branch correctly accommodates the existing `external_pool_binding` producer’s omitted redundant fields while rejecting contradictions. Autonomous scans also reuse one standard `ModelRouter` object and perform one final reload when candidates exist, eliminating per-row policy reloads.

The remaining scope limits are material:

- **Legacy generic Jobs:** the no-alias/no-profile path deliberately retains its historical behavior. This patch is not a universal provider-identity fence for every Job.
- **Policy freshness:** the second read detects changes visible between the two snapshots. It does not make filesystem policy and SQLite mutation atomic: policy can change after [the final check at line 16491](./control_plane/executive_runtime.py:16491), before mutation/commit, or after the transaction. Immediate routing-policy revocation through launch is not established here.
- **Host provenance and privilege:** the path enters through host construction, not normalized Job or worker metadata. `resolve(strict=True)` establishes path existence/canonicalization, not privileged ownership or immutability; those remain host/release obligations. `normalize_attended_route` likewise validates retained identity, not current attendance or live admission.

I ran no pytest, wrote no tests or files, opened no Executive store, and used no credentials, network, provider access, or child delegation. Evidence consists of source tracing, parser-only and synthetic in-memory probes, matching hashes, and a clean `git diff --check`. The reported 79 passes remain supplied evidence; broader results were not independently verified. Earlier denied Supervisor-reader and Bot-snapshot edits remain **NOT_APPLIED**. This review establishes no installed upgrade, heterogeneous live-provider admission, true served-model origin, or billing verification.
