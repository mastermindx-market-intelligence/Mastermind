# Morph routing acceptance — direct M2 activation

## Result

The Kimi K3.1 Pro / DeepSeek follow-up is implemented and active on the M2. Source commit: `6f3b8716b53cebb0dd3351d3010b5b89f94fdcc9`. Measured running generation: `model-tier-20261111-1ce495a38d8d15eb`, PID71314. Configuration digest: `ab8b965145805412ba3b9c574642e03c8b01f9b55ac396bd0db8e413bf4b4cc6`.

The deployed runtime files match the manifest. The admission ledger restored, its writer is healthy, file mode remains0600, and the temporary reload lock is released. Complete structured evidence is in [MORPH_ROUTING_ACCEPTANCE.json](MORPH_ROUTING_ACCEPTANCE.json). Host receipts and backups are under `/Users/chriswong/.local/share/mastermind/fabric-router/work/morph-fallback-20261113`.

Finalization: **PROVEN_OUTCOME for this bounded software repair and M2 activation**, with external provider availability constraints stated below. This is not a claim that every upstream provider is continuously available or that the router has no remaining defects.

## Admission and selection

| Resource | Provider ceiling: input/output TPM | Operating budget: input/output TPM | Local concurrency ceiling | Flexible alias output ceiling |
|---|---:|---:|---:|---:|
| Each of two Kimi Ultra resources |24290 /6162|21861 /5545.8|1|4096|
| Each of two DeepSeek Ultra resources |400000 /70000|380000 /66500|6|16384|

Input accounting uses uncached input. Strict resources reserve the whole effective output ceiling, including reasoning output; actual provider observations may constrain them further. Concurrency ceilings never override token admission. Exact requests retain their full output maximum and prompt; aliases have explicit visible bounds. Morph burst capacity is not assumed as recurring sustained throughput.

Preferred profiles:

- `fabric/kimi-preferred`: Kimi, Qwen4, Opus5.5.
- `fabric/deepseek-preferred`: eligible DeepSeek providers, Qwen4, Opus5.5.
- `auto`: DeepSeek/Kimi/GLM/Qwen4 with6:3:1:1 preference weights and current capacity awareness.
- `fabric/balanced`: GLM/Kimi/Qwen4 with4:4:2 preference weights.
- `fabric/fast`: DeepSeek/GLM/Qwen4.

Weights are preferences among eligible resources, not promised traffic shares. Existing exact1017 snapshot bindings, uncensored/abliterated exclusions, Grok exclusivity and GLM's configured time-window policy remain distinct.

## Fixed failure cases

1. Established conversations were incorrectly treated as active upstream execution and could become stranded on an impossible Kimi output/input budget. Opted-in families now switch models between settled requests; actual simultaneous inference remains fenced.
2. A healthy Morph sibling could be obscured by inconsistent allowlists or provider availability checks. Core selection and overflow now share eligibility.
3. Sticky fallback could bypass concurrent limits, and a sticky Qwen-to-Opus switch could omit its hourly charge. Planning and final admission now enforce the same caps and account for each new target.
4. Long provider lists could spend all five attempts before Opus. Two primary and two Qwen candidates precede an Opus candidate when eligible. With no substitute available, all primary candidates remain in the ladder. Only proven preacceptance rejection permits advancement.
5. DeepSeek's approximate output reservation could oversubscribe the subscription. Full effective-output reservation,95% headroom and bounded concurrency now apply.
6. A new hold/configuration withdrawal could arrive during asynchronous persistence and still permit a send. Strict admission rechecks current eligibility, circuit generation, holds and capacity afterward.
7. Generic server errors were treated as safe replay opportunities. Generic502/503/504/529 now preserve uncertain effects; only classified admission rejection can fall through.
8. Unknown quota exhaustion could create repeating retries. Direct-account exhaustion without a valid future reset becomes a durable owner hold.
9. Model grant refusals, prompt refusals and account restrictions had different required scopes. The classifier distinguishes them and does not use a permission refusal as a fallback trigger.
10. Reset timestamps and Retry-After handling could use the wrong provider interpretation or shorten a real deadline. Parsing is provider-scoped; positive authoritative delays are retained.
11. Diversion hourly windows and scoped holds now survive restart through the incumbent admission checkpoint.
12. Existing OpenCode credential concurrency, BytePlus family concurrency, Experiential gateway concurrency and Qwen local resource ceilings are explicit; no provider quota or additional entitlement is invented.

