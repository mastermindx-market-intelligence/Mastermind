# Web-Sol fleet native-wire falsifier — 2026-09-06

Operation: `web-sol-fleet-wire-f0-20260906-sol-001`. Parent: `WS:CHAIRMAN-CONTROL-ROOM` / MAS-198 / Mastermind #501. Carrier: `C0BSBM78V1N/1788720660.907229`.

This is executed research plus a proposed integration design, not an installed census service. No browser, provider, socket, native wrapper, account, real profile, secret, RuntimeBinding, Capacity, or Executive lifecycle was accessed or changed. The existing source/release owners for #502 and #509 were not replaced.

## Inputs and method

The experiment executes the actual `census_core.js` from PR #502 semantic head `a6dc03dc8ac241af7690101626a465c44e352c7a`, blob `190ab7064973cd8b58d6d23e89bcb4b8d40fd197`. Synthetic implementations of `tabs.query/get/sendMessage` supply ordinary, discarded, and frozen tabs. This is not a mock replacement of the collector itself.

The native codec and its six local dependency files are byte-checked against protected Mastermind `4fe4d6bc93d9543f77320f68342a10c5af4d4f49` before import. `encode_frame` and `read_frame` run in memory against those real modules. The script checks the legacy request validator separately; no request is sent to a host.

Source Git/SHA-256 identities, environment versions, cardinalities, exact sizes, coverage, refusals, and round-trip results are recorded in `results.json`. The full synthetic snapshot is transient. Fixed synthetic conversation coordinates are never company account data.

## Demonstrated result

| Fixture | Raw JSON bytes | Native raw result | Compact payload bytes | Preserved rows |
|---|---:|---|---:|---:|
| 0 tabs | 648 | Accepted | 1,048 | 0 |
| 1 tab | 1,214 | Accepted | 1,291 | 1 |
| 20 tabs | 11,806 | Accepted | 5,746 | 20 |
| 64 tabs | 36,336 | Accepted | 16,064 | 64 |
| 96 tabs | 54,176 | Accepted | 23,568 | 96 |
| 128 tabs | 72,049 | `frame_too_large` | 31,105 | 128 |
| 129 tabs | 72,034 | `frame_too_large` | 31,090 | 128 + explicit 1 omitted |
| 128 mixed sleeping/awake | 69,201 | `frame_too_large` | 28,257 | 128 |

All eight compact documents passed the existing encoder and decoder, then reconstructed the original snapshot exactly. Three malformed experimental table shapes were rejected. The actual native codec also round-tripped exactly 65,536 bytes and refused 65,537 bytes. The 129-tab fixture preserves partial coverage and omission; the mixed fixture probes only 42 awake tabs without waking the other 86. Every model/effort field remains null/unverified.

Byte sizes are the recorded execution, not a bound on every possible snapshot. Reruns may differ by a byte or two because the numeric observation duration has a different width. A future admitted codec needs closed field/value bounds and worst-case tests, including its complete receipt envelope. This compact experiment is not that production validator.

## Integration consequences

1. The current native module deliberately caps JSON payloads at **65,536 bytes**. This is our local guard, not Chrome's platform limit. Simply forwarding the popup document fails at an allowed collector cardinality. This is a future-integration mismatch, not a defect in the popup's local-only contract.
2. Shared column names remove repeated keys without dropping rows or fields. Prefer a versioned, bounded single-frame representation over silently truncating inventory, lifting every native limit, adding a chunk/reassembly registry, or introducing another transport.
3. The actual v1 validator accepts the control INSPECT request and refuses an otherwise identical CENSUS action. Generic frame round-trip success therefore does not establish that the native host admits or forwards census requests.
4. Static source comparison finds a 5,000 ms collector sweep and five-second total client/native deadlines. A full-budget census leaves no positive allowance for handshake, forwarding, and framing. This is a budget-composition finding, not an observed timeout or performance benchmark. Legacy INSPECT/FOREGROUND timing remains unchanged.
5. Per-profile transport routing already exists. A census client must consume that owner rather than discover sockets or infer accounts from tabs. The existing Control Room remains the final display owner.

Chrome's documented native-messaging limits are larger than our guard: host-to-Chrome 1 MB and Chrome-to-host 64 MiB. That is not a reason to lift the reviewed guard. Source: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging (read 2026-09-06).

## Reproduce

Use an isolated checkout at the protected pin with the PR #502 semantic Git object available. Do not reset an occupied worker checkout to obtain these objects.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 research/web_sol_fleet_wire_f0/run_probe.py > /tmp/web-sol-wire-f0-new-result.json
```

The runner refuses changed protected dependency bytes, checks the collector's Git object, exports only that source to an owned temporary directory, and launches Node once. A successful result is printed only after all checks. Shell redirection truncates the selected output before execution; errors produce `completed=false`, never reuse a previous success. Use a new output path per invocation.

The first run failed before collection because Node 26 exposes `globalThis.crypto` as a getter. The fixture had tried to replace it. The corrected fixture preserves an existing implementation and supplies webcrypto only when absent. This was a fixture compatibility failure, not a product or browser failure; it is not counted as a successful research case.

## Next action and ceiling

Review the accompanying C2 design and plan. After the existing source/deployment predecessors are accepted, commission one source-only native-to-machine vertical with its own exact receiver and path collision check. Its producer must use this real collector; its consumer must expose actual bounded per-profile/multi-profile results. A codec-only PR is not the useful capability.

The subsequent Control Room consumer and #340 installed two-profile proof remain required for fleet product acceptance. Model/effort discovery remains #480 under #473; capacity/usage remains #364. This research grants none of their pending permissions and makes no source authentication, provider model, remaining quota, or Executive execution claim.
