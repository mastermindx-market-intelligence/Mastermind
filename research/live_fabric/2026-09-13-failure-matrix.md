# Live Fabric adversarial acceptance matrix

**Parent:** WS:CHAIRMAN-CONTROL-ROOM. **Wave:** LF-F0. **Status of every case below:** REQUIRED / NOT_EXECUTED.

These 72 cases are design obligations, not passing tests or production evidence. Each implementation wave must bind applicable cases to actual test code, exact source/artifact identity and the right proof level. A synthetic fixture cannot establish real provider execution, physical fencing, browser installation or user acceptance.

Proof levels: **U** = pure/unit discriminator; **I** = integrated real component with controlled inputs; **B** = actual browser/WebView interaction; **P** = approved authentic installed path. Several cases require more than one level. Every negative test must also retain a positive control so that disabling the feature cannot make the suite pass.

## A. Identity, source and coverage

| ID | Adversarial condition | Required behavior and owning boundary | First milestone / proof |
|---|---|---|---|
| LF-T001 | Two Workers share an identical display name | Preserve distinct owner-qualified IDs; selecting one never addresses the other | LF-V1 / U,I,B |
| LF-T002 | A browser tab title matches an active mission but no exact binding exists | Show unjoined presence; no inferred Job, owner or action target | LF-V1 / U,I |
| LF-T003 | Two runtime candidates match a singular Steward query | Preserve ambiguous-runtime refusal; plural viewer uses its own existing owner read | LF-V1 / I |
| LF-T004 | Recorded RUNNING exists but provider activity is unavailable | Say recorded running with unverified activity; no animated live-execution claim | LF-V1 / U,B,P |
| LF-T005 | Provider generation cue exists without Executive execution evidence | Render the cue as observation only; no lifecycle or spare-capacity inference | LF-V2 / U,I,P |
| LF-T006 | An exact root contains a descendant joined to the wrong root | Refuse the affected join; retain safe source evidence and conflict detail | LF-V1 / U,I |
| LF-T007 | A source returns positively complete zero rows | Display exact zero for that scope, not unavailable and not whole-company zero | LF-V1 / U,B |
| LF-T008 | Inventory is partial but known rows exist | Keep known rows; total/overflow unknown; no all-clear headline | LF-V1 / U,B |
| LF-T009 | Inventory is complete but only half the probes succeed | Preserve exact inventory total; report incomplete probe/activity coverage independently | LF-V2 / U,I,B |
| LF-T010 | Authorization removes a hidden population | Do not disclose hidden counts or imply global completeness; name authorized scope | LF-WEB / I,P |
| LF-T011 | The source truncates at its supported row/byte bound | Preserve truncation and known subset; never extrapolate missing population | LF-V1 / U,I |
| LF-T012 | A correction invalidates a previously shown relation | Replace current relation, retain correction evidence, invalidate dependent action hint | LF-V2 / U,I,B |

## B. Consistency, streaming and history

| ID | Adversarial condition | Required behavior and owning boundary | First milestone / proof |
|---|---|---|---|
| LF-T013 | Old mission request completes after the user switches scope | Old scope/epoch response cannot overwrite current view or selection | LF-V1 / U,I,B |
| LF-T014 | Server restarts and its generation counter restarts | Owner epoch distinguishes generations; do not compare bare counters across restart | LF-V2 / I,P |
| LF-T015 | A delayed source value arrives in a newly timestamped wrapper | Preserve original age/validity; wrapper time cannot manufacture currentness | LF-V1 / U,I |
| LF-T016 | Stream heartbeat continues while underlying source is stale | Separate transport health from data validity; stale facts stay stale | LF-V2 / U,I,B |
| LF-T017 | Browser sleeps during a valid action hint | Resume forces source/preflight revalidation; paused JS cannot preserve permission | LF-V3 / B,P |
| LF-T018 | SSE client uses bare EventSource against header-gated local API | Test rejects this incompatible path; use approved fetch/header transport without weakening auth | LF-V2 / I,B |
| LF-T019 | Ten views request the same expensive source refresh | Existing single-flight owner bounds work; no ten independent Agent OS/GitHub gathers | LF-V2 / I,P |
| LF-T020 | Slow client cannot consume updates | Bound memory; coalesce display invalidations or demand resync; preserve canonical returns | LF-V2 / I |
| LF-T021 | History retention has a gap at reconnect | Explicit incomplete history; fresh snapshot may recover current view without invented replay | LF-V2 / U,I,B |
| LF-T022 | Cross-host clocks disagree about message order | Use explicit causal links; timestamps remain display ordering, not authority or causality | LF-V2 / U,I |
| LF-T023 | Same source event is observed twice | One semantic display item per exact event identity; no duplicate obligation consumption | LF-V2 / U,I |
| LF-T024 | Optional GitHub or browser source fails | Isolate dependent sections; do not suppress independent valid execution/attention evidence | LF-V1 / U,I,B |

