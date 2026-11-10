# Session Truth R1 — current-estate proof after bounded acquisition repair

Operation: `session-truth-r1-current-estate-budget120-proof-20260905-runtime-continuity-001`.
Owner: SOL-RUNTIME-CONTINUITY, native task `01a06f73-1dba-7951-9f1e-cded7b563cef`.

## Result and exact scope

The two real canonical receipt CLI calls succeeded in **90.618 seconds** and **92.672 seconds**, using the reviewed source default of 120 seconds per Agent OS subprocess, with no proof-time override. Their semantic projections are byte-identical and independently rebuild to:

`sha256:f172b639c650a682915e55dd0bf318506127f3a9ddd422e7a5a1b269410a3f9b`

The caller clocks were `2026-09-05T03:45:09Z` and `2026-09-06T04:45:09Z`. The 25-hour difference is an explicit clock input, not a claim that 25 hours elapsed between executions. Full receipts differ in their observation envelopes and Agent OS generated/age fields; the semantic projections do not.

This proves the frozen R1 boundary: receipt-envelope and digest-backed Agent OS acquisition clocks do not change semantic identity when authored records and sealed external source revisions remain fixed. The five external snapshots were freshly read and sealed at `2026-09-05T03:45:09Z`, then reused. Their `observed_at` values remain semantic source revisions under the existing contract and `test_source_revision_change_changes_semantic_hash`. This is not proof that independently refreshing external snapshots at new timestamps preserves a hash.

## Immutable source and integration pins

| Item | Identity |
|---|---|
| Protected Mastermind / same-SHA Skillpack | `0cdcd1ef260a23cc127b0998c4e455c9d8f5aa06` |
| Protected tree | `f21f5ee9d4c2ccd92b3db9893947a2d65574e982` |
| Reviewed source head, PR #170 | `8e6ccc3e893e8ab080ead0bb3e6054d98bf82ed0` |
| Source-head tree | `ad06e393e972718c49fc8fd32a54d4564380d422` |
| GitHub merge ref, parents protected + source head | `ec2b7989285421058f064cc3bb47a8604ecec6de` |
| Tested integration tree | `be668861a6c13978ddcf0b642fa7b13f26280c20` |
| Local detached integration commit, same parents/tree | `088f5cb0f494dd98a3c5fff7709c02a4e38763ea` |
| Current Macro read-root HEAD | `63fee292a9938664899284796e58926f13b8ed9e` |
| Macro tree | `0557ec0cbff53169a7fc2f632ef0d3bcc6cbdfb0` |
| Protected Macro digest producer merge | `348b9a683241a54f842bc9838f5a84171915a5fe` |

The source change consists of the 120-second default plus regressions in three existing paths. Independent source review approved that head. All **236 focused tests** passed on both the candidate and the current protected integration tree. A separate reviewer reran the 25 acquisition/CLI tests successfully. GitHub's fetched merge tree exactly equals the locally tested integration tree; no ancestry-only integration claim is used.

## Real observations and unavailable sources

The exact argument vectors, exit status, elapsed wall time, stderr and stdout hashes are in `run_log.json`. `receipt_clock_1.json` and `receipt_clock_2.json` are the actual CLI stdout. Stored projections and `comparison.json` were independently recomputed from those receipts.

Both receipts report **DIALOGUE_ONLY / modification_safe=false**. Missing completion-owner evidence for MAS-228 and Mastermind PR #169 remains blocking; PR #170's missing binding metadata and the historical Slack watcher return without an ACK remain visible warnings. The detector was not made green by changing owner facts.

The Executive connector currently exposes a fixture checkout with an absent fixture database. That does not prove the protected production database absent. The production read path remains unavailable. Executive and identity snapshots therefore retain explicit unavailable reasons; no account, current writer, RuntimeBinding or production state was guessed.

`required_executive_counterfactual.json` is a derived check using Clock 1's exact acquired inputs with only `scope.requires_executive=true`. It adds `RUNTIME_STATE_UNAVAILABLE` and required-unavailable `executive`, retaining `modification_safe=false`. It is not a third real acquisition.

## Authored record sensitivity

A third real CLI read completed in **93.764 seconds** against actual committed Macro source `bd862eedb854474b80b82303b1788d0c6fea0fbc`, the parent of authored-record commit `fe75dfe2cc834beb86ae5af0ee5811971a27f7aa`. The canonical `scripts/agentos.py` bytes are identical to the current read root. The only Agent OS changes between those states are:

- `agentos/decisions/DEC-MARKET-ONTOLOGY-F04-EXPLORER-LIVE-TRACE-SCENARIO-BOUNDARY.md`
- `agentos/handoffs/MARKET-ONTOLOGY-F04-EXPLORER-F00-RETURN-RECONCILIATION-2026-09-04.md`
- `agentos/handoffs/MARKET-ONTOLOGY-F04-EXPLORER-FABLE-COO-2026-09-04.md`

No authored records were edited for the test. The isolated Macro read worktree was checked out at the historical commit for acquisition, then restored cleanly to the current pin.

The global owner digest changed from `sha256:ab8bbea151415668a737c088c6debcfea3497eee9c530a8e3c07f97ea2a482b0` to `sha256:b0fbe9930ac9d4d992264bfb86bf373b0ceca0b8ed4eaf6e731cb0968c630b25`. The scoped Chairman Control Room context digest remained `sha256:ffdb73f0d0448f728f2d511a61e7b2ebc8ee1e181b28e226378f5750e8d14cb0`, as expected for unrelated authored records.

The historical semantic hash differs from the current hash. Because the Git source SHA also differs, `authored_record_delta_comparison.json` additionally records a derived control that replaces only the historical input's source SHA with the current SHA. Its hash still differs. This control is explicitly derived; it is not presented as another live acquisition.

## Review and release boundary

The independent evidence reviewer verified canonical JSON, stdout hashes, exact receipt rebuilds, independently recomputed projections, unchanged admission, explicit unavailable-source behavior, and the frozen clock boundary. Its subsequent authored-delta review confirmed that the source-SHA-controlled semantic projections differ at exactly one leaf: `/observations/agentos/state/source_records_digest`. Immutable evidence sealing, concluded checks on the final PR head, and Sol's explicit release remain separate gates.

At proof acquisition, PR #170 remained OPEN / DRAFT / HOLD. CI run `33942631173` was in progress; CodeQL run `33942629526` later passed. Pending CI is not a pass, and this file does not claim release, merge, host installation, Wake delivery, target acknowledgement, source resolution, provider execution or Worker-to-Sol-to-Worker continuity.

The prior failed six-artifact proof directory and two foreign census changes remain untouched. Only this new evidence directory belongs to this proof operation. The source repair and evidence are part of the existing PR #170 carrier; no replacement branch, PR, task, parser, store, watcher or runtime authority was created.
