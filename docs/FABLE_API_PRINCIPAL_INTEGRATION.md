# Fable 5.1 API principal in the existing Mastermind Fabric

**Status:** source-only / unarmed. No funded API call, provider enrollment, deployed secret, completed Fabric lifecycle, or live product proof is claimed.

**Decision:** add one metered principal advice call beneath the existing Executive OS / ModelRouter / Capacity and Agent OS responsibilities. Do **not** add a second autonomous Meta-CEO, job queue, memory or credential authority. The Anthropic API is distinct from Claude Code's subscription session adapter.

## Source paths

- config/executive_worker_routes.json: fable.api.principal selects exact model claude-fable-5-1 with provider anthropic_api, explicitly disabled and non-worker.
- control_plane/worker_adapter.py: closed, **unimplemented** anthropic-api-principal descriptor. Merely enabling the disabled provider still fails router policy loading until an approved installed composer is qualified.
- control_plane/model_router.py: incumbent METERED_EXCEPTION with complete MeteredCognitionReceipt (why metered, why included Chat insufficient, estimated cost, hard cap, stop, approved budget reference).
- control_plane/fable_api_principal.py: single-use, text-only Messages API transport using pinned HTTPS host and model; checks route+receipt, reserves the worst-case call ceiling through a **trusted existing Capacity owner callback**, reads a credential only after reservation through the **existing secret owner callback**, and checks provider identity / completion / usage before returning a bounded advisory result. It owns no durable state.
- tests/test_fable_api_principal.py, tests/test_fable_api_route.py: negative admission, no-replay, secret, usage and dead-catalogue tests.

## Intended end-to-end journey

1. The real Meta-CEO/Project conversation establishes the original root and required evidence; the resulting request is a **review-only** strategic question with cited source references and an explicit stop condition. Evidence remains untrusted data.
2. The existing Model Router selects fable.api.principal only for C3_FRONTIER_JUDGMENT, with a concrete frontier witness and complete METERED_EXCEPTION receipt; ordinary workers remain GLM/Grok/Codex/other economical routes.
3. Existing Executive OS admission and RuntimeBinding bind a single original Attempt; Capacity atomically reserves its budget against the **linked Anthropic Console organization** with verified available promotional credit. The reserve callback returns a receipt tied to the exact root, attempt and budget authority. Account/credit state must be observed from the real owning Console; no statement in a prompt can substitute.
4. Only inside that admitted, bound Attempt, the existing secret owner loads the restricted Anthropic API credential. The original Executive Attempt owner must then acknowledge the request SHA-256 and reservation reference via the injected dispatch callback **before** any paid send. FableApiPrincipal.invoke executes **at most one** POST https://api.anthropic.com/v1/messages, model claude-fable-5-1. The advice receipt retains original source references, request/response SHA-256 and provider usage; it is not a billing statement. No Claude Code OAuth token, subscription wrapper, streaming tool loop, dynamic provider URL, retry, automatic fallback, or autopay is involved.
5. The owning Executive Attempt records **distinct** reservation, provider-request, completion, actual usage, reconciled settlement and terminal return evidence. An ambiguous send, non-200, mismatched model, truncated answer or excessive charge is NOT automatically replayable. The same original Attempt must be reconciled by the lifecycle owner.
6. Advice returns through the incumbent Agent OS / dialogue path. It cannot merge, deploy, authorize spending, execute trades, or independently create a successor job. A real product journey displays the advice and falsifiers with linked sources and an actionable next step.
7. Optional Fabric worker/independent reviewer receives bounded follow-up via the **existing** Subagent Fabric provider/Capacity selection, without re-parenting the original root or silently transferring authority.

## Activation gates and current blockers

These gates remain **unmet** unless separately observed; source tests are not evidence of live eligibility:

1. **Console human/auth gate:** account owner links the Max 20x monthly API credit to the intended Anthropic Console organization, authorizes an API workspace key and confirms its eligibility/remaining credit. Do not expose credentials in repo, PR, logs, prompts, SDK trace, or chat.
2. **Capacity/Billing gate:** reuse the existing capacity reservation/settlement owner with an atomic per-Attempt allowance and an account-level monthly stop. Promotional credits are not an unlimited monthly entitlement; no auto-reload, fallback paid account or overage without an approved new spend envelope. Multi-Attempt concurrency must be covered by the existing atomic owner.
3. **Trusted host/execution gate:** an authenticated exact backend composer must supply current immutable route/RuntimeBinding, reservation callback, credential callback, original Executive Attempt dispatch acknowledgment callback, and attempt-owned once-only invocation. The disabled adapter descriptor and provider cannot be marked implemented/enabled solely because tests pass. A successfully loaded policy alias by itself is **not** Worker admission.
4. **Fabric/product integration:** expose principal consultation through an already-authorized Executive/Fabric contract, rather than permitting generic fabric_request users to select arbitrary providers, models, API keys or hosts. Confirm actual parent, original root, provider START, result, acceptance and terminal return.
5. **Real-path canary:** a small reversible funded call has an exact model ID, provider message ID, usage receipt, Console credit debit, accepted advice visible to the originating Meta-CEO, zero key leakage and no duplicate request. Qualify timeout/reconciliation with the original Attempt. Require an independent non-author review before normal protected merge/release.

## Local source qualification

python -m pytest -q tests/test_fable_api_principal.py tests/test_fable_api_route.py

Tests use synthetic in-memory metadata and fake senders, spending no credits. FableApiPrincipal is intentionally a non-worker helper. The FableApiEffectUnknown outcome is not permission to retry. The preflight input-byte estimate is conservative rather than a guaranteed provider billing upper bound. The original account-level hard limit and authoritative Console settlement remain mandatory. The post-hoc estimated_usd is a conservative estimate, not a Console billing statement; the existing account owner must settle authoritative spend and credit availability.

**Remaining product acceptance:** verified human-visible and machine-consumable Fable principal advice following one real authenticated funded request, cross-verified with the linked Console and original Executive/Fabric attempt/return records, with no duplicate control plane or unapproved spend.
