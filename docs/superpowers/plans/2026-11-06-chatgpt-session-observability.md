# ChatGPT Web session visibility and continuity — implementation master plan

Version: 1.2 • 2026-11-06 (America/Vancouver)
Operation: `chatgpt-session-observability-20261106-c2`
Workstream: `WS:CHAIRMAN-CONTROL-ROOM`; existing SC1 / active-dialogue program.
Source/law base: `af18454f0cd2086c7976e55e16fee1d8dd70f405`.
Agent OS source inspected: Macro `d83f26a8bfa09f2c5b2eaa932b58cd303ef6c301`,
`agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md`.
Carrier: `sol/web-chatgpt-session-observability-20261106-c2`.
Status: O1–O3 SOURCE MERGED (#2174); O5 consumer extension source tested; installation and live acceptance unproven.

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


## O5 consumer extension — original Workspace owner, not another memory plane

Operation: `chatgpt-session-continuity-consumer-20261106-c2`.
Source base: `9d1558e99615e30a0b4e47404e4b2b2e7c440083`.
Carrier: `sol/web-chatgpt-session-continuity-consumer-20261106-c2`.

O1–O3 landed through the protected queue in PR #2174, squash merge
`2986a584a96bd98e8ac4ee27c61ab84169667784`. Candidate
`50adff1969d1b0d2b43d6d99bfff62ccb148faa4` passed required CI
42331708315, Hermes harness 42331708309 and CodeQL 42331704806. Required CI
used its legitimate source-proximate classification; this is not a full pytest
suite claim. The preceding publication-pending frontier above is historical.

Neighboring native source #2134 and leadership organization source #2173 have
merged. That resolves source overlap, not native installation, role enrollment
or the original browser permission holds. Macro PR #10817 records this mission
in the existing SC1 workstream and Agent OS handoff, not a new task registry.

The next useful source slice connects the existing authenticated Workspace
project-plan route to the already existing Hermes leadership brief. The current
Executive resource allowlist does not itself supply per-caller profile/workstream
ACLs for O4. Do not invent an all-access adapter or use a direct filesystem
collector to fill that installed authorization gap.

| Leaf | Retained owner-seam work | Done when |
|---|---|---|
| O5A | Add `SecretaryAccessClient.read_project_plan()` on its current authenticated Workspace client | One fixed GET, host-selected work_ref only, incumbent v1/v2 validation, wire-size bound, no retry/control/auth changes |
| O5B | Optional `LeadershipReader(include_project_continuity=True)` composition | Default remains exactly one Mission read; enabled adds exactly one plan read; native tool arguments remain empty |
| O5C | Bounded authored-plan projection and authorization regression proof | Exact source/adoption/missingness, no raw adoption/proposal bodies; 401/403 survive malformed responses; revocation discards all earlier facts |
| O5D | Source publication and real installed-role acceptance frontier | Focused tests and required CI; host enrollment/actual role reads still separately proven, never inferred from source |

The projection is evidence from an authored workstream record, not an adopted
operating instruction or root-job binding. Keep the owner adoption state and
`matches_authored_record` distinction. Keep original DONE_WHEN and unresolved
effects missing: the plan route does not supply those contracts. Mission and
plan are separate reads, not an atomic snapshot. A local read-completion timestamp
is not a source freshness timestamp.

Each optional field has an explicit UTF-8 JSON budget. Oversized text is omitted
with coverage metadata, never silently truncated into an apparently complete
instruction. The existing whole-brief 24 KiB bound remains; optional plan content
may become explicitly unavailable rather than destroy an otherwise valid Mission.
No plan cache, raw transcript, new tool, new role, new credential, extra principal
scope, writer, queue, service or dispatch is introduced.

The currentness guard covers the actual host session/role/workstream grant and
authenticated client generation. Recheck before/after the additional await and
re-evaluate original Mission freshness after the plan and adviser-budget reads.
Any plan authorization refusal discards the entire earlier Mission/organization
brief, including malformed/empty/oversized/interrupted 401/403 bodies. Timeout or
5xx may leave a still-current Mission with explicitly missing plan content.
Cancellation propagates. Source text never grants admission or replay.

Validation will exercise the incumbent canonical producer, actual fixed Workspace
HTTP route and existing native handler with synthetic credentials and fixture
owners. This is source-path proof, not live Hermes or ChatGPT Web enrollment.


### O5 source verification

The new 49-case consumer suite and 186 incumbent regressions passed together:
**235 passed, zero skipped**, Python 3.12, 57.24 seconds (process 59.04 seconds).
The focused red-first baseline was two missing-feature failures and one preserved
default-path pass. The first full new-suite run was 42 passed / 1 failed: the
remaining failure was a test asserting a nonexistent `principal.subject` field.
It was corrected to the actual closed principal's `subject_digest`; no
production authorization contract was relaxed.

The final pack uses the existing signed Workspace HTTP routes, canonical Mission
producer, canonical v1/v2 plan validator and actual native brief handler with
synthetic owner records/credentials. It does not install Hermes or qualify a
production native profile. A read-only architectural critique identified the
malformed-401/403 and wire/brief-budget edges before release; the implemented
regression suite covers them. Main session self-checked the owned diff.

```sh
python -m pytest -o addopts='' -q \
  tests/test_hermes_project_continuity.py \
  tests/test_hermes_leadership.py tests/test_hermes_leadership_organization.py \
  tests/test_hermes_leadership_budget.py tests/test_hermes_leadership_cli.py \
  tests/test_secretary_team_access.py tests/test_secretary_team_access_http.py \
  tests/test_secretary_team_mission.py tests/test_workspace_project_plan_read.py \
  tests/test_project_plan_continuity_wire.py --tb=short
```

The native source test run reused isolated temporary test-only dependencies from
O1–O3, not an installed service environment. Next: publish this exact source,
consume required CI, release through protected repository controls, then obtain
the incumbent role/profile/Workspace bindings for a separately authorized live
canary. O4 and O6–O7 remain unproven; no all-account transcript/control capability
or product completion is claimed.

## O5E — Preserve the authored frontier across scoped steering

S4 continues the same operation and source carrier. Protected procedure pin:
`5f8c13da926011fb5fdc8cea21287b532ac968db` (Skillpack 1.0.1, bootstrap 1).
The original seven-path implementation and 235-case receipt remain historical
source evidence. S4 adds bounded wave projection; it does not enroll a native host.

The optional project projection now includes complete, explicitly selected
`id/title/status/depends_on/next_action/prs` wave rows in authored order. Each
candidate row is measured together with the final UTF-8 projection and updated
coverage against the existing 12 KiB limit. An oversized row is omitted whole,
and later smaller rows may still fit. No text, dependency or PR list is shortened.

Nonzero `wave_coverage.omitted` means an incomplete frontier. An omitted wave is
unknown to this projection, not completed, cancelled or satisfied. Retained
dependency IDs remain intact even if their predecessor row is omitted. The
existing 24 KiB brief may still replace the optional projection with explicit
`brief_capacity_exceeded`; it never retains false row coverage.

Steering remains authored evidence through existing owners:

| Authored instruction | What this reader preserves | What it does not establish |
|---|---|---|
| Pause | Original objective, waves and current pause instruction | A running Attempt stopped |
| Cancel named work | Owner's changed authored wave and unaffected work | Pending effects are absent or resolved |
| Reprioritize | New next action and all fitting original wave rows | Wider authority or a new task admission |
| Resume | A fresh authenticated read of the owner's current revision | Previous grants remain current or a send may be replayed |

There is no steering parser, status reinterpretation, new state store or queue.
The host-selected work reference, opt-in default, fixed authenticated GET,
128 KiB transport bound, per-await binding/freshness checks and total 401/403
invalidation stay unchanged. DONE_WHEN, root-job binding and unresolved effects
remain unavailable where the incumbent source does not supply them. Source prose
cannot cancel holds or expand permissions.

Focused fixtures run through the existing native handler and genuine owner
validators with synthetic authenticated transports. They cover fresh-reader
pause/cancel/reprioritize/resume revisions, urgent steering during an await,
retained original objective/waves, dependency-preserving omissions, Unicode and
whole-projection bounds, empty frontier without completion, and authority
non-escalation. This is source-level reacquisition, not process-crash recovery,
live model-window consumption, runtime cancellation or original-parent acceptance.

Execution ownership: `PRINCIPAL_JUDGMENT / LOWER_TOTAL_OVERHEAD`. The bounded
consumer repair remains on its existing clean registered workspace and typed
publisher, after current source/queue reconciliation. Native C3 judgment checked
the cross-owner boundary; it was not paid Fabric execution or formal PR approval.
No valid original Fabric root/parent/grant was supplied by this recovery, and the
current Executive state action returned `INVALID_ARGUMENT`; no identity or
worker enrollment is fabricated. Existing H24/selected-child operations and all
historical denied/uncertain effects remain unchanged.

### S4 focused verification

The affected optional-reader suite plus the new frontier suite completed with
**58 passed, zero failed/skipped** on Python 3.12 (189.54 seconds). This includes
nine new parameterized cases. The unchanged Mission-only/default path and
malformed/empty/oversized/interrupted 401/403 invalidation are covered in that
affected selection. Existing 24 KiB whole-brief omission also passes after wave
projection. The first new-suite run exposed the absent waves and a test-fixture
revision mismatch; the fixture now advances its decision-source commit together
with its record commit, as the existing v2 validator requires.

The read-only Executive Fabric root projection was subsequently serviceable,
with explicitly partial discovery provenance and `ceo_submit_armed=false`.
That visibility establishes neither this S4 operation's root/parent binding nor
worker admission. No Fabric submit, selected-child replay or provider call was made.

```sh
python -m pytest -o addopts='' -q \
  tests/test_hermes_project_continuity.py \
  tests/test_hermes_project_frontier.py --tb=short
```

Remaining S4 acceptance is unchanged: qualified live organizational context,
real steering/restart consumption, a bounded delegation and scoped peer exchange
consumed by their original parent. Authored wave visibility does not replace the
missing Executive pending-effect contract or prove that acceptance.


### O5F — ordinary harness integration after ModelArk source merge

The first ordinary Hermes harness run on S4 head `f04b0ee316f1383d4bb2a914574323cf4c051417`,
[42345842134](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42345842134),
failed on both Python 3.12 and 3.13. The exact integrated checkout was
`27bf3e8992635cec1195ce4ee890f3bad0868029`. Its failure was
`test_loaded_model_router_grants_no_authority`: a historical assertion required
all commercial aliases to remain absent until PR #1824 merged. PR #1824 had in
fact merged as `1e5f77a4e7aa5131ecbaef9bb00487882dec4d79`; the accepted aliases
remain disabled and worker-ineligible.

Repair only the stale test contract, on the original #2179 carrier. Check exact
alias membership and served models, distinguish absent versus present catalog
entries, require the loaded commercial provider to remain disabled and
non-autonomous, and snapshot all provider/alias records around binding.
Explicit absent, disabled-present and eligible-present fixtures prove that
catalog presence or eligibility never grants authority, production arming,
Capacity claims or selection commitment. The production router, profile,
credential, admission and provider-call code is unchanged.

Focused verification: `python -m unittest discover -v -s integrations/hermes_models/tests -p 'test_*.py'`
passed **23 tests** (including three presence/eligibility subcases), Python 3.12,
0.312 seconds; `git diff --check` passed. This is a repair to an observed required
integration path, not a substitute runner or a retry of the denied AF_UNIX
action. Ordinary hosted checks on the resulting exact head remain the release
evidence. The earlier 58-test frontier receipt remains applicable because this
repair changes no continuity source or frontier tests. Installed host/grant
qualification and original-parent consumption remain outstanding.
