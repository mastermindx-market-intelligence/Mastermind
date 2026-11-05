# Secretary shared-team integration contract

Project: [Mastermind #2082](https://github.com/mastermindx-market-intelligence/Mastermind/issues/2082).
Task tree: [GROK_SECRETARY_TEAM_ACCESS.md](GROK_SECRETARY_TEAM_ACCESS.md).
Source census and design pin: `531bd22b03ffac002221b6a75fe70be70e13f417`.
Recorded 2026-11-05. This document is a consumer design and source-evidence map; it does not enroll a principal, admit a Job, install a service or certify endurance.

## Product and ownership

GB1 is the intended Meta-CEO decision owner. Secretary 2 retains the secretary role. The connected Slack directory verified GB1 as U0BTCHX8HMF and Grok Secretary 2 as U0CE04DHLFN; these are routing/contact facts, not Runtime or OAuth enrollment. Both should see the same authorized mission, while each action continues to carry that caller's real, independently enrolled identity and current grant. A shared view does not make the principals interchangeable. A role label, Slack user ID, workstream selector or root string grants no access.

The Chairman excludes Y7 Elevate Retail **Audit BYOK Harness System**. Y7 retains Hermes/BYOK harness forward motion, runtime service integration, credentials, isolation and installation. This project consumes those contracts on new Secretary-facing paths. It does not edit `integrations/hermes_delegate/`, `integrations/hermes_secretary/`, #1966 or #2080. The unrelated application-inference work under #983 retains its own writers.

Executive owns admission, Jobs, Attempts and effects; Router/Capacity owns placement; Workspace owns authenticated read enrollment; the installed COO/principal owner owns modifying rights; Dialogue/Wake/Runtime return owns attention and delivery; Agent OS owns organizational continuity. The new consumer owns no durable state, identity, grant, queue, subscription ledger or lifecycle.

## Surface census

All source references below are relative to this repository at the census pin. Source presence and installed readiness are separate evidence.

| Existing surface | Owner and contract | Secretary use | Limits that must remain visible |
| --- | --- | --- | --- |
| Canonical mission | [Workspace read service](../control_plane/workspace_read_service.py), [Mission reducer](../control_plane/mission_workspace.py), [Fabric projection](../control_plane/fabric_job_view.py) | Primary shared team tree; root/children/Attempts, review/repair, blockers, qualified result references | Bounded root acquisition; provenance/currentness and omitted partitions remain explicit. HTTP 200 does not mean CURRENT. |
| Workspace member enrollment | [Workspace contract](../integrations/mastermind_workspace_app/contract.py) | Separately verified GB1 and Secretary 2 reads under existing enrolled-member policy | V2 membership supports distinct subjects and independent permission receipts. Current broad READ policy is not an exact-team-only grant. |
| Native paid-run diagnostics | [Fabric read owner](../control_plane/workspace_fabric_read.py), [closed metadata](../common/executive_workspace_fabric_contract.py) | Supplementary catalog/status for the original owner-qualified COO attempts | Always PARTIAL; at most four roots/32 rows; candidate/omitted totals unknown and scan incomplete. Requires the original COO identity. |
| Principal work request | [COO contract](../integrations/executive_mcp/coo.py), [COO app](../integrations/mastermind_executive_app/coo.py), [request identity](../control_plane/coo_principal_request.py) | Submit one bounded in-mission intention and reconcile its original receipt | Current mandate and bounded_intent permission required. Admission does not mean dispatch or START. |
| Decision steering | [Principal ruling boundary](../integrations/mastermind_executive_app/principal_ruling_http.py), [target](../control_plane/principal_ruling_target.py) | Rule on one host-bound actionable obligation | Not arbitrary child/session control. No model-selected obligation, principal or destination. |
| Secretary grounding | [Grounding gateway](../integrations/mastermind_secretary_mcp/adapter.py), [schemas](../integrations/mastermind_secretary_mcp/schemas.py) | Existing six read tools | Remains unchanged; this is not the place to add mutation authority. |
| Original-parent reply events | [Event projection](../integrations/session_bridge/web_reply_events.py), [subscription owner](../integrations/session_bridge/web_reply_subscription_owner.py), [installed host](../integrations/session_bridge/installed_reply_events.py) | Existing qualified callback/return seam for committed replies | Exact original request and principal; signed verified callback; enabled host required. A committed reply is not parent consumption. |
| Grok attention | [Routine Wake adapter](../integrations/executive_wake/grok_bot_routine.py), [HTTP carrier](../integrations/executive_wake/grok_bot_http.py) | Existing one-nudge delivery and observation-only reconciliation | No retry/failover after uncertain delivery; native handle and binding generation are host-owned. |
| Attended Web Fabric | [Accepted facade guide](../integrations/studio_direct_mcp/FABRIC.md) | Bounded paid source work with retained result review | Current observed capabilities report no native parent wake/background execution and process-generation-only controller tracking. It is not the proposed durable watcher host. |
| Hermes delegate and Secretary consumer | [Delegate](../integrations/hermes_delegate/README.md), [native consumer](../integrations/hermes_secretary/native_dialogue_consumer.py), [unported constraints](../integrations/hermes_secretary/UNPORTED.md) | Integration reference for the Y7-owned host | Source-only/unbound or disarmed features are not deployed grants. The bounded native progress consumer does not create work. Historical notes in UNPORTED are not current law. |

## Primary shared visibility: canonical Mission, not a native-run reconstruction

The preferred read is:

```text
GET /workspace/mission/v3/current
query = {work_ref, root_job_id}
```

Use [`v2_selection(value, "mission_v3")`](../common/executive_workspace_contract.py) for the exact selector grammar. The [public app](../integrations/mastermind_workspace_app/app.py) returns the Mission document directly; the private Unix envelope `{ok, result}` is not the public response.

The public schema is `mastermind.mission_workspace.v3`. Its `read_state.state` distinguishes CURRENT, PARTIAL, HISTORICAL and UNAVAILABLE. Preserve source observations, usable sections and reasons alongside the tree. The result index independently preserves availability, absent Job IDs, omitted Job IDs and truncation. A non-current producer cannot be turned into a current result selector by the client.

The source reader already permits two independently enrolled Workspace viewers to select the same canonical mission. It checks each member's permission stamp before and after the read and joins the exact current Control Room responsibility/root. This avoids a new observer registry.

That permission is not interchangeable with the original-COO check on native paid diagnostics. [`CooInstalledSource.for_workspace_read_principal`](../ops/executive_os/coo_principal_host.py) requires the original issuer/subject/client, and the activity membership marker checks that identity again. Do not give Secretary 2 the GB1 credential or bypass these checks to obtain a richer catalog.

The existing complete Mission consumer decoder is [`decodeMissionv3`](../app/mastermind_os/src/mission.ts). Python reducer validators validate producer inputs, not the entire HTTP-output document. A small Python summary must state that it validates its consumed subset, use exact closed keys for that subset, verify the selected work/root and result/source join, and withhold malformed data. No schema-string-only claim of complete validation.

### Meaning of full visibility

For every authorized mission, show the canonical parent/child relationships, native execution status and current Attempt, review/repair, blockers and owed decisions, retained result references, and product acceptance as separate facts. Show source identity, currentness, omissions, unsupported surfaces and any incomplete scan. Do not emit a bare `full_visibility: true`.

| Information | Existing truth | Consumer behavior |
| --- | --- | --- |
| Job/Attempt status | Canonical Runtime mission tree | Preserve native statuses; no Attempt means no proven start. |
| Native paid run | Exact original COO-to-paid binding | Do not infer a run from a similarly named root or Job. |
| Host/pool/model receipt requested by GB1 | Current closed native catalog and Mission Attempt cards do not expose the complete placement tuple | Mark placement detail unavailable until an existing placement owner supplies an authorized, sanitized receipt. Never infer it from task prose. |
| Result available | Native/result-reference owner | Does not imply reviewed or accepted. |
| Product acceptance | Existing acceptance owner/Mission v4 when qualified | Preserve NOT_PROJECTED/UNAVAILABLE/NOT_ACCEPTED; execution COMPLETED is not acceptance. |
| Return delivered | Existing Dialogue/Wake/return carrier | Does not imply original-parent consumption. |
| Missing rows | Explicit source limits/omissions | Never count omitted work as zero, completed or healthy. |

## Consumer operation contract

Each role uses a host-supplied authenticated client. Origin, workstream, optional original ruling target and credentials remain host-selected. Individual method arguments never take credentials, headers, arbitrary URLs, actor/role labels, provider accounts, model choice or routing policy.

| Operation | Fixed existing route | Identity and uncertainty rule |
| --- | --- | --- |
| Shared mission read | GET /workspace/mission/v3/current | Exact host-bound work_ref plus validated root selector; server decides current membership. |
| Native catalog | GET /workspace/fabric/catalog/current | No selectors or source choice; original owner scope only. |
| Native status | GET /workspace/fabric/status/current | Validated root/run selectors; no implied entitlement. |
| Mandate read | POST /v1/tools/executive_mandate | Existing `{arguments: {work_ref}}` envelope. |
| Submit | POST /v1/tools/submit_principal_intent | Reuse owner normalization and derive req-coo reference before the one send. Preserve admission/dispatched distinction. |
| Reconcile | POST /v1/tools/principal_intent_status | Original request_ref/work_ref only. Never submits; not_found is not permission to retry. |
| Bound ruling | POST /mcp/principal-ruling | Actual MCP JSON-RPC tools/call for ruling, original public args, exact host target and response identity. No invented ruling-status API. |

Default mutation/ruling ports remain unbound. Authenticated READ does not enable modifying methods. After a timeout, cancellation or malformed modifying response, retain the original request/obligation and report effect uncertainty with no automatic replay. The SDK sends once; the host must supply a no-retry transport. This is not a claim of physically exactly-once execution.

Use strict bounded UTF-8 JSON, reject duplicate keys/nonfinite values, disable redirects, cap reads, close responses and sanitize errors. Do not expose raw backend exception text or credential-bearing bodies. Host credential renewal remains its existing owner.

## Always-on execution and token efficiency

The desired always-on property belongs to existing supervised execution and attention services. Model reasoning is invoked for bounded work or a material decision. This consumer adds no timer, polling daemon, event queue, ledger, cursor or LLM invocation.

1. Existing Runtime/Workspace owners produce canonical status.
2. A qualified existing deterministic watcher reads a bounded view or receives an existing commit event.
3. A stateless semantic fingerprint identifies material change. Durable cursors/bookmarks remain with their incumbent owner.
4. Existing attention routing sends an opaque obligation/reference to the actual principal when action is needed.
5. GB1 or Secretary 2 reads compact context, issues one authorized intent/ruling if needed, and later reconciles the original identity.
6. Result review and original-parent consumption remain explicit; the watcher does not auto-accept.

Fingerprint equality is view equality, not an event cursor or wake grant. Ignore per-observation timestamp/key/row-order churn, but preserve source identity and qualified snapshot, lifecycle times, currentness/freshness class, permissions, native status, coverage, acceptance and result changes. An unchanged PARTIAL/stale view remains PARTIAL/stale in every response. Detail suppression must show the current row/count/omission information.

The existing reply-subscription owner caps requested TTL at seven days and also caps it by the authenticated principal and original-request expiry. Therefore a seven-day requested TTL does not prove seven-day availability. Renewal, expiry/revocation, durable restart and catch-up need acceptance through the existing host. Do not build a consumer credential refresher or duplicate subscription store.


### Event and audience limits

The existing `session.reply_committed` event is an original-request reply notification. [RuntimeSessionReturn](../integrations/session_bridge/runtime_return.py) verifies the stored request principal; a trusted READ/submit pair preserves issuer, subject and client. Secretary 2's shared Workspace read does not grant a subscription to GB1's original replies. The webhook contract and Grok opaque-nudge contract are distinct; a receiver adapter belongs in the existing host if necessary.

The [Wake router](../control_plane/wake_router.py) intentionally produces NO_WAKE for generic Job completion; review-required and existing canonical Inbox/Dialogue/consultation/CI attention have their own producers. [Session targets](../control_plane/session_targets.py) select one actual seat/root target, and [obligation identity](../control_plane/wake_events.py) does not permit duplicate same-source obligations just to fan out to another role. Do not invent a secretary routing seat or turn fingerprint changes into new Wake authority.

The accepted immediate design is selective original-request/owed-turn attention, followed by each role's own canonical Mission read. A lossless feed of material mission changes to both roles would require an existing-owner producer and independently qualified audience extension. That capability is not established by this client.

The [existing delivery composition](EXECUTIVE_REPLY_DELIVERY_COMPOSITION.md) records a crash-before-notification-start gap: the post-COMMIT service task is not a durable outbox. Event cursor is null. The incumbent `session_reply_references` read supports bounded original-principal recovery (page size at most 32), but cursors are process-local and restart-invalid. On a legitimate reconnect, begin a fresh authorized traversal and separately read current Mission state. This can recover visibility without claiming lossless intermediate-event replay. Runtime/Wake remains the owner of any needed durability repair.

## Source verification and real-path acceptance

Source tests must compose the existing owner contracts rather than replace them with success-shaped mocks:

- The signed multi-member pattern in [test_workspace_control_room_read_edge.py](../tests/test_workspace_control_room_read_edge.py) proves independent fixture members and revocation on the Control Room route.
- The signed HTTP/Unix/Runtime pattern in [test_workspace_result_http.py](../tests/test_workspace_result_http.py) proves a one-member Mission/result join.
- This project must compose those into a new two-member same-mission test. Neither prior test alone proves that joined scenario.
- Native read tests reuse [test_workspace_fabric_http.py](../tests/test_workspace_fabric_http.py); COO controls reuse [test_executive_coo_app.py](../tests/test_executive_coo_app.py); ruling uses [test_principal_ruling_mcp_producer.py](../tests/test_principal_ruling_mcp_producer.py).
- Negative cases include stale/unavailable/mismatched selection, malformed/oversized data, source movement, post-read permission revocation, missing modifying grant, lost response, no replay, result/acceptance separation and explicit omitted coverage.

Source tests and CI establish source behavior only. The original product is accepted only after the actual GB1 and Secretary 2 independently read the same authorized team, one permitted work request and one original-obligation ruling pass through existing owners, useful work is reviewed and consumed by the exact parent, and response loss/restart does not produce duplicate work.

### Seven-day measurement

Start the observation window only after canonical STARTED/RUNNING and the real return path are proved. Require at least 604800 elapsed seconds. Preserve the installed revision, root/Attempt identities, source receipts and actual counters; a short accelerated fixture is not endurance.

Measure parent reasoning calls and input/output tokens, worker/model usage, deterministic reads, changed/actionable events, useful interventions, result consumption, duplicate dispatches, missed actionable changes and recovery latency. Keep unknown/cached/billed values separate; absence of cost telemetry is not zero cost.

For a comparison, count actual baseline parent polls over an equivalent interval and actual event-triggered parent turns. Report `1 - observed_parent_tokens / comparable_baseline_parent_tokens` only when both measurements and workload comparability are available. Routine reads that invoke no model can suppress unnecessary parent turns, but no percentage saving is claimed before measurement.

Exercise parent inactivity, process restart, reconnect/catch-up, token expiry and one-member revocation, late/duplicate events, source staleness/truncation and ambiguous mutation replies. Each falsifier must preserve the original effect and current authorization.

## Integration sequence and Cursor boundary

1. This project publishes the additive client, compact native and canonical mission projections, and source tests. No harness edits.
2. The currently assigned integrator consumes that exact source revision, supplies separately enrolled Workspace clients for GB1/S2 and the existing role-specific modifying clients where authorized, and mounts fixed read/control calls in the incumbent host.
3. Y7 retains all harness/service/credential/role installation work. Resolve its actual holds through its original carriers; this project does not perform or re-commission that work.
4. Reuse the existing original-parent event/Wake subscription and supervised Runtime owner. Verify installed readiness, callback/return generation and revocation before declaring an always-on team.
5. Run the two-role live journey and measured seven-day acceptance. Keep source, installation, enrollment, execution, parent consumption and endurance as separate receipts.

Cursor may work on this project's additive consumer module/tests after checking live path custody and exact PR/head; it must not duplicate the active paid tasks or edit Y7 paths. If a future team-only observer grant is necessary, propose it in the existing sealed Workspace permission owner with independent revocation and both before/after checks. Do not invent a Secretary-side permission map.
