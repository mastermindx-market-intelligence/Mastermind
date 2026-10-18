# Mastermind OS Operator Harness — retained activity metadata source leaf

**State:** BUILT_NOT_PROVEN. **Full planning/agent-activity mission complete:** NO.

This slice reuses the existing *canonical* Runtime Operator Harness candidate evidence, not a second event store, transcript stream, provider adapter, auth plane, controller, scheduler or background process. The only new surface is a pure Python function and a strictly limited, source-only in-memory input dataclass. It performs no SQL/HTTP calls, publishes no endpoint and cannot grant a Web/native user access.

**Source base:** protected Mastermind `ef4be2f5c9b0b82fc11be83f03cf7bcdb8cea6f2`; exact implementation head and PR read back after publication.

## What existing owners already prove

- `control_plane.operator_harness_contract.NormalizedEvent` is the incumbent provider-normalized record shape. Codex and Claude adapters produce it; they do not confer Job completion or acceptance.
- `ExecutiveOperatorHarnessPort.finish_operator_candidate` writes through `Runtime.operator_harness.record_candidate_evidence` with existing original lease/fence/intent/APPLIED checks. The canonical resulting `Event` has `aggregate_type=operator_turn`, `event_type=OHF_CANDIDATE_RESULT_RECORDED`, `command_id=ohf-candidate:<turn_id>`, and a redacted payload under the *original* Job/Attempt identity.
- `RuntimeReadObservationReceipt` is the existing same-read source witness. A finalized `SAME` receipt is **as of that closed bounded read**, not an ongoing live guarantee. `BoundedRoleResultRootMetadata` plus original `Job` and `Attempt` are already-defined Runtime types; the source owner must obtain all material under one consistent observation. This leaf cannot authenticate a caller-supplied snapshot on its own.
- `EventRegistry.list_events` is a broad incumbent read and **not a public bounded authorization API**. Do not expose it to a browser, scan roots or select a candidate from guessed IDs; an owner-specific bounded acquisition must be built under the existing Runtime before public integration.

## One narrow metadata projection

`control_plane/operator_activity_projection.py::project_retained_operator_activity` accepts the typed `RetainedActivitySnapshot`, a finalized Runtime receipt and exact `(work_ref, root_job_id, job_id, attempt_id)`. It refuses foreign roots/jobs/attempts/workstreams, nonmatching worker/quota/turn/candidate/cursor identities, malformed source receipts, changed source, untrusted nested records, bad timestamps, duplicates and over-budget inputs.

It emits only `mastermind.operator_retained_activity_metadata.v1` with:

- original root/work/Job/Attempt selector and at most **32** sampled metadata rows, each containing the **original** candidate Event ID, Turn ID, ordinal, coarse known event category and the **candidate-recorded-at time**;
- exact source scope `RETAINED_CANDIDATES_ONLY`, `SAME_AS_OF_READ`, a declaration of input truncation, count of candidate receipts and normalized rows in this bounded sample, and omitted-in-sample count;
- explicit `null` global event total and live worker count. A read with no retained candidates is `NO_RETAINED_CANDIDATES`, **never idle**. Partial source or row omission is `PARTIAL`, not a fabricated complete timeline.

**Privacy:** the projector never copies raw or already-redacted provider payloads, prompts, summaries, candidate artifacts, private write paths, native subordinate IDs, provider event IDs, provider cursor, tokens, process IDs, lease owners or model output. Raw opaque `kind` strings map into a fixed coarse category, and unknown kinds become `OTHER_REDACTED_EVENT`. Result JSON is capped at 16 KiB. The timestamp is Runtime **candidate persistence time**, *not* when the provider tool action occurred; event ordinal is order in the retained candidate, *not* a cross-provider causal or elapsed-time measurement.

## Verification

- Original Runtime `Event`, `Job`, `Attempt`, `BoundedRoleResultRootMetadata`, `RuntimeReadObservationReceipt`, `TurnRef`, `CandidateResult`, `EventCursor` and `NormalizedEvent` typed shapes exercised.
- Adversarial tests cover: exact authority joins, finalized source identity, wrong workstream/root/Attempt (no principal authorization is supplied by this leaf), foreign worker/quota/command, nested identity drift, unknown fields/kinds, duplicate turns/events, absence-as-unknown, source truncation, 32-row cap, 64-source-Event budget, 256-per-candidate bound, UTF-8 output limit and secrecy under provider/token/path payloads.
- **47 passed, zero failed** using M2 Python 3.14 with `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -o addopts='' tests/test_operator_activity_projection.py` on the exact source implementation before publication. No real production candidate Event or full authenticated customer projection has been accepted.

## Exact remaining integration gates

1. **Original Runtime bounded reader owner:** qualify canonical root/workstream → Job → Attempt with a single bounded attempt-event acquisition and finalized before/after source receipt, actual bytes/rows ceiling, observer lifetime and lease/revision witness. Use original Runtime, not a second event registry. No events, unavailable, revoked or foreign source must fail closed.
2. **Original Workspace authorization owner:** for the authenticated pseudonymous principal, prove membership to that exact Executive Job/Attempt and current grant at acquisition and publication. Add a narrowly selected HTTP route only through existing Workspace and public-edge fixed allowlists after reviewed contract. Positive original Attempt plus negative sibling/cross-principal, revoked mid-read, expired credential and source-change tests required. No machine-wide Fabric run enumeration.
3. **Existing OS clients:** bounded Web OAuth and separately controlled native Tauri reader, strict DTO decoder, explicit selected-attempt metadata timeline, sign-out/rebind generation invalidation, no background polling or automatic worker restart. The existing plan UI and Fabric Mission inspector can locate a candidate Job but cannot infer tool-read permission.
4. **Protected release/acceptance:** exact-head independent review, CI and protected merge, installed/released app/edge identity, signed-in and signed-out real product tests with retained candidate evidence, robust unavailable/partial/refusal states, and acceptance as a distinct proof.
5. **Live tool activity remains separate:** Runtime retains evidence *after a candidate turn is collected*. Real-time progress would require an accepted original-owner read of live adapter events that preserves writer leases and provider generation; it cannot be inferred from this retained metadata. Hidden model chain of thought is not an accessible or approved surface.

**Known independent blocker:** read-only HTTPS probes on M2, M1 and Ubuntu0 observed `mcp.mastermind-x.com` resolving through `.eo.dnse3.com` and presenting `CN=*.cdn.myqcloud.com` rather than a hostname-valid certificate. Strict TLS fails before any app response. Restore trusted public-edge certificate with the existing EdgeOne domain owner before claiming any authenticated Web/native canary. Do not bypass verification.

**DO_NOT_REDO:** merged Fabric inspector #1411, Fabric MCP owner #1359, original Web/native plan PR #1601, incumbent draft Fabric catalog #1426 and its unresolved principal-to-original-run entitlement. Do not merge or deploy this projection until the original authority and real-path gates are met.
