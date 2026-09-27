# Browser reconciliation recovery implementation plan

**Goal:** Read the existing durable result for one exact browser action after its execution capability expires or its owned process retires, without reopening execution authority.

**Architecture:** Preserve BrowserActionPort, BrowserRefCodec, and ActionArtifactStore. Separate read-only historical receipt resolution from live browser dispatch validation. Authentication and exact owner/project/action binding remain mandatory; no new ledger, browser owner, or retry route.

**Tech stack:** Existing Python 3.12 Workbench browser companion.

**Scope:** integrations/workbench_browser_mcp/browser_port.py and tests/test_workbench_browser_port.py on immutable #940 head b2fdb1d1d1584a53c5ac1f94e2da1c1fa7be9200. This workspace is an isolated repair proposal; no incumbent branch custody is assumed.

**Protected procedure:** fda6ed3911cdda24eb63b2ccbe1b174121cf404f; Skillpack 1.0.1/bootstrap 1.

## Constraints and review focus

- Execution still requires fresh browser/action references and exact live process identity.
- Reconciliation authenticates both signed references, their mutual digest binding, and the current caller/owner/project/host binding.
- Expired caller or owner scope never becomes a historical-receipt authorization.
- An unresolved prior effect remains EFFECT_UNKNOWN; read-only reconciliation never calls the relay.
- Wrong caller, owner generation, host, or tampered reference still refuses.
- Host reboot, owner-generation replacement, egress policy and login readiness are separate integration work, not silently accepted here.

## Task 1 — recover durable receipts after execution expiry/process retirement

- [ ] Add parameterized expiry/dead-process tests for APPLIED, NOT_APPLIED and EFFECT_UNKNOWN, asserting no second relay dispatch.
- [ ] Run the new tests against unchanged source and preserve the failing output.
- [ ] Add the smallest read-only historical validation path; leave live dispatch validation strict.
- [ ] Add refusal tests for tampering, changed owner/caller, expired authentication/scope, and attempts to execute old references.
- [ ] Run the focused owning module and complete browser suite in the repository-pinned test environment.
- [ ] Preserve exact diff, source hashes and test receipts; return the proposal to #940 without claiming release or runtime acceptance.

## Task 2 — investigate unresolved-effect barriers

Use the existing action artifact owner to test whether preparing a new action while an earlier browser action is uncertain can dispatch twice. Any repair must remain within that existing owner; do not add a parallel operation journal.

## Initial capability/collision ledger

#473 exact source review approved; Rust analyzer failed and release remains held. #940 has no submitted review. #663/#988 remain unreleased. The connected C3 Workbench exposes canary file/command actions only, no browser actions. GitHub owner-app search resolves to #409; no successor found in the bounded exact-name search. No production profile, credentials, service or browser process changed. A separate source-map inspection call was safety-blocked and is not retried through another carrier. No effect uncertainty exists for this session's own operations.

## Executed source checkpoint

- Original five-module core baseline: 42 PASS.
- Nine expiry/process-retirement cases on unchanged production source: 9 FAIL, expected closed browser/action/process refusal paths, zero collection errors.
- Minimal historical-receipt recovery repair: original six plus new nine tests PASS.
- Seven additional wrong-identity/tampering/current-auth temporal cases added.
- Complete nine-module Browser suite: 81 PASS; XML and stdout retained in the operation evidence root.
- Full repository pytest attempted: collection stopped with two errors, `tests/test_self_tune.py` (missing vendored `engine.signal_archive`) and `tests/test_single_name_factor.py` (missing vendored `lib`). No full-repository pass claimed.
- Independent resource-uncertainty probes: 2 FAIL. A second freshly minted action_ref dispatches again on the same browser after the first action is EFFECT_UNKNOWN, whether prepared before or after the first lost reply. Synthetic relay call count is 2, expected 1. The current read-only reconciliation repair does not change prepare/run behavior and does not fix this blocker.
- Preserve the existing action/effect owner. A durable resource-wide uncertainty barrier is required before authenticated activation; an in-memory flag, fresh operation ID, or another ledger is not acceptance.
- No production browser/profile/credential use, installation, remote source push or merge occurred. This is a source repair candidate, not an independently approved release.

Evidence root: `/Volumes/Mastermind/evidence/browser-continuity-convergence-20260927-astra-001`.

## R2 — durable prior-effect fence (2026-09-27)

Fresh protected procedure pin: `429bf720788f8c68e76a576b7b3fedd8f8ad423a`; INDEX/Cold Start/Active Execution/Web CEO Delegation/Delivery/AGENTS fetched from this exact commit and unchanged from the prior pin. Owned source remains `4aecefb7fc08bb21ff575cc7a1b3b5ef492b29da`, clean, same workspace. No new #940 return since checkpoint5852810158.