Qwen4 and Opus5.5 each retain the configured diversion ceilings of6 concurrent requests and40 new diversions per hour. An accepted/uncertain effect stays charged; a proven no-send reservation is refunded. A ready primary may be selected after a minimum300seconds on its substitute.

## Qualification and genuine consumer proof

**270 tests passed locally and on M2 Python3.14.7**, including60 new follow-up cases. Provider failures and capacity races in the regression suite use mocked transports. Eight separate verification calls used the production service and real providers:

| Case | Actual route/model | Result | Elapsed |
|---|---|---|---:|
| Fitting Kimi requestA |morph_kimi / Kimi|HTTP200, correct marker|1.210s|
| Fitting Kimi requestB |morph_kimi_2 / Kimi|HTTP200, correct marker|1.691s|
| Seven-turn Kimi request,32768 output maximum |bailian_7 / Qwen4|HTTP200, output-budget fallback|6.639s|
| Direct DeepSeek |morph_ds / DeepSeek|HTTP200, correct marker|1.989s|
| DeepSeek-preferred profile |bailian_4 / Qwen4|HTTP200, real profile fallback|5.005s|
| Opus destination |claude_pool / Opus5.5|HTTP200, correct marker|1.682s|
| Auto profile |glm_chairman_2 / GLM5.3|HTTP200, correct marker|3.994s|
| Seven-turn streaming Kimi request,32768 output maximum |bailian_2 / Qwen4|HTTP200, correct marker, message_stop and final usage|3.491s|

These are connectivity/decision proofs, not throughput benchmarks. Client route/model headers and admission records agree on selected model, output request and observed usage. The streaming case reported98 input/61 output tokens. The Qwen-rejection-to-Opus chain is proven by fault fixtures; Opus itself is proven as a live destination. Provider failure was not induced to manufacture a production fallback.

At the saved post-activation snapshot, real traffic had97 completions,16 completed diversions, zero quota refusals, zero capacity waits and zero queue refusals. Both DeepSeek Morph resources were serving production work (16 and8 completions). A later read showed116 completions and one non-canary Bailian2 `FABRIC_UPSTREAM_EFFECT_UNKNOWN`; its root cause was not established. The uncertain-effect path retains the charge and does not replay the request. All eight verification calls succeeded.

## Deployment

Exact source/config preimages and private backups were captured. The existing route weights temporarily paused new admissions. Eleven active requests were present at that gate. The incumbent received gracefulSIGTERM, drained and exited; its ledger had no pending inference at handover. The same LaunchAgent started the replacement. Activation completed in113.02seconds.

All ten long provider cooldown deadlines were retained, including both BytePlus/OpenCode lanes and existing GLM/Bailian holds. No overlapping serving admission owner or forced stream termination was used. The running source/config identity, ledger restore, caps, configured funding hold and lock release were checked after activation.

## External constraints

- **Experiential Labs:** DeepSeek and its1017 snapshot are wired into the intended route lists but excluded by `PLAN_INCLUDED_FUNDING_UNVERIFIED`, which the incumbent gateway reports. Its public account metadata does not prove included inference funding. No alternate compatibility endpoint was used to bypass this gate.
- **OpenCode Go:** both lanes retained approximately64.7hours of cooldown at the saved snapshot. They become probe-eligible according to their deadlines and existing circuit policy. No extra-usage setting was enabled.
- **BytePlus ModelArk:** the two lanes retained approximately0.91hours and4.48hours at the saved snapshot. No quota reset, entitlement expansion or held-lane canary occurred.
- These periods are snapshot observations, not promised availability times. A provider can reject a recovery probe, in which case its current refusal controls the next decision.
- PR2464 remains a Draft source reconciliation archive because it includes existing M2 overlays. Direct activation did not merge it over protected master or bypass repository protections.

## References

- Morph Ultra provider capacities: https://www.morphllm.com/products/ultra
- Morph Ultra semantics: https://docs.morphllm.com/ultra-plan
- Experiential stable error codes: https://platform.experientiallabs.ai/docs/errors
- OpenCode Go usage windows: https://opencode.ai/docs/console/go/
- Existing source laws were read at `fc91f33ccce3e8f18c78546f03c955c2ced0c704`.
