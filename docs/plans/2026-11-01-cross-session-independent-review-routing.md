# Cross-session independent-review routing — task tree

**Chairman assignment (2026-11-01):** Enable authorized ChatGPT Web and other sessions to discover and properly use Subagent Fabric for independent review, with separately qualified direct Slack-to-Dot reviews that may use included Astra capacity when verified available.

**Procedure pin:** `Mastermind/master@19cb00cfed26b68f0a8a5cdc0f2f1a9463a3feec`; `mastermind.sol_skillpack.v1` 1.0.1/bootstrap 1. This source plan creates no runtime, reviewer queue, new authorization, automatic Dot wake, or backend.

## Canonical boundary

Executive OS / Fabric: reviewer Job, Attempt, admission, START and result. GitHub: PR/head, code, CI, formal reviewer identity, release. Agent OS: plan continuity. Slack: directed reviewer message, pickup and return transport. Reuse existing GitHub review intent and #1740/#1748/#1763 rather than duplicating the webhook/ingress. Avoid overlapping Fabric graph PR #1910. An active/unresolved or refused review cannot be rerouted by a new name or carrier.

## DONE_WHEN

A newly assigned Web/Codex/Claude/Grok seat loads the single review-routing procedure and chooses tools based on observed availability, not model labels. A genuinely eligible Fabric source review produces START and retained findings; a single independently eligible Dot produces real Slack pickup, START and completed source findings; formal GitHub release approval is submitted by an authenticated distinct non-author at current head. Source merge does not prove installation on Web accounts, unrestricted Dot usage, or production review path.

## Scoped tasks

| Task | Dependency | Evidence |
| --- | --- | --- |
| CSR-0 census | None | Current protected source pin, source collision check, current Web Fabric capability, Slack review channel membership, #1740 owner |
| CSR-1 shared review route | CSR-0 | Source-bound decision table and Dot/Fabric packet; independent identity and no forbidden failover |
| CSR-2 entrypoint links | CSR-1 | Mastermind AGENTS, CLAUDE, principal instructions, review skill and Project bootstrap kernel point to one guide |
| CSR-3 tests + PR | CSR-2 | Managed branch, source assertions, focused tests, GitHub exact-head Draft PR, distinct formal review request |
| CSR-4 Dot canary | CSR-3 | One real recipient in existing Slack channel, genuine ACK/START/RESULT, independent authenticated GitHub review or explicit NOT_PROVEN |
| CSR-5 Web/provider enrollment | CSR-3 | Approved compact Project instruction installed by actual editor; fresh-session tool/skill read on each claimed account/surface |
| CSR-6 end-to-end | CSR-4,5 | Real Fabric admission/START/result and optional Dot review, GitHub submission and required product path proved; each missing cell named |

## Observed at intake

Web Fabric adapter accessible; worker admission and START both UNPROBED, background_execution=false and native_parent_wake=false. Slack `#github-independent-reviews` (`C0CAUK8P8S3`) has ChatGPT1–4 membership on 2026-11-01 readback; membership is not runtime pickup. #1748 and #1763 are merged source; no resulting installed webhook-to-review production proof was observed. Executive session-target read returned backend_unavailable. Classify live all-account adoption as NOT_PROVEN.

**Next:** Implement CSR-1/2 on the current managed workspace operation `cross-session-review-routing-20261101-sol01`, validate, publish one Draft PR and request one separate, non-author Dot review. No new child for #1740, no same-scope replacement of its workers.