## C. Commands, authorization and effects

| ID | Adversarial condition | Required behavior and owning boundary | First milestone / proof |
|---|---|---|---|
| LF-T025 | Two client tabs create different keys for one single-consumption obligation | Existing command owner atomically admits only one semantic edge for that obligation/generation | LF-V3 / I,P |
| LF-T026 | Same request key arrives with a changed payload | Conflict/refusal; no second effect and no silent overwrite of intent | LF-V3 / U,I |
| LF-T027 | Target binding changes between preflight and dispatch | Owner refuses stale target or requires new preparation; never act on replacement implicitly | LF-V3 / I,P |
| LF-T028 | Authentication or grant is revoked during awaited work | Revalidate before result publication/effect; close stream and clear protected client state | LF-V3 / I,P |
| LF-T029 | Provider accepts action but response is lost | Preserve owner-native effect uncertainty; no retry/failover; reconcile original operation | LF-V3 / I,P |
| LF-T030 | Browser closes after submit before recording receipt | Restore only operation reference and ask canonical owner; no local offline outbox replay | LF-V3 / B,P |
| LF-T031 | User presses request-status repeatedly | Distinguish recorded-status read from provider-turn action; no accidental repeated spend | LF-V3 / I,B |
| LF-T032 | Pending message encounters an active writing turn | Follow supported next-turn/interrupt semantics explicitly; no hidden interrupt or duplicate queue | LF-V3 / I,P |
| LF-T033 | One target fails in a multi-target stop | Show per-target receipts and partial outcome; never fleet-wide atomic success | LF-ACTIONS / I,P |
| LF-T034 | Cancel is requested after an external effect completed | Explain that cancel cannot undo completed effects; retain actual result and action receipt | LF-ACTIONS / I,P |
| LF-T035 | Local process fetches the existing CSRF nonce | Nonce alone cannot authorize new provider/admin/remote writes | LF-V3 / I,P |
| LF-T036 | Client supplies arbitrary URL, path, executable or provider home | Reject before effect; use approved target/recipe IDs through existing owner | LF-V3 / U,I |

## D. Autonomous progress and owner recovery

| ID | Adversarial condition | Required behavior and owning boundary | First milestone / proof |
|---|---|---|---|
| LF-T037 | Worker returns while no GUI is open | Existing owner creates/retains parent obligation and exact wake path; no browser dependency | LF-V4 / P |
| LF-T038 | Worker forgets to post its result voluntarily to Slack | Accepted provider/runtime return path surfaces result; no reliance solely on model etiquette | LF-V4 / I,P |
| LF-T039 | Parent Sol is sleeping but exact wake is available | Deliver and prove actual target consumption; transport delivery alone is insufficient | LF-V4 / P |
| LF-T040 | Previous reasoning owner is permanently unavailable | Existing recovery owner uses accepted evidence-based transfer, not endless wait for dead actor | LF-V4 / P |
| LF-T041 | Old owner wakes after successor acquired authority | Actual effect sinks reject stale owner; no second ruling or write | LF-V4 / I,P |
| LF-T042 | Lease expired but old process retains filesystem access | Do not call it fenced; prove isolation/authority revocation or preserve scoped uncertainty | LF-V4 / I,P |
| LF-T043 | Prior modifying edge remains effect-unknown during takeover request | Reconcile before target transfer; independent non-conflicting work remains possible | LF-V4 / I,P |
| LF-T044 | Child is STOPped while parent and siblings remain active | Only child's cycle closes; sibling/aggregate watchers continue correctly | LF-V4 / I,P |
| LF-T045 | Active parent has no successor after accepted child close | Re-enter accountable responsibility; admit next child lawfully, not via stale child watcher | LF-V4 / I,P |
| LF-T046 | Two Sol observers notice one returned child | Both may read; exactly one current sanctioned target may issue the semantic edge | LF-V4 / I,P |
| LF-T047 | No eligible worker capacity exists | Show real placement debt; do not invent receiver or ask Chris to allocate routine accounts | LF-V5 / I,P |
| LF-T048 | A real 2FA/admin ceremony is unavoidable | Surface one precise authority-required decision with scope; no password exposure or hidden bypass | LF-FLEET / P |

## E. Content, native surface and remote security

