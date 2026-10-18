# Mastermind Executive Ecosystem — integrated programme plan (2026-10-17)

**Programme:** Executive Ecosystem Completion (Chairman brief 2026-10-17 "FABLE CEO META — Executive
Ecosystem Completion Mission"). **Seat:** Fable Meta-CEO, Claude session `873aabd3`, holding the Chairman's
programme delegation for this scope. **Ledger:** `research/EXECUTIVE_ECOSYSTEM_COMPLETION_CAPABILITY_LEDGER_2026-10-17.md`
(row IDs `E*` runtime, `F*` fabric/capacity, `G*` gateway/edge, `A*` app, `C*` continuity, `H*` journeys are cited
below). **Continuity:** macro `agentos/workstreams/WS-EXECUTIVE-ECOSYSTEM-COMPLETION.md` + dated handoffs.
**Prior plan this extends, never replaces:** `research/mastermind_meta_ceo_master_plan_r2_2026-10-12.md` (R2) and
macro `WS:EXECUTIVE-AUTONOMY-V1-CLOSURE` waves P4/P5, whose DONE_WHEN journey is this programme's `H1`.

DONE_WHEN (brief, restated): one real Chairman-originated request completes the multi-level path with
authenticated identity, correct source custody, valid admission, economical routing, retained results, actual
review, original-parent consumption, recoverable continuation and a coherent Mastermind OS outcome; both a
successful and an interrupted journey are proven. Census, architecture, a merged PR, green CI, one worker run or a
dashboard demo are rungs, not the outcome.

## 1. Architecture (Phase B) — ownership preserved, nothing duplicated

| Concern | Owner (existing) | Where it lives | This programme may… | …and never |
| --- | --- | --- | --- | --- |
| Runtime, admission, lifecycle, retained results, recovery | **Executive OS** | `control_plane/`, launchd `com.mastermind.executive.*`, `/var/db/mastermind-executive/control/db` | operate it through `ops/executive_os/*.sh` (root) and the authenticated gateway | add a queue, retry loop, second lifecycle store or raw-socket submitter |
| Arms and release acceptance | Executive OS (`autonomy-control.sh`, `acceptance.sh`, `acceptance_maintenance.py`) | installed release root | run the prepared acceptance and arm sequence under review | hand-edit `config/*.json`, reset predicates, fake a receipt |
| Worker placement, quotas, providers | **Capacity / Model Router** (`worker_quota_classes`, `provider-readiness*.json`, Fabric `pools.yaml`/`pick.py`) | installed config + Fabric kit | request placement; read quota state | edit `pools.yaml`, `pick.py`, `RELAUNCH_QUEUE.txt`, or multiply allowances |
| Continuity | **Agent OS** (macro `agentos/`) | workstream + handoffs + decisions/discoveries | write records through PRs | treat a record as liveness; hand-edit generated views |
| Source and proof | **GitHub** (Mastermind master `a552a5e5`, macro main) | PRs behind green checks | ship reviewed PRs | push to protected branches; replace Sol's open lanes |
| Portfolio projection | **Linear** (owner-run) | programme issue | report ledger deltas to the owner | mint a second projection store |
| Transport | **Slack** (agent-relay, sol-state-relay, dialogue bridge) | relays @`326c8469` | use dialogue canary via `autonomy-control.sh` | add a parallel relay |
| Session identity / RuntimeBinding | ChatGPT Web CEO root chats, Studio Direct, Claude seat (read scope only) | installed bindings | act under the identity the installed runtime recognises | enroll Fable with `intent.submit` (`REJECTED_BY_DESIGN`, G8) |
| Human interface | **Mastermind OS** (`app/mastermind_os/`, web + Tauri) | served `/os/`, release receipts | prove journeys with authenticated live data | substitute an inert preview or read-only transcript |

### 1.1 The multi-level path one Chairman request must traverse

Chairman (app, A3) → `POST /os/executive/submit` (G3, needs install) → gateway inner `submit_ceo_intent`
(G1/E3) → **`ceo_submit` arm** (E4) → root Job under the Web-CEO original root → **COO autonomy** (E5)
decomposes → planner child under a sealed grant (E9) → worker placement on `codex-01` / native Claude / Fabric
bridge (E12, F1, F3, F5) → retained `result_json` → review Job (`reviews_job_id`, H3) → **consumption by the
original parent** → `ceo_intent_status` → app renders the outcome (A3) → Agent OS handoff (C1). Interruption
anywhere must reconcile on the same carrier (E2 at process level, A4 at submit level) without a second root.

### 1.2 Architecture decisions (programme-local; recorded here, cited from Agent OS)

- **PD-1 Shallowest hierarchy.** A routine request goes Chairman → CEO ingress → worker. COO decomposition is used
  only when the request has ≥2 independent children or needs a review child. Opus suborchestrators administer a
  *lane*, never a single packet; native Claude children are not labour (routing law).
- **PD-2 One acceptance lineage.** The installed `91c1cac5` acceptance is the prepared
  `supersede_unstarted_v1` bundle (predecessor `25c4b792`, superseded unstarted `84c8a09d`, root `JOB-003`,
  terminal `JOB-006` carried, template proof `JOB-024`, worker `codex-01`, quota `codex-native`). It is **recovered,
  not re-prepared**. Any re-preparation is a material invalidator decision for the production owner.
- **PD-3 Historical roots are consumed or dispositioned, never replaced.** `JOB-003` is bound into PD-2;
  `JOB-013` and `JOB-002` are consumed through their original parents after arming or receive a recorded lawful
  disposition. No new root with the same objective (E8).
- **PD-4 Arming is a reviewed security change.** `ceo-submit-arm` and `arm` get one proportionate independent
  review (read-only Opus audit of predicates, coexistence law and roll-back) before execution; the review repairs
  only what changes.
- **PD-5 The app command path is installed, not emulated.** G3/G4 go live only through the runbook install
  (`os_executive_transport`, `os_executive_resource`, `os_commission_port`, root-sealed Studio opt-in). The app
  never gets a mock transport to "demo" a journey.
- **PD-6 Budgets and roots are conserved.** Every child of a programme root carries the root's effective grant
  digest; Fabric descendants keep the original root identity; no allowance is summed across sessions.
- **PD-7 Agent OS claims are not liveness.** The P4 "PICKED_UP by chat `01a1230a`" record is historical; the
  acceptance operation is recovered by this seat under PD-2 unless a live START is observed first.

## 2. Lanes and commissions (Phase C)

Execution model: the **seat** performs host-effectful and judgment steps directly (it holds sudo, custody and
the Chairman delegation); **independent read-only Opus audits** gate PD-4 changes; **Fabric workers** take
separable source/test/doc labour when framing+review cost less than direct execution; the **production owner**
(install lane: Sol/codex01 via `install.sh`) confirms install/readiness separately. Every commission below is
bounded by SCOPE / IDENTITY / ACCEPTANCE / RETURN / NON-GOALS.

R1 CORRECTION 2 note (2026-10-17 13:5xZ, seat 873aabd3): "confirms install/readiness separately" is not reachable today — the live `provider-readiness-v2.json` is FAILED (`provider_turn_failed`, observed 2026-10-12T07:08:21Z), every automated requalification route refuses on it, and readiness returns only after the human credential rotation in "Human gate (Lane R)" below, followed by one seat-run `--verify-ready`.

### Lane R — Runtime (Executive OS host). Owner: seat. Suborchestrator: none (host effects stay with the seat).

| ID | Commission | Scope | Identity | Acceptance (falsifiable) | Return | Non-goals |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | **Recover the prepared `91c1cac5` acceptance** (E6, PD-2) | read `acceptance.py` preconditions (quiescence, backup, worker availability); enable what the acceptance itself requires; run `acceptance.sh` as root against the prepared bundle | seat (root), release `91c1cac5` | receipt dir `/var/db/mastermind-executive/control/acceptance/91c1cac5…` with `acceptance-summary.json` valid; `autonomy-state-v1.json` `acceptance_passed true` | ledger E6 → `PROVEN_LIVE`; handoff entry | re-prepare; touch `config/*.json`; a second proof Job |
| R2 | **Arm `ceo_submit` and COO/operator harness** (E4, E5, PD-4) | `autonomy-control.sh ceo-submit-arm` then `arm --expected-sha 91c1cac5…` after R1 and F1 predicates | seat (root) after Opus read-only audit | `ceo-submit-state-v1.json` armed; `autonomy-state-v1.json` `ARMED`, all predicates true | ledger E4/E5 `PROVEN_LIVE`; audit return linked | arming without the audit; disabling the Web-CEO coexistence law |
| R3 | **Dispose historical roots** (E8, PD-3) | JOB-003 via PD-2; JOB-013 and JOB-002 placed once E5/F1 are live; else record a lawful cancel with reason through ingress | seat under the original roots' parents | each root COMPLETED-and-consumed or `cancel_requested_at_ms` + reason recorded; zero new roots for the same objective | ledger E8; inbox `job_failed`/unresolved counts | duplicate roots; editing rows directly |
| R4 | **Prove the planner-child grant repair** (E9, H6) | first planner child under the armed harness | runtime | a depth-1 Job reaches RUNNING with no `BrokerProtocolError`; JOB-006 remains the only FAILED row | ledger E9 `PROVEN_LIVE` | re-running JOB-006 |
| R5 | **Drain the attention inbox** (E10) | 19 `unresolved_next_actions` validation commands + 1 `job_failed` | seat via supervisor path | inbox count 0 or each item dispositioned | handoff | silencing items |
| R6 | **Refresh boot-packet macro grounding** (E11) | install-inputs macro source → current macro `main` ancestor through `install.sh` inputs (production owner) | production owner | inbox `grounding.macro_sha` current; no `boot packet not collected` | ledger E11 | hand-editing `control.json` |
| R7 | **Release coherence** (E7) | align relays/tunnel plists to one accepted release (next install) | production owner | all `com.mastermind.executive.*` resolve to the accepted SHA | ledger E7 | restarting services to "fix" labels |

R1 CORRECTION (2026-10-17 12:3xZ, seat 873aabd3): `validate_acceptance_source` (ops/executive_os/install_source_policy.py:128-142) is exact-protected-master only and explicitly 'does not gain the separate frozen-ancestor install mode'; it compares HEAD and the checkout's local refs/remotes/origin/master to the expected SHA. Mastermind master has moved past 91c1cac5 (head ad125292b34f313924f9719b8de772027f0ea225 at 11:28Z, 14/14 checks green), so the prepared 91c1cac5 acceptance can never PASS as prepared. The lawful path is docs/EXECUTIVE_ACCEPTANCE_SUPERSEDE_UNSTARTED.md: with control and worker.codex services stopped and all intake arms closed, run acceptance_maintenance.py --predecessor-sha 25c4b7923734392b1013afae179966985819d847 --successor-sha <current protected master head S> --root-job-id JOB-003 --carry-terminal-dispatch --supersede-unstarted-sha 91c1cac5a20a01f4bf1ac9e92e55613fd4640e1f --superseded-descriptor-sha256 cfd874e8b74070c65683ace4de9518a022b73c691ba1fc61c88e56efd9804ee2, install S with install.sh, then run acceptance.sh on S with --maintenance-descriptor-sha256 <printed digest>. Preconditions observed 12:2xZ: config/control.json proof_base_sha = 91c1cac5; autonomy status control_armed=false, worker_armed=false, CEO_SUBMIT_DISARMED; operator chriswong is the sole _mastermind_ops member; JOB-003 is QUEUED, orchestration_role aggregation, depth 0, attempt_count 0, no parent; JOB-013 is a second queued root (attempt_count 0); all 33 attempts terminal (11 LOST = 'process identity absent during supervisor restart', each requeued and completed); the 91c1cac5 bundle holds exactly baseline.json, descriptor.json, inventory.json, preparing.json, prestate.sqlite3, prior-secret-canary.json; /var/db/mastermind-executive/control/acceptance has no 91c1cac5 entry. 91c1cac5 stays NOT_STARTED and its bundle is never edited. S is the master head observed at preparation time, never a stale pin. An independent read-only Opus review of this sequence is running; no host mutation happens before its verdict. This paragraph supersedes the earlier R1 wording.

R1 CORRECTION 2 (2026-10-17 13:5xZ, seat 873aabd3): facts observed read-only on the Mac Studio between 13:0xZ and 13:5xZ. (1) Readiness is FAILED, not merely expired. `/Library/Application Support/MastermindExecutive/config/provider-readiness-v2.json`: passed false, refusal provider_turn_failed, observed_at 2026-10-12T07:08:21Z, credential and readiness deadline 2026-10-12T08:07:01Z, expected_credential_kind device-auth. Inference canary: exit_code 1, timed_out false, result_valid false, model gpt-5.6-sol, codex 0.159.2, provider_error_terms ["capacity","model"], provider identity refusal none, forced workspace id not applied. The Oct 12 break was a provider capacity/model-availability turn failure, not an identity failure. (2) Receipt chain (superseded files): PASSING receipts were renewed about hourly by device revalidation from 2026-10-03T11:46Z through the last passing receipt observed 2026-10-12T04:30:43Z; the chain broke at the 07:08Z failed canary. No acceptance has run since 25c4b792 (2026-10-11 21:07Z) — the probable root of the 5-day stall. Personal-Pro: codex-pro-01 receipt FAILED process_failed 2026-10-09T04:28Z; codex-pro-02/03 passing receipts EXPIRED 2026-10-10T23:30Z. (3) Every automated requalification route REFUSES on the live failed receipt (classifier codes observed from the installed 91c1cac5 provider_readiness module): classify_device_revalidation, validate_revalidation_predecessor_document and classify_refresh_eligibility → readiness_receipt_not_passing; classify_terminal_requalification → requalification_identity_continuity_unproven (that route exists for the reviewed 0.147.0 → 0.159.2 upgrade only); classify_company_device_drift_requalification → drift_requalification_credential_changed; current-pin recovery needs /var/db/mastermind-executive/provider-recovery/current-pin/grant.json and the release ships no ordinary grant creator; ordinary reuse returns 2, so provision-worker-auth.sh dispatch fails closed (exit 65, "existing provider readiness receipt is stale or invalid"). (4) Slot codex-01 (provider_worker_slots.py): default_credential_kind service-account, workspace_binding_class company-workspace-admin-attested, oauth_seat_ref empty (no Multilogin seat), readiness_receipt = the file above. The Oct 3–12 chain therefore ran on the device-auth FALLBACK kind. (5) The ONLY lawful recovery is explicit credential rotation with an enrollment mode, which is an EXACT_HUMAN_GATE for the Chairman / production owner (the seat never runs logout/login); the two commands are in "Human gate (Lane R)" directly below. (6) Install retarget: #1571 merged, so the protected master head is ee0f0d9ba71d76dbc8144f56f3566a1f9dc70a71 (or newer at install time). The clean clone Mastermind-ad125292 and the os-web-assets/codex01-ad125292 bundle are STALE for ordinary install mode (install_source_policy requires checkout HEAD == local origin/master == expected sha). Successor S' = current master head with a FRESH clone, a fresh os_release_assets prepare and fresh install-inputs (dir 0700 root:wheel; control-before.json, control-successor-input.json, worker-before.json 0400; successor input = the live control.json with proof_base_sha → S' and proof_source_repository → /var/db/mastermind-executive/control/admin-checkout/S'). Sequencing after the human gate: clone → assets → install-inputs → service-control.sh stop (91c1) → acceptance_maintenance.py --predecessor-sha 25c4b7923734392b1013afae179966985819d847 --successor-sha S' --root-job-id JOB-003 --carry-terminal-dispatch --supersede-unstarted-sha 91c1cac5a20a01f4bf1ac9e92e55613fd4640e1f --superseded-descriptor-sha256 91695ef2a4e89f8ca8c7ff65950808a7d38069542d3551b15bb0379c0c2d5a80 (the canonical JSON digest, am.digest(descriptor); a file-bytes sha256 is the wrong convention — this value replaces the cfd874e8… value given in R1 CORRECTION) → install.sh S' → verify-ready → acceptance.sh once → R2 arming. Nothing host-mutating happens before the gate clears: install leaves services stopped, and the acceptance preflight readiness.validate_receipt_file needs a passing receipt with ≥30 min margin. The Lane R critical path in §3 therefore begins at the human gate, not at F1 + R1. Where this paragraph and R1 CORRECTION differ, this paragraph governs.

#### Human gate (Lane R) — credential rotation for `codex-01` (R1 CORRECTION 2, 2026-10-17 13:5xZ, seat 873aabd3)

EXACT_HUMAN_GATE for the Chairman / production owner; the seat never runs `codex logout`/`login`. Both commands are run by the Chairman / production owner from the installed `91c1cac5` release's `ops/executive_os` directory; `codex-01` is the script's default slot, so no slot flag is passed. `prepare_explicit_replacement` invalidates the readiness receipt and runs `codex logout` first; `credential_rotation_interlock` requires all autonomy arms disarmed (true today).

- Canonical — service-account enrollment (workspace-admin workflow; must classify `agentIdentity`), fed from the Keychain item (account `mastermind-executive-codex-service`, service `mastermind-executive-codex-access-token`), exactly the `HOST_PREREQUISITES.md` §replacement shape: `/usr/bin/security find-generic-password -w -a mastermind-executive-codex-service -s mastermind-executive-codex-access-token | sudo -n /bin/bash provision-worker-auth.sh --enroll-service-account --replace-existing`. The Keychain item is currently ABSENT in System.keychain, so the workspace admin must provision it first.
- Fallback — device re-authorization in an interactive Terminal: `sudo /bin/bash provision-worker-auth.sh --reauthorize-device --replace-existing` (interactive controlling tty; `codex login --device-auth` as uid 451 via `/dev/tty`; the human opens the Codex URL, enters the one-time code and signs into the administrator-attested company workspace; prints "device fallback enrolled; login status passed; inference canary not run; not READY").

After enrollment the seat runs one `--verify-ready --expected-credential-kind <kind> --workspace-binding-class company-workspace-admin-attested --credential-expires-at <now+31..60min Z>` (fresh identity probe + one canary), then `acceptance.sh` inside the ≥30 min margin. Caveat: the Oct 12 failure terms were capacity/model, so a rotation alone may not clear a provider-capacity condition; the single fresh canary must be spent deliberately.

### Lane F — Capacity and Fabric. Owner: seat; Fabric labour via the kit. Suborchestrator: optional Opus for F3–F4 if ≥2 independent packets run.

| ID | Commission | Scope | Identity | Acceptance | Return | Non-goals |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | **Bring `codex-01` back as a live worker** (F1) | `launchctl enable/kickstart system/com.mastermind.executive.worker.codex` as the acceptance/arm sequence requires; readiness receipt current — CORRECTION 2 (2026-10-17 13:5xZ, seat 873aabd3): "readiness receipt current" is false today (`provider-readiness-v2.json` passed false, `provider_turn_failed`, 2026-10-12T07:08:21Z; every automated requalification route refuses); the human rotation in "Human gate (Lane R)" and one seat-run `--verify-ready` come first | seat (root) | service running; heartbeat advancing on a live attempt | ledger F1 | enabling pro realms; editing readiness JSON |
| F2 | **Native Claude finite admission coexistence** (F3) | observe #1563 / #1560; place one Job on the native quota class only after Sol's lane lands | seat reads; Sol writes | one COMPLETED attempt on `claude8-native-01`; one enrollment record | ledger F3 | a parallel enrollment PR |
| F3 | **Executive ↔ Fabric bridge live assignment** (F5) | one bridged placement with sealed assignment snapshot | runtime + kit | snapshot + retained result for one child | ledger F5 | editing `pools.yaml`; relaunch queue |
| F4 | **Remote worker gateway health** (F6) | one Ubuntu host | host owner | gateway health + one placed attempt | ledger F6 | installing on all hosts |
| F5 | **Personal-Pro realm readiness** (F2) | name the exact human/provider re-enrollment once — CORRECTION 2 (2026-10-17 13:5xZ, seat 873aabd3): codex-pro-01 receipt FAILED process_failed 2026-10-09T04:28Z; codex-pro-02/03 passing receipts EXPIRED 2026-10-10T23:30Z | **EXACT_HUMAN_GATE** candidate | fresh READY receipts | ledger F2 | probing repeatedly |

### Lane A — Mastermind OS app (web + native). Owner: seat for install/journeys; **Opus suborchestrator** eligible for A3–A6 (independent domain: app qualification), administering Fabric packets; no native children.

| ID | Commission | Scope | Identity | Acceptance | Return | Non-goals |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | **Install the OS executive transport** (G3, G4, G5, PD-5) | prepare the exact install inputs per `docs/runbooks/mastermind-os-public-launch.md` (`os_executive_transport`, `os_executive_resource`, `os_commission_port`, sealed `os-commission-publication.json` with sha256 flag); production owner runs `install.sh`; Opus read-only audit first (security/auth) | production owner + seat | local POST `/os/executive/context` → **401 not 404**; edge same; `session/context` 401 | ledger G3/G4/G5 | mock transport; editing installed config by hand |
| A2 | **Edge verification** (G6) | POST probes through `mcp.mastermind-x.com` | seat | gateway status bodies via edge | ledger G6 | VPS config edits (owner) |
| A3 | **Source qualification at `a552a5e5`** (A2) | `npm ci --ignore-scripts`, `vitest`, `vite build` in W; Python transport tests | Fabric or seat | all green; bundle digest reproducible | plan §Evidence | changing app behaviour |
| A4 | **Phase E journeys** (A3, A4, H8) | E-1 objective entry → interpretation inspect/correct; E-2 submit → Job → status; E-3 project/execution state; E-4 drill into workers/evidence/decisions/attention; E-5 result + reserved decision reply; E-6 interrupted connection → status reconciliation, one Job; E-7 grounded progress; E-8 recovery without duplicate | authenticated Web-CEO principal in the browser | per-journey capture + network trace; exactly one Job per submit | ledger A3/A4/H8 | read-only transcript as proof |
| A5 | **Native app qualification** (A5) | Tauri build; A4 E-2 and E-6 natively | seat/Fabric | native build artefact + journey capture | ledger A5 | store distribution |
| A6 | **Responsive qualification** (A6) | 375 px + desktop, office + conversation | seat/Fabric | captures without clipping/overflow | ledger A6 | redesign |

### Lane C — Continuity and projection. Owner: seat.

| ID | Commission | Scope | Acceptance | Non-goals |
| --- | --- | --- | --- | --- |
| C1 | Agent OS workstream `WS-EXECUTIVE-ECOSYSTEM-COMPLETION` + dated handoff (macro PR) | records link ledger/plan/PRs, P4/P5, CAPACITY-FABRIC | `scripts/agentos.py validate` 0 errors; merged | second memory store |
| C2 | Refresh `WS:EXECUTIVE-AUTONOMY-V1-CLOSURE` P4 frontier facts (installed `91c1cac5`, PD-2 lineage) | small frontmatter/body edit | validate 0 errors; owner-visible diff | rewriting P4/P5 |
| C3 | Linear projection (owner-run) and seat memory checkpoints | ledger deltas reported; memory file current | — | duplicate projection |

## 3. Sequencing and critical path

```
R1 acceptance (needs F1 worker for the proof Job) ──► R2 arm (Opus audit) ──► H2 routine job
                                                        │                      │
A1 transport install (Opus audit) ──► A2 edge ──────────┼──► A4 journeys ──────┼──► H1 full programme
                                                        │                      │
R3 roots · R4 grant proof · R5 inbox ◄──────────────────┘   H4 H5 H6 H7 interrupted/fail-closed/repair/correction
A3 source qualification · C1 C2 records ── run now (no host effect)                      └──► H8 browser proof
```

Runs now, no host effect: C1, C2, A3, the A1 install-input preparation, the R1 precondition read, the R2/A1
audit commissions. First host effect: F1 + R1. Nothing in Lane R or A1 proceeds while an active writer or an
uncertain operation on the same artefact is observed (ledger §3).

R1 CORRECTION 2 (2026-10-17 13:5xZ, seat 873aabd3) — Lane R critical path: the first host effect is no longer F1 + R1. The path is: human gate (credential rotation for `codex-01`, EXACT_HUMAN_GATE, "Human gate (Lane R)") → FRESH clone of S' (current protected master head, `ee0f0d9b` or newer at install time) → `os_release_assets` prepare → install-inputs → `service-control.sh stop` (91c1) → `acceptance_maintenance.py` supersede_unstarted (predecessor `25c4b792`, successor S', root JOB-003, superseded unstarted `91c1cac5`, descriptor digest `91695ef2…`) → `install.sh S'` → one `--verify-ready` → `acceptance.sh` once inside the ≥30 min receipt margin → R2 arming (Opus audit). The diagram above is kept as written; read its "R1 acceptance" box as this sequence.

