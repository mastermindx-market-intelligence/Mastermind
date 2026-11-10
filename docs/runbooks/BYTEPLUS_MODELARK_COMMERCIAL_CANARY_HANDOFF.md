# BytePlus ModelArk commercial — credential-owner canary and Worker/Capacity qualification

**Status: source-only preparation for Mastermind PR #1824. Production is NOT armed.**
The Chairman has already approved commercial ModelArk and commercial Codex use.
No further commercial-license approval is needed. The incumbent ProviderRealm
credential owner exclusively controls the private commercial API key.

## 1. Key-free checks now

Run in the existing PR worktree:

    PYTHONPATH=. python3 -m scripts.byteplus_modelark_commercial_preflight
    PYTHONPATH=. python3 -m pytest -q --noconftest tests/test_byteplus_modelark_commercial_preflight.py

The output must say evidence_scope=SOURCE_ONLY, credential_read=false,
provider_network_called=false, production_start_authorized=false. It validates
the distinct commercial realm, the two exact Flash models and the exact Dola
candidate, that Personal Coding Plan remains held, and that all commercial
candidates remain out of live tiers.
The SHA-256 of ModelRouter source is diagnostic, not installed provenance.

## 2. Credential-owner canary after source validation

Owner inputs, never shared with PR, Web session, or CI:

| Role | Exact contract |
|---|---|
| Commercial realm | byteplus-modelark-commercial |
| Provider | byteplus-modelark |
| Region endpoint | https://ark.ap-southeast.bytepluses.com/api/v3 |
| Protocol | Codex Responses |
| Secret owner name | BYTEPLUS_MODELARK_API_KEY |
| GLM Flash | glm-5-3-flash-260828 |
| DeepSeek Flash | deepseek-v4-1-flash-261017 |
| Candidate coding model | dola-seed-2-1-turbo-260628 |
| Retry policy | 0 request/stream retries |

Never use the Personal Coding Plan endpoints /api/coding or /api/coding/v3,
ARK_API_KEY, individual cookies, or subscriber usage balances.

After focused source validation and applicable release requirements, use the
existing credential owner for one authorized bounded Flash-model canary.
A separate reviewer is required only when an actual protected rule requires
one; the current session-local policy is not a blanket review hold.

The credential-owner operation must:
1. Verify the real commercial account/region, activated exact model IDs, and
   Responses + Codex tool schema compatibility from issuer-owned facts.
2. Bind the commercial key only through the existing worker-private provider
   home loader in control_plane.codex_provider_realm. Never store it in source,
   command argv, global/shared environment files, shell history, or CI.
3. Qualify the actual selected transport in a bounded, isolated,
   non-production Responses canary. For the Codex journey, pin the binary
   and use the source realm's config_overrides. For the application journey,
   use the existing commercial Responses transport and its settlement owner.
   The ordinary CodexWorkerAdapter still explicitly refuses ModelArk START;
   changing transport registry membership cannot authorize it.
4. Observe the terminal response, actually served model, finite nonzero
   provider-issued usage and a billable token/debit reference. A free-trial
   zero-debit response does not establish commercial accounting.
5. Retain only secret-free provider-origin evidence references and minimal
   model, account-region reference, executable digest, usage/debit,
   termination and provenance metadata in the *existing* evidence owner.

401/403: park enrollment and identify the scoped auth/permission problem,
never fall back to a Personal Plan secret. 429: retain cooldown and account
limits; no automatic retry after an uncertain effect. Timeout/EFFECT_UNKNOWN:
reconcile the original attempt/charge before any further action.

**A successful transport canary does not mint live Worker/Capacity rights.**

## 3. Real registered Worker and Capacity identity

The Worker/Capacity owner — not the credential owner or this source preflight —
must register a real commercial provider-bound Worker/quota class in the
existing Executive WorkerRegistry. The quota provider must be exactly
byteplus-modelark, never byteplus, glm or codex. Use the existing
mastermind.executive_capacity_join/v1 metadata, with a qualified remote
host_ref, a real capacity_capability_id,
provider_capacity_schema=mastermind.provider_capacity.v1,
and exact installed worker_source_config_digest (lowercase SHA-256).

