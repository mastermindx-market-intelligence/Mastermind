# Web-Sol production reliability, effort and recovery amendment

Date: 2026-08-30
Owner: Sol, AI CEO, under the Chairman's current direct Web-Sol production commission.
Workstream: existing WS:CHAIRMAN-CONTROL-ROOM. Projection: MAS-198.
Architecture carrier: existing Mastermind #188. Implementation plan: existing #212.
Implementation baseline: #219 / sol/wsx-s0s1-web-sol-20260829 / 244cca58abd71254738424251cc6182ea64da0e2.
Procedure snapshot: protected Mastermind fefd774701ea285b466cac2646a584801f4a976a, mastermind.sol_skillpack.v1 1.0.1, bootstrap major 1.
State of this document: architectural ruling and implementation contract; not installation, production proof or permission to impersonate a provider capability.

## 1. Outcome and precedence

The Chairman must be able to operate a fleet of already-authorized Web Sol reasoning surfaces without hunting windows, repairing lost watchers, accidentally interrupting a long reasoning run or losing the organizational context when a conversation reaches its usable limit.

The machine outcome is a real worker return producing canonical Sol attention, resolution of exactly one current Sol target, truthful cockpit health, an eligible bounded recovery/wake, canonical context rehydration, a governed Sol action and an explicit continuation or terminal boundary. Extension installation alone is not completion.

This amendment supersedes only the earlier Web-Sol clauses concerning a single fixed socket, absence of infrastructure reconnection, S0 detector precision, the earlier isolated one-profile proof sequence, and future S2/S3/effort/successor implementation eligibility. It does not change Executive, Agent OS, Wake, Capacity, Session Truth, RuntimeBinding, Steward, provider or organizational authority ownership. Other #188 Secretary/OpenClaw work retains its own owner and release boundaries. #228 Steward files and other active autonomy paths are not part of #219.

The current Chairman approved end-to-end planning and build, budgeted high-effort runs and dead-chat recovery, while asking to remove unnecessary ceremony. Consequently, implementation and ordinary engineering verification may advance together; no sequence of separate parked proof-only children is required. Real host permissions, provider compatibility, exact-target safety and truthful production proof remain necessary facts, not paperwork.

## 2. One system and threat boundary

Executive OS owns Job/Attempt/Worker/Event state and admission. Agent OS owns durable workstream decisions/discoveries/handoffs. GitHub owns implementation and evidence. Existing Capacity owns entitlements and scarce-cognition budget. Existing target/continuity owners choose or transfer the single action-authoritative Sol. Existing surface_bindings remains navigation-only. OCR-6/Steward consumes surface facts; it does not infer organizational truth from a tab.

The extension is a narrow installed adapter, not an organization, transcript exporter, general browser agent, scheduler of company work or second memory store. It must not export transcript/model output, cookies, provider storage, clipboard, browser-fingerprint data, credentials or arbitrary DOM. It must not expose caller-authored JavaScript, selectors, URLs, shell arguments, click/type primitives or hidden provider endpoints.

Native messaging origin validation authenticates an allowed installed extension identity; it does not cryptographically attest which managed profile launched it. Profile routing additionally relies on a trusted, exact-profile installation/readback and immutable profile-local deployment configuration. Receipts must not call a self-reported profile identifier independent profile attestation. Copying a deployment into another profile is unsupported; duplicate live instance ownership fails closed and installer/readback proof must detect wrong-profile installation. A later stronger vendor attestation may extend the existing binding seam, never invent a browser identity authority.

## 3. Fleet transport and installation

Derive adapter_instance_id deterministically from the existing managed environment coordinate (vendor plus the canonical folder/profile identifiers), with a versioned canonical byte representation and full SHA-256 digest. This is a routing derivative, not a new registry or identity. Do not derive it from title, recency, account guesses or transcript similarity.

Use one native-host process/transport endpoint per provisioned managed environment. A generated private executable wrapper fixes its expected instance ID; a matching profile-local extension deployment fixes the native host name and the same ID. The host never chooses a socket, executable, profile or filesystem path from an untrusted HELLO/request. The Python client derives the expected instance from the already-resolved canonical binding.

Use a short private user-local socket directory and deterministic bounded leaf. Validate the actual encoded path against the installed OS AF_UNIX limit. Full instance identity is validated in the handshake even if a shortened digest is used in the filesystem leaf. Parent and socket ownership/mode, symlink/refusal, same-user peer policy and inode-safe cleanup must be tested. A host may not unlink another live or replacement host's socket. No TCP/HTTP listener, persistent queue, action mailbox, discovery daemon or alternate socket fallback is introduced.

A closed HELLO/HELLO_ACK negotiates protocol major, package versions, expected instance ID, transport boot nonce and capability digest before actions are allowed. Version mismatch remains unavailable, not silently downgraded. Installation artifacts are generated from the reviewed release and existing binding; secrets/private profile coordinates do not enter Git or public logs. Installation has dry-run, exact-profile apply/readback and rollback of the adapter's own artifacts only. It does not change proxy/account/auth/managed-browser settings unrelated to extension assignment and native-host discovery.

