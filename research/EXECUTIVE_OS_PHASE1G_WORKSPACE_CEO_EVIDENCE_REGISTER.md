# Executive OS Phase 1G — Workspace CEO Evidence Register

**Status:** dated external and operator evidence for the protected Workspace CEO track  
**Evidence date:** 2026-08-15  
**Rule:** Workspace Agent models, reasoning controls, API contracts, tunnel behavior, usage accounting, and app approval semantics are volatile product behavior. The architecture uses stable logical capabilities and requires live acceptance before production authority.

---

## 0. Evidence classes

- **Official OpenAI documentation:** current provider-controlled documentation or release notes.
- **Operator observation:** behavior observed by Chairman Chris in the current Mastermind ChatGPT Business workspace.
- **Architecture inference:** a conservative design consequence derived from evidence; not represented as a product guarantee.
- **Unresolved:** a fact that must be proved by the X0 capability spike before production behavior depends on it.

No API key, tunnel runtime key, agent secret, account email, browser cookie, OAuth state, or other credential belongs in this file.

---

## 1. Workspace Agent external trigger

### Official evidence — developer reference

OpenAI's current Workspace Agent trigger reference documents a server-side trigger endpoint for a published agent. The documented request body contains:

```text
input
conversation_key?       # caller-defined stable conversation identifier
```

The request also supports `Idempotency-Key`; reusing a key is documented to return the original accepted outcome rather than enqueueing a duplicate trigger event.

The developer reference currently describes a successful trigger as HTTP `202 Accepted` with a `conversation_url`. With the beta header `OpenAI-Beta: workspace_agent_runs=v1`, the response may also include an `agent_trigger_run_id`, and a run-status endpoint reports states including queued, in-progress, suspended, completed, and failed.

The same developer reference states that the Workspace Agent's final response text cannot be retrieved through the API.

### Official evidence — Help Center discrepancy

The current Workspace Agents Help Center describes API triggers more conservatively and states that the trigger returns `202 Accepted` with no response body/run id and that the response is not retrievable through the API.

### Architecture implication

The two official surfaces currently disagree about response metadata.

Therefore:

- Mastermind correctness must depend only on the trigger being durably accepted plus a durable Executive OS CEO outcome;
- `conversation_url` and provider run id are optional observability fields until X0 proves their availability on this exact workspace;
- beta run-status telemetry is advisory and may not define canonical completion;
- trigger retry uses Executive OS activation identity plus `Idempotency-Key`;
- the final CEO result must be committed to Executive OS through a reviewed MCP action rather than scraped from the ChatGPT transcript.

### X0 proof required

- exact HTTP response body in this Business workspace;
- beta header/run-status availability;
- idempotency behavior after ambiguous timeout;
- `conversation_key` continuation behavior;
- trigger behavior after agent republish/version change.

---

## 2. Workspace Agent models and reasoning

### Official evidence

OpenAI's current Workspace Agents documentation states that builders can choose a model and reasoning effort. Current Business release documentation also describes reasoning-effort controls for Workspace Agents.

OpenAI's model/rate documentation is versioned and can lag or differ from the interactive picker. Current documentation should therefore be treated as evidence of the date, not a permanent model allowlist.

### Operator observation

Chairman Chris reports that the current Workspace Agent conversation UI in the Mastermind Business workspace exposes reasoning controls spanning Instant, Extra High, and Pro.

This is strong workspace-specific evidence that high-reasoning execution is available in the interactive Workspace Agent surface.

### Unresolved

The current documented external trigger request body exposes no `model`, `reasoning_effort`, or equivalent per-trigger selection field.

The live UI observation therefore does **not** establish how an externally triggered activation can be deterministically bound to Instant / Extra High / Pro.

### Architecture implication

Use stable logical classes:

```text
R0_FAST
R1_DEEP
R2_PRO
R3_CHAIRMAN
```

Do not store current UI labels/model names as permanent lifecycle semantics.

X0/X4 must select one proved routing design:

1. per-trigger reasoning selection if OpenAI exposes a trustworthy supported mechanism;
2. separate published Sol configurations sharing the same charter/MCP but pinned to distinct reasoning levels;
3. no autonomous R2 production if effective Pro execution cannot be proved.

No silent downgrade is allowed.

---

## 3. Apps, custom MCP, and write approvals

### Official evidence

OpenAI currently documents Workspace Agents as able to use apps/tools and custom MCP connections. The Workspace Agent/App configuration surface includes action approval behavior; write-capable actions may require confirmation unless configuration explicitly permits a different approval policy.

### Architecture implication

- Executive MCP remains the CEO's governed read/write surface;
- autonomous CEO production cannot assume a write action will execute unattended until X0 proves the actual app approval behavior;
- approval prompts are a runtime capability constraint, not something the model may bypass;
- a read-only Workspace CEO shadow can be tested before production writes are armed.

### X0/X5 proof required

- custom MCP connects from the intended published Workspace Agent;
- exact approval behavior for each candidate modifying action;
- application/action constraints cannot be bypassed with prompt text;
- unauthorized agent/app caller cannot acquire the production modifying surface.

---

## 4. Secure MCP Tunnel

### Official evidence

OpenAI currently documents Secure MCP Tunnel and an open-source `tunnel-client` for connecting ChatGPT and supported OpenAI products to an MCP server that is not publicly reachable.

