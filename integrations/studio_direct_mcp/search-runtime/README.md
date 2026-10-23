# #1027 bounded search candidate — deadline/admission qualification

This draft extends the existing Desktop Commander search owner. It preserves mihailt's PR768/PR779 composition and MIT attribution. It is **source-qualified, not installed and not a complete #1027 release**.

Donor: `wonderwhy-er/DesktopCommanderMCP@56b5127ec6539f1d182ed4c3ffdeb114cf6bfd66`. PR779 already contains PR768 `7cc1ff30646ef294cee4a1daa04470c27aebea30`; do not cherry-pick it again. License: `LICENSE.upstream`.

## Reproduce

Use Node/npm, Python 3, patch and existing ripgrep on an admitted POSIX execution host. Choose a new disposable evidence directory, not an installed package or Git checkout:

```sh
python3 test_owned_command.py
python3 validate-upstream.py --output /approved/evidence/new-issue1027-build
python3 test_mutations.py --upstream /approved/evidence/new-issue1027-build/upstream
```

The recipe materializes bounded build inputs from the pinned archive, verifies donor blobs, applies the seven-file patch, installs locked dependencies with lifecycle scripts disabled, builds the actual upstream package, and runs twelve suites. The upstream runner isolates configuration/home and disables telemetry. Each build/test command has its own POSIX session/process group and finite timeout, TERM/KILL teardown and observed empty-group settlement. A successful direct process with lingering children is an error. This does not supervise programs that deliberately escape their owned session.

No installed setting, account permission, credential or service is changed. The patch preserves original unified-diff whitespace; its local Git attribute applies only to this byte-pinned artifact.

## Candidate behavior

V3's finite budgets and Worker isolation remain: 100 default/500 maximum matches; 15-second maximum/default deadline (1.5 seconds for exact filenames); context/output/retained-text limits; exact-handle ripgrep escalation; bounded one-record Worker IPC; actual exit before completion.

The new source delta adds:

- Deadline reservation before path validation, binary resolution, stat and spawn acknowledgement. Expired asynchronous preflight cannot later spawn. Pending preflight still consumes its permit until actual settlement.
- At most two preparing/live searches per existing backend-local SearchManager. Completion/cancellation releases a permit only after owned sources settle.
- Identical normalized live requests reuse their existing promise/native handle. The effective `earlyTermination` value is normalized once: omitted/true share a handle, while false remains distinct and exhaustive. This is exact normalized request deduplication, not semantic equivalence across every filesystem alias.
- At most 32 retained/preparing sessions; excess work is refused without evicting unread handles. Existing cleanup remains the retention owner.
- Broad root refusal before validation and again after canonical path validation: filesystem/home/temp roots, host collections and workspace/repository collections. Narrow fixture/project/file access still uses existing path admission.
- Fixed two-thread ripgrep execution and bounded input strings.
- Typed admission refusal on the existing start handler. Initial responses preserve deadline/result-limit flags and incomplete-result text; later result pages disclose the result cap too.

These guards live in the existing SearchManager, not a separate scheduler, permission plane or result store. They do not grant host-wide Executive admission.

## Evidence and review repairs

`qualification.json` binds the current patch and evidence digests. New execution: full upstream package build; twelve suites with zero skips; 14 deadline/admission/response checks; three validation-owner/identity checks; 16 real Office checks with 17 actual worker exits and zero residual workers/processes; eleven causal mutations; three owned-command tests.

The Office suite now runs against the real compiled upstream dependency graph, rather than the earlier outer-integration stubs. Hard parser-preemption checks still use a bounded two-second injected stall at actual parser match-context entry, not huge resource stress.

ChatGPT3's review of predecessor `aea331f6ad2d3fe50c6a647caa1b307ae835774c` identified two defects. P1 is covered by before-return cap/deadline settlement and text/structured-output assertions. P2 is covered by a harmless TERM-resistant parent/child/grandchild timeout, observed zero survivors, an unaffected sentinel, and failure when children outlive an otherwise successful command. Exact new-head delta review is still required.

The subsequent review of `8118114e75b9f3cf3f8ffc665a38d640312347f0` found that the validation response could time out before the underlying operation settled, releasing admission early, and that the deduplication key disagreed with the effective `earlyTermination` default. Both regressions failed before repair. The existing filesystem validation owner now exposes separate `result` and `settled` promises. Search admission waits for actual validation settlement, including parallel allowed-directory realpath lookups, on both failure and completed-search paths. Existing `validatePath` callers retain the same response and access decisions.

The regression stalls inside the actual compiled validation operation, shortens only the fixture's internal timeout, and proves both permits stay charged, a third request is refused, disposal waits, and no late child is spawned. A second lifetime case covers parallel lookups after a successful answer. Omitted/true requests share one admission and native handle; explicit false uses a distinct exhaustive scan. Upstream allowed-directory and symlink-security suites are included to check preserved access behavior. Four additional causal mutations remove those repairs and are detected.

An uninterruptible native filesystem operation can keep its permit and disposal pending indefinitely. This repair bounds admission and reports caller deadlines; it does not invent cancellation or claim a hard native-I/O settlement deadline.

Prior V3 22 deterministic checks and earlier mutation evidence remain separately attributed to the previous artifact; they are not claimed rerun by this recipe.

## Remaining gates

Host-wide/Executive admission and authenticated operation attribution remain with their existing owners. The backend-local limits do not replace those controls. Worker V8 limits and retained-text accounting do not prove aggregate/native RSS bounds or interruption of arbitrary kernel I/O. The complete upstream suite, required CI, independent delta review and native installed-generation canary remain pending.

Protected REVIEW_RETURN Step 8B permits clean same-PR procedural release when the technical writer gate is unavailable. RULES_ABSENT requires fresh exact-head re-proof and procedural custody; it is not a requirement to change rules or invent fencing. No release authority is claimed by the receipt itself.

The smallest installer dependency is the existing vendor-owner's admitted preimage/update/rollback route for the manifest-pinned Desktop Commander backend. Those installed bytes are outside the observed connector paths. The Studio gateway installer owns account/gateway staging and seals backend identity; it is not the vendor updater. Keep installation held until that route, quiescence, source/review gates and rollback are verified. Do not hot-edit vendor bytes, widen permissions, change credentials/security settings or restart active work.
