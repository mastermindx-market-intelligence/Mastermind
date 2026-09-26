# Attended Codex Fabric bootstrap: preparation without onboarding

This supplements `codex-astra-fabric-delegation.md`; it does not replace its authentication, source-release, provider, Capacity, or exact-parent acceptance gates. This is an attended-client composition utility, not an Executive worker launcher.

## What is connected

The bootstrap reads the reviewed `mastermind-astra.config.toml`, inspects the existing `mastermind-executive` registration in the **target project** context, and builds a Codex invocation with that parent policy plus the existing Keychain-backed header helper. The helper runs from the reviewed client source directory, while Codex runs against the requested project. Spaces, quotes, and shell metacharacters in paths are quoted independently from TOML values.

No global Codex configuration, repository `.codex/config.toml`, OAuth registration, credential item, routing alias, or RuntimeBinding is changed. Other server registrations and approval/sandbox settings are not rewritten.

## No-login preparation

Run from the reviewed client source checkout, using the actual non-secret installed coordinates:

```bash
python3 -m ops.codex_fabric.attended_parent \
  --url "$EXECUTIVE_LOOPBACK_MCP_URL" \
  --codex-bin "$REVIEWED_CODEX_BINARY" \
  --python-bin "$REVIEWED_PYTHON_BINARY" \
  --project-dir "$TARGET_PROJECT"
```

The default performs only a local `codex --cd <project> mcp list --json` census. It never adds a registration, invokes the header helper, logs in, exchanges a token, launches a model turn, or submits an Executive intent.

For a known `not_logged_in` census, the JSON result is `PREPARED_NOT_AUTHENTICATED`, with explicit `authenticated_tool_discovery_proven=false`, prepared argv, source/project paths, and hashes of the profile/helper inputs. These hashes identify input bytes; they are not a signed release attestation, a whole-dependency-tree digest, or proof that the selected interpreter can authenticate.

Preparation refuses missing/duplicate/disabled/different registrations, existing header or environment credential sources, native OAuth or unknown authentication status, conflicting visible tool restrictions, malformed census, invalid paths, and profiles that enable native agents or widen the one-child ceiling. It does not overwrite or repair those conditions.

Codex may report `unsupported` when authentication-status data is absent. This recognized case returns `PREPARED_AUTH_STATUS_UNRESOLVED` with `launch_allowed=false`: configuration remains inspectable, but `--launch` refuses before executing Codex or the helper. Unrecognized/malformed states still refuse preparation. A true `launch_allowed` is only this attended wrapper's metadata preflight result, never authentication proof or an Executive execution grant.

## Explicit attended launch after onboarding

The same command with `--launch` performs a fresh preflight, then replaces the wrapper process with the prepared Codex invocation. No extra flags/prompts are passed through that could override the frozen client composition. A launch failure is returned without retry, provider fallback, or a second process attempt.

The existing header helper remains the sole client credential consumer. Its interpreter/dependencies and macOS Keychain custody must be qualified through the existing enrollment path before launch. Unsupported hosts remain unqualified. Codex's `required=true` setting makes an unavailable Executive MCP a startup failure rather than silently continuing without Fabric.

Only the existing five Executive tool names are allowlisted on this server: `executive_state`, `executive_inbox`, `executive_job`, `ceo_intent_status`, `submit_ceo_intent`. Preparation is not authenticated discovery or evidence that these tools are currently callable.

## Holds that remain unchanged

The legacy Auth0 DCR `EFFECT_UNKNOWN` operation must not be retried, cleared, renamed, or failed over. Account onboarding, tenant reconciliation, an attested production Astra-capable Codex generation, external-provider admission, real child execution, and exact-parent result consumption remain separately gated. This source utility does not close those gates.

## Verification

`python3 -m unittest tests.test_codex_fabric_attended_parent -v` uses temporary fake Codex/interpreter executables. It proves composition, refusal, actual helper cwd/quoting, default no-login behavior, project-bound census, and one-shot explicit launch mechanics without contacting an account or provider. It is not a real Codex protocol or end-to-end production canary.
