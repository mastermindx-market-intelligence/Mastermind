# Paper host-routing prototype: repaired in isolation, not integrated

This research directory is not imported or staged by the Paper service. Do not
install or enable it. The production-source changes remain those published at
`cf6e9c954fc34d3b7f3f0dfffef6a022652afab2` in PR #1017. Their full CI passed.

## Original findings and repairs

Commit `c071d6cf9486ec02ebdc94185950db60521ac091` preserves the original
prototype and its negative evidence. Seven structural checks passed, but eleven
adversarial checks found two defects: the real MCP SDK could not resolve a
function-local postponed return annotation, and lost local edit replies were
incorrectly labeled EFFECT_NONE. Both defects are repaired in this research copy.

The repair also removes the known Python-3.11-only asyncio.timeout dependency,
using the installed SDK's AnyIO cancellation scope instead. Python 3.10 syntax
validation passes; runtime execution on Python 3.10 has NOT been demonstrated.
Known-host paths with spaces are quoted for SSH configuration parsing. Refusal
codes remain typed, and successful/uncertain modifying replies must preserve the
requested operation identity. Successful prepare replies must match the file ID.

## Validation limits

- Seven structural checks: PASS.
- Eleven adversarial checks: PASS.
- Fourteen real SDK stdio checks with synthetic backends: PASS.
- No SSH, Paper application, tunnel, key, login, or fleet endpoint was contacted.
- The stdio checks prove message registration/serialization, not fleet operation.
- New evidence is repair_evidence.json; original evidence.json remains historical.

## Integration remains blocked

The platform blocked the earlier production integration patch before execution.
It was not retried, split, rephrased, delegated, or moved to another account.
The repairs above affect only this unconnected research directory. Production
mcp_server.py and direct_service.py remain unchanged. A passing prototype does
not clear the platform restriction, confer access, or authorize deployment.

## Architecture still requiring acceptance

One active stdio tunnel client per seat; controlled host selection inside the
existing Paper service; configured opaque fleet references only. Any adopted
remote path must consume existing authorized host/SSH bindings, enforce backend
identity and schema, preserve original-host effects, and never auto-failover an
uncertain write. The proposed configuration is not an authorization registry or
proof that an existing fleet interface accepts it. Native-worker Paper grants are
separate from attended ChatGPT routing and must not be invented as its prerequisite.

Next: independent architecture/security review and permitted integration recovery,
then qualified-host/per-account real-path acceptance. Do not roll out this module
or copy one seat's live tunnel across hosts. Live Ryan/M1/Mini 1 gates remain separate.
