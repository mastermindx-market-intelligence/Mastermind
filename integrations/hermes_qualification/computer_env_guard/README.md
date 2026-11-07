# Pinned Hermes computer environment repair

The existing computer helpers could return a parent-derived environment after
the native secret sanitizer failed. This bundle removes both fallbacks and
preserves the existing readiness callers' failure contracts. It reuses the
native sanitizer and desktop placement policy.

## What changes

- `permissions._child_env` refuses helper import, execution, or invalid output.
- `cua_backend.sanitized_cua_driver_env` refuses environment preparation and
  sanitizer failures. Only a plain dictionary of string keys and values succeeds;
  `None` cannot accidentally request ambient environment inheritance.
- `_run_driver` applies its caller's declared `swallow` contract to environment
  preparation as well as the subprocess. The fixed `OSError` message is
  `CUA_DRIVER_ENV_UNAVAILABLE`, with exception chaining suppressed.

An `OSError` is deliberate: the existing runtime-contract reader catches that
family and reports not ready. A plain `RuntimeError` would escape that caller.
Daemon liveness and JSON discovery continue to return unknown on preparation
failure; permission grant returns failure without launching a driver.

## Source identity and reuse

The two target files are byte-identical at NousResearch/hermes-agent commits
`1c0cd667746d3395fe9e1b6c74f8f85952486f18` (selected qualification source) and
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` (observed installed M2 source).
`manifest.json` records Git blob identities, whole-file SHA-256 preimages and
postimages, patch digest, and exact test-fixture digests. The unchanged driver
caller fixture comes from the latter commit. Upstream source remains under MIT;
its copyright and license are retained in `UPSTREAM_LICENSE`.

Fixtures are the actual donor bytes, stored as `.source` files so they are not
imported as plugins or live code. This bundle creates no installer, credential
broker, permission grant, runtime binding, or alternative computer controller.

## Reproduce qualification

From the Mastermind source root:

```sh
python -m unittest -v integrations.hermes_qualification.computer_env_guard.test_guard
python -m unittest discover -v -s integrations/hermes_qualification/tests -p 'test_computer_env_guard.py'
python -m integrations.hermes_qualification.computer_env_guard.qualify --donor-root /absolute/path/to/qualified/hermes-agent
```

The qualifier reads exact donor files, validates their preimages, and checks and
applies the exact patch only in a disposable directory. It validates the resulting
postimages and leaves the supplied donor tree unchanged. Altered, partially
patched, or already-patched targets refuse. The CLI never executes Hermes or a
computer driver. Its `EXACT_SOURCE_PATCH_VERIFIED` result is source evidence,
with `installed=false` and `runtime_ready=false`.

The 18 tests execute AST nodes from the actual patched donor functions and
original callers. Dependencies, platform, sanitizer outcomes and subprocess
execution are controlled. They cover both fallback layers, import/preparation/
execution errors, invalid results, synthetic-secret error suppression, the three
sensitive readiness callers, permission status/grant, successful environment
forwarding, exact preimages, double application and unchanged donor files.
They do not requalify the sanitizer's complete filtering policy, import the full
Hermes application, grant host permissions, or exercise a real desktop.

The attempted local pytest invocation could not run because pytest was absent;
the complete focused suite ran through Python's standard unittest runner:
18 tests, zero failures or skips. The small collector in
`integrations/hermes_qualification/tests/test_computer_env_guard.py` includes
these same cases in the existing Python 3.12/3.13 qualification workflow.
Hosted CI and live installation are separate.

## Delivery and remaining consumer proof

This is a qualified source patch for the existing Hermes packaging/installation
owner. That owner must include the patch and verify the recorded postimages in
its immutable release before claiming an installed fix. Do not modify a running
vendor checkout or update a source digest without requalification. A release
rollback restores the original qualified release through that same owner; do
not roll back by re-enabling an environment fallback in a live process.

The broader teammate mission still owes backend/account allowlisting, native
session/task binding, real browser/desktop workflow, takeover, revocation and
original-effect reconciliation. This patch proves none of those by itself.

Source custody: parent operation `hermes-teammate-evolution-20261106-c3`, plan
PR #2159. The original bounded Fabric request
`hermes-teammate-computer-env-20261107-c3-01` returned
`REQUEST_REFUSED_BEFORE_LAUNCH`; its exact retained refusal records
`launch_attempted=false`, and its original controller terminated. The failure
cause was not disclosed beyond `prelaunch_FabricTaskError`. No second worker
was launched. The assigned principal completed this permitted source work on
the already assigned `sol/hermes-computer-env-guard-20261107-c3` branch.
