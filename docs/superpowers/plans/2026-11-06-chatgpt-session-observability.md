# ChatGPT Web session visibility and continuity — implementation master plan

Version: 1.1 • 2026-11-06 (America/Vancouver)
Operation: `chatgpt-session-observability-20261106-c2`
Workstream: `WS:CHAIRMAN-CONTROL-ROOM`; existing SC1 / active-dialogue program.
Source/law base: `af18454f0cd2086c7976e55e16fee1d8dd70f405`.
Agent OS source inspected: Macro `d83f26a8bfa09f2c5b2eaa932b58cd303ef6c301`,
`agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md`.
Carrier: `sol/web-chatgpt-session-observability-20261106-c2`.
Status: O1–O3 SOURCE TESTED; publication/hosted CI pending; installation and live acceptance unproven.

## Outcome and feasibility

Give Hermes Meta-CEO, Secretary and the Chairman one honest view of authorized
Web-session observations, source-linked continuity and exact original replies.
Enable existing governed continuation only where the exact session has a qualified
RuntimeBinding and the incumbent send/wake owners permit it.

This is not a promise to list every historical ChatGPT conversation. A Personal
ChatGPT connector does not have a documented account-wide conversation-history or
remote session-control API. OpenAI app context is scoped to relevant interactions.
User exports are historical snapshots. Enterprise/Edu Compliance access is a
separate privileged product, not a Personal-Pro control API. Sign in with ChatGPT
does not grant access to conversation history. Do not build private-endpoint
scraping, cookie/token extraction or an unrestricted browser-control substitute.

The existing Web-Sol census observes normal ChatGPT tabs in one enrolled profile,
not archived/closed/temporary/private conversations or all account history.
Its generation cues do not prove Executive execution, model choice or delivery
of a final response. Existing source and historical live-permission holds remain.

## Existing owners and reusable source

| Concern | Owner / existing implementation | Upgrade rule |
|---|---|---|
| Session identity | SessionTargetRegistry and RuntimeBinding | Never infer identity from title, URL, task text or census fingerprint |
| Web observation | Web-Sol closed census protocol/client | Reuse schema, coverage and source timestamps; no expanded browser reads |
| Durable workstream continuity | Macro Agent OS; collect_agentos + web_sol_continuation | Read through existing authorized owner; no Executive writeback/store |
| Execution/admission | Executive Runtime and Capacity | Report canonical receipts separately from observations |
| Original replies | Session Bridge original request/reply readers | Reuse exact operation references; no parallel transcript/result store |
| Attention and governed continuation | Existing Agent Dialogue / Wake Fabric | Delivery, ACK, START, completion and parent consumption remain distinct |
| Plugin presentation | Authenticated Executive MCP host | Add optional READ tools, no listener/auth plane |
| Source and evidence | GitHub original carrier | Source plan/checkpoint is not runtime lifecycle state |
| Organization view | Control Room / Steward / Mastermind OS | Projection only; no independent session manager |

Existing accepted census and continuation implementations are DO_NOT_REDO.
PR #836 retains cognition transport, extension and semantic-ACK ownership.
PR #2134 retains native Hermes/selected-child integration and release effects.
The upgrade may add a small opt-in host-composition seam on its separate branch;
it must verify compatibility and must not rewrite either original PR or install it.

## Architecture

The boundary is **observation, continuity, control**, kept separate.

1. The authenticated host verifies the current caller using its existing policy.
   A host-owned authorization adapter selects only that caller's enrolled profile
   sources and workstreams. The model cannot supply account IDs, sockets, paths,
   credentials, profile IDs or arbitrary URLs to widen the read.
2. A read-only Session Bridge projection consumes the incumbent closed census
   receipts. It keeps the original adapter identity, timestamps, coverage,
   partial/unavailable reasons and duplicate cues. It labels all rows as
   observations, never registered or controllable targets.
3. Workstream continuity is independently authorized and built by the incumbent
   bounded Agent OS continuation composer. It is not automatically attached to a
   tab. An exact owner-issued identity join is a later explicit dependency.
