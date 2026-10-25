# Hermes candidate qualification — non-operational first slice

**Status:** source-only policy and CLI-observation guards, plus a separate, disposable **actual Hermes CLI qualification** on ubuntu1. `BUILT_NOT_PROVEN` for both guards; **partial P1 proof** for an isolated CLI import/version/tool list. The real agent turn, authenticated tools, gateway, desktop, models, provider billing, Fabric integration and release remain `NOT_BUILT` or unqualified. No model or production service is authorized by this directory.

This is a path-disjoint subordinate qualification surface for the existing [Meta-CEO R2 implementation contract](../../docs/superpowers/specs/2026-10-12-meta-ceo-office-r2-implementation.md), [open-harness assessment PR #1841](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1841), and DSH incumbents [#1717](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1717), [#1790](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1790), [#1845](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1845). It does not select Hermes over DSH, deploy to any host, or authorize a new company control plane. The `integrations/hermes_mastermind/` namespace is **outside** this slice and may have an unresolved Fabric request; do not modify it until that exact original operation is reconciled.

## Source evidence, not an installed provenance claim

- Upstream [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent/tree/1c0cd667746d3395fe9e1b6c74f8f85952486f18) commit `1c0cd667746d3395fe9e1b6c74f8f85952486f18` (source sampled 2026-10-25); [MIT license](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/LICENSE). This is an inspection pin, **not** a built-dependency or release pin.
- [Official setup](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart) documents **Blank Slate** but says it still enables file and terminal toolsets; this static candidate therefore expressly disables those plus scheduling/delegation/other actor-capable toolsets.
- [Official toolsets](https://hermes-agent.nousresearch.com/docs/user-guide/features/tools), [config `agent.disabled_toolsets`](https://hermes-agent.nousresearch.com/docs/user-guide/configuration), [MCP filtering](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp), [profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles), and [remote dashboard security](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard) require version-specific functional testing before relying on any static config.
- See [deployment and decision addendum](../../research/HERMES_DEPLOYMENT_AND_INCUMBENT_COMPARISON_2026-10-25.md) for costs, hosting and next build gates.

## What is implemented

`preflight.py` loads **one local YAML document** using `yaml.safe_load`, allows exactly a small candidate shape, requires global disabled-toolset settings, rejects unexpected top-level options, plugins/MCP, external channels, wildcard toolsets, inline credential fields, unsafe model overrides and unqualified vision routes. It writes a no-overwrite, private JSON receipt containing only a SHA-256 of the source config and structural findings. **It never reads credentials**, imports Hermes, performs SSH, probes a port, launches subprocesses, or calls a provider. Failed validation is exit 2; input/write failures are exit 3; static pass is exit 0.

This first canary deliberately permits **no actual Mastermind tools**. Adding an authenticated, narrow **read-only** steward MCP server is a *separate* phase after its exact tool schema, audience, account binding and receiving-service enforcement are tested. Adding `mcp_servers` or allowing `terminal` to circumvent the check is not an implementation shortcut.

```sh
python3 -m pip install 'PyYAML>=6,<7'    # in an already-approved isolated environment
python3 integrations/hermes_qualification/preflight.py \
  --config integrations/hermes_qualification/example-readonly.config.yaml \
  --receipt /secure/new/unique-receipt.json
python3 -m unittest discover -v \
  -s integrations/hermes_qualification/tests
```

The `--receipt` path must be **absent** before execution. If one exists, inspect/reconcile it—never overwrite or blind retry. `PASS_OFFLINE_POLICY_ONLY` means static YAML policy fit, **not** app execution, a qualified model route, active tool registry parity, protected isolation, TCC/screen permissions, approved ingress, a valid RuntimeBinding or organizational acceptance.


## Actual upstream canary and toolset escape discovery (2026-10-25)

On directly connected **ubuntu1**, in private scratch directories only, acquired clean immutable `NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18` (369 MiB source), installed source-pinned Python 3.14.7 with `uv sync --frozen --no-dev` into a separate private venv, and ran the real `hermes --version`, `hermes --help`, `hermes tools list --platform cli` and `hermes serve --help`. The binary reports `Hermes Agent vgit.1c0cd66 (2026.9.24)`, Python 3.14.7. The CLI help path had no model call and the serve help path had **73 MiB peak RSS**; this is **not** resident gateway/GUI memory proof. The controlled HOME was empty of API keys and channels.

**Critical finding:** first candidate YAML with 19 disabled toolset names still had `todo` and `connections` **enabled** in the real CLI registry, despite global `toolsets: [clarify]`. The sample and static checker now require **all 24 observed non-clarify CLI/plugin toolsets disabled**; the corrected actual Hermes `tools list` reports **only `clarify` enabled** for the CLI platform. This is a narrowly scoped observation, not proof the Desktop client, remote gateways, plugin loading or receiving services cannot act.

`runtime_registry.py` consumes a previously captured `hermes tools list --platform cli` UTF-8 output (never launches Hermes); it checks exact expected built-in/plugin toolset names, detects any additional enabled tools or unknown new toolsets, and creates an exclusive private JSON receipt with `PASS_CLI_REGISTRY_OBSERVATION_ONLY` or `BLOCKED`. The parser's pinned upstream source SHA is an **assertion**, not cryptographic attestation of a submitted text file or executable. A future binary/extension update invalidates the toolset census and requires a fresh source review before claiming eligibility.

```sh
# In an approved, isolated, no-credential Hermes runtime only:
hermes tools list --platform cli > /secure/new/captured-toolsets.txt
python3 integrations/hermes_qualification/runtime_registry.py \
  --tool-list /secure/new/captured-toolsets.txt \
  --receipt /secure/new/unique-registry-receipt.json
python3 -m unittest discover -v -s integrations/hermes_qualification/tests
```

The captured text must be from an observed verified executable and restricted profile; it must not contain tokens or private content. The output parser validates **CLI only** and cannot inspect actual model calls, authorization, host/network isolation, TCC or a Desktop-injected `desktop_ui` tool.

## Follow-on acceptance, held

1. On an authorized disposable host or qualified cloud instance with accepted source custody, pin an upstream stable release and its verified dependencies. Capture observed source SHA and packaged artifact provenance. Never execute an uninspected remote install script, reuse somebody else's profile credentials, or install to a busy GUI host just because port 9119 is free.
2. Start a **separate unprivileged Hermes home** with a loopback-only dashboard or a separately authenticated gateway and no provider credentials; inspect the actual registered tools and refuse any unauthorized actor. Compare the observed registry against this zero-actuation configuration. Record process lifetime and RAM high-water, version, ports, restarts and startup failures.
3. Qualify GLM-5.3 text, GLM-5.3-Flash vision and a DeepSeek multimodal challenger through existing Model Router/Capacity and explicitly allowed provider terms. Measure task quality and cost with a real provider receipt; a model name and YAML file prove neither usage rights nor authentication.
4. Connect an **existing** read-only Control Room/Steward MCP surface with exact identity and least-privilege tool inclusion. The following write lane goes only through authenticated Executive ingestion and its original Job/Attempt/effect owners. Hermes's own `cronjob`, `delegate_task`, memory, subagent queue, tool registry or Bot Mode must not become independent company authority.
5. Run one real signed-in Chairman journey and one rejected/adversarial journey, with actual original-parent return consumption, denied side-effects, canceled/unknown-effects handling and an independent non-author review. Preserve Grok Secretary as the live bridge until these tests and rollback pass.

## Safety limitations

- This Python code is **not** an OS sandbox, signer, credential firewall, reference monitor or production deployment authorizer. A local actor can mutate YAML after inspection; dynamic plugins can appear after launch; private token data may be in an existing app's home. Enforce permissions at the **receiving services**, use separate least-privileged OS identities/containers as needed, and verify an exact config digest immediately before start.
- Do not give a Hermes Cloud or FlyHermes hosted operator direct access to local host SSH, Mastermind provider credentials, or the raw Fabric broker. Remote desktop work must use an existing approved, attenuated computer-use consumer and real Runtime/Capacity admission.
- A failed tool call or receipt is not evidence of no effect; check original identities before continuing. The source-only module creates no Executive Job and cannot accept a Fabric result.
