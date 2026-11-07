# H2 — Account entitlement, quota and reset coverage

Programme: [#983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983),
`WS:EXECUTIVE-CAPACITY-FABRIC`. Assignment:
[HERMES_POOL_H2_20261107_C3](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6705878207).
Pickup and installed coverage:
[HERMES_POOL_H2_20261107_C1_PICKUP](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6706283300).
Operation: `hermes-pool-h2-entitlement-20261107-c1`.
Compatible protected procedure/source pin: `779fc3be9d07c366bf5b47c650b64e59fc6f3903`.
Observation date: 2026-11-07 UTC. This document is evidence and integration guidance,
not another account, quota, admission, identity or publication authority.

## Capability and acceptance boundary

Before: the installed quota reader could preserve optimistic cache after configuration
change, accept an invalid observation clock as read-time freshness, and report aggregate
GLM `OK` from different accounts' complementary windows. Go already had a collector,
but its public status omitted the original observation time. A per-response Go debit
was not a remaining-balance observation.

After source qualification: the existing reviewable quota-reader successor exposes
per-account, endpoint/configuration-bound evidence; invalidates readiness at reset;
keeps failures and their attempted generation; requires all applicable windows on one
account; and exposes the result through the original `show --qualified` CLI and
`glm_quota_decision`. It does not grant APPLICATION entitlement or prove no-overage.

**BUILT_NOT_PROVEN for installed H2 behavior.** The installed original refresh path
was exercised successfully. Source tests are separate from production installation,
natural reset evidence, application dispatch and programme acceptance. The source
carrier preserves all historical preimages/manifests and the selected native generation.
No provider inference, lease, account/credential change, service start/reload, or
generation selection was performed by H2.

## Actual configured coverage

The names below identify entries in incumbent account configuration. They are not
an upstream attestation that every alias is a distinct subscription or physical account.
No secret values or secret-derived hashes are retained. Models/caps describe actual
configuration observed on M2; they are not a claim about the provider's capacity promise.

| Pool / account | Actual configured product and endpoint | Configured model / workload | Configured admission cap | Quota source and exact qualification |
| --- | --- | --- | --- | --- |
| GLM `chairman-max` | Personal Max intl coding; OpenAI `https://api.z.ai/api/coding/paas/v4`; Anthropic `https://api.z.ai/api/anthropic` | GLM-5.3 review/operator; GLM-5.3-flash executor | 8; 24 across three entries | Original authenticated Z.ai quota/limit reader; 5h and weekly observed at 11:31:47Z. Hermes is listed by official supported-tool docs; an actual APPLICATION grant remains unproven. |
| GLM `chairman-max-2` | Same configured plan/endpoints | Same configured workload mapping | 8 | Separate original account read at 11:31:47Z; 5h reset is null and is preserved. No inferred new window or extra capacity from model aliases. |
| GLM `chairman-max-3` | Same configured plan/endpoints | Same configured workload mapping | 8 | Separate original account read at 11:31:48Z. Shared keys/aliases/consumers must resolve to this account's same allowance, never summed percentages. |
| Go `C1` | OpenCode Go entry; incumbent GoRouter defaults to legacy `https://opencode.ai/zen/go/v1` | Configured DeepSeek-v4.1-flash executor; actual model/plan coverage requires endpoint qualification | 3; 9 across three entries | GoRouter.refresh already reads `/usage` rolling/weekly/monthly. Live local health was unavailable; retained usage latest 2026-10-09, no fresh original snapshot clock. UNKNOWN; not admitted from this evidence. |
| Go `C2` | Same configured Go product/legacy endpoint | Same configured default | 3 | Same existing collector, separate entry. Plan tier, physical allowance scope, no-overage state and current endpoint entitlement unverified. UNKNOWN. |
| Go `C3` | Same configured Go product/legacy endpoint | Same configured default | 3 | Same evidence gap. A GLM model hosted by Go remains Go allowance; it is not a fourth Z.ai account. UNKNOWN. |
| MiniMax `default` | MiniMax coding configuration; OpenAI `/v1` and Anthropic `/anthropic` on `api.minimax.io` | MiniMax-M3 configured executor | 7 | Original authenticated token_plan/remains reader; general 5h and weekly observed at 11:31:44Z. Subscription-key versus PAYG/credit-pack billing and actual APPLICATION grant require owner qualification. |
| Bailian `Ryan` | Existing Alibaba/Bailian coding account owner | Configured Qwen worker pool | 7; 21 across three entries | No documented authoritative Token Plan balance endpoint found in the existing reader. Retained September local estimates are stale, not live allowance. UNKNOWN. |
| Bailian `Chris` | Same existing provider/account owner | Same configured pool | 7 | Historical local estimate only; no current authoritative balance/reset. UNKNOWN. |
| Bailian `Kris` | Same existing provider/account owner | Same configured pool | 7 | Historical local estimate only; no current authoritative balance/reset. UNKNOWN. |
| Grok / Cursor | Existing native worker configurations | Configured worker capabilities only | No numeric cap attested in this read | No general Hermes APPLICATION entitlement follows from worker configuration. The separate Grok manual ACP billing/marker constraints remain intact. |
| `ocfree` | Existing OpenCode free worker configuration | Worker-only membership observed | 3 | Paid Go entitlement does not establish free-tier external-client rights. Not offered as verified Hermes application capacity. |
| `codex-native` | Existing native worker membership | Worker-only membership observed | 1 | No inferred direct APPLICATION grant or included-plan API allowance. |
| `claude-native` | Disabled native membership | Not AUTO-enabled | 1 configured | Disabled remains disabled. |
| Experiential Labs | Separate disabled/manual-only protected integration | No AUTO enablement | Not admitted | Existing account-denial, readback and retention holds remain. Plugin presence is not permission, enrollment or quota proof. |

The observed M2 `provider_accounts.v1` configuration did not contain the explicit
`application_grants` required by the original `_read_application_accounts` owner.
Consequently none of these worker caps alone proves a Hermes APPLICATION route.
Configured concurrency, upstream rate limits, quota windows, remaining credits and
Fabric spend limits are distinct constraints. Unobserved upstream rate/concurrency
limits and monetary balances stay UNKNOWN; the caps above are not renamed as quotas.

## Provider semantics and entitlement

### Z.ai

Official [other supported tools](https://docs.z.ai/devpack/tool/others) lists Hermes
Agent and documents coding-specific compatible endpoints. The
[FAQ](https://docs.z.ai/devpack/faq) describes shared account usage across supported
coding tools and 5h/weekly limits; the
[usage policy](https://docs.z.ai/devpack/usage-policy) retains tier-dependent limits.
Therefore a blanket exclusion of Hermes merely because this is a coding plan is not
supported. The actual product/key, endpoint, allowed workload/model, account-sharing
constraints and incumbent APPLICATION grant still need to agree. Provider support
documentation does not silently enroll the account in Fabric.

Z.ai token/credit window units 3 and 6 are treated as 5h and weekly by the existing
reader. Unknown units are no longer guessed by array position. The separate monthly
MCP window is retained as `mcp/monthly`, not added to inference headroom.

### OpenCode Go

Official [Go documentation](https://opencode.ai/docs/console/go) specifies three
limits: five-hour 20%, weekly 50%, monthly 100% of the model- and plan-dependent
monthly limit. These are overlapping constraints, not additive wallets. Actual
provider reset timestamps are retained; undocumented clock anchors are not invented.
The current documented endpoint family is `/inference/go/...`; the installed legacy
endpoint is recorded above, not silently migrated or assumed equivalent.

Go documents direct API/client use, including supported Hermes versions, a descriptive
User-Agent and stable session identification on main and auxiliary requests. Applicable
native Claude/Codex metadata may supply the session identity; do not impose a false
universal literal-header rule. The route must prove its actual metadata behavior.
Go Teams excludes service accounts and defaults Extra Usage on. The account owner must
prove Extra Usage is off or an equivalent hard no-overage ceiling for the exact route;
the presence of an API key and an included-plan label does not prove that condition.

The [inference API](https://opencode.ai/docs/console/api/inference/) defines
`usage.opencode.allowance` (Gemini: `usageMetadata.opencode.allowance`) as that
request's debit in dollars of the plan monthly limit. It is **not remaining quota**.
`cost`, `list_cost`, `billing_source` and included-plan debit are separate facts.
Missing final usage or pricing is unknown, not zero. A zero balance charge does not
mean zero included allowance consumption; account meters may update after the response.
The source parser retains debit as `monthly_allowance_usd`, without cap, remaining
percentage or invented reset. The existing H4 usage/budget owner must consume pricing.

### MiniMax and the remaining pools

The official [MiniMax plan guide](https://platform.minimax.io/docs/m-plan/quickstart)
distinguishes subscription and PAYG keys and documents API use. It does not establish
the billing status of the observed key. The general provider percentage and count
units are preserved separately; malformed percentages are not replaced by optimistic
counts. Credit packs/overage and stricter Fabric budget gates require actual evidence.
Bailian local reconstruction cannot release a live allowance gate. Grok remains on
its separate authenticated manual evidence path; neither Grok nor Experiential is
automatically enabled by this work.

## Installed refresh receipt

At 11:31Z the already installed native launcher executed its original `pool status`
entry once on M2. Studio process 55258 completed with exit 0 in 4.91 seconds;
the native command returned 0 with empty stderr. This exercised the existing quota
reader and its original cache. `pool refresh` is host-pull, not this quota path.

Selected native generation:
`ef94479b8c768088e7c6b611d498879b9b6896ba24faa2558135ad8465f8be46`,
CURRENT sequence 35. Selected quota module SHA256:
`3c1484864848b5cdf4daeecde092f7c407ab313a9f0d94a7f0fd204dbcf813b8`.
This is the unchanged installed candidate, not the H2 successor.

| Account | Provider observation UTC | Remaining 5h | 5h reset UTC | Remaining weekly | Weekly reset UTC |
| --- | --- | --- | --- | --- | --- |
| GLM chairman-max | 2026-11-07 11:31:47 | 99% | 2026-11-07 12:03:09 | 99% | 2026-11-14 06:25:24 |
| GLM chairman-max-2 | 2026-11-07 11:31:47 | 100% | null | 59% | 2026-11-09 01:39:33 |
| GLM chairman-max-3 | 2026-11-07 11:31:48 | 81% | 2026-11-07 14:20:12 | 75% | 2026-11-11 06:16:02 |
| MiniMax default | 2026-11-07 11:31:44 | 96% | 2026-11-07 15:00:00 | 20% | 2026-11-09 00:00:00 |

All four came from `PROVIDER_AUTHORITATIVE` rows and were fresh at readback. These
are historical timestamped receipts, not a claim that the balances remain current.
The initial receipt preceded the 12:03:09 boundary. One subsequent original-owner
refresh started at 12:03:18Z and completed at 12:03:22Z (Studio PID51107, exit0,
4.78 seconds, empty stderr). Generation and sequence35 were unchanged before/after.
At **12:03:21Z**, the provider reported chairman-max 5h remaining **100%**, up from
99%, and a **null** next-reset clock. Its weekly balance/reset stayed99% / November14.
This is observed natural window replenishment, not an elapsed-clock inference,
recovery from total exhaustion, APPLICATION admission or installation of H2 source.

Post-refresh 5h/weekly observations at12:03:18–22Z were GLM chairman-max100%/99%,
chairman-max-2 100%/59%, chairman-max-3 76%/74%, and MiniMax96%/20%. The null
five-hour clocks for the first two GLM accounts are retained. The exact before/after
selection, cache modification times, producer clocks and balances are in
[the structured original-owner receipt](evidence/hermes-pool-h2-original-refresh-reset-2026-11-07.json)
and the [same H2 return carrier](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6706283300).

## Initial source qualification and remaining consumer joins (05454ec)

27 H2 regression tests passed locally, including all-three-window Go conjunction,
malformed/missing/future clocks, null/reset boundaries, separate physical entries,
configuration replacement during read, key-rotation metadata without secret hashing,
failure retention, no alternate-header retry after 401/403, denial-generation provenance,
cross-window GLM exhaustion, local-estimate exclusion and CLI read projection.
Cache publication failure is surfaced to the original owner; a refusal that could
not be persisted is not claimed durably recorded and is not retried within the call.
The existing seven Grok billing tests also passed, including frozen source/candidate
manifest checks and no model-prompt/automatic marker mutation. These are local tests;
hosted CI is an independent release condition recorded on the exact PR head.

Initial head17164ab CodeQL identified clear-text sensitive-data storage in the
key-rotation test fixture. The test used a deliberately fake token, not a real
credential. The repair keeps both credential-shaped fixture objects in memory and
writes only public revision/endpoint metadata to its temporary owner file. The
generation-change and no-secret-hashing assertions remain; no query, severity,
assertion or security gate was suppressed. Hosted requalification must cover the
repaired head before release. The production quota-reader bytes are unchanged by
that fixture repair.

The source successor is `ops/native_fabric/grok47/quota_billing/quota_remote.py`, the
existing replacement surface. No frozen candidate/source, generation manifest, active
GoRouter, APPLICATION writer, credential file or runtime configuration was modified.
Configuration generations hash public endpoint fields plus file revision metadata;
they are local invalidation fences, not provider physical-account attestations. Aliases
and shared allowance scopes must still be joined by the incumbent account owner.

Exact remaining joins, in the original owners:

1. **H3 / quota consumer:** pass the current `config_generation` into the cache-only
   GLM park helper and use qualified paired windows. False narrow park is not dispatch
   permission. Reconcile terminal refusals under the existing owner; configuration
   change alone is not permission to replay a denied observation.
2. **GoRouter / APPLICATION owner:** expose original `snapshot_at`, account/config
   identity, endpoint and refresh failure beside `provider_windows`. The current
   status construction may predate its later eligibility refresh. Do not stamp a
   status read with now or introduce another collector. Normalize that exact snapshot
   with `parse_go_usage_payload`, then require all three windows in `account_quota_view`.
3. **H4 / entitlement and dispatch:** establish physical allowance grouping, explicit
   APPLICATION grants, model/workload/endpoint entitlement, required client/session
   metadata, hard no-overage and existing stricter budgets. Then prove one genuinely
   admitted, correctly attributed consumer path. H2 quota evidence is not that proof.
4. **H5 / projection:** consume the same qualified per-account view, including UNKNOWN,
   failure generation and null clocks; do not sum aliases or percentages.
5. **Native publisher:** compose the accepted successor and the consumer joins through
   final APPLICATION #2175 / Macro #10740 and shared-pool #2109/#2182. Preserve the
   actual current selected predecessor, original J recovery custody and gateway
   uncertainty. Build/verify the complete successor before an authorized CAS selection.
   This isolated source contribution does not replace the active final carrier.

At 11:50Z #2175 remained actively written (head
`84ef19e38c2dcb5d4ba3017812e9c13cd1f9ae2c`) and #2182 remained a held draft
(`b5d7ece3acac6569d60b428e63af535e81ddd417`). Its active composition is the concrete
integration boundary. No orphaned historical author is an approval gate.

The canonical C0–C5 plan remains
[`docs/SHARED_MODEL_POOL_CONTROL.md` at 8dc8eb42](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8dc8eb42df7ed1f3c79f434da30df9ad12dafe14/docs/SHARED_MODEL_POOL_CONTROL.md).
Agent OS owns organisational continuity; the inspected `WS-EXECUTIVE-CAPACITY-FABRIC`
record did not expose a strict November 7 dated handoff. Do not invent that linkage or
mark the programme complete. This source document and #983 retain H2 recovery evidence.

## GLM reset-card continuation

The Chairman subsequently requested manual reset-card investigation and complete
automatic counter/cooldown recovery. The [reset implementation and operating
contract](HERMES_POOL_H2_GLM_RESET_RECOVERY.md) records official cycle semantics,
the unsupported public automatic-redemption contract, and the exact consumer joins.

The H2 successor now includes the original quota-circuit successor and bounded
Broker/picker patches. These supply the GLM paired-window generation join and keep
on-demand refresh reachable while the account is quota-blocked. Fresh evidence can
open one original half-open probe; its exact successful-work receipt clears the
matching old cooldown. This supersedes the initial missing GLM cache-only consumer
argument listed above. H3's broader expiry ranking, physical/shared-account identity
and operation ceilings remain distinct; Go freshness, H4 grants/no-overage, H5
projection and final native selection still require their actual owner receipts.

The concurrent same-carrier CI repair at `d538ca9dc42135cb43c769f1a124a2b7286c3dd4`
is preserved. It names terminal HTTP statuses with `HTTPStatus` and changes no
provider behavior. Reset implementation continues on that head, the original branch
and operation; no source or runtime effect is moved to a replacement programme.

Final reset continuation qualification passed 43 account/quota, 16 broker/picker
journey and 7 existing Grok cases. The same 16 journeys passed after composition
against isolated copies of the actual sequence-35 selected native predecessor;
[the byte-bound receipt](evidence/hermes-pool-h2-glm-reset-predecessor-2026-11-07.json)
records all input hashes and the unchanged selection. Overlapping rate holds,
refusal-publication contention/failure and a refresh arriving during atomic claim
are covered. Source and fixture qualification remain distinct from installation
or live exhausted-account/reset-card recovery.
