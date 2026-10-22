---
name: mastermind-verify-and-close
description: Verify Mastermind engineering changes through actual unit/integration/consumer paths, independent review, GitHub PR evidence and Agent OS continuity without merging from test green alone.
---
# Mastermind engineering proof and recovery

1. Start from the user's original outcome and identify the actual consuming surface (UI/browser, CLI, API, data pipeline, Job/Attempt, or authenticated MCP).
2. Confirm exact source revision, code owner, live workspace/collision, original effect root, valid testing scope and whether review is independent of the author.
3. Run the narrow deterministic test first; if meaningful, expand to integration/e2e. Assert negative paths: missing tool, denied identity, malformed data, stale revision, lost result, duplicate request, neighboring feature untouched.
4. Inspect the real consumer: native Cursor Task trace for true delegated child START and model, MCP tool catalog and admitted request for Fabric; browser/UI screenshots only if the user outcome actually requires them. Never translate installation, stub results or a setup screenshot into runtime proof.
5. Review exact diff plus evidence and record P0/P1 gaps. A timed-out independent reviewer or a model that merely repeats the author's claims is not a completed review.
6. Publish or reference the GitHub artifact with a stable SHA, test receipts and missing evidence. Reconcile pending CI on the same PR/head. Do not create a second PR just to get around a pending check.
7. Record the workstream's material result in the existing Agent OS if an authorized write path exists. An unavailable connector is a durability limitation; source evidence in GitHub is not a replacement for required Agent OS acceptance.
8. Reassess DONE_WHEN and continue the next unblocked slice. Call final acceptance only with the specific required real-path result and authority. Keep operational and source-only readiness separate.

Report: `source_head`, `test_receipts`, `review_state`, `real_consumer_state`, `effect_state`, `durable_ref`, `next_action`. This is a report shape, not a second lifecycle schema.
