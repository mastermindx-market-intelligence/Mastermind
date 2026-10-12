# Subagent Fabric — GLM expiring-account claim: source implementation & proof

**2026-10-12 UTC.** Owner/mission: Fabric selector continuation, existing draft Mastermind PR #1365.
**State:** BOUNDED_SOURCE_IMPLEMENTED / 271 FOCUSED TESTS PASS / **NOT INSTALLED** / **NO PROVIDER-LIVE QUOTA CONSUMPTION CLAIM**.
**Protected compatible procedure pin:** Mastermind master 25c4b7923734392b1013afae179966985819d847, sol_skillpack.v1 1.0.1, bootstrap 1.

## Product outcome

A subscription's expiring allowance must actually be used by the account awarded the lease. The old R31 pool router correctly detected an impending weekly reset in a GLM **account**, but lost that account identity on the handoff into the per-pool broker. The broker's original \`_pick_account\` sort chose \`(held, -account_cap, account_name)\` and could select a different, later-reset GLM account.

The new **source-only** candidate adds an optional per-account urgency preference **inside the incumbent broker's existing atomic claim**. It does **not** add an account picker, provider controller, lease registry, worker retry, web model picker, credential reader, quota writer, second lifecycle, or new trust/authority. It is deliberately limited to GLM because the installed provider cache has per-account provider-authoritative weekly and 5-hour windows; MiniMax/Grok/bailian do not have equivalent verified multi-account window coverage here.

## Exact installed source preimage and candidate artifacts

| Installed file | Exact source SHA256 at build | Candidate after isolated patch SHA256 |
| --- | --- | --- |
| ext/lease_broker.py | c17558441d408ed743ef3e282b50db1f4cf8926aad9cca3977ceb867c0d8eb4f | 1ecabe7b1fb776987d9b8d0663b8e97f18897a0e8968b64690fa3e1968b975b3 |
| ext/tests/test_r31_glm_burn_down.py | 23cf5a9269c553f9e09cf82ec326878a492b712b73fcae5b3ad32777f4a85d5e | 86fcb91b5a644a9c90ab0f3dea9e4746d13cce762f714ed00af4acf2e7039ca6 |

Published artifacts, **patches + tests, not installed source modifications**:

- \`ops/native_fabric/patches/lease_broker_glm_expiry_account_20261012.patch\`, local patch SHA256 bf63eda2e3cca61ee460f5ae58cdc3e4f8db0d6d7c770946a1690160aa4daafa.
- \`ops/native_fabric/patches/lease_broker_glm_expiry_account_20261012.tests.py.txt\`, test SHA256 dadee5ba48db6180f4414933a8e5f9c8e189e81f1678db2b0502aaf2336a7460.
- \`ops/native_fabric/patches/test_r31_quota_truth_20261012.patch\`, local patch SHA256 371abe497309de58ba126a62d3ba511d67391da577b2666817695c93fdcf3b6a.

Prior PR #1365 exact-source selector patches for \`fabric_task.py\`, \`pick.py\` and their tests remain separate, compatible source candidates, not live installations.

## Behavior and invariants

Within the *same incumbent Broker* object and SQLite-serialized claim process:
1. Preserve current provider enabled/parked/host lane/model caps and concurrency/fairness gates. Explicit \`--account\` remains a hard pre-start account choice; urgency cannot override it.
2. For GLM only, read the installed Provider Control \`quota_remote.CACHE_PATH\` **read-only**. No \`glm_accounts_state()\` or \`read_provider()\` call in the claim lock (those can issue network requests and modify cache). Bound the cached file to a regular non-symlink <= 1 MiB, and reuse existing \`pick._burn_down_cfg(pick.load_pools())\` for the 36-hour/15%-remaining burn-down policy rather than defining a new knob.
3. Trust no quota urgency without exactly one *same account* weekly and one 5h \`PROVIDER_AUTHORITATIVE\` row, matching timestamps, matching GLM provider and expected window kinds. Validate cache refresh timestamp AND provider observation time against the smaller of the incumbent freshness and refresh interval, positive future reset times, finite remaining percentages and both balances at or above the incumbent minimum.
4. Among **already grantable, model-compatible accounts**, prefer the eligible soonest future weekly reset. Fall back to the existing held/cap/account stable sorting when no account has verified urgency. Never invent unused quota from UNKNOWN/LOCAL_RECONSTRUCTION, stale, past or inconsistent windows. No new cost or spending authority follows from this preference.
5. The chosen account is inserted into the existing bound lease row, and is forwarded via existing \`ACCOUNT=\` / \`POOL_ACCOUNT\` through \`remote_sub.sh\` to the existing GLM lease-capability shim. Provider/served-model/actual consumption attestation is **not yet proven live** by this source test.

**Caveat:** the installed *pool* picker R31 currently reasons about per-account **weekly** windows but not the same-account 5h availability. The new broker preference is intentionally more conservative, so an urgent pool preview alone still cannot guarantee the exact expiring account will be chosen. This remaining planner-vs-claim consistency should be covered by the same current owner; no claim of complete provider-wide atomic quota consumption is made.

## Direct RED / GREEN proof against actual broker code and temporary SQLite

The isolated test \`test_urgency_selects_matching_account_in_actual_atomic_claim\` uses real temporary SQLite, the real Broker acquire/locking body and two synthetic account sources: same model headroom and concurrency; account alpha resets later, zeta resets in four hours; both have provider-reported fresh 5h balance.

- **Installed source RED:** actual original \`lease_broker.py\` SHA c175… returned a successful SQLite claim for \`alpha_far_reset\`; test required \`zeta_near_reset\` and failed, return code 1. The test fixture never touched production leases.
- **Patched source GREEN:** same test through the staged incumbent Broker code selects \`zeta_near_reset\`, and verifies the stored account, model and host directly in temporary SQLite.
- New candidate account-claim suite: **26 passed**. Covers sequential drain, at-cap fallback, frozen explicitly pinned account, per-model zero cap, six concurrent claims across four slots with no double claim, missing/corrupt/untrusted cache, symlink rejection, stale/future/missing/contradictory/duplicate weekly and 5-hour evidence, LOW/zero balances, disabled burn-down, hard cap and time-dependent reset invalidation.
- Full combined isolated M2 run with existing \`test_lease_broker.py\`, \`test_glm_accounts.py\`, \`test_pick_policy.py\`, corrected test R31, 18 exact-model tests, 15 existing selector tests and 26 new account-claim tests: **271 passed**, exit 0, about 10.74s. The original R31 test was stale (it incorrectly expected \`100.0\` for Grok quota when no observation existed); a separate exact-source test-only patch now asserts UNKNOWN=None. Earlier baseline including the original test was RED, so this distinction is recorded instead of calling untouched source green.
- All candidate code was loaded into the test runner from isolated copies, or applied to isolated fixture source. **No real provider request, M2 live account/broker modification, or worker spawn** occurred.

## Actual release / proof gate

1. Reconcile the incumbent active writer and check the *exact installed SHA256* for \`lease_broker.py\`, \`pick.py\`, \`fabric_task.py\`, the R31 test and native supports before any installation. A changed source requires a new conflict-aware patch review; no blind replays.
2. Have the existing Fabric source/install owner accept and install the minimal exact patch on its managed carrier. Publish and verify the **actual installation receipt and source hash** independently. Existing Mastermind PR #1247/#1248 and Macro #7116/#7142 quota/account planning lanes remain separate and are not silently subsumed.
3. Review quota-cache producer integrity and the paired multi-window generation/freshness assumptions. Select a task-qualified GLM model and eligible host; prove pool urgency, **actual exact leased account**, capability-bound provider key, served model/host, and matched usage/window reset in one current original operation.
4. Test post-START/EFFECT_UNKNOWN refusal to switch, a real active account's 5h or weekly rate exhaustion, concurrent claim safety and no duplicate child/lease on lost response. Original-parent accepted return, Auth0/native wake and release protections are separate gates.
5. The F04 incident \`mo-a-f04-preinvocation-census-grok-v1\` remains a distinct **started terminal error with census timeout and proven cleanup**, not quota evidence. No replay, lease settlement, runtime file modifications or delegated new ownership is part of this change.

**Capability state:** old pool-level R31 preference PARTIAL/proven for read-only Grok; **new GLM account-level broker source BUILT_NOT_PROVEN** (offline SQLite integration passed); live installation/actual provider quota burn-down NOT_PROVEN.