Bounded implementation choice: reuse the existing descriptor-owned ActionArtifactStore claim/result evidence and writer mutex, not a new ledger or an Executive database transplanted into attended Workbench. The earlier continuation's generic Executive/OHF composition wording applies to the future worker projection; it does not replace #940's attended effect owner. The existing Fleet renewal guard already treats unresolved store evidence as a renewal barrier. Strengthen the owning artifact API to provide a bounded descriptor-based terminal-evidence check, then consume it before NEW Browser actions/resources. Original-action reconciliation and safe historical replay stay readable. Gate destructive owner cleanup under the same writer mutex so a caller-supplied APPLIED flag cannot erase unresolved evidence.

The fence is intentionally conservative across this one exclusive Workbench artifact store. It persists across reconstructed port objects/service restart and newly minted resource/action references because it reads original durable records; it creates no files, new state schema, retry budget, registry, or queue. Cross-store/host/profile continuity still belongs to existing resource/profile admission and must be production-proven later; this local fence does not claim global cross-host authority.

Tests: two already-known fresh-ID cases; reconstructed port/store; second resource; positive sequential terminal actions; original unknown reconciliation; malformed/orphan/foreign/oversized evidence; writer contention; cleanup refusal. Bound the evidence scan and refuse overflow; never turn a partial scan into clear. All new effects in this slice are synthetic tests and source changes only.

Direct principal work rationale: PRINCIPAL_JUDGMENT for effect-owner adjudication, then LOWER_TOTAL_OVERHEAD for this bounded existing-owner repair. No worker is started, no Fable capacity consumed, no production browser or credential accessed. Prior safety-denied source-map/evidence-packaging operations remain unretired and are not retried.

### R2 implemented and tested

- New action/resource discriminator campaign BEFORE the fence: 14 FAIL / 2 PASS. The two controls prove normal terminal actions remain usable.
- Separate cleanup discriminator BEFORE cleanup integration: 1 FAIL (`released=True` despite a durable unresolved claim).
- Final Browser plus entire Workbench Action matrix: **446 PASS / 1 SKIP**, exit0, in `r2-final-browser.log` / `r2-final-browser.xml` in the existing evidence root. The skip is inherited; no full-repository acceptance is claimed.
- Focused durable fence/action/resource matrix: 58 PASS, including a fresh Python process reopening the original pending claim, repeated inventory reads, malformed/mismatched/foreign-store/unknown/symlink/oversized evidence, bounded-scan exhaustion and held-writer validation.
- Issuance refuses with `PRIOR_EFFECT_UNRESOLVED` before creating a replacement claim or dispatching. The original action can still reconcile. Owner-requested destructive cleanup now consumes durable evidence under the same writer mutex, rather than trusting a caller APPLIED flag.
- All evidence and tests are synthetic; no real browser, credentials or remote website were exercised. No record schema, persistent barrier file, index, queue, retry plane or new effect owner was added.

Remaining release/production obligations: independent review and incumbent #940 adoption; cross-store/profile/host admission and durable resource binding; relay self-retirement on parent loss/expiry remains a SEPARATE existing lifecycle path and has not acquired this store fence. Do not claim R2 prevents that automatic path from retiring an uncertain target. One useful real authenticated workflow and persistent-login proof remain owed. The prior full-repository collection blockers (`engine.signal_archive`, `lib`) are unchanged and were not rerun as another failure cycle.

Writer-gate lane: #409's exact branch still resolves to `55155d33a51921a3b6d2cae2db49d31703a80b8a`. Current source already owns bounded writer facts and repeated/conditional observation in `scripts/source_continuity.py::_run_writer_gate`; the existing GitHub app owns authenticated principal and installation-token provider protocols. A service extension should reuse these rather than copy the verifier/acquisition logic or route through human gh. Official GitHub REST branch-protection documentation confirms Administration(read) for GET and Administration(write) only for mutation; no live permission change or credential read occurred.

## R3 — automatic retirement retains uncertain targets

Current procedure pin: Mastermind `d7c949d31f3893d95822a4ee8e5e4be9edaf5593`, compatible Skillpack 1.0.1/bootstrap1. Current source `cd7df55e`; protected movement since `429bf720` is Executive MCP/application code, not the owned Browser/Action paths. Same registered workspace and current Chairman continuation; no active child or unknown modifying effect is displaced. Direct execution reason: PRINCIPAL_JUDGMENT for the retention/admission boundary, then LOWER_TOTAL_OVERHEAD for its bounded repair.