## 4. Acceptance campaign (Phase F) — the journeys that close the programme

| Journey | Procedure | Evidence location | Blocked by |
| --- | --- | --- | --- |
| H1 multi-domain programme through the full hierarchy | Chairman submits one real objective in the app; COO decomposes to ≥2 children (one via Fabric bridge); review child; original-parent consumption; app shows outcome | Job/Attempt/Event rows for the root; `ceo_intent_status` body; browser capture | R2 A1 F1 F3 |
| H2 routine direct-to-worker task | one Job without decomposition on `codex-01` | COMPLETED row + consumed result | R2 F1 |
| H3 operator → child → original-parent reviewed return | review Job linked by `reviews_job_id`; parent consumes | rows + consumption event | R2 |
| H4 interrupted connection + reconciliation | kill the connection after submit, before status; app reads status; exactly one Job | network trace + Job count | A1 A4 |
| H5 conflicting source writer / permission fail-closed | child requests a path outside `allowed_write_paths_json` | typed refusal event, no effect | R2 |
| H6 rejected/failed worker → lawful repair/escalation | induce a bounded failure; repair child or escalation item consumed | rows + inbox item | R2 R4 |
| H7 Chairman correction in flight | correction on a RUNNING Job → typed terminal state consumed by parent | rows + app | R2 A4 |
| H8 app/browser with authenticated live data + result consumption | A4 E-2/E-5 captures with authenticated requests | captures + trace | A1 |