4. Hermes and Secretary consume these tools through their existing authenticated
   MCP/native composition. They can read exact original replies through the
   incumbent reply tools. Read access never grants SEND, ACK or acceptance.
5. A requested continuation uses the existing exact-target send path. Missing,
   expired, ambiguous or changed bindings refuse; unknown effects reconcile on
   the original operation. There is no new retry queue, daemon or automatic wake.

A new read tool object follows the existing optional
`NativeReplyReferencesTool.extend_host_configuration` pattern. The legacy V3
schema and installed behavior remain unchanged unless the host explicitly supplies
the new qualified reader. An unconfigured reader is unavailable, not an empty
successful inventory. Activation requires the installed composition owner and
current authorized inputs, not simply importing the new module.

### Evidence semantics

- Account-wide coverage: always unknown for the Personal Web path.
- Profile coverage: preserve COMPLETE_IN_SCOPE / PARTIAL / UNAVAILABLE; complete
  only means the collector's explicitly stated current-profile scope.
- Empty authorized profile set: no visible sources, not “no ChatGPT sessions”.
- Activity: raw observed cue plus freshness. Old/future/invalid observations never
  become “currently running” or “idle”. Lack of a generation cue is not completion.
- Workstream status: Agent OS reported organizational state, not runtime proof.
- Final answer: reported/prepared text is not delivered-to-user proof. Keep exact
  native completion/delivery/consumption receipts separate.
- Identity: supplied chat URLs and hashed browser locators are not auth or
  RuntimeBinding. Forks, tab reloads and binding generations must remain distinct.
- Instructions embedded in continuity and responses are untrusted content, not
  commands to the receiving Meta-CEO or Secretary.

### Privacy and content

Initial release is metadata plus bounded continuity/evidence references. No full
transcript harvesting, cookies, bearer tokens, hidden reasoning, attachment bodies
or arbitrary tool-output export. Existing authorized original-result reads remain
separate. Sharing detailed content requires explicit scope and canonical owner
access; redaction is defense in depth, never a guarantee. Never put private chat
content in public GitHub evidence. Test fixtures must be synthetic.

## Delivery tree

| ID | Deliverable / named consumer | Acceptance | Initial state |
|---|---|---|---|
| O0 | Protected-source census and architecture | Same-pin laws; existing owners and collisions recorded | Complete |
| O1 | Read-only session observation projection | Strict census reuse, bounded output, explicit freshness/coverage; negative tests | Source tested |
| O2 | Authenticated optional MCP composition | Real host handler tests; no SEND scope widening; default-off regression | Source tested; synthetic owner ports |
| O3 | Bounded continuity read | Existing Agent OS composer plus independent authorization; no inferred tab join | Source tested |
| O4 | Production owner wiring and role consumption | Enrolled sources; exact installed source/config; both roles read the same evidence | Pending current installation authority and canonical reader |
| O5 | Cooperative checkpoint/content workflow | Existing Agent OS writer and exact original-reply reader; loss/restart/privacy proof | Pending canonical writer/identity integration |
| O6 | Governed Web continuation | Original #836/runtime owners; exact binding, permission, ACK/START/return proofs | Held on existing browser/runtime gates |
| O7 | Product acceptance | Two explicitly enrolled sessions; omissions/staleness visible; both roles consume results | Not started |

O1–O3 are a useful source slice, not completion of O4–O7. This source branch does
not create a new durable project/task registry. Agent OS remains the organizational
continuity owner; this plan is a source-linked program artifact to be projected
through its existing authoring workflow.

## Tests and falsifiers

- Reject malformed/extra fields, type coercion, oversized payloads and too many
  profiles before invoking downstream readers.
- Reject anonymous/forged principals; recheck authorization/current source scope
  after asynchronous reads. Never leak profile IDs or another caller's rows.