| ID | Adversarial condition | Required behavior and owning boundary | First milestone / proof |
|---|---|---|---|
| LF-T049 | Artifact Markdown/HTML contains scripts or malicious links | Text/sanitized or isolated preview; no privileged origin execution or native IPC | LF-V1 / U,B |
| LF-T050 | Tool output includes credentials, argv/env or provider-home content | Exclude before serialization; never rely on CSS hiding or post-hoc redaction alone | LF-V2 / I,P |
| LF-T051 | Terminal output attempts clipboard/escape-sequence side effects | Enforce the approved terminal isolation policy; inspection cannot become command execution | LF-ACTIONS / I,B |
| LF-T052 | Untrusted iframe or remote page attempts Tauri IPC | No privileged capability granted; fixed local shell commands are window-scoped | LF-MAC / I,B |
| LF-T053 | Bundled Tauri origin calls loopback API as though same-origin browser | Qualify fixed-target bridge; no permissive CORS or token-in-URL shortcut | LF-MAC / I,B,P |
| LF-T054 | WKWebView receives Chrome-qualified validity metadata | Do not inherit action qualification; separate client proof or read-only dated evidence | LF-MAC / I,B,P |
| LF-T055 | Local census field appears in remote output without an admitted projection | Reject/omit by remote contract; no raw profile/session/path leakage | LF-WEB / U,I,P |
| LF-T056 | Cached view is reused across different principals or project scopes | No cross-user/project leakage; auth/scope separated, stale protected state cleared | LF-WEB / I,P |
| LF-T057 | Mac update signature or release identity is invalid | Refuse update; retain known installed app; never migrate runtime on app launch | LF-MAC / I,P |
| LF-T058 | Provider or artifact content instructs the agent to expand permissions | Treat as data; no authority, budget or tool-grant escalation from retrieved prose | LF-STUDIO / U,I |
| LF-T059 | Two clones propose simultaneous instruction changes | Separate immutable proposals/preimages; no shared mutable log overwrite | LF-STUDIO / I,P |
| LF-T060 | New instruction version is promoted while an Attempt is active | Existing Attempt stays pinned; reviewed next admission may use the new version | LF-STUDIO / I,P |

## F. Fleet resources, usability and acceptance honesty

| ID | Adversarial condition | Required behavior and owning boundary | First milestone / proof |
|---|---|---|---|
| LF-T061 | Windows and WSL expose the same underlying memory/CPU | Use existing physical-domain identity; do not double-count capacity | LF-V5 / I,P |
| LF-T062 | Connector says online but a bounded operation times out | Show transport versus executor/operation health separately; no eligible-host inference | LF-V5 / I,P |
| LF-T063 | Provider quota is unavailable but UI wants a percentage | Show unknown; distinguish estimates, fixed subscription cost and measured incremental cost | LF-V5 / U,B |
| LF-T064 | Quota expires during an uncertain write | Preserve exact Attempt/realm/effect; no automatic cross-account or cross-host continuation | LF-V5 / I,P |
| LF-T065 | Source graph contains a cycle or deep nested cross-group edges | Preserve conflict/exact relations; bounded layout does not silently edit graph truth | LF-V1 / U,B |
| LF-T066 | Heartbeat arrives while user reads a selected node or scrolled history | Stable layout, focus and scroll; no auto-jump or decorative execution pulses | LF-V2 / B |
| LF-T067 | Keyboard-only, reduced-motion, narrow screen or 200-percent text zoom | Equivalent graph/list task completion; uncertainty and consequences remain readable | LF-V1 / B |
| LF-T068 | Large synthetic graph and bursty update input | Bounded visible detail and buffers; measure qualified resource budget, not arbitrary speed claims | LF-V2 / I,B |
| LF-T069 | Scheduler encounters daylight-saving change or missed/overlapping run | Existing scheduler owns explicit policy; GUI does not invent second timing or replay logic | LF-STUDIO / I,P |
| LF-T070 | CI is green and source merged but deployment/proof is absent | Preserve built/not-proven distinction; no shipped or fully autonomous badge | LF-V1 / U,B,P |
| LF-T071 | A proposed/deprecated adjacent PR claims a current gate | Reconcile live metadata and protected supersession; do not revive terminal #424 | LF-F0 / source inspection |
| LF-T072 | Sustained interval has token activity but no useful accepted outcome | Fail product acceptance; measure useful completion and Chairman labor, not activity volume | LF-FLEET / P |

## Evidence requirements for recording a pass

For each applicable row, retain the exact test or live input, positive control, source/head and artifact generation, host/client qualification when needed, actual observed output, effect count and evidence location. A failed or blocked run retains its real result. A source-only pass never advances a P-level obligation. The abstract two-client experiment in the design-review companion motivates LF-T025 but does not satisfy it.