Independent review (one each, scoped to the changed risk): R2 arming (security/auth), A1 transport install
(auth surface), any exactly-once change to reconciliation code if Phase D needs one. Production owner confirms
install/readiness separately (R1 receipt, R6, R7).

R1 CORRECTION 2 note (2026-10-17 13:5xZ, seat 873aabd3): readiness needs the human credential rotation first ("Human gate (Lane R)"); until a passing `provider-readiness-v2.json` exists with ≥30 min margin there is no R1 receipt to confirm, and the receipt R1 confirms is the one for successor S' (current master head), not for `91c1cac5` or `ad125292`.

## 5. Holds this programme preserves (never displaced)

Sol's open `sol/web-*` lanes (#1570 #1569 #1568 #1566 #1553 #1542 #1536 #1515 #1477 #1473) and codex #1563 ·
runtime roots JOB-002/003/013 (PD-3) · the prepared `91c1cac5` acceptance bundle (PD-2) · Fabric kit files
(`pools.yaml`, `pick.py`, `RELAUNCH_QUEUE.txt`) · original #633 Auth0 DCR `EFFECT_UNKNOWN` · pro-realm
enrollment ceremonies (human/provider) · Fable `intent.submit` enrollment (`REJECTED_BY_DESIGN`).

## 6. Evidence (updated as lanes return)