The deployment validation must include two simultaneous approved non-sensitive managed profiles. A successful single-profile run cannot establish fleet support. Vendor-specific support is labelled accurately; Mimic proof is not automatically Orbita proof.

## 4. Transport reconstitution is not effect retry

The MV3 service worker may restart. On startup, activation and a valid reconnection it rebuilds volatile mappings using only exact ChatGPT hosts in its own profile, and records fresh top-frame probes. Route changes and moved/removed/replaced tabs invalidate prior mappings. A fresh probe that observes a new exact conversation updates the local mapping rather than leaving it stranded under its old fingerprint.

A single bounded infrastructure reconnection mechanism may restore the same provisioned native port with backoff. It carries no company operation state, may not select another host/profile and may never replay a modifying action. Avoid a tight reconnect loop when the host is absent. Browser/service-worker/native-host restarts must preserve all canonical company facts and must not submit, reload or foreground anything merely because a transport connected.

Every frame read/write has an end-to-end monotonic deadline, byte ceiling, closed JSON schema and duplicate-key refusal. A partial frame must not hold the host forever. Malformed/slow clients must not destroy healthy future service. Bound concurrency and return a typed busy/unavailable result; no durable waiting queue. Write complete frames or return an error with correct effect uncertainty.

After bytes for a modifying request may have crossed the actuation boundary, disconnect, malformed acknowledgement, timeout or process death is EFFECT_UNKNOWN unless the existing canonical effect owner proves otherwise. Volatile deduplication is useful within one boot but is not a durable exactly-once guarantee. A new boot refuses old boot-bound work. Cross-boot reconciliation belongs to the existing Wake/actuation owner, not a new extension ledger.

## 5. Exact targeting, clocks and receipt truth

Use binding_fingerprint as the explicit navigation concurrency token. The prototype constant binding_revision=0 is not a real source revision and must not be represented as one. A versioned protocol transition may remove that field; no fake binding epoch is added to surface_bindings. Actual responsibility/runtime authority epochs stay with their existing owners.

The host/client re-read the existing binding at the appropriate pre-actuation boundary. Changed/deleted/conflicting bindings refuse before effect when observable; an after-effect drift must report uncertainty rather than claim a no-effect refusal. Conversation fingerprint, instance ID, operation identity, nonce, boot and binding token must agree end to end.

Validate issued_at/expires_at against an injected wall-clock at admission and immediately before actuation; use a separate monotonic elapsed deadline for transport. Bound future skew and total TTL. Expired, future, malformed, mismatched and replayed requests have deterministic typed outcomes. Clock adjustments or host sleep do not refresh old observations.

FOREGROUNDED_VERIFIED requires readback that the exact tab is active, its current window is focused and the fresh exact conversation still matches. A successful update call or visible content probe alone is insufficient. Re-read the tab's current window rather than trust a pre-move cached window ID. Ambiguous duplicate targets never select a winner.

## 6. Health and long-run classification

Keep observations and conclusions separate. At minimum observe extension/native transport availability, fresh probe response, exact route, document lifecycle, browser frozen/discarded metadata when supported, composer presence/usability, active generation, explicit provider/auth/network/limit UI states, detector version, observation time and probe latency. Unsupported observations are null/unknown. A content script response proves that probe executed; it does not prove the provider backend is progressing.

Use versioned deterministic detectors constrained to application chrome/status controls. They may read only the minimum bounded UI status needed to classify known errors/limits; no transcript text or broad document text extraction. Hidden/disabled controls do not prove an available composer. Missing selectors produce UNKNOWN rather than a false healthy/idle state. Unknown UI shapes do not trigger repair.

Distinguish RESPONSIVE_IDLE, GENERATING, LONG_RUNNING, UNRESPONSIVE, FROZEN, DISCARDED, CONTEXT_LIMIT_REACHED, AUTH_REQUIRED, PROVIDER_ERROR, NETWORK_ERROR, TARGET_MISSING, AMBIGUOUS_TARGET and UNKNOWN using supporting evidence. CONTEXT_LIMIT_REACHED requires explicit supported provider UI evidence, not a turn-count guess. OOM_CONFIRMED requires actual supported browser/host crash evidence; otherwise use UNRESPONSIVE or SUSPECTED_RESOURCE_FAILURE and retain uncertainty. A timer alone cannot diagnose OOM, completion or a dead reasoning run.

Separate renderer liveness, provider generation activity and canonical organizational progress. A healthy long Pro run must not be reloaded or duplicated because it has no recent transcript mutation or MCP checkpoint. Stuck suspicion uses the authorized effort profile plus corroborating stale/liveness/error evidence and leads to a governed decision, not autonomous cancellation. Host sleep/offline periods are explicitly distinguished from provider failure.

## 7. Scarce high-effort cognition

Support a requested effort class such as STANDARD or PRO_DEEP through the existing Capacity/cognition routing owner. Do not hardcode monthly entitlements from chat prose, presume all Business plans expose the same model, or treat ChatGPT Pro subscription, model selection and thinking-effort selection as the same setting.

