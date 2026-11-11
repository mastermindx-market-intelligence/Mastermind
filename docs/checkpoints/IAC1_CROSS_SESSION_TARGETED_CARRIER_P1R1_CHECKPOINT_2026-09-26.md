# IAC-P1-R1: exact cross-session consultation carriage

Date: 2026-09-26
Capability: BUILT_NOT_PROVEN / SOURCE_ONLY / review candidate
MISSION_COMPLETE: false
FINALIZATION_CLASSIFICATION: CHECKPOINTED_CONTINUATION

## Authority and continuity

Parent program: `agent-interconnect-mailbox-20260924-sol-001`.
Fabric parent: `agent-fabric-end-to-end-fable-integration-20260913-sol-001`.
Source operation: `iac1-cross-session-targeted-carrier-p1r1-20260926-sol-001`.
Canonical cumulative checkpoint: Mastermind #600/comment 5811144037.
Frozen architecture: #600/5832288417; authority amendment: #600/5832389941;
bounded R1 plan: #600/5845026001.

The Chairman's continuing commission is real teammate communication among
orchestrators and subagents: bounded Q&A, durable attention, actor inbox/detail,
explicit consumption, succession, cross-project reachability, and MastermindOS
integration. This is the existing communications program, not a second mailbox,
queue, registry, scheduler, or autonomy plane.

Protected procedure/source pin: `0d12bb45c4429a7441614fac8eff4830db5e7c0d`.
Skillpack: `mastermind.sol_skillpack.v1`, version 1.0.1, bootstrap 1. INDEX,
COLD_START, ACTIVE_EXECUTION, WEB_CEO_DELEGATION, RECONCILE_STATE, CLOSEOUT,
AGENTS, and DELIVERY_WORKFLOW were read at this same pin. The approved R1 design
is being executed; target existence does not grant cross-responsibility authority.

PR #986 is merged at this pin. Reviewed P1 head was
`34c467827d04158c63697fef8bf848d049c9bf98`; source acceptance is
#986/5844903386. Its old physical-origin and CI blockers are historical.
PR #959's accepted inbox/Wake foundation remains inherited. Do not replay those
repairs, merge a historical donor branch, or start another copy of the incumbent
Fable integration principal.

## Source custody and effects

Launcher-acquired workspace:

- Host: M2 Studio; lane: `web`.
- Branch: `sol/web-iac1-cross-session-targeted-carrier-p1r1-20260926-sol-001`.
- Worktree: `/Volumes/Mastermind/agent-workspaces/web/iac1-cross-session-targeted-carrier-p1r1-20260926-sol-001`.
- Initial carrier commit, pushed and read back: `809a1ca3978bcb502480215c6b58a2e40ffc6f6d`.
- Complete review candidate HEAD is recorded by exact SHA in the PR and cumulative checkpoint.

Direct execution rationale: PRINCIPAL_JUDGMENT for sender/target authority and
LOWER_TOTAL_OVERHEAD for this bounded source slice. No worker, independent
reviewer, provider, watcher, or source-custody transfer was dispatched in this
continuation. Existing Fable/Fabric integration ownership remains; its prior M1
worktree was not modified. Parallel Executive OS backend/status work was untouched.

Protected compatibility check: `763ec8f920177fdf48b18df1b8e37b61ab482ef0`,
protected=true. Movement from the source/procedure pin affects only
`ops/executive_os/status.sh` and `tests/test_executive_status.py`, disjoint from
this source/test/skill envelope. This does not waive exact-candidate CI/review.

No live Slack packet, provider invocation, installed service, credential,
production Runtime, account binding, availability marker, or capacity allocation
was modified. Source commit/push and GitHub metadata publication are separate
explicit effects. Temporary test Runtime/Wake writes are not production writes.

## Implemented source

### Separate caller authority from destination facts

`integrations/company_consultation_targets.py` adds immutable
`ConsultationDeliveryTarget` / `ConsultationPacketAccess` and an explicitly
host-configured `TargetedAgentDialogueConsultationPacketCarrier`.

A QUESTION is authenticated as the requester and sent to the recipient's exact
parent. An ANSWER is authenticated as the recipient and sent to the requester's
exact parent. Destination descriptors contain facts, not Company Dialogue
allowed-message grants. No model-facing routing field or public schema was added.
The incumbent same-parent carrier and default restrictions remain unchanged.

Reads establish exact party membership before fetching even an absent packet.
Caller and destination are checked after read I/O, before the owner's admission
callback, and after that awaited callback before COMMIT. Identity drift cannot
commit a packet. Existing callback-abort and effect-unknown semantics remain;
uncertain delivery is never relabeled as safe absence.

### Reconstruct destinations from canonical owners

