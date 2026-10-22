# Linux-native capacity observation v2

Operation: `fleet-linux-native-observation-v2-20260926-sol-c4-001`.
Parent: existing Fleet #644 / Workbench #539 / rollout #911.
Decision: #644 comment 5850080115.
Protected base: `a31f49f4056943124cc0e7e42349e46feee444c7`.
Status: UNVERIFIED source candidate; not protected, installed, or scheduling-qualified.

## Useful vertical and owner

Allow a machine-facing reader to consume Linux host/target-scope facts without manufacturing Darwin counters, accepting foreign/stale observations, or implying execution admission. Reuse the Packet-D pure arithmetic and the existing host-capacity contract owner. No new scheduler, queue, registry, Runtime or monitor.

Composition:

`captured receipts -> linux_capacity_facts.observe -> metric pairs + pool-total observation -> build_native_host_capacity_snapshot -> canonical bytes -> project_native_host_capacity`

Inputs are fixtures/offline receipts here. This is not an installed collector, authenticated endpoint, UI integration, physical normalizer or provider execution path.

The returned parser and its 79-test suite are included unchanged. The envelope factory lives in `control_plane/executive_host_capacity.py`; the new integration fixture explicitly converts Metric values to wire pairs. This preserves the parser's standard-library-only import contract rather than weakening its purity test.

## Compatibility and wire

The existing v1 validator/serializer and original HC0 module prefix are unchanged. Physical admission still consumes v1 and rejects v2. The old four Linux/v1 boundary REDs must not be made green with fake fseventsd/VM counters or relaxed v1 completeness.

Native schema: `mastermind.host_capacity_snapshot/v2`.
Platform: `linux` only.
Observation profile: `linux-native-observation/v1`.
Execution scope: `kind=cgroup-v2` only.

Closed references: host_ref, boot_ref, capacity_pool_ref, source_generation_sha256, execution_scope_sha256, namespace_sha256, ancestry_sha256. Reference syntax reuses the existing host/boot/pool rules; digest references are lowercase 64-hex. Arbitrary paths, endpoints, hostnames and provider credentials are excluded. No identity is minted.

The consumer compares all seven references against independently owner-supplied expected binding. Hash equality proves content identity, not authenticity. The future installed capture/reader must authenticate origin and expected binding separately; this pure function does not certify supplied ancestry.

Times are strict bounded integers, not floats/bools. Positive capture span <=5000ms; total span covers the sample. Freshness uses the oldest instant, observed_at_ms minus total_observation_window_ms, with future observations refused. Equality at the maximum age is allowed. Clock policy is construction-owned, not a model-exposed override.

## Values, units, nulls

Exact fields: the 34 Packet-D metrics plus pool_total_bytes. Pool total and unprivileged usable bytes must come from the same qualified descriptor/generation; the test composition validates Disk before deriving total.

Each wire metric is exactly `{value, null_reason}`. Units are static owner code added by the read projection, never sender-selected. Values are nonnegative int64; host logical CPU count 1..4096; percentage values are thousandths of one percent, 0..100000. Observed pair bounds reject memory headroom above the containing estimate, usable memory above total, scope CPU above host CPU count, swap used above total, and usable disk above total.

Meanings remain distinct: host usable memory is not installed DIMM inventory; MemAvailable and scope headroom are estimates; effective CPU capacity is `millicores_ceiling`, not free execution supply; PSI totals are microseconds; PSI averages retain their 10/60/300-second horizons; swap-page deltas are pages, not silently converted bytes.

Darwin VM counters, Darwin fseventsd and Linux system-wide full CPU pressure must be null/NOT_APPLICABLE, never observed zero. Applicable nulls need a typed reason; NOT_APPLICABLE cannot excuse a missing required native field. Unknown fields exactly equal the sorted applicable-null list. Known zero headroom differs from missing data.

COMPLETE means complete for this observation profile only. PARTIAL remains visible with reasons. Neither implies admission. Every reader output contains:

```
capability: OBSERVATION_ONLY
admission_state: NOT_EVALUATED
can_place_work: false
```

The read schema is `mastermind.native_host_capacity_read/v1`, carrying binding, source digest, time, statically labelled metrics and observation state. No default runtime consumer is registered. A canonical digest is integrity evidence, not origin, signature or permission.

## Normalization ruling

A CPU quota/cpuset/affinity ceiling is not idle supply. Do not multiply it by host idle percentage to invent scheduling allowance. Target usage/throttling, sibling interference and existing resource policy are still required.

Each ancestor's own memory limit minus current usage includes sibling load; subtracting leaf usage from parent limits exaggerates headroom. MemAvailable and these bounds remain estimates. memory.high/events, swap/protection/OOM assumptions and controller coverage require qualification.

Resolve storage to one enrolled physical pool. Bind mounts/subvolumes cannot double-count supply. Do not subtract materialized allocations a second time when already reflected in free space. Preserve the incumbent pool ledger, #996 atomic commitment and separate BEGIN.

This slice does not modify `_validate_host_capacity_evidence`, `_host_score`, selected reservations, Runtime or any installed policy. Cross-platform ranking requires its own reviewed comparable measures, not replacing Linux unknowns with Darwin zeroes.

## Source scope and evidence

Exactly five candidate paths: existing HC0 owner (additive functions), returned Linux parser, returned parser tests, new native-contract tests, and this document. A current census checked 238 open PRs (expanding the >100-file PR) and found no overlap on these paths. All incumbent #939/#996/#994/#988/#929 source and installed state are preserved.

45 new native tests failed before implementation because the API was absent. After placing the factory in the HC0 owner, the adjusted exact API suite again yielded 45 RED failures. The subsequent combined GREEN verification call was refused by the platform before a process receipt. It was not retried through another tool/mode/host/provider. Therefore the new contract/envelope/reader implementation is UNVERIFIED. Packet D's prior 79/175 passing campaigns do not certify the added functions.

After legitimate recovery of the denied verification capability, run the new contract suite, unchanged parser suite and selected protected Darwin/physical suites, then current repository/security checks and independent exact-head review. This artifact grants no installation or source acceptance.

## Installed proof still owed

Descriptor-safe bounded proc/cgroup capture; actual deadlines; target namespace/ancestry/mount attestation; cpu.stat/memory.high/events/swap coverage; authenticated release/service identity; Linux non-root enrollment; qualified normalization/preference; reserve/BEGIN; loss-safe execution; immutable child result/parent/auditor return and settlement. Ubuntu1 canary first; Ubuntu2 and mini4 remain excluded until their own complete current conformance.

## Primary technical references

https://docs.kernel.org/admin-guide/cgroup-v2.html
https://docs.kernel.org/accounting/psi.html
https://docs.kernel.org/filesystems/proc.html

These explain native metric meaning, not authority to modify the cluster.
