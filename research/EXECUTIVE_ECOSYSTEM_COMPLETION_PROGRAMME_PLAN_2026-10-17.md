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

### Lane F — Capacity and Fabric. Owner: seat; Fabric labour via the kit. Suborchestrator: optional Opus for F3–F4 if ≥2 independent packets run.

| ID | Commission | Scope | Identity | Acceptance | Return | Non-goals |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | **Bring `codex-01` back as a live worker** (F1) | `launchctl enable/kickstart system/com.mastermind.executive.worker.codex` as the acceptance/arm sequence requires; readiness receipt current | seat (root) | service running; heartbeat advancing on a live attempt | ledger F1 | enabling pro realms; editing readiness JSON |
| F2 | **Native Claude finite admission coexistence** (F3) | observe #1563 / #1560; place one Job on the native quota class only after Sol's lane lands | seat reads; Sol writes | one COMPLETED attempt on `claude8-native-01`; one enrollment record | ledger F3 | a parallel enrollment PR |
| F3 | **Executive ↔ Fabric bridge live assignment** (F5) | one bridged placement with sealed assignment snapshot | runtime + kit | snapshot + retained result for one child | ledger F5 | editing `pools.yaml`; relaunch queue |
| F4 | **Remote worker gateway health** (F6) | one Ubuntu host | host owner | gateway health + one placed attempt | ledger F6 | installing on all hosts |
| F5 | **Personal-Pro realm readiness** (F2) | name the exact human/provider re-enrollment once | **EXACT_HUMAN_GATE** candidate | fresh READY receipts | ledger F2 | probing repeatedly |

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
- 2026-10-17 master drift: Mastermind master advanced from the pin `a552a5e5` to `c57ab711` (4 merges: #1567
  market-view dates, #1491 fail-closed finite definition publication, #1565 fabric bootstrap effect classes,
  #1535 Studio Direct typed Git publisher). None touches `research/`, the OS app or the executive transport; the
  ledger's states hold at the pin.

## 7. Checkpoint (newest first)

- **2026-10-17 ~12:00Z** — Phase A census complete; ledger + this plan written in Mastermind worktree
  `claude/ssd-executive-ecosystem-completion-20261017-427d19196cd8f420` (SSD mint, base `a552a5e5`).
  Discovered: the `91c1cac5` acceptance is a prepared `supersede_unstarted_v1` lineage bound to `JOB-003`
  (PD-2). Next exact action: ship ledger+plan PR; write Agent OS records (C1); read `acceptance.py`
  preconditions for R1; commission the R2/A1 read-only audits; start A3 in W.
