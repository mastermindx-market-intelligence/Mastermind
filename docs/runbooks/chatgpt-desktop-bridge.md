# Grok / ChatGPT Desktop bridge: evidence boundary and release gate

## Scope and current capability

The user journey is Grok on an admitted mini -> exact local ChatGPT conversation
-> verified mode and prompt -> completed response -> Grok decision -> existing
Executive continuation. This repository increment implements only the pure turn
preparation and evidence-reduction boundary. It is `BUILT_NOT_PROVEN` and
`PRODUCTION_INERT`; no native producer, actuator, host service, Grok invocation,
worker registration, or fleet installation is enabled by importing the package.

The legacy 488-line Python controller was recovered at SHA-256
`6020664a3ce47ba61d4c251d3026e5691e4479aa57684786efe2105e54f9fb5d`.
It demonstrates local UI mechanics, not a verified bidirectional worker. Its
fuzzy session search, global input, unchecked click results, and success message
after Enter must not become the production sender. Existing installations are
not modified by this change, and no live transcript is committed here.

## Keep surface, model, effort, usage and authority separate

Extra High does not inherently require Work. OpenAI documents Extra High in Chat
on eligible plans, while Work follows Codex usage accounting. Therefore the
preparation API defaults to a Chat-only envelope. Work requires a separate
explicit projection from the current scope/spend owner, never a Grok-chosen
boolean or an implicit recovery fallback. Exact options must be observed on the
bound seat. Neither `Latest` nor prose saying 'think harder' proves selection.

Official references, checked 2026-10-02:
- [Chat models and thinking levels](https://help.openai.com/en/articles/20001354-GPT-5.6)
- [ChatGPT Work and Codex](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)

No quota, account entitlement, hidden reasoning budget or future model is hardcoded.
A selected UI model is not backend served-model attestation: the return preserves
`served_model=UNKNOWN`. Product availability alone is not permission for unattended
use; provider terms, workspace permissions and canonical admission remain gates.

## Existing owners and integration seam

Executive / Operator Harness remains the only authority for operation IDs,
INTENT reservation, exclusive writer custody, durable at-most-once dispatch,
effect recording and successor admission. RuntimeBinding supplies exact target
identity. Agent OS owns organizational continuity. Grok Wake transports an admitted
nudge; this package does not change its contract or create another retry journal.

The integration consumes actual `OperationIntentReceipt` / `OperationIntentTarget`
with `OperationKind.BEGIN_TURN`. `prepare_turn` builds a correlated payload;
`verify_pre_dispatch` checks a fresh unchanged observation immediately before the
separately admitted effect; `reconcile_turn` reduces the exact post-effect evidence.
`TurnObservation.as_turn_start()` provides the existing `TurnStartObservation`.
The native publisher and runtime composition are not implemented in this increment.

A Python dataclass, content hash or 'semantic' flag is not trusted by itself. Only
the reviewed native producer can project authenticated host/seat/project/session
identity and scoped message evidence into this seam. Model-originated JSON must
never be accepted as native evidence or an admission envelope. These functions
cannot provide durable deduplication across processes; use the existing OHF owner.

## Native evidence required before a live sender can be admitted

One observation must bind the existing Attempt, worker, session epoch, process
generation and provider conversation to host, seat, project, app build, PID plus
process-start identity, window and RuntimeBinding generation. Fuzzy labels and
window titles are not conversation identity. Reused PIDs must fail closed.

The operation-relevant message region must be complete and role-scoped. A full
exact user bubble with native turn identity confirms input; a unique subsequent
assistant message linked to that user and turn, explicitly complete with idle
provider state, permits response capture. A quiet screen alone does not prove
completion. OCR, incomplete viewport text, duplicate branches, missing IDs,
unrelated messages and mode drift must not become success evidence.

The producer must prove these fields on the real installed app. When that is not
possible, report the missing field and keep the sender held; do not invent IDs,
read private provider internals, enable an undocumented transport or fall back to
unbounded screen scraping. Existing managed-browser restrictions are unchanged.

## Effect and recovery rules

Preparation writes and sends nothing. An existing composer draft, active turn,
auth/quota/safety/permission block, stale capture, changed target or wrong mode
refuses preparation. Pre-dispatch evidence must be new and content-identical.
After possible dispatch, absence is `EFFECT_UNKNOWN`, never permission to resend.
Keep the original carrier, operation and payload digest until OHF reconciliation.

Confirmed input and completed output are distinct. Confirmed input remains applied
when the provider reports an error; that error does not authorize another prompt.
Only a terminal `REQUEST_MODE: PRO` or `REQUEST_MODE: EXTRA_HIGH` line in a verified
completed assistant response is returned as advice, excluding code fences. It
never changes a mode, grants authority, transfers custody, or bypasses a refusal.
Grok may propose a next step; the current execution and spending owners decide
whether it is admissible. Completion of an answer is not acceptance of the mission.

## Required real-path qualification, in order

1. Review this source and close exact-head CI; retain its production-inert ceiling.
2. Qualify a permitted native semantic producer on one exact disposable test chat.
3. Compose with the existing OHF writer/effect fence and a scoped native actuator.
4. Prove a Grok-originated canary reaches that exact chat and returns the exact
   completed answer to Grok with separate input, answer and consumption evidence.
5. Prove Chat Pro and Chat Extra High selection under current seat eligibility;
   reject unavailable modes instead of entering Work or downgrading silently.
6. Inject interruption after possible send, layout drift, duplicate delivery,
   wrong account/project/conversation, stale capture and preexisting draft. Require
   no duplicate turn, no unrelated mutation and preserved unknown effects.
7. Obtain independent acceptance, publish an approved immutable release, install
   through the existing host owner, then repeat the proof separately on every mini.

## Current continuation and restrictions

Operation: `grok-chatgpt-desktop-bridge-20261002-sol-001`.
Procedure/source base: `12ae50fa35254f99719bbeed82fde6e1f1423104`.
The authorized source workspace was acquired through `mmx-workspace`; it is not
shared with other operations. The implementation is tested only with synthetic
messages and identities; native schema viability and all four-seat proofs remain
open. Exact-target UI reinspection was platform-blocked before tool dispatch.
That live action was not retried through another tool, host, model or worker.
No canary messages were submitted; no app, permission, service or fleet settings
were changed. This block is not evidence that macOS permissions were denied.
The next live step requires a platform-permitted inspection path, not a replay.

The connected Executive ingress reported readonly mode. No worker was dispatched
through it and no background execution or automatic return is claimed. This does
not establish that every other existing Fabric surface is unavailable.

Do not redo the historical broad fleet audit or deploy the legacy sender as a
shortcut. Review and test this candidate, recover the exact safe native frontier,
and continue the same mission only through current permission and custody gates.
The parent outcome remains incomplete until the native/Grok/fleet journey passes.

## Local validation

```sh
python3 -m pytest tests/test_chatgpt_desktop_turn.py -o addopts='' -q
python3 -m compileall -q integrations/chatgpt_desktop
git diff --check
```

These tests prove reducer behavior against explicit fixture evidence, not the
truth or availability of that evidence on a real ChatGPT or Grok installation.