`integrations/company_consultation_target_resolution.py` adds read-only
`ExecutiveConsultationPacketTargetResolver`.

It reuses the existing Executive immutable-root and Wake physical-source readers
from `workspace_agent_runtime_binding.py`, without importing Workspace's
RESULT-only grant. Executive owns Job/Attempt/Worker lineage; Consultation
Runtime owns admitted parties; Wake owns physical parent evidence. There are no
new tables, caches, maps, stores, retry loops, or background tasks.

A new QUESTION requires an exact current target and a second current-target
read. An admitted consultation reconstructs its original exact Attempt rather
than the stable peer's newer current session. Missing or multiple physical
parents refuse. The host's configured Relay workspace/channel must match the
persisted physical source. Additional attention on the same parent does not
change its destination evidence digest.

### Compose dispatch and sticky recovery

`integrations/company_consultation_dispatch.py` enables targeted behavior only
for a host-supplied targeted carrier. Before the first INTENT, a validated
candidate supports read-only packet lookup without caching a route. Once INTENT
exists, retry uses its original actor/binding facts without a current-peer lookup.
A genuinely new invocation still requires current resolution and cannot fall
back to an old consultation route.

Existing Runtime admission, required Wake acknowledgement, answer availability,
explicit requester consumption, packet deduplication, and bilateral Wake owners
are reused. The Relay engine/service and public Company MCP schema are unchanged.
Production packet carriage remains UNAVAILABLE/disarmed.

## Verification

Three new test files contain 48 cases:

- `tests/test_company_consultation_targeted_carrier.py`: 33 cases covering exact
  direction, sender/party/target checks, callback/read fences, unknown transport
  outcomes, immutability, a real AF_UNIX Relay restart, and structural proof that
  these adapters add no parallel control plane.
- `tests/test_company_consultation_target_resolution.py`: 13 cases against real
  temporary Runtime/Wake records, including ambiguous/foreign/absent sources,
  reopened Runtime reconstruction, and current versus historical targets. The
  current-pointer rollover is synthetic, not a live provider-rotation receipt.
- `tests/test_company_consultation_targeted_dispatch.py`: 2 composed tests using
  Company MCP gateway, dispatcher, temporary Runtime/Wake persistence, canonical
  resolver, and real AF_UNIX service/engine. Slack and provider/harness identities
  are fixtures; no real account conversation is claimed.

The composed positive journey verifies QUESTION on B and ANSWER on A; service
restarts and fresh Runtime readers; zero-write detail reads; reply refusal before
Wake acknowledgement; exactly one INTENT, ANSWER_AVAILABLE and
CONSUMED_BY_REQUESTER; one question Wake and one answer Wake; duplicate-free
retry; and no current-peer lookup on admitted replay. Missing target evidence
produces no INTENT, packet, or Wake.

Final expanded regression: **593 passed, 1 skipped in 54.62s; exit 0**.
The skip is `tests/test_company_consultation_mcp.py:501`, because this host lacks
`mcp`. This is not proof of SDK/server installation.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -o addopts='' -q -rs -p no:cacheprovider \
  tests/test_company_consultation_targeted_carrier.py \
  tests/test_company_consultation_target_resolution.py \
  tests/test_company_consultation_targeted_dispatch.py \
  tests/test_company_inbox_iac1.py \
  tests/test_agent_dialogue_consultation_contract.py \
  tests/test_company_consultation_mcp.py \
  tests/test_w6c2_consultation_runtime.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_turn_observer.py \
  tests/test_slack_agent_dialogue_service.py \
  tests/test_slack_agent_dialogue_slack_web_api.py \
  tests/test_workspace_agent_runtime_binding.py