- 2026-10-17 census: see ledger §1 and §5 (read-only; no state changed).
- 2026-10-17 A3 (Python transport tests at `a552a5e5`): `tests/test_mastermind_os_executive_transport.py`,
  `tests/test_mastermind_os_session_transport.py`, `tests/test_executive_mcp_entry.py` — **213 passed, 0 failed**
  (`python -P -B -m pytest <files> -p no:cacheprovider --rootdir <W> -o pythonpath=.` in a scratch virtualenv with
  the `dev` extras plus `numpy`/`pandas`/`pyarrow` for the vendored engine stub). Two runner facts worth keeping:
  the repo root must be on `sys.path` (`pythonpath=.`), and the macro checkout's `tests/` package must **not** be
  on `sys.path` (hence `-P`), or `tests.test_executive_ceo_ingress` resolves to the wrong repository.
  Node-side (`npm ci`, `vitest`, `vite build`) still owed.
- A3 RESULT (2026-10-17 ~12:00Z, pin a552a5e5, node v26.5.0 / npm 11.17.0, Darwin): `npm ci --ignore-scripts` OK; `npm run typecheck` (tsc -b) exit 0; `npm test` (vitest run) 69 files, 1574 passed, 1 skipped, 14.7s; `npm run build` (vite build) OK, 74 modules, chunk-size warning only. Source build qualification is PROVEN at the pin; native Tauri packaging, signatures and the authenticated live-data journeys (E-1..E-8) remain unproven.
- 2026-10-17 master drift: Mastermind master advanced from the pin `a552a5e5` to `c57ab711` (4 merges: #1567
  market-view dates, #1491 fail-closed finite definition publication, #1565 fabric bootstrap effect classes,
  #1535 Studio Direct typed Git publisher). None touches `research/`, the OS app or the executive transport; the
  ledger's states hold at the pin.
- **2026-10-18 04:2xZ checkpoint (seat 873aabd3).** The facts below were observed by the seat (UTC) and recorded
  docs-only on #1598; the recorder took no host action. Where the facts and R1 CORRECTION 2 differ, the facts
  govern. The credential was not rotated: the same-generation admission replaced the "Human gate (Lane R)"
  rotation for this canary.
  1. *Engineering.* #1591 (explicit same-generation terminal requalification on the current pin) merged through
     the merge queue (GitHub `mergedAt` 2026-10-18T03:49:58Z; the seat observed it at 03:52Z). Protected master
     S2 = `08d7887335ee8aea11f0809e0660a5298c3ef68c`. The independent read-only Opus review verdict was MERGE, and
     CI was green.
  2. *Staging.* S2 was staged on the host from clone `Mastermind-08d78873`:
     - `os-web-assets` manifest `98ae8aad…`;
     - install-inputs successor control sha256 `0593db43…`, produced programmatically from the live root-only
       `control.json`.
  3. *The one canary.* `provision-worker-auth.sh --verify-ready` ran under the new same-generation admission:
     codex 0.159.2, pin `16593cc2…`, credential UNCHANGED (same `auth.json` lstat). It PASSED at 03:59:35Z. The
     receipt's `readiness_expires_at` is 04:56:45Z.
  4. *Install.* `stop-readside` ran at 04:01Z. The supersede prepare descriptor is
     `6594613bacf18c12f0494ac7983e6e2f2c4b2e27075a8cb6077ee5623b22d906`. Install SUCCEEDED at 04:08Z ("installed
     exact Executive OS release 08d78873"; privileged broker armed). Two install refusals were repaired first:
     - 20 stray root-owned `.pyc` files in the sealed Python framework were removed and the seal was restored;
     - `--protected-master-sha` is frozen-mode only, so it was dropped for plain mode.
  5. *Acceptance.* `acceptance.sh` at 04:09Z REFUSED fail-closed with "control account directory group set
     drifted" (`ops/executive_os/acceptance.py:1053`).
     - Cause: `_mastermind_exec` is a member of gid 470 `_mastermind_minimax`. The finite lane registered those
       finite worker principals on the host on 2026-10-14 at 19:57. Meanwhile `control.json` has no
       `fabric_attended_probe` stanza, and `FINITE_DEFINITION_DIR` `config/fabric-minimax-finite-01` is absent.
     - Source cross-check by the recorder at `08d78873`: with no stanza, `_attended_worker_membership` returns
       none, so gid 470 is not in the expected control group set.
     - #1563 is merged (the seat brief says 03:04Z; GitHub `mergedAt` is 2026-10-17T23:57:29Z). The host
       publication chain (`finite_definition_publication.py` → `autonomy_control.py finite-control-stage`) was
       never run.
     - The seat did not remedy the drift: no group strip, no check weakening, no hand edit of `control.json`.
  6. *Margin.* Acceptance and arm both enforce `MIN_ACCEPTANCE_MARGIN` = 30 min
     (`provider_readiness.validate_receipt_file`). The passing receipt therefore became unusable for acceptance
     at 04:26:45Z. The one canary is SPENT without acceptance or arm, and a further canary needs the Chairman's
     word.
  7. *Restore.* `start-readside` ran at 04:17Z from release 08d78873: control pid 78990, sol-state-relay
     pid 78959, mcp running. The `worker.codex` launchd job is ABSENT (preserved). The system was not left down.
  8. *Ladder.* Lane R engineering MERGED; S2 install DELIVERED on host; acceptance BLOCKED (cross-lane drift);
     NOT ARMED; no PRODUCTION_PROOF. The Chairman's decision was asked once:
     - (a) finite host publication + `finite-control-stage`, then `stop-readside` → ONE further canary →
       acceptance → arm → Phase F; or
     - (b) hold S2 installed-unaccepted.
  9. *Ledger F3.* F3 stays `BUILT_NOT_PROVEN` with a new completion blocker. The host principals are registered
     but the control stanza is unstaged, which blocks acceptance of ANY release until it is published or ruled.
     The ledger records this in rows E4–E7, F1 and F3.

## 7. Checkpoint (newest first)

- **2026-10-18 04:2xZ** — S2 `08d78873` is installed on the host (04:08Z) and the read side is restored
  (04:17Z). Acceptance REFUSED fail-closed on cross-lane finite group drift (gid 470). The one same-generation
  canary (PASSED 03:59:35Z) is spent. NOT ARMED.
  Next exact action: the Chairman's one ruling, either (a) finite host publication + `finite-control-stage`,
  then one further canary → acceptance → arm, or (b) hold S2 installed-unaccepted.
  Evidence: §6 "2026-10-18 04:2xZ checkpoint".

- **2026-10-17 ~12:00Z** — Phase A census complete; ledger + this plan written in Mastermind worktree
  `claude/ssd-executive-ecosystem-completion-20261017-427d19196cd8f420` (SSD mint, base `a552a5e5`).
  Discovered: the `91c1cac5` acceptance is a prepared `supersede_unstarted_v1` lineage bound to `JOB-003`
  (PD-2). Next exact action: ship ledger+plan PR; write Agent OS records (C1); read `acceptance.py`
  preconditions for R1; commission the R2/A1 read-only audits; start A3 in W.
