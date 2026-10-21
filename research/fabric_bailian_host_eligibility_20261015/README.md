# Qwen host/account readiness composition

A fleet lease could name a Bailian account unavailable on the selected worker host. The exact-account launcher repair (#1508) now refuses that mismatch without reserving another account; this change prevents the incompatible grant earlier.

The existing host collector publishes only policy-listed configured-account booleans from the exact existing Bailian validator. The existing owned telemetry reader, router and broker intersect them with current host admission before demand or lease creation. Missing, stale, foreign, unknown or invalid observations refuse. Current role/mode/qualification holds override a prior positive observation. The final Qwen model must equal the model used during host eligibility. GLM's public predicate remains GLM-only. No credentials, capacity, pool policy, provider calls, daemon or lifecycle is added.

## Source and review

`SOURCE_INTAKE.json` binds the six installed preimages. `candidate/` contains the proposed files; the local `host-eligibility.patch` was the review convenience diff. `REVIEW_SCOPE.json` binds the final reviewed hashes. Independent NativeCore review found current-policy revocation and final-model binding gaps; both were reproduced (9 failing cases, 2 controls) and closed after 19 affected checks passed. The reviewer separately reran both discriminating actual-function probes and approved the repaired scope.

## Verification

- 53 new predicate/generator/collector/router/broker checks qualified across affected runs; no provider or credential effects.
- 33 original GLM predicate checks passed.
- Existing broker/collector/router compatibility: 59 pass; one GLM fixture mismatch reproduces unchanged on installed baseline because it lacks current account-readiness metadata. Missing fixture dependencies were corrected only in the isolated stage.
- The incumbent collector shell-to-generated-probe-to-reader integration check passed with synthetic transport/configuration (included in the 53).

Run the focused suite with `python -m pytest -q research/fabric_bailian_host_eligibility_20261015/tests/test_host_account_composition.py` using an interpreter with pytest and PyYAML. Tests stage public installed dependencies and synthetic configurations; they never contact hosts or providers.

## Rollout

Producer first: install the reviewed shared reader/predicate, probe builder and collector backend against exact preimages. Reuse the existing collector and verify fresh local telemetry carrying the current validator digest. Then install the reviewed router/broker consumers. Existing holds, grants and account selection remain binding. No failed review or prelaunch-refused test operation is retried. Retain source/install/adoption outcomes separately in the existing programme checkpoint.

Native original-parent f75 admission and production proof are separate and remain pending with the existing release/host owners.

## Exact-head CI correction

The first hosted run at `c079516ff01431725c5e8815606b32a5748f6de0` found one D8 false positive: the unchanged `DEFAULT_MAX_AGE = 600` duration in the account-named predicate was classified as an identity literal. The correction uses the existing static reviewed-literal mechanism to identify only that token in the exact independently reviewed predicate (`00fdbdf5…`). It does not change runtime source. A regression reproduced the failure before repair; 150 affected D8 checks pass afterward, including missing postimage, different path, changed value, added UID, duplicate constant and unrelated byte drift. The full hosted suite remains a required release check.

Independent paid Qwen review returned scoped PASS for the exact two-file guard correction. Parent verified the source hash, token site, unique registry entry and actual scanner integration through the 150 affected tests. The worker echoed its in-memory source probe and exceeded the 3500-character return contract, so the child is recorded NOT_ACCEPTED and no worker acceptance command is issued; the concrete source assessment was separately adjudicated. The reviewed runtime files are unchanged.

The `befec11ef` push had no repository-test run. Local merge diagnosis independently found a conflict with protected `89ab904e0` in the reviewed-literal table. The merge resolution preserves the upstream HTTP-status pins byte-for-byte and appends the unchanged reviewed telemetry-age entry. All 150 affected D8 checks pass on the combined source. No runtime or installed-source change was introduced by the resolution.

Protected `a53062ff1` then landed another accepted entry in the same append location. The second merge preserves its complete AST and moves our unchanged exact token entry into the existing initial dictionary. This avoids repeated end-of-file conflicts without adding a registry or changing any guard. Removing our one entry from the resolved AST reproduces upstream exactly.

## Remote hard-cooldown admission correction

Two later reviews received a central lease for a configured account that was
already in a non-429 cooldown on the selected remote host. The original
configured-key observation did not represent this host-local restriction.

The existing probe now reads only each requested account's bounded cooldown
metadata and combines it with configured-key readiness. It emits only
true/false/unknown, never the marker reason, expiry, path or credentials. A
non-429 active cooldown excludes that account; missing or expired markers allow
normal admission, and the existing 429 soft-cap policy is unchanged. Expired
files are left untouched. Malformed, replaced, unsafe or unreadable markers
produce unknown and cannot qualify the account. No marker is cleared, no lease
or account is changed, and neither original failed review is retried.

The existing Qwen predicate additionally requires literal `cooldown_checked:
true`, so old configuration-only telemetry cannot qualify a new lease. GLM's
contract is unchanged. This is a freshness-bounded observation, not atomic
provider admission: a later cooldown still causes the strict remote launcher to
refuse the original grant. The two changed installed files are the existing
probe builder and predicate; broker, router, validator and launcher stay intact.

Fifteen new cases failed on the preceding implementation; all 68 affected
producer/consumer/collector/router/broker cases pass after the correction. The
new cases include the original mismatch with a controller that sees no cooldown,
old positive telemetry, expired-file nonmutation and unsafe metadata. Rollout is
producer first, then the existing collector's fresh observations, then consumer;
no manual probe, daemon restart or cooldown reset is needed. Earlier source and
review receipts above remain historical evidence for the configured-key phase.
