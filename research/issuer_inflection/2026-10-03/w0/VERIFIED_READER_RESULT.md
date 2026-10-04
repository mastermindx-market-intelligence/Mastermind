# Verified baseline reader and source-reference repair

**Development fixture capability only. W0 remains unaccepted; full W1 and the connected Terminal/Macro preview remain unaccepted.** This increment belongs to the same #1183 parent, #1195 child and `i3-w0-issuer-inflection-20261003-astra-c4` source workspace. No source-owner, rights, runtime, registry or live consumer authority is added.

## What now works

`verified_baseline_reader.py` resolves one of the four existing captured reconstructions, verifies its original committed capture records, verifies exact owner-response bytes, checks the existing semantic artifact hash and independently replays the response/request relationship. It returns either machine JSON or a readable text report from **the same existing artifact identity**. It does not mint a current generation/transition ID, recompute a financial metric, write an exposure, publish content, call the network or start a server.

The reader's trust anchor is the three explicit hashes of capture records at `b95a7ddcb24f74a81b9486620c219217518d6f20`. That candidate is committed, not a protected or owner-admitted production release. A digest supplied inside a modified document is not accepted as its own provenance proof. Rehashing the capture metadata, owner bytes or result cannot replace the source-bound trust anchor. All four original artifact identities remain unchanged.

The text report retains all four requested slots, explicit baseline and target cutoffs, original values/units or refusal reasons, and exact cell IDs. In the later-admission case, the baseline assets number remains baseline evidence and the target remains the original unlinked-vintage refusal—not a carried-forward current number. This is a tested development command-line reader, **not the requested authenticated Terminal/Macro browser workflow or Ask/Neural Web integration**.

## Actual defect corrected

The prior fixture consumer checked response digests and selected hashes but did not fully cross-check the selected fact's reporting period, unit, concept, context issuer and readiness clocks. Fourteen synthetic tampered-input cases were accepted under the old consumer. These tests deliberately recompute the outer response digest to distinguish source consistency from a trivial byte-hash test; no real source data was changed.

The new consumer check requires the selected direct fact to match the displayed period, the existing consolidated USD amount semantics, canonical context issuer and concept. Selected accepted/recorded times must match provenance. Public-source readiness cannot precede the fact or exceed the source cutoff. System readiness must include actual source admission, required metadata/mapping/governance availability and remain cutoff-visible. No estimate, currency conversion or new financial definition is inferred.

The same 15-test driver went from fourteen failures to all passing. All 42 original baseline tests also pass, preserving the original four actual semantic output hashes. `SOURCE_BINDING_RED.json` retains the test/module hashes, failing test names and actual output digest; `VERIFIED_READER_TESTS.json` records the corrected runs. The complete old failure output stays in this operation's scratch evidence, not a new log store.

## Consumer-boundary tests

Twenty-six reader tests pass. They cover four fixed case identities, human/machine parity, no writes/backdated emission, bad case/format refusal before file access, exact owner-byte binding, forged and self-rehashed capture/results, dropped refusal slots, forged links, duplicate JSON keys, semantic replay disagreement, detached returned objects and actual command-line success/refusal.

Filesystem tests reject symlinked files/directories, FIFOs without blocking, malformed and oversized files. Reads are bounded to regular files and use the same open file descriptor for check/read. A failure yields no partial stdout or leaked host path. The implementation targets the already-used macOS/Linux development filesystem; no Windows runtime admission is claimed.

## Run the same retained evidence

```sh
PYTHONDONTWRITEBYTECODE=1 python3 research/issuer_inflection/2026-10-03/w0/verified_baseline_reader.py later_admission_refusal --format text
PYTHONDONTWRITEBYTECODE=1 python3 research/issuer_inflection/2026-10-03/w0/verified_baseline_reader.py later_admission_refusal --format json
PYTHONDONTWRITEBYTECODE=1 python3 research/issuer_inflection/2026-10-03/w0/test_baseline_source_binding.py
PYTHONDONTWRITEBYTECODE=1 python3 research/issuer_inflection/2026-10-03/w0/test_verified_baseline_reader.py
```

The fixture reader does not make a real publisher, rights check, source signature, canonical trial/exposure writer, production canary or broad issuer service exist. Those original program gates remain outstanding.

## Normal repository test entry

`tests/test_i3_baseline_fixture_consumer.py` now invokes the three existing consumer suites under the normal repository test discovery path. Its three parametrized entries pass locally and execute the same 42 baseline, 15 source-binding and 26 reader tests; these are not three additional empirical issuer observations. This is one test-only path outside the research prefix, not a new engine or a modification to the protected-identity guard. `evidence/READER_CI_ENTRY_TESTS.json` binds the exact entrypoint hash and command/result. Hosted CI still must run the new candidate, and the diagnosed evidence-placement failure is not waived by this local result.
