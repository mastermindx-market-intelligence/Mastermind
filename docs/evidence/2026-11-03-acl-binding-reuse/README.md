# Native ACL binding reuse

This source slice removes repeated libc symbol loading and ctypes signature setup
from the macOS ACL observer. It reuses only the lazy native function tuple.
Every file/anchor identity check, ACL read, entry enumeration, errno check, and
ACL-handle cleanup still runs. Failed binding setup is not cached.

## Exact source scope

- Base: `b4a5a8925c6c1412dac67ba296cf65ee81c4d4c8`.
- Baseline `control_plane/fs_security.py` SHA-256:
  `aad443d4d712cc2483a912b6371779bd56f05ee08bc07bff9b3c3008ab0b52e7`.
- Candidate file SHA-256:
  `4a9aa64a34cbc84601fbfd5ea68b9792eb1c5558116c48d52c797ad0c83758a5`.
- Production change: import `lru_cache`; decorate the existing binding factory
  with `lru_cache(maxsize=1)`; document the boundary; correct its existing return
  annotation from four items to the actual three.
- AST source-segment comparison against the base found all other 15 top-level
  function/class definitions byte-identical. This includes `has_macos_acl`,
  whose source segment has SHA-256
  `3816562349cb88a835ee7a691841341ba98ac0961c0dfe3603a564cf29900140`.
- No existing exact source/identity pin for this file was found in the relevant
  tests. The ordinary release closure/seal must incorporate the new file bytes
  when a future release adopts the change. No installed closure was changed.

## Regression evidence

The five new tests use real temporary descriptors with controlled native results
to prove fresh absent/present/absent/error observations, one binding setup,
descriptor identity refusal, enumeration-error preservation through cleanup,
uncached binding failure, and unchanged non-Darwin behavior.

Before the production change: **2 failed, 3 passed**. Both failures observed
repeated library setup. After the change, this focused group passed:

```sh
/tmp/mmos-cloud-py312/bin/python -m pytest -q -o addopts='' --tb=short \
  tests/test_fs_security_native_bindings.py \
  tests/test_fs_security_symlink_acl.py \
  tests/test_subscription_provider_credential.py \
  tests/test_executive_persistent_origin.py \
  tests/test_executive_installer_native_acl.py
```

Result: **80 passed, 80 skipped** in 1.64 seconds. The skips are existing
platform/native cases on the Linux cloud runner.

Adding the Studio home/library ACL and attended worker definition test modules
produced **10 failed, 144 passed, 100 skipped, 32 subtests passed**. All ten
failures reproduced with the exact baseline source in those three modules
(**10 failed, 64 passed, 20 skipped, 32 subtests passed**): six fixture checks
encounter the writable `/tmp` ancestor before ACL classification, and four
worker-definition fixtures use UID/GID 0 where positive dedicated principals
are required. No production policy or unrelated test was weakened.

## Actual M2 native measurement

`measure-native.py` ran once as UID 501 on arm64 macOS with Python 3.12.10:

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B \
  /private/tmp/mmos-acl-bindings-measurement-20261103-c4-01/measure.py
```

The process completed successfully in 5.09 seconds. Both source variants
observed a real ACL changing **absent → present → absent** on a new empty file
owned by the runner. The driver removed that fixture. It then compared five
paired samples per mode, 512 native observations per sample, alternating the
variant order. The result includes all 20 timing rows.

| Observation mode | Baseline median CPU | Candidate median CPU | Baseline / candidate |
| --- | ---: | ---: | ---: |
| Held descriptor and expected identity | 49.615 µs | 2.729 µs | 18.18× |
| Observer owns the path descriptor | 88.037 µs | 29.916 µs | 2.94× |

These are isolated observer CPU measurements. Wall time was noisy under host
load; this evidence makes no end-to-end maintenance acceptance speed claim.
The running 09b acceptance, installed source, credentials, runtime and service
configuration were untouched.

- Exact raw receipt: [`native-microbenchmark.json` at the original commit](https://github.com/mastermindx-market-intelligence/Mastermind/blob/9a0b1c50affabab716de54ee8077928a61a94651/docs/evidence/2026-11-03-acl-binding-reuse/native-microbenchmark.json), SHA-256
  `c55677ea9391b86279ccbec6f03a24889d90666180886849423995e6aecdaeb6`.
- Current metrics projection: `native-microbenchmark-metrics.json` preserves all
  timing samples, source hashes, native transition results and measurement
  context, omitting the raw host UID. It identifies the exact original receipt
  and commit; it is not represented as the original receipt.
- Exact measured driver: `measure-native.py` at original published commit
  `9a0b1c50affabab716de54ee8077928a61a94651`, SHA-256
  `30527aab0a4a86da8bbd32a8f227cf1c43fa15a8ad12b933a78071c5a71e86fb`.

For reproduction, place the driver in a new private temporary directory beside
`baseline_fs_security.py` extracted from the exact base commit and
`candidate_fs_security.py` from this source slice. The driver verifies their
hashes and the pinned interpreter before creating its disposable fixture. It
requires its output `result.json` to be absent and never imports installed
Mastermind code. The current driver also requires `--expected-uid` with the
explicitly selected, verified unprivileged runner UID; there is no UID default.

## Hosted CI repair: explicit benchmark identity

Initial automatic run `41592711859`, attempt 1, at head
`9a0b1c50affabab716de54ee8077928a61a94651` failed job `125772874394`
(`pytest shard 0`) in `test_d8_template_topology_and_protected_defaults`.
The protected-identity guard correctly rejected the benchmark helper's
hard-coded UID and the numeric UID in its raw evidence JSON. The same test failed locally on the candidate; binding its Git
HEAD reads to the exact base commit passed. The ACL implementation was not the
cause.

The helper now takes a required `--expected-uid` argument, refuses non-positive
identities, and still requires both real and effective UIDs to match before
loading source or creating a fixture. Six focused tests cover missing input,
root/negative input, real/effective mismatches, and successful admission through
to source validation: **6 passed**. The unchanged protected-identity scanner
also passes the repaired helper. No guard or production identity policy changed.
The complete affected D8 group plus the driver admission tests passed:
**234 passed, 23 deselected** in 7.69 seconds.

The committed JSON is now a metrics projection without host-identity metadata;
the original raw receipt remains unmodified at the original commit linked above.
The actual runner identity remains documented as a historical observation in
this narrative. No numeric identity is introduced into executable/configuration
data to represent that observation.

The current driver SHA-256 is
`6058ddf7e19cab9e268119e01bfbc9fba976f7cd19a7b93fc77db5e09d21e627`.
It has not been rerun on M2 as part of this repair. Production source and the
original native measurement receipt remain byte-identical, and the exact driver used for
the recorded run remains available at the original commit above.
