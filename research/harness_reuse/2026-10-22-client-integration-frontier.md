# DeepSeek → Mastermind OS: delivered client slice and executable frontier

Operation: `deepseek-harness-os-upgrade-20261022-web-001`.
User outcome: a usable Mastermind OS with real project conversations, sessions and advanced agent capabilities, reusing licensed DeepSeek code where it reduces work without replacing Mastermind's established owners.

**MISSION_COMPLETE: false. SOURCE_IMPLEMENTED; LOCAL_TESTS_AND_COMPONENT_BROWSER_FIXTURE_PASS; NOT_INSTALLED; NOT_PRODUCTION_ACCEPTED.** This is an execution update to the existing selective-harness-reuse programme, not a replacement programme or a new runtime/control plane.

## 1. Preserve and connect the existing work

The protected source/procedure pin for this operation is `d31aade92b969e8897513d8634ecd59dba00e1e3`. The subsequent protected head `5a9dd2ceb95995aa7092ae073cd5315f31734009` was compared: its three commits touch six unrelated static/PBR paths, not this slice or its governing law. No ancestry-only merge was made.

Continue the original `docs/superpowers/specs/2026-09-27-selective-harness-reuse.md` and R3 `docs/superpowers/plans/2026-09-27-selective-harness-reuse.md` from merged #1037. Their 53 acceptance IDs are requirements, not inherited PASS receipts. The current estate audit #1683 at `1f991df27e8ed110e35772ae456ffc5c05c47e45` provides the crosswalk to earlier OS plans; preserve those plans and their accepted work.

Reuse the existing ACP worker, native process owner, cancellation, WorkerResult/CollectionReceipt and parent-consumption path. #825 and #1060 are merged predecessors, not work to recreate. #1196 remains the existing installed-factory carrier. #1362 remains the existing Executive/session bridge carrier. No new DSH worker, session database, scheduler, queue, credential store or permissions service is introduced.

## 2. What this slice actually implements

Two small, dependency-light source modules are copied **byte-for-byte** from the MIT-licensed upstream `deepseek-ai/deepseek-harness` at `687f282e8625c6b8d11ff58211a90524be2e4317`:

| Upstream source | Actual Mastermind consumer | Behavior and boundary |
| --- | --- | --- |
| `packages/client/ui-primitives/src/keyboard-composition.ts` | `orchestration/ui/useComposerKeyboard.ts` → `SelectedSessionContinuation.tsx` | Standard and Safari late-IME confirmation protection; Ctrl/Cmd+Enter uses the existing form submit; pending/unknown/recovery/validation and duplicate-send guards remain authoritative. |
| `packages/client/ui-primitives/src/markdown/incremental.ts` | `conversations/SourceMarkdown.tsx` → lazy formatted view in `ResultSourceReader.tsx` | GFM headings, tables, code, lists and source footnotes; explicit code copying; exact original source remains the evidence/draft input. Streaming support is implemented/tested, but the mounted result reader currently receives settled source. |

Plain Enter intentionally remains a newline in the governed continuation form. An existing regression test caught the initial plain-Enter behavior; the implementation was corrected instead of weakening that test. IME, held keys, Shift/Alt/AltGraph, invalid fields, pending effects and recovery holds cannot use the shortcut to bypass the original controller.

The formatted reader is opt-in and lazy-loaded. It does not interpret HTML, fetch images, navigate Markdown destinations, expose local files, execute tools or write source state. It refuses formatting beyond 65,536 UTF-16 units, 8,192 AST nodes or 48 levels while preserving the exact source view. Settled responses always receive a full parse so late reference definitions cannot inherit a provisional streaming parse. Code-copy failure is reported honestly; stale asynchronous completion cannot overwrite a newer source's state.

No DeepSeek brand, Electron shell, Cordis host, provider/account store, telemetry, scheduler or session persistence implementation is imported. The existing React/Tauri shell and Paper-derived Mastermind theme tokens remain in use. The source UI includes English/Chinese chrome, keyboard accessibility, responsive tables/code and dark/light rendering.

`src/vendor/deepseek/manifest.json` binds upstream paths and SHA-256 hashes; `NOTICE.md` explains the adapter boundary. The complete upstream MIT license is retained both with the donor source and in production `public/third-party`. Full license texts for all 58 newly introduced runtime dependency packages are included; all declare MIT at this exact lockfile. Production license bytes are tested, not merely mentioned in documentation.

## 3. Executed proof and its limits