The documented topology is customer-initiated/outbound: the tunnel client runs inside the customer environment, opens outbound HTTPS to OpenAI, receives queued MCP JSON-RPC work, forwards it to the configured local MCP server, and returns the response. No public inbound listener on the private MCP server is required.

The documented setup uses a tunnel identifier and runtime API credential. The tunnel can forward to MCP over supported local transports such as stdio/HTTP depending on configuration.

### Architecture implication

Secure MCP Tunnel is the preferred first candidate for PR #64's private Executive MCP because:

- PR #64 intentionally refuses public bind;
- a public reverse proxy is not required merely to make Workspace Sol reach the MCP;
- the tunnel can be hosted by a dedicated least-privilege principal outside the Executive DB and worker credential homes.

### Important non-implication

Secure connectivity does **not** by itself prove trusted caller identity for production writes.

PR #64's R6 caller-identity gate remains binding until the real transport demonstrates a trustworthy workspace/app/principal identity or a separately reviewed authorization layer is added.

### X1/X5 proof required

- outbound-only network behavior on the real host;
- local MCP remains non-public;
- tunnel process cannot read Executive SQLite directly;
- tunnel process cannot read worker/provider credentials;
- trusted caller identity and replay resistance for modifying actions;
- restart/reconnect behavior and bounded failure reporting.

---

## 5. Slack

### Official evidence

OpenAI currently supports Workspace Agent use from Slack in eligible Workspace Agent deployments.

### Architecture implication

Slack is an operator/human communication surface, not Mastermind's lifecycle authority or machine event bus.

A Slack-originated request may wake/interact with Sol, but consequential actions must still:

- re-read canonical Executive OS state;
- pass the same MCP authority and idempotency controls;
- commit a durable Executive OS outcome;
- never treat Slack message delivery as proof that an executive action completed.

Mastermind's autonomous machine wake path remains Executive OS → Workspace Agent trigger API.

---

## 6. Trigger API versus MCP

The two interfaces solve different problems.

```text
Workspace Agent Trigger API
  direction: Executive OS -> Sol
  purpose: wake/invoke cognition
  canonical company state: no

Executive MCP
  direction: Sol -> Executive OS tools (request/response)
  purpose: read canonical state and invoke governed actions
  canonical company state: Executive OS behind the gateway
```

### Architecture implication

Do not attempt to make MCP itself wake a sleeping Workspace Agent. Do not add Grok merely to bridge these two roles.

---

## 7. Grok/xAI evidence boundary

The existing Phase 1G provider evidence register already covers Grok Build as a supported worker/implementation surface with structured/headless options.

Nothing in current OpenAI Workspace Agent evidence requires Grok to serve as CEO wake broker.

### Architecture implication

- Grok remains available as an optional worker/specialist provider under the Agent Fabric;
- Grok may perform browser/research/implementation/critique work when commissioned;
- Grok failure or exhaustion must not stop the CEO wake/control loop;
- Grok does not choose company priority or the CEO reasoning class.

---

## 8. Production assertions that remain forbidden until proved

Do **not** state any of the following as production facts before X0/X1/X4/X5 evidence exists:

- “API triggers always return a conversation URL.”
- “API triggers always return a run id.”
- “The beta run-status endpoint is permanently available.”
- “A triggered run can select Pro dynamically in one request.”
- “A published Pro-configured agent necessarily runs Pro when triggered.”
- “The reasoning label exposed in UI is returned in machine-readable telemetry.”
- “Secure MCP Tunnel authenticates the exact Workspace Agent identity strongly enough for Executive writes.”
- “Workspace Agent modifying tools can always run without interactive confirmation.”
- “Conversation history is durable enough to replace Executive OS state.”
- “Slack is equivalent to a reliable machine event bus.”

Each may become true after a named acceptance proof. None is an architecture premise today.

---

## 9. Required live evidence artifact from X0

X0 must produce a machine/human-readable dated matrix similar to:

```text
capability                                    result       evidence
trigger 202 accepted                          PROVED       receipt ref
conversation_url returned                     ?            receipt ref
beta run id/status available                  ?            receipt ref
conversation_key continuity                   ?            receipt ref
Idempotency-Key duplicate suppression         ?            receipt ref
Instant external route                        ?            config/receipt
Extra High external route                     ?            config/receipt
Pro external route                            ?            config/receipt
actual effective reasoning identifiable       ?            evidence method
custom MCP read works                         ?            receipt ref
modifying action approval behavior            ?            receipt ref
Secure MCP Tunnel available                   ?            receipt ref
trusted caller identity for production write  ?            security receipt
```

Allowed values are `PROVED`, `REFUTED`, or `STILL_UNKNOWN`. A missing result is not silently interpreted as support.

---

## 10. Evidence refresh law

Before X5 production writes or X6 autonomous project initiation is armed:

1. re-check the official Workspace Agent trigger docs;
2. re-check Workspace Agent model/reasoning controls;
3. re-check Secure MCP Tunnel behavior/security documentation;
4. re-run the live X0 capability matrix if the Workspace Agent is republished or model configuration changes materially;
5. update this register when OpenAI changes the trigger request/response schema or approval model;
6. add a regression/acceptance test for every change that alters an architecture implication;
7. fail closed when a load-bearing capability is unknown or contradictory.

The current UI and documentation are evidence. Executive OS receipts remain runtime truth.