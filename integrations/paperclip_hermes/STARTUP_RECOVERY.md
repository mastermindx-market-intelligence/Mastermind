# Hermes startup recovery for Paperclip

Status: qualified source candidate; protected delivery and live activation remain separate. This repair continues the Chairman's Paperclip fleet migration and Secretary incident. It does not replace Hermes, OMH, Capacity Fabric, the native plugin registry, or Paperclip's existing process owner.

## Observed failures

Three separate boundaries failed during the incident:

1. A native package-manager validation timeout or signal was treated as proof of stale dependencies. Normal launch could then arm source-completion work despite unchanged dependency inputs.
2. A cold native gateway needed approximately nine minutes to become ready, while the local client waited 60 seconds and the classic connection waited 90 seconds. The failed client left the native gateway alive; starting another gateway would duplicate its owner.
3. Once a later Secretary attempt reached a real Hermes session, Fabric returned `FABRIC_ALL_ROUTES_COOLING` and direct Byteplus fallbacks returned explicit five-hour quota exhaustion.

The first boundary is a demonstrated code misclassification. The historical cause of the slow package-manager import probe is not established. The live gateway later stopped answering bounded control probes while its state still reported work; its exact liveness cause is unresolved.

The capacity failure is not repaired by resetting quotas, changing accounts, or making duplicate requests. Byteplus reported 2026-11-10 08:47:08 UTC as its reset. That is not a promise about Fabric route eligibility. The existing router resilience source remains [PR2367](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2367); no competing router implementation is introduced here.

## What changes

### Preserve inconclusive package-manager checks

`pm.runtime.RuntimeProbeUnavailable` distinguishes a timeout or signal from a missing or positively broken manager. It propagates through the public `venv_is_current` call. Normal launch warns and retains its ordinary selected-dependency activation gate without preparing a replacement runtime or inventing source-completion debt.

Existing completion records are preserved. A failed import, missing interpreter, invalid committed selection, genuine dependency drift, update lock or native pause retains its existing repair/refusal behavior. The patch never deletes a pending-update marker.

### Use one native client startup budget

`HERMES_GATEWAY_STARTUP_TIMEOUT_SECONDS` is an optional process-scoped setting. Values must be finite, greater than zero and at most 900 seconds. Invalid values fail with a bounded diagnostic that does not echo the supplied text.

| Path | Default | Paperclip opt-in |
| --- | --- | --- |
| Local native ensure | 60 seconds | 900 seconds |
| Encompassing classic connection wait | 90 seconds | 930 seconds |
| Paperclip complete invocation | Existing 1800 seconds | Existing 1800 seconds |

Explicit `GatewayConnection.start(N)` budgets remain unchanged. An explicitly selected remote WebSocket route ignores this local setting, including an invalid value; native remote validation and refusal remain authoritative. An explicit endpoint also skips local ensure. Native `gateway ensure --timeout`, WebSocket/RPC limits and the daemon watchdog are unchanged.

The setting is removed by the existing daemon environment scrub before both native macOS job creation and fallback process creation. It remains in the launching client's environment. No wrapper, additional child process, retry loop, timer, gateway or cancellation owner is added.

### Keep gateway refusal text accurate

Typed `GatewayUnavailableError` results retain the native lifecycle message and full repair details. They no longer acquire a misleading model-connection/provider-switch wrapper. Genuine provider failures retain their existing localized path.

## Qualified source

The addon is [native-startup-recovery.patch](native-startup-recovery.patch), SHA-256
`c4bdcf89de18ec6772a36f6f16dd3e6ec378528bcc74e237fa2638ae6164df56`.

It applies after the existing qualified credential-plus-hygiene composition from [PR2403](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2403):

- Installed Hermes commit: `ba4ddf9945a213ede9dda016602a86591ed634f9`.
- Qualified credential candidate: `5de1c0104d42eb406dcad6e3adf8dcacf8d5e968`.
- Qualified composition tree before this addon: `08ffdd48f5e0ed105fb628b137485073e8939b05`.
- Qualified composition tree including this addon: `82982661d113c989a8551c23d7faab7dfb5fbabc`.

The [qualification manifest](../../ops/paperclip_fleet/evidence/2026-11-10-startup-recovery-qualification.json) records all eleven exact preimages/postimages, native proof locations and log hashes. The gateway spawn file already contains the qualified finite-credential extension in its required preimage. Unknown, already changed or incomplete inputs must refuse; do not apply this addon directly to an arbitrary upstream checkout.

Seventeen empty context lines in the serialized patch omit their otherwise trailing space. Default `git apply --check` and `git apply` reproduced every qualified postimage exactly in a fresh isolated proof directory. No zero-context or whitespace-ignore mode was used.

## Verification

| Qualification | Distinct passing cases |
| --- | ---: |
| Package-manager uncertainty regressions | 8 |
| Existing source-completion behavior | 34 |
| Package-manager runtime and normal source launch | 24 |
| Typed gateway copy and existing CLI/discovery behavior | 19 |
| Startup budget, environment custody, classic/remote connections and restart wait | 73 |
| Total | 158 |

Two existing Linux-specific cases were skipped on macOS. The package-manager regressions failed on the preimage; the three typed copy cases also failed on the preimage. Before the startup-budget change, seventeen new cases failed and seven existing-semantics cases passed. Two additional daemon-custody cases verify both native spawn backends without creating a real gateway.

All fourteen native source checks pass, with zero blocking or advisory health findings. Native tests used the existing qualification interpreter through `scripts/run_tests.sh`, isolated home/runtime directories, the pinned native uv executable and disabled file retries. A source-launch rerun after correcting fixture name shadowing is recorded without double-counting its twenty cases.

Shared CI fixture portability is delivered separately in [PR2423](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2423). That repair keeps production source-custody and initializer guards intact.

## Activation and remaining acceptance

Protected-source acceptance, a qualified maintenance boundary, exact installed bytes, and a fresh running gateway are distinct obligations. Do not hot-patch the live source while a gateway can lazily import it. Acquire the native update lock when acting; a previous free-lock observation is insufficient.

The current native updater can proceed after a pause request times out and can terminate work after its drain deadline. Calling it is not proof of noninterrupting maintenance. Verify actual work completion and preserve native update ownership, pause records, completion/recovery obligations and every existing writer.

After safe source activation, use Paperclip's existing agent configuration owner to opt the finite fleet into 900 seconds, preserving the existing 1800-second invocation timeout, profile homes, instructions, environment bindings and secrets. Config freshness must reflect the real change; do not rewrite fingerprints. All thirteen observed agents use `persistSession=false`; native profiles/history remain retained.

The original MAS-2 still owns authenticated same-issue return, runtime MCP, Fabric route/accounting, OMH save/recall, a fresh second profile and representative skill materialization proofs. The failed Secretary attempts remain terminal evidence and must not be blindly replayed. A new attempt requires changed verified readiness/capacity.

MAS-3's archive publication is already Done and must not be exported or uploaded again without a new delta. The final history delta belongs after operating cutover. No completed full-fleet migration or successful Secretary turn is claimed by this source qualification.
