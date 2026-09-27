# Attended Sol/Astra coordinator bundle

This is an optional client configuration bundle, stacked on Mastermind #981 and
#633. Source tests and native prompt rendering do not make it production-authorized.
Do not activate an unreviewed source candidate, change the default Codex profile,
clear the historical DCR marker, or treat inherited credentials as child authority.

## Inspect before installation

From the exact accepted source checkout, inspect the intended existing Codex home:

```sh
python3 -m ops.codex_fabric.orchestrator_bundle --codex-home /absolute/codex/home
```

The receipt provides `bundle_digest`, per-file digests, and missing paths. Conflicting
content or symlinked path components refuse. Inspection never calls Codex, credentials,
servers or models and performs no writes. The two roles and optional parent profile
must be delivered together; #981's existing Sol role is reused byte-for-byte.

After source acceptance and the applicable installation authorization, installation
is explicit. Supply the exact inspected digest as `--expected-bundle-digest` and add
`--install` to that same command. Existing matching files are not rewritten. Roles
are published first; the optional profile last. Global `config.toml`, the incumbent
`mastermind-astra.config.toml`, unrelated roles and all auth state are left alone.
A partial or uncertain result is reconciled by inspection of the same target. Never
blindly repeat, overwrite, roll back, delete a marker or change destination as recovery.

## Compile effective configuration

A named profile alone is insufficient. Trusted project settings can increase the
concurrency limit. Use `--configuration-overrides` instead of `--install`, supplying
the same expected digest, to emit the exact verified `key=value` list. The existing
attended launcher consumes each list item as its own `-c` argument, preserving argv
boundaries; it must not shell-evaluate the strings. Absolute role paths avoid cwd
ambiguity. Revalidate the installed bundle and current permission grants at launch.
This utility never launches a model and never changes admission or OAuth state.

The native regression deliberately sets a project limit of three children. It
observes four slots including root without the explicit settings, and two with them.

```sh
MASTERMIND_CODEX_NATIVE_PROBE=/absolute/path/to/codex \
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python3 -m pytest -o addopts='' -q -p no:cacheprovider \
  tests/test_codex_orchestrator_native_config.py
```

The test uses temporary credentialless homes, file-only credential stores and
`debug prompt-input`. It starts no provider turn. This probe was exercised with
Codex 0.154.0; a changed native prompt shape must be requalified, not assumed.

## Execution gates still owed

`role_selection_proven=false` and `child_enforcement_proven=false` remain explicit.
The profile lists Sol and Astra coordinator roles; it does not prove other native
roles cannot be selected. A model name does not prove the served model. A read-only
role file does not prove the child's effective parent/MCP permissions.

The next accepted canary must bind one coordinator to its own admitted responsibility,
exact native handle, permission ceiling and existing RuntimeBinding. Only then may
that coordinator lead separately admitted worker Jobs through the existing Executive
Fabric. The role files request no native recursion, but this is not an enforced role boundary
on the qualified 0.154.0 binary; see the negative proof below. No new queue, broker,
credential path or parent identity is introduced here. Consume #1000's existing
attended launch owner rather than create a second launcher. Preserve #633's original
Auth0 EFFECT_UNKNOWN operation and #981's exact-head independent review request.

## Existing-launcher integration

The optional bundle is now consumed by ops/codex_fabric/attended_parent.py through
--orchestrator-bundle-digest. See codex-fabric-attended-bootstrap.md for the exact
preflight and proof boundary. The installer still never launches. The launcher
uses the current native home, revalidates local inputs before exec, and never
converts unsupported/unknown authentication into launch readiness. Source remains
Draft/HOLD pending independent review and the existing parent release gates.

## Native machinery qualification, without real model inference

The opt-in tests/test_codex_orchestrator_native_spawn.py drives the installed Codex
binary using the existing OHF AppServerClient and scripted loopback Responses events.
Every case uses an empty temporary HOME/CODEX_HOME with file-only credential stores;
the script is a test fixture, not a production provider or delegation route.

Both named roles create native child threads with the expected parentThreadId,
agentRole, requested model and high reasoning effort. The child request selects Sol
or Astra as specified. A child shell write to its test project is denied by the native
read-only sandbox. A child completion is delivered into the next request for its exact
parent. Cleanup proves the private native process group and loopback listener stopped.
None of this proves real Astra/Sol inference, Executive identity, MCP authority,
worker Job admission, a production RuntimeBinding, or production Wake.

**Do not raise the one-child cap based on role-local configuration.** On Codex
0.154.0 both children retain the native spawn_agent tool despite agents.enabled=false
in their role files. The normal one-child limit rejects a grandchild attempt with
agent thread limit reached. In an isolated test-only two-child configuration, a
real native grandchild is created even with agents.max_depth=1. Therefore the
one-child invocation limit is the observed recursion guard; the role flag and depth
setting are not substitutes. No live limit was changed to perform this test.

Generic worker/explorer/default roles are also advertised. The named-role profiles
are not a hard allowlist. Keep global installation and broader fanout held until
current native support and existing Executive capability/admission owners can prove
the exact required restrictions. Installer receipts intentionally keep broad
role_selection_proven and child_enforcement_proven false.
