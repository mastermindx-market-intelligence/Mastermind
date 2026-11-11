# Native Hermes GitHub App plugin

This is the disjoint native-loader composition for parent #2286. It depends on
PR #2285's adapter and issuer at `67bc92c3bbc3990dc3e1196ccfc9d1b2ff3fbdac`.
Those files are not duplicated here. The child source base/procedure pin is
`5c3d3885234358aefb97ecdbc59be0864df14f8b`. Source qualification is not installed
Hermes adoption, authorized credential binding, or the real two-bot canary.

## Inspected native owners

The repository pins NousResearch/hermes-agent at
`1c0cd667746d3395fe9e1b6c74f8f85952486f18` in
`integrations/hermes_runtime/constants.py`. The integration uses these actual
APIs, exercised from that source in the focused tests:

- `hermes_cli/plugins.py`: `get_plugin_manager()`, `PluginManager.scope_key`,
  `PluginContext.profile_name`, and `PluginContext.register_tool(...)`.
- `hermes_cli/profiles.py`: `get_active_profile_name()` derives the active
  profile from the native Hermes home, including its context-local override.
- `hermes_cli/plugins_loader.py`: `_load_plugin()` binds the manager's home,
  imports a user-directory plugin and calls exactly `register(ctx)`.
- `hermes_cli/plugins_manifest.py`: `parse_manifest_file(...)` reads
  `plugin.yaml`; `plugins_ledger.py` owns `unload()` and registration handles.
- `tools.registry`: scoped registration snapshots; `registration_lifecycle`:
  the existing replacement transaction. No replacement registry is added.

`integrations/hermes_harness/native_selected_child_plugin` and its existing
manager-private `ConsumerSlot` are the incumbent composition pattern. The new
GitHub slot holds only that profile's resolver/issuer and registration carrier;
it does not own authentication, source grants, sessions, leases, or key storage.

## Executable composition and installation contract

The installable directory package is `integrations/hermes_github_plugin/`.
Setuptools includes its `plugin.yaml` in the wheel. Its manifest deliberately
advertises no tools before registration, so unbound discovery exposes nothing.
Its single-argument `register(ctx)` calls the new host composition, which in
turn calls the existing `hermes_github_native.register_native_tool` unchanged.

The authorized installed host supplies `bind_native_host(manager, binding=...,
issuer=..., app_bot_login=..., package_path=...)` before native plugin discovery:

- `manager` is the real per-profile `get_plugin_manager()` result.
- `binding` is PR #2285's `HostHermesGitHubBinding`, with the host's existing
  authenticated current-session resolver. It returns each session owner's
  **retained** `HermesGitHubApp`, never a newly reconstructed client on lookup.
- `issuer` is the existing `GitHubAppInstallationTokens`, with exactly
  `AUTHORING_PERMISSIONS`, the authorized App/install/repository, and the sealed
  custodian's private-key callback. No key path or credentials enter plugin
  config, a model argument, an environment lookup, or this installation API.
- `app_bot_login` is the verified actor for that enrolled issuer. Every resolved
  client must have this actor and the **same issuer object**, plus the exact
  current profile/session and valid host source grant.
- `package_path` is the exact authorized user-plugin directory containing the
  packaged `__init__.py` and `plugin.yaml`. The installed source must already be
  qualified by its existing source/deployment owner. This function does not copy
  files or establish source trust by itself.

The existing installer places that directory in the chosen profile's
`plugins/mmx_github` and makes the integrated Mastermind package importable.
The existing host explicitly selects `plugins.isolation: in_process`; this
module neither changes that setting nor falls back from isolated plugin-host
mode. It accepts only the bound user-plugin path/name/profile. Native loading
owns the registration and unload; there is no service, startup daemon, separate
installer control plane, or automatic activation in this change.

Binding/discovery does no key read, token issuance, or HTTP request. Tool
arguments remain the queued adapter's closed schema: no credential, App,
repository, role or session selection. Distinct sessions may share one issuer
and actor while retaining separate operation/branch/audit identity. A failed
registration retains the original context and exception in the same manager
slot; it cannot be retried or replaced through this API. Repeated identical
binding returns that same slot. The native `PluginContext.on_unload` hook calls
`close()`: it invalidates captured handlers, disposes and verifies the known
native lease, then removes only its own manager slot. The authorized host may
explicitly bind again before native reload. A delayed old cleanup cannot remove
a newer binding. Registration or cleanup uncertainty retains the original slot
and exception and forbids rebind/retry until the original host reconciles it.