Before a paid/scarce effort run: resolve the actual supported model/effort controls for the exact enrolled surface, consult current entitlement/budget evidence, reserve once against the canonical logical run and construct a complete source-referenced mission brief. If availability or balance is unknown, remain explicit; do not switch accounts, purchase credits or silently substitute a metered API. The existing CHAT_PRO_DEFAULT/METERED_EXCEPTION law remains governing where accepted.

The brief asks for sustained substantive research/architecture/execution, rich relevant context, adversarial review, durable checkpoints when tools are available and a truthful completion/continuation receipt. The Chairman's 60–120 minute preference is a work-budget/grace intention, not a guaranteed provider duration or a reason to idle, pad tokens or continue after the outcome is complete. A prompt cannot force provider runtime or bypass provider limits. The adapter records requested versus actually observed mode separately.

Budget accounting, reservations and consumption survive cockpit rotation through existing owners. The extension stores no quota ledger. A lost submit receipt does not consume another reservation or trigger another Pro run. Large context travels through canonical context bundles and read tools, not an unbounded browser payload or transcript scraping.

## 8. S2 bounded same-surface repair

After current S0/S1 release proof, implement only closed operations such as RELOAD_EXACT_SURFACE and, where the real browser supports a verified contract, REOPEN_EXACT_BOUND_SURFACE. No caller-supplied URL or generic navigation primitive is exposed.

Before repair, verify the current exact target and authority, evidence supporting the repair, and whether generation/human input could be interrupted. A user draft or active healthy generation blocks automatic reload. A missing draft observation is not an empty draft. Escalate auth/rate-limit/account restrictions rather than bypass them. Repair budgets and decisions belong to existing owners; the extension executes one accepted action and returns a sanitized before/effect/after receipt. Partial/ambiguous repair never causes an automatic second action.

## 9. S3 bounded semantic wake

Implement WAKE_SOL as one Mastermind-authored semantic event for one current surface and canonical attention reference. The owner checks that attention is still owed and the Sol responsibility/epoch is current immediately before commit. The exact enrolled extension checks target identity, usable composer, no conflicting human draft, allowed model/effort, no active generation and no auth/provider restriction.

The browser message uses a fixed versioned wake template plus bounded canonical references/opaque correlation only. It cannot accept arbitrary prompt text from a model/tool caller. Sol must fetch current Skillpack, Executive/Agent OS/GitHub/dialogue state before acting. A wake is not authority to create or repeat underlying work.

Separate attempted input, submit-boundary crossed, provider generation observed, Sol canonical ACK and underlying source resolved. Composer clearing or spinner appearance alone is not canonical ACK. If submit might have occurred, preserve EFFECT_UNKNOWN and reconcile through the existing Wake owner; never press send again based on a timeout or start a replacement Pro run. Respect supported provider interfaces and service limits; no hidden endpoints or output harvesting.

## 10. Successor chat recovery

Keep a versioned continuation capsule in the existing Agent OS handoff/Executive context flow: original outcome, current responsibility and authority epoch, exact operation/carrier, source revisions, material decisions, result/effect reconciliation, outstanding worker returns, next action and capability ledger. GitHub holds full architecture/research. The capsule contains useful decisions and evidence, never private chain-of-thought or a second conversation database.

On explicit context exhaustion, irrecoverable surface failure or deliberate rotation, the existing continuity owner first reconciles any in-flight effect and fences the predecessor's modifying authority. Only then may an admitted exact replacement surface be provisioned, initialized with canonical capsule references and separately bound/ACKed. Preserve the old chat as read-only history; do not delete it or copy its entire transcript. One logical responsibility remains current and stale predecessor wake/action requests refuse.

A new chat must not be told that it can necessarily read an inaccessible predecessor transcript. It recovers durable company facts through supported tools; provider project memory or prior-chat references are supplementary only when actually available. Missing uncheckpointed facts are reported as context gaps. Recovery must not fabricate decisions or replay an uncertain operation. New-chat creation, project selection and final binding have explicit postconditions and ambiguous effects are reconciled before any repeat creation.

## 11. Product surface and release ruler

Expose the useful surface through the existing Control Room/Steward projection and a small profile-local diagnostic popup, not a second fleet dashboard database. Show exact enrolled instance, adapter version/compatibility, observation age, health evidence, requested/observed effort, canonical attention when supplied by its owner, and one eligible action or clear blocker. UNKNOWN must look different from idle. Provide a local pause/disarm and adapter-only diagnostics/rollback path; do not expose private URLs or credentials.

Release progression is: deterministic tests and real JS behavior tests; two-profile native/browser integration; one approved target installation with exact readback; a real worker-return-to-Sol action journey; limited fleet rollout with rollback; actual recovery/long-run proof. Consolidate these into the deployment wave and automate repeatable checks. Do not require a separate committee, permanent watcher or records-only PR per test. A provider-specific or permission blocker holds only the affected action/surface, not disjoint engineering.

Production is accepted only when actual installed code/version, target safety, recovery behavior and the real consumer journey are evidenced. Green CI, source merge, Slack delivery and an installed extension remain distinct. Record exact capability deltas and remaining limitations in #219/#212 and the existing Agent OS handoff so another Sol can continue without this conversation.