Read only that genuine registered quota through the existing helper:

    from scripts.byteplus_modelark_commercial_preflight import capacity_identity_preflight

    # These are already obtained from the incumbent Registry/install owner.
    report = capacity_identity_preflight(
        registry=existing_worker_registry,
        candidate_keys=[(registered_worker_id, registered_quota_class)],
        expected_worker_source_config_digest=verified_installed_config_sha256,
    )
    assert report["capacity_join_identity_validated"] is True
    assert report["production_start_authorized"] is False

The helper reuses control_plane.executive_capacity_join.read_remote_capacity_joins;
it never enumerates Workers, stores keys, ranks providers or creates a registry.
It checks identity, not slots. A synthetic quota fixture is not production proof.

Provider Control and Capacity owners must separately prove fresh issuer account
scope, available concurrency and token quota, spend cap, source generation,
host health, lease, model suitability, account cooldown, and current limits
at *claim time*. No capacity preview or static identity join admits a job.

**Existing incompatibility:** Z.AI GLM sealed read-only research and commercial
BytePlus Codex sealed write use different execution profiles. They cannot be
smuggled into one first-lawful ModelRouter tier just to trigger the preference.
Qualify the compatible execution profile and actual Worker binding first.

## 4. First controlled Executive canary — after all preceding gates

Use the incumbent Executive Job/Attempt/Worker, Capacity, ModelRouter,
ProviderRealm and installed release owners. Admit ONE bounded commercial
Flash worker only after genuine Worker/claim qualification and a verified
immutable generation. The source-only adapter refusal must not be bypassed;
its eventual successor must consume the actual owner-bound admission facts.
Observe separate QUEUED, STARTED, terminal, provider-origin debit/usage,
collected result, accepted result and quota lease release.

Before-START zero headroom, 429, 401/403 and unqualified host must fail closed.
This recovery authorizes no provider fallback. After START or EFFECT_UNKNOWN,
retain the original request, account and settlement owner until reconciled;
never duplicate the request, change carrier or rehome it. Full GLM 5.3 tasks
never demote to Flash merely to save capacity.

## 5. Application Capacity consumer contract

Application HTTP uses the incumbent broker's account binding, finite lease
and dispatch permission, one-send transport and terminal usage settlement.
It does not acquire an Executive Worker identity merely to make an HTTP
request. Keep the autonomous Worker qualification in sections 3-4 separate.

At the November 7 UTC protected-source integration, the native application
HTTP binding admits Bailian, and the sealed metadata contains only Bailian
and MiniMax. ModelArk has no admitted native HTTP account/pool binding.
Macro #10521's commercial provider modes supply transport and accounting;
they do not supply Fabric admission. Macro #10740 carries the application
Fabric client/factory absent from the inspected Macro main. Compose those
existing owners; never add a direct Hermes pool controller, a provider
waterfall fallback, or a wrapper that emits a second usage charge.

Before selecting a commercial application model, require the distinct
byteplus-modelark provider and byteplus-modelark-commercial realm in the
existing native registration, a qualified account/region and exact model,
the credential-owner binding, verified generation, bounded spend/tokens
and fresh admission. Preserve the existing Personal Coding Plan's identity,
eligibility and accounting. No alias or synthetic test account satisfies
these requirements.

The successful consumer receipt must link the original operation and
account reference to its selected and actually served model, transport
request/response reference, provider-origin input/output usage and debit
reference, terminal response, broker settlement and released lease.
Credential values must never enter the receipt. Record any unknown effect
against the original operation before further work.

Current outcome classification: source contract BUILT_NOT_PROVEN. Real
account/credential enrollment, transport qualification, fresh issuer quota,
commercial native admission and consumer acceptance are not attested by
this runbook. It adds no control plane or release authority.
