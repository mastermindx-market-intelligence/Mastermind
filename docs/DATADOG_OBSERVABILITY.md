# Datadog production observability

Mastermind has one Datadog destination: the Chris Wong organization on the GitHub Student plan.
That organization is hosted on Datadog US5 (`us5.datadoghq.com`); US1 is not its intake site.
The MastermindX trial organization is not a production observability authority.

## ChatGPT transport boundary

As of 2026-09-13, Datadog's packaged ChatGPT Preview app is US1-only. It cannot be
used to query or prove the canonical US5 Student organization. Never dual-ship or move
production telemetry to US1 just to satisfy that app. Datadog's official regional MCP
service has a US5 endpoint; any future Mastermind/Workbench exposure must remain a thin
transport to that existing US5 authority, with no second telemetry store, auth database,
queue, lifecycle, or retry plane.

The first production slice is the authoritative VPS running `mastermind.service`.
The host installer is `scripts/install_datadog_vps.sh`; it configures:

- Datadog Agent 7 host metrics;
- Single Step Instrumentation for Python APM;
- journald collection scoped to `mastermind.service`;
- unified `env`, `service`, `team`, and `role` tags;
- shared `service` / `env` identity across APM and journald logs;
- release correlation through `DD_VERSION=<exact deployed Git SHA>`.

It deliberately does not enable AppSec, IAST, profiling, or another control plane.
Observability remains telemetry/advisory and must not affect portfolio execution.

This slice does **not** claim per-request trace-to-log correlation. The current Uvicorn/journald
format does not emit `dd.trace_id` / `dd.span_id`; adding those fields is a separate application
logging capability and must be proven on real request logs before being called live.
## Installation

Run only on the authoritative VPS, as root, with an API key from the canonical Datadog org:

```bash
DD_API_KEY='<runtime secret>' ./scripts/install_datadog_vps.sh
```

The key is supplied to Datadog's official installer through the process environment. The Agent
necessarily persists it in Datadog's own root-owned configuration; Mastermind must not duplicate it
in Git, a systemd drop-in, `/etc/macro-api.env`, or deployment logs.

The installer first requires the existing Mastermind health endpoint to pass. It then installs or
updates the Datadog Agent using Datadog's official Agent 7 installer, enables host-level Python SSI,
configures log collection, restarts the Agent, and finally restarts `mastermind.service` so the
injected tracer is loaded. Once the Datadog installer begins, an exit guard protects the
application-side rollout: any later setup failure restores a touched Mastermind systemd override,
removes host SSI only when this rollout introduced it using Datadog's supported
`dd-host-install --uninstall` path, and rechecks Mastermind health. Pre-existing SSI is left intact.
The Agent package/config may remain for an idempotent repair rerun; it is not another application
control plane. Future deployments refresh the Datadog version tag from the exact release SHA before
restart, and rollback restores the previous tag.
## Production proof

A successful installer exit proves only the host-local configuration. Do not call Datadog
`PROVEN_LIVE` until the Chris Wong organization independently shows all of the following:

1. the authoritative VPS in host inventory with `env:production` and `role:authoritative-vps`;
2. `service:mastermind-api` journald logs from `mastermind.service`;
3. a real FastAPI request trace for `service:mastermind-api`;
4. the public Mastermind health path still passes after instrumentation.

Only after those producer paths are live should dashboards, SLOs, and monitors be treated as useful
operational surfaces. Browser RUM is a separate frontend producer and requires its own Datadog RUM
application/client token; it is not implied by Agent/APM onboarding.
