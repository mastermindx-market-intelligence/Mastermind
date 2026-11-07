# Subagent Fabric selector continuation and F04 source-collision evidence

**Observed:** 2026-10-12 UTC  
**Owned source carrier:** Mastermind draft PR #1365, branch sol/fabric-expiry-selector-20261011-sol-001.  
**Outcome:** New source-only selector patches and regressions; no installed Fabric changes or modification to F04.  
**Protected procedure pin reused:** Mastermind master 25c4b7923734392b1013afae179966985819d847, compatible mastermind.sol_skillpack.v1 / 1.0.1 / bootstrap_major=1.

## Custody statement / scoped intent

This selector lane **does not own** the active M2 source-install work for remote_sub.sh, lane_runtime.py, support_bundle.py, remote_sub_exec.py, or the F04 original operation. Another owner was actively changing those files while we inspected them. No direct edit, restart, source publication to the account-local runtime, process interruption, replay, lease settlement or provider call is authorized or performed by this selector lane.

The work here is limited to a source-bound **proposal** improving local-session selector affordances:
- read-only preview, pool auto/model auto, explicit eligible host with existing canonical picker;
- exact requested model only when task/pool policy already admits that model, preserving previous implicit GLM escalation witness and all gates;
- no new model registry, scheduler, quota owner, retry plane, producer, worker lifecycle or authority.
Web Executive session_summon/provider/host selection remains controlled by its existing admission owner; an installed local CLI is not proof of Web caller override.

M2 account-local kit source is not a Git checkout. Source fingerprints below are **observations**, not authenticated installer receipts or release approvals. No new native install receipt for these scripts was obtained; execution receipts for F04 are not installation receipts.

## Installed source snapshot and collisions

At read-only inspection after the Chairman's collision report:

| M2 installed ext file | Observed SHA256 | UTC modified time |
| --- | --- | --- |
| remote_sub.sh | 78b3d386e82b273bbb828671fb011ee8188df30fbe82e30b2817ccd5a8c7320d | 2026-10-12 04:59:31.249779 |
| lane_runtime.py | d36860ea8036ed5ec733a47c709a477c851fee95dddbae23c8e2214dc308b77e | 2026-10-12 05:15:42.191677 |
| support_bundle.py | 4f8544b91eb367f2179062e61d1e5b6b5fece4b15881a5635d34d8265e6a91ef | 2026-10-12 04:51:32.384452 |
| remote_sub_exec.py | c6b4292cdb7d106d5b376587f29276da1550e5eee02268f479abd7ad2ea61189 | 2026-10-12 04:52:05.984522 |
| fabric_task.py | 5596de46d2e8ca88178152fcd540db0ce50b3d96250aabe34bacf8a7a47727da | 2026-10-12 04:58:52.678782 |
| pick.py | 43fe863bd2207e55ca6d619aa92a55750f9468e05dd6b3567811eca96c288b4c | 2026-10-12 02:11:17.151395 |

The Chairman also observed earlier remote_sub and lane_runtime revisions around 04:51–04:59. This is a **later snapshot**, not a claim those earlier revisions never existed. Installed lane_runtime.py at 05:15 contains one bounded retry of a stalled ps census read; this later code is not proof the original already completed F04 process would succeed upon replay. Do not replay it.

## F04 immutable operation and evidence

