# WP-1 Commission — Worker-Aware Agent Relay V2

**Date:** 2026-08-27  
**Commissioner:** Sol, AI CEO  
**Chairman authority:** explicit current approval to proceed with the Worker Presence & Dialogue program and its turn-watcher amendment  
**Operation key:** `worker-presence-dialogue-wp1-20260827-sol-001`  
**Repository:** `mastermindx-market-intelligence/Mastermind`  
**Wave:** `WP-1`  
**Carrier branch:** `sol/worker-presence-dialogue-wp1-20260827`  
**Pickup / protected Mastermind:** `af43f356f4f7f34cb3514d1d1099b50444af8487`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1 at the same SHA  
**Authority:** implementation + tests + hosted-CI/adversarial-review return; **no production Slack/network/credential authority**  
**Completion:** `BUILT_NOT_PROVEN / PRODUCTION_INERT` only after Sol acceptance

## Observable mission

Implement the canonical Worker Presence & Dialogue V2 contract and normal storeless Agent Relay request/response path so an already-governed executive surface or Executive Worker can be represented with immutable, typed identity and applicability—while preserving ASD v1 exactly and performing **zero Wake classification, zero background observation, zero production Slack arming and zero lifecycle mutation**.

## Why it matters

WP-1 is the load-bearing identity seam for the Chairman-approved company-in-Slack experience. WP-2 cannot safely expose bounded company-dialogue MCP tools and WP-TW1 cannot safely classify dialogue turns until one accepted V2 parent/message contract establishes exact `operation_key`, watcher admission, actor identity, work/commission/session identity, applicability and semantic lineage without relying on Slack names or model prose.

This wave therefore unlocks two real machine capabilities for later consumers:

1. an exact, versioned dialogue identity contract for Sol/Fable/Executive Worker actors; and
2. one storeless Agent Relay request/response service that can carry that contract without becoming another lifecycle or Wake plane.

## Authority / document precedence

Read in this order:

1. **Chairman-approved architecture merge #177 / `af43f356f4f7f34cb3514d1d1099b50444af8487`**.
2. `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-chairman-approval.md`.
3. `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-turn-watcher-amendment.md` for watcher/Wake topics only.
4. `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md` for overall WP identity/MCP/transport/no-rebuild law.
5. **Exact WP-1 implementation plan:** `docs/superpowers/plans/2026-08-27-worker-presence-dialogue-wp1-agent-relay-v2.md`.
6. Existing accepted ASD A0/A1 implementation and tests from Mastermind PR #125 / merge `eb9910681a6db9f9675b25233c8865bb43325c32`.
7. Current protected code at the pickup SHA.

If a newer accepted source law or a colliding branch/PR lands on an expected WP-1 path, **STOP and return to Sol**. Do not reconcile authority by changing scope or creating a parallel file/service.

## Verified current state and collision receipt

At release:

- protected `master` = `af43f356f4f7f34cb3514d1d1099b50444af8487`;
- #177 is merged and WP architecture is `SPEC_ONLY`;
- existing ASD v1/A0-A1 is `BUILT_NOT_PROVEN / DEVELOPMENT_UNARMED`;
- production Agent Relay ASD-A2 and real ASD-A3 are still separate unproven gates;
- Wake PR #174 remains provider-native Wake transport only and explicitly excludes Slack Agent Relay changes;
- no open WP-1 implementation PR or branch existed before this carrier was created;
- no WP-2 or WP-TW1 implementation carrier is authorized to start before WP-1 acceptance.

### Current-base reconciliation and final-repair receipt — 2026-08-28

The release pin above is historical pickup evidence and is intentionally preserved. Before final acceptance, the same #178 carrier was first history-preservingly reconciled to protected `master = b901dee0272a99b8a1d60385848b99b7273e8261`, with the same compatible `mastermind.sol_skillpack.v1` v1.0.0 / bootstrap-major 1. The reconciled pre-review head was `4122dd245f60937cde44777cd5eda00ac03d25c9`; that protected-master catch-up changed no WP implementation path outside this carrier.