This in-process seam is not a sandbox against arbitrary Python executing as the
trusted host. The real enrolled host must protect its resolver and custodian;
an untrusted role process must not receive the broad App key or issuer object.

## Qualification and remaining dependency

`tests/test_hermes_github_plugin.py` runs the real pinned directory loader,
manifest parser, profile context, tool registry and unload with mocked GitHub
HTTP and ephemeral in-memory test keys. It covers two current sessions and two
profile managers sharing an App actor/issuer, wrong or expired binding, wrong
actor or issuer, missing key, model-supplied authority, unauthorized source
paths, collisions, retained registration errors, unload, and unsupported
loading mode. The loader/isolation source hashes are checked against the
existing repository provenance fixture before execution.

Set `HERMES_LEADERSHIP_UPSTREAM` to the pinned donor for those tests, as in the
incumbent native tests. On a base without #2285, the test explicitly skips for
that missing source dependency; such a skip is **not** qualification. During
this child, the exact queued modules were loaded from a temporary inspection
directory via `integrations.__path__` and tested together, without modifying or
cherry-picking the queued branch. No stub replaced the native loader.

The original parent #2286 should consume this child's local commit after
#2285's protected integration, rerun the combined exact candidate, and use its
existing release path. No new overlapping PR is needed from this child.

Production remains held on the authorized native host composition: provision
an approved least-privilege authoring identity through the existing custodian,
bind the real current-session/source-grant resolver, qualify the installed
package, and authorize the original two-session canary. The existing broad
App `4768173` / installation `157661343` is **not enrolled by this source**;
its root-only key and tokens must not be distributed. No App registration,
credential read, live token issuance, membership/billing change, service start,
or runtime installation occurred. The M2 `FLEET_ROUTE_PREFLIGHT_REFUSED` remains
on its original carrier; this child is not an alternate route to that host.

## Local qualification receipt (2026-11-08)

With the exact #2285 source overlay and the pinned Hermes donor above:

- `tests/test_hermes_github_plugin.py`, queued `tests/test_hermes_github_app.py`,
  `tests/test_github_review_app_token.py`, and
  `integrations/hermes_harness/tests/test_native_tool_registration.py`:
  **105 passed, 1 skipped, 2 subtests passed**. The single skip checks upstream
  Git checkout HEAD; the donor is an exact-commit public source archive, not a
  Git checkout. The actual loader tests ran, including source-hash checks.
- `TMPDIR=/private/tmp` is needed on this Mac for the incumbent native tests'
  string comparison of temporary paths; `/tmp` resolves to `/private/tmp` in
  Hermes. The initial broader run exposed this test-path mismatch and a
  collision fixture that incorrectly used the same plugin owner. The final
  run uses a genuinely foreign owner and the canonical temporary path.
- A local wheel of the combined source built with `pip wheel --no-deps
  --no-build-isolation`. Its plugin manifest, entry point and host module were
  compared byte-for-byte with this branch. This is package proof, not a live
  runtime install. The wheel is temporary qualification output, not a release.
- `git diff --check` passed. No remote publication or deployment was performed.

The separate read-only native review found that the first candidate retained
its slot after a clean native unload. The repair uses the inspected native
`PluginContext.on_unload` API and adds unload/rebind/reload and uncertain-cleanup
tests. Successful cleanup removes only its own slot; failed registration or
cleanup remains retained. Old captured handlers remain refused after reload.

Reproduce after the parent has integrated #2285 with the same pinned donor:

```sh
TMPDIR=/private/tmp \
HERMES_LEADERSHIP_UPSTREAM=/path/to/pinned/hermes-agent \
MASTERMIND_HERMES_VENDOR_ROOT=/path/to/pinned/hermes-agent \
python -m pytest tests/test_hermes_github_plugin.py \
  tests/test_hermes_github_app.py tests/test_github_review_app_token.py \
  integrations/hermes_harness/tests/test_native_tool_registration.py -ra
```

Independent technical review: native read-only task
`/root/github_plugin_review` inspected the frozen source and accepted the
lifecycle repair with no remaining findings on that delta. The reviewer
independently ran all **30 plugin tests** with the same #2285 source overlay and
pinned Hermes donor. Accepted host-module SHA-256:
`84a2e5960230b07248cd6714c6348e9717355de4d7482ceaad700cae87d8cbb9`;
accepted test-module SHA-256:
`2ac7a24231c8d0953284b53cc0495f587fdd228dbebd3566e37e574c66f8f107`.
The author consumed and repaired the finding on this original local branch.
This is technical assurance, not a formal GitHub approval or production proof.