Run: **mo-a-f04-preinvocation-census-grok-v1**  
Root and parent: **01a128b5-e26b-7b12-94b5-231bfe0b8036**  
Host: ubuntu3; mode/model: grok/grok-4.6.  
Evidence JSON:
\`/Volumes/Mastermind/evidence/marketontology-fabric-repair-01a128b5/f04-private-adoption/runtime-install/producer-preinvocation-5f54678d/coord/fabric-failure-evidence.json\`  
SHA256 **fdae0e8ba7b9a086cf66ba5336c8712a6005b31655bbc18942e2fec57b69dd98**, 3,205 bytes.

Exact retained receipts in the installed ext/state and ext/lanes paths:

| Original artifact | SHA256 |
| --- | --- |
| state/remote_sub/mo-a-f04-preinvocation-census-grok-v1.log | 705d1077065f59a41d394e7937a9f03867ee624c71ff321cad6b007e98592c62 |
| state/remote_sub/mo-a-f04-preinvocation-census-grok-v1.process.jsonl | 712e88f3de59cb06e0528cce8d4c0468b4724fdfb3682730533372724b2d284e |
| state/remote_sub/mo-a-f04-preinvocation-census-grok-v1.native-terminal.json | fca7958770604cf9843d7470f036a42eabc6a91c8fea3f5eeb7e07fd2f55bff5 |
| lanes/mo-a-f04-preinvocation-census-grok-v1.remote.stdout | d48efb575c658954963c9f1b3cbc1daa1ff876f8ffc4015a36c39dced7e59fd0 |

Retained facts: process actually STARTED 2026-10-12T04:50:28.416Z; ENDED 04:51:47.914Z; process returncode=1, owned runtime failure code=process_census_timeout, terminal wrapper rc=76. No useful stdout or stderr: stdout_bytes=0, stderr_bytes=0, both truncated=false, stdout_capture_complete=true, stderr_capture_complete=true. Cleanup status=terminated, identity_verified=true, census_proven=true, residual_count=0, SIGTERM delivered to one process-group member, SIGKILL not needed, cleanup_proven=true, output_complete=true. Existing fabric_task status projected state=TERMINAL/rc=76/acceptance_state=UNVERIFIED/accepted=null, not an accepted model result. Result_available=true refers only to retained **43-byte failure diagnostic**, not useful worker output. Provider usage receipt was missing; neither quota consumption nor quota exhaustion can be inferred.

### Two real misclassifications, observed in current code

1. **remote_sub_exec.py** blanket started-worker exception path emits \`REMOTE_CLEANUP_UNPROVEN ProcessCensusError\` and rc76. That generic text remains in the retained stdout, despite an independently retained, identity-proven cleanup receipt with zero residuals. The message is broader than what the later immutable evidence actually establishes.
2. **remote_sub.sh** maps \`RC=76\` in native mode to \`LEDGER_SIGNAL=other; LEDGER_REASON=native_capture_truncated\` unconditionally. But retained native-terminal.json says output_complete=true and both stdout/stderr truncated=false. The ledger description falsely asserts truncation.

**Correct interpretation:** a started, terminal **failed** worker/wrapper operation, with witnessed process-census failure and proven cleanup, complete captured streams, **no usable model result**; not a provider quota failure, no capture truncation, no unproven cleanup. Preserve original rc76, original root/parent/run identity, original lease/receipts and the absence of accepted work; no retry or settlement request.

### Future owner-scoped classification correction (not implemented here)

Proposed after the active file owner reconciles its carrier:

- Read, validate and bind the **original run-scoped** process/native-terminal receipts; do not infer cleanup from an incidental log string, current host census or empty stdout.
- When started=true, terminal rc76, \`runtime_failure_code=process_census_timeout\`, cleanup_proven=true, output_complete=true and neither stream truncated: project failure reason \`process_census_timeout\` (or a canonical typed alias), terminal failure/accepted=false; never say capture truncated or cleanup unproven. Keep model_output_usable=false even if a generic failure message is delivered.
- When stream capture is actually truncated, only then emit \`native_capture_truncated\`; when cleanup proof is absent, only then retain \`native_cleanup_unproven\` / existing effect-uncertain guard. An unknown or contradictory receipt remains held for reconciliation, not made green by later clean state.
- The in-flight process/exception handler should be able to distinguish a census error from a cleanup error, using the existing bound process receipt. This does not grant any replay/recovery rights.
- Add provider-free fixture tests for rc76: (a) proved cleanup + census timeout + complete zero output; (b) actual truncated stream; (c) missing or mismatched native receipt; (d) residual process present; (e) pre-START refusal. Assert original root and run IDs; no extra lease, run, account, host or claim; legacy codes preserved unless canonical schema owner accepts a change.

Do not merge, install or directly patch these **four actively held source files** from the selector lane. The original native Auth0 and same-parent admission/acceptance gates remain distinct and unsatisfied by F04 cleanup proof.

## Selector integration source work verified in parallel (no installed effects)

Old PR #1365 baseline had a patch against original installed fabric_task.py SHA256 \`cbd46bd88a4e5d545c77010bfb9eb1997399fe4f5cc67596210e849858eddd99\`, **now superseded for exact current source by the new v2 patch**:

1. \`ops/native_fabric/patches/fabric_task_expiry_host_select_20261012_v2.patch\`: exact input SHA256 **5596de46d2e8ca88178152fcd540db0ce50b3d96250aabe34bacf8a7a47727da**, isolated applied target SHA256 **69e18648e8a1243be23c6d84b1c944c6f98e5804b1281182fa380a9af4b6eed9**; the concurrent \`recover-mac-policy\` command and original \`--mac-policy-return\` path are preserved.
2. \`ops/native_fabric/patches/pick_exact_model_selection_20261012.patch\`: exact installed pick.py source SHA256 **43fe863bd2207e55ca6d619aa92a55750f9468e05dd6b3567811eca96c288b4c**, staged resulting source SHA256 **5a972eaba41ea71c018edd1b3c10861cfd66ea163c7a9f590804ec9feee757ed**. Manual pool+exact model only when it matches that bounded task's existing admitted model; unscoped unique worker-model inference; preserve existing GLM C2 full escalation witness, independent-review check, tier/economics, quality demotion, and host vetoes.
3. \`ops/native_fabric/patches/pick_exact_model_selection_20261012.tests.py.txt\`: 18 additional provider-free boundary tests.
4. Prior \`ops/native_fabric/patches/fabric_task_expiry_host_select_20261011.tests.py.txt\`: 15 existing selector tests.

**Offline tests:** existing policy suite 146 passed; added exact-model suite 18 passed; prior selector suite 15 passed. Combined **179 passed** in 7.13 seconds, with installed-source modules loaded against isolated candidate code *in memory*, no provider invocation or installed-file mutation. Read-only integrated candidate preview returned \`POOL=grok MODEL=grok-4.6 HOST=ubuntu3 MODE=grok PREVIEW_ONLY reserved=false\`; \`grok-99\` was refused before dispatch. A previous real Grok expiring screenshot priority was active and observed separately; the last read-only preview selected Grok because **explicitly requested**, reason=ok, not an asserted live expiry promotion.

The earlier exact-head PR #1365 GitHub CI run 38203556192 completed SUCCESS **before this candidate amendment**. New exact-head CI and source review belong to the changed GitHub branch; hosted CI for the amended head is not automatically proven by the earlier result.

## Actual next qualified integration sequence

- The incumbent runtime owner reconciles the four active shared files and the original F04 operation, and may elect to implement truthful classification above on that same source carrier after verifying exact installed source/effects. This selector lane makes **no** custody claim on that work.
- For the selector: review this draft and source hashes; have the accepted local Fabric installer rebase/apply both exact-hash patches to its already-owned managed source, refresh dependent tests without affecting active leases, and separately prove installation/readback. If the installed source has moved since these observed SHA256 pins, rebase from the actual owner revision, never blind-apply.
- Native local sessions may then use preview/host/pool/model flags through the qualified launcher, with current admission/quota and per-model rules intact. A single fresh bounded real child plus exact model/host/account attestation, provider usage observation, accepted original-parent return and failure regression are required before PROVEN_LIVE as a user-facing integrated capability.
- Universal Web CEO/Executive account or host overrides remain out of scope until current Capacity/Executive owns such an accepted selector path. No native Auth0 repair, same-parent return proof, autonomous deployment, or original F04 reissue is claimed.

**Capability state:** current R31 expiring-pool routing PARTIAL/observed Grok case; local selector source BUILT_NOT_PROVEN; integrated selected-account/host/model end-to-end production PROVEN_LIVE **not established**; original F04 terminal failure reconciled from receipts only, not accepted or replayed.