- Focused application checks: **79 passed** across existing/new composer, source-reader, Markdown and incremental-parser tests.
- Full application suite: **1,704 passed; one existing skipped test**, 76 files, using `npm test -- --maxWorkers=4`. The first unconstrained run had one existing daily-route timeout under the larger parallel load; the bounded-concurrency run kept the test's assertions/deadline unchanged and passed. This is not a claim that all unrelated performance issues are resolved.
- TypeScript plus production Vite build passed. The Markdown renderer is emitted as a separate lazy chunk, rather than making its parser an eager app dependency. Existing large-main-chunk/Tauri dynamic-import warnings remain.
- Python provenance checks: **4 passed**, including exact donor hashes and distributed license/notice bytes.
- Actual Chromium component fixture: desktop 1440×1100 and mobile 390×844, dark/light modes; no page errors, horizontal document overflow, external requests or active Markdown links/images; plain Enter makes zero fixture submissions and Ctrl+Enter makes exactly one. Mobile table/code layout was visually inspected and corrected before the retained proof.
- `git diff --check` passed.

Browser evidence is in `evidence/2026-10-22-client/`. `app/mastermind_os/tools/qualify_client_reuse.py` reproduces it against a dedicated loopback Vite origin; it starts a fresh isolated browser context and blocks external requests. The fixture is clearly labeled, refuses non-loopback hosts, is not the production entrypoint, and has no bearer, provider or real SEND. These screenshots do **not** establish authentication, production session execution, installed app use or original-parent consumption.

The parser tests compare every chunk prefix of representative GFM/code/Unicode/CRLF input with a fresh parse. A deterministic 100-paragraph case processes 18,578 parser-input UTF-16 units versus 312,145 for full reparsing; the growing open-fence case processes 9,743 versus 151,345. These are approximately 94% reductions in **parser input volume in fixtures**, not measured UI latency, model tokens, subscription savings or production throughput. The current settled-result consumer does not claim this streaming saving in production.

## 4. Why the app still does not have an accepted live chat journey

The repository already contains conversation, draft, original-result and selected-session components. Their existence does not mean an installed user can launch a real session. The current native client at the protected source pin lacks the `executiveSession` transport needed by that consumer. Existing #1362 contains the relevant connection and substantial backend composition work; duplicating it here would create competing ownership and risk.

Important qualification from the actual #1362 diff: its new native session transport is explicitly **READ-only** (`send` rejects `NATIVE_SESSION_READ_ONLY`). It adds context/reply/reference reading, while preserving a separate native SEND/F2 hold. Therefore even an eventual #1362 source merge is **not** proof of unrestricted native chat or session continuation. Web SEND and native READ are separate capabilities and must be qualified separately.

Fresh installed-owner observations on October 22:

- `session_targets` returned an empty array. No addressable target was invented from an open app or a UI row.
- The installed Executive release is `80f384b8f58b7ca46422d9783aa5c0613c7bf4b2`, not this source candidate.
- The exact installed `autonomy-control.sh status` returned `DISARMED`, both control/worker arming flags false, `service_state: AMBIGUOUS`, `status: EFFECT_UNKNOWN`, with an October 19 readiness expiry. This is a read-only observation of existing runtime uncertainty, not an uncertain modifying effect created by this operation.
- The separate installed `ceo-submit-status` returned `CEO_SUBMIT_DISARMED`, code `ceo_submit_disarmed`, transaction `autonomy-174a75c059eb`.
- The legacy `executive_state.mode=readonly` alone is **not** used to infer the availability of every separate V3 action. The exact status observations above are the actual admission evidence.
- No provider call, worker start, runtime arming, credential read, new grant or service modification was attempted by this client slice.

The missing live capability must be repaired through the incumbent installed/release/admission owners. A more attractive chat window cannot substitute for that work, and an empty target list does not authorize a synthetic target or parallel session service.

## 5. Incumbent work that must not be overwritten

### Executive/session bridge #1362

Immutable source head: `dd9f1bbc61a5413b09d98edea7ff81f0f72427b1`; branch `sol/web-cross-client-hooks-r1-20261012-sol-001`; current PR is draft. Its published receipt reports green hosted checks but an unreturned independent review. Preserve original review run `bridge-1362-integration-review-01a15e3f` and its pre-provider `canonical_source_unreadable` failure; no replacement/replay was issued here. Its original workspace has preserved staged/held source that this operation has not changed.

Next useful action is exact-head review/adjudication and current-base qualification on that carrier, followed by the existing installed release procedure when its actual gates permit. Do not relabel historical test receipts as this operation's reruns. Do not claim native SEND from its READ-only addition.

### Installed ACP factory #1196

Immutable remote head: `47bfa9d72e7d98c9d28f57020d5eb2b90b28b273`; branch `sol/web-deepseek-harness-acp-installed-adapter-20261003-sol-001`; draft, currently not mergeable. Its retained workspace is present and **dirty**, containing further changes to the installed/native adapter, capability/router/worker tests, and untracked `workspace_read_mcp.py`, `workspace_read_server.py`, their script and tests. Those are existing implementation, not permission to build replacements. This operation performed only a status read and did not reset, clean, copy over, rebase or commit that workspace.