Independent final adversarial review `wp1-final-adversarial-review-20260827-sol-001` returned `REQUEST_CHANGES` against that reconciled head. The later Slack pickup key `wp1-final-authority-boundary-repair-20260827-sol-001` was addressed to Claude5 but remained unACKed and was explicitly STOPPED before pickup; it produced no code and remains historical transport evidence only. It was not resumed and is not commit provenance. Sol performed the accepted bounded repair directly on the same #178 carrier under the existing Chairman-authorized WP-1 operation `worker-presence-dialogue-wp1-20260827-sol-001`, creating no new branch, PR, Executive Job, Worker, lifecycle, provider session or alternate carrier.

The final repair preserves the accepted Relay/personal-principal distinction: the trusted Relay app may transport already-validated logical actors, but it is never inserted into the personal Sol allowlist and transport identity never becomes Executive authority. Repair scope is limited to V2 contributor→executive reply direction, V2 frame/presentation integrity, mutation/static no-rebuild coverage, and this current-base evidence amendment. Historical authorship receipts are not rewritten by this section.

Final-repair TDD evidence begins with RED commit `1080053d9fd80bb305f3142454269f94b7ddd829`, whose hosted repository gate failed only the four intended missing behaviors: CEO self-adjudication refusal, worker ChatGPT-trailer refusal, Unicode U+2028/U+2029 frame-integrity refusal, and Slack mention-shaped presentation refusal. Production fixes then landed on the same carrier in `539724c183bad2fffdd051464cb135906b38a800` and `2d721347fea6d58eb3c68fdb5f0e8ba31c9650e3`; expanded mutation/static-fence coverage landed in `2646c9a8af18deb7111126a6c1000fae6b095a71`. Exact-head repository CI on repaired head `965a94737aeb59782f053c3ffd7f3b637a109363` succeeded in run `33145345657`, and the Python, Actions and JavaScript/TypeScript CodeQL analyses all completed successfully.

Protected master then advanced by one records-only operating-surface convergence merge, #185 / `97f85ce5b84030faf4d291f988a1c642fb15e80a`. That source law explicitly preserves Worker Presence/#178 as the same-carrier completion lane and adds zero WP implementation/test/runtime paths. The #178 branch was therefore history-preservingly reconciled again in merge commit `36fbc08166e658e253779f675bd10aabd8b95f46`, with parents repaired WP-1 `965a94737aeb59782f053c3ffd7f3b637a109363` and protected `97f85ce5b84030faf4d291f988a1c642fb15e80a`; no reset, rebase or force update was used. The PR remained an eight-file WP-1 diff. Final acceptance must cite the exact final carrier head and its fresh hosted CI/security plus a fresh independent rereview rather than treating intermediate commits as completion.

## Exact scope / owned paths

Expected implementation/test paths are exactly:

```text
integrations/slack_agent_dialogue/contract_v2.py          CREATE
integrations/slack_agent_dialogue/engine_v2.py            CREATE
integrations/slack_agent_dialogue/service.py              MODIFY narrowly for versioned request/response dispatch
tests/test_slack_agent_dialogue_contract_v2.py            CREATE
tests/test_slack_agent_dialogue_engine_v2.py              CREATE
tests/test_slack_agent_dialogue_service.py                MODIFY narrowly for V1 regression + V2 dispatch tests
```

The final adversarial repair explicitly widens the acceptance-fence surface to `tests/test_slack_agent_dialogue_a1_static_fences.py` so the new V2 modules participate in the already-existing A1 no-persistence/no-network/no-duplicate-transport fence. This is proof/fence scope, not a new product or runtime path.

This checked-in commission file and the already-merged plan/spec are evidence/source-law files; ordinary implementation commits need not edit them.

`integrations/slack_agent_dialogue/contract.py` is **read-only by default**. If a truly unavoidable pure-helper extraction is needed, STOP and return the concrete falsifier to Sol rather than casually changing v1.

## Reserved / protected sister paths

WP-1 MUST NOT create or edit:

```text
integrations/slack_agent_dialogue/turn_watcher.py
 tests/test_slack_agent_dialogue_turn_watcher.py
control_plane/wake_*
control_plane/session_targets.py
provider-native Wake/worker transport paths
Slack production installation/credential/config paths
control_plane/executive_agent_capabilities.py
config/executive_agent_capabilities.json
integrations/mastermind_company_mcp/**
Agent OS / Linear state
```