```

TDD: initial 32 carrier cases failed for the missing carrier; 13 resolver cases
failed for the missing resolver; the composed journey failed at the old
same-parent gate. Each capability then passed its corresponding tests. Two
fixture-admission errors (missing workstream and source object instead of closed
wire) were corrected in the new fixture, not by weakening Runtime admission.

Eleven deliberate mutants were caught by behavioral failures; original source
bytes were restored after every probe:

| Deliberate defect | Required discriminator |
| --- | --- |
| Route packet to sender thread | Physical destination differs from sender |
| Remove sender check | Destination binding cannot impersonate sender |
| Remove target actor check | Wrong destination actor refuses before transport |
| Remove read-party check | Nonparty cannot probe absence or fetch packet |
| Remove post-admission fence | Identity drift after admission cannot COMMIT |
| Remove post-read fence | Drift suppresses even an absent read |
| Accept foreign channel | Physical scope must match the host Relay |
| Remove second current read | Target drift refuses reconstruction |
| Use current target for history | Original admitted Attempt stays readable |
| Hash each attention as a new target | Same-parent attention is not rotation |
| Resolve current peer on admitted retry | Retry survives current-peer retirement |

These are author-run fault injections, not an independent whole-branch review.
Receipts and individual logs:
`/Volumes/Mastermind/evidence/iac1-cross-session-targeted-carrier-p1r1-20260926-sol-001/`.
Drivers: `/Volumes/Mastermind/tmp/iac-p1r1-mutations-20260926.py` and
`/Volumes/Mastermind/tmp/iac-p1r1-owner-mutations-20260926.py`.
Regression log: `/Volumes/Mastermind/tmp/iac-p1r1-final-regression-20260926.log`.

Source SHA-256 values after mutation restoration:

```text
61108976345edf47841668cfdaddf2771a5bb52db168945a8947b5574ec25bca  integrations/company_consultation_targets.py
a42e17fdc2a80aadc2fe989abe8eae965fac926e41694e40512e0c5385c6fe79  integrations/company_consultation_target_resolution.py
d0061c145360cdba6327aeb3836ca1b3c617dda125f9a9dbb0e07725ecff5538  integrations/company_consultation_dispatch.py
```

Repository-wide pytest was also attempted with `--maxfail=1`. Collection stopped
in `tests/mastermind_window_reader/test_mission_association.py` because this host
Python lacks `jwt`; PyJWT is declared in the repository's dev profile. Result:
2 skipped, 1 collection error. This is NOT a full-suite green/build receipt.
No shared dependency installation or unrelated auth-source change concealed it.

## Open gates and exact continuation

1. Independent exact-head whole-branch review and required hosted CI/source
   acceptance. Self-run tests/mutants do not satisfy these release gates.
2. R2 stable peer projection from the existing opaque responsibility identity,
   canonical current responsibility-to-runtime resolution, and explicit
   cross-responsibility authority/capability policy. Mere presence in Executive
   is not permission; no broadcast/forwarding expansion is authorized here.
3. P2 exact host/account production composition and installation. The resolver
   must use the actual Relay scope and existing peer policy/RuntimeBinding checks.
   Source tests must never set the production availability marker.
4. P3 real two-session A-to-B-to-A, actual rotation, orchestrator/subagent/provider
   qualification, and MastermindOS inbox/detail/attention/consumption proof.

Recovery: fresh-pin protected laws; read #600/5811144037, the PR's exact HEAD and
this checkpoint. Validate/reuse the registered operation workspace instead of
creating a duplicate writer. Review the three production files and three test
files against `0d12bb45c4429a7441614fac8eff4830db5e7c0d` and the frozen R1 plan.
Retain the incumbent integration owner. No independent review worker has been
launched by this checkpoint, and no automatic wake is implied.

Do not redo #959, #986's settled physical-origin repair, stale CI attribution, or
old review workspaces. Do not merge a historical donor branch. Do not replace
Executive lifecycle/admission, Agent OS continuity, RuntimeBinding, Capacity
placement or Wake with another communications control plane. Parent mission
remains incomplete; this checkpoint records a verified source boundary.

---

## Repair round R1 — deterministic destination and resolver-evidence classification

Consumed ruling `#600 5846064875` (one source carrier, Fable integration
principal) and independent review `#1001 5325831719` (`REQUEST_CHANGES`).
Source custody for this round is Fable's on this branch only. The donor branch
`claude/iac1-p1r1-targeted-carrier-20260926` head
`6a8a3c78e2629ffc2dfac183c80fd2f15b5dbe05` stays donor evidence and was not
transplanted, cherry-picked or merged; only the smallest missing semantics from
`3547843e` were consumed. #1001's resolver, stickiness, double-read/fence and
composed AF_UNIX journey are unchanged.

### What changed

1. **Deterministic destination conflicts leave the outage bucket.** The Relay
   service *returns* `{"ok": false, "error": {"code": ...}}` verbatim for engine
   codes — `terminal_response` returns it, and the post-COMMIT collapse narrows
   only service `ERROR_CODES` — so `THREAD_CONTEXT_MISMATCH` and
   `THREAD_BINDING_AMBIGUOUS` never arrive as a raised `DialogueServiceError`.
   Both are now mapped to `ConsultationTargetConflict` (a `StateConflict`) on
   the send and read edges. Genuine unavailability and `SEND_EFFECT_UNKNOWN`
   remain reconcile-only; the read edge still fences before classifying, so
   identity drift continues to outrank a stale refusal.

