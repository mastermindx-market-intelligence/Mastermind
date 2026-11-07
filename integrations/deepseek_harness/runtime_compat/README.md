# Current full-app runtime compatibility

This ports the accepted governed-tool boundary to the complete DeepSeek Harness
donor at `687f282e8625c6b8d11ff58211a90524be2e4317`. It does not replace the
native app, install an Executive route, or authorize a provider. The separate
[attended app package](../ATTENDED_DEPLOYMENT.md) retains the donor's existing
native provider/auth/session owners and does not depend on paid worker admission.

## Changes

- Opt-in `strictDispatchBinding` captures the original tool definition and result
  owner, then rechecks cancellation, guards and exact identity at the actual
  native staged scheduler body boundary. Non-opted-in behavior is retained.
- Governed MCP admission binds a frozen catalog and selected raw tool names to
  one live generation. Discovery replacement retires the old generation before
  suspension; failure rolls back registration and namespace ownership.
- The pinned MCP client SDK receives the exact `toolDefinition`, preventing its
  schema-mismatch retry. Governed rich results are refused before attachment or
  model-service processing. Ordinary native MCP behavior is retained.
- A bound ACP workspace reader declares the known Python MCP 1.28.1 legacy
  protocol to SDK 2.2.0. Other MCP connections keep native automatic negotiation.
  This avoids a speculative discovery sibling for that fixed target.
- `integrations/acp_worker/dsh_native_agent.mjs` joins the existing inherited-FD
  v2 admission channel to one already-created native Agent. MCP discovery and
  the original owner ACK precede model work. Agent-owned restrictions survive
  MCP-fiber revocation. ACP remains the prompt/cancel/result lifecycle owner.

No donor checkout is edited. `prepare.py` verifies the clean pin, lockfile,
15 source inputs, patch identities and output hashes, then creates ignored
pristine/patched artifacts. A partial patch effect is refused for reconciliation.

## Reproduce focused proof

Use the already-built, dependency-installed accepted donor. This does not install
dependencies or use provider credentials.

```sh
python3 integrations/deepseek_harness/runtime_compat/prepare.py "$DSH_SOURCE"
cd integrations/deepseek_harness/runtime_compat
ln -s "$DSH_SOURCE/node_modules" node_modules  # fresh artifact directory only
DSH_SOURCE="$DSH_SOURCE" node "$DSH_SOURCE/node_modules/vitest/vitest.mjs" run --config vitest.config.mts
node build-native-fixture.mjs "$DSH_SOURCE"
cd ../../..
MMX_DSH_FULLAPP_NATIVE_SUPPLY="$PWD/integrations/deepseek_harness/runtime_compat" \
  python3 -m pytest -q tests/harness_convergence/test_dsh_fullapp_native_agent.py
```

The Python environment needs the repository test dependencies and MCP 1.28.1.
Without the explicit native supply, those five real-process tests skip; a skip is
not successful native-path evidence. The builder uses the donor TypeScript
decorator transform and verifies a single shared scheduler identity across the
native Agent and the admitted tool runtime.

Observed on 2026-11-07: **42 runtime cases passed**, followed by **five actual
native-process cases passed**. The latter prove read → observed search → actual
result through the current Agent/ACP/real source MCP reader; late revocation;
original-owner cancellation; wrong-contract refusal before model work; and
owner abort without inherited-tool reappearance. The refusal preserves the
adapter's conservative original-operation classification while independently
proving child and task cleanup.

## Evidence boundary

The native fixture uses a deterministic test model, explicit ephemeral test
persistence and a synthetic registry projection whose digests cannot become an
installed host packet. It runs the real source workspace reader, not the missing
canonical installed launcher. It does not prove paid provider access, durable
native JSONL storage, dedicated-UID containment, installed ACP activation or
production browser acceptance. The attended package independently retains the
full app's native persistence implementation.

Source identities are in `source-manifest.json`; generated receipts and bundles
remain in ignored `.cache/`. Preserve the [upstream license](NOTICE.md).