The first two are reserved for WP-TW1 after WP-1 acceptance. Company MCP paths are reserved for WP-2 after WP-1 acceptance.

## Explicit non-goals

Do not:

- install/configure/arm the production Agent Relay Slack app;
- request or store Slack tokens, MCP credentials or OAuth state;
- send a real Slack message;
- add `chat:write.customize` or any Slack scope;
- create/read/modify Executive Jobs, Attempts, Workers or Events;
- classify turns into `WAKE_CEO` / `WAKE_COO`;
- create `AgentDialogueAttention`;
- mint or route Wake obligations;
- add a background polling/observer loop;
- register persistent waiters/cursors/inboxes;
- add a database, queue, scheduler, replay ledger or session registry;
- change provider selection, CF2/HF1/PF1/MH1, C1/B2/C2, or Wake #174;
- implement WP-2, WP-TW1, WP-TW2 or WP-3 in this carrier.

## Complete machine journey

### V2 thread creation/binding

```text
trusted already-authorized commission context
  -> V2 parent is built with immutable work_ref / commission_ref / session_ref
  -> exact operation_key is fingerprinted
  -> watch_mode is explicitly null or exact turn_watch_v1 and fingerprinted
  -> allowed Sol Slack principals are fingerprinted
  -> parent is rendered canonically
  -> V2 engine binds exactly one matching V2 parent
```

Historical V1 parent messages cannot satisfy a V2 binding and cannot become watcher-enabled by inference.

### V2 contributor message

```text
trusted actor/applicability context
  -> bounded semantic body
  -> actor_ref + applies_to mechanically validated
  -> worker_attempt actor exactly joins executive_attempt applicability
  -> canonical fingerprint generated
  -> existing injected SlackDialogueClient carries the frame
  -> same message key/fingerprint remains idempotent under reread
```

### V2 executive reply

```text
eligible executive_surface actor
  -> exact reply_to_message_key lineage
  -> existing TrustedAuthorityPolicy adjudicates consequential RULING semantics
  -> service carries reply in the same V2 context
```

Reasoning surface/provider/model name never grants executive authority.

### Failure/degraded journey

```text
wrong parent / changed operation_key / changed watch_mode / identity mismatch / history incomplete
  -> typed existing ASD refusal
  -> zero post or zero second post as applicable

Slack write EFFECT_UNKNOWN
  -> reconcile same thread + message key through existing history law
  -> never blind resend

V2 unavailable on service
  -> existing bounded request refusal
  -> V1 remains functional
```

## Data / contract / time / null / correction law

### V2 parent

Closed V2 parent keys are frozen by the merged plan:

```text
schema
work_ref
commission_ref
session_ref
operation_key
watch_mode
allowed_sol_user_ids
created_at
fingerprint
```

- `operation_key` is immutable semantic identity material.
- `watch_mode` is required and closed to `null | "turn_watch_v1"`.
- `watch_mode` is **admission metadata only** in WP-1; it grants no authority and causes no Wake behavior.
- `created_at` remains non-semantic clock evidence under the plan's fingerprint law.

### V2 actor

Closed actor families:

```text
executive_surface: kind + seat + reasoning_surface
worker_attempt: kind + job_id + attempt_id + worker_id
```

The implementation must use real current Executive Runtime test-generated IDs as positive worker vectors rather than inventing a Slack-specific Executive ID namespace.

### V2 applicability

Closed families:

```text
repository: repository + head_sha + pr
executive_attempt: job_id + attempt_id + worker_id
```

For `worker_attempt`, the actor triple and `executive_attempt` applicability triple must match exactly.

### Correction / replay

- duplicate message key + identical fingerprint = same semantic message;
- same key + changed fingerprint = conflict/refusal;
- edits/deletes require complete creation evidence under existing ASD law;
- V1 frames never satisfy V2 operations;
- no mutable cursor or current-time heuristic participates in identity.

## Deterministic / model-generated boundary

