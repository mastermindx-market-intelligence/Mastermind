# Office Result producer export

Unmodified bytes from one run of
`tests/test_workspace_result_http.py::test_signed_result_and_mission_join_real_owners`
on Mastermind `f93a807e278dd333650f02701318a5fc827c3b64`.

The test wrote these three files into its own temporary directory. Nothing in
this directory was reformatted, re-serialized, or edited after that write.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `actual-result.json` | 3229 | `fef28f4611e4d66b8db3f80c9dba8cb7b5247ce9071a2bc3e8aa0e5e16135f4a` |
| `actual-mission-v3.json` | 6452 | `eec67d2d44fe03c5b060089a3046f6e77f7ec5d60ed30fda5843723b773ac529` |
| `fixture-provenance.json` | 433 | `f76459d06520b84bd46ee03eddcc8df9d2b96ec358db755b85bd5de738366d5f` |

`fixture-provenance.json` records the closed test-owned proof string and the
exact five-key selection. The HTTP body is `actual-result.json`. The Mission v3
body is `actual-mission-v3.json`. The socket peer for that run is the test
process's effective UID. That is not installed UID 458 custody and not an Auth0
registration. No live credential is in these files.

## Consumer

`app/mastermind_os/src/meta-ceo/result-producer.test.ts` reads the bytes and
passes them to `decodeResultBytes`, `decodeResultEnvelope`, `decodeMissionv3`,
and `projectOffice`. Committed replay is the default Vitest run. Fresh
consumption is a separate mode: set `RESULT_PRODUCER_FIXTURE_DIR` to a directory
that contains these three names. An empty, missing, unreadable, or malformed
explicit input fails that process. The committed files are not substituted.

```sh
cd app/mastermind_os
npm test -- src/meta-ceo/result-producer.test.ts
RESULT_PRODUCER_FIXTURE_DIR=/absolute/export npm test -- src/meta-ceo/result-producer.test.ts
```

## Observed join

Both decoders accept the pair. The five-key review tuple is present in
`result_refs`. The Control Room brackets are equal and remain separate objects.
The runtime `source_identity` values differ:

- Mission `result_refs.generation.source_identity`: `21e17d36420f8de07b9f72167c390119`
- Result `source_observation.runtime.source_identity`: `371a2ea68a30441c37388d21b2513860`

`projectOffice` therefore withholds the result: state `UNKNOWN`, reason
`RESULT_OBSERVATION_UNQUALIFIED`. The Mission's own read stays `CURRENT`. The
result review verdict `reject`, result execution `COMPLETED`, Mission transport
`RETURNED`, and both acceptance states `NOT_PROJECTED` stay distinct. This
export does not establish a current joined result.

Root `meta-ceo-open-harness-convergence-20261024-sol-001`. Parent
`meta-ceo-harness-implementation-20261024-web-001`. Child
`meta-ceo-harness-office-result-cursor-20261024-01`.
Proof ceiling: `SOURCE_PRODUCER_CONSUMER_QUALIFICATION`.