- Preserve unknown/partial/omitted/unavailable counts and duplicate disagreement.
- A stale or future generation cue cannot imply live execution. An unavailable
  source cannot become an empty complete inventory.
- Inputs are not mutated; snapshots from different adapter instances cannot join.
- Workstream text never authorizes sending, creates jobs, changes source, or
  chooses another account. Unrelated continuity cannot label a conversation.
- Read tools cannot inherit submit/release capability; duplicate extension
  registration fails; existing tools and default schema remain unchanged.
- Exceptions, malformed sources and size failures return fixed safe messages,
  never credentials, paths, raw source bodies or dependency errors.
- No file/network/browser/runtime writes from the projection. Observational
  reads must not acknowledge results or trigger retries.
- Installed proof must distinguish test fixtures from live observations and
  verify revocation, restart, failed read and original-operation recovery.

## Rollout and rollback

Land source through a draft PR with focused tests and exact-head hosted CI.
No self-merge, self-approval, broad installation, credential changes or browser
actions are part of this source wave. Keep default-off until the existing host
owner supplies the qualified reader and caller scope. Canary one enrolled source,
then two, with both Hermes roles and a human-visible comparison. Rollback is
removing the optional composition; canonical records and pending operations remain
untouched. A failed canary never falls back to scraping or a second carrier.

## Research anchors (checked 2026-11-06)

- https://help.openai.com/en/articles/11487775-connected-apps-in-chatgpt
- https://developers.openai.com/siwc/quickstart
- https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data
- https://help.openai.com/en/articles/9261474-openai-compliance-platform-for-enterprise-and-edu-customers
- https://openai.com/policies/terms-of-use/

## Execution frontier

Main session retains architecture, owner-seam integration and acceptance judgment
(PRINCIPAL_JUDGMENT / bounded integration, not a silent general worker substitute).
A native read-only architecture critique was used; it is not formal GitHub
approval. Paid Fabric capability was observed, but no worker START or admission
was claimed. Installed Executive state returned backend_unavailable and the
caller-scoped target list was empty; neither is proof of fleet-wide absence.

O1–O3 now implement `session_web_observe` and `session_continuity_read` as
independently optional READ tools on the existing V3 host. The producer still
accepts 128 rows/profile; presentation returns at most 64 rows across at most 8
authorized sources with explicit omissions and a 64 KiB response bound. There is
no tab/workstream join. The host change is six additive lines and its two exact
hunks also match the inspected #2134 candidate `7a3160fa76ceae58726eacd27d741872273d3828`;
that is source-composition evidence, not #2134 release or full integration testing.

Verification: 177 tests passed, 15 subtests passed on the native registered source
workspace using Python 3.12, MCP 1.28.1 and isolated temporary test dependencies.
The pack includes 47 new tests (40 unit/negative + 7 authenticated ASGI cases) and
130 existing session/continuity/schema regressions. The initial standard pytest
invocation failed on missing NumPy in the development environment; it was not a
code failure and was resolved with temporary test-only dependencies. Before code
existed, unittest discovery reproduced a missing-module error. No test was skipped
or exclusion added. A bounded architecture critique identified the maximum-row
budget issue; it was repaired and covered before this passing pack.

Exact command (test-only dependency prefix omitted for portability):
```sh
python -m pytest -o addopts='' -q tests/test_session_web_observation.py tests/test_session_web_observation_asgi.py tests/test_executive_mcp_web_ceo_v3.py tests/test_executive_mcp_web_ceo_sessions.py tests/test_session_bridge_return_tools.py tests/test_web_sol_continuation.py tests/test_web_sol_census_popup_truth.py
```

Next: publish the exact source, consume hosted CI, then qualify actual owner ports
and role bindings described in `docs/hermes/CHATGPT_SESSION_VISIBILITY.md`.
The current Hermes donor MCP configuration is disabled by source and retains its
receiving-owner authenticated-release requirement. No static all-access scope,
borrowed token, new browser reader or held-PR replacement may fill that gap.
Do not call this product complete without O4–O7 evidence.