Recover its exact latest continuation and actual writer/effect state before continuing that work. The PR's explicit outstanding conditions remain: OS confinement, dedicated credentialless principal/root-installed packet, supervisor admission, immutable broker/sweeper composition, real governed read/search through Job→Attempt→Worker→Result→original parent, and cancellation/restart/UID-sweep/assignment-seal acceptance. `implemented:false` must not become true because source tests pass.

## 6. Full reuse map and next implementation order

The upstream package tree was inspected at the exact donor revision. Package existence below is an exploration lead, not a claim that its implementation has passed security or compatibility review.

| User capability | DeepSeek material to study/reuse | Mastermind integration owner and delivery condition |
| --- | --- | --- |
| Conversations, New Session, history, resume | `client/ui-session`, `ui-chat`, `ui-conversation`; core/session projection patterns | Existing Executive session transport and Agent OS references. Finish launch/target/original-answer journey first; never add a second transcript database. |
| Streaming rich replies and long outputs | `ui-primitives/markdown`, `ui-renderer`, `ui-chat` | Current source reader now has a tested rendering seam. Connect only actual canonical live text/settlement signals; preserve bounded display vs full parent-consumed result distinction. |
| Composer commands and @references | `ui-input-trigger`, `ui-commands`, `ui-reference`, context/file-reference and session-reference | Existing workspace/content/tool-binding owners. References must bind authorized exact source identities, not arbitrary filesystem or session strings. |
| Tool cards, approval and permissions | `ui-tool`, `ui-approval`, `ui-permission-presets` | Existing admission/grant and pending-effect owners. Distinguish observed call, approved call, committed effect and settled result; no UI-generated grant. |
| Files and deliverable previews | `ui-attachment`, `ui-deliverables`, `ui-sidebar-files`, `ui-sidebar-documentpreview` | Existing bounded content/artifact interface. Keep local-path and remote-image access independently authorized. |
| Context and compaction | `compaction-basic`, `compaction-image-offload`, `compaction-tool-result-pruner`, session-turn-outline | Existing context/continuity owner. Preserve exact source/artifact references and unresolved effects; test corrections, omitted-tail retrieval and tool-result attribution before adoption. |
| MCP plugin interoperability | `mcp-client`, `mcp-resources`, plugin UI | Existing tool registry/generation and actual dispatch gate. Continue R3 M01–M12 with real schema/callable generation checks, not a new discovery proxy. |
| Subagent fan-out and progress | subagent ACP/DSH SDK/fork/spawn patterns; `ui-subagent` | Existing Fabric/router/capacity/worker/result path. No duplicate child budget, runtime or queue; no implicit entitlement to a provider. |
| Plan/goals and worker activity | `ui-plan`, `ui-goal`, `ui-workflow-run`, `ui-trajectory` | Existing project/mission, result and acceptance projections. A plan step is not execution proof; preserve user completion conditions. |
| Background jobs and automation | `ui-jobs`, `ui-schedule`, schedule/workflow packages | Existing Executive/Dialogue/Wake scheduling and resource owners. Copy UX patterns only after exact capability projection; no parallel daemon. |
| Model/provider selection | `ui-model-selection`, agent-default-model | Existing Model Router/Capacity and credential owner. Only currently eligible choices; truthful requested/served identity and budget, never another account store. |
| Sessions on desktop and web | Shared React client patterns, API boundaries | Preserve Tauri/Web auth isolation and exact source/session scopes; do not import Electron/DeepSeek auth as a shortcut around native SEND review. |

Ordered delivery: (1) finish source publication of this client slice; (2) resolve the existing #1362 source/review and installed admission gates, including the separate native SEND boundary; (3) prove one real Web project/session→send→original reply→actual parent-consumption journey; (4) recover and complete #1196's preserved ACP work through a provider-free read/search task; (5) qualify one actually admitted paid provider without changing credential/routing ownership; (6) attach the remaining UI features to those proven owners; (7) qualify compaction/MCP/automation features with their own discriminating evidence. These are continuation actions, not automatic runtime grants.

## 7. End-to-end acceptance that is still owed

A real authenticated user can open or create a project, choose an admitted session, send an explicit instruction once, see truthful execution/tool/reply state, receive the original useful result, inspect exact evidence and deliverables, and resume after reload without resubmitting an uncertain effect. The actual assigning parent must consume the canonical full result, including an oversized-result tail sentinel where applicable. Cancellation must prove process/resource settlement, not just an ACK. Wrong principal/session/generation, stale grant, denied provider and disconnected runtime must fail without fabricated success or fallback.

Native and Web paths need their own receipts; source, merge, package build, installation, admission, START/RUNNING, completed result and acceptance remain distinct. Until those observations exist, this programme remains incomplete even though the client slice is useful and tested.