All identity, schema validation, canonical JSON, fingerprints, actor/applicability joins, message-family eligibility, presentation labels, version dispatch and history reconciliation are deterministic first-party code.

Model/worker text is inert bounded semantic content. It cannot author:

```text
worker identity
Executive seat/effective grant
operation_key
watch_mode
Slack channel/thread
presentation identity
provider/account/host
Wake target/kind
lifecycle status
```

## Failure states to discriminate

At minimum, tests must distinguish:

- malformed/extra V2 parent keys;
- malformed or changed operation key;
- null watcher versus exact watcher versus unknown watcher mode;
- V1 parent offered to V2 engine;
- unknown/extra actor fields;
- worker/applicability Job, Attempt or Worker mismatch;
- contributor trying to emit executive-only reply families;
- CEO/COO/chairman message-family mismatch;
- reasoning surface laundering authority;
- caller-supplied presentation identity;
- duplicate message same fingerprint;
- duplicate key changed fingerprint;
- incomplete history/reconciliation evidence;
- edited/deleted frame without creation evidence;
- Slack transport unavailable before effect;
- Slack send effect unknown;
- V2 request sent to V1-only service;
- malformed/oversized AF_UNIX request/response;
- disallowed AF_UNIX peer UID;
- accidental persistence/network/Wake/provider import in new V2 modules.

## Ordered implementation sequence — TDD is mandatory

Use the merged WP-1 plan task-by-task. For every behavioral addition:

```text
RED: write one discriminating failing test
-> run exact test and confirm it fails because behavior is missing
-> GREEN: minimal implementation only
-> rerun focused test and relevant V1 regression suite
-> refactor only while green
```

**No production code before a failing test.** Do not write the implementation first and backfill tests.

Sequence:

1. V2 parent/message contract + actor/applicability/presentation, with V1 regression.
2. Normal storeless V2 engine, with no watcher behavior.
3. Versioned V2 AF_UNIX request/response dispatch in existing service, preserving V1.
4. Adversarial/mutation/no-rebuild acceptance and exact changed-path census.

## Acceptance tests and proof

Focused acceptance must include:

```bash
python -m pytest \
  tests/test_slack_agent_dialogue_contract.py \
  tests/test_slack_agent_dialogue_contract_v2.py \
  tests/test_slack_agent_dialogue_engine.py \
  tests/test_slack_agent_dialogue_engine_v2.py \
  tests/test_slack_agent_dialogue_service.py \
  -q
python -m compileall -q integrations/slack_agent_dialogue
git diff --check
```

Also require:

- discriminating mutation/source-structure fences defined in the merged plan;
- exact changed-file census against current protected master;
- hosted exact-head repository CI;
- CodeQL/security checks;
- independent adversarial review attacking identity laundering, V1 drift, hidden persistence, hidden Wake behavior and sister-session path collision.

**No production Slack proof is owed or permitted in WP-1.** Green CI earns implementation evidence only.

## Stop condition

STOP and return to Sol when:

- the exact WP-1 files implement the full plan;
- focused tests, hosted CI and security checks pass at the exact returned head;
- independent adversarial review is complete;
- v1 compatibility is demonstrated;
- no forbidden/sister path is changed;
- the carrier remains production-inert.

Do not self-merge. Do not start WP-2, WP-TW1, WP-TW2 or any live canary.

Also STOP immediately on any material source-law/path collision, unsafe need to edit v1, or discovery that the accepted plan requires a duplicate authority/control plane.

## Required continuation handoff to Sol

Return one cold-stranger packet containing:

```text
operation_key
exact branch + head SHA
exact changed files
RED-before evidence summary per task
focused test results
full hosted CI/check-run identities
CodeQL/security status
independent adversarial-review verdict/findings/fixes
V1 compatibility receipt
mutation/no-rebuild receipt
all discoveries/falsifiers
what is BUILT_NOT_PROVEN
what remains NOT_BUILT
explicit confirmation: no Slack credential/app/scope/live message, no Wake, no Job/Attempt/Worker mutation
recommended exact next action
```

The expected next dependency on PASS is Sol acceptance/merge of WP-1. Only after that may separate WP-2 and WP-TW1 carriers be released in parallel.