2. **Resolver evidence failures are classified, not pooled.** Foreign scope and
   a moved-on-but-readable current Attempt are adjudicated as
   `ConsultationTargetConflict`. Owner-reader refusals become
   `ConsultationTargetEvidenceUnavailable`, a `ConsultationPacketCarrierUnknown`
   subtype: still unknown, because real observation uncertainty must not become
   a safe refusal. **The type enforces nothing.** It is typed only so a consumer
   *can* tell unreadable owner evidence from a dead transport and reconcile on
   the same target; nothing in the code prevents re-resolution onto a different
   parent, and this line must not be cited as though it did.

   **Measured limit, deliberately not papered over:** the owner readers carry
   exactly one code, `WorkspaceReturnError("BINDING_UNAVAILABLE")`, for a
   missing fact, an ambiguous one, a foreign scope *and* an unreadable store.
   So `missing`, `ambiguous` and a rotation that leaves no readable Attempt
   are **not separable here** and stay unknown by construction, not by choice.
   `test_owner_readers_carry_exactly_one_conflated_refusal_code` pins that
   conflation and fails the moment an owner adds a distinguishing code, which
   is the signal to refine the mapping.

3. **Structural guard restored to the incumbent surface.** Both P1-R1 production
   modules joined `_P1_PRODUCTION_PATHS`. They are absent at
   `_P1_PROTECTED_BASE`, so `_p1_base_source` now resolves an absent path to an
   empty base — and *proves* absence with `git cat-file -e` so a `git show`
   failing for any other reason breaks the guard loudly instead of reading as
   an empty base.

4. **Production composition pinned, not armed.** No non-test module composes the
   targeted carrier anywhere in the tree, and `PRODUCTION_PACKET_CARRIAGE`
   remains `"UNAVAILABLE"`. The pin asserts both, and asserts that any future
   composition must pass the canonical
   `ExecutiveConsultationPacketTargetResolver`. The Protocol seam stays open for
   tests. Production remains disarmed.

### Mutation teeth — eight mutants, all four send/read edges, all killed

Each mutant was proven to change the bytes before its result was trusted, and
every file was restored byte-identical (asserted, not assumed).

| Deliberate defect | Required discriminator | Verdict |
| --- | --- | --- |
| Send-edge refusal check removed | Both codes on `_put`, plus the real AF_UNIX journey | KILLED |
| Read-edge refusal check removed | Both codes on `_get_targeted` | KILLED |
| Code set narrowed to one code | `THREAD_BINDING_AMBIGUOUS` on both edges | KILLED |
| Mapping widened to any code | A non-destination envelope still reconciles | KILLED |
| Conflict retyped as carrier-unknown | Refusal is not the retryable bucket | KILLED |
| Owner-evidence handler removed | Reader refusals keep their typed class | KILLED |
| Unavailable retyped as a refusal | Uncertainty is never a safe refusal | KILLED |
| Production composition planted | Pin refuses a non-canonical read grant | KILLED |

### Guard reach — measured, not asserted

A `token_file` plant in `company_consultation_targets.py`, run against three
instruments on the same bytes:

| Instrument | Verdict |
| --- | --- |
| Incumbent guard, extended by this repair | **CAUGHT** (rc=1) |
| #1001's own local adapter guard | MISSED (rc=0) |
| Incumbent guard with the two paths removed | MISSED (rc=0) |

The second row is why the extension was required rather than optional; the third
shows the added paths are the load-bearing part.

### Command manifest

```text
# focused (158 passed)
python3 -m pytest tests/test_company_consultation_targeted_carrier.py \
  tests/test_company_consultation_target_resolution.py \
  tests/test_company_consultation_targeted_dispatch.py \
  tests/test_company_inbox_iac1.py -rA -p no:randomly

# owning dialogue/consultation/wake/workspace set, 55 files
# 1871 passed, 3 skipped, 57 subtests passed, rc=0, zero outcome-shaped failures
python3 -m pytest <55 files> -rA -p no:randomly
```

Three owning-set files are excluded and named rather than silently dropped:
`test_workspace_agent_profiles.py` (host lacks `mcp`),
`test_workspace_agent_return_app.py` and `test_workspace_agent_return_service.py`
(host lacks `jwt`/PyJWT). They abort collection on import of unrelated
integrations and touch nothing in this repair. This is not a full-suite receipt.

Source SHA-256 after mutation restoration:

```text
b7027489e6dab1e6b0d75d1d9413a57d50efd8579f77b548f903df8b60e7d283  integrations/company_consultation_targets.py
624160db7efcaa4439a1868e1cd061af3fa067b1e2097dc9dcaae9e496946801  integrations/company_consultation_target_resolution.py
d0061c145360cdba6327aeb3836ca1b3c617dda125f9a9dbb0e07725ecff5538  integrations/company_consultation_dispatch.py
```

`company_consultation_dispatch.py` is **unchanged** by this round.
