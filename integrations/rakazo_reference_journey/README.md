# Rakazo reference journey readiness

Source preparation for HC-P1B.T2. This directory is a launcher and evidence
surface for the pinned Rakazo `pnpm test:topology` journey. It does not run
that journey.

The protected base at authoring was `3095d09f1789a5b8002503beae872774c297b1a5`.
`origin/master` was that same commit: there was no newer protected source to
absorb. This change does not edit `#1852` or any other carrier.

## Donor

`https://github.com/elie222/rakazo.git` at
`c5e66e010ee3f3166d2ad216f928a75a0b9a2218`, Apache-2.0.
`topology.patch` is a derivative of that commit's topology runner and compose
file. The upstream license text is blob `35e6c9da4c9916cec4f785e20fa63a7cd680cdaf`
(`LICENSE`). The Apache-2.0 terms are at
<https://www.apache.org/licenses/LICENSE-2.0>.

| Path | Git blob | SHA-256 |
| --- | --- | --- |
| `packages/testkit/src/cli/topology.ts` | `6e56619314d78fecc1e3425a7b83d93ebd7bb190` | `1af4e4dd296c54aa23093c747bf4840b695f5da5877e659ea5f95af9a002dd74` |
| `infra/compose/docker-compose.topology.yml` | `ae71f3743242b7a69b90198b59d907f9f5a3b9f6` | `ca4297bda99a2bd2f1ba06a964e8a7572bbb9f7671ea3b9375f03572015252de` |
| `package.json` | `3f7685b6d87c4e269166c3bc22484eab1ca01b39` | `9f8c7ab2bd4ba6b50f5a66fc78bea92ed39a8c0154b3e96070eeb8b6013b740a` |
| `pnpm-lock.yaml` | `b7d840b21e81727a743dcc98134f05642e05cb40` | `6387f7a0e8783c8a01085dea0edeb718569e3a18443fc1d0fa75a47498931573` |
| `pnpm-workspace.yaml` | `f124691fa90eca20e1bbdfd4563af4c31594bfb3` | `25178b418b7047d388fd11f88a537d6a93cd10cc5bf1f5c26a8f1c8b57da6fc7` |

The native entry remains `pnpm test:topology` (`tsx packages/testkit/src/cli/topology.ts`).
The donor command fixes `--file`, so a `COMPOSE_FILE` value cannot install an
override. `topology.patch` is a zero-context unified diff applied with
`git apply --unidiff-zero` only to an attempt-owned copy. The result
is a derived runner, not an unchanged upstream run. Upstream health, queued-run,
file-byte, isolation, and recovery assertions stay in the derived runner.

`offline.compose.yaml` is the second Compose file. It sets
`RAKAZO_LIVE_MODEL_CATALOG=off` on `api` and `worker`, keeps scripted runtime,
Graphile, and the Docker sandbox, and requires attempt-owned app and computer
image tags. It does not use `rakazo/app:topology` or `rakazo/computer:topology`.
The derived compose file replaces the host Docker socket mount with
`${MMX_ADMITTED_DOCKER_SOCKET:?...}`. A project name does not qualify the shared
daemon the supervisor would otherwise mount.

## What `run.py readiness` does

1. Creates an attempt-owned root, config, cache, and temp directories.
2. Replaces the child environment with that closed set before the first child.
   Caller `NODE_OPTIONS`, npm config, provider keys, OIDC, proxies, and Docker
   host/context values are not inherited.
3. Admits immutable Git objects for the pin above, with replacement refs,
   hooks, fsmonitor, attributes, filters, and global/system Git config
   suppressed. A caller checkout is not adopted and is not deleted.
4. Derives the runner only after the patch, override, and upstream bytes match
   the hashes pinned in `run.py`.
5. Reads `/usr/bin/docker` and `/var/run/docker.sock` if they exist. It does
   not pull, build, or start containers. The admitted daemon id set is empty.
6. Prints one receipt and removes the owned root. Cleanup that is not proven
   stays `UNKNOWN`. Exit zero is not a clean-resource receipt. There is no
   automatic retry.

```sh
python3 -B integrations/rakazo_reference_journey/run.py readiness
```

`--object-store PATH` reads an existing Git directory and does not fetch. The
objects still have to be the pinned blobs. This placement's receipt status is
`READINESS_BLOCKED` when admission or daemon isolation is not proven.
`source_phase` may be `SOURCE_PREPARED` when the bytes were admitted and
derived. That is not a journey result.

`JOURNEY_PASSED`, `RUN_FAILED`, and `EFFECT_UNKNOWN` are named in the receipt
schema and are rejected for this placement. Unit fixtures cannot mint them.
Execution stays `NOT_RUN`. The planned command, which is not spawned, is
`pnpm test:topology -- --mmx-attempt <not-written>`.

## Limits

Deadlines are finite: readiness overall 180 seconds, and a recorded execution
budget of 900 seconds that is not armed. Logs are truncated at 8192 bytes and
redacted. Donor pnpm `9.15.0` is required and is not installed here. Observed
Node on a Cursor VM is not adopted as the journey toolchain.

A later one-attempt execution needs a separate reviewed continuation, a
non-empty admitted isolated daemon, and the exact donor toolchain. This
directory does not approve, merge, purchase, or change credentials.
