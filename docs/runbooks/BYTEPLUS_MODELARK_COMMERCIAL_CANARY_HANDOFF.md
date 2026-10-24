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
the distinct commercial realm and two exact Flash models, that Personal Coding
Plan remains held, and that all commercial candidates remain out of live tiers.
The SHA-256 of ModelRouter source is diagnostic, not installed provenance.

## 2. Credential-owner canary after review acceptance

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

Once independent semantic review passes, the existing credential owner should:
1. Verify the real commercial account/region, activated exact model IDs, and
   Responses + Codex tool schema compatibility from issuer-owned facts.
2. Bind the commercial key only through the existing worker-private provider
   home loader in control_plane.codex_provider_realm. Never store it in source,
   command argv, global/shared environment files, shell history, or CI.
3. Qualify a pinned Codex binary in a bounded, isolated, non-production
   Responses transport canary using the source realm's config_overrides.
   Do not use the ordinary Worker START path until the transport is reviewed.
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
Flash worker only after accepted review and a verified immutable generation.
Observe separate QUEUED, STARTED, terminal, provider-origin debit/usage,
collected result, accepted result and quota lease release.

Before-START zero headroom, 429, 401/403 and unqualified host must fail closed.
Fallback may use another already-lawful same-tier candidate only when the
original effect is proven absent. After START or EFFECT_UNKNOWN, no duplicate
request, carrier change or provider rehome. Full GLM 5.3 tasks never demote
to Flash merely to save capacity.

Current outcome classification: source contract BUILT_NOT_PROVEN. Key, real
transport, issuance/capacity facts, live Worker and production acceptance
are NOT ATTESTED. This runbook adds no control plane or release authority.