Design: auto expiry or parent loss closes relay tool admission permanently for that process. Destructive retirement must consume the same existing ActionArtifactStore terminal-evidence fence and hold its writer mutex through child close. Unknown, missing, malformed or busy evidence retains the original target; no replacement browser or effect record is created. The parent passes only its already-owned store descriptor and exact identity to its relay, never to the Playwright child. The existing relay loop may re-evaluate when owner evidence changes; a cached refusal is not a cached permission. Explicit owner-requested cleanup remains R2's separately fenced path.

Tests first: retained-target behavior after parent loss/expiry, expiry during request handling, original resource evidence required, response-write loss must not destroy target, inherited-fd launch composition, terminal-evidence retirement and restart/same-store negative cases. Preserve existing exact peer PID and schema/effect boundaries. No credential/profile enrollment or production activation is authorized by source tests.

### R3 verified implementation frontier

- Automatic expiry/parent loss now closes tool admission permanently for the exact relay process and consumes an injected ArtifactRetirementGuard over the existing descriptor-owned ActionArtifactStore. The original browser_resource claim is required; an empty or substituted store cannot prove cleanup safe.
- The existing resource launcher carries the owner-selected store fd/device/inode to its relay. The relay seals that fd before spawning its MCP child. No path/credential selector or new record schema is model-visible.
- Positive retirement proof is always fresh and its writer mutex remains held through child close. Only negative results may be cached against directory-generation metadata; new append-only owner evidence triggers another read. A busy writer causes retention, not waiting under another lock or permission to retire.
- Reply-write loss is connection-local: it closes further tool admission and preserves the original child instead of unwinding into destructive cleanup. Already-expired/orphaned authority refuses before native startup, and expiry is checked again at tool dispatch.
- Behavioral RED: four auto-retention/late-dispatch/lost-reply cases failed before repair; two pre-start authority cases failed before their repair. The initial test run also had two missing-test-import errors, corrected before the four-case RED claim. Six adapter cases and one launch-interface case initially exposed absent APIs, not six additional production bugs.
- Actual native proof uses the real relay main, real parent and MCP Python processes, and synthetic MCP catalog/owner artifacts. Parent termination and real deadline expiry both preserve the exact original native child while a claim is pending; finalizing that same synthetic action through the owner retires it. The native child observes no inherited owner-store descriptor. Two cases PASS. Fixture setup errors (helper argv index and required entrypoint path) were diagnosed/corrected; no production guard was removed.
- Final Browser plus complete Workbench Action matrix: **462 PASS / 1 inherited SKIP / 0 FAIL / 0 ERROR**, exit0. Exact log/XML: `r3-final.log` and `r3-final.xml` in the existing operation evidence root. `git diff --check` PASS. Prior whole-repository missing vendored `engine.signal_archive` and `lib` collection errors remain; no full-repository/hosted green claim is made.
- Current C3 Workbench live manifest still advertises only attended F0 canary file/command actions, with `network_call=false`; it is not Browser or writer-gate deployment. No new relevant #940/#409 comments were observed after the prior cumulative checkpoint.
- Unchanged release limits: this is same-store automatic-lifetime and connection-loss source proof, not cross-store/profile/host admission, protection from OS-forced termination, network-policy acceptance, credential enrollment, or authenticated UI proof. Explicit owner-requested process cleanup remains R2's separately guarded route. No real browser, provider, installation or credential effect occurred.

R3 final review refinement: a lost read-only status/refusal reply does not quarantine an unmodified resource; only a lost possible-native-effect reply closes tool admission. Its discriminator failed before the refinement. Final rerun supersedes the intermediate 462-test count: **463 PASS / 1 inherited SKIP / 0 FAIL / 0 ERROR**, exit0, in `r3-release-candidate.log/.xml`; diff check PASS. Retained pages continue their own site behavior; closing tool admission does not claim to suspend webpage timers or network activity. Network/target confinement remains a separate production gate.

Action-time protected source advanced to `b2e0b905bfac975766afda3cf65527897bc0e25a`. Fresh INDEX is still 1.0.1/bootstrap1; COLD_START, ACTIVE_EXECUTION, WEB_CEO_DELEGATION, DELIVERY_WORKFLOW, REVIEW_RETURN and CLOSEOUT blobs are identical to the pinned `d7c949d3` versions. The intervening changes are Paper/Studio integration source, not Browser/Action semantics. Typed source publication status freshly reports the existing local/remote `cd7df55e` and this operation's uncommitted R3 delta only; no ambiguous prior effect is present.
